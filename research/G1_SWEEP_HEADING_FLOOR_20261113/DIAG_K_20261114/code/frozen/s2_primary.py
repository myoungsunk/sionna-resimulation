"""G1-MODEL-001 S2′ primary: frozen RF pools, CRN, snap/direct and §8."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np

import run_step2 as legacy
from run_step1 import dump
from v32_filter import Calibration
from v32_observation import GRID, SEEDS, cost_curves
import v33_baseline as baseline
from v33_filter import simulate
from v33_observation import (ARM, CurveBank, build_stations, projected_sigma, snap_summary,
                             stationary_xy, train_loro)

N, M, B = 50, 200, 1000
ROUTES = ("R2", "R4", "R5")
SPEC = "06de4adf336ef4436626c2ad6103c2dcf197d041"
GATE_RUN = "RUN4_20261113T094312Z"
MODELS = legacy.MODELS
EXPECTED = (21, 21, 10, 10, 30, 30)
KEYS = ("err", "p_ee", "nees", "covered", "miss", "used", "reject", "invalid")


def load(path):
    return json.loads(path.read_bytes())


def progress(*words):
    print(*words, flush=True)


class GroupedBank(CurveBank):
    """Exact gather of snap rows, plus seed-singleton arithmetic on direct rows."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, direct_all_seeds=True, **kwargs)
        self.names = tuple(self.cases)
        self.meta = np.asarray([
            [self.names.index(name), self.grids[name][0][group], seed, valid]
            for name, group, seed, valid in (self.rows[i] for i in range(len(self.rows)))
        ])
        self.truth = np.asarray([
            self.cases[name].groups[group].yaw_deg
            for name, group, _, _ in (self.rows[i] for i in range(len(self.rows)))
        ])
        self.xy_lookup = {}

    def _compute(self, key):
        name, group, dx, dy, seed = key
        if seed is not None:
            return super()._compute(key)
        case = self.cases[name]
        ids = case.groups[group].ids
        sigma = projected_sigma(case, group, dx, dy)
        pred, weights = next(case._node_predictions(group, dx, dy, [sigma], 0.0085, GRID))
        values = [cost_curves(case.observed[i:i+1, ids], pred, case.sigma_s0_sq, weights)
                  for i in range(SEEDS)]
        return tuple(np.concatenate(v, axis=0).astype(np.float32) for v in zip(*values))

    def access(self, rows, k, path_indices=None):
        paths = np.arange(len(self.xy)) if path_indices is None else path_indices
        rows, paths = np.asarray(rows), np.asarray(paths)
        self.last_direct = direct = self.outside[paths, k]
        cost = np.empty((len(rows), len(GRID)))
        chi2 = np.empty_like(cost)
        meta = self.meta[rows]
        for case_i in np.unique(meta[~direct, 0]):
            pos = np.flatnonzero((meta[:, 0] == case_i) & ~direct)
            group, seed = meta[pos, 1:3].T
            ix, iy = self.indices[paths[pos], k].T
            _, arrays = self.grids[self.names[case_i]]
            cost[pos], chi2[pos] = (a[group, seed, ix, iy] for a in arrays)

        requests = {}
        for pos in np.flatnonzero(direct):
            name, group, seed, _ = self.rows[rows[pos]]
            dx, dy = self.xy[paths[pos], k]
            key = (name, group, dx, dy, None)
            requests.setdefault(key, []).append((pos, seed))
        self.direct_requests += int(direct.sum())
        self.requests += len(rows)
        for key, slots in requests.items():
            values = self.xy_lookup.get(key)
            if values is None:
                values = self._compute(key)
                self.xy_lookup[key] = values
                self.direct_calculations += 1
                self._bytes += sum(x.nbytes for x in values)
            pos, seed = np.asarray(slots).T
            cost[pos], chi2[pos] = (v[seed] for v in values)
        n_valid = meta[:, 3]
        good = n_valid >= 3
        if (not np.isfinite(cost[good]).all() or not np.isfinite(chi2[good]).all()
                or not np.isnan(cost[~good]).all() or not np.isnan(chi2[~good]).all()):
            raise ValueError("Curve validity mask differs from frozen RF metadata")
        return cost, chi2, n_valid, self.truth[rows]


