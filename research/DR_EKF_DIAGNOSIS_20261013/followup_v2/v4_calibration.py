"""V4: identify which calibration states create the DR heading uncertainty.

Two independent research diagnostics (NOT deployable algorithms):
  1. Paired subset-oracle ablations: true bg/SF/eps injected into x0 and
     corresponding prior variances constrained, with the frozen step unchanged.
  2. Fisher-information proxy for fixed vs varied wheel-speed motion. The
     proxy ignores shared-input cross covariance C; do not label it a full
     posterior or a guarantee of observability.

python v4_calibration.py --out runs/v4_001 --world gauss_level \
   --routes R2 R4 R5 --levels 0 1 2 --seeds 8000:8032
"""
from __future__ import annotations

import argparse
import dataclasses
import math

import numpy as np

import common as C
import dr_consistency as DC

H = C.H
MASKS = ("none", "bg", "sf", "eps", "bg+sf", "bg+eps", "sf+eps", "bg+sf+eps")
STATE_IDX = {"bg": 3, "sf": 4, "eps": 5}
WORLD = {"b0": "B0", "gauss_level": "A2_3_GAUSS_LEVEL",
         "gauss_default": "A2_3D_GAUSS_DEFAULT"}


def ablation_one(world, mask, route, level, seed, known_wheelbase=False):
    arm = H.ARMS[WORLD[world]]
    inputs, ev, params, truth6 = H.make_world(arm, route, level, seed)
    original = H.make_cfg(arm, level, params)
    p0 = np.asarray(original.p0_std, float)
    x0 = H.initial_state(arm, route, seed, params, p0)
    for key in mask.split("+") if mask != "none" else ():
        if key not in STATE_IDX:
            raise ValueError(f"unknown calibrated state {key}")
        k = STATE_IDX[key]
        x0[k] = truth6[0, k]                   # ORACLE diagnostic only
        p0[k] = H.ORACLE_CAL_STD * H.P0_CAL_DEFAULT[k - 3]
    cfg = dataclasses.replace(
        original, p0_std=tuple(p0),
        known_wheelbase_error=params["wheelbase"] if known_wheelbase
        else original.known_wheelbase_error)
    f = H.F.SensorV2Filter(cfg, None, x0)
    n = len(H.MOT[route]["t"])
    errors = np.empty((n, 3))
    Ppose = np.empty((n, 3, 3))
    for k in range(n):
        if k:
            f.step(inputs["ds_odom"][k], inputs["dtheta_gyro"][k],
                   inputs["dtheta_odom"][k], inputs["dt_s"][k])
        x, P = f.mean_cov()
        e = truth6[k, :3] - x[:3]
        e[2] = float(DC.wrap(e[2]))
        errors[k] = e
        Ppose[k] = P[:3, :3]
    N = DC.nees(errors, Ppose)
    split = DC.heading_conditional_split(errors, Ppose)
    return dict(nees=N, heading=split["heading"], cond_xy=split["cond_xy"],
                pos_error=np.hypot(errors[:, 0], errors[:, 1]),
                yaw_error=errors[:, 2])


def ablation_cell(world, mask, route, level, seeds, known_wheelbase=False):
    runs = [ablation_one(world, mask, route, level, seed, known_wheelbase)
            for seed in seeds]
    t = H.MOT[route]["t"]
    keep = t >= 30
    n = np.stack([r["nees"] for r in runs])
    heading = np.stack([r["heading"] for r in runs])
    xy = np.stack([r["cond_xy"] for r in runs])
    p = np.stack([r["pos_error"] for r in runs])
    yaw = np.stack([r["yaw_error"] for r in runs])
    late_idx = np.flatnonzero(keep)[int(.75 * keep.sum()):]
    mean, last, cover = float(n[:, keep].mean()), float(n[:, late_idx].mean()), \
                        float((n[:, keep] <= 7.814727903251179).mean())
    return dict(world=world, mask=mask, route=route, drift=level, n=len(seeds),
                anees=mean, anees_late25=last, coverage95=cover,
                heading_contribution=float(heading[:, keep].mean()),
                conditional_xy_contribution=float(xy[:, keep].mean()),
                pos_rmse_m=float(np.sqrt(np.mean(p[:, keep]**2))),
                heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(yaw[:, keep]**2)))),
                within_r22_band=bool(2.4 <= mean <= 3.6 and
                                    2.4 <= last <= 3.6 and .92 <= cover <= .98),
                note="Subset-oracle diagnostic, NOT a deployable estimator")


