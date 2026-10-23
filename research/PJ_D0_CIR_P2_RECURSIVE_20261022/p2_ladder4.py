#!/usr/bin/env python3
"""Ladder 4: augmentation, d0 information, early stopping, and update-vs-gate R, one factor per step.

W family (mu_s = 0, ehat = model):    CIR -> CIR3 -> WIDE_SHUF -> WIDE_NOES ;  WIDE_PREV -> WIDE_NOES (ES only)
P family (mu_s = POWER, ehat = Dhat): PCIR -> PCIR3 -> PWIDE_SHUF -> PWIDE_NOES -> _KU -> _KV ;  PWIDE_PREV -> PWIDE_NOES
R = POWER V_s for every arm except _KU (update R = kappa V_s) and _KV (update and gate R = kappa V_s).
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

# arm: (mu_s, source, model key, uses d0, R mode)
ARMS4={
 'L_BASE':          ('POWER','none',None,False,'V'),
 'L_CIR':           ('ZERO','l4','W_X1',False,'V'),
 'L_CIR3':          ('ZERO','l4','W_X3',False,'V'),
 'L_WIDE_SHUF':     ('ZERO','l4','W_SHUF',True,'V'),
 'L_WIDE_NOES':     ('ZERO','l4','W_D0',True,'V'),
 'L_WIDE_PREV':     ('ZERO','pack','WIDE',True,'V'),
 'L_PCIR':          ('POWER','l4','P_X1',False,'V'),
 'L_PCIR3':         ('POWER','l4','P_X3',False,'V'),
 'L_PWIDE_SHUF':    ('POWER','l4','P_SHUF',True,'V'),
 'L_PWIDE_NOES':    ('POWER','l4','P_D0',True,'V'),
 'L_PWIDE_NOES_KU': ('POWER','l4','P_D0',True,'KU'),
 'L_PWIDE_NOES_KV': ('POWER','l4','P_D0',True,'KV'),
 'L_PWIDE_PREV':    ('POWER','ptrain','PWIDE',True,'V'),
 'L_ORACLE':        ('ZERO','oracle',None,False,'V'),
}
ARMS=list(ARMS4)

def run(model,case,controls,x0,P0,t,z,features,src,mu0,R0,sL,kappa):
    n=len(t);J=len(ARMS)
    X=np.full((n,J,4),np.nan);C=np.full((n,J,4,4),np.nan);acc=np.zeros((n,J),bool)
    rec={k:np.full((n,J),np.nan) for k in ['nis','d0','ehat','nu_s','nu_r','s_clean','gpsi','prior_heading_rad','eps']}
    xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0)
    inp={};pre={}
    for arm,(mus,so,key,ud0,rm) in ARMS4.items():
        if so in ('l4','pack','ptrain'):
            mdl,med=src[so]['models'][key],src[so]['medians'][key];b=R2.m_inputs(features,med)
            inp[arm]=(mdl,b)
            if not ud0:pre[arm]=mdl.predict(b)
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),
                                          float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True)
        for j,arm in enumerate(ARMS):
            mus,so,key,ud0,rm=ARMS4[arm]
            rec['prior_heading_rad'][k,j]=float(xs[j,2]);rec['gpsi'][k,j]=H[j,1,2]*math.pi/180
            d0=float(z[k,1]-h[j,1]);rec['d0'][k,j]=d0
            if so=='none':ehat=0.
            elif so=='oracle':ehat=float(z[k,1]-sL[k])
            elif not ud0:ehat=float(pre[arm][k])
            else:
                mdl,b=inp[arm];x=b.iloc[[k]].copy();x['d0']=d0;ehat=float(mdl.predict(x)[0])
            mu=mu0[k].copy()
            if mus=='ZERO':mu[1]=0.
            Rg=R0[k].copy();Ru=R0[k].copy()
            if rm in ('KU','KV'):Ru[1,1]*=kappa
            if rm=='KV':Rg[1,1]*=kappa
            zk=z[k].copy();zk[1]-=ehat
            rec['ehat'][k,j]=ehat;rec['s_clean'][k,j]=zk[1]-mu[1];rec['eps'][k,j]=zk[1]-mu[1]-sL[k]
            rec['nu_s'][k,j]=zk[1]-h[j,1]-mu[1];rec['nu_r'][k,j]=zk[0]-h[j,0]-mu[0]
            xo,Po,nis,yes=S.update(xs[j][None],Ps[j][None],zk,h[j][None],H[j][None],mu[None],mu[None],
                                   Rg[None],Ru[None],np.array([False]))
            xs[j],Ps[j]=xo[0],Po[0];rec['nis'][k,j]=float(nis[0]);acc[k,j]=bool(yes[0])
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):raise FloatingPointError(arm)
            X[k,j]=xs[j];C[k,j]=Ps[j]
        if k%250==0:print(f'LADDER4_FRAME {case["id"]} k={k}/{n}',flush=True)
    return X,C,acc,rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--models',required=True)
    ap.add_argument('--pmodels',required=True);ap.add_argument('--l4models',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    src={'pack':joblib.load(a.models),'ptrain':joblib.load(a.pmodels),'l4':joblib.load(a.l4models)}
    for v in src.values():assert v['held']==Hr and Hr not in v['train_routes']
    kappa=float(src['l4']['kappa_P_D0']);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    pk=pk[pk.case==a.case].sort_values('pose_id')
    model=V.SourceFFD();scores=[];series=[]
    prev_info={'WIDE_PREV':{'n_iter':int(src['pack']['models']['WIDE'].n_iter_),'early_stopping':bool(src['pack']['models']['WIDE'].do_early_stopping_)},
               'PWIDE_PREV':{'n_iter':int(src['ptrain']['models']['PWIDE'].n_iter_),'early_stopping':bool(src['ptrain']['models']['PWIDE'].do_early_stopping_)}}
    qa={'case':a.case,'held':Hr,'kappa_P_D0':kappa,'l4_info':src['l4']['info'],'prev_info':prev_info,'parity':{}}
    ref_p2a=pd.read_csv(HERE/'results_full/P2_A_SCORES.csv');ref1=pd.read_csv(HERE/'results_ladder/LADDER_SCORES.csv')
    ref3=pd.read_csv(HERE/'results_ladder3/LADDER3_SCORES.csv')
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
        sL=pk.set_index('pose_id').loc[ids]['sL_+0'].to_numpy()
        X,C,acc,rec=run(model,case,controls,x0,P0,t,z,features,src,mu0,R0,sL,kappa)
        sc,st=R2.score(case,bias,ch,'NOM',t,truth,X,C,acc,ARMS,{k:v for k,v in rec.items() if k!='eps'})
        sc=L1.extra(sc,t,X,truth,acc,rec);scores+=sc;series.append(st)
        checks=[('L_BASE',ref_p2a[(ref_p2a.init=='NOM')&(ref_p2a.arm=='BASE_POWER')]),('L_CIR',ref1[ref1.arm=='L_CIR']),
                ('L_WIDE_PREV',ref1[ref1.arm=='L_WIDE']),('L_ORACLE',ref1[ref1.arm=='L_ORACLE']),
                ('L_PCIR',ref3[ref3.arm=='L_PCIR']),('L_PWIDE_PREV',ref3[ref3.arm=='L_PWIDE'])]
        for mine,ref in checks:
            row=next(v for v in sc if v['arm']==mine)
            rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.channel==ch)];assert len(rr)==1,(stem,mine)
            errs={k:abs(row[k]-float(rr.iloc[0][k])) for k in ('heading_rmse_deg','heading_nees_1d','xy_rmse_cm','anchor_range_rmse_cm')}
            qa['parity'][f'{stem}:{mine}']=errs;assert max(errs.values())<1e-7,('LADDER4_PARITY_FAIL',stem,mine,errs)
        print(f'LADDER4_DONE {stem}',flush=True)
    pd.DataFrame(scores).to_csv(out/f'{a.case}_LADDER4_SCORES.csv',index=False)
    pd.concat(series,ignore_index=True).to_csv(out/f'{a.case}_LADDER4_SERIES.csv.gz',index=False,compression='gzip')
    (out/f'{a.case}_LADDER4_QA.json').write_text(json.dumps(qa,indent=2,default=float))
    print('LADDER4_CASE_PASS '+json.dumps(qa,default=float),flush=True)

if __name__=='__main__':main()
