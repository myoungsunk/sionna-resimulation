"""Streaming runtime helpers for Part 4 v3 reconstructed-path analyses.

The helpers deliberately keep the expensive complex R2 shards on the remote
worker.  They stream one shard at a time, reconstruct deterministic channel
counterfactuals, and never use residuals or learned scores when building an
oracle quantity.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd


def require_full_reconstruction(oracle_root: Path) -> None:
    """Refuse R3 unless the outcome-blind R2 full gate is present and passes."""
    import json

    gate_path = Path(oracle_root) / "manifests" / "reconstruction_gates.json"
    manifest_path = Path(oracle_root) / "manifests" / "path_reconstruction_manifest.json"
    if not gate_path.is_file() or not manifest_path.is_file():
        raise ValueError("R3_BLOCKED_R2_MANIFEST_MISSING")
    gates = json.loads(gate_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not bool(gates.get("all_pass")) or manifest.get("mode") != "full" or manifest.get("execution_status") != "COMPLETED":
        raise ValueError("R3_BLOCKED_R2_FULL_GATE_FAILED")


def oracle_index(oracle_root: Path) -> pd.DataFrame:
    path = Path(oracle_root) / "tables" / "path_oracle_index.csv"
    if not path.is_file():
        raise ValueError("R3_BLOCKED_PATH_ORACLE_INDEX_MISSING")
    frame = pd.read_csv(path)
    required = {"case_id", "path_idx", "shard_file", "row_in_shard", "in_first_cluster", "is_direct_delay"}
    missing = required.difference(frame.columns)
    if missing or frame.duplicated(["case_id", "path_idx"]).any():
        raise ValueError(f"R3_BLOCKED_PATH_ORACLE_INVALID:{sorted(missing)}")
    return frame


def iter_oracle_cases(oracle_root: Path) -> Iterator[tuple[int, pd.DataFrame, np.ndarray, np.ndarray]]:
    """Yield a complete case at a time without materialising all NPZ shards.

    The R2 writer stores paths in contiguous shards.  The tiny pending cache
    only holds a case that straddles the current shard boundary.
    """
    root = Path(oracle_root)
    index = oracle_index(root)
    order = sorted(index.shard_file.astype(str).unique())
    last_shard = index.groupby("case_id").shard_file.max().to_dict()
    pending_meta: dict[int, list[pd.DataFrame]] = defaultdict(list)
    pending_co: dict[int, list[np.ndarray]] = defaultdict(list)
    pending_cross: dict[int, list[np.ndarray]] = defaultdict(list)
    for shard_name in order:
        shard_path = root / "shards" / shard_name
        if not shard_path.is_file():
            raise ValueError(f"R3_BLOCKED_COMPLEX_SHARD_MISSING:{shard_name}")
        rows = index.loc[index.shard_file.astype(str) == shard_name].copy()
        with np.load(shard_path, allow_pickle=False) as archive:
            stored_case = archive["case_id"].astype(int)
            stored_path = archive["path_idx"].astype(int)
            co_all, cross_all = archive["H_path_co"], archive["H_path_cross"]
            for case_id, group in rows.groupby("case_id", sort=True):
                group = group.sort_values("row_in_shard")
                positions = group.row_in_shard.to_numpy(int)
                if not np.array_equal(stored_case[positions], np.full(len(positions), int(case_id))) or not np.array_equal(stored_path[positions], group.path_idx.to_numpy(int)):
                    raise ValueError(f"R3_BLOCKED_SHARD_INDEX_MISMATCH:{shard_name}:{case_id}")
                key = int(case_id)
                pending_meta[key].append(group)
                pending_co[key].append(np.asarray(co_all[positions], dtype=np.complex128))
                pending_cross[key].append(np.asarray(cross_all[positions], dtype=np.complex128))
        finished = [case for case in pending_meta if str(last_shard.get(case)) == shard_name]
        for case_id in sorted(finished):
            meta = pd.concat(pending_meta.pop(case_id), ignore_index=True).sort_values("path_idx").reset_index(drop=True)
            co = np.concatenate(pending_co.pop(case_id), axis=0)
            cross = np.concatenate(pending_cross.pop(case_id), axis=0)
            if len(meta) != len(co) or len(co) != len(cross):
                raise ValueError(f"R3_BLOCKED_CASE_ASSEMBLY_MISMATCH:{case_id}")
            yield case_id, meta, co, cross
    if pending_meta:
        raise ValueError("R3_BLOCKED_INCOMPLETE_SHARD_STREAM")


def assemble_cp_tensor(co: np.ndarray, cross: np.ndarray) -> np.ndarray:
    """Build the canonical 2x2 circular tensor consumed by ``features``."""
    co_a, cross_a = np.asarray(co, dtype=np.complex128).reshape(-1), np.asarray(cross, dtype=np.complex128).reshape(-1)
    if co_a.shape != cross_a.shape:
        raise ValueError("co/cross frequency shape mismatch")
    tensor = np.zeros((2, 2, len(co_a)), dtype=np.complex128)
    # For the repository's R,T port convention select_circular_channels uses
    # H[L,R] as direct-compatible co and H[R,R] as cross.
    tensor[1, 0, :] = co_a
    tensor[0, 0, :] = cross_a
    return tensor


def deterministic_noise(co: np.ndarray, cross: np.ndarray, snr_db: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Add one fixed spectral noise draw reused by every paired intervention."""
    co_a, cross_a = np.asarray(co, dtype=np.complex128), np.asarray(cross, dtype=np.complex128)
    signal = float(np.mean(np.abs(co_a) ** 2 + np.abs(cross_a) ** 2))
    if not np.isfinite(signal) or signal <= 0:
        return co_a.copy(), cross_a.copy()
    variance = signal / max(10.0 ** (float(snr_db) / 10.0), 1e-12)
    rng = np.random.default_rng(int(seed))
    noise = np.sqrt(variance / 2.0) * (rng.standard_normal(co_a.shape) + 1j * rng.standard_normal(co_a.shape))
    # The same noise vector is shared by both branches and all counterfactuals.
    return co_a + noise, cross_a + noise


