"""V05 (exploratory, default LARGE position prior): range-only competitors on the frozen harness. usage: v05_analyze.py RUNS.csv OUT.json"""
import json,sys
import numpy as np,pandas as pd
d=pd.read_csv(sys.argv[1]);assert d.error.isna().all() or (d.error=='').all()
g=d.groupby('arm')[['heading_rmse_deg','pos_rmse_m','nees_mean','pose_coverage','range_reject_rate']].mean();g['nees_median']=d.groupby('arm').nees_mean.median()
piv=d.pivot_table(index=['case','drift','seed'],columns='arm',values='pos_rmse_m');rng=np.random.default_rng(0);comp={}
for a in piv.columns:
    for b in ('B','A'):
        if a in(b,'A','B'):continue
        df=pd.DataFrame({'a':piv[a],'b':piv[b]}).dropna();df['cs']=[i[0] for i in df.index];cm=df.groupby('cs')[['a','b']].mean();v=[]
        for _ in range(2000):
            x=cm.iloc[rng.integers(0,len(cm),len(cm))];v.append(x.a.mean()/x.b.mean()-1)
        comp[f'{a}_vs_{b}']=dict(point=float(cm.a.mean()/cm.b.mean()-1),ci95=[float(np.percentile(v,2.5)),float(np.percentile(v,97.5))])
json.dump(dict(n_runs=len(d),per_arm=g.round(5).to_dict('index'),pos_rmse_relative_change_cluster_bootstrap_over_12_conditions=comp,limitation='LARGE prior (V02 FAIL), 20 seeds, IAT from timestamp analysis of the same corridor; Gauss-Markov bias state / Schmidt-consider NOT_RUN'),open(sys.argv[2],'w'),indent=1)
print(g.round(3).to_string());print(json.dumps(comp,indent=0))
