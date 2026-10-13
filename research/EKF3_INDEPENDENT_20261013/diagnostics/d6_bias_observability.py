"""D6-0/D6-2: route-based bias/nonlinearity ablation (USER-RUN ONLY).

Identical wheel/gyro white-noise streams are used in the paired no-bias
and bias-injected cases.  Oracle bias subtraction and model-consistent RF
are explicit COUNTERFACTUAL controls; neither is deployable.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from d6_d9_common import (B_OLD, DiagnosticFilter, EVAL_START, RR, RS,
                          check_inputs, case_motion, eval_covariance, finish,
                          initial_state, make_out, original_lut, range_h, rf_case,
                          sensor_rng, spectrum, write_csv, wrap, arc,
                          sinc_with_derivative, s_model, THRESHOLD_2D_95)
from ekf3 import archived_direct_s_model
from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments

SCENARIOS = {
    'M0_NO_BIAS_D0': ('none', 'D0', 'none'),
    'M1_NO_BIAS_LOS': ('none', 'C', 'los'),
    'M2_BIAS_D0': ('bias', 'D0', 'none'),
    'M3_BIAS_LOS': ('bias', 'C', 'los'),
    'M4_BIAS_FULL': ('bias', 'C', 'full'),
    'M5_BIAS_ORACLE_RF': ('bias', 'C', 'oracle'),
}


def generate_paired(t, truth, level, seed):
    ds, da = motion_increments(t, truth, convention='legacy-euler')
    # Actual sensor experiment uses one paired base noise stream.  Bias-only
    # sensor is used to obtain a synthetic ADDITIVE fixed bias, not a new draw.
    neutral_cfg = SensorV2Config(level=level, condition='noise_pair',
                                 common_scale=0., bias_rw_rad_s_sqrt_s=0.)
    bias_cfg = SensorV2Config(level=level, condition='gyro_bias',
                              common_scale=0., bias_rw_rad_s_sqrt_s=0.)
    base, _ = generate(t, ds, da, neutral_cfg, seed)
    bias_only, ev = generate(t, ds, da, bias_cfg, seed)
    # For the archived constant-bias generator, the bias on step k is b[k-1].
    injected = np.array(bias_only['dtheta_gyro']-da, float)
    if not np.allclose(injected[1:], ev['true_bias_rad_s'][:-1]*np.diff(t), atol=1e-12):
        raise RuntimeError('Gyro bias injection parity failed')
    biased = {key: np.asarray(v).copy() if isinstance(v,np.ndarray) else v
              for key,v in base.items()}
    biased['dtheta_gyro'] += injected
    return base, biased, injected


def model_vs_legacy_truth(t, truth):
    ds, da = motion_increments(t, truth, convention='legacy-euler')
    traj = truth[0].copy()
    err = []
    for k in range(1,len(t)):
        traj = arc(traj, ds[k], da[k])
        err.append(float(np.linalg.norm(traj[:2]-truth[k,:2])))
    return max(err) if err else 0.


def local_observability(t, truth, case, model):
    """Whitened trajectory Jacobian rank, an optimistic independent-R metric.

    It assumes the *true* path for offline linearization only and R0 iid; it
    does NOT establish gyro-bias identifiability in the real multipath scene.
    """
    n = 4
    Phi = np.eye(n)
    rows = []
    ds, da = motion_increments(t, truth, convention='legacy-euler')
    for k in range(len(t)):
        if k > 0:
            d, a, dt = ds[k], da[k], t[k]-t[k-1]
            sc, sc_der = sinc_with_derivative(a/2)
            theta = truth[k-1,2]+a/2
            v = np.array([math.cos(theta),math.sin(theta)])
            vp = np.array([-v[1],v[0]])
            F = np.eye(n)
            F[:2,2] = d*sc*vp
            F[:2,3] = -dt*d/2*(sc_der*v+sc*vp)
            F[2,3] = -dt
            Phi = F@Phi
        if t[k] < EVAL_START:
            continue
        _, js = model(truth[k])
        _, jr = range_h(truth[k], case['anchor'], case['robot_z_m'])
        rows.append((np.r_[js,0.]@Phi)/math.sqrt(RS))
        rows.append((np.r_[jr,0.]@Phi)/math.sqrt(RR))
    O = np.asarray(rows)
    # Scale columns by declared prior state/bias scales (not by result).
    O = O @ np.diag([.1,.1,math.radians(5.),math.radians(.1)])
    s = np.linalg.svd(O, compute_uv=False)
    rank = int(np.sum(s>max(s)*1e-8)) if len(s) else 0
    return {'obs_rank_4state':rank, 'obs_smallest_singular':float(s[-1]),
            'obs_condition_ratio':float(s[-1]/max(s[0],1e-300)),
            'obs_assumption':'oracle_true_state_jacobian_iid_R0_upper_bound'}


def run_case(case, t, truth, meas0, measb, bias_inc, obs_los, obs_full,
             model, level, seed, bias_std_dps, save_trace=False):
    rows=[];steps=[]
    start=initial_state(truth[0], seed)
    for scen, (bias_mode, arm, rf) in SCENARIOS.items():
        meas = measb if bias_mode=='bias' else meas0
        for variant in ('EKF3','UT3','BIAS4','BIAS4_UT','ORACLE_GYRO_DEBIASED','WHEEL_YAW3'):
            if variant=='ORACLE_GYRO_DEBIASED' and bias_mode!='bias':
                continue
            if variant=='WHEEL_YAW3' and rf=='oracle':
                continue
            tracker = DiagnosticFilter(start, nonlinear=variant in ('UT3','BIAS4_UT'),
                                      bias_state=variant in ('BIAS4','BIAS4_UT'),
                                      bias_std_dps=bias_std_dps)
            sum_pos2=[];sum_heading2=[];sum_nees=[];sum_cov=[]
            sum_prior_sigpsi=[];sum_post_sigpsi=[]
            sum_prior_forward_var=[];sum_post_forward_var=[]
            sum_xy95=[];sum_xyabs=[];sum_headabs=[]
            sum_forward_err=[]
            for k in range(len(t)):
                if k:
                    gyro = float(meas['dtheta_gyro'][k])
                    if variant=='ORACLE_GYRO_DEBIASED':
                        gyro -= float(bias_inc[k])
                    if variant=='WHEEL_YAW3':
                        gyro = float(meas['dtheta_odom'][k])
                    tracker.predict(float(meas['ds_odom'][k]), gyro,
                                    float(meas['dt_s'][k]))
                prior_pose=tracker.pose.copy()
                Pprior=tracker.Ppose.copy()
                if rf != 'none':
                    if rf=='oracle':
                        s_value,_ = model(truth[k])
                        r_value,_ = range_h(truth[k], case['anchor'], case['robot_z_m'])
                    else:
                        ob = obs_los if rf=='los' else obs_full
                        s_value = ob['s'][k]
                        r_value = ob['range_raw_m'][k]-B_OLD
                    tracker.update(arm, float(s_value), float(r_value), model,
                                   case['anchor'], case['robot_z_m'])
                if t[k] < EVAL_START:
                    continue
                e = tracker.pose-truth[k]
                e[2] = wrap(e[2])
                P = tracker.Ppose
                n3, _, cover = eval_covariance(e, P)
                tangent = np.array([math.cos(truth[k,2]), math.sin(truth[k,2])])
                sum_pos2.append(float(e[:2]@e[:2]))
                sum_heading2.append(float(math.degrees(e[2])**2))
                sum_nees.append(n3)
                sum_cov.append(float(cover))
                sum_prior_sigpsi.append(math.degrees(math.sqrt(Pprior[2,2])))
                sum_post_sigpsi.append(math.degrees(math.sqrt(P[2,2])))
                sum_prior_forward_var.append(float(tangent@Pprior[:2,:2]@tangent))
                sum_post_forward_var.append(float(tangent@P[:2,:2]@tangent))
                sum_forward_err.append(float(e[:2]@tangent))
                sum_xyabs.append(float(np.linalg.norm(e[:2])))
                sum_headabs.append(float(abs(math.degrees(e[2]))))
                nxy=float(e[:2]@np.linalg.solve(P[:2,:2],e[:2]))
                sum_xy95.append(int(nxy<=THRESHOLD_2D_95))
                if save_trace:
                    steps.append(dict(case=case['id'],scenario=scen,variant=variant,
                        seed=seed,level=level,t_s=float(t[k]),
                        xprior=float(prior_pose[0]),yprior=float(prior_pose[1]),
                        psiprior=float(prior_pose[2]),
                        Ppsi_prior_rad2=float(Pprior[2,2]),
                        Ppsi_post_rad2=float(P[2,2]),
                        Pforward_prior_m2=float(tangent@Pprior[:2,:2]@tangent),
                        Pforward_post_m2=float(tangent@P[:2,:2]@tangent),
                        ex_m=float(e[0]),ey_m=float(e[1]),e_psi_rad=float(e[2]),
                        oracle_control=int(rf=='oracle' or variant=='ORACLE_GYRO_DEBIASED')))
            rows.append(dict(case=case['id'],route=case['route'],seed=seed,
                level=level,scenario=scen,variant=variant,n=len(sum_pos2),
                heading_rmse_deg=math.sqrt(np.mean(sum_heading2)),
                xy_rmse_m=math.sqrt(np.mean(sum_pos2)),
                mean_pose_nees=float(np.mean(sum_nees)),
                pose95=float(np.mean(sum_cov)),
                mean_predict_heading_std_deg=float(np.mean(sum_prior_sigpsi)),
                mean_posterior_heading_std_deg=float(np.mean(sum_post_sigpsi)),
                pose_xy95=float(np.mean(sum_xy95)),
                position_error_p95_m=float(np.percentile(sum_xyabs,95)),
                absolute_heading_error_p95_deg=float(np.percentile(sum_headabs,95)),
                mean_forward_bias_m=float(np.mean(sum_forward_err)),
                empirical_forward_rms_m=float(np.sqrt(np.mean(np.square(sum_forward_err)))),
                mean_predict_forward_std_m=float(np.sqrt(np.mean(sum_prior_forward_var))),
                mean_posterior_forward_std_m=float(np.sqrt(np.mean(sum_post_forward_var))),
                yaw_source='wheel_delta' if variant=='WHEEL_YAW3' else 'gyro_increment',
                online_oracle_input=(rf=='oracle' or variant=='ORACLE_GYRO_DEBIASED'),
                slip_robustness_evaluated=False,
                interpretation='EXPLORATORY_SAME_SCENE'))
    return rows,steps


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--seeds',type=int,nargs='+',default=[0,1,2])
    ap.add_argument('--levels',type=int,nargs='+',default=[0,1,2])
    ap.add_argument('--cases',nargs='*',default=[])
    ap.add_argument('--bias-prior-std-dps',type=float,default=.1)
    ap.add_argument('--save-step-trace',action='store_true',
                    help='Save full per-step prior/post prediction covariance CSV')
    args=ap.parse_args()
    if args.bias_prior_std_dps <= 0 or any(x not in (0,1,2) for x in args.levels):
        raise ValueError('Invalid settings')
    p0=check_inputs()
    fr=spectrum(p0)
    lut=original_lut(p0)
    ts={c['id']:c for c in p0['cases']}
    names=args.cases or list(ts)
    if len(names)!=len(set(names)) or any(n not in ts for n in names):
        raise ValueError('Unknown/duplicate cases')
    all_rows=[]; obs_rows=[]; trace_rows=[];kinematic=[]
    from run_d5_regimes import timelines
    trajectories=timelines(p0)
    for name in names:
        case=ts[name]
        t, truth, pids=trajectories[case['route']]
        lo=rf_case(p0,case,'los',fr,pids)
        fu=rf_case(p0,case,'full',fr,pids)
        model=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),
              tag_height_m=case['robot_z_m'],mount_deg=case['mount_deg'])
        obs_rows.append(dict(case=name,route=case['route'],
                             max_nominal_se2_vs_archived_legacy_m=model_vs_legacy_truth(t,truth),
                             **local_observability(t,truth,case,model)))
        ds_geom,da_geom=motion_increments(t,truth,convention='legacy-euler')
        path_se2=truth[0].copy()
        for k in range(len(t)):
            if k:path_se2=arc(path_se2,ds_geom[k],da_geom[k])
            kinematic.append(dict(case=name,route=case['route'],t_s=float(t[k]),
                x_legacy_m=float(truth[k,0]),y_legacy_m=float(truth[k,1]),
                x_integrated_se2_m=float(path_se2[0]),
                y_integrated_se2_m=float(path_se2[1]),
                kinematic_displacement_error_m=float(np.linalg.norm(path_se2[:2]-truth[k,:2])),
                rf_observation_kinematic_shift_not_permitted=True))
        for level in args.levels:
            for seed in args.seeds:
                meas0,measb,incs=generate_paired(t,truth,level,seed)
                aggregate,steps=run_case(case,t,truth,meas0,measb,incs,lo,fu,
                                   model,level,seed,args.bias_prior_std_dps,
                                   save_trace=args.save_step_trace)
                all_rows.extend(aggregate);trace_rows.extend(steps)
    out=make_out(args.out)
    f1=out/'D6_BIAS_ROUTE_ABLATION.csv'
    f2=out/'D6_BIAS_OBSERVABILITY.csv'
    write_csv(f1,all_rows);write_csv(f2,obs_rows)
    kinematic_path=out/'D6_KINEMATIC_CONTRACT.csv'
    write_csv(kinematic_path,kinematic)
    files=[f1,f2,kinematic_path]
    if args.save_step_trace:
        trace_path=out/'D6_PRIOR_POSTERIOR_STEP_TRACE.csv'
        write_csv(trace_path,trace_rows);files.append(trace_path)
    finish(out,'D6_BIAS',vars(args),files,caveats=[
        'Bias injected additively into identical base noise streams; generator source unmodified',
        'Oracle RF/bias subtraction are counterfactual offline upper controls',
        '4-state observability ranks assume oracle linearization and iid R0',
        'BIAS4 without an independent yaw constraint does not guarantee bias observability',
        'WHEEL_YAW3 REPLACES gyro increment rather than combining two correlated sensors; no slip robustness claim',
        'SE2-vs-legacy truth diagnostic is only model mismatch; frozen RF may not be shifted',
        'prior and posterior pose covariance recorded separately',
        'Same frozen RF scene; no scientific PASS'])
    print('D6_BIAS_EXPLORATORY_DONE',str(out))

if __name__=='__main__':
    main()
