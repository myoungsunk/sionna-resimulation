"""S1 online filter. Inputs contain current observations and controls only."""
import math,time
import numpy as np

TAU_DS=0.07138038868537433
GATE=9.210340371976184
def weight(arm,d0,delta,tau=.20):
 def soft(v,cut):
  return max(.25,min(1.,cut/(abs(v)+1e-12))**2)
 if arm=='W0':return 1.
 if arm=='H-d0':return float(abs(d0)<=tau)
 wd=soft(d0,tau)
 if arm=='W-d0':return wd
 if arm=='W-d0-DS':return max(.25,wd*soft(delta,TAU_DS))
 raise ValueError(arm)

def predict(core,x,P,k,controls):
 if k==0:return x,P
 ds,gy,dt=(float(controls[key][k]) for key in ('ds','gy','dt'))
 Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
 return core.predict(x,P,ds,gy,dt,Q)[:2]

def joseph(x,P,H,v,R,permitted,w):
 S=H@P@H.T+R;S=(S+S.T)*.5
 K=np.zeros((4,2))
 if not permitted:return x,P,K,S
 rows=slice(None) if w>0 else slice(0,1)
 Hr=H[rows];Rr=R[rows,rows];Sr=S[rows,rows]
 gain=np.linalg.solve(Sr,Hr@P).T;K[:,rows]=gain
 y=x+gain@v[rows];y[2]=(y[2]+math.pi)%(2*math.pi)-math.pi
 I=np.eye(4)-gain@Hr;C=I@P@I.T+gain@Rr@gain.T
 return y,(C+C.T)*.5,K,S

def replay(packet,controls,arm,core,model,spec,*,fixed_mask=None):
 n=len(packet['t']);x=np.r_[controls['x0'],0.];P=packet['P0'].copy();sx=x.copy();sp=P.copy()
 dims={'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'h':(2,),'H':(2,4),'mu':(2,),'Rvar':(2,2),'Reff':(2,2),'K':(4,2),'nu':(2,),'S':(2,2)}
 tr={k:np.empty((n,*shape)) for k,shape in dims.items()}
 for k in ['d0','weight','sigma_b','rho_before','nis','latency_ns']:tr[k]=np.empty(n)
 tr['mask']=np.empty(n,bool)
 for k,z in enumerate(packet['z']):
  start=time.perf_counter_ns()
  if fixed_mask is None:
   sx,sp=predict(core,sx,sp,k,controls)
   sh,sH=model.batch(sx[None],spec);sh=sh[0];sH=sH[0]
   R=packet['R'][k];v=z-sh-packet['muBASE'][k];S=sH@sp@sH.T+R
   allowed=bool(v@np.linalg.solve(S,v)<=GATE)
   if allowed:
    gain=np.linalg.solve(S,sH@sp).T;sx=sx+gain@v;sx[2]=core.wrap(sx[2])
    A=np.eye(4)-gain@sH;sp=A@sp@A.T+gain@R@gain.T;sp=(sp+sp.T)*.5
  else:allowed=bool(fixed_mask[k])
  rho=math.hypot(x[0]-spec['anchor'][0],x[1]-spec['anchor'][1])
  sig=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
  xp,pp=predict(core,x,P,k,controls);h,H=model.batch(xp[None],spec);h=h[0];H=H[0]
  mu=packet['muMB'][k];nu=z-h-mu;d0=z[1]-h[1];w=weight(arm,d0,packet['D'][k])
  rv=packet['R'][k].copy();rv[1,1]+=sig**2;re=rv.copy()
  if w:re[1,1]/=w
  x,P,K,S=joseph(xp,pp,H,nu,re,allowed,w)
  for key,val in [('x',x),('P',P),('prior',xp),('Pprior',pp),('h',h),('H',H),('mu',mu),('Rvar',rv),('Reff',re),('K',K),('nu',nu),('S',S),('d0',d0),('weight',w),('sigma_b',sig),('rho_before',rho),('nis',nu@np.linalg.solve(S,nu)),('mask',allowed)]:tr[key][k]=val
  tr['latency_ns'][k]=time.perf_counter_ns()-start
 return tr
