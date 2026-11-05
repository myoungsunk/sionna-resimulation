"""Causal covariance recovery. No evaluator inputs are accepted."""
from collections import deque
import math
import time
import numpy as np

SCALES=np.array([.1,.1,math.radians(1),math.radians(.05)])

def validate_covariance(P):
 C=P/SCALES[:,None]/SCALES[None,:]
 tol=1e-12*max(1.,np.linalg.norm(C,2))
 if np.linalg.norm(C-C.T,2)>tol or np.linalg.eigvalsh((C+C.T)/2)[0]<-tol:
  raise ValueError('invalid normalized covariance')

def inject(x,P,anchor,axes='tangent_heading'):
 """Add independent uncertainty floors and preserve mean/cross covariance."""
 delta=np.zeros((4,4));offset=x[:2]-np.asarray(anchor)[:2];rho=np.linalg.norm(offset)
 if axes not in ('heading','tangent_heading','tangent_heading_bg'):raise ValueError(axes)
 fallback=False
 if axes!='heading':
  if rho<.25:
   fallback=True;q=max(0.,.1**2-np.linalg.eigvalsh(P[:2,:2])[0]);delta[:2,:2]+=q*np.eye(2)
  else:
   u=np.r_[-offset[1]/rho,offset[0]/rho,0.,0.]
   delta+=max(0.,.1**2-u@P@u)*np.outer(u,u)
 delta[2,2]+=max(0.,math.radians(1)**2-P[2,2])
 if axes=='tangent_heading_bg':delta[3,3]+=max(0.,math.radians(.05)**2-P[3,3])
 validate_covariance(P+delta)
 return x.copy(),P+delta,delta,fallback

class Geometry:
 """Data information in the current prior chart, using transitions, not posterior P."""
 def __init__(self):self.history=deque()
 def add(self,t,H,R,F,accepted):
  # F maps previous prior perturbations to this prior before measurement feedback.
  self.history.append((float(t),H.copy(),R.copy(),F.copy(),bool(accepted)))
  while self.history and t-self.history[0][0]>2+1e-9:self.history.popleft()
 def information(self):
  I=np.zeros((4,4));back=np.eye(4)
  for _,H,R,F,accepted in reversed(self.history):
   if accepted:I+=back.T@H.T@np.linalg.solve(R,H)@back
   back=np.linalg.solve(F,back)
  G=SCALES[:,None]*I*SCALES[None,:];tol=1e-12*max(1.,np.linalg.norm(G,2))
  if np.linalg.norm(G-G.T,2)>tol:raise ValueError('information asymmetry')
  G=(G+G.T)/2
  if np.linalg.eigvalsh(G)[0]<-tol:raise ValueError('information PSD')
  A=G[:3,:3];b=G[:3,3];c=G[3,3]
  if c < -tol:raise ValueError('negative nuisance information')
  if c>tol:S=A-np.outer(b,b)/c
  elif np.linalg.norm(b)<=tol:S=A
  else:return False,float('nan'),float(np.linalg.eigvalsh(A)[0]),G
  minimum=float(np.linalg.eigvalsh((S+S.T)/2)[0])
  return minimum>=1e-6,minimum,float(np.linalg.eigvalsh(A)[0]),G

class RecoveryMachine:
 def __init__(self):
  self.risky=deque();self.first=None;self.quiet=None;self.applied=None
  self.monitor=None;self.last=-float('inf');self.count=0;self.status='MONITORING'
 def observe(self,t,accepted,w,rho,geometry_ok):
  risk=1-w
  if accepted and risk>=.5:
   self.risky.append(float(t))
  while self.risky and t-self.risky[0]>5+1e-9:self.risky.popleft()
  if self.first is None and len(self.risky)>=3:
   self.first=self.risky[0];self.status='SUSPECT_LATCH';self.applied=None;self.quiet=None
  safe=accepted and risk<=.25
  if safe:
   if self.quiet is None:self.quiet=float(t)
  else:self.quiet=None
  if self.first is None:return False,self.status
  if self.applied is not None:
   if safe and geometry_ok:
    if self.monitor is None:self.monitor=float(t)
    if t-self.monitor>=2-1e-9:
     self.first=None;self.applied=None;self.monitor=None;self.risky.clear();self.status='MONITORING'
   else:self.monitor=None
   return False,self.status
  if t-self.first>60+1e-9:self.status='HISTORY_EXPIRED_REMAIN_SUSPECT';return False,self.status
  if self.count>=3:self.status='MAX_RECOVERY';return False,self.status
  if t-self.last<20-1e-9:self.status='COOLDOWN';return False,self.status
  if self.quiet is None or t-self.quiet<1-1e-9:self.status='WAIT_QUIET';return False,self.status
  if rho>1.5:self.status='OUTSIDE_RECOVERY_RANGE';return False,self.status
  if not geometry_ok:self.status='INSUFFICIENT_GEOMETRY';return False,self.status
  self.status='RECOVERY_CANDIDATE';return True,self.status
 def commit(self,t):
  self.applied=float(t);self.last=float(t);self.count+=1;self.monitor=None;self.status='RECOVERY_APPLIED'

