"""One-transition Range kernel validation; independent QMC model and full MH."""
from pathlib import Path
import time,os
DEADLINE=float("inf")
def check_budget():
 if time.perf_counter()>DEADLINE:raise TimeoutError("frozen wall budget exceeded")
 if os.environ.get("MANAGED_PROCESS_STOP_FILE") and Path(os.environ["MANAGED_PROCESS_STOP_FILE"]).exists():raise InterruptedError("managed stop requested")
import numpy as np
from scipy.special import ndtr,ndtri,logsumexp
from scipy.optimize import brentq
from scipy.stats import qmc,rankdata
from i2_s0_batch import S0BatchTarget
from repair_target import full_log_density,log_rho_density,mh_log_ratio

class IndependentOneStep:
 def __init__(self,p,c):
  self.p=p;self.c=c;self.z=float(p['range_m'][0]);self.sig=float(c['range_sigma']);self.dz=abs(c['robot_z']-c['anchor_xyz'][2]);self.std=np.array(c['p0_std'][3:])
  self.hi=np.sqrt((max(self.dz,self.z)+12*self.sig)**2-self.dz**2);self.norm=self.primitive(np.sqrt(self.hi**2+self.dz**2))-self.primitive(self.dz)
  ss=np.unique(np.r_[np.linspace(self.dz,max(self.dz,self.z)+12*self.sig,131073),max(self.dz,self.z)])
  self.inverse_cdf=(self.primitive(ss)-self.primitive(self.dz))/self.norm;self.inverse_grid=np.sqrt(np.maximum(0,ss*ss-self.dz*self.dz))
 def primitive(self,s):
  t=(s-self.z)/self.sig
  return self.sig*self.z*np.sqrt(2*np.pi)*ndtr(t)-self.sig**2*np.exp(-.5*t*t)
 def radial_inverse(self,u):
  # Independently invert slant-area measure on an adaptively dense tail grid.
  lo=self.dz;hi=max(lo,self.z)+12*self.sig
  s=np.unique(np.r_[np.linspace(lo,hi,131073),max(lo,self.z)])
  cdf=(self.primitive(s)-self.primitive(lo))/self.norm
  return np.interp(u,self.inverse_cdf,self.inverse_grid)
 def radial_logpdf(self,r):
  with np.errstate(divide='ignore'):v=np.log(r)-.5*((np.sqrt(r*r+self.dz**2)-self.z)/self.sig)**2-np.log(self.norm)
  return np.where((r>=0)&(r<=self.hi),v,-np.inf)
 def prior_draw(self,u):
  u=np.clip(u,np.finfo(float).eps,1-np.finfo(float).eps)
  return np.column_stack([self.radial_inverse(u[:,0]),2*np.pi*u[:,1]-np.pi,ndtri(u[:,2:])])
 def likelihood(self,x,parts=False):
  # Direct Gaussian conditioning via matrix covariance inversion, independent
  # of production conditional()/evaluate() and its Cholesky formula.
  rho,de=x[:,0],x[:,1];bg,sf,eps=(x[:,2:5]*self.std).T
  dt,d,g,o=[float(self.p[k][1]) for k in ['dt_s','ds_odom','dtheta_gyro','dtheta_odom']]
  b=self.c['wheel_base'];qd=self.c['k_s']*abs(d);qg=self.c['gyro_N_rad_sqrt_s']**2*dt;qo=self.c['k_theta']*abs(o)+self.c['k_stheta']*abs(d)
  den=1+sf;level=1-eps**2/4;support=(den>0)&(level>0);den=np.where(support,den,1.);level=np.where(support,level,1.);v0=-eps/b;v1=-level/den
  S=qo+v0*v0*qd+v1*v1*qg;y=o-level*(g-bg*dt)/den-eps*d/b
  cov00=qd-qd*qd*v0*v0/S;cov01=-qd*qg*v0*v1/S;cov11=qg-qg*qg*v1*v1/S
  l0=np.sqrt(cov00);l10=np.divide(cov01,l0,out=np.zeros_like(l0),where=l0>0);schur=cov11-l10*l10
  if np.any(schur<0):raise FloatingPointError("negative independent conditional Schur variance; no PSD repair")
  l1=np.sqrt(schur)
  nd=qd*v0*y/S+l0*x[:,5];ng=qg*v1*y/S+l10*x[:,5]+l1*x[:,6]
  a=(g-ng-bg*dt)/den;u=d-nd-eps*b*a/4;step=u*np.sinc(a/(2*np.pi));xx=rho+step*np.cos(de+a/2);yy=step*np.sin(de+a/2)
  rr=np.sqrt(xx*xx+yy*yy+self.dz*self.dz)
  odo=-.5*(np.log(2*np.pi*S)+y*y/S);rng=-.5*((float(self.p['range_m'][1])-rr)**2/self.sig**2+np.log(2*np.pi*self.sig**2))
  good=support&np.all(np.isfinite(x),axis=1)&(rho>=0)&(de>=-np.pi)&(de<np.pi)
  odo=np.where(good,odo,-np.inf);rng=np.where(good,rng,-np.inf)
  return (odo,rng,rr) if parts else odo+rng
 def full(self,x):
  return self.likelihood(x)+self.radial_logpdf(x[:,0])-np.log(2*np.pi)-.5*(np.sum(x[:,2:]**2,axis=1)+5*np.log(2*np.pi))

