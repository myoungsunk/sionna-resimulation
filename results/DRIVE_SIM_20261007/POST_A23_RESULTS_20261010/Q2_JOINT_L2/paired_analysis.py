from pathlib import Path
import json,numpy as np,pandas as pd
root=Path(__file__).parent;o=root/'retrieved/OUTPUT';plan=json.loads((root/'PAIRED_ANALYSIS_PLAN.json').read_text())
df=pd.concat([pd.read_csv(o/x) for x in ['A0_ARMS.csv','ARMS_controls.csv','ARMS_q1.csv','ARMS_q2.csv','ARMS_joint.csv']],ignore_index=True)
rng=np.random.default_rng(plan['seed']);idx=rng.integers(0,50,size=(plan['bootstrap_replicates'],50));rows=[]
for tag in [0,1,2,'seed_mean_3drifts']:
 unit=df.groupby(['arm','seed'])[plan['metrics']].mean().reset_index() if isinstance(tag,str) else df[df.drift==tag]
 for contrast in plan['contrasts']:
  a,b=contrast.split('-');aa=unit[unit.arm==a].set_index('seed').sort_index();bb=unit[unit.arm==b].set_index('seed').sort_index();assert aa.index.tolist()==bb.index.tolist()==list(range(50))
  for metric in plan['metrics']:
   d=aa[metric].to_numpy()-bb[metric].to_numpy();boot=d[idx].mean(axis=1);lo,hi=np.quantile(boot,[.025,.975]);rows.append(dict(drift=tag,contrast=contrast,metric=metric,n_seeds=50,difference=float(d.mean()),ci_low=float(lo),ci_high=float(hi),median_seed_difference=float(np.median(d)),min_seed_difference=float(d.min()),max_seed_difference=float(d.max())))
pd.DataFrame(rows).to_csv(root/'PAIRED_CONTRASTS.csv',index=False)
summary=df.groupby(['arm','drift']).agg(nees_mean=('nees_mean','mean'),nees_median=('nees_mean','median'),nees_max=('nees_mean','max'),heading_median=('heading_rmse_deg','median'),heading_max=('heading_rmse_deg','max'),pos_median=('pos_rmse_m','median'),pos_max=('pos_rmse_m','max'));summary.to_csv(root/'SEED_DISTRIBUTION.csv')
us=pd.read_csv(o/'ARM_UNIT_STATS_joint.csv');j=us[us.arm=='J2_ar_corr'];clipping=j.j2_clipped.astype(str).str.lower();assert clipping.isin(['false','true']).all()
cor=dict(j2_runs=len(j),j2_clipped=int((clipping=='true').sum()),target_mean=float(j.j2_target_corr.mean()),innovation_corr=float(j.j2_innovation_corr.mean()),achieved_pre=float(j.noise_corr_pre.mean()),achieved_fed=float(j.fed_corr_s_r.mean()),achieved_fed_seed_mean_range=[float(v) for v in j.groupby('seed').fed_corr_s_r.mean().agg(['min','max']).to_numpy()])
(root/'JOINT_CORRELATION_CHECK.json').write_text(json.dumps(cor,indent=2));print(json.dumps(cor));print(pd.DataFrame(rows).query("drift=='seed_mean_3drifts' and metric=='nees_mean'").to_string(index=False))