def replay(packet,controls,arm,core,model,spec,online,*,axes='tangent_heading',gate_mode='F',schedule=None,start=0,initial=None,end=None):
 if arm not in ('A','B','C_P','D_P'):raise ValueError(arm)
 if gate_mode not in ('F','O'):raise ValueError(gate_mode)
 prevention=arm in ('B','D_P');recovery=arm in ('C_P','D_P')
 n=len(packet['t']) if end is None else end
 x=np.r_[controls['x0'],0.] if initial is None else initial[0].copy()
 P=packet['P0'].copy() if initial is None else initial[1].copy()
 sx=np.r_[controls['x0'],0.];sp=packet['P0'].copy();machine=RecoveryMachine();geometry=Geometry()
 shapes={'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'Pbefore_injection':(4,4),'delta_P':(4,4),'h':(2,),'H':(2,4),'mu':(2,),'Rvar':(2,2),'Reff':(2,2),'K':(4,2),'nu':(2,),'S':(2,2),'information':(4,4)}
 tr={k:np.empty((n-start,*v)) for k,v in shapes.items()}
 for name in ('d0','weight','risk_weight','sigma_b','rho_before','nis','latency_ns','conditional_lambda','marginal_lambda','episode_first'):tr[name]=np.empty(n-start)
 for name in ('mask','preinjection_mask','shadow_mask','injected','fallback','candidate'):tr[name]=np.zeros(n-start,bool)
 tr['status']=np.empty(n-start,dtype='U40');tr['sample_index']=np.arange(start,n)
 events=[]
 for k,z in enumerate(packet['z'][:n]):
  tick=time.perf_counter_ns();sx,sp=online.predict(core,sx,sp,k,controls)
  sh,sH=model.batch(sx[None],spec);sh,sH=sh[0],sH[0]
  R=packet['R'][k];sv=z-sh-packet['muBASE'][k];ss=sH@sp@sH.T+R
  fixed=bool(sv@np.linalg.solve(ss,sv)<=online.GATE)
  if fixed:
   sx,sp,_,_=online.joseph(sx,sp,sH,sv,R,True,1.)
  if k<start:continue
  j=k-start;rho=math.hypot(x[0]-spec['anchor'][0],x[1]-spec['anchor'][1]);sig=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
  F=np.eye(4) if k==0 else core.transition(x,float(controls['ds'][k]),float(controls['gy'][k]),float(controls['dt'][k]))[1]
  xp,pp=online.predict(core,x,P,k,controls);h,H=model.batch(xp[None],spec);h,H=h[0],H[0]
  mu=packet['muMB'][k];nu=z-h-mu;d0=z[1]-h[1];rw=online.weight('W-d0-DS',d0,packet['D'][k]);w=rw if prevention else 1.
  rv=R.copy();rv[1,1]+=sig**2;re=rv.copy();re[1,1]/=w
  S0=H@pp@H.T+re;allowed=fixed if gate_mode=='F' else bool(nu@np.linalg.solve(S0,nu)<=online.GATE)
  geometry.add(packet['t'][k],H,re,F,allowed);ok,conditional,marginal,info=geometry.information()
  estimated_rho=math.hypot(xp[0]-spec['anchor'][0],xp[1]-spec['anchor'][1])
  candidate,status=machine.observe(float(packet['t'][k]),fixed,rw,estimated_rho,ok)
  fire=candidate if schedule is None else bool(schedule[k])
  if candidate and not recovery:machine.commit(packet['t'][k])
  preinjection_allowed=allowed
  before=pp.copy();delta=np.zeros((4,4));fallback=False
  if recovery and fire:
   xp,pp,delta,fallback=inject(xp,pp,spec['anchor'],axes);machine.commit(packet['t'][k])
   events.append(dict(index=k,time=float(packet['t'][k]),episode_first=machine.first,common_schedule=schedule is not None))
  if gate_mode=='O':
   actual_S=H@pp@H.T+re;allowed=bool(nu@np.linalg.solve(actual_S,nu)<=online.GATE)
  x,P,K,S=online.joseph(xp,pp,H,nu,re,allowed,w);validate_covariance(P)
  values=dict(x=x,P=P,prior=xp,Pprior=pp,Pbefore_injection=before,delta_P=delta,h=h,H=H,mu=mu,Rvar=rv,Reff=re,K=K,nu=nu,S=S,information=info,d0=d0,weight=w,risk_weight=rw,sigma_b=sig,rho_before=rho,nis=nu@np.linalg.solve(S,nu),mask=allowed,preinjection_mask=preinjection_allowed,shadow_mask=fixed,injected=recovery and fire,fallback=fallback,candidate=candidate,conditional_lambda=conditional,marginal_lambda=marginal,episode_first=machine.first if machine.first is not None else -1.,status=machine.status,latency_ns=time.perf_counter_ns()-tick)
  for name,value in values.items():tr[name][j]=value
 return tr,events

