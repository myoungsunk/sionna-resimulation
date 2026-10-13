#!/usr/bin/env python3
"""Paired, within-route trial bootstrap confidence intervals for position RMSE improvements."""
from pathlib import Path
import numpy as np
import pandas as pd
from dual_heading_sim import Config,ROUTES,generate,measure,filter_run
cfg=Config(runs=1000)
rows=[]
for i,route in enumerate(ROUTES):
 d=generate(cfg,route); z=measure(cfg,d)
 r=filter_run(cfg,d,z,method='range')
 b=filter_run(cfg,d,z,method='both')
 rg=np.random.default_rng(20261012+277+i)
 idx=rg.integers(0,cfg.runs,size=(3000,cfg.runs),dtype=np.int32)
 ra=np.sqrt(np.mean(r['per_run_mse_2d'][idx],axis=1))
 ba=np.sqrt(np.mean(b['per_run_mse_2d'][idx],axis=1))
 imp=100*(1-ba/ra)
 cv=100*(np.mean(b['per_run_final_in'][idx],axis=1)-np.mean(r['per_run_final_in'][idx],axis=1))
 rows.append(dict(route=route,n_runs=cfg.runs,rmse_improvement_pct=100*(1-b['rmse_2d_m']/r['rmse_2d_m']),
           lower95_pct=np.quantile(imp,.025),upper95_pct=np.quantile(imp,.975),
           final_coverage_gain_pp=b['final_coverage_pct']-r['final_coverage_pct'],
           final_coverage_gain_lower95_pp=np.quantile(cv,.025),final_coverage_gain_upper95_pp=np.quantile(cv,.975)))
f=Path(__file__).resolve().parent/'13_paired_bootstrap.csv'
pd.DataFrame(rows).to_csv(f,index=False,float_format='%.12g')
print(pd.DataFrame(rows).round(3).to_string(index=False))