def leading_edge_detector(h: np.ndarray, time_axis: np.ndarray, direct_time_s: float, *, mode: str = "adaptive", threshold: float = 0.3, reference: float | None = None) -> dict[str, object]:
    """Small deterministic detector family used only for same-channel R3 tests."""
    values, time = np.asarray(h, dtype=np.complex128).reshape(-1), np.asarray(time_axis, dtype=float).reshape(-1)
    magnitude = np.abs(values)
    if not len(magnitude) or not np.isfinite(magnitude).any() or float(np.nanmax(magnitude)) <= 0:
        return {"selected_peak_index": -1, "first_crossing_index": -1, "estimate_s": np.nan, "residual_s": np.nan, "threshold_branch_id": str(mode), "basin_label": "B3", "ambiguity_margin": np.nan, "early_lobe_curvature": np.nan, "direct_lobe_selected": False}
    peak = int(np.nanargmax(magnitude))
    if mode == "global_peak":
        index = peak
    elif mode == "early_centroid":
        hits = np.flatnonzero(magnitude >= float(threshold) * float(np.nanmax(magnitude)))
        weights = np.square(magnitude[hits]) if hits.size else np.array([1.0])
        index = int(round(np.average(hits, weights=weights))) if hits.size else peak
    elif mode == "whitened":
        derivative = np.r_[0.0, np.abs(np.diff(magnitude))]
        index = int(np.nanargmax(derivative))
    else:
        base = float(np.nanmax(magnitude)) if mode != "fixed" or reference is None else float(reference)
        hits = np.flatnonzero(magnitude >= float(threshold) * max(base, 1e-300))
        index = int(hits[0]) if hits.size else -1
    direct_index = int(np.argmin(np.abs(time - float(direct_time_s))))
    shift = index - direct_index if index >= 0 else 10**9
    if index < 0:
        basin = "B3"
    elif abs(shift) <= 1:
        basin = "B0"
    elif abs(shift) <= 3:
        basin = "B1"
    else:
        basin = "B2"
    left = magnitude[max(0, index - 1)] if index >= 0 else np.nan
    right = magnitude[min(len(magnitude) - 1, index + 1)] if index >= 0 else np.nan
    return {
        "selected_peak_index": int(index), "first_crossing_index": int(index),
        "estimate_s": float(time[index]) if index >= 0 else np.nan,
        "residual_s": float(time[index] - direct_time_s) if index >= 0 else np.nan,
        "threshold_branch_id": str(mode), "basin_label": basin,
        "ambiguity_margin": float(magnitude[peak] - np.partition(magnitude, -2)[-2]) if len(magnitude) >= 2 else float(magnitude[peak]),
        "early_lobe_curvature": float(left - 2 * magnitude[index] + right) if index >= 0 else np.nan,
        "direct_lobe_selected": bool(basin == "B0"),
    }


