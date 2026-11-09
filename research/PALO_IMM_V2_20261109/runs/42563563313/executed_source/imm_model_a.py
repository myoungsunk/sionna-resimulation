"""V2-A: two mode-conditioned EKFs. No labels, scene identifiers or time lookup.
Real-valued Gaussian emission approximation to s in [-1,1], deliberately not
truncated: this preserves the original S4 Gaussian measurement convention.
T[i,j] = P(new mode=j | previous mode=i). G=0; C=1. No pruning or NIS gate.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.special import logsumexp

RS = .0081

def wrap(x):
    return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi

def moments(xs, Ps, w):
    xs, Ps, w = np.asarray(xs),np.asarray(Ps),np.asarray(w)
    if not (np.isfinite(xs).all() and np.isfinite(Ps).all() and np.isfinite(w).all()):
        raise ValueError('nonfinite mixture')
    if np.min(w)<0 or abs(w.sum()-1)>1e-10: raise ValueError('invalid mass')
    x=w@xs
    C=float(w@np.cos(xs[:,2]));S=float(w@np.sin(xs[:,2]))
    resultant=math.hypot(C,S)
    if resultant<1e-12: raise ValueError('undefined circular mixture mean')
    x[2]=math.atan2(S,C)
    d=xs-x; d[:,2]=wrap(d[:,2])
    P=np.sum(w[:,None,None]*(Ps+d[:,:,None]*d[:,None,:]),axis=0)
    return x,(P+P.T)/2,resultant

def interact(xs, Ps, logmu, T):
    T=np.asarray(T,float)
    if T.shape!=(2,2) or np.min(T)<=0 or not np.allclose(T.sum(1),1,rtol=0,atol=1e-12):
        raise ValueError('transition must be positive and row stochastic')
    logjoint=logmu[:,None]+np.log(T)
    logprior=logsumexp(logjoint,axis=0)
    omega=np.exp(logjoint-logprior[None,:])
    mixed=[moments(xs,Ps,omega[:,j]) for j in range(2)]
    return np.array([a[0] for a in mixed]),np.array([a[1] for a in mixed]),logprior,omega

def gaussian(x,P,z,h,H,R):
    """Same scalar Joseph update convention as frozen S4, without a hard gate."""
    if R<=0 or not np.isfinite(z): raise ValueError('invalid measurement')
    H=np.atleast_2d(np.asarray(H,float));nu=np.array([float(z)-float(h)])
    S=H@P@H.T+np.array([[R]])
    S=(S+S.T)/2
    if not np.isfinite(S).all() or S[0,0]<=0: raise ValueError('nonpositive S')
    K=np.linalg.solve(S,H@P).T
    y=x+K@nu;y[2]=wrap(y[2])
    A=np.eye(len(x))-K@H
    V=A@P@A.T+R*K@K.T;V=(V+V.T)/2
    nis=float(nu@np.linalg.solve(S,nu))
    ll=-.5*(math.log(2*np.pi*S[0,0])+nis)
    return y,V,dict(nu=float(nu[0]),S=float(S[0,0]),nis=nis,K=K[:,0],ll=ll)

def run(z,controls,x0,P0,predict,observe,T,pi0,Rc,kind='imm',stop=None):
    """IMM vs immediate collapse: identical emissions, transitions and data."""
    if kind not in ('imm','collapse'): raise ValueError(kind)
    if Rc<=RS: raise ValueError('C variance must exceed G variance')
    z=np.asarray(z,float);N=len(z) if stop is None else stop
    if not np.isfinite(z[:N]).all() or np.any(np.abs(z[:N])>1+1e-12):raise ValueError('invalid s')
    pi0=np.asarray(pi0,float)
    if len(pi0)!=2 or np.min(pi0)<=0 or abs(pi0.sum()-1)>1e-12:raise ValueError('initial probabilities')
    xs=np.repeat(x0[None,:],2,0);Ps=np.repeat(P0[None,:,:],2,0);logmu=np.log(pi0)
    out={name:np.empty(shape) for name,shape in {
        'X':(N,4),'P':(N,4,4),'mode_X':(N,2,4),'mode_P':(N,2,4,4),
        'prior_X':(N,2,4),'prior_P':(N,2,4,4),'weights':(N,2),
        'logweights':(N,2),'logprior':(N,2),'omega':(N,2,2),
        'H':(N,2,4),'nu':(N,2),'S':(N,2),'nis':(N,2),'logL':(N,2),
        'K':(N,2,4),'resultant':(N,),'logevidence':(N,)}.items()}
    for k in range(N):
        mx,mP,lp,omega=interact(xs,Ps,logmu,T)
        for j in range(2):
            xp,pv=predict(mx[j],mP[j],controls,k)
            h,H,clip=observe(xp)
            if clip:raise ValueError(f'LUT outside domain k={k},mode={j}')
            y,V,d=gaussian(xp,pv,z[k],h,H,RS if j==0 else Rc)
            xs[j]=y;Ps[j]=V
            for key,value in [('prior_X',xp),('prior_P',pv),('H',H)]:out[key][k,j]=value
            for key in ('nu','S','nis','K'):out[key][k,j]=d[key]
            out['logL'][k,j]=d['ll']
        lpost=lp+out['logL'][k];normal=logsumexp(lpost);logmu=lpost-normal
        w=np.exp(logmu)
        x,P,r=moments(xs,Ps,w)
        out['X'][k]=x;out['P'][k]=P;out['weights'][k]=w
        out['logweights'][k]=logmu;out['logprior'][k]=lp;out['omega'][k]=omega
        out['logevidence'][k]=normal;out['resultant'][k]=r
        out['mode_X'][k]=xs;out['mode_P'][k]=Ps
        if kind=='collapse':xs[:]=x;Ps[:]=P
    out['T']=np.asarray(T);out['pi0']=pi0;out['Rc']=np.array(Rc)
    return out
