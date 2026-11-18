"""Yaw estimation: geometry-based angle-model template versus the shifted-ideal templates.

Same protocol as corridor_case_check.py: the measured ratio |s| at a known yaw is inverted through a template curve; all yaw
candidates are found and the one nearest the true yaw is the estimate (ambiguity assumed resolved), so the error isolates
template mismatch.  Fitted templates use leave-one-yaw-out (18 of 19 points); the angle model needs no fitting at all.

Templates
  ideal            |cos 2 yaw|
  shift_xyA        ideal with fitted x-shift, y-shift and amplitude          (fitted on the measured curve)
  shift_los_params the same shape with the LoS fit's parameters               (a priori, needs the LoS fit)
  angle_model      LoS curve from the TX+RX angles of the coordinate           (a priori, coordinates only)
  angle_model_cal  angle model with a fitted yaw offset, offset and gain       (leave-one-out calibration)
Also: sensitivity of the angle model to a coordinate error.

  python scripts/corridor_template_compare.py
"""
from __future__ import annotations

import argparse
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
import corridor_tx_angle_sweep as ta  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

YAWS = sf.YAWS
# The angle model is built on -20..200 deg so that a calibration shift of up to 20 deg never leaves the computed range
# (outside it a clamped, flat template would create fake yaw candidates).
DENSE = np.arange(-40, 401) / 2.0
GRIDX = np.arange(-200, 2001) / 10.0
IN180 = (GRIDX >= -1e-9) & (GRIDX <= 180.0 + 1e-9)


def angles_for(setup, x, y):
    a = setup.anchor_position
    dz = a[2] - setup.robot_antenna_z_m
    dx, dy = x - a[0], y - a[1]
    d_h = float(np.hypot(dx, dy))
    theta = float(np.degrees(np.arctan2(d_h, dz)))
    alpha = float(np.degrees(np.arctan2(dy, dx))) if d_h > 1e-9 else 0.0
    return theta, -alpha, float(np.hypot(d_h, dz))


def model_curve(banks, setup, x, y, tn):
    """Signed ratio of the angle model on the dense yaw grid, interpolated to the 0.1 deg inversion grid."""
    theta, phi, rng = angles_for(setup, x, y)
    ta.LINK_M = rng
    s = np.array(ta.one(banks, np.radians(theta), np.radians(phi), rx_actual=True, tx_actual=True, yaws=DENSE)[tn]["s"])
    ext = np.interp(GRIDX, DENSE, s)
    return ext[IN180], ext


def err_from_curve(s_meas, curve_abs):
    err = []
    for k, yaw in enumerate(YAWS):
        cand = cc.invert(abs(s_meas[k]), curve_abs)
        err.append(float(cand[np.argmin(np.abs(cand - yaw))] - yaw))
    return np.array(err)


def calibrated_errors(s_meas, sm_pair):
    s_model_grid, s_ext = sm_pair
    """Angle model with fitted (yaw offset, B', A'): s ~ B' + A' * s_model(yaw - delta); leave-one-yaw-out."""
    err = []
    for k, yaw in enumerate(YAWS):
        idx = np.array([i for i in range(len(YAWS)) if i != k])
        best = None
        for delta in np.arange(-20.0, 20.01, 0.5):
            m = np.interp(YAWS[idx] - delta, GRIDX, s_ext)
            X = np.stack([np.ones_like(m), m], 1)
            w, *_ = np.linalg.lstsq(X, s_meas[idx], rcond=None)
            r = float(np.sum((X @ w - s_meas[idx]) ** 2))
            if best is None or r < best[0]:
                best = (r, delta, w)
        _, delta, (B, A) = best
        curve = np.abs(B + A * np.interp(cc.GRID - delta, GRIDX, s_ext))
        cand = cc.invert(abs(s_meas[k]), curve)
        err.append(float(cand[np.argmin(np.abs(cand - yaw))] - yaw))
    return np.array(err)


def fit_cal_all(s_meas, s_ext):
    """Calibration (yaw offset, B, A) from all 19 yaws of one curve."""
    best = None
    for delta in np.arange(-20.0, 20.01, 0.5):
        m = np.interp(YAWS - delta, GRIDX, s_ext)
        X = np.stack([np.ones_like(m), m], 1)
        w, *_ = np.linalg.lstsq(X, s_meas, rcond=None)
        r = float(np.sum((X @ w - s_meas) ** 2))
        if best is None or r < best[0]:
            best = (r, float(delta), float(w[0]), float(w[1]))
    return best[1:]


