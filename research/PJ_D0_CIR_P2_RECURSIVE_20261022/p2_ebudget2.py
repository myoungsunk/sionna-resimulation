#!/usr/bin/env python3
"""Error budget v2 (12_ERROR_BUDGET_V2_PLAN_KO.md): full source covariance, cross-propagation
(input vs propagation effect), polarization influence kernel, and saved per-step arrays.

Uses p2_ebudget.replay unchanged. Diagnostic only; GT is read for the decomposition.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import p2_ebudget as EB
import p2_replay as R2
from p2_replay import V
import core as CORE
import r2_bias_replay as RB

SRC=EB.SRC;POL=[4,5,6,7]

def prep(o,z,hgt,truth,controls,b_true,ds_true,dth_true,fp):
    n=len(z);X=np.c_[truth[:,:3],np.full(n,b_true)]
    def dx(a,b):d=a-b;d[...,2]=np.asarray(V.MC.wrap(d[...,2]));return d
    dm=dx(o['xm'],X);dp=dx(o['xp'],X)
    eps=np.c_[z[:,0]-o['mu'][:,0]-hgt[:,0],z[:,1]-o['ehat']-o['mu'][:,1]-hgt[:,1]]
    c2=o['ehat_gt']-o['ehat'];c1=eps[:,1]-c2
    r_meas=hgt-o['hm']+np.einsum('kij,kj->ki',o['H'],dm)
    F=np.repeat(np.eye(4)[None],n,0);G=np.zeros((n,4,3));w=np.zeros((n,3));r_pred=np.zeros((n,4))
    for k in range(1,n):
        _,Fk,Gk=CORE.transition(o['xp'][k-1],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        F[k]=Fk;G[k]=Gk
        w[k]=[controls['ds_odom'][k]-ds_true[k],controls['dtheta_gyro'][k]-dth_true[k]-b_true*controls['dt_s'][k],0.]
        r_pred[k]=dm[k]-Fk@dp[k-1]-Gk@w[k]
    lay=np.select([fp==0,np.abs(fp)==1],[0,1],2)
    return {'dm':dm,'dp':dp,'eps':eps,'c1':c1,'c2':c2,'r_meas':r_meas,'F':F,'G':G,'w':w,'r_pred':r_pred,'lay':lay,
            'K':o['K'],'H':o['H'],'acc':o['acc']}

def propagate(Wt,In):
    """Source-resolved heading error: weights (K,H,F,G) from Wt, inputs from In. Returns (n, nsrc)."""
    n=len(In['eps']);D=np.zeros((len(SRC),4));Hd=np.zeros((n,len(SRC)))
    for k in range(n):
        if k==0:Dm=np.zeros_like(D);Dm[0]=In['dm'][0]
        else:
            Dm=D@Wt['F'][k].T;Dm[1]+=Wt['G'][k][:,0]*In['w'][k,0];Dm[2]+=Wt['G'][k][:,1]*In['w'][k,1];Dm[8]+=In['r_pred'][k]
        Kk=Wt['K'][k];A=np.eye(4)-Kk@Wt['H'][k];D=Dm@A.T
        D[3]+=Kk[:,0]*In['eps'][k,0];D[4+In['lay'][k]]+=Kk[:,1]*In['c1'][k];D[7]+=Kk[:,1]*In['c2'][k];D[9]+=Kk@In['r_meas'][k]
        Hd[k]=D[:,2]
    return Hd

def kernel(Wt,t,ev,c1,g):
    """Polarization influence kernel W(t,k)=e_psi' Phi(t,k) K_k[:,1] for t in ev (subsampled)."""
    out=[];n=len(t)
    for ti in ev:
        lam=np.zeros(4);lam[2]=1.;Wk=np.zeros(ti+1)
        for k in range(ti,-1,-1):
            Wk[k]=lam@Wt['K'][k][:,1]
            if k>0:lam=lam@(np.eye(4)-Wt['K'][k]@Wt['H'][k])@Wt['F'][k]
        age=t[ti]-t[:ti+1];aw=np.abs(Wk);S=aw.sum()
        if S<=0:continue
        cs=np.cumsum(aw[::-1])[::-1]/S
        out.append({'t':float(t[ti]),'sum_abs_W':float(S),'neg_weight_frac':float(aw[Wk<0].sum()/S),
                    'mean_age_s':float((aw*age).sum()/S),'frac_older_10s':float(aw[age>10].sum()/S),'frac_older_30s':float(aw[age>30].sum()/S),
                    'half_weight_age_s':float(age[np.argmin(np.abs(cs-.5))]),'pol_signal_passthrough':float(np.sum(Wk*g[:ti+1])),
                    'pol_c1_heading_deg':math.degrees(float(np.sum(Wk*c1[:ti+1])))})
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--l4models',required=True)
    ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    l4=joblib.load(a.l4models);assert l4['held']==Hr and Hr not in l4['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz');pk=pk[pk.case==a.case].sort_values('pose_id')
    ref=pd.read_csv(HERE/'results_ladder4/LADDER4_SCORES.csv')
    refmap={'BASE':'L_BASE','CIR':'L_CIR','WIDE_NOES':'L_WIDE_NOES','PWIDE_NOES':'L_PWIDE_NOES','ORACLE':'L_ORACLE'}
    model=V.SourceFFD();share=[];cov=[];cross=[];kern=[];qa={'case':a.case,'parity':{},'closure':{}}
    for bias in ('B0','L2'):
        stem=f'{a.case}_full_{bias}';old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only'];n=len(t)
        d=obs[(obs.case==a.case)&(obs.channel=='full')].set_index('pose_id').loc[ids];z=d[['range_m','s_fp']].to_numpy(float)
        features,_=R2.full_features(pk,ids);mu0,R0=V.base_params(param,a.case,'full',ids,'POWER_DIAG')
        controls,x0r=V.build_positive_bias_controls(t,truth,bias)
        x0=np.r_[x0r,0.];P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
        P_=pk.set_index('pose_id').loc[ids];sL=P_['sL_+0'].to_numpy();fp=P_['fp_shift_tap'].to_numpy(float)
        hgt=np.concatenate([model.batch(np.c_[truth[i:i+32,:3],np.zeros(len(truth[i:i+32]))],case,gradient=True)[0] for i in range(0,n,32)])
        ds_true,dth_true=RB.motion_increments(t,truth,convention='legacy-euler');b_true=math.radians(V.BIAS_LEVELS[bias])
        res=EB.replay(model,case,controls,x0,P0,z,features,l4,mu0,R0,sL,hgt)
        pr={nm:prep(o,z,hgt,truth,controls,b_true,np.asarray(ds_true),np.asarray(dth_true),fp) for nm,o in res.items()}
        m=t>=30;ev=np.where(m)[0][::10]
        np.savez_compressed(out/f'{stem}_EB2_ARRAYS.npz',t=t,truth=truth,hgt=hgt,z=z,fp=fp,
            **{f'{nm}__{k}':v for nm,p in pr.items() for k,v in p.items()},**{f'{nm}__xp':o['xp'] for nm,o in res.items()},
            **{f'{nm}__xm':o['xm'] for nm,o in res.items()},**{f'{nm}__ehat':o['ehat'] for nm,o in res.items()})
        own={}
        for nm,p in pr.items():
            Hd=propagate(p,p);own[nm]=Hd;tot=p['dp'][m,2];mse=float(np.mean(tot**2))
            clo=float(np.max(np.abs(Hd.sum(1)-p['dp'][:,2])));qa['closure'][f'{stem}:{nm}']=math.degrees(clo)
            assert math.degrees(clo)<1e-6,('EB2_CLOSURE_FAIL',stem,nm,clo)
            rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.arm==refmap[nm])];par=abs(math.degrees(math.sqrt(mse))-float(rr.iloc[0].heading_rmse_deg))
            qa['parity'][f'{stem}:{nm}']=par;assert par<1e-6,('EB2_PARITY_FAIL',stem,nm,par)
            C=(Hd[m].T@Hd[m])/m.sum()
            for i,si in enumerate(SRC):
                share.append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,'source':si,'C_diag_deg2':math.degrees(1)**2*C[i,i],
                              'share':float(C[i].sum()/mse),'rms_deg':math.degrees(math.sqrt(C[i,i])),'heading_mse_deg2':math.degrees(1)**2*mse})
                for j,sj in enumerate(SRC):
                    cov.append({'case':a.case,'bias':bias,'arm':nm,'src_i':si,'src_j':sj,'C_deg2':math.degrees(1)**2*C[i,j]})
            for row in kernel(p,t,ev,p['c1'],p['H'][:,1,2]):kern.append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,**row})
        # cross-propagation vs BASE: inputs of A through weights of B
        for nm in [x for x in pr if x!='BASE']:
            for (In,Wt) in ((nm,nm),(nm,'BASE'),('BASE',nm),('BASE','BASE')):
                Hd=own[In] if In==Wt else propagate(pr[Wt],pr[In])
                mse_all=float(np.mean(Hd[m].sum(1)**2));mse_pol=float(np.mean(Hd[m][:,POL].sum(1)**2))
                cross.append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,'inputs':In,'weights':Wt,
                              'heading_mse_deg2':math.degrees(1)**2*mse_all,'pol_only_mse_deg2':math.degrees(1)**2*mse_pol})
        print(f'EB2_DONE {stem}',flush=True)
    pd.DataFrame(share).to_csv(out/f'{a.case}_EB2_SHARE.csv',index=False);pd.DataFrame(cov).to_csv(out/f'{a.case}_EB2_COV.csv',index=False)
    pd.DataFrame(cross).to_csv(out/f'{a.case}_EB2_CROSS.csv',index=False);pd.DataFrame(kern).to_csv(out/f'{a.case}_EB2_KERNEL.csv',index=False)
    (out/f'{a.case}_EB2_QA.json').write_text(json.dumps(qa,indent=2));print('EB2_CASE_PASS',flush=True)

if __name__=='__main__':main()
