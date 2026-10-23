#!/usr/bin/env python3
"""Aggregate error budget v2 (share, covariance, cross-propagation, kernel, ACF, w vs q) and Monte Carlo seeds."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True);p.add_argument('--n_seeds',type=int,required=True)
a=p.parse_args();src=Path(a.input);dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
pd.set_option('display.width',260);pd.set_option('display.max_columns',40);pd.set_option('display.max_rows',400)
def cat(pat,n=None):
    fs=sorted(src.rglob(pat));assert fs,pat
    if n:assert len(fs)==n,(pat,len(fs))
    return pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
# ---------- error budget v2 ----------
SH=cat('*_EB2_SHARE.csv',7);CV=cat('*_EB2_COV.csv',7);CR=cat('*_EB2_CROSS.csv',7);KE=cat('*_EB2_KERNEL.csv',7);AC=cat('*_EB2_ACF.csv',7);WQ=cat('*_EB2_WQ.csv',7)
for n,d in (('SHARE',SH),('COV',CV),('CROSS',CR),('KERNEL',KE),('ACF',AC),('WQ',WQ)):d.to_csv(dst/f'EB2_{n}.csv',index=False)
qa2=[json.loads(f.read_text()) for f in sorted(src.rglob('*_EB2_QA.json'))];assert len(qa2)==7
print('== EB2 heading-MSE share by source (t>=30), route median\n'+SH.pivot_table(index=['arm','bias','route'],columns='source',values='share',aggfunc='median').round(3).to_string())
x=CR.pivot_table(index=['case','route','bias','arm'],columns=['inputs','weights'],values='heading_mse_deg2').reset_index()
def g(r,i,w):return r[(i,w)]
rows=[]
for _,r in x.iterrows():
    A=r[('arm','')];AA=r[(A,A)];AB=r[(A,'BASE')];BA=r[('BASE',A)];BB=r[('BASE','BASE')]
    rows.append({'case':r[('case','')],'route':r[('route','')],'bias':r[('bias','')],'arm':A,'mse_arm':AA,'mse_base':BB,'gap':AA-BB,
                 'input_effect_baseW':AB-BB,'propagation_effect_armIn':AA-AB,'input_effect_armW':AA-BA,'propagation_effect_baseIn':BA-BB})
GX=pd.DataFrame(rows);GX.to_csv(dst/'EB2_CROSS_DECOMP.csv',index=False)
print('\n== gap vs BASE = input effect + propagation effect (deg^2), per case\n'+GX.round(3).to_string(index=False))
print('\n== polarization influence kernel (t>=30 sampled), route median\n'+KE.groupby(['arm','bias','route'])[['sum_abs_W','neg_weight_frac','mean_age_s','half_weight_age_s','frac_older_10s','frac_older_30s','pol_signal_passthrough']].median().round(3).to_string())
print('\n== residual ACF (t>=30), route median\n'+AC[AC.window=='t>=30'].groupby(['signal','arm','route'])[['mean','rms','rho1','tau_int_s','tau_e_s','info_factor']].median().round(3).to_string())
print('\n== input noise vs filter q\n'+WQ.round(3).to_string(index=False))
# ---------- Monte Carlo ----------
MC=cat('*_MC_*.csv');MC=MC.drop_duplicates(['case','bias','seed_idx','arm']);MC.to_csv(dst/'MC_ALL.csv',index=False)
assert MC.groupby(['case','bias','arm']).seed_idx.nunique().min()==a.n_seeds,'MC_INCOMPLETE'
qam=[json.loads(f.read_text()) for f in sorted(src.rglob('*_MC_*_QA.json'))]
W='stable_30_plus'
pv=MC.pivot_table(index=['case','route','bias','seed_idx'],columns='arm',values=f'{W}_heading_rmse_deg').reset_index()
pv['r_PW_B']=pv.PWIDE_NOES/pv.BASE;pv['r_OR_B']=pv.ORACLE/pv.BASE;pv['d_PW_B']=pv.PWIDE_NOES-pv.BASE;pv.to_csv(dst/'MC_PAIRED.csv',index=False)
cs=pv.groupby(['case','route','bias']).agg(BASE_mean=('BASE','mean'),BASE_sd=('BASE','std'),PW_mean=('PWIDE_NOES','mean'),PW_sd=('PWIDE_NOES','std'),
    OR_mean=('ORACLE','mean'),ratio_mean=('r_PW_B','mean'),ratio_sd=('r_PW_B','std'),ratio_p10=('r_PW_B',lambda v:v.quantile(.1)),
    ratio_p90=('r_PW_B',lambda v:v.quantile(.9)),frac_PW_better=('r_PW_B',lambda v:(v<1).mean()),d_mean=('d_PW_B','mean'),d_sd=('d_PW_B','std')).reset_index()
s0=pv[pv.seed_idx==0].set_index(['case','bias']).r_PW_B;cs['ratio_seed0']=[s0.loc[(c,b)] for c,b in zip(cs.case,cs.bias)]
cs['effect_size']=cs.d_mean/cs.d_sd;cs.to_csv(dst/'MC_CASE.csv',index=False)
print('\n== MC per case (t>=30 heading RMSE, deg; ratio PWIDE/BASE)\n'+cs.round(3).to_string(index=False))
rt=pv.groupby(['route','bias','seed_idx']).r_PW_B.median().reset_index().groupby(['route','bias']).r_PW_B.describe(percentiles=[.1,.5,.9])
rt.to_csv(dst/'MC_ROUTE.csv');print('\n== route-median ratio across seeds\n'+rt.round(3).to_string())
for wn in ('initial_0_10','middle_10_30'):
    q=MC.pivot_table(index=['case','route','bias','seed_idx'],columns='arm',values=f'{wn}_heading_rmse_deg').reset_index();q['r']=q.PWIDE_NOES/q.BASE
    print(f'\n== {wn}: ratio PWIDE/BASE mean (sd) per route\n'+q.groupby(['route','bias']).r.agg(['mean','std']).round(3).to_string())
qa={'eb2_closure_max_deg':max(v for q in qa2 for v in q['closure'].values()),'eb2_parity_max':max(v for q in qa2 for v in q['parity'].values()),
    'mc_parity_max':max([v for q in qam for v in q['parity'].values()] or [0.]),'n_seeds':a.n_seeds}
(dst/'EB2_MC_QA.json').write_text(json.dumps(qa,indent=2));print('EB2_MC_ALL_PASS '+json.dumps(qa),flush=True)
