"""Validate v3.2 grid interpolation using exact node values only where probed."""
from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from itertools import product
import json
from pathlib import Path
import time

import numpy as np

from run_step1 import GRID, dump
from v32_filter import Calibration, candidate_features, fit_e1, training_features, wrap
from v32_grid import ARM, PROBE_SEED, TRAIN_SEED, XY, primary_or_stop
from v32_observation import GridCase, ObservationCase, SEEDS


def aligned_indices(center):
    """Candidate search ±10° plus the full 17-point curvature fit."""
    return np.flatnonzero(np.abs(wrap(GRID - center)) <= 12. + 1e-10)


def padded(rows, yaw_indices):
    curves = np.full((*rows.shape[:-1], len(GRID)), np.nan)
    curves[..., yaw_indices] = rows
    return curves


def exact_training(args):
    root, banks, name = args
    case = ObservationCase(root, name, banks)
    rng = np.random.default_rng(TRAIN_SEED)
    costs, residuals, valid, truth = [], [], [], []
    for group, g in case.groups.items():
        yaw_indices = aligned_indices(g.yaw_deg)
        for seed, (dx, dy) in enumerate(rng.normal(0., .1, (SEEDS, 2))):
            sigma = case.projected_sigma(group, 0, dx, dy)
            c, r = next(case.costs_for_axes(
                group, dx, dy, [sigma], ARM, seeds=slice(seed, seed + 1),
                yaw_indices=yaw_indices,
            ))
            costs.append(padded(c[0], yaw_indices))
            residuals.append(padded(r[0], yaw_indices))
            valid.append(case.n_valid(group, seed))
            truth.append(g.yaw_deg)
    features = training_features(np.asarray(costs), np.asarray(residuals), valid, truth)
    print(f"exact E1 training {name}: {len(truth)} sweeps", flush=True)
    return name, features


def interp_corners(xy, dx, dy):
    ix, tx = GridCase._bracket(xy, dx)
    iy, ty = GridCase._bracket(xy, dy)
    for ox, wx in enumerate((1. - tx, tx)):
        for oy, wy in enumerate((1. - ty, ty)):
            yield ix + ox, iy + oy, wx * wy


def sparse_curves(case, group, seed, dx, dy, xy, sigma_axis, intervals):
    """Evaluate identical grid node curves and blend as the stored GridCase."""
    mids = (sigma_axis[intervals] + sigma_axis[intervals + 1]) / 2
    node_indices = np.union1d(intervals, intervals + 1)
    blend = np.zeros((len(intervals), 2, len(seed), len(GRID)))
    exact = np.full_like(blend, np.nan)
    distinct_groups = np.unique(group)
    corners = tuple(interp_corners(xy, dx, dy))
    for group_id in distinct_groups:
        g = case.groups[group_id]
        yaw_indices = aligned_indices(g.yaw_deg)
        use = np.flatnonzero(group == group_id)
        need = defaultdict(list)
        for i, j, weight in corners:
            for row in use:
                need[(i[row], j[row])].append((row, weight[row]))
        for (ix, iy), contributors in need.items():
            rows, weights = np.asarray(contributors).T
            rows = rows.astype(int)
            values = case.costs_for_axes(
                group_id, xy[ix], xy[iy], sigma_axis[node_indices], ARM,
                yaw_indices=yaw_indices,
            )
            for node, (cost, residual) in zip(node_indices, values):
                # Cache storage is float32. Match the actual file round-trip
                # before blending and use float64 accumulation as GridCase does.
                f32 = np.stack((cost, residual)).astype(np.float32)
                for slot in np.flatnonzero((intervals == node) | (intervals + 1 == node)):
                    blend[slot][:, rows[:, None], yaw_indices] += (
                        .5 * weights[None, :, None] * f32[:, seed[rows], :]
                    )
        for row in use:
            values = case.costs_for_axes(
                group_id, dx[row], dy[row], mids, ARM, seeds=slice(seed[row], seed[row] + 1),
                yaw_indices=yaw_indices,
            )
            for slot, (cost, residual) in enumerate(values):
                exact[slot][:, row, yaw_indices] = np.concatenate((cost, residual))
    return blend, exact


