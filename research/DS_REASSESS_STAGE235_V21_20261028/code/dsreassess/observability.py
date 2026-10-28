"""Local finite-window *data-only* Fisher observability for 4-/5-state EKF.

Every returned eigenvalue assumes locally linear, temporally independent
Gaussian observations. None is an empirically validated localization RMSE.
"""
from __future__ import annotations
import math
import numpy as np
from .io import Context,CaseData
from .numerics import transition, range_h, DEG


def coherent_window(ctx:Context,d:CaseData,span,nominal='GT'):
    """Dynamically consistent nominal motion, avoiding spurious gauge breaking.

    Stitching independently observed GT or posterior states while multiplying
    only motion F is WRONG: consecutive nominal points do not satisfy f(x,u).
    Instead initialize at GT (diagnostic) or BASE prior at the window start,
    and roll forward using the *same recorded odometry* with no RF updates.
    """
    if nominal not in ('GT','PRIOR'):
        raise ValueError('invalid nominal source')
    if not hasattr(ctx,'_coherent_window_cache'):
        ctx._coherent_window_cache={}
    key=(d.case['id'],d.bias,span[1],span[2],nominal)
    if key in ctx._coherent_window_cache:
        return ctx._coherent_window_cache[key]
    s,e=span[1:]
    x0=(d.truth[s] if nominal=='GT' else d.ref['prior'][s,0]).copy()
    X=np.empty((e-s,4))
    PHI=np.empty((e-s,4,4))
    x=x0.copy();T=np.eye(4)
    for k in range(s,e):
        if k>s:
            x,F,_=transition(x,float(d.controls['ds_odom'][k]),
                               float(d.controls['dtheta_gyro'][k]),
                               float(d.controls['dt_s'][k]))
            T=F@T
        X[k-s]=x
        PHI[k-s]=T
    H4=np.empty((e-s,2,4))
    for a in range(0,e-s,32):
        b=min(e-s,a+32)
        _,H=ctx.model.batch(X[a:b],d.case)
        H4[a:b]=H
    val=(X,PHI,H4)
    ctx._coherent_window_cache[key]=val
    return val


def first_pass_windows(ctx:Context,d:CaseData):
    p=ctx.first_pass(d.case['id'],d.bias)
    t=d.t
    def win(label,mask):
        idx=np.flatnonzero(mask)
        return (label,int(idx[0]),int(idx[-1]+1)) if len(idx)>=6 else None
    spans=[
      win('first_pass_window',(t>=float(p['window_start_s'])-1e-8)&(t<=float(p['window_end_s'])+1e-8)),
      win('first_pass_post',(t>=float(p['post_start_s'])-1e-8)&(t<=float(p['post_end_s'])+1e-8)),
      win('t_ge_30',t>=30),
    ]
    return [x for x in spans if x is not None]


def state_scale(n):
    # D maps scaled dimensionless perturbations to physical state units.
    q=[1.,1.,math.radians(5.),math.radians(.1)]
    if n==5:q.append(.10)
    return np.diag(q)


def eig_summary(W,Phi_end,geom_u_t,gauge,n):
    D=state_scale(n)
    A=(D.T @ W @ D)
    A=(A+A.T)/2
    lam,V=np.linalg.eigh(A)
    if np.min(lam)<-1e-7*max(1.,abs(lam).max()):
        raise RuntimeError('Fisher matrix not PSD')
    lam=np.maximum(lam,0.)
    largest=max(float(lam[-1]),1e-30)
    cutoff=max(largest*1e-8,1e-12)
    valid=lam>cutoff
    rank=int(valid.sum())
    gn=np.linalg.solve(D,gauge)
    gn/=max(float(np.linalg.norm(gn)),1e-20)
    gauge_strength=max(0.,float(gn@A@gn))
    # Terminal tangential uncertainty from initial-state Fisher, not simply W_xy^-1.
    l=np.zeros(n);l[:2]=geom_u_t
    target=D.T @ Phi_end.T @ l
    proj=V.T@target
    null_fraction=float(np.linalg.norm(proj[~valid])/max(np.linalg.norm(proj),1e-30))
    if null_fraction>1e-5:
        sigma_t=float('inf')
    else:
        sigma_t=float(np.sqrt(np.sum((proj[valid]**2)/lam[valid]))) * 100.
    return {'rank':rank,'dimension':n,'lambda_min':float(lam[0]),
            'lambda_max':float(lam[-1]),
            'condition_number':float(lam[-1]/lam[0]) if lam[0]>cutoff else float('inf'),
            'null_target_fraction':null_fraction,
            'sigma_terminal_tan_cm':sigma_t,
            'gauge_strength_normalized':gauge_strength,
            'gauge_rayleigh_over_lambda_max':gauge_strength/largest,
            'eigenvalues':lam.tolist()}


