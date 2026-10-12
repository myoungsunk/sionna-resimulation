"""V02 E1-E6 (see PREREG_KO.md). Usage: python -I run_e1e6.py {dev|confirm} [arm ...]"""
import sys,json,time,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import chi2
from multiprocessing import Pool
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'V02_DECOMP_20261011'))
import run as R                      # world generators / EKF / cubature from V02_DECOMP (same source tree path constant inside)
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.sensors import DRIFT_LEVELS
T=R.T;DT=R.DT;N=R.N;CHECK=R.CHECK;Config=R.Config
NOM=np.array([2.,.5,.2,0.,0.,0.]);LEV=DRIFT_LEVELS[2]
LEVEL_CAL=np.array([math.radians(LEV.gyro_bias_dps),LEV.gyro_sf,LEV.wheel_ratio])
def wrap(a):return (a+np.pi)%(2*np.pi)-np.pi
# ------------------------------------------------------------------ worlds
def world(wname,seed):
    """returns truth(N+1,6), d,g,o inputs, est0, pose-prior std(3), world tag"""
    cfg=R.cfg_()
    if wname in('CONS_SMALL','CONS_LARGE'):
        std=R.prior_std('SMALL' if wname.endswith('SMALL') else 'LARGE');truth,d,g,o,_=R.consistent_world(seed,std,cfg);return truth,d,g,o,NOM.copy(),std
    if wname=='HIGH':      # discrete +-level calibration, wheelbase 0, slip off; start offset in pose like the legacy HIGH modes
        std=np.asarray(Config().p0_std,float).copy();eps=np.random.default_rng([20261011,int(seed),2002]).normal(size=6)*std
        truth0=NOM.copy();est0=NOM.copy();est0[:3]-=eps[:3]
        t=np.arange(N+1)*DT;ds,ang=R.traj()
        inp,ev=V.generate(t,ds,ang,V.SensorV2Config(level=2,condition='all',slip_mode='off'),seed,parameters={'wheelbase':0.})
        pt=dict(zip([str(s) for s in ev['parameter_names']],ev['true_parameters']));tr=V.integrate(ds,ang,truth0[:3])
        truth=np.c_[tr,ev['true_bias_rad_s'],np.full(N+1,pt['gyro_sf']),np.full(N+1,pt['wheel_asymmetry'])]
        return truth,inp['ds_odom'],inp['dtheta_gyro'],inp['dtheta_odom'],est0,std
    raise ValueError(wname)
# ------------------------------------------------------------------ mixture (GSF)
class GSF:
    def __init__(self,cfg,comps):            # comps: list of (w,x0,P0)
        self.f=[F.SensorV2Filter(cfg,None,x,P0=P) for w,x,P in comps];self.lw=np.log([w for w,_,_ in comps])
    @staticmethod
    def _lik(y,S):return -0.5*(y*y/S+math.log(2*math.pi*S))
    def step(self,d,g,o,dt):
        for i,f in enumerate(self.f):
            r=f.step(d,g,o,dt)
            if r['status']=='applied':self.lw[i]+=self._lik(r['innovation'],r['S'])
        self.lw-=np.logaddexp.reduce(self.lw)
    def range_record(self,z):
        for i,f in enumerate(self.f):
            res,Rv,S,st=f.range_record(z)
            if st=='applied':self.lw[i]+=self._lik(res,S)
        self.lw-=np.logaddexp.reduce(self.lw)
    def mean_cov(self):
        w=np.exp(self.lw);xs=np.array([f.comps[0].x for f in self.f]);ref=xs[np.argmax(w),2]
        m=(w[:,None]*xs).sum(0);m[2]=ref+(w*wrap(xs[:,2]-ref)).sum();C=np.zeros((6,6))
        for wi,f in zip(w,self.f):
            dx=f.comps[0].x-m;dx[2]=wrap(f.comps[0].x[2]-m[2]);C+=wi*(f.comps[0].P+np.outer(dx,dx))
        return m,C
def split_prior(x0,std,dims,n,h2=0.5):
    """moment-preserving Gaussian split along `dims` with probabilists' Gauss-Hermite nodes; component var (1-h2)*sigma^2"""
    if n==1:return [(1.,x0.copy(),np.diag(std**2))]
    t,w=np.polynomial.hermite_e.hermegauss(n);w=w/w.sum();h=math.sqrt(h2);grids=np.meshgrid(*[np.arange(n)]*len(dims),indexing='ij');idx=np.stack([g.ravel() for g in grids],1);out=[]
    for ix in idx:
        x=x0.copy();P=std**2*np.ones(6);wt=1.
        for dim,i in zip(dims,ix):x[dim]+=h*t[i]*std[dim];P[dim]=(1-h2)*std[dim]**2;wt*=w[i]
        out.append((wt,x,np.diag(P)))
    return out
def sign_mixture(x0,std):
    out=[]
    for sg in np.array(np.meshgrid(*[[-1,1]]*3,indexing='ij')).reshape(3,-1).T:
        x=x0.copy();x[3:]=sg*LEVEL_CAL;s=std.copy();s[3:]=0.05*LEVEL_CAL;out.append((1/8,x,np.diag(s**2)))
    return out