def pools_and_draws(stations, rho):
    rng = np.random.default_rng(2026111303)
    case = np.arange(M) % len(stations)
    _, dr, _ = legacy.drivers(rng, M, w_sd=.486)
    uniforms = rng.uniform(size=(3, M, N))
    xy = stationary_xy(np.random.default_rng(2026111322), M, N)
    brng = np.random.default_rng(20261113)
    nominal_pool = legacy.station_pool(stations)
    sizes = np.array([len(s["x"]) for s in stations.values()])
    sampled = np.empty((B, len(stations), int(sizes.max())), dtype=np.int16)
    sampled.fill(-1)
    nominal = np.stack([legacy.pick_rows(stations, nominal_pool, case, rho, uniforms, model)
                        for model in MODELS])
    outer = np.empty((len(MODELS), B, M, N), dtype=np.int16)
    for rep in range(B):
        pool = legacy.station_pool(stations, brng)
        for i, name in enumerate(stations):
            sampled[rep, i, :sizes[i]] = pool[name][0]
        rotated = (case + rep) % len(stations)
        for i, model in enumerate(MODELS):
            outer[i, rep] = legacy.pick_rows(stations, pool, rotated, rho, uniforms, model)
    return case, dr, xy, nominal, outer, sampled


def validate_entry(args):
    source = args.entry / "outputs"
    manifest = load(args.entry / "MANIFEST.json")
    assert manifest["spec_commit"] == SPEC and manifest["run_id"] == GATE_RUN
    assert manifest["status"]["G_E2E_PRIME"] == "PASS"
    for f in ("S1P_G_E2E.json", "S1P_OBS_PREFLIGHT.json", "R0.json", "S1P_ERR_MODEL_LORO.json"):
        assert hashlib.sha256((source / f).read_bytes()).hexdigest() == manifest["output_sha256"]["outputs/" + f]
    assert load(source / "S1P_G_E2E.json")["status"] == "PASS"
    assert load(source / "R0.json")["passed"]
    pref = load(source / "S1P_OBS_PREFLIGHT.json")
    names = tuple(pref["primary"])
    assert names == legacy.CASES
    for name in names:
        gates = pref["by_case"][name]["gates"]
        assert gates["G-OBS-1"]["passed"] and gates["G-OBS-2"]["passed"]
    rho = {name: pref["by_case"][name]["spatial"]["lag_045_clipped_rho"] for name in names}
    assert all(0 <= v <= 1 for v in rho.values())
    return names, rho, manifest


def calibration(args, names, obs):
    destination = args.out / ("S1P_ERR_MODEL_LORO.json" if obs == "M1-R" else "B0_ERR_MODEL_LORO.json")
    if destination.exists():
        receipt = load(destination)
    else:
        receipt = {}
        for route in ROUTES:
            if obs == "M1-R" and route == "R5":
                detail = load(args.entry / "outputs/S1P_ERR_MODEL_LORO.json")
            else:
                fit = train_loro if obs == "M1-R" else baseline.train_loro
                _, detail = fit(args.inputs, args.banks, names, route, workers=args.workers)
            assert detail["holdout"] == route
            assert all(not name.startswith(route + "_") for name in detail["training_cases"])
            receipt[route] = detail
            progress("LORO", obs, route, detail["calibration"])
        dump(destination, receipt)
    return [Calibration(**receipt[name.split("_")[0]]["calibration"]) for name in names]


def check_access(args, stations, xy):
    trial = np.tile(np.array([[[.275, -.3], [.31, -.12], [-.15, -.31],
                              [.31, .33], [0., .15]]]), (12, 1, 1))
    for j in range(len(trial)):
        trial[j, 1:4, 0] += .0001 * j
    group_rows = np.array([r for s in stations.values() for r in (s["rows"][0, 0], s["rows"][-1, -1])])
    start = time.monotonic()
    reference = CurveBank(args.inputs, args.banks, args.grid, stations, trial)
    bank = GroupedBank(args.inputs, args.banks, args.grid, stations, trial)
    try:
        for k in range(trial.shape[1]):
            rows = np.roll(group_rows, k)
            left, right = reference.access(rows, k), bank.access(rows, k)
            for a, b in zip(left, right):
                np.testing.assert_array_equal(a, b)
                np.testing.assert_array_equal(a.view(np.uint8), b.view(np.uint8))
        paths = np.arange(len(trial))
        dr = xy[:len(trial), :trial.shape[1], 0]
        cases = paths // 2
        cal = [Calibration(10., 1., 4., 0., 12, 12)] * len(stations)
        def eval_bank(accessor):
            return simulate(lambda k: accessor.access(group_rows, k), dr, cases, [.25] * len(stations), cal)
        x, y = eval_bank(reference), eval_bank(bank)
        for key in KEYS:
            np.testing.assert_array_equal(x[key], y[key])
    finally:
        reference.close()
        bank.close()
    dump(args.out / "LOOKUP_REGRESSION.json", dict(status="PASS", paths=len(trial),
         visits=trial.shape[1], coordinates="snap, tie, x/y/both outside",
         verification="bit-identical float64 access after frozen float32 conversion and equal filter outputs",
         seconds=time.monotonic()-start))


