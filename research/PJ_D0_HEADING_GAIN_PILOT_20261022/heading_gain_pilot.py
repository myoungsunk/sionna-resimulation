#!/usr/bin/env python3
"""Preregistered quick test of heading-information preservation.

Input: LOSC_PACKET_DIAGNOSTIC.csv.gz from frozen held-route validation.
No model fitting; LoS oracle is used only for scoring.
GT +/-1 degree synthetic heading priors, fixed-gain single update, not recursive.
"""
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd

KEY=['route','case','pose_id','delta']
FIELDS=['los_error','nu','oracle_nu','hdiag_post_deg']
ARM_INPUT=['RAW','CIR_ONLY','CIR_PLUS_D0','D0_DIRECT','ORACLE_LOS']
WEIGHTS=(0.0,0.25,0.50,0.75,0.80,0.90,1.0)

def rms(x):
    y=np.asarray(x,float)
    return float(np.sqrt(np.mean(y*y)))

def make_predictions(raw):
    req=set(KEY+FIELDS+['arm'])
    missing=req-set(raw.columns)
    if missing: raise ValueError(f'Missing input columns: {missing}')
    frame=raw[raw.arm.isin(ARM_INPUT)].pivot(index=KEY,columns='arm',values=FIELDS)
    if frame.isna().any().any(): raise ValueError('Missing arm/field in diagnostic packets')
    frame=frame.sort_index()
    q=frame['oracle_nu']['ORACLE_LOS']
    for arm in ARM_INPUT:
        assert np.max(np.abs(frame['oracle_nu'][arm].to_numpy()-q.to_numpy()))<1e-9
    o=[]
    for arm in ARM_INPUT:
        sub=frame.xs(arm,axis=1,level='arm')[FIELDS].copy()
        sub['arm']=arm
        o.append(sub)
    cir=frame.xs('CIR_ONLY',axis=1,level='arm')
    d0=frame.xs('CIR_PLUS_D0',axis=1,level='arm')
    for weight in WEIGHTS:
        z=weight*cir[FIELDS]+(1-weight)*d0[FIELDS]
        z['arm']=f'BLEND_CIR_{weight:.2f}'
        o.append(z)
    for factor in [2.0,4.0,5.0]:
        nu=factor*d0['nu'].to_numpy()
        oracle=frame['oracle_nu']['ORACLE_LOS'].to_numpy()
        prior=frame.index.get_level_values('delta').to_numpy(float)
        sub=pd.DataFrame({
            'los_error':nu-oracle,
            'nu':nu,
            'oracle_nu':oracle,
            'hdiag_post_deg':prior+factor*(d0['hdiag_post_deg'].to_numpy()-prior),
            'arm':f'RESCALE_D0_{factor:g}X'
        },index=frame.index)
        o.append(sub)
    result=pd.concat(o).reset_index()
    assert not result[FIELDS].isna().any().any()
    return result

def summary(pred):
    s=[]
    for (route,arm),grp in pred.groupby(['route','arm']):
        los_rmse=np.mean([rms(y.los_error) for _,y in grp.groupby('delta')])
        heading_rmse=np.mean([rms(y.hdiag_post_deg) for _,y in grp.groupby('delta')])
        left=grp[grp.delta==-1].set_index(['case','pose_id'])
        right=grp[grp.delta==1].set_index(['case','pose_id'])
        if not left.index.equals(right.index): raise ValueError(f'Unpaired +/-1 degrees for {route}/{arm}')
        dnu=right.nu.to_numpy()-left.nu.to_numpy()
        dorec=right.oracle_nu.to_numpy()-left.oracle_nu.to_numpy()
        gain=float(np.dot(dnu,dorec)/np.dot(dorec,dorec))
        errors=np.abs(grp.hdiag_post_deg.to_numpy())
        s.append(dict(route=route,arm=arm,n_pose=len(left),
                los_rmse=los_rmse,heading_rmse_deg=heading_rmse,
                heading_gain=gain,
                heading_abs_q95_deg=float(np.quantile(errors,.95)),
                heading_abs_q99_deg=float(np.quantile(errors,.99)),
                heading_abs_max_deg=float(errors.max()),
                innovation_rmse=rms(grp.nu-grp.oracle_nu)))
    return pd.DataFrame(s).sort_values(['route','arm'])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--out',default='gain_pilot_results')
    args=ap.parse_args()
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv(args.input)
    pred=make_predictions(data)
    metric=summary(pred)
    metric.to_csv(out/'HEADING_GAIN_PILOT_SUMMARY.csv',index=False)
    z=metric[metric.arm.str.startswith('BLEND_')]
    cmp=z.pivot(index='arm',columns='route',values=['heading_gain','heading_rmse_deg','los_rmse'])
    print(cmp.round(5).to_string())
    print('\nRESCALE DIAGNOSTICS:\n',
        metric[metric.arm.str.startswith('RESCALE')]
            [['route','arm','heading_gain','heading_rmse_deg','los_rmse']]
            .round(4).to_string(index=False))
    candidate=z.assign(pass_route=(z.heading_gain>=.8)&(z.heading_rmse_deg<=1.0))
    passes=candidate.groupby('arm').pass_route.all()
    diag={'input_rows':len(data),'output_rows':len(pred),
       'routes':sorted(data.route.unique().tolist()),
       'criterion':'G>=0.8 and single-update heading RMSE <= 1 deg on all R2/R4/R5',
       'all_route_pass':passes.to_dict(),
       'check':'G(CIR_ONLY)=1, G(D0_DIRECT)=0, prior RMSE=1 deg',
       'no_recursive_ekf':True,'held_route_predictions_frozen':True}
    for rt in diag['routes']:
        t=metric[metric.route==rt].set_index('arm')
        assert abs(t.loc['CIR_ONLY','heading_gain']-1)<1e-10
        assert abs(t.loc['D0_DIRECT','heading_gain'])<1e-10
        assert abs(t.loc['D0_DIRECT','heading_rmse_deg']-1)<1e-10
    (out/'HEADING_GAIN_PILOT_QA.json').write_text(
        json.dumps(diag,ensure_ascii=False,indent=2))
    print('\nQA:',json.dumps(diag,ensure_ascii=False))

if __name__=='__main__':
    main()
