#!/usr/bin/env python3
"""Ladder 4 teacher: augmentation / d0-information / early-stopping controls, training routes only.

W family (target e_true, P1R/P2-A definition) and P family (target Delta = e_true - mu_inner,
verification-2 definition). Every new model uses the P1R HGB hyperparameters with early_stopping
fixed to False:
  X1      : one row per packet (= previous CIR_ONLY / PCIR, which had early stopping off already)
  X3      : the same rows duplicated 3 times
  SHUF    : 3 rows per packet with the same delta draws as X, d0 column permuted across rows
  D0      : 3 rows per packet, true d0 (same delta draws as the previous WIDE / PWIDE)
kappa (R scale) for P D0 from training-route LORO, same rule as verification 2.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
sys.path.insert(0,str(REPO/'research/PJ_D0_CIR_PRIOR_P1R_20261022'))
import strict_common as S
from strict_common import V
import p1r_eval as P

def mk():
    return HistGradientBoostingRegressor(max_iter=160,learning_rate=.055,max_leaf_nodes=17,max_depth=5,
             min_samples_leaf=20,l2_regularization=1.,random_state=20261022,early_stopping=False)

def rows(tr,target,grid,kind,seed,shuf_seed):
    med=tr[P.FEATURES].replace([np.inf,-np.inf],np.nan).median().fillna(0);a=P.feats(tr,med);y=tr[target].to_numpy()
    if kind=='X1':return a,y,med
    if kind=='X3':return pd.concat([a]*3,ignore_index=True),np.tile(y,3),med
    x,_=P.wide_rows(tr,a,grid,np.random.default_rng(seed))          # identical delta draws to the previous model
    if kind=='SHUF':x['d0']=np.random.default_rng(shuf_seed).permutation(x['d0'].to_numpy())
    return x,np.tile(y,P.WIDE_REP),med

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--held',required=True,choices=['R2','R4','R5'])
    ap.add_argument('--grid',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    H=a.held;out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    D=P.prepare();grid=P.load_grid(D,a.grid);obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    trr=sorted(set(D.route)-{H})
    D['mu_in']=np.nan;D['V_in']=np.nan
    for r in trr:
        other=[x for x in trr if x!=r];pin=S.power_fit(obs,other,r);pin=pin[pin.channel=='full'].set_index(['case','pose_id'])
        m=D.route==r;key=list(zip(D.case[m],D.pose_id[m]))
        D.loc[m,'mu_in']=pin.loc[key,'mu_s'].to_numpy(float);D.loc[m,'V_in']=pin.loc[key,'Vs'].to_numpy(float)
    tr=D[D.route!=H].copy();tr['delta']=tr.e_true-tr.mu_in
    # seeds: W D0 = P2 train (default_rng(SEED)); P D0 = verification-2 ptrain (SEED*1000+17)
    seeds={'W':P.SEED[H],'P':P.SEED[H]*1000+17}
    models={};meds={};info={}
    for fam,target in (('W','e_true'),('P','delta')):
        for kind in ('X1','X3','SHUF','D0'):
            x,y,med=rows(tr,target,grid,kind,seeds[fam],P.SEED[H]*7919+(1 if fam=='W' else 2))
            m=mk().fit(x,y);models[f'{fam}_{kind}']=m;meds[f'{fam}_{kind}']=med
            info[f'{fam}_{kind}']={'n_rows':int(len(y)),'n_iter':int(m.n_iter_),'early_stopping':bool(m.do_early_stopping_),
                                   'has_d0':bool('d0' in x.columns)}
    # kappa for P_D0 (LORO inside training routes, same rule as verification 2)
    res=[];vv=[]
    for r in trr:
        A=tr[tr.route!=r];B=tr[tr.route==r]
        x,y,med=rows(A,'delta',grid,'D0',P.SEED[H]*1000+100*int(r[1:])+17,0);m=mk().fit(x,y)
        bb=P.feats(B,med);xb,_=P.wide_rows(B,bb,grid,np.random.default_rng(P.SEED[H]*1000+100*int(r[1:])+18))
        res.append(m.predict(xb)-np.tile(B.delta.to_numpy(),P.WIDE_REP));vv.append(np.tile(B.V_in.to_numpy(),P.WIDE_REP))
    e=np.concatenate(res);v=np.concatenate(vv);kappa=float(np.mean(e*e/v))
    payload={'held':H,'train_routes':trr,'models':models,'medians':meds,'kappa_P_D0':kappa,'info':info}
    joblib.dump(payload,out/f'{H}_L4TRAIN.joblib',compress=3)
    qa={'held':H,'train_routes':trr,'kappa_P_D0':kappa,'info':info,'loro_rms_P_D0':float(np.sqrt(np.mean(e*e))),'loro_mean_P_D0':float(e.mean())}
    (out/f'{H}_L4TRAIN_QA.json').write_text(json.dumps(qa,indent=2))
    print('L4TRAIN_PASS '+json.dumps(qa),flush=True)

if __name__=='__main__':main()
