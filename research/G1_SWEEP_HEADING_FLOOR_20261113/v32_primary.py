"""Frozen v3.2 primary A2 paths, outer station bootstrap, and verdict."""
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

import numpy as np
import run_step2 as legacy
from run_step1 import dump
from v32_filter import Calibration, simulate
from v32_observation import GridCase
from v32_simcache import CurveBank

N = legacy.N
M = legacy.M
B = legacy.B
MODEL_CASE = "M1-R"

def build_stations(grid, names):
    stations = {}
    offset = 0
    for name in names:
        case = GridCase(grid, name, MODEL_CASE)
        groups = case.index["groups"]
        n = len(groups)
        stations[name] = dict(x=np.array([g["x"] for g in groups]),
                              y=np.array([g["y"] for g in groups]),
                              gids=[g["group"] for g in groups],
                              rows=np.arange(offset, offset+n*20).reshape(n, 20))
        offset += n*20
    return stations

def random_draws(stations, reps):
    rng = np.random.default_rng(2026111303)
    cases = np.arange(M) % len(stations)
    _, dr, _ = legacy.drivers(rng, M, w_sd=.486)
    uniforms = rng.uniform(size=(3, M, N))
    xy_rng = np.random.default_rng(2026111322)
    xy0 = xy_rng.normal(0., .10, (M, 2))
    xy = xy0[:, None, :] + np.cumsum(xy_rng.normal(0., .03, (M, N, 2)), axis=1)
    brng = np.random.default_rng(20261113)
    pools = [legacy.station_pool(stations, brng) for _ in range(reps)]
    return cases, dr, uniforms, xy, pools

def path_shard(args):
    inputs, banks, grid, stations, rho, scales, cases, dr, uniforms, xy, pools, shard = args
    bank = CurveBank(inputs, banks, grid, stations, xy, arm=MODEL_CASE)
    rho_array = [rho[c] for c in stations]
    cal_array = [Calibration(**scales[c.split("_")[0]]) for c in stations]
    boot = np.zeros((len(legacy.MODELS), len(pools), N))
    nominal = {}
    for j, model in enumerate(legacy.MODELS):
        rows = legacy.pick_rows(stations, legacy.station_pool(stations), cases, rho, uniforms, model)
        nominal[model] = simulate(lambda k: bank.access(rows[shard, k], k, path_indices=shard),
                                  dr[shard], cases[shard], rho_array, cal_array)
        for rep, pool in enumerate(pools):
            rotated = (cases + rep) % len(stations)
            rows = legacy.pick_rows(stations, pool, rotated, rho, uniforms, model)
            res = simulate(lambda k: bank.access(rows[shard, k], k, path_indices=shard),
                           dr[shard], rotated[shard], rho_array, cal_array)
            boot[j, rep] = np.sum(res["err"]**2, axis=0)
            if (rep + 1) % 100 == 0:
                print("paths", int(shard[0]), int(shard[-1]), model, "bootstrap", rep + 1,
                      "cache", bank.stats(), flush=True)
    return nominal, boot, bank.stats()

def primary_stats(result, dr, ci, cases, names):
    m = legacy.calc_stats(result, dr, ci)
    rr = result["reject"][:, :17]
    denom = result["used"][:, :17] | rr
    m["gate_reject_1_to_17"] = float(rr.sum()/denom.sum()) if denom.any() else None
    m["gate_eligible_count"] = int(denom.sum())
    m["routes"] = {}
    for route in ("R2", "R4", "R5"):
        selected = np.array([names[c].startswith(route+"_") for c in cases])
        m["routes"][route] = float(legacy.ratio_curve(result["err"][selected], dr[selected])[16])
    integrity = dict(nees=.5 <= m["nees_1_to_17"] <= 2.,
                     coverage=m["coverage_1_to_17"] >= .88,
                     endpoint_coverage=m["coverage_at_17"] >= .80)
    accuracy = dict(ratio=m["ratio_1_to_17"] <= .8, ci_upper=ci[1, 16] < 1.,
                    rmse=m["rmse_g1_1_to_17"] <= 3., all_routes=all(v < 1. for v in m["routes"].values()),
                    gate_rejection=m["gate_reject_1_to_17"] is not None and m["gate_reject_1_to_17"] <= .20)
    m.update(integrity={k: bool(v) for k, v in integrity.items()}, accuracy={k: bool(v) for k, v in accuracy.items()},
             integrity_pass=all(integrity.values()),
             accuracy_pass=all(integrity.values()) and all(accuracy.values()))
    return m