def curves_per_yaw(name, s_meas, sg, d, sm_pair):
    sm, s_ext = sm_pair
    """The template curve (abs, on the 0.1 deg grid) used to estimate each of the 19 yaws (fitted templates leave that yaw out)."""
    out = []
    for k in range(len(YAWS)):
        idx = np.array([i for i in range(len(YAWS)) if i != k])
        if name == "ideal":
            out.append(np.abs(np.cos(2 * cc.GP)))
        elif name == "shift_xyA":
            out.append(cc.template("xyA", cc.fit_template("xyA", s_meas, idx, sg), cc.GP))
        elif name == "shift_los_params":
            out.append(cc.template("xyA", dict(sigma=sg, yaw0=d["fit_los"]["yaw0_deg"], B=d["fit_los"]["B"], A=d["fit_los"]["A"]), cc.GP))
        elif name == "angle_model":
            out.append(np.abs(sm_pair[0]))
        else:  # angle_model_cal
            best = None
            for delta in np.arange(-20.0, 20.01, 0.5):
                m = np.interp(YAWS[idx] - delta, GRIDX, s_ext)
                X = np.stack([np.ones_like(m), m], 1)
                w, *_ = np.linalg.lstsq(X, s_meas[idx], rcond=None)
                r = float(np.sum((X @ w - s_meas[idx]) ** 2))
                if best is None or r < best[0]:
                    best = (r, delta, w)
            _, delta, (B, A) = best
            out.append(np.abs(B + A * np.interp(cc.GRID - delta, GRIDX, s_ext)))
    return out


