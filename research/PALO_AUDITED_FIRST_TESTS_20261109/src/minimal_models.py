"""Minimal mechanisms. All inference functions receive NO ground truth/LoS.
Angles radians, metres, seconds. Normal observation R=.0081 is frozen.
This module is research code, not a certified navigation implementation.
"""
from __future__ import annotations
import numpy as np
from scipy.special import logsumexp

R=.0081
GATE=6.6348966010212145
T_MODE=np.array([[.95,.05],[.05,.95]])  # OFF,ON; predeclared, not tuned
PI_MODE=np.array([.1,.9])

def wrap(x): return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi

def init_cov(): return np.diag(np.array([.1,.1,np.deg2rad(5),np.deg2rad(.1)])**2)

def predict(e,x,P,u,k):
    ds,da,dt=map(float,(u['ds_odom'][k],u['dtheta_gyro'][k],u['dt_s'][k]))
    Q=np.diag([2e-5*abs(ds),np.deg2rad(.015)**2*dt,0.])
    if np.asarray(x).ndim==1:
        y,C,_,_=e.core.predict(x,P,ds,da,dt,Q)
        return y,C
    pairs=[e.core.predict(a,b,ds,da,dt,Q)[:2] for a,b in zip(x,P)]
    return np.stack([v[0] for v in pairs]),np.stack([v[1] for v in pairs])

def mix_moments(x,p,w):
    w=np.asarray(w);x=np.asarray(x);p=np.asarray(p)
    m=w@x
    m[2]=np.arctan2(w@np.sin(x[:,2]),w@np.cos(x[:,2]))
    d=x-m;d[:,2]=wrap(d[:,2])
    V=np.einsum('b,bij->ij',w,p)+np.einsum('b,bi,bj->ij',w,d,d)
    return m,(V+V.T)/2

def log_likelihood(z,h,S):
    if not np.isfinite(z) or abs(z)>1+1e-12: raise ValueError('s outside [-1,1]')
    on=-.5*(np.log(2*np.pi*S)+(z-h)**2/S)
    return np.full_like(np.asarray(on),-np.log(2.)),on

def scalar_candidate(e,x,P,z):
    """Canonical original scalar kernel for exact long replay/checkpoint parity.
    Batched mixture updates remain separately checked step-by-step.
    """
    def obs(v):
        hh,JJ=e.scalar_lut.model(v,e.case)
        return hh[1:],JJ[1:]
    y,C,a=e.core.gaussian_update(x,P,np.array([z]),obs,np.array([[R]]))
    hh,JJ=obs(x);cl=e.observe(x)[2]
    return y,C,dict(h=float(hh[0]),H=JJ[0],nu=float(a['innovation'][0]),
        S=float(a['S'][0,0]),K=a['K'][:,0],step=a['K'][:,0]*a['innovation'][0],
        nis=float(a['NIS']),clip=bool(cl))

def run_baseline(e,u,z,x0,gate=GATE):
    n=len(z);x=x0.copy();P=init_cov()
    X=[];PP=[];PX=[];PC=[];NN=[];A=[];HH=[];CC=[];FS=[]
    for k in range(n):
        F=np.eye(4)
        if k:
            _,F,_=e.core.transition(x,float(u['ds_odom'][k]),float(u['dtheta_gyro'][k]),float(u['dt_s'][k]))
            x,P=predict(e,x,P,u,k)
        PX.append(x.copy());PC.append(P.copy());FS.append(F)
        y,C,d=scalar_candidate(e,x,P,float(z[k]))
        yes=gate is not None and float(d['nis'])<=gate
        if yes:x,P=y,C
        X.append(x.copy());PP.append(P.copy());NN.append(float(d['nis']))
        A.append(yes);HH.append(d['H']);CC.append(bool(d['clip']))
    return {k:np.asarray(v) for k,v in dict(X=X,P=PP,prior_X=PX,prior_P=PC,nis=NN,accepted=A,H=HH,clip=CC,F=FS).items()}

