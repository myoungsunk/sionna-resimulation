#!/usr/bin/env python3
"""Error budget v3 (13_ERROR_BUDGET_V3_AUDIT_FIX_KO.md): audit fixes to v2. Diagnostic only.

Changes vs v2: (A) source matrix reported as uncentered M, centered C and source means;
(B) input error mean / variance / mean square each against the filter q; (3) kernel-based variance
inflation F_psi,corr = W' Gamma W / W' diag(Gamma) W for polarization and range (raw and 10 s detrended
residual ACF, stationarity assumed); (4) cross-propagation also with exogenous inputs only
(initial, odom, gyro, range, c1); (5) static WLS weights (10 s, 30 s windows, accepted packets) against the
recursive kernel, full kernels saved; (6) finite-difference QA of H, F, G; memory boundary fixed;
P-, P+, R, NIS saved. All decompositions are accounting identities under the realized linearization.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import p2_ebudget as EB
import p2_ebudget2 as E2
import p2_replay as R2
from p2_replay import V
import core as CORE
import r2_bias_replay as RB

SRC=E2.SRC;POL=[4,5,6,7];EXO=[0,1,2,3,4,5,6]
D2=math.degrees(1)**2

def memory(Wt,dp,t,m,T):
    """Heading part of the state error older than T s propagated homogeneously; 0 when t-T precedes the start."""
    n=len(t);old=np.zeros(n);I=np.eye(4)
    for k in np.where(m)[0]:
        if t[k]-T<=t[0]:continue
        j0=int(np.searchsorted(t,t[k]-T));d=dp[j0-1].copy()
        for q in range(j0,k+1):d=(I-Wt['K'][q]@Wt['H'][q])@(Wt['F'][q]@d)
        old[k]=d[2]
    return old

def rho_series(x,dt,L=400,detrend_s=None):
    x=np.asarray(x,float).copy()
    if detrend_s:
        w=max(3,int(round(detrend_s/dt)));x=x-pd.Series(x).rolling(w,center=True,min_periods=1).mean().to_numpy()
    x=x-x.mean();n=len(x);v=float(np.dot(x,x)/n);L=min(L,n//2)
    return np.array([np.dot(x[:n-l],x[l:])/(n*v) for l in range(1,L+1)]) if v>0 else np.zeros(L)

def finflate(W,rho,trunc):
    r=rho.copy()
    if trunc:
        neg=np.where(r<=0)[0]
        if len(neg):r[neg[0]:]=0.
    den=float(np.dot(W,W))
    if den<=0:return np.nan
    num=den+2*sum(r[l-1]*float(np.dot(W[:-l],W[l:])) for l in range(1,min(len(r),len(W)-1)+1) if r[l-1]!=0.)
    return num/den

def kernels(Wt,ev):
    out={}
    for ti in ev:
        lam=np.zeros(4);lam[2]=1.;Wp=np.zeros(ti+1);Wr=np.zeros(ti+1)
        for k in range(ti,-1,-1):
            Wp[k]=lam@Wt['K'][k][:,1];Wr[k]=lam@Wt['K'][k][:,0]
            if k>0:lam=lam@(np.eye(4)-Wt['K'][k]@Wt['H'][k])@Wt['F'][k]
        out[ti]=(Wp,Wr)
    return out

def fd_qa(model,case,o,controls,idx):
    eH=[];eF=[];eG=[];h=1e-6
    for k in idx:
        x=o['xm'][k].copy();_,Ha=model.batch(x[None],case,gradient=True);Ha=Ha[0]
        Hn=np.zeros((2,3))
        for c in range(3):
            xp=x.copy();xm=x.copy();xp[c]+=h;xm[c]-=h
            Hn[:,c]=(model.batch(xp[None],case,gradient=True)[0][0]-model.batch(xm[None],case,gradient=True)[0][0])/(2*h)
        eH.append(np.max(np.abs(Hn-Ha[:,:3]))/max(np.max(np.abs(Ha[:,:3])),1e-12))
        if k>0:
            x=o['xp'][k-1];u=(float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
            _,Fa,Ga=CORE.transition(x,*u);Fn=np.zeros((4,4));Gn=np.zeros((4,2))
            for c in range(4):
                xp=x.copy();xm=x.copy();xp[c]+=h;xm[c]-=h
                a=CORE.transition(xp,*u)[0];b=CORE.transition(xm,*u)[0];d=a-b;d[2]=float(V.MC.wrap(d[2]));Fn[:,c]=d/(2*h)
            for c in range(2):
                up=list(u);um=list(u);up[c]+=h;um[c]-=h
                a=CORE.transition(x,*up)[0];b=CORE.transition(x,*um)[0];d=a-b;d[2]=float(V.MC.wrap(d[2]));Gn[:,c]=d/(2*h)
            eF.append(np.max(np.abs(Fn-Fa)));eG.append(np.max(np.abs(Gn-Ga[:,:2])))
    return {'H_relmax':float(np.max(eH)),'F_absmax':float(np.max(eF)) if eF else np.nan,'G_absmax':float(np.max(eG)) if eG else np.nan}

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
    model=V.SourceFFD();T={k:[] for k in ('SHARE','MAT','CROSS','KERNEL','WLS','ACF','WQ','PATH','FINF','FD')}
    qa={'case':a.case,'parity':{},'closure':{}};rng=np.random.default_rng(20261023)
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
        pr={nm:E2.prep(o,z,hgt,truth,controls,b_true,np.asarray(ds_true),np.asarray(dth_true),fp) for nm,o in res.items()}
        m=t>=30;ev=np.where(m)[0][::10];dtm=float(np.median(np.diff(t)))
        # (B) input error statistics against q
        w0=next(iter(pr.values()))['w'];q_ds=2e-5*np.abs(np.asarray(controls['ds_odom']));q_g=math.radians(.015)**2*np.asarray(controls['dt_s'])
        for lab,mk in (('all',t>=0),('t>=30',m)):
            mk=mk.copy();mk[0]=False;row={'case':a.case,'route':Hr,'bias':bias,'window':lab,'dt_median_s':dtm}
            for nm,wv,qv in (('odom',w0[mk,0],q_ds[mk]),('gyro',w0[mk,1],q_g[mk])):
                mu_w=float(wv.mean());var=float(wv.var());ms=float(np.mean(wv**2));qm=float(qv.mean())
                row.update({f'{nm}_mean':mu_w,f'{nm}_var_over_q':var/qm,f'{nm}_mse_over_q':ms/qm,f'{nm}_mean2_over_q':mu_w**2/qm,
                            f'{nm}_rho1':E2.acf_stats(wv,dtm)['rho1']})
            row['gyro_mean_equiv_bias_dps']=math.degrees(float(w0[mk,1].mean())/float(np.asarray(controls['dt_s'])[mk].mean()))
            T['WQ'].append(row)
        rho={}
        for nm,p in pr.items():
            for sig,x in (('pol_total',p['eps'][:,1]),('range',p['eps'][:,0]),('pol_c1',p['c1']),('pol_c2',p['c2'])):
                for lab,mk in (('all',t>=0),('t>=30',m)):
                    xs=x[mk];mv=pd.Series(xs).rolling(max(3,int(round(10/dtm))),center=True,min_periods=1).mean().to_numpy()
                    T['ACF'].append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,'window':lab,'signal':sig,'mean':float(xs.mean()),
                                     'rms':float(np.sqrt(np.mean(xs**2))),'slow_mean_rms_10s':float(np.sqrt(np.mean(mv**2))),**E2.acf_stats(xs,dtm),
                                     **{f'detrended_{k}':v for k,v in E2.acf_stats(xs-mv,dtm).items()}})
            rho[nm]={(sig,dtr):rho_series(x,dtm,detrend_s=dtr) for sig,x in (('pol_total',p['eps'][:,1]),('range',p['eps'][:,0])) for dtr in (None,10.)}
        own={};kers={}
        for nm,p in pr.items():
            o=res[nm];Hd=E2.propagate(p,p);own[nm]=Hd;tot=p['dp'][m,2];mse=float(np.mean(tot**2))
            clo=float(np.max(np.abs(Hd.sum(1)-p['dp'][:,2])));qa['closure'][f'{stem}:{nm}']=math.degrees(clo)
            assert math.degrees(clo)<1e-6,('EB3_CLOSURE_FAIL',stem,nm,clo)
            rr=ref[(ref.case==a.case)&(ref.bias==bias)&(ref.arm==refmap[nm])];par=abs(math.degrees(math.sqrt(mse))-float(rr.iloc[0].heading_rmse_deg))
            qa['parity'][f'{stem}:{nm}']=par;assert par<1e-6,('EB3_PARITY_FAIL',stem,nm,par)
            # (A) uncentered M, centered C, means
            Y=Hd[m];M=(Y.T@Y)/len(Y);mean=Y.mean(0);C=M-np.outer(mean,mean)
            for i,si in enumerate(SRC):
                T['SHARE'].append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,'source':si,'heading_mse_deg2':D2*mse,'share_of_mse':float(M[i].sum()/mse),
                    'mean_deg':math.degrees(mean[i]),'rms_deg':math.degrees(math.sqrt(M[i,i])),'sd_deg':math.degrees(math.sqrt(max(C[i,i],0.))),
                    'share_of_var':float(C[i].sum()/max(C.sum(),1e-30)),'mean_part_of_mse':float(mean[i]*mean.sum()/mse)})
                for j,sj in enumerate(SRC):T['MAT'].append({'case':a.case,'bias':bias,'arm':nm,'src_i':si,'src_j':sj,'M_deg2':D2*M[i,j],'C_deg2':D2*C[i,j]})
            Hn=E2.propagate(E2.nobias_weights(p),p);cb=Hd-Hn
            prow={'case':a.case,'route':Hr,'bias':bias,'arm':nm,'heading_mse_deg2':D2*mse,'biaspath_share_total':float(np.mean(cb[m].sum(1)*tot)/mse),
                  'nobias_linear_heading_rmse_deg':math.degrees(float(np.sqrt(np.mean(Hn[m].sum(1)**2)))),
                  'nees_mean':float(np.mean(tot**2/o['Pp'][m,2,2])),'nis_mean_acc':float(o['nis'][m&o['acc']].mean())}
            for i,si in enumerate(SRC):prow[f'biaspath_share_{si}']=float(np.mean(cb[m,i]*tot)/mse)
            for TT in (10.,30.):
                oldv=memory(p,p['dp'],t,m,TT);prow[f'memory_share_older_{int(TT)}s']=float(np.mean(oldv[m]*tot)/mse)
                prow[f'memory_rms_older_{int(TT)}s_deg']=math.degrees(float(np.sqrt(np.mean(oldv[m]**2))))
            T['PATH'].append(prow)
            # (3) kernel-based inflation, (5) WLS comparison
            K=kernels(p,ev);kers[nm]=K;g=p['H'][:,1,2];Rs=o['R'][:,1,1];acc=o['acc'];polc1=Hd[:,4:7].sum(1)
            for ti,(Wp,Wr) in K.items():
                age=t[ti]-t[:ti+1];aw=np.abs(Wp);S=aw.sum()
                rowk={'case':a.case,'route':Hr,'bias':bias,'arm':nm,'t':float(t[ti]),'sum_abs_Wpol':float(S),
                      'neg_weight_frac':float(aw[Wp<0].sum()/S) if S>0 else np.nan,'mean_age_s':float((aw*age).sum()/S) if S>0 else np.nan,
                      'frac_older_10s':float(aw[age>10].sum()/S) if S>0 else np.nan,'frac_older_30s':float(aw[age>30].sum()/S) if S>0 else np.nan,
                      'pol_signal_passthrough':float(np.sum(Wp*g[:ti+1])),'rec_pred_c1_deg':math.degrees(float(np.sum(Wp*p['c1'][:ti+1]))),
                      'pol_c1_component_deg':math.degrees(float(polc1[ti])),'heading_err_deg':math.degrees(float(p['dp'][ti,2]))}
                T['KERNEL'].append(rowk)
                for sig,W in (('pol_total',Wp),('range',Wr)):
                    for dtr in (None,10.):
                        r=rho[nm][(sig,dtr)][:len(W)]
                        T['FINF'].append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,'t':float(t[ti]),'signal':sig,'detrend_10s':dtr is not None,
                                          'F_full':finflate(W,r,False),'F_trunc':finflate(W,r,True)})
                for Tw in (10.,30.):
                    mk=(t[:ti+1]>t[ti]-Tw)&acc[:ti+1];den=float(np.sum(g[:ti+1][mk]**2/Rs[:ti+1][mk]))
                    Ww=np.zeros(ti+1)
                    if den>0:Ww[mk]=g[:ti+1][mk]/Rs[:ti+1][mk]/den
                    T['WLS'].append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,'t':float(t[ti]),'window_s':Tw,
                        'wls_sum_abs_W':float(np.abs(Ww).sum()),'wls_neg_frac':float(np.abs(Ww)[Ww<0].sum()/max(np.abs(Ww).sum(),1e-30)),
                        'wls_pred_c1_deg':math.degrees(float(np.sum(Ww*p['c1'][:ti+1]))),'rec_pred_c1_deg':rowk['rec_pred_c1_deg'],
                        'rec_sum_abs_W':rowk['sum_abs_Wpol'],'heading_err_deg':rowk['heading_err_deg'],
                        'corr_W_rec_vs_wls':float(np.corrcoef(Wp,Ww)[0,1]) if np.std(Ww)>0 and np.std(Wp)>0 else np.nan})
            idx=np.sort(rng.choice(np.arange(1,n),size=min(20,n-1),replace=False))
            T['FD'].append({'case':a.case,'bias':bias,'arm':nm,**fd_qa(model,case,o,controls,idx)})
        # (4) cross-propagation, all inputs and exogenous inputs only
        for nm in [x for x in pr if x!='BASE']:
            for In,Wt in ((nm,nm),(nm,'BASE'),('BASE',nm),('BASE','BASE')):
                Hd=own[In] if In==Wt else E2.propagate(pr[Wt],pr[In]);Y=Hd[m]
                T['CROSS'].append({'case':a.case,'route':Hr,'bias':bias,'arm':nm,'inputs':In,'weights':Wt,
                    'mse_all_deg2':D2*float(np.mean(Y.sum(1)**2)),'mse_exo_deg2':D2*float(np.mean(Y[:,EXO].sum(1)**2)),
                    'mse_pol_deg2':D2*float(np.mean(Y[:,POL].sum(1)**2)),'mse_pol_c1_deg2':D2*float(np.mean(Y[:,4:7].sum(1)**2))})
        np.savez_compressed(out/f'{stem}_EB3_ARRAYS.npz',t=t,truth=truth,hgt=hgt,z=z,fp=fp,ev=ev,
            **{f'{nm}__{k}':v for nm,p in pr.items() for k,v in p.items()},
            **{f'{nm}__{k}':res[nm][k] for nm in res for k in ('xp','xm','ehat','ehat_gt','P','Pp','R','nis','mu')},
            **{f'{nm}__Wpol':np.array([np.r_[kers[nm][ti][0],np.zeros(n-ti-1)] for ti in ev],dtype=np.float32) for nm in kers},
            **{f'{nm}__Wrng':np.array([np.r_[kers[nm][ti][1],np.zeros(n-ti-1)] for ti in ev],dtype=np.float32) for nm in kers})
        print(f'EB3_DONE {stem}',flush=True)
    for k,v in T.items():pd.DataFrame(v).to_csv(out/f'{a.case}_EB3_{k}.csv',index=False)
    (out/f'{a.case}_EB3_QA.json').write_text(json.dumps(qa,indent=2));print('EB3_CASE_PASS',flush=True)

if __name__=='__main__':main()
