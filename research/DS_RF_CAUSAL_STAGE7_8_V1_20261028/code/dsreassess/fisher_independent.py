"""Independent, real-input Stage-5 numerical Fisher audit.

Does NOT import/call observability.fisher, eig_summary, coherent_window,
transition, or its analytic transition Jacobian.  Forward kinematics are
written independently and Phi uses centered finite differences at every step.
SourceFFD is the frozen common physical measurement oracle; selected H*Phi
columns are additionally checked against fully perturbed observer rollouts.
"""
from __future__ import annotations
import math
import numpy as np


FD_STEPS=np.array([1e-4,1e-4,2e-6,1e-6],float)


def _wrap(value):
    return (value+math.pi)%(2*math.pi)-math.pi


def _step(x, ds, gyro, dt):
    """Standalone motion function equivalent to the frozen 4-state odometry."""
    y=np.asarray(x,float).copy()
    a=float(gyro-x[3]*dt)
    sinc=math.sin(.5*a)/(.5*a) if abs(a)>1e-7 else 1-a*a/24+a**4/1920
    th=float(x[2]+.5*a)
    y[0]+=ds*sinc*math.cos(th)
    y[1]+=ds*sinc*math.sin(th)
    y[2]=_wrap(float(x[2]+a))
    return y


def _jacobian_numerical(x,ds,gyro,dt):
    J=np.empty((4,4))
    for j,eps in enumerate(FD_STEPS):
        xp=np.asarray(x,float).copy();xm=xp.copy()
        xp[j]+=eps;xm[j]-=eps
        diff=_step(xp,ds,gyro,dt)-_step(xm,ds,gyro,dt)
        diff[2]=_wrap(float(diff[2]))
        J[:,j]=diff/(2*eps)
    return J


def independent_nominal(d,span,nominal):
    s,e=span[1:]
    x=np.asarray(d.truth[s] if nominal=='GT' else d.ref['prior'][s,0],float).copy()
    X=np.empty((e-s,4));PHI=np.empty((e-s,4,4))
    phi=np.eye(4)
    for i,k in enumerate(range(s,e)):
        if i:
            ds=float(d.controls['ds_odom'][k]);gyro=float(d.controls['dtheta_gyro'][k]);dt=float(d.controls['dt_s'][k])
            J=_jacobian_numerical(x,ds,gyro,dt)
            x=_step(x,ds,gyro,dt)
            phi=J@phi
        X[i]=x;PHI[i]=phi
    return X,PHI


def _state_scale(n):
    q=[1.,1.,math.radians(5.),math.radians(.1)]
    if n==5:q.append(.1)
    return np.diag(q)


def independent_fisher(d,span,X,PHI,H4,*,pol,prior,bias5,bias_prior_var=None):
    """Build data likelihood design matrix independently, then SVD/eigen."""
    s,e=span[1:];n=5 if bias5 else 4
    D=_state_scale(n)
    anc=np.asarray(d.case['anchor'],float)
    height=anc[2]-float(d.case['robot_z_m'])
    design=[];rows_k=[]
    for i,k in enumerate(range(s,e)):
        if not bool(d.mask[k]):continue
        dxy=X[i,:2]-anc[:2]
        rr=math.sqrt(float(dxy@dxy)+height*height)
        hr4=np.zeros(4);hr4[:2]=dxy/rr
        hr=np.r_[hr4,1.] if bias5 else hr4
        if bias5:
            phi=np.eye(5);phi[:4,:4]=PHI[i]
            hs=np.r_[H4[i,1],0.]
        else:
            phi=PHI[i];hs=H4[i,1]
        rvar=float(d.R[k,0,0]);svar=float(d.R[k,1,1])
        if rvar<=0 or svar<=0:raise RuntimeError('nonpositive data-only R')
        if abs(float(d.R[k,0,1]))>1e-12 or abs(float(d.R[k,1,0]))>1e-12:
            raise RuntimeError('original Fisher assumes diagonal R')
        design.append((hr@phi)/math.sqrt(rvar))
        rows_k.append((k,'r'))
        if pol:
            design.append((hs@phi)/math.sqrt(svar))
            rows_k.append((k,'s'))
    B=np.asarray(design,float).reshape(-1,n)
    if prior:
        P=np.asarray(d.ref['Pprior'][s,0],float)
        if bias5:
            enlarged=np.zeros((5,5));enlarged[:4,:4]=P
            # Standalone Stage 5 uses the frozen 8 cm prior for this experiment.
            # The caller must supply the exact configured bias prior variance.
            biasvar=bias_prior_var
            if biasvar is None:raise RuntimeError('independent Fisher missing bias prior contract')
            enlarged[4,4]=biasvar
            P=enlarged
        # Cholesky factor L L^T = P^-1, rows L^T whiten the prior.
        LP=np.linalg.cholesky(np.linalg.inv(P)).T
        B=np.vstack([B,LP])
    weighted=B@D
    W=weighted.T@weighted
    W=.5*(W+W.T)
    vals,V=np.linalg.eigh(W)
    if vals.min() < -1e-8*max(float(vals.max()),1.):
        raise RuntimeError('independent Fisher not PSD')
    vals=np.maximum(vals,0.)
    largest=max(float(vals[-1]),1e-30)
    threshold=max(1e-12,largest*1e-8)
    rank=int(np.sum(vals>threshold))
    sv=np.linalg.svd(weighted,compute_uv=False)
    rank_svd=int(np.count_nonzero(sv**2>threshold))
    if rank!=rank_svd:
        raise RuntimeError(f'SVD/eigen rank disagree {rank} != {rank_svd}')
    Phi_end=np.eye(n)
    Phi_end[:4,:4]=PHI[-1]
    rad=X[-1,:2]-anc[:2]
    un=np.linalg.norm(rad)
    if un<1e-7:raise RuntimeError('terminal tangent undefined')
    ut=np.array([-rad[1],rad[0]])/un
    target=np.zeros(n);target[:2]=ut
    target=D.T@Phi_end.T@target
    projection=V.T@target
    null_frac=float(np.linalg.norm(projection[vals<=threshold])/max(np.linalg.norm(projection),1e-30))
    sig=(math.inf if null_frac>1e-5 else
         100*float(np.sqrt(np.sum(projection[vals>threshold]**2/vals[vals>threshold]))))
    start=X[0,:2]-anc[:2]
    gauge=np.zeros(n);gauge[:2]=[-start[1],start[0]];gauge[2]=1.
    gn=np.linalg.solve(D,gauge);gn=gn/np.linalg.norm(gn)
    grel=float(max(0.,gn@W@gn)/largest)
    # Tolerance and state-unit sensitivity are DIAGNOSTICS, not fitted tuning.
    sensitivity={}
    for factor in (.1,10.):
        sensitivity[f'rank_cutoff_x{factor:g}']=int(np.count_nonzero(vals>threshold*factor))
    for factor in (.5,2.):
        q=np.ones(n);q[2]=q[3]=factor
        sensitivity[f'rank_angles_x{factor:g}']=int(np.count_nonzero(
            np.linalg.eigvalsh(np.diag(q)@W@np.diag(q))>
            max(1e-12,float(np.linalg.eigvalsh(np.diag(q)@W@np.diag(q))[-1])*1e-8)))
    out={'rank':rank,'rank_svd':rank_svd,'lambda_min':float(vals[0]),
         'lambda_max':float(vals[-1]),'null_target_fraction':null_frac,
         'sigma_terminal_tan_cm':sig,'gauge_rayleigh_over_lambda_max':grel,
         'min_psd_eigenvalue':float(np.linalg.eigvalsh(W)[0]),
         'sensitivity':sensitivity}
    return out,W,B,rows_k


