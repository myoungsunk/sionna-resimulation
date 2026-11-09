"""History-only 4D profile. Scores are nonconformity, NOT probabilities.

The monitor never receives evaluator truth, clean CIR, route labels, or future
RF. A 1 Hz profile is reused for at most 0.8 s; current scores remain 5 Hz.
Limited nonlinear search is not a proof of global feasibility.
"""
from dataclasses import dataclass,field
import time
import numpy as np
from scipy.optimize import least_squares
from numerics import paths,SPEC,wrap

@dataclass(frozen=True)
class MonitorConfig:
    window_s:float=5.
    minimum_history_s:float=2.
    refit_every_s:float=1.
    max_nfev:int=12
    cost_slack:float=1.
    max_target_width_sigma:float=4.
    max_history_mean_loss:float=20.
    prior_penalty:float=.1
    bias_penalty:float=.5
    max_gap_s:float=.4

@dataclass
class Profile:
    anchor:int
    target_at_fit:int
    reference:np.ndarray
    bounds:np.ndarray
    candidates:np.ndarray
    costs:np.ndarray
    best_cost:float
    rank:int
    condition:float
    fit_success:bool
    bound_hit:bool
    history_count:int
    support_hash:str
    elapsed_ms:float
    why:str
    overlap_residual_fraction:float

