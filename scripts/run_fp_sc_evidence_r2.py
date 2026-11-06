"""Offline evidence interventions and separately contracted C-only detection.

No production provider, selector, SourceFFD or EKF update. All outputs are new.
"""
import os
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import argparse, csv, gzip, hashlib, importlib.util, json, math, platform
import subprocess, sys, time, traceback, unittest
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import psutil
process = psutil.Process()
process.cpu_affinity(process.cpu_affinity()[:3])
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R/'src'))
from qclean_uwb.fp_sc.followup.contracts import Policy, sha256, write_json, verify_files
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup import detection, selection, numerics, engine
from qclean_uwb.fp_sc.followup.numerics import cir_from_spectrum, raw_detection
from qclean_uwb.fp_sc.e0_baseline import SPEC
B = R/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001'
PKG = B/'PRIOR_EVIDENCE_R2_20261106'
BASE = B/'E0_20261105/A2_20261105/RUN_E0_A2_001/baseline'

def stop_check():
    s = os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if s and Path(s).exists():
        raise RuntimeError('MANAGED_STOP_REQUESTED')

def arrays(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}

def wrap(x):
    return (x+np.pi) % (2*np.pi)-np.pi

def past(nis, mask, t):
    """Only timestamps j<k in the preceding five seconds; rejected rows retained."""
    out = np.full((len(t), 3), np.nan)
    for k in range(len(t)):
        start = np.searchsorted(t, t[k]-5, side='left')
        out[k, 1:] = [k-start, np.count_nonzero(~mask[start:k])]
        if k > start:
            out[k, 0] = np.mean(nis[start:k])
    return out

def scenarios():
    out = [dict(id='NOMINAL', direction='none', m=0., deg=0., profile='constant', scale=1., shared=False)]
    for scale in (.1, .01):
        out.append(dict(out[0], id=f'P_ONLY_{scale}', scale=scale))
    # Paired identical error paths at each covariance scale; no result-dependent selection.
    for profile in ('constant', 'jump', 'drift'):
        for sign in (-1, 1):
            for m, deg in ((.1, 5.), (.5, 15.), (1., 45.)):
                for direction, pos, yaw in [('radial',m,0.),('tangent',m,0.),('none',0.,deg),
                                             ('radial',m,deg),('tangent',m,deg)]:
                    for scale in (1., .1, .01):
                        ident = f'{profile}_{direction}_{sign*pos}_{sign*yaw}_P{scale}'
                        out.append(dict(id=ident,direction=direction,m=sign*pos,deg=sign*yaw,
                                        profile=profile,scale=scale,shared=False))
    for sign in (-1, 1):
        for direction,m,deg in [('world_x',1.,0.),('none',0.,45.)]:
            out.append(dict(id=f'SHARED_{direction}_{sign}',direction=direction,m=sign*m,
                            deg=sign*deg,profile='constant',scale=1.,shared=True))
    assert len({s['id'] for s in out}) == len(out)
    return out

def stat(a):
    a = np.asarray(a); finite = a[np.isfinite(a)]
    return dict(n=int(a.size),available=len(finite),missing=int(a.size-len(finite)),
                median=float(np.median(finite)) if len(finite) else None,
                p95=float(np.quantile(finite,.95)) if len(finite) else None,
                maximum=float(np.max(finite)) if len(finite) else None)

