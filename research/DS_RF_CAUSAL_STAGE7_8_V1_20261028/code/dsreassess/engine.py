"""Independent nonlinear replay and full-state scoring. No original EKF calls."""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable
import numpy as np
import pandas as pd
from .numerics import DEG,wrap,propagate,joint_update,augment,range_h,psd_check
from .io import CaseData, Context, StageWriter


@dataclass
class Replay:
    name: str
    x: np.ndarray
    P: np.ndarray
    prior: np.ndarray
    Pprior: np.ndarray
    K: np.ndarray
    H: np.ndarray
    h: np.ndarray
    nu: np.ndarray
    mu: np.ndarray
    R: np.ndarray
    nis: np.ndarray
    acc: np.ndarray
    q_active: np.ndarray
    cut_active: np.ndarray


def replay(ctx:Context, d:CaseData, name:str, *, mu_kind='BASE',
           R_rule:Callable|None=None, cut_rule:Callable|None=None,
           bias_state=False, tangent_q_std=0.0, q_after_exit_s=0.0,
           range_bias_q_std=0.0):
    """Track one independent arm with frozen A_B acceptance.

    Callbacks are evaluated solely from current prior state/observation and
    predetermined t; only explicitly labeled oracle cut reads GT.
    Bias 5th state modeled as additive residual range bias after the fixed mu.
    """
    model=ctx.model
    n=len(d.t)
    nv=5 if bias_state else 4
    x=np.r_[d.x0,0.] if nv==4 else np.r_[d.x0,0.,0.]
    sig_pose=np.asarray(ctx.V.INITIAL_POSE_STD,float)
    sig_bg=float(ctx.V.BIAS_PRIOR_STD)
    sig=(np.r_[sig_pose,sig_bg] if nv==4 else
         np.r_[sig_pose,sig_bg,ctx.cfg.augmented_br_prior_std_m])
    P=np.diag(sig*sig)
    mu0={'BASE':d.mu_b,'EX':d.mu_ex,'EXDS':d.mu_exds,'ORACLE':None}.get(mu_kind)
    if mu_kind not in ('BASE','EX','EXDS','ORACLE'):
        raise ValueError('unknown mu_kind')
    obs={k:np.empty((n,)+shape,float) for k,shape in {
        'x':(nv,),'P':(nv,nv),'prior':(nv,),'Pprior':(nv,nv),
        'K':(nv,2),'H':(2,nv),'h':(2,),'nu':(2,),
        'mu':(2,),'R':(2,2),'nis':()}.items()}
    acc=d.mask.astype(bool).copy()
    q_active=np.zeros(n,bool)
    cut_active=np.zeros(n,bool)
    inside=False
    last_exit=-np.inf
    for k in range(n):
        if k:
            control=d.controls
            dt=float(control['dt_s'][k]);ds=float(control['ds_odom'][k]);gy=float(control['dtheta_gyro'][k])
            # Online geometric switch: detect near-zone exit with *prior* estimate;
            # not GT first-pass windows. Different from CUT_RT oracle timing.
            anc=np.asarray(d.case['anchor'])[:2]
            r_prev=np.linalg.norm(x[:2]-anc)
            now_inside = r_prev<=1.5
            if inside and not now_inside:
                last_exit=float(d.t[k-1])
            inside=now_inside
            q_active[k]=bool(tangent_q_std>0 and (d.t[k]-last_exit)<=q_after_exit_s and not inside)
            x,P,_=propagate(x,P,ds,gy,dt,
                            tangent_q=tangent_q_std**2 if q_active[k] else 0.0,
                            range_bias_q=range_bias_q_std**2 if bias_state else 0.0,
                            anchor_xy=anc)
        else:
            inside=np.linalg.norm(x[:2]-np.asarray(d.case['anchor'])[:2])<=1.5
        obs['prior'][k]=x
        obs['Pprior'][k]=P
        h4,H4=model.batch(x[None,:4],d.case)
        h4=np.asarray(h4[0],float)
        H4=np.asarray(H4[0],float)
        if bias_state:
            h,H=augment(h4,H4,x[4])
        else:
            h,H=h4,H4
        if mu_kind=='ORACLE':
            gt_h,_=range_h(d.truth[k,:2],d.case,b_old=d.b_old)
            mu_r=float(d.z[k,0]-gt_h)
        else:
            mu_r=float(mu0[k])
        mu=np.array([mu_r,d.mu_s[k]])
        R=np.array(d.R[k],copy=True)
        if R_rule is not None:
            R=R_rule(k,x.copy(),np.array(R,copy=True),h.copy(),H.copy())
        ut=None
        if cut_rule is not None:
            ut=cut_rule(k,x.copy(),d)
            cut_active[k]=ut is not None
        upd=joint_update(x,P,d.z[k],h,H,mu,R,acc[k],tangent_cut_xy=ut)
        x,P=upd.x,upd.P
        for key,value in [('x',x),('P',P),('h',h),('H',H),('K',upd.K),('nu',upd.nu),
                          ('mu',mu),('R',R),('nis',upd.nis)]:
            obs[key][k]=value
    return Replay(name,**obs,acc=acc,q_active=q_active,cut_active=cut_active)


