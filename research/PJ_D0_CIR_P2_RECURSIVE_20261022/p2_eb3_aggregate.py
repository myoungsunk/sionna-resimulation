#!/usr/bin/env python3
"""Aggregate error budget v3."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();src=Path(a.input);dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
pd.set_option('display.width',260);pd.set_option('display.max_columns',40);pd.set_option('display.max_rows',500)
D={}
for k in ('SHARE','MAT','CROSS','KERNEL','WLS','ACF','WQ','PATH','FINF','FD'):
    fs=sorted(src.rglob(f'*_EB3_{k}.csv'));assert len(fs)==7,(k,len(fs));D[k]=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
    D[k].to_csv(dst/f'EB3_{k}.csv',index=False)
qas=[json.loads(f.read_text()) for f in sorted(src.rglob('*_EB3_QA.json'))];assert len(qas)==7
S=D['SHARE'];print('== share of heading MSE (t>=30), route median\n'+S.pivot_table(index=['arm','bias','route'],columns='source',values='share_of_mse',aggfunc='median').round(3).to_string())
print('\n== source mean (deg), route median\n'+S.pivot_table(index=['arm','bias','route'],columns='source',values='mean_deg',aggfunc='median').round(3).to_string())
print('\n== source sd (deg), route median\n'+S.pivot_table(index=['arm','bias','route'],columns='source',values='sd_deg',aggfunc='median').round(3).to_string())
print('\n== bias path / memory / NEES, route median\n'+D['PATH'].groupby(['arm','bias','route'])[['heading_mse_deg2','biaspath_share_total','nobias_linear_heading_rmse_deg','memory_share_older_10s','memory_share_older_30s','memory_rms_older_10s_deg','memory_rms_older_30s_deg','nees_mean','nis_mean_acc']].median().round(3).to_string())
print('\n== input error vs q\n'+D['WQ'].round(4).to_string(index=False))
A=D['ACF'];print('\n== residual ACF (t>=30), route median\n'+A[A.window=='t>=30'].groupby(['signal','arm','route'])[['mean','rms','slow_mean_rms_10s','rho1','tau_int_s','info_factor','detrended_rho1','detrended_info_factor']].median().round(3).to_string())
print('\n== kernel-based variance inflation F (median over t), route median\n'+D['FINF'].groupby(['signal','detrend_10s','arm','route'])[['F_full','F_trunc']].median().round(3).to_string())
print('\n== recursive kernel summary, route median\n'+D['KERNEL'].groupby(['arm','bias','route'])[['sum_abs_Wpol','neg_weight_frac','mean_age_s','frac_older_10s','frac_older_30s','pol_signal_passthrough']].median().round(3).to_string())
W=D['WLS'];rows=[]
for (c,b,arm,tw),g in W.groupby(['case','bias','arm','window_s']):
    rows.append({'case':c,'bias':b,'arm':arm,'window_s':tw,'rms_rec_pred_c1_deg':float(np.sqrt(np.mean(g.rec_pred_c1_deg**2))),
                 'rms_wls_pred_c1_deg':float(np.sqrt(np.mean(g.wls_pred_c1_deg**2))),'corr_rec_vs_wls_pred':float(np.corrcoef(g.rec_pred_c1_deg,g.wls_pred_c1_deg)[0,1]),
                 'median_sum_abs_W_rec':float(g.rec_sum_abs_W.median()),'median_sum_abs_W_wls':float(g.wls_sum_abs_W.median()),'median_corr_W':float(g.corr_W_rec_vs_wls.median())})
WS=pd.DataFrame(rows);WS.to_csv(dst/'EB3_WLS_SUMMARY.csv',index=False);print('\n== recursive kernel vs static WLS (pol c1)\n'+WS.round(3).to_string(index=False))
x=D['CROSS'];rows=[]
for (c,b,arm),g in x.groupby(['case','bias','arm']):
    gg=g.set_index(['inputs','weights'])
    for col in ('mse_all_deg2','mse_exo_deg2','mse_pol_c1_deg2'):
        AA=gg.loc[(arm,arm),col];AB=gg.loc[(arm,'BASE'),col];BA=gg.loc[('BASE',arm),col];BB=gg.loc[('BASE','BASE'),col]
        rows.append({'case':c,'bias':b,'arm':arm,'quantity':col,'arm_own':AA,'base_own':BB,'gap':AA-BB,'input_term_baseW':AB-BB,'propagation_term_armIn':AA-AB,
                     'input_term_armW':AA-BA,'propagation_term_baseIn':BA-BB})
CX=pd.DataFrame(rows);CX.to_csv(dst/'EB3_CROSS_DECOMP.csv',index=False);print('\n== accounting decomposition of gap vs BASE (deg^2)\n'+CX.round(3).to_string(index=False))
print('\n== finite-difference QA\n'+D['FD'].groupby('arm')[['H_relmax','F_absmax','G_absmax']].max().to_string())
qa={'closure_max_deg':max(v for q in qas for v in q['closure'].values()),'parity_max':max(v for q in qas for v in q['parity'].values()),
    'fd_H_relmax':float(D['FD'].H_relmax.max()),'fd_F_absmax':float(D['FD'].F_absmax.max()),'fd_G_absmax':float(D['FD'].G_absmax.max())}
(dst/'EB3_QA.json').write_text(json.dumps(qa,indent=2));print('EB3_ALL_PASS '+json.dumps(qa),flush=True)