# ------------------------------------------------------------------ particle filter
class PF:
    JIT_DIMS=(0,1,2,3,4,5);JIT_A=0.98
    def __init__(self,cfg,x0,std,N_part,rng,mixture=None):
        self.cfg=cfg;self.n=N_part;self.rng=rng;self.b=cfg.wheel_base
        if mixture is None:self.x=x0+rng.normal(size=(N_part,6))*std
        else:
            comp=rng.integers(0,len(mixture),N_part);self.x=np.empty((N_part,6))
            for ci,(w,xm,P) in enumerate(mixture):
                m=comp==ci;self.x[m]=xm+rng.normal(size=(int(m.sum()),6))*np.sqrt(np.diag(P))
        self.lw=np.zeros(N_part)
    def _norm(self):self.lw-=np.logaddexp.reduce(self.lw)
    def step(self,d,g,o,dt):
        """Locally optimal proposal (amendment v2): given x_prev the odometry model is linear-Gaussian in the shared input noise (nd,ng):
        y = o-h(x,d,g) = -(eps/b) nd - (L/D) ng + no.  Weight by the exact marginal N(y;0,S) and draw (nd,ng) from its conditional (Matheron)."""
        c=self.cfg;n=self.n;x=self.x;rng=self.rng
        Qd=c.k_s*abs(d);Qg=c.gyro_N_rad_sqrt_s**2*dt;Qo=c.k_theta*abs(o)+c.k_stheta*abs(d)
        D=1+x[:,4];eps=x[:,5];L=1-eps**2/4;a0=(g-x[:,3]*dt)/D;h0=L*a0+eps*d/self.b
        z1=rng.normal(size=n)*math.sqrt(Qd);z2=rng.normal(size=n)*math.sqrt(Qg)
        if c.use_odom_heading:
            B1=-eps/self.b;B2=-L/D;S=B1*B1*Qd+B2*B2*Qg+Qo;y=o-h0
            self.lw+=-0.5*y*y/S-0.5*np.log(S)
            nos=rng.normal(size=n)*math.sqrt(Qo);r=(y-(B1*z1+B2*z2+nos))/S
            nd=z1+Qd*B1*r;ng=z2+Qg*B2*r
        else:nd,ng=z1,z2
        dt_=d-nd;gt_=g-ng;a=(gt_-x[:,3]*dt)/D
        u=dt_-eps*self.b*a/4;half=a/2;small=np.abs(half)<1e-5
        s=np.where(small,1-half**2/6+half**4/120,np.sin(half)/np.where(small,1,half));ang=x[:,2]+half
        xn=x.copy();xn[:,0]+=u*s*np.cos(ang);xn[:,1]+=u*s*np.sin(ang);xn[:,2]=wrap(x[:,2]+a);self.x=xn;self._norm();self._maybe_resample()
    def range_record(self,z):
        a=self.cfg.anchor_xyz;dz=a[2]-self.cfg.robot_z;hh=np.sqrt((self.x[:,0]-a[0])**2+(self.x[:,1]-a[1])**2+dz**2)+self.cfg.range_offset
        R2=self.cfg.range_sigma**2+self.cfg.range_quant_var+self.cfg.range_extra_sigma**2;self.lw+=-0.5*(z-hh)**2/R2;self._norm();self._maybe_resample()
    def _maybe_resample(self):
        w=np.exp(self.lw);ess=1/np.sum(w*w)
        if ess>=self.n/2:return
        pos=(self.rng.random()+np.arange(self.n))/self.n;idx=np.minimum(np.searchsorted(np.cumsum(w),pos),self.n-1);self.x=self.x[idx].copy();self.lw=np.full(self.n,-math.log(self.n))
        dims=list(PF.JIT_DIMS);th=self.x[:,dims].copy();ref=th[:,2-0] if 2 in dims else None
        if 2 in dims:j=dims.index(2);th[:,j]=wrap(th[:,j]-self.x[0,2])      # heading relative to a reference particle (avoids wrap seams)
        m=th.mean(0);V_=np.cov(th.T)+1e-30*np.eye(len(dims));A=PF.JIT_A;Lc=np.linalg.cholesky(V_)
        new=A*th+(1-A)*m+math.sqrt(1-A*A)*(self.rng.normal(size=(self.n,len(dims)))@Lc.T)
        if 2 in dims:new[:,j]=wrap(new[:,j]+self.x[0,2])
        self.x[:,dims]=new
    def mean_cov(self):
        w=np.exp(self.lw);x=self.x;m=w@x;m[2]=math.atan2(w@np.sin(x[:,2]),w@np.cos(x[:,2]))
        dx=x-m;dx[:,2]=wrap(x[:,2]-m[2]);C=(dx*w[:,None]).T@dx;return m,C
    def skew_kurt(self):
        w=np.exp(self.lw);x=self.x[:,:2];m=w@x;dx=x-m;v=w@(dx*dx);sk=(w@(dx**3))/v**1.5;ku=(w@(dx**4))/v**2;return sk,ku
