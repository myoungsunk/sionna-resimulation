from pathlib import Path
import json,time,hashlib,concurrent.futures
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
J=Path('/job');OUT=J/'ANALYSIS';OUT.mkdir(exist_ok=True)
def longest(v):
 idx=np.flatnonzero(np.diff(np.r_[False,v,False]));return int((idx[1::2]-idx[::2]).max()) if len(idx) else 0
def rawstats(path):
 a=np.load(path);mask=a['keep']&a['completed'];e=a['pose_error'][mask];truth=a['truth'][mask];heading=np.degrees(abs(e[:,2]));lat=-np.sin(truth[:,2])*e[:,0]+np.cos(truth[:,2])*e[:,1];row=json.loads(path.with_suffix('.json').read_text())['row'];row.update(heading_abs_p95_deg=float(np.quantile(heading,.95)),lateral_rmse_m=float(np.sqrt(np.mean(lat*lat))),heading_abs_worst_deg=float(heading.max()),longest_bad5_samples=longest(heading>5),eval_mask='t>=30 and completed')
 applied=(a['s_status']=='applied')&mask;pre=np.degrees(abs((a['truth'][:,2]-a['post_range_state'][:,2]+np.pi)%(2*np.pi)-np.pi));post=np.degrees(abs(a['pose_error'][:,2]));row['s_accepted_count']=int(applied.sum());row['s_harmful_accepted_count']=int((applied&(post>pre)).sum());row['s_harmful_accepted_fraction']=float(np.mean(post[applied]>pre[applied])) if applied.any() else None;row['harm_definition']='absolute circular heading error increased after accepted s; not a causal production verdict'
 if 'q_good_5deg' in a:
  abst=(a['s_status']=='reliability_abstained')&mask;row['reliability_abstention_fraction']=float(abst[mask].mean());row['reliability_outage_longest_samples']=longest(abst);row['q_mean']=float(np.mean(a['q_good_5deg'][mask]));row['R_multiplier_mean']=float(np.mean(a['R_multiplier'][mask]));row['availability_fraction']=float(np.mean(a['rf_available'][mask]))
 return row