def run_shard(args, stations, rho, cal, case, dr, xy, nominal, outer, indices):
    local_xy, local_dr, local_case = xy[indices], dr[indices], case[indices]
    bank = GroupedBank(args.inputs, args.banks, args.grid, stations, local_xy)
    rho_values = list(rho.values())
    output = {}
    squared = np.empty((len(MODELS), B, N))
    try:
        for model_i, model in enumerate(MODELS):
            def evaluate(rows, assigned):
                return simulate(lambda k: bank.access(rows[:, k], k), local_dr, assigned, rho_values, cal)
            output[model] = evaluate(nominal[model_i, indices], local_case)
            for rep in range(B):
                res = evaluate(outer[model_i, rep, indices], (local_case + rep) % len(stations))
                squared[model_i, rep] = np.sum(res["err"]**2, axis=0)
                if rep % 100 == 99 and indices[0] == 0:
                    progress("bootstrap", model, rep + 1, bank.stats())
        return output, squared, bank.stats()
    finally:
        bank.close()


def longest_miss(miss):
    streak = np.zeros(len(miss), dtype=int)
    longest = np.zeros_like(streak)
    for col in miss.T:
        streak = np.where(col, streak + 1, 0)
        np.maximum(longest, streak, out=longest)
    return longest


def stats(data, dr, case, names, ci=None):
    out = legacy.calc_stats(data, dr, ci)
    rejected = data["reject"][:, :17]
    eligible = data["used"][:, :17] | rejected
    out["gate_reject_1_to_17"] = float(rejected.sum() / eligible.sum()) if eligible.any() else None
    out["gate_eligible_count"] = int(eligible.sum())
    streak = longest_miss(data["miss"][:, :17])
    out["longest_window_miss_1_to_17"] = int(streak.max())
    out["longest_window_miss_1_to_17_p95"] = float(np.quantile(streak, .95))
    out["longest_window_miss_1_to_50"] = int(longest_miss(data["miss"]).max())
    routes = np.array([names[c].split("_")[0] for c in case])
    out["routes"] = {r: float(legacy.ratio_curve(data["err"][routes == r], dr[routes == r])[16])
                     for r in ROUTES if np.any(routes == r)}
    if ci is not None:
        integrity = dict(nees=.5 <= out["nees_1_to_17"] <= 2.,
                         coverage=out["coverage_1_to_17"] >= .88,
                         endpoint_coverage=out["coverage_at_17"] >= .80)
        accuracy = dict(ratio=out["ratio_1_to_17"] <= .8, ci_upper=ci[1, 16] < 1.,
                        rmse=out["rmse_g1_1_to_17"] <= 3.,
                        all_routes=len(out["routes"]) == 3 and all(v < 1. for v in out["routes"].values()),
                        gate_rejection=out["gate_reject_1_to_17"] is not None
                        and out["gate_reject_1_to_17"] <= .2)
        out.update(integrity={k: bool(v) for k,v in integrity.items()},
                   accuracy={k: bool(v) for k,v in accuracy.items()},
                   integrity_pass=all(integrity.values()),
                   accuracy_pass=all(integrity.values()) and all(accuracy.values()),
                   integrity_misses=[k for k,v in integrity.items() if not v],
                   accuracy_misses=[k for k,v in accuracy.items() if not v])
    return out


def subset(data, selected):
    return {k: v[selected] for k, v in data.items()}


def classify(report):
    both = [report[m] for m in ("independent", "markov")]
    if all(m["accuracy_pass"] for m in both):
        return "PROCEED_A2", "ROBUST" if report["cell"]["ratio_1_to_17"] < 1. else "CORRELATION_SENSITIVE"
    if all(m["integrity_pass"] for m in both):
        return "INTEGRITY_ONLY", None
    return "STOP", None


