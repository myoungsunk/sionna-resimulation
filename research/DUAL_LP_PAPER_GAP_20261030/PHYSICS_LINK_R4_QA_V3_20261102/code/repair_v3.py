#!/usr/bin/env python3
"""Append-only R4 QA V3 repair on archived DLP-PHYS-LINK-001 retrospective traces.

Does not alter EKF, observations, source FFD, raw/control data, or V1 archives.
No new complete filter recursions or independent audit. Fail-closed QA is
measured, not a hard-coded PASS. Invoke with PYTHONOPTIMIZE=1 as a guard check.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, pathlib, platform, sys, time, datetime
import numpy as np
import pandas as pd
from collections import Counter

TOLS = {
    "exact": 0., "xy": 1e-8, "heading": 1e-10, "state": 1e-10,
    "P": 1e-10, "observer": 1e-10, "control": 1e-10,
    "R": 1e-12, "innovation": 1e-10, "S": 1e-10,
    "NIS": 1e-10, "K": 1e-10, "score": 1e-10,
    "schur_rel": 1e-10, "closure": 1e-12, "source_mean": 1e-12,
}

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def dump(path,obj):
    pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False,default=jsonable)

def jsonable(v):
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,pathlib.Path):return str(v)
    raise TypeError(str(type(v)))

def diff(a,b,angle=False):
    a=np.asarray(a);b=np.asarray(b)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():return float('inf')
    if a.dtype.kind=="b" or b.dtype.kind=="b":return float(np.count_nonzero(a!=b))
    d=a-b
    if angle:d=(d+np.pi)%(2*np.pi)-np.pi
    return float(np.max(np.abs(d))) if d.size else float('inf')

class Ledger:
    def __init__(self):self.rows=[]
    def add(self,cid,scope,error,tolerance_key,n,required=True,context=None,expected="LE"):
        tol=TOLS[tolerance_key]
        ok=bool(np.isfinite(error) and n>0 and (error<=tol if expected=='LE' else error>=tol))
        self.rows.append(dict(check_id=cid,scope=scope,n_compared=int(n),measured_error=float(error) if np.isfinite(error) else None,
                              tolerance=float(tol),comparison=expected,required=required,status='PASS' if ok else 'FAIL',context=context or ''))
        return ok
    def status(self,expected=None):
        rows=[r for r in self.rows if r['required']]
        if expected is not None:
            ids=[r['check_id'] for r in rows]
            counts=Counter(ids)
            missing=sorted(set(expected)-set(ids))
            extra=sorted(set(ids)-set(expected))
            duplicate=sorted(k for k,v in counts.items() if v!=1)
            if missing or extra or duplicate:return 'BLOCKED',{'missing':missing,'unexpected':extra,'duplicate':duplicate}
        if not rows:return 'NOT_RUN',[]
        return ('PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL'),[]

def guard_eq(cid,scope,a,b,tol,n,ledger,angle=False,context=''):
    return ledger.add(cid,scope,diff(a,b,angle),tol,n,context=context)

def shadow_update(x,P,J,R,nu,wrap):
    """4-state Joseph posterior: same frozen update algebra, explicit caller-provided mean."""
    S=J@P@np.swapaxes(J,1,2)+R;S=(S+np.swapaxes(S,1,2))/2
    K=np.linalg.solve(S,J@P).transpose(0,2,1)
    delta=np.einsum('nij,nj->ni',K,nu)
    y=x+delta;y[:,2]=wrap(y[:,2])
    A=np.eye(4)[None]-K@J
    Pn=A@P@np.swapaxes(A,1,2)+K@R@np.swapaxes(K,1,2)
    Pn=(Pn+np.swapaxes(Pn,1,2))/2
    nis=np.einsum('ni,ni->n',nu,np.linalg.solve(S,nu[...,None])[...,0])
    signed=np.stack([K[:,:,0]*nu[:,0,None],K[:,:,1]*nu[:,1,None]],axis=-1)
    return dict(x=y,P=Pn,S=S,K=K,nis=nis,signed=signed,dx=delta)

def no_mean_changed(x,P,J,R,z,h,mu_bb,mu_mb,wrap):
    """Actually substitute MB mean with BB mean and run BOTH complete update paths."""
    before=(hashlib.sha256(mu_bb.tobytes()).hexdigest(),hashlib.sha256(mu_mb.tobytes()).hexdigest())
    forced_mb=mu_mb.copy();forced_mb[:]=mu_bb  # deliberate real mean intervention
    bb=shadow_update(x,P,J,R,z-h-mu_bb,wrap)
    mb_forced=shadow_update(x,P,J,R,z-h-forced_mb,wrap)
    after=(hashlib.sha256(mu_bb.tobytes()).hexdigest(),hashlib.sha256(mu_mb.tobytes()).hexdigest())
    return bb,mb_forced,forced_mb,before==after

def max_comparison(bb,other,threshold):
    keys=['x','P','S','K','nis','signed','dx']
    errors={k:diff(bb[k],other[k]) for k in keys}
    errors['accepted']=diff(bb['nis']<=threshold,other['nis']<=threshold)
    return errors

def r3_and_schur(SRC,OUT,B,ledger):
    details=[];mut=[];alln=0;schur_n=0
    for case in B.CASES:
        for bias in B.BIASES:
            D=B.read_data(case,bias);trace=B.read_trace(case,bias,'BB_ORIG','self')
            x=trace['xp'];P=trace['Pp'];J=trace['J'];h=trace['hx'];z=D['z']
            mu_b=D['mu']['BB'];mu_m=D['mu']['MB'];original_hashes=(sha(SRC/'results/inputs_for_runs'/f'{case}_{bias}.npz'),sha(SRC/'results/shadow'/f'{case}_{bias}.npz'))
            for label,lam in [('ORIG',np.zeros(len(x))),('VAR',trace['sigma_lookup']**2)]:
                R=D['R'].copy();R[:,1,1]+=lam
                bb,forced,copied,unchanged=no_mean_changed(x,P,J,R,z,h,mu_b,mu_m,B.wrap)
                errors=max_comparison(bb,forced,B.DG.GATE)
                errors['innovation']=diff(z-h-mu_b,z-h-copied)
                errors['forced_mean']=diff(copied,mu_b)
                errors['input_unmodified']=0 if unchanged else 1
                check_id=f'R3_MEAN_NULL_{case}_{bias}_{label}'
                worst=max(errors.values());passed=ledger.add(check_id,'REAL_FORCED_MEAN',worst,'closure',len(x))
                # Compare explicit shadow archived reference without taking its old PASS flag.
                shadow_path=SRC/'results/shadow'/f'{case}_{bias}.npz'
                with np.load(shadow_path,allow_pickle=False) as archive:
                    for name,key in [('x','posterior'),('P','P'),('K','K'),('nis','NIS')]:
                        ledger.add(f'R3_ARCHIVE_SHADOW_{case}_{bias}_{label}_{name}','ARCHIVED_REFERENCE',diff(bb[name],archive[f'BB_{label}_{key}']),'K' if name=='K' else 'state' if name=='x' else 'P' if name=='P' else 'NIS',len(x))
                    # Posterior Schur complement from independent precision, compared to recorded 1/Ppsi.
                    precision=np.linalg.inv(P)+J.transpose(0,2,1)@np.linalg.solve(R,J)
                    ii=np.array([0,1,3]);sub=precision[:,ii][:,:,ii]
                    s=precision[:,2,2]-np.einsum('ni,ni->n',precision[:,2,ii],np.linalg.solve(sub,precision[:,ii,2][...,None])[...,0])
                    rel=np.abs(s-1/bb['P'][:,2,2])/np.maximum(np.abs(s),1.)
                    error=float(np.max(rel));schur_n+=len(x)
                    ledger.add(f'R4_SCHUR_{case}_{bias}_{label}','ACTUAL_SCHUR_CALC',error,'schur_rel',len(x))
                    ledger.add(f'R4_ARCHIVED_SCHUR_{case}_{bias}_{label}','ARCHIVED_SCHUR_VS_CALC',diff(s,archive[f'BB_{label}_lambda_eff_psi']),'state',len(x))
                    # Use archived MB path and replace mean via separate call, not only K identity.
                    var_mb=shadow_update(x,P,J,R,z-h-mu_m,B.wrap)
                    if label=='VAR':
                        ledger.add(f'R3_GAIN_INVARIANCE_{case}_{bias}','SAME_R_DIFFERENT_MEAN',diff(bb['K'],var_mb['K']),'K',len(x))
                # sigma=0 must reproduce original mean path, with actual calls.
                if label=='ORIG':
                    zeroR=D['R'].copy();zeroR[:,1,1]+=np.zeros(len(x))
                    zero=shadow_update(x,P,J,zeroR,z-h-mu_b,B.wrap)
                    ze=max(max_comparison(bb,zero,B.DG.GATE).values())
                    ledger.add(f'R3_SIGMA_ZERO_{case}_{bias}','ACTUAL_ZERO_VARIANCE',ze,'closure',len(x))
                # Mutated mean MUST fail in an accepted fixed packet t>=30.
                eligible=np.flatnonzero(D['acc'] & (D['t']>=30-1e-9))
                if len(eligible)==0:raise RuntimeError(f'NO_ACCEPTED_MUTATION_SAMPLE:{case}:{bias}')
                idx=int(eligible[0]);mutated=copied.copy();mutated[idx,0]+=.02;mutated[idx,1]+=.05
                bad=shadow_update(x,P,J,R,z-h-mutated,B.wrap)
                wrong=max_comparison(bb,bad,B.DG.GATE)
                wrong['innovation']=diff(z-h-mu_b,z-h-mutated)
                mutated_detector_fail=not(all(v<=TOLS['closure'] for v in wrong.values()))
                detector_status='FAIL' if not mutated_detector_fail else 'PASS'
                mut.append(dict(check_id=f'MUTATE_MEAN_{case}_{bias}_{label}',packet_id=idx,pose_id=int(D['pose_id'][idx]),expected_validation='FAIL',observed_validation='FAIL' if mutated_detector_fail else 'PASS',mutation={'r_mean_m':.02,'s_mean':.05},max_abs=max(wrong.values()),status=detector_status))
                # Schur result perturbation must fail the standalone measured guard.
                sch_bad=s.copy();sch_bad[idx]+=1e-3*max(1.,abs(s[idx]));bad_rel=float(np.max(np.abs(sch_bad-1/bb['P'][:,2,2])/np.maximum(np.abs(sch_bad),1)))
                mut.append(dict(check_id=f'MUTATE_SCHUR_{case}_{bias}_{label}',expected_validation='FAIL',observed_validation='FAIL' if bad_rel>TOLS['schur_rel'] else 'PASS',max_abs=bad_rel,status='PASS' if bad_rel>TOLS['schur_rel'] else 'FAIL'))
                alln+=len(x)
                details.append(dict(case=case,bias=bias,variance_arm=label,executed=True,n_compared=len(x),errors=errors,max_abs=worst,
                                    atol=TOLS['closure'],rtol=0,source_trace_hash=sha(B.trace_path(case,bias,'BB_ORIG','self')),
                                    source_shadow_sha256=original_hashes[1],source_input_sha256=original_hashes[0],status='PASS' if passed else 'FAIL',
                                    mutation_packet_pose_id=int(D['pose_id'][idx])))
    return details,mut,alln,schur_n

def vectorized_motion_prediction(prev_x,prev_P,ds,gy,dt,wrap):
    """Frozen core.transition/predict expressed in batch arithmetic; no changed motion model."""
    from core import predict
    x=np.asarray(prev_x,float);P=np.asarray(prev_P,float);ds=np.asarray(ds,float);gy=np.asarray(gy,float);dt=np.asarray(dt,float)
    n=len(x)
    a=gy-x[:,3]*dt
    c=np.empty(n);dc=np.empty(n)
    near=np.abs(a)<1e-4
    v=a[near];v2=v*v
    c[near]=1-v2/24+v2*v2/1920-v2**3/322560
    dc[near]=-v/12+v**3/480-v**5/53760
    vv=a[~near];half=vv/2
    c[~near]=np.sin(half)/half
    dc[~near]=(half*np.cos(half)-np.sin(half))/(2*half*half)
    phi=x[:,2]+a/2
    u=np.stack((np.cos(phi),np.sin(phi)),axis=1);up=np.stack((-u[:,1],u[:,0]),axis=1)
    d=ds[:,None]*c[:,None]*u
    v=ds[:,None]*(dc[:,None]*u+c[:,None]*up/2)
    xp=x.copy();xp[:,:2]+=d;xp[:,2]=wrap(x[:,2]+a)
    F=np.broadcast_to(np.eye(4),(n,4,4)).copy();F[:,0,2]=-d[:,1];F[:,1,2]=d[:,0]
    F[:,0,3]=-dt*v[:,0];F[:,1,3]=-dt*v[:,1];F[:,2,3]=-dt
    G=np.zeros((n,4,3))
    G[:,:2,0]=c[:,None]*u;G[:,:2,1]=v;G[:,2,1]=1;G[:,3,2]=1
    q0=2e-5*np.abs(ds);q1=np.radians(.015)**2*dt
    PP=F@P@np.swapaxes(F,1,2)+np.einsum('nij,nj,nkj->nik',G,np.stack((q0,q1,np.zeros(n)),axis=1),G)
    PP=(PP+np.swapaxes(PP,1,2))/2
    return xp,PP

def strict_score_guard(t, reference_t, dt):
    """Validate timing against an independent immutable CONTROL timeline, not itself.

    Counts packets against the original t>=30 s scoring population, and also
    checks which specific samples are scored. Equal timestamps are invalid.
    """
    actual=np.asarray(t,dtype=float)
    original=np.asarray(reference_t,dtype=float)
    dt=np.asarray(dt,dtype=float)
    if actual.shape != original.shape or dt.shape != actual.shape or len(actual)<2:
        return dict(time_order=float('inf'),timeline_reference=float('inf'),timeline_dt=float('inf'),
                    score_count=float('inf'),score_mask=float('inf'))
    delta=np.diff(actual)
    valid_time=np.isfinite(actual).all() and np.isfinite(delta).all() and np.all(delta>0)
    actual_mask=actual>=30-1e-9
    original_mask=original>=30-1e-9
    return dict(
        time_order=float(0 if valid_time else np.count_nonzero(~np.isfinite(delta) | (delta<=0)) or 1),
        timeline_reference=diff(actual,original),
        timeline_dt=diff(delta,dt[1:]),
        score_count=float(abs(int(np.count_nonzero(actual_mask))-int(np.count_nonzero(original_mask)))),
        score_mask=float(np.count_nonzero(actual_mask!=original_mask)))


def required_violations(metrics, norm):
    """Pure fail-closed comparator: every metric must have a declared threshold."""
    if not metrics or set(metrics)!=set(norm):
        return ['MISSING_OR_EXTRA_METRIC']
    return [name for name,value in metrics.items()
            if not np.isfinite(value) or value > TOLS[norm[name]]]


def r4_mutation_probe(B,case,bias,arm,gate,D,T,norm,reference_t,metrics_override=None):
    """One fresh invocation per candidate, with no read of prior test variables.

    metrics_override is deliberately test-only; it can simulate a defeated
    checker. An undetected contaminated sample must make the mutation test FAIL.
    """
    if metrics_override is not None:
        current_metrics=metrics_override
    else:
        try:
            current_metrics=trace_metrics(B,case,bias,arm,gate,D,T,reference_t=reference_t)
        except (ValueError,AssertionError,np.linalg.LinAlgError) as error:
            return dict(detected=True,kind='EXCEPTION',offending_metrics=[type(error).__name__],current_metrics=None)
    failing=required_violations(current_metrics,norm)
    return dict(detected=bool(failing),kind='METRIC',offending_metrics=failing,current_metrics=current_metrics)


def trace_metrics(B,case,bias,arm,gate,D,T,check_motion=True,reference_t=None):
    """Recompute all mandatory EKF trace quantities with frozen algorithm, not PASS strings."""
    from core import predict
    n=len(D['t']);out={};fin=np.isfinite(D['z']).all(1)
    if n==0 or T['X'].shape!=(n,4) or T['PX'].shape!=(n,4,4) or not fin.all():raise ValueError('INVALID_PACKET_GRAIN')
    rho=np.hypot(np.r_[D['x0'][0],T['X'][:-1,0]]-D['anchor'][0],np.r_[D['x0'][1],T['X'][:-1,1]]-D['anchor'][1])
    table=np.asarray(B.DG.HAND[0]);values=np.asarray(B.DG.HAND[1])
    mean_sig=np.interp(rho,table,values)
    expected_R=D['R'].copy()
    if arm.endswith('VAR'):expected_R[:,1,1]+=mean_sig**2
    elif arm.endswith('CONST'):
        constants=json.loads((B.RESULTS/'CONSTANT_VARIANCE_TRAIN_LOCK.json').read_text())['held_route_constants']
        expected_R[:,1,1]+=constants[case]['variance']
    mu=D['mu'][arm[:2]]
    h=T['hx'];J=T['J'];R=T['Ru'];P=T['Pp'];xp=T['xp'];v=T['nu'];S=T['S'];used=T['used']
    out['key_count']=float(abs(len(np.unique(D['pose_id']))-n))
    # Archived CONTROL is independent from the copied/possibly corrupted D.
    if reference_t is None:reference_t=B.C.load_control(case,'B0')['t_s']
    out.update(strict_score_guard(D['t'],reference_t,D['dt']))
    out['initial_state']=diff(xp[0],D['x0'])
    out['initial_P']=diff(P[0],D['P0'])
    out['rho_lookup']=diff(rho,T['rho_lookup'])
    out['R']=diff(R,expected_R)
    out['innovation']=diff(v,D['z']-h-mu)
    SS=J@P@np.swapaxes(J,1,2)+R;SS=(SS+np.swapaxes(SS,1,2))/2
    out['S']=diff(S,SS)
    K=np.linalg.solve(S,J@P).transpose(0,2,1)
    nis=np.einsum('ni,ni->n',v,np.linalg.solve(S,v[...,None])[...,0])
    out['NIS']=diff(nis,T['nis'])
    should_use=fin & ((nis<=B.DG.GATE) if gate=='self' else D['acc'])
    out['mask']=float(np.count_nonzero(should_use!=used))
    y=xp+np.einsum('nij,nj->ni',K,v);y[:,2]=B.wrap(y[:,2]);y[~used]=xp[~used]
    out['post_state']=diff(y,T['X'])
    A=np.eye(4)[None]-K@J
    PP=A@P@np.swapaxes(A,1,2)+K@R@np.swapaxes(K,1,2);PP=(PP+np.swapaxes(PP,1,2))/2;PP[~used]=P[~used]
    out['post_P']=diff(PP,T['PX'])
    out['observer_finite']=0. if np.isfinite(np.c_[h,J.reshape(n,-1),R.reshape(n,-1)]).all() else float('inf')
    out['P_symmetry']=float(np.max(abs(T['PX']-T['PX'].transpose(0,2,1))))
    if check_motion:
        predx=np.empty_like(xp);predP=np.empty_like(P)
        predx[0]=D['x0'];predP[0]=D['P0']
        predx[1:],predP[1:]=vectorized_motion_prediction(T['X'][:-1],T['PX'][:-1],D['ds'][1:],D['gy'][1:],D['dt'][1:],B.wrap)
        delta=predx-xp;delta[:,2]=B.wrap(delta[:,2]);out['motion_prior']=float(np.max(abs(delta)))
        out['motion_Pprior']=diff(predP,P)
    return out

def r4_fail_closed(SRC,OUT,B,ledger):
    scores=pd.read_csv(SRC/'results/tables/RECURSIVE_144_LOGICAL_SCORES.csv');control=pd.read_csv(SRC/'results/tables/CONTROL_STATE_COVARIANCE_PARITY.csv')
    hist=pd.read_csv(SRC/'results/tables/LEGACY_96x9_PARITY.csv')
    if len(scores)!=144 or len(hist)!=864 or len(control)!=12:raise ValueError('REQUIRED_TABLE_MISSING_ROWS')
    for _,r in control.iterrows():
        scope=f"{r['case']}:{r['bias']}:{r['arm']}"
        for key,tol in {'mask_mismatch':'exact','xy_abs_max':'xy','heading_abs_max':'heading','bg_abs_max':'state','P_abs_max':'P','prior_abs_max':'state','Pprior_abs_max':'P','nu_used_abs_max':'innovation','J_used_abs_max':'observer','ds_abs_max':'control','gyro_abs_max':'control'}.items():
            ledger.add(f'R4_CONTROL_{key}_{scope}',scope,float(r[key]),tol,1)
    for _,r in hist.iterrows():
        cid=f"R4_LEGACY_{r['case']}_{r['bias']}_{r['arm']}_{r['gate']}_{r['metric']}"
        actual=float(r['new_at_6sig']);expected=float(r['historical_csv_value'])
        ledger.add(cid,'FROZEN_CSV_6_SIG',abs(actual-expected),'exact',1)
    logical=[];mut=[]
    for _,r in scores.iterrows():
        case,bias,arm,gate=(r[k] for k in ('case','bias','arm','gate'))
        D=B.read_data(case,bias);T=B.read_trace(case,bias,arm,gate)
        scope=f'{case}:{bias}:{arm}:{gate}';trusted_time=B.C.load_control(case,'B0')['t_s'];err=trace_metrics(B,case,bias,arm,gate,D,T,reference_t=trusted_time)
        norm={'key_count':'exact','time_order':'exact','timeline_reference':'exact','timeline_dt':'control','score_mask':'exact','initial_state':'state','initial_P':'P','rho_lookup':'state','R':'R',
              'innovation':'innovation','S':'S','NIS':'NIS','mask':'exact','post_state':'state','post_P':'P','observer_finite':'exact',
              'P_symmetry':'P','motion_prior':'state','motion_Pprior':'P','score_count':'exact'}
        for name,value in err.items():ledger.add(f'R4_TRACE_{name}_{scope}',scope,value,norm[name],len(D['t']))
        # Truth is used ONLY for scoring; re-score all 8 legacy published diagnostics.
        sc=B.PB.scores(D,T['X'],T['PX'])
        for name,value in sc.items():ledger.add(f'R4_SCORE_{name}_{scope}',scope,abs(value-float(r[name])),'score',1)
        ledger.add(f'R4_SCORE_N_USED_{scope}',scope,abs(int(T['used'].sum())-int(r['n_used'])),'exact',1)
        ledger.add(f'R4_SCORE_N_USED_WINDOW_{scope}',scope,abs(int((T['used']&(D['t']>=30-1e-9)).sum())-int(r['n_used_score'])),'exact',1)
        logical.append(dict(case=case,bias=bias,arm=arm,gate=gate,n=int(len(D['t'])),errors=err,score_residual_max=max(abs(sc[k]-float(r[k])) for k in sc)))
        if case==B.CASES[0] and bias=='B0' and arm=='MB_VAR' and gate=='self':
            # Actual field corruption and changed check results, not merely a row-status edit.
            t={key:(val.copy() if isinstance(val,np.ndarray) else val) for key,val in T.items()}
            base=err
            variants={'prior_x':('xp',0,(3e-3,0)), 'Pprior':('Pp',0,(4e-3,0,0)),
                      'h':('hx',0,(3e-3,0)), 'J':('J',0,(2e-3,0,0)), 'R':('Ru',0,(2e-3,0,0)),
                      'nu':('nu',0,(3e-3,0)), 'S':('S',0,(2e-3,0,0)),
                      'post_x':('X',0,(3e-3,0)), 'post_P':('PX',0,(4e-3,0,0)),
                      'mask':('used',0,None)}
            for label,(key,k,values) in variants.items():
                mutated={a:(v.copy() if isinstance(v,np.ndarray) else v) for a,v in T.items()}
                if label=='mask':mutated[key][k]=~mutated[key][k]
                else:
                    amount=values[0];index=(k,)+tuple(values[1:]);mutated[key][index]+=amount
                got=trace_metrics(B,case,bias,arm,gate,D,mutated,check_motion=True)
                detected=any(got[c]>TOLS[norm[c]] for c in got)
                mut.append(dict(id=f'R4_MUTATE_{label}',source_trace_sha256=sha(B.trace_path(case,bias,arm,gate)),
                                expected='FAIL',observed='FAIL' if detected else 'PASS',status='PASS' if detected else 'FAIL',
                                offending_metrics=[c for c in got if got[c]>TOLS[norm[c]]]))
            # controls must enter actual predictor; corrupt ds / gyro / dt without modifying truth.
            for name in ['ds','gy','dt']:
                copied={k:(v.copy() if isinstance(v,np.ndarray) else v) for k,v in D.items()}
                copied[name][1]+=0.03 if name!='dt' else 0.02
                got=trace_metrics(B,case,bias,arm,gate,copied,T)
                detected=any(got[c]>TOLS[norm[c]] for c in got)
                mut.append(dict(id=f'R4_MUTATE_CONTROL_{name}',expected='FAIL',observed='FAIL' if detected else 'PASS',
                                status='PASS' if detected else 'FAIL',offending_metrics=[c for c in got if got[c]>TOLS[norm[c]]]))
            # Score and pose/timestamp negatives; don't contaminate original arrays.
            corruption=({**r.to_dict(),'head_rmse':float(r['head_rmse'])+0.1})
            detect=abs(sc['head_rmse']-corruption['head_rmse'])>TOLS['score']
            mut.append(dict(id='R4_MUTATE_SCORE',expected='FAIL',observed='FAIL' if detect else 'PASS',status='PASS' if detect else 'FAIL'))
            # Fresh, isolated probes: no 'got' inherited from prior dt mutation.
            def make_corruption(name):
                copied={k:(v.copy() if isinstance(v,np.ndarray) else v) for k,v in D.items()}
                if name=='pose_id':copied['pose_id'][1]=copied['pose_id'][0]
                elif name=='t':copied['t'][1]=copied['t'][0]-1.0
                elif name=='t_equal':copied['t'][1]=copied['t'][0]
                elif name=='score_window_shift':copied['t']+=1.0
                else:raise ValueError(f'UNKNOWN_CORRUPTION:{name}')
                return copied
            probes={}
            for name in ('pose_id','t','t_equal','score_window_shift'):
                copied=make_corruption(name)
                probe=r4_mutation_probe(B,case,bias,arm,gate,copied,T,norm,trusted_time)
                probes[name]=probe
                detected=probe['detected']
                mut.append(dict(id=f'R4_MUTATE_{name}',expected='FAIL',observed='FAIL' if detected else 'PASS',
                                status='PASS' if detected else 'FAIL',offending_metrics=probe['offending_metrics'],
                                actual_return_current_call=True))
                # Defeat the *current* detector deliberately: this negative test
                # must report FAIL, else the mutation harness is vacuous.
                all_zero={metric:0.0 for metric in norm}
                defeated=r4_mutation_probe(B,case,bias,arm,gate,copied,T,norm,trusted_time,metrics_override=all_zero)
                selftest_pass=not defeated['detected']
                mut.append(dict(id=f'R4_MUTATE_DETECTOR_DISABLED_{name}',expected='UNDETECTED',
                                observed='UNDETECTED' if selftest_pass else 'DETECTED',
                                status='PASS' if selftest_pass else 'FAIL',offending_metrics=defeated['offending_metrics'],
                                observed_negative_test_status='FAIL' if selftest_pass else 'PASS'))
            # Normal input must not be rejected. No hidden previous result.
            clean=r4_mutation_probe(B,case,bias,arm,gate,D,T,norm,trusted_time)
            ok=not clean['detected']
            mut.append(dict(id='R4_NORMAL_INPUT_NO_FALSE_POSITIVE',expected='NOT_DETECTED',
                            observed='NOT_DETECTED' if ok else 'DETECTED',status='PASS' if ok else 'FAIL',
                            offending_metrics=clean['offending_metrics']))
            # Reordering probes and isolated invocation must yield the same outcomes.
            order_ok=True
            for name in reversed(list(probes)):
                stand=r4_mutation_probe(B,case,bias,arm,gate,make_corruption(name),T,norm,trusted_time)
                if (stand['detected']!=probes[name]['detected'] or
                        stand['offending_metrics']!=probes[name]['offending_metrics']):order_ok=False
            mut.append(dict(id='R4_PROBE_ORDER_INVARIANCE',expected='IDENTICAL',
                            observed='IDENTICAL' if order_ok else 'DIFFERENT',status='PASS' if order_ok else 'FAIL'))
            solo=r4_mutation_probe(B,case,bias,arm,gate,make_corruption('t_equal'),T,norm,trusted_time)
            solo_ok=solo['detected'] and solo['offending_metrics']==probes['t_equal']['offending_metrics']
            mut.append(dict(id='R4_PROBE_STANDALONE_INVARIANCE',expected='IDENTICAL',
                            observed='IDENTICAL' if solo_ok else 'DIFFERENT',status='PASS' if solo_ok else 'FAIL'))
            # Bad stored K from shadow must be detectable against independently calculated K.
            sh=SRC/'results/shadow'/f'{case}_{bias}.npz'
            with np.load(sh,allow_pickle=False) as data:
                altered=data['MB_VAR_K'].copy();altered[0,2,1]+=0.05
                base=B.read_trace(case,bias,'BB_ORIG','self')
                jj=base['J'];pp=base['Pp'];RR=D['R'].copy();RR[:,1,1]+=base['sigma_lookup']**2
                ss=jj@pp@jj.transpose(0,2,1)+RR
                true_k=np.linalg.solve(ss,jj@pp).transpose(0,2,1)
                detect=diff(altered,true_k)>TOLS['K']
                mut.append(dict(id='R4_MUTATE_K',expected='FAIL',observed='FAIL' if detect else 'PASS',status='PASS' if detect else 'FAIL'))
    return logical,mut

def r5_divergence(SRC,OUT,B,ledger):
    scores=pd.read_csv(SRC/'results/tables/RECURSIVE_144_LOGICAL_SCORES.csv')
    rec=[];shadow_rows=[]
    keys=['previous_x','previous_P','rho_lookup','sigma_b_effective','control_ds','control_gyro','control_dt',
          'prior_x','prior_P','h','J','mu','R','nu','S','K','NIS','accepted','post_x','post_P']
    def snap(T,D,arm,k):
        X=T['X'];P=T['PX'];mu=D['mu'][arm[:2]][k]
        S=T['S'][k];J=T['J'][k];K=np.linalg.solve(S,J@T['Pp'][k]).T
        sigma=float(math.sqrt(max(0,T['Ru'][k,1,1]-D['R'][k,1,1])))
        return dict(previous_x=(D['x0'] if k==0 else X[k-1]).tolist(),
                    previous_P=(D['P0'] if k==0 else P[k-1]).tolist(),
                    rho_lookup=float(T['rho_lookup'][k]),sigma_b_effective=sigma,
                    control_ds=float(D['ds'][k]),control_gyro=float(D['gy'][k]),control_dt=float(D['dt'][k]),
                    prior_x=T['xp'][k].tolist(),prior_P=T['Pp'][k].tolist(),h=T['hx'][k].tolist(),
                    J=J.tolist(),mu=mu.tolist(),R=T['Ru'][k].tolist(),nu=T['nu'][k].tolist(),S=S.tolist(),
                    K=K.tolist(),NIS=float(T['nis'][k]),accepted=bool(T['used'][k]),
                    post_x=X[k].tolist(),post_P=P[k].tolist())
    for _,score in scores.iterrows():
        case,bias,arm,gate=(score[c] for c in ['case','bias','arm','gate']);D=B.read_data(case,bias)
        base=B.read_trace(case,bias,'BB_ORIG',gate);other=B.read_trace(case,bias,arm,gate)
        def fields_at(k):
            a=snap(base,D,'BB_ORIG',k);b=snap(other,D,arm,k)
            errors={f:(float(a[f]!=b[f]) if f=='accepted' else diff(np.asarray(a[f]),np.asarray(b[f]),angle=False)) for f in keys}
            different=[f for f in keys if errors[f]>(0. if f=='accepted' else 1e-10)]
            return a,b,errors,different
        first_post=None;first_gate=None;first_field=None;first_any=None
        dx=other['X']-base['X'];dx[:,2]=B.wrap(dx[:,2]);mask=(abs(dx)>np.array([1e-8,1e-8,1e-10,1e-10])).any(1)
        pp=np.where(mask)[0];first_post=int(pp[0]) if len(pp) else None
        gg=np.where(other['used']!=base['used'])[0];first_gate=int(gg[0]) if len(gg) else None
        for k in range(len(D['t'])):
            # First physical filter-contract difference (not sampling/clock).
            if arm=='BB_ORIG':break
            a,b,e,d=fields_at(k)
            if d: first_any=k;first_field=d[0];break
        k=(first_any if first_any is not None else (first_post if first_post is not None else 0))
        a,b,e,d=fields_at(k)
        must=['control_ds','control_gyro','control_dt']
        bad=[f for f in must if e[f]>0]
        if k==0:bad += [f for f in ['previous_x','previous_P','prior_x','prior_P','h','J','rho_lookup'] if e[f]>TOLS['state']]
        if gate=='fixed' and np.any(other['used']!=base['used']):bad.append('fixed_mask_diff')
        ledger.add(f'R5_CONTRACT_{case}_{bias}_{arm}_{gate}','MUST_EQUAL_FIELDS',len(bad),'exact',len(D['t']))
        # Assertions force actual source row from immutable archived input files.
        rec.append(dict(case=case,bias=bias,reference_arm='BB_ORIG',target_arm=arm,gate=gate,
                        packet_id=k,pose_id=int(D['pose_id'][k]),t_s=float(D['t'][k]),
                        first_state_difference_packet=first_post,first_gate_difference_packet=first_gate,
                        first_differing_field=first_field or 'NONE',first_difference_fields=d,measured_errors=e,
                        reference=a,target=b,must_be_equal_fields=must+(['previous_x','previous_P','prior_x','prior_P','h','J','rho_lookup'] if k==0 else []),
                        must_equal_checks={'pass':not bad,'violations':bad},
                        allowed_intervention_fields=['mu','R','nu','S','K','NIS','accepted','post_x','post_P'],
                        recursive_feedback_allowed_after_first_state_divergence=['previous_x','previous_P','prior_x','prior_P','rho_lookup','h','J'],
                        score_window='ALL_T_GE_30_S_FOR_FINAL_RMSE',analysis_class='RECURSIVE_TRAJECTORY_DIVERGENCE',
                        source_trace_sha256={'reference':sha(B.trace_path(case,bias,'BB_ORIG','self' if gate=='fixed' else gate)),
                                             'target':sha(B.trace_path(case,bias,arm,'self' if arm=='BB_ORIG' and gate=='fixed' else gate))}))
    for case in B.CASES:
        for bias in B.BIASES:
            sh=SRC/'results/shadow'/f'{case}_{bias}.npz'
            with np.load(sh,allow_pickle=False) as z:
                for target in ['BB_ORIG','MB_ORIG','BB_VAR','MB_VAR']:
                    aa=z['BB_ORIG_posterior'];bb=z[target+'_posterior']
                    dd=bb-aa;dd[:,2]=B.wrap(dd[:,2]);indices=np.where(np.any(abs(dd)>1e-10,axis=1))[0]
                    k=int(indices[0]) if len(indices) else 0
                    prior=z['prior'][k];P=z['Pprior'][k]
                    shadow_rows.append(dict(case=case,bias=bias,reference_arm='BB_ORIG',target_arm=target,packet_id=k,
                                            pose_id=int(z['pose_id'][k]),t_s=float(z['t_s'][k]),
                                            same_prior_x=prior.tolist(),same_prior_P=P.tolist(),J=z['J'][k].tolist(),
                                            reference_nu=z['BB_ORIG_nu'][k].tolist(),target_nu=z[target+'_nu'][k].tolist(),
                                            reference_K=z['BB_ORIG_K'][k].tolist(),target_K=z[target+'_K'][k].tolist(),
                                            reference_post_x=aa[k].tolist(),target_post_x=bb[k].tolist(),
                                            source_shadow_sha256=sha(sh),analysis_class='SAME_PRIOR_SHADOW'))
    pd.DataFrame([{k:v for k,v in x.items() if k not in ['reference','target','measured_errors']}
                    |{'reference':json.dumps(x['reference'],separators=(',',':')),'target':json.dumps(x['target'],separators=(',',':')),
                      'measured_errors':json.dumps(x['measured_errors'],separators=(',',':'))} for x in rec]).to_csv(OUT/'results/FIRST_DIVERGENCE_DETAILS_V3.csv',index=False)
    dump(OUT/'results/FIRST_DIVERGENCE_DETAILS_V3.json',{'rows':rec,'number_of_records':len(rec),'schema_version':'2.0'})
    dump(OUT/'results/SAME_PRIOR_SHADOW_DIVERGENCE_V3.json',{'rows':shadow_rows,'number_of_records':len(shadow_rows)})
    return rec,shadow_rows

def r6_stratified(SRC,OUT,B,ledger):
    # Supporting explanation; no causal promotion or new design.
    phy=pd.read_csv(SRC/'results/PHYSICS_PACKET_LEDGER.csv.gz')
    sh=pd.read_csv(SRC/'results/MATCHED_PRIOR_2X2.csv.gz')
    fd=pd.read_csv(SRC/'results/tables/FFD_FD_CHECKS.csv')
    stable=(fd.groupby(['case','pose_id']).stable_branch.agg('all').reset_index().rename(columns={'stable_branch':'stable_all_xyz'}))
    if phy.duplicated(['case','pose_id','t_s']).any():raise ValueError('DUPLICATE_PHYSICS_KEYS')
    if stable.duplicated(['case','pose_id']).any():raise ValueError('DUPLICATE_STABILITY_KEYS')
    if sh.duplicated(['case','bias','pose_id','t_s','arm']).any():raise ValueError('DUPLICATE_SHADOW_KEYS')
    merged=sh.merge(phy[['case','pose_id','t_s','rho_true_m','relative_yaw_rad','Full_tap','SourceFFD_tap','J_spsi_per_rad']],on=['case','pose_id','t_s'],how='left',validate='many_to_one',indicator=True)
    if not (merged['_merge']=='both').all():raise ValueError('UNMATCHED_PHYSICS_PACKET')
    merged=merged.merge(stable,on=['case','pose_id'],how='left',validate='many_to_one')
    if merged['stable_all_xyz'].isna().any():raise ValueError('MISSING_FD_STABILITY')
    merged['rho_bin']=pd.cut(merged.rho_true_m,[-.001,1.5,3,6,10,1000],labels=['0–1.5m','1.5–3m','3–6m','6–10m','≥10m'],right=False)
    merged['bearing_bin']=pd.cut(np.degrees(merged.relative_yaw_rad).add(180).mod(360).sub(180),[-181,-90,-30,30,90,181],labels=['-180:-90','-90:-30','-30:30','30:90','90:180'])
    merged['tap_bin']=np.where(merged.Full_tap==merged.SourceFFD_tap,'TAP_EQUAL','TAP_DIFFERENT')
    merged['Kpsi_eps_r_deg']=np.degrees(merged.K_psi_r*merged.epsilon_r)
    merged['Kpsi_eps_s_deg']=np.degrees(merged.K_psi_s*merged.epsilon_s)
    merged['Kpsi_delta_h_deg']=np.degrees(merged.K_psi_r*merged.delta_h_r+merged.K_psi_s*merged.delta_h_s)
    merged['Kpsi_nu_total_deg']=np.degrees(merged.K_psi_r*merged.nu_r+merged.K_psi_s*merged.nu_s)
    merged['is_accepted']=merged.fixed_accepted.astype(bool)
    merged['n_stable']=merged.stable_all_xyz.astype(int)
    merged['scoring']=merged.primary_score_mask.astype(bool)
    # Preserve sparse, zero and opposite-direction strata, including unlabeled buckets.
    frames=[]
    for group_type,by in [('DISTANCE',['rho_bin']),('BEARING',['bearing_bin']),('TAP',['tap_bin']),('DISTANCE_X_TAP',['rho_bin','tap_bin'])]:
        cols=['case','bias','arm']+by
        for key,g in merged.groupby(cols,observed=True,sort=True,dropna=False):
            if not isinstance(key,tuple):key=(key,)
            n=len(g);accepted=g[g.is_accepted];scored=g[g.scoring]
            if n==0:continue
            row=dict(zip(cols,[str(x) for x in key]));row.update(group_type=group_type,n_all=n,
              n_used=int(g.is_accepted.sum()),n_stable=int(g.stable_all_xyz.sum()),
              n_used_and_stable=int((g.is_accepted & g.stable_all_xyz).sum()),
              n_score=int(g.scoring.sum()),n_score_and_stable=int((g.scoring & g.stable_all_xyz).sum()),
              signed_Kpsi_eps_r_deg_mean=float(accepted.Kpsi_eps_r_deg.mean()) if len(accepted) else None,
              signed_Kpsi_eps_s_deg_mean=float(accepted.Kpsi_eps_s_deg.mean()) if len(accepted) else None,
              signed_Kpsi_delta_h_deg_mean=float(accepted.Kpsi_delta_h_deg.mean()) if len(accepted) else None,
              signed_Kpsi_nu_total_deg_mean=float(accepted.Kpsi_nu_total_deg.mean()) if len(accepted) else None,
              head_loss_deg2_mean=float(scored.head_loss_deg2.mean()) if len(scored) else None,
              xy_loss_cm2_mean=float(scored.xy_loss_cm2.mean()) if len(scored) else None,
              sparse_n_used_lt_10=len(accepted)<10,truth_role='OFFLINE_DIAGNOSTIC_ONLY',
              note='Not a temporal cumulative causal decomposition')
            frames.append(row)
    f=pd.DataFrame(frames)
    f.to_csv(OUT/'results/PHYSICS_SHADOW_STRATA_V3.csv',index=False,float_format='%.17g')
    ledger.add('R6_EXACT_JOIN','ALL_50176_SHADOW_ROWS',abs(len(merged)-len(sh)),'exact',len(merged),required=False)
    ledger.add('R6_STABILITY_JOIN','ALL_50176_SHADOW_ROWS',int(merged.stable_all_xyz.isna().sum()),'exact',len(merged),required=False)
    return dict(stratified_rows=len(f),matched_rows=len(merged),unique_physics_packets=len(phy),sparse_rows=int(f.sparse_n_used_lt_10.sum()),
                group_types=sorted(f.group_type.unique().tolist()),note='Diagnostic joining only; not V4 cumulative causal evidence')

def expected_required_check_ids(B, source_root):
    """Independent declared matrix, not acceptance derived from executed test rows."""
    ids=[]
    arms=['BB_ORIG','BB_VAR','BB_CONST','MB_ORIG','MB_VAR','MB_CONST']
    trace_fields=['key_count','time_order','timeline_reference','timeline_dt','score_mask','initial_state','initial_P','rho_lookup','R','innovation','S','NIS','mask',
                  'post_state','post_P','observer_finite','P_symmetry','score_count','motion_prior','motion_Pprior']
    metrics=['head_rmse','head_bias','xy_rmse_cm','range_rmse_cm','head_z_rms','head_cov95','nees_xy','xy_cov95']
    historical_metrics=metrics+['n_used']
    for c in B.CASES:
      for b in B.BIASES:
        for v in ['ORIG','VAR']:
          ids+= [f'R3_MEAN_NULL_{c}_{b}_{v}',f'R4_SCHUR_{c}_{b}_{v}',f'R4_ARCHIVED_SCHUR_{c}_{b}_{v}']
          ids.extend(f'R3_ARCHIVE_SHADOW_{c}_{b}_{v}_{nm}' for nm in ['x','P','K','nis'])
        ids += [f'R3_SIGMA_ZERO_{c}_{b}',f'R3_GAIN_INVARIANCE_{c}_{b}']
        for a in arms:
          for g in ['fixed','self']:
            scope=f'{c}:{b}:{a}:{g}'
            ids.extend(f'R4_TRACE_{field}_{scope}' for field in trace_fields)
            ids.extend(f'R4_SCORE_{metric}_{scope}' for metric in metrics)
            ids.extend([f'R4_SCORE_N_USED_{scope}',f'R4_SCORE_N_USED_WINDOW_{scope}'])
            ids.append(f'R5_CONTRACT_{c}_{b}_{a}_{g}')
        for a in ['BB_ORIG','BB_VAR','MB_ORIG','MB_VAR']:
          for g in ['fixed','self']:
            ids.extend(f'R4_LEGACY_{c}_{b}_{a}_{g}_{metric}' for metric in historical_metrics)
        if b in ['B0','L2']:
          for a in ['BB_ORIG','MB_ORIG']:
            scope=f'{c}:{b}:{a}'
            for f in ['mask_mismatch','xy_abs_max','heading_abs_max','bg_abs_max','P_abs_max','prior_abs_max','Pprior_abs_max',
                      'nu_used_abs_max','J_used_abs_max','ds_abs_max','gyro_abs_max']:
              ids.append(f'R4_CONTROL_{f}_{scope}')
        for v in ['ORIG','VAR']:
          ids.extend([f'MUTATION_CHECK_MUTATE_MEAN_{c}_{b}_{v}',f'MUTATION_CHECK_MUTATE_SCHUR_{c}_{b}_{v}'])
    for label in ['prior_x','Pprior','h','J','R','nu','S','post_x','post_P','mask']:
       ids.append(f'MUTATION_CHECK_R4_MUTATE_{label}')
    for label in ['ds','gy','dt']:ids.append(f'MUTATION_CHECK_R4_MUTATE_CONTROL_{label}')
    ids.extend(['MUTATION_CHECK_R4_MUTATE_SCORE','MUTATION_CHECK_R4_MUTATE_pose_id','MUTATION_CHECK_R4_MUTATE_t',
                'MUTATION_CHECK_R4_MUTATE_t_equal','MUTATION_CHECK_R4_MUTATE_score_window_shift',
                *[f'MUTATION_CHECK_R4_MUTATE_DETECTOR_DISABLED_{name}' for name in ('pose_id','t','t_equal','score_window_shift')],
                'MUTATION_CHECK_R4_NORMAL_INPUT_NO_FALSE_POSITIVE',
                'MUTATION_CHECK_R4_PROBE_ORDER_INVARIANCE','MUTATION_CHECK_R4_PROBE_STANDALONE_INVARIANCE',
                'MUTATION_CHECK_R4_MUTATE_K','MUTATION_CHECK_FAIL_CLOSED_MISSING_REQUIRED_CHECK',
                'MUTATION_CHECK_FAIL_CLOSED_INJECTED_NUMERIC_ERROR','R1_ORIGINAL_SOURCE_IMMUTABILITY'])
    if len(ids)!=5729:raise RuntimeError(f'EXPECTED_REQUIRED_MATRIX_COUNT:{len(ids)}')
    if len(set(ids))!=len(ids):raise RuntimeError('DECLARED_DUPLICATE_REQUIRED_ID')
    return ids

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source-root',required=True);ap.add_argument('--out',required=True);ap.add_argument('--audit-sha',default='25e16bfb71786835dbd7260467e243016c0bca6b');args=ap.parse_args()
    SRC=pathlib.Path(args.source_root).resolve();OUT=pathlib.Path(args.out).resolve()
    if SRC==OUT or OUT in SRC.parents or SRC in OUT.parents:raise ValueError('MUST_BE_APPEND_ONLY_SEPARATE_ROOT')
    OUT.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(SRC/'code'))
    import bootstrap as B
    from core import predict
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    record=Ledger();t0=time.monotonic()
    # Preflight input and archived source identity without rewriting old files.
    inputs=json.loads((SRC/'contracts/INPUT_LOCK.json').read_text())['files']
    missing=[];bad=[]
    for f in inputs:
        p=SRC/'recovered'/f['path']
        if not p.is_file():missing.append(str(p));continue
        if sha(p)!=f['sha256']:bad.append(f['path'])
    if missing or bad:raise RuntimeError('INPUT_LOCK_MISMATCH '+str({'missing':missing,'bad':bad}))
    previous_manifest=SRC/'MANIFEST.json';old_config=SRC/'contracts/CONFIG_LOCK.json'
    input_lock=SRC/'contracts/INPUT_LOCK.json'
    source_trace_hash={p.name:sha(p) for p in sorted((SRC/'results/traces').glob('*.npz'))}
    if len(source_trace_hash)!=132:raise RuntimeError('TRACE_COUNT_DIFFERENT_FROM_FROZEN_RECONSTRUCTION')
    source_qa=sha(SRC/'QA.json')
    # Proactively verify immutable score counts before any new tests.
    scores_path=SRC/'results/tables/RECURSIVE_144_LOGICAL_SCORES.csv'
    if len(pd.read_csv(scores_path))!=144:raise RuntimeError('144_LOGICAL_SCORE_COUNT_REQUIRED')
    source_counters=dict(n_input_files=len(inputs),n_trace_files=len(source_trace_hash),n_score_rows=144)
    code_sha=sha(pathlib.Path(__file__).resolve())
    admission=dict(contract_id='DLP-PHYS-LINK-001',record_id='RUN_ADMISSION_RECORD_V3',status='RETROSPECTIVE_REPAIR_AUTHORIZED',
      action='R4 isolated-probe, strictly-increasing time, independent score denominator guard correction; no estimator edits',
      user_authority='2026-11-02 user explicitly requests repair, rerun and GitHub push for remaining R4 QA defects (stale detector, strict time, scoring denominator)',
      current_user_instruction_id='DLP-PHYS-LINK-001-R4-GUARD-USER-20261102',
      current_run_utc=now,role='IMPLEMENTER',review_role='SELF_REVIEW_ONLY_PENDING_DISTINCT_AUDITOR',
      allowed_phases=['RETROSPECTIVE_R4_QA_REPAIR_V3','FAIL_CLOSED_QA','SOURCE_LOCKED_REAGGREGATION','REPORT_AND_GITHUB_PUBLISH'],
      excluded=['EKF_OR_OBSERVATION_MODEL_CHANGE','NEW_RT','NEW_TRAINING','NEW_FULL_RECURSIVE_SWEEP','PREREGISTERED_RESULT_CLAIM'],
      source_reconstruction_class='NEW_RETROSPECTIVE_RECONSTRUCTION',source_reconstruction_qa_sha256=source_qa,
      source_manifest_sha256=sha(previous_manifest),source_config_sha256=sha(old_config),
      source_input_lock_sha256=sha(input_lock),source_scores_sha256=sha(scores_path),
      source_code_sha256={p.name:sha(p) for p in sorted((SRC/'code').glob('*.py'))},
      repair_code_sha256=code_sha,
      referenced_auditor_report_commit=args.audit_sha,
      old_execution_original_commit={'claimed_sha':'1550335002367c656939bab4876675c612f0915c','availability':'MISSING_NOT_RECOVERED'},
      independent_pre_run_signoff='UNAVAILABLE_NOT_RETROACTIVE',prior_scientific_results_observed=True,
      retrospective_acceptance_not_prerun_signoff=True,document_edit_permission='GRANTED_FOR_NEW_APPEND_ONLY_FILES',
      code_execution_permission='GRANTED_FOR_LIMITED_R4_QA_REPAIR',public_github_push_permission='USER_EXPLICIT',
      manuscript_publication_permission='NOT_REQUESTED',source_data_preserved=True)
    dump(OUT/'contracts/RUN_ADMISSION_RECORD_V3.json',admission)
    checks=[]
    details,mean_mut,nshadow,schurn=r3_and_schur(SRC,OUT,B,record)
    dump(OUT/'results/NULL_AND_MUTATION_TESTS_V3.json',dict(real_mean_null_checks=details,negative_mutation_checks=mean_mut,
      expected_negative_failures=len(mean_mut),observed_negative_failures=sum(x['status']=='PASS' for x in mean_mut),
      original_mean_array_immutability='SHA_OF_SOURCE_NPZ_VERIFIED_AT_END',n_compared=nshadow,schur_checks_total=schurn))
    logical,trace_mut=r4_fail_closed(SRC,OUT,B,record)
    first,shadow=r5_divergence(SRC,OUT,B,record)
    r6=r6_stratified(SRC,OUT,B,record)
    all_mut=mean_mut+trace_mut
    # Controls for missing required data and validator itself must be fail-closed.
    test=Ledger();test.add('MUTATION_REQUIRED_DETECTOR','demo',0,'exact',1)
    expected=['MUTATION_REQUIRED_DETECTOR','MISSING_REQUIRED_TEST']
    missing_blocks=test.status(expected)[0]=='BLOCKED'
    failing=Ledger();failing.add('MUTATED_VALUE','demo',TOLS['observer']+1e-4,'observer',1)
    failure_blocks=failing.status()[0]=='FAIL'
    mut_extra=[dict(id='FAIL_CLOSED_MISSING_REQUIRED_CHECK',expected='BLOCKED',observed='BLOCKED' if missing_blocks else 'PASS',status='PASS' if missing_blocks else 'FAIL'),
               dict(id='FAIL_CLOSED_INJECTED_NUMERIC_ERROR',expected='FAIL',observed='FAIL' if failure_blocks else 'PASS',status='PASS' if failure_blocks else 'FAIL')]
    all_mut+=mut_extra
    for m in all_mut:record.add('MUTATION_CHECK_'+m.get('check_id',m.get('id','unknown')),'NEGATIVE_TEST',0 if m['status']=='PASS' else 1,'exact',1)
    expected_ids=expected_required_check_ids(B,SRC)
    status,missing_required=record.status(expected_ids)
    pd.DataFrame(record.rows).to_csv(OUT/'results/REQUIRED_CHECKS_V3.csv',index=False,float_format='%.17g')
    dump(OUT/'results/REQUIRED_CHECKS_V3.json',dict(status=status,n_required=sum(x['required'] for x in record.rows),n_optional=sum(not x['required'] for x in record.rows),
      n_passed=sum(x['status']=='PASS' and x['required'] for x in record.rows),
      n_failed=sum(x['status']=='FAIL' and x['required'] for x in record.rows),missing_required=missing_required,thresholds=TOLS,
      derived_by='all(required_checks); required missing/empty is BLOCKED; failures cause FAIL',
      definition='Historical QA is preserved; this V3 gate supersedes only R4 V2 QA evidence, not past preregistration'))
    dump(OUT/'results/NULL_AND_MUTATION_TESTS_V3_SUPPLEMENT.json',dict(negative_mutation_checks=trace_mut+mut_extra,
      n_expected_failures=len(all_mut),n_observed_failures=sum(x['status']=='PASS' for x in all_mut)))
    # Provenance output hash ledger with old archives unchanged.
    original_unchanged=source_qa==sha(SRC/'QA.json') and source_counters['n_trace_files']==len(list((SRC/'results/traces').glob('*.npz')))
    original_unchanged=original_unchanged and all(sha(B.trace_path(*parse_trace_filename(name)))==hashv for name,hashv in source_trace_hash.items())
    record.add('R1_ORIGINAL_SOURCE_IMMUTABILITY','OLD_TRACES_AND_QA',0 if original_unchanged else 1,'exact',len(source_trace_hash))
    status,missing_required=record.status(expected_ids)
    dump(OUT/'results/REQUIRED_CHECKS_V3.json',dict(status=status,n_required=sum(x['required'] for x in record.rows),n_optional=sum(not x['required'] for x in record.rows),
      n_passed=sum(x['status']=='PASS' and x['required'] for x in record.rows),
      n_failed=sum(x['status']=='FAIL' and x['required'] for x in record.rows),missing_required=missing_required,thresholds=TOLS,
      derived_by='all(required_checks); required missing/empty is BLOCKED; failures cause FAIL'))
    pd.DataFrame(record.rows).to_csv(OUT/'results/REQUIRED_CHECKS_V3.csv',index=False,float_format='%.17g')
    verdict=dict(status=status,repair_ids={'R1':'METADATA_PREPARED_GITHUB_PUBLISH_PENDING',
      'R2':'PASS_APPEND_ONLY_ADMISSION','R3':'PASS_ACTUAL_MEAN_NULL' if all(x['status']=='PASS' for x in mean_mut) else 'FAIL',
      'R4':'PASS_STRICT_TIME_SCORE_AND_ISOLATED_PROBES' if status=='PASS' else 'FAIL',
      'R5':'PASS_FIRST_DIVERGENCE_VALUES' if len(first)==144 and len(shadow)==48 else 'FAIL'},
      n_mean_null_batches=len(details),n_mean_null_packet_comparisons=nshadow,n_first_divergence=len(first),
      n_same_prior_ledger=len(shadow),n_mutations=len(all_mut),mutations_pass=sum(x['status']=='PASS' for x in all_mut),
      trace_keys=len(logical),r6_stratified=r6,input_files_verified=len(inputs),original_132_traces_unchanged=original_unchanged,
      original_144_scores_unchanged=sha(scores_path),old_original_commit='MISSING',
      source_reconstruction='NEW_RETROSPECTIVE_RECONSTRUCTION',independent_audit='SELF_REVIEW_ONLY',
      scientific_interpretation='MIXED',v4='NOT_RUN_OPTIONAL',v5_fresh_inference='BLOCKED_MISSING_MODEL_SCALER_FOLD',
      seconds=time.monotonic()-t0)
    dump(OUT/'results/REPAIR_VERDICT_V3.json',verdict)
    dump(OUT/'results/SOURCE_HASHES_V3.json',dict(code_sha=code_sha,source_qa_sha=source_qa,source_input_sha=sha(input_lock),
         scores_sha=sha(scores_path),trace_count=len(source_trace_hash),trace_aggregate_sha256=hashlib.sha256(json.dumps(source_trace_hash,sort_keys=True).encode()).hexdigest()))
    print(json.dumps({'status':status,'counts':{k:verdict[k] for k in ['n_mean_null_batches','n_mean_null_packet_comparisons','n_first_divergence','n_mutations','mutations_pass']},'duration_s':verdict['seconds']},indent=2),flush=True)
    if status!='PASS':raise RuntimeError('REPAIR_QA_FAILED '+str([x['check_id'] for x in record.rows if x['status']!='PASS'][:10]))

def parse_trace_filename(s):
    c,b,a,g=s.removesuffix('.npz').split('__')
    return c,b,a,g

if __name__=='__main__':main()