def run_mixture(e,u,z,x0,capacity=2,collapse=False):
    """Two current RF modes with up to K separate histories, K=2 or4.
    At K=2 preserve the most likely history ending in EACH current mode.
    At K=4 keep two per mode. Dropped probability is measured before
    renormalization. Collapse control moment-matches both modes every step.
    """
    K=1 if collapse else capacity
    if not collapse and K not in (2,4):raise ValueError('K must be 2/4')
    n=len(z);xx=x0[None,:].copy();pp=init_cov()[None,:,:];w=np.ones(1)
    modes=np.array([-1]);mode_prob=PI_MODE.copy()
    out={name:np.zeros(shape) for name,shape in {
        'X':(n,4),'P':(n,4,4),'component_X':(n,K,4),'component_P':(n,K,4,4),
        'weights':(n,K),'modes':(n,K),'parents':(n,K),'pool_index':(n,K),
        'counts':(n,),'discarded_mass':(n,),'log_predictive':(n,),
        'p_on':(n,),'clip_count':(n,),'pool_weights':(n,2*max(K,1)),
        'mode_probs':(n,2)}.items()}
    for k in range(n):
        if k:xx,pp=predict(e,xx,pp,u,k)
        yy,cc,d=e.candidate(xx,pp,float(z[k]))
        off,on=log_likelihood(float(z[k]),d['h'],d['S'])
        if collapse:
            pm=PI_MODE if k==0 else mode_prob@T_MODE
            logs=np.log(pm)+np.array([float(off[0]),float(on[0])])
            norm=logsumexp(logs);cw=np.exp(logs-norm)
            cm=np.stack([xx[0],yy[0]]);cp=np.stack([pp[0],cc[0]])
            m,V=mix_moments(cm,cp,cw)
            out['pool_weights'][k,:2]=cw
            xx,pp=m[None,:],V[None,:,:];w=np.ones(1);modes=np.array([-1]);mode_prob=cw
            kept=np.array([0]);parents=np.array([0]);lost=0.
        else:
            pm=np.broadcast_to(PI_MODE,(len(w),2)) if k==0 else T_MODE[modes]
            logs=(np.log(np.maximum(w,1e-300))[:,None]+np.log(pm)+np.stack([off,on],axis=1)).ravel()
            norm=logsumexp(logs);cw=np.exp(logs-norm)
            cm=np.stack([xx,yy],axis=1).reshape(-1,4)
            cp=np.stack([pp,cc],axis=1).reshape(-1,4,4)
            cmode=np.tile(np.array([0,1]),len(w))
            selected=[]
            for mode in (0,1):
                ids=np.where(cmode==mode)[0]
                selected.extend(ids[np.argsort(-cw[ids],kind='stable')[:K//2]].tolist())
            kept=np.array(selected,int);parents=kept//2
            keptmass=float(cw[kept].sum());lost=max(0.,1-keptmass)
            w=cw[kept]/keptmass;xx=cm[kept];pp=cp[kept];modes=cmode[kept]
            m,V=mix_moments(xx,pp,w)
            mode_prob=np.array([w[modes==q].sum() for q in (0,1)])
            out['pool_weights'][k,:len(cw)]=cw
        b=len(w)
        out['X'][k]=m;out['P'][k]=V
        out['component_X'][k,:b]=xx;out['component_P'][k,:b]=pp
        out['weights'][k,:b]=w;out['modes'][k,:b]=modes
        out['parents'][k,:b]=parents;out['pool_index'][k,:b]=kept
        out['counts'][k]=b;out['discarded_mass'][k]=lost
        out['log_predictive'][k]=norm;out['p_on'][k]=mode_prob[1]
        out['mode_probs'][k]=mode_prob;out['clip_count'][k]=np.count_nonzero(d['clip'])
    return out

def replay(e,u,z,start,end,xprior,Pprior,omit=()):
    """Start is already predicted. Each remaining RF id is used at most once.
    All subsequent gates are re-evaluated on this branch, not donor masks.
    """
    omit=set(int(i) for i in omit);x=xprior.copy();P=Pprior.copy()
    X=[];Ps=[];xp=[];pp=[];Fs=[];used=[];lp=[];nis=[]
    for k in range(start,end+1):
        F=np.eye(4)
        if k>start:
            _,F,_=e.core.transition(x,float(u['ds_odom'][k]),float(u['dtheta_gyro'][k]),float(u['dt_s'][k]))
            x,P=predict(e,x,P,u,k)
        xp.append(x.copy());pp.append(P.copy());Fs.append(F)
        y,C,d=scalar_candidate(e,x,P,float(z[k]))
        off,on=log_likelihood(float(z[k]),d['h'],d['S'])
        lp.append(float(np.logaddexp(np.log(.1)+off,np.log(.9)+on)))
        yes=k not in omit and float(d['nis'])<=GATE
        if yes:x,P=y,C
        X.append(x.copy());Ps.append(P.copy());used.append(yes);nis.append(float(d['nis']))
    return {key:np.asarray(val) for key,val in dict(X=X,P=Ps,prior_X=xp,prior_P=pp,F=Fs,accepted=used,log_score=lp,nis=nis).items()}

def rts(window):
    """Extended RTS backward pass using stored causal linearizations.
    No window posterior reused as an additional prior or observation.
    """
    x=window['X'].copy();P=window['P'].copy()
    for i in range(len(x)-2,-1,-1):
        C=np.linalg.solve(window['prior_P'][i+1],window['F'][i+1]@window['P'][i]).T
        delta=x[i+1]-window['prior_X'][i+1];delta[2]=wrap(delta[2])
        x[i]=window['X'][i]+C@delta;x[i,2]=wrap(x[i,2])
        P[i]=window['P'][i]+C@(P[i+1]-window['prior_P'][i+1])@C.T
        P[i]=(P[i]+P[i].T)/2
    return x,P

def window_info(e,u,x0,P0,z_full,z_los,start,n,rho=0.):
    """4-state initial-condition information, conditional on the window controls.
    Marginalize motion process noise into cross-time observation covariance.
    Prior-conditioned heading/bias info and prior-free nuisance-adjusted info
    are reported separately. c_B has no prior (unknown constant).
    """
    x=x0.copy();Phi=np.eye(4);C=np.zeros((n,4,n,4));G=[];H=[];hs=[];clips=0
    for j in range(n):
        k=start+j
        if j:
            yn,F,B=e.core.transition(x,float(u['ds_odom'][k]),float(u['dtheta_gyro'][k]),float(u['dt_s'][k]))
            Q=np.diag([2e-5*abs(u['ds_odom'][k]),np.deg2rad(.015)**2*u['dt_s'][k],0.])
            for i in range(j):
                C[j,:,i,:]=F@C[j-1,:,i,:];C[i,:,j,:]=C[j,:,i,:].T
            C[j,:,j,:]=F@C[j-1,:,j-1,:]@F.T+B@Q@B.T
            x=yn;Phi=F@Phi
        h,J,clip=e.observe(x);hs.append(float(h));H.append(J);G.append(J@Phi);clips+=int(clip)
    G=np.asarray(G);H=np.asarray(H)
    V=R*rho**np.abs(np.arange(n)[:,None]-np.arange(n)[None,:])
    for i in range(n):
        for j in range(n):V[i,j]+=H[i]@C[i,:,j,:]@H[j]
    L=np.linalg.cholesky(V)
    W=np.linalg.solve(L,G);a=np.linalg.solve(L,np.ones(n))
    q=a/np.linalg.norm(a);B=W-q[:,None]*(q@W)[None,:]
    J=W.T@W;Jc=B.T@B
    # Nuisance elimination computed a second way in the independent auditor.
    P1=np.linalg.inv(np.linalg.inv(P0)+J);Pc=np.linalg.inv(np.linalg.inv(P0)+Jc)
    raw_info=1/np.diag(P1)-1/np.diag(P0)
    proj_info=1/np.diag(Pc)-1/np.diag(P0)
    def conditional(A,target):
        N=np.delete(A,target,axis=1)
        U,sv,_=np.linalg.svd(N,full_matrices=False)
        rank=int(np.sum(sv>max(sv[0] if len(sv) else 0.,1e-30)*1e-10))
        y=A[:,target];res=y-U[:,:rank]@(U[:,:rank].T@y)
        return float(res@res)
    scale=np.diag([.1,.1,np.deg2rad(5),np.deg2rad(.1)])
    sv=np.linalg.svd(B@scale,compute_uv=False)
    # Endpoint information: motion noise is correlated with the observations.
    # Do NOT merely propagate the initial posterior and re-add independent Q.
    Pend=Phi@P0@Phi.T+C[n-1,:,n-1,:]
    E=Phi@P0@G.T
    for i in range(n):E[:,i]+=C[n-1,:,i,:]@H[i]
    Y=G@P0@G.T+V
    Yi=np.linalg.solve(Y,np.eye(n));yo=Yi@np.ones(n)
    PE=Pend-E@Yi@E.T
    PEC=Pend-E@(Yi-np.outer(yo,yo)/(np.ones(n)@yo))@E.T
    end_raw=1/np.diag(PE)-1/np.diag(Pend)
    end_proj=1/np.diag(PEC)-1/np.diag(Pend)
    er=np.asarray(z_full[start:start+n])-np.asarray(z_los[start:start+n])
    # Retain residual diagnostics, no GT/CIR enters construction of H or J.
    row=dict(start=start,end=start+n-1,n=n,rho=rho,clip=clips,
        endpoint_heading_info_raw=float(end_raw[2]),endpoint_heading_info_projected=float(end_proj[2]),
        endpoint_heading_ratio=float(end_proj[2]/end_raw[2]) if end_raw[2]>1e-10 else np.nan,
        endpoint_bias_ratio=float(end_proj[3]/end_raw[3]) if end_raw[3]>1e-10 else np.nan,
        heading_info_raw=float(raw_info[2]),heading_info_projected=float(proj_info[2]),
        heading_prior_ratio=float(proj_info[2]/raw_info[2]) if raw_info[2]>1e-10 else np.nan,
        bias_info_raw=float(raw_info[3]),bias_info_projected=float(proj_info[3]),
        bias_prior_ratio=float(proj_info[3]/raw_info[3]) if raw_info[3]>1e-10 else np.nan,
        heading_schur_raw=conditional(W,2),heading_schur_projected=conditional(B,2),
        bias_schur_raw=conditional(W,3),bias_schur_projected=conditional(B,3),
        scaled_rank=int(np.sum(sv>sv[0]*1e-8)) if sv[0]>0 else 0,
        scaled_condition=float(sv[0]/sv[-1]) if sv[-1]>1e-18 else np.nan,
        discrepancy_mean=float(er.mean()),discrepancy_std=float(er.std()),
        discrepancy_rms=float(np.sqrt(np.mean(er**2))),
        discrepancy_centered_fraction=float(np.sum((er-er.mean())**2)/np.sum(er**2)) if er@er>1e-20 else np.nan,
        monotonic_min_eig=float(np.linalg.eigvalsh(Pc-P1).min()))
    audit=dict(G=G,V=V,P0=P0,J=J,Jc=Jc,P1=P1,Pc=Pc,Pend=Pend,E=E,Y=Y,PE=PE,PEC=PEC)
    return row,audit
