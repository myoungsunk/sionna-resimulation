#!/usr/bin/env python3
"""P2-A: REAL recursive 4-state EKF using each arm's own wheel/gyro/RF prior.

No GT in estimator prediction/observation. The only GT accesses generate
frozen shared IMU/odom controls, set predeclared initial conditions, score,
and offline ORACLE diagnostics (never operational candidate).
"""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
sys.path.insert(0,str(REPO/'research/PJ_D0_CIR_PRIOR_P1R_20261022'))
import p1r_eval as PE
import strict_common as S
from strict_common import V
import hpath_lut as HP

ARMS=['DR_ONLY','RANGE_ONLY','BASE_POWER','RAW_SHARED',
      'CIR_ONLY_SHARED','WIDE_SHARED','WIDE_CAL','NARROW_CAL','ORACLE_SHARED']
INITS=[('NOM',None,None),('E+10_P5',10,'5'),('E-10_P5',-10,'5'),
       ('E+20_P5',20,'5'),('E-20_P5',-20,'5'),
       ('E+10_PM',10,'M'),('E-10_PM',-10,'M'),
       ('E+20_PM',20,'M'),('E-20_PM',-20,'M')]
CONDITIONS=[('B0','full'),('L2','full'),('B0','los')]
WINDOWS={'initial_0_2':(0,2),'early_2_10':(2,10),
         'middle_10_30':(10,30),'stable_30_plus':(30,np.inf),'all':(0,np.inf)}
DEG=180/math.pi

def full_features(pk,ids):
    d=pk.set_index('pose_id').loc[ids].reset_index()
    for o in PE.OFFS:d[f'ds_{o:+d}']=d[f'sF_{o:+d}']-d['sF_+0']
    return d[PE.FEATURES].copy(),d

def los_features(case,ids,pk):
    h=np.load(V.ROOT/case['los_path'],mmap_mode='r',allow_pickle=False)
    ident=pd.DataFrame(json.loads((V.ROOT/case['samples_path']).read_text())).pose_id.to_numpy(int)
    chunks=[]
    for k in range(0,len(h),128):
        cir=HP.cir_of(np.asarray(h[k:k+128,:,:,0]))
        fp,s=HP.profile(cir);idx=np.arange(len(fp))
        power=np.abs(cir[idx,fp,:])**2
        part={'pose_id':ident[k:k+len(fp)],'fp_full':fp,
              'log_fp_power':np.log10(np.maximum(power.sum(1),np.finfo(float).tiny)),
              'sF_+0':s[0]}
        for o in PE.OFFS:part[f'sF_{o:+d}']=s[o]
        chunks.append(pd.DataFrame(part))
    q=pd.concat(chunks,ignore_index=True).set_index('pose_id').loc[ids].reset_index()
    for o in PE.OFFS:q[f'ds_{o:+d}']=q[f'sF_{o:+d}']-q['sF_+0']
    d=pk.set_index('pose_id').loc[ids]
    if np.max(np.abs(q['sF_+0'].to_numpy()-d['sL_+0'].to_numpy()))>1e-9:
        raise AssertionError('LOS_PROFILE_NOT_MATCHED_TO_FROZEN_CIR')
    return q[PE.FEATURES].copy(),q

def m_inputs(df,med):
    # Same fill policy and column order as P1R.
    return df.replace([np.inf,-np.inf],np.nan).fillna(med).loc[:,PE.FEATURES]

def update_one(x,P,z,h,H,mu,R,ronly=False):
    xo,Po,nis,accepted=S.update(x[None],P[None],z,h[None],H[None],
                                mu[None],mu[None],R[None],R[None],
                                np.array([ronly],bool))
    return xo[0],Po[0],float(nis[0]),bool(accepted[0])

