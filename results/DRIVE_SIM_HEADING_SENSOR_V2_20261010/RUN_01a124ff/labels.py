from pathlib import Path
import sys,json,time,concurrent.futures
import numpy as np,pandas as pd
import simulate as S
J=Path('/job');GRID=np.radians(np.arange(-180,180.001,.25))
FEAT=pd.read_csv(J/'FEATURES_V2/01_FEATURES.csv').set_index(['case','pose_id'])
def inverse(x,P,case,z):
 c=S.BYCASE[case];x=np.atleast_2d(x);P=np.atleast_3d(P) if np.ndim(P)<3 else P;z=np.atleast_1d(z)
 curves=S.s_model(S.LUT,c['anchor_xyz'],c['robot_z'],x[:,0,None],x[:,1,None],GRID[None,:],c['mount_deg']);r=curves-z[:,None];cross=(r[:,:-1]*r[:,1:]<=0)&(abs(curves[:,1:]-curves[:,:-1])>1e-14);results=[];allroots=[]
 for k in range(len(x)):
  ix=np.flatnonzero(cross[k]);roots=GRID[ix]-r[k,ix]*(GRID[ix+1]-GRID[ix])/(r[k,ix+1]-r[k,ix]);roots=S.V.wrap(roots)
  if len(roots):roots=np.unique(np.round(roots,12))
  match=bool(len(roots));residual=0.
  if not match:
   j=np.argmin(abs(r[k]));roots=np.array([GRID[j]]);residual=float(abs(r[k,j]));match=residual<=.01
  dif=S.V.wrap(roots-x[k,2]);scores=dif*dif/max(float(P[k,2,2]),1e-300);order=np.argsort(scores);best=order[0];ambiguous=bool(len(order)>1 and abs(S.V.wrap(roots[order[1]]-roots[best]))>np.radians(5) and scores[order[1]]-scores[best]<2)
  results.append((float(roots[best]),not match,ambiguous,int(len(roots)),residual,float(scores[best]),float(scores[order[1]]-scores[best]) if len(order)>1 else np.inf));allroots.append(roots)
 return np.array(results),allroots
def label(task):
 case,d,s=task;path=J/'TRACES/main'/f'{case}_d{d}_s{s}_A_stochastic_unknown.npz';a=np.load(path);valid=a['completed']&a['keep'];ix=np.flatnonzero(valid);x=a['pre_rf_state'][ix];P=a['pre_rf_cov'][ix];ids=a['pose_id'][ix];f=FEAT.loc[[(case,int(i)) for i in ids]].reset_index();z=f.s.to_numpy();inv,roots=inverse(x,P,case,z);c=S.BYCASE[case]
 pred,H=S.s_model(S.LUT,c['anchor_xyz'],c['robot_z'],x[:,0],x[:,1],x[:,2],c['mount_deg'],with_jac=True);R=np.full(len(ix),.09**2);var=np.einsum('ni,nij,nj->n',H,P[:,:3,:3],H)+R;truth=a['truth'][ix];err=np.degrees(abs(S.V.wrap(inv[:,0]-truth[:,2])));available=(inv[:,1]==0)&(inv[:,2]==0)
 f['drift']=d;f['seed']=s;f['time_index']=ix;f['t_s']=a['t'][ix];f['K_distance']=f.range_m;f['K_slope_per_rad']=abs(H[:,2]);f['K_position_variance']=P[:,0,0]+P[:,1,1];f['K_heading_variance']=P[:,2,2];f['K_gyro_wheel_discrepancy']=a['gyro'][ix]-a['wheel_yaw'][ix];f['K_innovation_standardized']=(z-pred)/np.sqrt(var);f['rf_heading_rad']=inv[:,0];f['no_match']=inv[:,1].astype(bool);f['ambiguous']=inv[:,2].astype(bool);f['candidate_count']=inv[:,3].astype(int);f['min_s_residual']=inv[:,4];f['branch_score']=inv[:,5];f['ambiguity_margin']=inv[:,6];f['available']=available
 # Truth and outcome fields are only in this evaluation table, never model columns.
 f['heading_error_deg']=err;f['correct_5deg']=err<=5;f['correct_2deg']=err<=2;f['correct_10deg']=err<=10
 maximum=max(map(len,roots));rr=np.full((len(roots),maximum),np.nan)
 for k,r in enumerate(roots):rr[k,:len(r)]=r
 out=J/'LABELS';out.mkdir(exist_ok=True);base=out/f'{case}_d{d}_s{s}';f.to_parquet(str(base)+'.parquet',index=False);np.savez_compressed(str(base)+'_CANDIDATES.npz',pose_id=ids,time_index=ix,heading_roots_rad=rr,selected_heading_rad=inv[:,0],no_match=inv[:,1],ambiguous=inv[:,2],pre_rf_state=x,pre_rf_cov=P,heading_error_deg_eval_only=err)
 return {'case':case,'drift':d,'seed':s,'n':len(f),'available':int(available.sum()),'bad5_available':int(((err>5)&available).sum()),'no_match':int(f.no_match.sum()),'ambiguous':int(f.ambiguous.sum()),'missing_prior_pose_ids':int(len(FEAT.loc[case])-len(np.unique(ids)))}
if __name__=='__main__':
 start=time.time();plan=json.loads((J/'PLAN.json').read_text());tasks=[(c,d,s) for c in plan['cases'] for d in range(3) for s in range(50)];rows=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=24) as ex:
  for r in ex.map(label,tasks,chunksize=1):
   rows.append(r)
   if len(rows)%50==0:print('labels',len(rows),'/',len(tasks),round(time.time()-start),flush=True)
 pd.DataFrame(rows).to_csv(J/'OUTPUT/HEADING_LABEL_COUNTS.csv',index=False);(J/'OUTPUT/LABEL_STATUS.json').write_text(json.dumps({'state':'completed','files':len(rows),'rows':sum(r['n'] for r in rows),'seconds':time.time()-start,'truth_policy':'outcomes only; selected roots use RF-disabled pre-RF estimate and covariance','prior_unavailable_RF_poses':'not labeled as operational; offline features remain available'},indent=2));print('completed labels',len(rows),flush=True)
