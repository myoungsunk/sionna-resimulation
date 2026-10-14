"""Offline frozen-LUT inference. Oracle arguments are confined to scoring."""
import json,math,sys
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from scipy.optimize import minimize_scalar
from numpy.polynomial.hermite import hermgauss

ROOT=Path(__file__).resolve().parent
REPO=Path('D:/SLAM_bot/artifacts/EKF3_P0_VERIFY_20261013_01a132b7/checkout')
PROJECT=REPO/'research/EKF3_INDEPENDENT_20261013'
sys.path.insert(0,str(PROJECT/'diagnostics'))
import d6_d9_common as c
from qclean_uwb.drivesim.hs_lut import s_model
from qclean_uwb.drivesim.filters import DriveFilter,FilterConfig
C=json.loads((ROOT/'CONTRACT.json').read_text())
RAD=180/np.pi
def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi

def angles(x,case):
    u,v=np.asarray(x)[...,0]-case['anchor'][0],np.asarray(x)[...,1]-case['anchor'][1]
    height=case['anchor'][2]-case['robot_z_m'];rho=np.sqrt(np.maximum(u*u+v*v,1e-12))
    return np.stack([np.arctan2(rho,height)*RAD,np.arctan2(-v,u)*RAD,
        wrap(np.arctan2(-v,-u)-np.asarray(x)[...,2]-case['mount_deg']/RAD)*RAD],axis=-1)

def model(lut,x,case,jac=False):
    return s_model(lut,case['anchor'],case['robot_z_m'],np.asarray(x)[...,0],
        np.asarray(x)[...,1],np.asarray(x)[...,2],case['mount_deg'],with_jac=jac)

def chain(lut,x,case):
    a=angles(x,case);_,g=lut(*a,with_grad=True)
    u,v=x[0]-case['anchor'][0],x[1]-case['anchor'][1]
    h=case['anchor'][2]-case['robot_z_m'];rho2=max(u*u+v*v,1e-12);rho=np.sqrt(rho2)
    da=np.array([[h*u/rho/(rho2+h*h),h*v/rho/(rho2+h*h)],
        [v/rho2,-u/rho2],[-v/rho2,u/rho2]])*RAD
    terms=g[:,None]*da;_,jac=model(lut,x,case,True)
    step=C['finite_difference_step'];num=[]
    for j in range(3):
        d=np.eye(3)[j]*step
        num.append(float((model(lut,x+d,case)-model(lut,x-d,case))/(2*step)))
    cells=np.array([a[0]/lut.dt,(a[1]+180)/lut.dp,(a[2]+180)/lut.dp])
    boundary=bool(np.min(np.abs(cells-np.rint(cells)))<1e-4)
    clipping=bool(a[0]<=lut.theta[0] or a[0]>=lut.theta[-1])
    err=float(np.max(np.abs(jac-np.array(num))))
    if np.max(np.abs(terms.sum(0)-jac[:2]))>1e-10:raise RuntimeError('Chain sum mismatch')
    if not (boundary or clipping) and err>C['jacobian_absolute_tolerance']:
        raise RuntimeError('Jacobian numerical gate '+str(err))
    return terms,np.asarray(jac),err,boundary,clipping

def legacy(lut,x,p,z,case,truth=None):
    grid=np.radians(np.arange(-180,180,.5));body=grid-case['mount_deg']/RAD
    points=np.tile(x,(len(grid),1));points[:,2]=body
    sg=model(lut,points,case);diff=sg-z;roots=[]
    for i in np.flatnonzero((diff==0)|(diff*np.roll(diff,-1)<0)):
        j=(i+1)%len(grid);frac=diff[i]/(diff[i]-diff[j]) if diff[i]!=diff[j] else 0
        roots.append((body[i]+frac*wrap(body[j]-body[i]),
            (sg[j]-sg[i])/(wrap(body[j]-body[i])*RAD)))
    if not roots:return dict(selected=float(x[2]),status='no_root',root_count=0,nearest=None,oracle=None)
    best=min(roots,key=lambda q:abs(wrap(q[0]-x[2])));slope=abs(best[1])
    status='applied';selected=float(x[2]);nis=None
    if slope<.01:status='low_slope'
    else:
        rh=c.RS/(slope*RAD)**2;innov=float(wrap(best[0]-x[2]));nis=innov**2/(p[2,2]+rh)
        if nis>FilterConfig().gate:status='rejected_NIS'
        else:selected=float(wrap(x[2]+p[2,2]/(p[2,2]+rh)*innov))
    oracle=min(roots,key=lambda q:abs(wrap(q[0]-truth[2])))[0] if truth is not None else None
    return dict(selected=selected,status=status,root_count=len(roots),nearest=float(wrap(best[0])),
        oracle=None if oracle is None else float(wrap(oracle)),NIS=nis)

