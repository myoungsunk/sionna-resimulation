#!/usr/bin/env python3
"""E5 single packet counterfactual from the SAME recursive BASE x-,P-,H,R and gate.

The filter carrying a true state forward is exclusively BASE_POWER.
Different alpha arms are evaluated off this frozen BASE prior but never feed
back into it. Thus no inter-arm feedback, variance changes or gate differences.
No hidden GT in operational alpha arms; GT used for offline Dpsi labels only.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import e5e6_replay as E
from e5e6_replay import V,R2,S,DEG,OFFS,ARMS

def analyze(case,modpack,obs,par,pk):
    th=E.thresholds(case['route'],obs,pk)
    pp=pk[pk.case==case['id']].copy()
    for o in OFFS:pp[f'ds_{o:+d}']=pp[f'sF_{o:+d}']-pp['sF_+0']
    model=V.SourceFFD()
    scores=[];traces=[];qa={'case':case['id'],'held':case['route'],'cutoffs':th,'parity':{}}
    for bias in ['B0','L2']:
        old=np.load(V.one(f'{case["id"]}_full_{bias}_TRACE.npz'),allow_pickle=False)
        t,ids,truth=old['t_s'],old['pose_id'],old['truth_scoring_only']
        q=obs[(obs.case==case['id'])&(obs.channel=='full')].set_index('pose_id').loc[ids]
        z=q[['range_m','s_fp']].to_numpy(float)
        ff,fr=R2.full_features(pp,ids)
        assert np.max(np.abs(ff['sF_+0'].to_numpy()-z[:,1]))<1e-9
        mu,R=V.base_params(par,case['id'],'full',ids,'POWER_DIAG')
        x0_features=R2.m_inputs(ff,modpack['medians']['PWIDE'])
        sh=np.nanmax(np.abs(fr[[f'ds_{o:+d}' for o in OFFS]].to_numpy()),axis=1)
        vv=R[:,1,1]>=th['tau_Vs']; ss=sh>=th['tau_shape']
        dd=q.detector_s_span.to_numpy()>=th['tau_detector']
        true_e=fr['sF_+0'].to_numpy()-fr['sL_+0'].to_numpy()
        controls,x0=V.build_positive_bias_controls(t,truth,bias)
        x=np.r_[x0,0.]
        P=np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2])
        X=np.empty((len(t),1,4));CP=np.empty((len(t),1,4,4))
        r=[]
        for k in range(len(t)):
            if k:x,P=V.predict_one(x,P,float(controls['ds_odom'][k]),
                float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
            hk,Hk=model.batch(x[None],case,gradient=True)
            h=hk[0];H=Hk[0];nu=z[k]-h-mu[k]
            Sig=H@P@H.T+R[k]
            nis=float(nu@np.linalg.solve(Sig,nu))
            gate=nis<=S.G2
            K=np.linalg.solve(Sig,H@P).T
            ix=x0_features.iloc[[k]].copy();ix['d0']=z[k,1]-h[1]
            hat=float(modpack['models']['PWIDE'].predict(ix)[0])
            r_base=true_e[k]-mu[k,1]
            ds_true=float(r_base*r_base-(r_base-hat)**2)
            proj=[]
            for arm in ARMS:
                if arm!='ORACLE_Ds_DIAG':
                    alpha=E.bin_alpha(arm,vv[k],ss[k],dd[k],None,None)
                else:
                    alpha=float(ds_true>0)
                xx=x+K@(nu-np.array([0.,alpha*hat]))
                xx[2]=V.MC.wrap(xx[2])
                if not gate:xx=x.copy()
                err=float(V.MC.wrap(xx[2]-truth[k,2])*DEG)
                proj.append((arm,alpha,err,xx))
            base_post=proj[0][2]
            # Same physical gate+K; counterfactual labels do NOT update prediction.
            for arm,alpha,err,xx in proj:
                r.append({'case':case['id'],'route':case['route'],'bias':bias,'k':k,'t_s':t[k],'arm':arm,
                   'alpha':alpha,'base_gate':gate,'base_nis':nis,
                   'base_prior_heading_err_deg':float(V.MC.wrap(x[2]-truth[k,2])*DEG),
                   'post_heading_error_deg':err,'Dpsi_deg2':base_post**2-err**2,
                   'base_rpol_gt':r_base,'rp_gt':r_base-alpha*hat,
                   'D_s_gt':ds_true,'pw_delta_hat':hat,
                   'fp_shift_truth':fr.fp_shift_tap.iloc[k]})
            # Ground truth is NOT read in the BASE propagation path; the normal BASE update advances it.
            x,P,ni,yes=R2.update_one(x,P,z[k],h,H,mu[k],R[k],False)
            assert yes==gate and abs(ni-nis)<1e-9
            X[k,0]=x;CP[k,0]=P
        sc,ex=S.score_extra(X,CP,t,truth,case)
        ref=pd.read_csv(R2.REPO/'research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_ladder3/LADDER3_SCORES.csv')
        zref=ref[(ref.case==case['id'])&(ref.bias==bias)&(ref.arm=='L_BASE')]
        assert len(zref)==1
        err={q:abs(sc[0][q]-float(zref.iloc[0][q])) for q in ['heading_rmse_deg','heading_nees_1d','heading_cov95','xy_rmse_cm']}
        assert max(err.values())<1e-7,(case['id'],bias,err)
        qa['parity'][bias]=err
        zsc=pd.DataFrame(r);m=zsc.t_s>=30
        for arm,a in zsc[m].groupby('arm'):
            scores.append({'case':case['id'],'route':case['route'],'bias':bias,'arm':arm,'n':len(a),
               'heading_rmse_after_deg':float(np.sqrt(np.mean(a.post_heading_error_deg**2))),
               'heading_q99_abs_deg':float(np.quantile(np.abs(a.post_heading_error_deg),.99)),
               'mean_Dpsi_deg2':float(a.Dpsi_deg2.mean()),
               'fraction_Dpsi_positive':float(np.mean(a.Dpsi_deg2>0)),
               'fraction_alpha_positive':float(np.mean(a.alpha>0)),
               'mean_polarization_improvement':float(np.mean(a.base_rpol_gt**2-a.rp_gt**2)),
               'base_gate_accept':float(a.base_gate.mean())})
        traces.append(zsc)
        print('SAME_PRIOR_OK',case['id'],bias,'PARITY',max(err.values()),flush=True)
    return pd.DataFrame(scores),pd.concat(traces,ignore_index=True),qa

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--case',required=True);ap.add_argument('--models',required=True)
    ap.add_argument('--out',required=True);a=ap.parse_args()
    case=next(c for c in V.MANIFEST['cases'] if c['id']==a.case)
    pack=joblib.load(a.models)
    assert pack['held']==case['route'] and case['route'] not in pack['train_routes']
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    par=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    pk=pd.read_csv(R2.REPO/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    d=Path(a.out);d.mkdir(exist_ok=True,parents=True)
    summary,tr,qa=analyze(case,pack,obs,par,pk)
    assert len(summary)==2*len(ARMS)
    summary.to_csv(d/f'{a.case}_E5_SAMEPRIOR.csv',index=False)
    tr.to_csv(d/f'{a.case}_E5_PACKET.csv.gz',index=False,compression='gzip')
    (d/f'{a.case}_E5_QA.json').write_text(json.dumps(qa,indent=2))
    print('E5_CASE_PASS',case['id'],flush=True)
if __name__=='__main__':main()