def run(args):
    pref = json.loads((args.out / "S1P_OBS_PREFLIGHT.json").read_bytes())
    r0 = json.loads((args.out / "R0.json").read_bytes())
    gate = json.loads(args.gate.read_bytes())
    if not r0["passed"] or not gate["passed"]:
        raise ValueError("R0 and G-INT must pass before the primary run")
    names = pref["primary"]
    if len(names) < 4 or {n.split("_")[0] for n in names} != {"R2","R4","R5"}:
        raise ValueError("Insufficient eligible cases or routes")
    stations = build_stations(Path(gate["grid"]), names)
    rho = {n: pref["by_case"][n]["rho"] for n in names}
    if not all(v is not None and 0 <= v <= 1 for v in rho.values()):
        raise ValueError("Missing spatial autocorrelation for an eligible case")
    scales = json.loads(args.calibration.read_bytes())
    cases, dr, uniforms, xy, pools = random_draws(stations, B)
    shards = np.array_split(np.arange(M), min(args.workers, M))
    common = (args.inputs, args.banks, Path(gate["grid"]), stations, rho,
              scales, cases, dr, uniforms, xy, pools)
    with ProcessPoolExecutor(max_workers=len(shards)) as pool:
        parts = list(pool.map(path_shard, (common + (shard,) for shard in shards)))
    sumsq = sum(x[1] for x in parts)
    bootstrap = np.sqrt(np.cumsum(sumsq, axis=-1)/np.cumsum(np.sum(dr**2, axis=0)))
    stats, results = {}, {}
    for i, model in enumerate(legacy.MODELS):
        keys = parts[0][0][model]
        res = {k: np.concatenate([x[0][model][k] for x in parts]) for k in keys}
        ci = np.quantile(bootstrap[i], [.025, .975], axis=0)
        stats[model] = primary_stats(res, dr, ci, cases, names)
        results[model] = res, ci
    both = [stats[k] for k in ("independent", "markov")]
    correlation = None
    if all(x["accuracy_pass"] for x in both):
        verdict = "PROCEED_A2"
        correlation = "ROBUST" if stats["cell"]["ratio_1_to_17"] < 1. else "CORRELATION_SENSITIVE"
    elif all(x["integrity_pass"] for x in both):
        verdict = "INTEGRITY_ONLY"
    else:
        verdict = "STOP"
    dump(args.out / "S2P_VERDICT.json", dict(verdict=verdict, cases=names,
         coverage="FULL_6" if len(names) == 6 else f"REDUCED_{len(names)}",
         correlation=correlation, models=stats, bootstrap_replicates=B,
         paths_per_replica=M, sigma_w=.486, sigma_beta=.45,
         rho=rho, cache=[x[2] for x in parts]))
    np.savez_compressed(args.out / "S2P_BOOTSTRAP.npz",
                        **{k:bootstrap[i] for i,k in enumerate(legacy.MODELS)})
    legacy.csv_curves(args.out / "S2P_CURVES.csv", results, dr,
                      dr + 2.046*np.arange(1,N+1), dr + 5.*np.random.default_rng(2026111304)
                      .standard_normal(M)[:,None])
    print("primary", verdict, flush=True)

def main():
    p = ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--banks", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--gate", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--workers", type=int, default=16)
    run(p.parse_args())

if __name__ == "__main__":
    main()
