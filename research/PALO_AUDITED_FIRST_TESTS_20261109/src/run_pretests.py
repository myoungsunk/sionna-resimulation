#!/usr/bin/env python3
"""Execute ordered first tests with separate source/math/array audit receipts.
New inference gets only sensor inputs and initial condition. Ground truth is
used here solely for source-data generation compatibility and scoring.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import logsumexp
import minimal_models as m
import audit_checks as audit

LEVELS={'B0':0.,'L0':.01,'L1':.05,'L2':.2}
CASES=('R2_aB_m0','R4_aA_m0','R5_aA_m0','R5_aB_m0')
EVENTS={'R2_aB_m0':(201,483,525),'R4_aA_m0':(300,450,600),
        'R5_aA_m0':(500,900,1150),'R5_aB_m0':(500,900,1150)}
DEG=180/np.pi
R2_ZIP_SHA='46c6070a138f181d73f21796160fba1d52291faef1097f77d205963ddc12e140'

def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def rms(x):return float(np.sqrt(np.mean(np.asarray(x)**2)))

def load_engine(root):
    sys.path.insert(0,str(Path(root)/'vendor'))
    import common
    e=common.Engine(Path(root)/'cache')
    return e

def metric_rows(t,truth,bias,data,meta):
    X,P=data['X'],data['P'];v=X[:,:3]-truth;v[:,2]=m.wrap(v[:,2]);xy=np.linalg.norm(v[:,:2],axis=1)
    bh=X[:,3]-np.deg2rad(bias)
    nh=v[:,2]**2/P[:,2,2];nb=bh**2/P[:,3,3]
    nx=np.einsum('ni,ni->n',v[:,:2],np.linalg.solve(P[:,:2,:2],v[:,:2,None])[:,:,0])
    windows={'all':t>=40,'late':t>=140,'early':(t>=40)&(t<120)}
    ans=[]
    for name,mask in windows.items():
        if not mask.any():continue
        r=dict(**meta,window=name,n=int(mask.sum()),heading_rmse_deg=rms(v[mask,2])*DEG,
          xy_rmse_m=rms(xy[mask]),bias_rmse_deg_s=rms(bh[mask])*DEG,
          heading_q95_deg=float(np.quantile(abs(v[mask,2]),.95)*DEG),
          heading_q99_deg=float(np.quantile(abs(v[mask,2]),.99)*DEG),
          heading_max_deg=float(abs(v[mask,2]).max()*DEG),xy_q99_m=float(np.quantile(xy[mask],.99)),
          heading95=float(np.mean(nh[mask]<=3.841458820694124)),
          xy95_moment_ellipse=float(np.mean(nx[mask]<=5.991464547107979)),
          bias95_moment_interval=float(np.mean(nb[mask]<=3.841458820694124)),
          heading_nees_moment=float(np.mean(nh[mask])),xy_nees_moment=float(np.mean(nx[mask])),
          bias_nees_moment=float(np.mean(nb[mask])),heading_sigma_rms_deg=rms(np.sqrt(P[mask,2,2]))*DEG)
        if 'accepted' in data:r['accepted']=int(data['accepted'][mask].sum())
        if 'weights' in data:
            r['p_on_mean']=float(data['p_on'][mask].mean());r['discarded_mass_mean']=float(data['discarded_mass'][mask].mean())
            r['discarded_mass_q99']=float(np.quantile(data['discarded_mass'][mask],.99))
            r['predictive_nll_mean']=float(-data['log_predictive'][mask].mean())
            r['covariance_interpretation']='mixture moment surrogate; see actual mixture HPD/NLPD'
            r['heading_HPD95']=float(data['heading_HPD_hit'][mask].mean())
            r['heading_HPD_width_deg']=float(data['heading_HPD_width'][mask].mean()*DEG)
            r['heading_mixture_NLPD']=float(data['heading_NLPD'][mask].mean())
            r['heading_MAP_rmse_deg']=rms(data['heading_MAP_error'][mask])*DEG
            r['best_retained_heading_rmse_ORACLE_deg']=rms(data['best_retained_error'][mask])*DEG
        else:r['covariance_interpretation']='single Gaussian local tangent diagnostic'
        ans.append(r)
    blocks=[]
    for start in range(40,int(t[-1])+1,10):
        q=(t>=start)&(t<start+10)
        if q.sum()<10:continue
        blocks.append(dict(**meta,start_s=start,n=int(q.sum()),heading_rmse_deg=rms(v[q,2])*DEG,
           heading_max_deg=float(abs(v[q,2]).max()*DEG),xy_rmse_m=rms(xy[q]),bias_rmse_deg_s=rms(bh[q])*DEG))
    return ans,blocks

def add_mixture_scores(out,truth):
    """Offline score only; wrap density on full circle, no Gaussian NEES
    certification for a multimodal posterior. HPD grid is resolution-audited.
    """
    n=len(truth);hit=np.zeros(n,bool);width=np.zeros(n);nlpd=np.zeros(n);best=np.zeros(n);emap=np.zeros(n)
    masserr=0.;checks=[]
    for k in range(n):
        b=int(out['counts'][k]);w=out['weights'][k,:b];mu=out['component_X'][k,:b,2]
        sd=np.sqrt(out['component_P'][k,:b,2,2]);err=m.wrap(truth[k,2]-mu)
        best[k]=np.min(abs(err));emap[k]=err[np.argmax(w)]
        def dens(x):
            d=m.wrap(x[:,None]-mu[None,:]);den=np.zeros_like(d)
            for shift in (-2,-1,0,1,2):den+=np.exp(-.5*((d+shift*2*np.pi)/sd)**2)/(np.sqrt(2*np.pi)*sd)
            return den@w
        ngrid=4096
        if sd.min()<.0015:ngrid=16384
        grid=np.linspace(-np.pi,np.pi,ngrid,endpoint=False);p=dens(grid);step=2*np.pi/ngrid
        mass=float(p.sum()*step);masserr=max(masserr,abs(mass-1))
        ps=np.sort(p)[::-1];cut=ps[min(len(ps)-1,np.searchsorted(np.cumsum(ps)*step,.95))]
        at=float(dens(np.array([truth[k,2]]))[0]);hit[k]=at>=cut;width[k]=np.count_nonzero(p>=cut)*step
        nlpd[k]=-math.log(max(at,1e-300))
        if k in (201,483,590,850):
            finer=np.linspace(-np.pi,np.pi,ngrid*2,endpoint=False);pf=dens(finer)
            order=np.sort(pf)[::-1];cut2=order[min(len(order)-1,np.searchsorted(np.cumsum(order)*step/2,.95))]
            checks.append(dict(k=k,coarse_hit=bool(hit[k]),fine_hit=bool(at>=cut2),width_diff_deg=float(abs(width[k]-np.count_nonzero(pf>=cut2)*step/2)*DEG)))
    audit.check(masserr<1e-5,'CIRCULAR_MIXTURE_DENSITY_INTEGRAL')
    out.update(heading_HPD_hit=hit,heading_HPD_width=width,heading_NLPD=nlpd,
               best_retained_error=best,heading_MAP_error=emap)
    return dict(grid_mass_max_error=masserr,resolution_checks=checks)

def scores_independent(data,truth,bias,t,rows):
    # Recompute load-bearing whole-cohort numbers using scalar Python arithmetic.
    sel=np.where(t>=40)[0]
    he=[];xe=[];be=[]
    for i in sel:
        dif=float(data['X'][i,2]-truth[i,2]);angle=math.atan2(math.sin(dif),math.cos(dif))
        he.append((angle*DEG)**2)
        xe.append(float(sum((data['X'][i,j]-truth[i,j])**2 for j in (0,1))))
        be.append((data['X'][i,3]*DEG-bias)**2)
    expected=[math.sqrt(sum(a)/len(a)) for a in (he,xe,be)]
    allrow=next(x for x in rows if x['window']=='all')
    actual=[allrow[f] for f in ('heading_rmse_deg','xy_rmse_m','bias_rmse_deg_s')]
    difference=max(abs(a-b) for a,b in zip(actual,expected))
    audit.check(difference<1e-10,'INDEPENDENT_METRIC_RECOUNT')
    return difference

def do_withdrawals(e,u,z,x0,truth,t,baseline,meta,outdir):
    results=[];qa=[];exclusions=[]
    for start in EVENTS[meta['case']]:
        group=tuple(range(start,start+3));max_end=min(len(z)-1,start+50-1+100)
        # Separate scalar whole-history no-factor reference.
        reference=audit.fresh_reference(e,u,z,x0,max_end,set(group))
        for sec,lag in ((2,10),(5,25),(10,50)):
            decision=start+lag-1
            if decision>=len(z):
                exclusions.append(dict(**meta,start=start,lag_s=sec,reason='NO_DECISION_FRAME'));continue
            keep=m.replay(e,u,z,start,max_end,baseline['prior_X'][start],baseline['prior_P'][start])
            drop=m.replay(e,u,z,start,max_end,baseline['prior_X'][start],baseline['prior_P'][start],omit=group)
            ex=audit.errmax(drop['X'],reference['X'][start:max_end+1]);ep=audit.errmax(drop['P'],reference['P'][start:max_end+1])
            ek=audit.errmax(keep['X'],baseline['X'][start:max_end+1]);pk=audit.errmax(keep['P'],baseline['P'][start:max_end+1])
            audit.check(ex<1e-7 and ep<1e-8 and ek<1e-7 and pk<1e-8,f'WITHDRAW_FRESH_XP_PARITY:{meta}:{start}:{sec}:{ex,ep,ek,pk}')
            audit.check(not drop['accepted'][:3].any(),'WITHDRAW_FACTOR_NOT_REMOVED')
            endidx=decision-start
            # Only post-group validation evidence up to current decision time.
            logBF=float(drop['log_score'][3:endidx+1].sum()-keep['log_score'][3:endidx+1].sum())
            chosen_drop=logBF>math.log(9.)
            delayed={}
            for arm,arr in (('KEEP',keep),('DROP',drop)):
                window={k:v[:endidx+1] for k,v in arr.items()}
                sx,sP=m.rts(window)
                audit.check(np.linalg.eigvalsh(sP).min()>0,'RTS_COV_NOT_PD')
                delayed[arm]=(sx,sP)
            raw=dict(t=t[start:max_end+1],truth=truth[start:max_end+1],start=start,decision=decision,
                     omitted_ids=np.array(group),logBF=logBF,selected_drop=chosen_drop)
            for arm,arr in (('keep',keep),('drop',drop)):
                for key,val in arr.items():raw[f'{arm}_{key}']=val
            raw['keep_smoothed_X'],raw['keep_smoothed_P']=delayed['KEEP']
            raw['drop_smoothed_X'],raw['drop_smoothed_P']=delayed['DROP']
            fname=f"{meta['channel']}_{meta['level']}_event{start}_lag{sec}.npz"
            np.savez_compressed(outdir/fname,**raw)
            qa.append(dict(**meta,start=start,decision=decision,lag_s=sec,
                fresh_state_max=ex,fresh_cov_max=ep,keep_state_max=ek,keep_cov_max=pk,
                original_group_accepted=int(keep['accepted'][:3].sum()),removed_observations=len(group),
                logBF=logBF,selected_drop=chosen_drop,unique_used_ids=True))
            for horizon in (0,10,20):
                idx=endidx+int(horizon/.2)
                if idx>=len(keep['X']):
                    exclusions.append(dict(**meta,start=start,lag_s=sec,horizon_s=horizon,reason='INSUFFICIENT_FUTURE'));continue
                baseerr=m.wrap(keep['X'][idx,2]-truth[start+idx,2])*DEG
                basexy=float(np.sum((keep['X'][idx,:2]-truth[start+idx,:2])**2))
                for arm in ('KEEP','DROP','SELECTED'):
                    arr=drop if arm=='DROP' or (arm=='SELECTED' and chosen_drop) else keep
                    eh=float(m.wrap(arr['X'][idx,2]-truth[start+idx,2])*DEG)
                    epv=arr['X'][idx,:2]-truth[start+idx,:2];xy=float(epv@epv)
                    tail=slice(endidx,idx+1)
                    he=m.wrap(arr['X'][tail,2]-truth[start+endidx:start+idx+1,2])*DEG
                    hh=m.wrap(keep['X'][tail,2]-truth[start+endidx:start+idx+1,2])*DEG
                    results.append(dict(**meta,start=start,decision=decision,lag_s=sec,horizon_s=horizon,arm=arm,
                        logBF=logBF,selected_drop=chosen_drop,heading_error_deg=eh,xy_error_m=math.sqrt(xy),
                        heading_gain_deg2=float(baseerr**2-eh**2),xy_gain_m2=float(basexy-xy),
                        heading_ISE_gain_deg2_s=float(np.trapezoid(hh**2-he**2,dx=.2)),
                        bias_error_deg_s=float(arr['X'][idx,3]*DEG-LEVELS[meta['level']]),
                        heading95=bool(eh**2<=3.841458820694124*arr['P'][idx,2,2]*DEG**2),
                        delayed_start_error_deg=float(m.wrap(delayed['DROP' if arr is drop else 'KEEP'][0][0,2]-truth[start,2])*DEG)))
    return results,qa,exclusions

def load_data(e,root,caseid):
    if caseid=='R2_aB_m0':
        return e.case,e.t,e.truth,e.trace['full']['pose_id'],{ch:e.trace[ch]['z_s'] for ch in ('full','los')},{'source':'verified single-metric artifact','sha256':R2_ZIP_SHA}
    sys.path.insert(0,str(Path(root).resolve()))
    import route_loader
    here=os.getcwd();os.chdir(root)
    try:case,t,truth,pose,obs,fp,info=route_loader.load_case(caseid)
    finally:os.chdir(here)
    return case,t,truth,pose,obs,dict(info,download_receipts=route_loader.INPUTS)

def run_case(root,caseid,outroot):
    e=load_engine(root);case,t,truth,pose,obs,provenance=load_data(e,root,caseid);e.case=case
    folder=Path(outroot)/caseid;folder.mkdir(parents=True,exist_ok=False)
    (folder/'trajectories').mkdir();(folder/'withdrawals').mkdir()
    frozen=Path(root)/'cache/pol/experiments/POL_FGO_CORR_20261106_v1/frozen/repo/research/EKF4_RANGE_S_STAGED_20261014'
    sys.path.insert(0,str(frozen));import r2_bias_replay as r2
    results=[];blocks=[];info=[];fisherqa=[];mixqa=[];sourceqa=[];eventrows=[];eventqa=[];exclusions=[]
    baselines={};controls={};xinit={}
    for lv,b in LEVELS.items():
        if caseid=='R2_aB_m0':u=e.controls['full',lv];x0,_=e.initial('full',lv)
        else:
            u,p0=r2.build_positive_bias_controls(t,truth,lv,seed=0);x0=np.r_[p0,0.]
        controls[lv]=u;xinit[lv]=x0
        for ch in ('full','los'):
            for name,gate in (('DR',None),('S4',m.GATE),('NIS05',.5),('NIS2',2.)):
                start=time.perf_counter();out=m.run_baseline(e,u,obs[ch],x0,gate);dt=time.perf_counter()-start
                q=audit.state_qa(out);q.update(channel=ch,level=lv,policy=name)
                if caseid=='R2_aB_m0' and name in ('DR','S4'):
                    q['original_parity']=audit.baseline_parity(out,e.original[ch,lv],1 if name=='DR' else 3,name=='S4')
                if name=='S4':q['derivatives']=audit.audit_jacobians(e,u,out)
                sourceqa.append(q);baselines[ch,lv,name]=out
                meta=dict(case=caseid,channel=ch,level=lv,policy=name)
                rr,bb=metric_rows(t,truth,b,out,meta);results+=rr;blocks+=bb
                q['metric_recount_max']=scores_independent(out,truth,b,t,rr)
                np.savez_compressed(folder/'trajectories'/f'{ch}_{lv}_{name}.npz',t=t,truth=truth,**out)
                print('BASELINE',caseid,ch,lv,name,'elapsed',round(dt,2),flush=True)
    # Ordered stage 1: all source checks above precede new scientific tests.
    for ch in ('full','los'):
      for lv in ('B0','L2'):
       u=controls[lv]
       for donor in ('S4','DR'):
        a=baselines[ch,lv,donor]
        for sec,n in ((1,5),(2,10),(5,25)):
         for start in range(200,len(t)-n+1,n):
          for rho in (0.,.5,.9):
            row,test=m.window_info(e,u,a['prior_X'][start],a['prior_P'][start],obs['full'],obs['los'],start,n,rho)
            row.update(case=caseid,channel=ch,level=lv,donor=donor,window_s=sec,t0=float(t[start]))
            info.append(row);fq=audit.projection_audit(test);fisherqa.append(fq)
    pd.DataFrame(info).to_csv(folder/'INFORMATION_WINDOWS.csv',index=False)
    dump(folder/'STAGE1_AUDIT.json',dict(status='PASS',windows=len(info),
        max_matrix_relative_error=max(x['matrix_relative_error'] for x in fisherqa),
        max_augmented_cov_error=max(x['augmented_cov_error'] for x in fisherqa),
        min_monotonic_eigen=min(x['min_information_loss_eigen'] for x in fisherqa)))
    print('STAGE1_PASS',caseid,len(info),flush=True)
    # Stage2: fixed predeclared 2-mode model; no re-tuning after output.
    for ch in ('full','los'):
     for lv,b in LEVELS.items():
      u=controls[lv];x0=xinit[lv]
      for name,cap,col in (('COLLAPSE',1,True),('TWO',2,False),('FOUR',4,False)):
        begin=time.perf_counter();out=m.run_mixture(e,u,obs[ch],x0,cap,col);runsecs=time.perf_counter()-begin
        q=audit.audit_mixture(e,u,obs[ch],x0,out,col);q.update(audit.state_qa(out))
        q.update(add_mixture_scores(out,truth));q.update(case=caseid,channel=ch,level=lv,policy=name,run_seconds=runsecs)
        meta=dict(case=caseid,channel=ch,level=lv,policy=name)
        rr,bb=metric_rows(t,truth,b,out,meta);results+=rr;blocks+=bb
        q['metric_recount_max']=scores_independent(out,truth,b,t,rr);mixqa.append(q)
        np.savez_compressed(folder/'trajectories'/f'{ch}_{lv}_{name}.npz',t=t,truth=truth,**out)
        print('STAGE2_PASS',caseid,ch,lv,name,'seconds',round(runsecs,2),flush=True)
    # Stage3: event-level withdrawal; not a completed online full-route optimizer.
    for ch in ('full','los'):
     for lv in LEVELS:
        meta=dict(case=caseid,channel=ch,level=lv)
        rr,qq,ee=do_withdrawals(e,controls[lv],obs[ch],xinit[lv],truth,t,baselines[ch,lv,'S4'],meta,folder/'withdrawals')
        eventrows+=rr;eventqa+=qq;exclusions+=ee
        print('STAGE3_PASS',caseid,ch,lv,len(qq),'events',flush=True)
    pd.DataFrame(results).to_csv(folder/'METRICS.csv',index=False)
    pd.DataFrame(blocks).to_csv(folder/'BLOCKS.csv',index=False)
    pd.DataFrame(eventrows).to_csv(folder/'WITHDRAWAL_OUTCOMES.csv',index=False)
    pd.DataFrame(eventqa).to_csv(folder/'WITHDRAWAL_AUDIT.csv',index=False)
    pd.DataFrame(exclusions).to_csv(folder/'EXCLUSIONS.csv',index=False)
    dump(folder/'REUSED_SOURCE_AUDIT.json',sourceqa);dump(folder/'MIXTURE_REPLAY_AUDIT.json',mixqa)
    dump(folder/'PROVENANCE.json',provenance)
    manifest={str(p.relative_to(folder)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.rglob('*') if p.is_file()}
    dump(folder/'SHA256.json',manifest)
    dump(folder/'CASE_PASS.json',dict(case=caseid,status='NUMERICAL_AUDIT_PASS_NOT_SCIENTIFIC_ADOPTION',
        stage1_windows=len(info),stage2_component_steps=sum(x['retained_component_steps'] for x in mixqa),
        stage3_events=len(eventqa),excluded_horizons=len(exclusions),metric_rows=len(results),
        audit_independence='same author, different mathematical/code path, no external audit'))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path('.'))
    ap.add_argument('--out',type=Path,default=Path('results'));ap.add_argument('--case',choices=CASES)
    ap.add_argument('--unit',action='store_true');args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if args.unit:
        q=audit.synthetic_audit(m);q['gt_leak_audit']=audit.leak_audit(Path(m.__file__))
        dump(args.out/'UNIT_AUDIT.json',q);print(json.dumps(q))
    else:run_case(args.root.resolve(),args.case,args.out.resolve())
