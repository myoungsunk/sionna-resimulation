"""S1/S2/S4/S5 diagnostics: populations, finite responses, common-prior and actual branches."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from .common import require, Trace, OFFSETS
from .runtime_features import Corrector, profile_features, SCALE
from .replay import update, simulate
from .numerics import (wrap, delta, moments, finite_jacobian, response_pair, projector, masked_projector)
from .oracle_scoring import residual_table, error_arrays, score_trace, all4_budget


def summarize_residual(rows):
    f=pd.DataFrame(rows);strata=[];statistics=[];temporal=[]
    group=['case','bias','seed_idx','source_prior','arm']
    for key,d in f.groupby(group,sort=False):
        identity=dict(zip(group,key))
        for window,w in [('all',d),('stable_30_plus',d[d.t_s>=30])]:
            for population,p in [('all',w),('common_gate',w[w.common_accepted]),('own_gate',w[w.own_accepted])]:
                if len(p)==0:
                    statistics.append({**identity,'window':window,'population':population,'n':0,'status':'EMPTY'});continue
                for name in ('r_B','r_candidate','correction','c1','c2'):
                    v=p[name].to_numpy();statistics.append({**identity,'window':window,'population':population,'signal':name,'n':len(v),
                        'mean':v.mean(),'variance':v.var(),'mean_square':np.mean(v*v),'status':'PASS'})
                for tau in (.02,.05,.1):
                    for label,mask in [('small',abs(p.r_B)<tau),('other',abs(p.r_B)>=tau)]:
                        z=p[mask];strata.append({**identity,'window':window,'population':population,'threshold_diagnostic_only':tau,'stratum':label,
                            'n':len(z),'mean_Ds':z.D_s.mean(),'harm_mass':float(np.maximum(-z.D_s,0).sum()),
                            'benefit_mass':float(np.maximum(z.D_s,0).sum()),'status':'PASS' if len(z) else 'EMPTY'})
                # Preserve the historical 0.05--0.2 and >0.2 bins, including residual sign.
                for label,mask in [('middle',abs(p.r_B).between(.05,.2,inclusive='left')),('large',abs(p.r_B)>=.2)]:
                    z=p[mask];strata.append({**identity,'window':window,'population':population,'stratum':label,'n':len(z),
                        'mean_Ds':z.D_s.mean(),'harm_mass':float(np.maximum(-z.D_s,0).sum()),'status':'PASS' if len(z) else 'EMPTY'})
        for sign,mask in [('negative',d.r_B<0),('nonnegative',d.r_B>=0)]:
            z=d[mask];strata.append({**identity,'window':'all','population':'all','stratum':'signed_'+sign,'n':len(z),'mean_Ds':z.D_s.mean(),'harm_mass':float(np.maximum(-z.D_s,0).sum()),'status':'PASS' if len(z) else 'EMPTY'})
        for layer,mask in [('fp0',d.fp_shift_diagnostic_only==0),('fp1',abs(d.fp_shift_diagnostic_only)==1),('fp2plus',abs(d.fp_shift_diagnostic_only)>=2)]:
            z=d[mask];strata.append({**identity,'window':'all','population':'all','stratum':layer,'n':len(z),'mean_Ds':z.D_s.mean(),'harm_mass':float(np.maximum(-z.D_s,0).sum()),'status':'PASS' if len(z) else 'EMPTY'})
        ordered=d.sort_values('t_s');t=ordered.t_s.to_numpy()
        for name in ('r_B','r_candidate','correction'):
            v=ordered[name].to_numpy();sg=np.sign(v);change=np.r_[True,sg[1:]!=sg[:-1]];starts=np.flatnonzero(change);ends=np.r_[starts[1:],len(v)]
            for a,b in zip(starts,ends):
                temporal.append({**identity,'signal':name,'start_t':t[a],'end_t':t[b-1],'sign':sg[a],
                    'duration_s':t[b-1]-t[a],'n':b-a,'signed_sum':v[a:b].sum(),'right_censored':b==len(v)})
    return strata,statistics,temporal


def s1(inputs,truth,model,priors,correctors):
    rows=[]
    for prior in priors:
        common=np.array([update(prior.arrays['x_minus'][k],prior.arrays['P_minus'][k],p,prior.arrays['h'][k],prior.arrays['H'][k],0.)['accepted'] for k,p in enumerate(inputs.packets)])
        rr=residual_table(inputs,truth,model,prior,correctors,common)
        for r in rr:
            k=int(r['k']);p=inputs.packets[k];a=prior.arrays
            own=update(a['x_minus'][k],a['P_minus'][k],p,a['h'][k],a['H'][k],r['correction'])
            r['own_accepted']=own['accepted']
        rows+=rr
    strata,statistics,temporal=summarize_residual(rows)
    return {'S1_RESIDUAL.csv.gz':rows,'S1_STRATA.csv':strata,'S1_MEAN_VAR.csv':statistics,'S1_TEMPORAL.csv':temporal}


def perturbations(P):
    vectors=[]
    for degrees in (.1,.5,1,2,5,10,20):
        v=np.zeros(4);v[2]=math.radians(degrees);vectors.append((f'heading_{degrees:g}deg',v))
    for axis in (0,1):
        for m in (.01,.05,.20):
            v=np.zeros(4);v[axis]=m;vectors.append((f'xy{axis}_{m:g}m',v))
    for sign in (-1,1):
        vectors.append((f'physical_joint_{sign}',np.array([.05,sign*.05,math.radians(5),0.])))
    # Covariance-scaled directions supplemented, not replaced, by fixed physical directions.
    physical=np.array([.05,.05,np.deg2rad(5.)]);scaled=P[:3,:3]/physical[:,None]/physical[None,:]
    e,U=np.linalg.eigh((scaled+scaled.T)/2)
    for j in range(3):
        v=np.r_[physical*U[:,j]*np.sqrt(max(e[j],0)),0.];vectors.append((f'P_direction_{j}',v))
    return vectors


def s2(inputs,model,priors,correctors,omega):
    response=[];ranks=[];leakage=[]
    for tr in priors:
        a=tr.arrays
        for k,p in enumerate(inputs.packets):
            x=a['x_minus'][k];h,H=model.observe(x)
            identity={**inputs.identity,'source_prior':tr.metadata['arm'],'k':k,'pose_id':p.pose_id,'t_s':p.t}
            # Observe-Jacobian FD; profile derivative includes observer and detector effects separately.
            Hfd=finite_jacobian(lambda z:model.observe(z)[0],x)
            err=float(np.max(abs(Hfd-H[:,:3])));scale=max(float(np.max(abs(H[:,:3]))),1e-8)
            switching=False
            for col,step in enumerate((1e-5,1e-5,1e-6)):
                xp,xm=x.copy(),x.copy();xp[col]+=step;xm[col]-=step
                switching |= model.profile(xp)[2]!=model.profile(xm)[2]
            near_axis=np.linalg.norm(x[:2]-inputs.anchor[:2])<1e-7
            fdstatus='NONSMOOTH_OBSERVER' if switching else ('COORDINATE_AXIS_DIAGNOSTIC' if near_axis else ('PASS' if err<=1e-6+1e-3*scale else 'QA_FAIL'))
            ranks.append({**identity,'representation':'physical_H','fd_absmax':err,'fd_relmax':err/scale,'fp_switch':switching,'near_anchor_axis':near_axis,'status':fdstatus})
            for representation in ('own_fp','measured_fp'):
                for heading_only in (True,False):
                    u0,info,(d0,J0,mask0)=profile_features(p,x,model,omega,representation=representation,heading_only=heading_only)
                    ranks.append({**identity,'representation':representation,'heading_only':heading_only,**info})
                    for label,v in perturbations(a['P_minus'][k]):
                        xp,xm=x+v,x-v;xp[2]=wrap(xp[2]);xm[2]=wrap(xm[2])
                        up,ip,(dp,Jp,mp)=profile_features(p,xp,model,omega,representation=representation,heading_only=heading_only)
                        um,im,(dm,Jm,mm)=profile_features(p,xm,model,omega,representation=representation,heading_only=heading_only)
                        same=mask0 & mp & mm;cols=[2] if heading_only else [0,1,2]
                        fixed=np.nan;fixed_status='NO_COMMON_VALID_TAPS'
                        if same.any():
                            try:
                                _,P,W,_=projector(d0[same],J0[same][:,cols],omega[np.ix_(same,same)],SCALE[cols])
                                fixed=float(np.linalg.norm(P@W@(dp[same]-dm[same])));fixed_status='PASS'
                            except ValueError as exc:fixed_status='UNIDENTIFIABLE:'+str(exc)
                        leakage.append({**identity,'representation':representation,'heading_only':heading_only,'perturbation':label,
                            'fixed_projector_response':fixed,'fixed_projection_status':fixed_status,'full_operator_response':float(np.linalg.norm(up[same]-um[same])) if same.any() else np.nan,
                            'n_valid_common':int(same.sum()),'fp_switch':ip['model_fp']!=im['model_fp'],
                            'mask_changed':not(np.array_equal(mp,mm) and np.array_equal(mp,mask0)),
                            'status':'PASS' if same.any() else 'NO_COMMON_VALID_TAPS'})
            for label,v in perturbations(a['P_minus'][k]):
                xp,xm=x+v,x-v;xp[2]=wrap(xp[2]);xm[2]=wrap(xm[2]);hp,_=model.observe(xp);hm,_=model.observe(xm)
                bp=p.z[1]-hp[1]-p.mu[1];bm=p.z[1]-hm[1]-p.mu[1]
                for c in correctors:
                    cp,_=c(p,xp,hp,model);cm,_=c(p,xm,hm,model)
                    response.append({**identity,'arm':c.name,'perturbation':label,'dx_m':v[0],'dy_m':v[1],'dpsi_rad':v[2],
                        'correction_jump':cp-cm,'base_plus':bp,'base_minus':bm,**response_pair(bp,bm,bp-cp,bm-cm)})
    return {'S2_FINITE_RESPONSE.csv.gz':response,'S2_PROJECTOR_RANK.csv':ranks,'S2_STATE_LEAKAGE.csv':leakage}


def common_prior(inputs,truth,model,priors,correctors):
    rows=[]
    for tr in priors:
        a=tr.arrays
        for k,p in enumerate(inputs.packets):
            x,P=a['x_minus'][k],a['P_minus'][k];h,H=model.observe(x);B=update(x,P,p,h,H,0.)
            hg,_=model.observe(truth.state[k]);rb=p.z[1]-hg[1]-p.mu[1]
            for corr in correctors:
                c,_=corr(p,x,h,model)
                for gate in ('common','force_accept','own'):
                    bb=update(x,P,p,h,H,0.,gate=gate,common_accept=B['accepted'])
                    cc=update(x,P,p,h,H,c,gate=gate,common_accept=B['accepted'])
                    eb=delta(bb['x'],truth.state[k]);ec=delta(cc['x'],truth.state[k]);difference=delta(cc['x'],bb['x'])
                    target=-bb['K'][:,1]*c
                    aligned=(gate!='own') or bb['accepted']==cc['accepted']
                    chart_cross=abs((cc['x'][2]-truth.state[k,2])-ec[2])>1e-9 or abs((bb['x'][2]-truth.state[k,2])-eb[2])>1e-9
                    chart_cross=chart_cross or abs(target[2])>=np.pi
                    wrapped_target=target.copy();wrapped_target[2]=wrap(wrapped_target[2])
                    closure=float(np.max(abs(difference-wrapped_target))) if aligned else np.nan
                    if aligned and not chart_cross:
                        require(closure<1e-8,'Common-prior state change closure failed')
                    v=bb['K'][:,1]*c
                    dpsi_formula=2*eb[2]*v[2]-v[2]**2;dxy_formula=2*eb[:2]@v[:2]-v[:2]@v[:2]
                    dpsi=eb[2]**2-ec[2]**2;dxy=eb[:2]@eb[:2]-ec[:2]@ec[:2]
                    if aligned and not chart_cross:
                        require(abs(dpsi-dpsi_formula)<1e-10 and abs(dxy-dxy_formula)<1e-10,'One-step loss identity failed')
                    rows.append({**inputs.identity,'source_prior':tr.metadata['arm'],'arm':corr.name,'model_hash':corr.model_hash,'source_hash':inputs.source_hash,'k':k,'t_s':p.t,'gate_policy':gate,
                        'D_s':2*rb*c-c*c,'D_heading_rad2':dpsi,'D_xy_m2':dxy,'formula_heading_rad2':dpsi_formula if aligned and not chart_cross else np.nan,
                        'formula_xy_m2':dxy_formula if aligned else np.nan,'closure':closure,'wrap_chart_cross':chart_cross,
                        'base_accepted':bb['accepted'],'candidate_accepted':cc['accepted'],'gate_changed':bb['accepted']!=cc['accepted'],
                        'measurement_good_heading_bad':(2*rb*c-c*c)>0 and dpsi<0,'heading_good_xy_bad':dpsi>0 and dxy<0,
                        'correction':c,'Kpsi_s':bb['K'][2,1],'Hpsi_s':H[1,2],
                        'Ppsi_x':P[2,0],'Ppsi_y':P[2,1],'Ppsi_bias':P[2,3]})
    return rows


def _time_mse(t,v):
    if len(t)==1:return float(v[0])
    return float(np.trapezoid(v,t)/(t[-1]-t[0]))


def branch_effects(inputs,truth,model,source,correctors,horizons=(0,2,10,30,60,120)):
    records=[];censor=[];linear=[]
    t=inputs.t;starts=np.unique(np.searchsorted(t,np.arange(t[0],t[-1]+1e-10,10.)))
    starts=starts[starts<len(t)];zero=Corrector('BASE')
    for start in starts:
        xs=source.arrays['x_minus'][start].copy();Ps=source.arrays['P_minus'][start].copy()
        base=simulate(inputs,model,zero,start=int(start),x_prior=xs,P_prior=Ps)
        EB=error_arrays(inputs,truth,base)
        for corr in correctors:
            for kind in ('packet','block10s'):
                end=np.nextafter(t[start],np.inf) if kind=='packet' else t[start]+10.
                candidate=simulate(inputs,model,corr,start=int(start),x_prior=xs,P_prior=Ps,active_end=end,diagnostic_allowed=corr.diagnostic)
                EC=error_arrays(inputs,truth,candidate);a=base.arrays;ca=candidate.arrays
                # Frozen BASE matrices, correction re-evaluated on BASE branch priors: explicitly a bookkeeping control.
                dd=np.zeros(4);D=[]
                for j,k in enumerate(a['k'].astype(int)):
                    if j:dd=(np.eye(4)-a['K'][j]@a['H'][j])@a['F'][j]@dd
                    c,_=corr(inputs.packets[k],a['x_minus'][j],a['h'][j],model) if t[k]<end else (0.,{})
                    dd-=a['K'][j,:,1]*c;D.append(dd.copy())
                D=np.array(D);actual=delta(ca['x_plus'],a['x_plus'])
                ident={**inputs.identity,'source_prior':source.metadata['arm'],'arm':corr.name,'model_hash':corr.model_hash,'source_hash':inputs.source_hash,'start_t':t[start],'start_k':int(start),
                       'intervention_kind':kind,'intervention_end_t':float(end),'algorithm_suffix':'BASE','raw_input_sha256':inputs.checksum()}
                for h in (*horizons,'route_end'):
                    requested=t[-1]-t[start] if h=='route_end' else float(h);available=min(requested,t[-1]-t[start])
                    jj=np.searchsorted(a['t'],t[start]+available+1e-10,side='right')-1;jj=max(0,int(jj));s=slice(0,jj+1)
                    r={**ident,'horizon_requested':h,'horizon_available_s':float(a['t'][jj]-t[start]),
                       'right_censored':bool(requested>t[-1]-t[start]+1e-9),'gate_changes':int(np.sum(a['accepted'][s]!=ca['accepted'][s])),
                       'nonlinear_minus_fixed_norm':float(np.linalg.norm(actual[jj]-D[jj]))}
                    for comp in ('heading_deg','xy_cm','radial_cm','tangential_cm','bias_dps'):
                        b,c=EB[comp][s],EC[comp][s]
                        r[comp+'_instant_delta_sq']=float(c[-1]**2-b[-1]**2)
                        r[comp+'_integrated_delta_mse']=_time_mse(a['t'][s],c*c-b*b)
                        r[comp+'_base_peak']=float(np.max(abs(b)));r[comp+'_candidate_peak']=float(np.max(abs(c)))
                        r[comp+'_candidate_q99']=float(np.quantile(abs(c),.99))
                    r['P_delta_fro']=float(np.linalg.norm(ca['P_plus'][jj]-a['P_plus'][jj]));records.append(r)
                    censor.append({**ident,'horizon_requested':h,'available_s':r['horizon_available_s'],'right_censored':r['right_censored']})
                    linear.append({**ident,'horizon_requested':h,**{f'linear_d{c}':D[jj,i] for i,c in enumerate(('x','y','psi','bg'))},
                                   **{f'actual_d{c}':actual[jj,i] for i,c in enumerate(('x','y','psi','bg'))},
                                   'interpretation':'BASE-branch realized matrices; not a filter re-execution'})
    return records,censor,linear
