"""Post-hoc gate calculations requested by the A009 audit (audit/mbvar-info-a009-g1g7-20261030, 6998e402).

Reads committed CSV outputs only; it does not re-run or alter any frozen code or result. Not part of any lock
(reviews/ is outside the code_sha256 scope). Writes POSTHOC_A009_GATES.json next to --out.

  python3 posthoc_a009_gate_calc.py --s1v4 results/P2_S1V4_run_<id> [--c3v4 results/P2_C3V4_run_<id>]
         [--btap results/P2_BTAP_run_<id>] [--s1v3 results/P2_S1V3_run_40981032471] --out <dir>

Finding 1 (G2): the S1V4 QA counter combined E's newton_decrement with E''s probe. The state-consistent test is
                dec_A_fixed (at E') <= 1e-10 AND probe_min_dcost (at E') < -tau. Both are reported.
Finding 2 (G4): sample-selection sensitivity: residual rows and independent fields per analysis (all / without
                KINK_P_UNCERTAIN / without kink-at-E' rows) for every (arm, role, cell) used by the H tests.
Finding 3 (G5): full-covariance reproducibility: nees4_C10 (depends on all 10 C10 entries) C3V4 vs S1V4.
Option B:        tap-error counts, heading / XY RMSE, ratio to TAP_ORACLE, field-paired differences with bootstrap CI.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

TAU, DEC_TOL = 0.01, 1e-10
H_CELLS = {"LOW": ("LOWCORR", "POSE_HIGH"), "HIGH": ("LOWCORR", "POSE_HIGH")}


def _b(s):
    return s.astype(str).str.lower().isin(["true", "1"])


def batch(df):
    return df[df.arm.astype(str).str.endswith("_BATCH") & (df.status == "OK")].copy()


def g2(b, label):
    smooth_E = b.newton_decrement <= DEC_TOL
    smooth_Ep = b.dec_A_fixed <= DEC_TOL
    desc = b.probe_min_dcost < -TAU
    out = dict(run=label, rows=int(len(b)),
               qa_counter_as_coded_E_decrement_with_Ep_probe=int((smooth_E & desc).sum()),
               state_consistent_Ep_decrement_with_Ep_probe=int((smooth_Ep & desc).sum()),
               Ep_smooth_rows=int(smooth_Ep.sum()), E_smooth_rows=int(smooth_E.sum()),
               rows_E_smooth_but_Ep_not=int((smooth_E & ~smooth_Ep).sum()))
    if "class_v31" in b:
        out["class_v31_counts"] = b.class_v31.value_counts().to_dict()
        out["class_v31_consistent_with_columns"] = bool(((b.class_v31 == "NOT_CERTIFIED") == desc).all())
        hit = b[smooth_Ep & desc]
        out["state_consistent_hits"] = hit[["field", "role", "cell", "sensor_seed", "arm", "probe_min_dcost", "probe_argmin", "kink_poses_at_E"]].to_dict("records")
    return out


def selection(b):
    """Finding 2: rows and independent fields per (arm, role, cell) under each sample definition."""
    k = _b(b.KINK_P_UNCERTAIN) if "KINK_P_UNCERTAIN" in b else pd.Series(False, index=b.index)
    kink = b.kink_poses_at_E.fillna(0).astype(float) > 0
    defs = {"all": pd.Series(True, index=b.index), "without_KINK_P_UNCERTAIN": ~k, "without_kink_rows": ~kink}
    rows = []
    for (arm, role, cell), d in b.groupby(["arm", "role", "cell"]):
        r = dict(arm=arm, role=role, cell=cell)
        for nm, m in defs.items():
            dd = d[m.loc[d.index]]
            r[f"{nm}_rows"] = int(len(dd)); r[f"{nm}_fields"] = int(dd.field.nunique())
        rows.append(r)
    t = pd.DataFrame(rows)
    used = t[((t.role.isin(["LOW", "HIGH"])) & t.cell.isin(["LOWCORR", "POSE_HIGH"])) | t.role.isin(["REV60", "FWD60"])]
    return t, dict(total_rows={nm: int(m.sum()) for nm, m in defs.items()},
                   min_fields_in_tested_cells={nm: int(used[f"{nm}_fields"].min()) for nm in defs},
                   cells_below_10_fields={nm: used.loc[used[f"{nm}_fields"] < 10, ["arm", "role", "cell", f"{nm}_fields"]].to_dict("records") for nm in defs})


def g5_full_cov(s1v4, c3v4):
    """Finding 3: nees4_C10 agreement between the S1V4 run and its C3V4 re-execution (relative)."""
    a = batch(s1v4).set_index(["field", "role", "cell", "sensor_seed", "arm"])
    c = c3v4.set_index(["field", "role", "cell", "sensor_seed", "arm"])
    j = a[["nees4_C10"]].join(c[["nees4_C10"]], rsuffix="_c3", how="inner")
    rel = (j.nees4_C10 - j.nees4_C10_c3).abs() / j.nees4_C10.abs()
    return dict(rows_compared=int(len(j)), nees4_C10_rel_max=float(rel.max()), nees4_C10_rel_q99=float(rel.quantile(0.99)),
                n_rel_gt_1e3=int((rel > 1e-3).sum()),
                note="nees4_C10 depends on all 10 unique C10 entries; the 10 entries themselves are not in the C3V4 rows "
                     "(frozen c3v4.py), so this is a necessary-not-sufficient check of full-covariance reproducibility")


def boot_mean(x, B=4000, seed=20261030):
    x = np.asarray(x, float); r = np.random.default_rng(seed)
    bs = [x[r.integers(0, len(x), len(x))].mean() for _ in range(B)]
    return float(x.mean()), float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))


def btap(rows):
    b = rows[(rows.status == "OK") & (rows.cond != "EKF")].copy()
    out = dict(tap_errors_per_window=b.groupby("cond").n_tap_errors.agg(["min", "mean", "max"]).to_dict("index"), conditions={})
    for arm in ("IID_BATCH", "ORACLE_CORR_BATCH"):
        base = b[(b.cond == "TAP_ORACLE") & (b.arm == arm)].groupby("field")[["win_head_ms_deg2", "win_xy_ms_cm2"]].mean()
        for cond in ("TAP_ERR_1", "TAP_ERR_4", "TAP_STATE"):
            d = b[(b.cond == cond) & (b.arm == arm)].groupby("field")[["win_head_ms_deg2", "win_xy_ms_cm2"]].mean()
            idx = base.index.intersection(d.index)
            rec = {}
            for col, nm in (("win_head_ms_deg2", "head"), ("win_xy_ms_cm2", "xy")):
                lr = np.log(d.loc[idx, col] / base.loc[idx, col]) / 2          # log RMSE ratio per field
                m, lo, hi = boot_mean(lr)
                rec[f"{nm}_rmse_ratio_vs_oracle"] = dict(est=math.exp(m), lo=math.exp(lo), hi=math.exp(hi), n_fields=int(len(idx)))
                rec[f"{nm}_rmse"] = float(math.sqrt(d[col].mean())); rec[f"{nm}_rmse_oracle"] = float(math.sqrt(base[col].mean()))
            rec["not_certified"] = int((b[(b.cond == cond) & (b.arm == arm)].class_v31 == "NOT_CERTIFIED").sum())
            out["conditions"][f"{arm}|{cond}"] = rec
    e = rows[rows.cond == "EKF"].groupby(["arm", "field"])[["win_head_ms_deg2", "win_xy_ms_cm2"]].mean()
    if len(e):
        st, ot = e.loc["EKF_STATE_TAP"], e.loc["EKF_ORACLE_TAP"]; idx = st.index.intersection(ot.index)
        m, lo, hi = boot_mean(np.log(st.loc[idx, "win_head_ms_deg2"] / ot.loc[idx, "win_head_ms_deg2"]) / 2)
        out["ekf_state_vs_oracle_tap_head_rmse_ratio"] = dict(est=math.exp(m), lo=math.exp(lo), hi=math.exp(hi), n_fields=int(len(idx)))
    out["note"] = "10 % tap error is a controlled synthetic stress, not a receiver error rate"
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--s1v4"); ap.add_argument("--c3v4"); ap.add_argument("--btap"); ap.add_argument("--s1v3")
    ap.add_argument("--out", required=True); a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True); res = {}
    if a.s1v3:
        b3 = batch(pd.read_csv(Path(a.s1v3) / "S1V3_RESULTS_DEV2.csv", low_memory=False))
        res["G2_S1V3_W1"] = int(((b3.newton_decrement <= DEC_TOL) & (b3.probe_min_dcost < -TAU)).sum())
        t3, s3 = selection(b3); t3.to_csv(out / "POSTHOC_SELECTION_S1V3.csv", index=False); res["G4_selection_S1V3"] = s3
    if a.s1v4:
        s4 = pd.read_csv(Path(a.s1v4) / "S1V4_RESULTS_DEV2.csv", low_memory=False); b4 = batch(s4)
        res["G2_S1V4"] = g2(b4, Path(a.s1v4).name)
        t4, s4s = selection(b4); t4.to_csv(out / "POSTHOC_SELECTION_S1V4.csv", index=False); res["G4_selection_S1V4"] = s4s
        dec = json.loads((Path(a.s1v4) / "S1V4_DECISION_DEV2.json").read_text())
        res["G4_power_vs_exclusion"] = dict(A86_convention_outcome=dec.get("A86_convention_outcome"), A86_exclusion_outcome=dec.get("A86_exclusion_outcome"),
                                            power_emitted=not isinstance(dec.get("power"), str),
                                            interpretation="power output is NOT an approval: HOLDOUT2 entry additionally requires A86_exclusion_outcome == EXCLUSION_STABLE or an explicit auditor decision")
        if a.c3v4:
            c4 = pd.read_csv(Path(a.c3v4) / "C3V4_ROWS.csv", low_memory=False)
            res["G5_full_cov_S1V4_vs_C3V4"] = g5_full_cov(s4, c4)
    if a.btap:
        res["BTAP_extended"] = btap(pd.read_csv(Path(a.btap) / "BTAP_RESULTS_DEV2.csv", low_memory=False))
    (out / "POSTHOC_A009_GATES.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float)[:4000])


if __name__ == "__main__":
    main()
