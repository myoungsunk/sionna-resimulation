"""Frozen Joint-C recursion and same-prior controls; no parameter fitting."""
import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_loss_family as old
import rf_components as rf
from d6_d9_common import RS, RR, range_h, REPO
from fixed_weight_control import FixedWeightPoseEKF

MODELS = ('M0', 'RF_HUBER_ONLY', 'RF_CAUCHY', 'RF_FIXED_THIRD')
DONORS = ('M0', 'RF_CAUCHY')
# Every vector/matrix is row-major. Codes: applied=1, rejected_NIS=0.
FIELDS = [('t',1),('truth',3),('prior',3),('P_prior',9),('H',6),('S',4),
          ('innovation',2),('truth_RF_residual',2),('state_innovation',2),
          ('posterior',3),('P_post',9),('K',6),('R_eff',4),('weight',1),
          ('NIS',1),('applied',1),('error',3),('pose_NEES',1),('heading_NEES',1),
          ('pose95',1),('heading95',1),('heading_sq_change',1),('xy_sq_change',1)]
SLICES = {}; cursor = 0
for field, size in FIELDS:
    SLICES[field] = slice(cursor,cursor+size); cursor += size

def get(a, field):
    v=a[:,SLICES[field]]
    return v[:,0] if v.shape[1]==1 else v

def make(name, x, contract):
    return FixedWeightPoseEKF(x,weight=1/3) if name==MODELS[-1] else old.make_filter(name,x,contract)

def reset(f, x, p):
    base=f.f if hasattr(f,'f') else f.filter.f
    base.x=x.copy(); base.P=p.copy()

def update(name,f,zs,zr,model,case,contract,shape):
    if name==MODELS[-1]:
        return f.update('C',zs,zr,model,case['anchor'],case['robot_z_m'],cov=np.diag([RS,RR]))
    return old.update_filter(name,f,'C',zs,zr,model,case,np.zeros(2),np.diag([RS,RR]),contract['huber_delta'],shape)

def cached_model(model):
    cache={}
    def call(x):
        key=np.asarray(x).tobytes()
        if key not in cache: cache[key]=model(x)
        h,j=cache[key]
        return h,np.asarray(j).copy()
    return call

def checked_step(name,f,zs,zr,model,case,contract,shape,truth,t,prior=None,rf_truth=None):
    x=f.pose.copy(); p=f.Ppose.copy()
    if prior is None:
        prior=rf.observation_prior(f,'C',zs,zr,model,case,np.zeros(2),np.diag([RS,RR]))
    if prior is None or prior['H'].shape!=(2,3): raise RuntimeError('Joint C requires both frozen measurements')
    st=update(name,f,zs,zr,model,case,contract,shape)
    expected=prior['NIS']<=prior['gate_threshold']
    applied=st['status']=='applied'
    if applied!=expected or st['status'] not in ('applied','rejected_NIS'):
        raise RuntimeError('Common prior gate mismatch '+name)
    if abs(st['NIS']-prior['NIS'])>1e-8: raise RuntimeError('Common prior NIS mismatch')
    if not np.isfinite(f.pose).all() or np.linalg.eigvalsh(f.Ppose).min()<=0:
        raise RuntimeError('Invalid posterior')
    H=prior['H']; w=st.get('robust_weight',st.get('huber_weight'))
    if applied:
        w=1. if name=='M0' else float(w)
        re=np.diag([RS,RR])/w
        K=st.get('K',np.linalg.solve(H@p@H.T+re,H@p).T)
        delta=f.pose-x; delta[2]=old.wrap(delta[2])
        if np.max(np.abs(delta-K@prior['innovation']))>1e-8:
            raise RuntimeError('Correction/gain disagreement '+name)
        I=np.eye(3)-K@H; jp=I@p@I.T+K@re@K.T
        if np.max(np.abs(jp-f.Ppose))>1e-8: raise RuntimeError('Joseph covariance mismatch')
    else:
        w=np.nan;re=np.full((2,2),np.nan);K=np.zeros((3,2))
        if not (np.array_equal(x,f.pose) and np.array_equal(p,f.Ppose)):
            raise RuntimeError('Rejected update changed state')
    e=f.pose-truth; e[2]=old.wrap(e[2]); ep=x-truth;ep[2]=old.wrap(ep[2])
    nees,hn,cover=old.eval_covariance(e,f.Ppose)
    if rf_truth is None:
        rf_truth=np.array([zs-model(truth)[0],zr-range_h(truth,case['anchor'],case['robot_z_m'])[0]])
    parts=[t,truth,x,p,H,prior['S'],prior['innovation'],rf_truth,prior['innovation']-rf_truth,
        f.pose,f.Ppose,K,re,w,prior['NIS'],int(applied),e,nees,hn,int(cover),int(hn<=3.841458820694124),
        e[2]**2-ep[2]**2,e[:2]@e[:2]-ep[:2]@ep[:2]]
    return np.concatenate([np.asarray(v,dtype=float).reshape(-1) for v in parts])

