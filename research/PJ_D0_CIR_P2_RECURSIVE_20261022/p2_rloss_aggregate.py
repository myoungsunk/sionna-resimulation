#!/usr/bin/env python3
"""Aggregate the recursive-loss counterfactuals and compare with the static local-window bias ratio."""
from __future__ import annotations
import argparse, json, glob
from pathlib import Path
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
fs=sorted(Path(a.input).rglob('*_RLOSS_SCORES.csv'));assert len(fs)==7,fs
S=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True);assert len(S)==7*2*15
qas=[json.loads(f.read_text()) for f in sorted(Path(a.input).rglob('*_RLOSS_QA.json'))];assert len(qas)==7
par=max(v for q in qas for e in q['parity'].values() for v in e.values());assert par<1e-7
S.to_csv(dst/'RLOSS_SCORES.csv',index=False)
# static local-window weighted bias ratio PWIDE/BASE at the GT pose (R2 decomposition packets, 65-packet windows)
P=pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(HERE/'results_r2diag/*_R2DIAG_PACKETS.csv.gz')))],ignore_index=True)
st={}
for case,g in P.groupby('case'):
    g=g.sort_values('pose_id');blk=np.arange(len(g))//65;b=[];w=[]
    for _,x in g.groupby(blk):
        if len(x)<32:continue
        den=np.sum(x.g**2/x.V);b.append(np.sum(x.g*x.r_base/x.V)/den);w.append(np.sum(x.g*x.r_pwide/x.V)/den)
    st[case]=float(np.sqrt(np.mean(np.square(w)))/np.sqrt(np.mean(np.square(b))))
W='stable_30_plus'
piv=S.pivot_table(index=['case','route','bias','mode'],columns='corrector',values=f'{W}_heading_rmse_deg').reset_index()
piv['ratio_PWIDE_BASE']=piv.PWIDE/piv.BASE;piv['static_ratio']=piv.case.map(st);piv['gap']=piv.ratio_PWIDE_BASE-piv.static_ratio
piv.to_csv(dst/'RLOSS_RATIO.csv',index=False)
extra=S.pivot_table(index=['case','route','bias','mode'],columns='corrector',
        values=[f'{W}_bg_err_rms_dps',f'{W}_accept',f'{W}_heading_nees_1d',f'{W}_c2_rms',f'{W}_c2_acc_mean',f'{W}_eps_acc_mean',f'{W}_xy_rmse_cm'])
extra.columns=[f'{c[0].replace(W+"_","")}__{c[1]}' for c in extra.columns];extra.reset_index().to_csv(dst/'RLOSS_EXTRA.csv',index=False)
pd.set_option('display.width',260);pd.set_option('display.max_columns',40);pd.set_option('display.max_rows',400)
print('heading RMSE t>=30, route median\n'+piv.groupby(['mode','bias','route'])[['BASE','PWIDE','ORACLE','ratio_PWIDE_BASE','static_ratio','gap']].median().round(3).to_string())
print('\nper case ratio PWIDE/BASE by mode (mean over B0/L2)\n'+piv.groupby(['case','mode']).ratio_PWIDE_BASE.mean().unstack().round(3).assign(static=pd.Series(st).round(3)).to_string())
print('\nextra (route median)\n'+extra.groupby(['mode','route']).median().round(4).to_string())
(dst/'RLOSS_QA.json').write_text(json.dumps({'parity_max':par,'static_ratio':st},indent=2))
print('RLOSS_ALL_PASS',flush=True)