def fisher(ctx:Context,d:CaseData, *, span:tuple,nominal='GT',anchors=None,
           use_pol=False,use_prior=False,bias5=False,measurement_filter='A_B',
           diagnostics=None):
    """Anchor geometry counterfactual; DO NOT pair relocated-anchor range with measured s.

    `use_pol=True` is valid only when the *original* anchor is retained.
    `anchors` is [(x,y,z),...] and assumes independent same-Rrr range errors.
    A_B is frozen from original experiment, not recomputed for hypothetical anchors.
    """
    if measurement_filter!='A_B':raise ValueError('only frozen A_B permitted')
    s,e=span[1:]
    X,PHI,H4=coherent_window(ctx,d,span,nominal)
    n=5 if bias5 else 4
    default=np.asarray(d.case['anchor'],float)
    if anchors is None:anchors=[default]
    anchors=[np.asarray(a,float) for a in anchors]
    if use_pol and not any(np.allclose(a,default,atol=1e-12,rtol=0) for a in anchors):
        raise ValueError('Cannot reuse original-anchor RF polarization for relocated-only setup')
    P0=d.ref['Pprior'][s,0]
    if bias5:
        P5=np.zeros((5,5));P5[:4,:4]=P0
        P5[4,4]=ctx.cfg.augmented_br_prior_std_m**2
        P0=P5
    W=np.zeros((n,n))
    for local,k in enumerate(range(s,e)):
        if not bool(d.mask[k]):continue
        Phi4=PHI[local]
        if bias5:
            Phi=np.eye(5);Phi[:4,:4]=Phi4
        else:
            Phi=Phi4
        rows=[];variances=[]
        for a in anchors:
            _,Hrange4=range_h(X[local,:2],d.case,anchor=a,b_old=d.b_old)
            hr=np.r_[Hrange4,1.0] if bias5 else Hrange4
            rows.append(hr)
            variances.append(float(d.R[k,0,0]))
        if use_pol:
            hs=np.r_[H4[local,1],0.] if bias5 else H4[local,1]
            rows.append(hs)
            variances.append(float(d.R[k,1,1]))
        if not rows:continue
        H=np.stack(rows,axis=0)@Phi
        # Independent measurement hypothesis - deliberate limitation.
        sqrtv=np.sqrt(np.asarray(variances))
        B=H/sqrtv[:,None]
        W+=B.T@B
    if use_prior:
        W+=np.linalg.inv(P0)
    Phi_end=PHI[-1]
    if bias5:
        f5=np.eye(5);f5[:4,:4]=Phi_end
        Phi_end=f5
    p_end=X[-1,:2]
    rad=p_end-default[:2]
    d_horiz=np.linalg.norm(rad)
    if d_horiz<1e-7:
        raise ValueError('undefined terminal tangent reference')
    ut=np.array([-rad[1],rad[0]])/d_horiz
    startxy=X[0,:2]
    gauge=np.zeros(n)
    gauge[:2]=[-(startxy[1]-default[1]), startxy[0]-default[0]]
    gauge[2]=1.
    if diagnostics is not None:
        # Audit snapshot captures the ACTUAL reference Fisher accumulator and
        # associated real-input linearizations; not a second calculation.
        diagnostics.update(W=W.copy(),X=X.copy(),Phi=PHI.copy(),
                           H4=H4.copy(),R=d.R[s:e].copy(),
                           mask=d.mask[s:e].copy(),P0=P0.copy(),
                           anchor=np.array(anchors),s=s,e=e)
    metrics=eig_summary(W,Phi_end,ut,gauge,n)
    del metrics['eigenvalues']
    return {'case':d.case['id'],'bias':d.bias,'window':span[0],
            't_start':float(d.t[s]),'t_end':float(d.t[e-1]),
            'n_packets':int(e-s),'accepted_packets':int(d.mask[s:e].sum()),
            'nominal_initialization':nominal,'trajectory':'coherent_odom_rollout',
            'use_pol':bool(use_pol),'use_prior':bool(use_prior),
            'bias5':bool(bias5),'anchor_count':len(anchors),
            **metrics}
