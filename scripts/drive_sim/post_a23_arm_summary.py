"""Post-A23 descriptive summary of the published Q1/Q2/joint arm CSVs: per-arm means/medians and seed-paired contrasts (mean over drifts)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

FILES = ("A0_ARMS", "ARMS_controls", "ARMS_q1", "ARMS_q2", "ARMS_joint")
CONTRASTS = (("J2-J1", "J2_ar_corr", "J1_ar_indep"), ("J1-S3", "J1_ar_indep", "S3_ar1"), ("R3-W0", "R3_ar1", "W0_white_white"), ("S3-W0", "S3_ar1", "W0_white_white"),
             ("A0-S8", "A0_real_real", "S8_real"), ("R8-W0", "R8_real", "W0_white_white"), ("J3-S7", "J3_joint_block", "S7_block"), ("S7-W0", "S7_block", "W0_white_white"),
             ("J3-J1", "J3_joint_block", "J1_ar_indep"), ("R5-R8", "R5_realdem", "R8_real"))
METRICS = ("nees_mean", "heading_rmse_common_deg", "pos_rmse_common_m", "nees_cov95", "heading_cov95")


def boot(x, B=4000, seed=20261010):
    rng = np.random.default_rng(seed)
    b = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(B)]
    return dict(mean=float(x.mean()), lo=float(np.percentile(b, 2.5)), hi=float(np.percentile(b, 97.5)), n=int(len(x)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    d = pd.concat([pd.read_csv(a.output_dir / f"{f}.csv") for f in FILES], ignore_index=True)
    d["arm"] = d["arm"].fillna("A0_real_real")
    per_arm = d.groupby("arm").agg(n=("seed", "size"), **{f"{m}_mean": (m, "mean") for m in METRICS}, nees_median=("nees_mean", "median"),
                                   heading_median=("heading_rmse_common_deg", "median"), pos_median=("pos_rmse_common_m", "median"),
                                   nis_s_acc=("nis_s_eval_acc", "mean"), nis_r_acc=("nis_r_eval_acc", "mean"))
    contrasts = {}
    for m in METRICS:
        P = d.pivot_table(index="seed", columns="arm", values=m, aggfunc="mean")
        contrasts[m] = {n: boot((P[x] - P[y]).values) for n, x, y in CONTRASTS}
        contrasts[m]["interaction_J1-S3-R3+W0"] = boot((P.J1_ar_indep - P.S3_ar1 - P.R3_ar1 + P.W0_white_white).values)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(dict(scope="descriptive; exploratory; seed-paired bootstrap over 50 seeds (mean over drifts); no thresholds", per_arm=per_arm.round(4).reset_index().to_dict("records"), contrasts=contrasts), indent=1))
    print(per_arm.round(3).to_string())


if __name__ == "__main__":
    main()
