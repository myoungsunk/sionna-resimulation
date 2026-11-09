"""B-MCG numerical contracts. No ground-truth or clean-RF input is accepted here."""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,time,math
import numpy as np

SPEC={'anchor':(10.,0.,2.65),'robot_z_m':.45,'mount_deg':0.}
STEP=299792458/(1028*1950000)
ACTIONS=np.array([[1,1],[.5,1],[.25,1],[0,1],[1,.5],[1,.25],[1,0],[.5,.5],[.25,.25],[0,0]],float)

def wrap(v):return (np.asarray(v)+np.pi)%(2*np.pi)-np.pi

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def dump(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    def default(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,np.generic):return v.item()
        raise TypeError(type(v).__name__)
    partial=p.with_suffix(p.suffix+'.part')
    partial.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=default,allow_nan=False)+'\n')
    partial.replace(p)

def save(path,**arrays):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix('.part')
    with q.open('wb') as f:np.savez_compressed(f,**arrays)
    q.replace(p)

def covariance(P,n):
    P=np.asarray(P,float)
    if P.shape!=(n,n) or not np.isfinite(P).all():raise ValueError('COVARIANCE_SHAPE_NONFINITE')
    if not np.allclose(P,P.T,atol=1e-12,rtol=1e-10):raise ValueError('COVARIANCE_ASYMMETRIC')
    if np.linalg.eigvalsh(P).min() < -1e-11:raise ValueError('COVARIANCE_NOT_PSD')
    return P

@dataclass(frozen=True)
class OnlineSeries:
    t:np.ndarray
    ds:np.ndarray
    gy:np.ndarray
    dt:np.ndarray
    z:np.ndarray
    mu:np.ndarray
    R:np.ndarray
    x0:np.ndarray
    P0:np.ndarray
    mu_gate:np.ndarray
    def __post_init__(self):
        n=len(self.t)
        shapes={'t':(n,),'ds':(n,),'gy':(n,),'dt':(n,),'z':(n,2),'mu':(n,2),'R':(n,2,2),'x0':(4,),'P0':(4,4),'mu_gate':(n,2)}
        for key,shape in shapes.items():
            a=np.asarray(getattr(self,key))
            if a.shape!=shape or not np.isfinite(a).all():raise ValueError('INVALID_ONLINE_FIELD:'+key)
        if np.any(np.diff(self.t)<=0) or np.max(abs(self.dt-np.r_[0.,np.diff(self.t)]))>1e-9:raise ValueError('INVALID_TIMESTAMPS')
        if np.linalg.eigvalsh(self.R).min()<=0:raise ValueError('R_NOT_SPD')
    def controls(self):return dict(ds=self.ds,gy=self.gy,dt=self.dt,x0=self.x0[:3])
    def packet(self):return dict(t=self.t,z=self.z,muMB=self.mu,muBASE=self.mu_gate,R=self.R,P0=self.P0,D=np.zeros(len(self.t)))

def extract_B(Hrf,obs):
    c=obs.cir_batch(Hrf);mag=abs(c);peak=mag.max(1)
    if np.any(peak<=0) or not np.isfinite(mag).all():raise ValueError('INVALID_CIR')
    edges=np.argmax(mag>=.3*peak[:,None,:],axis=1);tap=edges.min(1)
    p=abs(c[np.arange(len(c)),tap])**2;den=p.sum(1)
    if np.any(den<=0):raise ValueError('EMPTY_FP_POWER')
    z=np.column_stack([tap*STEP,(p[:,0]-p[:,1])/den])
    features=np.column_stack([edges,mag.argmax(1),peak,p])
    return tap,z,features

def effective_R(R,beta):
    beta=np.asarray(beta,float)
    if beta.shape!=(2,) or not np.isfinite(beta).all() or np.any((beta<0)|(beta>1)):raise ValueError('INVALID_BETA')
    ids=np.flatnonzero(beta>0);rr=R[np.ix_(ids,ids)].copy()
    for j,i in enumerate(ids):rr[j,j]+=(1/beta[i]-1)*R[i,i]
    return ids,rr

