"""Nominal DR sigma-beta sensitivities with the S2′ primary CRN sample."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import numpy as np

import run_step2 as legacy
from run_step1 import dump
from v33_filter import simulate
from v33_observation import build_stations
from s2_primary_final import (
    MODELS, GroupedBank, calibration, classify, load, progress, stats, validate_entry,
)

POINTS = (0.0, .08, .16, .24, .32, .40, .45, .56, .64, .72, .80, .88, .93)
TARGET = .8


def shard(args, stations, rho, cal, case, drs, xy, rows, indices):
    bank = GroupedBank(args.inputs, args.banks, args.grid, stations, xy[indices])
    cases = case[indices]
    result = {}
    try:
        for i, model in enumerate(MODELS):
            row = rows[i, indices]
            def curve(k):
                return bank.access(row[:, k], k)
            result[model] = [simulate(curve, dr[indices], cases, list(rho.values()), cal, beta_sd=s)
                             for s, dr in zip(POINTS, drs)]
        return result
    finally:
        bank.close()


def crossings(values):
    result = []
    for (a, x), (b, y) in zip(zip(POINTS, values), zip(POINTS[1:], values[1:])):
        if x == TARGET:
            result.append({"root_deg_per_station": a, "bracket": [a, a], "rule": "observed grid hit"})
        if (x - TARGET) * (y - TARGET) < 0.:
            root = a + (b-a) * (TARGET-x) / (y-x)
            result.append({"root_deg_per_station": root, "bracket": [a, b], "rule": "linear interpolation"})
    if values[-1] == TARGET:
        result.append({"root_deg_per_station": POINTS[-1], "bracket": [POINTS[-1]] * 2,
                       "rule": "observed grid hit"})
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("sensitivity",))
    for name in ("inputs", "banks", "grid", "entry", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--workers", type=int, default=12)
    args = p.parse_args()
    names, rho, _ = validate_entry(args)
    stations = build_stations(args.inputs, args.banks, names)
    cal = calibration(args, names, "M1-R")
    with np.load(args.out / "S2P_DRAWS.npz", allow_pickle=False) as draws:
        case, dr, xy, rows = (draws[k] for k in ("case_index", "dr", "xy", "nominal_rows"))
    rng = np.random.default_rng(2026111303)
    m, n = dr.shape
    _ = rng.standard_normal(m)
    z_beta = rng.standard_normal(m)
    w = .486 * rng.standard_normal((m, n))
    drs = [np.cumsum(s*z_beta[:, None] + w, axis=1) for s in POINTS]
    np.testing.assert_array_equal(drs[POINTS.index(.45)], dr)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        calculate = partial(shard, args, stations, rho, cal, case, drs, xy, rows)
        parts = list(pool.map(calculate, np.array_split(np.arange(m), args.workers)))
    nominal = np.load(args.out / "S2P_NOMINAL.npz", allow_pickle=False)
    outputs = {}
    for model in MODELS:
        metrics = {}
        for i, (s, d) in enumerate(zip(POINTS, drs)):
            run = {k:np.concatenate([part[model][i][k] for part in parts]) for k in parts[0][model][i]}
            if s == .45:
                for k, value in run.items():
                    np.testing.assert_array_equal(value, nominal[f"{model}_{k}"])
            metrics[str(s)] = stats(run, d, case, names)
        ratio = [metrics[str(s)]["ratio_1_to_17"] for s in POINTS]
        outputs[model] = {"metrics": metrics, "crossings": crossings(ratio)}
    import csv
    with (args.out / "S2P_SIGMA_BETA_STAR.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("arm", "model", "status", "root_deg_per_station", "bracket_lo", "bracket_hi"))
        for model, result in outputs.items():
            for x in result["crossings"]:
                writer.writerow(("M1-R(J_joint) x E1", model, x["rule"], x["root_deg_per_station"], *x["bracket"]))
            if not result["crossings"]:
                writer.writerow(("M1-R(J_joint) x E1", model, "no observed crossing", "", POINTS[0], POINTS[-1]))
    dump(args.out / "S2P_SIGMA_BETA.json", dict(target=TARGET, sigma_beta=POINTS,
         estimand="nominal CRN interpolation, no extrapolation", models=outputs))
    progress("Sigma beta sensitivity complete")


if __name__ == "__main__":
    main()
