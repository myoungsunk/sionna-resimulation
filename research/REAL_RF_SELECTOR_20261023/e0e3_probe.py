#!/usr/bin/env python3
"""G0/E0-E3: frozen outer-held PWIDE applied to REAL BASE prior from ladder 3.

P1R WIDE/PWIDE models were trained on other 2 routes; the proposed correction
is evaluated on matching L_BASE filter prior. Offline ground truth is used
ONLY for benefit/harm labels and strata/metrics (never RF feature columns).
This is an observational observability test; no selector model is fitted.
"""
from __future__ import annotations
import argparse, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score,average_precision_score

OFFS=[-8,-4,-2,-1,1,2,4,8]
SOURCE_COLS=['sF_+0','log_fp_power','fp_full']+[f'sF_{o:+d}' for o in OFFS]+[f'ds_{o:+d}' for o in OFFS]
CASE_ROUTES={'R2_aA_m0':'R2','R2_aA_m45':'R2','R2_aB_m0':'R2',
             'R4_aA_m0':'R4','R4_aB_m0':'R4',
             'R5_aA_m0':'R5','R5_aB_m0':'R5'}
QCOL=['detector_s_span','detector_delay_span_ns','early4','early8','early16',
       'delay_rms_ns','peak_diff_ns','tap_pol_var80','s_diff4','s_diff8','s_diff16']
F0=['sF_+0','abs_s0','log_fp_power','fp_full','mu_power','Vs']
F1=['shape_spread','shape_early_late','shape_asym','shape_first_delta','ds_-2','ds_-1','ds_+1','ds_+2','ds_+4']
F2=QCOL
F3=['d0_baseprior','abs_d0_baseprior','nu_baseprior','abs_nu_baseprior','pred_delta','abs_pred_delta']
ALLOWED=set(F0+F1+F2+F3)
FORBIDDEN=('fp_shift','gt','true','oracle','label','r_base','r_pw','e_s','sL_','sMGT','h_gt','future',
           'bias','case','route','accepted','time','pose_id','k')
SEVERE=0.01 # descriptive severe benefit squared polarization-ratio units, not a tuned threshold.

def load_csv(path):
    p=Path(path)
    assert p.is_file(),str(p)
    return pd.read_csv(p)

def find_one(base,pattern):
    fs=sorted(Path(base).rglob(pattern))
    assert len(fs)==1,(pattern,[str(x) for x in fs])
    return fs[0]

