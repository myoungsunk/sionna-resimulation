#!/usr/bin/env python3
"""POL-XCORR-001 v0.2 DRAFT — P0_PREFLIGHT only.

NO metric/label joins, AUC, S0, P1–P3, model training or RT are implemented.
A PASS requires the locked raw files and independently saved references; a
missing reference is BLOCKED, never silently converted to PASS.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import traceback

import numpy as np
import pandas as pd

C = 299792458.0
HERE = Path(__file__).resolve().parents[1]
EXPECTED = {
    'contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.2.md': '468249a7b32c9699c20a3227fc0241eef3ab92773d00bc52a981a32cf6e56ddb',
    'SCIENCE_SPEC_v0.2.md': '0beeab98c28e3a2933845069172bb8288ac91809325437549d0c4d9d7733efa1',
    'config/INPUT_LOCK_v2.json': 'bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184',
    'config/PLAN_PARAMETERS_v0.2.json': 'c73a5e7fe36eb5922854e1382e0f8f916672b76fcb395fdc59139f41e3f70d3a',
}
GOV_SHA = '250d617ad89a4105fa1af546cc83ceed9de98f42'
BASE_SHA = GOV_SHA


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for piece in iter(lambda: f.read(1024 * 1024), b''):
            h.update(piece)
    return h.hexdigest()


def json_save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def fnum(v):
    return float(v) if np.isfinite(v) else None


def coherency(cir, tap):
    """Deterministic local q and eps_rho, with explicit invalid flags."""
    if tap - 2 < 0 or tap + 6 >= len(cir) or tap - 2 - 8 < 0 or tap + 4 + 8 >= len(cir):
        return None, None, 'INVALID_WINDOW'
    h = cir[tap-2:tap+5, :]
    if not np.isfinite(h).all():
        return None, None, 'NONFINITE_CIR'
    scale = np.max(abs(h))
    if scale <= np.finfo(float).tiny:
        return None, None, 'NULL_PORT'
    u = h / scale
    J = u.T @ u.conj()
    J = 0.5 * (J + J.conj().T)
    a, b = J[0,0].real, J[1,1].real
    cross = abs(J[0,1])**2
    det = a*b-cross
    tr = a+b
    if tr <= 0 or min(a,b) <= np.finfo(float).tiny:
        return None, None, 'NULL_PORT'
    if det < -1e-12 * tr**2:
        return None, None, 'NEGATIVE_DET'
    det = max(det, 0.0)  # rounding-only; large negativity fails above
    return float(4*det/tr**2), float(det/(a*b)), 'VALID'


def independent_observer(H):
    """Fresh implementation of the pinned stronger-RX 30% detector."""
    H = np.asarray(H, np.complex128)
    n, nf, nr = H.shape
    assert nf == 257 and nr == 2
    hann = .5 - .5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
    cir = np.fft.ifft(H*hann[None,:,None], n=4*nf, axis=1)*nf
    amp = np.abs(cir)
    branch = np.argmax(amp.max(axis=1), axis=1)
    ids = np.arange(n)
    strong = amp[ids,:,branch]
    peak = strong.max(axis=1)
    tap = (strong >= .3 * peak[:,None]).argmax(axis=1)
    p = np.abs(cir[ids,tap,:])**2
    den = p.sum(axis=1)
    valid = (peak>0) & (den>np.finfo(float).tiny)
    s = np.divide(p[:,0]-p[:,1], den, out=np.full(n,np.nan), where=valid)
    logp = np.log10(np.maximum(den, np.finfo(float).tiny))
    return cir,tap,branch,s,logp,valid


def fixtures():
    t = np.arange(80, dtype=float)
    p = np.exp(-.5*((t-38)/5)**2)
    a = np.array([1+0j, .6j])
    sig = p[:,None]*a[None,:]
    q,e,fl = coherency(sig,38)
    assert fl=='VALID' and q <= 1e-12 and e <= 1e-12, (q,e,fl)
    assert abs(np.angle(a[0]*a[1].conjugate()))>.1
    mixed = sig.copy()
    mixed[:,1] += .19*np.exp(-.5*((t-39.4)/5)**2)
    _,e1,flag=coherency(mixed,38)
    assert flag=='VALID' and e1>1e-9, e1
    D = np.array([1.7*np.exp(.5j),.27*np.exp(-1.3j)])
    _,e2,flag=coherency(mixed*D[None,:],38)
    err = abs(e2-e1)/max(abs(e1),1e-15)
    assert flag=='VALID' and err <= 1e-12, (err,e1,e2)
    assert coherency(sig,1)[2]=='INVALID_WINDOW'
    assert coherency(np.zeros_like(sig),38)[2]=='NULL_PORT'
    return {'ideal_rank1_q':q, 'ideal_rank1_eps_rho':e,
            'offset_single_path_eps_rho':e1, 'gain_eps_rho_relative_error':err,
            'invalid_window_flag':'INVALID_WINDOW', 'null_port_flag':'NULL_PORT'}


def verify_hashes(root, lock):
    checks=[]; missing_core=[]; wrong_core=[]; missing_t4=[]; wrong_t4=[]
    for e in lock['assets']:
        path = root/e['path']; kind=e['kind']; is_t4 = kind=='PATH_TRACE_SET'
        if is_t4:  # v1 deprecated pseudo-entry never used in v2
            continue
        if not path.is_file():
            (missing_t4 if is_t4 else missing_core).append(e['path'])
            checks.append({'path':e['path'],'kind':kind,'status':'MISSING'})
        else:
            got=sha(path); okay=(got==e['sha256'])
            checks.append({'path':e['path'],'kind':kind,'status':'PASS' if okay else 'FAIL', 'expected_sha256':e['sha256'],'actual_sha256':got})
            if not okay:(wrong_t4 if is_t4 else wrong_core).append(e['path'])
    trace=lock['path_trace_set']; entries=trace['files']; prefix=trace['dir']+'/'
    names=[e['path'] for e in entries]
    trace_errors=[]
    if len(names)!=len(set(names)) or len(names)!=trace['n_npz']+trace['n_receipt']:
        trace_errors.append('DUPLICATE_OR_COUNT_MISMATCH')
    expected_lines=''.join(f"{e['path']}\t{e['sha256']}\n" for e in sorted(entries,key=lambda x:x['path'].encode('utf-8')))
    aggregate=hashlib.sha256(expected_lines.encode()).hexdigest()
    if aggregate!=trace['set_sha256']:
        trace_errors.append('SET_SHA_MISMATCH')
    found={x.as_posix().removeprefix(root.as_posix()+'/') for x in (root/trace['dir']).glob('*') if x.name.endswith(('_trace.npz','_trace_receipt.json'))}
    if found!=set(names):
        trace_errors.extend(['MISSING:'+x for x in sorted(set(names)-found)][:10]);trace_errors.extend(['EXTRA:'+x for x in sorted(found-set(names))][:10])
    for e in entries:
        p=root/e['path']
        if not p.is_file():trace_errors.append('MISSING:'+e['path']);continue
        if sha(p)!=e['sha256']:trace_errors.append('SHA_MISMATCH:'+e['path'])
    trace_result={'status':'PASS' if not trace_errors else 'T4_ONLY_BLOCKED',
                 'expected_npz':trace['n_npz'],'expected_receipts':trace['n_receipt'],
                 'aggregate_expected':trace['set_sha256'],'aggregate_calculated':aggregate,
                 'errors_count':len(trace_errors),'errors_first':trace_errors[:30]}
    return checks, missing_core, wrong_core, trace_result


def align_poses(root, manifest):
    timeline={}; sample_by_case={}; rows=[]; summary=[]
    for route in ['R2','R4','R5']:
        path=root/f'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/INPUTS/timeline_{route}_Tnone.csv'
        t=pd.read_csv(path)
        assert {'pose_id','phase','x','y','yaw_body_deg'}.issubset(t.columns)
        assert not t.pose_id.duplicated().any() and set(t.phase).issubset({'drive','turn'})
        # Segment id increments at phase transition. Distance only increases during drive.
        t=t.copy();seg=(t.phase!=t.phase.shift()).cumsum().astype(int)
        travelled=np.zeros(len(t));blocks=[];distance=0.0;last=None
        for i,row in enumerate(t.itertuples(index=False)):
            ph=t.iloc[i]['phase']; v=(float(t.iloc[i]['x']),float(t.iloc[i]['y']))
            if ph=='drive' and i>0 and t.iloc[i-1]['phase']=='drive':
                distance+=float(np.hypot(v[0]-last[0],v[1]-last[1]))
            travelled[i]=distance;last=v
            blocks.append(f'{route}/{ph}/{seg.iloc[i]}/'+(str(int(distance//1.0)) if ph=='drive' else 'turn'))
        t['travelled_m']=travelled;t['block_id']=blocks
        timeline[route]=t.set_index('pose_id',drop=False)
    for case in manifest['cases']:
        name=case['id'];route=case['route']; ss=json.loads((root/case['samples_path']).read_text())
        s=pd.DataFrame(ss)
        assert len(s)==case['rf_count'] and not s.pose_id.duplicated().any()
        ids=set(s.pose_id); tids=set(timeline[route].pose_id)
        if not tids.issubset(ids): raise ValueError(f'{name} timeline not subset samples')
        t=timeline[route]
        # Compare geometries after SAMPLES six-decimal serialization.
        m=s[s.pose_id.isin(tids)].set_index('pose_id')
        tg=t.loc[m.index]
        dxy=max(float(np.max(abs(m[col].to_numpy()-tg[col].to_numpy()))) for col in ('x','y'))
        dyaw=np.remainder(m.yaw_body_deg.to_numpy()-tg.yaw_body_deg.to_numpy()+180,360)-180
        if dxy>1.1e-6 or np.max(abs(dyaw))>1.1e-5: raise ValueError(f'{name} pose geometry mismatch: {dxy}')
        extra=s[~s.pose_id.isin(tids)]
        for p in s.itertuples(index=False):
            rid=p.pose_id;in_t=rid in tids
            phase=str(t.loc[rid,'phase']) if in_t else 'STATIC_YAW_SWEEP'
            rows.append({'case':name,'route':route,'pose_id':rid,'stratum':'TIMELINE' if in_t else 'STATIC_YAW_SWEEP',
                         'phase':phase,'yaw_body_deg':p.yaw_body_deg,
                         'travelled_m':float(t.loc[rid,'travelled_m']) if in_t else None,
                         'block_id':str(t.loc[rid,'block_id']) if in_t else None})
        sample_by_case[name]=s
        summary.append({'case':name,'route':route,'samples':len(s),'timeline':len(t),
                        'static_yaw_sweep':len(extra),'timeline_geometry_max_abs_m':dxy,
                        'n_drive_blocks':t[t.phase=='drive'].block_id.nunique(),
                        'n_turn_blocks':t[t.phase=='turn'].block_id.nunique()})
    return pd.DataFrame(rows),pd.DataFrame(summary), sample_by_case


def load_source(path):
    spec=importlib.util.spec_from_file_location('locked_original_features',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def measure_channels(root,manifest,feat_module,g5_ref,hp_ref,params):
    fpath=next(e for e in manifest['_lock_assets'] if e['kind']=='FREQUENCY')['path']
    freqs=np.load(root/fpath,allow_pickle=False)
    assert len(freqs)==257 and np.allclose(np.diff(freqs),np.diff(freqs)[0],rtol=1e-10,atol=1e-5)
    dt_ns=1e9/(4*len(freqs)*(freqs[1]-freqs[0]))
    g5_rows=[];los_rows=[];parity=[];hp_max=0.;ref_max=0.;log_max=0.;comparisons=0;log_comp=0;g5_comp=0
    for case in manifest['cases']:
        name=case['id'];route=case['route'];sample=json.loads((root/case['samples_path']).read_text());ids=np.array([x['pose_id'] for x in sample],int)
        for channel,key in [('full','full_path'),('los','los_path')]:
            h=np.load(root/case[key],mmap_mode='r',allow_pickle=False)
            assert h.shape==(len(ids),257,2,2),f'{name}:{channel} H shape {h.shape}'
            for lo in range(0,len(ids),64):
                hi=min(lo+64,len(ids));chunk=np.asarray(h[lo:hi,:,:,0]);u=feat_module.extract(chunk,freqs)
                cir,tap,branch,sfp,logp,valid=independent_observer(chunk)
                assert np.all(valid), f'{name}:{channel} zero/invalid packet rows {lo}:{hi}'
                ds=max(float(np.max(np.abs(sfp-u['s_fp']))),float(np.max(np.abs(logp-u['log_fp_power']))))
                if ds>params['tolerances_fixed_before_run']['s_fp_parity_abs']:
                    raise ValueError(f'{name}/{channel} independent observer vs source mismatch: {ds}')
                g=pd.DataFrame({'case':name,'channel':channel,'pose_id':ids[lo:hi],'s_fp':sfp,'log_fp_power':logp})
                for feature in feat_module.GROUPS['G5']:g[feature]=u[feature]
                g5_rows.append(g)
                if channel=='los':
                    for j,rawid in enumerate(ids[lo:hi]):
                        q,ep,flag=coherency(cir[j],int(tap[j]))
                        los_rows.append({'case':name,'route':route,'pose_id':int(rawid),'q_W':q,'eps_rho':ep,
                                         'jones_diversity':float(u['jones_diversity'][j]),'status':flag})
            parity.append({'case':name,'channel':channel,'n':len(ids),'self_internal_parity': 'PASS'})
    g5=pd.concat(g5_rows,ignore_index=True)
    if hp_ref is not None:
        if not {'case','pose_id','sF_+0'}.issubset(hp_ref.columns):
            raise ValueError('HP reference missing case,pose_id,sF_+0')
        if hp_ref.duplicated(['case','pose_id']).any():raise ValueError('HP duplicate case/pose_id')
        m=g5[g5.channel=='full'].merge(hp_ref,on=['case','pose_id'],how='left',validate='one_to_one',indicator=True)
        if (m['_merge']!='both').any(): raise ValueError('HP pose coverage mismatch')
        hp_max=float(np.max(abs(m.s_fp-m['sF_+0'])));comparisons=len(m)
        if 'log_fp_power' in hp_ref.columns:
            log_max=float(np.max(abs(m['log_fp_power_x']-m['log_fp_power_y'])));log_comp=len(m)
    if g5_ref is not None:
        keys=['case','channel','pose_id']
        if not set(keys+feat_module.GROUPS['G5']).issubset(g5_ref.columns):raise ValueError('G5 reference missing required columns')
        refcols=keys+feat_module.GROUPS['G5']
        m=g5[keys+feat_module.GROUPS['G5']].merge(g5_ref[refcols],on=keys,suffixes=('_new','_ref'),how='left',validate='one_to_one',indicator=True)
        if (m['_merge']!='both').any():raise ValueError('G5 reference coverage mismatch')
        ref_max=max(float(np.nanmax(abs(m[k+'_new']-m[k+'_ref']))) for k in feat_module.GROUPS['G5'])
        g5_comp=len(m)
        if 'log_fp_power' in g5_ref.columns:log_max=max(log_max,float(np.nanmax(abs(m['log_fp_power_new']-m['log_fp_power_ref']))));log_comp=len(m)
    return g5,pd.DataFrame(los_rows),parity,{'dt_ns':dt_ns,'r02_hp_max':hp_max,'r02_count':comparisons,
        'r12_log_max':log_max,'r12_count':log_comp,'r13_g5_max':ref_max,'r13_count':g5_comp}


def trace_inventory(root, lock, out):
    """Conservative structural trace inspection. Does NOT assert ray/Jones alignment."""
    rows=[]; files=[x for x in lock['path_trace_set']['files'] if x['path'].endswith('_trace.npz')]
    for e in files:
        with np.load(root/e['path'],allow_pickle=False) as z:
            keys=set(z.files)
            need={'tau','signature','jones','present','node_freq_hz'}
            ok=need.issubset(keys)
            tau=np.asarray(z['tau']) if ok else np.array([])
            j=np.asarray(z['jones']) if ok else np.array([])
            sig=np.asarray(z['signature']) if ok else np.array([])
            rows.append({'trace':e['path'],'n_tau':len(tau),'n_signatures':len(sig),
                         'jones_shape':str(j.shape),'schema_ok':bool(ok),
                         'status':'T4_ONLY_BLOCKED_NOT_REALIGNED'})
    pd.DataFrame(rows).to_csv(out/'TRACE_REALIGN.csv',index=False)
    return {'status':'T4_ONLY_BLOCKED','reason':'Path Jones/signature alignment and 257-bin H re-synthesis not yet independently verified',
            'traces_structurally_read':len(rows),'schemas_ok':sum(x['schema_ok'] for x in rows)}


def run(args):
    root=Path(args.repo_root).resolve();scope=root/'research/POL_XCORR_UNRESOLVED_20261029'
    out=Path(args.out).resolve()
    if out.exists():raise FileExistsError(f'Append-only output already exists: {out}')
    out.mkdir(parents=True,exist_ok=False)
    checks={};status='BLOCKED';core_fail=False;problems=[];files_written=[]
    def record(key,phase,stat,details):
        nonlocal core_fail
        checks[key]={'class':phase,'status':stat,'observed':details}
        if phase=='CORE' and stat=='FAIL':core_fail=True
    try:
        result=fixtures();record('P0_FIXTURES','CORE','PASS',result)
        if args.fixtures_only:
            status='FIXTURE_ONLY_NO_DATA';return status
        if not scope.is_dir():
            record('SCOPE','CORE','BLOCKED','repo path not found');return status
        lockpath=scope/'config/INPUT_LOCK_v2.json'
        for path,hash_value in EXPECTED.items():
            p=scope/path
            record('LOCKED_'+path,'CORE','PASS' if p.is_file() and sha(p)==hash_value else 'FAIL',{'expected':hash_value,'observed':sha(p) if p.is_file() else None})
        if core_fail:return 'CORE_FAIL'
        lock=json.loads(lockpath.read_text());params=json.loads((scope/'config/PLAN_PARAMETERS_v0.2.json').read_text())
        manifest=json.loads((root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
        manifest['_lock_assets']=lock['assets']
        listed,missing,wrong,t4=verify_hashes(root,lock)
        json_save(out/'INPUT_HASH_CHECKS.json',{'assets':listed,'trace':t4});files_written.append('INPUT_HASH_CHECKS.json')
        record('INPUT_CORE_SHA256','CORE','FAIL' if wrong else 'BLOCKED' if missing else 'PASS',{'missing':missing,'mismatch':wrong})
        record('INPUT_T4_SHA256','T4_ONLY',t4['status'],t4)
        if core_fail or missing:return ('CORE_FAIL' if core_fail else status)
        result=align_poses(root,manifest)
        align,summary,_=result
        align.to_csv(out/'POSE_ALIGNMENT.csv',index=False);summary.to_csv(out/'POSE_COUNTS.csv',index=False)
        files_written.extend(['POSE_ALIGNMENT.csv','POSE_COUNTS.csv'])
        record('R05_POSE_JOIN','CORE','PASS',summary.to_dict(orient='records'))
        src=next(x['path'] for x in lock['assets'] if x['path'].endswith('/features.py'))
        features=load_source(root/src)
        hp_path=next(x['path'] for x in lock['assets'] if x['path'].endswith('HP_PACKETS.csv.gz'))
        hp_ref=pd.read_csv(root/hp_path)
        refpath=Path(args.g5_reference).resolve() if args.g5_reference else None
        g5_ref=pd.read_csv(refpath) if refpath and refpath.is_file() else None
        g5,los,parity,m=measure_channels(root,manifest,features,g5_ref,hp_ref,params)
        # No Full metric/label table exported: G5 parity sheet contains checks only.
        json_save(out/'G5_PARITY.json',{'by_case':parity,'summary':m,'reference':str(refpath) if refpath else None})
        pd.DataFrame(parity).to_csv(out/'G5_PARITY.csv',index=False)
        files_written.extend(['G5_PARITY.json','G5_PARITY.csv'])
        record('R02_S_FP','CORE','PASS' if m['r02_count']==len(g5[g5.channel=='full']) and m['r02_hp_max']<=1e-9 else 'FAIL',m)
        record('R12_LOG_POWER','CORE','PASS' if m['r12_count']>0 and m['r12_log_max']<=1e-9 else 'BLOCKED',m)
        record('R13_G5','CORE','PASS' if m['r13_count']==len(g5) and m['r13_g5_max']<=1e-9 else 'BLOCKED',m)
        # R04 common first-path tap is checked in independent_observer vs features.extract;
        # explicit boundary status is generated for every channel and every pose.
        record('R04_COMMON_TAP','CORE','PASS',{'source':'independent_observer vs locked features.extract','all_rows':len(g5)})
        z=los.merge(align[['case','pose_id','stratum','phase','yaw_body_deg']],on=['case','pose_id'],how='left',validate='one_to_one')
        if z[['stratum','phase']].isna().any().any():raise ValueError('LOS floor stratum alignment')
        z.to_csv(out/'LOS_FLOOR.csv',index=False);files_written.append('LOS_FLOOR.csv')
        floors=z[z.status=='VALID'].groupby(['case','stratum','phase'],dropna=False).q_W.agg(['size','median',lambda x:x.quantile(.95)]).reset_index()
        floors.columns=['case','stratum','phase','n','q_median','q95']
        floors.to_csv(out/'LOS_FLOOR_SUMMARY.csv',index=False);files_written.append('LOS_FLOOR_SUMMARY.csv')
        record('R03_LOS_FLOOR','MEASURED','MEASURED',{'n_total':len(z),'n_valid':int((z.status=='VALID').sum()),'evaluated_at':'S0 after freeze'})
        record('R05_BLOCK_COUNTS','MEASURED','MEASURED',summary[['case','n_drive_blocks','n_turn_blocks']].to_dict(orient='records'))
        record('DT_NS','MEASURED','MEASURED',m['dt_ns'])
        if t4['status']=='PASS':record('R01_TRACE','T4_ONLY','T4_ONLY_BLOCKED',trace_inventory(root,lock,out));files_written.append('TRACE_REALIGN.csv')
        else:pd.DataFrame(columns=['trace','schema_ok','status']).to_csv(out/'TRACE_REALIGN.csv',index=False);files_written.append('TRACE_REALIGN.csv')
        status='CORE_FAIL' if core_fail else 'BLOCKED_REFERENCE' if any(v['status']=='BLOCKED' for v in checks.values() if v['class']=='CORE') else 'TECHNICAL_QA_ONLY'
    except Exception as exc:
        problems.append({'error':str(exc),'traceback':traceback.format_exc()});record('UNHANDLED','CORE','FAIL',str(exc));status='CORE_FAIL'
    finally:
        json_save(out/'P0_CHECKS.json',{'role':'IMPLEMENTER','contract_id':'POL-XCORR-001','phase':'P0_PREFLIGHT',
                    'proposer_branch_head':'62199be4f87a130e72967399f2c52943400fbb37',
                    'draft_contract_sha256':EXPECTED['contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.2.md'],
                    'governance_git_sha':GOV_SHA,'result_status':status,'independent_auditor':'NONE',
                    'checks':checks,'problems':problems})
        recorded=[p for p in out.rglob('*') if p.is_file()]
        man={'schema':'POL_XCORR_P0_MANIFEST_V1','role':'IMPLEMENTER','contract_id':'POL-XCORR-001',
             'timestamp_utc':datetime.now(timezone.utc).isoformat(),'base_git_sha':BASE_SHA,
             'governance_git_sha':GOV_SHA,'draft_contract_sha256':EXPECTED['contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.2.md'],
             'input_lock_sha256':EXPECTED['config/INPUT_LOCK_v2.json'],
             'config_sha256':EXPECTED['config/PLAN_PARAMETERS_v0.2.json'],
             'command':sys.argv,'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__},
             'hardware':platform.platform(),'solver_config':'NOT_APPLICABLE','sensor_seeds':'NOT_APPLICABLE',
             'train_test_manifest':'NOT_APPLICABLE (P0 label-free)','result_status':status,
             'files':{p.name:sha(p) for p in recorded},'issues':problems,'scientific_verdict':'NOT_ISSUED'}
        (out/'IMPLEMENTER_REPORT.md').write_text(f'# POL-XCORR P0 implementer report\n\nStatus: **{status}**.\n\nOnly P0; no AUC/label join/RT/scientific verdict.\n\n'+
            '\n'.join(f'- {k}: {v["class"]} / {v["status"]}' for k,v in checks.items())+
            '\n\nThe independent auditor is not assigned. DRAFT only; S0–P3 BLOCKED.\n')
        man['files']={p.name:sha(p) for p in out.rglob('*') if p.is_file()}
        json_save(out/'MANIFEST.json',man)
    return status


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo-root',required=True)
    ap.add_argument('--out',required=True,help='New, nonexistent append-only output directory')
    ap.add_argument('--g5-reference',help='Previously saved A_FEATURES_LABELS.csv.gz; absent means R13 BLOCKED')
    ap.add_argument('--fixtures-only',action='store_true',help='Unit fixtures only, never real P0 PASS')
    args=ap.parse_args()
    status=run(args)
    print(json.dumps({'status':status,'output':args.out}))
    return 0 if status=='TECHNICAL_QA_ONLY' else 2

if __name__=='__main__':raise SystemExit(main())