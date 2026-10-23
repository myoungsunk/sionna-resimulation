#!/usr/bin/env python3
"""Train-only per-packet R_s rule for each arm: R_s,k = kappa_arm * V_s,k (inner POWER V_s).

kappa_arm = mean over training-route LORO residual rows of eps^2 / V_s, where eps is the residual
of the observation that arm feeds to the filter (BASE: e_s - mu_s; CIR/WIDE: e_true - e_hat).
The residual rows are exactly those of P1R calib_R (same models, seeds, rows); their plain mean
square must reproduce the stored constant R_cal (QA). Held route H is never used: V_s for a
training route comes from POWER fitted on the other training route only (strict inner teacher).
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/'research/PJ_DS_GATED_20261021'))
sys.path.insert(0,str(REPO/'research/PJ_D0_CIR_PRIOR_P1R_20261022'))
import strict_common as S
from strict_common import V
import p1r_eval as P

def spearman(a,b):
    ra=pd.Series(a).rank().to_numpy();rb=pd.Series(b).rank().to_numpy();return float(np.corrcoef(ra,rb)[0,1])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--held',required=True,choices=['R2','R4','R5'])
    ap.add_argument('--grid',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    H=a.held;out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    D=P.prepare();grid=P.load_grid(D,a.grid);tr=D[D.route!=H]
    obs=pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    res={k:[] for k in ('BASE','RAW','CIR_ONLY','CIR_PLUS_D0','CIR_PLUS_D0_WIDE')};vs={k:[] for k in res}
    for r in sorted(set(tr.route)):
        other=[x for x in sorted(set(tr.route)) if x!=r];assert len(other)==1 and H not in other+[r]
        pin=S.power_fit(obs,other,r)
        pin=pin[pin.channel=='full'].set_index(['case','pose_id'])
        A=tr[tr.route!=r];B=tr[tr.route==r]
        key=list(zip(B.case,B.pose_id));vb=pin.loc[key,'Vs'].to_numpy(float);mub=pin.loc[key,'mu_s'].to_numpy(float)
        assert np.all(vb>0) and np.isfinite(vb).all()
        res['BASE'].append(B.e_true.to_numpy()-mub);vs['BASE'].append(vb)
        res['RAW'].append(B.e_true.to_numpy());vs['RAW'].append(vb)
        m,med=P.fit_cir(A);res['CIR_ONLY'].append(m.predict(P.feats(B,med))-B.e_true.to_numpy());vs['CIR_ONLY'].append(vb)
        rng=np.random.default_rng(P.SEED[H]*100+int(r[1:]))          # identical stream to P1R calib_R
        for arm,kind,rep in (('CIR_PLUS_D0','NARROW',2),('CIR_PLUS_D0_WIDE','WIDE',P.WIDE_REP)):
            m,med=P.fit_d0(A,grid,kind,rng);bb=P.feats(B,med)
            x,y=P.narrow_rows(B,bb) if kind=='NARROW' else P.wide_rows(B,bb,grid,rng)
            res[arm].append(m.predict(x)-y);vs[arm].append(np.tile(vb,rep))
    ref=json.loads((REPO/'research/PJ_D0_CIR_PRIOR_P1R_20261022/results/P1R_QA.json').read_text())
    ref=next(q['R_cal'] for q in ref['held_route_qa'] if q['held']==H)
    outj={'held':H,'train_routes':sorted(set(tr.route)),'kappa':{},'mse':{},'mse_ref_diff':{},
          'spearman_eps2_vs_Vs':{},'n':{},'rule':'R_s,k = kappa_arm * V_s,k (inner POWER), train routes only'}
    for k in res:
        e=np.concatenate(res[k]);v=np.concatenate(vs[k]);assert len(e)==len(v)
        outj['kappa'][k]=float(np.mean(e*e/v));outj['mse'][k]=float(np.mean(e*e));outj['n'][k]=int(len(e))
        outj['spearman_eps2_vs_Vs'][k]=spearman(e*e,v)
        if k in ref:
            outj['mse_ref_diff'][k]=abs(outj['mse'][k]-float(ref[k]))
            assert outj['mse_ref_diff'][k]<1e-12,('CALIB_R_ROWS_NOT_REPRODUCED',k,outj['mse'][k],ref[k])
    (out/f'{H}_RKAPPA.json').write_text(json.dumps(outj,indent=2))
    print('RKAPPA_PASS '+json.dumps(outj),flush=True)

if __name__=='__main__':main()
