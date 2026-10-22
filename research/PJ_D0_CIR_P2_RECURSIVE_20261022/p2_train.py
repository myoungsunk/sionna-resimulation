#!/usr/bin/env python3
"""P2-A teacher fit. Outer held route never used to fit e_s correction or R.

Reuses exact P1R estimator and frozen random seeds. Serialization trusted only from
artifacts produced by this repository and scikit-learn-pinned Actions runtime.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import joblib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/PJ_D0_CIR_PRIOR_P1R_20261022'))
import p1r_eval as P

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--held',required=True,choices=['R2','R4','R5'])
    a.add_argument('--grid',required=True)
    a.add_argument('--out',required=True)
    args=a.parse_args()
    dest=Path(args.out);dest.mkdir(parents=True,exist_ok=True)
    D=P.prepare();grid=P.load_grid(D,args.grid)
    train=D[D.route!=args.held].copy()
    assert set(train.route)==({'R2','R4','R5'}-{args.held})
    # Inner cross-fit calibration EXACTLY as P1R; held route H never supplied.
    R=P.calib_R(train,grid,args.held)
    mc,medc=P.fit_cir(train)
    mn,medn=P.fit_d0(train,grid,'NARROW',np.random.default_rng(P.SEED[args.held]))
    mw,medw=P.fit_d0(train,grid,'WIDE',np.random.default_rng(P.SEED[args.held]))
    payload={'held':args.held,'models':{'CIR_ONLY':mc,'WIDE':mw,'NARROW':mn},
             'medians':{'CIR_ONLY':medc,'WIDE':medw,'NARROW':medn},
             'R_cal':R,'R_shared':R['CIR_ONLY'],'feature_columns':P.FEATURES,
             'train_routes':sorted(set(train.route)),'train_cases':sorted(set(train.case))}
    assert args.held not in payload['train_routes']
    assert all(float(v)>0 for v in R.values())
    joblib.dump(payload,dest/f'{args.held}_TRAIN.joblib',compress=3)
    info={k:v for k,v in payload.items() if k not in ('models','medians')}
    info.update(train_n=len(train),tested_route_disjoint=True,
                wide_train_distribution='3 independent U(-20,+20) deg per training row',
                source='P1R p1r_eval.fit_d0, fit_cir, calib_R')
    (dest/f'{args.held}_TRAIN_QA.json').write_text(json.dumps(info,indent=2))
    print('P2_TRAIN_DONE '+json.dumps(info),flush=True)

if __name__=='__main__':main()
