#!/usr/bin/env python3
"""System-level verification, stage 2 (16_SYSTEM_VERIFICATION_PLAN_KO.md): net value of the polarization channel.

V3: the Monte Carlo replay of p2_mc.py (same seeds, same RF, same motion noise) with
  BASE, PWIDE_NOES, ORACLE                    as in p2_mc (parity against MC_ALL.csv, 1e-6)
  NOPOL                                       range-only update, chi2_1(0.99) gate (strict_common ronly path)
  BASE_RS{3,10,30}, PWIDE_RS{3,10,30}         R_s multiplied by k in both gate and update (diagnostic sensitivity
                                              scan of the polarization weight, NOT a proposed fix)
Scored per window (0-10, 10-30, 30-60, 60+ and 30+ s): heading, XY, radial, tangential, NEES/coverage, accept.
"""
from __future__ import annotations
import argparse, json, math, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import p2_replay as R2
from p2_replay import V, S
import r2_bias_replay as RB
warnings.filterwarnings('ignore',message='X does not have valid feature names')

ARMS=[('BASE','base',1.),('BASE_RS3','base',3.),('BASE_RS10','base',10.),('BASE_RS30','base',30.),
      ('PWIDE_NOES','pwide',1.),('PWIDE_RS3','pwide',3.),('PWIDE_RS10','pwide',10.),('PWIDE_RS30','pwide',30.),
      ('NOPOL','nopol',1.),('ORACLE','oracle',1.)]
WIN={'w0_10':(0,10),'w10_30':(10,30),'w30_60':(30,60),'w60_plus':(60,np.inf),'stable_30_plus':(30,np.inf)}
CH1=3.841458820694124;CH2=5.991464547107979
def seed_of(i):return RB.SEED if i==0 else RB.SEED+7919*i

