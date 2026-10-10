from pathlib import Path
import json,time,concurrent.futures
import numpy as np,pandas as pd
import simulate as S
J=Path('/job');OUT=J/'PROBES';OUT.mkdir(exist_ok=True)
def blocks(case):
 rows=json.loads((S.B/case/'SAMPLES.json').read_text());groups=[];current=[]
 for r in rows:
  key=(r['x'],r['y'])
  if current and key!=(current[-1]['x'],current[-1]['y']):groups.append(current);current=[]
  current.append(r)
 if current:groups.append(current)
 return [g for g in groups if len(g)>=5]
def run(task):
 case,d,seed=task;c=S.BYCASE[case];a=np.load(J/'TRACES/main'/f'{case}_d{d}_s{seed}_A_stochastic_unknown.npz');obs=np.load(J/'OBS'/f'{case}_full.npz');rows=[]
 for gi,g in enumerate(blocks(case)):
  ids=np.array([g[i]['pose_id'] for i in [0,2,4]]);ix=np.flatnonzero((a['pose_id']==ids[0])&a['keep']&a['completed'])
  if not len(ix):rows.append({'case':case,'route':case[:2],'station':gi,'drift':d,'seed':seed,'status':'NO_EVALUATION_PRIOR','n_angles':0});continue
  k=int(ix[0]);x=a['pre_rf_state'][k];P=a['pre_rf_cov'][k];delta=S.V.wrap(np.radians(np.array([g[i]['yaw_body_deg'] for i in [0,2,4]])-g[0]['yaw_body_deg']));z=obs['s'][ids];h,H=S.s_model(S.LUT,c['anchor_xyz'],c['robot_z'],x[0],x[1],x[2]+delta,c['mount_deg'],with_jac=True);r=z-h;slopes=H[:,2];pv=P[2,2]
  for n in [1,2,3]:
   rr=r[:n];hh=slopes[:n];cor=float(np.sum(hh*rr)/(.09**2/pv+np.sum(hh**2)));res=rr-hh*cor;err=abs(np.degrees(S.V.wrap(x[2]+cor-np.radians(g[0]['yaw_body_deg']))));influences=[]
   if n>1:
    for j in range(n):
     mask=np.arange(n)!=j;lo=float(np.sum(hh[mask]*rr[mask])/(.09**2/pv+np.sum(hh[mask]**2)));influences.append(abs(np.degrees(cor-lo)))
   rows.append({'case':case,'route':case[:2],'station':gi,'drift':d,'seed':seed,'status':'OFFLINE_DIAGONAL_SCORE_ONLY','n_angles':n,'pose_ids':json.dumps(ids[:n].tolist()),'scheduled_yaw_offsets_deg':json.dumps(np.degrees(delta[:n]).tolist()),'correction_deg':np.degrees(cor),'heading_error_deg_eval_only':err,'bad5_eval_only':err>5,'shape_residual_squared':float(res@res),'worst_residual':float(abs(res).max()),'slope_span_per_rad':float(np.ptp(hh)),'point_influence_max_deg':max(influences) if influences else None,'residual_vector':json.dumps(res.tolist()),'pre_rf_state':json.dumps(x.tolist()),'prior_heading_variance':pv,'Sigma_probe_validated':False,'probe_time_s':None,'operational_body_rotation_model':'NOT_VERIFIED: recorded RF angle schedule, no sensor-noisy probe replay'})
 return rows
if __name__=='__main__':
 start=time.time();tasks=[(c,d,s) for c in S.BYCASE for d in range(3) for s in range(50)];rows=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=24) as ex:
  for r in ex.map(run,tasks):rows.extend(r)
 df=pd.DataFrame(rows);df.to_csv(OUT/'07_PROBE_STATIONS.csv.gz',index=False);good=df[df.n_angles>0];summary=good.groupby(['case','drift','n_angles']).agg(rows=('seed','size'),stations=('station','nunique'),mean_bad5=('bad5_eval_only','mean'),heading_rmse_deg=('heading_error_deg_eval_only',lambda x:np.sqrt(np.mean(x*x))),mean_shape_residual_squared=('shape_residual_squared','mean')).reset_index();summary.to_csv(OUT/'08_PROBE_COMPARISONS.csv',index=False)
 pairs=good.pivot(index=['case','route','station','drift','seed'],columns='n_angles',values='heading_error_deg_eval_only').dropna();pairs['delta_2_minus_1']=pairs[2]-pairs[1];pairs['delta_3_minus_1']=pairs[3]-pairs[1];pairs.to_csv(OUT/'PAIRED_DIAGNOSTIC.csv.gz');(OUT/'STATUS.json').write_text(json.dumps({'state':'DIAGNOSTIC_COMPLETED_PROBABILITY_BLOCKED','rows':len(df),'usable_rows':len(good),'missing_prior':int((df.n_angles==0).sum()),'seconds':time.time()-start,'blockers':['Sigma_probe temporal/offdiagonal covariance not independently validated','probe angular-speed/time contract and noisy body-rotation control absent','probability Brier/uplift and filter F not run; diagonal score is not probability'],'no_new_RF':True,'no_truth_branch_selection':True},indent=2));print('completed probes',len(df),flush=True)
