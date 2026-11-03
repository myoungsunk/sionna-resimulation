import json,hashlib,subprocess
from pathlib import Path
import pandas as pd,numpy as np
root=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');pkg=root/'research/MBVAR_PRR_001_20261103';s=pkg/'S3';r=s/'runs/EVAL_001'
sc=pd.read_csv(r/'SCORES_PER_SEED.csv');main=sc[sc.kind=='P'];summary=pd.read_csv(r/'PAIRED_SUMMARY.csv');factorial=pd.read_csv(r/'FACTORIAL_CONTRASTS.csv');checks=0;maxdiff=0
def equal(a,b,label):
 global checks,maxdiff
 if np.isfinite(a) and np.isfinite(b):maxdiff=max(maxdiff,abs(float(a)-float(b)))
 assert np.isclose(a,b,rtol=2e-10,atol=2e-10,equal_nan=True),(label,a,b);checks+=1
for _,row in summary.iterrows():
 tb=main[(main.route==row.route)&(main.bias==row.bias)&(main.channel==row.channel)&(main.window==row.window)];a=tb[tb.arm=='A'].sort_values('seed')[row.metric].to_numpy();b=tb[tb.arm==row.arm].sort_values('seed')[row.metric].to_numpy();assert len(a)==len(b)==20;diff=b-a;idx=np.random.default_rng(20261103).integers(20,size=(10000,20));lo,hi=np.percentile(np.median(diff[idx],axis=1),[2.5,97.5]);d=dict(seeds=20,baseline_median=np.median(a),method_median=np.median(b),paired_delta_median=np.median(diff),delta_ci_low=lo,delta_ci_high=hi,baseline_max=a.max(),method_max=b.max(),decreased_fraction=np.mean(diff<0))
 if row.metric in ('heading_rmse_deg','xy_rmse_m'):
  margin=.05 if row.metric=='heading_rmse_deg' else .01;normal=a>margin
  if normal.any():d.update(ratio_median=np.median(b[normal]/a[normal]),ratio_p90=np.quantile(b[normal]/a[normal],.9))
  d.update(near_zero_n=int((~normal).sum()),near_zero_margin_violations=int(np.sum(diff[~normal]>margin)))
 if row.metric=='heading_coverage95':d['mean_distance_to_target_delta']=np.mean(abs(b-.95)-abs(a-.95))
 for k,v in d.items():equal(row[k],v,'summary '+k)
for _,row in factorial.iterrows():
 tb=main[(main.route==row.route)&(main.bias==row.bias)&(main.channel==row.channel)&(main.seed==row.seed)&(main.window==row.window)].set_index('arm');A,B,C,D=[tb.loc[a,row.metric] for a in ('A','B','C_CP','D_CP')];equal(row.D_minus_B,D-B,'D-B');equal(row.D_minus_C,D-C,'D-C');equal(row.interaction,D-B-C+A,'interaction')
aux=pd.DataFrame()
for _,row in aux.iterrows():
 fields=('route','bias','channel','seed','window','arm');mask=np.ones(len(sc),bool)
 for k in fields:mask&=sc[k]==row[k]
 a=sc[mask&(sc.kind=='P')][row.metric].iloc[0];b=sc[mask&(sc.variant==row.variant)][row.metric].iloc[0];equal(row.paired_delta,b-a,'aux')
old=pd.read_csv(pkg/'S2/runs/EVAL_001/SCORES_PER_SEED.csv');cross=pd.read_csv(r/'CROSS_STAGE_PAIRED.csv')
for _,row in cross.iterrows():
 mask=np.ones(len(main),bool);before=np.ones(len(old),bool)
 for k in ('route','bias','channel','seed','window'):mask&=main[k]==row[k];before&=old[k]==row[k]
 a=old[before&(old.arm=='D_P')&(old.kind=='P')][row.metric].iloc[0];b=main[mask&(main.arm=='D_CP')][row.metric].iloc[0];equal(row.D_CP_minus_D_P,b-a,'cross')
print(json.dumps(dict(summary='PASS',paired_rows=len(summary),factorial_rows=len(factorial),auxiliary_rows=len(aux),cross_stage_rows=len(cross),scalar_checks=checks,max_abs_difference=maxdiff)),flush=True)
print('PRIMARY_RMSE',summary[(summary.window=='primary')&summary.metric.isin(['heading_rmse_deg','xy_rmse_m'])][['route','bias','channel','arm','metric','ratio_median','ratio_p90','near_zero_margin_violations']].to_string(index=False),flush=True)
print('FULL_FACTORIAL',factorial[(factorial.window=='primary')&(factorial.channel=='Full')].groupby(['route','bias','metric'])[['D_minus_B','D_minus_C','interaction']].median().to_string(),flush=True)
print('CROSS_STAGE',cross[cross.window=='primary'].groupby(['route','bias','channel','metric']).D_CP_minus_D_P.median().to_string(),flush=True)
