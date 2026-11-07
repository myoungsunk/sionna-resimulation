"""Direct angular-variance IMM from all inverse polarization heading candidates.

Likelihood is derived from the frozen polarization forward model, not an
independently invented angle sensor. Integrates heading on the full circle;
position/bias conditional on heading use a first-order Gaussian approximation.
Discrete variance modes are marginalized, including between-mode covariance.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,time,csv,math,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
BASE=Path(__file__).resolve().parent
OLD_CODE=BASE.parent/'POL_FGO_CORR_20261106_v1';sys.path.insert(0,str(OLD_CODE))
import experiment as e
SIGMA_DEG=np.array([1.,2.,5.,10.,20.,45.]);SCALES=np.deg2rad(SIGMA_DEG)**2;PI=np.array([.70,.15,.075,.04,.025,.01]);PI/=PI.sum()
STEP=.25;TH=np.deg2rad(np.arange(-180.,180.,STEP));OTH=np.array([0,1,3]);PERSIST=5.
def dump(name,x):(BASE/name).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def model(x):
 """Vectorized exact frozen trilinear LUT and analytic x/y derivatives."""
 lut=e.LUT;ax,ay,az=e.CASE['anchor'];u=x[:,0]-ax;v=x[:,1]-ay;h=az-e.CASE['robot_z_m'];r2=np.maximum(u*u+v*v,1e-12);r=np.sqrt(r2);k=180/np.pi
 tg=np.arctan2(r,h)*k;tx=np.arctan2(-v,u)*k;rx=(np.arctan2(-v,-u)*k-x[:,2]*k+180)%360-180
 tt=np.clip(tg/lut.dt,0,lut.nt-1-1e-9);aa=(tx+180)/lut.dp;bb=(rx+180)/lut.dp
 i=np.floor(tt).astype(int);j=np.floor(aa).astype(int)%lut.np;q=np.floor(bb).astype(int)%lut.np;ft=tt-i;fa=aa-np.floor(aa);fb=bb-np.floor(bb);j1=(j+1)%lut.np;q1=(q+1)%lut.np;S=lut.s
 c000,c001,c010,c011=S[i,j,q],S[i,j,q1],S[i,j1,q],S[i,j1,q1];c100,c101,c110,c111=S[i+1,j,q],S[i+1,j,q1],S[i+1,j1,q],S[i+1,j1,q1]
 c00=c000*(1-fb)+c001*fb;c01=c010*(1-fb)+c011*fb;c10=c100*(1-fb)+c101*fb;c11=c110*(1-fb)+c111*fb;c0=c00*(1-fa)+c01*fa;c1=c10*(1-fa)+c11*fa
 val=c0*(1-ft)+c1*ft;gt=(c1-c0)/lut.dt;ga=((c01-c00)*(1-ft)+(c11-c10)*ft)/lut.dp;gb=(((c001-c000)*(1-fa)+(c011-c010)*fa)*(1-ft)+((c101-c100)*(1-fa)+(c111-c110)*fa)*ft)/lut.dp
 H=np.zeros((len(x),4));H[:,0]=gt*h/(r2+h*h)*u/r*k+ga*v/r2*k-gb*v/r2*k
 H[:,1]=gt*h/(r2+h*h)*v/r*k-ga*u/r2*k+gb*u/r2*k;H[:,2]=-gb*k
 return val,H

def moment(parts):
 """[(weight,mean,cov)] -> normalized circular mean and total covariance."""
 weights=np.array([a[0] for a in parts]);mass=weights.sum();weights/=mass;X=np.array([a[1] for a in parts]);mean=weights@X
 cs=np.sum(weights*np.exp(1j*X[:,2]));mean[2]=np.angle(cs) if abs(cs)>1e-8 else X[np.argmax(weights),2]
 delta=X-mean;delta[:,2]=e.wrap(delta[:,2]);P=sum(w*(c+np.outer(dx,dx)) for w,(_,_,c),dx in zip(weights,parts,delta))
 return mass,mean,(P+P.T)/2

def interact(comps,dt,variable):
 """IMM interaction within distinct circular-heading basins; preserve modes."""
 # Basin identity is assigned by the previous circular posterior projection.
 # Never collapse distinct basins merely because their means are nearby.
 groups={}
 for comp in comps:groups.setdefault(comp[4],[]).append(comp)
 n=6 if variable else 1;stay=np.exp(-dt/PERSIST);T=stay*np.eye(n)+(1-stay)*np.tile(PI if variable else [1.],(n,1));result=[]
 for basin,g in groups.items():
  for dest in range(n):
   parts=[(w*T[src,dest],mu,P) for w,src,mu,P,_ in g];mass,mu,P=moment(parts)
   result.append((mass,dest,mu,P,basin))
 return result

def inverse_roots(mu,z):
 """All piecewise-linear LUT inverse roots at predicted XY, no yaw-prior selection."""
 ax,ay,_=e.CASE['anchor'];bearing=np.arctan2(-(mu[1]-ay),-(mu[0]-ax))
 theta=np.sort(e.wrap(bearing-np.deg2rad(-180+np.arange(e.LUT.np)*e.LUT.dp)))
 xx=np.tile(mu,(len(theta),1));xx[:,2]=theta;h,_=model(xx)
 th=np.r_[theta,theta[0]+2*np.pi];hh=np.r_[h,h[0]];roots=[]
 for i in range(len(theta)):
  if abs(hh[i+1]-hh[i])<1e-12:
   if abs(z-hh[i])<1e-10:return [] # continuum of angles: uninformative
   continue
  f=(z-hh[i])/(hh[i+1]-hh[i])
  if 0<=f<1:roots.append(e.wrap(th[i]+f*(th[i+1]-th[i])))
 if not roots:return []
 xx=np.tile(mu,(len(roots),1));xx[:,2]=roots;_,H=model(xx)
 if np.any(abs(H[:,2])<1e-6):return [] # unstable inverse: no forced candidate
 return [(float(angle),np.array([hrow[0]/hrow[2],hrow[1]/hrow[2],0.])) for angle,hrow in zip(roots,H)]

def measurement(comps,z,variable,theta=TH,fun=model,rootfun=inverse_roots):
 """Angular pseudo-observation mixture; R is directly radian squared, never Rs."""
 n=len(theta);step=2*np.pi/n;records=[]
 for weight,scale,mu,P,basin in comps:
  roots=rootfun(mu,z);sy=P[2,2];delta=e.wrap(theta-mu[2]);a=P[OTH,2]/sy
  C=P[np.ix_(OTH,OTH)]-np.outer(P[OTH,2],P[2,OTH])/sy
  J=int(np.ceil((9*np.sqrt(sy)+np.pi)/(2*np.pi)))
  for winding in range(-J,J+1):
   unwrapped=delta+2*np.pi*winding
   if np.min(abs(unwrapped))>9*np.sqrt(sy):continue
   xx=np.tile(mu,(n,1));xx[:,2]=theta;xx[:,OTH]=mu[OTH]+unwrapped[:,None]*a
   lp=np.log(weight)-.5*unwrapped**2/sy-.5*np.log(2*np.pi*sy)+np.log(step)
   if not roots:
    records.append((scale,lp-np.log(2*np.pi),xx,np.tile(C,(n,1,1))));continue
   for angle,Ho in roots:
    R=SCALES[scale] if variable else SCALES[0];CH=C@Ho;V=float(R+Ho@CH);assert V>0
    innovation=e.wrap(angle-theta-(xx[:,OTH]-mu[OTH])@Ho)
    CC=np.tile(C-np.outer(CH,CH)/V,(n,1,1))
    K=CH/V;L=int(np.ceil((9*np.sqrt(V)+np.pi)/(2*np.pi)))
    for turn in range(-L,L+1):
     resid=innovation+2*np.pi*turn
     if np.min(abs(resid))>9*np.sqrt(V):continue
     cond=xx.copy();cond[:,OTH]+=resid[:,None]*K
     ll=lp-np.log(len(roots))-.5*(resid**2/V+np.log(2*np.pi*V))
     records.append((scale,ll,cond,CC))
 norm=logsumexp(np.concatenate([x[1] for x in records]));density=sum(np.exp(x[1]-norm) for x in records)
 # Physical-angle smoothing is used ONLY for topology detection, never likelihood.
 # Subcell peak interpolation and continuous partition remove nearest-node jumps.
 smooth=gaussian_filter1d(density,np.deg2rad(1.)/step,mode='wrap')
 ext=np.tile(smooth,3);peaks=find_peaks(ext,prominence=max(smooth)*.01)[0];peaks=peaks[(peaks>=n)&(peaks<2*n)]-n
 if not len(peaks):peaks=np.array([np.argmax(smooth)])
 if len(peaks)>24:raise RuntimeError('EXCESSIVE_HEADING_MODES')
 yl=smooth[(peaks-1)%n];yc=smooth[peaks];yr=smooth[(peaks+1)%n]
 denom=yl-2*yc+yr;offset=np.divide(.5*(yl-yr),denom,out=np.zeros(len(peaks)),where=abs(denom)>1e-300)
 centers=e.wrap(theta[peaks]+np.clip(offset,-.5,.5)*step)
 dist=abs(e.wrap(theta[:,None]-centers[None,:]))
 logits=-dist/np.deg2rad(1.);partition=np.exp(logits-logsumexp(logits,axis=1)[:,None]);new=[]
 for mode in range(len(peaks)):
  cells=np.ones(n,dtype=bool);ref=centers[mode]
  for sc in range(6 if variable else 1):
   mass=0.;first=np.zeros(4);second=np.zeros((4,4))
   for idx,ll,cond,CC in records:
    if idx!=sc:continue
    weights=np.exp(ll[cells]-norm)*partition[:,mode];m=cond[cells].copy();m[:,2]=ref+e.wrap(m[:,2]-ref);cov=np.zeros((len(m),4,4));cov[:,OTH[:,None],OTH]=CC[cells]
    mass+=weights.sum();first+=weights@m;second+=np.einsum('n,nij->ij',weights,cov)+np.einsum('n,ni,nj->ij',weights,m,m)
   if mass<1e-280:continue
   mean=first/mass;P=second/mass-np.outer(mean,mean);mean[2]=e.wrap(mean[2]);P=(P+P.T)/2
   if np.linalg.eigvalsh(P).min()<=0:raise RuntimeError('NON_PD_MIXTURE_MOMENT')
   new.append((float(mass),sc,mean,P,mode))
 total=sum(x[0] for x in new);new=[(w/total,sc,x,P,mode) for w,sc,x,P,mode in new]
 return new,density,{'heading_modes':len(peaks),'entropy':float(-np.sum(density*np.log(np.maximum(density,1e-300)))),'mass_before_renormalize':float(total)}

def wrapped_prior(theta,mean,var):
 delta=e.wrap(theta-mean);J=int(np.ceil((9*np.sqrt(var)+np.pi)/(2*np.pi)))
 return sum(np.exp(-.5*(delta+2*np.pi*j)**2/var) for j in range(-J,J+1))/np.sqrt(2*np.pi*var)

def run(ctrl,z,x0,variable,mask,theta=TH):
 mu,P=e.initial(x0,4);comps=[(float(w),j,mu.copy(),P.copy(),0) for j,w in enumerate(PI if variable else [1.])];X=[];C=[];scaleprobs=[];modes=[];density=[];maxcomps=0
 for k in range(len(z)):
  if os.getenv('MANAGED_PROCESS_STOP_FILE') and Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('CANCELLED')
  if k:
   comps=interact(comps,ctrl['dt_s'][k],variable);nxt=[]
   for w,j,x,P,basin in comps:
    xp,pp=e.predict_one(x,P,ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k]);nxt.append((w,j,xp,pp,basin))
   comps=nxt
  if mask[k]:comps,den,di=measurement(comps,z[k],variable,theta);modes.append(di['heading_modes'])
  else:
   den=sum(w*wrapped_prior(theta,x[2],P[2,2]) for w,j,x,P,basin in comps);den/=den.sum();modes.append(0)
  _,x,P=moment([(w,x,P) for w,j,x,P,basin in comps]);X.append(x);C.append(P);density.append(den.astype('float32'));probs=np.zeros(6 if variable else 1)
  for w,j,_,_,_ in comps:probs[j]+=w
  scaleprobs.append(probs);maxcomps=max(maxcomps,len(comps))
 return np.array(X),np.array(C),dict(angular_variance_prob=np.array(scaleprobs),sigma_candidates_deg=SIGMA_DEG if variable else SIGMA_DEG[:1],heading_density=np.array(density),heading_modes=np.array(modes),theta_rad=theta,max_components=maxcomps)