def baseline_parity(lut,x,p,z,case):
    cfg=FilterConfig(s_mode='inverse',anchor_xyz=tuple(case['anchor']),robot_z=case['robot_z_m'],mount_deg=case['mount_deg'])
    pp=np.eye(6);pp[:3,:3]=p;f=DriveFilter(cfg,lut,np.r_[x,0.,0.,0.],pp)
    f._update_inverse_heading(z,c.RS);ours=legacy(lut,x,p,z,case)
    difference=abs(float(wrap(f.comps[0].x[2]-ours['selected'])))
    if difference>C['parity_absolute_tolerance'] or (f.stats['s_updates']==1)!=(ours['status']=='applied'):
        raise RuntimeError('Frozen inverse parity failed')
    return difference

def wrapped_logprior(psi,mean,var):
    if not np.isfinite(var) or var<=0:raise RuntimeError('Invalid heading prior')
    d=wrap(psi-mean);n=max(2,int(np.ceil(8*np.sqrt(var)/(2*np.pi))))
    shifts=np.arange(-n,n+1)*2*np.pi
    return logsumexp(-.5*(d[...,None]+shifts)**2/var,axis=-1)-.5*np.log(2*np.pi*var)

def summarize(grid,logp,logfun=None):
    prob=np.exp(logp-logsumexp(logp));step=2*np.pi/len(grid)
    imax=int(np.argmax(prob));mapangle=float(grid[imax]);sigma=None;local_valid=False
    # Refine every circular local maximum; never rely on a single initial guess.
    peaks=np.flatnonzero((logp>=np.roll(logp,1))&(logp>np.roll(logp,-1)))
    refined=[]
    for i in peaks:
        a=float(grid[i]);b=a
        if logfun is not None:
            opt=minimize_scalar(lambda q:-float(logfun(wrap(q))),bounds=(a-step,a+step),method='bounded',options={'xatol':1e-10})
            b=float(wrap(opt.x));value=float(logfun(b))
        else:value=float(logp[i])
        refined.append((b,value,int(i)))
    if refined:
        mapangle,_,imax=max(refined,key=lambda q:q[1])
    if logfun is not None:
        eps=1e-4;center=float(logfun(mapangle))
        left=float(logfun(wrap(mapangle-eps)));right=float(logfun(wrap(mapangle+eps)))
        curve=(left-2*center+right)/eps**2
        halfcurve=(float(logfun(wrap(mapangle-eps/2)))-2*center+float(logfun(wrap(mapangle+eps/2))))/(eps/2)**2
        local_valid=bool(curve<0 and abs(halfcurve-curve)/max(abs(curve),1e-12)<=C['local_Gaussian_Hessian_relative_agreement'])
        if local_valid:sigma=float(np.sqrt(-1/curve))
    order=np.argsort(prob)[::-1];num=int(np.searchsorted(np.cumsum(prob[order]),.95)+1)
    hpd=np.zeros(len(grid),bool);hpd[order[:num]]=True
    # Assign mass to peaks via adjacent valleys, retaining separated intervals.
    mode_records=[]
    if len(peaks):
        for j,i in enumerate(peaks):
            prev=peaks[(j-1)%len(peaks)];nxt=peaks[(j+1)%len(peaks)]
            if len(peaks)==1:mass=1.
            else:
                seq1=np.arange(prev,i+len(grid) if i<=prev else i+1)%len(grid)
                seq2=np.arange(i,nxt+len(grid) if nxt<=i else nxt+1)%len(grid)
                lo=int(seq1[np.argmin(prob[seq1])]);hi=int(seq2[np.argmin(prob[seq2])])
                idx=np.arange(lo,hi+len(grid) if hi<=lo else hi)%len(grid);mass=float(prob[idx].sum())
            mode_records.append(dict(angle_rad=float(grid[i]),mass=mass))
    intervals=[];starts=np.flatnonzero(hpd&~np.roll(hpd,1))
    if hpd.all():intervals=[[-np.pi,np.pi]]
    for start in starts:
        length=0
        while hpd[(start+length)%len(grid)] and length<len(grid):length+=1
        intervals.append([float(wrap(grid[start]-step/2)),float(wrap(grid[start]+(length-.5)*step))])
    return dict(grid=grid,prob=prob,MAP=mapangle,local_sigma=sigma,local_valid=local_valid,
        hpd=hpd,hpd_width_deg=float(num*step*RAD),hpd_intervals=intervals,modes=mode_records,
        mode_count=sum(m['mass']>=C['mode_min_mass'] for m in mode_records))

