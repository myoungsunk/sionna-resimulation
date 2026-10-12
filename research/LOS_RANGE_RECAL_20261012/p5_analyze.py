"""P5 analysis: paired comparison of range-only EKF arms on identical (case, drift, seed) runs.
Metrics: pose RMSE, heading RMSE, endpoint error, mean pose NEES (3 DoF) + chi2 95 % interval, pose95 coverage, range-innovation lag-1 autocorrelation, accepted range fraction.
CIs: bootstrap over the 12 conditions as clusters (seed-level means inside a cluster) -- only 3 routes / 1 scene, so the interval is marked LIMITED; seed-level paired Wilcoxon is added as a within-condition check.
usage: p5_analyze.py RUNS.csv OUT_DIR [LABEL]"""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import chi2,wilcoxon
d=pd.read_csv(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);label=sys.argv[3] if len(sys.argv)>3 else ''
d=d[d.error.isna()|(d.error=='')].copy();arms=list(d.arm.unique());K=['case','drift','seed']
n_runs=d.groupby('arm').size().to_dict();M=['pos_rmse_m','heading_rmse_deg','endpoint_pos_err','endpoint_hdg_err_deg','nees_mean','pose_coverage','range_innov_acf1','range_reject_rate']
summ=[]
for arm in arms:
    q=d[d.arm==arm];n=len(q);lo,hi=chi2.ppf([.025,.975],3*n)/n   # NEES mean interval is for n independent runs of an exact 3-DoF test; kept as a reference only (the per-run NEES is itself a time average)
    summ.append(dict(arm=arm,n_runs=n,**{m:float(q[m].mean()) for m in M if m in q},nees_median=float(q.nees_mean.median()),nees_p95=float(q.nees_mean.quantile(.95)),pos_rmse_median=float(q.pos_rmse_m.median()),pos_rmse_p95=float(q.pos_rmse_m.quantile(.95)),hdg_rmse_p95=float(q.heading_rmse_deg.quantile(.95)),nees_interval_ref=[float(lo),float(hi)]))
S=pd.DataFrame(summ);S.to_csv(out/'P5_ARM_SUMMARY.csv',index=False)
piv=d.pivot_table(index=K,columns='arm',values=['pos_rmse_m','heading_rmse_deg','nees_mean','pose_coverage'])
rng=np.random.default_rng(20261012);res={'label':label,'n_runs_per_arm':n_runs,'clusters':int(d.case.nunique()),'ci_note':'LIMITED: 12 conditions share one corridor scene and 3 routes; seed-level pairs inside a condition are independent sensor/RF-noise draws','comparisons':{}}
cases=sorted(d.case.unique())
def cluster_boot(a,b,metric,rel=True):
    A=piv[metric][a];B=piv[metric][b];df=pd.DataFrame({'a':A,'b':B}).dropna();df['cs']=[i[0] for i in df.index]
    cm=df.groupby('cs')[['a','b']].mean();point=float((cm.a.mean()/cm.b.mean())-1) if rel else float(cm.a.mean()-cm.b.mean());vals=[]
    for _ in range(4000):
        pick=rng.integers(0,len(cm),len(cm));x=cm.iloc[pick];vals.append((x.a.mean()/x.b.mean()-1) if rel else (x.a.mean()-x.b.mean()))
    try:w=float(wilcoxon(df.a-df.b).pvalue)
    except Exception:w=None
    return dict(point=point,ci95=[float(np.percentile(vals,2.5)),float(np.percentile(vals,97.5))],wilcoxon_p_seedlevel=w,n_pairs=int(len(df)))
for a in arms:
    for b in ('B_OLD','A'):
        if a==b or b not in arms:continue
        res['comparisons'][f'{a}_vs_{b}']={m:cluster_boot(a,b,m,rel=(m!='pose_coverage')) for m in ('pos_rmse_m','heading_rmse_deg','nees_mean','pose_coverage')}
(out/'P5_COVERAGE_NEES.json').write_text(json.dumps(res,indent=1,default=float))
d.groupby(['arm','case']).agg(pos_rmse_m=('pos_rmse_m','mean'),heading_rmse_deg=('heading_rmse_deg','mean'),nees_mean=('nees_mean','mean'),pose_coverage=('pose_coverage','mean'),n=('seed','size')).reset_index().to_csv(out/'P5_POSE_ERRORS.csv',index=False)
d[['case','drift','seed','arm','pos_rmse_m','heading_rmse_deg','endpoint_pos_err','endpoint_hdg_err_deg','nees_mean','nees_p95','nees_max','pose_coverage','range_innov_acf1','range_nis_mean_applied','n_range_applied','range_reject_rate']].to_csv(out/'P5_EKF_PAIRED_RUNS.csv',index=False)
d.groupby('arm')[['range_innov_acf1']].describe().to_csv(out/'P5_INNOVATION_ACF.csv')
pd.set_option('display.width',250);print(S[['arm','n_runs','pos_rmse_m','heading_rmse_deg','nees_mean','nees_median','pose_coverage','range_innov_acf1','range_reject_rate','pos_rmse_p95']].round(4).to_string(index=False))
for k,v in res['comparisons'].items():
    if k.endswith('_vs_B_OLD') or k.endswith('_vs_A'):print(k,{m:(round(x['point'],3),[round(c,3) for c in x['ci95']]) for m,x in v.items()})
