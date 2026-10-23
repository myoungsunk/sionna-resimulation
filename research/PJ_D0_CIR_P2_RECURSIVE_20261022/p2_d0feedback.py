#!/usr/bin/env python3
"""P4: d0 prior sensitivity and recursive feedback (15_FULL_STATE_BUDGET_PLAN_KO.md). Diagnostic only.

A. Innovation curve around the true state (seed independent). For a perturbed state x = x_GT + delta
   (heading grid +-10 deg, tangential grid +-0.3 m) the polarization innovation of each arm is
     nu(delta) = s_F - ehat(CIR, d0(delta)) - mu_s - h_s(x),  d0(delta) = s_F - h_s(x)
   BASE: ehat = 0. PWIDE (P_D0, mu POWER), WIDE (W_D0, mu 0): ehat depends on d0. ORACLE: ehat = s_F - s_L, mu 0.
   kappa_phys(delta) = -(nu(delta)-nu(0)) / (g delta), g the analytic slope at x_GT (tangent).
   kappa_rel(delta) = (nu(delta)-nu(0)) / (nu_BASE(delta)-nu_BASE(0)) = 1 - d ehat / d d0 (finite difference).
   kappa <= 0: the corrected innovation no longer restores the perturbation (or reverses it).
B. Paired replays (same RF, same motion noise of a seed) with an initial heading offset added to x0, P0 unchanged.
   Arms: BASE, PWIDE_CL (as deployed, d0 from its own prior), PWIDE_OB (d0 from the BASE prior of the same run:
   corrector without self feedback), PWIDE_GT (d0 from the true state, GT leakage, diagnostic only), ORACLE.
   Output: window scores, gate decision change and corrector output change vs the zero offset, local kappa_rel
   along the PWIDE_CL prior, 1 s time series.
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
import r2_bias_replay as RB
import warnings
warnings.filterwarnings('ignore',message='X does not have valid feature names')

ARMS=['BASE','PWIDE_CL','PWIDE_OB','PWIDE_GT','ORACLE']
WIN={'w0_10':(0,10),'w10_30':(10,30),'w30_60':(30,60),'w60_plus':(60,np.inf),'stable_30_plus':(30,np.inf)}
DPSI=np.round(np.r_[-10:10.001:0.5],3);DTAN=np.round(np.r_[-0.3:0.3001:0.025],4)
CH95_1=3.841458820694124
def seed_of(i):return RB.SEED if i==0 else RB.SEED+7919*i

def hs_batch(model,case,X,chunk=64):
    return np.concatenate([model.batch(X[i:i+chunk],case,gradient=False)[0][:,1] for i in range(0,len(X),chunk)])

def curve(model,case,truth,z,Xf_p,Xf_w,mdlP,mdlW,mu_s,R_s,sL,Hgt,ur,ut,fr):
    """Innovation curves on the heading and tangential grids around the true state at frames fr."""
    rows=[];arrays={}
    for kind,grid,unit in (('heading',DPSI,math.radians(1.)),('tangential',DTAN,1.)):
        G=len(grid);i0=int(np.where(grid==0)[0][0]);Xg=np.repeat(np.c_[truth[fr,:3],np.zeros(len(fr))],G,0)
        dl=np.tile(grid*unit,len(fr))
        if kind=='heading':Xg[:,2]+=dl;g=Hgt[fr,1,2]
        else:Xg[:,:2]+=dl[:,None]*np.repeat(ut[fr],G,0);g=np.sum(Hgt[fr,1,:2]*ut[fr],1)
        hs=hs_batch(model,case,Xg).reshape(len(fr),G);zs=z[fr,1][:,None];d0=zs-hs
        eP=mdlP.predict(np.c_[np.repeat(Xf_p[fr],G,0),d0.ravel()]).reshape(len(fr),G)
        eW=mdlW.predict(np.c_[np.repeat(Xf_w[fr],G,0),d0.ravel()]).reshape(len(fr),G)
        nu={'BASE':zs-mu_s[fr][:,None]-hs,'PWIDE':zs-eP-mu_s[fr][:,None]-hs,'WIDE':zs-eW-hs,'ORACLE':sL[fr][:,None]-hs}
        ehat={'PWIDE':eP,'WIDE':eW}
        arrays[kind]={'grid':grid,'hs':hs,'d0':d0,'eP':eP,'eW':eW,'g':g}
        w=g**2/R_s[fr];dB=nu['BASE']-nu['BASE'][:,[i0]];np.seterr(divide='ignore',invalid='ignore')
        for arm,v in nu.items():
            dv=v-v[:,[i0]]
            # zero crossings of nu over the grid and the root nearest to 0
            sgn=np.sign(v);nroot=np.sum(sgn[:,1:]*sgn[:,:-1]<0,1)
            roots=np.full(len(fr),np.nan)
            for f in range(len(fr)):
                ix=np.where(sgn[f,1:]*sgn[f,:-1]<0)[0]
                if len(ix):
                    rr=grid[ix]-v[f,ix]*(grid[ix+1]-grid[ix])/(v[f,ix+1]-v[f,ix]);roots[f]=rr[np.argmin(np.abs(rr))]
            near=np.abs(grid)<=(2. if kind=='heading' else 0.05)
            jump_e=np.max(np.abs(np.diff(ehat[arm][:,near],axis=1)),1) if arm in ehat else np.zeros(len(fr))
            jump_h=np.max(np.abs(np.diff(hs[:,near],axis=1)),1)
            for j,dlt in enumerate(grid):
                if j==i0:continue
                kp=-dv[:,j]/(g*dlt*unit);kr=dv[:,j]/np.where(np.abs(dB[:,j])>1e-12,dB[:,j],np.nan)
                rows.append({'kind':kind,'arm':arm,'delta':float(dlt),'n_frames':len(fr),
                    'kappa_phys_median':float(np.nanmedian(kp)),'kappa_phys_infoweighted':float(np.nansum(w*kp)/np.sum(w[np.isfinite(kp)])),
                    'frac_kappa_phys_le0':float(np.mean(kp<=0)),'frac_kappa_phys_0_05':float(np.mean((kp>0)&(kp<.5))),
                    'kappa_rel_median':float(np.nanmedian(kr)),'kappa_rel_mean':float(np.nanmean(kr)),
                    'kappa_rel_p10':float(np.nanquantile(kr,.1)),'kappa_rel_p90':float(np.nanquantile(kr,.9)),'kappa_rel_infoweighted':float(np.nansum(w*kr)/np.sum(w[np.isfinite(kr)])),
                    'frac_kappa_rel_le0':float(np.nanmean(kr<=0)),'frac_kappa_rel_0_05':float(np.nanmean((kr>0)&(kr<.5))),
                    'root_abs_median':float(np.nanmedian(np.abs(roots))),'frac_no_root':float(np.mean(~np.isfinite(roots))),
                    'frac_multi_root':float(np.mean(nroot>=2)),'ehat_jump_near_median':float(np.median(jump_e)),
                    'ehat_jump_near_p95':float(np.quantile(jump_e,.95)),'hs_jump_near_median':float(np.median(jump_h)),
                    'hs_jump_near_p95':float(np.quantile(jump_h,.95))})
    return rows,arrays

def run(model,case,controls,x0,P0,z,Xf,mdl,mu0,R0,sL,egt):
    n=len(z);J=len(ARMS);X=np.zeros((n,J,4));Xm=np.zeros((n,J,4));C=np.zeros((n,J,4,4));acc=np.zeros((n,J),bool)
    E=np.zeros((n,J));D0=np.full((n,J),np.nan);xs=np.repeat(x0[None],J,0);Ps=np.repeat(P0[None],J,0);rows=np.zeros((2,Xf.shape[1]+1))
    for k in range(n):
        if k:
            for j in range(J):
                xs[j],Ps[j]=V.predict_one(xs[j],Ps[j],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=model.batch(xs,case,gradient=True);Xm[k]=xs
        rows[:,:-1]=Xf[k];rows[0,-1]=z[k,1]-h[1,1];rows[1,-1]=z[k,1]-h[0,1];ecl,eob=mdl.predict(rows)
        D0[k,1]=rows[0,-1];D0[k,2]=rows[1,-1]
        for j,arm in enumerate(ARMS):
            mu=mu0[k].copy()
            if arm=='BASE':e=0.
            elif arm=='PWIDE_CL':e=float(ecl)
            elif arm=='PWIDE_OB':e=float(eob)
            elif arm=='PWIDE_GT':e=float(egt[k])
            else:e=float(z[k,1]-sL[k]);mu[1]=0.
            zk=z[k].copy();zk[1]-=e;r=R0[k];E[k,j]=e
            xo,Po,nis,yes=S.update(xs[j][None],Ps[j][None],zk,h[j][None],H[j][None],mu[None],mu[None],r[None],r[None],np.array([False]))
            xs[j],Ps[j]=xo[0],Po[0];acc[k,j]=bool(yes[0])
            if not(np.isfinite(xs[j]).all() and np.isfinite(Ps[j]).all()):raise FloatingPointError(arm)
            X[k,j]=xs[j];C[k,j]=Ps[j]
    return X,Xm,C,acc,E,D0

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--l4models',required=True)
    ap.add_argument('--bias',required=True);ap.add_argument('--seeds',default='0,3,5,7,8');ap.add_argument('--offsets',default='-10,-5,-2,0,2,5,10')
    ap.add_argument('--curve',action='store_true');ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    l4=joblib.load(a.l4models);assert l4['held']==Hr and Hr not in l4['train_routes']
    mdl=l4['models']['P_D0'];medP=l4['medians']['P_D0'];mdlW=l4['models']['W_D0'];medW=l4['medians']['W_D0']
    assert list(mdl.feature_names_in_)[-1]=='d0' and list(mdlW.feature_names_in_)[-1]=='d0'
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);seeds=[int(x) for x in a.seeds.split(',')];offs=[float(x) for x in a.offsets.split(',')]
    assert 0. in offs
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz');pk=pk[pk.case==a.case].sort_values('pose_id')
    mc=pd.read_csv(HERE/'results_eb2_mc/MC_ALL.csv');model=V.SourceFFD()
    bias=a.bias;stem=f'{a.case}_full_{bias}';old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
    t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only'];n=len(t)
    d=obs[(obs.case==a.case)&(obs.channel=='full')].set_index('pose_id').loc[ids];z=d[['range_m','s_fp']].to_numpy(float)
    features,_=R2.full_features(pk,ids);mu0,R0=V.base_params(param,a.case,'full',ids,'POWER_DIAG')
    Xf=R2.m_inputs(features,medP)[list(mdl.feature_names_in_)[:-1]].to_numpy(float)
    Xfw=R2.m_inputs(features,medW)[list(mdlW.feature_names_in_)[:-1]].to_numpy(float)
    sL=pk.set_index('pose_id').loc[ids]['sL_+0'].to_numpy()
    hres=[model.batch(np.c_[truth[i:i+32,:3],np.zeros(len(truth[i:i+32]))],case,gradient=True) for i in range(0,n,32)]
    hgt=np.concatenate([r[0] for r in hres]);Hgt=np.concatenate([r[1] for r in hres])
    egt=mdl.predict(np.c_[Xf,z[:,1]-hgt[:,1]])
    anc=np.asarray(case['anchor'],float);ur=np.c_[truth[:,0]-anc[0],truth[:,1]-anc[1]];ur/=np.linalg.norm(ur,axis=1,keepdims=True);ut=np.c_[-ur[:,1],ur[:,0]]
    qa={'case':a.case,'bias':bias,'seeds':{i:seed_of(i) for i in seeds},'offsets_deg':offs,'P0_heading_sd_deg':math.degrees(float(V.INITIAL_POSE_STD[2])),'parity':{}}
    if a.curve:
        fr=np.arange(0,n,4);cr,arr=curve(model,case,truth,z,Xf,Xfw,mdl,mdlW,mu0[:,1],R0[:,1,1],sL,Hgt,ur,ut,fr)
        pd.DataFrame([{'case':a.case,'route':Hr,**r} for r in cr]).to_csv(out/f'{a.case}_D0FB_CURVE.csv',index=False)
        np.savez_compressed(out/f'{a.case}_D0FB_CURVE_ARRAYS.npz',frames=fr,t=t[fr],**{f'{k}__{q}':v for k,dd in arr.items() for q,v in dd.items()})
        print('D0FB_CURVE_DONE',flush=True)
    P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]);b_true=math.radians(V.BIAS_LEVELS[bias])
    rows=[];ts=[];loc=[];step=max(1,int(round(1./float(np.median(np.diff(t))))))
    for i in seeds:
        controls,x0r=V.build_positive_bias_controls(t,truth,bias,seed=seed_of(i));ref={}
        for off in sorted(offs,key=lambda v:(v!=0.,v)):
            x0=np.r_[x0r,0.];x0[2]=float(V.MC.wrap(x0[2]+math.radians(off)))
            X,Xm,C,acc,E,D0=run(model,case,controls,x0,P0,z,Xf,mdl,mu0,R0,sL,egt)
            if off==0.:ref=dict(acc=acc,E=E,D0=D0)
            init=math.degrees(float(V.MC.wrap(x0[2]-truth[0,2])))
            for j,arm in enumerate(ARMS):
                he=np.degrees(np.asarray(V.MC.wrap(X[:,j,2]-truth[:,2])));sg=np.degrees(np.sqrt(C[:,j,2,2]))
                ex=X[:,j,:2]-truth[:,:2];et=np.sum(ex*ut,1)*100;er=np.sum(ex*ur,1)*100
                base={'case':a.case,'route':Hr,'bias':bias,'seed_idx':i,'seed':seed_of(i),'offset_deg':off,'init_heading_err_deg':init,'arm':arm}
                last=t>=t[-1]-10
                for wn,(t0,t1) in WIN.items():
                    mk=(t>=t0)&(t<t1)
                    if mk.sum()<5:continue
                    r={**base,'window':wn,'heading_rmse_deg':float(np.sqrt(np.mean(he[mk]**2))),'heading_bias_deg':float(he[mk].mean()),
                       'heading_nees':float(np.mean((he[mk]/sg[mk])**2)),'heading_cov95':float(np.mean((he[mk]/sg[mk])**2<=CH95_1)),
                       'xy_rmse_cm':float(np.sqrt(np.mean(et[mk]**2+er[mk]**2))),'tangential_rmse_cm':float(np.sqrt(np.mean(et[mk]**2))),
                       'radial_rmse_cm':float(np.sqrt(np.mean(er[mk]**2))),'accept':float(acc[mk,j].mean()),
                       'final10_heading_mean_deg':float(he[last].mean()),'gate_change_frac':float(np.mean(acc[mk,j]!=ref['acc'][mk,j]))}
                    if arm in ('PWIDE_CL','PWIDE_OB'):
                        de=np.abs(E[mk,j]-ref['E'][mk,j]);dd=np.abs(D0[mk,j]-ref['D0'][mk,j])
                        r.update({'ehat_change_median':float(np.median(de)),'ehat_change_p95':float(np.quantile(de,.95)),'ehat_change_max':float(de.max()),
                                  'd0_change_median':float(np.median(dd)),'d0_change_p95':float(np.quantile(dd,.95)),
                                  'ehat_over_d0_change':float(de.sum()/max(dd.sum(),1e-300))})
                    rows.append(r)
                for k in range(0,n,step):
                    ts.append({**base,'t':float(t[k]),'eh_deg':float(he[k]),'sh_deg':float(sg[k]),'et_cm':float(et[k]),'ehat':float(E[k,j]),
                               'd0':float(D0[k,j]) if np.isfinite(D0[k,j]) else np.nan,'acc_1s':float(acc[k:k+step,j].mean())})
                if off==0. and arm in ('BASE','PWIDE_CL','ORACLE'):
                    mk=t>=30;rmse=float(np.sqrt(np.mean(he[mk]**2)));xy=float(np.sqrt(np.mean(et[mk]**2+er[mk]**2)))
                    rr=mc[(mc.case==a.case)&(mc.bias==bias)&(mc.seed_idx==i)&(mc.arm==('PWIDE_NOES' if arm=='PWIDE_CL' else arm))].iloc[0]
                    p=[abs(rmse-rr.stable_30_plus_heading_rmse_deg),abs(xy-rr.stable_30_plus_xy_rmse_cm)];qa['parity'][f'{i}:{arm}']=p
                    assert max(p)<1e-6,('D0FB_PARITY_FAIL',i,arm,p)
            # local kappa_rel along the prior of PWIDE_CL and BASE (corrector absorption at the operating point)
            for j,arm in (((0,'BASE_prior'),(1,'PWIDE_CL_prior')) if off in (0.,-5.,5.) else ()):
                fr=np.arange(0,n,4);x=Xm[fr,j];hp=hs_batch(model,case,x)
                for dlt in (-2.,-1.,1.,2.):
                    xx=x.copy();xx[:,2]+=math.radians(dlt);hq=hs_batch(model,case,xx)
                    d0a=z[fr,1]-hp;d0b=z[fr,1]-hq;ea=mdl.predict(np.c_[Xf[fr],d0a]);eb=mdl.predict(np.c_[Xf[fr],d0b])
                    dB=-(hq-hp);kr=(dB-(eb-ea))/np.where(np.abs(dB)>1e-12,dB,np.nan)
                    for wn,(t0,t1) in WIN.items():
                        mk=(t[fr]>=t0)&(t[fr]<t1)
                        if mk.sum()<3:continue
                        loc.append({'case':a.case,'bias':bias,'seed_idx':i,'offset_deg':off,'around':arm,'delta_deg':dlt,'window':wn,
                                    'kappa_rel_median':float(np.nanmedian(kr[mk])),'kappa_rel_mean':float(np.nanmean(kr[mk])),
                                    'kappa_rel_p10':float(np.nanquantile(kr[mk],.1)),'frac_kappa_rel_le0':float(np.nanmean(kr[mk]<=0)),
                                    'frac_kappa_rel_0_05':float(np.nanmean((kr[mk]>0)&(kr[mk]<.5)))})
            print(f'D0FB_DONE {stem} seed_idx={i} offset={off}',flush=True)
    pd.DataFrame(rows).to_csv(out/f'{stem}_D0FB_PAIRED.csv',index=False);pd.DataFrame(ts).to_csv(out/f'{stem}_D0FB_TS.csv.gz',index=False)
    pd.DataFrame(loc).to_csv(out/f'{stem}_D0FB_LOCAL.csv',index=False)
    (out/f'{stem}_D0FB_QA.json').write_text(json.dumps(qa,indent=2,default=float));print('D0FB_PASS '+json.dumps(qa['parity'],default=float),flush=True)

if __name__=='__main__':main()
