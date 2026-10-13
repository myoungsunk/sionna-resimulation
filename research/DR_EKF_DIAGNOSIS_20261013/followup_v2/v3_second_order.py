"""V3: separate second-order mean and covariance terms in the frozen DR dynamics.

The transformed vector is y = [f(x, d-nd, g-ng), h(x,d-nd,g-ng)+no].
All noise/state derivatives are evaluated at the PRE-step state, including
the shared IMU/wheel input noise and the odometry pseudo-measurement.
The second-order delta method for jointly Gaussian u is:
 mean ~= f(mu) + 1/2 tr(H_f Sigma)
 cov  ~= J Sigma J.T + 1/2 tr(H_i Sigma H_j Sigma).
No ad-hoc Q/R/P inflation. Invalid PSD raises an error; no covariance repair.
This is a NEW estimator (research only), not a modification of frozen D6.

Example (development seeds ONLY):
 python v3_second_order.py --out runs/v3_smoke --world gauss_level \
     --routes R4 --levels 0 --seeds 8000:8002 --steps 40
Full routes: --steps 0. New output directory required.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

import common as C
import dr_consistency as DC

H = C.H
MODEL = H.F
METHODS = ("BASE", "MEAN2", "COV2", "BOTH2")
WORLD = {"b0": "B0", "gauss_level": "A2_3_GAUSS_LEVEL",
         "gauss_default": "A2_3D_GAUSS_DEFAULT"}

# x, y derivatives of f are exactly linear; h does not depend on x or y.
ACTIVE = (2, 3, 4, 5, 6, 7, 8)
FLOORS = (1e-3, 2e-6, 2e-5, 2e-5, 1e-6, 1e-7, 1e-6)


def normalized_difference(y, ref):
    out = y - ref
    out[2] = DC.wrap(out[2])
    return out


def transform(u, x, d, gyro, dt, b, b_nom, known):
    """u = [dx_6, nd, ng, no]; output [post-state_6, predicted-odom_1]."""
    state = x + u[:6]
    dd, gg = d - u[6], gyro - u[7]
    new, _, _ = MODEL.transition(state, dd, gg, dt, b)
    h = MODEL.odometry_model(state, dd, gg, dt, b_nom, known)[0] + u[8]
    return np.r_[new, h]


def hessian_numeric(f, Sigma, reference):
    """Central-difference Hessian on nonlinear coordinates only (7 outputs,9 vars)."""
    Hess = np.zeros((7, 9, 9), dtype=float)
    h = np.zeros(9)
    for k, floor in zip(ACTIVE, FLOORS):
        h[k] = min(max(0.10 * math.sqrt(max(float(Sigma[k, k]), 0.0)),
                           floor), 0.04 if k == 2 else float("inf"))
    zero = np.zeros(9)
    val0 = f(zero)
    def eval_at(du):
        # Return consistent local tangent-coordinate outputs for heading.
        return normalized_difference(f(du), reference)
    v0 = eval_at(zero)
    for i in ACTIVE:
        up, um = zero.copy(), zero.copy()
        up[i] += h[i]; um[i] -= h[i]
        Hess[:, i, i] = (eval_at(up) - 2.0 * v0 + eval_at(um)) / (h[i] ** 2)
        for j in ACTIVE:
            if j <= i:
                continue
            aa, ab, ba, bb = (zero.copy() for _ in range(4))
            aa[i] += h[i]; aa[j] += h[j]
            ab[i] += h[i]; ab[j] -= h[j]
            ba[i] -= h[i]; ba[j] += h[j]
            bb[i] -= h[i]; bb[j] -= h[j]
            val = (eval_at(aa) - eval_at(ab) - eval_at(ba) + eval_at(bb)) / (4 * h[i] * h[j])
            Hess[:, i, j] = Hess[:, j, i] = val
    return val0, Hess


def joint_moments(x, P, d, gyro, odom, dt, cfg, method):
    """Joint state/odometry Gaussian moment approximation from PRE-step posterior."""
    if method not in METHODS:
        raise ValueError(method)
    b_nom = cfg.wheel_base
    known = cfg.known_wheelbase_error
    b = b_nom / (1 + known)
    xp, F, G = MODEL.transition(x, d, gyro, dt, b)
    h, Hm, B = MODEL.odometry_model(x, d, gyro, dt, b_nom, known)
    Q = np.diag([cfg.k_s * abs(d), cfg.gyro_N_rad_sqrt_s**2 * dt,
                 cfg.k_theta * abs(odom) + cfg.k_stheta * abs(d)])
    Sigma = np.zeros((9, 9))
    Sigma[:6, :6] = P
    Sigma[6:, 6:] = Q

    # The augmented measurement h is a function of PRE-step calibration.
    J = np.zeros((7, 9))
    J[:6, :6] = F
    J[:6, 6:8] = -G[:, :2]
    J[6, :6] = Hm
    J[6, 6:] = B
    base_mu = np.r_[xp, h]
    base_cov = J @ Sigma @ J.T
    if method == "BASE":
        mean, covariance = base_mu, base_cov
    else:
        f = lambda u: transform(u, x, d, gyro, dt, b, b_nom, known)
        _, Hess = hessian_numeric(f, Sigma, base_mu)
        mean = base_mu.copy()
        covariance = base_cov.copy()
        if method in ("MEAN2", "BOTH2"):
            mean += 0.5 * np.einsum("iab,ba->i", Hess, Sigma, optimize=True)
            mean[2] = float(DC.wrap(mean[2]))
        if method in ("COV2", "BOTH2"):
            # This term accounts for the Gaussian quadratic-form variance,
            # NOT an arbitrary covariance multiplier.
            correction = 0.5 * np.einsum(
                "iab,bc,jcd,da->ij", Hess, Sigma, Hess, Sigma, optimize=True)
            covariance += correction

    covariance = (covariance + covariance.T) / 2
    if not np.isfinite(mean).all() or not np.isfinite(covariance).all():
        raise FloatingPointError("nonfinite joint moments")
    if np.linalg.eigvalsh(covariance).min() < -1e-9:
        raise FloatingPointError("indefinite joint predicted covariance")
    S = float(covariance[6, 6])
    if S <= 1e-20:
        raise FloatingPointError(f"invalid odometry innovation variance {S}")

    status = "disabled"
    pred_m, pred_P = mean[:6].copy(), covariance[:6, :6].copy()
    innov = odom - mean[6]
    if cfg.use_odom_heading:
        if innov**2 / S > H.CHI2_1_999:
            status = "rejected"
        else:
            K = covariance[:6, 6] / S
            mean[:6] += K * innov
            covariance[:6, :6] -= S * np.outer(K, K)
            status = "applied"
    posterior_x = mean[:6].copy()
    posterior_x[2] = float(DC.wrap(posterior_x[2]))
    posterior_P = (covariance[:6, :6] + covariance[:6, :6].T) / 2
    eig = np.linalg.eigvalsh(posterior_P)
    if not np.isfinite(eig).all() or eig.min() <= 0:
        raise FloatingPointError(f"nonpositive posterior covariance {eig.min():.3g}")
    return posterior_x, posterior_P, dict(
        innovation=float(innov), S=S, status=status,
        predicted_mean=pred_m, predicted_cov=pred_P)


def run_episode(world, method, route, level, seed, steps=0):
    """Run own source-isolated estimator; not part of the D6 harness/cache."""
    arm = H.ARMS[WORLD[world]]
    inputs, evaluation, params, truth6 = H.make_world(arm, route, level, seed)
    cfg = H.make_cfg(arm, level, params)
    p0 = np.asarray(cfg.p0_std, float)
    x = H.initial_state(arm, route, seed, params, p0)
    P = np.diag(p0**2)
    n_full = len(inputs["ds_odom"])
    n = n_full if steps == 0 else min(n_full, steps + 1)
    xs = np.empty((n, 6), float)
    Ps = np.empty((n, 6, 6), float)
    statuses = []
    xs[0], Ps[0] = x, P
    for k in range(1, n):
        args = (inputs["ds_odom"][k], inputs["dtheta_gyro"][k],
                inputs["dtheta_odom"][k], inputs["dt_s"][k], cfg, method)
        x, P, info = joint_moments(x, P, *args)
        xs[k], Ps[k] = x, P
        statuses.append(info["status"])
    e = H.errors(truth6[:n], xs)
    d = DC.per_run_diagnostics(e, Ps, H.MOT[route]["pose"][:n, 2])
    return dict(world=world, method=method, route=route, level=level, seed=seed,
                t=H.MOT[route]["t"][:n], errors=e, cov=Ps, est=xs,
                diag=d, statuses=statuses)


def summarize_runs(runs):
    ref = runs[0]
    t = ref["t"]
    keep = t >= 30
    if not keep.any():
        keep = np.ones(len(t), bool)
    n = len(runs)
    N = np.stack([r["diag"]["nees_pose"] for r in runs])
    head = np.stack([r["diag"]["nees_heading"] for r in runs])
    cond = np.stack([r["diag"]["nees_cond_xy"] for r in runs])
    all_E = np.stack([r["errors"] for r in runs])
    late = np.flatnonzero(keep)[int(np.floor(0.75 * keep.sum())):]
    return dict(n_seeds=n, n_steps=len(t), limited_horizon=bool(t[-1] < H.MOT[ref["route"]]["t"][-1]),
                anees=float(N[:, keep].mean()), anees_late25=float(N[:, late].mean()),
                coverage95=float((N[:, keep] <= 7.814727903251179).mean()),
                heading_contribution=float(head[:, keep].mean()),
                conditional_xy_contribution=float(cond[:, keep].mean()),
                pos_rmse_m=float(np.sqrt(np.mean(np.sum(all_E[:, keep, :2]**2, axis=2)))),
                heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(all_E[:, keep, 2]**2)))),
                reject_fraction=float(np.mean([sum(s == "rejected" for s in r["statuses"]) /
                                               max(len(r["statuses"]), 1) for r in runs])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--world", choices=list(WORLD), default="gauss_level")
    ap.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    ap.add_argument("--routes", nargs="+", choices=H.ROUTES, default=["R2"])
    ap.add_argument("--levels", nargs="+", type=int, choices=H.LEVELS, default=[0, 2])
    ap.add_argument("--seeds", default="8000:8002")
    ap.add_argument("--steps", type=int, default=80,
                    help="0 = full route; >0 = limited development smoke")
    a = ap.parse_args()
    seeds = C.development_seeds(a.seeds)
    if a.steps < 0:
        raise ValueError("--steps must be zero (full route) or positive")
    C.git_frozen_spec()
    out = C.new_dir(a.out)
    rows = []
    for route in a.routes:
        for lv in a.levels:
            for method in a.methods:
                runs = [run_episode(a.world, method, route, lv, seed, a.steps)
                        for seed in seeds]
                rows.append(dict(route=route, drift=lv, method=method,
                                 **summarize_runs(runs)))
                print(route, lv, method, rows[-1]["anees"])
    C.write_json_new(out / "V3_SECOND_ORDER_ABLATION.json",
                     dict(status="DEVELOPMENT_ONLY", rows=rows,
                          model="2nd-order Gaussian delta joint state/odom transform",
                          no_covariance_inflation=True,
                          restriction="no D6 claim; analytic/numeric Hessian candidate only"))
    C.write_json_new(out / "V3_MANIFEST.json", C.provenance(
        dict(world=a.world, routes=a.routes, levels=a.levels,
             methods=a.methods, seeds=a.seeds, steps=a.steps)))


if __name__ == "__main__":
    main()