def information_proxy(route, profile="fixed", level=1):
    m = H.MOT[route]
    ds = m["ds"].copy()
    yaw_increments = m["dtheta"].copy()
    if profile not in ("fixed", "vary_speed"):
        raise ValueError(profile)
    if profile == "vary_speed":
        # Perturb only forward steps, preserving total forward distance,
        # turn increments and the zero-motion (spin) samples.
        moving = np.abs(ds) > 1e-12
        u = np.linspace(0, 6 * np.pi, int(moving.sum()))
        factor = 1 + 0.75 * np.sin(u)
        orig = float(np.sum(np.abs(ds[moving])))
        ds[moving] *= factor
        ds[moving] *= orig / np.sum(np.abs(ds[moving]))
    cfg = H.make_cfg(H.ARMS["B0"], level, {"wheelbase": 0.})
    p0 = np.asarray(H.P0_CAL_DEFAULT)
    info = np.zeros((3, 3))
    x_nom = np.zeros(6)
    for k in range(1, len(m["t"])):
        d, g, dt = ds[k], yaw_increments[k], m["dt"][k]
        _, jac, B = H.F.odometry_model(x_nom, d, g, dt, cfg.wheel_base)
        Q = np.diag([cfg.k_s * abs(d), cfg.gyro_N_rad_sqrt_s**2 * dt,
                     cfg.k_theta * abs(g) + cfg.k_stheta * abs(d)])
        R = float(B @ Q @ B)
        if R > 1e-20:
            info += np.outer(jac[3:], jac[3:]) / R
    # Normalize by prior scales before computing eigenvalues/condition.
    Ip = info * np.outer(p0, p0)
    post = np.linalg.inv(np.diag(1/p0**2) + info)
    sd = np.sqrt(np.diag(post))
    corr = post / np.outer(sd, sd)
    eig = np.linalg.eigvalsh(Ip)
    return dict(route=route, speed_profile=profile,
                forward_distance_m=float(np.abs(ds).sum()),
                physical_samples=int(np.count_nonzero(ds)),
                prior_whitened_information_eigenvalues=eig.tolist(),
                weakest_info_eigenvalue=float(eig[0]),
                bg_eps_correlation_proxy=float(corr[0, 2]),
                approximate_bias_posterior_sd_deg_s=float(np.degrees(sd[0])),
                approximation="static local Fisher proxy, NOT correlated posterior",
                limitation="C ignored; changing speed also changes motion/noise distribution")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--world", choices=list(WORLD), default="gauss_level")
    ap.add_argument("--routes", nargs="+", choices=H.ROUTES, default=list(H.ROUTES))
    ap.add_argument("--levels", nargs="+", type=int, choices=H.LEVELS,
                    default=list(H.LEVELS))
    ap.add_argument("--seeds", default="8000:8032")
    ap.add_argument("--masks", nargs="+", choices=MASKS, default=list(MASKS))
    ap.add_argument("--known-wheelbase", action="store_true")
    a = ap.parse_args()
    seeds = C.development_seeds(a.seeds)
    C.git_frozen_spec()
    out = C.new_dir(a.out)
    rows = []
    for route in a.routes:
        for level in a.levels:
            for mask in a.masks:
                row = ablation_cell(a.world, mask, route, level,
                                    seeds, a.known_wheelbase)
                rows.append(row)
                print(route, level, mask, f"ANEES={row['anees']:.4f}")
    information = [information_proxy(route, profile, level=1)
                   for route in a.routes for profile in ("fixed", "vary_speed")]
    C.write_json_new(out / "V4_CALIBRATION_ABLATION.json",
                     dict(status="DEVELOPMENT_DIAGNOSTIC", rows=rows,
                          caveat="Oracle subset interventions change initial information"))
    C.write_json_new(out / "V4_IDENTIFIABILITY_PROXY.json",
                     dict(status="DESCRIPTIVE", rows=information))
    C.write_json_new(out / "V4_MANIFEST.json", C.provenance(
        dict(world=a.world, routes=a.routes, levels=a.levels, masks=a.masks,
             seeds=a.seeds, known_wheelbase=a.known_wheelbase)))


if __name__ == "__main__":
    main()