def run(model,case,controls,x0,P0,z,Xf,mdl,mu0,R0,sL):
    n=len(z);J=len(ARMS);X=np.zeros((n,J,4));C=np.zeros((n,J,4,4));acc=np.zeros((n,J),bool)
    xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0);row=np.zeros((1,Xf.shape[1]+1))
    ronly=np.array([kind=='nopol' for _,kind,_ in ARMS])
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True);cache={}
        for j,(arm,kind,ks) in enumerate(ARMS):
            mu=mu0[k].copy();r=R0[k].copy();r[1,1]*=ks
            if kind in ('base','nopol'):ehat=0.
            elif kind=='oracle':ehat=float(z[k,1]-sL[k]);mu[1]=0.
            else:row[0,:-1]=Xf[k];row[0,-1]=z[k,1]-h[j,1];ehat=float(mdl.predict(row)[0])
            zk=z[k].copy();zk[1]-=ehat
            xo,Po,nis,yes=S.update(xs[j][None],Ps[j][None],zk,h[j][None],H[j][None],mu[None],mu[None],r[None],r[None],ronly[j:j+1])
            xs[j],Ps[j]=xo[0],Po[0];acc[k,j]=bool(yes[0])
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):raise FloatingPointError(arm)
            X[k,j]=xs[j];C[k,j]=Ps[j]
    return X,C,acc

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--l4models',required=True)
    ap.add_argument('--seeds',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    l4=joblib.load(a.l4models);assert l4['held']==Hr and Hr not in l4['train_routes']
    mdl=l4['models']['P_D0'];med=l4['medians']['P_D0'];assert list(mdl.feature_names_in_)[-1]=='d0'
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);idx=[int(x) for x in a.seeds.split(',')]
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz');pk=pk[pk.case==a.case].sort_values('pose_id')
    mc=pd.read_csv(HERE/'results_eb2_mc/MC_ALL.csv');model=V.SourceFFD();rows=[];qa={'case':a.case,'seeds':{i:seed_of(i) for i in idx},'parity':{}}
    anc=np.asarray(case['anchor'],float);dz=anc[2]-float(case['robot_z_m'])
    for bias in ('B0','L2'):
        stem=f'{a.case}_full_{bias}';old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only']
        d=obs[(obs.case==a.case)&(obs.channel=='full')].set_index('pose_id').loc[ids];z=d[['range_m','s_fp']].to_numpy(float)
        features,_=R2.full_features(pk,ids);Xf=R2.m_inputs(features,med)[list(mdl.feature_names_in_)[:-1]].to_numpy(float)
        mu0,R0=V.base_params(param,a.case,'full',ids,'POWER_DIAG');sL=pk.set_index('pose_id').loc[ids]['sL_+0'].to_numpy()
        ur=np.c_[truth[:,0]-anc[0],truth[:,1]-anc[1]];ur/=np.linalg.norm(ur,axis=1,keepdims=True);ut=np.c_[-ur[:,1],ur[:,0]]
        for i in idx:
            controls,x0r=V.build_positive_bias_controls(t,truth,bias,seed=seed_of(i))
            x0=np.r_[x0r,0.];P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
            X,C,acc=run(model,case,controls,x0,P0,z,Xf,mdl,mu0,R0,sL)
            init=math.degrees(float(V.MC.wrap(x0r[2]-truth[0,2])))
            for j,(arm,kind,ks) in enumerate(ARMS):
                he=np.asarray(V.MC.wrap(X[:,j,2]-truth[:,2]));ex=X[:,j,:2]-truth[:,:2];er=np.sum(ex*ur,1);et=np.sum(ex*ut,1)
                Pxy=C[:,j,:2,:2];nxy=np.einsum('ki,kij,kj->k',ex,np.linalg.inv(Pxy),ex);nh=he**2/C[:,j,2,2]
                s2r=np.einsum('ki,kij,kj->k',ur,Pxy,ur);s2t=np.einsum('ki,kij,kj->k',ut,Pxy,ut)
                dtrue=np.sqrt(np.sum((truth[:,:2]-anc[:2])**2,1)+dz**2);dhat=np.sqrt(np.sum((X[:,j,:2]-anc[:2])**2,1)+dz**2)
                base={'case':a.case,'route':Hr,'bias':bias,'seed_idx':i,'seed':seed_of(i),'arm':arm,'kind':kind,'Rs_scale':ks,'init_heading_err_deg':init}
                for wn,(t0,t1) in WIN.items():
                    mk=(t>=t0)&(t<t1)
                    if mk.sum()<5:continue
                    rows.append({**base,'window':wn,'heading_rmse_deg':math.degrees(float(np.sqrt(np.mean(he[mk]**2)))),'heading_bias_deg':math.degrees(float(he[mk].mean())),
                        'heading_nees':float(nh[mk].mean()),'heading_cov95':float(np.mean(nh[mk]<=CH1)),
                        'xy_rmse_cm':100*float(np.sqrt(np.mean(er[mk]**2+et[mk]**2))),'radial_rmse_cm':100*float(np.sqrt(np.mean(er[mk]**2))),
                        'tangential_rmse_cm':100*float(np.sqrt(np.mean(et[mk]**2))),'tangential_bias_cm':100*float(et[mk].mean()),
                        'range_err_rmse_cm':100*float(np.sqrt(np.mean((dhat-dtrue)[mk]**2))),'xy_nees':float(nxy[mk].mean()),'xy_cov95':float(np.mean(nxy[mk]<=CH2)),
                        'tangential_cov95':float(np.mean(et[mk]**2/s2t[mk]<=CH1)),'radial_cov95':float(np.mean(er[mk]**2/s2r[mk]<=CH1)),'accept':float(acc[mk,j].mean())})
                if arm in ('BASE','PWIDE_NOES','ORACLE'):
                    r=next(x for x in rows if x['seed_idx']==i and x['bias']==bias and x['arm']==arm and x['window']=='stable_30_plus')
                    rr=mc[(mc.case==a.case)&(mc.bias==bias)&(mc.seed_idx==i)&(mc.arm==arm)].iloc[0]
                    p=[abs(r['heading_rmse_deg']-rr.stable_30_plus_heading_rmse_deg),abs(r['xy_rmse_cm']-rr.stable_30_plus_xy_rmse_cm)]
                    qa['parity'][f'{stem}:{i}:{arm}']=p;assert max(p)<1e-6,('NOPOL_PARITY_FAIL',stem,i,arm,p)
            print(f'NOPOL_DONE {stem} seed_idx={i}',flush=True)
    tag='_'.join(map(str,idx))
    pd.DataFrame(rows).to_csv(out/f'{a.case}_NOPOL_{tag}.csv',index=False);(out/f'{a.case}_NOPOL_QA_{tag}.json').write_text(json.dumps(qa,indent=2))
    from p2_sysdiag import write_manifest
    write_manifest(out/f'{a.case}_NOPOL_MANIFEST_{tag}.json',vars(a),[a.l4models,str(HERE/'results_eb2_mc/MC_ALL.csv')],[f'{a.case}_NOPOL_{tag}.csv'])
    print('NOPOL_PASS',flush=True)

if __name__=='__main__':main()
