from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent
R=BASE/'release'; pol=json.loads((R/'POLICIES.json').read_text()); tol=2e-8
wrap=lambda x:(x+np.pi)%(2*np.pi)-np.pi
reports=[]
for ch in ['los','full']:
 for lv in ['B0','L0','L1','L2']:
  c=np.load(BASE/f'cache/pol/experiments/POL_FGO_CORR_20261106_v1/outputs/controls_{ch}_{lv}.npz')
  a=np.load(R/f'{ch}_{lv}_trajectories.npz'); X=a['X']; P=a['P']; prior=a['prior_X']; step=a['step']; nis=a['nis']; accepted=a['accepted'];score=a['score']
  n,m=X.shape[:2]
  x0=np.r_[c['initial_pose'],0.];P0=np.diag(np.array([.1,.1,np.deg2rad(5),np.deg2rad(.1)])**2)
  xp=np.empty_like(X);pp=np.empty_like(P);xp[0]=x0;pp[0]=P0
  prev=X[:-1];ds=c['ds_odom'][1:,None];dt=c['dt_s'][1:,None];ang=c['dtheta_gyro'][1:,None]-prev[:,:,3]*dt
  sm=abs(ang)<1e-4; half=np.where(sm,1,ang/2)
  sinc=np.where(sm,1-ang**2/24+ang**4/1920-ang**6/322560,np.sin(half)/half)
  dc=np.where(sm,-ang/12+ang**3/480-ang**5/53760,(half*np.cos(half)-np.sin(half))/(2*half**2))
  phi=prev[:,:,2]+ang/2;co=np.cos(phi);si=np.sin(phi)
  dx=ds*sinc*co;dy=ds*sinc*si;vx=ds*(dc*co-sinc*si/2);vy=ds*(dc*si+sinc*co/2)
  xp[1:]=prev;xp[1:,:,0]+=dx;xp[1:,:,1]+=dy;xp[1:,:,2]=wrap(prev[:,:,2]+ang)
  F=np.broadcast_to(np.eye(4),P[1:].shape).copy()
  F[:,:,0,2]=-dy;F[:,:,1,2]=dx;F[:,:,0,3]=-dt*vx;F[:,:,1,3]=-dt*vy;F[:,:,2,3]=-dt
  G0=np.stack([sinc*co,sinc*si,np.zeros_like(co),np.zeros_like(co)],axis=2)
  G1=np.stack([vx,vy,np.ones_like(co),np.zeros_like(co)],axis=2)
  pp[1:]=F@P[:-1]@np.swapaxes(F,-1,-2)+2e-5*abs(ds)[:,:,None,None]*G0[:,:,:,None]*G0[:,:,None,:]+np.deg2rad(.015)**2*dt[:,:,None,None]*G1[:,:,:,None]*G1[:,:,None,:]
  de=abs(xp-prior);de[:,:,2]=abs(wrap(xp[:,:,2]-prior[:,:,2]));maxprior=float(de.max());assert maxprior<1e-10,(ch,lv,maxprior)
  proposed=prior+step;proposed[:,:,2]=wrap(proposed[:,:,2]);expected=np.where(accepted[:,:,None],proposed,prior)
  delta=expected-X;delta[:,:,2]=wrap(delta[:,:,2]);maxx=float(abs(delta).max());assert maxx<1e-10,(ch,lv,maxx)
  positive=nis>1e-20
  update=step[:,:,:,None]*step[:,:,None,:]/np.where(positive,nis,1)[:,:,None,None]
  post=pp-np.where(accepted[:,:,None,None],update,0)
  maxp=float(abs(post-P)[positive].max());assert maxp<tol,(ch,lv,maxp)
  decisions=np.zeros_like(accepted)
  for j,p in enumerate(pol):
   eligible=nis[:,j]<=6.6348966010212145
   if p['op']=='all':decisions[:,j]=eligible
   elif p['op']=='none':pass
   elif p['op']=='exists':decisions[:,j]=eligible&np.isfinite(score[:,j])
   elif p['op']=='le':decisions[:,j]=eligible&np.isfinite(score[:,j])&(score[:,j]<=p['threshold'])
   elif p['op']=='ge':decisions[:,j]=eligible&np.isfinite(score[:,j])&(score[:,j]>=p['threshold'])
  assert np.array_equal(decisions,accepted)
  metr=pd.read_csv(R/f'{ch}_{lv}_metrics.csv')
  h=wrap(X[:,:,2]-a['truth'][:,None,2])*180/np.pi;xy=np.linalg.norm(X[:,:,:2]-a['truth'][:,None,:2],axis=2)
  md=0.
  for window,mask in [('all_eval',a['t']>=40),('development',(a['t']>=40)&(a['t']<120)),('late_test',a['t']>=140)]:
   mm=metr[metr.window==window].set_index('id').loc[a['policies']]
   md=max(md,float(abs(np.sqrt(np.mean(h[mask]**2,axis=0))-mm.heading_rmse_deg.to_numpy()).max()),float(abs(np.sqrt(np.mean(xy[mask]**2,axis=0))-mm.xy_rmse_m.to_numpy()).max()))
  assert md<1e-10
  reports.append(dict(channel=ch,level=lv,n_trajectory=m,n_steps=n*m,prior_x_max_error=maxprior,selected_x_max_error=maxx,covariance_rank1_max_error=maxp,metric_max_error=md,gate_and_feature_rule_disagreements=0,very_small_nis_skipped_covariance_rows=int((~positive).sum())))
print(json.dumps(reports,indent=2))
(R/'LOCAL_ARITHMETIC_AUDIT.json').write_text(json.dumps(dict(status='PASS',scope='Separate vectorized prediction/Joseph-rank1 check and all decisions; same author, not external scientific review',source_run=42466288321,records=reports),indent=2))
