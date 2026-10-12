"""Regress 7 published sensor-v2 main-phase cases (arms A-D) against the 12-case replay."""
import json,numpy as np,pandas as pd
from pathlib import Path
S=Path(__file__).resolve().parent;G=S/'g7'
pub=pd.read_csv('/home/user/sionna-resimulation/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/OUTPUT/09_V2_main.csv')
new=pd.read_csv(G/'job/OUTPUT/09_V2_main.csv');keys=['case','drift','seed','arm']
assert len(new)==7200 and len(pub)==4200 and not new.duplicated(keys).any()
n7=new[new.case.isin(set(pub.case))].sort_values(keys).reset_index(drop=True);p=pub.sort_values(keys).reset_index(drop=True)
assert list(n7.columns)==list(p.columns) and (n7[keys].values==p[keys].values).all()
rep={};worst=0.;bad=[]
for c in p.columns:
    if c=='seconds':continue
    if p[c].dtype.kind=='f':
        x,y=n7[c].to_numpy(float),p[c].to_numpy(float);nan_eq=bool((np.isnan(x)==np.isnan(y)).all());d=float(np.nanmax(np.abs(x-y))) if np.isfinite(x).any() else 0.;sc=float(max(np.nanmax(np.abs(y)) if np.isfinite(y).any() else 0.,1.));rep[c]=d/sc;worst=max(worst,d/sc)
        if not nan_eq:bad.append(c+':nan_pattern')
    elif not (n7[c].astype(str)==p[c].astype(str)).all():bad.append(c)
res=dict(rows_compared=len(p),columns=len(p.columns)-1,worst_rel_to_scale=worst,nonmatching_columns=bad,pass_1e12=bool(worst<=1e-12 and not bad),worst_columns=sorted(((v,k) for k,v in rep.items()),reverse=True)[:5],
         failed_runs_new_total=int(new.error.notna().sum()),failed_runs_new_5cases=int(new[~new.case.isin(set(pub.case))].error.notna().sum()),failed_runs_published=int(pub.error.notna().sum()))
json.dump(res,open(G/'out/REGRESSION_SIM_7.json','w'),indent=1,default=float);print(json.dumps(res,default=float))
nn=new[~new.case.isin(set(pub.case))];cols=['heading_rmse_deg','pos_rmse_m','nees_mean','pose_coverage','range_reject_rate','s_reject_rate']
print('NEW 5 cases by arm (mean over drift,seed):');print(nn.groupby(['case','arm'])[cols].mean().round(3).to_string())
print('PUBLISHED 7 cases by arm:');print(p.groupby(['arm'])[cols].mean().round(3).to_string());print(nn.groupby('arm')[cols].mean().round(3).to_string())
new.to_csv(G/'out/09_V2_main_12.csv',index=False)
