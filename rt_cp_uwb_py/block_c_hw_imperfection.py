"""Block C CP-basis hardware-imperfection helpers.

These helpers implement the locked CP-basis receive Jones injection only.
They do not make any grounded hardware-range or failure-threshold claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any

import numpy as np


MISSING_GROUNDED_HW_RANGE = "MISSING_GROUNDED_HW_RANGE"


@dataclass(frozen=True)
class CpJonesProfile:
    """CP-basis receive antenna imperfection profile."""

    gain_mismatch_db: float = 0.0
    axial_ratio_db: float = 0.0
    xpi_db: float = float("inf")
    switch_iso_db: float = float("inf")
    phase_rl_rad: float = 0.0
    phase_lr_rad: float = 0.0

    def matrix(self) -> np.ndarray:
        """Return the 2 x 2 CP-basis Jones matrix in [R, L] order."""

        gain_r, gain_l = gain_mismatch_amplitudes(self.gain_mismatch_db)
        leakage_ar = axial_ratio_leakage(self.axial_ratio_db)
        leakage_xpi = db_isolation_to_amplitude(self.xpi_db)
        leakage_switch = db_isolation_to_amplitude(self.switch_iso_db)
        leakage = rss_leakage(leakage_ar, leakage_xpi, leakage_switch)
        return np.array(
            [
                [gain_r, leakage * np.exp(1j * float(self.phase_rl_rad))],
                [leakage * np.exp(1j * float(self.phase_lr_rad)), gain_l],
            ],
            dtype=np.complex128,
        )

    def provenance(self) -> dict[str, Any]:
        """Return explicit, non-claiming provenance for manifests."""

        leakage_ar = axial_ratio_leakage(self.axial_ratio_db)
        leakage_xpi = db_isolation_to_amplitude(self.xpi_db)
        leakage_switch = db_isolation_to_amplitude(self.switch_iso_db)
        return {
            "gain_mismatch_db": float(self.gain_mismatch_db),
            "axial_ratio_db": float(self.axial_ratio_db),
            "xpi_db": finite_or_inf(self.xpi_db),
            "switch_iso_db": finite_or_inf(self.switch_iso_db),
            "phase_rl_rad": float(self.phase_rl_rad),
            "phase_lr_rad": float(self.phase_lr_rad),
            "leakage_axial_ratio_amplitude": float(leakage_ar),
            "leakage_xpi_amplitude": float(leakage_xpi),
            "leakage_switch_amplitude": float(leakage_switch),
            "leakage_rss_effective_amplitude": float(rss_leakage(leakage_ar, leakage_xpi, leakage_switch)),
            "grounded_hw_range_status": MISSING_GROUNDED_HW_RANGE,
            "failure_threshold_interpretation": "FORBIDDEN_WITHOUT_GROUNDED_HW_RANGE",
        }


def gain_mismatch_amplitudes(gain_mismatch_db: float) -> tuple[float, float]:
    """Map symmetric R/L gain mismatch in dB to diagonal amplitudes."""

    delta = float(gain_mismatch_db)
    return 10.0 ** (delta / 40.0), 10.0 ** (-delta / 40.0)


def axial_ratio_leakage(axial_ratio_db: float) -> float:
    """Map axial ratio in dB to ellipticity leakage rho=(r-1)/(r+1)."""

    ar_db = float(axial_ratio_db)
    if not isfinite(ar_db):
        raise ValueError("axial_ratio_db must be finite")
    if ar_db < 0.0:
        raise ValueError("axial_ratio_db must be non-negative")
    ratio = 10.0 ** (ar_db / 20.0)
    return abs((ratio - 1.0) / (ratio + 1.0))


def db_isolation_to_amplitude(db_value: float) -> float:
    """Map isolation/cross-pol discrimination in dB to amplitude leakage."""

    db = float(db_value)
    if db == float("inf"):
        return 0.0
    if not isfinite(db):
        raise ValueError("isolation/XPI dB must be finite or +inf")
    return 10.0 ** (-db / 20.0)


def rss_leakage(*components: float) -> float:
    """Root-sum-square leakage magnitude from independent components."""

    return sqrt(sum(float(item) ** 2 for item in components))


def apply_cp_jones(samples: np.ndarray, jones_matrix: np.ndarray) -> np.ndarray:
    """Apply a CP-basis Jones matrix to samples with final dimension [R, L]."""

    x = np.asarray(samples, dtype=np.complex128)
    j = np.asarray(jones_matrix, dtype=np.complex128)
    if j.shape != (2, 2):
        raise ValueError(f"jones_matrix must have shape (2, 2), got {j.shape}")
    if x.shape[-1] != 2:
        raise ValueError(f"samples must have final dimension 2 for [R, L], got {x.shape}")
    return np.einsum("ab,...b->...a", j, x)


def finite_or_inf(value: float) -> float | str:
    raw = float(value)
    if raw == float("inf"):
        return "inf"
    return raw