def production_full(t,x):return full_log_density(t,x[:5],x[5:].reshape(2,1))
def radial_proposal_log(grid,cdf,r):
 r=np.asarray(r);i=np.clip(np.searchsorted(grid,r,side="right")-1,0,len(grid)-2);density=(cdf[i+1]-cdf[i])/(grid[i+1]-grid[i])
 with np.errstate(divide="ignore"):return np.where((r>=grid[0])&(r<=grid[-1]),np.log(density),-np.inf)
def proposal_log(t,x):return float(radial_proposal_log(t.table.grid,t.table.cdf,x[0])-np.log(2*np.pi)-.5*(x[2:]@x[2:]+5*np.log(2*np.pi)))
def draw_proposal(t,rng,n):return np.column_stack([t.table.sample(rng,n),rng.uniform(-np.pi,np.pi,n),rng.normal(size=(n,5))])
def joint_mh(t,seed,burn=4000,retained=8000):
 chains=[];acc=[]
 for j in range(4):
  rng=np.random.default_rng(np.random.SeedSequence([seed,4421,j]));x=draw_proposal(t,rng,1)[0];lp=production_full(t,x);keep=[];accepted=np.zeros(2)
  for it in range(burn+retained):
   if it%1000==0:check_budget()
   block=int(rng.random()>=.5)
   if block==0:
    y=draw_proposal(t,rng,1)[0];ly=production_full(t,y);lr=mh_log_ratio(ly,lp,proposal_log(t,x),proposal_log(t,y))
   else:
    q=x.copy();q[0]=np.log(x[0]);new=q+np.array([.01,.8,.6,.6,.6,.6,.6])*rng.normal(size=7);new[1]=(new[1]+np.pi)%(2*np.pi)-np.pi;y=new.copy();y[0]=np.exp(new[0]);ly=production_full(t,y);lr=mh_log_ratio(ly+new[0],lp+q[0])
   if np.log(rng.random())<lr:x,lp=y,ly;accepted[block]+=1
   if it>=burn:keep.append(x.copy())
  chains.append(keep);acc.append((accepted/(burn+retained)).tolist())
 return np.array(chains),acc

def statistics(x,w):
 f=np.column_stack([x[:,0],np.sin(x[:,1]),np.cos(x[:,1]),x[:,2:5],x[:,5:]])
 w=w/w.sum();mu=w@f;v=f-mu;cov=(v*w[:,None]).T@v
 qs=[]
 for col in f.T:
  ix=np.argsort(col);qs.append(np.interp([.025,.5,.975],np.cumsum(w[ix]),col[ix]).tolist())
 sectors=np.floor((x[:,1]+np.pi)/(np.pi/6)).astype(int)%12
 return dict(mean=mu.tolist(),sd=np.sqrt(np.diag(cov)).tolist(),covariance=cov.tolist(),quantiles=qs,sector_mass=np.bincount(sectors,weights=w,minlength=12).tolist(),ess=float(1/(w@w)))

def integration(model,power,rep):
 x=model.prior_draw(qmc.Sobol(7,scramble=True,seed=9301+100*power+rep).random_base2(power));ll=model.likelihood(x)+model.radial_logpdf(x[:,0])-radial_proposal_log(model.inverse_grid,model.inverse_cdf,x[:,0]);w=np.exp(ll-logsumexp(ll));return x,w,dict(statistics(x,w),log_normalizer=float(logsumexp(ll)-np.log(len(ll))))

