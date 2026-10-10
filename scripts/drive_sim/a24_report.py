"""A24 stage-1 report: variant-vs-F0 tables and seed-paired contrasts from the published A23 rows (F0) and the A24 run outputs.

Reads only result files.  Writes a JSON (all numbers) and a Markdown summary.  No PASS/FAIL label is produced unless ``--criteria approved``
is given; the proposed bands of REQUESTS/A24_MEASUREMENT_ERROR_STATE_PREREG.md section 4 are reported as 'within_proposed_band' flags only
(assistant-proposed, unapproved).  Paired differences use the seeds present for both sides, averaged over drifts, bootstrap over seeds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["arm", "seed", "drift"]
METRICS = ["nees_mean", "nees_cov95", "heading_cov95", "nees_tail_lo", "nees_tail_hi", "heading_rmse_common_deg", "pos_rmse_common_m", "s_reject_frac_eval", "r_reject_frac_eval", "nis_s_eval_acc", "nis_r_eval_acc"]
GROUPS = dict(positive_control=["S3_ar1", "R3_ar1", "J1_ar_indep"], no_harm=["M0_Rmatched_Rmatched", "W0_white_white", "S5_iid0"], in_sample_real=["A0_real_real", "S8_real", "R8_real"],
              model_mismatched=["S4_iid", "S6_realdem", "S7_block", "J3_joint_block"])
BANDS = dict(nees_mean=(2.0, 5.0), nees_cov95=(0.90, 0.99), heading_cov95=(0.90, 0.99), nees_tail_lo=(0.0, 0.10), nees_tail_hi=(0.0, 0.10))   # assistant-proposed, unapproved


def load_rows(paths, variant=None):
    d = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    if "arm" not in d.columns:
        d["arm"] = "A0_real_real"
    d["arm"] = d["arm"].fillna("A0_real_real")
    if "error" in d.columns:
        d = d[d["error"].fillna("") == ""]
    if "baseline" in d.columns:
        d = d[(d["baseline"] == "range_s_P0") & (d["filter"] == "ekf")]
    d = d.drop_duplicates(KEY, keep="first")
    d["variant"] = variant or d.get("variant", "F0")
    return d


def boot(x, B=4000, seed=20261010):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return dict(mean=float("nan"), lo=float("nan"), hi=float("nan"), n=0)
    rng = np.random.default_rng(seed)
    b = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(B)]
    return dict(mean=float(x.mean()), lo=float(np.percentile(b, 2.5)), hi=float(np.percentile(b, 97.5)), n=int(len(x)))


def seed_means(d, arm, metric, drifts=None):
    s = d[d.arm == arm]
    if drifts is not None:
        s = s[s.drift.isin(drifts)]
    return s.groupby("seed")[metric].mean()


def band_flags(summary):
    return {m: bool(BANDS[m][0] <= summary[m]["mean"] <= BANDS[m][1]) for m in BANDS if m in summary and np.isfinite(summary[m]["mean"])}


def build(f0, variants, drifts_list):
    out = dict(scope="descriptive; seed-paired bootstrap 95% over seeds; per-drift first, then mean over drifts", arms={}, contrasts={}, groups=GROUPS, bands_proposed_unapproved=BANDS)
    arms = sorted(set(f0.arm) | {a for v in variants.values() for a in v.arm})
    for vname, v in {"F0": f0, **variants}.items():
        for arm in arms:
            if arm not in set(v.arm):
                continue
            rec = {}
            for m in METRICS + [c for c in v.columns if c.startswith("beta_")]:
                if m in v.columns:
                    rec[m] = boot(seed_means(v, arm, m).values)
            rec["per_drift"] = {int(dr): {m: float(v[(v.arm == arm) & (v.drift == dr)][m].mean()) for m in ("nees_mean", "nees_cov95", "heading_cov95", "heading_rmse_common_deg", "pos_rmse_common_m") if m in v.columns} for dr in drifts_list}
            rec["within_proposed_band_UNAPPROVED"] = band_flags(rec)
            out["arms"].setdefault(vname, {})[arm] = rec
    for vname, v in variants.items():
        for arm in sorted(set(v.arm) & set(f0.arm)):
            c = {}
            common = sorted(set(v[v.arm == arm].drift) & set(f0[f0.arm == arm].drift))        # pair on the drifts both sides have
            for m in METRICS:
                a, b = seed_means(v, arm, m, common), seed_means(f0, arm, m, common)
                idx = a.index.intersection(b.index)
                c[m] = boot((a.loc[idx] - b.loc[idx]).values)
            out["contrasts"].setdefault(vname + "-F0", {})[arm] = c
    return out


def distance_tercile_table(trace_dirs, d3_by_case):
    """Optional: NEES / NIS_s / |heading error| by distance tercile from traces (seeds with traces only)."""
    rows = []
    for label, tdir in trace_dirs.items():
        for f in sorted(Path(tdir).glob("*.npz")):
            z = np.load(f)
            if bool(z["failed"]):
                continue
            case = f.name.split("_m")[0]
            arm = f.name.split("_m0_")[1].rsplit("_s", 1)[0] if "_m0_" in f.name else f.name
            d3 = d3_by_case.get(case)
            if d3 is None:
                continue
            ev = z["t"] >= 30.0
            d = d3[ev]
            nees, err = z["nees"], np.degrees(np.abs(z["err"][ev, 2]))
            k = z["s_log"][:, 0].astype(int)
            nis = np.full(len(z["t"]), np.nan)
            nis[k] = z["s_log"][:, 1]
            nis = nis[ev]
            for lo, hi in ((0, 5), (5, 10), (10, 99)):
                s = (d >= lo) & (d < hi)
                rows.append(dict(variant=label, arm=arm, bin=f"{lo}-{hi}", nees=float(np.nanmean(nees[s])), nis_s=float(np.nanmean(nis[s])), heading_abs_deg=float(err[s].mean()), file=f.name))
    return pd.DataFrame(rows)


def markdown(out):
    L = ["# A24 stage 1 — descriptive summary (no PASS/FAIL; proposed bands are unapproved)", ""]
    for vname, arms in out["arms"].items():
        L += [f"## {vname}", "", "| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | proposed-band flags (unapproved) |", "|---|---|---|---|---|---|---|---|---|"]
        for arm, r in arms.items():
            g = lambda m: f"{r[m]['mean']:.3f}" if m in r else "-"  # noqa: E731
            L.append(f"| {arm} | {g('nees_mean')} | {g('nees_cov95')} | {g('heading_cov95')} | {g('nees_tail_lo')} | {g('nees_tail_hi')} | {g('heading_rmse_common_deg')} | {g('pos_rmse_common_m')} | {r['within_proposed_band_UNAPPROVED']} |")
        L.append("")
    for name, arms in out["contrasts"].items():
        L += [f"## Paired contrast {name} (mean [95% CI], seeds paired, mean over drifts)", "", "| arm | ΔNEES | Δpose cov95 | Δheading cov95 | Δheading RMSE ° | Δpos RMSE m |", "|---|---|---|---|---|---|"]
        for arm, c in arms.items():
            f = lambda m: f"{c[m]['mean']:+.3f} [{c[m]['lo']:+.3f}, {c[m]['hi']:+.3f}]"  # noqa: E731
            L.append(f"| {arm} | {f('nees_mean')} | {f('nees_cov95')} | {f('heading_cov95')} | {f('heading_rmse_common_deg')} | {f('pos_rmse_common_m')} |")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--f0", type=Path, nargs="+", required=True, help="A23 rows: A0_ARMS.csv ARMS_controls.csv ARMS_q1.csv ARMS_q2.csv ARMS_joint.csv")
    ap.add_argument("--variant", nargs="+", required=True, help="NAME=csv[,csv...] e.g. F2=OUT/ARMS_F2.csv")
    ap.add_argument("--drifts", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--criteria", choices=["proposed", "approved"], default="proposed")
    a = ap.parse_args()
    f0 = load_rows(a.f0, "F0")
    variants = {}
    for spec in a.variant:
        name, paths = spec.split("=", 1)
        variants[name] = load_rows([Path(p) for p in paths.split(",")], name)
    out = build(f0, variants, a.drifts)
    out["criteria_status"] = a.criteria
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    a.out.with_suffix(".md").write_text(markdown(out))
    print(markdown(out)[:4000])


if __name__ == "__main__":
    main()