def primary(args, names, rho, station):
    start = time.monotonic()
    cal = calibration(args, names, "M1-R")
    case, dr, xy, nominal, outer, sampled = pools_and_draws(station, rho)
    np.savez_compressed(args.out / "S2P_DRAWS.npz", cases=np.array(names), models=np.array(MODELS),
                        case_index=case, dr=dr, xy=xy, nominal_rows=nominal,
                        outer_station_indices=sampled, outer_rows=outer)
    dump(args.out / "S2P_G_SNAP.json", snap_summary(xy))
    check_access(args, station, xy)
    progress("Starting", B, "replicates of", M, "paths", time.monotonic()-start)
    parts = np.array_split(np.arange(M), args.workers)
    calculate = partial(run_shard, args, station, rho, cal, case, dr, xy, nominal, outer)
    with ProcessPoolExecutor(max_workers=len(parts)) as pool:
        gathered = list(pool.map(calculate, parts))
    sumsq = np.sum([p[1] for p in gathered], axis=0)
    dr_sumsq = np.sum(dr**2, axis=0)
    boot = np.sqrt(np.cumsum(sumsq, axis=-1) / np.cumsum(dr_sumsq))
    nom = {m:{k: np.concatenate([p[0][m][k] for p in gathered]) for k in KEYS} for m in MODELS}
    ci = {m: np.quantile(boot[i], [.025, .975], axis=0) for i, m in enumerate(MODELS)}
    report = {m:stats(nom[m], dr, case, names, ci[m]) for m in MODELS}
    verdict, correlation = classify(report)
    selected = case != names.index("R2_aB_m0")
    common = {m: stats(subset(nom[m], selected), dr[selected], case[selected], names) for m in MODELS}
    np.savez_compressed(args.out / "S2P_NOMINAL.npz", dr=dr, case_index=case, cases=np.array(names),
                        **{f"{m}_{k}":a for m,d in nom.items() for k,a in d.items()})
    np.savez_compressed(args.out / "S2P_BOOTSTRAP.npz", models=np.array(MODELS),
                        sumsq=sumsq, dr_sumsq=dr_sumsq, **{m:boot[i] for i,m in enumerate(MODELS)})
    legacy.csv_curves(args.out / "S2P_CURVES.csv", {m:(nom[m],ci[m]) for m in MODELS}, dr,
                      dr + 2.046*np.arange(1,N+1),
                      dr + 5.*np.random.default_rng(2026111304).standard_normal(M)[:,None])
    dump(args.out / "S2P_VERDICT.json", dict(verdict=verdict, coverage="FULL_6", correlation=correlation,
         question_id="G1-MODEL-001", spec_commit=SPEC, gate_run=GATE_RUN, cases=names,
         physical_stations={n:len(s["x"]) for n,s in station.items()}, rho=rho, models=report,
         common_five_case_models=common, bootstrap_replicates=B, paths_per_replica=M,
         seeds=dict(dr_rf=2026111303, xy=2026111322, outer_station=20261113, calibration=2026111336),
         sigma_beta=.45, sigma_w=.486, beta_uncal=2.046, dr_version="r1.3.1",
         b0="separate paired comparison", step3="HELD", cache=[p[2] for p in gathered],
         seconds=time.monotonic()-start))
    progress("§8", verdict, correlation)


def run_b0(args, names, rho, station):
    b0_cal = calibration(args, names, "M0")
    draws = np.load(args.out / "S2P_DRAWS.npz", allow_pickle=False)
    case, dr, xy, nominal = (draws[k] for k in ("case_index","dr","xy","nominal_rows"))
    selected = np.flatnonzero(case != names.index("R2_aB_m0"))
    common = {n:s for n,s in station.items() if n not in baseline.M0_EXCLUDED}
    bank = baseline.CurveBank(args.inputs, args.banks, args.grid, common, xy,
                              workers=args.workers, direct_bytes=2*1024**3)
    try:
        outcome = {}
        for i, model in enumerate(MODELS):
            outcome[model] = simulate(lambda k: bank.access(nominal[i, selected, k], k, selected),
                                      dr[selected], case[selected], list(rho.values()), b0_cal)
    finally:
        bank.close()
    nom = np.load(args.out / "S2P_NOMINAL.npz", allow_pickle=False)
    comparison = {}
    for m in MODELS:
        new = {k:nom[f"{m}_{k}"][selected] for k in KEYS}
        comparison[m] = {
            "M0_E0":stats(outcome[m], dr[selected], case[selected], names),
            "M1_R_E1":stats(new, dr[selected], case[selected], names),
        }
    np.savez_compressed(args.out / "B0_NOMINAL.npz", path_id=selected, case_index=case[selected],
                        dr=dr[selected], **{f"{m}_{k}":a for m,d in outcome.items() for k,a in d.items()})
    dump(args.out / "B0_COMPARISON.json", dict(models=comparison, cases=list(common),
         paired_paths=len(selected), bootstrap="primary §8 only", shared="path IDs, case, XY, RF rows, DR"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("calibrate", "primary", "b0"))
    for key in ("inputs", "banks", "grid", "entry", "out"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--workers", type=int, default=24)
    args = p.parse_args()
    names, rho, manifest = validate_entry(args)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.phase == "calibrate":
        calibration(args, names, "M1-R")
        calibration(args, names, "M0")
        return
    station = build_stations(args.inputs, args.banks, names)
    assert tuple(len(s["x"]) for s in station.values()) == EXPECTED
    for a,b in zip(names[::2], names[1::2]):
        for axis in ("x", "y"):
            np.testing.assert_array_equal(station[a][axis], station[b][axis])
    if args.phase == "primary":
        primary(args, names, rho, station)
    else:
        run_b0(args, names, rho, station)


if __name__ == "__main__":
    main()