def decide(curves, s_meas, rule, rng, prior_deg=None, draws=10):
    """Errors under a decision rule: 'oracle' = candidate nearest the true yaw; 'prior' = nearest to a coarse prior yaw (true + U(-prior, prior))."""
    errs, ncand = [], []
    for k, yaw in enumerate(YAWS):
        cand = cc.invert(abs(s_meas[k]), curves[k])
        ncand.append(len(cand))
        if rule == "oracle":
            errs.append(float(cand[np.argmin(np.abs(cand - yaw))] - yaw))
        else:
            for _ in range(draws):
                pr = yaw + rng.uniform(-prior_deg, prior_deg)
                errs.append(float(cand[np.argmin(np.abs(cand - pr))] - yaw))
    return np.array(errs), float(np.mean(ncand))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "TEMPLATE_COMPARE.json")
    ap.add_argument("--sensitivity-m", type=float, nargs="*", default=[0.1, 0.25, 0.5])
    args = ap.parse_args()
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    curves, errs = [], {k: [] for k in ("ideal", "shift_xyA", "shift_los_params", "angle_model", "angle_model_cal")}
    sens = {m: [] for m in args.sensitivity_m}
    rules = {k: dict(ncand=[], prior15=[], prior30=[]) for k in errs}
    store = []
    rng = np.random.default_rng(20261006)
    for p in sorted(shift["positions"], key=lambda q: (q["x"], q["y"])):
        if p["off_boresight_deg"] < 1:
            continue
        for tn in sf.TX:
            d, sg = p["tx"][tn], sf.SIGMA[tn]
            s_meas = np.array(d["s_full"])
            sm = model_curve(banks, setup, p["x"], p["y"], tn)
            e = dict(
                ideal=cc.estimate_errors("ideal", s_meas, sg, loo=False),
                shift_xyA=cc.estimate_errors("xyA", s_meas, sg, loo=True),
                shift_los_params=np.array([float(c[np.argmin(np.abs(c - Y))] - Y) for Y, c in ((Y, cc.invert(abs(s_meas[k]), cc.template("xyA", dict(sigma=sg, yaw0=d["fit_los"]["yaw0_deg"], B=d["fit_los"]["B"], A=d["fit_los"]["A"]), cc.GP))) for k, Y in enumerate(YAWS))]),
                angle_model=err_from_curve(s_meas, np.abs(sm[0])),
                angle_model_cal=calibrated_errors(s_meas, sm))
            for k in errs:
                errs[k].append(e[k])
            for k in rules:
                cv = curves_per_yaw(k, s_meas, sg, d, sm)
                rules[k]["ncand"].append(decide(cv, s_meas, "oracle", rng)[1])
                for pr in (15.0, 30.0):
                    rules[k][f"prior{int(pr)}"].append(decide(cv, s_meas, "prior", rng, pr)[0])
            for m in args.sensitivity_m:   # coordinate error: 8 directions, model built at the wrong coordinate, curve measured at the right one
                vals = []
                for ang in np.arange(0, 360, 45):
                    x2, y2 = p["x"] + m * np.cos(np.radians(ang)), p["y"] + m * np.sin(np.radians(ang))
                    vals.append(np.sqrt(np.mean(err_from_curve(s_meas, np.abs(model_curve(banks, setup, x2, y2, tn)[0])) ** 2)))
                sens[m].append(float(np.mean(vals)))
            store.append(dict(x=p["x"], y=p["y"], tn=tn, s_meas=s_meas, ext=sm[1], cal=fit_cal_all(s_meas, sm[1])))
            curves.append(dict(x=p["x"], y=p["y"], tx=tn, off_boresight_deg=p["off_boresight_deg"], **{f"rmse_{k}": float(np.sqrt(np.mean(v[-1] ** 2))) for k, v in errs.items()}))
    # Calibration transfer: the calibration (offset, B, A) of the nearest OTHER coordinate is applied to this coordinate's angle model.
    transfer, tr_prior, dist = [], [], []
    for it in store:
        others = [o for o in store if o["tn"] == it["tn"] and (o["x"], o["y"]) != (it["x"], it["y"])]
        o = min(others, key=lambda q: np.hypot(q["x"] - it["x"], q["y"] - it["y"]))
        delta, B, A = o["cal"]
        curve = np.abs(B + A * np.interp(cc.GRID - delta, GRIDX, it["ext"]))
        transfer.append(err_from_curve(it["s_meas"], curve))
        tr_prior.append(decide([curve] * len(YAWS), it["s_meas"], "prior", rng, 15.0)[0])
        dist.append(float(np.hypot(o["x"] - it["x"], o["y"] - it["y"])))
    tr = np.array(transfer)
    transfer_summary = dict(rmse=float(np.sqrt(np.mean(tr ** 2))), median_abs=float(np.median(np.abs(tr))), within5=float(np.mean(np.abs(tr) <= 5)),
                            prior15_rmse=float(np.sqrt(np.mean(np.concatenate([np.ravel(x) for x in tr_prior]) ** 2))), mean_neighbour_distance_m=float(np.mean(dist)))
    summ = {}
    for k, v in errs.items():
        a = np.array(v)
        summ[k] = dict(rmse=float(np.sqrt(np.mean(a ** 2))), median_abs=float(np.median(np.abs(a))), p90_abs=float(np.percentile(np.abs(a), 90)), max_abs=float(np.abs(a).max()),
                       within5=float(np.mean(np.abs(a) <= 5)), within3=float(np.mean(np.abs(a) <= 3)),
                       rmse_by_yaw=[float(np.sqrt(np.mean(a[:, i] ** 2))) for i in range(a.shape[1])])
    a_m, a_x = np.array(errs["angle_model"]), np.array(errs["shift_xyA"])
    better = int(np.sum(np.sqrt(np.mean(a_m ** 2, axis=1)) < np.sqrt(np.mean(a_x ** 2, axis=1))))
    decision = {}
    for k, v in rules.items():
        decision[k] = dict(mean_candidates=float(np.mean(v["ncand"])))
        for key in ("prior15", "prior30"):
            a = np.concatenate([np.ravel(x) for x in v[key]])
            decision[k][key] = dict(rmse=float(np.sqrt(np.mean(a ** 2))), median_abs=float(np.median(np.abs(a))), within5=float(np.mean(np.abs(a) <= 5)), wrong_branch=float(np.mean(np.abs(a) > 20)))
    out = dict(calibration_transfer=transfer_summary, decision_rules=decision, curves=curves, summary=summ, n_curves=len(curves), angle_model_better_than_shift_xyA_curves=better,
               coordinate_error_sensitivity={str(m): dict(rmse_mean=float(np.sqrt(np.mean(np.square(v)))), per_curve=v) for m, v in sens.items()}, yaw_deg=YAWS.tolist())
    args.out.write_text(json.dumps(out, indent=1))
    for k, v in summ.items():
        print(f"{k:18s} RMSE {v['rmse']:5.2f}  median {v['median_abs']:5.2f}  p90 {v['p90_abs']:5.1f}  max {v['max_abs']:5.1f}  within3 {v['within3']*100:3.0f}%  within5 {v['within5']*100:3.0f}%")
    print("angle model better than shift_xyA on", better, "of", len(curves), "curves")
    for k, v in decision.items():
        print(f"{k:18s} candidates/inversion {v['mean_candidates']:.2f} | prior +-15: RMSE {v['prior15']['rmse']:5.2f} within5 {v['prior15']['within5']*100:3.0f}% wrong-branch(>20) {v['prior15']['wrong_branch']*100:4.1f}% | prior +-30: RMSE {v['prior30']['rmse']:5.2f} wrong-branch {v['prior30']['wrong_branch']*100:4.1f}%")
    print("calibration transfer from the nearest other coordinate:", {k: round(v, 2) for k, v in transfer_summary.items()})
    print("coordinate-error sensitivity (RMSE of the angle-model template):", {m: round(float(np.sqrt(np.mean(np.square(v)))), 2) for m, v in sens.items()})


if __name__ == "__main__":
    main()
