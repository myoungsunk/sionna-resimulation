"""Executable S0--S7 stages, with scope completeness, evidence receipts and no hidden fallbacks."""
from __future__ import annotations
from pathlib import Path
import itertools
import importlib.metadata
import json
import numpy as np
import pandas as pd
import joblib
from .common import (Workspace, Inputs, Trace, REFERENCE_SHA, CASES, BIASES, SEEDS, CANDIDATES,
                     require, BlockedError, file_hash, write_json, read_json, exact_rows)
from .runtime_features import Corrector
from .native import NativeAssets
from .replay import simulate,update
from .oracle_scoring import OracleCorrector,score_trace,error_arrays,all4_budget,process_noise_statistics
from .diagnostics import s1,s2,common_prior,branch_effects,perturbations
from .training import native_learning_data,FitLineage,fit_omega,train_route,load_candidate
from .temporal import fit_spectral_metric,s6
from .scorecard import compare,ledger
from .numerics import response_pair,wrap,delta,time_block_sensitivity


def units(cfg,*,native_los=False):
    for case,bias,seed in itertools.product(cfg.get('cases',CASES),cfg.get('biases',BIASES),cfg.get('seeds',SEEDS)):
        yield case,bias,int(seed),'full'
    if native_los:
        for case,seed in itertools.product(cfg.get('cases',CASES),cfg.get('seeds',SEEDS)):
            yield case,'B0',int(seed),'los'


def trace_path(ws,stage,inp,arm):return ws.root/stage/'traces'/f'{inp.tag}__{arm}.npz'


def frozen_correctors(assets,inp,truth):
    return [Corrector('BASE'),assets.legacy(inp.route,'PCIR3'),assets.legacy(inp.route,'PWIDE_NOES'),
            assets.legacy(inp.route,'WIDE_NOES'),OracleCorrector(inp,truth),Corrector('RANGE_ONLY'),Corrector('BASE_ETA2')]


def candidates(ws,route):return [load_candidate(ws.root/'S3'/'models',route,m) for m in CANDIDATES]


def prior_traces(ws,inp):
    return [Trace.load(trace_path(ws,'S0',inp,name)) for name in ('BASE','PWIDE_NOES','RANGE_ONLY')]


def append_tables(acc,tables):
    for name,rows in tables.items():acc.setdefault(name,[]).extend(rows)


def save_tables(ws,stage,tables):
    for name,rows in tables.items():ws.table(stage,name,rows)


