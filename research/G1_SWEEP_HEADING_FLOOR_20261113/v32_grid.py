"""Primary v3.2 J interpolation verification and cached grid preparation."""
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import numpy as np
from run_step1 import GRID, dump
from v32_filter import candidate_features, training_features, fit_e1, fit_e0, wrap
from v32_observation import GridCase, ObservationCase, write_grid

XY = np.linspace(-.30, .30, 7)
PROBE_SEED = 2026111321
TRAIN_SEED = 2026111301
ARM = "M1-R"

def build_case(args):
    inputs, banks, out, name, arm, xy, sigma = args
    case = ObservationCase(inputs, name, banks)
    started = time.monotonic()
    idx = write_grid(case, out, xy, sigma, arm)
    print("grid", name, arm, time.monotonic()-started, flush=True)
    return idx

def case_calibration(root, banks, out, name, arm):
    case = ObservationCase(root, name, banks)
    grid = GridCase(out, name, arm)
    rng = np.random.default_rng(TRAIN_SEED)
    truth, n_valid, costs, residuals = [], [], [], []
    direct_count = 0
    for group in case.groups:
        offsets = rng.normal(0, .1, (20, 2))
        n = np.arange(20)
        dx, dy = offsets.T
        sig = case.projected_sigma(group, 0, dx, dy)
        c, r = grid.interpolate_batch(group, n, dx, dy, sig)
        for j in np.flatnonzero(~grid.in_bounds(dx, dy, sig)):
            c[j], r[j] = case.direct(group, j, dx[j], dy[j], sig[j], arm)
            direct_count += 1
        costs.append(c)
        residuals.append(r)
        n_valid.extend(case.n_valid(group, j) for j in n)
        truth.extend([case.groups[group].yaw_deg] * 20)
    print("training", name, arm, "direct", direct_count, flush=True)
    return name, training_features(np.vstack(costs), np.vstack(residuals), n_valid, truth)

def train(root, banks, out, names, arm, workers):
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(case_calibration, root, banks, out, name, arm) for name in names]
        features = dict(f.result() for f in futures)
    res = {}
    for route in sorted({c.split("_")[0] for c in names}):
        held_out = [f for c, f in features.items() if c.split("_")[0] != route]
        e1 = fit_e1(held_out)
        res[route] = asdict(e1 if arm == ARM else fit_e0(held_out, e1))
    return res

def build_probe_args(root, banks, out, name, arm, sigma, calibration, case_number):
    return root, banks, out, name, arm, np.asarray(sigma), calibration, case_number

def probe_case(args):
    from v32_filter import Calibration
    root, banks, out, name, arm, sigma, values, case_number = args
    case = ObservationCase(root, name, banks)
    grid = GridCase(out, name, arm)
    cal = Calibration(**values)
    rng = np.random.default_rng(PROBE_SEED + case_number)
    group = rng.choice(case.group_ids, 100)
    seed = rng.integers(20, size=100)
    dx, dy = rng.uniform(-.30, .30, (2, 100))
    truth = np.array([case.groups[g].yaw_deg for g in group])
    # The aligned prior probes local curvature and candidates near the normal
    # 10-degree minimum causal half-window. The cases and points are fixed.
    nvalid = [case.n_valid(g, s) for g, s in zip(group, seed)]
    reports = []
    mids = (sigma[:-1] + sigma[1:]) / 2
    if len(sigma) == 1:
        mids = sigma
    for i, mid in enumerate(mids):
        jc, rc = grid.interpolate_batch(group, seed, dx, dy, mid)
        pairs = [case.direct(g, s, x, y, mid, arm) for g, s, x, y in zip(group, seed, dx, dy)]
        jd, rd = np.asarray(pairs).transpose(1, 0, 2)
        c = candidate_features(jc, rc, nvalid, truth, 10.)
        d = candidate_features(jd, rd, nvalid, truth, 10.)
        valid = (c.count > 0) & (d.count > 0)
        yaw = np.abs(wrap(c.yaw_deg[valid, 0] - d.yaw_deg[valid, 0]))
        v0 = cal.variance(d)[valid, 0]
        v1 = cal.variance(c)[valid, 0]
        rv = np.abs(v0 - v1) / np.maximum(np.abs(v0), np.finfo(float).tiny)
        metric = dict(yaw_p95=float(np.quantile(yaw, .95)) if len(yaw) else None,
                      variance_rel_p95=float(np.quantile(rv, .95)) if len(rv) else None,
                      candidate_count_agreement=float(np.mean(c.count == d.count)),
                      paired=int(valid.sum()), samples=100, sigma_mid=float(mid))
        metric["passed"] = bool(len(yaw) and metric["yaw_p95"] <= .25
                                and metric["variance_rel_p95"] <= .20
                                and metric["candidate_count_agreement"] >= .95)
        metric["sigma_interval"] = [float(sigma[i]), float(sigma[i+1])] if len(sigma) > 1 else None
        reports.append(metric)
        print("G-INT", name, arm, metric, flush=True)
    return name, reports

