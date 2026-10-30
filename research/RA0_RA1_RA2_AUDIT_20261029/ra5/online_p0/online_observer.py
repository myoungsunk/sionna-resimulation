#!/usr/bin/env python3
"""RA5 P0 source-FFD fractional ToA/s0/ds1 observer and prior-only bias model.
No GT access at inference. Same complex source spectrum and fixed tap/peak in
the Jacobian; changing first-edge labels are recorded and NOT differentiated.
"""
from __future__ import annotations
import math
import numpy as np

C0=299792458.
CHI2={2:9.210340371976184,3:11.344866730144373}
def require(cond,message):
    if not cond:raise RuntimeError(message)
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi

def make_cir(H):
    """H (Nposes,Nfreq,2), no extra antenna columns."""
    H=np.asarray(H)
    require(H.ndim==3 and H.shape[2]==2 and H.shape[1]==257,"ERR_CIR_INPUT_SHAPE")
    nf=H.shape[1]
    win=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
    return np.fft.ifft(H*win[None,:,None],n=4*nf,axis=1)*nf

def observer(H,df):
    """One common 30% first-path tap; exactly native strong-port detector."""
    H=np.asarray(H)
    C=make_cir(H);amp=np.abs(C);n,nt,_=amp.shape
    port=np.argmax(amp.max(axis=1),axis=1)
    strong=amp[np.arange(n),:,port]
    peakidx=np.argmax(strong,axis=1)
    peak=strong[np.arange(n),peakidx]
    valid0=np.isfinite(peak)&(peak>0)
    tap=np.argmax(strong>=.3*peak[:,None],axis=1)
    frac,ok,margin=cross_fixed(C,tap,port,peakidx)
    p0=amp[np.arange(n),tap]**2;p1=amp[np.arange(n),np.minimum(tap+1,nt-1)]**2
    den0=p0.sum(axis=1);den1=p1.sum(axis=1)
    valid=valid0&(den0>0)&(den1>0)&(tap+1<nt)
    s0=np.full(n,np.nan);s1=np.full(n,np.nan)
    s0[valid]=(p0[valid,0]-p0[valid,1])/den0[valid]
    s1[valid]=(p1[valid,0]-p1[valid,1])/den1[valid]
    return dict(r_int=tap*C0/(nt*df),
      r_sub=frac*C0/(nt*df),
      s0=s0,ds1=s1-s0,s1=s1,tap=tap,port=port,peakidx=peakidx,
      margin=margin,valid_int=valid,valid_sub=valid&ok,
      power=den0,power_next=den1)
def cross_fixed(cir,tap,port,peakidx):
    """Fractional leading-edge with fixed discrete label, port and peak index."""
    c=np.asarray(cir)
    n,nt,_=c.shape
    t=np.broadcast_to(np.asarray(tap,int),(n,))
    p=np.broadcast_to(np.asarray(port,int),(n,))
    pk=np.broadcast_to(np.asarray(peakidx,int),(n,))
    near=np.clip(t-1,0,nt-1)
    u=np.abs(c[np.arange(n),near,p])
    v=np.abs(c[np.arange(n),np.clip(t,0,nt-1),p])
    peak=np.abs(c[np.arange(n),np.clip(pk,0,nt-1),p])
    threshold=.3*peak
    den=v-u
    good=(t>0)&(t<nt)&np.isfinite(den)&(den>1e-14*max(1.,float(np.max(peak))))&(u<threshold)&(threshold<=v)
    margin=np.minimum(v-threshold,threshold-u)/np.maximum(peak,np.finfo(float).tiny)
    fraction=np.full(n,np.nan)
    fraction[good]=t[good]-1+(threshold[good]-u[good])/den[good]
    return fraction,good,margin
def source_los(model,states,spec):
    """LoS source-predicted r_sub, s0, ds1 and own (reselected) tap."""
    X=np.asarray(states,dtype=float)
    H,_,_,_,_,_=model.spectrum(X,spec,False)
    r=observer(H,float(model.freqs[1]-model.freqs[0]))
    return r
