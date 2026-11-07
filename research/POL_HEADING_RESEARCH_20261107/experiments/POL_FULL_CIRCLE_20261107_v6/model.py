"""Finite-residual full-circle likelihood with calibrated angular displacement."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,hashlib,importlib.util
from pathlib import Path
import numpy as np
from scipy.special import ndtr,logsumexp
from scipy.optimize import minimize
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('grid_reference',BASE.parent/'POL_HEADING_VAR_20261106_v3/run_heading.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
e=old.e;OTH=np.array([0,1,3]);TH=old.TH

def dump(name,x):(BASE/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def moment(parts):
 w=np.array([r[0] for r in parts]);mass=w.sum();w/=mass;X=np.array([r[1] for r in parts]);mean=w@X
 resultant=np.sum(w*np.exp(1j*X[:,2]-.5*np.array([r[2][2,2] for r in parts])))
 mean[2]=np.angle(resultant) if abs(resultant)>1e-10 else X[np.argmax(w),2]
 delta=X-mean;delta[:,2]=e.wrap(delta[:,2]);P=sum(v*(r[2]+np.outer(d,d)) for v,r,d in zip(w,parts,delta));return mass,mean,(P+P.T)/2

def segments(xx,span,subdiv=1):
 """LUT-aligned delta intervals; angular dependence of h is exactly linear per cell."""
 step=np.deg2rad(e.LUT.dp/subdiv);ax,ay,_=e.CASE['anchor'];bearing=np.arctan2(-(xx[:,1]-ay),-(xx[:,0]-ax));offset=np.mod(bearing-xx[:,2]+np.pi,step)
 k=np.arange(-int(np.ceil(span/step))-1,int(np.ceil(span/step))+2);edges=np.clip(offset[:,None]+k[None,:]*step,-span,span)
 lo,hi=edges[:,:-1],edges[:,1:];mid=(lo+hi)/2
 q=np.repeat(xx[:,None,:],mid.shape[1],axis=1);q[:,:,2]=e.wrap(xx[:,2,None]+mid);h,H=old.model(q.reshape(-1,4))
 return lo,hi,mid,h.reshape(mid.shape),H.reshape(*mid.shape,4)

def interval_terms(lo,hi,mid,h,H,z,variance,C,tau):
 Ho=H[:,:,OTH];CH=Ho@C;V=variance+np.einsum('nsi,nsi->ns',CH,Ho);b=H[:,:,2];d=np.asarray(z).reshape(-1,1)-h+b*mid
 S=V+b*b*tau*tau;eta=b*tau*tau/S*d;W=tau*tau*V/S;sd=np.sqrt(W);a=(lo-eta)/sd;bb=(hi-eta)/sd
 Z=np.where(a>0,ndtr(-a)-ndtr(-bb),ndtr(bb)-ndtr(a));good=(Z>1e-30)&(hi>lo)
 pa=np.exp(-.5*a*a)/np.sqrt(2*np.pi);pb=np.exp(-.5*bb*bb)/np.sqrt(2*np.pi)
 ratio=np.divide(pa-pb,Z,out=np.zeros_like(Z),where=good);ratio2=np.divide(a*pa-bb*pb,Z,out=np.zeros_like(Z),where=good)
 mean=eta+sd*ratio;var=np.maximum(W*(1+ratio2-ratio*ratio),0.)
 ll=-.5*d*d/S-.5*np.log(2*np.pi*S)+np.log(np.maximum(Z,1e-300));ll[~good]=-np.inf
 residual=d-b*mean;return ll,CH,V,residual,b*b*var

def integrated(xx,z,C,p,subdiv=1):
 lo,hi,mid,h,H=segments(xx,9*p['sigma_angle_rad'],subdiv)
 ll,CH,V,r,rv=interval_terms(lo,hi,mid,h,H,z,p['residual_variance'],C,p['sigma_angle_rad'])
 ll+=np.log1p(-p['outlier_probability']);uniform=np.full((len(xx),1),np.log(p['outlier_probability']/2))
 norm=logsumexp(np.c_[uniform,ll],axis=1);w=np.exp(ll-norm[:,None]);K=CH/V[:,:,None]
 shift=np.einsum('ns,nsi->ni',w*r,K)
 second=np.tile(C,(len(xx),1,1))+np.einsum('ns,nsi,nsj->nij',w*(r*r+rv-V),K,K)
 cov=second-np.einsum('ni,nj->nij',shift,shift);return norm,xx[:,OTH]+shift,cov

def fit(datasets):
 los=datasets['los'];sel=los['t_s']<30;truth=los['truth_for_offline_scoring_only'][sel];xx=np.c_[truth,np.zeros(len(truth))];res=los['z_s'][sel]-old.model(xx)[0];R=float(np.mean(res*res));assert R>0
 full=datasets['full'];sel=full['t_s']<30;truth=full['truth_for_offline_scoring_only'][sel];xx=np.c_[truth,np.zeros(len(truth))];z=full['z_s'][sel];cache=segments(xx,np.deg2rad(450),1)
 def objective(v):
  tau=np.exp(v[0]);eps=1/(1+np.exp(-v[1]));ll,*_=interval_terms(*cache,z,R,np.zeros((3,3)),tau)
  lp=logsumexp(ll,axis=1);return float(-np.sum(np.logaddexp(np.log1p(-eps)+lp,np.log(eps/2))))
 sols=[]
 for deg in [1.,5.,15.]:
  r=minimize(objective,[np.log(np.deg2rad(deg)),np.log(.01/.99)],method='L-BFGS-B',bounds=[(np.log(np.deg2rad(.001)),np.log(np.deg2rad(45))),(-14.,14.)],options={'maxiter':400,'ftol':1e-12,'gtol':1e-6});sols.append(dict(x=r.x.tolist(),nll=float(r.fun),success=bool(r.success),message=str(r.message)))
 best=min(sols,key=lambda r:r['nll']);assert best['success'];p=dict(residual_variance=R,sigma_angle_rad=float(np.exp(best['x'][0])),outlier_probability=float(1/(1+np.exp(-best['x'][1]))))
 return p,dict(los_calibration_n=int((los['t_s']<30).sum()),full_calibration_n=int(sel.sum()),max_training_time=float(full['t_s'][sel].max()),sigma_s=float(np.sqrt(R)),sigma_angle_deg=float(np.rad2deg(p['sigma_angle_rad'])),solutions=sols,residual_mean=float(res.mean()),note='LOS residual RMS includes model discrepancy; Full angular displacement is phenomenological, not independently measured physical rotation.')

def observation_curve(mu,z,p,theta=TH,subdiv=1):
 xx=np.tile(mu,(len(theta),1));xx[:,2]=theta
 ll,_,_=integrated(xx,z,np.zeros((3,3)),p,subdiv);return np.exp(ll-logsumexp(ll))

def project(theta,logw,means,covs,grid_step_deg=.25):
 norm=logsumexp(logw);w=np.exp(logw-norm);grid=np.deg2rad(np.arange(-180,180,grid_step_deg));n=len(grid)
 # Linear bin deposition is only for finding posterior basins, not state integration.
 index=(e.wrap(theta)+np.pi)/(2*np.pi)*n;i=np.floor(index).astype(int)%n;f=index-np.floor(index);den=np.bincount(i,weights=w*(1-f),minlength=n)+np.bincount((i+1)%n,weights=w*f,minlength=n)
 smooth=gaussian_filter1d(den,1/grid_step_deg,mode='wrap');peaks=find_peaks(np.tile(smooth,3),prominence=smooth.max()*.01)[0];peaks=peaks[(peaks>=n)&(peaks<2*n)]-n
 if not len(peaks):peaks=np.array([smooth.argmax()])
 yl=smooth[(peaks-1)%n];yc=smooth[peaks];yr=smooth[(peaks+1)%n];off=np.divide(.5*(yl-yr),yl-2*yc+yr,out=np.zeros(len(peaks)),where=abs(yl-2*yc+yr)>1e-300);centers=e.wrap(grid[peaks]+np.clip(off,-.5,.5)*2*np.pi/n)
 dist=abs(e.wrap(theta[:,None]-centers[None,:]));part=np.exp(-dist/np.deg2rad(1)-logsumexp(-dist/np.deg2rad(1),axis=1)[:,None]);comps=[]
 for j,center in enumerate(centers):
  ww=w*part[:,j];mass=ww.sum()
  if mass<1e-14:continue
  ww/=mass;X=means.copy();X[:,2]=center+e.wrap(X[:,2]-center)
  mean=ww@X;mean[2]=np.angle(np.sum(ww*np.exp(1j*theta)))
  delta=X-mean;delta[:,2]=e.wrap(delta[:,2]);P=np.einsum('n,nij->ij',ww,covs)+np.einsum('n,ni,nj->ij',ww,delta,delta);P=(P+P.T)/2
  assert np.linalg.eigvalsh(P).min()>0
  comps.append((float(mass),mean,P))
 total=sum(c[0] for c in comps);return [(w/total,x,P) for w,x,P in comps],den

def measurement(comps,z,p,max_step_deg=.25,subdiv=1):
 ts=[];logs=[];means=[];covs=[]
 for weight,mu,P in comps:
  sy=P[2,2];sd=np.sqrt(sy);n=max(128,int(np.ceil(18*sd/np.deg2rad(max_step_deg))));dx=(np.arange(n)+.5)*18*sd/n-9*sd;theta=e.wrap(mu[2]+dx)
  C=P[np.ix_(OTH,OTH)]-np.outer(P[OTH,2],P[2,OTH])/sy;a=P[OTH,2]/sy
  xx=np.tile(mu,(n,1));xx[:,2]=theta;xx[:,OTH]+=dx[:,None]*a
  ll,cond,cc=integrated(xx,z,C,p,subdiv);lp=np.log(weight)-.5*(dx/sd)**2-.5*np.log(2*np.pi*sy)+np.log(18*sd/n)
  xx[:,OTH]=cond;PP=np.zeros((n,4,4));PP[:,OTH[:,None],OTH]=cc
  ts.append(theta);logs.append(lp+ll);means.append(xx);covs.append(PP)
 return project(np.concatenate(ts),np.concatenate(logs),np.concatenate(means),np.concatenate(covs),max_step_deg)

def run(ctrl,z,x0,mask,p,max_step_deg=.25,subdiv=1):
 mu,P=e.initial(x0,4);comps=[(1.,mu,P)];X=[];C=[];branch=[];dens=[];like=[]
 for k in range(len(z)):
  if os.getenv('MANAGED_PROCESS_STOP_FILE') and Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('CANCELLED')
  if k:comps=[(w,*e.predict_one(x,P,ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k])) for w,x,P in comps]
  _,donor,_=moment(comps)
  if mask[k]:comps,den=measurement(comps,z[k],p,max_step_deg,subdiv)
  _,x,P=moment(comps);X.append(x);C.append(P)
  # Cell masses and branch weights retained; circular mean is only a summary output.
  grid=TH;dd=sum(w*old.wrapped_prior(grid,xx[2],pp[2,2]) for w,xx,pp in comps);dd/=dd.sum();dens.append(dd.astype('float32'))
  branch.append([dict(weight=w,heading_rad=float(xx[2]),heading_sigma_rad=float(np.sqrt(pp[2,2]))) for w,xx,pp in comps])
  # Full observation likelihood at predicted mean XY. Display excludes XY uncertainty.
  like.append(observation_curve(donor,z[k],p,TH,subdiv).astype('float32'))
 return np.array(X),np.array(C),dict(heading_density=np.array(dens),observation_angle_likelihood=np.array(like),theta_rad=TH),branch
