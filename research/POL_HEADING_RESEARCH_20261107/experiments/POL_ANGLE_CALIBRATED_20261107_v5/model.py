import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import importlib.util,json,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp,expit
from scipy.optimize import minimize
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('angle_analytic',BASE.parent/'POL_ANGLE_UNCERTAINTY_20261107_v4b/run_angle.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
e=base.e;CAL_END=30.;EVAL_START=40.
def dump(name,x):(BASE/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def roots(mu,z):
 r=base.inverse_roots(mu,z)
 if not r:return []
 xx=np.tile(mu,(len(r),1));xx[:,2]=[x[0] for x in r];_,H=base.old.model(xx)
 return [(angle,Ho,float(abs(h[2]))) for (angle,Ho),h in zip(r,H)]
def calibration_records(datasets):
 records=[];unsupported=0;times=[]
 for ch,d in datasets.items():
  for k in np.flatnonzero(d['t_s']<CAL_END):
   truth=d['truth_for_offline_scoring_only'][k];mu=np.r_[truth,0.];r=roots(mu,d['z_s'][k]);times.append(float(d['t_s'][k]))
   if not r:unsupported+=1;continue
   records.append(dict(channel=ch,k=int(k),t=float(d['t_s'][k]),errors=[float(e.wrap(a-truth[2])) for a,H,g in r],slope=[g for a,H,g in r]))
 return records,unsupported,times

def sigma(slope,p):
 g=np.clip(np.asarray(slope),p['slope_min'],p['slope_max']);q=np.log((g+p['slope_offset'])/p['slope_reference'])
 return np.clip(np.exp(p['a']+p['b']*q),np.deg2rad(.05),np.pi)
def fit(datasets):
 records,unsupported,times=calibration_records(datasets);assert len(records)>=30
 slopes=np.concatenate([r['slope'] for r in records]);offset=float(np.quantile(slopes,.05)/2);reference=float(np.median(slopes)+offset)
 n=len(records);M=max(len(r['errors']) for r in records);err=np.zeros((n,M));g=np.full((n,M),reference-offset);mask=np.zeros((n,M),bool);counts=[]
 for i,r in enumerate(records):
  count=len(r['errors']);err[i,:count]=r['errors'];g[i,:count]=r['slope'];mask[i,:count]=True;counts.append(count)
 q=np.log((g+offset)/reference)
 def objective(x):
  sd=np.clip(np.exp(x[0]+x[1]*q),np.deg2rad(.05),np.pi);v=err[:,:,None]+2*np.pi*np.arange(-5,6)
  logs=logsumexp(-.5*(v/sd[:,:,None])**2-np.log(sd[:,:,None])- .5*np.log(2*np.pi),axis=2);logs[~mask]=-np.inf
  lp=logsumexp(logs,axis=1)-np.log(counts);eps=expit(x[2]);return float(-np.sum(np.logaddexp(np.log1p(-eps)+lp,np.log(eps)-np.log(2*np.pi))))
 starts=[(5.,.1),(15.,.2),(45.,.4)];solutions=[]
 for deg,eps in starts:
  result=minimize(objective,[np.log(np.deg2rad(deg)),-1.,np.log(eps/(1-eps))],method='L-BFGS-B',bounds=[(np.log(np.deg2rad(.05)),np.log(np.deg2rad(90))),(-2.,0.),(-14.,14.)],options={'ftol':1e-12,'gtol':1e-7,'maxiter':500})
  solutions.append(dict(x=result.x.tolist(),nll=float(result.fun),success=bool(result.success),message=str(result.message)))
 best=min(solutions,key=lambda r:r['nll']);assert best['success'],best
 a,b,logit=best['x'];p=dict(a=a,b=b,outlier_probability=float(expit(logit)),slope_offset=offset,slope_reference=reference,slope_min=float(slopes.min()),slope_max=float(slopes.max()))
 near=np.array([min(r['errors'],key=abs) for r in records]);sd=sigma(slopes,p)
 info=dict(supported=len(records),unsupported=unsupported,calibration_samples=len(times),max_training_time=max(times),solutions=solutions,sigma_range_deg=np.rad2deg([sd.min(),sd.max()]).tolist(),nearest_branch_diagnostic_only=dict(rmse_deg=float(np.sqrt(np.mean(np.rad2deg(near)**2))),mean_deg=float(np.rad2deg(near.mean())),std_deg=float(np.rad2deg(near.std()))),note='All roots in fitting likelihood; nearest branch used only in descriptive diagnostic. GT XY in calibration, predicted XY in runtime.')
 return p,info,records

def measurement(comps,z,p,tol=1e-8,maxiter=200,rootfun=roots):
 parts=[];unsupported=0;sigmas=[];eps=p['outlier_probability']
 for w,sc,mu,P,basin in comps:
  rts=rootfun(mu,z)
  if not rts:parts.append((np.log(w)-np.log(2*np.pi),0,mu,P));unsupported+=1;continue
  # Uniform outlier branch preserves the prior; no nearest-angle forcing.
  parts.append((np.log(w)+np.log(eps)-np.log(2*np.pi),0,mu,P))
  for angle,Ho,slope in rts:
   sd=float(sigma(slope,p));sigmas.append(sd);H=np.array([Ho[0],Ho[1],1.,0.]);PH=P@H;S=float(H@PH+sd*sd)
   lp,g,c=base.wrapped_stats(e.wrap(angle-mu[2]),S);x=mu-PH*g;x[2]=e.wrap(x[2]);cov=P+np.outer(PH,PH)*c;cov=(cov+cov.T)/2;assert np.linalg.eigvalsh(cov).min()>0
   parts.append((np.log(w)+np.log1p(-eps)-np.log(len(rts))+lp,0,x,cov))
 norm=logsumexp([a[0] for a in parts]);weights=np.exp(np.array([a[0] for a in parts])-norm);keep=weights>=1e-12;lost=float(weights[~keep].sum());mass=weights[keep].sum()
 comps=[(float(w/mass),sc,x,P,0) for w,(lp,sc,x,P),yes in zip(weights,parts,keep) if yes]
 comps,di=base.reduce_mixture(comps,tol,maxiter);di.update(discarded_mass=lost,unsupported_components=unsupported,sigma_min_deg=float(np.rad2deg(min(sigmas))) if sigmas else 0.,sigma_max_deg=float(np.rad2deg(max(sigmas))) if sigmas else 0.);return comps,di

def run(ctrl,z,x0,mask,p,tol=1e-8,maxiter=200):
 mu,P=e.initial(x0,4);comps=[(1.,0,mu,P,0)];X=[];C=[];dens=[];diagnostics=[]
 for k in range(len(z)):
  if os.getenv('MANAGED_PROCESS_STOP_FILE') and Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('CANCELLED')
  if k:comps=[(w,0,*e.predict_one(x,P,ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k]),b) for w,j,x,P,b in comps]
  di=dict(modes=len(comps),mode_unconverged=False,discarded_mass=0.,unsupported_components=0,sigma_min_deg=0.,sigma_max_deg=0.)
  if mask[k]:comps,di=measurement(comps,z[k],p,tol,maxiter)
  _,x,P=base.moment([(w,x,P) for w,j,x,P,b in comps]);X.append(x);C.append(P);dens.append(base.density(comps,base.TH).astype('float32'));diagnostics.append(di)
 return np.array(X),np.array(C),dict(heading_density=np.array(dens),theta_rad=base.TH,**{key:np.array([d[key] for d in diagnostics]) for key in ['modes','mode_unconverged','discarded_mass','unsupported_components','sigma_min_deg','sigma_max_deg']})
def metrics(X,P,truth,t):
 sel=t>=EVAL_START
 return e.metrics(X[sel],P[sel],truth[sel],np.full(sel.sum(),EVAL_START))