def make_dataset(repo,source_dir,models_dir,series_dir):
    hp=load_csv(repo/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz')
    hm=load_csv(repo/'research/PJ_DS_GATED_20261021/results_hpath/HP_SERIES.csv.gz')
    assert set(hp.route)=={'R2','R4','R5'},set(hp.route)
    assert len(hp)==9519,len(hp)
    assert not hp.duplicated(['case','pose_id']).any()
    for o in OFFS:hp[f'ds_{o:+d}']=hp[f'sF_{o:+d}']-hp['sF_+0']
    feat_obs=load_csv(find_one(source_dir,'OBSERVATION_FEATURES_LABELS.csv.gz'))
    feat_obs=feat_obs[feat_obs.channel=='full']
    assert set(QCOL).issubset(feat_obs.columns),(set(QCOL)-set(feat_obs.columns))
    assert not feat_obs.duplicated(['case','pose_id']).any()
    hp=hp.merge(feat_obs[['case','pose_id']+QCOL],on=['case','pose_id'],how='left',validate='one_to_one')
    assert hp[QCOL].notna().all().all(),'MISSING_ONLINE_QUALITY_FEATURE'
    models={}
    oracle={}
    for rt in ('R2','R4','R5'):
        f=find_one(models_dir,f'{rt}_PTRAIN.joblib')
        v=joblib.load(f)
        assert v['held']==rt and rt not in v['train_routes'] and set(v['train_routes'])=={'R2','R4','R5'}-{rt}
        assert set(SOURCE_COLS)==set(v['features'])
        models[rt]=v
        d=load_csv(repo/f'research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_r2diag/{rt}_R2DIAG_PACKETS.csv.gz')
        d['route']=rt
        assert not d.duplicated(['case','pose_id']).any()
        oracle[rt]=d[['case','pose_id','r_base','mu_oof','V','fp_shift_tap','e_true']]
    odf=pd.concat(list(oracle.values()),ignore_index=True)
    hp=hp.merge(odf,on=['case','pose_id'],how='left',validate='one_to_one')
    assert hp[['r_base','mu_oof','V','e_true']].notna().all().all()
    assert np.all(hp['V']>0)
    out=[];qa=[]
    for case,rt in CASE_ROUTES.items():
        sc=load_csv(find_one(series_dir,f'{case}_LADDER3_SERIES.csv.gz'))
        gp=hm[hm.case==case][['case','bias','k','pose_id','t_s']].copy()
        assert not gp.duplicated(['case','bias','k']).any()
        assert not sc.duplicated(['case','bias','k']).any()
        a=sc.merge(gp,on=['case','bias','k'],how='left',validate='one_to_one',suffixes=('_trace','_map'))
        assert a.pose_id.notna().all(),case
        assert np.max(np.abs(a.t_s_trace.to_numpy()-a.t_s_map.to_numpy()))<1e-10,case
        d=a.merge(hp[hp.case==case],on=['case','pose_id'],how='left',validate='many_to_one')
        assert len(d)==len(a),case
        assert d[['sF_+0','r_base','V','L_BASE__d0']].notna().all().all(),case
        v=models[rt]
        med=v['medians']['PWIDE']
        x=d[SOURCE_COLS].replace([np.inf,-np.inf],np.nan).fillna(med).copy()
        x['d0']=d['L_BASE__d0'].to_numpy()
        ehat=v['models']['PWIDE'].predict(x)
        rb=d.r_base.to_numpy(float); rp=rb-ehat
        ds=rb**2-rp**2
        assert np.max(np.abs(ds-(2*rb*ehat-ehat**2)))<1e-12
        assert np.max(np.abs(rb-(d.e_true-d.mu_oof).to_numpy()))<1e-10
        f=pd.DataFrame({'case':case,'route':rt,'bias':d.bias,'k':d.k,'pose_id':d.pose_id.astype(int),
                't_s':d.t_s_trace,'accepted_BASE':d['L_BASE__acc'].astype(bool),
                'r_base_truth':rb,'r_pwide_truth':rp,
                'label_ds':ds,'benefit_truth':ds>0,
                'severe_benefit_truth':ds>SEVERE,'severe_harm_truth':ds<-SEVERE,
                'fp_shift_truth':d.fp_shift_tap.to_numpy()})
        for c in F0+QCOL:
            source={'mu_power':'mu_oof','Vs':'V','abs_s0':'sF_+0'}.get(c,c)
            f[c]=np.abs(d[source].to_numpy()) if c=='abs_s0' else d[source].to_numpy()
        for c in ['ds_-2','ds_-1','ds_+1','ds_+2','ds_+4']:f[c]=d[c].to_numpy()
        mat=d[[f'ds_{o:+d}' for o in OFFS]].to_numpy(float)
        f['shape_spread']=np.nanmax(np.abs(mat),axis=1)
        f['shape_first_delta']=np.abs(d['ds_+1'].to_numpy())
        f['shape_early_late']=np.abs(d['ds_+4'].to_numpy()-d['ds_-4'].to_numpy())
        f['shape_asym']=np.abs(d['ds_+1'].to_numpy()+d['ds_-1'].to_numpy())
        f['d0_baseprior']=d['L_BASE__d0'].to_numpy()
        f['abs_d0_baseprior']=np.abs(f.d0_baseprior.to_numpy())
        f['nu_baseprior']=f.d0_baseprior-f.mu_power
        f['abs_nu_baseprior']=np.abs(f.nu_baseprior.to_numpy())
        f['pred_delta']=ehat
        f['abs_pred_delta']=np.abs(ehat)
        assert f[list(ALLOWED)].notna().all().all(),case
        qa.append({'case':case,'route':rt,'n':len(f),'nB0':int((f.bias=='B0').sum()),
                 'nL2':int((f.bias=='L2').sum()),
                 'prior_source':'L_BASE prior from actual gyro/odom+RF replay',
                 'pw_model_routes':v['train_routes'],
                 'full_vs_obs_s0_max':float(np.max(np.abs(d['sF_+0']-d['s_fp']))) if 's_fp' in d else None})
        out.append(f)
    z=pd.concat(out,ignore_index=True)
    assert set(z.route)=={'R2','R4','R5'}
    assert set(z.bias)=={'B0','L2'}
    for case,g in z.groupby('case'):
        b=g[g.bias=='B0']; l=g[g.bias=='L2']
        assert np.array_equal(b.pose_id.to_numpy(),l.pose_id.to_numpy()),case
        assert np.allclose(b.r_base_truth,l.r_base_truth,rtol=0,atol=1e-12)
    return z,qa

def agg(group):
    rb=group.r_base_truth.to_numpy();rp=group.r_pwide_truth.to_numpy();ds=group.label_ds.to_numpy()
    oracle=np.where(ds>0,rp,rb)
    return {'n':len(group),'benefit_frac':float(np.mean(ds>0)),
      'severe_benefit_frac':float(np.mean(ds>SEVERE)),
      'severe_harm_frac':float(np.mean(ds<-SEVERE)),
      'base_rmse':float(np.sqrt(np.mean(rb**2))),
      'pwide_rmse':float(np.sqrt(np.mean(rp**2))),
      'oracle_select_rmse':float(np.sqrt(np.mean(oracle**2))),
      'mean_benefit_ds':float(ds.mean()),
      'harm_if_apply_frac':float(np.mean(ds<0)),
      'fp_shift0_frac':float(np.mean(group.fp_shift_truth.to_numpy()==0)),
      'loss_on_baseclean':float(np.mean(ds[np.abs(rb)<.05])) if np.any(np.abs(rb)<.05) else np.nan,
      'n_baseclean':int(np.sum(np.abs(rb)<.05))}

def score_features(D):
    rows=[]
    for route,sub in D[D.bias=='B0'].groupby('route'):
        for setname,cc in [('F0',F0),('F1',F1),('F2',F2),('F3',F3)]:
            for col in cc:
                x=sub[col].to_numpy(float)
                b=sub.benefit_truth.to_numpy(bool)
                if len(np.unique(x))<2 or len(np.unique(b))<2:continue
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    auc=float(roc_auc_score(b,x))
                    ap=float(average_precision_score(b,x))
                    auc_rev=float(roc_auc_score(b,-x))
                    corr=float(spearmanr(x,sub.label_ds.to_numpy()).statistic)
                rows.append({'route':route,'group':setname,'feature':col,
                  'AUC_signed':auc,'AUC_reversed':auc_rev,
                  'AUC_best_posthoc_exploratory':max(auc,auc_rev),
                  'AP_signed':ap,'base_prevalence':float(b.mean()),
                  'spearman_feature_Ds':corr,
                  'n':len(sub),
                  'usage':'exploratory_only_no_held_tuning'})
    return pd.DataFrame(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True)
    p.add_argument('--models',required=True)
    p.add_argument('--series',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--repo',default='.')
    a=p.parse_args();dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
    z,caseqa=make_dataset(Path(a.repo),a.source,a.models,a.series)
    z.to_csv(dst/'E2_PACKET_BENEFIT_OFFLINE.csv.gz',index=False,compression='gzip')
    d=[]
    for (rt,bias),q in z.groupby(['route','bias']):
        for name,mask in [('all',np.ones(len(q),bool)),('t30',q.t_s.to_numpy()>=30),
                          ('t30_accept',(q.t_s.to_numpy()>=30)&q.accepted_BASE.to_numpy(bool))]:
            x=q.iloc[np.where(mask)[0]]
            if not len(x):continue
            for stratum,sel in [('all',np.ones(len(x),bool)),('fp_shift0',x.fp_shift_truth.to_numpy()==0),
                                ('fp_shift_abs_ge2',np.abs(x.fp_shift_truth.to_numpy())>=2),
                                ('base_abs_le005',np.abs(x.r_base_truth.to_numpy())<.05)]:
                y=x.iloc[np.where(sel)[0]]
                if not len(y):continue
                d.append({'route':rt,'bias':bias,'window':name,'stratum':stratum,**agg(y)})
    D=pd.DataFrame(d);D.to_csv(dst/'E0_E2_STRATA.csv',index=False)
    feats=score_features(z)
    assert set(feats.feature).issubset(ALLOWED)
    assert len(feats)>20
    feats.to_csv(dst/'E3_UNIVARIATE_FEATURES.csv',index=False)
    qa={'status':'PASS_G0_E0_E3_DESCRIPTIVE','n_rows':len(z),
        'n_unique_packets':int(z[z.bias=='B0'].groupby(['case','pose_id']).ngroups),
        'routes':sorted(z.route.unique()),'cases':caseqa,
        'online_allowlist':sorted(ALLOWED),
        'strictly_forbidden_feature_tokens':FORBIDDEN,
        'labels_are_offline_only':True,
        'pw_outer_held_disjoint':all(q['route'] not in q['pw_model_routes'] for q in caseqa),
        'benefit_pred_uses_L_BASE_prior_not_GT':True,
        'selector_fitted':False,'recursive_selector_tested':False,
        'no_held_threshold_selection':True,
        'note':'Feature AUC orientation chosen on held data is descriptive, not deployment accuracy'}
    assert qa['n_unique_packets']==9519 and qa['pw_outer_held_disjoint']
    (dst/'G0_E3_QA.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False))
    print('E0/E2 t>=30, BASE-accepted:\n'+D[(D.window=='t30_accept')&(D.stratum=='all')].round(5).to_string(index=False),flush=True)
    print('\nE3 best descriptive AUC per route:\n'+feats.sort_values('AUC_best_posthoc_exploratory',ascending=False).groupby('route').head(8).round(4).to_string(index=False),flush=True)
    print('G0_E3_PASS '+json.dumps({k:qa[k] for k in ['status','n_rows','n_unique_packets','pw_outer_held_disjoint','selector_fitted']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
