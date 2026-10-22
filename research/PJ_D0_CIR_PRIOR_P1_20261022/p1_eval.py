#!/usr/bin/env python3
"""P1: held-route frozen HGB, exact SourceFFD prior at 0/±1/±2/±5/±10/±20 deg.

Pre-registration: 00_P1_PLAN_KO.md.
Only GT pose for constructing synthetic prior and evaluation; never a learned RF feature.
Single heading scalar update, not navigation EKF.
"""
from __future__ import annotations
import argparse, json, os, sys, math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
import v_replay as V

IN=REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz'
OFFS=[-8,-4,-2,-1,1,2,4,8]
FEATURES=['sF_+0','log_fp_power','fp_full']+[f'sF_{o:+d}' for o in OFFS]+[f'ds_{o:+d}' for o in OFFS]
DELTAS=[0,1,-1,2,-2,5,-5,10,-10,20,-20]
ARMS=['PRIOR_ONLY','RAW','CIR_ONLY','CIR_PLUS_D0','D0_DIRECT','ORACLE_LOS']
GAIN_MODES=['LOCAL_3DEG','GTREF_3DEG','LOCAL_MATCHED']
DEG2RAD=math.pi/180.

def rmse(v):
    v=np.asarray(v,float)
    return float(np.sqrt(np.mean(v*v)))

def mkm():
    return HistGradientBoostingRegressor(max_iter=160,learning_rate=.055,
             max_leaf_nodes=17,max_depth=5,min_samples_leaf=20,
             l2_regularization=1.,random_state=20261022)

def prepare():
    D=pd.read_csv(IN).sort_values(['case','pose_id']).reset_index(drop=True)
    for o in OFFS: D[f'ds_{o:+d}']=D[f'sF_{o:+d}']-D['sF_+0']
    D['e_true']=D['sF_+0']-D['sL_+0']
    assert set(D.route)=={'R2','R4','R5'}
    assert D[['sF_+0','sL_+0','sMGTp1_+0','sMGTm1_+0']].notna().all().all()
    return D

def fit_models(D,held):
    tr=D[D.route!=held]; te=D[D.route==held].copy().reset_index(drop=True)
    med=tr[FEATURES].replace([np.inf,-np.inf],np.nan).median().fillna(0)
    a=tr[FEATURES].replace([np.inf,-np.inf],np.nan).fillna(med).reset_index(drop=True)
    b=te[FEATURES].replace([np.inf,-np.inf],np.nan).fillna(med).reset_index(drop=True)
    cir=mkm().fit(a,tr.e_true.to_numpy())
    cir_pred=cir.predict(b)
    train_d0=np.r_[tr['sF_+0'].to_numpy()-tr['sMGTp1_+0'].to_numpy(),
                   tr['sF_+0'].to_numpy()-tr['sMGTm1_+0'].to_numpy()]
    atr=pd.concat([a,a],ignore_index=True)
    atr['d0']=train_d0
    y=np.tile(tr.e_true.to_numpy(),2)
    d0_model=mkm().fit(atr,y)
    return te,b,cir_pred,d0_model,len(tr)

def compute_lut(model,te,delta):
    """Exact SourceFFD s and analytic local Jacobian at GT position, GT heading+delta."""
    s=np.empty(len(te)); gdeg=np.empty(len(te))
    for cname,cc in te.groupby('case',sort=False):
        case=next(c for c in V.MANIFEST['cases'] if c['id']==cname)
        poses=pd.DataFrame(json.loads((V.ROOT/case['samples_path']).read_text())).set_index('pose_id')
        coords=poses.loc[cc.pose_id,['x','y','yaw_body_deg']].to_numpy(float)
        assert np.all(np.isfinite(coords))
        coords[:,2]=np.deg2rad(coords[:,2]+delta)
        out_s=[];out_g=[]
        for i in range(0,len(coords),32):
            h,H=model.batch(coords[i:i+32],case,gradient=True)
            out_s.append(h[:,1]);out_g.append(H[:,1,2]*DEG2RAD)
        ix=cc.index.to_numpy()
        s[ix]=np.concatenate(out_s)
        gdeg[ix]=np.concatenate(out_g)
    assert np.isfinite(s).all() and np.isfinite(gdeg).all()
    return s,gdeg

