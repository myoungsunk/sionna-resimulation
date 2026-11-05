"""Separate E0 result arithmetic; no production FP-SC or receiver imports.

Reads locked originals and actual result files. Uses separately written scalar
receiver math, direct inverse DFT spot checks, and Cholesky Joseph arithmetic.
SourceFFD polarization interpolation and BASE shadow recursion are compared
against archived traces, not claimed as independently reimplemented here.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_reference_receiver as receiver_ref

BASE = Path('research/MBVAR_PRR_001_20261103')
PHYS = BASE / 'PHYSICAL_CAUSALITY_20261104'
E0 = PHYS / 'FP_SELECTIVE_CORRECTION_001/E0_20261105'
PACKETS = PHYS / 'C1/C1A_001/FROZEN_PACKETS'
RF = Path('results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C')
B_OLD = -0.5315983906250129
COUNTS = {'R2':979,'R4':742,'R5':1415}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def js(path):
    return json.loads(Path(path).read_text())


def npz(path):
    with np.load(path, allow_pickle=False) as z:
        return {k:z[k] for k in z.files}


def csvrows(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def column(rows, key, integer=False):
    if integer:
        return np.asarray([int(row[key]) for row in rows])
    return np.asarray([float(row[key]) if row[key] not in ('',None) else np.nan for row in rows])


def compare(expected, actual, label, *, tol=1e-10, exact=False, relative=False):
    a,b=np.asarray(expected),np.asarray(actual)
    if a.shape!=b.shape:
        return {'label':label,'pass':False,'reason':'SHAPE','expected':list(a.shape),'actual':list(b.shape)}
    if exact:
        mismatches=int(np.count_nonzero(a!=b))
        return {'label':label,'pass':mismatches==0,'elements':int(a.size),'mismatches':mismatches,'rule':'EXACT'}
    finite=np.isfinite(a)&np.isfinite(b)
    masks=(np.array_equal(np.isfinite(a),np.isfinite(b)) and np.array_equal(np.isnan(a),np.isnan(b)))
    inf=np.isinf(a)&np.isinf(b)
    masks=bool(masks and np.array_equal(a[inf],b[inf]))
    delta=np.abs(a[finite]-b[finite])
    maximum=float(delta.max(initial=0.0))
    normalized=float(np.max(delta/np.maximum(1.,np.abs(a[finite])),initial=0.0))
    relative_l2=float(np.linalg.norm((a[finite]-b[finite]).ravel())/max(np.linalg.norm(a[finite].ravel()),np.finfo(float).tiny))
    tested=relative_l2 if relative else normalized
    return {'label':label,'pass':bool(masks and tested<=tol),'elements':int(a.size),'finite_pairs':int(finite.sum()),
            'nonfinite_masks_equal':masks,'max_absolute_error':maximum,'max_normalized_error':normalized,
            'relative_l2_error':relative_l2,'test':'RELATIVE_L2' if relative else 'NORMALIZED_MAX', 'tolerance':tol}


def record(checks, expected, actual, label, **kw):
    check=compare(expected,actual,label,**kw)
    checks.append(check)
    return check


def stats(errors, step):
    values=np.asarray(errors);valid=np.isfinite(values);x=values[valid]
    result={'rows':len(values),'valid':int(valid.sum()),'invalid':int((~valid).sum())}
    if len(x):
        a=np.abs(x)
        result.update(signed_bias_m=float(np.mean(x)),mae_m=float(np.mean(a)),rmse_m=float(np.sqrt(np.dot(x,x)/len(x))),
                      p95_abs_m=float(np.percentile(a,95)),p99_abs_m=float(np.percentile(a,99)),max_abs_m=float(max(a)),
                      within_4cm_fraction=float(np.count_nonzero(a<=.04)/len(a)),within_one_tap_fraction=float(np.count_nonzero(a<=step)/len(a)))
    return result


def reference_archive(repo,route,bias,channel):
    if route=='R2':
        folder=repo/BASE/'POST_S3_PROPOSER_20261104/R2_EXTENSION'/('FULL_002' if channel=='Full' else 'NATIVE_001')
        relative=f'natural/R2_{bias}_{channel}_10_A.npz'
        registry=js(folder/'NATURAL_INDEX.json')
    else:
        folder=repo/BASE/'S1/runs/EVAL_001';relative=f'{route}_aB_m0_{bias}_{channel}_10_W0.npz'
        registry=js(folder/'TRACE_INDEX.json')
    matches=[r for r in registry if r['file']==relative]
    if len(matches)!=1 or sha(folder/relative)!=matches[0]['sha256']:
        raise ValueError(f'ARCHIVED_TRACE_IDENTITY:{relative}')
    return folder/relative


def verify_identities(repo,run):
    entries=js(repo/E0/'INPUT_LOCK.json')['files'];failures=[];total=0
    for entry in entries:
        p=repo/entry['path'];total+=p.stat().st_size
        if p.stat().st_size!=entry['size_bytes'] or sha(p)!=entry['sha256']:
            failures.append(entry['path'])
    outputs=js(run/'ARTIFACT_HASHES.json');bad_outputs=[]
    for path,expected in outputs.items():
        if sha(run/path)!=expected:bad_outputs.append(path)
    code=js(repo/E0/'CODE_LOCK.json')['files'];bad_code=[]
    for path,expected in code.items():
        if sha(repo/path)!=expected:bad_code.append(path)
    manifest=js(run/'RUN_MANIFEST.json')
    if manifest['stage']!='E0' or manifest['new_RT_runs']!=0 or manifest['stages_E1_E5_executed']:
        raise ValueError('RUN_SCOPE_INVALID')
    return {'input_files_rehashed':len(entries),'input_bytes_rehashed':total,'input_hash_failures':failures,
            'result_files_rehashed':len(outputs),'result_hash_failures':bad_outputs,
            'locked_code_files_rehashed':len(code),'code_hash_failures':bad_code,
            'pass':not (failures or bad_outputs or bad_code)}


def check_dynamic(repo,run):
    frequencies=np.load(repo/RF/'freqs_hz.npy',allow_pickle=False)
    step=receiver_ref.C0/(1028*(frequencies[1]-frequencies[0]))
    summary=js(run/'receiver/SUMMARY.json');summary_by={r['cell']:r for r in summary['cells']}
    checks=[];cells=[];dft_frames=0;numeric_files=set();unique=0;paired=0
    for route,n in COUNTS.items():
        for channel in ('Full','Native_LoS'):
            rf=repo/RF/(f'FULL_RF/H_{route}_aB_m0.npy' if channel=='Full' else f'H_LoS_{route}_aB_m0.npy')
            raw=np.load(rf,allow_pickle=False,mmap_mode='r');numeric_files.add(str(rf.relative_to(repo)))
            initial=npz(repo/PACKETS/'algorithm_input'/f'{route}_aB_m0_B0_{channel}.npz')
            ids=initial['pose_id'];record(checks,n,len(ids),f'{route}_{channel}:expected_count',exact=True)
            h=np.asarray(raw[ids]);got=receiver_ref.reference_observe(h,frequencies);unique+=len(ids)
            samples=np.unique(np.linspace(0,len(ids)-1,min(9,len(ids)),dtype=int));dft_frames+=len(samples)
            for i in samples:
                tap=int(got['index'][i]);taps=np.array([max(0,tap-1),tap,min(1027,tap+1)])
                direct=receiver_ref.direct_dft_taps(h[i,:,:,0],taps)
                fft=receiver_ref.reference_cir(h[i:i+1,:,:,0])[0,taps]
                record(checks,fft,direct,f'{route}_{channel}:direct_DFT_pose{int(ids[i])}',relative=True)
            for bias in ('B0','L2'):
                label=f'{route}_{bias}_{channel}';packetpath=repo/PACKETS/'algorithm_input'/f'{route}_aB_m0_{bias}_{channel}.npz'
                truthpath=repo/PACKETS/'evaluator_truth'/f'{route}_{bias}_TRUTH.npz'
                packet=npz(packetpath);truth=npz(truthpath);tracepath=reference_archive(repo,route,bias,channel);trace=npz(tracepath)
                numeric_files.update(str(p.relative_to(repo)) for p in (packetpath,truthpath,tracepath))
                rows=csvrows(run/'receiver'/f'{label}_RECEIVER_AND_RANGES.csv');paired+=len(rows)
                for key in ('pose_id','t'):
                    record(checks,initial[key],packet[key],label+':packet_join_'+key,exact=True)
                    record(checks,packet[key],truth[key],label+':truth_join_'+key,exact=True)
                    record(checks,packet[key],trace[key],label+':trace_join_'+key,exact=True)
                record(checks,ids,column(rows,'pose_id',True),label+':CSV_pose_ids',exact=True)
                record(checks,packet['t'],column(rows,'t_s'),label+':CSV_time',exact=True)
                for name,col,exact in [('index','raw_tap',True),('rx','raw_rx',True),('detected','detected',True),('reference_valid','reference_valid',True),
                                       ('range_m','r_det_clean_m',False),('s','s_clean',False),('peak','peak',False)]:
                    record(checks,got[name],column(rows,col,integer=exact),label+':receiver_'+name,tol=1e-12,exact=exact)
                csvpower=np.column_stack([column(rows,'power_plus'),column(rows,'power_minus')])
                record(checks,got['power'],csvpower,label+':receiver_power_relative',relative=True)
                raw_checks=[record(checks,got['range_m'],packet['z'][:,0],label+':clean_to_archived_range',tol=1e-12),
                            record(checks,got['s'],packet['z'][:,1],label+':clean_to_archived_s',tol=1e-12)]
                geo=np.sqrt((truth['truth'][:,0]-10)**2+truth['truth'][:,1]**2+2.2**2)
                state=np.sqrt((trace['prior'][:,0]-10)**2+trace['prior'][:,1]**2+2.2**2)
                corrected=packet['z'][:,0]-packet['muMB'][:,0]-B_OLD
                derived={'r_geo_m':geo,'r_state_m':state,'r_corrected_archived_m':corrected,'r_det_clean_minus_B_OLD_m':got['range_m']-B_OLD}
                for name,array in derived.items():record(checks,array,column(rows,name),label+':'+name,tol=1e-12)
                errors={'error_r_det_clean_m':got['range_m']-geo,
                        'error_r_det_clean_minus_B_OLD_m':got['range_m']-B_OLD-geo,
                        'error_r_corrected_archived_m':corrected-geo,'error_r_state_m':state-geo}
                cellstats={}
                for name,array in errors.items():
                    calculated=stats(array,step);cellstats[name]=calculated
                    archived=summary_by[label]['errors'][name]
                    for field,value in calculated.items():record(checks,value,archived[field],label+':stats_'+name+'_'+field,tol=1e-12)
                cells.append({'cell':label,'n':len(ids),'valid_reference':int(got['reference_valid'].sum()),
                              'clean_to_archived_r_and_s_pass':all(c['pass'] for c in raw_checks),'range_statistics':cellstats})
    return {'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,'cells':cells,
            'unique_dynamic_spectra':unique,'paired_route_bias_channel_rows':paired,
            'direct_DFT_dynamic_frames':dft_frames,'numeric_input_files':sorted(numeric_files),
            'baseline_RF_lineage_numeric_verdict':'CLEAN_H_REPRODUCES_ALL_ARCHIVED_R_AND_S' if all(c['clean_to_archived_r_and_s_pass'] for c in cells) else 'UNRESOLVED'}


def check_g4(repo,run):
    folder=repo/PHYS/'C3/G4_001';conditions=js(folder/'RUN_001/CONDITIONS.json');plan=js(folder/'PLAN.json')
    frequencies=6250400000.+1950000.*np.arange(257);step=receiver_ref.C0/(1028*1950000.)
    actualrows={(r['condition_id'],r['channel']):r for r in csvrows(run/'g4/RAW_RECEIVER_ROWS.csv')}
    actualoracle={r['condition_id']:r for r in csvrows(run/'g4/ORACLE_STATIC_ROWS.csv')}
    checks=[];numeric=[];observations=[];matches={'baseline':0,'minus4cm':0,'zero':0,'plus4cm':0};rescue=harm=0;valid=0
    for condition in conditions:
        ident=condition['condition_id'];path=folder/'RUN_001'/ident/'FIELDS_AND_WINDOWS.npz';fields=npz(path);numeric.append(str(path.relative_to(repo)))
        extracted={}
        for channel in ('full','direct'):
            h=fields[channel+'_spectrum'][None,:,:,None];got=receiver_ref.reference_observe(h,frequencies);extracted[channel]=got
            archive=condition['physical']['detector']['full' if channel=='full' else 'los'];row=actualrows[(ident,channel)]
            for name,expected in [('index',[archive['tap']]),('rx',[archive['rx']]),('s',[archive['s']]),('range_m',[archive['range_m']])]:
                record(checks,got[name],np.array(expected),ident+':archive_'+channel+'_'+name,exact=name in ('index','rx'),tol=1e-12)
            for key,col in [('index','tap'),('rx','rx'),('s','s'),('range_m','range_m')]:
                val=int(row[col]) if key in ('index','rx') else float(row[col])
                record(checks,got[key][0],val,ident+':output_'+channel+'_'+key,exact=key in ('index','rx'),tol=1e-12)
            record(checks,got['power'][0],[float(row['power_plus']),float(row['power_minus'])],ident+':output_'+channel+'_power',relative=True)
            cir=receiver_ref.reference_cir(h[...,0])[0]
            record(checks,cir,fields[channel+'_cir'],ident+':archived_'+channel+'_cir_relative',relative=True)
            tap=int(got['index'][0]);taps=np.array([max(0,tap-1),tap,min(1027,tap+1)])
            direct=receiver_ref.direct_dft_taps(h[0,:,:,0],taps)
            record(checks,cir[taps],direct,ident+':'+channel+'_direct_DFT',relative=True)
            observations.append({'condition_id':ident,'channel':channel,'tap':tap,'rx':int(got['rx'][0]),'s':float(got['s'][0]),'reference_valid':bool(got['reference_valid'][0])})
        fulltap=int(extracted['full']['index'][0]);lostap=int(extracted['direct']['index'][0]);isvalid=bool(extracted['direct']['reference_valid'][0]);valid+=int(isvalid)
        if not isvalid:continue
        modelrange=float(np.linalg.norm(np.asarray(condition['xyz'])-np.asarray(plan['anchor'])))+B_OLD
        record(checks,modelrange,condition['model']['h_range'],ident+':continuous_range_geometry',tol=1e-12)
        matches['baseline']+=int(fulltap==lostap)
        selected0=None
        for label,shift in [('minus4cm',-.04),('zero',0.),('plus4cm',.04)]:
            selected=int(np.rint((modelrange+shift)/step));matches[label]+=int(selected==lostap)
            record(checks,selected,int(actualoracle[ident]['oracle_'+label+'_tap']),ident+':oracle_'+label,exact=True)
            if label=='zero':selected0=selected
        rescue+=int(fulltap!=lostap and selected0==lostap);harm+=int(fulltap==lostap and selected0!=lostap)
    actual=js(run/'g4/SUMMARY.json')
    for key,value in matches.items():record(checks,value,actual['matches'][key],'G4:matches_'+key,exact=True)
    record(checks,rescue,actual['aggregate']['rescued'],'G4:rescued',exact=True);record(checks,harm,actual['aggregate']['harmed'],'G4:harmed',exact=True)
    record(checks,24,len(conditions),'G4:conditions',exact=True);record(checks,24,valid,'G4:valid_direct_reference',exact=True)
    return {'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,'static_conditions':len(conditions),
            'unique_static_spectra':len(observations),'direct_DFT_static_frames':len(observations),
            'valid_direct_references':valid,'matches':matches,'rescued':rescue,'harmed':harm,
            'observations':observations,'numeric_input_files':numeric,
            'SourceFFD_scope':'Continuous range rederived geometrically. FFD polarization model itself was source-code reviewed and implementer-replayed, not independently reimplemented here.'}


def predict_one(x,P,ds,gyro,seconds):
    angle=float(gyro-x[3]*seconds);half=angle/2
    if abs(angle)<1e-4:
        c=1-angle**2/24+angle**4/1920-angle**6/322560
        dc=-angle/12+angle**3/480-angle**5/53760
    else:
        c=math.sin(half)/half;dc=(half*math.cos(half)-math.sin(half))/(2*half*half)
    bearing=x[2]+half;u=np.array([math.cos(bearing),math.sin(bearing)]);perp=np.array([-u[1],u[0]])
    delta=ds*c*u;derivative=ds*(dc*u+.5*c*perp)
    y=x.copy();y[:2]+=delta;y[2]=(x[2]+angle+np.pi)%(2*np.pi)-np.pi
    F=np.eye(4);F[:2,2]=[-delta[1],delta[0]];F[:2,3]=-seconds*derivative;F[2,3]=-seconds
    G=np.zeros((4,3));G[:2,0]=c*u;G[:2,1]=derivative;G[2,1]=1.;G[3,2]=1.
    Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*seconds,0.])
    predicted=F@((P+P.T)/2)@F.T+G@Q@G.T
    return y,(predicted+predicted.T)/2


def check_baseline(repo,run):
    checks=[];cells=[];numeric=[];total=0;replayed_rows=0;prediction_rows=0;blocked=[]
    for route,n in COUNTS.items():
        for bias in ('B0','L2'):
            for channel in ('Full','Native_LoS'):
                cell=f'{route}_{bias}_{channel}_10';packetpath=repo/PACKETS/'algorithm_input'/f'{route}_aB_m0_{bias}_{channel}.npz'
                originalpath=reference_archive(repo,route,bias,channel);packet=npz(packetpath);original=npz(originalpath)
                replay_path=run/'baseline'/f'{cell}_REPLAY.npz';controls_path=run/'baseline'/f'{cell}_CONTROLS.npz'
                replay=npz(replay_path) if replay_path.exists() else None
                controls=npz(controls_path) if controls_path.exists() else None
                if replay is None:blocked.append({'cell':cell,'status':'MISSING_REPLAY_OUTPUT_PRESERVED','original_record':js(run/'baseline'/f'{cell}.json')['status']})
                numeric.extend(str(p.relative_to(repo)) for p in (packetpath,originalpath))
                for name in original:
                    if replay is None or name in ('latency_ns',) or name not in replay:continue
                    record(checks,original[name],replay[name],cell+':source_replay_'+name,exact=name in ('mask','pose_id','t'))
                pred=np.empty((n,4));predP=np.empty((n,4,4));state=np.empty((n,4));postP=np.empty((n,4,4));K=np.zeros((n,4,2));S=np.empty((n,2,2));NIS=np.empty(n);sigmas=np.empty(n)
                originalx=original['x'];originalP=original['P'];x0=np.r_[controls['x0'],0.] if controls is not None else original['prior'][0]
                for k in range(n):
                    prev=x0 if k==0 else originalx[k-1];prevP=packet['P0'] if k==0 else originalP[k-1]
                    if controls is not None:
                        pred[k],predP[k]=(prev,prevP) if k==0 else predict_one(prev,prevP,float(controls['ds'][k]),float(controls['gy'][k]),float(controls['dt'][k]))
                    rho=float(np.linalg.norm(prev[:2]-[10.,0.]));sigma=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]));sigmas[k]=sigma
                    R=packet['R'][k].copy();R[1,1]+=sigma*sigma
                    xp=original['prior'][k];P=original['Pprior'][k];H=original['H'][k];nu=packet['z'][k]-original['h'][k]-packet['muMB'][k]
                    innovation=H@P@H.T+R;innovation=(innovation+innovation.T)/2;S[k]=innovation
                    L=np.linalg.cholesky(innovation);white=np.linalg.solve(L,nu);NIS[k]=white@white
                    if original['mask'][k]:
                        gain=np.linalg.solve(L.T,np.linalg.solve(L,H@P)).T;K[k]=gain
                        state[k]=xp+gain@nu;state[k,2]=(state[k,2]+np.pi)%(2*np.pi)-np.pi
                        A=np.eye(4)-gain@H;C=A@P@A.T+gain@R@gain.T;postP[k]=(C+C.T)/2
                    else:state[k]=xp;postP[k]=P
                values=[('x',state),('P',postP),('K',K),('S',S),('nis',NIS),('sigma_b',sigmas)]
                if controls is not None:
                    values.extend([('prior',pred),('Pprior',predP)]);prediction_rows+=n
                for name,value in values:record(checks,value,original[name],cell+':independent_'+name)
                geometric=np.sqrt((original['prior'][:,0]-10)**2+original['prior'][:,1]**2+2.2**2)
                record(checks,geometric+B_OLD,original['h'][:,0],cell+':range_model')
                Hj=np.column_stack(((original['prior'][:,0]-10)/geometric,original['prior'][:,1]/geometric,np.zeros(n),np.zeros(n)))
                record(checks,Hj,original['H'][:,0],cell+':range_Jacobian')
                total+=n;replayed_rows+=n if replay is not None else 0
                cells.append({'cell':cell,'n':n,'accepted':int(original['mask'].sum()),'replay_available':replay is not None,'controls_available':controls is not None})
    passed=all(c['pass'] for c in checks)
    return {'status':('PASS' if not blocked else 'PARTIAL_BASELINE_REPLAY_BLOCKED') if passed else 'FAIL','checks':checks,'cells':cells,'total_update_rows':total,
            'numerical_checks_pass':passed,'full_replay_compared_rows':replayed_rows,'independent_prediction_rows':prediction_rows,'blocked_replays':blocked,
            'numeric_input_files':sorted(set(numeric)),
            'independent_scope':'Per-step motion propagation, previous-state sigma, Cholesky gain/Joseph/NIS/range h-H from originals; all output trace arrays compared with archived traces.',
            'not_independently_reimplemented':['SourceFFD polarization h/H interpolation','BASE shadow state and gate regeneration'],
            'note':'For those two parts, source review and exact full no-op replay parity are evidence; not a claim of a second FFD/filter engine.'}


def check_flat(repo,run):
    freq=np.load(repo/RF/'freqs_hz.npy',allow_pickle=False);dist=np.arange(2.,16.,.001)
    rows=csvrows(run/'flat_mapping/FLAT_SUBTAP_SWEEP.csv');checks=[];taps=[];ranges=[]
    for start in range(0,len(dist),256):
        d=dist[start:start+256];h=np.exp(-2j*np.pi*freq[None,:]*d[:,None]/receiver_ref.C0)
        h=np.repeat(h[:,:,None,None],2,axis=2);got=receiver_ref.reference_observe(h,freq)
        taps.extend(got['index']);ranges.extend(got['range_m'])
    taps=np.asarray(taps);ranges=np.asarray(ranges)
    record(checks,14000,len(rows),'flat:rows',exact=True)
    record(checks,dist,column(rows,'distance_m'),'flat:distances',exact=True)
    record(checks,taps,column(rows,'detector_tap',True),'flat:taps',exact=True)
    record(checks,ranges,column(rows,'r_det_m'),'flat:ranges',tol=1e-12)
    record(checks,ranges-B_OLD-dist,column(rows,'corrected_error_m'),'flat:corrected_errors',tol=1e-12)
    step=receiver_ref.C0/(1028*1950000.);actual=js(run/'flat_mapping/SUMMARY.json')
    calculated={'receiver_offset':stats(ranges-dist,step),'constant_offset_corrected':stats(ranges-B_OLD-dist,step)}
    for group,values in calculated.items():
        for field,value in values.items():record(checks,value,actual[group][field],'flat:stats_'+group+'_'+field,tol=1e-12)
    return {'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,'synthetic_direct_samples':len(dist),
            'statistics':calculated,'claim_limit':'Analytical flat direct spectrum only; no physical RF scene or route simulation.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();repo=a.repo.resolve();run=a.run.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=js(run/'RUN_MANIFEST.json')
    if source['status']=='RUNNING':raise ValueError('RESULTS_NOT_COMPLETE')
    report={'schema':'FP_SC_E0_SEPARATE_RESULT_REVIEW_V1','study_id':'FP-SC-001','stage':'E0',
            'reviewer':'/root/design_audit','reviewer_provenance':'SAME_SESSION_SEPARATE_REVIEWER',
            'external_independent_accept':False,'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),
            'checker_sha256':sha(__file__),'reference_receiver_sha256':sha(Path(receiver_ref.__file__)),
            'implementation_commit':source['implementation_commit'],'execution_commit':source['execution_commit'],
            'execution_lock_sha256':source['execution_lock_sha256'],'code_lock_sha256':sha(repo/E0/'CODE_LOCK.json'),
            'production_functions_imported':False,'results':{},'failures':[],'E1_E5_executed':False}
    report['identities']=verify_identities(repo,run)
    for label,fn in [('dynamic',check_dynamic),('g4',check_g4),('baseline',check_baseline),('flat',check_flat)]:
        print('CHECK',label,flush=True)
        try:
            result=fn(repo,run);report['results'][label]=result
        except Exception as exc:
            import traceback
            report['failures'].append({'component':label,'error':str(exc),'traceback':traceback.format_exc()})
            result={'status':'ERROR','error':str(exc)}
        (out/(label.upper()+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print('RESULT',label,result['status'],flush=True)
    all_pass=report['identities']['pass'] and not report['failures'] and all(x['status']=='PASS' for x in report['results'].values())
    partial=(report['identities']['pass'] and not report['failures'] and all(x['status'] in ('PASS','PARTIAL_BASELINE_REPLAY_BLOCKED') for x in report['results'].values()))
    report['verdict']='PASS_REVIEWED_E0_NUMERICAL_SCOPE' if all_pass else ('PASS_AVAILABLE_ARITHMETIC_BASELINE_REPLAY_BLOCKED' if partial else 'FAIL_OR_PARTIAL_REVIEWED_E0_SCOPE')
    report['utc_end']=dt.datetime.now(dt.timezone.utc).isoformat();report['next_stage_GO']=False
    report['claim_scope']='E0 definitions/baseline/no-op/input/mapping reproduction only; no selective-correction, H1-H7, closed-loop benefit, noisy-policy, runtime or generalization claim.'
    numeric=set()
    for result in report['results'].values():numeric.update(result.get('numeric_input_files',[]))
    report['numerically_read_original_files']=sorted(numeric)
    report['numerically_read_original_file_bytes']=sum((repo/path).stat().st_size for path in numeric)
    (out/'E0_RESULT_REVIEW.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    digest={path.name:sha(path) for path in sorted(out.iterdir()) if path.is_file() and path.name!='ARTIFACT_HASHES.json'}
    (out/'ARTIFACT_HASHES.json').write_text(json.dumps(digest,indent=2)+'\n')
    print(json.dumps({'verdict':report['verdict'],'components':{k:v['status'] for k,v in report['results'].items()},'failures':len(report['failures'])}),flush=True)
    raise SystemExit(0 if all_pass else 2)


if __name__=='__main__':main()
