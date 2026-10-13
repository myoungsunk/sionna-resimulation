"""D9: paired exploratory recursive EKF3/UT/Bias4/CIR-quality ablation.

USER-RUN ONLY.  F0 reproduces frozen D5; F1-F6 are separate NEW-only
filter variants.  D8 Q3 coefficients are route-held-out training artifacts,
not refit on D9's evaluation labels.  Results cannot establish scientific PASS.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import hashlib
import math
from pathlib import Path

import numpy as np

from d6_d9_common import (B_OLD, DiagnosticFilter, EVAL_START, RR, RS,
                          check_inputs, eval_covariance, file_sha, finish,
                          initial_state, make_out, original_lut, rf_case,
                          spectrum, write_csv, read_csv, corrected_ranges, wrap, P3_SHA256, P3_MODEL)
from d8_polarization_quality import predict_mean, predict_variance, RANGE_LABELS
from d7_cir_multipath_audit import ONLINE_KEYS
from ekf3 import archived_direct_s_model
from run_d5_regimes import timelines
from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments

METHODS = {
    'F0_ORIGINAL': (False,False,False),
    'F1_UT': (True,False,False),
    'F2_BIAS4': (False,True,False),
    'F3_CIR_R': (False,False,True),
    'F4_UT_CIR_R': (True,False,True),
    'F5_BIAS4_CIR_R': (False,True,True),
    'F6_UT_BIAS4_CIR_R': (True,True,True),
}
REFERENCE = ('research/EKF3_INDEPENDENT_20261013/diagnostics/results/'
             'AUDITED_RUN_20261013_701b8d2/D5_MULTI_SEED_FULL_ROUTE_METRICS.csv')


def source_evidence(d7: Path, d8: Path):
    for root,stage,files in [
        (d7,'D7',['D7_ONLINE_CIR_FEATURES.csv','D7_ORACLE_EVALUATION_LABELS.csv']),
        (d8,'D8',['D8_FOLD_MODELS.json','D8_CIR_QUALITY_VALIDATION.csv'])]:
        receipt=root/(stage+'_MANIFEST.json')
        if not receipt.exists():raise FileNotFoundError(receipt)
        j=json.loads(receipt.read_text(encoding='utf-8'))
        if j.get('stage')!=stage or j.get('scientific_PASS') is not False:
            raise RuntimeError('Wrong D7/D8 evidence metadata')
        for name in files:
            if file_sha(root/name)!=j['sha256'][name]:
                raise RuntimeError(f'{stage} evidence hash mismatch: {name}')
    folds=json.loads((d8/'D8_FOLD_MODELS.json').read_text(encoding='utf-8'))
    if folds['d7_input_sha256']['D7_ONLINE_CIR_FEATURES.csv']!=file_sha(
            d7/'D7_ONLINE_CIR_FEATURES.csv'):
        raise RuntimeError('D8 model trained on a different D7 feature source')
    if (folds.get('scientific_PASS') is not False or
        folds.get('schema') != 'D8_ROUTE_HELDOUT_CORRECTION_SPECIFIC_V2' or
        not folds.get('train_never_uses_heldout_truth') or
        folds.get('range_targets') != RANGE_LABELS or
        not folds.get('separate_centered_bias_and_variance')):
        raise RuntimeError('Untrusted D8 evaluation/training contract')
    rows=read_csv(d7/'D7_ONLINE_CIR_FEATURES.csv')
    if not rows or set(rows[0])!=set(ONLINE_KEYS):
        raise RuntimeError('D7 online CSV is not the strict non-oracle schema')
    mapping={}
    for row in rows:
        key=(row['case'],row['channel'],int(row['sample_index']))
        if key in mapping:raise RuntimeError('Duplicate D7 online sample index')
        mapping[key]=row
    return mapping,folds


def validate_e1_outer_fold(contract, fold, heldout_route):
    """Reject old per-row E1 labels even when exploratory quality is requested."""
    frozen = json.loads(P3_MODEL.read_text(encoding="utf-8"))
    params = frozen["loro_fold_params"][heldout_route]["E1"]
    expected_sha = hashlib.sha256(json.dumps(params, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if (fold.get("e1_outer_coefficients_sha256") != expected_sha or
        contract.get('e1_outer_fold_contract') !=
            'SINGLE_OUTER_ROUTE_EXCLUDED_FOLD_FOR_ALL_LABELS' or
        contract.get('e1_frozen_model_sha256') != P3_SHA256 or
        contract.get('e1_model_family_selection_nested') is not False or
        fold.get('e1_label_outer_excluded_route') != heldout_route):
        raise RuntimeError('E1 outer-fold provenance mismatch: regenerate D7/D8')


def covariance_for(row, fold, method, use_corr=False):
    """Return (Rs,Rr,Rsr,bias_s,bias_r) from correction-matched models.

    Q3 is a conditional *residual* model only after its fitted mean is
    subtracted from the incoming observation. Raw second moment is NOT R.
    """
    if use_corr:
        raise RuntimeError('Unvalidated R_sr cannot be passed as measurement covariance')
    if not METHODS[method][2]:
        return RS, RR, 0., 0., 0.
    if fold.get('range_target') != RANGE_LABELS[fold['range_model']]:
        raise RuntimeError('D8 correction/target mismatch')
    quality = fold['models']['Q3_CIR_POL']
    for target in ('s','r'):
        model = quality[target]
        if model['range_model']!=fold['range_model'] or model['target']!=target:
            raise RuntimeError('D9 refused range correction / covariance mismatch')
        expected = 'error_s' if target=='s' else RANGE_LABELS[fold['range_model']]
        if model['target_label']!=expected:
            raise RuntimeError('D9 refused quality model trained on different residual target')
    return (predict_variance(row,quality['s']),
            predict_variance(row,quality['r']), 0.,
            predict_mean(row,quality['s']), predict_mean(row,quality['r']))


def run_one(case, channel, condition, level, seed, t, truth, pids,
            meas, det, physical_range, model, fold, online, methods,
            bias_prior, bias_rw, use_rsr, save_trace):
    filters={(variant,arm):DiagnosticFilter(
        initial_state(truth[0],seed),nonlinear=METHODS[variant][0],
        bias_state=METHODS[variant][1],bias_std_dps=bias_prior,
        bias_rw_dps_sqrt_s=bias_rw)
        for variant in methods for arm in ('D0','A','B','C')}
    results={name:defaultdict(list) for name in filters}
    traces=[]
    for k in range(len(t)):
        row=online.get((case['id'],channel,k))
        if row is None or int(row['pose_id'])!=int(pids[k]):
            raise RuntimeError('D7 timeline alignment failure (missing/incorrect pose)')
        if not (math.isclose(float(row['t_s']),float(t[k]),abs_tol=1e-10) and
                math.isclose(float(row['s_fp']),float(det['s'][k]),abs_tol=1e-9) and
                math.isclose(float(row['range_raw_m']),float(det['range_raw_m'][k]),abs_tol=1e-9)):
            raise RuntimeError('D7 online features differ from D5 frozen observer')
        z_s=float(row['s_fp'])
        z_r=float(physical_range[k])
        for key,f in filters.items():
            variant,arm=key
            if k>0:
                f.predict(float(meas['ds_odom'][k]),
                          float(meas['dtheta_gyro'][k]),float(meas['dt_s'][k]))
            prior=f.pose.copy()
            Pprior=f.Ppose.copy()
            rs,rr,rsr,mean_s,mean_r=covariance_for(row,fold,variant,use_rsr)
            # Bias compensation matches the CENTERED-residual covariance.
            # F0/F1/F2 keep unmodified observations and R0 exactly.
            status,nis=f.update(arm,z_s-mean_s,z_r-mean_r,model,
                                 case['anchor'],case['robot_z_m'],rs=rs,rr=rr,rsr=rsr)
            if t[k]<EVAL_START:
                continue
            e=f.pose-truth[k]
            e[2]=wrap(e[2])
            n3,nh,coverage=eval_covariance(e,f.Ppose)
            d=results[key]
            d['xy2'].append(float(e[0]**2+e[1]**2))
            d['xy_abs'].append(float(np.linalg.norm(e[:2])))
            d['yaw_abs'].append(float(abs(math.degrees(e[2]))))
            d['nis'].append(float(nis) if nis is not None and math.isfinite(float(nis)) else None)
            d['prior_sig_h'].append(math.degrees(math.sqrt(Pprior[2,2])))
            d['yaw2'].append(math.degrees(e[2])**2)
            d['nees'].append(n3);d['heading_nees'].append(nh)
            d['cover'].append(int(coverage))
            d['yaw95'].append(int(nh<=3.841458820694124))
            d['sig_h'].append(math.degrees(math.sqrt(f.Ppose[2,2])))
            d['status'].append(status)
            if status=='applied':
                e_prior=wrap(prior[2]-truth[k,2])
                d['improved'].append(int(abs(e[2])<abs(e_prior)))
                d['delta_sq_deg2'].append(float(math.degrees(e[2])**2-
                                                    math.degrees(e_prior)**2))
            if save_trace:
                traces.append(dict(case=case['id'],channel=channel,
                    condition=condition,level=level,seed=seed,
                    model=variant,arm=arm,sample_index=k,t_s=float(t[k]),
                    x=float(f.pose[0]),y=float(f.pose[1]),
                    yaw_rad=float(f.pose[2]),
                    Ppsi_prior=float(Pprior[2,2]),
                    Ppsi_posterior=float(f.Ppose[2,2]),
                    R_mean_s_subtracted=mean_s,R_mean_r_subtracted_m=mean_r,
                    Pxx=float(f.Ppose[0,0]),
                    Pyy=float(f.Ppose[1,1]),Ppsi=float(f.Ppose[2,2]),
                    Pxy=float(f.Ppose[0,1]),Pxpsi=float(f.Ppose[0,2]),
                    Pypsi=float(f.Ppose[1,2]),
                    error_yaw_deg=math.degrees(e[2]),
                    error_position_m=float(np.linalg.norm(e[:2])),pose_nees=n3,
                    NIS_pre_gate=nis,gate=status,
                    R_s=rs,R_r=rr,R_sr=rsr,
                    bias_est_rad_s=float(f.x[3]) if f.bias_state else None))
    grouped=[]
    for (variant,arm),d in results.items():
        good_nis=np.asarray([v for v in d['nis'] if v is not None],float)
        nis_acf=(float(np.corrcoef(good_nis[:-1],good_nis[1:])[0,1])
                 if len(good_nis)>2 and np.std(good_nis)>1e-14 and
                    np.std(good_nis[1:])>1e-14 else None)
        grouped.append(dict(case=case['id'],channel=channel,condition=condition,
            level=level,seed=seed,range_model='DYNAMIC_BY_CALLER',
            method=variant,arm=arm,n=len(d['xy2']),
            heading_rmse_deg=math.sqrt(float(np.mean(d['yaw2']))),
            xy_rmse_m=math.sqrt(float(np.mean(d['xy2']))),
            mean_pose_NEES=float(np.mean(d['nees'])),
            mean_heading_NEES=float(np.mean(d['heading_nees'])),
            pose95=float(np.mean(d['cover'])),
            heading95=float(np.mean(d['yaw95'])),
            mean_pred_heading_std_deg=float(np.mean(d['prior_sig_h'])),
            mean_post_heading_std_deg=float(np.mean(d['sig_h'])),
            position_error_p95_m=float(np.percentile(d['xy_abs'],95)),
            absolute_heading_error_p95_deg=float(np.percentile(d['yaw_abs'],95)),
            nis_pre_gate_lag1=nis_acf,
            accepted_updates=d['status'].count('applied'),
            rejected_updates=d['status'].count('rejected_NIS'),
            accepted_heading_improvement_fraction=(float(np.mean(d['improved']))
                          if d['improved'] else None),
            mean_accepted_heading_sq_change_deg2=(float(np.mean(d['delta_sq_deg2']))
                          if d['delta_sq_deg2'] else None)))
    return grouped,traces


def enforce_d5_baseline(new_rows, reference, *, range_model: str):
    """Fail closed: every requested F0 cell must match original archived D5.

    No 'missing archived cell => skip' behavior and no duplicate baseline keys.
    """
    archived = read_csv(reference)
    cols = ('case','channel','condition','level','seed','range_model','arm')
    lookup = {}
    for src in archived:
        key=(src['case'],src['channel'],src['condition'],int(src['level']),
             int(src['seed']),src['range_model'],src['arm'])
        if key in lookup:
            raise RuntimeError('Duplicate frozen D5 parity key: '+str(key))
        lookup[key]=src
    f0=[r for r in new_rows if r['method']=='F0_ORIGINAL']
    if not f0:
        raise RuntimeError('F0 selected but missing from generated rows')
    compared=0;max_error=0.; seen=set()
    for r in f0:
        key=(r['case'],r['channel'],r['condition'],int(r['level']),int(r['seed']),
             range_model if r['channel']=='full' else 'B_OLD',r['arm'])
        if key in seen:
            raise RuntimeError('Duplicate new F0 D9 parity cell: '+str(key))
        seen.add(key)
        baseline=lookup.get(key)
        if baseline is None:
            raise RuntimeError('MISSING frozen D5 parity cell: '+str(key))
        compared+=1
        for field in ('heading_rmse_deg','xy_rmse_m','mean_pose_NEES',
                      'mean_heading_NEES','pose95'):
            difference=abs(float(baseline[field])-float(r[field]))
            max_error=max(max_error,difference)
            if not math.isfinite(difference) or difference>1e-8:
                raise RuntimeError(f'D5 F0 parity FAIL: {key} {field} delta {difference}')
        for field in ('n','accepted_updates','rejected_updates'):
            if int(baseline[field])!=int(r[field]):
                raise RuntimeError(f'D5 F0 parity count FAIL: {key} {field}')
    return {'status':'ALL_REQUESTED_F0_CELLS_MATCHED',
            'compared':compared,'expected':len(f0),
            'archived_reference_rows':len(archived),
            'max_metric_abs_difference':max_error}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d7',type=Path,required=True)
    ap.add_argument('--d8',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--seeds',type=int,nargs='+',default=[0,1,2])
    ap.add_argument('--levels',type=int,nargs='+',default=[0,1,2])
    ap.add_argument('--conditions',nargs='+',default=['noise_pair','gyro_bias','gyro_sf','all'])
    ap.add_argument('--channels',nargs='+',choices=['los','full'],default=['los','full'])
    ap.add_argument('--cases',nargs='*',default=[])
    ap.add_argument('--methods',nargs='+',choices=list(METHODS),default=list(METHODS))
    ap.add_argument('--range-model',choices=['B_OLD','E1_FULL_LORO'],default='B_OLD')
    ap.add_argument('--bias-prior-std-dps',type=float,default=.1)
    ap.add_argument('--bias-rw-dps-sqrt-s',type=float,default=0.)
    ap.add_argument('--use-trained-rsr',action='store_true',
                     help='Unsupported: fail-closed until independent residual covariance calibration')
    ap.add_argument('--exploratory-unvalidated-quality',action='store_true',
                     help='Explicitly allow Q3 arms when D8 heldout gate FAILS; not a validated result')
    ap.add_argument('--save-trace',action='store_true')
    ap.add_argument('--d5-reference',type=Path,default=None)
    ap.add_argument('--skip-d5-parity',action='store_true',
                     help='Non-comparative new-seed use only; result explicitly marks parity NOT_RUN')
    args=ap.parse_args()
    from qclean_uwb.drivesim.sensor_v2 import CONDITIONS
    if (args.bias_prior_std_dps<=0 or args.bias_rw_dps_sqrt_s<0 or
        any(x not in (0,1,2) for x in args.levels) or
        any(x not in CONDITIONS for x in args.conditions) or
        len(set(args.seeds))!=len(args.seeds)):
        raise ValueError('Bad runtime configuration')
    if args.use_trained_rsr:
        raise RuntimeError('R_sr train correlation is NOT calibrated; joint RF off-diagonal prohibited')
    if len(set(args.methods))!=len(args.methods):
        raise ValueError('Duplicate D9 method')
    p0=check_inputs()
    online,folds=source_evidence(args.d7,args.d8)
    fr=spectrum(p0)
    lut=original_lut(p0)
    roots=timelines(p0)
    bycase={c['id']:c for c in p0['cases']}
    cases=args.cases or list(bycase)
    if len(set(cases))!=len(cases) or any(c not in bycase for c in cases):
        raise ValueError('Invalid cases')
    result=[];trace=[]
    for cid in cases:
        case=bycase[cid]
        t,truth,pids=roots[case['route']]
        s_func=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),
                  tag_height_m=float(case['robot_z_m']),mount_deg=float(case['mount_deg']))
        for ch in args.channels:
            det=rf_case(p0,case,ch,fr,pids)
            if case['route'] not in folds['folds'] or ch not in folds['folds'][case['route']]:
                raise RuntimeError('D8 held-out model absent for '+case['route']+'/'+ch)
            fold_root=folds['folds'][case['route']][ch]
            expected_range=args.range_model if ch=='full' else 'B_OLD'
            if expected_range not in fold_root['range_models']:
                raise RuntimeError('No D8 model trained for selected correction '+expected_range)
            fold=fold_root['range_models'][expected_range]
            if expected_range=='E1_FULL_LORO':
                validate_e1_outer_fold(folds, fold, case['route'])
            if fold['range_target']!=RANGE_LABELS[expected_range]:
                raise RuntimeError('D8 range residual target mismatch')
            if (any(METHODS[m][2] for m in args.methods) and
                fold['q3_heldout_gate']['status']!='EXPLORATORY_GATE_PASS' and
                not args.exploratory_unvalidated_quality):
                raise RuntimeError('D8 Q3 heldout gate failed; explicitly choose --exploratory-unvalidated-quality for exploratory run')
            if (case['route'] in fold_root['train_routes'] or
                fold_root['heldout_route']!=case['route']):
                raise RuntimeError('D8 training/evaluation route leakage')
            if ch=='full' and args.range_model=='E1_FULL_LORO':
                p3=json.loads(__import__('d6_d9_common').P3_MODEL.read_text(encoding='utf-8'))
                corrected=corrected_ranges(det,p3['loro_fold_params'][case['route']],
                                      allow_e1_on_los=False,channel='full')
                physical=corrected['E1_FULL_LORO']
            else:
                physical=det['range_raw_m']-B_OLD
            for condition in args.conditions:
                for level in args.levels:
                    for seed in args.seeds:
                        ds,da=motion_increments(t,truth,convention='legacy-euler')
                        cfg=SensorV2Config(level=level,condition=condition,
                              common_scale=0.,bias_rw_rad_s_sqrt_s=0.,slip_mode='time')
                        measure,_eval_only=generate(t,ds,da,cfg,seed)
                        rows,tr=run_one(case,ch,condition,level,seed,t,truth,pids,
                             measure,det,physical,s_func,fold,online,args.methods,
                             args.bias_prior_std_dps,args.bias_rw_dps_sqrt_s,
                             args.use_trained_rsr,args.save_trace)
                        for row in rows:
                            row['range_model']=args.range_model if ch=='full' else 'B_OLD'
                        result.extend(rows);trace.extend(tr)
    check={'status':'NOT_RUN_USER_DISABLED','compared':0}
    if not args.skip_d5_parity and 'F0_ORIGINAL' in args.methods:
        ref=args.d5_reference or (__import__('d6_d9_common').REPO/REFERENCE)
        if not ref.is_file():
            raise FileNotFoundError('D5 baseline parity reference missing: '+str(ref))
        check=enforce_d5_baseline(result,ref,range_model=args.range_model)
        check['reference_sha256']=file_sha(ref)
    out=make_out(args.out)
    path=out/'D9_RECURSIVE_FUSION_METRICS.csv'
    write_csv(path,result)
    files=[path]
    if trace:
        tpath=out/'D9_SAMPLE_TRACE.csv'
        write_csv(tpath,trace);files.append(tpath)
    parity=out/'D9_F0_D5_PARITY.json'
    from d6_d9_common import atomic_json
    atomic_json(parity,check)
    files.append(parity)
    finish(out,'D9',vars(args)|{'d5_baseline_parity':check},files,
           caveats=['F0 matches frozen D5 only on matched archived cells',
                    'F1 is 3-state UT prediction; F2/F5 use estimated gyro-bias state',
                     'F3-F6 subtract train-only conditional bias, and use centered Q3 error proxy',
                     'D8 gate is scene-internal exploratory, not independent-scene confirmation',
                     'If exploratory-unvalidated-quality is requested, heldout gate may have failed',
                    'Time-correlated Multipath and observation mean biases remain',
                    'E1 family was selected on the frozen scene; no nested family-selection claim; D9 scores all requested positions',
                    'Single frozen RF scene, no independent confirmation seeds or scientific PASS'])
    print('D9_EXPLORATORY_DONE',str(out))

if __name__=='__main__':
    main()
