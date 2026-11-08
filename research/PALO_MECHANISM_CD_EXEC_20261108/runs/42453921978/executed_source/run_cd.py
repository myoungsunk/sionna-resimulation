"""C0-C4/D1-D3 mechanism verification; no detector fitting or RF generation.

Run on GitHub Actions after committing this source. Stage status is written only
following successful checks. Raw rollout arrays and exclusion masks are retained.
"""
from __future__ import annotations
import argparse
import itertools
import json
import os
import platform
import traceback
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from common import *

FIXED_EVENTS=(201,483,485,525,630,962,973)
HORIZONS=(0,1,5,10,20)
ARMS=('OFF','MEAN_ONLY','P_ONLY','ON','NO_BIAS_UPDATE','BIAS_ONLY','SOFT_005','SOFT_010','SOFT_025','SOFT_050')
FUTURES=('s4','off')
NAMES={0:'reference',1:'P',2:'heading',3:'heading+P',4:'position',5:'position+P',6:'position+heading',7:'all'}


def csv(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(path,index=False,compression='gzip' if path.suffix=='.gz' else None)


def maxabs(x):
    return float(np.max(np.abs(x)))


def replay(E,ch,lv,mode,switch=0):
    """Original frozen scalar replay for the pre-science C0 parity gate.

    Never relax the scientific parity contract to accommodate cumulative
    floating-point differences of the vectorized intervention engine.
    """
    import r2_bias_replay as frozen
    c=E.controls[ch,lv];z=E.trace[ch]['z_s'];x,P=E.initial(ch,lv)
    def model(q):
        h,H=E.scalar_lut.model(q,E.case)
        return h[1:],H[1:]
    xs=[];ps=[];pri=[];prp=[];nis=[];used=[]
    for k in range(len(E.t)):
        if k:
            x,P=frozen.predict_one(x,P,float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
        xm,Pm=x.copy(),P.copy()
        u,V,d=E.core.gaussian_update(xm,Pm,np.array([float(z[k])]),model,np.array([[RS]]),gate_threshold=GATE)
        yes=bool(d['accepted']) if E.t[k]<switch or mode=='s4' else False
        x,P=(u,V) if yes else (xm,Pm)
        xs.append(x.copy());ps.append(P.copy());pri.append(xm);prp.append(Pm);nis.append(float(d['NIS']));used.append(yes)
    return dict(X=np.array(xs),P=np.array(ps),prior_X=np.array(pri),prior_P=np.array(prp),nis=np.array(nis),accepted=np.array(used),t=E.t)


def c0(E,out):
    parity=[]; scalar_checks=[]
    for ch,lv in itertools.product(('los','full'),LEVELS):
        original=E.original[ch,lv]
        for mode,idx in [('s4',3),('dr',1)]:
            a=replay(E,ch,lv,mode)
            dx=maxabs(a['X']-original['estimate'][:,idx]);dp=maxabs(a['P']-original['covariance'][:,idx])
            dn=maxabs(a['nis']-original['nis'][:,idx]) if mode=='s4' else 0.
            dm=int(np.sum(a['accepted']!=(original['status'][:,idx]=='APPLIED'))) if mode=='s4' else int(a['accepted'].sum())
            assert dx<=1e-7 and dp<=1e-8 and dn<=1e-7 and dm==0, (ch,lv,mode,dx,dp,dn,dm)
            mineig=float(np.linalg.eigvalsh(a['P']).min());assert mineig>0
            np.savez_compressed(out/f'C0_{ch}_{lv}_{mode}.npz',**a)
            parity.append(dict(channel=ch,level=lv,policy=mode,X_error=dx,P_error=dp,NIS_error=dn,mask_mismatch=dm,min_eig=mineig))
        # Scalar frozen-source comparison independently exercises interpolation and Joseph update.
        s=E.saved[lv,'s4']
        for k in (0,201,483,525,630,973):
            x,P=s['prior_X'][k],s['prior_P'][k]
            h,H,cl=E.observe(x)
            hf,Hf=E.scalar_lut.model(x,E.case)
            assert abs(h-hf[1])<1e-10 and maxabs(H-Hf[1])<1e-10
            u,V,d=E.candidate(x,P,E.trace[ch]['z_s'][k])
            def model(q):
                hh,HH=E.scalar_lut.model(q,E.case);return hh[1:],HH[1:]
            uf,Vf,df=E.core.gaussian_update(x,P,np.array([E.trace[ch]['z_s'][k]]),model,np.array([[RS]]),gate_threshold=None)
            assert maxabs(u-uf)<1e-10 and maxabs(V-Vf)<1e-10 and abs(d['nis']-df['NIS'])<1e-10
            x2=x.copy();x2[3]+=.07
            h2,H2,cl2=E.observe(x2)
            assert h2==h and np.array_equal(H2,H) and H[3]==0
            scalar_checks.append(dict(channel=ch,level=lv,k=k,h_diff=float(abs(h-hf[1])),H_diff=maxabs(H-Hf[1]),candidate_X_diff=maxabs(u-uf),candidate_P_diff=maxabs(V-Vf),clipped=bool(cl)))
    receipt=dict(status='PASS',parity=parity,scalar_checks=scalar_checks)
    dump(out/'C0_QA.json',receipt)
    print('C0 PASS: original S4/DR4 and scalar-model checks',flush=True)
    return receipt


def stage_c(E,out):
    factual=[];comps=[];factorial=[];paired=[];verdicts=[];alpha_rows=[];admissible=[];disagree={}
    qa=dict(candidate_X=0.,candidate_P=0.,candidate_nis=0.,innovation_sum=0.,gain_sum=0.,endpoint_X=0.,endpoint_P=0.,delta_decomposition=0.)
    ks=np.flatnonzero(E.t>=40);z=E.trace['full']['z_s'][ks];truth=E.truth[ks]
    xt=np.c_[truth,np.zeros(len(ks))];hTT,_,ctt=E.observe(xt)
    candidates={}
    for lv,donor in itertools.product(LEVELS,('s4','dr','heading')):
        a=E.saved[lv,donor];x=a['prior_X'][ks];P=a['prior_P'][ks]
        u,V,d=E.candidate(x,P,z)
        for key,diff in [('candidate_X',u-a['candidate_X'][ks]),('candidate_P',V-a['candidate_P'][ks]),('candidate_nis',d['nis']-a['nis'][ks])]:
            qa[key]=max(qa[key],maxabs(diff));assert maxabs(diff)<1e-7,key
        xET=x.copy();xET[:,2]=truth[:,2]
        xTE=x.copy();xTE[:,:2]=truth[:,:2]
        hET,_,cET=E.observe(xET);hTE,_,cTE=E.observe(xTE);hEE=d['h']
        r0=z-hTT;cp=.5*((hTT-hET)+(hTE-hEE));ch=.5*((hTT-hTE)+(hET-hEE));interaction=hEE-hET-hTE+hTT
        qa['innovation_sum']=max(qa['innovation_sum'],maxabs(d['nu']-r0-cp-ch))
        kd=P[:,2,2]*d['H'][:,2]/d['S'];kp=(P[:,2,0]*d['H'][:,0]+P[:,2,1]*d['H'][:,1])/d['S']
        qa['gain_sum']=max(qa['gain_sum'],maxabs(kd+kp-d['K'][:,2]))
        e=errors(x,truth);eu=errors(u,truth);g=(e[:,2]**2-eu[:,2]**2)*DEG**2
        gx=np.sum(e[:,:2]**2-eu[:,:2]**2,axis=1)
        candidates[lv,donor]=(x,P,u,V,d,g,gx)
        for j,k in enumerate(ks):
            no_wrap=abs(e[j,2]+d['step'][j,2]-eu[j,2])<1e-9
            mechanism='beneficial' if g[j]>1e-10 else 'neutral'
            if g[j]<-1e-10:
                mechanism='wrong_direction_or_unneeded' if e[j,2]*d['step'][j,2]>=0 else 'overshoot'
            if not no_wrap:mechanism='circular_wrap'
            base=dict(level=lv,donor=donor,k=int(k),t=float(E.t[k]))
            factual.append(dict(**base,e_deg=float(e[j,2]*DEG),delta_deg=float(d['step'][j,2]*DEG),post_e_deg=float(eu[j,2]*DEG),heading_gain_deg2=float(g[j]),xy_gain_m2=float(gx[j]),nu=float(d['nu'][j]),Kpsi=float(d['K'][j,2]),Kdirect=float(kd[j]),Kcross=float(kp[j]),nis=float(d['nis'][j]),gate=bool(d['nis'][j]<=GATE),Ppsi=float(P[j,2,2]),mechanism=mechanism,clipped=bool(d['clip'][j])))
            comps.append(dict(**base,z=float(z[j]),hTT=float(hTT[j]),hET=float(hET[j]),hTE=float(hTE[j]),hEE=float(hEE[j]),RF_model_residual=float(r0[j]),Full_minus_LoS=float(z[j]-E.trace['los']['z_s'][k]),position_component=float(cp[j]),heading_component=float(ch[j]),interaction=float(interaction[j]),clipped=bool(ctt[j] or cET[j] or cTE[j] or d['clip'][j])))
            hh,xx,both,best=allowed_intervals(e[j,2],d['step'][j,2],e[j,:2],d['step'][j,:2])
            admissible.append(dict(**base,heading_intervals=json.dumps(hh),xy_intervals=json.dumps(xx),joint_intervals=json.dumps(both),joint_positive_exists=bool(both),oracle_heading_alpha=best))
        for alpha in ALPHAS:
            ua,Va=soften(x,P,u,V,d['step'],alpha);ea=errors(ua,truth)
            assert np.linalg.eigvalsh(Va).min()>0
            for j,k in enumerate(ks):
                alpha_rows.append(dict(level=lv,donor=donor,k=int(k),t=float(E.t[k]),alpha=alpha,heading_gain_deg2=float((e[j,2]**2-ea[j,2]**2)*DEG**2),xy_gain_m2=float(np.sum(e[j,:2]**2-ea[j,:2]**2)),Ppsi=float(Va[j,2,2])))
    # All three paired priors; S4->DR is the primary inference population.
    for lv,(da,db) in itertools.product(LEVELS,(('s4','dr'),('s4','heading'),('dr','heading'))):
        xa,Pa,ua,Va,a,ga,gxa=candidates[lv,da];xb,Pb,ub,Vb,b,gb,gxb=candidates[lv,db]
        nus=.5*(a['K'][:,2]+b['K'][:,2])*(b['nu']-a['nu'])
        gains=.5*(a['nu']+b['nu'])*(b['K'][:,2]-a['K'][:,2])
        qa['delta_decomposition']=max(qa['delta_decomposition'],maxabs(b['step'][:,2]-a['step'][:,2]-nus-gains))
        pair_name=da+'__'+db
        if (da,db)==('s4','dr'):
            disagree[lv]=ks[sign_label(ga)!=sign_label(gb)]
        all_g=[];all_gate=[]
        for mask in range(8):
            # b_g co-sourced with heading for exact four-state endpoints.
            # C0 verifies that b_g has NO direct current observation effect.
            x=xa.copy();P=Pb.copy() if mask&1 else Pa.copy()
            if mask&4:x[:,:2]=xb[:,:2]
            if mask&2:x[:,2:]=xb[:,2:]
            u,V,d=E.candidate(x,P,z);e=errors(x,truth);eu=errors(u,truth)
            gh=(e[:,2]**2-eu[:,2]**2)*DEG**2;gx=np.sum(e[:,:2]**2-eu[:,:2]**2,axis=1)
            all_g.append(gh);all_gate.append(d['nis']<=GATE)
            assert np.linalg.eigvalsh(P).min()>0 and np.linalg.eigvalsh(V).min()>0
            if mask in (0,7):
                target=ua if mask==0 else ub;targetP=Va if mask==0 else Vb
                qa['endpoint_X']=max(qa['endpoint_X'],maxabs(u-target));qa['endpoint_P']=max(qa['endpoint_P'],maxabs(V-targetP))
            for j,k in enumerate(ks):
                factorial.append(dict(level=lv,pair=pair_name,primary=da=='s4' and db=='dr',k=int(k),t=float(E.t[k]),mask=mask,changed=NAMES[mask],heading_gain_deg2=float(gh[j]),xy_gain_m2=float(gx[j]),prior_heading_error_deg=float(e[j,2]*DEG),delta_heading_deg=float(d['step'][j,2]*DEG),nu=float(d['nu'][j]),Kpsi=float(d['K'][j,2]),nis=float(d['nis'][j]),gate=bool(d['nis'][j]<=GATE),clipped=bool(d['clip'][j]),h=float(d['h'][j]),Hpsi=float(d['H'][j,2]),Hx=float(d['H'][j,0]),Hy=float(d['H'][j,1]),Ppsi=float(P[j,2,2])))
        gg=np.array(all_g)
        # Mobius factorial contrasts retain interactions; never convert to causal %.
        contrast=gg.copy()
        for bit in (1,2,4):
            for mask in range(8):
                if mask&bit:contrast[mask]-=contrast[mask^bit]
        for j,k in enumerate(ks):
            la,lb=int(sign_label(ga[j])),int(sign_label(gb[j]))
            fits=[]
            if la!=lb:
                fits=[m for m in range(1,8) if int(sign_label(gg[m,j]))==lb]
                minsize=min(m.bit_count() for m in fits)
                minimal=[m for m in fits if m.bit_count()==minsize]
                classification='single_factor_sufficient' if minsize==1 else 'multiple_factors_required'
            else:
                minimal=[];classification='no_endpoint_sign_difference'
            verdicts.append(dict(level=lv,pair=pair_name,primary=(da,db)==('s4','dr'),k=int(k),label_a=la,label_b=lb,both_gate=bool(a['nis'][j]<=GATE and b['nis'][j]<=GATE),classification=classification,minimal_masks=json.dumps(minimal),minimal_factors='|'.join(NAMES[m] for m in minimal),P_alone_flips=bool(la!=lb and int(sign_label(gg[1,j]))==lb),heading_alone_flips=bool(la!=lb and int(sign_label(gg[2,j]))==lb),position_alone_flips=bool(la!=lb and int(sign_label(gg[4,j]))==lb)))
            row=dict(level=lv,pair=pair_name,k=int(k),nu_delta_term_rad=float(nus[j]),gain_delta_term_rad=float(gains[j]),delta_difference_rad=float(b['step'][j,2]-a['step'][j,2]),gate_a=bool(a['nis'][j]<=GATE),gate_b=bool(b['nis'][j]<=GATE))
            row.update({f'contrast_{m}':float(contrast[m,j]) for m in range(1,8)})
            paired.append(row)
    assert len(factorial)==3*4*779*8
    assert all(v<1e-7 for v in qa.values()),qa
    for name,rows in [('factual_events',factual),('innovation_components',comps),('factorial_candidates',factorial),('gain_components',paired),('mechanism_verdicts',verdicts),('admissible_alpha',admissible),('alpha_candidates',alpha_rows)]:
        csv(out/(name+'.csv.gz'),rows)
    dump(out/'C_QA.json',dict(status='PASS',errors=qa,primary_combinations=24928,total_combinations=len(factorial),factual_events=len(factual),alpha_candidates=len(alpha_rows),clipped_factorial=sum(r['clipped'] for r in factorial),warning='State/P exchanges are model-internal interventions; synthetic joint priors need not arise from actual history.'))
    vf=pd.DataFrame(verdicts);summary=[]
    for lv in LEVELS:
        z=vf[(vf.level==lv)&vf.primary]
        s=z[z.label_a!=z.label_b]
        summary.append(dict(level=lv,matched=len(z),disagree=len(s),P_alone=int(s.P_alone_flips.sum()),heading_alone=int(s.heading_alone_flips.sum()),position_alone=int(s.position_alone_flips.sum()),interaction_required=int((s.classification=='multiple_factors_required').sum()),note='Single-factor counts overlap; do not add them.'))
    dump(out/'C_SUMMARY.json',summary)
    print('C1-C4 PASS',summary,flush=True)
    return disagree,summary


def segment_end_index(t,k):
    # No horizon scoring crosses the existing fit/calibration/gap/test boundary.
    bounds=(40.,100.,120.,140.)
    future=[b for b in bounds if b>t[k]+1e-9]
    return (int(np.searchsorted(t,min(future),side='left'))-1) if future else len(t)-1


def initialize_arms(E,x,P,z):
    u,V,d=E.candidate(x,P,z)
    X=np.repeat(x[:,None,:],len(ARMS),axis=1);C=np.repeat(P[:,None,:,:],len(ARMS),axis=1)
    X[:,1]=u;C[:,2]=V;X[:,3]=u;C[:,3]=V
    X[:,4]=u;X[:,4,3]=x[:,3];C[:,4]=V
    X[:,5,3]=u[:,3]  # BIAS_ONLY holds P at prior, explicitly diagnostic.
    for j,alpha in enumerate((.05,.10,.25,.50),6):
        X[:,j],C[:,j]=soften(x,P,u,V,d['step'],alpha)
    return X,C,d


def run_d_chunk(E,lv,donor,starts,future,path):
    """Vectorized cohorts; all arrays double precision; invalid tails masked."""
    saved=E.saved[lv,donor];starts=np.asarray(starts,int);n=len(starts);c=E.controls['full',lv]
    x,P,d=initialize_arms(E,saved['prior_X'][starts],saved['prior_P'][starts],E.trace['full']['z_s'][starts])
    limits=np.minimum(np.array([segment_end_index(E.t,k) for k in starts]),starts+100)
    H=101;A=len(ARMS)
    XX=np.zeros((n,H,A,4));PP=np.zeros((n,H,A,4,4));NN=np.full((n,H,A),np.nan)
    accept=np.zeros((n,H,A),bool);clip=np.zeros((n,H,A),bool);valid=np.zeros((n,H),bool)
    XX[:,0]=x;PP[:,0]=P;NN[:,0]=d['nis'][:,None];clip[:,0]=d['clip'][:,None];valid[:,0]=True
    # alpha/diagnostic interventions are forced at q=0; not regular gate decisions.
    initial_nonzero=np.ones(A,bool);initial_nonzero[0]=False
    accept[:,0]=initial_nonzero
    for q in range(1,H):
        ii=np.flatnonzero(starts+q<=limits)
        if not len(ii):break
        kk=starts[ii]+q
        xm,Pm=E.advance(x[ii],P[ii],c['ds_odom'][kk,None],c['dtheta_gyro'][kk,None],c['dt_s'][kk,None])
        if future=='s4':
            u,V,diag=E.candidate(xm,Pm,E.trace['full']['z_s'][kk,None]);yes=diag['nis']<=GATE
            x[ii]=np.where(yes[...,None],u,xm);P[ii]=np.where(yes[...,None,None],V,Pm)
            NN[ii,q]=diag['nis'];accept[ii,q]=yes;clip[ii,q]=diag['clip']
        else:
            x[ii],P[ii]=xm,Pm
        XX[ii,q]=x[ii];PP[ii,q]=P[ii];valid[ii,q]=True
    actual=PP[valid]
    assert np.isfinite(XX[valid]).all() and np.isfinite(actual).all()
    mineig=float(np.linalg.eigvalsh(actual).min());assert mineig>0
    neg=0.
    if future=='off':
        # P cannot affect mean propagation absent later RF; TWO exact controls.
        neg=max(maxabs(XX[:,:,0][valid]-XX[:,:,2][valid]),maxabs(XX[:,:,1][valid]-XX[:,:,3][valid]))
        assert neg<1e-12,neg
    np.savez_compressed(path,X=XX,P=PP,nis=NN,accepted=accept,clipped=clip,valid=valid,event_k=starts,limits=limits,arm_names=np.array(ARMS),future=np.array(future),donor=np.array(donor),level=np.array(lv),t=E.t)
    reacceptance=[]
    if future=='s4':
        for i,start in enumerate(starts):
            for arm,name in enumerate(ARMS):
                streak=0
                for q in range(1,int(limits[i]-start)+1):
                    if not accept[i,q,arm]:
                        streak+=1
                        continue
                    if streak>=5:
                        k=int(start+q)
                        xp,Pp=E.advance(XX[i,q-1,arm],PP[i,q-1,arm],c['ds_odom'][k],c['dtheta_gyro'][k],c['dt_s'][k])
                        before=score(xp,Pp,E.truth[k]);after=score(XX[i,q,arm],PP[i,q,arm],E.truth[k])
                        record=dict(level=lv,donor=donor,event_k=int(start),k=k,arm=name,preceding_rejects=streak,
                                    prior_heading_abs_deg=float(abs(before['heading_error_rad'])*DEG),
                                    posterior_heading_abs_deg=float(abs(after['heading_error_rad'])*DEG),
                                    prior_xy_m=float(before['xy_error_m']),posterior_xy_m=float(after['xy_error_m']),
                                    Ppsi_before=float(Pp[2,2]),Ppsi_after=float(PP[i,q,arm,2,2]),
                                    heading_nees_before=float(before['heading_nees']),heading_nees_after=float(after['heading_nees']),
                                    xy_nees_before=float(before['xy_nees']),xy_nees_after=float(after['xy_nees']),
                                    heading_P_shrink_error_grow=bool(PP[i,q,arm,2,2]<Pp[2,2] and abs(after['heading_error_rad'])>abs(before['heading_error_rad'])),
                                    xy_P_shrink_error_grow=bool(after['xy_cov_trace']<before['xy_cov_trace'] and after['xy_error_m']>before['xy_error_m']))
                        reacceptance.append(record)
                    streak=0
    if reacceptance:csv(path.with_suffix('.reaccept.csv.gz'),reacceptance)
    summaries=[];exclusions=[]
    for i,k in enumerate(starts):
        for horizon in HORIZONS:
            target=E.t[k]+horizon
            idx=int(np.searchsorted(E.t,target-1e-9));q=idx-k
            eligible=idx<=limits[i] and idx<len(E.t) and abs(E.t[idx]-target)<1e-8
            if not eligible:
                exclusions.append(dict(level=lv,donor=donor,k=int(k),future=future,horizon_s=horizon,reason='source_end' if idx>=len(E.t) else 'split_boundary'))
                continue
            XXi=XX[i,:q+1];PPi=PP[i,:q+1];truth=E.truth[k:k+q+1,None,:]
            scores=score(XXi,PPi,truth)
            he=scores['heading_error_rad']*DEG;xy=scores['xy_error_m']
            ts=E.t[k:k+q+1]
            ih=np.trapezoid(he*he,x=ts,axis=0) if q else np.zeros(A)
            ip=np.trapezoid(xy*xy,x=ts,axis=0) if q else np.zeros(A)
            for arm,name in enumerate(ARMS):
                h0=he[-1,0];p0=xy[-1,0];h1=he[-1,arm];p1=xy[-1,arm]
                summaries.append(dict(level=lv,donor=donor,k=int(k),t=float(E.t[k]),future=future,horizon_s=horizon,arm=name,heading_error_deg=float(h1),xy_error_m=float(p1),bias_error_deg_s=float((XXi[-1,arm,3]-np.deg2rad(BIAS_DEG_S[lv]))*DEG),heading_gain_vs_off_deg2=float(h0*h0-h1*h1),xy_gain_vs_off_m2=float(p0*p0-p1*p1),heading_ise_deg2_s=float(ih[arm]),xy_ise_m2_s=float(ip[arm]),heading_ise_gain_vs_off=float(ih[0]-ih[arm]),xy_ise_gain_vs_off=float(ip[0]-ip[arm]),max_heading_abs_deg=float(np.max(abs(he[:,arm]))),max_xy_m=float(np.max(xy[:,arm])),heading_nees=float(scores['heading_nees'][-1,arm]),xy_nees=float(scores['xy_nees'][-1,arm]),heading_95=bool(scores['heading_nees'][-1,arm]<=3.841458820694124),xy_95=bool(scores['xy_nees'][-1,arm]<=5.991464547107979),Ppsi=float(PPi[-1,arm,2,2]),future_gate_accepts=int(accept[i,1:q+1,arm].sum()),clipped_steps=int(clip[i,:q+1,arm].sum())))
    return summaries,exclusions,dict(level=lv,donor=donor,future=future,events=n,valid_branch_steps=int(valid.sum()*A),negative_control_max=neg,min_cov_eigenvalue=mineig,reacceptance_events=len(reacceptance))


def stage_d(E,out,disagree):
    allrows=[];excluded=[];quality=[];selection=[]
    trace_dir=out/'history_rollouts';trace_dir.mkdir()
    for lv in LEVELS:
        starts=np.union1d(disagree[lv],np.array(FIXED_EVENTS))
        starts=starts[(E.t[starts]>=40)&(starts<len(E.t))]
        for k in starts:
            selection.append(dict(level=lv,k=int(k),t=float(E.t[k]),endpoint_disagreement=bool(k in disagree[lv]),fixed_illustration=k in FIXED_EVENTS))
        for donor,future in itertools.product(('s4','dr'),FUTURES):
            for chunk in range(0,len(starts),32):
                part=starts[chunk:chunk+32]
                p=trace_dir/f'{lv}_{donor}_{future}_{chunk//32:03d}.npz'
                rows,ex,q=run_d_chunk(E,lv,donor,part,future,p)
                allrows.extend(rows);excluded.extend(ex);quality.append(q)
            print('D completed',lv,donor,future,'events',len(starts),flush=True)
    csv(out/'D_events.csv',selection)
    csv(out/'D_horizon_outcomes.csv.gz',allrows)
    csv(out/'D_exclusions.csv.gz',excluded)
    csv(out/'D_rollout_QA.csv',quality)
    reaccept_files=sorted(trace_dir.glob('*.reaccept.csv.gz'))
    if reaccept_files:
        pd.concat([pd.read_csv(p) for p in reaccept_files],ignore_index=True).to_csv(out/'D_reacceptance_events.csv.gz',index=False,compression='gzip')
    rr=pd.DataFrame(allrows)
    group=rr.groupby(['level','donor','future','horizon_s','arm'])
    agg=group.agg(n=('k','size'),heading_gain_sum=('heading_gain_vs_off_deg2','sum'),xy_gain_sum=('xy_gain_vs_off_m2','sum'),heading_ise_gain_sum=('heading_ise_gain_vs_off','sum'),xy_ise_gain_sum=('xy_ise_gain_vs_off','sum'),heading_95_fraction=('heading_95','mean'),xy_95_fraction=('xy_95','mean'),heading_nees_mean=('heading_nees','mean'),xy_nees_mean=('xy_nees','mean')).reset_index()
    agg.to_csv(out/'D_summary.csv',index=False)
    # Difference-in-differences identifies the interaction of mean and P pathways.
    piv=rr.pivot(index=['level','donor','k','future','horizon_s'],columns='arm',values=['heading_ise_deg2_s','xy_ise_m2_s'])
    inter=pd.DataFrame(index=piv.index)
    for metric in ('heading_ise_deg2_s','xy_ise_m2_s'):
        inter[metric+'_interaction']=piv[metric]['ON']-piv[metric]['MEAN_ONLY']-piv[metric]['P_ONLY']+piv[metric]['OFF']
    inter.reset_index().to_csv(out/'D_mean_P_interactions.csv.gz',index=False,compression='gzip')
    # Cold DR vs prior fused-history RF-off: distinct histories, same future rule.
    coldhot=[]
    for lv,switch,mode in itertools.product(LEVELS,(0,140),('s4','off')):
        a=replay(E,'full',lv,mode,switch=switch)
        np.savez_compressed(out/f'D_history_full_{lv}_{mode}_switch{switch}.npz',**a)
        mask=E.t>=max(40,switch);ss=score(a['X'][mask],a['P'][mask],E.truth[mask])
        coldhot.append(dict(level=lv,switch=switch,mode=mode,n=int(mask.sum()),heading_rmse_deg=float(np.sqrt(np.mean(ss['heading_error_rad']**2))*DEG),xy_rmse_m=float(np.sqrt(np.mean(ss['xy_error_m']**2))),heading_nees=float(np.mean(ss['heading_nees'])),xy_nees=float(np.mean(ss['xy_nees'])),scope='history reference, not a new detector'))
    csv(out/'D_cold_hot_references.csv',coldhot)
    receipt=dict(status='PASS',event_level_pairs=len(selection),cohort_batches=len(quality),raw_branch_steps=sum(x['valid_branch_steps'] for x in quality),horizon_rows=len(allrows),excluded_horizon_cohorts=len(excluded),negative_control_max=max(x['negative_control_max'] for x in quality),reacceptance_events=sum(x['reacceptance_events'] for x in quality),min_cov_eigenvalue=min(x['min_cov_eigenvalue'] for x in quality),warning='Policy-events share RF, controls and truth; not independent trials. Forced q=0 interventions bypass the gate only at the intervention.')
    dump(out/'D_QA.json',receipt)
    return receipt


def write_report(out,summary,dqa):
    lines=['# PALO C·D 메커니즘 검증 실행 결과','','상태: C0 원본 재현 및 C/D 검산 통과. 독립 과학 감사·온라인 판별기·독립 RF 일반화 검증은 수행하지 않음.','',
    '## C: 같은 RF의 손익 반전 원인','각 값은 전체 후보의 국소 요인 교환 결과다. 단일 요인의 충분성은 서로 겹치며 합산하거나 인과 기여율로 환산하지 않는다.','',
    '|조건|endpoint 손익 상이|P만 교체로 target 부호 재현|헤딩만|위치만|복수 요인 변경 필요|','|---|---:|---:|---:|---:|---:|']
    for r in summary:lines.append(f"|{r['level']}|{r['disagree']}|{r['P_alone']}|{r['heading_alone']}|{r['position_alone']}|{r['interaction_required']}|")
    lines+=['','## D: 이력·평균·공분산·바이어스 개입',f"사건-수준 조합 {dqa['event_level_pairs']}; 저장된 유효 branch-step {dqa['raw_branch_steps']}; RF-off negative control 최대차 {dqa['negative_control_max']:.3e}.",
    '미래 RF-off에서는 평균이 같고 P만 다른 분기의 평균 궤적이 같아야 한다. 미래 S4 규칙에서의 차이는 공분산→후속 gain/gate→평균 경로를 별도로 검사한다.',
    'D_summary.csv와 D_mean_P_interactions.csv.gz는 사건별 원자료에서 계산한 지연 손익과 mean/P 상호작용이다. mean-only·P-only·bias-only는 진단 분기이며 올바른 Bayesian posterior라고 주장하지 않는다.',
    '', '## 해석 제한','- C의 혼합 평균/P는 실제 이력에서 생성 가능한 공동 prior임을 보장하지 않는다.','- D는 저장된 공통 prior에서 현재 사건을 바꾼 뒤 실제 같은 운동·RF와 인과 규칙으로 진행한다. 과거 모든 사건의 전역 기여분을 증명하지 않는다.','- horizon은 fit/calibration/gap/test 경계를 넘으면 제외한다. 끝부분 사건을 20초 결과에 포함하지 않는다.','- 참값은 오프라인 성분분해·손익·필요 범위 계산에만 사용한다. 새 판정기를 학습하지 않는다.','- 작은 NEES나 큰 포함률을 통계적 공분산 보정 성공으로 해석하지 않는다.','- 결과를 보기 전 동결된 계약과 전체 raw X/P/masks를 함께 보존한다.']
    (out/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,default=Path('cache'));ap.add_argument('--output',type=Path,required=True);ap.add_argument('--download',action='store_true');args=ap.parse_args()
    if args.output.exists():raise RuntimeError('OUTPUT_EXISTS: refusing to overwrite evidence')
    args.output.mkdir(parents=True)
    for name in ('SOURCE_CODE_SHA256.json','EXECUTION_CONTRACT_KO.md','DESIGN_SOURCE_KO.md'):
        source=Path(name)
        if source.exists():(args.output/('SOURCE_'+name)).write_bytes(source.read_bytes())
    contract=dict(question='C/D same-RF mechanism verification',design_commit=DESIGN_SHA,input_commit=INPUT_SHA,gap_commit=GAP_SHA,source_sha=os.environ.get('GITHUB_SHA'),github_run_id=os.environ.get('GITHUB_RUN_ID'),environment=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__),alpha_grid=ALPHAS,fixed_events=FIXED_EVENTS,horizons=HORIZONS,arms=ARMS,futures=FUTURES,truth='offline diagnostics and scores only; no online selector is fit',primary='S4 vs DR; full; 4 levels x779; all gate-before candidates',D_events='all primary endpoint sign disagreements plus predeclared illustrations, BOTH S4 and DR checkpoints',horizon_boundary='same 40/100/120/140 split segment; truncated horizons excluded',started=datetime.now(timezone.utc).isoformat())
    dump(args.output/'EXECUTION_CONTRACT.json',contract)
    try:
        if args.download:download_inputs(args.cache,args.output)
        E=Engine(args.cache)
        c0_result=c0(E,args.output)
        disagree,summary=stage_c(E,args.output)
        dqa=stage_d(E,args.output,disagree)
        write_report(args.output,summary,dqa)
        dump(args.output/'EXECUTION_COMPLETE.json',dict(status='COMPLETE_SELF_CHECK_PASS',finished=datetime.now(timezone.utc).isoformat(),independent_audit=False,source_sha=contract['source_sha'],github_run_id=contract['github_run_id']))
        manifest={str(p.relative_to(args.output)):dict(bytes=p.stat().st_size,sha256=sha256(p.read_bytes())) for p in sorted(args.output.rglob('*')) if p.is_file()}
        dump(args.output/'OUTPUT_SHA256.json',manifest)
    except Exception as exc:
        dump(args.output/'FAILURE.json',dict(status='FAILED_NOT_PUBLISHABLE',error=repr(exc),traceback=traceback.format_exc()))
        raise

if __name__=='__main__':main()