def propagate(model,case,controls,x_initial,P_initial,t,z,features,models,meds,Rs,
              mu0,R0,sL,truth,arm_filter,featlabels):
    """
    - Estimator loop never reads truth or sL EXCEPT for ORACLE arm.
    - All other correction arms use only current measured CIR features & prior.
    """
    arms=[arm for arm in ARMS if arm in arm_filter]
    J=len(arms);n=len(t)
    X=np.full((n,J,4),np.nan);C=np.full((n,J,4,4),np.nan)
    rec={nm:np.full((n,J),np.nan) for nm in ['nis','d0','ehat','nu_s','nu_r','s_clean','psig','gpsi','prior_herr_deg']}
    accept=np.zeros((n,J),bool)
    xs=np.repeat(x_initial[None,:],J,axis=0)
    Ps=np.repeat(P_initial[None,:,:],J,axis=0)
    # Full observed CIR features are constant across arms; d0 recomputed from own prior.
    b={arm:m_inputs(features,meds[arm]) if arm in meds else None for arm in ('CIR_ONLY','WIDE','NARROW')}
    cir_pred=models['CIR_ONLY'].predict(b['CIR_ONLY']) if b['CIR_ONLY'] is not None else np.zeros(n)
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],
                       float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),
                       float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True)
        state_prior=xs.copy()
        for j,arm in enumerate(arms):
            rec['psig'][k,j]=math.sqrt(max(Ps[j,2,2],0))*DEG
            rec['gpsi'][k,j]=H[j,1,2]*math.pi/180
            d0=float(z[k,1]-h[j,1])
            rec['d0'][k,j]=d0
            rec['prior_herr_deg'][k,j]=float(V.MC.wrap(state_prior[j,2]-truth[k,2])*DEG)
            if arm=='DR_ONLY':
                accept[k,j]=False;X[k,j]=xs[j];C[k,j]=Ps[j];continue
            if arm in ('BASE_POWER','RANGE_ONLY','RAW_SHARED'):
                ehat=0.0
            elif arm=='CIR_ONLY_SHARED':
                ehat=float(cir_pred[k])
            elif arm in ('WIDE_SHARED','WIDE_CAL','NARROW_CAL'):
                name='WIDE' if 'WIDE' in arm else 'NARROW'
                inp=b[name].iloc[[k]].copy();inp['d0']=d0
                ehat=float(models[name].predict(inp)[0])
            elif arm=='ORACLE_SHARED':
                # Offline oracle reference only. Never allow its result in practical arms.
                ehat=float(z[k,1]-sL[k])
            else:raise RuntimeError('UNKNOWN_ARM:'+arm)
            rec['ehat'][k,j]=ehat
            raw_mu=mu0[k].copy()
            r=R0[k].copy()
            if arm in ('CIR_ONLY_SHARED','WIDE_SHARED','RAW_SHARED','NARROW_CAL','WIDE_CAL','ORACLE_SHARED'):
                r[0,1]=r[1,0]=0.
                r[1,1]=float(Rs['CIR_PLUS_D0_WIDE'] if arm=='WIDE_CAL' else
                             Rs['CIR_PLUS_D0'] if arm=='NARROW_CAL' else
                             Rs['CIR_ONLY'])
            zk=z[k].copy()
            if arm not in ('BASE_POWER','RANGE_ONLY','RAW_SHARED'):
                zk[1]-=ehat
                raw_mu[1]=0.
            elif arm=='RAW_SHARED':raw_mu[1]=0.
            rec['s_clean'][k,j]=zk[1]
            rec['nu_s'][k,j]=zk[1]-h[j,1]-raw_mu[1]
            rec['nu_r'][k,j]=zk[0]-h[j,0]-raw_mu[0]
            xs[j],Ps[j],nisk,yes=update_one(xs[j],Ps[j],zk,h[j],H[j],raw_mu,r,arm=='RANGE_ONLY')
            rec['nis'][k,j]=nisk;accept[k,j]=yes
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):
                raise FloatingPointError(f'NONFINITE_FILTER arm={arm}, step={k}')
            if np.linalg.eigvalsh(Ps[j]).min()<-1e-11:
                raise FloatingPointError(f'COV_NOT_PSD arm={arm}, step={k}')
            X[k,j]=xs[j];C[k,j]=Ps[j]
        if k%250==0:print(f'P2_FRAME {case["id"]} k={k}/{n}',flush=True)
    return arms,X,C,accept,rec

