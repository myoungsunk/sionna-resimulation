"""v3.3 driver for the frozen G-SNAP and G-E2E entry gates."""
from argparse import ArgumentParser
from contextlib import ExitStack
from pathlib import Path
import json
import time

import numpy as np
import run_step2 as legacy
from run_step1 import dump
from v32_filter import Calibration
from v33_filter import simulate
from v33_equivalence import check_paths, evaluate, write_paths
from v33_observation import CurveBank, build_grid, snap_summary, stationary_xy, train_loro
from v32_observation import ObservationCase

CASE = "R5_aA_m0"
RHO = 0.5187741068843829
HORIZON = 17
PILOT = 50
PATHS = 250
MODELS = ("independent", "markov")
SEEDS = dict(calibration=2026111336, xy=2026111337, dr=2026111338, rf=2026111339,
             bootstrap=2026111340)


def log(*args):
    print(*args, flush=True)


def prep(args, names):
    start = time.monotonic()
    cal, detail = train_loro(args.inputs, args.banks, names, "R5", workers=args.workers)
    from dataclasses import asdict
    dump(args.out / "S1P_ERR_MODEL_LORO.json", {
        "holdout": "R5", "calibration": asdict(cal), "diagnostics": detail,
        "training_seed": SEEDS["calibration"],
    })
    log("R5 LORO calibration complete", round(time.monotonic() - start, 1))
    build_grid(args.inputs, args.banks, args.grid, CASE, workers=args.workers)
    log("G-E2E R5 J/residual grid complete", round(time.monotonic() - start, 1))


def draws():
    xy = stationary_xy(np.random.default_rng(SEEDS["xy"]), PATHS, HORIZON)
    # E0 is fixed at zero. Each row has one residual bias followed by 17 increments.
    noise = np.random.default_rng(SEEDS["dr"]).standard_normal((PATHS, 1 + HORIZON))
    dr = np.cumsum(0.45 * noise[:, :1] + 0.486 * noise[:, 1:], axis=1)
    uniforms = np.random.default_rng(SEEDS["rf"]).random((PATHS, HORIZON, 3))
    return xy, dr, uniforms


def rows_for(case, uniforms, model):
    keys = sorted(case.groups)
    x = np.array([case.groups[g].x for g in keys])
    y = np.array([case.groups[g].y for g in keys])
    stations = {CASE: dict(x=x, y=y, gids=keys, rows=np.arange(len(keys)*20).reshape(len(keys), 20))}
    if len(keys) != 30:
        raise ValueError(f"Expected 30 frozen stations, got {len(keys)}")
    padded = np.zeros((3, len(uniforms), legacy.N))
    padded[:, :, :HORIZON] = np.moveaxis(uniforms, -1, 0)
    rows = legacy.pick_rows(stations, legacy.station_pool(stations), np.zeros(len(uniforms), dtype=int),
                           {CASE: RHO}, padded, model)[:, :HORIZON]
    return stations, rows


def run_e2e(args, names):
    if CASE not in names:
        raise ValueError("Frozen G-E2E case failed G-OBS eligibility")
    calibration = Calibration(**json.loads((args.out / "S1P_ERR_MODEL_LORO.json").read_bytes())["calibration"])
    case = ObservationCase(args.inputs, CASE, args.banks)
    xy, dr, uniforms = draws()
    rows = {}
    for model in MODELS:
        stations, rows[model] = rows_for(case, uniforms, model)
    model_codes = np.zeros(PATHS, dtype=int)
    start = time.monotonic()
    with ExitStack() as stack:
        snap = CurveBank(args.inputs, args.banks, args.grid, stations, xy,
                         mode="snap", workers=args.workers)
        stack.callback(snap.close)
        direct = CurveBank(args.inputs, args.banks, args.grid, stations, xy,
                           mode="continuous", workers=args.workers)
        stack.callback(direct.close)
        def phase(ids):
            result = {}
            for model in MODELS:
                snap_result = simulate(lambda k: snap.access(rows[model][ids, k], k, path_indices=ids),
                                       dr[ids], model_codes[ids], [RHO], [calibration])
                log("snap", model, len(ids), "seconds", round(time.monotonic() - start, 1))
                cont_result = simulate(lambda k: direct.access(rows[model][ids, k], k, path_indices=ids),
                                       dr[ids], model_codes[ids], [RHO], [calibration])
                check_paths(snap_result, cont_result, dr[ids], len(ids))
                result[model] = (snap_result, cont_result)
                log("continuous", model, len(ids), "seconds", round(time.monotonic() - start, 1))
            return result

        pilot = phase(np.arange(PILOT))
        node_check = snap.validate_nodes()
        if not node_check["passed"]:
            raise ValueError(f"Node check failed: {node_check}")
        dump(args.out / "G_E2E_PILOT_CHECK.json", {
            "status": "NUMERICAL_CHECK_PASSED", "paths_per_model": PILOT, "node_check": node_check,
            "models": list(MODELS),
        })
        log("G-E2E numerical pilot passed, starting predeclared 200 extra pairs per model")
        rest = phase(np.arange(PILOT, PATHS))
        results = {model: tuple({key: np.concatenate((first[key], next_arm[key]))
                                for key in first} for first, next_arm in zip(pilot[model], rest[model]))
                   for model in MODELS}
        report = evaluate(results, dr)
        report.update(case=CASE, rho=RHO, phase_sizes=[PILOT, PATHS-PILOT], seeds=SEEDS,
                      snap_access=snap.stats(), continuous_access=direct.stats())
        write_paths(args.out / "S1P_G_E2E_PATHS.csv", results, dr)
        dump(args.out / "S1P_SNAP.json", dict(snap_summary(xy), node_check=node_check, curve_access=snap.stats()))
        dump(args.out / "S1P_G_E2E.json", report)
        log("G-E2E final", report["status"], "seconds", round(time.monotonic() - start, 1))
        return report["status"]


def main():
    p = ArgumentParser()
    p.add_argument("phase", choices=("prep", "e2e"))
    for key in ("inputs", "banks", "out", "grid"):
        p.add_argument("--" + key, required=True, type=Path)
    p.add_argument("--workers", type=int, default=12)
    args = p.parse_args()
    prior = json.loads((args.out / "S1P_OBS_PREFLIGHT.json").read_bytes())
    names = prior["primary"]
    if not json.loads((args.out / "R0.json").read_bytes())["passed"]:
        raise ValueError("R0 did not pass")
    if prior["by_case"][CASE]["spatial"]["lag_045_clipped_rho"] != RHO:
        raise ValueError("Unexpected R5_aA_m0 spatial correlation")
    try:
        if args.phase == "prep":
            prep(args, names)
            return 0
        status = run_e2e(args, names)
        return {"PASS": 0, "FAIL": 4, "INCONCLUSIVE": 5, "INVALID": 6}[status]
    except Exception as exc:
        dump(args.out / f"{args.phase.upper()}_INVALID.json",
             dict(status="INVALID", phase=args.phase, reason=str(exc), exception=type(exc).__name__))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