def main():
 start=time.time();files=sorted((J/'TRACES/main').glob('*.npz'))+sorted((J/'TRACES/E').glob('*.npz'));assert len(files)==5250
 with concurrent.futures.ProcessPoolExecutor(max_workers=24) as ex:rows=list(ex.map(rawstats,files,chunksize=8))
 df=pd.DataFrame(rows);assert not df.duplicated(['case','drift','seed','arm']).any();assert len(df)==7*3*50*5;df.to_csv(OUT/'ALL_RUN_METRICS.csv',index=False);metrics=['heading_rmse_deg','pos_rmse_m','lateral_rmse_m','heading_abs_p95_deg','nees_mean','pose_coverage','heading_coverage','nees_lower_fraction','nees_upper_fraction','s_nis_pregate','s_nis_accepted','s_reject_rate','s_harmful_accepted_fraction'];summary=df.groupby(['case','drift','arm'])[metrics].mean().reset_index();summary.to_csv(OUT/'CASE_DRIFT_ARM.csv',index=False);summary2=df.groupby(['arm'])[metrics].mean().reset_index();summary2.to_csv(OUT/'ARM_MEAN_SEED_METRICS.csv',index=False);paired=[];rng=np.random.default_rng(20261010)
 for (case,d),g in df.groupby(['case','drift']):
  for a,b in [('B','A'),('C','B'),('D','C'),('E','D'),('E','B')]:
   ga=g[g.arm==a].set_index('seed');gb=g[g.arm==b].set_index('seed');assert set(ga.index)==set(gb.index);ga=ga.sort_index();gb=gb.sort_index()
   for m in ['heading_rmse_deg','pos_rmse_m','nees_mean','pose_coverage']:
    v=(ga[m]-gb[m]).to_numpy();boot=v[rng.integers(0,len(v),(1000,len(v)))].mean(axis=1);paired.append({'case':case,'drift':d,'contrast':a+' minus '+b,'metric':m,'n_seed':len(v),'difference_mean':float(v.mean()),'ci_low':float(np.quantile(boot,.025)),'ci_high':float(np.quantile(boot,.975))})
 pd.DataFrame(paired).to_csv(OUT/'PAIRED_SEED_BOOTSTRAP.csv',index=False)
 # Passive residual intervals cluster repeated headings by station, not independent channel rows.
 f=pd.read_csv(J/'OUTPUT/01_FEATURES.csv');labels=pd.read_csv(J/'OUTPUT/02_LABELS_EVAL_ONLY.csv');z=f.merge(labels,on=['case','route','pose_id'],validate='one_to_one');z['distance_bin']=pd.cut(z.true_distance_m,[0,5,10,np.inf],right=False).astype(str);ci=[]
 for (case,bin),g in z.groupby(['case','distance_bin']):
  for m in ['e_s','e_MP','e_range']:
   st=g.assign(v=g[m],v2=g[m]**2).groupby('station_group').agg(n=('v','size'),s=('v','sum'),s2=('v2','sum'));idx=rng.integers(0,len(st),(1000,len(st)));n=st.n.to_numpy()[idx].sum(axis=1);mean=st.s.to_numpy()[idx].sum(axis=1)/n;var=st.s2.to_numpy()[idx].sum(axis=1)/n-mean*mean;rms=np.sqrt(st.s2.to_numpy()[idx].sum(axis=1)/n)
   ci.append({'case':case,'distance_bin':bin,'error':m,'n':len(g),'station_groups':len(st),'mean':g[m].mean(),'variance_ddof0':g[m].var(ddof=0),'rms':np.sqrt(np.mean(g[m]**2)),'mean_ci_low':np.quantile(mean,.025),'mean_ci_high':np.quantile(mean,.975),'variance_ci_low':np.quantile(var,.025),'variance_ci_high':np.quantile(var,.975),'rms_ci_low':np.quantile(rms,.025),'rms_ci_high':np.quantile(rms,.975),'descriptive_only':len(g)<20,'bootstrap':'1000 station resamples; same corridor'})
 pd.DataFrame(ci).to_csv(OUT/'DISTANCE_STATION_CI.csv',index=False)
 # Gain invariance of registered normalized P1/P4 with epsilon AFTER normalization.
 inv=[]
 for case in f.case.unique():
  a=np.load(J/'FEATURES_V2'/f'CIR_AMPLITUDE_{case}.npz');ff=f[f.case==case].head(20)
  for i,rr in ff.iterrows():
   k=int(rr.pose_id);tap=int(rr.tap);powers=a['amplitude'][k,tap:tap+16,:]**2;values=[]
   for gain in [1e-8,1,1e8]:
    q=powers*gain;q=q/q.sum(axis=0);q=np.maximum(q,1e-12);q=q/q.sum(axis=0);m=q.mean(axis=1);values.append([.5*np.sum(q[:,0]*np.log(q[:,0]/m))+.5*np.sum(q[:,1]*np.log(q[:,1]/m)),abs(q[:,0]-q[:,1]).sum()])
   inv.append(float(np.ptp(np.array(values),axis=0).max()))
 # Source preservation check on exact bytes from pinned archive.
 src=json.loads((J/'SOURCE_MANIFEST.json').read_text());source_ok=True
 for rel,h in src['sha256'].items():
  if isinstance(h,str) and len(h)==64:
   p=J/rel.replace('\\','/');source_ok&=p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==h
 checks={'run_keys_exact':True,'runs':len(df),'failed':int(df.error.fillna('').ne('').sum()),'feature_gain_invariance_max':max(inv),'feature_gain_tolerance':1e-12,'source_bytes_unchanged':source_ok,'time_samples_not_used_as_seed_bootstrap_units':True,'same_corridor_generalization_not_proven':True};(OUT/'CHECKS.json').write_text(json.dumps(checks,indent=2))
 # Plot paired distribution and route calibration from stored predictions.
 fig,axes=plt.subplots(1,2,figsize=(10,4))
 for arm in ['A','B','C','D','E']:
  gg=df[df.arm==arm];axes[0].scatter(np.full(len(gg),ord(arm)-65)+rng.normal(0,.035,len(gg)),gg.heading_rmse_deg,s=2,alpha=.12);axes[1].scatter(np.full(len(gg),ord(arm)-65)+rng.normal(0,.035,len(gg)),gg.nees_mean,s=2,alpha=.12)
 for ax in axes:ax.set_xticks(range(5),list('ABCDE'));ax.grid(alpha=.2)
 axes[0].set_ylabel('Heading RMSE (degree), one dot per seed/case/drift');axes[1].set_ylabel('Pose NEES, seed means (3 DOF)');axes[1].set_yscale('log');fig.tight_layout();fig.savefig(OUT/'FILTER_SEED_DISTRIBUTIONS.png',dpi=160);plt.close(fig)
 fig,axes=plt.subplots(1,3,figsize=(12,4));cal=[]
 for ax,route in zip(axes,['R2','R4','R5']):
  pred=pd.read_csv(J/'RELIABILITY'/f'{route}_HELD_OUT_PREDICTIONS.csv.gz');q=pred.q_DPK;y=pred.correct_5deg.astype(int);idx=np.minimum((q*10).astype(int),9)
  for b,g in pred.assign(q=q,y=y,bin=idx).groupby('bin'):
   cal.append({'route':route,'bin':int(b),'n':len(g),'q_mean':g.q.mean(),'correct_fraction':g.y.mean()})
  cc=pd.DataFrame([r for r in cal if r['route']==route]);ax.plot(cc.q_mean,cc.correct_fraction,'o-');ax.plot([0,1],[0,1],'k--');ax.set_title(route);ax.set_xlim(0,1);ax.set_ylim(0,1);ax.set_xlabel('Held-out DPK probability');ax.set_ylabel('Observed correct <=5 degree')
 pd.DataFrame(cal).to_csv(OUT/'CALIBRATION_BINS.csv',index=False);fig.tight_layout();fig.savefig(OUT/'HELD_OUT_CALIBRATION.png',dpi=160);plt.close(fig)
 (OUT/'STATUS.json').write_text(json.dumps({'state':'completed','seconds':time.time()-start,'checks':checks},indent=2));print('completed analysis',json.dumps(checks),flush=True)
if __name__=='__main__':main()


