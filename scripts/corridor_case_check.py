"""Case check for one robot position and anchor TX port.

A. Is the x-shift fit right?  Closed-form fit vs an independent nonlinear fit, vs the measured null positions
   (zero crossings of the signed ratio s), over all curves; plus a synthetic recovery test of the fit itself.
B. How well does ideal + x-shift (+ y-shift, + amplitude) estimate yaw?  Template inversion with leave-one-yaw-out
   (fit on 18 yaws, estimate the 19th), compared with the unshifted ideal curve and with a harmonic template.
C. For the chosen case, which reflections arrive from where the robot's ports look at each yaw, and does their
   polarization match the LoS polarization?  (Jones vectors recovered from the two port amplitudes at each yaw.)

  python scripts/corridor_case_check.py --x 7 --y 0.7 --tx LP_plus45
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_reflection_fit as crf  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
from qclean_uwb.features.reflection_attribution import GROUPS  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

YAWS, PSI = sf.YAWS, sf.PSI
TXI = {"LP_plus45": 0, "LP_minus45": 1}


# ---------------------------------------------------------------- A. shift fit checks
def synthetic_recovery():
    """fit_shift must recover known parameters from noiseless curves, for both TX signs and a range of shifts."""
    worst = 0.0
    for sigma in (-1.0, 1.0):
        for yaw0 in (-30.0, -5.0, 0.0, 12.0, 40.0):
            for B, A in ((0.0, 1.0), (0.15, 0.9), (-0.1, 0.8)):
                s = B + sigma * A * np.cos(2 * np.radians(YAWS - yaw0))
                f = sf.fit_shift(s, sigma)
                worst = max(worst, abs(f["yaw0_deg"] - yaw0), abs(f["B"] - B) * 100, abs(f["A"] - A) * 100)
    return worst


def nonlinear_fit_abs(r, sigma):
    """Independent fit of |B + sigma A cos 2(yaw - yaw0)| directly to the plotted metric |s| (multi-start)."""
    best = None
    for y0 in np.radians(np.arange(-80, 81, 10)):
        for B0 in (-0.2, 0.0, 0.2):
            res = least_squares(lambda p: np.abs(p[0] + sigma * p[1] * np.cos(2 * (PSI - p[2]))) - r, [B0, 0.9, y0])
            if best is None or res.cost < best.cost:
                best = res
    B, A, y0 = best.x
    if A < 0:
        A, y0 = -A, y0 + np.pi / 2
    return float((np.degrees(y0) + 90) % 180 - 90), float(B), float(A), float(np.sqrt(2 * best.cost / len(r)))


def crossings(s):
    """Linear-interpolated zero crossings of the signed ratio over 0..180 deg."""
    out = []
    for k in range(len(s) - 1):
        if s[k] == 0 or s[k] * s[k + 1] < 0:
            out.append(float(YAWS[k] + 10.0 * s[k] / (s[k] - s[k + 1])))
    return out


def crossing_shifts(s, sigma):
    """Null positions relative to the ideal 45 and 135 deg; returns (shift1, shift2) or None if |s| never reaches 0."""
    c = crossings(s)
    if len(c) < 2:
        return None
    c1 = min(c, key=lambda v: abs(v - 45))
    c2 = min(c, key=lambda v: abs(v - 135))
    return c1 - 45.0, c2 - 135.0


# ---------------------------------------------------------------- B. yaw estimation by template inversion
GRID = np.arange(0.0, 180.0 + 1e-9, 0.1)
GP = np.radians(GRID)


def template(model, params, psi):
    sigma = params["sigma"]
    if model == "ideal":
        return np.abs(np.cos(2 * psi))
    if model == "x":
        return np.abs(np.cos(2 * (psi - np.radians(params["yaw0"]))))
    if model == "xy":
        return np.abs(params["B"] + sigma * np.cos(2 * (psi - np.radians(params["yaw0"]))))
    if model == "xyA":
        return np.abs(params["B"] + sigma * params["A"] * np.cos(2 * (psi - np.radians(params["yaw0"]))))
    if model == "harm":
        c = params["c"]
        return np.abs(c[0] + c[1] * np.cos(2 * psi) + c[2] * np.sin(2 * psi) + c[3] * np.cos(psi) + c[4] * np.sin(psi) + c[5] * np.cos(3 * psi) + c[6] * np.sin(3 * psi))
    raise ValueError(model)


def fit_template(model, s, idx, sigma):
    """Fit the template to the signed curve s at yaw indices idx; returns params."""
    psi, s = PSI[idx], s[idx]
    if model == "ideal":
        return dict(sigma=sigma)
    if model == "x":  # shift only: A = 1, B = 0, fit yaw0 on the signed curve
        best = min(((float(np.sum((sigma * np.cos(2 * (psi - np.radians(y0))) - s) ** 2)), y0) for y0 in np.arange(-89.9, 90, 0.1)))
        return dict(sigma=sigma, yaw0=best[1])
    X = np.stack([np.ones_like(psi), np.cos(2 * psi), np.sin(2 * psi)], 1)
    if model in ("xy", "xyA"):
        (B, a, b), *_ = np.linalg.lstsq(X, s, rcond=None)
        A = float(np.hypot(a, b))
        yaw0 = float(np.degrees(0.5 * np.arctan2(sigma * b, sigma * a)))
        if model == "xy":  # amplitude fixed to 1: refit B and yaw0 with A = 1
            best = min(((float(np.sum((B2 + sigma * np.cos(2 * (psi - np.radians(y0))) - s) ** 2)), y0, B2) for y0 in np.arange(-89.9, 90, 0.2) for B2 in np.arange(-0.4, 0.41, 0.02)))
            return dict(sigma=sigma, yaw0=best[1], B=best[2])
        return dict(sigma=sigma, yaw0=yaw0, B=float(B), A=A)
    if model == "harm":
        Xh = np.stack([np.ones_like(psi), np.cos(2 * psi), np.sin(2 * psi), np.cos(psi), np.sin(psi), np.cos(3 * psi), np.sin(3 * psi)], 1)
        c, *_ = np.linalg.lstsq(Xh, s, rcond=None)
        return dict(sigma=sigma, c=c)
    raise ValueError(model)


def invert(r, curve):
    """All local minima of |curve - r| on the grid, as yaw candidates."""
    d = np.abs(curve - r)
    inner = (d[1:-1] <= d[:-2]) & (d[1:-1] <= d[2:])
    cand = list(GRID[1:-1][inner])
    if d[0] <= d[1]:
        cand.append(GRID[0])
    if d[-1] <= d[-2]:
        cand.append(GRID[-1])
    return np.array(cand)


def estimate_errors(model, s, sigma, loo=True):
    """Yaw errors (estimate - true) using the candidate nearest the true yaw (ambiguity assumed resolved)."""
    err = []
    for k in range(len(YAWS)):
        idx = np.array([i for i in range(len(YAWS)) if (i != k or not loo)])
        params = fit_template(model, s, idx, sigma)
        cand = invert(abs(s[k]), template(model, params, GP))
        err.append(float(cand[np.argmin(np.abs(cand - YAWS[k]))] - YAWS[k]))
    return np.array(err)


# ---------------------------------------------------------------- C. reflections vs the robot's look direction
def jones_from_ports(c1, c2, yaw_deg):
    """Ideal-port inversion: [c1; c2] = M(yaw) [Ex; Ey], rows of M are the port axes at 45+yaw and -45+yaw."""
    a1, a2 = np.radians(45.0 + yaw_deg), np.radians(-45.0 + yaw_deg)
    M = np.array([[np.cos(a1), np.sin(a1)], [np.cos(a2), np.sin(a2)]])
    return np.linalg.solve(M, np.array([c1, c2]))


def pol_overlap(e1, e2):
    return float(abs(np.vdot(e1, e2)) ** 2 / (np.vdot(e1, e1).real * np.vdot(e2, e2).real))


def pol_state(e):
    S0 = abs(e[0]) ** 2 + abs(e[1]) ** 2
    S1, S2, S3 = abs(e[0]) ** 2 - abs(e[1]) ** 2, 2 * np.real(e[0] * np.conj(e[1])), -2 * np.imag(e[0] * np.conj(e[1]))
    return float(0.5 * np.degrees(np.arctan2(S2, S1))), float(np.hypot(S1, S2) / S0), float(S3 / S0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=float, default=7.0)
    ap.add_argument("--y", type=float, default=0.7)
    ap.add_argument("--tx", default="LP_plus45")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "CASE_CHECK.json")
    args = ap.parse_args()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    res = dict(case=dict(x=args.x, y=args.y, tx=args.tx), synthetic_worst=synthetic_recovery())
    # ---- A and B over all curves
    A_rows, B_rows = [], {m: [] for m in ("ideal", "x", "xy", "xyA", "harm", "xyA_los_params")}
    for p in shift["positions"]:
        for tn in sf.TX:
            d = p["tx"][tn]
            sg = sf.SIGMA[tn]
            s_full, s_los = np.array(d["s_full"]), np.array(d["s_los"])
            lin = d["fit_full"]
            nl = nonlinear_fit_abs(np.abs(s_full), sg)
            cr = crossing_shifts(s_full, sg)
            A_rows.append(dict(x=p["x"], y=p["y"], tx=tn, lin_yaw0=lin["yaw0_deg"], nl_yaw0=nl[0], lin_B=lin["B"], nl_B=nl[1], null_shift_1=None if cr is None else cr[0],
                               null_shift_2=None if cr is None else cr[1], rmse_lin=lin["rmse_abs"], rmse_nl=nl[3]))
            if p["off_boresight_deg"] < 1:
                continue
            for m in ("ideal", "x", "xy", "xyA", "harm"):
                B_rows[m].append(dict(x=p["x"], y=p["y"], tx=tn, err=estimate_errors(m, s_full, sg).tolist()))
            # template parameters taken from the LoS-only fit (what position + antenna patterns would predict), measured curve = full channel
            fl = d["fit_los"]
            err = []
            for k in range(len(YAWS)):
                cand = invert(abs(s_full[k]), template("xyA", dict(sigma=sg, yaw0=fl["yaw0_deg"], B=fl["B"], A=fl["A"]), GP))
                err.append(float(cand[np.argmin(np.abs(cand - YAWS[k]))] - YAWS[k]))
            B_rows["xyA_los_params"].append(dict(x=p["x"], y=p["y"], tx=tn, err=err))
    res["A"] = A_rows
    sm = {}
    for m, rows in B_rows.items():
        e = np.array([r["err"] for r in rows])
        sm[m] = dict(rmse=float(np.sqrt(np.mean(e ** 2))), median_abs=float(np.median(np.abs(e))), max_abs=float(np.abs(e).max()), within5=float(np.mean(np.abs(e) <= 5)),
                     curves=len(rows), per_curve_rmse=[float(np.sqrt(np.mean(np.square(r["err"])))) for r in rows])
        for r in rows:
            if (r["x"], r["y"], r["tx"]) == (args.x, args.y, args.tx):
                sm[m]["case_err"] = r["err"]
    res["B"] = sm
    # ---- C for the chosen case
    setup = CorridorSetup()
    npz = next(pp for pp in crf.find_inputs() if np.allclose(np.load(pp)["robot_xy_m"], [args.x, args.y]))
    z = np.load(npz)
    Hg, label, order, call, table = crf.group_channels(z, setup)
    Hf = Hg.sum(0)
    from rt_cp_uwb_py.features import extract_first_path
    from rt_cp_uwb_py.rf_channel_closure import contribution_cir
    idx = []
    for k in range(len(YAWS)):
        cir, t = contribution_cir(Hf[k], sf.FREQ)
        pk = np.abs(cir).max(0)
        rx, tx = np.unravel_index(pk.argmax(), pk.shape)
        idx.append(extract_first_path(cir[:, rx, tx], t)[0])
    C = np.zeros((len(GROUPS), len(YAWS), 2, 2), complex)
    for g in range(len(GROUPS)):
        for k in range(len(YAWS)):
            C[g, k] = contribution_cir(Hg[g, k], sf.FREQ)[0][idx[k]]
    t = TXI[args.tx]
    # arrival azimuth at the robot of each first-order reflection (image method), world frame, and the squint azimuth of each port
    a_pos, r_pos = z["anchor_m"], z["robot_antenna_m"]
    from qclean_uwb.features.reflection_attribution import _mirror, planes
    pl = planes(setup.length_m, setup.y_half, setup.height_m)
    arrivals = {}
    for name in ("floor", "ceiling", "wall_y_neg", "wall_y_pos", "end_x_min", "end_x_max"):
        v = r_pos - _mirror(a_pos, pl[name])
        v = v / np.linalg.norm(v)
        arrivals[name] = dict(azimuth_deg=float(np.degrees(np.arctan2(v[1], v[0]))), polar_from_up_deg=float(np.degrees(np.arccos(-v[2]))), delay_excess_ns=float((np.linalg.norm(r_pos - _mirror(a_pos, pl[name])) - np.linalg.norm(r_pos - a_pos)) / sf.C0 * 1e9))
    los = r_pos - a_pos
    arrivals["los"] = dict(azimuth_deg=float(np.degrees(np.arctan2(-los[1], -los[0]))), polar_from_up_deg=float(np.degrees(np.arccos(-los[2] / np.linalg.norm(los)))), delay_excess_ns=0.0)
    # (arrival azimuth is the direction the wave comes FROM, i.e. toward the source image)
    for name in arrivals:
        if name != "los":
            v = r_pos - _mirror(a_pos, pl[name])
            arrivals[name]["from_azimuth_deg"] = float(np.degrees(np.arctan2(-v[1], -v[0])))
    arrivals["los"]["from_azimuth_deg"] = arrivals["los"]["azimuth_deg"]
    rows = []
    for k, yaw in enumerate(YAWS):
        e_los = jones_from_ports(C[0, k, 0, t], C[0, k, 1, t], yaw)
        sl, sf_ = sf.signed(C[0, k:k + 1], t)[0], sf.signed(C.sum(0)[k:k + 1], t)[0]
        row = dict(abs_s_los=float(abs(sl)), abs_s_full=float(abs(sf_)), yaw=float(yaw), port_plus45_beam_azimuth=float((yaw + 41.0 + 180) % 360 - 180), port_minus45_beam_azimuth=float((yaw - 44.0 + 180) % 360 - 180),
                   p1_los_db=float(20 * np.log10(abs(C[0, k, 0, t]))), p2_los_db=float(20 * np.log10(abs(C[0, k, 1, t]))), los_pol=dict(zip(("tilt_deg", "dolp", "s3"), pol_state(e_los))), groups={})
        for g in range(1, len(GROUPS)):
            eg = jones_from_ports(C[g, k, 0, t], C[g, k, 1, t], yaw)
            amp = float(np.linalg.norm(eg) / np.linalg.norm(e_los))
            ph = float(np.degrees(np.angle(np.vdot(e_los, eg))))
            s_los_k = sf.signed(C[0, k:k + 1], t)[0]
            d_abs = float(abs(sf.signed((C[0, k] + C[g, k])[None], t)[0]) - abs(s_los_k))
            row["groups"][GROUPS[g]] = dict(d_abs_s=d_abs, c1_phase_deg=float(np.degrees(np.angle(C[g, k, 0, t] / C[0, k, 0, t]))), c2_phase_deg=float(np.degrees(np.angle(C[g, k, 1, t] / C[0, k, 1, t]))), rel_amp=amp, overlap=pol_overlap(e_los, eg), rel_phase_deg=ph, pol=dict(zip(("tilt_deg", "dolp", "s3"), pol_state(eg))),
                                            c1_over_los=float(abs(C[g, k, 0, t]) / abs(C[0, k, 0, t])), c2_over_los=float(abs(C[g, k, 1, t]) / abs(C[0, k, 1, t])))
        rows.append(row)
    res["C"] = dict(arrivals=arrivals, rows=rows, first_path_tap=[int(i) for i in idx])
    args.out.write_text(json.dumps(res, indent=1))
    print("synthetic worst error (deg / 0.01):", round(res["synthetic_worst"], 6))
    cs = next(r for r in A_rows if (r["x"], r["y"], r["tx"]) == (args.x, args.y, args.tx))
    print("case A:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in cs.items()})
    d_all = np.array([[r["lin_yaw0"], r["nl_yaw0"], 0.5 * (r["null_shift_1"] + r["null_shift_2"]) if r["null_shift_1"] is not None else np.nan] for r in A_rows])
    print("A over all %d curves: median |lin - nonlinear| = %.2f deg; median |lin - mean null shift| = %.2f deg (max %.1f)" % (len(A_rows), np.nanmedian(np.abs(d_all[:, 0] - d_all[:, 1])), np.nanmedian(np.abs(d_all[:, 0] - d_all[:, 2])), np.nanmax(np.abs(d_all[:, 0] - d_all[:, 2]))))
    for m, v in sm.items():
        print(f"B {m:16s} RMSE {v['rmse']:5.2f}  median|e| {v['median_abs']:5.2f}  max {v['max_abs']:5.1f}  within5deg {v['within5']*100:4.0f}%  (case RMSE {np.sqrt(np.mean(np.square(v.get('case_err', [np.nan])))):.2f})")


if __name__ == "__main__":
    main()