def posterior(logfun,*,strict=True):
    prev=None;tv=mapdiff=widthdiff=np.inf
    for n in C['angle_grids']:
        grid=np.linspace(-np.pi,np.pi,n,endpoint=False);lp=np.asarray(logfun(grid))
        if lp.shape!=(n,) or not np.isfinite(lp).all():raise RuntimeError('Invalid posterior density')
        result=summarize(grid,lp,logfun)
        if prev is not None:
            # Compare equal-bin integrated mass, not raw density values.
            # Both grids are centered at the same angles. A coarse bin contains
            # one fine bin and half of each adjacent fine bin, including the seam.
            fine=result['prob']
            coarse=fine[::2]+.5*(np.roll(fine,1)[::2]+np.roll(fine,-1)[::2])
            tv=.5*np.abs(coarse-prev['prob']).sum()
            mapdiff=abs(wrap(result['MAP']-prev['MAP']))*RAD
            widthdiff=abs(result['hpd_width_deg']-prev['hpd_width_deg'])
            if tv<=C['posterior_TV_tolerance'] and mapdiff<=C['MAP_angle_convergence_deg'] and widthdiff<=C['HPD_width_convergence_deg']:
                result.update(angle_grid_n=n,TV=float(tv),MAP_change_deg=float(mapdiff),HPD_width_change_deg=float(widthdiff),converged=True)
                return result
        prev=result
    result.update(angle_grid_n=n,TV=float(tv),MAP_change_deg=float(mapdiff),HPD_width_change_deg=float(widthdiff),converged=False)
    if strict:raise RuntimeError(f'Angular convergence gate TV={tv} MAP={mapdiff} HPD={widthdiff}')
    return result

def fixed_logfun(lut,x,p,z,case,mu=0.,var=c.RS,override_theta=None):
    def fn(psi):
        psi=np.asarray(psi);pts=np.broadcast_to(x,psi.shape+(3,)).copy();pts[...,2]=psi
        if override_theta is None:pred=model(lut,pts,case)
        else:
            a=angles(pts,case);pred=lut(override_theta,a[...,1],a[...,2])
        return -.5*(z-pred-mu)**2/var+wrapped_logprior(psi,x[2],p[2,2])
    return fn

def range_update(x,p,z,case,mu,var,full_cross):
    h,H=c.range_h(x,case['anchor'],case['robot_z_m']);y=z-h-mu;S=H@p@H+var
    if y*y/S>c.GATE_1D_99:return x.copy(),p.copy(),'rejected_NIS'
    gain=p@H/S
    if not full_cross:gain[2]=0
    xp=x+gain*y;xp[2]=wrap(xp[2]);A=np.eye(3)-np.outer(gain,H)
    pp=A@p@A.T+np.outer(gain,gain)*var
    if not full_cross:
        pp[:2,2]=pp[2,:2]=0;pp[2,2]=p[2,2]
    return xp,pp,'applied'

