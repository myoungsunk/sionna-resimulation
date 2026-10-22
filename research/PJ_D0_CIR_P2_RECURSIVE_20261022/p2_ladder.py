#!/usr/bin/env python3
"""P2 ladder: adjacent arms differ by exactly one factor (03_LADDER_ONE_FACTOR_KO.md).

Reuses P2-A inputs, models, update and scoring code unchanged. Only NOM init, Full B0/L2.
GT is read only for scoring, for the diagnostic L_WIDE_GTD0 d0, and for offline residual
bookkeeping; L_ORACLE reads s_LoS. All other arms use estimated state and measurements only.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import p2_replay as R2
from p2_replay import V, S, DEG

# name: (mu_s source, R_s source, ehat source)
LADDER={
 'L_BASE':     ('POWER','POWER','NONE'),
 'L_NOMU':     ('ZERO', 'POWER','NONE'),
 'L_CONSTR':   ('POWER','CONST','NONE'),
 'L_CIR':      ('ZERO', 'POWER','CIR'),
 'L_WIDE':     ('ZERO', 'POWER','WIDE_PRIOR'),
 'L_WIDE_GTD0':('ZERO', 'POWER','WIDE_GT'),
 'L_ORACLE':   ('ZERO', 'POWER','ORACLE'),
 'L_RAW':      ('ZERO', 'CONST','NONE'),
}
ARMS=list(LADDER)
CONDITIONS=[('B0','full'),('L2','full')]

def run(model,case,controls,x0,P0,t,z,features,models,meds,Rconst,mu0,R0,sL,truth):
    n=len(t);J=len(ARMS)
    X=np.full((n,J,4),np.nan);C=np.full((n,J,4,4),np.nan);acc=np.zeros((n,J),bool)
    rec={k:np.full((n,J),np.nan) for k in ['nis','d0','ehat','nu_s','nu_r','s_clean','gpsi','prior_heading_rad','eps']}
    xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0)
    bc=R2.m_inputs(features,meds['CIR_ONLY']);bw=R2.m_inputs(features,meds['WIDE'])
    cir=models['CIR_ONLY'].predict(bc)
    # GT-pose LUT for the diagnostic arm only (computed once, never enters other arms)
    hgt=np.concatenate([model.batch(truth[i:i+32,:3],case,gradient=True)[0][:,1] for i in range(0,n,32)])
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),
                                          float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True)
        for j,arm in enumerate(ARMS):
            mus,rs,es=LADDER[arm]
            rec['prior_heading_rad'][k,j]=float(xs[j,2]);rec['gpsi'][k,j]=H[j,1,2]*math.pi/180
            d0=float(z[k,1]-h[j,1]);rec['d0'][k,j]=d0
            if es=='NONE':ehat=0.
            elif es=='CIR':ehat=float(cir[k])
            elif es in ('WIDE_PRIOR','WIDE_GT'):
                inp=bw.iloc[[k]].copy();inp['d0']=d0 if es=='WIDE_PRIOR' else float(z[k,1]-hgt[k])
                ehat=float(models['WIDE'].predict(inp)[0])
            elif es=='ORACLE':ehat=float(z[k,1]-sL[k])
            else:raise RuntimeError(es)
            mu=mu0[k].copy();r=R0[k].copy()
            if mus=='ZERO':mu[1]=0.
            if rs=='CONST':r[0,1]=r[1,0]=0.;r[1,1]=float(Rconst)
            zk=z[k].copy();zk[1]-=ehat
            rec['ehat'][k,j]=ehat;rec['s_clean'][k,j]=zk[1]-mu[1]
            rec['eps'][k,j]=zk[1]-mu[1]-sL[k]        # offline bookkeeping only
            rec['nu_s'][k,j]=zk[1]-h[j,1]-mu[1];rec['nu_r'][k,j]=zk[0]-h[j,0]-mu[0]
            xs[j],Ps[j],nis,yes=R2.update_one(xs[j],Ps[j],zk,h[j],H[j],mu,r,False)
            rec['nis'][k,j]=nis;acc[k,j]=yes
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):raise FloatingPointError(arm)
            X[k,j]=xs[j];C[k,j]=Ps[j]
        if k%250==0:print(f'LADDER_FRAME {case["id"]} k={k}/{n}',flush=True)
    return X,C,acc,rec

def extra(rows,t,X,truth,acc,rec):
    """Per-window signed heading bias and offline residual statistics, appended to score rows."""
    for j,row in enumerate(rows):
        he=np.asarray(V.MC.wrap(X[:,j,2]-truth[:,2]))*DEG;eps=rec['eps'][:,j];a=acc[:,j]
        for key,(t0,t1) in R2.WINDOWS.items():
            m=(t>=t0)&(t<t1)
            if not m.any():continue
            row[f'{key}_heading_signed_bias_deg']=float(he[m].mean())
            row[f'{key}_eps_mean']=float(eps[m].mean());row[f'{key}_eps_rms']=float(np.sqrt(np.mean(eps[m]**2)))
            ma=m&a;row[f'{key}_eps_acc_mean']=float(eps[ma].mean()) if ma.any() else float('nan')
            row[f'{key}_gpsi_rms']=float(np.sqrt(np.nanmean(rec['gpsi'][m,j]**2)))
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True)
    ap.add_argument('--models',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    pack=joblib.load(a.models);assert pack['held']==Hr and Hr not in pack['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    pk=pk[pk.case==a.case].sort_values('pose_id')
    model=V.SourceFFD();scores=[];series=[]
    qa={'case':a.case,'held':Hr,'train_routes':pack['train_routes'],'R_const':float(pack['R_cal']['CIR_ONLY']),
        'arms':LADDER,'parity':{},'max_abs_Crs':{}}
    p2a=pd.read_csv(HERE/'results_full/P2_A_SCORES.csv')
    for bias,ch in CONDITIONS:
        stem=f'{a.case}_{ch}_{bias}'
        old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only']
        d=obs[(obs.case==a.case)&(obs.channel==ch)].set_index('pose_id').loc[ids]
        z=d[['range_m','s_fp']].to_numpy(float)
        features,_=R2.full_features(pk,ids)
        assert np.max(np.abs(features['sF_+0'].to_numpy()-z[:,1]))<1e-9
        mu0,R0=V.base_params(param,a.case,ch,ids,'POWER_DIAG')
        qa['max_abs_Crs'][stem]=float(np.max(np.abs(R0[:,0,1])))
        controls,x0r=V.build_positive_bias_controls(t,truth,bias)
        x0=np.r_[x0r,0.];P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
        sL=pk.set_index('pose_id').loc[ids]['sL_+0'].to_numpy()
        X,C,acc,rec=run(model,case,controls,x0,P0,t,z,features,pack['models'],pack['medians'],
                        pack['R_cal']['CIR_ONLY'],mu0,R0,sL,truth)
        sc,st=R2.score(case,bias,ch,'NOM',t,truth,X,C,acc,ARMS,{k:v for k,v in rec.items() if k!='eps'})
        sc=extra(sc,t,X,truth,acc,rec);scores+=sc;series.append(st)
        for mine,ref in (('L_BASE','BASE_POWER'),('L_RAW','RAW_SHARED')):
            mrow=next(v for v in sc if v['arm']==mine)
            rr=p2a[(p2a.case==a.case)&(p2a.bias==bias)&(p2a.channel==ch)&(p2a.init=='NOM')&(p2a.arm==ref)]
            assert len(rr)==1,(stem,ref)
            errs={k:abs(mrow[k]-float(rr.iloc[0][k])) for k in ('heading_rmse_deg','heading_nees_1d','xy_rmse_cm','anchor_range_rmse_cm')}
            qa['parity'][f'{stem}:{mine}=={ref}']=errs
            assert max(errs.values())<1e-7,('LADDER_PARITY_FAIL',stem,mine,errs)
        print(f'LADDER_DONE {stem}',flush=True)
    pd.DataFrame(scores).to_csv(out/f'{a.case}_LADDER_SCORES.csv',index=False)
    pd.concat(series,ignore_index=True).to_csv(out/f'{a.case}_LADDER_SERIES.csv.gz',index=False,compression='gzip')
    (out/f'{a.case}_LADDER_QA.json').write_text(json.dumps(qa,indent=2))
    print('LADDER_CASE_PASS '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