def score(z,pose,delta,gr,gg,case,names):
    res=[]
    for gain_mode in GAIN_MODES:
        if gain_mode=='GTREF_3DEG': gd=gg; sig=3.
        else:
            gd=gr
            sig=3. if gain_mode=='LOCAL_3DEG' else max(3.,abs(delta))
        K=sig*sig*gd/(sig*sig*gd*gd+0.01)
        for arm,e_hat in names.items():
            nu=(z-e_hat)-pose
            post=np.full(len(nu),float(delta)) if arm=='PRIOR_ONLY' else delta+K*nu
            los_err=z-e_hat-names['ORACLE_LOS']
            abs_e=np.abs(post)
            out={'delta':delta,'gain_mode':gain_mode,'arm':arm,
                 'n':len(te_global_placeholder) if False else len(post),
                 'heading_rmse_deg':rmse(post),
                 'heading_mae_deg':float(abs_e.mean()),
                 'heading_signed_bias_deg':float(np.mean(post)),
                 'heading_q95_abs_deg':float(np.quantile(abs_e,.95)),
                 'heading_q99_abs_deg':float(np.quantile(abs_e,.99)),
                 'heading_max_abs_deg':float(abs_e.max()),
                 'heading_improved_frac':float(np.mean(abs_e<abs(delta))) if delta else np.nan,
                 'los_rmse':rmse(los_err),
                 'innovation_oracle_rmse':rmse(nu-(z-names['ORACLE_LOS']-pose)),
                 'gain_k_abs_mean':float(np.mean(np.abs(K))),
                 'local_g_abs_med':float(np.median(np.abs(gr)))}
            res.append((out,post,nu))
    return res

