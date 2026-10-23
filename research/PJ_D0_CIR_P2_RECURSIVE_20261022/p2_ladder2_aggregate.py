#!/usr/bin/env python3
"""Aggregate ladder 2: R_s rule steps, then the same-rule comparison BASE_KV / CIR_KV / WIDE_KV."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

STEPS=[]
for X in ('BASE','CIR','WIDE'):
    STEPS+=[(f'{X}: update R V_s -> kappa V_s',f'L_{X}',f'L_{X}_KU'),(f'{X}: gate R V_s -> kappa V_s',f'L_{X}_KU',f'L_{X}_KV')]
STEPS+=[('same rule: BASE_KV -> CIR_KV','L_BASE_KV','L_CIR_KV'),('same rule: CIR_KV -> WIDE_KV','L_CIR_KV','L_WIDE_KV'),
        ('same rule: BASE_KV -> WIDE_KV','L_BASE_KV','L_WIDE_KV'),('reference: BASE -> WIDE_KV','L_BASE','L_WIDE_KV'),
        ('reference: WIDE_KV -> ORACLE','L_WIDE_KV','L_ORACLE')]
WIN=['initial_0_2','early_2_10','middle_10_30','stable_30_plus','all']
M=['heading_rmse_deg','heading_signed_bias_deg','heading_nees_1d','heading_cov95','xy_rmse_cm','accept','eps_acc_mean']
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
fs=sorted(Path(a.input).rglob('*_LADDER2_SCORES.csv'));assert len(fs)==7,[str(f) for f in fs]
S=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
assert S.case.nunique()==7 and S.arm.nunique()==10 and len(S)==7*2*10
qas=[json.loads(f.read_text()) for f in sorted(Path(a.input).rglob('*_LADDER2_QA.json'))];assert len(qas)==7
par=max(v for q in qas for e in q['parity'].values() for v in e.values());assert par<1e-7
kap=[json.loads(f.read_text()) for f in sorted(Path(a.input).rglob('*_RKAPPA.json'))];assert len(kap)==3
S.to_csv(dst/'LADDER2_SCORES.csv',index=False)
K=['case','route','bias'];rows=[]
for name,a0,a1 in STEPS:
    x0=S[S.arm==a0].set_index(K);x1=S[S.arm==a1].set_index(K);assert x0.index.equals(x1.index)
    for idx in x0.index:
        for w in WIN:
            r={'step':name,'from':a0,'to':a1,**dict(zip(K,idx)),'window':w}
            for m in M:
                r[f'{m}_from']=x0.loc[idx,f'{w}_{m}'];r[f'{m}_to']=x1.loc[idx,f'{w}_{m}']
            r['rmse_ratio']=r['heading_rmse_deg_to']/r['heading_rmse_deg_from']
            r['xy_ratio']=r['xy_rmse_cm_to']/r['xy_rmse_cm_from'];rows.append(r)
D=pd.DataFrame(rows);D.to_csv(dst/'LADDER2_STEPS.csv',index=False)
R=(D.groupby(['step','bias','window','route'])
   .agg(rmse_ratio_median=('rmse_ratio','median'),xy_ratio_median=('xy_ratio','median'),
        n_better=('rmse_ratio',lambda v:int((v<1).sum())),n=('rmse_ratio','size'),
        nees_from=('heading_nees_1d_from','median'),nees_to=('heading_nees_1d_to','median'),
        cov_from=('heading_cov95_from','median'),cov_to=('heading_cov95_to','median'),
        acc_from=('accept_from','median'),acc_to=('accept_to','median')).reset_index())
R.to_csv(dst/'LADDER2_ROUTE.csv',index=False)
qa={'parity_max':par,'kappa':{k['held']:k['kappa'] for k in kap},'spearman_eps2_vs_Vs':{k['held']:k['spearman_eps2_vs_Vs'] for k in kap},
    'mse_ref_diff_max':max(v for k in kap for v in k['mse_ref_diff'].values())}
(dst/'LADDER2_QA.json').write_text(json.dumps(qa,indent=2))
v=R[R.window=='stable_30_plus'].pivot_table(index=['step','bias'],columns='route',values='rmse_ratio_median')
print('LADDER2 heading rmse ratio (to/from), route median, t>=30 s\n'+v.round(3).to_string(),flush=True)
print('LADDER2_ALL_PASS '+json.dumps(qa),flush=True)
