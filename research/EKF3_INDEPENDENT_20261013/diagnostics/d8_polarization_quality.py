"""D8: fit/evaluate train-route-only CIR-conditioned RF error variance.

USER-RUN ONLY.  Uses ground truth exclusively as *training targets* and
held-out scoring labels; the deployable predictors contain only whitelisted
online CIR features.  A leave-one-ROUTE-out split does not establish
independence across new RF scenes or validate time-independent residuals.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from d6_d9_common import (RR, RS, file_sha, finish, make_out, read_csv,
                          write_csv)
from d7_cir_multipath_audit import GEOMETRY_BASE, NUMERIC_FEATURES, ONLINE_KEYS

QUALITY_FEATURES = {
    'Q0_FIXED': (),
    'Q1_S_ONLY': ('s_fp',),
    'Q2_CIR_TIME_POWER': (
        's_fp','range_raw_m','log_fp_power','peak_fp_ratio',
        'peak_minus_fp_m','late_energy_fraction','tau_rms_ns'),
    'Q3_CIR_POL': (
        's_fp','range_raw_m','log_fp_power','peak_fp_ratio',
        'peak_minus_fp_m','late_energy_fraction','tau_rms_ns',
        'first_late_s_difference','rx_port_first_tap_delta_m',
        's_neighborhood_std','tap_step_delta_m','phase_valid',
        'rx1_fp_power','rx2_fp_power'),
    'Q4_COMPLEX_PHASE': (
        's_fp','range_raw_m','log_fp_power','peak_fp_ratio',
        'peak_minus_fp_m','late_energy_fraction','tau_rms_ns',
        'first_late_s_difference','rx_port_first_tap_delta_m',
        's_neighborhood_std','tap_step_delta_m','phase_valid',
        'rx1_fp_power','rx2_fp_power',
        'phase_fp_rad','phase_late_shift_rad'),
}
TARGETS = {'s':('error_s', RS, 1e-4, 4.),
           'r':('error_range_B_OLD_m', RR, 1e-5, 9.)}


def online_vector(row: dict, names: tuple[str,...]) -> list[float]:
    if not set(names) <= set(NUMERIC_FEATURES):
        raise RuntimeError('Oracle/off-contract field requested by predictor')
    v=[float(row[x]) for x in names]
    if not np.isfinite(v).all():
        raise RuntimeError('Nonfinite online CIR feature')
    return v


def fit_ridge(train: list[dict], target: str, variant: str, ridge: float) -> dict:
    """Fixed-ridge model of log(error^2 + floor), a second-moment proxy.

    Mean (bias) is not corrected; NLL is only a descriptive zero-mean
    pseudo-likelihood.  Never fit to heldout labels.
    """
    col, baseline, floor, ceiling=TARGETS[target]
    names=QUALITY_FEATURES[variant]
    if variant=='Q0_FIXED':
        return dict(variant=variant,feature_names=[],mu=[],sd=[],coef=[],
                    intercept=math.log(baseline),floor=floor,cap=ceiling,
                    baseline_variance=baseline,learned=False)
    X=np.asarray([online_vector(row,names) for row in train],float)
    errors=np.asarray([float(row[col]) for row in train],float)
    y=np.log(errors**2+floor)
    mu=np.mean(X,axis=0); sd=np.std(X,axis=0)
    sd=np.where(sd>1e-10,sd,1.)
    Z=(X-mu)/sd
    # Preregistered ridge penalty, regularise slopes but not intercept.
    center=float(np.mean(y))
    co=np.linalg.solve(Z.T@Z+ridge*np.eye(Z.shape[1]),Z.T@(y-center))
    return dict(variant=variant,feature_names=list(names),
                mu=mu.tolist(),sd=sd.tolist(),coef=co.tolist(),
                intercept=center,floor=floor,cap=ceiling,
                baseline_variance=baseline,learned=True)


def predict_variance(row: dict, params: dict) -> float:
    fields=tuple(params['feature_names'])
    if not fields:
        logvar=float(params['intercept'])
    else:
        v=np.asarray(online_vector(row,fields),float)
        mu=np.asarray(params['mu'],float)
        sd=np.asarray(params['sd'],float)
        w=np.asarray(params['coef'],float)
        if v.shape!=w.shape or np.any(sd<=0):
            raise RuntimeError('Invalid D8 fold feature contract')
        logvar=float(params['intercept']+((v-mu)/sd)@w)
    # Fixed numerical envelope precommitted before test predictions.
    return float(np.clip(math.exp(np.clip(logvar,-40.,15.)),
                         params['floor'],params['cap']))


def split_exclude_overlap(train: list[dict], holdout: list[dict],
                          tolerance_m: float) -> tuple[list[dict],int]:
    """Remove train XY near held-out XY (including +/- bin boundaries)."""
    if tolerance_m <= 0:
        raise ValueError('Positive XY exclusion radius required')
    hgrid: dict[tuple[int,int],list[tuple[float,float]]]={}
    for r in holdout:
        x,y=float(r['true_x_m']),float(r['true_y_m'])
        key=(int(math.floor(x/tolerance_m)),int(math.floor(y/tolerance_m)))
        hgrid.setdefault(key,[]).append((x,y))
    kept=[];dropped=0
    for r in train:
        x,y=float(r['true_x_m']),float(r['true_y_m'])
        i,j=int(math.floor(x/tolerance_m)),int(math.floor(y/tolerance_m))
        duplicate=False
        for a in range(i-1,i+2):
            for b in range(j-1,j+2):
                if any((x-xh)**2+(y-yh)**2<=tolerance_m**2
                       for xh,yh in hgrid.get((a,b),[])):
                    duplicate=True
                    break
            if duplicate:break
        if duplicate:dropped+=1
        else:kept.append(r)
    return kept,dropped


def load_paired(source: Path):
    man=source/'D7_MANIFEST.json'
    if not man.exists():
        raise FileNotFoundError('D7 execution manifest required')
    meta=json.loads(man.read_text(encoding='utf-8'))
    if meta.get('stage')!='D7' or meta.get('scientific_PASS') is not False:
        raise RuntimeError('Unexpected D7 manifest')
    on=source/'D7_ONLINE_CIR_FEATURES.csv'
    la=source/'D7_ORACLE_EVALUATION_LABELS.csv'
    for p in (on,la):
        if file_sha(p)!=meta['sha256'][p.name]:
            raise RuntimeError('D7 data hash mismatch: '+p.name)
    online=read_csv(on);labels=read_csv(la)
    if not online or set(online[0])!=set(ONLINE_KEYS):
        raise RuntimeError('D7 online schema mismatch: expected STRICT whitelist')
    def key(row):return row['case'],row['channel'],row['sample_index']
    # No left join with duplicated poses: sample index is timeline-unique.
    lm={key(l):l for l in labels}
    if len(lm)!=len(labels) or len(online)!=len(labels):
        raise RuntimeError('D7 duplicate labels/feature cardinality mismatch')
    combined=[]
    for o in online:
        k=key(o)
        if k not in lm:raise RuntimeError('Online feature has no matching offline label')
        label=lm[k]
        if label['route']!=o['route'] or label['pose_id']!=o['pose_id']:
            raise RuntimeError('D7 label alignment mismatch')
        # offline *training* view; all model features are still whitelisted.
        combined.append(o|{k:v for k,v in label.items() if k not in o})
    if len({key(x) for x in combined})!=len(combined):
        raise RuntimeError('Duplicate online sample index')
    return combined, {p.name:file_sha(p) for p in (on,la)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d7',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--ridge',type=float,default=10.)
    ap.add_argument('--xy-buffer-m',type=float,default=1e-4)
    ap.add_argument('--min-train-rows',type=int,default=100)
    args=ap.parse_args()
    if args.ridge<=0 or args.xy_buffer_m<=0 or args.min_train_rows<10:
        raise ValueError('Invalid train settings')
    records, hashes=load_paired(args.d7)
    records=[r for r in records if int(r['eval_after_30s'])==1]
    for r in records:
        if any(not math.isfinite(float(r[c])) for c in ['error_s','error_range_B_OLD_m']):
            raise RuntimeError('Nonfinite D8 training/scoring label')
    routes=sorted({r['route'] for r in records})
    if len(routes)<3:
        raise RuntimeError('D8 requires R2/R4/R5 route-held-out evaluation')
    models={};predictions=[];summary=[]
    for holdout in routes:
        for channel in ('los','full'):
            test=[r for r in records if r['route']==holdout and r['channel']==channel]
            base=[r for r in records if r['route']!=holdout and r['channel']==channel]
            train,dropped=split_exclude_overlap(base,test,args.xy_buffer_m)
            # Repeated timeline visits to the *same RF pose* should not
            # dominate learning as if new spatial RF draws occurred.
            unique={}
            for r in train:
                unique.setdefault((r['case'],r['pose_id']),r)
            train=list(unique.values())
            if len(train)<args.min_train_rows or not test:
                raise RuntimeError(f'Insufficient disjoint samples: {holdout}/{channel}')
            sub={}
            es=np.asarray([float(r['error_s']) for r in train])
            er=np.asarray([float(r['error_range_B_OLD_m']) for r in train])
            rho=float(np.corrcoef(es,er)[0,1]) if es.std()>0 and er.std()>0 else 0.
            rho=float(np.clip(rho,-.75,.75))
            for variant in QUALITY_FEATURES:
                vm={}
                for target in TARGETS:
                    fit=fit_ridge(train,target,variant,args.ridge)
                    fits=[predict_variance(r,fit) for r in test]
                    actual=np.asarray([float(r[TARGETS[target][0]]) for r in test])
                    fit_loss=.5*(np.log(fits)+actual**2/np.asarray(fits))
                    sumrow=dict(heldout_route=holdout,channel=channel,
                         variant=variant,target=target,
                         n_test=len(test),n_train_unique=len(train),
                         overlap_train_dropped=dropped,
                         oracle_training_only=1,
                         predicted_rms=float(math.sqrt(np.mean(fits))),
                         empirical_rms=float(math.sqrt(np.mean(actual**2))),
                         calibration_empirical_over_predict_var=float(
                             np.mean(actual**2)/np.mean(fits)),
                         zero_mean_gaussian_nll_proxy=float(np.mean(fit_loss)))
                    summary.append(sumrow)
                    for row,v in zip(test,fits):
                        predictions.append(dict(case=row['case'],channel=channel,
                            route=holdout,sample_index=row['sample_index'],
                            variant=variant,target=target,
                            predicted_var=v,observed_error=float(row[TARGETS[target][0]]),
                            scoring_label_oracle_only=1))
                    vm[target]=fit
                sub[variant]={'s':vm['s'],'r':vm['r'],
                              'rho_sr_train_centered':rho,
                              'rho_train_only_not_validated':True}
            models.setdefault(holdout,{})[channel]={
                'heldout_route':holdout,
                'train_routes':sorted({r['route'] for r in train}),
                'n_train_unique':len(train),
                'n_xy_overlap_removed':dropped,
                'models':sub}
    out=make_out(args.out)
    summary_path=out/'D8_CIR_QUALITY_VALIDATION.csv'
    pred_path=out/'D8_HELDOUT_PREDICTIONS.csv'
    fold_path=out/'D8_FOLD_MODELS.json'
    write_csv(summary_path,summary);write_csv(pred_path,predictions)
    contract=dict(schema='D8_ROUTE_HELDOUT_V1',
        d7_input_sha256=hashes,
        online_features= list(NUMERIC_FEATURES),
        training_target_labels=list(TARGETS),
        train_never_uses_heldout_truth=True,
        fixed_variance_envelope=True,
        same_scene_not_independent=True,
        scientific_PASS=False,
        ridge=args.ridge,xy_buffer_m=args.xy_buffer_m,folds=models)
    fold_path.write_text(json.dumps(contract,indent=2,ensure_ascii=False),encoding='utf-8')
    finish(out,'D8',vars(args)|{'out':str(out)},
           [summary_path,pred_path,fold_path],caveats=[
           'LORO within SAME frozen corridor; no independent RF scene',
           'Train excludes XY coinciding with heldout route and repeated case/pose',
           'Labels are usable only in offline training and scoring',
           'Log squared error regression predicts second moment, not unbiased noise variance',
           'Train-centered R_sr correlation is not independently calibrated',
           'No automatic Q3 selection based on heldout D8 results'])
    print('D8_EXPLORATORY_DONE',str(out))

if __name__=='__main__':
    main()
