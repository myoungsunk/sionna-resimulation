"""Shared recursive D13/D14 paired filter runner; original EKF remains unmodified.

F0 uses DiagnosticFilter's original EKF3/SE(2) prediction and direct-s
update.  Full UT uses separate *3-state* sigma-point measurement update,
whereas BIAS4_UT_PRED explicitly still has a linearized update.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np

from d10_d14_core import normalized_ukf_update, read_table, file_sha
from d6_d9_common import (B_OLD, RR,RS,P0_COV,DiagnosticFilter,wrap,
    range_h,EVAL_START,THRESHOLD_3D_95,THRESHOLD_1D_95,
    GATE_1D_99,GATE_2D_99,initial_state)

VARIANTS=('EKF3','UT_PRED','UT_BOTH','BIAS4','BIAS4_UT_PRED')
ARCHIVED_D5=('research/EKF3_INDEPENDENT_20261013/diagnostics/results/'
             'AUDITED_RUN_20261013_701b8d2/D5_MULTI_SEED_FULL_ROUTE_METRICS.csv')


def setup_tracker(start, sigma_heading_deg, kind, bias_prior_std_dps=.1):
    if kind not in VARIANTS:raise ValueError('Unknown filter '+kind)
    b=kind in ('BIAS4','BIAS4_UT_PRED')
    ut=kind in ('UT_PRED','UT_BOTH','BIAS4_UT_PRED')
    t=DiagnosticFilter(start,nonlinear=ut,bias_state=b,bias_std_dps=bias_prior_std_dps)
    if b:t.P[2,2]=math.radians(sigma_heading_deg)**2
    else:t.f.P[2,2]=math.radians(sigma_heading_deg)**2
    return t


def run_cell(case,t,truth,meas,z_s,r_physical,model,*,channel,seed,level,
             bias_mode,sigma_heading_deg,arm,variant,save_trace=False,
             bias_prior_std_dps=.1):
    """Run one arm; truth is accessed ONLY in per-step scoring after update.

    z_s, r_physical and model are strictly online RF/geometry observables.
    The same start and motion stream must be given for paired arms/methods.
    """
    if arm not in ('D0','A','B','C') or variant not in VARIANTS:
        raise ValueError('Unrecognised D13/D14 cell')
    n=len(t)
    if not (len(truth)==len(meas['ds_odom'])==len(z_s)==len(r_physical)==n):
        raise ValueError('Missing/unaligned motion or RF observations')
    if sigma_heading_deg<=0 or level not in (0,1,2):raise ValueError('Invalid design')
    start=initial_state(truth[0],seed)
    yaw_original=wrap(float(start[2]-truth[0,2]))
    if float(sigma_heading_deg)!=5.0:
        start[2]=wrap(float(truth[0,2]+yaw_original*sigma_heading_deg/5.))
    tracker=setup_tracker(start,sigma_heading_deg,variant,bias_prior_std_dps)
    stats={k:[] for k in ['head2','xy2','nees','headnees','pose95','heading95',
        'forward_error','forward_var','heading_prior_var','heading_post_var','nis',
        'accepted_heading_sq_change','xy_norm','heading_abs']}
    cnt={'applied':0,'rejected_NIS':0}
    samples=[]
    for k in range(n):
        if k:
            tracker.predict(float(meas['ds_odom'][k]),float(meas['dtheta_gyro'][k]),
                            float(meas['dt_s'][k]))
        Pprior=tracker.Ppose.copy()
        prior=tracker.pose.copy()
        status='DR_only';nis=None
        if arm!='D0':
            s=float(z_s[k]);r=float(r_physical[k]);
            if not math.isfinite(s) or not math.isfinite(r):
                raise RuntimeError('No oracle replacement for missing RF data')
            if variant=='UT_BOTH':
                def pred(x):
                    hs=float(model.value(x) if hasattr(model,'value') else model(x)[0])
                    rr=float(range_h(x,case['anchor'],case['robot_z_m'])[0])
                    return np.asarray([hs] if arm=='A' else [rr] if arm=='B' else [hs,rr])
                z=np.asarray([s] if arm=='A' else [r] if arm=='B' else [s,r])
                R=np.asarray([[RS]] if arm=='A' else [[RR]] if arm=='B'
                    else [[RS,0.],[0.,RR]])
                result,pc,status,nis=normalized_ukf_update(tracker.pose,tracker.Ppose,z,pred,R,
                    gate_threshold=GATE_2D_99 if arm=='C' else GATE_1D_99)
                tracker.f.x,tracker.f.P=result,pc
            else:
                status,nis=tracker.update(arm,s,r,model,case['anchor'],
                                          case['robot_z_m'],rs=RS,rr=RR,rsr=0.)
        if t[k]<EVAL_START:continue
        if status in cnt:cnt[status]+=1
        e=tracker.pose-np.asarray(truth[k],float)
        e[2]=wrap(float(e[2]))
        P=tracker.Ppose
        if np.linalg.eigvalsh((P+P.T)/2).min()<=0:
            raise RuntimeError('Non-PD posterior pose covariance')
        nees=float(e@np.linalg.solve(P,e))
        he=float(e[2]**2/P[2,2]);hprior=wrap(float(prior[2]-truth[k,2]))
        tangent=np.array([math.cos(truth[k,2]),math.sin(truth[k,2])])
        stats['head2'].append(float(math.degrees(e[2])**2))
        stats['xy2'].append(float(e[0]**2+e[1]**2))
        stats['xy_norm'].append(float(np.linalg.norm(e[:2])))
        stats['heading_abs'].append(abs(float(math.degrees(e[2]))))
        stats['nees'].append(nees);stats['headnees'].append(he)
        stats['pose95'].append(int(nees<=THRESHOLD_3D_95))
        stats['heading95'].append(int(he<=THRESHOLD_1D_95))
        stats['forward_error'].append(float(e[:2]@tangent))
        stats['forward_var'].append(float(tangent@P[:2,:2]@tangent))
        stats['heading_prior_var'].append(float(Pprior[2,2]))
        stats['heading_post_var'].append(float(P[2,2]))
        if nis is not None:stats['nis'].append(float(nis))
        if status=='applied':
            stats['accepted_heading_sq_change'].append(float(math.degrees(e[2])**2-math.degrees(hprior)**2))
        if save_trace:
            samples.append(dict(case=case['id'],route=case['route'],channel=channel,
                arm=arm,method=variant,seed=seed,level=level,
                bias_mode=bias_mode,sigma_heading_deg=sigma_heading_deg,
                sample_index=k,t_s=float(t[k]),
                error_x_m=float(e[0]),error_y_m=float(e[1]),
                error_heading_deg=float(math.degrees(e[2])),
                forward_error_m=float(e[:2]@tangent),
                predicted_forward_var_m2=float(tangent@P[:2,:2]@tangent),
                Ppsi_prior=float(Pprior[2,2]),Ppsi_posterior=float(P[2,2]),
                pose_NEES=nees,heading_NEES=he,status=status,nis=nis))
    def rmse(x):return float(np.sqrt(np.mean(np.asarray(x,float))))
    def mean(x):return float(np.mean(np.asarray(x,float))) if x else None
    def acf1(x):
        arr=np.asarray(x,float)
        return float(np.corrcoef(arr[:-1],arr[1:])[0,1]) if len(arr)>2 and np.std(arr)>1e-12 else None
    x=stats['forward_error']
    record=dict(case=case['id'],route=case['route'],channel=channel,
        condition='noise_pair' if bias_mode=='off' else 'paired_additive_gyro_bias',
        bias_mode=bias_mode,level=level,seed=seed,sigma_heading_deg=sigma_heading_deg,
        range_model='B_OLD',arm=arm,method=variant,
        n=len(stats['head2']),heading_rmse_deg=rmse(stats['head2']),
        xy_rmse_m=rmse(stats['xy2']),mean_pose_NEES=mean(stats['nees']),
        mean_heading_NEES=mean(stats['headnees']),pose95=mean(stats['pose95']),
        heading95=mean(stats['heading95']),
        empirical_forward_mean_m=mean(x),
        empirical_forward_rms_m=float(np.sqrt(np.mean(np.square(x)))),
        mean_predicted_forward_variance_m2=mean(stats['forward_var']),
        mean_heading_prior_var_rad2=mean(stats['heading_prior_var']),
        mean_heading_posterior_var_rad2=mean(stats['heading_post_var']),
        nis_pre_gate_lag1=acf1(stats['nis']),
        accepted_updates=cnt['applied'],rejected_updates=cnt['rejected_NIS'],
        mean_accepted_heading_sq_change_deg2=mean(stats['accepted_heading_sq_change']),
        position_error_p95_m=float(np.quantile(stats['xy_norm'],.95)),
        absolute_heading_error_p95_deg=float(np.quantile(stats['heading_abs'],.95)))
    return record,samples


def verify_frozen_d5(rows,reference,*,tolerance=1e-8):
    """Every REQUESTED baseline cell must match archived D5; no relaxed gate."""
    reference=Path(reference)
    archive=read_table(reference)
    keys=['case','channel','condition','level','seed','range_model','arm']
    by={tuple(r[c] for c in keys):r for r in archive}
    if len(by)!=len(archive):raise RuntimeError('Duplicate archived D5 cell')
    matched=0;maximum=0.
    for r in rows:
        if r['method']!='EKF3' or r['sigma_heading_deg']!=5 or r['bias_mode']!='off':
            continue
        key=tuple(str(r[c]) for c in keys)
        if key not in by:raise RuntimeError('Missing requested archived D5 cell '+str(key))
        old=by[key]
        for name in ['heading_rmse_deg','xy_rmse_m','mean_pose_NEES','mean_heading_NEES','pose95']:
            delta=abs(float(r[name])-float(old[name]))
            maximum=max(maximum,delta)
            if delta>tolerance:raise RuntimeError(f'D5 parity {key}: {name}: {delta} > {tolerance}')
        for name in ['n','accepted_updates','rejected_updates']:
            if int(r[name])!=int(old[name]):
                raise RuntimeError(f'D5 count parity FAIL {key}: {name}')
        matched+=1
    expected=sum(x['method']=='EKF3' and x['sigma_heading_deg']==5 and x['bias_mode']=='off' for x in rows)
    if matched!=expected or expected<1:raise RuntimeError('No complete original F0 parity cells')
    return {'status':'MATCHED_ALL_REQUESTED_BASELINE_CELLS','compared':matched,
       'expected':expected,'max_abs_difference':maximum,'tolerance':tolerance,
       'reference_sha256':file_sha(reference)}
