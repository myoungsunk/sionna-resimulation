#!/usr/bin/env python3
"""Verification 2 teacher: POWER-preserving residual correctors, training routes only.

Target Delta = e_true - mu_POWER(inner OOF). PCIR: CIR features. PWIDE: CIR features + d0 with
delta~U(-20,20) x3 exactly as P1R WIDE. Same HGB and features as P1R. Held route never used.
Inner mu for training route r comes from POWER fitted on the other training route only.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
sys.path.insert(0,str(REPO/'research/PJ_D0_CIR_PRIOR_P1R_20261022'))
import strict_common as S
from strict_common import V
import p1r_eval as P

def fit_p(tr,grid,kind,rng):
    med=tr[P.FEATURES].replace([np.inf,-np.inf],np.nan).median().fillna(0);a=P.feats(tr,med)
    y=tr.delta.to_numpy()
    if kind=='PCIR':return P.mkm().fit(a,y),med
    x,_=P.wide_rows(tr,a,grid,rng);return P.mkm().fit(x,np.tile(y,P.WIDE_REP)),med

def eval_p(m,med,B,grid,kind,rng):
    bb=P.feats(B,med);y=B.delta.to_numpy()
    if kind=='PCIR':return m.predict(bb)-y,np.ones(len(B),int)
    x,_=P.wide_rows(B,bb,grid,rng);return m.predict(x)-np.tile(y,P.WIDE_REP),np.full(len(B),P.WIDE_REP)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--held',required=True,choices=['R2','R4','R5'])
    ap.add_argument('--grid',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    H=a.held;out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    D=P.prepare();grid=P.load_grid(D,a.grid)
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    trr=sorted(set(D.route)-{H});assert len(trr)==2
    D['mu_in']=np.nan;D['V_in']=np.nan
    for r in trr:
        other=[x for x in trr if x!=r];pin=S.power_fit(obs,other,r);pin=pin[pin.channel=='full'].set_index(['case','pose_id'])
        m=D.route==r;key=list(zip(D.case[m],D.pose_id[m]))
        D.loc[m,'mu_in']=pin.loc[key,'mu_s'].to_numpy(float);D.loc[m,'V_in']=pin.loc[key,'Vs'].to_numpy(float)
    tr=D[D.route!=H].copy();assert tr[['mu_in','V_in']].notna().all().all() and (tr.V_in>0).all()
    tr['delta']=tr.e_true-tr.mu_in
    models={};meds={}
    for kind,seed in (('PCIR',0),('PWIDE',17)):
        models[kind],meds[kind]=fit_p(tr,grid,kind,np.random.default_rng(P.SEED[H]*1000+seed))
    loro={k:{'res':[],'V':[],'delta':[]} for k in ('PCIR','PWIDE')}
    for r in trr:
        A=tr[tr.route!=r];B=tr[tr.route==r]
        for kind,seed in (('PCIR',0),('PWIDE',17)):
            rng=np.random.default_rng(P.SEED[H]*1000+100*int(r[1:])+seed)
            m,med=fit_p(A,grid,kind,rng);res,rep=eval_p(m,med,B,grid,kind,rng)
            loro[kind]['res'].append(res);loro[kind]['V'].append(np.repeat(B.V_in.to_numpy(),1) if kind=='PCIR' else np.tile(B.V_in.to_numpy(),P.WIDE_REP))
            loro[kind]['delta'].append(B.delta.to_numpy() if kind=='PCIR' else np.tile(B.delta.to_numpy(),P.WIDE_REP))
    stats={'BASE':{'kappa':float(np.mean(tr.delta**2/tr.V_in)),'mean_delta':float(tr.delta.mean()),'rms_delta':float(np.sqrt(np.mean(tr.delta**2)))}}
    for k,v in loro.items():
        e=np.concatenate(v['res']);Vv=np.concatenate(v['V']);dl=np.concatenate(v['delta']);assert len(e)==len(Vv)==len(dl)
        stats[k]={'kappa':float(np.mean(e*e/Vv)),'loro_mean_resid':float(e.mean()),'loro_rms_resid':float(np.sqrt(np.mean(e*e))),
                  'loro_rms_delta':float(np.sqrt(np.mean(dl*dl))),'loro_R2':float(1-np.mean(e*e)/np.var(dl)),'n':int(len(e))}
    payload={'held':H,'train_routes':trr,'models':models,'medians':meds,'stats':stats,
             'mu_source':'strict inner POWER (other training route only)','features':P.FEATURES}
    joblib.dump(payload,out/f'{H}_PTRAIN.joblib',compress=3)
    info={k:v for k,v in payload.items() if k not in ('models','medians')}
    (out/f'{H}_PTRAIN_QA.json').write_text(json.dumps(info,indent=2))
    print('PTRAIN_PASS '+json.dumps(info),flush=True)

if __name__=='__main__':main()
