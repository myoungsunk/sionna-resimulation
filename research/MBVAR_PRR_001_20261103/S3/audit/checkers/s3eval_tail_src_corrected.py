from pathlib import Path
import pandas as pd,numpy as np,json
p=Path('/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103');r=p/'S3/runs/EVAL_001'
sc=pd.read_csv(r/'SCORES_PER_SEED.csv');sm=pd.read_csv(r/'PAIRED_SUMMARY.csv')
print('D_WORST_PRIMARY',sc[(sc.window=='primary')&sc.arm.isin(['A','D_CP'])].groupby(['route','bias','channel','arm'])[['heading_rmse_deg','xy_rmse_m','heading_max_deg','xy_max_m','nees4']].max().to_string())
print('PROTECTION_ALL_WINDOWS_FAILURES_DESCRIPTIVE',sm[(sm.metric.isin(['heading_rmse_deg','xy_rmse_m']))&((sm.route=='R5')|(sm.channel=='Native_LoS'))&((sm.ratio_median>1.05)|(sm.ratio_p90>1.2)|(sm.near_zero_margin_violations>0))][['route','bias','channel','window','arm','metric','ratio_median','ratio_p90','near_zero_margin_violations']].to_string(index=False))
ep=pd.read_csv(r/'EVENT_ENDPOINTS.csv')
print('ALL_EVENT_COHORTS',json.dumps(dict(n=len(ep),already_accurate=int(ep.already_accurate.sum()),censored=int(ep.censored.sum()),inaccurate_censored=int((~ep.already_accurate&ep.censored).sum()))))
print('SHORT_REMAINDER',ep.groupby('disposition')[['window_10s_censored','window_20s_censored']].sum().to_string())

rows=[]
for route in ('R4','R5'):
 for bias in ('B0','L2'):
  for ch in ('Full','Native_LoS'):
   path=p/'S2/runs/DEV_001'/f'{route}_aB_m0_{bias}_{ch}_0_D_P.npz'
   with np.load(path) as f:
    rows.append(dict(route=route,bias=bias,channel=ch,kernel_p99_ms=float(np.quantile(f['latency_ns'],.99)/1e6),kernel_max_ms=float(f['latency_ns'].max()/1e6)))
print('S2_DP_UNSCHEDULED_KERNEL_COST_ONLY',json.dumps(rows))
