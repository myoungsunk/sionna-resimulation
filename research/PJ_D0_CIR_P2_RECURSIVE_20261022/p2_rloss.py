#!/usr/bin/env python3
"""Recursive-loss mechanism decomposition (10_RECURSIVE_LOSS_PLAN_KO.md). Diagnostic counterfactuals.

3 correctors (BASE, PWIDE_NOES, ORACLE) x 5 filter conditions (REAL, NOGATE, GTLIN, BIASFIX, XYGT).
GTLIN, BIASFIX, XYGT and ORACLE read GT on purpose; none of them is an operational candidate.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import p2_replay as R2
import p2_ladder as L1
from p2_replay import V, S

CORR=['BASE','PWIDE','ORACLE'];MODES=['REAL','NOGATE','GTLIN','BIASFIX','XYGT']
ARMS=[f'{c}__{m}' for m in MODES for c in CORR]

def run(model,case,controls,x0,P0,t,z,features,l4,mu0,R0,sL,truth,b_true):
    n=len(t);J=len(ARMS)
    X=np.full((n,J,4),np.nan);C=np.full((n,J,4,4),np.nan);acc=np.zeros((n,J),bool)
    rec={k:np.full((n,J),np.nan) for k in ['nis','d0','ehat','nu_s','nu_r','s_clean','gpsi','prior_heading_rad','eps','c2']}
    xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0)
    mdl=l4['models']['P_D0'];b=R2.m_inputs(features,l4['medians']['P_D0'])
    hgt_all=[];Hgt_all=[]
    for i in range(0,n,32):
        hh,HH=model.batch(np.c_[truth[i:i+32,:3],np.zeros(len(truth[i:i+32]))],case,gradient=True);hgt_all.append(hh);Hgt_all.append(HH)
    hgt=np.concatenate(hgt_all);Hgt=np.concatenate(Hgt_all)
    xg=b.copy();xg['d0']=z[:,1]-hgt[:,1];eh_gt=mdl.predict(xg)
    for j,arm in enumerate(ARMS):
        if arm.endswith('__BIASFIX'):
            xs[j,3]=b_true;Ps[j,3,:]=0.;Ps[j,:,3]=0.
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),
                                          float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        for j,arm in enumerate(ARMS):
            if arm.endswith('__XYGT'):
                xs[j,:2]=truth[k,:2];Ps[j,:2,:]=0.;Ps[j,:,:2]=0.
            if arm.endswith('__BIASFIX'):
                xs[j,3]=b_true;Ps[j,3,:]=0.;Ps[j,:,3]=0.
        h,H=model.batch(xs,case,gradient=True)
        for j,arm in enumerate(ARMS):
            corr,mode=arm.split('__')
            hj=h[j].copy();Hj=H[j].copy()
            if mode=='GTLIN':
                dx=xs[j]-np.r_[truth[k,:3],xs[j,3]];dx[2]=float(V.MC.wrap(dx[2]));Hj=Hgt[k].copy();hj=hgt[k]+Hj@dx
            rec['prior_heading_rad'][k,j]=float(xs[j,2]);rec['gpsi'][k,j]=Hj[1,2]*math.pi/180
            d0=float(z[k,1]-h[j,1]);rec['d0'][k,j]=d0          # corrector input always from the real prior
            if corr=='BASE':ehat=0.
            elif corr=='ORACLE':ehat=float(z[k,1]-sL[k])
            else:
                x=b.iloc[[k]].copy();x['d0']=d0;ehat=float(mdl.predict(x)[0]);rec['c2'][k,j]=float(eh_gt[k]-ehat)
            mu=mu0[k].copy()
            if corr=='ORACLE':mu[1]=0.
            Ru=R0[k].copy();Rg=R0[k].copy()
            if mode=='NOGATE':Rg=Rg*1e12
            zk=z[k].copy();zk[1]-=ehat
            rec['ehat'][k,j]=ehat;rec['s_clean'][k,j]=zk[1]-mu[1];rec['eps'][k,j]=zk[1]-mu[1]-sL[k]
            rec['nu_s'][k,j]=zk[1]-hj[1]-mu[1];rec['nu_r'][k,j]=zk[0]-hj[0]-mu[0]
            xo,Po,nis,yes=S.update(xs[j][None],Ps[j][None],zk,hj[None],Hj[None],mu[None],mu[None],Rg[None],Ru[None],np.array([False]))
            xs[j],Ps[j]=xo[0],Po[0];rec['nis'][k,j]=float(nis[0]);acc[k,j]=bool(yes[0])
            if mode=='BIASFIX':xs[j,3]=b_true;Ps[j,3,:]=0.;Ps[j,:,3]=0.
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):raise FloatingPointError(arm)
            X[k,j]=xs[j];C[k,j]=Ps[j]
        if k%250==0:print(f'RLOSS_FRAME {case["id"]} k={k}/{n}',flush=True)
    return X,C,acc,rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--l4models',required=True)
    ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    l4=joblib.load(a.l4models);assert l4['held']==Hr and Hr not in l4['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    pk=pk[pk.case==a.case].sort_values('pose_id')
    model=V.SourceFFD();scores=[];series=[];qa={'case':a.case,'held':Hr,'parity':{}}
    ref_p2a=pd.read_csv(HERE/'results_full/P2_A_SCORES.csv');ref1=pd.read_csv(HERE/'results_ladder/LADDER_SCORES.csv')
    ref4=pd.read_csv(HERE/'results_ladder4/LADDER4_SCORES.csv')
    for bias,ch in L1.CONDITIONS:
        stem=f'{a.case}_{ch}_{bias}'
        old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only']
        d=obs[(obs.case==a.case)&(obs.channel==ch)].set_index('pose_id').loc[ids]
        z=d[['range_m','s_fp']].to_numpy(float)
        features,_=R2.full_features(pk,ids);assert np.max(np.abs(features['sF_+0'].to_numpy()-z[:,1]))<1e-9
        mu0,R0=V.base_params(param,a.case,ch,ids,'POWER_DIAG')
        controls,x0r=V.build_positive_bias_controls(t,truth,bias)
        x0=np.r_[x0r,0.];P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
        sL=pk.set_index('pose_id').loc[ids]['sL_+0'].to_numpy();b_true=math.radians(V.BIAS_LEVELS[bias])
        X,C,acc,rec=run(model,case,controls,x0,P0,t,z,features,l4,mu0,R0,sL,truth,b_true)
        sc,st=R2.score(case,bias,ch,'NOM',t,truth,X,C,acc,ARMS,{k:v for k,v in rec.items() if k not in('eps','c2')})
        sc=L1.extra(sc,t,X,truth,acc,rec)
        for j,row in enumerate(sc):
            m=t>=30;bias_err=np.degrees(X[:,j,3]-b_true)
            row['stable_30_plus_bg_err_rms_dps']=float(np.sqrt(np.mean(bias_err[m]**2)));row['stable_30_plus_bg_err_mean_dps']=float(bias_err[m].mean())
            row['stable_30_plus_c2_rms']=float(np.sqrt(np.nanmean(rec['c2'][m,j]**2))) if np.isfinite(rec['c2'][m,j]).any() else np.nan
            row['stable_30_plus_c2_acc_mean']=float(np.nanmean(rec['c2'][m&acc[:,j],j])) if np.isfinite(rec['c2'][m,j]).any() else np.nan
            row['corrector'],row['mode']=ARMS[j].split('__')
        scores+=sc
        for j,arm in enumerate(ARMS):st[f'{arm}__c2']=rec['c2'][:,j];st[f'{arm}__eps']=rec['eps'][:,j]
        series.append(st)
        checks=[('BASE__REAL',ref_p2a[(ref_p2a.init=='NOM')&(ref_p2a.arm=='BASE_POWER')]),
                ('PWIDE__REAL',ref4[ref4.arm=='L_PWIDE_NOES']),('ORACLE__REAL',ref1[ref1.arm=='L_ORACLE'])]
        for mine,ref in checks:
            row=next(v for v in sc if v['arm']==mine)
            rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.channel==ch)];assert len(rr)==1,(stem,mine)
            errs={k:abs(row[k]-float(rr.iloc[0][k])) for k in ('heading_rmse_deg','heading_nees_1d','xy_rmse_cm','anchor_range_rmse_cm')}
            qa['parity'][f'{stem}:{mine}']=errs;assert max(errs.values())<1e-7,('RLOSS_PARITY_FAIL',stem,mine,errs)
        print(f'RLOSS_DONE {stem}',flush=True)
    pd.DataFrame(scores).to_csv(out/f'{a.case}_RLOSS_SCORES.csv',index=False)
    pd.concat(series,ignore_index=True).to_csv(out/f'{a.case}_RLOSS_SERIES.csv.gz',index=False,compression='gzip')
    (out/f'{a.case}_RLOSS_QA.json').write_text(json.dumps(qa,indent=2))
    print('RLOSS_CASE_PASS '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