def update(x,P,H,nu,R,allowed,beta=(1.,1.)):
    # No mutation, no output clipping; rejected updates retain original prior.
    ids,rr=effective_R(R,beta);K=np.zeros((4,2));y=x.copy();C=P.copy()
    if not allowed or not len(ids):return y,C,K,ids
    hh=H[ids];ss=hh@P@hh.T+rr;ss=(ss+ss.T)*.5
    gain=np.linalg.solve(ss,hh@P).T;K[:,ids]=gain
    y=x+gain@nu[ids];y[2]=wrap(y[2]);A=np.eye(4)-gain@hh
    C=A@P@A.T+gain@rr@gain.T;C=(C+C.T)*.5
    return y,C,K,ids

def paths(core,theta,ds,gy,dt,a,k,jac=True):
    states=[np.asarray(theta,float).copy()];sens=[np.eye(4)]
    for j in range(a+1,k+1):
        x,F,_=core.transition(states[-1],float(ds[j]),float(gy[j]),float(dt[j]))
        states.append(x)
        if jac:sens.append(F@sens[-1])
    return np.asarray(states),np.asarray(sens) if jac else None

def loss(x,truth):
    e=x[:,:3]-truth;e[:,2]=wrap(e[:,2])
    return np.column_stack([np.rad2deg(e[:,2])**2,np.sum(e[:,:2]**2,axis=1)])

def metrics(x,P,truth,mask):
    e=x[:,:3]-truth;e[:,2]=wrap(e[:,2]);l=loss(x,truth)
    c=P[:,:3,:3];nees=np.einsum('ni,ni->n',e,np.linalg.solve(c,e[...,None])[...,0])
    nxy=np.einsum('ni,ni->n',e[:,:2],np.linalg.solve(c[:,:2,:2],e[:,:2,None])[...,0])
    nh=e[:,2]**2/P[:,2,2]
    return dict(n=len(x),heading_mse=float(l[:,0].mean()),xy_mse=float(l[:,1].mean()),heading_rmse_deg=float(np.sqrt(l[:,0].mean())),xy_rmse_cm=float(100*np.sqrt(l[:,1].mean())),nees3=float(nees.mean()),pose95=float(np.mean(nees<=7.814727903251179)),xy95=float(np.mean(nxy<=5.991464547107979)),heading95=float(np.mean(nh<=3.841458820694124)),Pxy_trace=float(np.trace(P[:,:2,:2],axis1=1,axis2=2).mean()),heading_sigma_deg=float(np.rad2deg(np.sqrt(P[:,2,2])).mean()),logdet_pose_mean=float(np.linalg.slogdet(c)[1].mean()),accepted=int(np.sum(mask)))

def action_losses(trace,truth,force=False):
    n=len(trace['x']);L=np.empty((n,len(ACTIONS),2));states=np.empty((n,len(ACTIONS),4))
    parity=0.;order=0.
    for ai,beta in enumerate(ACTIONS):
        for k in range(n):
            y,C,_,_=update(trace['prior'][k],trace['Pprior'][k],trace['H'][k],trace['nu'][k],trace['Reff'][k],True if force else bool(trace['mask'][k]),beta)
            states[k,ai]=y
            if ai==0 and not force:parity=max(parity,float(np.max(abs(y-trace['x'][k]))),float(np.max(abs(C-trace['P'][k]))))
            if not force:order=min(order,float(np.linalg.eigvalsh(C-trace['P'][k]).min()))
        L[:,ai]=loss(states[:,ai],truth)
    if not force and parity>1e-10:raise ValueError(('P1_PARITY',parity))
    return L,states,parity,order

def utility(base,skip,candidate):
    ans=[]
    for j in range(2):
        benefit=skip[:,j]-base[:,j];good=benefit>1e-12;bad=benefit< -1e-12
        lost=float(np.maximum(candidate[good,j]-base[good,j],0).sum())
        den=float(benefit[good].sum())
        ans.append(dict(net_gain=float((base[:,j]-candidate[:,j]).sum()),lost_useful_gain=lost/den if den>0 else None,good_n=int(good.sum()),bad_n=int(bad.sum()),saved_bad_loss=float((base[bad,j]-candidate[bad,j]).sum()),lost_gain_absolute=lost))
    return dict(heading=ans[0],xy=ans[1])