def run_s0(ws,assets):
    parity=[];schemas=[];inputslog=[];summary=[];process_rows=[];full_ref=pd.read_csv(assets.ref/'research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_eb2_mc/MC_ALL.csv')
    for case,bias,seed,ch in units(ws.config,native_los=True):
        inp,model,truth=assets.load(case,bias,seed,ch);correctors=frozen_correctors(assets,inp,truth);traces={}
        for corr in correctors:
            tr=simulate(inp,model,corr,diagnostic_allowed=corr.diagnostic);tr.save(trace_path(ws,'S0',inp,corr.name));traces[corr.name]=tr
            scored,_=score_trace(inp,truth,tr);summary+=scored
            # Independently call the original strict_common function on every recorded prior/update.
            mx=0.;mp=0.;gate_errors=0
            for k,p in enumerate(inp.packets):
                a=tr.arrays;z=p.z.copy();z[1]-=a['correction'][k];Rupdate=p.R*(2 if corr.name=='BASE_ETA2' else 1)
                xo,Po,ni,acc=assets.S.update(a['x_minus'][k:k+1],a['P_minus'][k:k+1],z,a['h'][k:k+1],a['H'][k:k+1],
                                           p.mu[None],p.mu[None],p.R[None],Rupdate[None],np.array([corr.name=='RANGE_ONLY']))
                mx=max(mx,float(np.max(abs(delta(xo[0],a['x_plus'][k])))));mp=max(mp,float(np.max(abs(Po[0]-a['P_plus'][k]))));gate_errors+=int(bool(acc[0])!=bool(a['accepted'][k]))
            require(max(mx,mp)<1e-9 and gate_errors==0,'Original single-update parity failed')
            parity.append({**inp.identity,'arm':corr.name,'check':'all_intermediate_updates','max_x_error':mx,'max_P_error':mp,'gate_mismatches':gate_errors,'status':'PASS'})
            schemas.append({**inp.identity,'arm':corr.name,'arrays':json.dumps({k:list(v.shape) for k,v in tr.arrays.items()})})
        # Independent original 3-arm full recursive implementation, not the new replay helper.
        X,C,acc=assets.independent_reference(inp,truth,model)
        for j,name in enumerate(('BASE','PWIDE_NOES','ORACLE')):
            a=traces[name].arrays
            minus_x=np.empty_like(X[:,j]);minus_P=np.empty_like(C[:,j]);minus_x[0]=inp.x0;minus_P[0]=inp.P0
            for k in range(1,len(inp.packets)):
                minus_x[k],minus_P[k]=assets.V.predict_one(X[k-1,j].copy(),C[k-1,j].copy(),*map(float,inp.controls[k]))
            require(np.max(abs(delta(minus_x,a['x_minus'])))<1e-7 and np.max(abs(minus_P-a['P_minus']))<1e-7,'Original intermediate prior parity failed')
            ex=float(np.max(abs(delta(a['x_plus'],X[:,j]))));ep=float(np.max(abs(a['P_plus']-C[:,j])));ea=int(np.sum(a['accepted']!=acc[:,j]))
            require(max(ex,ep)<1e-7 and ea==0,'Full original recursive parity failed')
            parity.append({**inp.identity,'arm':name,'check':'independent_original_full_replay','max_x_error':ex,'max_P_error':ep,'gate_mismatches':ea,'status':'PASS'})
            if ch=='full':
                r=full_ref[(full_ref.case==case)&(full_ref.bias==bias)&(full_ref.seed_idx==seed)&(full_ref.arm==name)]
                require(len(r)==1,'Missing frozen MC score row')
                scores=[z for z in summary if all(z.get(k)==v for k,v in {**inp.identity,'arm':name,'window':'stable_30_plus'}.items())]
                require(len(scores)==1,'Ambiguous new score row')
                dh=abs(scores[0]['heading_deg_rmse']-float(r.iloc[0]['stable_30_plus_heading_rmse_deg']))
                dx=abs(scores[0]['xy_cm_rmse']-float(r.iloc[0]['stable_30_plus_xy_rmse_cm']))
                require(max(dh,dx)<1e-7,'Frozen MC score parity failed')
                parity.append({**inp.identity,'arm':name,'check':'MC_ALL_summary','heading_error_deg':dh,'xy_error_cm':dx,'status':'PASS'})
        process_rows+=process_noise_statistics(inp,truth,model)
        inputslog.append({**inp.identity,'n_packets':len(inp.packets),'raw_input_hash':inp.checksum(),'source_hash':inp.source_hash,
                          'controls_frozen_before_filter':True,'truth_operational_features':False,'status':'PASS'})
    ws.table('S0','S0_PARITY.csv',parity);ws.table('S0','S0_ARRAY_SCHEMA.csv',schemas);ws.table('S0','S0_INPUT_QA.csv',inputslog)
    ws.table('S0','S0_BASELINE_SCORES.csv',summary);ws.table('S0','S0_PROCESS_NOISE.csv',process_rows)
    write_json(ws.root/'S0'/'S0_ARRAY_SCHEMA.json',schemas)
    write_json(ws.root/'S0'/'S0_INPUT_QA.json',inputslog)
    write_json(ws.root/'S0'/'S0_MANIFEST.json',ws.provenance('S0',asset_lock=assets.lock,eta2_definition='R_update=2*R_base; R_gate=R_base',
               cases=list(ws.config.get('cases',CASES)),seeds=list(ws.config.get('seeds',SEEDS)),native_los='B0 only, separate native BASE parameters'))
    ws.finish('S0',rf_executed=True,n_units=len(inputslog),reference_intermediate_parity=True)


