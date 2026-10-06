"""Which axis of the curve does the multipath effect live on?  Calibrate the angle model on the OBSERVABLE |s| only.

Template = |B + A * s_angle_model(yaw - delta)|.  Fitted subsets of (delta = x-shift, B = y-shift, A = amplitude), leave-one-yaw-out,
fit on the 18 other |s| samples.  Yaw error = nearest-to-true candidate (as before).  Also: flat regions versus the two TX ports, and a
joint two-port estimator.

  python scripts/corridor_axis_ablation.py
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_case_check as cc  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

YAWS = sf.YAWS
DELTAS = np.arange(-20.0, 20.01, 0.5)
BS = np.arange(-0.3, 0.301, 0.02)
AS = np.arange(0.6, 1.201, 0.02)


def fit_subset(r_meas, idx, s_ext, use):
    """Grid fit of (delta, B, A) on |s| at yaw indices idx; parameters not in `use` stay at (0, 0, 1)."""
    ds = DELTAS if "x" in use else np.array([0.0])
    bs = BS if "y" in use else np.array([0.0])
    as_ = AS if "A" in use else np.array([1.0])
    best = (np.inf, 0.0, 0.0, 1.0)
    Bg, Ag = np.meshgrid(bs, as_, indexing="ij")
    for d in ds:
        m = np.interp(YAWS[idx] - d, tc.GRIDX, s_ext)                       # (n,)
        pred = np.abs(Bg[..., None] + Ag[..., None] * m[None, None, :])      # (nB, nA, n)
        sse = np.sum((pred - r_meas[idx]) ** 2, axis=-1)
        i = np.unravel_index(np.argmin(sse), sse.shape)
        if sse[i] < best[0]:
            best = (float(sse[i]), float(d), float(Bg[i]), float(Ag[i]))
    return best[1:]


def loo_errors(r_meas, s_ext, use):
    e = []
    for k, yaw in enumerate(YAWS):
        idx = np.array([i for i in range(len(YAWS)) if i != k])
        d, B, A = fit_subset(r_meas, idx, s_ext, use)
        curve = np.abs(B + A * np.interp(cc.GRID - d, tc.GRIDX, s_ext))
        cand = cc.invert(r_meas[k], curve)
        e.append(float(cand[np.argmin(np.abs(cand - yaw))] - yaw))
    return np.array(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "AXIS_ABLATION.json")
    args = ap.parse_args()
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    subsets = [(), ("x",), ("y",), ("A",), ("x", "y"), ("x", "A"), ("y", "A"), ("x", "y", "A")]
    names = {(): "보정 없음 (각도 모델)", ("x",): "x축 이동만", ("y",): "y축 이동만", ("A",): "진폭만", ("x", "y"): "x + y", ("x", "A"): "x + 진폭", ("y", "A"): "y + 진폭", ("x", "y", "A"): "x + y + 진폭"}
    errs = {u: [] for u in subsets}
    joint = {"single_tx_plus45": [], "single_tx_minus45": [], "joint": []}
    flat = []
    n_cand = {k: [] for k in joint}
    glob = {k: [] for k in joint}
    wrap = lambda e: (e + 90.0) % 180.0 - 90.0
    for p in sorted(shift["positions"], key=lambda q: (q["x"], q["y"])):
        if p["off_boresight_deg"] < 1:
            continue
        S = {tn: tc.model_curve(banks, setup, p["x"], p["y"], tn) for tn in sf.TX}
        meas = {tn: np.abs(np.array(p["tx"][tn]["s_full"])) for tn in sf.TX}
        for tn in sf.TX:
            for u in subsets:
                errs[u].append(loo_errors(meas[tn], S[tn][1], u))
        # flat regions and the joint two-port estimator (a-priori angle model, no calibration)
        curves = {tn: np.abs(S[tn][0]) for tn in sf.TX}
        slope = {tn: np.abs(np.gradient(curves[tn], 0.1)) for tn in sf.TX}
        g_joint = np.sqrt(slope[sf.TX[0]] ** 2 + slope[sf.TX[1]] ** 2)
        peaks = {tn: [float(cc.GRID[i]) for i in range(1, len(cc.GRID) - 1) if curves[tn][i] >= curves[tn][i - 1] and curves[tn][i] >= curves[tn][i + 1] and curves[tn][i] > 0.8] for tn in sf.TX}
        flat.append(dict(x=p["x"], y=p["y"], flat_fraction={tn: float(np.mean(slope[tn] < 0.01)) for tn in sf.TX}, flat_fraction_joint=float(np.mean(g_joint < 0.01)),
                         mean_slope={tn: float(np.mean(slope[tn])) for tn in sf.TX}, mean_slope_joint=float(np.mean(g_joint)), peak_yaws=peaks))
        for k, yaw in enumerate(YAWS):
            cost = (meas[sf.TX[0]][k] - curves[sf.TX[0]]) ** 2 + (meas[sf.TX[1]][k] - curves[sf.TX[1]]) ** 2
            inner = (cost[1:-1] <= cost[:-2]) & (cost[1:-1] <= cost[2:])
            cand = list(cc.GRID[1:-1][inner])
            if cost[0] <= cost[1]:  # sweep edges (0 and 180 deg) are valid estimates too
                cand.append(cc.GRID[0])
            if cost[-1] <= cost[-2]:
                cand.append(cc.GRID[-1])
            cand = np.array(cand)
            joint["joint"].append(float(cand[np.argmin(np.abs(cand - yaw))] - yaw))
            n_cand["joint"].append(len(cand))
            # no oracle: take the global minimum of the cost (error wraps at 180 deg)
            glob["joint"].append(float(wrap(cc.GRID[np.argmin(cost)] - yaw)))
            for tn, key in zip(sf.TX, ("single_tx_plus45", "single_tx_minus45")):
                c = cc.invert(meas[tn][k], curves[tn])
                joint[key].append(float(c[np.argmin(np.abs(c - yaw))] - yaw))
                n_cand[key].append(len(c))
                glob[key].append(float(wrap(cc.GRID[np.argmin(np.abs(curves[tn] - meas[tn][k]))] - yaw)))
    summ = {}
    for u in subsets:
        a = np.concatenate(errs[u])
        summ["+".join(u) or "none"] = dict(label=names[u], rmse=float(np.sqrt(np.mean(a ** 2))), median_abs=float(np.median(np.abs(a))), within5=float(np.mean(np.abs(a) <= 5)), max_abs=float(np.abs(a).max()))
    js = {k: dict(rmse=float(np.sqrt(np.mean(np.square(v)))), median_abs=float(np.median(np.abs(v))), within5=float(np.mean(np.abs(v) <= 5)), n=len(v),
                  mean_candidates=float(np.mean(n_cand[k])), global_min_rmse=float(np.sqrt(np.mean(np.square(glob[k])))), global_min_within5=float(np.mean(np.abs(glob[k]) <= 5)),
                  global_min_median=float(np.median(np.abs(glob[k])))) for k, v in joint.items()}
    args.out.write_text(json.dumps(dict(ablation=summ, two_port=js, flat=flat, n_curves=len(errs[()])), indent=1))
    for k, v in summ.items():
        print(f"{v['label']:18s} RMSE {v['rmse']:5.2f}  median {v['median_abs']:5.2f}  within5 {v['within5']*100:3.0f}%")
    for k, v in js.items():
        print(f"two-port {k:18s} oracle RMSE {v['rmse']:5.2f} within5 {v['within5']*100:3.0f}% cand {v['mean_candidates']:.1f} | global-min RMSE {v['global_min_rmse']:5.2f} median {v['global_min_median']:.1f} within5 {v['global_min_within5']*100:3.0f}%")
    print("flat fraction (slope<0.01/deg) mean over positions: single TX+45 %.2f, TX-45 %.2f, joint %.2f" % (np.mean([f["flat_fraction"][sf.TX[0]] for f in flat]), np.mean([f["flat_fraction"][sf.TX[1]] for f in flat]), np.mean([f["flat_fraction_joint"] for f in flat])))


if __name__ == "__main__":
    main()
