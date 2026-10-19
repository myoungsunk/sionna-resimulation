from pathlib import Path
import numpy as np,pandas as pd,json,sys
ROOT=Path(sys.argv[1]);OUT=Path(sys.argv[2]);OUT.mkdir(exist_ok=True)
q=pd.read_csv(ROOT/'OOF_PARAMETERS.csv.gz');records=[];episodes=[];origins=[];gate=[]
def wrap(x):return np.arctan2(np.sin(x),np.cos(x))
def corr(a,b):return float(np.corrcoef(a,b)[0,1]) if len(a)>3 and min(np.std(a),np.std(b))>1e-12 else None
for f in sorted((ROOT/'traces').glob('*.npz')):
 cid,label=f.stem.rsplit('_',1)
 with np.load(f,allow_pickle=False) as a:d={k:a[k] for k in a.files}
 frame=q[(q['case']==cid)&(q.channel=='full')].set_index('pose_id').loc[d['pose_id']]
 truth=d['truth_for_offline_scoring_only'];t=d['t'];ev=t>=30;names=list(d['names'])
 z=d['observations'];htrue=z-frame[['e_r','e_s']].to_numpy()
 for method in ['JOINT4','POWER1','POWER_MEMORY','POWER_MEMORY_NO_CROSS','POWER_NO_GATE','POWER_ITERATED']:
  j=names.index(method);e0=wrap(d['prior'][:,j,2]-truth[:,2]);e1=wrap(d['state'][:,j,2]-truth[:,2]);sig=np.sqrt(d['cov'][:,j,2,2]);B=d['B'][:,j];u=d['prior'][:,j,4:];beta=np.einsum('nij,nj->ni',B,u)
  residual=z-htrue-d['mean'][:,j];priorgeom=htrue-d['h'][:,j]
  truewhite=residual-beta
  innovation=residual+priorgeom-beta
  closure=float(np.max(abs(innovation-d['innovation'][:,j])))
  W=np.linalg.solve(np.linalg.cholesky(d['S'][:,j]),innovation[...,None])[...,0]
  K=d['K'][:,j,2,:];rr=K*residual;pp=K*priorgeom;bb=-K*beta;delta=np.sum(rr+pp+bb,axis=1);acc=d['accepted'][:,j]
  actualdelta=wrap(d['state'][:,j,2]-d['prior'][:,j,2]);cl2=float(np.max(abs(delta[acc]-actualdelta[acc]))) if acc.any() else None
  if method=='POWER_ITERATED':cl2=None  # Saved K describes first linearization, not iterated final step.
  ne=e1*e1/(sig*sig)
  rec={'case':cid,'bias':label,'method':method,'n':int(ev.sum()),'innovation_closure':closure,'accepted_update_closure':cl2,'mean_nis_all':float(d['nis'][ev,j].mean()),'nis95_all':float(np.mean(d['nis'][ev,j]<=5.991464547)), 'accepted_fraction':float(acc[ev].mean()),'whitened_innovation_lag1_r':corr(W[:-1,0][ev[1:]],W[1:,0][ev[1:]]),'whitened_innovation_lag1_s':corr(W[:-1,1][ev[1:]],W[1:,1][ev[1:]]),'prior_heading_rmse_deg':float(np.degrees(np.sqrt(np.mean(e0[ev]**2)))),'post_heading_rmse_deg':float(np.degrees(np.sqrt(np.mean(e1[ev]**2)))),'signed_mean_deg':float(np.degrees(e1[ev].mean())),'mean_heading_nees':float(ne[ev].mean()),'white_residual_rmse_r':float(np.sqrt(np.mean(truewhite[ev,0]**2))),'white_residual_rmse_s':float(np.sqrt(np.mean(truewhite[ev,1]**2))),'unmodeled_residual_rmse_r':float(np.sqrt(np.mean(residual[ev,0]**2))),'unmodeled_residual_rmse_s':float(np.sqrt(np.mean(residual[ev,1]**2))),'beta_actual_corr_r':corr(beta[ev,0],residual[ev,0]),'beta_actual_corr_s':corr(beta[ev,1],residual[ev,1]),'beta_signed_r':float(beta[ev,0].mean()),'actual_signed_r':float(residual[ev,0].mean()),'beta_signed_s':float(beta[ev,1].mean()),'actual_signed_s':float(residual[ev,1].mean())}
  records.append(rec)
  # Counterfactual single joint update at saved prior: diagnostic, never used online.
  candidate_error=wrap(e0+delta);helpful=candidate_error**2<e0**2
  gate.append({'case':cid,'bias':label,'method':method,'rejected':int(np.sum(ev&~acc)),'rejected_but_helpful':int(np.sum(ev&~acc&helpful)),'accepted':int(np.sum(ev&acc)),'accepted_but_harmful':int(np.sum(ev&acc&~helpful)),'note':'iterated uses first proposed joint update for this diagnostic'})
  if label!='B0':continue
  # Locate all persistent large/overconfident episodes for audit, not intervention selection.
  bad=(abs(np.degrees(e1))>3)&(ne>3.84145882);starts=[];a0=None
  for k,yes in enumerate(np.r_[bad,False]):
   if yes and a0 is None:a0=k
   elif not yes and a0 is not None:
    if k-a0>=5:starts.append((a0,k))
    a0=None
  for a0,b0 in starts:
   sl=slice(a0,b0);rho=float(frame.rho_m.iloc[a0]);eprec={'case':cid,'method':method,'index_start':a0,'index_end':b0,'x':float(truth[a0,0]),'y':float(truth[a0,1]),'yaw_deg':float(np.degrees(truth[a0,2])),'rho_m':rho,'gpsi':float(frame.gpsi.iloc[a0]),'detector_s_span':float(frame.detector_s_span.iloc[a0]),'duration_s':float(t[min(b0,len(t)-1)]-t[a0]),'signed_mean_deg':float(np.degrees(e1[sl].mean())),'rmse_deg':float(np.degrees(np.sqrt(np.mean(e1[sl]**2)))),'sigma_rms_deg':float(np.degrees(np.sqrt(np.mean(sig[sl]**2)))),'nis_median':float(np.median(d['nis'][sl,j])),'accepted_fraction':float(acc[sl].mean()),'gyro_bias_mean_dps':float(np.degrees(d['state'][sl,j,3].mean())),'beta_s_mean':float(beta[sl,1].mean()),'true_residual_s_mean':float(residual[sl,1].mean())}
   episodes.append(eprec)
  # k-by-k additive contributions to the actual joint update, not total trajectory causes.
  for component,v in [('measurement_range',rr[:,0]),('measurement_s',rr[:,1]),('prior_geometry_range',pp[:,0]),('prior_geometry_s',pp[:,1]),('memory_range',bb[:,0]),('memory_s',bb[:,1])]:
   values=np.where(acc,v,0.)[ev]
   origins.append({'case':cid,'method':method,'component':component,'signed_sum_deg':float(np.degrees(values.sum())),'rms_deg':float(np.degrees(np.sqrt(np.mean(values**2)))),'note':'algebraic sum at saved gains, not deletion-intervention effect'})
for name,rows in [('TEMPORAL_MODEL_DIAGNOSTICS.csv',records),('PHYSICAL_ERROR_EPISODES.csv',episodes),('SIGNED_HEADING_UPDATE_COMPONENTS.csv',origins),('GATE_HELPFUL_HARMFUL.csv',gate)]:pd.DataFrame(rows).to_csv(OUT/name,index=False)
sel=[r for r in records if r['bias']=='B0' and r['case'] in ['R2_aA_m45','R5_aA_m0'] and r['method'] in ['POWER1','POWER_MEMORY']]
print('DEEP_TIME_DIAGNOSTICS',json.dumps(sel),flush=True)
print('DEEP_EPISODES',json.dumps([r for r in episodes if r['method'] in ['POWER1','POWER_MEMORY'] and r['case'] in ['R2_aA_m0','R2_aA_m45','R5_aA_m0']])[:20000],flush=True)
print('DEEP_CLOSURE',max(r['innovation_closure'] for r in records),max(r['accepted_update_closure'] or 0 for r in records),flush=True)