def fd_chain_samples(ctx,d,span,nominal,X,PHI,H4,*,points=5):
    """Perturb *initial* motion states; validate nonlinear h(f^k(x0)) Jacobian.

    A changed tap/cell is recorded NONSMOOTH, never asserted to satisfy a
    within-cell analytic derivative.  Reuses no observability Jacobian code.
    """
    s,e=span[1:];n=e-s
    choices=np.unique(np.linspace(0,n-1,min(points,n),dtype=int))
    rows=[];stable=0
    x0=np.array(X[0],copy=True)
    for j,eps in enumerate(FD_STEPS):
        xp=x0.copy();xm=x0.copy();xp[j]+=eps;xm[j]-=eps
        pp=xp.copy();pm=xm.copy()
        sampled={}
        for i,k in enumerate(range(s,e)):
            if i:
                ds=float(d.controls['ds_odom'][k]);g=float(d.controls['dtheta_gyro'][k]);dt=float(d.controls['dt_s'][k])
                pp=_step(pp,ds,g,dt);pm=_step(pm,ds,g,dt)
            if i in choices:sampled[i]=(pp.copy(),pm.copy())
        for i in choices:
            p,m=sampled[int(i)]
            source=np.vstack([X[i],p,m])
            hh,_,diag=ctx.model.batch(source,d.case,gradient=False,return_diagnostics=True)
            tap=diag['tap'];cell=diag['cells']
            ok=(int(tap[0])==int(tap[1])==int(tap[2]) and
                np.array_equal(cell[0],cell[1]) and np.array_equal(cell[0],cell[2]))
            fdd=(hh[1]-hh[2])/(2*eps)
            expected=np.asarray(H4[i]@PHI[i][:,j],float)
            # The original SourceFFD range channel remains differentiable.
            rerr=float(abs(fdd[0]-expected[0]))
            serr=float(abs(fdd[1]-expected[1]))
            if rerr>max(.005,abs(expected[0])*.005):
                raise RuntimeError(f'range nonlinear FD chain failure {d.key} {i}/{j}: {rerr}')
            if ok:
                stable+=1
                if serr>max(.02,abs(expected[1])*.005):
                    raise RuntimeError(f'polarization stable FD chain failure {d.key} {i}/{j}: {serr}')
            rows.append({'case':d.case['id'],'bias':d.bias,'window':span[0],
                         'nominal':nominal,'packet_index':int(s+i),
                         't_s':float(d.t[s+i]),'initial_state_axis':('x_m','y_m','psi_rad','bg_rad_s')[j],
                         'tap_cell_stable':bool(ok),'status':'STABLE_PASS' if ok else 'NONSMOOTH_SEPARATE',
                         'hphi_r_fd':float(fdd[0]),'hphi_r_analytic':float(expected[0]),
                         'hphi_s_fd':float(fdd[1]),'hphi_s_analytic':float(expected[1]),
                         'abs_range_error':rerr,'abs_pol_error':serr})
    if stable==0:
        raise RuntimeError(f'NO_STABLE_FD_CHAIN_SAMPLES {d.key}/{span[0]}/{nominal}')
    return rows
