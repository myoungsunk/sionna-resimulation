"""Bind existing S2 inputs and freeze the G1-INT diagnostic contract."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from d1_shuffle import dump, sha, verify_file


root = Path(__file__).resolve().parent
workspace = root.parent.parent
checkout = workspace / "g1_char002_s2_ekf_20261115"
s2 = checkout / "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF"
state = s2 / "run_20261115_a"
native = (workspace / "artifacts/G1_CHAR002_S2_INPUTS_20261115/source_minimal/research"
          / "FP_SC_RECOVERY_R0_R5_20261107/R45_sources")
plan = workspace / "artifacts/G1_INT_PLAN_20261115/VALIDATION_PLAN_KO.md"
governance = Path.home() / ".codex/research-governance"
routes = ("R2", "R4", "R5")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def receipt(path):
    return {"path": str(path), "sha256": sha(path)}


def payload(item):
    with np.load(verify_file(item), allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def exact(left, right, keys):
    for key in keys:
        if left[key].dtype != right[key].dtype or left[key].shape != right[key].shape:
            raise ValueError(f"A/L2 attachment schema mismatch: {key}")
        if left[key].tobytes() != right[key].tobytes():
            raise ValueError(f"A/L2 attachment byte identity failed: {key}")


def bind_a_l2(cells):
    index = {(c["anchor"], c["bias"], c["route"]): c for c in cells}
    binding = []
    out = root / "bound_a_l2"
    out.mkdir(exist_ok=False)
    compare = ("pose_id", "t", "ds", "dt", "x0", "P0")
    keep = ("Hrf", "clean_Hrf", "t", "pose_id", "x0", "ds", "gy", "dt", "P0",
            "z", "muMB", "muBASE", "R", "D")
    for route in routes:
        a_cell, b_cell = index[("A", "B0", route)], index[("B", "L2", route)]
        a, b = payload(a_cell["online"]), payload(b_cell["online"])
        a_eval, b_eval = payload(a_cell["evaluator"]), payload(b_cell["evaluator"])
        exact(a, b, compare)
        exact(a_eval, b_eval, ("t", "pose_id", "truth"))
        for online, evaluator in ((a, a_eval), (b, b_eval)):
            exact(online, evaluator, ("t", "pose_id"))
        if np.array_equal(a["gy"], b["gy"]) or not np.isfinite(b["gy"]).all():
            raise ValueError(f"L2 gyro input invalid: {route}")
        packet = out / f"{route}_A_L2__online.npz"
        with packet.open("xb") as stream:
            np.savez_compressed(stream, **{key: (b if key == "gy" else a)[key] for key in keep})
        result = receipt(packet)
        new_arrays = payload(result)
        exact(new_arrays, a, [key for key in keep if key != "gy"])
        exact(new_arrays, b, ("gy",))
        cells.append({"stage": "derived_A_L2", "anchor": "A", "bias": "L2", "route": route,
                      "online": result, "evaluator": a_cell["evaluator"], "archive_trace": None})
        binding.append({"route": route, "anchor_A_input": a_cell["online"], "gyro_L2_source": b_cell["online"],
                        "online": result, "verified_byte_identical_control_fields": list(compare),
                        "verified_byte_identical_evaluator_fields": ["t", "pose_id", "truth"],
                        "gyro_max_abs_difference_rad": float(np.max(np.abs(a["gy"] - b["gy"]))),
                        "archived_A_L2_E0": False})
    path = out / "BINDING.json"
    dump(path, {"scope": "A B0 anchor payload + B L2 gyro, Full seed 10, mount 0", "by_route": binding})
    return receipt(path)


def freeze():
    target = root / "RUN_CONTRACT.json"
    if target.exists():
        raise ValueError("Contract already frozen")
    sys.path.insert(0, str(native / "src"))
    from qclean_uwb.fp_sc.e0_baseline import BANKS, ORIGINAL_CODE

    source_files = ["src/qclean_uwb/drivesim/" + f for f in
                    ("pattern_apply.py", "observation.py", "hs_lut.py", "sensor_v2.py", "sensors.py")]
    source_files += ["src/qclean_uwb/scenarios/corridor.py", "src/qclean_uwb/fp_sc/e0_baseline.py"]
    native_files = {name: receipt(native / name) for name in [*ORIGINAL_CODE, *BANKS, *source_files]}
    for name, expected in (ORIGINAL_CODE | BANKS).items():
        if native_files[name]["sha256"] != expected:
            raise ValueError(f"Native asset changed: {name}")

    cells = []
    prior_receipts = {}
    for stage, anchor, bias in (("2a", "B", "B0"), ("2b", "B", "L2"), ("2c", "A", "B0")):
        stage_dir = state / stage
        paths = [stage_dir / filename for filename in ("INPUTS.json", "EXECUTION.json", "RESULTS.json")]
        inputs, execution, _ = (read(path) for path in paths)
        prior_receipts[stage] = [receipt(path) for path in paths]
        for route in routes:
            trace = stage_dir / f"{route}_E0_trace.npz"
            cell = {"stage": stage, "anchor": anchor, "bias": bias, "route": route,
                    **{key: inputs[route][key] for key in ("online", "evaluator")},
                    "archive_trace": {"path": str(trace), "sha256": execution["outputs"][trace.name]}}
            for role in ("online", "evaluator", "archive_trace"):
                verify_file(cell[role])
            cells.append(cell)
    derived = bind_a_l2(cells)
    amendment = root / "CONTRACT_AMENDMENT_KO.md"
    code_files = [root / name for name in ("freeze_contract.py", "d0_d5.py", "e0_batch.py", "d1_shuffle.py")]
    code_files += [s2 / name for name in ("run_s2.py", "replay_s2.py", "verify_s2.py", "metrics_s2.py")]
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    contract = {
        "study": "G1-INT-DIAG-001", "structure_protocol": "G1-INT-001",
        "role": "IMPLEMENTER", "classification": "DIAGNOSTIC_ONLY",
        "frozen_utc": datetime.now(timezone.utc).isoformat(), "order": ["D0", "D5", "D1"],
        "governance": [receipt(governance / f) for f in ("COMMON_CONTRACT.md", "ROLE_IMPLEMENTER.md")],
        "provenance": {"repository": "myoungsunk/sionna-resimulation", "local_checkout_head": head,
                       "working_copy_scripts_hashed": True, "native_commit": "beb845665661ad8c68d07c88f6d268da4832e493",
                       "s2_upload_commit": "c7f0cf74f8362316db86328adf95d5e44e7a366d",
                       "plan_commit": "45c1977c7499ff20dc39b1af3977d14fcd7c515c",
                       "original_plan": receipt(plan), "amendment": receipt(amendment),
                       "s2_contract": receipt(state / "RUN_CONTRACT.json"), "s2_receipts": prior_receipts,
                       "A_L2_binding": derived, "native_files": native_files,
                       "code": [receipt(path) for path in code_files]},
        "s2": str(s2), "native": str(native), "cells": cells,
        "anchors": {"B": [10., 0., 2.65], "A": [4., 0., 2.65]},
        "scope": {"rf": "Full", "data_seed": 10, "mount_deg": 0, "robot_z_m": .45, "n_expected": 12,
                  "grid_packets_per_route": dict(zip(routes, (979, 742, 1415))),
                  "same_rf_B0_L2": "paired controls sensitivity; B z differs at most original S2 tolerance"},
        "D0": {"normalized_tolerance": 1e-10, "mask_exact": True, "archived_cells": 9,
               "independent_joseph_and_shadow_self_check_only_cells": 3,
               "prior_and_posterior_states_and_covariance": True, "on_failure": "retain evidence and stop"},
        "D5": {"knots_m": [0, 1.5, 3, 6, 10], "sigma_floor": .005, "hat_min_weight_exclusive": 5,
               "lookup": "previous posterior horizontal range", "donors": "other two B B0 routes",
               "estimator": "square root of mean epsilon_s squared minus R_BASE,ss with floor",
               "H4_pose95_drop_b_b0_pp_min": 10, "bootstrap_seconds": [5, 10], "bootstrap_repetitions": 1500},
        "D1": {"seed": 20261115, "repetitions": 100, "conditions": ["s_only", "r_only", "both", "both_paired"],
               "batch_size": 32, "identity_per_cell": 1, "total_replays": 4812,
               "rng": "NumPy default_rng (PCG64); SeedSequence([seed, anchor B/A index, R2/R4/R5 index, zero-based repetition, map r/s/paired index])",
               "distance_bins_m": [0, 3, 6, 10, "inf"], "folded_bearing_bins_deg": [0, 30, 90],
               "stratum_min_packets": 20, "max_legal_swap_sweeps": 20,
               "minimum_moved_fraction": .8, "minimum_valid_reps": 90, "lag_floor": .1, "lag_orig_fraction": .5,
               "H1_R4_s_only_heading95_median_min": .9, "H6_R4_r_only_xy95_median_min": .9,
               "H7_s_only_xy95_gain_median_min": .03,
               "comparison": "Original E0 hand table and fixed W0 acceptance from D0"},
        "M1": {"joint": ["distance_knotted_q", "ell_d", "ell_psi"], "q_knots_m": [0, 1.5, 3, 6, 10],
               "q_bounds": [0, 1], "ell_d_m": [.1, .25, .5, 1, 2, 4], "ell_psi_deg": [5, 10, 20, 45, 90, 180],
               "nugget": "1-q", "white_floor_fraction": .05, "D3_role": "diagnostic comparator only",
               "implemented_in_this_run": False, "KI_first_10s_separate": True},
        "M2": {"pooled_pose95_min": .90, "pooled_heading95_min": .90, "per_route_pose95_min": .75,
               "per_route_heading95_min": .75, "per_route_xy95_min": .75,
               "pooled_mean_nees3_interval": [1.5, 6.0], "pooled_rmse_ratio_max": 1.10, "per_route_rmse_ratio_max": 1.25},
        "M3": {"diagnostics": ["D2", "D3"], "proximity_m": .05, "wrapped_yaw_diff_max_deg": 10,
               "revisit_min_arc_m": .5, "min_pairs": 20, "mean_covariance_residual_min": .20,
               "status": "SPECIFIED_NOT_EXECUTED"},
        "frozen": ["SourceFFD", "z except D1 intervention", "muMB", "BASE R", "Q", "initial state", "original per-cell gate"],
        "claim_limit": "One frozen corridor per data source and seed, paired controls, diagnostic-only replay; no structure adoption",
    }
    dump(target, contract)
    print(f"{target}\n{sha(target)}")


if __name__ == "__main__":
    freeze()