def run_s1(ws,assets):
    tables={}
    for spec in units(ws.config):
        inp,model,truth=assets.load(*spec);priors=prior_traces(ws,inp)
        correctors=frozen_correctors(assets,inp,truth)[:5]
        append_tables(tables,s1(inp,truth,model,priors,correctors))
    save_tables(ws,'S1',tables);ws.finish('S1',rf_executed=True)


def run_s2(ws,assets):
    tables={};metrics={}
    routes=sorted({x.split('_')[0] for x in ws.config.get('cases',CASES)})
    for held in routes:
        data=native_learning_data(assets,held);lin=FitLineage(held);omega,lid=fit_omega(data,lin);metrics[held]=omega
        p=ws.root/'S2'/'metrics'/f'{held}.npz';p.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(p,omega=omega)
        write_json(p.with_suffix('.json'),dict(held=held,fit_lineage=lin.events,file_sha256=file_hash(p),metric_kind='centered_deterministic_residual_not_thermal'))
    for spec in units(ws.config):
        inp,model,truth=assets.load(*spec)
        append_tables(tables,s2(inp,model,prior_traces(ws,inp),frozen_correctors(assets,inp,truth)[:4],metrics[inp.route]))
    save_tables(ws,'S2',tables)
    bad=[r for r in tables.get('S2_PROJECTOR_RANK.csv',[]) if r.get('representation')=='physical_H' and r.get('status')=='QA_FAIL']
    require(not bad,f'Physical Jacobian FD failed on {len(bad)} rows; distinguish seams/poles before proceeding')
    ws.finish('S2',rf_executed=True,absolute_bias_prediction='paired P2/P4 nested predictions generated by S3, not claimed here')


def run_s3(ws,assets):
    results=[];lineage=[];oof=[]
    for held in sorted({x.split('_')[0] for x in ws.config.get('cases',CASES)}):
        rr,ll,oo=train_route(assets,held,ws.root/'S3'/'models');results+=rr;lineage+=ll;oof+=oo
    ws.table('S3','S3_VERSION_COMPARISON.csv',results);ws.table('S3','S3_TEACHER_LINEAGE.csv',lineage);ws.table('S3','S3_OOF_PREDICTIONS.csv',oof)
    df=pd.DataFrame(oof);pairs=[]
    if len(df) and 'prediction' in df:
        keys=['held','fold','key','offset_deg']
        A=df[(df.arm=='P2_DB')&(df.status=='PASS')];B=df[(df.arm=='P4_PERP')&(df.status=='PASS')]
        require(not A.duplicated(keys).any() and not B.duplicated(keys).any(),'OOF pair duplicates')
        joined=A.merge(B,on=keys,how='outer',suffixes=('_P2','_P4'),indicator=True,validate='one_to_one')
        for r in joined.to_dict('records'):
            ok=r['_merge']=='both'
            pairs.append({k:r[k] for k in keys}|dict(status='PASS' if ok else 'BLOCKED',
                delta_squared_error=(r['residual_P4']**2-r['residual_P2']**2) if ok else np.nan,
                note='additional absolute-bias prediction; must be combined with S4 state response'))
    ws.table('S3','S2_ABSOLUTE_BIAS_OOF.csv',pairs)
    # Training-only, timestamped POWER residuals for S6. Missing timestamps remain explicit.
    cal=pd.DataFrame(lineage);cal=cal[cal['mode']=='P2_DB'].copy()
    ws.table('S3','S3_TEMPORAL_CALIBRATION.csv',cal)
    write_json(ws.root/'S3'/'S3_MODEL_MANIFEST.json',dict(fixed_candidates=list(CANDIDATES),test_based_selection=False,models=results,
               nested_status='BLOCKED folds retained in OOF table; no complete-inner-validation claim for blocked roles'))
    ws.finish('S3',real_data_fitting=True,nested_blocked_rows=int(sum(r.get('status')=='BLOCKED' for r in oof)))