def _quadratic_vertex_offset(left: float, center: float, right: float) -> float:
    """Return a bounded three-point quadratic vertex offset in sample units."""
    denominator = float(left) - 2.0 * float(center) + float(right)
    if not np.isfinite(denominator) or abs(denominator) <= np.finfo(float).eps:
        return 0.0
    return float(np.clip(0.5 * (float(left) - float(right)) / denominator, -1.0, 1.0))


def _continuous_time(time: np.ndarray, index: int, offset: float) -> float:
    """Interpolate a possibly nonuniform time axis without extrapolating."""
    if index < 0 or index >= len(time):
        return np.nan
    if offset >= 0.0 and index + 1 < len(time):
        return float(time[index] + offset * (time[index + 1] - time[index]))
    if offset < 0.0 and index - 1 >= 0:
        return float(time[index] + offset * (time[index] - time[index - 1]))
    return float(time[index])


def continuous_leading_edge_detector(
    h: np.ndarray,
    time_axis: np.ndarray,
    direct_time_s: float,
    *,
    mode: str = "adaptive",
    threshold: float = 0.3,
    reference: float | None = None,
) -> dict[str, object]:
    """Continuous v4 leading-edge estimator with retained coarse diagnostics.

    The coarse index is used only for basin/branch diagnostics.  Every
    residual and finite-difference quantity must consume
    ``estimate_s_continuous`` so sub-grid amplitude and phase perturbations do
    not collapse to exact zero merely because a discrete IFFT index is stable.
    """
    values = np.asarray(h, dtype=np.complex128).reshape(-1)
    time = np.asarray(time_axis, dtype=float).reshape(-1)
    magnitude = np.abs(values)
    base = {
        "selected_peak_index": -1,
        "first_crossing_index": -1,
        "coarse_index": -1,
        "estimate_s": np.nan,
        "estimate_s_continuous": np.nan,
        "residual_s": np.nan,
        "threshold_branch_id": str(mode),
        "basin_label": "B3",
        "ambiguity_margin": np.nan,
        "early_lobe_curvature": np.nan,
        "direct_lobe_selected": False,
        "reason_code": "INVALID_INPUT",
    }
    if len(magnitude) != len(time) or len(magnitude) == 0:
        return base
    if not np.isfinite(time).all() or np.any(np.diff(time) <= 0.0):
        base["reason_code"] = "INVALID_TIME_AXIS"
        return base
    if not np.isfinite(magnitude).any() or float(np.nanmax(magnitude)) <= 0.0:
        base["reason_code"] = "NO_SIGNAL"
        return base
    peak = int(np.nanargmax(magnitude))
    reason = "OK"
    index = -1
    continuous = np.nan
    if mode == "global_peak":
        index = peak
        if 0 < index < len(magnitude) - 1:
            offset = _quadratic_vertex_offset(magnitude[index - 1], magnitude[index], magnitude[index + 1])
            continuous = _continuous_time(time, index, offset)
        else:
            continuous = float(time[index])
            reason = "EDGE_FALLBACK"
    elif mode == "early_centroid":
        cutoff = float(threshold) * float(np.nanmax(magnitude))
        hits = np.flatnonzero(magnitude >= cutoff)
        if hits.size:
            index = int(hits[0])
            weights = np.square(magnitude[hits])
            continuous = float(np.average(time[hits], weights=weights))
        else:
            reason = "THRESHOLD_NOT_CROSSED"
    elif mode == "whitened":
        derivative = np.r_[0.0, np.abs(np.diff(magnitude))]
        index = int(np.nanargmax(derivative))
        if 0 < index < len(derivative) - 1:
            offset = _quadratic_vertex_offset(derivative[index - 1], derivative[index], derivative[index + 1])
            continuous = _continuous_time(time, index, offset)
        else:
            continuous = float(time[index])
            reason = "EDGE_FALLBACK"
    else:
        scale = float(np.nanmax(magnitude)) if mode != "fixed" or reference is None else float(reference)
        cutoff = float(threshold) * max(scale, 1e-300)
        hits = np.flatnonzero(magnitude >= cutoff)
        if hits.size:
            index = int(hits[0])
            if index == 0:
                continuous = float(time[0])
                reason = "THRESHOLD_AT_LEFT_EDGE"
            else:
                left, right = float(magnitude[index - 1]), float(magnitude[index])
                if np.isfinite(left) and np.isfinite(right) and right > left:
                    fraction = float(np.clip((cutoff - left) / (right - left), 0.0, 1.0))
                    continuous = float(time[index - 1] + fraction * (time[index] - time[index - 1]))
                else:
                    continuous = float(time[index])
                    reason = "THRESHOLD_INTERPOLATION_FALLBACK"
        else:
            reason = "THRESHOLD_NOT_CROSSED"
    direct_index = int(np.argmin(np.abs(time - float(direct_time_s))))
    shift = index - direct_index if index >= 0 else 10**9
    if index < 0:
        basin = "B3"
    elif abs(shift) <= 1:
        basin = "B0"
    elif abs(shift) <= 3:
        basin = "B1"
    else:
        basin = "B2"
    left = magnitude[max(0, index - 1)] if index >= 0 else np.nan
    right = magnitude[min(len(magnitude) - 1, index + 1)] if index >= 0 else np.nan
    ambiguity = float(magnitude[peak] - np.partition(magnitude, -2)[-2]) if len(magnitude) >= 2 else float(magnitude[peak])
    return {
        "selected_peak_index": int(index),
        "first_crossing_index": int(index),
        "coarse_index": int(index),
        "estimate_s": float(time[index]) if index >= 0 else np.nan,
        "estimate_s_continuous": float(continuous),
        "residual_s": float(continuous - float(direct_time_s)) if np.isfinite(continuous) else np.nan,
        "threshold_branch_id": str(mode),
        "basin_label": basin,
        "ambiguity_margin": ambiguity,
        "early_lobe_curvature": float(left - 2 * magnitude[index] + right) if index >= 0 else np.nan,
        "direct_lobe_selected": bool(basin == "B0"),
        "reason_code": reason,
    }


def mixture_variance(weight: np.ndarray, sigma_c: np.ndarray, sigma_x: np.ndarray, mu_c: np.ndarray, mu_x: np.ndarray) -> np.ndarray:
    weight = np.asarray(weight, dtype=float)
    mean = weight * np.asarray(mu_c, dtype=float) + (1.0 - weight) * np.asarray(mu_x, dtype=float)
    return weight * (np.square(sigma_c) + np.square(np.asarray(mu_c) - mean)) + (1.0 - weight) * (np.square(sigma_x) + np.square(np.asarray(mu_x) - mean))
