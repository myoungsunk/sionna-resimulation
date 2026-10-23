#!/usr/bin/env python3
"""E0-E3: Full-RF packet harm/benefit diagnostic on existing frozen OOF outputs.

CAUTION: R2DIAG OOF PWIDE labels come from models trained on the OTHER TWO
routes. If reused as classifier-training labels, the outer held route can
influence nuisance labels on the two training routes. Consequently E3 is an
EXPLORATORY SEPARABILITY SCREEN, NOT STRICT GENERALIZATION. Train-only nested
OOF and recursive E5/E6 must follow before deployment claims.
"""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
ROOT=Path(__file__).resolve().parents[2]
PK=ROOT/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz'
DIAG=ROOT/'research/PJ_D0_CIR_P2_RECURSIVE_20261022/results_r2diag'
GROUP={
  'F0':['sF_+0','log_fp_power','fp_full'],
  'F1':['sF_-8','sF_-4','sF_-2','sF_-1','sF_+1','sF_+2','sF_+4','sF_+8'],
}
def metrics(y,p):
    y=np.asarray(y,bool);p=np.asarray(p,float)
    d={'n':len(y),'positive_rate':float(np.mean(y)),
       'auc':float(roc_auc_score(y,p)) if 0<sum(y)<len(y) else None,
       'auprc':float(average_precision_score(y,p)) if any(y) else None,
       'brier':float(brier_score_loss(y,p))}
    for quant in (.10,.25,.5):
        n=max(1,int(round(len(y)*quant))); ix=np.argsort(-p)[:n]
        d[f'top_{int(quant*100)}_precision']=float(y[ix].mean())
    return d
def run(out):
    P=pd.read_csv(PK)
    frames=[]
    for held in ('R2','R4','R5'):
        f=DIAG/f'{held}_R2DIAG_PACKETS.csv.gz'
        if not f.is_file():raise FileNotFoundError(f)
        d=pd.read_csv(f);d['route']=held
        frames.append(d)
    D=pd.concat(frames,ignore_index=True)
    # Uniqueness and join contract: no truth-dependent feature in online input.
    assert not D.duplicated(['case','pose_id']).any()
    assert not P.duplicated(['case','pose_id']).any()
    F=P[['case','pose_id']+list(dict.fromkeys(sum(GROUP.values(),[])))].copy()
    D=D.merge(F,on=['case','pose_id'],how='left',validate='one_to_one',indicator=True)
    assert (D['_merge']=='both').all()
    D['Ds']=D.r_base**2-D.r_pwide**2
    D['benefit']=D.Ds>0
    D['harm']=D.Ds<0
    D['severe']=D.r_base.abs()>.2
    D['clean']=D.r_base.abs()<.05
    D['injury_clean']=D.clean & D.harm
    D['fp_large']=D.fp_shift_tap.abs()>=2  # DIAGNOSTIC LABEL ONLY
    D['ideal_binary_err_sq']=np.minimum(D.r_base**2,D.r_pwide**2)
    allrows=[];classes=[];preds=[]
    for H in ('R2','R4','R5'):
        te=D[D.route==H].copy();tr=D[D.route!=H].copy()
        assert len(te)>0 and len(tr)>0
        for name,grp in [('all',te),('fp0',te[te.fp_shift_tap==0]),('fp2+',te[te.fp_large]),('clean',te[te.clean]),('severe',te[te.severe])]:
            if not len(grp):continue
            row=dict(route=H,stratum=name,n=len(grp),benefit_rate=float(grp.benefit.mean()),
                     clean_rate=float(grp.clean.mean()),base_rms=float(np.sqrt(np.mean(grp.r_base**2))),
                     pwide_rms=float(np.sqrt(np.mean(grp.r_pwide**2))),
                     oracle_select_rms=float(np.sqrt(np.mean(grp.ideal_binary_err_sq))),
                     mean_ds=float(grp.Ds.mean()),median_ds=float(grp.Ds.median()),
                     injury_rate=float(grp.harm.mean()))
            allrows.append(row)
        for group in ('F0','F0_F1'):
            features=GROUP['F0']+(GROUP['F1'] if group=='F0_F1' else [])
            y=tr.benefit.astype(int).to_numpy(); yt=te.benefit.astype(int).to_numpy()
            # Calibration is exploratory only; no threshold fitted on held H.
            model=make_pipeline(SimpleImputer(strategy='median'),
                       HistGradientBoostingClassifier(max_iter=90,max_leaf_nodes=9,min_samples_leaf=45,
                              learning_rate=.04,l2_regularization=5,early_stopping=False,random_state=20261023))
            # HGB needs no fitted preprocessing beyond train-route median.
            model.fit(tr[features],y)
            prob=model.predict_proba(te[features])[:,1]
            # D_s as outcome (diagnostic, not recursive EKF performance).
            sel=prob>=.5
            rm=np.sqrt(np.mean(np.where(sel,te.r_pwide**2,te.r_base**2)))
            row={'route':H,'group':group,**metrics(yt,prob),
                 'selection_rate_05':float(sel.mean()),
                 'selected_rms_05':float(rm),
                 'always_base_rms':float(np.sqrt(np.mean(te.r_base**2))),
                 'always_pwide_rms':float(np.sqrt(np.mean(te.r_pwide**2))),
                 'oracle_rms':float(np.sqrt(np.mean(te.ideal_binary_err_sq)))}
            classes.append(row)
            preds.append(pd.DataFrame({'route':H,'case':te.case,'pose_id':te.pose_id,'group':group,
                                       'p_benefit':prob,'benefit_oracle':yt,'Ds':te.Ds,
                                       'r_base':te.r_base,'r_pwide':te.r_pwide,
                                       'fp_large_diagnostic':te.fp_large}))
    out.mkdir(exist_ok=True,parents=True)
    pd.DataFrame(allrows).to_csv(out/'E1_ORACLE_BENEFIT.csv',index=False)
    pd.DataFrame(classes).to_csv(out/'E3_EXPLORATORY_RF_SEPARABILITY.csv',index=False)
    pd.concat(preds,ignore_index=True).to_csv(out/'E3_PACKET_SCORES.csv.gz',index=False,compression='gzip')
    diag={'matched_rows':len(D),'routes':D.route.value_counts().to_dict(),
       'label':'Ds = (e-mu_POWER)^2-(e-mu_POWER-delta_hat_PWIDE)^2',
       'features':GROUP,
       'GT_only_diagnostics':['r_base','r_pwide','benefit','fp_large','clean','severe'],
       'estimator':"train on other two routes' frozen OOF labels; inner crossfit nuisance is NOT strictly outer-held independent",
       'scientific_status':'EXPLORATORY ONLY; requires train-only nested crossfit before E5/E6',
       'prior_at_d0':'GT pose in frozen R2DIAG (not operational recursive prior)',
       'recursive_ekf_executed':False}
    (out/'E0_QA.json').write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print('E0_E3_OK',json.dumps(diag,ensure_ascii=False),flush=True)
    print(pd.DataFrame(allrows).round(4).to_string(index=False),flush=True)
    print(pd.DataFrame(classes).round(4).to_string(index=False),flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True)
    x=a.parse_args();run(Path(x.out))