def _candidate_responses(inp,model,priors,cs):
    rows=[]
    for tr in priors:
        for k,p in enumerate(inp.packets):
            x=tr.arrays['x_minus'][k];P=tr.arrays['P_minus'][k]
            for label,v in perturbations(P):
                xp,xm=x+v,x-v;xp[2]=wrap(xp[2]);xm[2]=wrap(xm[2]);hp,_=model.observe(xp);hm,_=model.observe(xm)
                bp=p.z[1]-hp[1]-p.mu[1];bm=p.z[1]-hm[1]-p.mu[1]
                for c in cs:
                    cp,_=c(p,xp,hp,model);cm,_=c(p,xm,hm,model)
                    rows.append({**inp.identity,'source_prior':tr.metadata['arm'],'arm':c.name,'k':k,'t_s':p.t,'perturbation':label,
                                 **response_pair(bp,bm,bp-cp,bm-cm)})
    return rows


def run_s4(ws,assets):
    rows=[];responses=[];residual=[]
    for spec in units(ws.config):
        inp,model,truth=assets.load(*spec);priors=prior_traces(ws,inp);cs=candidates(ws,inp.route)
        rows+=common_prior(inp,truth,model,priors,cs+[assets.legacy(inp.route,'PWIDE_NOES'),OracleCorrector(inp,truth)])
        responses+=_candidate_responses(inp,model,priors,cs)
        residual+=s1(inp,truth,model,priors,cs)['S1_RESIDUAL.csv.gz']
    ws.table('S4','S4_COMMON_PRIOR.csv.gz',rows);ws.table('S4','S4_CANDIDATE_RESPONSE.csv.gz',responses);ws.table('S4','S4_CANDIDATE_RESIDUAL.csv.gz',residual)
    ws.finish('S4',rf_executed=True,interpretation='same-prior update and finite-response only; not a recursive success verdict')


def run_s5(ws,assets):
    effects=[];censor=[];linear=[];budget=[];covariances=[]
    for spec in units(ws.config):
        inp,model,truth=assets.load(*spec);cs=candidates(ws,inp.route)+[assets.legacy(inp.route,'PWIDE_NOES'),OracleCorrector(inp,truth)]
        for source in prior_traces(ws,inp):
            e,c,l=branch_effects(inp,truth,model,source,cs);effects+=e;censor+=c;linear+=l
        for corrector in [Corrector('BASE')]+cs:
            tr=simulate(inp,model,corrector,diagnostic_allowed=corrector.diagnostic)
            tr.save(trace_path(ws,'S5',inp,corrector.name))
            r,m,Y=all4_budget(inp,truth,model,tr,corrector);budget+=r;covariances+=m
    ws.table('S5','S5_BRANCH_EFFECTS.csv.gz',effects);ws.table('S5','S5_RIGHT_CENSOR.csv',censor)
    ws.table('S5','S5_FIXED_MATRIX_CONTROL.csv.gz',linear);ws.table('S5','S5_ALL4_BUDGET.csv',budget);ws.table('S5','S5_SOURCE_MATRICES.csv.gz',covariances)
    if effects:
        f=pd.DataFrame(effects);key=['case','bias','arm','source_prior','intervention_kind','horizon_requested']
        # Descriptive counts only; branch points are not independent environments.
        rows=f.groupby(key,dropna=False).agg(n=('start_t','size'),n_censored=('right_censored','sum')).reset_index()
        ws.table('S5','S5_CASE_HORIZONS.csv',rows)
    ws.finish('S5',rf_executed=True)


