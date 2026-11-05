"""FP-SC-001 E0 receiver reproduction and range accounting.

This module has no candidate selector, online policy, new RT, or fitting.  The
unchanged receiver in ``drivesim.observation`` supplies all production receiver
values.  A separately authored checker must establish numerical parity; these
functions do not call that checker or label their own replay independent.

The caller owns authorization, code/input/environment locks, and the run-level
manifest.  Every runner below creates a NEW output directory, records the input
bytes it actually read, and reports absent LFS payloads as BLOCKED_DATA.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from qclean_uwb.drivesim import observation as source


RF_ROOT = Path("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C")
PHYSICAL_ROOT = Path("research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104")
C1A_ROOT = PHYSICAL_ROOT / "C1/C1A_001"
G4_ROOT = PHYSICAL_ROOT / "C3/G4_001"
ORACLE_ROOT = PHYSICAL_ROOT / "FP_PRIOR_PILOT_001/RESULTS_ORACLE_001"
EXPECTED_POSES = {"R2": 979, "R4": 742, "R5": 1415}
N_BINS = 257
N_TAPS = 1028
DF_HZ = 1_950_000.0
ANCHOR_B = (10.0, 0.0, 2.6500000000000004)
ROBOT_Z_M = 0.45


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class MissingPayload(RuntimeError):
    """A path is missing or contains an LFS pointer rather than array bytes."""

    def __init__(self, path: Path, pointer: Mapping[str, Any] | None = None):
        self.path = str(path)
        self.pointer = dict(pointer or {})
        super().__init__(f"BLOCKED_DATA: {path}")

    def record(self) -> dict[str, Any]:
        return {"path": self.path, "status": "BLOCKED_DATA", **self.pointer}


def require_payload(path: Path) -> Path:
    path = Path(path)
    if not path.is_file():
        raise MissingPayload(path, {"reason": "MISSING_FILE"})
    with path.open("rb") as handle:
        prefix = handle.read(512)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        pointer: dict[str, Any] = {"reason": "LFS_POINTER_NOT_PAYLOAD"}
        for line in prefix.decode("ascii").splitlines():
            if line.startswith("oid sha256:"):
                pointer["expected_payload_sha256"] = line.split(":", 1)[1]
            elif line.startswith("size "):
                pointer["expected_payload_bytes"] = int(line.split()[1])
        raise MissingPayload(path, pointer)
    return path


def load_npz_payload(path: Path) -> dict[str, np.ndarray]:
    require_payload(path)
    with np.load(path, allow_pickle=False) as data:
        return {name: data[name] for name in data.files}


def input_record(path: Path, arrays: Mapping[str, np.ndarray] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path), "bytes": path.stat().st_size,
        "sha256": sha256_file(path), "actual_payload_read": True,
    }
    if arrays is not None:
        record["arrays"] = {
            key: {"shape": list(value.shape), "dtype": str(value.dtype)}
            for key, value in arrays.items()
        }
    return record


def put_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8")


def write_rows(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("x", newline="", encoding="utf8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def finite_scalar(value: Any) -> float | None:
    return float(value) if np.isfinite(value) else None


def validate_frequencies(freqs_hz: np.ndarray) -> float:
    freq = np.asarray(freqs_hz)
    if freq.shape != (N_BINS,) or freq.dtype != np.dtype("float64"):
        raise ValueError("expected float64 frequency grid with 257 bins")
    if not np.isfinite(freq).all() or not np.all(np.diff(freq) > 0):
        raise ValueError("frequency grid must be finite and increasing")
    if not np.allclose(np.diff(freq), DF_HZ, rtol=0.0, atol=1e-6):
        raise ValueError("frequency spacing differs from frozen 1.95 MHz")
    return float(freq[1] - freq[0])


def source_range_offset(repo_root: Path) -> tuple[float, dict[str, Any]]:
    """Read the literal B_OLD without importing Windows-bound legacy modules."""
    path = Path(repo_root) / "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py"
    require_payload(path)
    values = []
    for node in ast.parse(path.read_text(encoding="utf8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "B_OLD" for t in node.targets):
            values.append(float(ast.literal_eval(node.value)))
    if len(values) != 1 or not np.isfinite(values[0]):
        raise ValueError("unambiguous finite source B_OLD literal required")
    return values[0], input_record(path)


def snapshot_from_cir(cir: np.ndarray, df_hz: float, *, threshold: float = 0.0,
                      denominator_floor: float = 0.0) -> dict[str, np.ndarray | float]:
    """Original detector plus explicit RX and separate arithmetic validity.

    Zero clean CIR deliberately remains detected=True/tap=0/range=0/s=NaN,
    matching the original receiver.  ``reference_valid`` rejects that sample.
    A positive denominator alone is NOT a calibrated low-SNR support claim.
    """
    cir = np.asarray(cir)
    if cir.ndim != 3 or cir.shape[1:] != (N_TAPS, 2) or not np.iscomplexobj(cir):
        raise ValueError("CIR must have shape (N, 1028, 2) and complex dtype")
    if not np.isfinite(cir).all():
        raise ValueError("nonfinite CIR")
    if not np.isfinite([df_hz, threshold, denominator_floor]).all() or df_hz <= 0 or threshold < 0 or denominator_floor < 0:
        raise ValueError("invalid detector units/support threshold")
    out = source.first_path_batch(cir, df_hz)
    out["rx"] = np.abs(cir).max(axis=1).argmax(axis=1)
    out["detected"] = out["peak"] >= threshold
    for key in ("s", "range_m", "delay_s"):
        out[key] = np.where(out["detected"], out[key], np.nan)
    den = out["power"].sum(axis=1)
    out["denominator"] = den
    out["reference_valid"] = out["detected"] & (den > denominator_floor) & np.isfinite(out["s"]) & np.isfinite(out["range_m"])
    out["threshold"] = float(threshold)
    out["cir"] = cir
    return out


def receiver_snapshot(h_clean: np.ndarray, freqs_hz: np.ndarray, *,
                      noise_var: float | None = None, seed: int | None = None,
                      tx: int = 0, threshold: float | None = None,
                      denominator_floor: float = 0.0) -> dict[str, Any]:
    """Call the original receiver once, retaining its exact batch noise order.

    A seed here defines an explicit new realization unless external evidence
    proves the archived RNG state, shape and call order.  The function never
    calls noise-free arrays 'the original noisy packet'.
    """
    df = validate_frequencies(freqs_hz)
    h = np.asarray(h_clean)
    if h.ndim != 4 or h.shape[1:3] != (N_BINS, 2) or h.shape[3] not in (1, 2):
        raise ValueError("CFR must have axes (N, 257, 2 RX, 1 or 2 TX)")
    if not np.iscomplexobj(h) or not np.isfinite(h).all():
        raise ValueError("finite complex CFR required")
    if not isinstance(tx, (int, np.integer)) or not 0 <= tx < h.shape[3]:
        raise ValueError("TX column out of bounds")
    if noise_var is not None and (not np.isfinite(noise_var) or noise_var < 0):
        raise ValueError("nonnegative finite noise variance required")
    if noise_var and seed is None:
        raise ValueError("explicit noise seed required")
    rng = np.random.default_rng(seed) if noise_var else None
    original = source.observe(h, freqs_hz, noise_var, rng, tx=tx, threshold=threshold, return_h=True)
    cir = source.cir_batch(original["h_noisy"])
    enriched = snapshot_from_cir(cir, df, threshold=float(original["threshold"]), denominator_floor=denominator_floor)
    for key in ("index", "s", "power", "range_m", "delay_s", "peak", "detected"):
        # This is an internal adapter check, not independent numerical parity.
        if not np.array_equal(original[key], enriched[key], equal_nan=True):
            raise ValueError("adapter changed original receiver: " + key)
    enriched["h_noisy"] = original["h_noisy"]
    enriched["noise_var"] = float(noise_var or 0.0)
    enriched["noise_seed"] = seed if noise_var else None
    return enriched


def validate_pose_join(left: Mapping[str, np.ndarray], right: Mapping[str, np.ndarray] | None,
                       *, expected_count: int, rf_count: int | None = None) -> np.ndarray:
    ids = np.asarray(left["pose_id"])
    t = np.asarray(left["t"])
    if ids.shape != (expected_count,) or t.shape != (expected_count,):
        raise ValueError("pose/time denominator mismatch")
    if not np.issubdtype(ids.dtype, np.integer):
        raise ValueError("pose_id must retain integer source dtype")
    if np.any(ids < 0) or len(np.unique(ids)) != len(ids) or np.any(np.diff(ids) <= 0):
        raise ValueError("pose IDs must be unique, nonnegative and increasing")
    if not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("strictly increasing finite timeline required")
    if rf_count is not None and ids.max(initial=-1) >= rf_count:
        raise ValueError("pose IDs exceed raw RF array")
    if right is not None:
        for key in ("pose_id", "t"):
            if not np.array_equal(left[key], right[key]):
                raise ValueError("exact pose/time join failed: " + key)
    return ids


def geometric_range(states: np.ndarray, *, anchor: Sequence[float] = ANCHOR_B,
                    robot_z_m: float = ROBOT_Z_M) -> np.ndarray:
    x = np.asarray(states)
    a = np.asarray(anchor, dtype=float)
    if x.ndim != 2 or x.shape[1] < 2 or a.shape != (3,) or not np.isfinite(x).all() or not np.isfinite(a).all() or not np.isfinite(robot_z_m):
        raise ValueError("finite state/anchor geometry required")
    return np.sqrt((x[:, 0] - a[0]) ** 2 + (x[:, 1] - a[1]) ** 2 + (robot_z_m - a[2]) ** 2)


def range_accounting(r_det: np.ndarray, *, b_old: float,
                     original_z_r: np.ndarray | None = None,
                     original_mu_r: np.ndarray | None = None,
                     r_geo: np.ndarray | None = None,
                     r_state: np.ndarray | None = None,
                     h_r: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Keep clean extraction, archived packet correction and state prediction distinct."""
    det = np.asarray(r_det, dtype=float)
    if det.ndim != 1 or not np.isfinite(b_old):
        raise ValueError("invalid range accounting inputs")
    n = len(det)
    arrays = {"r_det_clean_m": det, "r_det_clean_minus_B_OLD_m": det - b_old}
    for name, value in (("r_geo_m", r_geo), ("r_state_m", r_state), ("h_r_archived_m", h_r),
                        ("z_r_archived_m", original_z_r), ("mu_r_archived_m", original_mu_r)):
        if value is not None:
            value = np.asarray(value, dtype=float)
            if value.shape != (n,):
                raise ValueError("range vector shape mismatch: " + name)
            arrays[name] = value
    if original_z_r is not None and original_mu_r is not None:
        corrected_detector = arrays["z_r_archived_m"] - arrays["mu_r_archived_m"]
        arrays["z_r_minus_mu_r_m"] = corrected_detector
        arrays["r_corrected_archived_m"] = corrected_detector - b_old
        arrays["clean_old_mu_mechanism_only_m"] = det - arrays["mu_r_archived_m"] - b_old
    if r_geo is not None:
        for name in ("r_det_clean_m", "r_det_clean_minus_B_OLD_m", "r_corrected_archived_m", "r_state_m"):
            if name in arrays:
                arrays["error_" + name] = arrays[name] - arrays["r_geo_m"]
    if r_state is not None and h_r is not None:
        arrays["h_r_minus_state_plus_B_OLD_m"] = arrays["h_r_archived_m"] - (arrays["r_state_m"] + b_old)
    return arrays