def source_jacobian(model,x,spec):
    """3x4 Jacobian of [LoS r_fractional,s0,ds1] at fixed tap and peak.
    Range derivative is centered FD of the actual fractional-threshold crossing
    functional. The two s Jacobians are analytic gradients of complex powers.
    """
    x=np.asarray(x,float)
    require(x.shape==(4,) and np.isfinite(x).all(),"ERR_SOURCE_STATE")
    h,dh,_,_,_,_=model.spectrum(x[None],spec,True)
    r=observer(h,float(model.freqs[1]-model.freqs[0]))
    require(bool(r["valid_sub"][0]),"ERR_LOS_FRACTIONAL_INVALID")
    C=make_cir(h)
    nf=model.nf
    window=model.window
    dcir=np.fft.ifft(dh*window[None,:,None,None],n=4*nf,axis=1)*nf
    idx=int(r["tap"][0]);i=np.arange(1);port=int(r["port"][0]);pk=int(r["peakidx"][0])
    vals=np.array([r["r_sub"][0],r["s0"][0],r["ds1"][0]],float)
    j=np.zeros((3,4))
    for ix,k in enumerate((idx,idx+1)):
        z=C[0,k];dz=dcir[0,k]
        pw=np.abs(z)**2;dp=2*np.real(np.conj(z)[:,None]*dz)
        ss=float((pw[0]-pw[1])/pw.sum())
        row=(dp[0]-dp[1]-ss*dp.sum(axis=0))/pw.sum()
        if ix==0:j[1]=row
        else:j[2]=row-j[1]
    steps=(1e-4,1e-4,1e-5)
    points=[]
    for k,step in enumerate(steps):
        d=np.zeros(4);d[k]=step
        points.extend((x+d,x-d))
    hp,*_=model.spectrum(np.asarray(points),spec,False)
    cp=make_cir(hp)
    frac,good,_=cross_fixed(cp,np.full(6,idx),np.full(6,port),np.full(6,pk))
    require(bool(np.all(good)),"ERR_FD_CROSSING_DISCONTINUITY")
    for k,step in enumerate(steps):
        j[0,k]=float((frac[2*k]-frac[2*k+1])*C0/(4*nf*(model.freqs[1]-model.freqs[0]))/(2*step))
    # An actual unconditioned first-edge may have changed; must be logged.
    other=observer(hp,float(model.freqs[1]-model.freqs[0]))
    smooth=bool(np.all(other["tap"]==idx) and np.all(other["port"]==port) and
                np.all(other["peakidx"]==pk))
    require(np.isfinite(vals).all() and np.isfinite(j).all(),"ERR_SOURCE_NAN")
    return vals,j,dict(tap=idx,port=port,peakidx=pk,margin=float(r["margin"][0]),
      smooth_active_branch=smooth)
def bias_features(case,x,spec):
    """Analytic online features derived ONLY from current prior 4D state + known anchor/mount."""
    x=np.asarray(x,float).reshape(4)
    a=np.asarray(spec["anchor"][:2],float)
    u=x[0]-a[0];v=x[1]-a[1]
    d=math.sqrt(u*u+v*v+(spec["anchor"][2]-spec["robot_z_m"])**2)
    bearing=math.atan2(-v,-u)
    angle=x[2]+math.radians(float(spec["mount_deg"]))-bearing
    return np.array([1.,d,math.sin(angle),math.cos(angle),math.sin(2*angle),
                     math.cos(2*angle),float("m45" in case),float("aB" in case)])
def fit_bias(features,response,alpha=1.):
    X=np.asarray(features,float);Y=np.asarray(response,float)
    require(X.ndim==2 and X.shape[1]==8 and len(X)==len(Y),"ERR_FIT_SHAPE")
    mu=X[:,1:].mean(axis=0)
    sd=np.maximum(X[:,1:].std(axis=0),1e-12)
    W=np.column_stack([np.ones(len(X)),(X[:,1:]-mu)/sd])
    coeff=np.linalg.solve(W.T@W+np.diag([0.]+[alpha]*7),W.T@Y)
    return dict(center=mu,scale=sd,coeff=coeff)
def predict_bias(fit,case,x,spec):
    f=bias_features(case,x,spec)
    return float(np.r_[1.,(f[1:]-fit["center"])/fit["scale"]]@fit["coeff"])
def predict_bias_jac(fit,case,x,spec):
    val=predict_bias(fit,case,x,spec)
    j=np.zeros(4)
    for k,step in enumerate((1e-4,1e-4,1e-5)):
        v=np.zeros(4);v[k]=step
        j[k]=(predict_bias(fit,case,x+v,spec)-predict_bias(fit,case,x-v,spec))/(2*step)
    return val,j
def quality_bin(margin):
    return "AMBIG" if not np.isfinite(margin) or margin<.02 else "STABLE"
def class_delta(d):
    if d<-2:return "LT_M2"
    if d>2:return "GT_P2"
    return str(int(d))
CATEGORIES=("-2","-1","0","1","2","LT_M2","GT_P2")
def fit_categorical(delta,quality):
    """Train-only Dirichlet-smoothed delta-tap classes conditional on observed edge quality."""
    d=np.asarray(delta,int);q=np.asarray(quality)
    res={}
    for b in ("AMBIG","STABLE"):
        sub=d[q==b]
        counts={c:.5 for c in CATEGORIES}
        for v in sub:counts[class_delta(v)]+=1
        total=sum(counts.values())
        res[b]=dict(n=int(len(sub)),p={k:float(v/total) for k,v in counts.items()})
    return res
def fit_covariance(X,quality,shrink=.15):
    """Measured response-minus-LoS mean residual, source-route-only, NOT hardware R."""
    X=np.asarray(X,float);q=np.asarray(quality)
    require(X.ndim==2 and X.shape[1]==3 and len(X)>400,"ERR_TRAIN_COV_SHAPE")
    result={}
    base=np.cov(X,rowvar=False)
    for b in ("AMBIG","STABLE"):
        sub=X[q==b]
        C=np.cov(sub,rowvar=False) if len(sub)>=100 else base
        C=.75*C+.25*base
        C=(1-shrink)*C+shrink*np.diag(np.diag(C))
        C=.5*(C+C.T)
        eig=np.linalg.eigvalsh(C)
        require(np.all(np.isfinite(C)) and eig[0]>1e-10,"ERR_R_NOT_PD_"+b+" "+str(eig))
        result[b]=dict(n=int(len(sub)),R3=C,R2=C[:2,:2],
                       eigen_min=float(eig[0]),condition=float(np.linalg.cond(C)))
    return result