def main():
    p=argparse.ArgumentParser();p.add_argument('--held',required=True,choices=['R2','R4','R5'])
    p.add_argument('--out',required=True); a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    D=prepare();te,B,cir_pred,d0_model,ntr=fit_models(D,a.held)
    model=V.SourceFFD()
    z=te['sF_+0'].to_numpy()
    es=te.e_true.to_numpy()
    gg=(te['sMGTp1_+0']-te['sMGTm1_+0']).to_numpy()/2
    met=[]; cases=[]; pk=[]; nu_cache={}
    check={'held':a.held,'train_n':ntr,'test_n':len(te),'delta_list':DELTAS,
           'git_sha':os.environ.get('GITHUB_SHA','local'),'qa_lut':{},
           'qa_legacy_1degree':{},'model':'HGB 160 iters unchanged, retrained only on original +/-1 synthetic priors',
           'position_prior':'GT fixed','gt_ref_for_scoring_only':True,'recursive':False}
    for delta in DELTAS:
        s,g=compute_lut(model,te,delta)
        if delta in (0,1,-1):
            col={0:'sMGT_+0',1:'sMGTp1_+0',-1:'sMGTm1_+0'}[delta]
            dev=float(np.max(np.abs(s-te[col].to_numpy())))
            check['qa_lut'][str(delta)]=dev
            if dev>2e-5: raise AssertionError(f'SourceFFD LUT mismatch delta={delta} err={dev}')
        X=B.copy();X['d0']=z-s
        e_d0=d0_model.predict(X)
        names={'PRIOR_ONLY':z-s,'RAW':np.zeros(len(te)), 'CIR_ONLY':cir_pred,
               'CIR_PLUS_D0':e_d0, 'D0_DIRECT':z-s,'ORACLE_LOS':es}
        nu_cache[delta]={nm:z-eh-s for nm,eh in names.items()}
        # Evaluate all comparison arms under fixed-prior and diagnostic matched-prior gains.
        gmode_data={}
        for gain_mode in GAIN_MODES:
            gd=gg if gain_mode=='GTREF_3DEG' else g
            sig=3. if gain_mode!='LOCAL_MATCHED' else max(3.,abs(delta))
            k=sig*sig*gd/(sig*sig*gd*gd+0.01)
            for arm,e_hat in names.items():
                nu=z-eh-s
                post=np.full(len(te),delta,dtype=float) if arm=='PRIOR_ONLY' else delta+k*nu
                er=z-eh-te['sL_+0'].to_numpy()
                ab=np.abs(post)
                item={'route':a.held,'delta':delta,'abs_delta':abs(delta),
                     'gain_mode':gain_mode,'arm':arm,'n':len(te),
                     'heading_rmse_deg':rmse(post),'heading_mae_deg':float(ab.mean()),
                     'heading_signed_bias_deg':float(post.mean()),
                     'heading_q95_abs_deg':float(np.quantile(ab,.95)),
                     'heading_q99_abs_deg':float(np.quantile(ab,.99)),
                     'heading_max_abs_deg':float(ab.max()),
                     'heading_improved_frac':float(np.mean(ab<abs(delta))) if delta else np.nan,
                     'los_rmse':rmse(er),'innovation_oracle_rmse':rmse(er),
                     'gain_k_abs_mean':float(np.mean(np.abs(k)))}
                met.append(item)
                if delta in (0,-1,1,-5,5,-10,10,-20,20):
                    for cname,idx in te.groupby('case').groups.items():
                        sub=post[np.asarray(list(idx))]
                        cases.append({'route':a.held,'case':cname,'delta':delta,'gain_mode':gain_mode,'arm':arm,
                                      'heading_rmse_deg':rmse(sub),'heading_q95_abs_deg':float(np.quantile(np.abs(sub),.95))})
                if arm in ('CIR_PLUS_D0','ORACLE_LOS') and gain_mode=='LOCAL_3DEG':
                    pk.append(pd.DataFrame({'route':a.held,'case':te.case,'pose_id':te.pose_id,
                            'delta':delta,'arm':arm,'sF':z,'sL':te['sL_+0'].to_numpy(),
                            'h_prior':s,'s_clean':z-e_hat,'e_hat':e_hat,'d0':z-s,'local_g':g,'K':k,
                            'innovation':nu,'post_error_deg':post}))
        if abs(delta)==1:
            old={'R2':.9880157018709935,'R4':.9690106002806752,'R5':.9858921711457884}[a.held]
            h=[row['heading_rmse_deg'] for row in met if row['delta']==delta and row['gain_mode']=='GTREF_3DEG' and row['arm']=='CIR_PLUS_D0'][-1]
            # Per-sign RMSE can differ from previously reported +/- mean, checked at both signs below.
        print(f'P1_PRIOR_DONE {a.held} delta={delta:+g}',flush=True)
    mm=pd.DataFrame(met)
    for gm in GAIN_MODES:
        base=mm[(mm.gain_mode==gm)&(mm.arm=='PRIOR_ONLY')].set_index('delta').heading_rmse_deg
        mm.loc[mm.gain_mode==gm,'ratio_to_prior']=mm.loc[mm.gain_mode==gm].apply(
            lambda x:x.heading_rmse_deg/base.loc[x.delta] if x.delta else np.nan,axis=1)
    for mode in ('GTREF_3DEG','LOCAL_3DEG'):
        h=mm[(mm.gain_mode==mode)&(mm.arm=='CIR_PLUS_D0')&(mm.delta.isin((-1,1)))]
        check['qa_legacy_1degree'][mode]=float(h.heading_rmse_deg.mean())
    old={'R2':.9880157018709935,'R4':.9690106002806752,'R5':.9858921711457884}[a.held]
    check['qa_legacy_maxdiff']=abs(check['qa_legacy_1degree']['GTREF_3DEG']-old)
    assert check['qa_legacy_maxdiff']<1e-6,(a.held,check['qa_legacy_maxdiff'])
    assert all(abs(mm[(mm.arm=='D0_DIRECT')&(mm.gain_mode=='LOCAL_3DEG')&(mm.delta==d)].heading_rmse_deg.iloc[0]-abs(d))<1e-8 for d in DELTAS)
    # Paired slope is diagnostic only.
    gain=[]
    for absd in (1,2,5,10,20):
        o=nu_cache[absd]['ORACLE_LOS']-nu_cache[-absd]['ORACLE_LOS']
        denom=np.dot(o,o)
        for arm in ARMS:
            u=nu_cache[absd][arm]-nu_cache[-absd][arm]
            gain.append({'route':a.held,'abs_delta':absd,'arm':arm,'G':float(np.dot(u,o)/denom)})
    mm.to_csv(out/f'{a.held}_P1_METRICS.csv',index=False)
    pd.DataFrame(cases).to_csv(out/f'{a.held}_P1_CASE.csv',index=False)
    pd.DataFrame(gain).to_csv(out/f'{a.held}_P1_GAIN.csv',index=False)
    pd.concat(pk,ignore_index=True).to_csv(out/f'{a.held}_P1_PACKET.csv.gz',index=False,compression='gzip')
    (out/f'{a.held}_P1_QA.json').write_text(json.dumps(check,indent=2))
    print(f'P1_DONE {a.held} QA {json.dumps(check)}',flush=True)
    print(mm[(mm.gain_mode=='LOCAL_3DEG')&(mm.arm.isin(['PRIOR_ONLY','CIR_ONLY','CIR_PLUS_D0','ORACLE_LOS']))]
          [['delta','arm','heading_rmse_deg','ratio_to_prior','heading_q95_abs_deg']].round(4).to_string(index=False),flush=True)

if __name__=='__main__':main()
