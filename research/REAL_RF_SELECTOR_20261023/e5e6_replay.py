#!/usr/bin/env python3
"""E5/E6 RF observable-only selector pilot with 4-state recursive EKF.

Prespecified *unlabelled train-route quantile* heuristics, not a learnt classifier:
  SEL_VS_Q80, SEL_SHAPE_Q80, SEL_DETECTOR_Q80, SEL_HALFSHRINK.
Held PWIDE target Δ=e−μ from run 39885708483, POWER μ,V from strict OOF.
Inputs to deployable alpha selector only Full RF features & its own current prior.
GT/LoS read for controls/offline scoring and ORACLE_DIAG arm only.
"""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'research/PJ_D0_CIR_P2_RECURSIVE_20261022'))
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
import p2_replay as R2
from p2_replay import S,V
import p1r_eval as P
OFFS=P.OFFS
ARMS=['BASE','PWIDE_ALL','SEL_VS_Q80','SEL_SHAPE_Q80','SEL_DETECTOR_Q80','SEL_HALFSHRINK','ORACLE_Ds_DIAG']
QA_THRESH_QUANTILE=.8
DEG=180/math.pi

def thresholds(held,obs,pk):
    T=sorted({'R2','R4','R5'}-{held})
    inner=[]
    for rt in T:
        other=[a for a in T if a!=rt];assert len(other)==1
        pred=S.power_fit(obs,other,rt)
        inner.append(pred[pred.channel=='full'])
    dat=pd.concat(inner,ignore_index=True)
    assert set(dat.route)==set(T) and held not in set(dat.route)
    train=pk[pk.route.isin(T)].copy()
    for o in OFFS:
        train[f'ds_{o:+d}']=train[f'sF_{o:+d}']-train['sF_+0']
    shape=np.nanmax(np.abs(train[[f'ds_{o:+d}' for o in OFFS]].to_numpy(float)),axis=1)
    quality=obs[(obs.route.isin(T))&(obs.channel=='full')]
    assert len(quality)>0 and quality.detector_s_span.notna().sum()>30
    return {'tau_Vs':float(dat.Vs.quantile(QA_THRESH_QUANTILE)),
        'tau_shape':float(np.nanquantile(shape,QA_THRESH_QUANTILE)),
        'tau_detector':float(quality.detector_s_span.quantile(QA_THRESH_QUANTILE)),
        'train_routes':T,'threshold_quantile':QA_THRESH_QUANTILE,
        'trained_without_held_labels':True}

def bin_alpha(arm,vs,shape,detector,rb=None,ehat=None):
    if arm=='BASE':return 0.
    if arm=='PWIDE_ALL':return 1.
    if arm=='SEL_VS_Q80':return float(vs)
    if arm=='SEL_SHAPE_Q80':return float(shape)
    if arm=='SEL_DETECTOR_Q80':return float(detector)
    if arm=='SEL_HALFSHRINK':return .5
    if arm=='ORACLE_Ds_DIAG':
        assert rb is not None and ehat is not None
        return float((rb*rb-(rb-ehat)**2)>0)
    raise ValueError(arm)

