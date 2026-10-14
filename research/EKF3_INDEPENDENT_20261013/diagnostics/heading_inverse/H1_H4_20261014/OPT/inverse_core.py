import math
import numpy as np
TAU=2*np.pi

def wrap(v):return (np.asarray(v)+np.pi)%TAU-np.pi

def curve(lut,case,xy):
    u,v=np.asarray(xy)-np.asarray(case['anchor'][:2]);h=case['anchor'][2]-case['robot_z_m']
    th=np.degrees(np.arctan2(np.hypot(u,v),h));tx=np.degrees(np.arctan2(-v,u))
    az=np.degrees(np.arctan2(-v,-u))-case['mount_deg']
    psi=np.sort(np.radians((az-lut.phi+180)%360-180));psi=np.r_[psi,psi[0]+TAU]
    rx=(az-np.degrees(psi)+180)%360-180
    values=np.asarray(lut(th,tx,rx),float)
    return psi,values,bool(th<lut.theta[0] or th>=lut.theta[-1]),float(th)

def inverse(x,y,z,sigma,prior=None,truth=None):
    x=np.asarray(x);y=np.asarray(y);dx=np.diff(x);dy=np.diff(y)
    assert np.all(dx>0) and abs(x[-1]-x[0]-TAU)<1e-10 and abs(y[-1]-y[0])<1e-10
    if not np.isfinite(z):return dict(valid=False,reason='MISSING')
    flat=np.abs(dy)<=1e-14;onflat=flat&(np.abs(y[:-1]-z)<=1e-12)
    roots=list(x[:-1][np.abs(y[:-1]-z)<=1e-12]);ratio=np.divide(z-y[:-1],dy,out=np.full_like(dy,np.nan),where=~flat)
    mask=(ratio>0)&(ratio<1)&~flat
    roots.extend(x[:-1][mask]+ratio[mask]*dx[mask]);roots=np.sort(wrap(roots))
    if len(roots):
        roots=roots[np.r_[True,np.diff(roots)>1e-10]]
        if len(roots)>1 and TAU-roots[-1]+roots[0]<1e-10:roots=roots[:-1]
    tol=1.96*sigma
    aa=np.divide(z-tol-y[:-1],dy,out=np.zeros_like(dy),where=~flat)
    bb=np.divide(z+tol-y[:-1],dy,out=np.zeros_like(dy),where=~flat)
    lo=np.maximum(0,np.minimum(aa,bb));hi=np.minimum(1,np.maximum(aa,bb))
    lo[flat]=0;hi[flat]=np.where(np.abs(y[:-1][flat]-z)<=tol,1,-1)
    hit=hi>=lo
    intervals=[]
    for a,b in zip((x[:-1]+lo*dx)[hit],(x[:-1]+hi*dx)[hit]):
        if intervals and a<=intervals[-1][1]+1e-12:intervals[-1][1]=max(intervals[-1][1],float(b))
        else:intervals.append([float(a),float(b)])
    components=len(intervals)
    if components>1 and intervals[0][0]<=x[0]+1e-12 and intervals[-1][1]>=x[-1]-1e-12:components-=1
    width=float(sum(b-a for a,b in intervals))
    gaps=np.diff(np.r_[roots,roots[0]+TAU]) if len(roots)>1 else np.array([])
    row=dict(valid=True,root_count=len(roots),flat_solution=bool(onflat.any()),no_exact_solution=not len(roots) and not onflat.any(),
        roots_deg=np.degrees(roots).tolist(),root_gaps_deg=np.degrees(gaps).tolist(),band_width_deg=math.degrees(width),band_components=components,
        band_intervals_deg=np.degrees(intervals).tolist(),minimum_residual=float(max(y.min()-z,z-y.max(),0)),
        selected_heading_deg=np.nan,selected_error_deg=np.nan,oracle_error_deg=np.nan,selected_not_oracle=np.nan,selection_ties=0,band_truth=np.nan,
        flat_intervals_deg=np.degrees(np.column_stack([x[:-1][onflat],x[1:][onflat]])).tolist())
    if truth is not None:
        yt=np.interp((truth-x[0])%TAU+x[0],x,y);row['band_truth']=bool(abs(z-yt)<=tol+1e-12)
        if len(roots):row['oracle_error_deg']=float(np.degrees(np.min(abs(wrap(roots-truth)))))
    # Flat intervals cannot be represented by an arbitrary endpoint point estimate.
    if prior is not None and len(roots) and not onflat.any():
        d=abs(wrap(roots-prior));j=int(np.argmin(d));row['selected_heading_deg']=math.degrees(roots[j]);row['selection_ties']=int(np.sum(abs(d-d[j])<1e-10))
        if truth is not None:
            err=abs(wrap(roots-truth));row['selected_error_deg']=float(np.degrees(wrap(roots[j]-truth)))
            row['selected_not_oracle']=bool(err[j]>err.min()+1e-10)
    return row

def propagated_cov(p,psi,ds,da,dt):
    half=da/2;small=abs(half)<1e-4
    sc=np.sinc(half/np.pi)
    sd=np.empty_like(half);t=half[small];sd[small]=-t/3+t**3/30-t**5/840
    t=half[~small];sd[~small]=(t*np.cos(t)-np.sin(t))/(t*t)
    direction=np.column_stack([np.cos(psi+half),np.sin(psi+half)]);perp=np.column_stack([-direction[:,1],direction[:,0]])
    F=np.tile(np.eye(3),(len(p),1,1));F[:,:2,2]=(ds*sc)[:,None]*perp
    G=np.zeros((len(p),3,2));G[:,:2,0]=sc[:,None]*direction;G[:,:2,1]=ds[:,None]/2*(sd[:,None]*direction+sc[:,None]*perp);G[:,2,1]=1
    q=np.column_stack([2e-5*abs(ds),np.radians(.015)**2*dt])
    out=F@p@F.transpose(0,2,1)+(G*q[:,None,:])@G.transpose(0,2,1)
    return (out+out.transpose(0,2,1))/2
