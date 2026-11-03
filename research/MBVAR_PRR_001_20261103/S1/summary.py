"""Summarize paired outcomes within each individual route, bias, and channel."""
import numpy as np
import pandas as pd
def paired_summary(scores):
 rows=[]
 for (route,bias,ch,window),table in scores.groupby(['route','bias','channel','window'],sort=True):
  baseline=table[table.arm=='W0'].set_index('seed',verify_integrity=True).sort_index()
  for arm,group in table[table.arm!='W0'].groupby('arm'):
   other=group.set_index('seed',verify_integrity=True).sort_index()
   if not other.index.equals(baseline.index):raise ValueError('seed coverage')
   for field in ('heading_rmse_deg','xy_rmse_m','heading_p95_deg','xy_p95_m','heading_coverage95','nees3','nees4','nees2'):
    x=baseline[field].to_numpy();y=other[field].to_numpy();diff=y-x
    if not np.isfinite(diff).all():continue
    rng=np.random.default_rng(20261103);idx=rng.integers(len(x),size=(10000,len(x)))
    lower,upper=np.percentile(np.median(diff[idx],axis=1),[2.5,97.5])
    row=dict(route=route,bias=bias,channel=ch,window=window,arm=arm,metric=field,seeds=len(x),baseline_median=np.median(x),method_median=np.median(y),paired_delta_median=np.median(diff),delta_ci_low=lower,delta_ci_high=upper,baseline_max=x.max(),method_max=y.max(),decreased_fraction=(diff<0).mean())
    if field in ('heading_rmse_deg','xy_rmse_m'):
     margin=.05 if field=='heading_rmse_deg' else .01
     normal=x>margin
     if np.any(normal):row.update(ratio_median=np.median(y[normal]/x[normal]),ratio_p90=np.quantile(y[normal]/x[normal],.9))
     row.update(near_zero_n=int((~normal).sum()),near_zero_margin_violations=int((diff[~normal]>margin).sum()))
    if field=='heading_coverage95':row['mean_distance_to_target_delta']=float(np.mean(abs(y-.95)-abs(x-.95)))
    rows.append(row)
 return pd.DataFrame(rows)