def score(case,bias,ch,init,t,truth,X,C,acc,arms,rec):
    main,_=S.score_extra(X,C,t,truth,case)
    scores=[];stream=pd.DataFrame({'case':case['id'],'route':case['route'],'bias':bias,
        'channel':ch,'init':init,'k':np.arange(len(t)),'t_s':t})
    for j,arm in enumerate(arms):
        he=np.asarray(V.MC.wrap(X[:,j,2]-truth[:,2]))*DEG
        xy=np.sqrt(np.sum((X[:,j,:2]-truth[:,:2])**2,axis=1))*100
        sigma=np.sqrt(np.maximum(C[:,j,2,2],1e-300))*DEG
        good=np.isfinite(he)&np.isfinite(xy)&np.isfinite(sigma)
        if not good.all():raise FloatingPointError(f'NONFINITE_SCORE {case["id"]} {init} {arm}')
        srow={'case':case['id'],'route':case['route'],'bias':bias,'channel':ch,
             'init':init,'arm':arm,'n':len(t),**main[j]}
        for key,(start,end) in WINDOWS.items():
            mask=(t>=start)&(t<end)
            if not mask.any():continue
            eh=he[mask];es=sigma[mask];ex=xy[mask]
            srow[f'{key}_heading_rmse_deg']=float(np.sqrt(np.mean(eh**2)))
            srow[f'{key}_heading_q95_abs_deg']=float(np.quantile(np.abs(eh),.95))
            srow[f'{key}_heading_q99_abs_deg']=float(np.quantile(np.abs(eh),.99))
            srow[f'{key}_heading_diverge10_frac']=float(np.mean(np.abs(eh)>=10.))
            srow[f'{key}_heading_nees_1d']=float(np.mean((eh/es)**2))
            srow[f'{key}_heading_cov95']=float(np.mean((eh/es)**2<=S.C1))
            srow[f'{key}_xy_rmse_cm']=float(np.sqrt(np.mean(ex**2)))
            srow[f'{key}_accept']=float(acc[mask,j].mean())
        scores.append(srow)
        stream[f'{arm}__heading_err_deg']=he
        stream[f'{arm}__heading_prior_err_deg']=rec['prior_herr_deg'][:,j]
        stream[f'{arm}__Ppsi_deg']=sigma
        stream[f'{arm}__xy_err_cm']=xy
        stream[f'{arm}__bias_dps']=np.degrees(X[:,j,3])
        stream[f'{arm}__acc']=acc[:,j]
        for nm in ['nis','d0','ehat','nu_s','nu_r','s_clean','gpsi']:
            stream[f'{arm}__{nm}']=rec[nm][:,j]
    return scores,stream

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--case',required=True)
    ap.add_argument('--models',required=True)
    ap.add_argument('--out',required=True)
    ap.add_argument('--mode',choices=['smoke','full'],default='smoke')
    a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case)
    H=case['route'];pack=joblib.load(a.models)
    assert pack['held']==H and H not in pack['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    train_models=pack['models'];med=pack['medians'];Rs=pack['R_cal']
    observation=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    pk=pk[pk.case==a.case].sort_values('pose_id')
    model=V.SourceFFD();scores=[];series=[];qa={'case':a.case,'held':H,
               'mode':a.mode,'train_routes':pack['train_routes'],'baseline_parity':{},
               'source':'original SourceFFD, same sensor gyro/wheel, same held-route POWER'}
    ref=pd.read_csv(REPO/'research/PJ_DS_GATED_20261021/results_strict/SB_SCORES.csv')
    for bias,ch in CONDITIONS:
        if a.mode=='smoke' and (bias,ch)!=('B0','full'):continue
        stem=f'{a.case}_{ch}_{bias}'
        old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only']
        d=observation[(observation.case==a.case)&(observation.channel==ch)].set_index('pose_id').loc[ids]
        z=d[['range_m','s_fp']].to_numpy(float)
        features,ff=full_features(pk,ids) if ch=='full' else los_features(case,ids,pk)
        assert np.max(np.abs(features['sF_+0'].to_numpy()-z[:,1]))<1e-9
        mu0,R0=V.base_params(param,a.case,ch,ids,'POWER_DIAG')
        controls,x0r=V.build_positive_bias_controls(t,truth,bias)
        initsets=INITS[:3] if a.mode=='smoke' else INITS
        for init,off,pkey in initsets:
            x0=x0r.copy()
            p0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
            if off is not None:
                x0[2]=V.MC.wrap(truth[0,2]+math.radians(off))
                if pkey=='M':p0[2,2]=math.radians(abs(off))**2
            xstate=np.r_[x0,0.]
            arms,X,C,accepted,rec=propagate(model,case,controls,xstate,p0,t,z,features,
                train_models,med,Rs,mu0,R0,pk.set_index('pose_id').loc[ids]['sL_+0'].to_numpy() if ch=='full'
                else z[:,1],truth,set(ARMS),d)
            sc,st=score(case,bias,ch,init,t,truth,X,C,accepted,arms,rec)
            scores+=sc;series.append(st)
            if init=='NOM':
                bp=next(v for v in sc if v['arm']=='BASE_POWER')
                rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.channel==ch)&(ref.arm=='BASE')]
                assert len(rr)==1,('STRICT_BASE_MISSING',stem)
                errs={nm:abs(bp[nm]-float(rr.iloc[0][nm]))
                      for nm in ('heading_rmse_deg','heading_nees_1d','heading_cov95','xy_rmse_cm','anchor_range_rmse_cm')}
                qa['baseline_parity'][stem]=errs
                assert max(errs.values())<1e-7,('STRICT_BASE_PARITY_FAIL',stem,errs)
            print(f'P2_CASE_DONE {stem} init={init}',flush=True)
    assert scores and series
    pd.DataFrame(scores).to_csv(out/f'{a.case}_P2_SCORES.csv',index=False)
    pd.concat(series,ignore_index=True).to_csv(out/f'{a.case}_P2_SERIES.csv.gz',index=False,compression='gzip')
    (out/f'{a.case}_P2_QA.json').write_text(json.dumps(qa,indent=2))
    print(f'P2_DONE {a.case} '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
