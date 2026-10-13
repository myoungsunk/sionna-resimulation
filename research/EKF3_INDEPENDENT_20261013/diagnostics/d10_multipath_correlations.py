"""D10: frozen D7 CIR descriptors versus range/s/heading errors.

User-run diagnostic, NO new RF simulation. Labels and truth appear ONLY here,
never in D11 online features or D13/D14 estimator inputs.
"""
from __future__ import annotations
import argparse, csv, gzip, math
from pathlib import Path
import numpy as np
from d10_d14_core import (validate_stage, read_table, correlation, write_rows,
    stage_finish, new_output, file_sha)

TARGETS={
  'signed_range_MP_m':'e_mp_m',
  'abs_range_MP_m':'e_mp_m',
  'abs_range_B_OLD_m':'error_range_B_OLD_m',
  'abs_range_E1_m':'error_range_E1_FULL_LORO_m',
  'signed_s_MP':'full_minus_los_s',
  'abs_s_MP':'full_minus_los_s',
  'abs_s_model':'error_s',
  'abs_s_tap':'tap_selection_effect_s',
  'abs_s_same_tap':'same_tap_channel_effect_s',
}
FEATURES=['s_fp','range_raw_m','peak_fp_ratio','peak_minus_fp_m',
  'late_energy_fraction','tau_rms_ns','first_late_s_difference',
  'rx_port_first_tap_delta_m','s_neighborhood_std','tap_step_delta_m']


def paired_records(d7):
    validate_stage(d7,'D7',['D7_ONLINE_CIR_FEATURES.csv','D7_ORACLE_EVALUATION_LABELS.csv'])
    o=read_table(Path(d7)/'D7_ONLINE_CIR_FEATURES.csv')
    y=read_table(Path(d7)/'D7_ORACLE_EVALUATION_LABELS.csv')
    def key(r):return (r['case'],r['channel'],r['sample_index'],r['pose_id'],r['t_s'])
    lookup={key(r):r for r in y}
    if len(lookup)!=len(y) or len(o)!=len(y):raise RuntimeError('D7 non-bijective alignment')
    rows=[]
    for r in o:
        k=key(r)
        if k not in lookup:raise RuntimeError('D7 orphaned online feature')
        if r['channel']=='full' and int(r['eval_after_30s']):
            rows.append(r|lookup[k])
    if not rows:raise RuntimeError('No paired Full RF observations')
    return rows


def vals(rows,field):return np.asarray([float(r[field]) for r in rows],float)


def stats(rows):
    if not rows:raise ValueError('No rows')
    x=vals(rows,'e_mp_m');y=vals(rows,'full_minus_los_s')
    base={
     'n':len(rows),
     'signed_pearson':correlation(x,y),
     'signed_spearman':correlation(x,y,method='spearman'),
     'abs_pearson':correlation(abs(x),abs(y)),
     'abs_spearman':correlation(abs(x),abs(y),method='spearman'),
     'squared_pearson':correlation(x*x,y*y),
     'signed_covariance':float(np.cov(x,y,ddof=1)[0,1]) if len(rows)>1 else None,
     'rms_range_mp_m':float(np.sqrt(np.mean(x*x))),
     'rms_s_mp':float(np.sqrt(np.mean(y*y))),
     'mean_range_mp_m':float(np.mean(x)),
     'mean_s_mp':float(np.mean(y)),
    }
    # Descriptive within-case 90th-percentile tails; NOT a prospective gate.
    qx=np.quantile(abs(x),.9);qy=np.quantile(abs(y),.9)
    base['both_top10_fraction']=float(np.mean((abs(x)>=qx)&(abs(y)>=qy)))
    return base


def summarize(rows):
    groups={'ALL_SAME_SCENE':rows}
    for r in rows:
        groups.setdefault(r['case'],[]).append(r)
        d=float(r['true_range_m'])
        b='<5m' if d<5 else '5-10m' if d<10 else '>=10m'
        groups.setdefault('DISTANCE_'+b,[]).append(r)
        groups.setdefault('ROUTE_'+r['route'],[]).append(r)
    summary=[{'group':name,**stats(a)} for name,a in groups.items()]
    correlations=[]
    for name,a in groups.items():
        for target,field in TARGETS.items():
            y=vals(a,field)
            if target.startswith('abs_'):y=abs(y)
            for feat in FEATURES:
                x=vals(a,feat)
                correlations.append({'group':name,'target':target,'feature':feat,
                    'n':len(a),'pearson':correlation(x,y),
                    'spearman':correlation(x,y,method='spearman')})
    time=[]
    for name, a in groups.items():
        if name=='ALL_SAME_SCENE' or name.startswith('DISTANCE_'):
            continue
        if name.startswith('ROUTE_'):
            continue  # multiple anchors per route: not a single temporal stream
        series=sorted(a,key=lambda r:int(r['sample_index']))
        x=vals(series,'e_mp_m');y=vals(series,'full_minus_los_s')
        time.append({'case':name,'n':len(series),
            'range_lag1':correlation(x[:-1],x[1:]),
            's_lag1':correlation(y[:-1],y[1:]),
            'range_to_next_s':correlation(x[:-1],y[1:]),
            's_to_next_range':correlation(y[:-1],x[1:])})
    return summary,correlations,time