def run_s6(ws,assets):
    cal=pd.read_csv(ws.root/'S3'/'S3_TEMPORAL_CALIBRATION.csv');metrics={};tables={}
    for held in sorted(cal.held.unique()):
        subset=cal[cal.held==held];metric=fit_spectral_metric(subset,held);metrics[held]=metric
        write_json(ws.root/'S6'/f'{held}_TEMPORAL_METRIC.json',metric)
    from .temporal import bias_forecast_diagnostic
    training_forecasts=[]
    for (held,case),sub in cal.groupby(['held','case']):
        sub=sub[np.isfinite(sub.t_s)].sort_values('t_s');tt=sub.t_s.to_numpy();bb=sub.target.to_numpy()
        if len(tt)<5:continue
        for now in np.unique(np.searchsorted(tt,np.arange(tt[0],tt[-1]+1e-10,10.))):
            if now>=len(tt):continue
            for window in (2,5,10,30,60):
                for kind in ('constant','linear'):
                    for horizon in (2.,10.):
                        training_forecasts.append(dict(held=held,case=case,now_t=tt[now],window_s=window,bias_model=kind,forecast_horizon_s=horizon,**bias_forecast_diagnostic(tt,bb,now,window,horizon,kind)))
    ws.table('S6','S6_TRAIN_BIAS_MODEL_FORECAST.csv',training_forecasts)
    for spec in units(ws.config):
        inp,model,truth=assets.load(*spec);base=Trace.load(trace_path(ws,'S0',inp,'BASE'))
        append_tables(tables,s6(inp,truth,model,base,metrics[inp.route]))
    save_tables(ws,'S6',tables)
    write_json(ws.root/'S6'/'S6_TEMPORAL_ADOPTION.json',dict(status='INCONCLUSIVE',operational_temporal_filter_installed=False,
        reason='Bias-model adequacy, nuisance-marginal RF information, nonlinear ambiguity and recovery must be reviewed together. Rank alone cannot authorize deployment.'))
    ws.finish('S6',rf_executed=True,operational_temporal_filter=False)


