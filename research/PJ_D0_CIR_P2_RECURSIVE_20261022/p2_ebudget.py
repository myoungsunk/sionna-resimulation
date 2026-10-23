#!/usr/bin/env python3
"""Exact linear error budget of the realized recursive EKF (11_ERROR_BUDGET_PLAN_KO.md). Diagnostic.

Replays BASE, CIR, WIDE_NOES, PWIDE_NOES, ORACLE (REAL filter, R = POWER V_s) and stores per step
the gain K (0 when gated out), H at the prior, F/G of the transition, states and residuals. Then,
with K, H, F, G fixed, the state error is an exact sum of sources:
  d-_k = F_k d+_{k-1} + G_k w_k + r_pred_k,   d+_k = (I - K_k H_k) d-_k + K_k eps_k + K_k r_meas_k
eps_k = z_k - ehat_k - mu_k - h(x_k^GT) split into range, pol c1 by FP-shift layer, pol c2.
GT is read for the decomposition only.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import p2_replay as R2
from p2_replay import V, S
import core as CORE
import r2_bias_replay as RB

ARMS={'BASE':('POWER','none',None),'CIR':('ZERO','l4','W_X1'),'WIDE_NOES':('ZERO','l4','W_D0'),
      'PWIDE_NOES':('POWER','l4','P_D0'),'ORACLE':('ZERO','oracle',None)}
SRC=['initial','odom','gyro','range','pol_c1_fp0','pol_c1_fp1','pol_c1_fp2','pol_c2','r_pred','r_meas']

def replay(model,case,controls,x0,P0,z,features,l4,mu0,R0,sL,hgt):
    n=len(z);names=list(ARMS);J=len(names)
    out={nm:{'xm':np.zeros((n,4)),'xp':np.zeros((n,4)),'K':np.zeros((n,4,2)),'H':np.zeros((n,2,4)),'hm':np.zeros((n,2)),
             'mu':np.zeros((n,2)),'ehat':np.zeros(n),'ehat_gt':np.zeros(n),'acc':np.zeros(n,bool),'P':np.zeros((n,4,4)),
             'Pp':np.zeros((n,4,4)),'R':np.zeros((n,2,2)),'nis':np.zeros(n)} for nm in names}
    xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0);pre={};mdl={}
    for nm,(mus,so,key) in ARMS.items():
        if so=='l4':
            b=R2.m_inputs(features,l4['medians'][key]);m=l4['models'][key];mdl[nm]=(m,b)
            if 'd0' in getattr(m,'feature_names_in_',[]):
                xg=b.copy();xg['d0']=z[:,1]-hgt[:,1];out[nm]['ehat_gt'][:]=m.predict(xg)
            else:
                pre[nm]=m.predict(b);out[nm]['ehat_gt'][:]=pre[nm]
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True)
        for j,nm in enumerate(names):
            mus,so,key=ARMS[nm];o=out[nm];o['xm'][k]=xs[j];o['H'][k]=H[j];o['hm'][k]=h[j];o['P'][k]=Ps[j]
            if so=='none':ehat=0.
            elif so=='oracle':ehat=float(z[k,1]-sL[k]);o['ehat_gt'][k]=ehat
            elif nm in pre:ehat=float(pre[nm][k])
            else:
                m,b=mdl[nm];x=b.iloc[[k]].copy();x['d0']=float(z[k,1]-h[j,1]);ehat=float(m.predict(x)[0])
            mu=mu0[k].copy()
            if mus=='ZERO':mu[1]=0.
            r=R0[k].copy();zk=z[k].copy();zk[1]-=ehat;o['mu'][k]=mu;o['ehat'][k]=ehat
            HP=H[j]@Ps[j];Se=HP@H[j].T+r;Se=.5*(Se+Se.T);Kk=np.linalg.solve(Se,HP).T
            xo,Po,nis,yes=S.update(xs[j][None],Ps[j][None],zk,h[j][None],H[j][None],mu[None],mu[None],r[None],r[None],np.array([False]))
            if yes[0]:o['K'][k]=Kk
            o['acc'][k]=bool(yes[0]);xs[j],Ps[j]=xo[0],Po[0];o['xp'][k]=xs[j];o['Pp'][k]=Ps[j];o['R'][k]=r;o['nis'][k]=float(nis[0])
        if k%250==0:print(f'EB_FRAME {case["id"]} k={k}/{n}',flush=True)
    return out

def budget(o,z,hgt,truth,controls,b_true,ds_true,dth_true,fp,t):
    n=len(z);X=np.c_[truth[:,:3],np.full(n,b_true)]
    def dx(a,b):d=a-b;d[...,2]=np.asarray(V.MC.wrap(d[...,2]));return d
    dm=dx(o['xm'],X);dp=dx(o['xp'],X)
    eps=np.c_[z[:,0]-o['mu'][:,0]-hgt[:,0],z[:,1]-o['ehat']-o['mu'][:,1]-hgt[:,1]]
    c2=o['ehat_gt']-o['ehat'];c1=eps[:,1]-c2
    r_meas=hgt-o['hm']+np.einsum('kij,kj->ki',o['H'],dm)
    F=np.zeros((n,4,4));G=np.zeros((n,4,3));w=np.zeros((n,3));r_pred=np.zeros((n,4))
    for k in range(1,n):
        _,Fk,Gk=CORE.transition(o['xp'][k-1],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        F[k]=Fk;G[k]=Gk
        w[k]=[controls['ds_odom'][k]-ds_true[k],controls['dtheta_gyro'][k]-dth_true[k]-b_true*controls['dt_s'][k],0.]
        r_pred[k]=dm[k]-Fk@dp[k-1]-Gk@w[k]
    lay=np.select([fp==0,np.abs(fp)==1],[0,1],2)
    def run(nobias):
        D=np.zeros((len(SRC),4));Hd=np.zeros((n,len(SRC)));tot_check=np.zeros((n,4))
        for k in range(n):
            if k==0:Dm=np.zeros_like(D);Dm[0]=dm[0]
            else:
                Fk=F[k].copy()
                if nobias:Fk[:,3]=0.;Fk[3,3]=1.
                Dm=D@Fk.T;Dm[1]+=G[k][:,0]*w[k,0];Dm[2]+=G[k][:,1]*w[k,1];Dm[8]+=r_pred[k]
            A=np.eye(4)-o['K'][k]@o['H'][k];D=Dm@A.T;Kk=o['K'][k]
            D[3]+=Kk[:,0]*eps[k,0]
            D[4+lay[k]]+=Kk[:,1]*c1[k]
            D[7]+=Kk[:,1]*c2[k]
            D[9]+=Kk@r_meas[k]
            Hd[k]=D[:,2];tot_check[k]=D.sum(0)
        return Hd,tot_check
    Hd,chk=run(False);Hn,_=run(True)
    closure=float(np.max(np.abs(chk-dp)[:,2]))
    m=t>=30;tot=dp[m,2];mse=float(np.mean(tot**2))
    res={'heading_rmse_deg':math.degrees(math.sqrt(mse)),'closure_max_deg':math.degrees(closure),'acc_frac':float(o['acc'][m].mean())}
    for i,s in enumerate(SRC):
        c=Hd[m,i];cb=c-Hn[m,i]
        res[f'share_{s}']=float(np.mean(c*tot)/mse);res[f'rms_{s}_deg']=math.degrees(math.sqrt(np.mean(c**2)))
        res[f'biaspath_share_{s}']=float(np.mean(cb*tot)/mse)
    res['biaspath_share_total']=float(sum(res[f'biaspath_share_{s}'] for s in SRC))
    # memory: share of heading MSE carried by errors older than T seconds (homogeneous propagation)
    for T in (10.,30.):
        old=np.zeros(n)
        for k in np.where(m)[0]:
            j0=np.searchsorted(t,t[k]-T)
            if j0<=0:old[k]=dp[k,2];continue
            d=dp[j0-1].copy()
            for q in range(j0,k+1):
                d=F[q]@d;d=(np.eye(4)-o['K'][q]@o['H'][q])@d
            old[k]=d[2]
        res[f'memory_share_older_{int(T)}s']=float(np.mean(old[m]*tot)/mse)
    res['bg_err_rms_dps']=math.degrees(math.sqrt(np.mean(dp[m,3]**2)))
    return res

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--l4models',required=True)
    ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    l4=joblib.load(a.l4models);assert l4['held']==Hr and Hr not in l4['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz');pk=pk[pk.case==a.case].sort_values('pose_id')
    ref=pd.read_csv(HERE/'results_ladder4/LADDER4_SCORES.csv');refmap={'BASE':'L_BASE','CIR':'L_CIR','WIDE_NOES':'L_WIDE_NOES','PWIDE_NOES':'L_PWIDE_NOES','ORACLE':'L_ORACLE'}
    model=V.SourceFFD();rows=[];qa={'case':a.case,'parity':{}}
    for bias in ('B0','L2'):
        stem=f'{a.case}_full_{bias}';old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only'];n=len(t)
        d=obs[(obs.case==a.case)&(obs.channel=='full')].set_index('pose_id').loc[ids];z=d[['range_m','s_fp']].to_numpy(float)
        features,_=R2.full_features(pk,ids);mu0,R0=V.base_params(param,a.case,'full',ids,'POWER_DIAG')
        controls,x0r=V.build_positive_bias_controls(t,truth,bias)
        x0=np.r_[x0r,0.];P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
        P_=pk.set_index('pose_id').loc[ids];sL=P_['sL_+0'].to_numpy();fp=P_['fp_shift_tap'].to_numpy(float)
        hgt=np.concatenate([model.batch(np.c_[truth[i:i+32,:3],np.zeros(len(truth[i:i+32]))],case,gradient=True)[0] for i in range(0,n,32)])
        ds_true,dth_true=RB.motion_increments(t,truth,convention='legacy-euler')
        b_true=math.radians(V.BIAS_LEVELS[bias])
        res=replay(model,case,controls,x0,P0,z,features,l4,mu0,R0,sL,hgt)
        for nm,o in res.items():
            r=budget(o,z,hgt,truth,controls,b_true,np.asarray(ds_true),np.asarray(dth_true),fp,t)
            rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.arm==refmap[nm])];assert len(rr)==1
            par=abs(r['heading_rmse_deg']-float(rr.iloc[0].heading_rmse_deg));qa['parity'][f'{stem}:{nm}']=par
            assert par<1e-6,('EB_PARITY_FAIL',stem,nm,par,r['heading_rmse_deg'])
            assert r['closure_max_deg']<1e-6,('EB_CLOSURE_FAIL',stem,nm,r['closure_max_deg'])
            rows.append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,**r})
        print(f'EB_DONE {stem}',flush=True)
    pd.DataFrame(rows).to_csv(out/f'{a.case}_EB.csv',index=False)
    (out/f'{a.case}_EB_QA.json').write_text(json.dumps(qa,indent=2))
    print('EB_CASE_PASS '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
