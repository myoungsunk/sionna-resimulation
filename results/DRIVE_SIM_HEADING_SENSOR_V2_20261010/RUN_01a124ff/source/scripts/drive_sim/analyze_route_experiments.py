"""A9: statistics for the added routes: H1/H2 per route and anchor, H5 (mount), H6 (loop closure), H7 (anchor A vs B), H4 at 20 and 10 degrees.

  python scripts/drive_sim/analyze_route_experiments.py --results results/DRIVE_SIM_20261007/S6_routes --out results/DRIVE_SIM_20261007/S6_routes/ANALYSIS
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import analysis as A  # noqa: E402

ORDER = ["odom_imu", "gyro_only", "range", "range_s_P0", "range_s_P0_noturn", "range_s_P1_T60", "range_s_P1_T20", "range_s_P1_T10", "inverse_heading_P0"]


def md(df: pd.DataFrame, floatfmt=3) -> str:
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "|".join("---" for _ in df.columns) + "|\n"
    return head + "".join("| " + " | ".join(f"{v:.{floatfmt}g}" if isinstance(v, (float, np.floating)) else str(v) for v in r) + " |\n" for r in df.itertuples(index=False))


def count(d: pd.DataFrame, by):
    g = d.groupby(by).agg(conditions=("improved", "size"), improved=("improved", "sum"), worse=("worse", "sum"), median_rel_improvement=("median_rel_improvement", "median")).reset_index()
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    df = pd.concat([pd.read_csv(p) for p in sorted(args.results.glob("results_R*_a*_m*.csv"))], ignore_index=True)
    df["error"] = df["error"].fillna("")
    ek = df[(df["filter"] == "ekf") & (df.error == "")]
    rep = ["# DRIVE_SIM routes R2/R4/R5, anchors A/B (simulation only, placeholder parameters; `s` is not q_clean)\n",
           f"runs {len(df)}; failed {int((df.error != '').sum())}; EKF runs used {len(ek)}\n"]
    heads = ek.pivot_table(index=["route", "anchor", "mount_deg"], columns="baseline", values="heading_rmse_deg", aggfunc="median").reindex(columns=[c for c in ORDER if c in set(ek.baseline)]).round(2)
    heads.to_csv(args.out / "heading_rmse_median_by_route_anchor_mount.csv")
    rep += ["## heading RMSE median [deg] by route / anchor / mount (EKF, drift and SNR pooled)\n", md(heads.reset_index()), "\n"]
    pos = ek.pivot_table(index=["route", "anchor", "mount_deg"], columns="baseline", values="pos_rmse_m", aggfunc="median").reindex(columns=[c for c in ORDER if c in set(ek.baseline)]).round(2)
    pos.to_csv(args.out / "pos_rmse_median_by_route_anchor_mount.csv")
    rep += ["## position RMSE median [m]\n", md(pos.reset_index()), "\n"]
    clo = ek[ek.baseline.isin(["odom_imu", "gyro_only", "range", "range_s_P0", "range_s_P1_T20", "range_s_P1_T10"])].pivot_table(
        index=["route", "anchor", "mount_deg"], columns="baseline", values="disp_err_m", aggfunc="median").round(3)
    clo.to_csv(args.out / "displacement_error_median.csv")
    rep += ["## displacement (loop-closure) error median [m]: |(x_end - x_start)_est - (x_end - x_start)_true|; for R2 the true displacement is ~0\n", md(clo.reset_index()), "\n"]
    for name, d in A.h1(ek).items():
        d.to_csv(args.out / f"H1_{name}.csv", index=False)
        rep += [f"## H1 ({name}) per route/anchor: conditions improved / worse\n", md(count(d, ["route", "anchor"])), "\n"]
    h2 = A.h2(ek)
    h2.to_csv(args.out / "H2.csv", index=False)
    rep += ["## H2 (s as measurement vs inverted heading)\n", md(count(h2, ["route", "anchor"])), "\n"]
    h5 = A.h3(ek)
    h5.to_csv(args.out / "H5_mount.csv", index=False)
    rep += ["## H5: mount 45 vs 0 (median_rel_improvement > 0: 45 deg better; < 0: 0 deg better). Registered: R4 -> 0 deg better, R2/R5 -> 45 deg better\n",
            md(h5.groupby(["route", "anchor"]).agg(conditions=("improved", "size"), mount45_better=("improved", "sum"), mount0_better=("worse", "sum"), median_rel=("median_rel_improvement", "median")).reset_index()), "\n"]
    h6 = A.h6_closure(ek)
    h6.to_csv(args.out / "H6_closure.csv", index=False)
    rep += ["## H6: range+s (P0) vs odom+IMU on the displacement error\n", md(count(h6, ["route", "anchor"])), "\n"]
    h7 = A.h7_anchor(ek)
    h7.to_csv(args.out / "H7_anchor.csv", index=False)
    rep += ["## H7 (exploratory): anchor B vs A on heading RMSE of range+s (P0); median_rel_improvement > 0 means B better\n", md(count(h7, ["route"])), "\n"]
    for col, label in (("wrong_branch_frac", "20 deg"), ("wrong_branch_frac_10", "10 deg")):
        h4 = A.h4(ek, 10.0, column=col)
        h4.to_csv(args.out / f"H4_{label.split()[0]}deg.csv", index=False)
        rep += [f"## H4 at {label}: largest probe period with the wrong-branch upper bound <= 10 % (None = P1 never reaches it)\n",
                md(h4.groupby(["route", "anchor", "mount_deg"]).largest_T_ok.apply(lambda s: sorted(set(s.fillna(-1).astype(int)))).reset_index()), "\n"]
    comp = df[(df.error == "") & df.baseline.isin(["range_s_P0", "range_s_P1_T20"])].groupby(["route", "baseline", "filter"]).agg(heading_rmse_median=("heading_rmse_deg", "median"), nees_mean=("nees_mean", "mean")).reset_index()
    comp.to_csv(args.out / "filter_comparison.csv", index=False)
    rep += ["## Filter types\n", md(comp), "\n"]
    (args.out / "ANALYSIS.md").write_text("\n".join(rep), encoding="utf8")
    print("\n".join(rep[:6]))


if __name__ == "__main__":
    main()