def metrics(a,identity):
    e=get(a,'error'); applied=get(a,'applied').astype(bool);w=get(a,'weight')[applied]
    r=dict(identity,n=len(a),heading_rmse_deg=float(np.sqrt(np.mean(e[:,2]**2))*180/np.pi),
        xy_rmse_m=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
        mean_pose_NEES=float(get(a,'pose_NEES').mean()),mean_heading_NEES=float(get(a,'heading_NEES').mean()),
        pose95=float(get(a,'pose95').mean()),heading95=float(get(a,'heading95').mean()),
        accepted_updates=int(applied.sum()),rejected_updates=int((~applied).sum()),
        mean_weight=float(w.mean()) if len(w) else None,median_weight=float(np.median(w)) if len(w) else None,
        mean_heading_squared_error_change=float(get(a,'heading_sq_change').mean()),
        mean_position_squared_error_change=float(get(a,'xy_sq_change').mean()))
    return r

def parity(rows,refs,expected):
    counts=dict.fromkeys(MODELS[:3],0);maximum=0.
    for row in rows:
        name=row['model']
        if name not in counts:continue
        ref=refs[(name,old.key(row))]
        for field in ('n','accepted_updates','rejected_updates'):
            if int(row[field])!=int(ref[field]):raise RuntimeError('Archived count parity '+field)
        for field in old.PARITY+('heading95',):
            d=abs(float(row[field])-float(ref[field]));maximum=max(maximum,d)
            if not math.isfinite(d) or d>1e-8:raise RuntimeError(f'Archived parity {name} {field} {d}')
        counts[name]+=1
    if any(n!=expected for n in counts.values()):raise RuntimeError('Incomplete parity grid')
    return dict(status='PASS',counts=counts,max_abs_difference=maximum,tolerance=1e-8)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('inputs','reference','parameters','out'):ap.add_argument('--'+k,type=Path,required=True)
    ap.add_argument('--condition',choices=('noise_pair','gyro_bias'),required=True)
    ap.add_argument('--level',type=int,choices=(1,2),required=True)
    ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    contract=old.extension_contract(args.condition,args.level)
    contract.update(models=list(MODELS),arms=['C'],fixed_weight=1/3,donors=list(DONORS),
        parameter_retuning=False,experiment='FIXED_WEIGHT_SAME_PRIOR_AND_RECURSIVE_V1')
    args.out.mkdir(parents=True,exist_ok=False);started=time.time()
    im=json.loads((args.inputs/'MANIFEST.json').read_text())
    for n,h in im['sha256'].items():
        if old.file_sha(args.inputs/n)!=h:raise RuntimeError('Input drift '+n)
    if json.loads((args.inputs/'M0_PARITY.json').read_text())['status']!='PASS':raise RuntimeError('Input gate')
    training=json.loads((args.parameters/'TRAINING_RECEIPT.json').read_text())
    if training['status']!='PASS':raise RuntimeError('Training gate')
    for n,h in training['output_sha256'].items():
        if old.file_sha(args.parameters/n)!=h:raise RuntimeError('Parameter drift '+n)
    params={(r['heldout_route'],r['channel'],r['range_model'],r['arm']):r for r in json.loads((args.parameters/'FROZEN_LOSS_PARAMETERS.json').read_text())}
    prefix='NOISE' if args.condition=='noise_pair' else 'L'+str(args.level)
    refpath=args.reference/(prefix+'_RF_COMPONENT_METRICS.csv')
    rm=json.loads((args.reference/'RESULT_MANIFEST.json').read_text())
    if old.file_sha(refpath)!=rm['sha256'][refpath.name]:raise RuntimeError('Reference drift')
    refs={(r['model'],old.key(r)):r for r in csv.DictReader(refpath.open())}
    sources=old.source_hashes()
    for n in ('run_fixed_weight_comparison.py','fixed_weight_control.py','test_fixed_weight_control.py','FIXED_WEIGHT_PLAN_KO.md'):
        sources[str((HERE/n).relative_to(REPO))]=old.file_sha(HERE/n)
    old.atomic_json(args.out/'EXECUTION_CONTRACT.json',dict(contract=contract,command=sys.argv,
        started_utc=datetime.now(timezone.utc).isoformat(),source_sha256=sources,
        input_sha256=im['sha256'],input_manifest_sha256=old.file_sha(args.inputs/'MANIFEST.json'),
        reference_sha256={refpath.name:old.file_sha(refpath)},parameters_sha256=old.file_sha(args.parameters/'FROZEN_LOSS_PARAMETERS.json'),
        training_receipt_sha256=old.file_sha(args.parameters/'TRAINING_RECEIPT.json')))
    old.atomic_json(args.out/'TRACE_SCHEMA.json',dict(fields=FIELDS,status_codes={'applied':1,'rejected_NIS':0},
        matrix_order='row-major',errors='radians and metres',oracle_usage='evaluation only',
        one_step='donor prior cloned; candidate posterior never recursively propagated'))
    p0=old.check_inputs();lut=old.original_lut(p0);rows=[];ones=[];common_count=0;cell_count=0
    for case in p0['cases']:
        if args.smoke and case['id']!=contract['smoke_case']:continue
        physical=old.archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),tag_height_m=case['robot_z_m'],mount_deg=case['mount_deg'])
        for channel in contract['channels']:
            with np.load(args.inputs/(case['id']+'_'+channel+'.npz')) as cache:
                t,truth,pids=cache['t'],cache['truth'],cache['pose_ids']
                for range_model in contract['range_models']:
                    if range_model not in cache:continue
                    if channel=='full' and range_model=='E1_FULL_LORO' and not np.array_equal(cache[range_model],cache['E1_outer_'+case['route']]):
                        raise RuntimeError('E1 outer-fold mismatch')
                    for seed in ([0] if args.smoke else contract['seeds']):
                        mt,mttruth,mpids,motion,_=old.case_motion(p0,case,seed,args.level,args.condition)
                        if not all(np.array_equal(a,b) for a,b in ((t,mt),(truth,mttruth),(pids,mpids))):raise RuntimeError('Motion mismatch')
                        identity=dict(case=case['id'],channel=channel,range_model=range_model,condition=args.condition,level=args.level,seed=seed,arm='C')
                        shape=params[(case['route'],channel,range_model,'C')]
                        x0=old.initial_state(truth[0],seed);filters={n:make(n,x0,contract) for n in MODELS}
                        candidates={n:make(n,x0,contract) for n in MODELS}
                        rec={n:[] for n in MODELS};one={(d,n):[] for d in DONORS for n in MODELS}
                        for k,tk in enumerate(t):
                            model=cached_model(physical);zs=float(cache['s'][k]);zr=float(cache[range_model][k])
                            rftruth=np.array([zs-model(truth[k])[0],zr-range_h(truth[k],case['anchor'],case['robot_z_m'])[0]])
                            step={}
                            for n,f in filters.items():
                                if k:f.predict(float(motion['ds_odom'][k]),float(motion['dtheta_gyro'][k]),float(motion['dt_s'][k]))
                                step[n]=checked_step(n,f,zs,zr,model,case,contract,shape,truth[k],tk,rf_truth=rftruth)
                                if tk>=contract['eval_start_s']:rec[n].append(step[n])
                            if tk<contract['eval_start_s']:continue
                            for donor in DONORS:
                                dr=step[donor];x=dr[SLICES['prior']];p=dr[SLICES['P_prior']].reshape(3,3)
                                for n,f in candidates.items():
                                    if n==donor:a=dr.copy()
                                    else:
                                        reset(f,x,p)
                                        a=checked_step(n,f,zs,zr,model,case,contract,shape,truth[k],tk,rf_truth=rftruth)
                                    if a[SLICES['applied']][0]!=dr[SLICES['applied']][0]:raise RuntimeError('Same-prior gate divergence')
                                    if not np.array_equal(a[SLICES['prior']],x) or not np.array_equal(a[SLICES['P_prior']],p.ravel()):raise RuntimeError('Prior clone mismatch')
                                    one[(donor,n)].append(a);common_count+=1
                        arrays={}
                        for n,v in rec.items():
                            a=np.asarray(v);arrays['recursive__'+n]=a;rows.append(metrics(a,dict(identity,model=n)))
                        for (d,n),v in one.items():
                            a=np.asarray(v);arrays['one__'+d+'__'+n]=a;ones.append(metrics(a,dict(identity,model=n,donor=d)))
                        cell_count+=1
                        np.savez_compressed(args.out/(case['id']+'__'+channel+'__'+range_model+'__seed'+str(seed)+'.npz'),**arrays)
                        # Fail as soon as any completed cell differs from its frozen baseline.
                        parity(rows,refs,cell_count)
                        print(case['id'],channel,range_model,seed,'cells',cell_count,flush=True)
    expected=3 if args.smoke else 63
    if cell_count!=expected or len(rows)!=expected*4 or len(ones)!=expected*8:raise RuntimeError('Incomplete requested grid')
    par=parity(rows,refs,expected)
    old.write_csv(args.out/'RECURSIVE_METRICS.csv',rows);old.write_csv(args.out/'ONE_STEP_METRICS.csv',ones)
    old.write_csv(args.out/'POOLED_METRICS.csv',old.pooled_metrics(rows))
    old.atomic_json(args.out/'PARITY.json',dict(baseline=par,same_prior_gate='PASS',same_prior_comparisons=common_count,
        gain_correction_Joseph='PASS',input_parameter_hashes='PASS'))
    for n,h in sources.items():
        if old.file_sha(REPO/n)!=h:raise RuntimeError('Source changed during run '+n)
    old.atomic_json(args.out/'MANIFEST.json',dict(status='COMPLETED',scientific_PASS=False,exit_code=0,
        elapsed_s=time.time()-started,completed_utc=datetime.now(timezone.utc).isoformat(),
        input_cells=cell_count,recursive_cells=len(rows),one_step_cells=len(ones),same_prior_comparisons=common_count,
        sha256={p.name:old.file_sha(p) for p in args.out.iterdir() if p.is_file()}))

if __name__=='__main__':main()