def evidence(out, manifest, core, grid):
    sums=[]; checks=[]; input_hashes={}; total=0; events=[]
    baseline_index=json.loads((BASE/'ARTIFACT_HASHES.json').read_text())
    columns=['dr_position_difference_m','dr_yaw_difference_rad','P_position_trace_m2',
             'P_yaw_variance_rad2','evaluation_position_error_m','evaluation_yaw_error_rad']
    for cid,spec in manifest['cases'].items():
        stop_check(); n=spec['expected_rows']; total+=n
        a=arrays(R/spec['online_npz']); tr=arrays(BASE/(cid+'_REPLAY.npz'))
        source=BASE/(cid+'_REPLAY.npz'); assert sha256(source)==baseline_index[source.name]
        input_hashes[str(source.relative_to(R))]=sha256(source)
        t=a['t']; assert len(t)==n and np.all(np.diff(t)>0)
        assert np.array_equal(t,tr['t']) and np.array_equal(a['pose_id'],tr['pose_id'])
        dr=np.empty_like(a['prior']); dr[0]=a['x0']
        for k in range(1,n):
            dr[k]=core.transition(dr[k-1],a['ds'][k],a['gy'][k],a['dt'][k])[0]
        # Reference is joined exclusively for evaluation columns, never passed to past()/DR.
        ev=arrays(R/spec['evaluator_npz'])
        assert np.array_equal(t,ev['t']) and np.array_equal(a['pose_id'],ev['pose_id'])
        past_features=past(tr['nis'],tr['mask'],t)
        midpoint=n//2; changed=tr['nis'].copy(); changed[midpoint:]=1e12
        assert np.array_equal(past(changed,tr['mask'],t)[midpoint],past_features[midpoint],equal_nan=True)
        one_step=max(float(np.max(abs(core.transition(tr['x'][k-1],a['ds'][k],a['gy'][k],a['dt'][k])[0]-a['prior'][k]))) for k in range(1,n))
        assert one_step<1e-10
        delta=a['prior'][:,:2]-np.asarray(SPEC['anchor'][:2]); norm=np.linalg.norm(delta,axis=1)
        assert np.all(norm>1e-12), 'ANCHOR_DIRECTION_UNDEFINED'
        radial=delta/norm[:,None]; tangent=np.column_stack((-radial[:,1],radial[:,0]))
        values=np.empty((len(grid),n,len(columns)))
        base_diff=a['prior'][:,:2]-dr[:,:2]; base_yaw=wrap(a['prior'][:,2]-dr[:,2])
        shared_max=0.
        for j,s in enumerate(grid):
            amplitude=np.ones(n)
            if s['profile']=='jump': amplitude=(np.arange(n)>=midpoint).astype(float)
            if s['profile']=='drift': amplitude=np.clip((t-t[midpoint])/10.,0.,1.)
            direction={'radial':radial,'tangent':tangent,'world_x':np.tile([1.,0.],(n,1)), 'none':np.zeros((n,2))}[s['direction']]
            offset=direction*s['m']*amplitude[:,None]; yaw=math.radians(s['deg'])*amplitude
            x=a['prior'].copy(); x[:,:2]+=offset; x[:,2]=wrap(x[:,2]+yaw)
            d=dr.copy()
            if s['shared']: d[:,:2]+=offset; d[:,2]=wrap(d[:,2]+yaw)
            diff=x[:,:2]-d[:,:2]; yd=wrap(x[:,2]-d[:,2])
            if s['shared']:
                err=max(float(np.max(abs(diff-base_diff))),float(np.max(abs(wrap(yd-base_yaw)))))
                shared_max=max(shared_max,err); assert err<1e-10
            v=np.column_stack((np.linalg.norm(diff,axis=1),abs(yd),
                s['scale']*(a['Pprior'][:,0,0]+a['Pprior'][:,1,1]),s['scale']*a['Pprior'][:,2,2],
                np.linalg.norm(x[:,:2]-ev['truth'][:,:2],axis=1),abs(wrap(x[:,2]-ev['truth'][:,2]))))
            assert np.isfinite(v).all(); values[j]=v
            sums.append(dict(case_id=cid,scenario=s['id'],metrics={name:stat(v[:,i]) for i,name in enumerate(columns)}))
        # Event fixtures do not fabricate a trusted FP or claim a functioning M provider.
        for kind in ('missing','delay','reinitialize','wrong_past_fp_minus2','wrong_past_fp_plus2','zero_innovation_wrong_prior'):
            for seconds in ((1.,2.,5.) if kind in ('missing','delay') else (0.,)):
                events.append(dict(case_id=cid,k=midpoint,event=kind,duration_s=seconds,
                    expected_P='UNKNOWN',expected_M='UNKNOWN',provider_executed=False,
                    note='FIXTURE_SPEC_ONLY_NO_RECOVERY_LATENCY_CLAIM'))
        np.savez_compressed(out/(cid+'_DIAGNOSTICS.npz'),values=values,columns=np.array(columns),
            scenario_ids=np.array([s['id'] for s in grid]),pose_id=a['pose_id'],t=t,dr_mean=dr,
            past_features=past_features,past_feature_columns=np.array(['past_nis_mean_5s','history_count','rejected_count']),
            episode_id=np.floor((t-t[0])/20).astype(int),main_nis=tr['nis'],shadow_mask=tr['mask'])
        checks.append(dict(case_id=cid,n=n,rejected=int((~tr['mask']).sum()),one_step_error=one_step,
                           shared_difference_error=shared_max,current_future_nis_invariance=True))
        print('EVIDENCE',cid,n,len(grid),flush=True)
    assert total==6272
    old=B/'DYNAMIC_MAPPING_R1_20261105/RUN_001'; receipt=json.loads((old/'RUN_RECEIPT.json').read_text())
    for name in ('NOMINAL.csv','STRESS.csv'):
        assert sha256(old/name)==receipt['files'][name]; input_hashes[str((old/name).relative_to(R))]=sha256(old/name)
    with (old/'STRESS.csv').open() as f: rows=list(csv.DictReader(f))
    assert len(rows)==43904
    exclusion=sum(int(r['narrow_reference_exclusion']) for r in rows); assert exclusion==11095
    write_json(out/'EVIDENCE_SUMMARY.json',sums)
    write_json(out/'HISTORY_EVENT_FIXTURES.json',events)
    write_json(out/'EVIDENCE_CHECK.json',dict(status='PASS_ARRAY_DIAGNOSTICS_ONLY',original_rows=total,
        scenario_count=len(grid),expanded_rows=total*len(grid),checks=checks,input_hashes=input_hashes,
        regression_narrow_exclusions=exclusion,static_rows=0,provider='NOT_IMPLEMENTED',
        event_recovery_performance='NOT_RUN',provider_gate='UNDETERMINED',VALID_count=0,
        hypothetical_all_UNKNOWN_activation_rate=0.,dangerous_VALID_rate=None))

