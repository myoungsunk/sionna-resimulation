import sys, math
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parent
PRIOR=Path('D:/codex/PALO_EXACT_ORACLE_20261107_01')
sys.path.insert(0,str(PRIOR/'source'))
import palo_oracle_closedloop as orig
core,lut,case=orig.load_deps(PRIOR/'inputs')
import r2_bias_replay as frozen
FULL=orig.get_input(PRIOR/'inputs','full'); LOS=orig.get_input(PRIOR/'inputs','los')
assert all(np.array_equal(FULL[k],LOS[k]) for k in ('t_s','pose_id','truth_for_offline_scoring_only'))
T=FULL['t_s']; TRUTH=FULL['truth_for_offline_scoring_only']; Z=FULL['z_s']
CLEAN=np.abs(Z-LOS['z_s']); N=len(T); GATE=orig.GATE
FEATURES=['nis','innovation_abs','Hpsi_abs','Hxy_norm','Pxy_trace','Ppsi','Pxypsi_norm','correction_abs','dr_innov_mean5','dr_innov_std5','dr_heading_diff','dr_xy_diff']
DR_CACHE={}
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def controls(lv):return orig.get_controls(PRIOR/'inputs','full',lv)
def initial(c):return orig.make_initial(c)
def advance(x,P,c,k):
 return (x.copy(),P.copy()) if k==0 else frozen.predict_one(x,P,float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
def dr_reference(lv):
 if lv in DR_CACHE:return DR_CACHE[lv]
 c=controls(lv);x,P=initial(c);xx=[];inn=[]
 for k in range(N):
  x,P=advance(x,P,c,k);xx.append(x.copy());inn.append(float(Z[k]-lut.model(x,case)[0][1]))
 history=np.array([[np.mean(inn[max(0,k-5):k]) if k else 0,np.std(inn[max(0,k-5):k]) if k else 0] for k in range(N)])
 DR_CACHE[lv]=(np.array(xx),history)
 return DR_CACHE[lv]
def error_masks(rate,seed,kind):
 rng=np.random.default_rng(seed); masks=[]
 for _ in range(2):
  u=rng.random(N)
  if kind=='iid':a=u<rate
  else:
   a=np.zeros(N,bool);a[0]=u[0]<rate
   for k in range(1,N):a[k]=(u[k]>=.2) if a[k-1] else (u[k]<rate/(5*(1-rate)))
  masks.append(a)
 return masks
def action(spec,k,f,benefit,gate):
 mode=spec['mode']
 if mode=='dr':return False
 if mode=='s4':return gate
 if mode=='heading':return benefit>1e-12 and (gate or not spec.get('gated',True))
 if mode=='rf':return CLEAN[k]<=spec['tau'] and (gate or not spec.get('gated',True))
 if mode=='random':return bool(spec['schedule'][k])
 if mode=='errors':
  if not gate:return False
  if benefit>1e-12:return not (spec['kind'] in ('fn','both') and spec['fn'][k])
  if benefit< -1e-12:return spec['kind'] in ('fp','both') and bool(spec['fp'][k])
  return False
 if mode=='learned':
  model=spec['model']
  if model['feature']=='never':return False
  if model['feature']=='always':return gate
  v=f[FEATURES.index(model['feature'])]
  return gate and (v<=model['threshold'] if model['direction']=='le' else v>model['threshold'])
 raise ValueError(mode)
def replay(lv,spec,path=None,truth=None,switch=None,feature_output=False):
 truth=TRUTH if truth is None else truth
 c=controls(lv); x,P=initial(c); dr,hist=dr_reference(lv)
 a={k:np.empty(shape) for k,shape in {'X':(N,4),'P':(N,4,4),'prior_X':(N,4),'prior_P':(N,4,4),'candidate_X':(N,4),'candidate_P':(N,4,4),'nis':(N,),'benefit':(N,),'xy_benefit':(N,)}.items()}
 a['accepted']=np.zeros(N,bool)
 if feature_output:a['features']=np.empty((N,len(FEATURES)))
 for k in range(N):
  xm,Pm=advance(x,P,c,k)
  xu,Pu,d=orig.candidate(core,lut,case,xm,Pm,Z[k])
  b=float(abs(wrap(xm[2]-truth[k,2]))-abs(wrap(xu[2]-truth[k,2])))
  bx=float(np.linalg.norm(xm[:2]-truth[k,:2])-np.linalg.norm(xu[:2]-truth[k,:2]))
  f=np.array([d['NIS'],abs(d['innovation'][0]),abs(d['H'][0,2]),np.linalg.norm(d['H'][0,:2]),np.trace(Pm[:2,:2]),Pm[2,2],np.linalg.norm(Pm[:2,2]),abs(wrap(xu[2]-xm[2])),hist[k,0],hist[k,1],abs(wrap(xm[2]-dr[k,2])),np.linalg.norm(xm[:2]-dr[k,:2])])
  use={'mode':'s4'} if switch is not None and T[k]<switch else spec
  yes=action(use,k,f,b,d['NIS']<=GATE)
  x,P=(xu,Pu) if yes else (xm,Pm)
  for key,val in [('X',x),('P',P),('prior_X',xm),('prior_P',Pm),('candidate_X',xu),('candidate_P',Pu),('nis',d['NIS']),('benefit',b),('xy_benefit',bx),('accepted',yes)]:a[key][k]=val
  if feature_output:a['features'][k]=f
 for key in a:assert np.isfinite(a[key]).all(),key
 assert np.linalg.eigvalsh(a['P']).min()>0
 a.update(t=T,truth=truth,pose_id=FULL['pose_id'])
 if path is not None:np.savez_compressed(path,**a)
 return a
def metrics(a,start=40):
 take=T>=start;x=a['X'][take];P=a['P'][take];e=x[:,:3]-a['truth'][take];e[:,2]=wrap(e[:,2]);xy=np.linalg.norm(e[:,:2],axis=1)
 hn=e[:,2]**2/P[:,2,2];xn=np.einsum('ni,ni->n',e[:,:2],np.linalg.solve(P[:,:2,:2],e[:,:2,None])[...,0])
 gate=a['nis']<=GATE;good=a['benefit']>1e-12;bad=a['benefit']< -1e-12;yes=a['accepted'];ev=take
 return dict(n=int(take.sum()),heading_rmse_deg=float(np.rad2deg(np.sqrt(np.mean(e[:,2]**2)))),xy_rmse_m=float(np.sqrt(np.mean(xy**2))),heading_nees=float(hn.mean()),xy_nees=float(xn.mean()),heading_95_coverage=float(np.mean(hn<=3.841458820694124)),xy_95_coverage=float(np.mean(xn<=5.991464547107979)),applied=int(yes[take].sum()),applied_all=int(yes.sum()),beneficial_opportunities=int((gate&good&ev).sum()),harmful_opportunities=int((gate&bad&ev).sum()),false_reject=int((gate&good&~yes&ev).sum()),false_accept=int((gate&bad&yes&ev).sum()),min_cov_eigenvalue=float(np.linalg.eigvalsh(a['P']).min()))