def score(d:CaseData, arm:Replay, *, mask=None, scope='scoring'):
    if mask is None:mask=(d.t>=30)
    mask=np.asarray(mask,bool)
    if not mask.any():
        return {'case':d.case['id'],'bias':d.bias,'arm':arm.name,'scope':scope,'n':0,'status':'NO_SAMPLES'}
    e=arm.x[:,:4]-d.truth
    e[:,2]=wrap(e[:,2])
    E=e[mask]
    yaw=DEG*E[:,2]
    dist_gt=np.linalg.norm(d.truth[:,:2]-np.asarray(d.case['anchor'])[:2],axis=1)
    height=float(d.case['anchor'][2]-d.case['robot_z_m'])
    tr=np.sqrt(dist_gt**2+height**2)
    dist_est=np.linalg.norm(arm.x[:,:2]-np.asarray(d.case['anchor'])[:2],axis=1)
    est=np.sqrt(dist_est**2+height**2)
    range_err=(est-tr)[mask]*100
    S=arm.P[mask]
    psi_nees=(E[:,2]**2)/S[:,2,2]
    state_nees=np.array([v@np.linalg.solve(p,v) for v,p in zip(E,S[:,:4,:4])]) if arm.x.shape[1]==4 else np.full(len(E),np.nan)
    # Extended 5-state: 4D marginal consistency is not full state NEES.
    if arm.x.shape[1]==5:
        state_nees=np.array([v@np.linalg.solve(p,v) for v,p in zip(E,S[:,:4,:4])])
    return {'case':d.case['id'],'bias':d.bias,'arm':arm.name,'scope':scope,
            'n':int(mask.sum()),'status':'OK','accepted':int(np.sum(arm.acc[mask])),
            'heading_rmse_deg':float(np.sqrt(np.mean(yaw*yaw))),
            'heading_signed_bias_deg':float(yaw.mean()),
            'heading_std_deg':float(yaw.std()),
            'heading_nees':float(psi_nees.mean()),
            'state4_marginal_nees':float(state_nees.mean()),
            'xy_rmse_m':float(np.sqrt(np.mean(np.sum(E[:,:2]**2,axis=1)))),
            'anchor_range_rmse_cm':float(np.sqrt(np.mean(range_err**2))),
            'gyro_bias_rmse_dps':float(DEG*np.sqrt(np.mean(E[:,3]**2))),
            'mean_sigma_psi_deg':float(np.mean(DEG*np.sqrt(S[:,2,2]))),
            'q_active_accepted':int(np.count_nonzero(arm.q_active[mask]&arm.acc[mask])),
            'cut_active_accepted':int(np.count_nonzero(arm.cut_active[mask]&arm.acc[mask]))}


def geom_series(d:CaseData, arm:Replay):
    anc=np.asarray(d.case['anchor'],float)[:2]
    gr=d.truth[:,:2]-anc
    norm=np.linalg.norm(gr,axis=1)
    if np.min(norm)<1e-9:
        raise RuntimeError('GT horizontal vector zero: radial/tangent undefined')
    ur=gr/norm[:,None]
    ut=np.c_[-ur[:,1],ur[:,0]]
    e=arm.x[:,:2]-d.truth[:,:2]
    beta_gt=np.arctan2(-gr[:,1],-gr[:,0])
    rr=arm.x[:,:2]-anc
    beta_est=np.arctan2(-rr[:,1],-rr[:,0])
    return pd.DataFrame({'case':d.case['id'],'bias':d.bias,'arm':arm.name,
                         't_s':d.t,'pose_id':d.ids,
                         'e_rad_cm':100*np.sum(e*ur,axis=1),
                         'e_tan_cm':100*np.sum(e*ut,axis=1),
                         'e_beta_deg':DEG*wrap(beta_est-beta_gt),
                         'e_psi_deg':DEG*wrap(arm.x[:,2]-d.truth[:,2]),
                         'scoring':d.t>=30,'accepted':arm.acc,
                         'cut_active':arm.cut_active,'q_active':arm.q_active})


def assert_off_parity(writer:StageWriter,d:CaseData,arm:Replay,idx:int):
    ref=d.ref
    mapping={'x':'x','P':'P','prior':'prior','Pprior':'Pprior','K':'K',
             'H':'H','h':'h','nu':'nu','mu':'mu','R':'R','acc':'acc'}
    for field,reference in mapping.items():
        original=ref[reference][:,idx]
        result=getattr(arm,field)
        if field in ('x','prior'):
            err=np.asarray(result)-np.asarray(original)
            err[:,2]=wrap(err[:,2])
            writer.check(d.key+'_'+arm.name+'_'+field,err,np.zeros_like(err),1e-10)
        else:
            writer.check(d.key+'_'+arm.name+'_'+field,result,original,1e-10)
    if not np.array_equal(arm.acc,d.mask):
        raise AssertionError('MASK_FROZEN_A_B violated')


def save_replay(writer:StageWriter,d:CaseData,arm:Replay):
    writer.npz(f'{d.key}_{arm.name}.npz',t_s=d.t,pose_id=d.ids,truth_scoring_only=d.truth,
               z=d.z,case=d.case['id'],bias=d.bias,
               x=arm.x,P=arm.P,prior=arm.prior,Pprior=arm.Pprior,
               K=arm.K,H=arm.H,h=arm.h,nu=arm.nu,mu=arm.mu,R=arm.R,
               nis=arm.nis,acc=arm.acc,q_active=arm.q_active,cut_active=arm.cut_active)


def score_window(d,arm,ctx):
    p=ctx.first_pass(d.case['id'],d.bias)
    begin=round(float(p['post_start_s']),8)
    end=round(float(p['post_end_s']),8)
    win=(np.round(d.t,8)>=begin)&(np.round(d.t,8)<=end)
    return score(d,arm,mask=win,scope='first_pass_post')
