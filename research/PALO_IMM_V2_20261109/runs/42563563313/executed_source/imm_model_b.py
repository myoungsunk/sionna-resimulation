"""V2-B adds exactly one persistent RF offset to the two-mode IMM.
G: original physical state measurement, inactive c reset independent.
C: c evolves AR(1), observed as s=h(x)+c+noise; x-c covariance retained.
No reference or true bias input. rho=0 must recover V2-A physical marginals.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.special import logsumexp
from imm_model_a import RS,wrap,moments,interact,gaussian

def motion_F(x,c,k):
    if k==0:return np.eye(4)
    ds=float(c['ds_odom'][k]);dt=float(c['dt_s'][k]);a=float(c['dtheta_gyro'][k])-x[3]*dt
    if abs(a)<1e-4:
        a2=a*a;v=1-a2/24+a2*a2/1920-a2**3/322560;dv=-a/12+a**3/480-a**5/53760
    else:
        h=a/2;v=math.sin(h)/h;dv=(h*math.cos(h)-math.sin(h))/(2*h*h)
    phi=x[2]+a/2;u=np.array([math.cos(phi),math.sin(phi)]);up=np.array([-u[1],u[0]])
    d=ds*v*u;g=ds*(dv*u+v*up/2);F=np.eye(4)
    F[:2,2]=[-d[1],d[0]];F[:2,3]=-dt*g;F[2,3]=-dt
    return F

def predict5(x,P,c,k,j,rho,Vc,predict,jacobian=motion_F):
    y,V=predict(x[:4],P[:4,:4],c,k)
    out=np.r_[y,0.];cov=np.zeros((5,5));cov[:4,:4]=V
    if j==0:
        cov[4,4]=Vc
    else:
        r=0. if k==0 else rho
        F=jacobian(x[:4],c,k)
        out[4]=r*x[4];cov[:4,4]=r*(F@P[:4,4]);cov[4,:4]=cov[:4,4]
        cov[4,4]=r*r*P[4,4]+(1-r*r)*Vc
    return out,(cov+cov.T)/2

def run(z,controls,x0,P0,predict,observe,T,pi0,Rc,kind='imm',rho=0.,stop=None,jacobian=motion_F):
    if kind not in ('imm','collapse') or not (0<=rho<1) or Rc<=RS:raise ValueError('invalid model settings')
    z=np.asarray(z,float);N=len(z) if stop is None else stop
    if not np.isfinite(z[:N]).all() or np.any(abs(z[:N])>1+1e-12):raise ValueError('invalid s')
    pi0=np.asarray(pi0,float)
    if pi0.shape!=(2,) or min(pi0)<=0 or abs(sum(pi0)-1)>1e-12:raise ValueError('initial mass')
    Vc=Rc-RS;start=np.r_[x0,0.];cov=np.zeros((5,5));cov[:4,:4]=P0;cov[4,4]=Vc
    xs=np.repeat(start[None,:],2,0);Ps=np.repeat(cov[None,:,:],2,0);logmu=np.log(pi0)
    out={name:np.empty(shape) for name,shape in {
        'X':(N,5),'P':(N,5,5),'mode_X':(N,2,5),'mode_P':(N,2,5,5),
        'prior_X':(N,2,5),'prior_P':(N,2,5,5),'weights':(N,2),
        'logweights':(N,2),'logprior':(N,2),'omega':(N,2,2),
        'H':(N,2,5),'nu':(N,2),'S':(N,2),'nis':(N,2),'logL':(N,2),
        'K':(N,2,5),'resultant':(N,),'logevidence':(N,)}.items()}
    for k in range(N):
        mx,mP,lp,omega=interact(xs,Ps,logmu,T)
        for j in range(2):
            xp,pv=predict5(mx[j],mP[j],controls,k,j,rho,Vc,predict,jacobian)
            h,H,clip=observe(xp[:4])
            if clip:raise ValueError(f'LUT outside domain k={k},mode={j}')
            Hg=np.r_[H,float(j)]
            y,V,d=gaussian(xp,pv,z[k],h+j*xp[4],Hg,RS)
            xs[j]=y;Ps[j]=V
            for key,value in [('prior_X',xp),('prior_P',pv),('H',Hg)]:out[key][k,j]=value
            for key in ('nu','S','nis','K'):out[key][k,j]=d[key]
            out['logL'][k,j]=d['ll']
        lpost=lp+out['logL'][k];normal=logsumexp(lpost);logmu=lpost-normal;w=np.exp(logmu)
        x,P,r=moments(xs,Ps,w)
        out['X'][k]=x;out['P'][k]=P;out['weights'][k]=w
        out['logweights'][k]=logmu;out['logprior'][k]=lp;out['omega'][k]=omega
        out['logevidence'][k]=normal;out['resultant'][k]=r
        out['mode_X'][k]=xs;out['mode_P'][k]=Ps
        if kind=='collapse':xs[:]=x;Ps[:]=P
    out['T']=np.asarray(T);out['pi0']=pi0;out['Rc']=np.array(Rc);out['rho_C']=np.array(rho)
    return out