def primary_or_stop(pref, out):
    names = pref["primary"]
    if len(names) < 4 or {n.split("_")[0] for n in names} != {"R2", "R4", "R5"}:
        dump(out / "S2P_VERDICT.json", dict(verdict="INCOMPLETE", primary_cases=names,
             reason="G-OBS eligibility leaves fewer than four cases or omits a route"))
        raise SystemExit("G-OBS eligibility gate is incomplete")
    return names

def main():
    p = ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--banks", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--grid-dir", type=Path)
    p.add_argument("--probe-only", action="store_true")
    p.add_argument("--refine", type=Path)
    a = p.parse_args()
    pref = json.loads((a.out / "S1P_OBS_PREFLIGHT.json").read_bytes())
    names = primary_or_stop(pref, a.out)
    sigma = np.asarray(pref["sigma_axis"])
    phase = "initial"
    xy = XY
    if a.refine:
        old = json.loads(a.refine.read_bytes())
        failures = {tuple(x["sigma_interval"]) for case in old.values() for x in case if not x["passed"]}
        sigma = np.sort(np.r_[sigma, [sum(interval) / 2 for interval in sorted(failures)]])
        # The 0.10 m position increment is large relative to the sub-tap
        # period. Test the authorized 0.05 m resolution as well on retry.
        xy = np.linspace(-.30, .30, 13)
        phase = "refined"
    grid = a.grid_dir or a.out / f"grid_{phase}"
    if not a.probe_only:
        grid.mkdir(exist_ok=False)
        args = [(a.inputs, a.banks, grid, n, ARM, xy, sigma) for n in names]
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            for _ in pool.map(build_case, args):
                pass
    calibration = train(a.inputs, a.banks, grid, names, ARM, a.workers)
    dump(a.out / f"S1P_ERR_MODEL_LORO_{phase}.json", calibration)
    args = [build_probe_args(a.inputs, a.banks, grid, n, ARM, sigma,
                             calibration[n.split("_")[0]], i) for i, n in enumerate(names)]
    probes = {}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for name, intervals in pool.map(probe_case, args):
            probes[name] = intervals
            dump(a.out / f"S1P_G_INT_{phase}.json", probes)
    passed = all(x["passed"] for intervals in probes.values() for x in intervals)
    dump(a.out / f"S1P_G_INT_RESULT_{phase}.json", dict(passed=passed, grid=str(grid),
         xy=xy.tolist(), sigma=sigma.tolist(), probes=probes,
         conventions=dict(training="seeded XY-P draws, projected sigma at k=0",
                          probe="fixed in-domain points, sample RF group/seed with replacement, truth-aligned +/-10deg",
                          count="after C1; E1 variance comparison at each implementation's winner")))
    if not passed:
        raise SystemExit("G-INT-a failed")

if __name__ == "__main__":
    main()