def signed_error_stats(values: np.ndarray, step_m: float) -> dict[str, Any]:
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    x = values[finite]
    if not len(x):
        return {"rows": int(len(values)), "valid": 0, "invalid": int(len(values))}
    a = np.abs(x)
    return {
        "rows": int(len(values)), "valid": int(len(x)), "invalid": int((~finite).sum()),
        "signed_bias_m": float(x.mean()), "mae_m": float(a.mean()),
        "rmse_m": float(np.sqrt(np.mean(x * x))), "p95_abs_m": float(np.quantile(a, .95)),
        "p99_abs_m": float(np.quantile(a, .99)), "max_abs_m": float(a.max()),
        "within_4cm_fraction": float(np.mean(a <= .04)),
        "within_one_tap_fraction": float(np.mean(a <= step_m)),
    }


def _optional_npz(path: Path, evidence: list[dict[str, Any]], blocked: list[dict[str, Any]]) -> dict[str, np.ndarray] | None:
    try:
        data = load_npz_payload(path)
    except MissingPayload as exc:
        blocked.append(exc.record())
        return None
    evidence.append(input_record(path, data))
    return data


def _numeric_checks(actual: np.ndarray, expected: np.ndarray, *, scale: float = 1.0,
                    tolerance: float = 1e-10, exact: bool = False) -> dict[str, Any]:
    a, b = np.asarray(actual), np.asarray(expected)
    if a.shape != b.shape:
        return {"pass": False, "reason": "SHAPE", "actual": list(a.shape), "expected": list(b.shape)}
    finite_a, finite_b = np.isfinite(a), np.isfinite(b)
    masks_equal = np.array_equal(finite_a, finite_b) and np.array_equal(np.isnan(a), np.isnan(b))
    finite = finite_a & finite_b
    max_abs = float(np.max(np.abs(a[finite] - b[finite]), initial=0.0))
    passed = bool(np.array_equal(a, b, equal_nan=True)) if exact else bool(masks_equal and max_abs / scale <= tolerance)
    return {"pass": passed, "max_absolute_error": max_abs, "scale": scale,
            "max_normalized_error": max_abs / scale, "tolerance": 0.0 if exact else tolerance,
            "nan_finite_masks_equal": bool(masks_equal), "elements": int(a.size)}