def probe(args):
    root, banks, name, case_number, cal, xy, sigma_axis, intervals = args
    started = time.monotonic()
    case = ObservationCase(root, name, banks)
    rng = np.random.default_rng(PROBE_SEED + case_number)
    group = rng.choice(case.group_ids, 100)
    seed = rng.integers(SEEDS, size=100)
    dx, dy = rng.uniform(-.30, .30, (2, 100))
    truth = np.array([case.groups[g].yaw_deg for g in group])
    nvalid = [case.n_valid(g, s) for g, s in zip(group, seed)]
    blend, exact = sparse_curves(case, group, seed, dx, dy, xy, sigma_axis, intervals)
    reports = []
    for i, (interpolated, direct) in zip(intervals, zip(blend, exact)):
        c = candidate_features(*interpolated, nvalid, truth, 10.)
        d = candidate_features(*direct, nvalid, truth, 10.)
        valid = (c.count > 0) & (d.count > 0)
        yaw = np.abs(wrap(c.yaw_deg[valid, 0] - d.yaw_deg[valid, 0]))
        v0, v1 = (cal.variance(f)[valid, 0] for f in (d, c))
        rv = np.abs(v0 - v1) / np.maximum(np.abs(v0), np.finfo(float).tiny)
        lo, hi = sigma_axis[i:i + 2]
        report = dict(
            yaw_p95=float(np.quantile(yaw, .95)) if len(yaw) else None,
            variance_rel_p95=float(np.quantile(rv, .95)) if len(rv) else None,
            candidate_count_agreement=float(np.mean(c.count == d.count)),
            paired=int(valid.sum()), expected_valid=int(np.sum(np.asarray(nvalid) >= 3)), samples=100, sigma_mid=float((lo + hi) / 2),
            sigma_interval=[float(lo), float(hi)],
        )
        report["passed"] = bool(len(yaw) and report["paired"] == report["expected_valid"] and report["yaw_p95"] <= .25
                                and report["variance_rel_p95"] <= .20
                                and report["candidate_count_agreement"] >= .95)
        reports.append(report)
        print(f"G-INT-a {name} {report}", flush=True)
    print(f"sparse G-INT-a {name} {time.monotonic() - started:.1f}s", flush=True)
    return name, reports


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--banks", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--refine", type=Path)
    p.add_argument("--calibration", type=Path)
    p.add_argument("--only-case", choices=("R2_aA_m0", "R2_aB_m0", "R4_aA_m0",
                                          "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"))
    args = p.parse_args()
    pref = json.loads((args.out / "S1P_OBS_PREFLIGHT.json").read_bytes())
    names = primary_or_stop(pref, args.out)
    axes = {name: np.asarray(pref["sigma_axis"]) for name in names}
    xy = XY
    phase = "sparse_initial"
    if args.refine:
        prior = json.loads(args.refine.read_bytes())
        for name in names:
            failed = [x["sigma_mid"] for x in prior["probes"][name] if not x["passed"]]
            axes[name] = np.sort(np.r_[prior["sigma_by_case"][name], failed])
        xy = np.linspace(-.3, .3, 13)
        phase = "sparse_refined"
    if args.only_case:
        phase += "_" + args.only_case
    result_path = args.out / f"S1P_G_INT_RESULT_{phase}.json"
    cal_path = args.out / f"S1P_ERR_MODEL_LORO_{phase}.json"
    if result_path.exists() or cal_path.exists():
        raise FileExistsError(f"Refusing to overwrite {phase} in {args.out}")
    if args.calibration:
        calibrations = {
            key: Calibration(**values)
            for key, values in json.loads(args.calibration.read_bytes()).items()
        }
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            training = dict(pool.map(exact_training, ((args.inputs, args.banks, n) for n in names)))
        routes = sorted({name.split("_")[0] for name in names})
        calibrations = {
            route: fit_e1([f for name, f in training.items() if name.split("_")[0] != route])
            for route in routes
        }
    dump(cal_path, {route: asdict(cal) for route, cal in calibrations.items()})
    probe_args = []
    for case_number, name in enumerate(names):
        if args.only_case and args.only_case != name:
            continue
        axis = axes[name]
        probe_args.append((args.inputs, args.banks, name, case_number, calibrations[name.split("_")[0]],
                           xy, axis, np.arange(len(axis)-1)))
    reports = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for name, values in pool.map(probe, probe_args):
            reports[name] = values
            dump(args.out / f"S1P_G_INT_{phase}.json", reports)
    passed = all(x["passed"] for values in reports.values() for x in values)
    dump(result_path, dict(
        passed=passed, probes=reports, xy=xy.tolist(), diagnostic_subset=bool(args.only_case),
        sigma_by_case={name: axis.tolist() for name, axis in axes.items()},
        conventions=dict(
            training="seeded XY-P draws, exact projected sigma at k=0",
            probe="fixed in-domain points, sample RF group/seed with replacement, truth-aligned +/-10deg",
            count="after C1; E1 variance comparison at each implementation's winner",
            interpolation="node values rounded to float32, float64 accumulation",
        ),
    ))
    if not passed:
        raise SystemExit("G-INT-a failed")


if __name__ == "__main__":
    main()
