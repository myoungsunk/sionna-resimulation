"""Condition-aware two-ended complex Jones recovery utilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class JonesRecovery:
    jones: np.ndarray
    tx_condition: float
    rx_condition: float
    relative_residual: float
    stable: bool
    reason: str


def recover_path_jones(
    observed_port_matrix: np.ndarray,
    tx_port_to_wave: np.ndarray,
    rx_wave_to_port: np.ndarray,
    scalar: complex,
    *,
    max_condition: float = 1.0e6,
    rcond: float = 1.0e-12,
) -> JonesRecovery:
    """Recover a 2x2 propagation Jones matrix from a separated path response.

    The forward model is ``H = G_rx @ R @ (scalar * G_tx)``.  Both antenna
    responses must already be evaluated in their production local frames.
    Near-null/ill-conditioned antenna maps fail closed.
    """
    observed = np.asarray(observed_port_matrix, dtype=np.complex128).reshape(2, 2)
    tx_map = np.asarray(tx_port_to_wave, dtype=np.complex128).reshape(2, 2)
    rx_map = np.asarray(rx_wave_to_port, dtype=np.complex128).reshape(2, 2)
    scalar = complex(scalar)
    if not np.isfinite(scalar.real) or not np.isfinite(scalar.imag) or abs(scalar) <= rcond:
        return JonesRecovery(np.full((2, 2), np.nan + 1j * np.nan), np.inf, np.inf, np.inf, False, "zero_or_nonfinite_scalar")

    tx_condition = float(np.linalg.cond(tx_map))
    rx_condition = float(np.linalg.cond(rx_map))
    if not np.isfinite(tx_condition) or not np.isfinite(rx_condition):
        return JonesRecovery(np.full((2, 2), np.nan + 1j * np.nan), tx_condition, rx_condition, np.inf, False, "nonfinite_condition")
    if tx_condition > max_condition or rx_condition > max_condition:
        return JonesRecovery(np.full((2, 2), np.nan + 1j * np.nan), tx_condition, rx_condition, np.inf, False, "antenna_near_null")

    recovered = np.linalg.pinv(rx_map, rcond=rcond) @ (observed / scalar) @ np.linalg.pinv(tx_map, rcond=rcond)
    reconstructed = rx_map @ recovered @ (scalar * tx_map)
    denominator = max(float(np.linalg.norm(observed)), rcond)
    residual = float(np.linalg.norm(reconstructed - observed) / denominator)
    stable = bool(np.isfinite(residual) and residual <= 1.0e-8)
    return JonesRecovery(
        recovered,
        tx_condition,
        rx_condition,
        residual,
        stable,
        "ok" if stable else "reconstruction_residual",
    )
