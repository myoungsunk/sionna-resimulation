"""Outcome-blind first-cluster oracle helpers for Part 4 v3.

This module does not invent path amplitudes from geometry.  Its path-level
functions consume reconstructed complex contributions only, which keeps the
R2/R3 claim boundary literal.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def waveform_overlap(delays_s: np.ndarray, direct_delay_s: np.ndarray | float, bandwidth_hz: float) -> np.ndarray:
    """Rectangular-band pulse autocorrelation magnitude proxy: |sinc(B Δτ)|.

    This is a membership proxy, not a reconstructed path-energy oracle.  The
    exact waveform response is stored by the reconstruction runner separately.
    """
    return np.abs(np.sinc((np.asarray(delays_s, dtype=float) - np.asarray(direct_delay_s, dtype=float)) * float(bandwidth_hz)))


def assign_waveform_cluster(paths: pd.DataFrame, bandwidth_hz: float, threshold: float) -> pd.DataFrame:
    required = {"case_id", "path_idx", "delay_s", "valid", "blocked"}
    missing = required.difference(paths.columns)
    if missing:
        raise ValueError(f"path cluster source missing: {sorted(missing)}")
    work = paths.loc[paths.valid.astype(bool) & ~paths.blocked.astype(bool)].copy()
    direct = work.groupby("case_id")["delay_s"].transform("min")
    work["tau_direct_s"] = direct
    work["overlap_abs"] = waveform_overlap(work.delay_s.to_numpy(float), direct.to_numpy(float), bandwidth_hz)
    work["in_first_cluster"] = (work.delay_s >= direct) & (work.overlap_abs >= float(threshold))
    work["is_direct_delay"] = np.isclose(work.delay_s.to_numpy(float), direct.to_numpy(float), rtol=0.0, atol=1e-15)
    return work


def no_interferer_row(case_id: int) -> dict[str, object]:
    return {"case_id": int(case_id), "oracle_status": "NO_INTERFERER", "total_interferer_energy": 0.0, "dmax": np.nan, "neff": np.nan, "entropy": np.nan}


def energy_concentration(case_id: int, energy: Iterable[float]) -> dict[str, object]:
    values = np.asarray(list(energy), dtype=float)
    values = values[np.isfinite(values) & (values >= 0.0)]
    total = float(values.sum())
    if not len(values) or total <= 0.0:
        return no_interferer_row(case_id)
    share = values / total
    return {
        "case_id": int(case_id), "oracle_status": "RECONSTRUCTED", "total_interferer_energy": total,
        "dmax": float(share.max()), "neff": float(1.0 / np.square(share).sum()),
        "entropy": float(-(share * np.log(np.maximum(share, 1e-300))).sum()),
    }


def path_sum_relative_error(full_h: np.ndarray, per_path_h: Iterable[np.ndarray]) -> float:
    summed = np.sum(np.asarray(list(per_path_h)), axis=0)
    denom = max(float(np.linalg.norm(full_h)), 1e-300)
    return float(np.linalg.norm(np.asarray(full_h) - summed) / denom)


def deletion_without_renormalization(per_path_h: list[np.ndarray], delete_index: int) -> np.ndarray:
    """Return channel after exact path removal; no power rescaling is permitted."""
    if delete_index < 0 or delete_index >= len(per_path_h):
        raise IndexError("path delete index out of range")
    kept = [value for index, value in enumerate(per_path_h) if index != delete_index]
    return np.sum(np.asarray(kept), axis=0) if kept else np.zeros_like(per_path_h[delete_index])


def coherent_summary(z: Iterable[complex]) -> dict[str, float]:
    values = np.asarray(list(z), dtype=np.complex128)
    v = float(np.square(np.abs(values)).sum())
    q = float(np.abs(values.sum()) ** 2)
    return {"V": v, "Q": q, "kappa": float(q / (v + 1e-300))}
