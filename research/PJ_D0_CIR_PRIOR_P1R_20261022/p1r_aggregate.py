#!/usr/bin/env python3
"""Collect P1R route results; fail if a held route or a reproduction QA is missing."""
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd

PRIMARY='SMATCH_RCAL_IEKF'
ARMS=['PRIOR_ONLY','RAW','CIR_ONLY','CIR_PLUS_D0','CIR_PLUS_D0_WIDE','D0_DIRECT','ORACLE_LOS']
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
a=p.parse_args();src=Path(a.input);dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
for key in ('P1R_METRICS','P1R_CASE','P1R_GAIN'):
    fs=sorted(src.rglob(f'*_{key}.csv'));assert len(fs)==3,(key,fs)
    df=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True);assert set(df.route)=={'R2','R4','R5'}
    df.to_csv(dst/f'{key}.csv',index=False)
qas=[json.loads(f.read_text()) for f in sorted(src.rglob('*_P1R_QA.json'))]
assert len(qas)==3 and {q['held'] for q in qas}=={'R2','R4','R5'}
for q in qas:
    assert q['legacy_LOCAL_diff']<1e-6 and q['legacy_GTREF_diff']<1e-6,q['held']
    assert max(q['grid_lut_qa_max'].values())<2e-5,q['held']
m=pd.read_csv(dst/'P1R_METRICS.csv');m=m[m['mode']!='GTREF_LEGACY']
rows=[]
for (mode,delta,arm),g in m.groupby(['mode','delta','arm']):
    r={'mode':mode,'delta':delta,'arm':arm,'rmse_mean':g.heading_rmse_deg.mean(),
       'routes_better_than_prior':int((g.heading_rmse_deg<abs(delta)-1e-9).sum()) if delta else np.nan,
       'q95_mean':g.heading_q95_abs_deg.mean(),'q99_mean':g.heading_q99_abs_deg.mean(),
       'nees_mean':g.nees_mean.mean(),'cover95_mean':g.cover95.mean(),
       'improved_frac_mean':g.heading_improved_frac.mean(),'nonconv_max':g.nonconv_frac.max(),'clip_max':g.clip_frac.max()}
    for _,x in g.iterrows():r[f'{x.route}_rmse']=x.heading_rmse_deg
    rows.append(r)
S=pd.DataFrame(rows);S.to_csv(dst/'P1R_SUMMARY.csv',index=False)
interp={q['held']:q.get('interp_qa') for q in qas}
(dst/'P1R_QA.json').write_text(json.dumps({'held_route_qa':qas,'interp_qa':interp,'primary_mode':PRIMARY,
    'synthetic_GT_centered_prior':True,'position_prior':'GT fixed','recursive':False},indent=2))
pv=S[S['mode']==PRIMARY].pivot_table(index='delta',columns='arm',values='rmse_mean')[[x for x in ARMS if x!='D0_DIRECT']]
print('P1R PRIMARY heading RMSE (deg, mean of 3 held routes)\n'+pv.round(3).to_string(),flush=True)
print('P1R_ALL_PASS',flush=True)
