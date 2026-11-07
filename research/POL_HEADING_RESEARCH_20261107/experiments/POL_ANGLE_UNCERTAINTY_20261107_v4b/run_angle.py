"""Direct angular variance, analytic wrapped-Gaussian update and mixture reduction."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,hashlib,importlib.util
from pathlib import Path
import numpy as np
from scipy.special import logsumexp,ndtr
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('angle_grid',BASE.parent/'POL_ANGLE_UNCERTAINTY_20261107_v4/run_angle.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
e=old.e;PI=old.PI;SIGMA_DEG=old.SIGMA_DEG;SCALES=old.SCALES;TH=old.TH;inverse_roots=old.inverse_roots;moment=old.moment;interact=old.interact

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(name,value):(BASE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def wrapped_stats(r,S):
 """Log wrapped-normal likelihood and log derivatives; all winding moments retained."""
 r=float(e.wrap(r))
 if S>=.5:
  n=np.arange(1,int(np.ceil(np.sqrt(80/S)))+1);a=np.exp(-.5*n*n*S)
  f=1+2*np.sum(a*np.cos(n*r));fp=-2*np.sum(n*a*np.sin(n*r));fpp=-2*np.sum(n*n*a*np.cos(n*r))
  assert f>0
  return np.log(f/(2*np.pi)),fp/f,fpp/f-(fp/f)**2
 J=int(np.ceil((9*np.sqrt(S)+np.pi)/(2*np.pi)));v=r+2*np.pi*np.arange(-J,J+1)
 logs=-.5*v*v/S-.5*np.log(2*np.pi*S);norm=logsumexp(logs);w=np.exp(logs-norm);mean=w@v;var=w@((v-mean)**2)
 return norm,-mean/S,var/S**2-1/S

def reduce_mixture(comps,tol=1e-8,maxiter=200):
 """Continuous circular mode finding; no angular quadrature or fixed45deg merge."""
 weights=np.array([c[0] for c in comps]);mu=np.array([c[2][2] for c in comps]);var=np.array([c[3][2,2] for c in comps])+np.deg2rad(1.)**2
 kappa=1/var;centers=mu.copy()
 # VM approximations only locate basins. Original Gaussian moments are preserved.
 from scipy.special import i0e
 lognorm=np.log(2*np.pi)+np.log(i0e(kappa))+kappa
 for iteration in range(maxiter):
  logq=np.log(weights)[None,:]+kappa[None,:]*np.cos(centers[:,None]-mu[None,:])-lognorm[None,:]
  q=np.exp(logq-logsumexp(logq,axis=1)[:,None])*kappa
  nxt=np.angle(q@np.exp(1j*mu));change=np.max(abs(e.wrap(nxt-centers)));centers=nxt
  if change<tol:break
 groups=[]
 for i,center in enumerate(centers):
  for g in groups:
   if abs(e.wrap(center-centers[g[0]]))<np.deg2rad(.05):g.append(i);break
  else:groups.append([i])
 result=[]
 for basin,g in enumerate(groups):
  for sc in range(6):
   parts=[(comps[i][0],comps[i][2],comps[i][3]) for i in g if comps[i][1]==sc]
   if parts:
    w,x,P=moment(parts);result.append((w,sc,x,P,basin))
 return result,dict(modes=len(groups),mode_iterations=iteration+1,mode_unconverged=bool(change>=tol))

def measurement(comps,z,tol=1e-8,maxiter=200,rootfun=inverse_roots):
 parts=[];unsupported=0
 for w,sc,mu,P,basin in comps:
  roots=rootfun(mu,z)
  if not roots:parts.append((np.log(w)-np.log(2*np.pi),sc,mu,P));unsupported+=1;continue
  for angle,Ho in roots:
   H=np.array([Ho[0],Ho[1],1.,0.]);PH=P@H;S=float(H@PH+SCALES[sc]);r=e.wrap(angle-mu[2]);lp,g,c=wrapped_stats(r,S)
   x=mu-PH*g;x[2]=e.wrap(x[2]);cov=P+np.outer(PH,PH)*c;cov=(cov+cov.T)/2
   assert np.linalg.eigvalsh(cov).min()>0
   parts.append((np.log(w)-np.log(len(roots))+lp,sc,x,cov))
 norm=logsumexp([a[0] for a in parts]);weights=np.exp(np.array([a[0] for a in parts])-norm);keep=weights>=1e-12;discard=float(weights[~keep].sum());mass=weights[keep].sum()
 comps=[(float(w/mass),sc,x,P,0) for w,(lp,sc,x,P),yes in zip(weights,parts,keep) if yes]
 comps,di=reduce_mixture(comps,tol,maxiter);di.update(discarded_mass=discard,unsupported_components=unsupported,prior_components=len(parts));return comps,di

def density(comps,theta):
 # Cell-integrated wrapped Gaussian masses, also valid for sigma much below a cell.
 step=2*np.pi/len(theta);den=np.zeros(len(theta))
 for w,sc,x,P,k in comps:
  sd=np.sqrt(P[2,2]);delta=e.wrap(theta-x[2]);J=int(np.ceil((9*sd+np.pi)/(2*np.pi)))
  for j in range(-J,J+1):
   a=(delta+2*np.pi*j-step/2)/sd;b=a+step/sd
   den+=w*np.where(a>0,ndtr(-a)-ndtr(-b),ndtr(b)-ndtr(a))
 return den/den.sum()

def run(ctrl,z,x0,mask,theta=TH,tol=1e-8,maxiter=200):
 mu,P=e.initial(x0,4);comps=[(float(w),j,mu.copy(),P.copy(),0) for j,w in enumerate(PI)];X=[];C=[];probs=[];dens=[];modes=[];diagnostics=[]
 for k in range(len(z)):
  if os.getenv('MANAGED_PROCESS_STOP_FILE') and Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('CANCELLED')
  if k:
   comps=interact(comps,ctrl['dt_s'][k],True);comps=[(w,j,*e.predict_one(x,P,ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k]),b) for w,j,x,P,b in comps]
  di=dict(modes=len(set(c[4] for c in comps)),mode_iterations=0,mode_unconverged=False,discarded_mass=0.,unsupported_components=0,prior_components=len(comps))
  if mask[k]:comps,di=measurement(comps,z[k],tol,maxiter)
  _,x,P=moment([(w,x,P) for w,j,x,P,b in comps]);X.append(x);C.append(P);pr=np.zeros(6)
  for w,j,x,P,b in comps:pr[j]+=w
  probs.append(pr);dens.append(density(comps,theta).astype('float32'));modes.append(di['modes']);diagnostics.append(di)
 return np.array(X),np.array(C),dict(angular_variance_prob=np.array(probs),sigma_candidates_deg=SIGMA_DEG,heading_density=np.array(dens),heading_modes=np.array(modes),theta_rad=theta,mode_unconverged=np.array([d['mode_unconverged'] for d in diagnostics]),discarded_mass=np.array([d['discarded_mass'] for d in diagnostics]),unsupported_components=np.array([d['unsupported_components'] for d in diagnostics]))