class Monitor:
    def __init__(self,core,model,series,envelope,config=None):
        self.core=core;self.model=model;self.data=series;self.envelope=np.asarray(envelope,float)
        if self.envelope.shape!=(4,) or np.any(self.envelope<=0):raise ValueError('INVALID_ENVELOPE')
        self.config=config or MonitorConfig();self.profile=None;self.last_k=-1
    def scale(self,q,indices):
        R=self.data.R[indices].copy()
        rho=np.linalg.norm(q[:,:2]-np.array(SPEC['anchor'][:2]),axis=1)
        sig=np.interp(rho,[0,1.5,3,6,10],[.011,.020,.050,.120,.240])
        R[:,1,1]+=sig**2
        return np.linalg.cholesky(R)
    def _fit(self,k,priors,Ppriors):
        import hashlib
        started=time.perf_counter();d=self.data;c=self.config
        a=int(np.searchsorted(d.t,d.t[k]-c.window_s-1e-9))
        if a>=k or d.t[k]-d.t[a]<c.minimum_history_s-1e-8:return None
        if np.any(d.dt[a+1:k+1]>c.max_gap_s):return None
        ref=priors[a].copy();bounds=np.maximum(3*np.sqrt(np.maximum(np.diag(Ppriors[a]),0)),self.envelope)
        # Preserve correlated uncertainty in main P; box bounds are monitor-only.
        q0,_=paths(self.core,ref,d.ds,d.gy,d.dt,a,k)
        ids=np.arange(a,k);L=self.scale(q0[:-1],ids)
        mu=d.mu[ids];z=d.z[ids]
        penalty=np.array([c.prior_penalty]*3+[c.bias_penalty])
        last=None;cache=None
        def calc(v):
            nonlocal last,cache
            if last is not None and np.array_equal(last,v):return cache
            theta=ref+bounds*v
            q,T=paths(self.core,theta,d.ds,d.gy,d.dt,a,k)
            h,H=self.model.batch(q[:-1],SPEC)
            e=np.linalg.solve(L,(z-h-mu)[...,None])[...,0]
            J=-np.linalg.solve(L,H@T[:-1])*bounds[None,None,:]
            residual=np.r_[e.ravel(),penalty*v]
            jac=np.vstack([J.reshape(-1,4),np.diag(penalty)])
            last=v.copy();cache=(residual,jac,q);return cache
        starts=[np.zeros(4)]
        shift=min(.6,np.deg2rad(10)/bounds[2])
        for sign in (-1,1):
            v=np.zeros(4);v[2]=sign*shift;starts.append(v)
        fits=[]
        for v in starts:
            result=least_squares(lambda u:calc(u)[0],v,jac=lambda u:calc(u)[1],bounds=(-np.ones(4),np.ones(4)),loss='soft_l1',f_scale=1.,max_nfev=c.max_nfev,ftol=1e-4,xtol=1e-4,gtol=1e-4)
            fits.append(result)
        best=min(fits,key=lambda r:r.cost);v=best.x
        rr,jj,_=calc(v)
        _,s,V=np.linalg.svd(jj[:-4],full_matrices=False)
        rank=int(np.sum(s>max(s[0]*1e-5,1e-8)))
        cond=float(s[0]/max(s[-1],1e-12))
        weighted=rr[:-4];projection=jj[:-4]@np.linalg.lstsq(jj[:-4],weighted,rcond=1e-5)[0]
        perpendicular=float(np.dot(weighted-projection,weighted-projection)/max(np.dot(weighted,weighted),1e-20))
        proposals=[r.x for r in fits if r.cost<=best.cost+c.cost_slack]
        for direction,sv in zip(V,s):
            step=min(1.,1./max(sv,1e-6))
            for sign in (-1,1):proposals.append(np.clip(v+sign*step*direction,-.999,.999))
        candidates=[];costs=[]
        for u in proposals:
            residual,_,_=calc(u);cost=float(np.sum(np.sqrt(1+residual**2)-1))
            if cost<=best.cost+c.cost_slack+1e-8:
                candidates.append(ref+bounds*u);costs.append(cost)
        if not candidates:candidates=[ref+bounds*v];costs=[float(best.cost)]
        success=any(r.success and r.cost<=best.cost+c.cost_slack for r in fits)
        bound=bool(np.any(abs(v)>.98))
        why='OK' if success and not bound else ('SEARCH_BUDGET' if not success else 'BOUND_HIT')
        if best.cost/max(len(ids),1)>c.max_history_mean_loss:why='HISTORY_MISFIT'
        hashdata=np.ascontiguousarray(np.c_[d.t[ids],z,mu]).tobytes()
        return Profile(a,k,ref,bounds,np.asarray(candidates),np.asarray(costs),float(best.cost),rank,cond,success,bound,len(ids),hashlib.sha256(hashdata).hexdigest(),(time.perf_counter()-started)*1000,why,perpendicular)
    def assess(self,k,priors,Ppriors):
        started=time.perf_counter();d=self.data;c=self.config
        if k<=self.last_k:raise ValueError('NONMONOTONIC_MONITOR_CALL')
        self.last_k=k
        if not np.isfinite(d.z[k]).all():raise ValueError('INVALID_CURRENT_RF')
        refit=self.profile is None or d.t[k]-d.t[self.profile.target_at_fit]>=c.refit_every_s-1e-9
        if refit:self.profile=self._fit(k,priors,Ppriors)
        p=self.profile
        if p is None:return dict(k=k,state='WARMUP',score=np.zeros(3),width=np.zeros(2),valid=np.zeros(2,bool),anchor=-1,support_end=-1,history_cost=0.,rank=0,condition=0.,theta=np.zeros(4),fit_ms=0.,latency_ms=(time.perf_counter()-started)*1000,reason='INSUFFICIENT_OR_GAPPED_HISTORY',n_candidates=0,perpendicular_fraction=0.,support_hash='')
        # Refit does not see target; reuse does not see intervening RF either.
        q=[]
        for theta in p.candidates:q.append(paths(self.core,theta,d.ds,d.gy,d.dt,p.anchor,k,jac=False)[0][-1])
        q=np.asarray(q);h,_=self.model.batch(q,SPEC,gradient=False)
        nom=paths(self.core,p.reference,d.ds,d.gy,d.dt,p.anchor,k,jac=False)[0][-1:]
        L=self.scale(nom,np.array([k]))[0];e=d.z[k]-h-d.mu[k]
        marg=np.abs(e)/np.sqrt(np.diag(L@L.T))[None]
        whiten=np.linalg.solve(L,e.T).T
        score=np.r_[marg.min(0),np.sqrt((whiten**2).sum(1).min())]
        width=np.ptp(h,axis=0)/np.sqrt(np.diag(L@L.T))
        valid=(width<=c.max_target_width_sigma)&(p.why=='OK')
        reason=p.why if p.why!='OK' else ('TARGET_AMBIGUOUS' if not valid.all() else 'OK')
        return dict(k=k,state='COMPATIBLE' if valid.all() else 'UNKNOWN',score=score,width=width,valid=valid,anchor=p.anchor,support_end=p.target_at_fit-1,history_cost=p.best_cost/max(p.history_count,1),rank=p.rank,condition=p.condition,theta=p.candidates[0],fit_ms=p.elapsed_ms if refit else 0.,latency_ms=(time.perf_counter()-started)*1000,reason=reason,n_candidates=len(p.candidates),perpendicular_fraction=p.overlap_residual_fraction,support_hash=p.support_hash)

def weights(score,valid,threshold,channel='RS',beta_min=.25):
    if threshold is None:raise ValueError('ACTIVE_REQUIRES_FROZEN_CALIBRATION')
    score=np.asarray(score);valid=np.asarray(valid,bool)
    beta=np.ones(2)
    for j in range(2):
        if valid[j] and score[j]>threshold:beta[j]=max(beta_min,(threshold/score[j])**2)
    if channel=='R':beta[1]=1.
    elif channel=='S':beta[0]=1.
    elif channel!='RS':raise ValueError('INVALID_CHANNEL_POLICY')
    # An unresolved joint conflict is NOT silently attributed to one channel.
    if channel=='RS' and valid.all() and score[2]>threshold*np.sqrt(2) and np.all(score[:2]<=threshold):
        beta[:]=max(beta_min,(threshold*np.sqrt(2)/score[2])**2)
    return beta
