#!/usr/bin/env python3
"""R2 failure decomposition (07_R2_FAILURE_DECOMPOSITION_PLAN_KO.md). Diagnostic only.

Per held route H (R2 and controls R4, R5): static per-packet decomposition at the GT pose of the
POWER-preserving residual corrector (verification 2 models), plus stratified contributions on the
verification-2 recursive trajectories. Nothing here feeds back into models or thresholds.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.metrics import roc_auc_score

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
sys.path.insert(0,str(REPO/'research/PJ_D0_CIR_PRIOR_P1R_20261022'))
import strict_common as S
from strict_common import V
import p1r_eval as P
import p2_replay as R2

def qbin(x,q=5):
    return pd.qcut(pd.Series(x).rank(method='first'),q,labels=[f'Q{i+1}' for i in range(q)]).astype(str).to_numpy()

def strata_table(df,col,H,label):
    rows=[];tot=np.sum(df.g*df.r_pwide/df.V);totb=np.sum(df.g*df.r_base/df.V);totc=np.sum(df.g*df.r_pcir/df.V)
    den=np.sum(df.g**2/df.V)
    for k,g in df.groupby(col):
        rows.append({'held':H,'stratum_type':label,'stratum':str(k),'n':len(g),'frac':len(g)/len(df),
            'mean_delta_true':g.r_base.mean(),'mean_dhat_pwide':g.dhat_pwide.mean(),'mean_dhat_pcir':g.dhat_pcir.mean(),
            'mean_r_pwide':g.r_pwide.mean(),'mean_r_pcir':g.r_pcir.mean(),'rms_r_pwide':float(np.sqrt(np.mean(g.r_pwide**2))),
            'rms_r_base':float(np.sqrt(np.mean(g.r_base**2))),
            'wb_contrib_base_deg':float(np.sum(g.g*g.r_base/g.V)/den),'wb_contrib_pcir_deg':float(np.sum(g.g*g.r_pcir/g.V)/den),
            'wb_contrib_pwide_deg':float(np.sum(g.g*g.r_pwide/g.V)/den),
            'share_pwide':float(np.sum(g.g*g.r_pwide/g.V)/tot) if tot else np.nan,
            'share_base':float(np.sum(g.g*g.r_base/g.V)/totb) if totb else np.nan})
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--held',required=True,choices=['R2','R4','R5'])
    ap.add_argument('--pmodels',required=True);ap.add_argument('--series_dir',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args();H=a.held;out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    pp=joblib.load(a.pmodels);assert pp['held']==H and H not in pp['train_routes']
    D=P.prepare();obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'));param=pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    trr=sorted(pp['train_routes']);te=D[D.route==H].copy()
    # mu_OOF (BASE) and mu_single (POWER fitted on one training route only) for held packets
    oof=param[(param.channel=='full')&(param.model=='POWER_DIAG')].set_index(['case','pose_id'])
    key=list(zip(te.case,te.pose_id));te['mu_oof']=oof.loc[key,'mu_s'].to_numpy(float);te['V']=oof.loc[key,'Vs'].to_numpy(float)
    for r in trr:
        pin=S.power_fit(obs,[r],H);pin=pin[pin.channel=='full'].set_index(['case','pose_id'])
        te[f'mu_single_{r}']=pin.loc[key,'mu_s'].to_numpy(float)
    # GT pose quantities
    model=V.SourceFFD();parts=[]
    for cname,cc in te.groupby('case',sort=False):
        case=next(c for c in V.MANIFEST['cases'] if c['id']==cname)
        poses=pd.DataFrame(json.loads((V.ROOT/case['samples_path']).read_text())).set_index('pose_id')
        co=poses.loc[cc.pose_id,['x','y','yaw_body_deg']].to_numpy(float);co[:,2]=np.deg2rad(co[:,2])
        hs=[];gs=[]
        for i in range(0,len(co),32):
            h,Hj=model.batch(co[i:i+32],case,gradient=True);hs.append(h[:,1]);gs.append(Hj[:,1,2]*math.pi/180)
        anc=np.asarray(case['anchor'],float)
        parts.append(pd.DataFrame({'idx':cc.index,'h_gt':np.concatenate(hs),'g':np.concatenate(gs),
                                   'dist':np.hypot(co[:,0]-anc[0],co[:,1]-anc[1])}))
    gp=pd.concat(parts).set_index('idx');te=te.join(gp)
    te['d0_gt']=te['sF_+0']-te.h_gt
    xc=P.feats(te,pp['medians']['PCIR']);te['dhat_pcir']=pp['models']['PCIR'].predict(xc)
    xw=P.feats(te,pp['medians']['PWIDE']).copy();xw['d0']=te.d0_gt.to_numpy();te['dhat_pwide']=pp['models']['PWIDE'].predict(xw)
    te['r_base']=te.e_true-te.mu_oof;te['r_pcir']=te.r_base-te.dhat_pcir;te['r_pwide']=te.r_base-te.dhat_pwide
    # H4 domain classifier: held vs training-route packets, cross-fitted
    tr=D[D.route!=H];X=pd.concat([P.feats(te,pp['medians']['PCIR']),P.feats(tr,pp['medians']['PCIR'])],ignore_index=True)
    y=np.r_[np.ones(len(te)),np.zeros(len(tr))]
    clf=HistGradientBoostingClassifier(max_iter=200,learning_rate=.05,max_leaf_nodes=17,random_state=20261023)
    pr=cross_val_predict(clf,X,y,cv=StratifiedKFold(5,shuffle=True,random_state=0),method='predict_proba')[:,1]
    auc=float(roc_auc_score(y,pr));te['domain_score']=pr[:len(te)]
    te['fp_layer']=np.select([te.fp_shift_tap==0,te.fp_shift_tap.abs()==1],['0','|1|'],'>=2')
    te['dtrue_bin']=pd.cut(te.r_base,[-np.inf,-.2,-.05,.05,.2,np.inf],labels=['<-0.2','-0.2..-0.05','|.|<0.05','0.05..0.2','>0.2']).astype(str)
    te['domain_q']=qbin(te.domain_score);te['dist_q']=qbin(te.dist);te['absg_q']=qbin(te.g.abs())
    rows=[]
    for col,lab in (('case','case'),('fp_layer','fp_shift'),('dtrue_bin','delta_true'),('domain_q','domain_score'),('dist_q','anchor_distance'),('absg_q','abs_g')):
        rows+=strata_table(te,col,H,lab)
    rows+=strata_table(te.assign(all='all'),'all',H,'all')
    # H1 target mismatch summary
    h1={'held':H,'train_routes':trr,'domain_auc':auc,'mean_e':float(te.e_true.mean()),'mean_mu_oof':float(te.mu_oof.mean()),
        'mean_delta_true_oof':float(te.r_base.mean()),'mean_dhat_pcir':float(te.dhat_pcir.mean()),'mean_dhat_pwide':float(te.dhat_pwide.mean()),
        'mean_r_pcir':float(te.r_pcir.mean()),'mean_r_pwide':float(te.r_pwide.mean()),'rms_r_base':float(np.sqrt(np.mean(te.r_base**2))),
        'rms_r_pwide':float(np.sqrt(np.mean(te.r_pwide**2))),
        'corr_dhat_pwide_vs_delta_oof':float(np.corrcoef(te.dhat_pwide,te.r_base)[0,1])}
    for r in trr:
        ds=te.e_true-te[f'mu_single_{r}']
        h1[f'mean_delta_true_single_{r}']=float(ds.mean());h1[f'mean_mu_oof_minus_single_{r}']=float((te.mu_oof-te[f'mu_single_{r}']).mean())
        h1[f'corr_dhat_pwide_vs_delta_single_{r}']=float(np.corrcoef(te.dhat_pwide,ds)[0,1])
        h1[f'corr_dhat_pwide_vs_mu_oof_minus_single_{r}']=float(np.corrcoef(te.dhat_pwide,te.mu_oof-te[f'mu_single_{r}'])[0,1])
    h1['corr_dhat_pwide_vs_mu_oof']=float(np.corrcoef(te.dhat_pwide,te.mu_oof)[0,1])
    # recursive check on verification-2 trajectories
    rec=[]
    for f in sorted(Path(a.series_dir).rglob('*_LADDER3_SERIES.csv.gz')):
        ser=pd.read_csv(f);cname=ser.case.iloc[0]
        if next(c for c in V.MANIFEST['cases'] if c['id']==cname)['route']!=H:continue
        for bias in ('B0','L2'):
            st=ser[(ser.bias==bias)].sort_values('k');stem=f'{cname}_full_{bias}'
            ids=np.load(V.one(stem+'_TRACE.npz'),allow_pickle=False)['pose_id'];assert len(ids)==len(st)
            tt=te.set_index(['case','pose_id']).loc[[(cname,int(p)) for p in ids]]
            for arm in ('L_BASE','L_PWIDE'):
                acc=st[f'{arm}__acc'].to_numpy(bool);g=st[f'{arm}__gpsi'].to_numpy(float);t=st.t_s.to_numpy()
                eps=(st[f'{arm}__s_clean'].to_numpy()-tt['sL_+0'].to_numpy())
                m=acc&(t>=30);den=np.sum(g[m]**2/tt.V.to_numpy()[m])
                for col in ('fp_layer','dtrue_bin','domain_q'):
                    lab=tt[col].to_numpy()
                    for k in np.unique(lab):
                        mk=m&(lab==k)
                        rec.append({'held':H,'case':cname,'bias':bias,'arm':arm,'stratum_type':col,'stratum':k,'n':int(mk.sum()),
                                    'mean_eps':float(eps[mk].mean()) if mk.any() else np.nan,
                                    'wb_contrib_deg':float(np.sum(g[mk]*eps[mk]/tt.V.to_numpy()[mk])/den) if den>0 else np.nan})
    te[['case','pose_id','fp_shift_tap','fp_layer','dtrue_bin','domain_score','dist','g','V','e_true','mu_oof']+[f'mu_single_{r}' for r in trr]+
       ['dhat_pcir','dhat_pwide','r_base','r_pcir','r_pwide']].to_csv(out/f'{H}_R2DIAG_PACKETS.csv.gz',index=False,compression='gzip')
    pd.DataFrame(rows).to_csv(out/f'{H}_R2DIAG_STRATA.csv',index=False)
    pd.DataFrame(rec).to_csv(out/f'{H}_R2DIAG_RECURSIVE.csv',index=False)
    (out/f'{H}_R2DIAG_H1.json').write_text(json.dumps(h1,indent=2))
    print('R2DIAG_PASS '+json.dumps(h1),flush=True)

if __name__=='__main__':main()