def evaluate_one(case,bias,model,pack,th,obs,params,pk):
    stem=f'{case["id"]}_full_{bias}'
    old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
    t,ids,truth=old['t_s'],old['pose_id'],old['truth_scoring_only']
    q=obs[(obs.case==case['id'])&(obs.channel=='full')].set_index('pose_id').loc[ids]
    raw_z=q[['range_m','s_fp']].to_numpy(float)
    mu,R=V.base_params(params,case['id'],'full',ids,'POWER_DIAG')
    features,fr=R2.full_features(pk,ids)
    assert np.max(np.abs(features['sF_+0'].to_numpy()-raw_z[:,1]))<1e-9
    baseX=R2.m_inputs(features,pack['medians']['PWIDE'])
    ds=np.nanmax(np.abs(fr[[f'ds_{o:+d}' for o in OFFS]].to_numpy(float)),axis=1)
    vgate=R[:,1,1]>=th['tau_Vs']
    sgate=ds>=th['tau_shape']
    dgate=q.detector_s_span.to_numpy(float)>=th['tau_detector']
    rftruth=fr['sF_+0'].to_numpy()-fr['sL_+0'].to_numpy()
    controls,x0=V.build_positive_bias_controls(t,truth,bias)
    P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]);x0=np.r_[x0,0.]
    X=np.full((len(t),len(ARMS),4),np.nan)
    C=np.full((len(t),len(ARMS),4,4),np.nan)
    acc=np.zeros((len(t),len(ARMS)),bool)
    aalpha=np.zeros((len(t),len(ARMS)))
    steps=[]; xs=np.tile(x0,(len(ARMS),1));ps=np.tile(P0,(len(ARMS),1,1))
    for k in range(len(t)):
        if k:
            for j in range(len(ARMS)):
                xs[j],ps[j]=V.predict_one(xs[j],ps[j],float(controls['ds_odom'][k]),
                    float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True)
        for j,arm in enumerate(ARMS):
            d0=float(raw_z[k,1]-h[j,1])
            f=baseX.iloc[[k]].copy();f['d0']=d0
            hat=float(pack['models']['PWIDE'].predict(f)[0])
            rb=rftruth[k]-mu[k,1]
            alpha=bin_alpha(arm,vgate[k],sgate[k],dgate[k],rb,hat)
            aalpha[k,j]=alpha
            zk=raw_z[k].copy();zk[1]-=alpha*hat
            qmu=mu[k].copy()
            xs[j],ps[j],nis,yes=R2.update_one(xs[j],ps[j],zk,h[j],H[j],qmu,R[k],False)
            if np.linalg.eigvalsh(ps[j]).min()<-1e-10 or not np.isfinite(xs[j]).all():
                raise FloatingPointError(f'P/C BAD {case["id"]}/{bias}/{arm}/{k}')
            X[k,j]=xs[j];C[k,j]=ps[j];acc[k,j]=yes
            if arm in ('BASE','PWIDE_ALL','SEL_VS_Q80','SEL_SHAPE_Q80','SEL_DETECTOR_Q80','SEL_HALFSHRINK','ORACLE_Ds_DIAG'):
                steps.append({'case':case['id'],'route':case['route'],'bias':bias,'k':k,'t_s':t[k],
                    'arm':arm,'alpha':alpha,'accepted':yes,'d0_ownprior':d0,
                    'rb_gt':rb,'rp_gt':rb-alpha*hat,'d_s_truth':rb**2-(rb-hat)**2,
                    'fp_shift_truth':fr['fp_shift_tap'].iloc[k] if 'fp_shift_tap' in fr else np.nan,
                    'post_heading_err_deg':float(V.MC.wrap(xs[j,2]-truth[k,2])*DEG),
                    'Ppsi_deg':float(np.sqrt(ps[j,2,2])*DEG)})
        if k%250==0:print('RFSEL_FRAME',case['id'],bias,k,'/',len(t),flush=True)
    # E5 replay on single fixed BASE prior: use reverse-prediction from post state not valid.
    # Keep E5 as separate stage, do NOT label these different-recursion outputs 'same prior'.
    scores,_=R2.score(case,bias,'full','NOM',t,truth,X,C,acc,ARMS,
        {'prior_heading_rad':np.tile(truth[:,2,None],(1,len(ARMS))),
         'nis':np.full((len(t),len(ARMS)),np.nan),
         'd0':np.full((len(t),len(ARMS)),np.nan),
         'ehat':np.full((len(t),len(ARMS)),np.nan),
         'nu_s':np.full((len(t),len(ARMS)),np.nan),
         'nu_r':np.full((len(t),len(ARMS)),np.nan),
         's_clean':np.full((len(t),len(ARMS)),np.nan),
         'gpsi':np.full((len(t),len(ARMS)),np.nan)})
    for j,row in enumerate(scores):
        row['alpha_frac_t30']=float(aalpha[t>=30,j].mean())
        row['accept_t30']=float(acc[t>=30,j].mean())
        e=np.array([z['rb_gt']-z['rp_gt'] for z in steps if z['arm']==ARMS[j]])
        # This label is offline only; never used by operating arms.
    return pd.DataFrame(scores),pd.DataFrame(steps)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--case',required=True)
    ap.add_argument('--models',required=True)
    ap.add_argument('--out',required=True)
    a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case)
    pack=joblib.load(a.models);assert pack['held']==case['route'] and case['route'] not in pack['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    params=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    th=thresholds(case['route'],obs,pk);print('TRAIN_Q80_ONLY',json.dumps(th),flush=True)
    pk=pk[pk.case==a.case].sort_values('pose_id').copy()
    for o in OFFS:pk[f'ds_{o:+d}']=pk[f'sF_{o:+d}']-pk['sF_+0']
    model=V.SourceFFD();SCORES=[];TRACE=[]
    for bias in ('B0','L2'):
        sc,raw=evaluate_one(case,bias,model,pack,th,obs,params,pk)
        SCORES.append(sc);TRACE.append(raw)
        old=pd.read_csv(R2.REPO/'research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_ladder3/LADDER3_SCORES.csv')
        base=sc[sc.arm=='BASE'].iloc[0];pwide=sc[sc.arm=='PWIDE_ALL'].iloc[0]
        for orig,reference in ((base,'L_BASE'),(pwide,'L_PWIDE')):
            r=old[(old.case==case['id'])&(old.bias==bias)&(old.arm==reference)]
            assert len(r)==1
            diff=max(abs(float(orig[k])-float(r.iloc[0][k])) for k in ('heading_rmse_deg','xy_rmse_cm','heading_nees_1d','heading_cov95'))
            assert diff<1e-7,('BASELINE_PARITY',case['id'],bias,reference,diff)
        print('E6_PAIRED_REPLAY',case['id'],bias,'BASE',base.heading_rmse_deg,'PWIDE',pwide.heading_rmse_deg,flush=True)
    df=pd.concat(SCORES,ignore_index=True);trace=pd.concat(TRACE,ignore_index=True)
    assert len(df)==len(ARMS)*2
    df.to_csv(out/f'{a.case}_E6_SCORES.csv',index=False)
    trace.to_csv(out/f'{a.case}_E6_TRACE.csv.gz',index=False,compression='gzip')
    info={'case':a.case,'train_routes':th['train_routes'],'thresholds':th,
          'source':'held PWIDE from P2 ladder3, original RF, each own prior',
          'all_online_candidates_have_no_GT_features':True,
          'oracle_diagnoistic_offline_only':True,
          'first_result_excludes_same_prior_E5':True,
          'n_rows':len(df),'n_steps':len(trace)}
    (out/f'{a.case}_E6_QA.json').write_text(json.dumps(info,indent=2))
    print('E6_CASE_PASS',json.dumps(info),flush=True)

if __name__=='__main__':main()