def c_online(spectrum,variance,adapter,policy):
    e=adapter.evidence(cir_from_spectrum(spectrum),variance)
    d,prepared=detection.detect(e,'C',policy)
    assert d.selected_tap==e.raw_tap and d.raw_tap==e.raw_tap
    return dict(raw_tap=e.raw_tap,selected_tap=d.selected_tap,raw_valid=e.valid,
                wrong_score=d.wrong_score,flag=None if d.wrong_score is None else bool(d.wrong_score>=policy.wrong_cut),
                reason=d.reason,pool_hash=e.pool_hash,candidate_set_sha=prepared.sha)

def confusion(rows):
    valid=[r for r in rows if r['raw_valid'] and r['reference_valid']]
    normal=[r for r in valid if r['raw_tap']==r['reference_tap']]
    wrong=[r for r in valid if r['raw_tap']!=r['reference_tap']]
    active=[r for r in valid if r['flag'] is not None]
    tp=sum(r['flag'] is True for r in wrong); fp=sum(r['flag'] is True for r in normal)
    an=sum(r['flag'] is not None for r in normal); aw=sum(r['flag'] is not None for r in wrong)
    div=lambda a,b:a/b if b else None
    return dict(total=len(rows),labelled=len(valid),normal=len(normal),wrong=len(wrong),tp=tp,fp=fp,
        tn=an-fp,fn=aw-tp,held=len(rows)-sum(r['flag'] is not None for r in rows),
        labelled_held=len(valid)-len(active),reference_invalid=sum(not r['reference_valid'] for r in rows),
        raw_invalid=sum(not r['raw_valid'] for r in rows),activation_rate=div(sum(r['flag'] is not None for r in rows),len(rows)),
        tpr_all_wrong=div(tp,len(wrong)),fpr_all_normal=div(fp,len(normal)),
        tpr_active=div(tp,aw),fpr_active=div(fp,an),corrected=0,interpretation='DETECTION_NOT_CORRECTION_DESCRIPTIVE')

