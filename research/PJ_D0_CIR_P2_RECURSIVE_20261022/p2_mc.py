#!/usr/bin/env python3
"""Monte Carlo over sensor-noise / initial-pose seeds (12_ERROR_BUDGET_V2_MC_PLAN_KO.md).

BASE, PWIDE_NOES (ladder-4 P_D0), ORACLE; R = POWER V_s; Full B0 and L2; NOM initial covariance.
Seed index 0 is the original seed (RB.SEED) and must reproduce earlier results. Each other seed changes
the gyro/odometry noise stream and the initial pose draw only; RF packets are identical.
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

ARMS=['BASE','PWIDE_NOES','ORACLE']
WIN={'initial_0_10':(0,10),'middle_10_30':(10,30),'stable_30_plus':(30,np.inf)}
def seed_of(i):return RB.SEED if i==0 else RB.SEED+7919*i

def run(model,case,controls,x0,P0,z,Xf,mdl,mu0,R0,sL):
    n=len(z);J=len(ARMS);X=np.zeros((n,J,4));C=np.zeros((n,J,4,4));acc=np.zeros((n,J),bool)
    xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0);row=np.zeros((1,Xf.shape[1]+1))
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True)
        for j,arm in enumerate(ARMS):
            mu=mu0[k].copy()
            if arm=='BASE':ehat=0.
            elif arm=='ORACLE':ehat=float(z[k,1]-sL[k]);mu[1]=0.
            else:row[0,:-1]=Xf[k];row[0,-1]=z[k,1]-h[j,1];ehat=float(mdl.predict(row)[0])
            zk=z[k].copy();zk[1]-=ehat;r=R0[k]
            xo,Po,nis,yes=S.update(xs[j][None],Ps[j][None],zk,h[j][None],H[j][None],mu[None],mu[None],r[None],r[None],np.array([False]))
            xs[j],Ps[j]=xo[0],Po[0];acc[k,j]=bool(yes[0])
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):raise FloatingPointError(arm)
            X[k,j]=xs[j];C[k,j]=Ps[j]
    return X,C,acc

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--l4models',required=True)
    ap.add_argument('--seeds',required=True,help='comma separated seed indices');ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    l4=joblib.load(a.l4models);assert l4['held']==Hr and Hr not in l4['train_routes']
    mdl=l4['models']['P_D0'];med=l4['medians']['P_D0'];assert list(mdl.feature_names_in_)[-1]=='d0'
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);idx=[int(x) for x in a.seeds.split(',')]
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz');pk=pk[pk.case==a.case].sort_values('pose_id')
    ref_p2a=pd.read_csv(HERE/'results_full/P2_A_SCORES.csv');ref4=pd.read_csv(HERE/'results_ladder4/LADDER4_SCORES.csv')
    model=V.SourceFFD();rows=[];qa={'case':a.case,'seeds':{i:seed_of(i) for i in idx},'parity':{}}
    for bias in ('B0','L2'):
        stem=f'{a.case}_full_{bias}';old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only']
        d=obs[(obs.case==a.case)&(obs.channel=='full')].set_index('pose_id').loc[ids];z=d[['range_m','s_fp']].to_numpy(float)
        features,_=R2.full_features(pk,ids);Xf=R2.m_inputs(features,med)[list(mdl.feature_names_in_)[:-1]].to_numpy(float)
        mu0,R0=V.base_params(param,a.case,'full',ids,'POWER_DIAG');sL=pk.set_index('pose_id').loc[ids]['sL_+0'].to_numpy()
        ds_true,dth_true=RB.motion_increments(t,truth,convention='legacy-euler');b_true=math.radians(V.BIAS_LEVELS[bias])
        for i in idx:
            controls,x0r=V.build_positive_bias_controls(t,truth,bias,seed=seed_of(i))
            x0=np.r_[x0r,0.];P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
            X,C,acc=run(model,case,controls,x0,P0,z,Xf,mdl,mu0,R0,sL)
            wg=np.asarray(controls['dtheta_gyro'])-np.asarray(dth_true)-b_true*np.asarray(controls['dt_s'])
            init_err=math.degrees(float(V.MC.wrap(x0r[2]-truth[0,2])))
            for j,arm in enumerate(ARMS):
                he=np.degrees(np.asarray(V.MC.wrap(X[:,j,2]-truth[:,2])));sg=np.degrees(np.sqrt(C[:,j,2,2]))
                xy=np.hypot(X[:,j,0]-truth[:,0],X[:,j,1]-truth[:,1])*100
                r={'case':a.case,'route':Hr,'bias':bias,'seed_idx':i,'seed':seed_of(i),'arm':arm,'init_heading_err_deg':init_err,
                   'gyro_noise_rms_deg':math.degrees(float(np.sqrt(np.mean(wg[1:]**2))))}
                for wn,(t0,t1) in WIN.items():
                    mk=(t>=t0)&(t<t1)
                    r[f'{wn}_heading_rmse_deg']=float(np.sqrt(np.mean(he[mk]**2)));r[f'{wn}_heading_bias_deg']=float(he[mk].mean())
                    r[f'{wn}_heading_nees']=float(np.mean((he[mk]/sg[mk])**2));r[f'{wn}_cov95']=float(np.mean((he[mk]/sg[mk])**2<=3.841458820694124))
                    r[f'{wn}_xy_rmse_cm']=float(np.sqrt(np.mean(xy[mk]**2)));r[f'{wn}_accept']=float(acc[mk,j].mean())
                rows.append(r)
            if i==0:
                for arm,ref,nm in (('BASE',ref_p2a[(ref_p2a.init=='NOM')&(ref_p2a.arm=='BASE_POWER')],'heading_rmse_deg'),
                                   ('PWIDE_NOES',ref4[ref4.arm=='L_PWIDE_NOES'],'heading_rmse_deg'),('ORACLE',ref4[ref4.arm=='L_ORACLE'],'heading_rmse_deg')):
                    mine=next(v for v in rows if v['seed_idx']==0 and v['bias']==bias and v['arm']==arm)['stable_30_plus_heading_rmse_deg']
                    rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.channel=='full')];par=abs(mine-float(rr.iloc[0][nm]))
                    qa['parity'][f'{stem}:{arm}']=par;assert par<1e-7,('MC_PARITY_FAIL',stem,arm,par)
            print(f'MC_DONE {stem} seed_idx={i}',flush=True)
    tag='_'.join(map(str,idx))
    pd.DataFrame(rows).to_csv(out/f'{a.case}_MC_{tag}.csv',index=False);(out/f'{a.case}_MC_{tag}_QA.json').write_text(json.dumps(qa,indent=2))
    print('MC_PASS '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
