"""B-MCG v1 research monitor and covariance adapter.

Runtime module: no truth, clean channel, file loaders, route identity or evaluator.
The bounded profile is a finite local search, not a posterior or a global proof.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json, time
import numpy as np
from scipy.optimize import lsq_linear

def wrap(a): return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi

@dataclass(frozen=True)
class Config:
    span_s: float=5.
    minimum_s: float=2.
    bounds: tuple=(.5,.5,np.pi/6,np.pi/900)
    motion_xy_m: float=.03
    motion_yaw_rad: float=np.pi/180
    regularizer: float=.01
    fit_slack_per_sample: float=.1
    max_prediction_span_sigma: float=2.
    linearity_rms_sigma: float=.5
    max_history_cost_per_sample: float=6.
    projected_gradient_per_sample_max: float=.05
    max_refinements: int=3
    minimum_profile_candidates: int=3
    tau_r: float=3.
    tau_s: float=3.
    tau_joint: float=4.242640687119286
    beta_min: float=.25
    max_history_gap_s: float=.3
    enable_r: bool=True
    enable_s: bool=True

    def __post_init__(self):
        positive=(self.span_s,self.minimum_s,self.motion_xy_m,self.motion_yaw_rad,self.regularizer,
            self.fit_slack_per_sample,self.max_prediction_span_sigma,self.linearity_rms_sigma,
            self.max_history_cost_per_sample,self.projected_gradient_per_sample_max,self.tau_r,self.tau_s,self.tau_joint,self.max_history_gap_s)
        if not np.isfinite(positive).all() or min(positive)<=0 or self.minimum_s>self.span_s:raise ValueError('INVALID_CONFIG')
        if len(self.bounds)!=4 or not np.isfinite(self.bounds).all() or min(self.bounds)<=0:raise ValueError('INVALID_BOUNDS')
        if not np.isfinite(self.beta_min) or not 0<self.beta_min<=1:raise ValueError('INVALID_BETA_MIN')
        if self.max_refinements<0 or self.minimum_profile_candidates<1:raise ValueError('INVALID_SEARCH_CONFIG')

    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()

def covariance_update(x, P, H, nu, R, beta=(1.,1.), permitted=True):
    """One Joseph update from the untouched prior; zero beta removes rows.

    Full-sized K is diagnostic (zero for unused channels). R_used retains the
    full base covariance plus finite diagonal additions; used_rows is authoritative
    for beta=0. No infinite covariance stand-ins are used.
    """
    x=np.asarray(x,float);P=np.asarray(P,float);H=np.asarray(H,float)
    nu=np.asarray(nu,float);R=np.asarray(R,float);beta=np.asarray(beta,float)
    if x.shape!=(4,) or P.shape!=(4,4) or H.shape!=(2,4) or nu.shape!=(2,) or R.shape!=(2,2) or beta.shape!=(2,):
        raise ValueError('SHAPE')
    if not all(np.isfinite(a).all() for a in (x,P,H,nu,R,beta)): raise ValueError('NONFINITE')
    if np.any((beta<0)|(beta>1)): raise ValueError('BETA_RANGE')
    if not np.allclose(P,P.T,rtol=1e-12,atol=1e-14) or np.linalg.eigvalsh(P).min() < -1e-12: raise ValueError('INVALID_P')
    if not np.allclose(R,R.T,rtol=1e-12,atol=1e-14) or np.linalg.eigvalsh(R).min()<=0: raise ValueError('INVALID_R')
    used=np.flatnonzero(beta>0) if permitted else np.array([],int)
    re=R.copy();positive=beta>0
    re[np.diag_indices(2)]+=np.where(positive,1/np.maximum(beta,1e-300)-1,0)*np.diag(R)
    K=np.zeros((4,2));out=x.copy();C=P.copy()
    if len(used):
        hr=H[used];rr=re[np.ix_(used,used)];S=hr@P@hr.T+rr;S=(S+S.T)*.5
        gain=np.linalg.solve(S,hr@P).T;K[:,used]=gain
        out+=gain@nu[used];out[2]=wrap(out[2])
        A=np.eye(4)-gain@hr;C=A@P@A.T+gain@rr@gain.T;C=(C+C.T)*.5
    return out,C,K,re,used

def motion_path(core,anchor,controls):
    """controls[0] is anchor index: its already-applied increment is skipped."""
    q=[np.asarray(anchor,float).copy()];sens=[np.eye(4)]
    for ds,gy,dt in np.asarray(controls,float)[1:]:
        x,F,_=core.transition(q[-1],float(ds),float(gy),float(dt))
        q.append(x);sens.append(F@sens[-1])
    return np.asarray(q),np.asarray(sens)

def _soft_cost(res, u, reg):
    # Vector robust loss per RF pair; history rows are not assumed independent.
    return float(np.sum(2*(np.sqrt(1+np.sum(res*res,axis=1))-1))+reg*np.dot(u,u))

def _affine_fit(A,b,center,reg):
    # Solve in global bounded normalized coordinates u, not independent per-frame yaw.
    target=b+np.einsum('nij,j->ni',A,center)
    weights=np.ones(len(b));u=center.copy()
    for _ in range(4):
        mat=(A*weights[:,None,None]).reshape(-1,4)
        vec=(target*weights[:,None]).ravel()
        sol=lsq_linear(np.vstack((mat,np.sqrt(reg)*np.eye(4))),np.r_[vec,np.zeros(4)],bounds=(-np.ones(4),np.ones(4)),tol=1e-8,max_iter=30)
        u=sol.x;res=target-np.einsum('nij,j->ni',A,u)
        weights=(1+np.sum(res*res,axis=1))**(-.25)
    return u,res,weights

def profile_history(core,model,spec,anchor,controls,t,z,mu,Rmon_base,cfg):
    """History excludes last z; last control/time is causal current target.

    `z` and `mu` have history rows only. No current observation is accepted here.
    The returned candidate target predictions can later score any current z.
    """
    start=time.perf_counter_ns();t=np.asarray(t,float);controls=np.asarray(controls,float)
    z=np.asarray(z,float);mu=np.asarray(mu,float);Rb=np.asarray(Rmon_base,float)
    n=len(t);nh=n-1
    if z.shape!=(nh,2) or mu.shape!=(nh,2) or Rb.shape!=(n,2,2) or controls.shape!=(n,3):raise ValueError('HISTORY_SHAPE')
    info={'status':'UNKNOWN','reason':'UNINITIALIZED','candidate_h':np.empty((0,2)),'valid_channels':np.zeros(2,bool),
          'history_n':nh,'profile_cost':None,'rank':0,'bound_hit':False,'linearity_sigma':None,'target_span_sigma':np.full(2,np.nan),
          'theta':np.full(4,np.nan),'singular_values':np.full(4,np.nan),'candidate_count':0}
    if not all(np.isfinite(x).all() for x in (anchor,controls,t,z,mu,Rb)) or np.any(np.diff(t)<=0) or (n>1 and np.max(np.diff(t))>cfg.max_history_gap_s):
        info.update(reason='NONFINITE_OR_GAP');return info
    if not np.allclose(Rb,Rb.transpose(0,2,1),rtol=1e-12,atol=1e-14) or (len(Rb) and np.linalg.eigvalsh(Rb).min()<=0):
        info.update(reason='INVALID_MONITOR_COVARIANCE');return info
    if n>1 and not np.allclose(controls[1:,2],np.diff(t),rtol=0,atol=1e-9):
        info.update(reason='CONTROL_TIME_MISMATCH');return info
    if n<2 or t[-1]-t[0]<cfg.minimum_s-1e-9:
        info.update(status='WARMUP',reason='SHORT_HISTORY');return info
    bounds=np.asarray(cfg.bounds,float)
    if bounds.shape!=(4,) or np.any(bounds<=0):raise ValueError('INVALID_BOUNDS')
    centers=np.zeros((3,4));centers[1,2]=-.5;centers[2,2]=.5
    paths=[];Ts=[]
    for c in centers:
        q,T=motion_path(core,np.asarray(anchor)+bounds*c,controls);paths.append(q);Ts.append(T)
    h,H=model.batch(np.concatenate(paths),spec)
    h=h.reshape(3,n,2);H=H.reshape(3,n,2,4)
    elapsed=np.maximum(t-t[0],0)/max(cfg.span_s,1e-9)
    # Fixed pre-inflation scales, with explicit motion-shape error envelope.
    env=np.column_stack((np.full(n,cfg.motion_xy_m),np.full(n,cfg.motion_xy_m),cfg.motion_yaw_rad*elapsed,np.zeros(n)))
    extra=np.einsum('nci,ni->nc',H[0]**2,env**2)
    Rmon=Rb.copy();Rmon[:,0,0]+=extra[:,0];Rmon[:,1,1]+=extra[:,1]
    L=np.linalg.cholesky(Rmon);scale=np.sqrt(np.diagonal(Rmon,axis1=1,axis2=2))
    sols=[];fits=[];matrices=[]
    for c in range(3):
        J=np.einsum('nci,nij->ncj',H[c],Ts[c])*bounds[None,None,:]
        A=np.linalg.solve(L[:-1],J[:-1]);b=np.linalg.solve(L[:-1],(z-h[c,:-1]-mu)[...,None])[...,0]
        u,res,weights=_affine_fit(A,b,centers[c],cfg.regularizer)
        sols.append(u);fits.append((res,weights));matrices.append((A,b,J))
    # Exact nonlinear costs for all chart solutions before choosing a profile centre.
    qsol=[motion_path(core,np.asarray(anchor)+bounds*u,controls)[0] for u in sols]
    exact,_=model.batch(np.concatenate(qsol),spec,gradient=False);exact=exact.reshape(3,n,2)
    residual=[np.linalg.solve(L[:-1],(z-exact[c,:-1]-mu)[...,None])[...,0] for c in range(3)]
    costs=np.array([_soft_cost(residual[c],sols[c],cfg.regularizer) for c in range(3)])
    ib=int(np.argmin(costs));ub=sols[ib].copy();refinements=0
    # Exact-model local refinement. Convergence is checked separately from
    # profile coverage; a low candidate spread alone cannot assert validity.
    def at(u):
        qq,TT=motion_path(core,np.asarray(anchor)+bounds*u,controls)
        hh,HH=model.batch(qq,spec)
        JJ=np.einsum('nci,nij->ncj',HH,TT)*bounds[None,None,:]
        AA=np.linalg.solve(L[:-1],JJ[:-1]);rr=np.linalg.solve(L[:-1],(z-hh[:-1]-mu)[...,None])[...,0]
        ww=(1+np.sum(rr*rr,axis=1))**(-.25)
        grad=-2*np.einsum('nci,nc->i',AA,rr*ww[:,None]**2)+2*cfg.regularizer*u
        projected=grad.copy();projected[(u>=.999)&(grad<0)]=0;projected[(u<=-.999)&(grad>0)]=0
        return hh,JJ,AA,rr,ww,_soft_cost(rr,u,cfg.regularizer),float(np.max(abs(projected))/nh)
    hb,J,A,b,weights,refcost,stationarity=at(ub)
    last_linearity=0.
    for _ in range(cfg.max_refinements):
        if stationarity<=cfg.projected_gradient_per_sample_max:break
        proposal,_,_=_affine_fit(A,b,ub,cfg.regularizer)
        trials=[ub+frac*(proposal-ub) for frac in (1.,.5,.25)]
        qt=[motion_path(core,np.asarray(anchor)+bounds*u,controls)[0] for u in trials]
        ht,_=model.batch(np.concatenate(qt),spec,gradient=False);ht=ht.reshape(3,n,2)
        rt=np.linalg.solve(L[None,:-1],(z[None]-ht[:,:-1]-mu[None])[...,None])[...,0]
        ct=np.array([_soft_cost(r,u,cfg.regularizer) for r,u in zip(rt,trials)])
        j=int(np.argmin(ct))
        if ct[j]>=refcost-1e-10:break
        last_linearity=float(np.sqrt(np.mean(((ht[j]-(hb+np.einsum('nci,i->nc',J,trials[j]-ub)))/scale)**2)))
        ub=trials[j];refinements+=1
        hb,J,A,b,weights,refcost,stationarity=at(ub)
    sols.append(ub.copy());exact=np.concatenate((exact,hb[None]),axis=0)
    # Final local tangent is used solely for proposing exact-checked profiles.
    weighted=A*weights[:,None,None];flat=weighted.reshape(-1,4)
    _,sv,Vt=np.linalg.svd(flat,full_matrices=False)
    rank=int(np.sum(sv>max(1e-8,sv[0]*1e-3)))
    slack=cfg.fit_slack_per_sample*nh
    probes=[]
    # Probe weak/null as well as strong nuisance directions up to physical bounds.
    directions=[(s,d) for s,d in zip(sv,Vt)]
    curvature=flat.T@flat+cfg.regularizer*np.eye(4)
    for channel in range(2):
        d=np.linalg.solve(curvature,J[-1,channel]/scale[-1,channel]);dn=np.linalg.norm(d)
        if dn>1e-12:
            d/=dn;directions.append((float(np.linalg.norm(flat@d)),d))
    for s,direction in directions:
        ideal=min(2.,np.sqrt(slack/max(s*s,1e-10)))
        for sign in (-1.,1.):
            d=direction*sign
            allowed=np.min(np.where(abs(d)>1e-12,(1-np.sign(d)*ub)/np.maximum(abs(d),1e-12),np.inf))
            step=min(ideal,max(0.,float(allowed))*.98)
            if step>1e-7:probes.append(ub+step*d)
    candidates=np.asarray(sols+probes);all_exact=list(exact)
    if probes:
        qp=[motion_path(core,np.asarray(anchor)+bounds*u,controls)[0] for u in probes]
        hp,_=model.batch(np.concatenate(qp),spec,gradient=False)
        all_exact.extend(hp.reshape(len(probes),n,2))
    all_exact=np.asarray(all_exact)
    all_res=np.linalg.solve(L[None,:-1],(z[None]-all_exact[:,:-1]-mu[None])[...,None])[...,0]
    all_cost=np.array([_soft_cost(r,u,cfg.regularizer) for r,u in zip(all_res,candidates)])
    best=int(np.argmin(all_cost));keep=all_cost<=all_cost[best]+slack
    target=all_exact[keep,-1]
    span=np.ptp(target,axis=0)/scale[-1]
    linearity=last_linearity
    bound_hit=bool(np.max(abs(candidates[best]))>.98)
    accepted=candidates[keep]
    boundary_support=bool(np.any(np.max(abs(accepted),axis=1)>.98))
    valid=(span<=cfg.max_prediction_span_sigma)
    reason='PROFILE_IDENTIFIABLE_AT_TARGET'
    if bound_hit:valid[:]=False;reason='PROFILE_AT_BOUND'
    # A nuisance probe may reach its physical bound while the current predicted
    # observation stays stable. The frozen per-channel target-span cap decides
    # that uncertainty; boundary_support is diagnostic, not a blanket veto.
    if stationarity>cfg.projected_gradient_per_sample_max:valid[:]=False;reason='NONLINEAR_FIT_NOT_STATIONARY'
    if int(keep.sum())<cfg.minimum_profile_candidates:valid[:]=False;reason='PROFILE_UNDERSAMPLED'
    if all_cost[best]<refcost-1e-6:valid[:]=False;reason='UNRESOLVED_LOWER_PROFILE_CANDIDATE'
    if linearity>cfg.linearity_rms_sigma:valid[:]=False;reason='NONLINEAR_CHECK_FAILED'
    if all_cost[best]/max(nh,1)>cfg.max_history_cost_per_sample:valid[:]=False;reason='HISTORY_FIT_FAILED'
    if not np.all(valid) and reason=='PROFILE_IDENTIFIABLE_AT_TARGET':reason='TARGET_PROFILE_TOO_BROAD'
    info.update(status='PROFILE_READY' if valid.any() else 'UNKNOWN',reason=reason,candidate_h=target,
        valid_channels=valid,profile_cost=float(all_cost[best]),rank=rank,bound_hit=bound_hit,linearity_sigma=linearity,
        target_span_sigma=span,theta=np.asarray(anchor)+bounds*candidates[best],singular_values=sv,candidate_count=int(keep.sum()),
        Rmon_target=Rmon[-1],scale=scale[-1],duration_ms=(time.perf_counter_ns()-start)/1e6,
        stationarity_per_sample=stationarity,refinements=refinements,boundary_support=boundary_support,
        finite_search_only=True,anchor_sha256=hashlib.sha256(np.asarray(anchor,dtype='<f8').tobytes()).hexdigest())
    return info

def score_current(profile,z,mu):
    z=np.asarray(z,float);mu=np.asarray(mu,float)
    if z.shape!=(2,) or mu.shape!=(2,) or not np.isfinite(np.r_[z,mu]).all():
        return dict(status='INVALID',reason='INVALID_CURRENT_RF',scores=np.full(3,np.nan),valid_channels=np.zeros(2,bool))
    if not len(profile['candidate_h']):
        return dict(status=profile['status'],reason=profile['reason'],scores=np.full(3,np.nan),valid_channels=profile['valid_channels'])
    e=z[None]-profile['candidate_h']-mu[None]
    marginal=np.min(abs(e),axis=0)/profile['scale']
    whiten=np.linalg.solve(np.linalg.cholesky(profile['Rmon_target']),e.T).T
    joint=float(np.sqrt(np.min(np.sum(whiten*whiten,axis=1))))
    return dict(status=profile['status'],reason=profile['reason'],scores=np.r_[marginal,joint],valid_channels=profile['valid_channels'].copy())

def weights(score,cfg,mode='ACTIVE_RS'):
    beta=np.ones(2);valid=np.asarray(score['valid_channels'],bool);s=np.asarray(score['scores'])
    if score['status']=='INVALID':return np.zeros(2),'INVALID'
    if mode in ('OFF','OBSERVE_ONLY'):return beta,score['status']
    if not valid.any():return beta,score['status']
    enabled=np.array([mode in ('ACTIVE_R','ACTIVE_RS'),mode in ('ACTIVE_S','ACTIVE_RS')])&np.array([cfg.enable_r,cfg.enable_s])
    tau=np.array([cfg.tau_r,cfg.tau_s]);bad=valid&(s[:2]>tau)
    for c in range(2):
        if bad[c] and enabled[c]:beta[c]=max(cfg.beta_min,(tau[c]/s[c])**2)
    joint=bool(valid.all() and not bad.any() and s[2]>cfg.tau_joint)
    if joint and mode=='ACTIVE_RS':beta[:]=max(cfg.beta_min,(cfg.tau_joint/s[2])**2)
    if joint:return beta,'CONFLICT_JOINT_UNRESOLVED'
    if bad.all():return beta,'CONFLICT_RS'
    if bad[0]:return beta,'CONFLICT_R'
    if bad[1]:return beta,'CONFLICT_S'
    return beta,'COMPATIBLE' if valid.all() else 'PARTIAL_UNKNOWN'

class Monitor:
    """Snapshots are immutable; history is raw RF including legacy rejections."""
    def __init__(self,core,model,spec,cfg):
        self.core=core;self.model=model;self.spec=spec;self.cfg=cfg;self.records=[]

    def observe(self,k,t,prior,controls,z,mu,Rbase):
        if k!=len(self.records):raise ValueError('NONSEQUENTIAL_INDEX')
        controls=np.asarray(controls,float)
        if controls.shape!=(3,) or not np.isfinite(controls).all() or not np.isfinite(t):raise ValueError('INVALID_TIME_CONTROL')
        if np.asarray(prior).shape!=(4,) or not np.isfinite(prior).all():raise ValueError('INVALID_ANCHOR')
        if np.asarray(z).shape!=(2,) or np.asarray(mu).shape!=(2,) or np.asarray(Rbase).shape!=(2,2):raise ValueError('INVALID_RF_SHAPE')
        if k and (t<=self.records[-1]['t'] or abs(controls[2]-(t-self.records[-1]['t']))>1e-9):raise ValueError('CONTROL_TIME_MISMATCH')
        if not k and controls[2]!=0:raise ValueError('INITIAL_DT_MUST_BE_ZERO')
        prior=np.array(prior,float,copy=True);prior.flags.writeable=False
        # Current z is stored only AFTER profile fitting and scoring.
        times=np.array([v['t'] for v in self.records]+[float(t)])
        a=int(np.searchsorted(times,float(t)-self.cfg.span_s-1e-9))
        history=self.records[a:]
        record={'t':float(t),'prior':prior,'controls':np.array(controls,float,copy=True),'z':np.array(z,float,copy=True),'mu':np.array(mu,float,copy=True),'R':np.array(Rbase,float,copy=True)}
        record['rf_valid']=bool(np.isfinite(np.r_[record['z'],record['mu'],record['R'].ravel()]).all())
        if record['rf_valid']:
            record['rf_valid']=bool(np.allclose(record['R'],record['R'].T,rtol=1e-12,atol=1e-14) and np.linalg.eigvalsh(record['R']).min()>0)
        if history and record['rf_valid'] and all(v.get('rf_valid',True) for v in history):
            info=profile_history(self.core,self.model,self.spec,history[0]['prior'],
               np.array([v['controls'] for v in history]+[record['controls']]),times[a:],
               np.array([v['z'] for v in history]),np.array([v['mu'] for v in history]),
               np.array([v['R'] for v in history]+[record['R']]),self.cfg)
        else:info={'status':'UNKNOWN' if history else 'WARMUP','reason':'INVALID_HISTORY_RF' if history else 'SHORT_HISTORY','candidate_h':np.empty((0,2)),'valid_channels':np.zeros(2,bool),'history_n':len(history)}
        sc=score_current(info,z,mu) if record['rf_valid'] else {'status':'INVALID','reason':'INVALID_CURRENT_RF','scores':np.full(3,np.nan),'valid_channels':np.zeros(2,bool)}
        self.records.append(record)
        info.update(anchor_index=a,history_start=a,history_end=k-1,current_index=k,anchor_age_s=float(t-times[a]))
        return sc,info
