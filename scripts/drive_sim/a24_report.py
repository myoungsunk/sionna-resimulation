"""A24 stage-1 report: variant-vs-F0 tables and seed-paired contrasts from the published A23 rows (F0) and the A24 run outputs.

Reads only result files.  Writes a JSON (all numbers) and a Markdown summary.  The consistency bands, the accuracy co-requisite and the no-harm limits of
REQUESTS/A24_MEASUREMENT_ERROR_STATE_PREREG.md section 4 were approved by the user on 2026-10-10 (A24 rev4); ``--criteria approved`` (default) adds the
P1-P4 verdicts, ``--criteria proposed`` reports the band flags only.  Paired differences use the seeds present for both sides, averaged over drifts, bootstrap over seeds.
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
BANDS = dict(nees_mean=(2.0, 5.0), nees_cov95=(0.90, 0.99), heading_cov95=(0.90, 0.99), nees_tail_lo=(0.0, 0.10), nees_tail_hi=(0.0, 0.10))   # approved by the user 2026-10-10 (A24 rev4)
NO_HARM = dict(nees_upper=1.0, heading_upper_deg=0.10)                                                                                     # approved by the user 2026-10-10
P_ARMS = dict(P1=["S3_ar1", "R3_ar1", "J1_ar_indep"], P2=["A0_real_real"], P3=["A0_real_real"], P4=["M0_Rmatched_Rmatched", "W0_white_white", "S5_iid0"])


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


def verdicts(out, variant="F2"):
    """Approved criteria (A24 rev4).  Consistency of an arm = all five band checks on the arm mean over seeds (mean over drifts).
    P3 co-requisite: neither heading nor position RMSE is worse than F0 with the paired interval entirely above 0.  P4: upper interval bound of
    the paired difference to F0 <= +1.0 NEES and <= +0.10 deg heading RMSE."""
    res = dict(variant=variant)
    arms = out["arms"].get(variant, {})
    cons = {a: all(band_flags(r).values()) and len(band_flags(r)) == len(BANDS) for a, r in arms.items()}
    cont = out["contrasts"].get(variant + "-F0", {})
    worse = lambda c, m: bool(np.isfinite(c[m]["lo"]) and c[m]["lo"] > 0)  # noqa: E731
    res["P1_positive_control_consistent"] = {a: cons.get(a) for a in P_ARMS["P1"]}
    res["P2_A0_consistent"] = {a: cons.get(a) for a in P_ARMS["P2"]}
    res["P3_not_worse_than_F0"] = {a: (None if a not in cont else not worse(cont[a], "heading_rmse_common_deg") and not worse(cont[a], "pos_rmse_common_m")) for a in P_ARMS["P3"]}
    res["P4_no_harm"] = {a: (None if a not in cont else bool(cont[a]["nees_mean"]["hi"] <= NO_HARM["nees_upper"] and cont[a]["heading_rmse_common_deg"]["hi"] <= NO_HARM["heading_upper_deg"])) for a in P_ARMS["P4"]}
    res["consistency_by_arm"] = cons
    return res


def build(f0, variants, drifts_list):
    out = dict(scope="descriptive; seed-paired bootstrap 95% over seeds; per-drift first, then mean over drifts", arms={}, contrasts={}, groups=GROUPS, bands_approved=BANDS, no_harm_approved=NO_HARM)
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
            rec["within_band"] = band_flags(rec)
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
    L = ["# A24 stage 1 — summary (bands and limits approved 2026-10-10; verdicts in the JSON `verdicts` block)", ""]
    for vname, arms in out["arms"].items():
        L += [f"## {vname}", "", "| arm | NEES mean | pose cov95 | heading cov95 | tail lo | tail hi | heading RMSE ° | pos RMSE m | band flags |", "|---|---|---|---|---|---|---|---|---|"]
        for arm, r in arms.items():
            g = lambda m: f"{r[m]['mean']:.3f}" if m in r else "-"  # noqa: E731
            L.append(f"| {arm} | {g('nees_mean')} | {g('nees_cov95')} | {g('heading_cov95')} | {g('nees_tail_lo')} | {g('nees_tail_hi')} | {g('heading_rmse_common_deg')} | {g('pos_rmse_common_m')} | {r['within_band']} |")
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
    ap.add_argument("--criteria", choices=["proposed", "approved"], default="approved", help="approved = the bands and no-harm limits approved by the user on 2026-10-10 (A24 rev4)")
    a = ap.parse_args()
    f0 = load_rows(a.f0, "F0")
    variants = {}
    for spec in a.variant:
        name, paths = spec.split("=", 1)
        variants[name] = load_rows([Path(p) for p in paths.split(",")], name)
    out = build(f0, variants, a.drifts)
    out["criteria_status"] = a.criteria
    if a.criteria == "approved":
        out["verdicts"] = {v: verdicts(out, v) for v in variants}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    a.out.with_suffix(".md").write_text(markdown(out))
    print(markdown(out)[:4000])


if __name__ == "__main__":
    main()