def run_s7(ws,assets):
    scores=[];episodes=[];failures=[];blockrows=[];correlations=[]
    allarms=['BASE','PWIDE_NOES','ORACLE','BASE_ETA2',*CANDIDATES]
    for spec in units(ws.config,native_los=True):
        inp,model,truth=assets.load(*spec)
        base=Trace.load(trace_path(ws,'S0',inp,'BASE'));Eb=error_arrays(inp,truth,base)
        cs=[Corrector('BASE'),assets.legacy(inp.route,'PWIDE_NOES'),OracleCorrector(inp,truth),Corrector('BASE_ETA2')]+candidates(ws,inp.route)
        for c in cs:
            try:
                existing=trace_path(ws,'S5',inp,c.name)
                if existing.exists() and inp.channel=='full':tr=Trace.load(existing)
                elif c.name in ('BASE','PWIDE_NOES','ORACLE','BASE_ETA2'):tr=Trace.load(trace_path(ws,'S0',inp,c.name))
                else:
                    tr=simulate(inp,model,c,diagnostic_allowed=c.diagnostic);tr.save(trace_path(ws,'S7',inp,c.name))
                sc,ep=score_trace(inp,truth,tr);scores+=sc;episodes+=ep;E=error_arrays(inp,truth,tr)
                for comp in ('heading_deg','xy_cm'):
                    for rr in time_block_sensitivity(inp.t,E[comp]**2-Eb[comp]**2):
                        blockrows.append({**inp.identity,'arm':c.name,'component':comp,**rr})
                # Prior-residual cross moments, explicitly retrospective and not inserted in the filter.
                dm=delta(tr.arrays['x_minus'],truth.state)
                eps=np.array([p.z-p.mu-model.observe(truth.state[k])[0] for k,p in enumerate(inp.packets)])
                eps[:,1]-=tr.arrays['correction']
                Z=np.c_[dm,eps];mean=Z.mean(0);centered=(Z-mean).T@(Z-mean)/len(Z)
                correlations.append({**inp.identity,'arm':c.name,'mean':json.dumps(mean.tolist()),'centered_joint_covariance':json.dumps(centered.tolist()),
                                     'scope':'time-direction retrospective; NOT noise covariance across independent RF realizations'})
            except Exception as exc:
                failures.append({**inp.identity,'arm':c.name,'status':'QA_FAIL','reason':f'{type(exc).__name__}: {exc}'})
                scores.append({**inp.identity,'arm':c.name,'window':'stable_30_plus','status':'QA_FAIL'})
    ws.table('S7','S7_ALL_SCORES.csv',scores);ws.table('S7','S7_EPISODES.csv',episodes);ws.table('S7','S7_FAILURES.csv',failures)
    ws.table('S7','S7_BLOCK_SENSITIVITY.csv',blockrows);ws.table('S7','S7_PRIOR_RESIDUAL_COV.csv',correlations)
    comparisons=[];coverage=[]
    for channel,biases in [('full',ws.config.get('biases',BIASES)),('los',['B0'])]:
        rr,cc=compare(scores,allarms,cases=ws.config.get('cases',CASES),biases=biases,seeds=ws.config.get('seeds',SEEDS),channel=channel,margin=ws.config.get('noninferiority_margin',0.))
        comparisons+=rr;coverage+=cc
    ws.table('S7','S7_PAIRED_CASE_SCORECARD.csv',comparisons);ws.table('S7','S7_COMPLETENESS.csv',coverage)
    full_scope=(tuple(ws.config.get('cases',CASES))==CASES and tuple(ws.config.get('biases',BIASES))==BIASES and tuple(ws.config.get('seeds',SEEDS))==SEEDS)
    simple_comparisons=[]
    for channel,biases in [('full',ws.config.get('biases',BIASES)),('los',['B0'])]:
        rr,_=compare(scores,['BASE_ETA2',*CANDIDATES],cases=ws.config.get('cases',CASES),biases=biases,seeds=ws.config.get('seeds',SEEDS),channel=channel,reference_arm='BASE_ETA2',margin=ws.config.get('noninferiority_margin',0.))
        simple_comparisons+=rr
    ws.table('S7','S7_BASE_ETA2_COMPARISON.csv',simple_comparisons)
    claims=ledger([r for r in comparisons if r['channel']=='full'],candidates=CANDIDATES,
                  population=f"{len(ws.config.get('cases',CASES))} cases x {len(ws.config.get('biases',BIASES))} biases x {len(ws.config.get('seeds',SEEDS))} paired motion seeds",complete_protocol=full_scope)
    for row in claims:
        row['evidence_file']='S7_PAIRED_CASE_SCORECARD.csv; S7_EPISODES.csv; ../S4/S4_CANDIDATE_RESPONSE.csv.gz; ../S4/S4_CANDIDATE_RESIDUAL.csv.gz; ../S5/S5_BRANCH_EFFECTS.csv.gz'
        row['model_version']=json.dumps({route:load_candidate(ws.root/'S3'/'models',route,row['arm']).model_hash for route in sorted({x.split('_')[0] for x in ws.config.get('cases',CASES)})})
        row['S6_status']='PASS' if (ws.root/'S6_STATUS.json').exists() and read_json(ws.root/'S6_STATUS.json').get('status')=='PASS' else 'NOT_COMPLETED'
        row['mechanism_status']='REVIEW_REQUIRED: absolute-bias prediction plus prior-response and branch effects, not inferred from RMSE alone'
    ws.table('S7','S7_FINDING_LEDGER.csv',claims)
    if failures:
        ws.receipt('S7','QA_FAIL',n_failures=len(failures),failures_preserved=True)
    else:
        ws.finish('S7',rf_executed=True,n_scores=len(scores),no_unseen_scene_claim=True)


DEPENDENCIES={'S0':(), 'S1':('S0',), 'S2':('S0',), 'S3':('S0','S2'), 'S4':('S0','S3'),
              'S5':('S0','S4'), 'S6':('S0','S3'), 'S7':('S0','S1','S5')}


def run(stage,ws,assets):
    require(stage in DEPENDENCIES,'Unknown stage')
    ws.require_stage('AUDIT')
    for dependency in DEPENDENCIES[stage]:ws.require_stage(dependency)
    try:
        globals()['run_'+stage.lower()](ws,assets)
    except BlockedError as e:
        ws.receipt(stage,'BLOCKED',reason=str(e));raise
    except Exception as e:
        ws.receipt(stage,'QA_FAIL',reason=f'{type(e).__name__}: {e}');raise
