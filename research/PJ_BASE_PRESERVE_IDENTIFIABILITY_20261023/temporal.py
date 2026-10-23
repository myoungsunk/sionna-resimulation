"""S6 conditional window-identifiability diagnostics; never installs a temporal filter.

Covariance is trained on outer-training residuals. Every operational window ends at 'now'.
Future truth is used only for separately labelled retrospective forecast scoring.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from .common import require, BlockedError
from .numerics import (whiten, information, profiled_cost, motion_observation_covariance, wrap, psd)


def fit_spectral_metric(frame, held):
    require(held not in set(frame.route),'Held route in temporal covariance fit')
    frequencies=[];weights=[];used=0;missing=0
    for case,d in frame.groupby('case'):
        d=d.sort_values('t_s');valid=np.isfinite(d.t_s)&np.isfinite(d.target)
        missing+=int((~valid).sum());d=d[valid]
        if len(d)<5:continue
        t=d.t_s.to_numpy();r=d.target.to_numpy();require((np.diff(t)>0).all(),'Duplicate temporal training times')
        dt=float(np.median(np.diff(t)));cuts=np.r_[0,np.flatnonzero(np.diff(t)>1.5*dt)+1,len(t)]
        for lo,hi in zip(cuts[:-1],cuts[1:]):
            if hi-lo<5:continue
            tt=t[lo:hi];rr=r[lo:hi]
            require(np.max(abs(np.diff(tt)-dt))<max(1e-6,.01*dt),'Irregular time segment cannot be FFT-interpreted')
            z=rr-rr.mean();s=abs(np.fft.rfft(z))**2;f=np.fft.rfftfreq(len(z),dt)
            if s.sum()<=0:continue
            # Nonnegative spectral mass yields a PSD kernel at arbitrary evaluation timestamps.
            s=s/s.sum()*float(np.var(z))*len(z);frequencies.extend(f);weights.extend(s);used+=len(z)
    if not used:raise BlockedError('No contiguous, timestamped outer-training residual segment')
    weights=np.array(weights)/used
    return dict(held=held,frequencies=np.array(frequencies),weights=weights,n_used=used,n_missing=missing,
                fit_routes=sorted(set(frame.route)),interpretation='centered residual metric; stationarity assumption, not thermal noise')


def spectral_covariance(metric,t):
    t=np.asarray(t,float);diff=t[:,None]-t[None,:];G=np.zeros((len(t),len(t)))
    for f,w in zip(metric['frequencies'],metric['weights']):
        G+=float(w)*np.cos(2*np.pi*float(f)*diff)
    return psd(G)


def window_design(inputs,model,start,end,x0):
    """Motion-only propagation inside the window avoids double-assimilating its RF packets."""
    x=x0.copy();Phi=np.eye(4);states=[];J=[];H=[];F=[];G=[];Q=[];h=[]
    P=np.zeros((4,4))
    for k in range(start,end+1):
        fk,gk,qk=np.eye(4),np.zeros((4,3)),np.zeros((3,3))
        if k>start:
            x,P,fk,gk,qk=model.predict(x,P,inputs.controls[k]);Phi=fk@Phi
        hk,Hk=model.observe(x);states.append(x.copy());J.append(Hk[1]@Phi);h.append(hk[1]);H.append(Hk[1:2]);F.append(fk);G.append(gk);Q.append(qk)
    return dict(states=np.array(states),J=np.array(J),h=np.array(h),H=np.array(H),F=np.array(F),G=np.array(G),Q=np.array(Q))


def bias_forecast_diagnostic(t,b,now,window,horizon,kind):
    """Oracle-label diagnostic. Never returned as an operational correction."""
    lo=np.searchsorted(t,t[now]-window);idx=np.arange(lo,now+1)
    future=np.flatnonzero((t>t[now])&(t<=t[now]+horizon))
    if len(idx)<3 or not len(future):return dict(status='INSUFFICIENT_OR_CENSORED')
    time=t[idx]-t[now];U=np.ones((len(idx),1)) if kind=='constant' else np.c_[np.ones(len(idx)),time]
    beta=np.linalg.lstsq(U,b[idx],rcond=None)[0];uf=np.ones((len(future),1)) if kind=='constant' else np.c_[np.ones(len(future)),t[future]-t[now]]
    error=b[future]-uf@beta
    return dict(status='PASS',future_mse=float(np.mean(error**2)),last_value_mse=float(np.mean((b[future]-b[now])**2)),
                right_censored=bool(t[now]+horizon>t[-1]),classification='TRUTH_LABEL_BIAS_MODEL_DIAGNOSTIC_ONLY')


def nonlinear_profile(inputs,model,start,end,xstart,Gamma,U_bias,Pstart,grid_degrees=np.arange(-20,21,1.)):
    """For every heading hypothesis, optimize x/y/bg and RF-bias nuisance (not just sign crossings)."""
    W,_=whiten(Gamma);p=inputs.packets[start:end+1]
    measured=np.array([x.z[1]-x.mu[1] for x in p]);rows=[]
    scale=np.array([max(.2,3*np.sqrt(Pstart[0,0])),max(.2,3*np.sqrt(Pstart[1,1])),max(np.deg2rad(.05),3*np.sqrt(Pstart[3,3]))])
    for degrees in grid_degrees:
        trial=xstart.copy();trial[2]=wrap(trial[2]+np.deg2rad(degrees))
        def residual(beta):
            x=trial.copy();x[[0,1,3]]+=beta[:3]*scale
            des=window_design(inputs,model,start,end,x)
            return W@(measured-des['h']-U_bias@beta[3:])
        n=3+U_bias.shape[1]
        fit=least_squares(residual,np.zeros(n),bounds=(np.r_[np.full(3,-1.),np.full(n-3,-np.inf)],
                                                      np.r_[np.ones(3),np.full(n-3,np.inf)]),max_nfev=60)
        rows.append(dict(delta_heading_deg=float(degrees),cost=float(fit.fun@fit.fun),success=bool(fit.success),
                         evaluations=fit.nfev,nuisance_boundary=bool(np.any(abs(fit.x[:3])>.99)),
                         initialization='actual-prior motion-only; no rotated Full channel'))
    costs=np.array([r['cost'] for r in rows]);mins=np.flatnonzero((costs[1:-1]<costs[:-2])&(costs[1:-1]<costs[2:]))+1
    return rows,dict(local_minima=int(len(mins)),best_delta_heading_deg=rows[int(costs.argmin())]['delta_heading_deg'],
                    all_optimizations_converged=all(r['success'] for r in rows),
                    conclusion='DIAGNOSTIC_PROFILE_NOT_GLOBAL_UNIQUENESS_PROOF')


def s6(inputs,truth,model,base,metric,window_lengths=(2,5,10,30,60)):
    require(inputs.route==metric['held'],'Wrong outer-fold temporal metric')
    require(inputs.route not in metric['fit_routes'],'Covariance trained on held route')
    t=inputs.t;rows=[];profiles=[];forecasts=[];a=base.arrays
    times=np.arange(t[0],t[-1]+1e-9,10.);ends=np.unique(np.searchsorted(t,times));ends=ends[ends<len(t)]
    true_res=np.array([p.z[1]-model.observe(truth.state[k])[0][1]-p.mu[1] for k,p in enumerate(inputs.packets)])
    for end in ends:
        for seconds in window_lengths:
            if t[end]-seconds<t[0]:continue
            start=int(np.searchsorted(t,t[end]-seconds));tw=t[start:end+1];tau=tw-tw[0]
            if len(tw)<5:continue
            x0=a['x_minus'][start];P0=a['P_minus'][start]
            D=window_design(inputs,model,start,end,x0);J=D['J'];Gamma_rf=spectral_covariance(metric,tw)
            Gamma_motion=motion_observation_covariance(D['F'],D['G'],D['Q'],D['H'])
            Gamma=psd(Gamma_rf+Gamma_motion);W,wm=whiten(Gamma)
            r=np.array([p.z[1]-p.mu[1] for p in inputs.packets[start:end+1]])-D['h']
            for bias_model in ('constant','linear','free_packet'):
                B=np.ones((len(tw),1)) if bias_model=='constant' else (np.c_[np.ones(len(tw)),tau] if bias_model=='linear' else np.eye(len(tw)))
                U=np.c_[J[:,[0,1,3]],B];info=information(J[:,2],U,Gamma)
                M=np.c_[J,B];Mw=W@M;rw=W@r
                beta=np.linalg.lstsq(Mw,rw,rcond=1e-8)[0];rank=int(np.linalg.matrix_rank(Mw))
                recovered=beta[2];target=float(wrap(truth.state[start,2]-x0[2]))
                # Add the initial-state prior as separate rows. RF bias has no invented prior.
                L,_=whiten(P0);prior_rows=np.c_[L,np.zeros((len(L),B.shape[1]))]
                augmented=np.vstack([Mw,prior_rows]);ar=np.r_[rw,np.zeros(len(L))]
                joint=np.linalg.lstsq(augmented,ar,rcond=1e-8)[0]
                j=augmented[:,2];nu=augmented[:,[0,1,3]+list(range(4,augmented.shape[1]))]
                priorinfo=information(j,nu,np.eye(len(j)))['information']
                ident={**inputs.identity,'now_t':t[end],'start_t':t[start],'window_s':seconds,'bias_model':bias_model}
                rows.append({**ident,**info,'information_with_prior':priorinfo,'prior_added_information':priorinfo-info['information'],
                    'design_rank':rank,'design_columns':Mw.shape[1],'rf_recovery_error_deg':float(np.degrees(recovered-target)),
                    'prior_assisted_recovery_error_deg':float(np.degrees(joint[2]-target)),
                    'rf_recovery_identifiable':rank==Mw.shape[1],
                    'motion_covariance_trace':float(np.trace(Gamma_motion)),'covariance_rank':wm['cov_rank'],
                    'status':'INCONCLUSIVE' if rank<Mw.shape[1] else 'DIAGNOSTIC_COMPLETE'})
                if bias_model!='free_packet':
                    for horizon in (2.,10.):
                        forecasts.append({**ident,'forecast_horizon_s':horizon,**bias_forecast_diagnostic(t,true_res,end,seconds,horizon,bias_model)})
                    # Explicit nonlinear nuisance optimization; only current/past observations enter fitting.
                    pp,summary=nonlinear_profile(inputs,model,start,end,x0,Gamma,B,P0)
                    profiles.extend({**ident,**summary,**v} for v in pp)
    return {'S6_INFORMATION.csv':rows,'S6_NONLINEAR_PROFILE.csv.gz':profiles,'S6_BIAS_FORECAST_DIAGNOSTIC.csv':forecasts}
