#!/usr/bin/env python3
"""Aggregate frozen M8 far Kriging paired experiment; fail on missing seeds."""
import csv
import json
import sys
from pathlib import Path
import numpy as np

OUT=Path("/home/claude/m8/far_kriging_ab_20261119/explore")
ROUTES=("R2","R4","R5","pooled")
CONDITIONS=("B0","L2_GYRO_ARW")
ARMS=("F2SKRWV","F2SKRWV_FAR_K")
REFS=("H2","H2S")
SEEDS=range(30,50)
RMSE=("xy_rmse_cm","heading_rmse_deg")
METRICS=("xy_rmse_cm","heading_rmse_deg","pose95_coverage",
         "heading95_coverage","xy95_coverage","mean_nees3")
SEED_BOOT=20261119

def save_csv(path, rows):
    if not rows: raise RuntimeError("Nothing to save")
    with path.open("w",newline="") as fp:
        writer=csv.DictWriter(fp, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

def read():
    results={}
    for condition in CONDITIONS:
        for seed in SEEDS:
            path=OUT/condition/f"seed{seed}"/"RESULT.json"
            if not path.is_file():
                raise RuntimeError(f"INCOMPLETE: missing frozen-grid result {path}")
            d=json.loads(path.read_text())
            if (d["condition"],d["seed"])!=(condition,seed):
                raise RuntimeError(f"Mismatch: {path}")
            if d["frozen_parity_max_abs"]>1e-8:
                raise RuntimeError(f"PARITY_FAIL: {path}")
            results[condition,seed]=d
    assert len(results)==40
    return results

def summarize(R):
    detail=[]; decisions=[]; paired=[]
    for cond in CONDITIONS:
        for seed in SEEDS:
            d=R[cond,seed]
            for route in ROUTES:
                for arm in ARMS:
                    row=d["point"][route][arm]
                    detail.append(dict(condition=cond,seed=seed,route=route,arm=arm,
                                       **{k:row[k] for k in METRICS}))
        for ref in REFS:
            for arm in ARMS:
                rr=[R[cond,seed]["seed_assessments"][ref][arm] for seed in SEEDS]
                nij=[sum(bool(x[f]) for x in rr) for f in ("I_seed","A_seed","J_seed")]
                mirrors=sum(x["mirror_fail"] for x in rr)
                decisions.append(dict(condition=cond,reference=ref,arm=arm,
                    n=20,N_I=nij[0],N_A=nij[1],N_J=nij[2],mirror_passages=mirrors,
                    condition_pass=(nij[2]>=18 and mirrors==0)))
        for route in ROUTES:
            rng=np.random.default_rng(SEED_BOOT)
            for metric in RMSE:
                old=np.array([R[cond,seed]["point"][route][ARMS[0]][metric] for seed in SEEDS])
                new=np.array([R[cond,seed]["point"][route][ARMS[1]][metric] for seed in SEEDS])
                if not (np.isfinite(old).all() and np.isfinite(new).all() and (old>0).all()):
                    raise RuntimeError("Invalid RMSE")
                ratio=new/old
                draw=rng.integers(0,len(old),size=(10000,len(old)))
                medians=np.median(ratio[draw],axis=1)
                paired.append(dict(condition=cond,route=route,metric=metric,n=20,
                    baseline_median=float(np.median(old)),
                    far_kriging_median=float(np.median(new)),
                    paired_ratio_median=float(np.median(ratio)),
                    ratio_CI95_lo=float(np.quantile(medians,.025)),
                    ratio_CI95_hi=float(np.quantile(medians,.975)),
                    seeds_improved=int((ratio<1).sum()),
                    seeds_worsened=int((ratio>1).sum())))
    return detail, decisions, paired

def main():
    R=read()
    detail,decisions,paired=summarize(R)
    out=OUT.parent/"summary"
    out.mkdir(parents=True,exist_ok=True)
    for name,records in (("FAR_AB_POINTS.csv",detail),
                         ("FAR_AB_DECISIONS.csv",decisions),
                         ("FAR_AB_PAIRED.csv",paired)):
        save_csv(out/name,records)
    with (out/"SUMMARY.json").open("w") as fp:
        json.dump(dict(status="EXECUTED_WITH_BASELINE_PARITY",n=40,
                       conditions=CONDITIONS,seeds=[30,49],arms=ARMS,
                       decisions=decisions,paired=paired,
                       note="Same RT RF realization; seed bootstrap does not imply new scene"),fp,indent=2)
    for c in CONDITIONS:
        print("\n",c)
        for row in decisions:
            if row["condition"]==c: print(row)
        for row in paired:
            if row["condition"]==c and row["route"]=="pooled":print(row)
    print("COMPLETE",out,flush=True)

if __name__=="__main__":
    main()
