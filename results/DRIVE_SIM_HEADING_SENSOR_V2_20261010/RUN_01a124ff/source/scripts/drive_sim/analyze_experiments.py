"""S6: pre-registered statistics H1-H4 and summary tables from the run_experiments.py output.

  python scripts/drive_sim/analyze_experiments.py --results results/DRIVE_SIM_20261007/S6 --out results/DRIVE_SIM_20261007/S6/ANALYSIS
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import analysis as A  # noqa: E402


def md_table(df: pd.DataFrame, cols=None, floatfmt=3) -> str:
    cols = cols or list(df.columns)
    head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    body = ""
    for _, r in df[cols].iterrows():
        body += "| " + " | ".join(f"{v:.{floatfmt}g}" if isinstance(v, (float, np.floating)) else str(v) for v in r) + " |\n"
    return head + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--x-percent", type=float, default=10.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    df = pd.concat([pd.read_csv(p) for p in sorted(args.results.glob("results_y*_m*.csv"))], ignore_index=True)
    df["error"] = df["error"].fillna("")
    errors = df[df.error != ""]
    main_df = df[(df["filter"] == "ekf") & (df.error == "")]
    report = ["# DRIVE_SIM v1 analysis (simulation only, placeholder parameters; `s` is not q_clean)\n",
              f"runs: {len(df)}; failed runs: {len(errors)}; ekf runs used for H1-H4: {len(main_df)}\n"]
    summary = main_df.groupby(["baseline"]).agg(heading_rmse_median=("heading_rmse_deg", "median"), pos_rmse_median=("pos_rmse_m", "median"),
                                                 wrong_branch_mean=("wrong_branch_frac", "mean"), nees_mean=("nees_mean", "mean"), nis_s_mean=("nis_s_mean", "mean"),
                                                 s_reject_mean=("s_reject_frac", "mean"), probes=("n_probes", "mean"), duration_s=("duration_s", "mean")).reset_index()
    summary.to_csv(args.out / "summary_by_baseline.csv", index=False)
    report += ["## Summary by baseline (EKF, all conditions)\n", md_table(summary), "\n"]
    by_cond = main_df.groupby(["drift_name", "mount_deg", "baseline"]).heading_rmse_deg.median().unstack("baseline")
    by_cond.to_csv(args.out / "heading_rmse_median_by_condition.csv")
    h1 = A.h1(main_df)
    for k, v in h1.items():
        v.to_csv(args.out / f"H1_{k}.csv", index=False)
        report += [f"## H1 ({k}): range+s (P0) vs reference, {int(v.improved.sum())}/{len(v)} conditions improved, {int(v.worse.sum())} worse\n"]
    h2 = A.h2(main_df)
    h2.to_csv(args.out / "H2.csv", index=False)
    report += [f"## H2: s as measurement vs heading inverted from s: {int(h2.improved.sum())}/{len(h2)} improved, {int(h2.worse.sum())} worse\n"]
    h3 = A.h3(main_df)
    h3.to_csv(args.out / "H3.csv", index=False)
    report += [f"## H3 / H3_alt (passive P0, mount 45 vs 0): 45 deg better in {int(h3.improved.sum())}/{len(h3)} conditions (H3), 0 deg better in {int(h3.worse.sum())} (H3_alt)\n"]
    h4 = A.h4(main_df, args.x_percent)
    h4.to_csv(args.out / "H4.csv", index=False)
    report += [f"## H4: largest probe period with wrong-branch upper bound <= {args.x_percent:g} %\n", md_table(h4), "\n"]
    comp = df[(df.error == "") & df.baseline.isin(["range_s_P0", "range_s_P1_T20"])].groupby(["baseline", "filter"]).agg(
        heading_rmse_median=("heading_rmse_deg", "median"), nees_mean=("nees_mean", "mean"), s_reject_mean=("s_reject_frac", "mean")).reset_index()
    comp.to_csv(args.out / "filter_comparison.csv", index=False)
    report += ["## Filter types (EKF vs IEKF/UKF/GSF)\n", md_table(comp), "\n"]
    if len(errors):
        errors.groupby(["baseline", "filter", "error"]).size().reset_index(name="n").to_csv(args.out / "failed_runs.csv", index=False)
        report += [f"## Failed runs: {len(errors)} (see failed_runs.csv)\n"]
    (args.out / "ANALYSIS.md").write_text("\n".join(report), encoding="utf8")
    print("\n".join(report[:3]))


if __name__ == "__main__":
    main()