def run_dynamic(repo_root: Path, output_dir: Path, *, biases: Sequence[str] = ("B0", "L2"),
                seed: int = 10, routes: Sequence[str] = ("R2", "R4", "R5"),
                trace_paths: Mapping[str, str] | None = None,
                denominator_floor: float = 0.0) -> dict[str, Any]:
    """Re-extract aligned clean RF and audit the four distinct range quantities.

    ``trace_paths`` keys are ``R2_B0_Full`` etc.  Without an override, the Full
    C1a trace supplies the Full prior.  A Full prior is never silently called a
    Native-LoS prior.  Missing traces do not prevent available receiver rows,
    but leave the corresponding state-range component explicitly untested.
    """
    root, out = Path(repo_root), Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    evidence: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "experiment_ids": ["E0-01", "E0-02"], "scope": "clean original RF and archived packet accounting; no selector",
        "noise": "CLEAN_H; archived z kept as a separate input; noisy-waveform parity not established here",
        "independent_audit": False, "new_rt_calls": 0, "new_filter_replays": 0,
        "reference_validity": "detected, finite s/r, denominator above externally fixed floor; no calibrated weak-signal claim",
        "denominator_floor": denominator_floor, "cells": [], "missing": blocked, "inputs": evidence,
    }
    freq_path = root / RF_ROOT / "freqs_hz.npy"
    try:
        freq = np.load(require_payload(freq_path), allow_pickle=False)
        df = validate_frequencies(freq)
        b_old, b_evidence = source_range_offset(root)
    except MissingPayload as exc:
        blocked.append(exc.record())
        report["status"] = "BLOCKED_DATA"
        put_json(out / "SUMMARY.json", report)
        return report
    evidence.extend([input_record(freq_path, {"freqs_hz": freq}), b_evidence])
    step = source.C0 / (N_TAPS * df)
    report.update(step_m=step, source_B_OLD_m=b_old,
                  corrected_range_definition="archived_z_r - archived_muMB_r - B_OLD; model h_r=geometry+B_OLD")
    snapshots: dict[tuple[str, str], tuple[np.ndarray, Path]] = {}
    for route in routes:
        if route not in EXPECTED_POSES:
            raise ValueError("unregistered route")
        for channel in ("Full", "Native_LoS"):
            rf = root / RF_ROOT / (f"FULL_RF/H_{route}_aB_m0.npy" if channel == "Full" else f"H_LoS_{route}_aB_m0.npy")
            try:
                raw = np.load(require_payload(rf), allow_pickle=False, mmap_mode="r")
            except MissingPayload as exc:
                blocked.append(exc.record())
                continue
            if raw.ndim != 4 or raw.shape[1:] != (N_BINS, 2, 2) or raw.dtype != np.dtype("complex128"):
                raise ValueError("archived RF shape/dtype mismatch: " + str(rf))
            evidence.append(input_record(rf, {"H": raw}))
            snapshots[(route, channel)] = (raw, rf)
        for bias in biases:
            if bias not in ("B0", "L2"):
                raise ValueError("unregistered bias")
            truth_path = root / C1A_ROOT / "FROZEN_PACKETS/evaluator_truth" / f"{route}_{bias}_TRUTH.npz"
            truth = _optional_npz(truth_path, evidence, blocked)
            for channel in ("Full", "Native_LoS"):
                key = f"{route}_{bias}_{channel}"
                packet_path = root / C1A_ROOT / "FROZEN_PACKETS/algorithm_input" / f"{route}_aB_m0_{bias}_{channel}.npz"
                packet = _optional_npz(packet_path, evidence, blocked)
                if packet is None or (route, channel) not in snapshots:
                    report["cells"].append({"cell": key, "status": "BLOCKED_DATA", "rows": 0})
                    continue
                raw, rf = snapshots[(route, channel)]
                ids = validate_pose_join(packet, truth, expected_count=EXPECTED_POSES[route], rf_count=len(raw))
                snapshot = receiver_snapshot(np.asarray(raw[ids]), freq, denominator_floor=denominator_floor)
                # Evaluator state/truth remain outside the receiver call above.
                trace = None
                prior_label = "NOT_AVAILABLE"
                if trace_paths and key in trace_paths:
                    trace_path = root / trace_paths[key]
                    trace = _optional_npz(trace_path, evidence, blocked)
                    prior_label = str(trace_path)
                elif channel == "Full":
                    trace_path = root / C1A_ROOT / "RESULTS_001/cells" / f"{route}_{bias}_{seed}.npz"
                    trace = _optional_npz(trace_path, evidence, blocked)
                    prior_label = "C1a archived Full premeasurement state, seed " + str(seed)
                if trace is not None:
                    validate_pose_join(packet, trace, expected_count=EXPECTED_POSES[route])
                    if np.asarray(trace["prior"]).shape != (len(ids), 4):
                        raise ValueError("archived prior shape")
                if np.asarray(packet["z"]).shape != (len(ids), 2) or np.asarray(packet["muMB"]).shape != (len(ids), 2):
                    raise ValueError("archived packet z/mu shape")
                values = range_accounting(
                    snapshot["range_m"], b_old=b_old, original_z_r=packet["z"][:, 0],
                    original_mu_r=packet["muMB"][:, 0],
                    r_geo=geometric_range(truth["truth"]) if truth is not None else None,
                    r_state=geometric_range(trace["prior"]) if trace is not None else None,
                    h_r=trace["h"][:, 0] if trace is not None else None,
                )
                rows = []
                for i in range(len(ids)):
                    row = {"route": route, "bias": bias, "channel": channel, "sensor_seed": seed,
                           "current_waveform": "CLEAN", "pose_id": int(ids[i]), "t_s": float(packet["t"][i]),
                           "raw_tap": int(snapshot["index"][i]), "raw_rx": int(snapshot["rx"][i]),
                           "detected": int(snapshot["detected"][i]), "reference_valid": int(snapshot["reference_valid"][i]),
                           "s_clean": finite_scalar(snapshot["s"][i]), "peak": float(snapshot["peak"][i]),
                           "power_plus": float(snapshot["power"][i, 0]), "power_minus": float(snapshot["power"][i, 1]),
                           "s_archived": finite_scalar(packet["z"][i, 1]), "prior_provenance": prior_label}
                    row.update({name: finite_scalar(array[i]) for name, array in values.items()})
                    rows.append(row)
                csv_name = key + "_RECEIVER_AND_RANGES.csv"
                write_rows(out / csv_name, rows)
                errors = {name: signed_error_stats(array, step) for name, array in values.items() if name.startswith("error_")}
                packet_delta = packet["z"][:, 0] - snapshot["range_m"]
                cell = {"cell": key, "status": "RECEIVER_EXTRACTED_WITH_RANGE_ACCOUNTING" if truth is not None else "PARTIAL_NO_TRUTH",
                        "rows": len(ids), "valid_reference": int(snapshot["reference_valid"].sum()),
                        "invalid_reference": int((~snapshot["reference_valid"]).sum()), "table": csv_name,
                        "state_range_available": trace is not None, "truth_available": truth is not None,
                        "errors": errors, "archived_z_minus_clean_range": signed_error_stats(packet_delta, step),
                        "noisy_waveform_parity": "NOT_ESTABLISHED_BY_CLEAN_COMPARISON"}
                # The archived feature producer used a stricter 1e-12 receiver
                # parity threshold. Preserve it, and test BOTH observations.
                raw_parity = {
                    "range": _numeric_checks(snapshot["range_m"], packet["z"][:, 0], tolerance=1e-12),
                    "signed_s": _numeric_checks(snapshot["s"], packet["z"][:, 1], tolerance=1e-12),
                }
                cell["archived_raw_observation_parity"] = raw_parity
                clean_confirmed = all(check["pass"] for check in raw_parity.values())
                cell["baseline_RF_provenance"] = ("CLEAN_H_REPRODUCES_ARCHIVED_R_AND_S" if clean_confirmed
                                                   else "MAPPING_OR_RF_NOISE_UNRESOLVED")
                cell["noisy_waveform_parity"] = ("NOT_APPLICABLE_NO_RF_NOISE_IF_SOURCE_LINEAGE_CONFIRMED"
                                                  if clean_confirmed else "NOT_ESTABLISHED")
                if trace is not None:
                    cell["source_continuous_range_formula"] = _numeric_checks(trace["h"][:, 0], values["r_state_m"] + b_old)
                    if not cell["source_continuous_range_formula"]["pass"]:
                        cell["status"] = "FAIL_RANGE_MODEL_CONVENTION"
                report["cells"].append(cell)
    report["receiver_rows"] = sum(c["rows"] for c in report["cells"])
    report["unique_rf_pose_rows_if_complete"] = sum(EXPECTED_POSES[r] for r in routes) * 2
    report["repetition_note"] = "B0/L2 share clean RF; row duplication is not extra independent RF evidence"
    report["status"] = ("FAIL" if any(c["status"].startswith("FAIL") for c in report["cells"])
                        else "BLOCKED_DATA" if report["receiver_rows"] == 0
                        else "PARTIAL" if blocked or any(not c.get("state_range_available", False) for c in report["cells"])
                        else "E0_RECEIVER_ACCOUNTING_COMPLETE_PENDING_INDEPENDENT_CHECK")
    put_json(out / "SUMMARY.json", report)
    return report