def integrated_logfun(lut,x,p,zs,zr,case,mu,R,order,conditional=False):
    if np.linalg.eigvalsh(R).min()<=0:raise RuntimeError('Invalid RF covariance')
    gh,gw=hermgauss(order);gx,gy=np.meshgrid(gh,gh,indexing='ij')
    nodes=np.stack([gx.ravel(),gy.ravel()],axis=1)*np.sqrt(2)
    lw=np.log(np.outer(gw,gw).ravel()/np.pi)
    varpsi=p[2,2];cross=p[:2,2]/varpsi
    condcov=p[:2,:2]-np.outer(p[:2,2],p[2,:2])/varpsi
    L=np.linalg.cholesky(condcov)
    inv=np.linalg.inv(R)
    def fn(psi):
        psi=np.asarray(psi);flat=psi.reshape(-1);output=[]
        for start in range(0,len(flat),128):
            headings=flat[start:start+128];d=wrap(headings-x[2])
            points=np.empty((len(headings),len(nodes),3))
            points[:,:,:2]=x[:2]+d[:,None,None]*cross+nodes[None]@L.T
            points[:,:,2]=headings[:,None]
            hs=model(lut,points,case)
            hr=np.sqrt(np.sum((points[:,:,:2]-case['anchor'][:2])**2,axis=-1)+(case['robot_z_m']-case['anchor'][2])**2)
            es=zs-hs-mu[0];er=zr-hr-mu[1]
            if conditional:
                alpha=R[0,1]/R[1,1];var=R[0,0]-R[0,1]**2/R[1,1]
                like=-.5*(es-alpha*er)**2/var
            else:like=-.5*(inv[0,0]*es**2+2*inv[0,1]*es*er+inv[1,1]*er**2)
            output.append(logsumexp(like+lw,axis=1)+wrapped_logprior(headings,x[2],varpsi))
        return np.concatenate(output).reshape(psi.shape)
    return fn

def integrated_posterior(lut,x,p,zs,zr,case,mu,R,conditional=False):
    previous=None;probe=np.linspace(-np.pi,np.pi,1440,endpoint=False)
    for order in C['position_quadrature_orders']:
        fn=integrated_logfun(lut,x,p,zs,zr,case,mu,R,order,conditional)
        lp=fn(probe);prob=np.exp(lp-logsumexp(lp))
        if previous is not None:
            tv=float(.5*np.abs(prob-previous).sum())
            if tv<=C['position_quadrature_TV_tolerance']:
                result=posterior(fn);result.update(position_order=order,position_TV=tv);return result
        previous=prob
    raise RuntimeError('Position quadrature convergence gate TV='+str(tv))

def scored(result,truth):
    grid=result['grid'];prob=result['prob'];step=2*np.pi/len(grid)
    index=int(np.floor((float(wrap(truth))+np.pi)/step+.5))%len(grid)
    return dict(MAP_rad=result['MAP'],heading_error_deg=float(wrap(result['MAP']-truth)*RAD),
        opposite_branch=int(abs(wrap(result['MAP']-truth))>np.pi/2),
        hpd95_contains_truth=int(result['hpd'][index]),hpd_width_deg=result['hpd_width_deg'],
        truth_5deg_mass=float(prob[np.abs(wrap(grid-truth))<=5/RAD].sum()),
        mode_count=result['mode_count'],modes_json=json.dumps(result['modes']),
        hpd_intervals_json=json.dumps(result['hpd_intervals']),local_valid=result['local_valid'],
        local_sigma_deg=None if result['local_sigma'] is None else result['local_sigma']*RAD,
        local95_contains_truth=None if result['local_sigma'] is None else int(abs(wrap(result['MAP']-truth))<=1.95996398454*result['local_sigma']),
        angle_grid_n=result['angle_grid_n'],angle_TV=result['TV'],
        position_order=result.get('position_order'),position_TV=result.get('position_TV'))
