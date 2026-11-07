"""Portable, additive E0 checks of the archived MB_VAR W0 baseline.

The caller owns the FP-SC-001 stage/code/input authorization.  Importing this
module does not run a filter, fit a model, download data, or write artifacts.
Only seed 10, B0/L2, R2/R4/R5, Full/Native_LoS are implemented here.

Stored-array arithmetic is an implementer check, not independent acceptance
and not a replay.  Missing banks, controls, or reference arrays explicitly
block the corresponding recursive checks.  Original source files and results
are read only.  New results require a new, empty output directory.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np


STUDY_BASE = Path("research/MBVAR_PRR_001_20261103")
PACKETS = STUDY_BASE / "PHYSICAL_CAUSALITY_20261104/C1/C1A_001/FROZEN_PACKETS"
EXT = STUDY_BASE / "POST_S3_PROPOSER_20261104/R2_EXTENSION"
ROUTE_ROWS = {"R2": 979, "R4": 742, "R5": 1415}
SPEC = {"anchor": (10.0, 0.0, 2.65), "robot_z_m": 0.45, "mount_deg": 0.0}
B_OLD = -0.5315983906250129
TOL = 1e-10
BANKS = {
    "LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
    "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
}
ORIGINAL_CODE = {
    "research/FFD_P0P3_20261016/source_model.py": "e2591ecb238917e656e2effe50b0cb92543be343e90aef460edcf7b859820ba3",
    "research/FFD_P0P3_20261016/p0_initial.py": "369eb78b4e7b67a5f00df532cdf319b56de14d7c19658aa45c8e9631e3382086",
    "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py": "dfec050fcc81ff39aed0058a2654b3b845b8d3320437136a3f2317033e5efe22",
    "research/EKF4_RANGE_S_STAGED_20261014/core.py": "1abdac002631e1de2303b0ef7c39c6c9eb619b53d9ba9fd8d89d1a3cd9c630d1",
    "research/MBVAR_PRR_001_20261103/S1/online.py": "c38f33d31515d23059a13d30f3243e23be8a18d4d4d4f6c41f12d38c4445d173",
}
TRACE_SHAPES = {
    "x": (4,), "P": (4, 4), "prior": (4,), "Pprior": (4, 4),
    "h": (2,), "H": (2, 4), "mu": (2,), "Rvar": (2, 2),
    "Reff": (2, 2), "K": (4, 2), "nu": (2,), "S": (2, 2),
    "sigma_b": (), "rho_before": (), "weight": (), "nis": (), "d0": (),
}
REPLAY_FIELDS = tuple(TRACE_SHAPES)


class BlockedInput(RuntimeError):
    """A required payload or portable original dependency is unavailable."""


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def payload(path: Path, expected_sha256: str | None = None) -> Path:
    if not path.is_file():
        raise BlockedInput(f"MISSING_FILE: {path}")
    with path.open("rb") as handle:
        if handle.read(48).startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise BlockedInput(f"LFS_POINTER_WITHOUT_PAYLOAD: {path}")
    if expected_sha256 and sha256(path) != expected_sha256:
        raise ValueError(f"PAYLOAD_SHA256_MISMATCH: {path}")
    return path


def read_npz(path: Path, expected_sha256: str | None = None) -> dict[str, np.ndarray]:
    payload(path, expected_sha256)
    with np.load(path, allow_pickle=False) as arrays:
        return {name: arrays[name] for name in arrays.files}


def _json(path: Path) -> Any:
    if not path.is_file():
        raise BlockedInput(f"MISSING_REGISTRY: {path}")
    return json.loads(path.read_bytes())


def _put(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def difference(actual: np.ndarray, expected: np.ndarray) -> dict[str, Any]:
    a, b = np.asarray(actual), np.asarray(expected)
    if a.shape != b.shape:
        return {"passed": False, "reason": "SHAPE_MISMATCH", "actual": list(a.shape), "expected": list(b.shape)}
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        return {"passed": False, "reason": "NONFINITE"}
    if a.dtype.kind == "b" or b.dtype.kind == "b":
        return {"passed": bool(np.array_equal(a, b)), "mismatches": int(np.count_nonzero(a != b))}
    delta = np.abs(a - b)
    normalized = delta / np.maximum(1.0, np.abs(b))
    return {"passed": bool(np.all(normalized <= TOL)),
            "max_abs_error": float(delta.max(initial=0.0)),
            "max_normalized_error": float(normalized.max(initial=0.0))}


def covariance_check(matrices: np.ndarray) -> dict[str, Any]:
    value = np.asarray(matrices, float)
    if value.ndim < 2 or value.shape[-1] != value.shape[-2] or not np.isfinite(value).all():
        raise ValueError("INVALID_COVARIANCE_ARRAY")
    value = value.reshape(-1, value.shape[-1], value.shape[-1])
    symmetric = (value + value.swapaxes(-1, -2)) * 0.5
    eigenvalues = np.linalg.eigvalsh(symmetric)
    scale = np.maximum(1.0, np.max(np.abs(eigenvalues), axis=1))
    error = np.linalg.norm(value - value.swapaxes(-1, -2), ord=2, axis=(1, 2))
    ok = np.all(error <= 1e-12 * scale) and np.all(eigenvalues[:, 0] >= -1e-12 * scale)
    return {"passed": bool(ok), "minimum_eigenvalue": float(eigenvalues.min()),
            "max_symmetry_error": float(error.max()), "count": len(value)}


def joint_update(prior: np.ndarray, covariance: np.ndarray, jacobian: np.ndarray,
                 innovation: np.ndarray, noise: np.ndarray, accepted: np.ndarray) -> dict[str, np.ndarray]:
    """Separate batched Joseph arithmetic; never calls S1.online.joseph."""
    n = len(prior)
    items = ((prior, (n, 4)), (covariance, (n, 4, 4)), (jacobian, (n, 2, 4)),
             (innovation, (n, 2)), (noise, (n, 2, 2)))
    for array, shape in items:
        if np.shape(array) != shape or not np.isfinite(array).all():
            raise ValueError("UPDATE_SHAPE_OR_NONFINITE")
    if accepted.dtype != np.dtype(bool) or accepted.shape != (n,):
        raise ValueError("ORIGINAL_BOOLEAN_MASK_REQUIRED")
    if not covariance_check(covariance)["passed"] or not covariance_check(noise)["passed"]:
        raise ValueError("UPDATE_COVARIANCE_INVALID")
    hp = jacobian @ covariance
    S = hp @ jacobian.swapaxes(-1, -2) + noise
    S = (S + S.swapaxes(-1, -2)) * 0.5
    gain = np.linalg.solve(S, hp).swapaxes(-1, -2)
    gain = np.where(accepted[:, None, None], gain, 0.0)
    state = prior + np.einsum("nij,nj->ni", gain, innovation)
    state[accepted, 2] = (state[accepted, 2] + np.pi) % (2 * np.pi) - np.pi
    # Original rejected updates return the prior without another heading wrap.
    state[~accepted] = prior[~accepted]
    residual_matrix = np.eye(4) - gain @ jacobian
    P = residual_matrix @ covariance @ residual_matrix.swapaxes(-1, -2) + gain @ noise @ gain.swapaxes(-1, -2)
    P = (P + P.swapaxes(-1, -2)) * 0.5
    P[~accepted] = covariance[~accepted]
    nis = np.einsum("ni,ni->n", innovation, np.linalg.solve(S, innovation[..., None])[..., 0])
    return {"x": state, "P": P, "K": gain, "S": S, "nis": nis}


def validate_packet_trace(packet: dict, trace: dict, expected_n: int) -> None:
    shapes = {"z": (expected_n, 2), "muMB": (expected_n, 2),
              "muBASE": (expected_n, 2), "R": (expected_n, 2, 2),
              "P0": (4, 4), "D": (expected_n,), "t": (expected_n,), "pose_id": (expected_n,)}
    for name, shape in shapes.items():
        if name not in packet or packet[name].shape != shape or not np.isfinite(packet[name]).all():
            raise ValueError(f"INVALID_PACKET_FIELD: {name}")
    for name, shape in TRACE_SHAPES.items():
        if name not in trace or trace[name].shape != (expected_n, *shape) or not np.isfinite(trace[name]).all():
            raise ValueError(f"INVALID_TRACE_FIELD: {name}")
    if trace.get("mask", np.array(0)).shape != (expected_n,) or trace["mask"].dtype != np.dtype(bool):
        raise ValueError("INVALID_TRACE_MASK")
    for name in ("pose_id", "t"):
        if not np.array_equal(packet[name], trace.get(name)):
            raise ValueError(f"PACKET_TRACE_JOIN_MISMATCH: {name}")
    if packet["pose_id"].dtype.kind not in "iu" or len(np.unique(packet["pose_id"])) != expected_n:
        raise ValueError("INVALID_POSE_IDS")
    if np.any(np.diff(packet["pose_id"]) <= 0) or np.any(np.diff(packet["t"]) <= 0):
        raise ValueError("NONMONOTONIC_INPUT")


def stored_arithmetic(packet: dict, trace: dict, expected_n: int) -> dict[str, Any]:
    """Check all W0 stored updates, retaining the original frozen mask."""
    validate_packet_trace(packet, trace, expected_n)
    prior = trace["prior"]
    previous = np.vstack((prior[:1], trace["x"][:-1]))
    rho = np.hypot(previous[:, 0] - 10.0, previous[:, 1])
    sigma = np.interp(rho, [0.0, 1.5, 3.0, 6.0, 10.0], [0.011, 0.020, 0.050, 0.120, 0.240])
    noise = packet["R"].copy()
    noise[:, 1, 1] += sigma**2
    innovation = packet["z"] - trace["h"] - packet["muMB"]
    calculated = joint_update(prior, trace["Pprior"], trace["H"], innovation, noise, trace["mask"])
    geometry = np.sqrt((prior[:, 0] - 10.0)**2 + prior[:, 1]**2 + 2.2**2)
    range_H = np.column_stack(((prior[:, 0] - 10.0) / geometry, prior[:, 1] / geometry,
                               np.zeros(expected_n), np.zeros(expected_n)))
    values = {"mu": packet["muMB"], "nu": innovation, "Rvar": noise, "Reff": noise,
              "d0": packet["z"][:, 1] - trace["h"][:, 1],
              "weight": np.ones(expected_n), "rho_before": rho, "sigma_b": sigma, **calculated}
    checks = {name: difference(value, trace[name]) for name, value in values.items()}
    checks["range_model_geometry_plus_B_OLD"] = difference(trace["h"][:, 0], geometry + B_OLD)
    checks["range_model_jacobian"] = difference(trace["H"][:, 0], range_H)
    checks["initial_P"] = difference(trace["Pprior"][0], packet["P0"])
    checks["prior_covariance"] = covariance_check(trace["Pprior"])
    checks["posterior_covariance"] = covariance_check(trace["P"])
    checks["noise_covariance"] = covariance_check(noise)
    return {"status": "PASS_STORED_ARITHMETIC" if all(v["passed"] for v in checks.values()) else "FAIL_STORED_ARITHMETIC",
            "role": "IMPLEMENTER_CHECK", "n": expected_n, "accepted": int(trace["mask"].sum()),
            "checks": checks, "mask_regenerated": False, "polarization_h_H_regenerated": False,
            "full_recursive_replay": False,
            "claim": "Stored same-prior mathematical consistency; not a baseline replay or independent audit."}


def _reference_path(repo: Path, route: str, bias: str, channel: str) -> tuple[Path, str]:
    if route == "R2":
        run = repo / EXT / ("FULL_002" if channel == "Full" else "NATIVE_001")
        relative = f"natural/R2_{bias}_{channel}_10_A.npz"
        index = _json(run / "NATURAL_INDEX.json")
    else:
        run = repo / STUDY_BASE / "S1/runs/EVAL_001"
        relative = f"{route}_aB_m0_{bias}_{channel}_10_W0.npz"
        index = _json(run / "TRACE_INDEX.json")
    matches = [record for record in index if record["file"] == relative]
    if len(matches) != 1:
        raise ValueError(f"REFERENCE_REGISTRY_NOT_UNIQUE: {relative}")
    return run / relative, matches[0]["sha256"]


def _controls(repo: Path, route: str, bias: str, packet: dict, truth: dict) -> tuple[dict, dict]:
    for key in ("t", "pose_id"):
        if not np.array_equal(packet[key], truth[key]):
            raise ValueError(f"CONTROLS_TRUTH_JOIN: {key}")
    if route == "R2":
        folder = repo / EXT / "inputs"
        name = f"R2_aB_m0_{bias}_10.npz"
        expected = _json(folder / "INPUT_LOCK.json")["files"][name]
        controls = read_npz(folder / name, expected)
        origin = {"kind": "ARCHIVED_CONTROLS", "file": str((folder / name).relative_to(repo)), "sha256": expected}
    else:
        # This is offline re-materialization of the published exp_pb recipe.
        # The resulting arrays must equal the historical byte-level array hashes.
        from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments, rng
        pose = truth["truth"]
        ds, angle = motion_increments(packet["t"], pose, convention="legacy-euler")
        if bias == "B0":
            config = SensorV2Config(level=1, condition="noise_pair", common_scale=0.0, bias_rw_rad_s_sqrt_s=0.0)
            inputs, generated_truth = generate(packet["t"], ds, angle, config, 10)
            expected_bias = 0.0
        else:
            expected_bias = math.radians(0.2)
            config = SensorV2Config(level=2, condition="all", slip_mode="off", common_scale=0.0, bias_rw_rad_s_sqrt_s=0.0)
            parameters = {"gyro_bias": expected_bias, "gyro_sf": 0.0, "wheel_asymmetry": 0.0,
                          "wheelbase": 0.0, "common_scale": 0.0}
            inputs, generated_truth = generate(packet["t"], ds, angle, config, 10, parameters=parameters)
        if np.max(np.abs(generated_truth["true_bias_rad_s"] - expected_bias)) > 1e-14:
            raise ValueError("GENERATED_GYRO_BIAS_MISMATCH")
        x0 = np.asarray(pose[0] + rng(10, "initial").standard_normal(3) * [0.1, 0.1, math.radians(5.0)])
        x0[2] = (x0[2] + math.pi) % (2 * math.pi) - math.pi
        controls = {"ds": np.asarray(inputs["ds_odom"]), "gy": np.asarray(inputs["dtheta_gyro"]),
                    "dt": np.asarray(inputs["dt_s"]), "x0": x0}
        registry = repo / STUDY_BASE / "A0_R3_REFIT/BASE_INPUTS.json"
        key = f"{route}_aB_m0_{bias}_10"
        expected = _json(registry)["controls"][key]
        actual = {name: array_sha256(value) for name, value in controls.items()}
        if actual != expected:
            raise BlockedInput(f"REGENERATED_CONTROL_ARRAY_HASH_MISMATCH: {key}; actual={actual}; expected={expected}")
        origin = {"kind": "REGENERATED_AND_EXACT_ARRAY_HASH_VERIFIED", "registry": str(registry.relative_to(repo)),
                  "registry_key": key, "array_sha256": actual, "GT_use": "offline original controls generation only"}
    n = len(packet["t"])
    for name in ("ds", "gy", "dt"):
        if controls[name].shape != (n,) or not np.isfinite(controls[name]).all():
            raise ValueError(f"INVALID_CONTROL: {name}")
    if controls["x0"].shape != (3,) or not np.isfinite(controls["x0"]).all():
        raise ValueError("INVALID_INITIAL_STATE")
    if np.any(controls["dt"][1:] <= 0) or not np.array_equal(controls["dt"], np.r_[0.0, np.diff(packet["t"])]):
        raise ValueError("CONTROL_TIME_ALIGNMENT")
    return controls, origin


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BlockedInput(f"CANNOT_IMPORT_SOURCE: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _original_model(repo: Path):
    sources = {}
    for relative, expected in ORIGINAL_CODE.items():
        payload(repo / relative, expected)
        sources[relative] = expected
    for relative, expected in BANKS.items():
        payload(repo / relative, expected)
    old_path = list(sys.path)
    try:
        sys.path[:0] = [str(repo / "research/FFD_P0P3_20261016"),
                        str(repo / "research/EKF4_RANGE_S_STAGED_20261014"), str(repo / "src")]
        for name, relative in (("p0_initial", "research/FFD_P0P3_20261016/p0_initial.py"),
                               ("p3_rf_adapter4", "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py"),
                               ("source_model", "research/FFD_P0P3_20261016/source_model.py")):
            if name in sys.modules and Path(sys.modules[name].__file__).resolve() != (repo / relative).resolve():
                raise ValueError(f"CONFLICTING_IMPORTED_SOURCE: {name}")
        source_model = importlib.import_module("source_model")
        from qclean_uwb.drivesim.pattern_apply import Bank
        banks = []
        for relative, expected in BANKS.items():
            arrays = read_npz(repo / relative, expected)
            for name in ("e_theta", "e_phi"):
                if arrays[name].shape != (257, 181, 361) or arrays[name].dtype != np.dtype("complex64"):
                    raise ValueError(f"BANK_SCHEMA_MISMATCH: {relative}/{name}")
                if not np.isfinite(arrays[name]).all():
                    raise ValueError(f"BANK_NONFINITE: {relative}/{name}")
            if not np.array_equal(arrays["freqs_hz"], 6250400000.0 + 1950000.0 * np.arange(257)):
                raise ValueError(f"BANK_FREQUENCY_MISMATCH: {relative}")
            banks.append(Bank(arrays))
        model = source_model.SourceFFD(banks=banks)
        core = _module("fp_sc_original_motion_core", repo / "research/EKF4_RANGE_S_STAGED_20261014/core.py")
        online = _module("fp_sc_original_s1_online", repo / STUDY_BASE / "S1/online.py")
    finally:
        sys.path[:] = old_path
    for relative in ("src/qclean_uwb/drivesim/pattern_apply.py", "src/qclean_uwb/drivesim/observation.py",
                     "src/qclean_uwb/drivesim/hs_lut.py", "src/qclean_uwb/scenarios/corridor.py",
                     "src/qclean_uwb/drivesim/sensor_v2.py", "src/qclean_uwb/drivesim/sensors.py"):
        sources[relative] = sha256(repo / relative)
    return core, online, model, sources


def load_original_model(repo: str | Path):
    """Load the pinned source-only FFD observer for an authorized E0 evaluator.

    Returns ``(core, original_online, model, source_hashes)``.  It validates the
    actual FFD payloads and source files; it never falls back to a geometric
    approximation.  ``model.batch(states, SPEC, return_diagnostics=True)`` gives
    the continuous range surrogate and the separate native detector range.
    """
    return _original_model(Path(repo).resolve())


def run_baseline(repo: str | Path, output_dir: str | Path, *, mode: str = "auto",
                 rematerialized_registry: str | Path | None = None) -> dict[str, Any]:
    """Run the caller-authorized E0 subset; ``arithmetic`` never starts recursion.

    ``auto`` attempts full original replay and explicitly records unavailable
    dependencies. ``full`` has the same fail-closed checks, with requested scope
    recorded. The caller should require ``PASS_FULL_BASELINE_PARITY`` before
    claiming the complete baseline parity part of E0-01. A separately reviewed
    A2 registry may supply newly frozen R4/R5 controls; this never changes the
    default historical byte-identity requirement or any numerical tolerance.
    """
    if mode not in ("auto", "arithmetic", "full"):
        raise ValueError("INVALID_BASELINE_MODE")
    repo, output = Path(repo).resolve(), Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "study": "FP-SC-001", "experiment": "E0-01_MBVAR", "mode": mode,
        "role": "IMPLEMENTER_CHECK", "independent_acceptance": False, "status": "RUNNING",
        "scope": {"routes": list(ROUTE_ROWS), "biases": ["B0", "L2"], "channels": ["Full", "Native_LoS"], "seeds": [10]},
        "utc_start": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runtime": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()},
        "numeric_contract": {"normalized_error_max": TOL, "normalization": "abs(delta)/max(1,abs(reference))", "covariance_relative_tolerance": 1e-12},
        "new_RT_calls": 0, "new_data_calibration_fits": 0, "cells": rows,
        "control_reproduction_mode": "HISTORICAL_IDENTITY" if rematerialized_registry is None else "A2_REMATERIALIZED_CONTROLS",
        "exact_historical_control_bytes": "REQUIRED" if rematerialized_registry is None else "UNRESOLVED_R4_R5",
        "source_model_initialization": "Original deterministic FFD source-ring polynomial cap fit; no new RF-label training.",
    }
    _put(output / "MANIFEST.json", manifest)
    (output / "FAILURES.jsonl").touch()
    model_status: dict[str, Any] = {"status": "NOT_REQUESTED_ARITHMETIC_ONLY"}
    original = None
    try:
        registry = _json(repo / PACKETS / "MANIFEST.json")
        if mode != "arithmetic":
            print("[FP-SC E0 baseline] Loading pinned SourceFFD and verified FFD banks.", flush=True)
            try:
                original = _original_model(repo)
                model_status = {"status": "READY", "code_sha256": original[3], "bank_sha256": BANKS}
                print("[FP-SC E0 baseline] SourceFFD ready; original W0 replay enabled.", flush=True)
            except BlockedInput as error:
                model_status = {"status": "BLOCKED_DATA", "reason": str(error)}
                print(f"[FP-SC E0 baseline] SourceFFD blocked: {error}", flush=True)
        manifest["source_model"] = model_status
        for route, n in ROUTE_ROWS.items():
            for bias in ("B0", "L2"):
                for channel in ("Full", "Native_LoS"):
                    cell = f"{route}_{bias}_{channel}_10"
                    record: dict[str, Any] = {"cell": cell, "route": route, "bias": bias, "channel": channel, "seed": 10, "expected_rows": n}
                    rows.append(record)
                    try:
                        name = f"algorithm_input/{route}_aB_m0_{bias}_{channel}.npz"
                        packet_path = repo / PACKETS / name
                        packet = read_npz(packet_path, registry[name]["sha256"])
                        ref_path, ref_sha = _reference_path(repo, route, bias, channel)
                        reference = read_npz(ref_path, ref_sha)
                        record["inputs"] = {"packet": {"path": str(packet_path.relative_to(repo)), "sha256": registry[name]["sha256"]},
                                            "reference": {"path": str(ref_path.relative_to(repo)), "sha256": ref_sha}}
                        check = stored_arithmetic(packet, reference, n)
                        record["stored_arithmetic"] = check
                        record["recursive"] = {"status": "BLOCKED_SOURCE_MODEL" if original is None else "NOT_RUN",
                                                "mask_regenerated": False, "h_H_regenerated": False}
                        if check["status"] != "PASS_STORED_ARITHMETIC":
                            raise ValueError(f"STORED_ARITHMETIC_FAIL: {cell}")
                        if original is not None:
                            truth_name = f"evaluator_truth/{route}_{bias}_TRUTH.npz"
                            truth = read_npz(repo / PACKETS / truth_name, registry[truth_name]["sha256"])
                            if rematerialized_registry is not None and route in ("R4", "R5"):
                                from qclean_uwb.fp_sc.e0_rematerialized import load_rematerialized_controls
                                controls, provenance = load_rematerialized_controls(
                                    repo, route, bias, packet, rematerialized_registry)
                            else:
                                controls, provenance = _controls(repo, route, bias, packet, truth)
                            record["controls"] = provenance
                            # Truth is used only by the offline controls materializer;
                            # the original replay receives packet and controls only.
                            core, online, model, _ = original
                            replayed = online.replay(packet, controls, "W0", core, model, SPEC)
                            checks = {name: difference(replayed[name], reference[name]) for name in REPLAY_FIELDS}
                            checks["mask"] = difference(replayed["mask"], reference["mask"])
                            checks["posterior_covariance"] = covariance_check(replayed["P"])
                            checks["prior_covariance"] = covariance_check(replayed["Pprior"])
                            passed = all(value["passed"] for value in checks.values())
                            record["recursive"] = {"status": "PASS" if passed else "FAIL", "checks": checks,
                                                    "mask_regenerated": True, "h_H_regenerated": True,
                                                    "n": n, "accepted": int(replayed["mask"].sum())}
                            # Timing is diagnostic only; this is not an E5 5Hz test.
                            np.savez_compressed(output / f"{cell}_REPLAY.npz", **replayed, t=packet["t"], pose_id=packet["pose_id"])
                            np.savez_compressed(output / f"{cell}_CONTROLS.npz", **controls)
                            if not passed:
                                raise ValueError(f"FULL_RECURSIVE_PARITY_FAIL: {cell}")
                        record["status"] = "PASS_FULL" if record["recursive"]["status"] == "PASS" else "PARTIAL_STORED_ARITHMETIC"
                    except BlockedInput as error:
                        record["status"] = "BLOCKED_DATA"
                        record["reason"] = str(error)
                    except Exception as error:
                        record["status"] = "FAIL"
                        record["reason"] = f"{type(error).__name__}: {error}"
                        with (output / "FAILURES.jsonl").open("a", encoding="utf-8") as log:
                            log.write(json.dumps({"cell": cell, "error": record["reason"]}) + "\n")
                    _put(output / f"{cell}.json", record)
                    _put(output / "MANIFEST.json", manifest)
                    print(f"[FP-SC E0 baseline] {len(rows)}/12 {cell}: {record['status']} "
                          f"(arithmetic={record.get('stored_arithmetic', {}).get('status', 'NOT_RUN')}, "
                          f"recursive={record.get('recursive', {}).get('status', 'NOT_RUN')})", flush=True)
        statuses = [record["status"] for record in rows]
        if any(status == "FAIL" for status in statuses):
            status = "FAIL_BASELINE_PARITY"
        elif len(rows) == 12 and all(status == "PASS_FULL" for status in statuses):
            status = "PASS_FULL_BASELINE_PARITY"
        elif any(record.get("stored_arithmetic", {}).get("status") == "PASS_STORED_ARITHMETIC" for record in rows):
            status = "PARTIAL_BASELINE_PARITY"
        else:
            status = "BLOCKED_DATA"
        manifest.update(status=status, utc_end=dt.datetime.now(dt.timezone.utc).isoformat(),
                        completed_recursive_cells=statuses.count("PASS_FULL"),
                        completed_stored_arithmetic_cells=sum(record.get("stored_arithmetic", {}).get("status") == "PASS_STORED_ARITHMETIC" for record in rows),
                        full_recursive_gate_pass=status == "PASS_FULL_BASELINE_PARITY",
                        controls_regenerated_from_truth_offline_only=True)
        with (output / "CELL_SUMMARY.csv").open("w", newline="", encoding="utf-8") as handle:
            fields = ("cell", "expected_rows", "status", "arithmetic", "recursive", "reason")
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in rows:
                writer.writerow({"cell": record["cell"], "expected_rows": record["expected_rows"], "status": record["status"],
                                 "arithmetic": record.get("stored_arithmetic", {}).get("status", "NOT_RUN"),
                                 "recursive": record.get("recursive", {}).get("status", "NOT_RUN"), "reason": record.get("reason", "")})
    except Exception as error:
        manifest.update(status="FAILED", error=f"{type(error).__name__}: {error}", utc_end=dt.datetime.now(dt.timezone.utc).isoformat())
        with (output / "FAILURES.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"global_error": manifest["error"]}) + "\n")
        _put(output / "MANIFEST.json", manifest)
        raise
    _put(output / "MANIFEST.json", manifest)
    _put(output / "ARTIFACT_HASHES.json", {path.name: sha256(path) for path in sorted(output.iterdir()) if path.is_file() and path.name != "ARTIFACT_HASHES.json"})
    return manifest
