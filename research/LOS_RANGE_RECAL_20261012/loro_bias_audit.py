#!/usr/bin/env python3
"""LORO LoS-only detector bias audit. No evaluation truth used in fitting.
Usage: python research/LOS_RANGE_RECAL_20261012/loro_bias_audit.py
Only simulation-derived LoS calibration; NOT independent physical calibration.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
G7=ROOT/"research/V01B_CLOSURE_20261012/G7/out"
OUT=Path(__file__).resolve().parent
OLD_OFFSET_M=-0.5315983906250129
f=pd.read_csv(G7/"01_FEATURES_12.csv",usecols=["case","route","pose_id","range_m"])
l=pd.read_csv(G7/"02_LABELS_EVAL_ONLY_12.csv",usecols=["case","route","pose_id","range_los","true_distance_m"])
d=f.merge(l,on=["case","route","pose_id"],validate="one_to_one")
assert len(d)==16432 and d.notna().all().all()
rows=[]
def rmse(x): return float(np.sqrt(np.mean(np.asarray(x,dtype=float)**2)))
for route in sorted(d.route.unique()):
    tr=d[d.route!=route]
    te=d[d.route==route].copy()
    # Train solely using LoS receiver and calibration truth, never full RF or heldout truth.
    c=float((tr.range_los-tr.true_distance_m).mean())
    b,a=np.polyfit(tr.true_distance_m.to_numpy(),tr.range_los.to_numpy(),1)
    err0=te.range_m-te.true_distance_m
    err_old=te.range_m-OLD_OFFSET_M-te.true_distance_m
    err_const=te.range_m-c-te.true_distance_m
    err_affine=(te.range_m-a)/b-te.true_distance_m
    rows.append(dict(route=route,n=len(te),train_n=len(tr),train_los_offset_m=c,
        train_los_affine_intercept_m=float(a),train_los_affine_slope=float(b),
        rmse_uncal_m=rmse(err0),rmse_existing_m=rmse(err_old),
        rmse_new_los_const_m=rmse(err_const),rmse_new_los_affine_m=rmse(err_affine),
        mean_existing_residual_m=float(err_old.mean()),
        mean_const_residual_m=float(err_const.mean()),
        los_rmse_existing_m=rmse(te.range_los-OLD_OFFSET_M-te.true_distance_m),
        los_rmse_const_m=rmse(te.range_los-c-te.true_distance_m)))
df=pd.DataFrame(rows)
df.to_csv(OUT/"loro_metrics.csv",index=False)
n=df.n.sum()
agg={k:float(np.sqrt(np.sum(df.n*df[k]**2)/n)) for k in
 ("rmse_uncal_m","rmse_existing_m","rmse_new_los_const_m","rmse_new_los_affine_m")}
agg.update(n=int(n),existing_offset_m=OLD_OFFSET_M,folds=rows,
  method="leave-one-route-out, fit on simulation LoS-only calibrated training routes; evaluate full RF held-out route")
(OUT/"loro_summary.json").write_text(json.dumps(agg,indent=2)+"\n")
print(json.dumps(agg,indent=2))