def run_g4(repo_root: Path, output_dir: Path, *, source_model: Any = None,
           denominator_floor: float = 0.0, tolerance: float = 1e-10) -> dict[str, Any]:
    """Reproduce 24 static RF receivers and the stored-GT range oracle.

    Without a supplied SourceFFD instance, only its literal range formula is
    independently evaluated; its FFD polarization/native-tap computation is
    explicitly NOT_RUN.  Stored model scalars never masquerade as a model run.
    """
    root, out = Path(repo_root), Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    condition_path = root / G4_ROOT / "RUN_001/CONDITIONS.json"
    conditions = json.loads(require_payload(condition_path).read_text(encoding="utf8"))
    plan_path = root / G4_ROOT / "PLAN.json"
    plan = json.loads(require_payload(plan_path).read_text(encoding="utf8"))
    if len(conditions) != 24 or len({r["condition_id"] for r in conditions}) != 24:
        raise ValueError("G4 exact 24 unique condition denominator")
    if len({r["coordinate"] for r in conditions}) != 6:
        raise ValueError("G4 six selected static coordinates required")
    b_old, b_evidence = source_range_offset(root)
    freq = np.asarray(6_250_400_000.0 + DF_HZ * np.arange(N_BINS), dtype=np.float64)
    step = source.C0 / (N_TAPS * DF_HZ)
    evidence = [input_record(condition_path), input_record(plan_path), b_evidence]
    missing: list[dict[str, Any]] = []
    rows, receiver_rows, checks = [], [], []
    for row in conditions:
        ident = row["condition_id"]
        physical = row["physical"]["detector"]
        stored_full, stored_los = physical["full"], physical["los"]
        h_stored = float(row["model"]["h_range"])
        h_formula = float(np.linalg.norm(np.asarray(row["xyz"]) - np.asarray(plan["anchor"]))) + b_old
        checks.append({"id": ident, "quantity": "stored_h_r_vs_source_range_formula",
                       **_numeric_checks(np.array([h_stored]), np.array([h_formula]), tolerance=tolerance)})
        taps = [int(np.rint((h_stored + shift) / step)) for shift in (-.04, 0., .04)]
        record = {
            "condition_id": ident, "coordinate": row["coordinate"], "yaw_deg": row["yaw_deg"],
            "baseline_tap_stored": int(stored_full["tap"]), "reference_los_tap_stored": int(stored_los["tap"]),
            "h_r_stored_m": h_stored, "h_r_formula_m": h_formula,
            "oracle_minus4cm_tap": taps[0], "oracle_zero_tap": taps[1], "oracle_plus4cm_tap": taps[2],
            "raw_receiver_status": "BLOCKED_DATA", "source_model_full_evaluation": "NOT_RUN" if source_model is None else "RUN",
        }
        if source_model is not None:
            state = np.array([[row["xyz"][0], row["xyz"][1], np.deg2rad(row["yaw_deg"]), 0.0]])
            model_case = {"anchor": plan["anchor"], "robot_z_m": plan["robot_z_m"], "mount_deg": plan["mount_deg"]}
            h, _, diagnostics = source_model.batch(state, model_case, gradient=True, return_diagnostics=True)
            for name, actual, expected in (("source_model_h_r", h[0, 0], h_stored),
                                            ("source_model_h_s", h[0, 1], row["model"]["h_s"]),
                                            ("source_model_native_range", diagnostics["native_range"][0], row["model"]["model_native_range"])):
                checks.append({"id": ident, "quantity": name, **_numeric_checks(np.array([actual]), np.array([expected]), tolerance=tolerance)})
        fields_path = root / G4_ROOT / "RUN_001" / ident / "FIELDS_AND_WINDOWS.npz"
        fields = _optional_npz(fields_path, evidence, missing)
        if fields is not None:
            for label in ("full", "direct"):
                spectrum = fields[label + "_spectrum"]
                if spectrum.shape != (N_BINS, 2) or spectrum.dtype != np.dtype("complex128"):
                    raise ValueError("G4 spectrum shape/dtype")
                got = receiver_snapshot(spectrum[None, :, :, None], freq, denominator_floor=denominator_floor)
                expected = stored_full if label == "full" else stored_los
                for name, actual, reference, exact in (
                    ("tap", got["index"], np.array([expected["tap"]]), True),
                    ("rx", got["rx"], np.array([expected["rx"]]), True),
                    ("s", got["s"], np.array([expected["s"]]), False),
                    ("range", got["range_m"], np.array([expected["range_m"]]), False),
                    ("power", got["power"], np.asarray([expected["power"]]), False),
                    ("cir", got["cir"][0], fields[label + "_cir"], False),
                ):
                    checks.append({"id": ident, "quantity": label + "_" + name,
                                   **_numeric_checks(actual, reference, tolerance=tolerance, exact=exact)})
                receiver_rows.append({"condition_id": ident, "channel": label, "tap": int(got["index"][0]),
                                      "rx": int(got["rx"][0]), "s": finite_scalar(got["s"][0]),
                                      "range_m": finite_scalar(got["range_m"][0]), "detected": bool(got["detected"][0]),
                                      "reference_valid": bool(got["reference_valid"][0]), "peak": float(got["peak"][0]),
                                      "power_plus": float(got["power"][0, 0]), "power_minus": float(got["power"][0, 1])})
                if label == "full":
                    c = got["cir"][0]
                    for suffix, tap in zip(("minus4cm", "zero", "plus4cm"), taps):
                        if not 0 <= tap < N_TAPS:
                            raise ValueError("oracle tap outside receiver window")
                        power = np.abs(c[tap]) ** 2
                        den = float(power.sum())
                        record["oracle_" + suffix + "_s_from_full_cir"] = float((power[0] - power[1]) / den) if den > denominator_floor else None
            record["raw_receiver_status"] = "REPLAYED"
        rows.append(record)
    original = np.array([r["baseline_tap_stored"] for r in rows])
    reference = np.array([r["reference_los_tap_stored"] for r in rows])
    selected = np.array([r["oracle_zero_tap"] for r in rows])
    matches = {"baseline": int((original == reference).sum()),
               "minus4cm": sum(r["oracle_minus4cm_tap"] == r["reference_los_tap_stored"] for r in rows),
               "zero": int((selected == reference).sum()),
               "plus4cm": sum(r["oracle_plus4cm_tap"] == r["reference_los_tap_stored"] for r in rows)}
    oracle_summary_path = root / ORACLE_ROOT / "SUMMARY.json"
    sensitivity_path = root / ORACLE_ROOT / "SENSITIVITY_4CM.json"
    expected_summary = json.loads(require_payload(oracle_summary_path).read_text(encoding="utf8"))
    expected_sensitivity = json.loads(require_payload(sensitivity_path).read_text(encoding="utf8"))
    evidence.extend([input_record(oracle_summary_path), input_record(sensitivity_path)])
    aggregate = {"cases": len(rows), "locations": 6, "baseline_exact": matches["baseline"], "model_exact": matches["zero"],
                 "rescued": int(((original != reference) & (selected == reference)).sum()),
                 "harmed": int(((original == reference) & (selected != reference)).sum()),
                 "still_bad": int(((original != reference) & (selected != reference)).sum())}
    for name, value in aggregate.items():
        if name in expected_summary["aggregate"]:
            checks.append({"id": "aggregate", "quantity": name, "pass": bool(value == expected_summary["aggregate"][name])})
    checks.append({"id": "aggregate", "quantity": "4cm_matches", "pass": bool(matches == expected_sensitivity["matches"])})
    write_rows(out / "ORACLE_STATIC_ROWS.csv", rows, list(dict.fromkeys(k for row in rows for k in row)))
    write_rows(out / "RAW_RECEIVER_ROWS.csv", receiver_rows)
    put_json(out / "PARITY_CHECKS.json", checks)
    all_pass = all(c["pass"] for c in checks)
    report = {
        "experiment_id": "E0-03", "status": "FAIL" if not all_pass else "PARTIAL_STORED_MODEL_ARITHMETIC" if missing else "RAW_RECEIVER_AND_ORACLE_REPRODUCED",
        "independent_audit": False, "new_rt_calls": 0, "static_conditions": 24, "locations": 6,
        "raw_conditions_replayed": len(receiver_rows) // 2, "raw_receiver_rows": len(receiver_rows),
        "aggregate": aggregate, "matches": matches, "all_parity_checks_pass": all_pass,
        "source_model_full_evaluation": "NOT_RUN" if source_model is None else "RUN",
        "source_range_formula_evaluated": True, "source_model_polarization_claim": "NOT_REPRODUCED" if source_model is None else "COMPARED_TO_ARCHIVE",
        "oracle_basis": "archived SourceFFD h_r at true static pose; separately verified d+B_OLD formula",
        "claim_limit": "24 static conditions from 6 selected coordinates; fixed CIR with perturbed oracle prediction, not motion, online policy, noisy replay or independent environments",
        "missing": missing, "inputs": evidence,
    }
    put_json(out / "SUMMARY.json", report)
    return report


