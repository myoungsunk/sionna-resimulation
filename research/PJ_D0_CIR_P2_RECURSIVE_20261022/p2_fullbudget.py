#!/usr/bin/env python3
"""Full-state error budget v4 (15_FULL_STATE_BUDGET_PLAN_KO.md). Diagnostic only, GT used for decomposition.

P1  multi-seed position performance: radial / tangential (anchor frame of the true position) RMSE and bias,
    XY NEES (2 dof), XY / radial / tangential 95 % coverage, time windows and a 1 s time series.
P2  source-resolved full state error d+_k = sum_i D_i,k for x, y, psi, b_g, projected on heading, radial, tangential.
P3  heading -> position paths. (a) entry split: every injection is split by the state component it enters
    (position, heading, bias) and propagated with the same realized F, K, H. (b) increment accounting:
    dp_t = initial + sum F_p,psi dpsi+_{k-1} + sum F_p,b db+_{k-1} + sum (G w + r_pred)_p
           + sum -(K_r H_r d-)_p + sum -(K_s H_s d-)_p + sum (K eps + K r_meas)_p   (exact telescoping, F_pp = I)
P5  lag-binned influence kernel: c_b(t) = sum_{k: t-t_k in b} e_c' Phi(t,k) K_k eps_k for c in (psi, r, t),
    bins 0-10, 10-30, 30-60, >60 s, signed MSE contribution and cross terms.
Replays use p2_ebudget.replay (5 arms) with the Monte Carlo seed convention of p2_mc.py.
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
import r2_bias_replay as RB

SRC=E2.SRC
GROUPS={'initial':[0],'odom':[1],'gyro':[2],'range':[3],'pol':[4,5,6,7],'pol_c1':[4,5,6],'pol_c2':[7],'unexplained':[8,9]}
ENTRY=['pos','head','bias'];EMASK=np.array([[1,1,0,0],[0,0,1,0],[0,0,0,1]],float)
TERMS=['initial','head_coupling','bias_coupling','pred_input','corr_range','corr_pol','update_injection']
WINS={'w0_10':(0,10),'w10_30':(10,30),'w30_60':(30,60),'w60_90':(60,90),'w90_120':(90,120),'w120_180':(120,180),'w180_plus':(180,np.inf),
      'stable_30_plus':(30,np.inf)}
LAGB=[(0.,10.),(10.,30.),(30.,60.),(60.,np.inf)];LAGN=['lag0_10','lag10_30','lag30_60','lag60_plus']
COMP=['heading','radial','tangential']
CH95_1=3.841458820694124;CH95_2=5.991464547107979

def seed_of(i):return RB.SEED if i==0 else RB.SEED+7919*i

def anchor_frame(case,truth):
    anc=np.asarray(case['anchor'],float);ur=np.c_[truth[:,0]-anc[0],truth[:,1]-anc[1]];ur/=np.linalg.norm(ur,axis=1,keepdims=True)
    return anc,ur,np.c_[-ur[:,1],ur[:,0]]

def project(D,ur,ut):
    """(n,...,4) state errors -> (n,...,3) heading [rad], radial [m], tangential [m] with the frame of each time."""
    e=D[...,:2];sh=(len(D),)+(1,)*(D.ndim-2)+(2,)
    return np.stack([D[...,2],np.sum(e*ur.reshape(sh),-1),np.sum(e*ut.reshape(sh),-1)],-1)

def propagate_all(Wt,In):
    """One pass of the fixed-gain recursion returning
    Dfull (n,nsrc,4) source-resolved state error,
    Dent  (n,nsrc,3,4) the same split by entry component,
    Cinc  (n,nsrc,len(TERMS),2) cumulative position increments by term (telescoping)."""
    n=len(In['eps']);ns=len(SRC);I4=np.eye(4)
    D=np.zeros((ns,4));De=np.zeros((ns,3,4));cum=np.zeros((ns,len(TERMS),2))
    Dfull=np.zeros((n,ns,4));Dent=np.zeros((n,ns,3,4));Cinc=np.zeros((n,ns,len(TERMS),2))
    for k in range(n):
        if k==0:
            inj=np.zeros((ns,4));inj[0]=In['dm'][0];Dm=inj.copy();Dme=EMASK[None]*inj[:,None,:]
            cum[:,0]+=Dm[:,:2]
        else:
            F=Wt['F'][k];G=Wt['G'][k];inj=np.zeros((ns,4))
            inj[1]=G[:,0]*In['w'][k,0];inj[2]=G[:,1]*In['w'][k,1];inj[8]=In['r_pred'][k]
            Dm=D@F.T+inj;Dme=De@F.T+EMASK[None]*inj[:,None,:]
            cum[:,1]+=D[:,2:3]*F[:2,2][None];cum[:,2]+=D[:,3:4]*F[:2,3][None];cum[:,3]+=inj[:,:2]
        K=Wt['K'][k];H=Wt['H'][k];A=I4-K@H
        add=np.zeros((ns,4));add[3]=K[:,0]*In['eps'][k,0];add[4+In['lay'][k]]=K[:,1]*In['c1'][k];add[7]=K[:,1]*In['c2'][k];add[9]=K@In['r_meas'][k]
        cum[:,4]-=(Dm@H[0][:,None])*K[:2,0][None];cum[:,5]-=(Dm@H[1][:,None])*K[:2,1][None];cum[:,6]+=add[:,:2]
        D=Dm@A.T+add;De=Dme@A.T+EMASK[None]*add[:,None,:]
        Dfull[k]=D;Dent[k]=De;Cinc[k]=cum
    return Dfull,Dent,Cinc

def lag_kernels(Wt,t,ev,ur,ut,inputs):
    """Backward influence kernels for heading / radial / tangential at the evaluation indices ev, all at once.
    inputs: dict name -> (channel index 0 range / 1 pol, series). Returns contributions C[name] (E,3,nbin) and
    absolute weight mass Wm[ch] (E,3,nbin)."""
    n=len(t);E=len(ev);L=np.zeros((E,3,4));ar=np.arange(E);start={int(k):[] for k in ev}
    for e,k in enumerate(ev):start[int(k)].append(e)
    C={nm:np.zeros((E,3,len(LAGB))) for nm in inputs};Wm={ch:np.zeros((E,3,len(LAGB))) for ch in (0,1)}
    edges=np.array([b[0] for b in LAGB[1:]]);tev=t[ev]
    for k in range(n-1,-1,-1):
        for e in start.get(k,()):
            L[e]=0.;L[e,0,2]=1.;L[e,1,:2]=ur[ev[e]];L[e,2,:2]=ut[ev[e]]
        Wk=L@Wt['K'][k]                                       # (E,3,2); rows not yet started are 0
        bi=np.searchsorted(edges,np.maximum(tev-t[k],0.),side='right')
        for ch in (0,1):Wm[ch][ar,:,bi]+=np.abs(Wk[:,:,ch])
        for nm,(ch,x) in inputs.items():C[nm][ar,:,bi]+=Wk[:,:,ch]*x[k]
        if k>0:L=L@((np.eye(4)-Wt['K'][k]@Wt['H'][k])@Wt['F'][k])
    return C,Wm

def pos_metrics(X,Pp,acc,truth,ur,ut,anc,dz,t,b_true):
    e=X[:,:3]-truth[:,:3];e[:,2]=np.asarray(V.MC.wrap(e[:,2]))
    er=np.sum(e[:,:2]*ur,1);et=np.sum(e[:,:2]*ut,1);Pxy=Pp[:,:2,:2]
    s2r=np.einsum('ki,kij,kj->k',ur,Pxy,ur);s2t=np.einsum('ki,kij,kj->k',ut,Pxy,ut)
    nxy=np.einsum('ki,kij,kj->k',e[:,:2],np.linalg.inv(Pxy),e[:,:2]);nh=e[:,2]**2/Pp[:,2,2]
    dtrue=np.sqrt(np.sum((truth[:,:2]-anc[:2])**2,1)+dz**2);dhat=np.sqrt(np.sum((X[:,:2]-anc[:2])**2,1)+dz**2)
    return dict(eh=e[:,2],er=er,et=et,s2h=Pp[:,2,2],s2r=s2r,s2t=s2t,nxy=nxy,nh=nh,rng=dhat-dtrue,acc=acc,eb=X[:,3]-b_true)

def window_rows(base,M,t):
    rows=[]
    for wn,(a,b) in WINS.items():
        mk=(t>=a)&(t<b)
        if mk.sum()<5:continue
        g=lambda v:v[mk]
        rows.append({**base,'window':wn,'n':int(mk.sum()),
            'heading_rmse_deg':math.degrees(float(np.sqrt(np.mean(g(M['eh'])**2)))),'heading_bias_deg':math.degrees(float(g(M['eh']).mean())),
            'heading_nees':float(g(M['nh']).mean()),'heading_cov95':float(np.mean(g(M['nh'])<=CH95_1)),
            'xy_rmse_cm':100*float(np.sqrt(np.mean(g(M['er'])**2+g(M['et'])**2))),
            'radial_rmse_cm':100*float(np.sqrt(np.mean(g(M['er'])**2))),'radial_bias_cm':100*float(g(M['er']).mean()),
            'tangential_rmse_cm':100*float(np.sqrt(np.mean(g(M['et'])**2))),'tangential_bias_cm':100*float(g(M['et']).mean()),
            'range_err_rmse_cm':100*float(np.sqrt(np.mean(g(M['rng'])**2))),
            'xy_nees':float(g(M['nxy']).mean()),'xy_cov95':float(np.mean(g(M['nxy'])<=CH95_2)),
            'radial_nees':float(np.mean(g(M['er'])**2/g(M['s2r']))),'radial_cov95':float(np.mean(g(M['er'])**2/g(M['s2r'])<=CH95_1)),
            'tangential_nees':float(np.mean(g(M['et'])**2/g(M['s2t']))),'tangential_cov95':float(np.mean(g(M['et'])**2/g(M['s2t'])<=CH95_1)),
            'bias_rmse_dps':math.degrees(float(np.sqrt(np.mean(g(M['eb'])**2)))),'accept':float(g(M['acc']).mean())})
    return rows

def share_rows(base,Y,tot,mk):
    """Y (n,ngroups-like dict) components (n,3); tot (n,3). Signed MSE share, mean and RMS per component."""
    rows=[];mse=np.mean(tot[mk]**2,0);sc=np.array([math.degrees(1),100.,100.])
    tot_mse={'heading_total_mse_deg2':float(mse[0]*sc[0]**2),'radial_total_mse_cm2':float(mse[1]*1e4),'tangential_total_mse_cm2':float(mse[2]*1e4)}
    for nm,y in Y.items():
        yy=y[mk];r={**base,**tot_mse,'part':nm}
        for c,cn in enumerate(COMP):
            r[f'{cn}_share']=float(np.mean(yy[:,c]*tot[mk][:,c])/mse[c]) if mse[c]>0 else np.nan
            r[f'{cn}_mean']=float(sc[c]*yy[:,c].mean());r[f'{cn}_rms']=float(sc[c]*np.sqrt(np.mean(yy[:,c]**2)))
        rows.append(r)
    return rows

def analyse(case,res,pr,t,truth,ur,ut,anc,dz,b_true,base0,want_kernels=True):
    T={k:[] for k in ('POS','TS','SHARE','ENTRY','INC','LAG','LAGX')};qa={}
    m=t>=30;ev=np.where(m)[0][::10];step=max(1,int(round(1./float(np.median(np.diff(t))))))
    for nm,p in pr.items():
        o=res[nm];base={**base0,'arm':nm}
        M=pos_metrics(o['xp'],o['Pp'],o['acc'],truth,ur,ut,anc,dz,t,b_true);T['POS']+=window_rows(base,M,t)
        ts=np.arange(0,len(t),step)
        T['TS']+=[{**base,'t':float(t[k]),'eh_deg':math.degrees(M['eh'][k]),'er_cm':100*M['er'][k],'et_cm':100*M['et'][k],
                   'sh_deg':math.degrees(math.sqrt(M['s2h'][k])),'sr_cm':100*math.sqrt(M['s2r'][k]),'st_cm':100*math.sqrt(M['s2t'][k]),
                   'acc_1s':float(o['acc'][k:k+step].mean())} for k in ts]
        Dfull,Dent,Cinc=propagate_all(p,p);tot=project(p['dp'],ur,ut)
        clo=float(np.max(np.abs(Dfull.sum(1)-p['dp'])));clo_e=float(np.max(np.abs(Dent.sum(2)-Dfull)))
        clo_i=float(np.max(np.abs(Cinc.sum(2)-Dfull[...,:2])));qa[f'{nm}']={'closure':clo,'closure_entry':clo_e,'closure_increment':clo_i}
        tol=1e-9*max(1.,float(np.max(np.abs(p['dp']))));assert max(clo,clo_e,clo_i)<tol,('FB_CLOSURE_FAIL',nm,clo,clo_e,clo_i)
        Pj=project(Dfull,ur,ut)                                      # (n,nsrc,3)
        Y={g:Pj[:,ix].sum(1) for g,ix in GROUPS.items()}
        T['SHARE']+=share_rows(base,Y,tot,m)
        Pe=project(Dent,ur,ut)                                       # (n,nsrc,3entry,3)
        Ye={f'{g}|{en}':Pe[:,ix,j].sum(1) for g,ix in GROUPS.items() if g in ('initial','odom','gyro','range','pol','unexplained') for j,en in enumerate(ENTRY)}
        T['ENTRY']+=share_rows(base,Ye,tot,m)
        Ci=np.stack([Cinc[...,0]*ur[:,0,None,None]+Cinc[...,1]*ur[:,1,None,None],
                     Cinc[...,0]*ut[:,0,None,None]+Cinc[...,1]*ut[:,1,None,None]],-1)      # (n,nsrc,nterm,2) radial, tangential
        Yi={}
        for g in ('initial','odom','gyro','range','pol','unexplained','ALL'):
            ix=list(range(len(SRC))) if g=='ALL' else GROUPS[g]
            for j,tn in enumerate(TERMS):
                v=Ci[:,ix,j].sum(1);Yi[f'{g}|{tn}']=np.c_[np.zeros(len(t)),v]
        T['INC']+=[{k:v for k,v in r.items() if not k.startswith('heading')} for r in share_rows(base,Yi,tot,m)]
        if want_kernels:
            ins={'pol':(1,p['eps'][:,1]),'pol_c1':(1,p['c1']),'range':(0,p['eps'][:,0])}
            C,Wm=lag_kernels(p,t,ev,ur,ut,ins)
            ker_pol=C['pol'].sum(2);ref=Pj[ev][:,4:8].sum(1);kq=float(np.max(np.abs(ker_pol-ref)))
            ker_rng=C['range'].sum(2);kqr=float(np.max(np.abs(ker_rng-Pj[ev][:,3])));qa[nm].update({'kernel_vs_propagate_pol':kq,'kernel_vs_propagate_range':kqr})
            assert max(kq,kqr)<tol,('FB_KERNEL_FAIL',nm,kq,kqr)
            te=tot[ev]
            for inp,Cx in C.items():
                for c,cn in enumerate(COMP):
                    cb=Cx[:,c,:];cs=cb.sum(1);e2=float(np.mean(te[:,c]**2));c2=float(np.mean(cs**2))
                    ch=0 if inp=='range' else 1;wm=Wm[ch][:,c,:];wms=wm.sum(1)
                    for b,bn in enumerate(LAGN):
                        T['LAG'].append({**base,'input':inp,'component':cn,'lag_bin':bn,
                            'share_of_input_part':float(np.mean(cb[:,b]*cs)/c2) if c2>0 else np.nan,
                            'share_of_total_mse':float(np.mean(cb[:,b]*te[:,c])/e2) if e2>0 else np.nan,
                            'rms':float(np.sqrt(np.mean(cb[:,b]**2)))*(math.degrees(1) if c==0 else 100.),
                            'abs_weight_frac':float(np.median(wm[:,b]/np.maximum(wms,1e-300)))})
                        for b2,bn2 in enumerate(LAGN):
                            T['LAGX'].append({**base,'input':inp,'component':cn,'bin_i':bn,'bin_j':bn2,
                                              'cross_over_input_mse':float(np.mean(cb[:,b]*cb[:,b2])/c2) if c2>0 else np.nan})
    return T,qa

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--l4models',required=True)
    ap.add_argument('--seeds',required=True);ap.add_argument('--out',required=True);ap.add_argument('--no-kernels',action='store_true');a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case);Hr=case['route']
    l4=joblib.load(a.l4models);assert l4['held']==Hr and Hr not in l4['train_routes']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);idx=[int(x) for x in a.seeds.split(',')]
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz');pk=pk[pk.case==a.case].sort_values('pose_id')
    mc=pd.read_csv(HERE/'results_eb2_mc/MC_ALL.csv');ref4=pd.read_csv(HERE/'results_ladder4/LADDER4_SCORES.csv')
    refmap={'CIR':'L_CIR','WIDE_NOES':'L_WIDE_NOES'}
    model=V.SourceFFD();T={};qa={'case':a.case,'seeds':{i:seed_of(i) for i in idx},'parity':{},'closure':{}}
    for bias in ('B0','L2'):
        stem=f'{a.case}_full_{bias}';old=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)
        t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only'];n=len(t)
        d=obs[(obs.case==a.case)&(obs.channel=='full')].set_index('pose_id').loc[ids];z=d[['range_m','s_fp']].to_numpy(float)
        features,_=R2.full_features(pk,ids);mu0,R0=V.base_params(param,a.case,'full',ids,'POWER_DIAG')
        P_=pk.set_index('pose_id').loc[ids];sL=P_['sL_+0'].to_numpy();fp=P_['fp_shift_tap'].to_numpy(float)
        hgt=np.concatenate([model.batch(np.c_[truth[i:i+32,:3],np.zeros(len(truth[i:i+32]))],case,gradient=True)[0] for i in range(0,n,32)])
        ds_true,dth_true=RB.motion_increments(t,truth,convention='legacy-euler');b_true=math.radians(V.BIAS_LEVELS[bias])
        anc,ur,ut=anchor_frame(case,truth);dz=float(anc[2]-float(case['robot_z_m']))
        for i in idx:
            controls,x0r=V.build_positive_bias_controls(t,truth,bias,seed=seed_of(i))
            x0=np.r_[x0r,0.];P0=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
            res=EB.replay(model,case,controls,x0,P0,z,features,l4,mu0,R0,sL,hgt)
            pr={nm:E2.prep(o,z,hgt,truth,controls,b_true,np.asarray(ds_true),np.asarray(dth_true),fp) for nm,o in res.items()}
            base0={'case':a.case,'route':Hr,'bias':bias,'seed_idx':i,'seed':seed_of(i),
                   'init_heading_err_deg':math.degrees(float(V.MC.wrap(x0r[2]-truth[0,2])))}
            Ti,qi=analyse(case,res,pr,t,truth,ur,ut,anc,dz,b_true,base0,want_kernels=not a.no_kernels)
            for k,v in Ti.items():T.setdefault(k,[]).extend(v)
            qa['closure'][f'{stem}:{i}']=qi
            # parity: BASE / PWIDE_NOES / ORACLE against the v2 Monte Carlo, CIR / WIDE_NOES (seed 0) against ladder 4
            for arm in ('BASE','PWIDE_NOES','ORACLE'):
                r=next(x for x in Ti['POS'] if x['arm']==arm and x['window']=='stable_30_plus')
                rr=mc[(mc.case==a.case)&(mc.bias==bias)&(mc.seed_idx==i)&(mc.arm==arm)].iloc[0]
                ph=abs(r['heading_rmse_deg']-rr.stable_30_plus_heading_rmse_deg);px=abs(r['xy_rmse_cm']-rr.stable_30_plus_xy_rmse_cm)
                qa['parity'][f'{stem}:{i}:{arm}']=[ph,px];assert ph<1e-6 and px<1e-6,('FB_PARITY_FAIL',stem,i,arm,ph,px)
            if i==0:
                for arm,ra in refmap.items():
                    r=next(x for x in Ti['POS'] if x['arm']==arm and x['window']=='stable_30_plus')
                    rr=ref4[(ref4.case==a.case)&(ref4.bias==bias)&(ref4.channel=='full')&(ref4.arm==ra)].iloc[0]
                    ph=abs(r['heading_rmse_deg']-float(rr.heading_rmse_deg));qa['parity'][f'{stem}:0:{arm}']=[ph]
                    assert ph<1e-6,('FB_PARITY_FAIL',stem,arm,ph)
            print(f'FB_DONE {stem} seed_idx={i}',flush=True)
    tag='_'.join(map(str,idx))
    for k,v in T.items():pd.DataFrame(v).to_csv(out/f'{a.case}_FB_{k}_{tag}.csv.gz',index=False)
    (out/f'{a.case}_FB_QA_{tag}.json').write_text(json.dumps(qa,indent=2,default=float));print('FB_CASE_PASS',flush=True)

if __name__=='__main__':main()
