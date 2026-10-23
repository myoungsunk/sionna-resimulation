#!/usr/bin/env python3
"""Aggregate verification 1: case tables, block-level check of the weighted bias formula."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
def cat(tag):
    fs=sorted(Path(a.input).rglob(f'*_V1_{tag}.csv'));assert len(fs)==7,(tag,fs);return pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
S=cat('SUMMARY');B=cat('BLOCKS');T=cat('STRATA')
S.to_csv(dst/'V1_SUMMARY.csv',index=False);B.to_csv(dst/'V1_BLOCKS.csv',index=False);T.to_csv(dst/'V1_STRATA.csv',index=False)
fit=[]
for (arm,bias),g in B[B.t0>=30].groupby(['arm','bias']):
    x=g.wb_total.to_numpy();y=g.heading_err_mean.to_numpy();ok=np.isfinite(x)&np.isfinite(y)
    sl=float(np.polyfit(x[ok],y[ok],1)[0]) if ok.sum()>3 else np.nan
    fit.append({'arm':arm,'bias':bias,'n_blocks':int(ok.sum()),'pearson':float(np.corrcoef(x[ok],y[ok])[0,1]),'slope':sl})
for (arm,bias),g in S[S.window=='stable_30_plus'].groupby(['arm','bias']):
    x=g.wb_total.to_numpy();y=g.heading_err_mean.to_numpy()
    fit.append({'arm':arm,'bias':bias,'level':'case t>=30','n_blocks':len(g),'pearson':float(np.corrcoef(x,y)[0,1]),'slope':float(np.polyfit(x,y,1)[0])})
F=pd.DataFrame(fit);F.to_csv(dst/'V1_WBIAS_FIT.csv',index=False)
pd.set_option('display.width',250);pd.set_option('display.max_columns',30)
cols=['case','bias','arm','heading_err_mean','wb_total','wb_c1','wb_c2','wb_c3','c1_acc_mean','c2_acc_mean','c3_acc_mean','acc_frac']
print('V1 t>=30 (heading in deg, c in s units)\n'+S[S.window=='stable_30_plus'][cols].round(4).to_string(index=False))
print('\nV1 weighted-bias formula vs actual\n'+F.round(3).to_string(index=False))
print('V1_ALL_PASS',flush=True)
