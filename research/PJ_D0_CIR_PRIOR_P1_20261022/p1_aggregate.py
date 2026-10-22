#!/usr/bin/env python3
"""Collect strict P1 evaluations; fail if a held route or sanity QA is missing."""
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
args=p.parse_args()
src=Path(args.input);dst=Path(args.out);dst.mkdir(parents=True,exist_ok=True)
paths={key:sorted(src.rglob('*_'+key+'.csv')) for key in ('P1_METRICS','P1_CASE','P1_GAIN')}
for key,entries in paths.items():
    assert len(entries)==3,(key,[str(x) for x in entries])
    df=pd.concat([pd.read_csv(f) for f in entries],ignore_index=True)
    assert set(df.route)=={'R2','R4','R5'},(key,set(df.route))
    df.to_csv(dst/(key+'.csv'),index=False)
qa_files=sorted(src.rglob('*_P1_QA.json'))
assert len(qa_files)==3,qa_files
qas=[json.loads(p.read_text()) for p in qa_files]
assert set(q['held'] for q in qas)=={'R2','R4','R5'}
assert max(q['qa_legacy_maxdiff'] for q in qas)<1e-6
assert max(max(q['qa_lut'].values()) for q in qas)<2e-5
all_=pd.read_csv(dst/'P1_METRICS.csv')
key=['route','delta','gain_mode'];base=all_[all_.arm=='PRIOR_ONLY'].set_index(key)
rows=[]
for g,armdata in all_.groupby('gain_mode'):
 for delta in [0,1,-1,2,-2,5,-5,10,-10,20,-20]:
  sel=armdata[(armdata.delta==delta)&(armdata.arm=='CIR_PLUS_D0')]
  assert len(sel)==3
  rr=sel.heading_rmse_deg.to_numpy()
  rr0=base.loc[[tuple(x) for x in sel[key].to_numpy()], 'heading_rmse_deg'].to_numpy()
  rows.append({'gain_mode':g,'delta':delta,'heading_rmse_mean':float(np.mean(rr)),
     'route_success_vs_prior':int(np.sum(rr<rr0)),
     'R2_heading_rmse':float(sel[sel.route=='R2'].heading_rmse_deg.iloc[0]),
     'R4_heading_rmse':float(sel[sel.route=='R4'].heading_rmse_deg.iloc[0]),
     'R5_heading_rmse':float(sel[sel.route=='R5'].heading_rmse_deg.iloc[0])})
summary=pd.DataFrame(rows)
summary.to_csv(dst/'P1_ROUTE_SUMMARY.csv',index=False)
(dst/'P1_QA.json').write_text(json.dumps({
    'held_route_qa':qas,
    'n_route_models':3,
    'primary_rule':'Compare one-step heading RMSE against prior (|delta|) and CIR_ONLY, never threshold G',
    'data_held_out':'R2/R4/R5 each excluded during HGB training',
    'synthetic_GT_centered_prior':True,
    'actual_IMU_odom_recursive_evaluation':False
},indent=2))
print('P1 ROUTE SUMMARY (LOCAL_3DEG)\n'+summary[summary.gain_mode=='LOCAL_3DEG'].round(4).to_string(index=False),flush=True)
print('P1_ALL_PASS, summaries and diagnostics saved',flush=True)
