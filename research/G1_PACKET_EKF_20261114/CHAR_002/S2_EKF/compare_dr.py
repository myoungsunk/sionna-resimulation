"""Compare frozen S2 EKF trajectories against wheel-and-gyro prediction only."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

from metrics_s2 import _moving_block_indices, _summarize
from replay_s2 import ARMS, read_npz, sha
from verify_s2 import check_metric_rows, from_trace


STAGES = ("2a", "2b", "2c")
ROUTES = ("R2", "R4", "R5")
NATIVE = {
    "core": Path("research/EKF4_RANGE_S_STAGED_20261014/core.py"),
    "online": Path("research/MBVAR_PRR_001_20261103/S1/online.py"),
}
RMSE_KEYS = ("heading_rmse_deg", "xy_rmse_cm")


def read_json(path):
    return json.loads(path.read_bytes())


def load_native(root, hashes):
    modules = {}
    for name, relative in NATIVE.items():
        path = root / relative
        if sha(path) != hashes[str(relative).replace("/", "\\")]:
            raise ValueError(f"Unexpected motion source: {path}")
        spec = importlib.util.spec_from_file_location(f"dr_native_{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules["core"], modules["online"]


def read_checked_input(receipt, keys):
    path = Path(receipt["path"])
    if sha(path) != receipt["sha256"]:
        raise ValueError(f"Frozen input hash mismatch: {path}")
    with np.load(path, allow_pickle=False) as source:
        return {key: source[key] for key in keys}


def replay_dr(packet, e0, core, online, tolerance):
    controls = {key: packet[key] for key in ("ds", "gy", "dt")}
    state = np.r_[packet["x0"][:3], 0.]
    covariance = packet["P0"].copy()
    grid = {key: packet[key] for key in ("t", "pose_id")}
    n = len(grid["t"])
    x = np.empty((n, 4))
    P = np.empty((n, 4, 4))
    max_prior_delta = 0.
    for k in range(n):
        # With the actual E0 parent, the same prediction must reproduce its stored prior.
        parent_x = e0["x"][k - 1] if k else state
        parent_P = e0["P"][k - 1] if k else covariance
        prior_x, prior_P = online.predict(core, parent_x, parent_P, k, controls)
        max_prior_delta = max(max_prior_delta, np.max(abs(prior_x - e0["prior"][k])),
                              np.max(abs(prior_P - e0["Pprior"][k])))
        state, covariance = online.predict(core, state, covariance, k, controls)
        x[k], P[k] = state, covariance
    if max_prior_delta > tolerance or not np.isfinite(x).all() or not np.isfinite(P).all():
        raise ValueError(f"Invalid prediction-only replay, E0 prior maximum delta {max_prior_delta:g}")
    if np.any(x[:, 3] != 0.):
        raise ValueError("DR bias mean changed without a measurement update")
    return dict(grid, x=x, P=P), float(max_prior_delta)


def compare(rows, time, settings):
    metrics = {arm: _summarize(values) for arm, values in rows.items()}
    dr = metrics["DR"]
    differences = {
        arm: {
            key: {
                "delta": metrics[arm][key] - dr[key],
                "reduction_pct": 100 * (1 - metrics[arm][key] / dr[key]),
                "ci95": {},
            }
            for key in RMSE_KEYS
        }
        for arm in ARMS
    }
    for block in settings["sizes_s"]:
        indices = _moving_block_indices(time, block, settings["repetitions"],
                                        np.random.default_rng(settings["seed"]))
        for col, key in enumerate(RMSE_KEYS):
            baseline = np.sqrt(rows["DR"][:, col][indices].mean(axis=1))
            for arm in ARMS:
                estimate = np.sqrt(rows[arm][:, col][indices].mean(axis=1)) - baseline
                differences[arm][key]["ci95"][f"{block}s"] = np.quantile(
                    estimate, [0.025, 0.975]).tolist()
    return metrics, differences


def verify_grid(actual, evaluator):
    if any(not np.array_equal(actual[key], evaluator[key]) for key in ("t", "pose_id")):
        raise ValueError("Trajectory and evaluator packet IDs or timestamps disagree")


def evaluate(run, native, out):
    contract_path = run / "RUN_CONTRACT.json"
    contract = read_json(contract_path)
    core, online = load_native(native, contract["native_source_hashes"])
    contract_hash = sha(contract_path)
    started = datetime.now(timezone.utc).isoformat()
    out.mkdir(parents=True, exist_ok=False)
    results = {}
    trace_paths = {}
    for stage in STAGES:
        stage_dir = run / stage
        execution = read_json(stage_dir / "EXECUTION.json")
        if execution["status"] != "PASS_EXECUTION" or execution["run_contract_sha256"] != contract_hash:
            raise ValueError(f"Unverified S2 execution: {stage}")
        for name in ("INPUTS.json", "RESULTS.json"):
            if sha(stage_dir / name) != execution["outputs"][name]:
                raise ValueError(f"Unexpected frozen S2 file: {stage}/{name}")
        inputs = read_json(stage_dir / "INPUTS.json")
        archived = read_json(stage_dir / "RESULTS.json")["by_case"]
        results[stage] = {}
        for route in ROUTES:
            packet = read_checked_input(inputs[route]["online"],
                                        ("t", "pose_id", "ds", "gy", "dt", "x0", "P0"))
            rows = {}
            traces = {}
            for arm in ARMS:
                filename = f"{route}_{arm}_trace.npz"
                path = stage_dir / filename
                if sha(path) != execution["outputs"][filename]:
                    raise ValueError(f"Unexpected frozen S2 trace: {stage}/{filename}")
                traces[arm] = read_npz(path)
            trace, prior_delta = replay_dr(packet, traces["E0"], core, online, 1e-10)
            evaluator = read_checked_input(inputs[route]["evaluator"], ("t", "pose_id", "truth"))
            traces["DR"] = trace
            for arm, estimate in traces.items():
                verify_grid(estimate, evaluator)
                rows[arm] = from_trace(estimate, evaluator["truth"])
                if arm != "DR":
                    check_metric_rows(rows[arm], archived[route][arm])
            metrics, changes = compare(rows, evaluator["t"], contract["bootstrap"])
            path = out / f"{stage}_{route}_DR_trace.npz"
            np.savez_compressed(path, **trace)
            trace_paths[stage, route] = path
            results[stage][route] = {
                "metrics": metrics,
                "rmse_vs_dr": changes,
                "end_error": {
                    arm: {key: float(np.sqrt(values[-1, col])) for col, key in enumerate(RMSE_KEYS)}
                    for arm, values in rows.items()
                },
                "e0_prior_max_abs_delta": prior_delta,
                "dr_trace_sha256": sha(path),
                "inputs": {key: inputs[route][key] for key in ("online", "evaluator")},
            }
    identical_b0 = {}
    for route in ROUTES:
        b = read_npz(trace_paths["2a", route])
        a = read_npz(trace_paths["2c", route])
        identical_b0[route] = all(np.array_equal(b[key], a[key]) for key in b)
    result = {
        "status": "PASS_EXECUTION_AND_SELF_CHECK",
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "s2_run": str(run),
        "native_source_root": str(native),
        "s2_run_contract_sha256": contract_hash,
        "script_sha256": sha(__file__),
        "stage_execution_sha256": {stage: sha(run / stage / "EXECUTION.json") for stage in STAGES},
        "reference": "Frozen wheel/gyro increments ds/gy/dt and E0 x0, bias=0, P0 and Q; no RF update.",
        "bootstrap": contract["bootstrap"],
        "identical_b0_dr_2a_2c": identical_b0,
        "by_stage": results,
    }
    (out / "RESULTS.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("s2_run", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    evaluate(args.s2_run.resolve(), args.native.resolve(), args.out.resolve())