def heading_gains(d2path, labels):
    """Optional original D2 counterfactual: same pose, B_OLD arms B/C."""
    if d2path is None:return []
    lookup={(r['case'],r['pose_id'],r['channel']):r for r in labels}
    records=[];seen=set()
    opener=gzip.open if str(d2path).endswith('.gz') else open
    with opener(d2path,'rt',newline='',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['model']!='B_OLD' or r['channel']!='full' or r['arm'] not in ('B','C'):continue
            key=(r['case'],r['pose_id'],r['channel']);l=lookup.get(key)
            if l is None:continue
            unique=key+(r['arm'],)
            if unique in seen:raise RuntimeError('D2 gain duplicate pose/arm')
            seen.add(unique)
            records.append({'case':r['case'],'route':l['route'],'pose_id':r['pose_id'],
                'arm':r['arm'],'status':r['status'],
                'range_mp_m':float(l['e_mp_m']),
                's_mp':float(l['full_minus_los_s']),
                'tap_error_s':float(l['tap_selection_effect_s']),
                'same_tap_error_s':float(l['same_tap_channel_effect_s']),
                'dpsi_s_deg':float(r['dpsi_s_deg']),
                'dpsi_r_deg':float(r['dpsi_r_deg']),
                'heading_sq_change_deg2':float(r['mse_post_deg2'])-float(r['mse_pre_deg2'])})
    return records


def correction_specific_cross_covariance(rows):
    """RF joint R_sr descriptive target: NEVER feed training truth to EKF.

    A raw residual covariance includes mean offset and spatial/time correlation;
    it is NOT a calibrated same-time noise covariance.
    """
    output=[]
    groups={'ALL_SAME_SCENE':rows}
    for r in rows:
        groups.setdefault(r['case'],[]).append(r)
        groups.setdefault('ROUTE_'+r['route'],[]).append(r)
    for group, subset in groups.items():
        for model,field in [('B_OLD','error_range_B_OLD_m'),
                            ('E1_FULL_LORO','error_range_E1_FULL_LORO_m')]:
            r=vals(subset,field)
            for target,tcol in [('s_model','error_s'),('s_multipath','full_minus_los_s')]:
                s=vals(subset,tcol)
                output.append(dict(group=group,range_model=model,s_target=target,
                   n=len(subset),range_mean_m=float(np.mean(r)),s_mean=float(np.mean(s)),
                   residual_centered_cross_cov_m=float(np.cov(r,s,ddof=1)[0,1]),
                   signed_pearson=correlation(r,s),
                   absolute_pearson=correlation(abs(r),abs(s)),
                   empirical_range_rms_m=float(np.sqrt(np.mean(r*r))),
                   empirical_s_rms=float(np.sqrt(np.mean(s*s)))))
    return output


def gain_correlations(gains):
    """Descriptive association of MP component to actual one-step heading harm.

    Harm here is squared-error increase, not a calibrated causal gate.
    Each case/arm is correlated separately to avoid conflating A/B/C gains.
    """
    groups={}
    for row in gains:
        groups.setdefault((row['case'],row['arm']),[]).append(row)
        groups.setdefault(('ALL_SAME_SCENE',row['arm']),[]).append(row)
    result=[]
    for (case,arm),rows in sorted(groups.items()):
        for feature in ('range_mp_m','s_mp','tap_error_s','same_tap_error_s'):
            x=vals(rows,feature)
            for target in ('dpsi_s_deg','dpsi_r_deg','heading_sq_change_deg2'):
                y=vals(rows,target)
                result.append(dict(group=case,arm=arm,mp_error=feature,
                    heading_effect=target,n=len(rows),
                    pearson=correlation(x,y),spearman=correlation(x,y,method='spearman'),
                    abs_error_pearson=correlation(abs(x),abs(y)),
                    heading_sq_harmed_fraction=float(np.mean(vals(rows,'heading_sq_change_deg2')>0))))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d7',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--d2',type=Path,default=None,help='Original frozen D2_HEADING_DECOMPOSITION.csv.gz')
    args=ap.parse_args()
    rows=paired_records(args.d7)
    summary,associations,temporal=summarize(rows)
    gains=heading_gains(args.d2,rows)
    out=new_output(args.out)
    names=[('D10_RANGE_S_CORRELATION.csv',summary),
           ('D10_CIR_ERROR_ASSOCIATIONS.csv',associations),
           ('D10_TEMPORAL_DEPENDENCE.csv',temporal),
           ('D10_RANGE_MODEL_CROSS_COV.csv',correction_specific_cross_covariance(rows))]
    if gains:
        names.append(('D10_ORIGINAL_D2_HEADING_GAINS.csv',gains))
        names.append(('D10_RF_HEADING_CORRELATION.csv',gain_correlations(gains)))
    files=[]
    for n,x in names:
        f=out/n;write_rows(f,x);files.append(f)
    stage_finish(out,'D10',files,config=vars(args),
        evidence={'D7_manifest_sha256':file_sha(args.d7/'D7_MANIFEST.json'),
                  'D2_sha256':file_sha(args.d2) if args.d2 else None},
        warnings=['Samples/time/7 anchor-cases are NOT independent RF scenes',
                  'Full-vs-LoS oracle errors are OFFLINE-only labels',
                  'Within-case 90th percentile is descriptive, not a trained threshold',
                  'D2 gain analysis NOT_RUN if --d2 omitted; does not create new recursive heading runs'])
    print('D10_DIAGNOSTIC_ONLY',str(out))
if __name__=='__main__':main()
