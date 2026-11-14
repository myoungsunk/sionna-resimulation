"""Validate TB3 G4 with frozen M1-T direct-distance LoS observations."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import json
import math
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np


CASES = tuple(
    f"{geometry}_{anchor}"
    for geometry in ("G-T1", "G-T2", "G-V")
    for anchor in ("A", "B", "C")
) + ("G-T1_A_P-F", "G-T1_B_P-F")
DIAGNOSTIC_ARMS = ("P-D", "P-E", "P-F")
MOUNT_DEG = 0.0
RELATIVE_ANGLE_TOL_RAD = 1e-4
DELAY_TOL_S = 2e-13
LOS_RECONSTRUCTION_TOL = 1e-6
MODEL_SOURCE_SHA256 = {
    "qclean_uwb/drivesim/hs_lut.py": "24f1007e12d84dc68e07ab62164b92997a5a92377c1079ec679505da4ca5d8a6",
    "qclean_uwb/drivesim/observation.py": "95079dc044a31d94a1aa7f771fb0d59093d15571bcc4752167ad93e47837dbab",
    "qclean_uwb/drivesim/pattern_apply.py": "ab991a70a7333dbd7b0b9b90d8845ce306fc5e1bd6c73de7c6e62184242969e8",
    "qclean_uwb/scenarios/corridor.py": "38c42cb12a8492679652b862a3d614a5c04d4b208b041098b215f52fc2b3354e",
}
BANK_SHA256 = {
    "LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
    "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_bytes())


def wrap_rad(angle):
    return (np.asarray(angle) + np.pi) % (2 * np.pi) - np.pi


def quantiles(values):
    data = np.asarray(values, dtype=np.float64)
    if not len(data) or not np.isfinite(data).all():
        raise ValueError("G4 requires a nonempty set of finite observation differences")
    return {
        "n_observations": int(len(data)),
        "median_abs_delta_s": float(np.quantile(data, 0.5)),
        "p90_abs_delta_s": float(np.quantile(data, 0.9)),
        "max_abs_delta_s": float(data.max()),
    }


def load_model(args):
    source = args.model_source.resolve()
    src = source / "src" if (source / "src").is_dir() else source
    sys.path.insert(0, str(src))
    actual_hashes = {
        name: sha256(src / name) for name in MODEL_SOURCE_SHA256
    }
    if actual_hashes != MODEL_SOURCE_SHA256:
        raise ValueError("Pinned G1-MODEL-001 source hashes do not match")
    model = importlib.import_module("qclean_uwb.drivesim.hs_lut")
    observation = importlib.import_module("qclean_uwb.drivesim.observation")
    pattern = importlib.import_module("qclean_uwb.drivesim.pattern_apply")

    banks = []
    bank_hashes = {}
    for name, expected in BANK_SHA256.items():
        path = args.banks_dir / name
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"FFD bank SHA-256 mismatch for {name}")
        with np.load(path, allow_pickle=False) as archive:
            banks.append(pattern.Bank(dict(archive)))
        bank_hashes[name] = actual
    frequencies = np.asarray(banks[0].freqs_hz, dtype=np.float64)
    if any(not np.array_equal(frequencies, bank.freqs_hz) for bank in banks[1:]):
        raise ValueError("FFD bank frequency axes differ")
    return model, observation, banks, frequencies, actual_hashes, bank_hashes


def validate_path_archive(path: Path, poses, h_los, frequencies, scene, anchor_name):
    with np.load(path, allow_pickle=False) as archive:
        required = {
            "a", "tau", "counts", "interactions", "theta_t", "phi_t",
            "theta_r", "phi_r", "freqs_hz",
        }
        if not required.issubset(archive.files):
            raise ValueError(f"PATHS_LOS fields missing: {sorted(required - set(archive.files))}")
        arrays = {key: np.array(archive[key], copy=True) for key in required}

    count = len(poses)
    shape = (count, len(frequencies))
    if (arrays["a"].shape != (count, len(frequencies), 2, 2)
            or arrays["a"].dtype.kind != "c"
            or arrays["tau"].shape != shape
            or arrays["counts"].shape != shape
            or arrays["interactions"].shape != shape
            or any(arrays[name].shape != shape for name in ("theta_t", "phi_t", "theta_r", "phi_r"))
            or not np.array_equal(arrays["freqs_hz"], frequencies)):
        raise ValueError("PATHS_LOS dimensions or frequency axis do not match H_LoS and poses")
    if not np.all(arrays["counts"] == 1) or not np.all(arrays["interactions"] == 0):
        raise ValueError("PATHS_LOS must contain exactly one interaction-free LoS path per bin")

    anchors = scene["anchors_xyz_m"]
    anchor = np.asarray(anchors[anchor_name], dtype=np.float64)
    robot_z = float(scene["rx_z_m"])
    coords = np.asarray([[row["x"], row["y"], robot_z] for row in poses], dtype=np.float64)
    vectors = coords - anchor
    distances = np.linalg.norm(vectors, axis=1)
    units = vectors / distances[:, None]
    expected_tau = distances / 299792458.0
    if np.max(np.abs(arrays["tau"] - expected_tau[:, None])) > DELAY_TOL_S:
        raise ValueError("PATHS_LOS delay rows do not align with the case pose coordinates")
    expected_angles = np.column_stack((
        np.arccos(np.clip(units[:, 2], -1.0, 1.0)),
        np.arctan2(units[:, 1], units[:, 0]),
        np.arccos(np.clip(-units[:, 2], -1.0, 1.0)),
        np.arctan2(-units[:, 1], -units[:, 0]),
    ))
    expected_angles[:, (1, 3)] = (expected_angles[:, (1, 3)] + np.pi) % (2 * np.pi) - np.pi
    actual_angles = np.column_stack(tuple(
        np.asarray(arrays[name])[:, 0] for name in ("theta_t", "phi_t", "theta_r", "phi_r")
    ))
    angular_error = np.abs(wrap_rad(actual_angles - expected_angles))
    if np.max(angular_error) > RELATIVE_ANGLE_TOL_RAD:
        raise ValueError("PATHS_LOS directions do not align with the case coordinates")

    reconstructed = arrays["a"] * np.exp(
        -2j * np.pi * arrays["freqs_hz"][None, :, None, None]
        * arrays["tau"][:, :, None, None]
    )
    relative_error = np.abs(reconstructed - h_los) / np.maximum(np.abs(h_los), 1e-300)
    exact_zero_mismatch = np.any((h_los == 0) & (reconstructed != 0))
    if np.max(relative_error) >= LOS_RECONSTRUCTION_TOL or exact_zero_mismatch:
        raise ValueError("H_LoS does not match its PATHS_LOS coefficient and delay rows")
    return {
        "max_delay_geometry_error_s": float(np.max(np.abs(arrays["tau"] - expected_tau[:, None]))),
        "max_direction_error_rad": float(np.max(angular_error)),
        "max_h_reconstruction_relative_error": float(np.max(relative_error)),
        "path_rows": int(count),
        "unique_los_paths_per_pose_bin": True,
    }


def evaluate_case(results_root, case, model, observation, banks, frequencies):
    poses_dir = results_root / "poses" / case
    h_path = results_root / "H" / case / "H_LoS.npy"
    paths_path = results_root / "paths" / case / "PATHS_LoS.npz"
    pose_path = poses_dir / "rf_poses.json"
    samples_path = poses_dir / "SAMPLES.json"
    scene_path = poses_dir / "SCENE_ENTRY.json"
    for path in (pose_path, samples_path, scene_path, h_path, paths_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    poses = read_json(pose_path)
    samples = read_json(samples_path)
    scene = read_json(scene_path)
    h_los = np.load(h_path, allow_pickle=False)
    if (h_los.dtype != np.complex128 or h_los.shape != (len(poses), len(frequencies), 2, 2)
            or not np.isfinite(h_los).all()):
        raise ValueError(f"{case}: expected finite complex128 H_LoS aligned to the pose table")
    if not poses or [row["pose_id"] for row in poses] != list(range(len(poses))):
        raise ValueError(f"{case}: RF pose IDs are not contiguous and ordered")
    path_checks = validate_path_archive(
        paths_path, poses, h_los, frequencies, scene, case.split("_")[1]
    )

    anchor = np.asarray(scene["anchors_xyz_m"][case.split("_")[1]], dtype=np.float64)
    rx_z = float(scene["rx_z_m"])
    position = np.asarray([[row["x"], row["y"], rx_z] for row in poses], dtype=np.float64)
    vector = position - anchor
    distance = np.linalg.norm(vector, axis=1)
    if not np.isfinite(distance).all() or np.any(distance <= 0):
        raise ValueError(f"{case}: invalid transmitter-receiver separation")
    unit = vector / distance[:, None]
    yaw = np.asarray([row["yaw_body_deg"] for row in poses], dtype=np.float64) + MOUNT_DEG
    direct_h = np.stack([
        model.los_h(banks, direction, float(angle), dist_m=float(range_m))
        for direction, angle, range_m in zip(unit, yaw, distance, strict=True)
    ])
    direct_s = observation.observe(direct_h, frequencies, None, None, tx=0)["s"]
    saved_s = observation.observe(h_los, frequencies, None, None, tx=0)["s"]
    delta = np.abs(saved_s - direct_s)
    if not np.isfinite(delta).all():
        raise ValueError(f"{case}: non-finite M1-T s difference")
    if len(samples) == 0 or any(not 0 <= row["pose_id"] < len(poses) for row in samples):
        raise ValueError(f"{case}: invalid SAMPLES pose references")
    referenced = {row["pose_id"] for row in samples}
    if referenced != set(range(len(poses))):
        raise ValueError(f"{case}: SAMPLES do not reference every pose in H_LoS")

    by_set = defaultdict(list)
    for row in samples:
        by_set[row["set"]].append(float(delta[row["pose_id"]]))
    by_arm = {"original": []}
    for name in DIAGNOSTIC_ARMS:
        if any(row["set"] == name for row in samples):
            by_arm[name] = []
    for row in samples:
        arm = row["set"] if row["set"] in DIAGNOSTIC_ARMS else "original"
        by_arm[arm].append(float(delta[row["pose_id"]]))
    arm_metrics = {name: quantiles(values) for name, values in by_arm.items() if values}
    gate_passed = all(metric["p90_abs_delta_s"] <= 0.005 for metric in arm_metrics.values())
    return {
        "status": "PASS" if gate_passed else "FAIL",
        "gate_by_arm": {
            name: metric | {"threshold_p90_abs_delta_s": 0.005,
                            "passed": metric["p90_abs_delta_s"] <= 0.005}
            for name, metric in arm_metrics.items()
        },
        "by_set": {name: quantiles(values) for name, values in sorted(by_set.items())},
        "unique_pose_metrics": quantiles(delta),
        "path_archive_checks": path_checks,
        "input_sha256": {
            "rf_poses.json": sha256(pose_path),
            "SAMPLES.json": sha256(samples_path),
            "SCENE_ENTRY.json": sha256(scene_path),
            "H_LoS.npy": sha256(h_path),
            "PATHS_LoS.npz": sha256(paths_path),
        },
        "_delta_by_pose": delta.tolist(),
    }


def run(args):
    model, observation, banks, frequencies, source_hashes, bank_hashes = load_model(args)
    case_results = {}
    for case in CASES:
        case_results[case] = evaluate_case(
            args.results_root, case, model, observation, banks, frequencies
        )
        print(f"{case}: {case_results[case]['status']}", flush=True)
    aggregate_values = {name: [] for name in ("original", *DIAGNOSTIC_ARMS)}
    for case in CASES:
        samples = read_json(args.results_root / "poses" / case / "SAMPLES.json")
        delta = case_results[case].pop("_delta_by_pose")
        for row in samples:
            name = row["set"] if row["set"] in DIAGNOSTIC_ARMS else "original"
            aggregate_values[name].append(float(delta[row["pose_id"]]))
    aggregate_report = {
        arm: quantiles(values)
        for arm, values in aggregate_values.items()
        if values
    }
    return {
        "question_id": "G1-RT-TB3-001",
        "gate": "G4",
        "metric": "abs(s_saved_noise_free_los - s_M1_T_direct_distance)",
        "status": "PASS" if all(row["status"] == "PASS" for row in case_results.values()) else "FAIL",
        "threshold_p90_abs_delta_s": 0.005,
        "cases": case_results,
        "aggregates": aggregate_report,
        "model_source_sha256": source_hashes,
        "ffd_bank_sha256": bank_hashes,
        "frequencies_hz": [float(frequencies[0]), float(frequencies[-1])],
        "n_frequency_bins": int(len(frequencies)),
        "mount_deg": MOUNT_DEG,
        "execution": {
            "host": platform.node(),
            "python": sys.version.split()[0],
            "numpy": np.__version__,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--model-source", type=Path, required=True,
                        help="Frozen G1-MODEL source root or its src/ directory")
    parser.add_argument("--banks-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    result = run(args)
    result["execution"].update(
        command=[sys.executable, *sys.argv],
        started_utc=started_utc,
        elapsed_seconds=time.monotonic() - start,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"G4 {result['status']}: {len(result['cases'])} cases; {args.out}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
