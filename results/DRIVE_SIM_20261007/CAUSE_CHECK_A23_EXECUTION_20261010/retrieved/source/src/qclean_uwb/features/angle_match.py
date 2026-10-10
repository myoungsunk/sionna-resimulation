"""Yaw estimation by matching a measured FP-power ratio to the ideal curve |cos(2 yaw)|.

The ideal curve has period 90 deg, so a ratio ``r`` maps to four yaw candidates in [0, 180):
``a/2, 90 - a/2, 90 + a/2, 180 - a/2`` with ``a = arccos(r)`` in degrees.  The representative
estimate is the candidate closest (circularly, period 180 deg) to the true yaw, i.e. the
ambiguity is assumed resolved by prior knowledge and the remaining error is distortion only.
"""
from __future__ import annotations

import numpy as np


def yaw_candidates(ratio) -> np.ndarray:
    a = np.degrees(np.arccos(np.clip(np.asarray(ratio, dtype=float), 0.0, 1.0)))
    half = a / 2.0
    return np.stack([half, 90.0 - half, 90.0 + half, 180.0 - half], axis=-1)


def wrap180(delta_deg) -> np.ndarray:
    """Signed angular difference on a 180 deg circle, in [-90, 90)."""
    return (np.asarray(delta_deg, dtype=float) + 90.0) % 180.0 - 90.0


def representative_yaw(ratio, true_yaw_deg):
    """Return (estimate, error = estimate - true) using the candidate nearest the true yaw."""
    cand = yaw_candidates(ratio)
    true = np.asarray(true_yaw_deg, dtype=float)
    err = wrap180(cand - true[..., None])
    pick = np.argmin(np.abs(err), axis=-1)
    e = np.take_along_axis(err, pick[..., None], axis=-1)[..., 0]
    return true + e, e
