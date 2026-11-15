"""Reproduce the Stage 2 observational TRACE_DIAGNOSTICS.json from frozen traces."""

import argparse
import json
from pathlib import Path
import re

import numpy as np

from replay_s2 import read_npz, sha
from verify_s2 import from_trace


ARMS = ("E0", "E1", "E2", "E3", "E4")
ADAPTER = "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py"


def read_json(path):
    return json.loads(path.read_bytes())


def require_hash(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Frozen data hash mismatch: {path}")


def read_checked(path, sha256):
    require_hash(path, sha256)
    return read_npz(path)


def route_stats(packet, evaluator, traces, anchor_x, bias, degrees):
    truth = evaluator["truth"]
    for trace in (packet, *traces):
        if any(not np.array_equal(evaluator[key], trace[key]) for key in ("t", "pose_id")):
            raise ValueError("Evaluator packet IDs or timestamps differ")
    base, e1, e2, e3, e4 = traces
    mask = base["mask"]
    if any(not np.array_equal(mask, trace["mask"]) for trace in traces):
        raise ValueError("E0 gate mask differs across arms")
    delta = np.column_stack((truth[:, :2] - [anchor_x, 0], np.full(len(truth), 2.65 - .45)))
    residual = packet["z"][:, 0] - (np.linalg.norm(delta, axis=1) + bias)
    cm = 100 * np.column_stack((residual, residual - base["mu"][:, 0], residual - e1["mu"][:, 0]))

    prior_projection = np.einsum("ni,nij,nj->n", e3["H"][:, 1], e3["Pprior"], e3["H"][:, 1])
    base_s3 = e3["Rvar"][:, 1, 1]
    variance = base_s3.copy()
    positive = mask.copy()
    for _ in range(3):
        weights = (degrees + 1) / (degrees + e3["nu"][:, 1]**2 / (prior_projection + variance))
        positive &= weights > 1.
        variance /= weights
    if not np.allclose(variance, e3["Reff"][:, 1, 1], rtol=1e-14):
        raise ValueError("Recalculated E3 effective polarization variance differs")
    e3_rows = from_trace(e3, truth)
    e4_rows = from_trace(e4, truth)
    reset = e4["phi"] == 0.
    return cm, {
        "n": len(cm),
        "range_rmse_cm_raw_e0_e1": np.sqrt(np.mean(cm**2, axis=0)).tolist(),
        "range_mean_cm_raw_e0_e1": cm.mean(axis=0).tolist(),
        "s3_accept_w_gt_1_all_three": int(positive.sum()),
        "accepted": int(mask.sum()),
        "e3_e2_R_eff_ss_ratio_med_accepted": float(np.median((variance / e2["Reff"][:, 1, 1])[mask])),
        "e3_R_eff_ss_base_ratio_med_accepted": float(np.median((variance / base_s3)[mask])),
        "e4_reset_noninitial": int(reset[1:].sum()),
        "e3_e4_pose95_by_e4_reset": {
            str(bool(value)): [float(rows[reset == value, 3].mean()) for rows in (e3_rows, e4_rows)]
            for value in np.unique(reset)
        },
    }


def inspect(run, native):
    contract_path = run / "RUN_CONTRACT.json"
    contract_hash = sha(contract_path)
    contract = read_json(contract_path)
    adapter = native / ADAPTER
    require_hash(adapter, contract["native_source_hashes"][ADAPTER.replace("/", "\\")])
    bias = float(re.search(r"^B_OLD=(\S+)", adapter.read_text(encoding="utf-8"), re.M)[1])
    degrees = contract["student_t"]["nu/E3-E4"]
    observed = {}
    for stage in ("2a", "2b", "2c"):
        stage_dir = run / stage
        execution = read_json(stage_dir / "EXECUTION.json")
        if execution["status"] != "PASS_EXECUTION" or execution["run_contract_sha256"] != contract_hash:
            raise ValueError(f"Unverified S2 execution: {stage}")
        input_path = stage_dir / "INPUTS.json"
        require_hash(input_path, execution["outputs"]["INPUTS.json"])
        by_route = {}
        route_errors = []
        for route, inputs in read_json(input_path).items():
            packet = read_checked(**inputs["online"])
            evaluator = read_checked(**inputs["evaluator"])
            traces = []
            for arm in ARMS:
                name = f"{route}_{arm}_trace.npz"
                traces.append(read_checked(stage_dir / name, execution["outputs"][name]))
            anchor_x = 4 if stage == "2c" else 10
            cm, by_route[route] = route_stats(packet, evaluator, traces, anchor_x, bias, degrees)
            route_errors.append(cm)
        all_cm = np.concatenate(route_errors)
        observed[stage] = {"by_route": by_route, "range_rmse_cm_raw_e0_e1": np.sqrt(
            np.mean(all_cm**2, axis=0)).tolist()}
    return {
        "range_measurement_equation": "z_r - (distance_3d(truth,anchor)+B_OLD) - mu_r(k)",
        "B_OLD": bias,
        "by_stage": observed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("run", "native", "out"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(inspect(args.run, args.native), stream, indent=2, allow_nan=False)
