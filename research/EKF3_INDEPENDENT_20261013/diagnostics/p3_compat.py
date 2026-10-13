"""Frozen P3 detector feature contract, NumPy-only, for EKF3 diagnostics.

The formulas are a minimal read-only reproduction of:
 research/LOS_RANGE_RECAL_20261012/p3_common.py
 pinned at GitHub commit 5058368123d40e621405113803816a749c19368f.
Feature/prediction/observer parity must be checked before interpreting E1.
No truth information enters any feature or corrected range prediction.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

C0 = 299792458.0
LEADING_EDGE = 0.3
B_OLD = -0.5315983906250129
FEATURE_SCHEMA = [
    "1", "r_raw", "r_raw^2", "peak_minus_first_tap_m",
    "that*r_raw", "log_peak", "first_over_peak", "mount==45",
]


def tap_metres(freqs: np.ndarray) -> float:
    freq = np.asarray(freqs, dtype=float)
    if freq.ndim != 1 or len(freq) < 2 or not np.all(np.isfinite(freq)):
        raise ValueError("invalid frequency axis")
    step = np.diff(freq)
    if np.any(step <= 0) or not np.allclose(step, step[0], rtol=1e-10, atol=1e-4):
        raise ValueError("frequency axis is not uniformly spaced")
    return float(C0 / (4.0 * len(freq) * step[0]))


def frozen_detector(
    H: np.ndarray,
    freq: np.ndarray,
    mount_deg: float,
    frozen_observer: Any,
    chunk_size: int = 128,
) -> dict[str, np.ndarray]:
    """Extract P3/E1 online features and d1 fractional detector from P0-pinned H.

    Mimics P3 strongest-RX CIR magnitude after frozen observer.cir_batch,
    preserving TX0, Hann, 4N zero pad, 30% threshold and shared tap.
    """
    if getattr(frozen_observer, "LEADING_EDGE", None) != LEADING_EDGE:
        raise RuntimeError("frozen first-path leading edge changed")
    arr = H
    if arr.ndim != 4 or arr.shape[2:] != (2, 2) or len(freq) != arr.shape[1]:
        raise ValueError(f"expected H=(pose,bin,2,2), got {arr.shape}")
    if not math.isfinite(mount_deg) or mount_deg not in (0.0, 45.0):
        raise ValueError("mount must be one of frozen 0/45 degrees")
    if chunk_size <= 0:
        raise ValueError("positive chunk size required")
    tm = tap_metres(freq)
    cols: dict[str, list[np.ndarray]] = {
        k: [] for k in (
            "s", "range_raw_m", "power", "index", "peak", "peak_idx",
            "first_mag", "r_d1_m", "fractional_tap", "features",
        )
    }
    for a in range(0, arr.shape[0], chunk_size):
        block = np.asarray(arr[a : a + chunk_size, ..., 0])
        cir = frozen_observer.cir_batch(block)
        mag = np.abs(cir)
        strongest_port = mag.max(axis=1).argmax(axis=1)
        strongest = np.take_along_axis(mag, strongest_port[:, None, None], axis=2)[:, :, 0]
        peak = strongest.max(axis=1)
        if np.any(peak <= 0) or not np.isfinite(peak).all():
            raise ValueError("unusable zero/invalid first-path peak")
        i1 = (strongest >= LEADING_EDGE * peak[:, None]).argmax(axis=1)
        peak_idx = strongest.argmax(axis=1)
        k = np.arange(len(block))
        power = np.abs(cir[k, i1, :]) ** 2
        p_total = power.sum(axis=1)
        if np.any(p_total <= 0):
            raise ValueError("zero first-path combined power")
        s = (power[:, 0] - power[:, 1]) / p_total

        # Mirrors the P3 fractional 30%-of-peak crossing exactly.
        m1 = strongest[k, i1]
        m0 = np.where(i1 > 0, strongest[k, np.maximum(i1 - 1, 0)], 0.0)
        threshold = LEADING_EDGE * peak
        rel = np.where(m1 > m0, (threshold - m0) / np.maximum(m1 - m0, 1e-300), 1.0)
        frac = np.where(i1 > 0, i1 - 1.0 + np.clip(rel, 0, 1), 0.)
        r_raw = i1 * tm
        dpk = (peak_idx - i1) * tm
        m45 = np.full(len(block), float(mount_deg == 45.))
        features = np.column_stack([
            np.ones(len(block)), r_raw, r_raw**2, dpk, dpk * r_raw,
            np.log(np.maximum(peak, 1e-300)),
            m1 / np.maximum(peak, 1e-300), m45
        ])
        for field, v in (
            ("s", s), ("range_raw_m", r_raw), ("power", power),
            ("index", i1), ("peak", peak), ("peak_idx", peak_idx),
            ("first_mag", m1), ("r_d1_m", frac * tm),
            ("fractional_tap", frac), ("features", features),
        ):
            cols[field].append(np.asarray(v))
    return {key: np.concatenate(chunks, axis=0) for key, chunks in cols.items()}


def predict_e1_bias(features: np.ndarray, fold: dict) -> np.ndarray:
    """E1 predicts B_old residual in metres, not total raw delay or s error."""
    x = np.asarray(features, float)
    params = fold["E1"]
    w = np.asarray(params["w"], float)
    mu = np.asarray(params["mu"], float)
    sd = np.asarray(params["sd"], float)
    if x.ndim != 2 or x.shape[1] != 8 or w.shape != (8,) or mu.shape != (7,) or sd.shape != (7,):
        raise ValueError("frozen E1 dimension mismatch")
    if not (np.isfinite(x).all() and np.isfinite(w).all() and np.all(sd > 0)):
        raise ValueError("invalid E1 features or frozen parameters")
    return w[0] + ((x[:, 1:] - mu) / sd) @ w[1:]


def corrected_ranges(
    det: dict[str, np.ndarray],
    fold: dict,
    *,
    allow_e1_on_los: bool,
    channel: str,
) -> dict[str, np.ndarray]:
    """Return physical-range predictions (r ≈ true slant distance) for each control.

    E1 applied to LoS is an explicit NEGATIVE CONTROL because E1 was trained
    for Full RF; this function rejects it unless user requests that test.
    """
    r = np.asarray(det["range_raw_m"], float)
    c_const = float(fold["C_const"])
    d1_const = float(fold["D1_offset"])
    result = {
        "B_OLD": r - B_OLD,
        "C_CONST_LOS": r - c_const,
        "D1_FRACTIONAL": np.asarray(det["r_d1_m"], float) - d1_const,
    }
    if channel == "full" or allow_e1_on_los:
        result["E1_FULL_LORO" if channel == "full" else "E1_ON_LOS_NEGCTRL"] = (
            r - B_OLD - predict_e1_bias(det["features"], fold)
        )
    return result


def assert_observation_parity(
    det: dict[str, np.ndarray], p2: dict[str, np.ndarray],
    rows: np.ndarray, *, tol: float = 1e-9,
) -> dict[str, float]:
    """Compare detector outputs against original P2 one-step RF observations.

    Explicit fail-closed parity, never silently repair observational inputs.
    """
    i = np.asarray(rows, int)
    n = len(i)
    checks = {}
    for our, archived in (("s", "z_s"), ("range_raw_m", "z_r_m")):
        left = np.asarray(det[our][i], float)
        right = np.asarray(p2[archived], float)
        if right.shape != (n,) or not np.all(np.isfinite(left) == np.isfinite(right)):
            raise RuntimeError(f"{archived} finite mask/shape changed")
        finite = np.isfinite(left)
        error = float(np.max(np.abs(left[finite] - right[finite]))) if finite.any() else 0.
        checks[archived] = error
        if error > tol:
            raise RuntimeError(f"{archived} differs from frozen observer by {error}")
    indices = np.asarray(det["index"][i])
    old_index = np.asarray(p2["first_arrival_tap"])
    if not np.array_equal(indices, old_index):
        raise RuntimeError("frozen first-arrival tap parity failed")
    p = np.asarray(det["power"][i])
    q = np.asarray(p2["power"])
    if p.shape != q.shape or not np.allclose(p, q, rtol=1e-10, atol=1e-20):
        raise RuntimeError("frozen first-path port power parity failed")
    checks["tap_identical"] = True
    checks["powers_identical_with_tol"] = True
    return checks
