#!/usr/bin/env python3
"""Aggregate the one-factor ladder: per adjacent pair, per case x bias x window effect sizes."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

STEPS=[('S0->S1 mu_s POWER removed','L_BASE','L_NOMU'),
       ('S0->S2 R_s per-packet->const','L_BASE','L_CONSTR'),
       ('S1->S3 add CIR corrector','L_NOMU','L_CIR'),
       ('S3->S4 CIR->WIDE (add d0)','L_CIR','L_WIDE'),
       ('S4->S5 d0 at prior->d0 at GT','L_WIDE','L_WIDE_GTD0'),
       ('S4->S6 WIDE->oracle LoS','L_WIDE','L_ORACLE')]
WIN=['initial_0_2','early_2_10','middle_10_30','stable_30_plus','all']
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
fs=sorted(Path(a.input).rglob('*_LADDER_SCORES.csv'));assert len(fs)==7,[str(f) for f in fs]
S=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
assert set(S.route)=={'R2','R4','R5'} and S.case.nunique()==7 and S.arm.nunique()==8 and len(S)==7*2*8
qas=[json.loads(f.read_text()) for f in sorted(Path(a.input).rglob('*_LADDER_QA.json'))];assert len(qas)==7
par=max(v for q in qas for e in q['parity'].values() for v in e.values());assert par<1e-7
S.to_csv(dst/'LADDER_SCORES.csv',index=False)
K=['case','route','bias']
rows=[]
for name,a0,a1 in STEPS:
    x0=S[S.arm==a0].set_index(K);x1=S[S.arm==a1].set_index(K);assert x0.index.equals(x1.index)
    for idx in x0.index:
        for w in WIN:
            r0,r1=x0.loc[idx,f'{w}_heading_rmse_deg'],x1.loc[idx,f'{w}_heading_rmse_deg']
            rows.append({'step':name,'from':a0,'to':a1,**dict(zip(K,idx)),'window':w,
                'rmse_from':r0,'rmse_to':r1,'rmse_ratio':r1/r0,'rmse_diff':r1-r0,
                'bias_from':x0.loc[idx,f'{w}_heading_signed_bias_deg'],'bias_to':x1.loc[idx,f'{w}_heading_signed_bias_deg'],
                'nees_from':x0.loc[idx,f'{w}_heading_nees_1d'],'nees_to':x1.loc[idx,f'{w}_heading_nees_1d'],
                'cov95_from':x0.loc[idx,f'{w}_heading_cov95'],'cov95_to':x1.loc[idx,f'{w}_heading_cov95'],
                'xy_from':x0.loc[idx,f'{w}_xy_rmse_cm'],'xy_to':x1.loc[idx,f'{w}_xy_rmse_cm'],
                'eps_mean_from':x0.loc[idx,f'{w}_eps_mean'],'eps_mean_to':x1.loc[idx,f'{w}_eps_mean'],
                'eps_acc_mean_from':x0.loc[idx,f'{w}_eps_acc_mean'],'eps_acc_mean_to':x1.loc[idx,f'{w}_eps_acc_mean'],
                'eps_rms_from':x0.loc[idx,f'{w}_eps_rms'],'eps_rms_to':x1.loc[idx,f'{w}_eps_rms']})
D=pd.DataFrame(rows);D.to_csv(dst/'LADDER_STEPS.csv',index=False)
R=(D.groupby(['step','bias','window','route'])
     .agg(rmse_ratio_median=('rmse_ratio','median'),n_better=('rmse_diff',lambda v:int((v<0).sum())),n=('rmse_diff','size'),
          rmse_from=('rmse_from','median'),rmse_to=('rmse_to','median'),
          nees_from=('nees_from','median'),nees_to=('nees_to','median'),
          eps_acc_mean_from=('eps_acc_mean_from','median'),eps_acc_mean_to=('eps_acc_mean_to','median'))
     .reset_index());R.to_csv(dst/'LADDER_ROUTE.csv',index=False)
# additivity of the two BASE-side factors versus the joint change (RAW)
b=S[S.arm=='L_BASE'].set_index(K)
add=[]
for idx in b.index:
    for w in WIN:
        g=lambda arm:float(S[(S.arm==arm)&(S.case==idx[0])&(S.bias==idx[2])][f'{w}_heading_rmse_deg'].iloc[0])
        d1=g('L_NOMU')-g('L_BASE');d2=g('L_CONSTR')-g('L_BASE');d12=g('L_RAW')-g('L_BASE')
        add.append({**dict(zip(K,idx)),'window':w,'d_mu':d1,'d_R':d2,'sum':d1+d2,'d_joint':d12,'interaction':d12-d1-d2})
pd.DataFrame(add).to_csv(dst/'LADDER_ADDITIVITY.csv',index=False)
qa={'cases':sorted(S.case.unique().tolist()),'rows':len(S),'parity_max':par,
    'max_abs_Crs':max(v for q in qas for v in q['max_abs_Crs'].values()),
    'R_const':{q['case']:q['R_const'] for q in qas}}
(dst/'LADDER_QA.json').write_text(json.dumps(qa,indent=2))
v=R[R.window=='stable_30_plus'].pivot_table(index=['step','bias'],columns='route',values='rmse_ratio_median')
print('LADDER rmse ratio (to/from), route median, t>=30 s\n'+v.round(3).to_string(),flush=True)
print('LADDER_ALL_PASS '+json.dumps(qa),flush=True)
