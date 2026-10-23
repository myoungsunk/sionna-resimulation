#!/usr/bin/env python3
"""System-level verification, stage 3 (16_SYSTEM_VERIFICATION_PLAN_KO.md). Offline, no filter.

V5  Inside the two training routes of a held route H (inner LORO, A -> B): residuals of
      BASE  : delta = e - mu_inner                    (mu_inner = strict inner POWER, as p2_l4train)
      WD0   : e - What   (target e, CIR + d0)
      PX1   : delta - Dhat (target delta, CIR only)
      PD0   : delta - Dhat (target delta, CIR + d0; = the deployed P_D0 recipe)
      PA2   : delta - Dhat_s (target = 30 s moving average of delta along each case trajectory, CIR + d0)
    evaluated with d0 at the true state, and their heading-equivalent bias along B's trajectories
      b_psi(T) = sum_{window T} g eps / R / sum g^2 / R       (g = true-state slope from the P1R grid, R = V_inner)
    -> does a training-route-only statistic rank the held-route recursion (C1), and does a window target help (A2)?
X1  On the held route itself (diagnostic, uses held labels): the deployed model, an in-sample model (train = test)
    and a 2-fold time-block model within H. In-sample failure to reduce b_psi = no information in the features.
QA  The deployed P_D0 is retrained from the same rows / seeds and must reproduce the saved model's predictions.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1];sys.path.insert(0,str(HERE))
import p2_l4train as L4                       # rows(), mk(), and the P1R / strict_common imports
from p2_l4train import P, S, V
DEG=180/math.pi;WINDOWS=[10.,30.,60.,120.]

def case_times(cases):
    out={}
    for c in cases:
        z=np.load(V.one(f'{c}_full_B0_TRACE.npz'),allow_pickle=False);out[c]=pd.Series(z['t_s'],index=z['pose_id'].astype(int))
    return out

def smooth_by_case(df,col,T,times):
    s=np.empty(len(df))
    for c,g in df.groupby('case'):
        tt=times[c].loc[g.pose_id.to_numpy()].to_numpy();o=np.argsort(tt);dt=float(np.median(np.diff(tt[o])));w=max(1,int(round(T/dt)))
        v=pd.Series(g[col].to_numpy()[o]).rolling(w,center=True,min_periods=1).mean().to_numpy();r=np.empty(len(g));r[o]=v
        s[np.flatnonzero(df.index.isin(g.index))]=r          # df has a RangeIndex aligned with positions
    return s

def bpsi_stats(t,g,eps,R,step=5.):
    """Heading-equivalent bias over sliding windows (all packets), RMS and mean in degrees."""
    o=np.argsort(t);t,g,eps,R=t[o],g[o],eps[o],R[o];out={}
    for T in WINDOWS:
        vals=[]
        for t0 in np.arange(t[0],t[-1]-T+1e-9,step):
            m=(t>=t0)&(t<t0+T);den=float(np.sum(g[m]**2/R[m]))
            if m.sum()>=5 and den>0:vals.append(float(np.sum(g[m]*eps[m]/R[m]))/den)
        v=np.array(vals);out[f'bpsi_{int(T)}s_rms_deg']=DEG*float(np.sqrt(np.mean(v**2))) if len(v) else np.nan
        out[f'bpsi_{int(T)}s_mean_deg']=DEG*float(v.mean()) if len(v) else np.nan
    m30=pd.Series(eps).rolling(max(1,int(round(30/float(np.median(np.diff(t)))))),center=True,min_periods=1).mean().to_numpy()
    out['packet_rms']=float(np.sqrt(np.mean(eps**2)));out['slow30_rms']=float(np.sqrt(np.mean(m30**2)));out['mean']=float(eps.mean())
    return out

def d0_gt(df,grid):
    s0,_=grid.node(df.index.to_numpy(),0.);return df['sF_+0'].to_numpy()-s0

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--held',required=True,choices=['R2','R4','R5']);ap.add_argument('--grid',required=True)
    ap.add_argument('--l4models',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    H=a.held;out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    D=P.prepare();grid=P.load_grid(D,a.grid);obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'));l4=joblib.load(a.l4models);assert l4['held']==H
    trr=sorted(set(D.route)-{H});assert H not in trr and len(trr)==2
    times=case_times(sorted(D.case.unique()))
    s0,g0=grid.node(np.arange(len(D)),0.);sp,_=grid.node(np.arange(len(D)),1.);sm,_=grid.node(np.arange(len(D)),-1.)
    D['g_gt_rad']=g0*DEG;D['t']=[float(times[c].loc[p]) for c,p in zip(D.case,D.pose_id)]
    qa={'held':H,'train_routes':trr,'grid_plus1_vs_stored':float(np.max(np.abs(sp-D['sMGTp1_+0'].to_numpy()))) if 'sMGTp1_+0' in D else np.nan,
        'grid_slope_vs_central_diff_rel':float(np.median(np.abs(g0-(sp-sm)/2)/np.maximum(np.abs(g0),1e-9)))}
    # strict inner POWER for the training routes (exactly as p2_l4train)
    D['mu_in']=np.nan;D['V_in']=np.nan
    for r in trr:
        other=[x for x in trr if x!=r];pin=S.power_fit(obs,other,r);pin=pin[pin.channel=='full'].set_index(['case','pose_id'])
        m=D.route==r;key=list(zip(D.case[m],D.pose_id[m]))
        D.loc[m,'mu_in']=pin.loc[key,'mu_s'].to_numpy(float);D.loc[m,'V_in']=pin.loc[key,'Vs'].to_numpy(float)
    tr=D[D.route!=H].copy();tr['delta']=tr.e_true-tr.mu_in
    # QA: the deployed P_D0 retrained from identical rows and seeds reproduces the saved model on the held route
    x,y,med=L4.rows(tr,'delta',grid,'D0',P.SEED[H]*1000+17,P.SEED[H]*7919+2);mq=L4.mk().fit(x,y)
    he=D[D.route==H].copy();xa=P.feats(he,l4['medians']['P_D0']);xa['d0']=d0_gt(he,grid);xb=P.feats(he,med);xb['d0']=xa['d0'].to_numpy()
    qa['retrain_parity_P_D0']=float(np.max(np.abs(mq.predict(xb)-l4['models']['P_D0'].predict(xa))))
    rows=[]
    def emit(scope,fit_on,eval_on,arm,df,resid,R,flags):
        for c,g in df.assign(_r=resid,_R=R).groupby('case'):
            st=bpsi_stats(g.t.to_numpy(),g.g_gt_rad.to_numpy(),g._r.to_numpy(),g._R.to_numpy())
            rows.append({'held':H,'scope':scope,'fit_routes':fit_on,'eval_route':eval_on,'case':c,'arm':arm,**flags,**st})
    # ---------------- V5 inner LORO inside the training routes
    for r in trr:
        A=tr[tr.route!=r].copy();B=tr[tr.route==r].copy();sd=P.SEED[H]*1000+100*int(r[1:])
        A['delta_s30']=smooth_by_case(A.reset_index(drop=True),'delta',30.,times)
        dB=d0_gt(B,grid);Rb=B.V_in.to_numpy();fl={'uses_held_labels':False,'in_sample':False}
        emit('inner_loro',A.route.iloc[0],r,'BASE',B,B.delta.to_numpy(),Rb,fl)
        for arm,target,kind in (('WD0','e_true','D0'),('PX1','delta','X1'),('PD0','delta','D0'),('PA2','delta_s30','D0')):
            # rows() reads the heading grid by the frame index, so A keeps the original D index
            xA,yA,medA=L4.rows(A,target,grid,kind,sd+{'WD0':1,'PX1':2,'PD0':3,'PA2':4}[arm],0)
            m=L4.mk().fit(xA,yA);xB=P.feats(B,medA)
            if kind=='D0':xB['d0']=dB
            pr=m.predict(xB);res=(B.e_true.to_numpy()-pr) if target=='e_true' else (B.delta.to_numpy()-pr)
            emit('inner_loro',A.route.iloc[0],r,arm,B,res,Rb,fl)
    # ---------------- X1 on the held route (diagnostic)
    mu_oof=np.empty(len(he));v_oof=np.empty(len(he))
    for c,g in he.groupby('case'):
        mu,Rr=V.base_params(param,c,'full',g.pose_id.to_numpy(),'POWER_DIAG');mu_oof[np.flatnonzero(he.index.isin(g.index))]=mu[:,1];v_oof[np.flatnonzero(he.index.isin(g.index))]=Rr[:,1,1]
    he['delta_oof']=he.e_true.to_numpy()-mu_oof
    emit('held','-',H,'BASE_OOF',he,he.delta_oof.to_numpy(),v_oof,{'uses_held_labels':False,'in_sample':False})
    dep=l4['models']['P_D0'].predict(xa);emit('held','+'.join(trr),H,'DEPLOYED_PD0',he,he.delta_oof.to_numpy()-dep,v_oof,{'uses_held_labels':False,'in_sample':False})
    xi,yi,mi=L4.rows(he,'delta_oof',grid,'D0',P.SEED[H]*1000+999,0);mI=L4.mk().fit(xi,yi);xI=P.feats(he,mi);xI['d0']=d0_gt(he,grid)
    emit('held',H,H,'INSAMPLE_PD0',he,he.delta_oof.to_numpy()-mI.predict(xI),v_oof,{'uses_held_labels':True,'in_sample':True})
    half=np.zeros(len(he),bool)
    for c,g in he.groupby('case'):
        pos=np.flatnonzero(he.index.isin(g.index));half[pos]=g.t.to_numpy()>=np.median(g.t.to_numpy())
    resb=np.empty(len(he))
    for fold in (False,True):
        trn=he[half!=fold];tst=he[half==fold];xt,yt,mt=L4.rows(trn,'delta_oof',grid,'D0',P.SEED[H]*1000+990+int(fold),0)
        mb=L4.mk().fit(xt,yt);xs=P.feats(tst,mt);xs['d0']=d0_gt(tst,grid);resb[half==fold]=tst.delta_oof.to_numpy()-mb.predict(xs)
    emit('held',H+'_otherhalf',H,'BLOCKCV_PD0',he,resb,v_oof,{'uses_held_labels':True,'in_sample':False})
    pd.DataFrame(rows).to_csv(out/f'{H}_INNERLORO.csv',index=False);(out/f'{H}_INNERLORO_QA.json').write_text(json.dumps(qa,indent=2))
    from p2_sysdiag import write_manifest
    write_manifest(out/f'{H}_INNERLORO_MANIFEST.json',vars(a),[a.l4models]+sorted(str(x) for x in Path(a.grid).rglob('GRID_*.npz')),[f'{H}_INNERLORO.csv'])
    assert qa['retrain_parity_P_D0']<1e-12,('RETRAIN_PARITY_FAIL',qa)
    print('INNERLORO_PASS '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