# ------------------------------------------------------------------ one run
def build(arm,wname,x0,std,cfg,seed):
    cal_std=std.copy()
    if arm=='EKF':return F.SensorV2Filter(cfg,None,x0,P0=np.diag(std**2))
    if arm=='CUBA':return R.JointCubatureFilter(cfg,None,x0,P0=np.diag(std**2))
    if arm.startswith('GSFXY'):n=int(round(math.sqrt(int(arm[5:]))));return GSF(cfg,split_prior(x0,std,[0,1],n))
    if arm.startswith('GSFXYP'):pass
    if arm.startswith('GSFP'):n=round(int(arm[4:])**(1/3));return GSF(cfg,split_prior(x0,std,[0,1,2],n))
    if arm=='EKF_MATCHED':s=std.copy();s[3:]=LEVEL_CAL;return F.SensorV2Filter(cfg,None,x0,P0=np.diag(s**2))
    if arm=='GSF_SIGN8':return GSF(cfg,sign_mixture(x0,std))
    if arm=='PF' or arm.startswith('PF_N'):
        n=20000 if arm=='PF' else int(arm[4:]);rng=np.random.default_rng([20261012,int(seed),7007])
        return PF(cfg,x0,std,n,rng,mixture=sign_mixture(x0,std) if wname=='HIGH' else None)
    raise ValueError(arm)
def one(args):
    arm,wname,seed=args;cfg=R.cfg_();t0=time.time()
    truth,d,g,o,est0,std=world(wname,seed);f=build(arm,wname,est0,std,cfg,seed)
    nr=np.random.default_rng([20261011,seed,8002]).normal(0,.08,N+1);E=[];Ps=[];extra={}
    for k in range(N+1):
        if k:f.step(float(d[k]),float(g[k]),float(o[k]),DT)
        r=float(np.sqrt((truth[k,0]-4.)**2+truth[k,1]**2+2.2**2))+nr[k];f.range_record(r)
        if k in CHECK:
            x,P=f.mean_cov();e=truth[k]-x;e[2]=V.wrap(e[2]);E.append(e);Ps.append(P.copy())
    if isinstance(f,PF):extra['skew'],extra['kurt']=f.skew_kurt()
    return np.array(E),np.array(Ps),time.time()-t0,extra
ARMS_PLAN=[('CONS_SMALL',['EKF','CUBA','PF','GSFXY1','GSFXY4','GSFXY9','GSFXY16','GSFP8','GSFP27']),
           ('CONS_LARGE',['EKF','CUBA','PF','GSFXY1','GSFXY4','GSFXY9','GSFXY16','GSFP8','GSFP27']),
           ('HIGH',['EKF','EKF_MATCHED','GSF_SIGN8','PF'])]
def summarize(arm,wname,res,n_note=''):
    E=np.stack([r[0] for r in res]);P=np.stack([r[1] for r in res]);n=len(E);rows=[];sec=float(np.mean([r[2] for r in res]))
    for j,k in enumerate(CHECK):
        e=E[:,j,:3];C=P[:,j,:3,:3];nees=np.einsum('ni,ni->n',e,np.linalg.solve(C,e[...,None])[...,0])
        lo,hi=chi2.ppf([.025,.975],3*n)/n
        rows.append(dict(world=wname,arm=arm,k=k,n=n,NEES=float(nees.mean()),lo=float(lo),hi=float(hi),inside=bool(lo<=nees.mean()<=hi),cov95=float(np.mean(nees<=chi2.ppf(.95,3))),
          hdg_MSE_over_P=float(np.mean(E[:,j,2]**2)/P[:,j,2,2].mean()),pos_rmse=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,1)))),pos_P_rms=float(np.sqrt(np.mean(P[:,j,0,0]+P[:,j,1,1]))),sec_per_seed=sec,
          skew_mean=float(np.mean([r[3].get('skew',np.nan) if not np.isscalar(r[3].get('skew',np.nan)) else r[3].get('skew',np.nan) for r in res]) if False else np.nan)))
    return rows
if __name__=='__main__':
    mode=sys.argv[1];sel=sys.argv[2:] ;seeds=list(range(2900,2932)) if mode=='dev' else list(range(3000,3512))
    rows=[];t0=time.time();out=HERE/('RESULTS_DEV.csv' if mode=='dev' else 'RESULTS_E1E6.csv')
    for wname,arms in ARMS_PLAN:
        for arm in arms:
            if sel and f'{wname}:{arm}' not in sel and arm not in sel:continue
            with Pool(4) as p:res=p.map(one,[(arm,wname,s) for s in seeds],chunksize=2)
            rows+=summarize(arm,wname,res);j=[r for r in rows if r['arm']==arm and r['world']==wname][-1]
            print(wname,arm,'NEES48=%.3f [%.3f,%.3f] inside=%s cov95=%.3f posRMSE=%.4f sec/seed=%.2f'%(j['NEES'],j['lo'],j['hi'],j['inside'],j['cov95'],j['pos_rmse'],j['sec_per_seed']),'| elapsed %.0f'%(time.time()-t0),flush=True)
            pd.DataFrame(rows).to_csv(out,index=False)