def run_flat_sweep(freqs_hz: np.ndarray, output_dir: Path, *, distances_m: np.ndarray,
                   b_old: float, batch_size: int = 256) -> dict[str, Any]:
    """Evaluate frozen flat-spectrum direct-path distances; no ray tracing.

    The caller MUST freeze the distance vector before invoking this function.
    Resulting support intervals are sampled supports for this ideal spectrum,
    not guarantees for frequency-dependent FFD or multipath channels.
    """
    df = validate_frequencies(freqs_hz)
    d = np.asarray(distances_m, dtype=np.float64)
    if d.ndim != 1 or len(d) < 2 or not np.isfinite(d).all() or np.any(d <= 0) or np.any(np.diff(d) <= 0):
        raise ValueError("finite positive increasing distance grid required")
    if not np.isfinite(b_old) or batch_size < 1:
        raise ValueError("invalid sweep configuration")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    taps, ranges, ports = [], [], []
    for start in range(0, len(d), batch_size):
        distance = d[start:start + batch_size]
        h = np.exp(-2j * np.pi * freqs_hz[None, :] * distance[:, None] / source.C0)[:, :, None]
        h = np.repeat(h, 2, axis=2)
        got = receiver_snapshot(h[:, :, :, None], freqs_hz)
        taps.extend(got["index"].tolist())
        ranges.extend(got["range_m"].tolist())
        ports.extend(got["rx"].tolist())
    taps = np.asarray(taps, dtype=np.int64)
    ranges = np.asarray(ranges, dtype=float)
    step = source.C0 / (N_TAPS * df)
    rows = [{"distance_m": float(x), "detector_tap": int(n), "rx": int(rx), "r_det_m": float(r),
             "r_det_minus_geo_m": float(r - x), "r_det_minus_B_OLD_m": float(r - b_old),
             "corrected_error_m": float(r - b_old - x), "source_continuous_h_r_m": float(x + b_old),
             "h_r_minus_detector_m": float(x + b_old - r)}
            for x, n, r, rx in zip(d, taps, ranges, ports)]
    supports = []
    for tap in np.unique(taps):
        values = d[taps == tap]
        supports.append({"tap": int(tap), "r_det_m": float(tap * step), "samples": len(values),
                         "sampled_geo_min_m": float(values.min()), "sampled_geo_max_m": float(values.max()),
                         "sampled_h_min_m": float(values.min() + b_old), "sampled_h_max_m": float(values.max() + b_old),
                         "sampled_geo_minus_detector_min_m": float(values.min() - tap * step),
                         "sampled_geo_minus_detector_max_m": float(values.max() - tap * step),
                         "truncated_at_sweep_edge": bool(values.min() == d[0] or values.max() == d[-1])})
    write_rows(out / "FLAT_SUBTAP_SWEEP.csv", rows)
    write_rows(out / "SAMPLED_TAP_SUPPORT.csv", supports)
    report = {
        "experiment_id": "E0-02_MAPPING", "status": "IDEAL_DIRECT_SWEEP_COMPLETED",
        "source": "analytic exp(-2j*pi*f*d/c), identical unit-amplitude RX ports; no FFD/no noise/no RT",
        "samples": len(d), "distance_min_m": float(d[0]), "distance_max_m": float(d[-1]),
        "max_grid_spacing_m": float(np.diff(d).max()), "distance_array_sha256": hashlib.sha256(d.tobytes()).hexdigest(),
        "step_m": step, "source_B_OLD_m": b_old, "receiver_offset": signed_error_stats(ranges - d, step),
        "constant_offset_corrected": signed_error_stats(ranges - b_old - d, step),
        "source_h_outside_detector_half_step": int((np.abs(d + b_old - ranges) > step / 2).sum()),
        "geometry_outside_detector_half_step": int((np.abs(d - ranges) > step / 2).sum()),
        "equal_port_tie_preserved": bool(np.array_equal(ports, np.zeros(len(d), dtype=int))),
        "mapping_status": "IDEAL_SPECTRUM_ONLY; FFD/yaw-dependent support requires separate data",
        "independent_audit": False, "new_rt_calls": 0,
    }
    put_json(out / "SUMMARY.json", report)
    return report