def particle(t,seed,n=80000):
 rng=np.random.default_rng(seed);x=draw_proposal(t,rng,n)
 # PF weights from production likelihood evaluated without shared vector model.
 # Compute conditional arrays in bounded vector batches via production state.
 ll=np.empty(n);odo=np.empty(n)
 for k,a in enumerate(x):
  if k%1000==0:check_budget()
  cond=t.conditional(np.r_[a[0],0.,a[1],t.std*a[2:5]]);odo[k]=cond[-1] if cond else -np.inf;ll[k]=t.evaluate(a[:5],a[5:].reshape(2,1))
 # No mandatory resampling: full importance weights retain both update factors;
 # normalized odometry prefix weights and final ESS retained explicitly.
 correction=t.table.logpdf(x[:,0])-radial_proposal_log(t.table.grid,t.table.cdf,x[:,0]);ll=ll+correction;odo=odo+correction
 w=np.exp(ll-logsumexp(ll));ow=np.exp(odo-logsumexp(odo))
 return x,w,dict(statistics=statistics(x,w),prefix_ess=float(1/(ow@ow)),log_weight_variance=float(np.var(ll[np.isfinite(ll)])),resampling='none; ESS-trigger unnecessary for one-transition validation; weighted final posterior')

def ess1(a):
 m,n=a.shape;centered=a-a.mean(axis=1,keepdims=True);ac=np.fft.irfft(np.abs(np.fft.rfft(centered,n=2*n,axis=1))**2,n=2*n,axis=1)[:,:n]/np.arange(n,0,-1);W=np.mean(np.var(a,axis=1,ddof=1));V=(n-1)/n*W+np.var(a.mean(axis=1),ddof=1)
 if V<=0:return 0.
 rho=1-(W-np.mean(ac,axis=0))/V;total=0.;prev=np.inf
 for k in range(0,n-1,2):
  pair=rho[k]+rho[k+1]
  if pair<0:break
  pair=min(prev,pair);total+=pair;prev=pair
 return float(min(m*n,m*n/max(1.,-1+2*total)))
def rhat(a):
 n=a.shape[1];W=np.mean(np.var(a,axis=1,ddof=1));V=(n-1)/n*W+np.var(a.mean(axis=1),ddof=1)
 return float(np.sqrt(V/W)) if W>0 else None

def diagnostics(x,extras=None):
 f=np.concatenate([x[:,:,:1],np.sin(x[:,:,1:2]),np.cos(x[:,:,1:2]),x[:,:,2:]],axis=2);rs=[];es=[];tails=[];means=[]
 if extras is not None:f=np.concatenate([f,extras],axis=2)
 for a in f.transpose(2,0,1):
  if np.var(a)==0:return dict(passes=False,reason="undefined constant diagnostic",rank_folded_split_rhat=[],bulk_ess=[],tail_ess=[],mean_mcse=[])
  n=a.shape[1]//2;s=np.concatenate([a[:,:n],a[:,-n:]],axis=0);z=ndtri((rankdata(s.ravel()).reshape(s.shape)-.375)/(s.size+.25));fold=np.abs(s-np.median(s));fz=ndtri((rankdata(fold.ravel()).reshape(s.shape)-.375)/(s.size+.25));rs.append(max(rhat(z),rhat(fz)));es.append(ess1(z));tails.append(min(ess1((s<=np.quantile(s,.05)).astype(float)),ess1((s>=np.quantile(s,.95)).astype(float))));means.append(float(np.std(s)/np.sqrt(max(ess1(s),1))))
 return dict(rank_folded_split_rhat=rs,bulk_ess=es,tail_ess=tails,mean_mcse=means,passes=bool(max(rs)<1.01 and min(es+tails)>=400))




def batch_mcse(a):
 """Nonoverlapping batch estimator, 16 blocks/chain; validity requires mixing.
 Block quantiles give direct autocorrelation-aware numerical MCSE estimates.
 """
 blocks=np.array_split(a,16);ss=[statistics(b,np.ones(len(b))) for b in blocks]
 return {key:(np.std([s[key] for s in ss],axis=0,ddof=1)/4).tolist() for key in ['mean','sd','quantiles','sector_mass']}