def c_only(out,manifest):
    adapter=RevisionEvidenceAdapter('VAB','TWO_PORT_UNION'); policy=Policy()
    assert policy.sha==manifest['policy_sha256'] and policy.wrong_cut==2.
    rows=[]; refs={}
    for cid,spec in manifest['cases'].items():
        a=arrays(R/spec['online_npz'])
        for k,spectrum in enumerate(a['Hrf']):
            stop_check()
            rows.append(dict(case_id=cid,k=k,pose_id=int(a['pose_id'][k]),corpus='dynamic',
                episode=int((a['t'][k]-a['t'][0])//20),**c_online(spectrum,spec['metadata']['noise_variance'],adapter,policy)))
        refs[cid]=(spec['evaluator_npz'],'clean_H')
        print('C_ONLY_ONLINE',cid,len(a['Hrf']),flush=True)
    for cid,spec in manifest['static_cases'].items():
        a=arrays(R/spec['online_npz']); assert set(a)=={'Hrf'}
        rows.append(dict(case_id=cid,k=0,pose_id=None,corpus='static',episode=None,
                         **c_online(a['Hrf'],0.,adapter,policy)))
        refs[cid]=(spec['evaluator_npz'],'reference_H')
    assert len(rows)==6320
    with gzip.open(out/'C_ONLY_ONLINE.jsonl.gz','wt',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,allow_nan=False)+'\n')
    # Freeze all decisions before accessing evaluator files or computing reference labels.
    online_sha=sha256(out/'C_ONLY_ONLINE.jsonl.gz'); cache={}
    for r in rows:
        cid=r['case_id']; path,key=refs[cid]
        if cid not in cache: cache[cid]=arrays(R/path)[key]
        h=cache[cid][r['k']] if r['corpus']=='dynamic' else cache[cid]
        ref,_,_=raw_detection(cir_from_spectrum(h))
        r.update(reference_tap=ref,reference_valid=ref is not None,
                 error_taps=None if ref is None or r['raw_tap'] is None else abs(ref-r['raw_tap']))
    with gzip.open(out/'C_ONLY_LABELLED.jsonl.gz','wt',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,allow_nan=False)+'\n')
    groups=defaultdict(list); eps=defaultdict(list)
    for r in rows:
        groups[r['case_id']].append(r); eps[(r['case_id'],r['episode'])].append(r)
    report=dict(status='COMPLETE_C_ONLY_SEPARATE_CONTRACT',policy_sha=policy.sha,wrong_cut=2.,
        all=confusion(rows),dynamic=confusion([r for r in rows if r['corpus']=='dynamic']),
        static=confusion([r for r in rows if r['corpus']=='static']),cases={k:confusion(v) for k,v in groups.items()},
        error_size={str(size):confusion([r for r in rows if r['error_taps'] is not None and
                    (r['error_taps']==size if size<2 else r['error_taps']>=2)]) for size in (0,1,2)},
        episodes=[dict(case_id=k[0],episode=k[1],**confusion(v)) for k,v in eps.items()],
        online_sha256_before_evaluation=online_sha,E1_02_started=False,E2_started=False,
        prior_inputs_to_detector=0,motion_inputs_to_detector=0,trusted_history_calls=0)
    write_json(out/'C_ONLY_SUMMARY.json',report)

def forbidden(*args,**kwargs):
    raise AssertionError('SELECTION_HISTORY_MODEL_OR_EKF_FORBIDDEN')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False); started=time.time()
    manifest=json.loads((B/'PRIOR_INTEGRITY_R1_20261105/PREPARATION_001/MANIFEST_PREP_ONLY.json').read_text())
    static=json.loads((B/'DYNAMIC_MAPPING_R1_20261105/STATIC48/MANIFEST_PREP_ONLY.json').read_text())
    manifest['static_cases']=static['static_cases']; manifest['input_files'].update(static['input_files'])
    grid=scenarios()
    used={spec[field]:manifest['input_files'][spec[field]] for specs in (manifest['cases'],manifest['static_cases'])
          for spec in specs.values() for field in ('online_npz','evaluator_npz')}
    verify_files(R,used)
    source_paths=[Path(__file__),*sorted((R/'src/qclean_uwb/fp_sc/followup').glob('*.py')),
                  R/'src/qclean_uwb/fp_sc/candidate_revision.py',R/'src/qclean_uwb/fp_sc/candidates.py',
                  R/'research/EKF4_RANGE_S_STAGED_20261014/core.py']
    receipt=dict(status='STARTED',utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,
        base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),
        code_hashes={str(p.relative_to(R)):sha256(p) for p in source_paths},input_hashes=used,
        contract_hashes={p.name:sha256(p) for p in PKG.glob('*CONTRACT_KO.md')},scenario_grid=grid,
        governance_hashes={n:sha256(Path('C:/Users/Myoungsun Kim/.codex/research-governance')/n) for n in
            ('COMMON_CONTRACT.md','ROLE_PROPOSER.md','ROLE_IMPLEMENTER.md')},
        cpu_affinity=process.cpu_affinity(),python=platform.python_version(),numpy=np.__version__,
        independent_audit=False,E1_02_started=False,E2_started=False)
    write_json(out/'RUN_RECEIPT.json',receipt)
    try:
        suite=unittest.defaultTestLoader.discover(str(R/'tests'),pattern='test_fp_sc_prior_integrity.py')
        with (out/'GUARD_TESTS.log').open('w') as f: result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
        assert result.wasSuccessful() and result.testsRun>0
        spec=importlib.util.spec_from_file_location('evidence_core',R/'research/EKF4_RANGE_S_STAGED_20261014/core.py')
        core=importlib.util.module_from_spec(spec);sys.modules[spec.name]=core;spec.loader.exec_module(core)
        x=core.transition(np.zeros(4),2.,0.,1.)[0]; assert np.allclose(x,[2,0,0,0],atol=1e-12)
        x=core.transition(np.zeros(4),math.pi/2,math.pi/2,1.)[0]
        assert np.allclose(x,[1,1,math.pi/2,0],atol=1e-12)
        # Sentinel protection stays in force for BOTH independent experiment lanes.
        selection.select=forbidden; selection.TrustedHistory.observe=forbidden
        detection.RawDetectionHistory.observe_raw=forbidden
        engine.open_loop=forbidden;engine.OriginalAdapter=forbidden;numerics.update=forbidden
        evidence(out,manifest,core,grid)
        c_only(out,manifest)
        receipt.update(status='COMPLETE_DIAGNOSTICS_AND_C_ONLY_PROVIDER_HOLD',guard_tests=result.testsRun,
            elapsed_s=time.time()-started,peak_rss_bytes=process.memory_info().peak_wset,
            provider_gate='UNDETERMINED_NO_VALID_BASIS_OR_RISK_BUDGET',files={p.name:sha256(p) for p in out.iterdir() if p.name!='RUN_RECEIPT.json'})
    except BaseException:
        receipt.update(status='FAILED_PRESERVED',traceback=traceback.format_exc(),elapsed_s=time.time()-started)
        raise
    finally: write_json(out/'RUN_RECEIPT.json',receipt)
    print(receipt['status'],flush=True)

if __name__=='__main__': main()
