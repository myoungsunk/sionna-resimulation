"""Can an artifact-severity indicator improve the yaw-matching estimate?

Indicator (observable, no ground truth): I1 = |r(TX+45) - r(TX-45)|, the disagreement of the two anchor
TX ports' FP-power ratios (zero for ideal ports on axis).  Tested: (1) gating by I1, (2) fusing the two TX
ports, (3) leave-one-position-out ridge correction of the signed angle error.  The yaw candidate
nearest the true yaw is used (as in corridor_angle_match.py), so errors isolate distortion.

  python scripts/corridor_artifact_correction.py --sweep-dir results/CORRIDOR_SWEEP_20261006
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from rt_cp_uwb_py.features import extract_first_path  # noqa: E402
from rt_cp_uwb_py.rf_channel_closure import contribution_cir  # noqa: E402
from qclean_uwb.features.angle_match import representative_yaw, wrap180  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

FREQ = 6250400000.0 + 1950000.0 * np.arange(257)
TX = ("LP_plus45", "LP_minus45")
rm = lambda e: float(np.sqrt(np.mean(np.square(e))))


def build_table(sweep: Path, setup: CorridorSetup) -> pd.DataFrame:
    yaws = np.array(setup.yaw_sweep_deg)
    series = {(s["position"], s["tx_port"]): np.array(s["ratio"]) for s in json.loads((sweep / "fp_ratio_series.json").read_text())["series"]}
    rows = []
    for pos, (x, y) in enumerate(setup.example_xy_m):
        H = np.load(sweep / f"pos{pos}" / f"position_{pos}_H.npy")
        geo = setup.link_geometry(x, y, 0.0)
        for k, yaw in enumerate(yaws):
            cir, t = contribution_cir(H[k], FREQ)
            peak = np.abs(cir).max(0)
            rx, tx = np.unravel_index(peak.argmax(), peak.shape)
            idx, _, _ = extract_first_path(cir[:, rx, tx], t)
            e = np.abs(cir) ** 2
            for tp, other in ((TX[0], TX[1]), (TX[1], TX[0])):
                r, ro = series[(pos, tp)][k], series[(pos, other)][k]
                _, err = representative_yaw(r, yaw)
                rows.append(dict(pos=pos, tx=tp, yaw=float(yaw), r=r, I1=abs(r - ro), tail=e[idx + 8:idx + 40].sum() / e[idx:idx + 8].sum(),
                                 fp_db=10 * np.log10(e[idx].sum()), off=geo["anchor_off_boresight_deg"], R=geo["range_m"], err=float(err)))
    df = pd.DataFrame(rows)
    df["abserr"] = df.err.abs()
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-dir", type=Path, default=ROOT / "results" / "CORRIDOR_SWEEP_20261006")
    args = ap.parse_args()
    df = build_table(args.sweep_dir, CorridorSetup())
    far = df[df.pos >= 1]
    out = dict(n=len(df), baseline_rmse_deg=dict(all=rm(df.err), far=rm(far.err), per_position=[rm(df[df.pos == p].err) for p in range(4)]))
    out["indicator_spearman_with_abs_error"] = {
        f: dict(pooled=float(spearmanr(df[f], df.abserr).statistic), far_only=float(spearmanr(far[f], far.abserr).statistic))
        for f in ("I1", "tail", "fp_db", "off", "R")}
    gate = []
    for keep in (100, 75, 50, 25):
        for name, d in (("all", df), ("far", far)):
            sel = d[d.I1 <= np.percentile(d.I1, keep)]
            gate.append(dict(scope=name, keep_percent=keep, n=len(sel), rmse_deg=rm(sel.err), max_abs_deg=float(sel.abserr.max()),
                             kept_by_position=[int((sel.pos == p).sum()) for p in range(4)]))
    out["gating_by_I1"] = gate
    fuse = []
    for (pos, yaw), g in df.groupby(["pos", "yaw"]):
        a, b = g[g.tx == TX[0]].iloc[0], g[g.tx == TX[1]].iloc[0]
        fuse.append(dict(pos=pos, yaw=yaw, e_p=a.err, e_m=b.err, e_mean_ratio=float(representative_yaw((a.r + b.r) / 2, yaw)[1]),
                         e_mean_est=float(wrap180((a.err + b.err) / 2))))
    fuse = pd.DataFrame(fuse)
    fz = lambda d: dict(tx_plus45=rm(d.e_p), tx_minus45=rm(d.e_m), mean_of_ratios=rm(d.e_mean_ratio), mean_of_estimates=rm(d.e_mean_est))
    out["fusion"] = dict(all=fz(fuse), far=fz(fuse[fuse.pos >= 1]), per_position=[fz(fuse[fuse.pos == p]) for p in range(4)])
    reg = {}
    for name, feats in {"I1": ["I1"], "I1+ratio": ["I1", "r"], "I1+ratio+tail+fp_db": ["I1", "r", "tail", "fp_db"], "geometry(off,R)": ["off", "R"]}.items():
        pred = np.zeros(len(df))
        for p in range(4):
            tr, te = (df.pos != p).values, (df.pos == p).values
            X = df[feats].values
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            pred[te] = Ridge(alpha=1.0).fit((X[tr] - mu) / sd, df.err[tr]).predict((X[te] - mu) / sd)
        e = pd.Series(df.err.values - pred, index=df.index)
        reg[name] = dict(all=rm(e), far=rm(e[df.pos >= 1]), per_position=[rm(e[df.pos == p]) for p in range(4)])
    out["lopo_ridge_correction"] = reg
    # Gating within each far position (no cross-position selection effect).
    out["gating_within_position_keep_best_half"] = [
        dict(position=p, baseline=rm(df[df.pos == p].err), kept=rm(df[(df.pos == p) & (df.I1 <= df[df.pos == p].I1.median())].err)) for p in range(4)]
    (args.sweep_dir / "ARTIFACT_CORRECTION.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(dict(baseline=out["baseline_rmse_deg"], spearman=out["indicator_spearman_with_abs_error"]["I1"], fusion_all=out["fusion"]["all"],
                          fusion_far=out["fusion"]["far"], gating_far=[g for g in gate if g["scope"] == "far"], within=out["gating_within_position_keep_best_half"],
                          reg={k: round(v["all"], 2) for k, v in reg.items()}), indent=1, default=float))


if __name__ == "__main__":
    main()
