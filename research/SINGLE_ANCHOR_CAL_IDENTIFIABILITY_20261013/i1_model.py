"""Deterministic mean and sensitivity, plus correlated tangent-noise whitening."""
import numpy as np
from replay import ROOT
from qclean_uwb.drivesim.filter_v2 import transition, odometry_model, correlated_update

CAL=[3,5]; NUIS=[0,1,2,4]

def forward(theta, inputs, anchor, use_range=True, jac=False):
    dt,d,g=inputs['dt'],inputs['d'],inputs['g']
    b=.287; den=1+theta[4]
    a=(g-theta[3]*dt)/den
    u=d-theta[5]*b*a/4
    yaw=theta[2]+np.cumsum(a); mid=yaw-a/2
    si=np.sinc(a/(2*np.pi))
    xy=theta[:2]+np.cumsum(np.column_stack([u*si*np.cos(mid),u*si*np.sin(mid)]),axis=0)
    pose=np.column_stack([xy,yaw])
    h=(1-theta[5]**2/4)*a+theta[5]*d/b
    delta=xy-np.array(anchor[:2]); r=np.sqrt(np.sum(delta**2,axis=1)+(anchor[2]-.45)**2)
    values=np.column_stack([h,r]) if use_range else h[:,None]
    if not jac:return values,pose
    da=np.zeros((len(dt),6));da[:,3]=-dt/den;da[:,4]=-a/den
    du=-theta[5]*b/4*da;du[:,5]-=b*a/4
    dm=np.cumsum(da,axis=0)-da/2;dm[:,2]+=1
    half=a/2; sp=np.zeros_like(a); small=abs(half)<1e-5
    sp[small]=-half[small]/3+half[small]**3/30
    sp[~small]=(half[~small]*np.cos(half[~small])-np.sin(half[~small]))/half[~small]**2
    dl=si[:,None]*du+u[:,None]*sp[:,None]*da/2
    jx=np.cumsum(np.cos(mid)[:,None]*dl-(u*si*np.sin(mid))[:,None]*dm,axis=0);jx[:,0]+=1
    jy=np.cumsum(np.sin(mid)[:,None]*dl+(u*si*np.cos(mid))[:,None]*dm,axis=0);jy[:,1]+=1
    jh=(1-theta[5]**2/4)*da;jh[:,5]+=-theta[5]*a/2+d/b
    jr=(delta[:,0,None]*jx+delta[:,1,None]*jy)/r[:,None]
    J=np.stack([jh,jr],axis=1) if use_range else jh[:,None,:]
    return values,pose,J

def build_whitener(theta, inputs, anchor, spec, use_range):
    """Initial parameters deterministic. Marginalize propagated input noise only.

    Whitening operates on raw deterministic observation residuals, maintaining
    a conditional noise-state mean. Q is fixed at the nominal design.
    """
    values,pose,J=forward(theta,inputs,anchor,use_range,True)
    n=len(pose); P=np.zeros((6,6)); ops=[]; rows=[]
    for k in range(n):
        F=np.eye(6)
        if k:
            xp=np.r_[pose[k-1],theta[3:]]
            d,g,o,dt=inputs['d'][k],inputs['g'][k],inputs['o'][k],inputs['dt'][k]
            _,F,G=transition(xp,d,g,dt,.287)
            Q=np.diag([spec['k_s']*abs(d),spec['gyro_N']**2*dt,spec['k_theta']*abs(o)+spec['k_stheta']*abs(d)])
            P=F@P@F.T+G@Q@G.T
            _,H,B=odometry_model(xp,d,g,dt,.287)
            C=-G@Q@B; R=float(B@Q@B);S=float(H@P@H+R+2*H@C)
            if S<=0:raise ValueError('degenerate odometry innovation')
            K=(P@H+C)/S
            _,P,_=correlated_update(np.zeros(6),P,H,0,R,C)
            ops.append((k,0,F,H,K,np.sqrt(S)));rows.append(J[k,0])
            F=np.eye(6)
        if use_range:
            H=np.zeros(6);H[:2]=(pose[k,:2]-anchor[:2])/values[k,1]
            R=spec['range_sigma_m']**2;S=float(H@P@H+R);K=P@H/S
            _,P,_=correlated_update(np.zeros(6),P,H,0,R,np.zeros(6))
            ops.append((k,1,F,H,K,np.sqrt(S)));rows.append(J[k,1])
    return ops,values,J

def whiten(residual,ops):
    vector=residual.ndim==2
    if vector:residual=residual[...,None]
    e=np.zeros((6,residual.shape[-1]));out=[]
    for k,j,F,H,K,std in ops:
        e=F@e; innovation=residual[k,j]-H@e
        out.append(innovation/std);e+=K[:,None]*innovation
    a=np.array(out)
    return a[:,0] if vector else a

def rank(matrix,rtol):
    s=np.linalg.svd(matrix,compute_uv=False)
    return int(np.sum(s>rtol*s[0])) if len(s) and s[0]>0 else 0

def effective(J,rtol):
    A=J[:,NUIS];B=J[:,CAL]
    U,s,_=np.linalg.svd(A,full_matrices=False)
    keep=s>rtol*s[0] if len(s) and s[0]>0 else np.zeros_like(s,dtype=bool)
    E=B-U[:,keep]@(U[:,keep].T@B)
    M=E.T@E;sv=np.linalg.svd(E,compute_uv=False)
    # Rank relative to the original interest-column scale avoids magnifying roundoff.
    scale=np.linalg.norm(B,2)
    r=int(np.sum(sv>rtol*scale)) if scale>0 else 0
    eig=np.linalg.eigvalsh(M)
    return dict(rank=r,eigenvalues=eig.tolist(),condition=float(eig[-1]/eig[0]) if r==2 and eig[0]>0 else None,matrix=M.tolist(),nuisance_rank=int(keep.sum()))

def augment_prior(J,case,kind,spec):
    result=J.copy();scale=np.array(spec['scales'])
    indices=[]
    if case=='S1' and kind in ('POSE_PRIOR','POSTERIOR'):indices+=list(range(3))
    if kind=='POSTERIOR':indices+=list(range(3,6))
    std=np.array(spec['pose_prior_std']+spec['cal_prior_std'])
    if indices:result=np.vstack([result,np.diag(scale/std)[indices]])
    return result
