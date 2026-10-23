#!/usr/bin/env python3
"""P2 ladder 2: replace the R_s rule only (04_LADDER_RS_RULE_KO.md).

For each corrector X in {BASE, CIR, WIDE}:  L_X (update R = gate R = V_s)
  -> L_X_KU (update R = kappa_X V_s, gate R = V_s)  -> L_X_KV (gate R also kappa_X V_s).
kappa_X comes from p2_rkappa.py (training routes only). Everything else equals ladder 1.
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

# arm: (mu_s, ehat, kappa key, scale update R, scale gate R)
ARMS2={
 'L_BASE':   ('POWER','NONE','BASE',False,False),
 'L_BASE_KU':('POWER','NONE','BASE',True, False),
 'L_BASE_KV':('POWER','NONE','BASE',True, True),
 'L_CIR':    ('ZERO','CIR','CIR_ONLY',False,False),
 'L_CIR_KU': ('ZERO','CIR','CIR_ONLY',True, False),
 'L_CIR_KV': ('ZERO','CIR','CIR_ONLY',True, True),
 'L_WIDE':   ('ZERO','WIDE','CIR_PLUS_D0_WIDE',False,False),
 'L_WIDE_KU':('ZERO','WIDE','CIR_PLUS_D0_WIDE',True, False),
 'L_WIDE_KV':('ZERO','WIDE','CIR_PLUS_D0_WIDE',True, True),
 'L_ORACLE': ('ZERO','ORACLE','CIR_ONLY',False,False),
}
ARMS=list(ARMS2)

def run(model,case,controls,x0,P0,t,z,features,models,meds,kappa,mu0,R0,sL):
    n=len(t);J=len(ARMS)
    X=np.full((n,J,4),np.nan);C=np.full((n,J,4,4),np.nan);acc=np.zeros((n,J),bool)
    rec={k:np.full((n,J),np.nan) for k in ['nis','d0','ehat','nu_s','nu_r','s_clean','gpsi','prior_heading_rad','eps']}
    xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0)
    cir=models['CIR_ONLY'].predict(R2.m_inputs(features,meds['CIR_ONLY']));bw=R2.m_inputs(features,meds['WIDE'])
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),
                                          float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True)
        for j,arm in enumerate(ARMS):
            mus,es,kk,su,sg=ARMS2[arm]
            rec['prior_heading_rad'][k,j]=float(xs[j,2]);rec['gpsi'][k,j]=H[j,1,2]*math.pi/180
            d0=float(z[k,1]-h[j,1]);rec['d0'][k,j]=d0
            if es=='NONE':ehat=0.
            elif es=='CIR':ehat=float(cir[k])
            elif es=='WIDE':
                inp=bw.iloc[[k]].copy();inp['d0']=d0;ehat=float(models['WIDE'].predict(inp)[0])
            elif es=='ORACLE':ehat=float(z[k,1]-sL[k])
            else:raise RuntimeError(es)
            mu=mu0[k].copy()
            if mus=='ZERO':mu[1]=0.
            Rg=R0[k].copy();Ru=R0[k].copy();kap=float(kappa[kk])
            if su:Ru[1,1]*=kap
            if sg:Rg[1,1]*=kap
            zk=z[k].copy();zk[1]-=ehat
            rec['ehat'][k,j]=ehat;rec['s_clean'][k,j]=zk[1]-mu[1];rec['eps'][k,j]=zk[1]-mu[1]-sL[k]
            rec['nu_s'][k,j]=zk[1]-h[j,1]-mu[1];rec['nu_r'][k,j]=zk[0]-h[j,0]-mu[0]
            xo,Po,nis,yes=S.update(xs[j][None],Ps[j][None],zk,h[j][None],H[j][None],mu[None],mu[None],
                                   Rg[None],Ru[None],np.array([False]))
            xs[j],Ps[j]=xo[0],Po[0];rec['nis'][k,j]=float(nis[0]);acc[k,j]=bool(yes[0])
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):raise FloatingPointError(arm)
            if np.linalg.eigvalsh(Ps[j]).min()<-1e-11:raise FloatingPointError(f'COV_NOT_PSD {arm} {k}')
            X[k,j]=xs[j];C[k,j]=Ps[j]
        if k%250==0:print(f'LADDER2_FRAME {case["id"]} k={k}/{n}',flush=True)
    return X,C,acc,rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--models',required=True)
    ap.add_argument('--kappa',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    pack=joblib.load(a.models);assert pack['held']==Hr and Hr not in pack['train_routes']
    kq=json.loads(Path(a.kappa).read_text());assert kq['held']==Hr and Hr not in kq['train_routes']
    kappa=kq['kappa'];out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    pk=pk[pk.case==a.case].sort_values('pose_id')
    model=V.SourceFFD();scores=[];series=[]
    qa={'case':a.case,'held':Hr,'kappa':kappa,'arms':ARMS2,'parity':{}}
    ref_p2a=pd.read_csv(HERE/'results_full/P2_A_SCORES.csv');ref_l1=pd.read_csv(HERE/'results_ladder/LADDER_SCORES.csv')
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
        X,C,acc,rec=run(model,case,controls,x0,P0,t,z,features,pack['models'],pack['medians'],kappa,mu0,R0,sL)
        sc,st=R2.score(case,bias,ch,'NOM',t,truth,X,C,acc,ARMS,{k:v for k,v in rec.items() if k!='eps'})
        sc=L1.extra(sc,t,X,truth,acc,rec);scores+=sc;series.append(st)
        checks=[('L_BASE',ref_p2a[(ref_p2a.init=='NOM')&(ref_p2a.arm=='BASE_POWER')]),
                ('L_CIR',ref_l1[ref_l1.arm=='L_CIR']),('L_WIDE',ref_l1[ref_l1.arm=='L_WIDE']),('L_ORACLE',ref_l1[ref_l1.arm=='L_ORACLE'])]
        for mine,ref in checks:
            row=next(v for v in sc if v['arm']==mine)
            rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.channel==ch)];assert len(rr)==1,(stem,mine)
            errs={k:abs(row[k]-float(rr.iloc[0][k])) for k in ('heading_rmse_deg','heading_nees_1d','xy_rmse_cm','anchor_range_rmse_cm')}
            qa['parity'][f'{stem}:{mine}']=errs;assert max(errs.values())<1e-7,('LADDER2_PARITY_FAIL',stem,mine,errs)
        print(f'LADDER2_DONE {stem}',flush=True)
    pd.DataFrame(scores).to_csv(out/f'{a.case}_LADDER2_SCORES.csv',index=False)
    pd.concat(series,ignore_index=True).to_csv(out/f'{a.case}_LADDER2_SERIES.csv.gz',index=False,compression='gzip')
    (out/f'{a.case}_LADDER2_QA.json').write_text(json.dumps(qa,indent=2))
    print('LADDER2_CASE_PASS '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
