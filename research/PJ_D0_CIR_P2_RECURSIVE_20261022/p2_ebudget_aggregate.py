#!/usr/bin/env python3
"""Aggregate the exact error budget; attribute the PWIDE-vs-BASE heading MSE gap to sources."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

SRC=['initial','odom','gyro','range','pol_c1_fp0','pol_c1_fp1','pol_c1_fp2','pol_c2','r_pred','r_meas']
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
fs=sorted(Path(a.input).rglob('*_EB.csv'));assert len(fs)==7,fs
E=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True);assert len(E)==7*2*5
E.to_csv(dst/'EB_ALL.csv',index=False)
E['mse']=E.heading_rmse_deg**2
for s in SRC:E[f'mse_{s}']=E.mse*E[f'share_{s}'];E[f'mse_bias_{s}']=E.mse*E[f'biaspath_share_{s}']
gap=[]
for (c,b),g in E.groupby(['case','bias']):
    g=g.set_index('arm')
    for arm in ('CIR','WIDE_NOES','PWIDE_NOES','ORACLE'):
        r={'case':c,'route':g.route.iloc[0],'bias':b,'arm':arm,'mse_arm':g.loc[arm,'mse'],'mse_base':g.loc['BASE','mse'],'d_mse':g.loc[arm,'mse']-g.loc['BASE','mse']}
        for s in SRC:r[f'd_{s}']=g.loc[arm,f'mse_{s}']-g.loc['BASE',f'mse_{s}']
        gap.append(r)
Gp=pd.DataFrame(gap);Gp.to_csv(dst/'EB_GAP_VS_BASE.csv',index=False)
pd.set_option('display.width',260);pd.set_option('display.max_columns',40);pd.set_option('display.max_rows',300)
cols=['heading_rmse_deg','acc_frac']+[f'share_{s}' for s in SRC]+['biaspath_share_total','memory_share_older_10s','memory_share_older_30s','closure_max_deg']
print('share of heading MSE (t>=30), route median\n'+E.groupby(['arm','bias','route'])[cols].median().round(3).to_string())
print('\nMSE gap vs BASE by source (deg^2), route median\n'+Gp.groupby(['arm','bias','route'])[['d_mse']+[f'd_{s}' for s in SRC]].median().round(3).to_string())
qa={'closure_max_deg':float(E.closure_max_deg.max())}
(dst/'EB_QA.json').write_text(json.dumps(qa,indent=2));print('EB_ALL_PASS '+json.dumps(qa),flush=True)
