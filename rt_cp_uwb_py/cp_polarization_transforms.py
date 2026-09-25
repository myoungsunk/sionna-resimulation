"""Explicit, testable linear/circular polarization transform contracts.

The functions in this module operate on a Jones tensor whose first two axes
are receiver and transmitter.  They deliberately expose no antenna or
calibration claim: they only prove the mathematical DLP-to-CP basis change.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .channel import circular_basis_matrix


class PolarizationTransformError(ValueError):
    """Raised when a Jones tensor cannot satisfy the transform contract."""


def _as_jones_tensor(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.complex128)
    if array.ndim < 2 or array.shape[0:2] != (2, 2):
        raise PolarizationTransformError(f"expected Jones tensor [2,2,...], got shape={array.shape}")
    if not np.all(np.isfinite(array)):
        raise PolarizationTransformError("Jones tensor contains non-finite values")
    return array


def circular_transform(*, convention: str = "IEEE-RHCP", circular_order: str = "RL") -> np.ndarray:
    """Return the unitary linear-to-circular basis matrix used by the package."""

    matrix = np.asarray(circular_basis_matrix(convention, circular_order), dtype=np.complex128)
    if matrix.shape != (2, 2):
        raise PolarizationTransformError(f"expected 2x2 basis matrix, got {matrix.shape}")
    return matrix


def linear_to_circular(jones_linear: Any, *, convention: str = "IEEE-RHCP", circular_order: str = "RL") -> np.ndarray:
    """Transform a [rx, tx, ...] linear Jones tensor to circular basis."""

    array = _as_jones_tensor(jones_linear)
    transform = circular_transform(convention=convention, circular_order=circular_order)
    return np.einsum("ab,bc...,cd->ad...", transform.conj().T, array, transform, optimize=True)


def circular_to_linear(jones_circular: Any, *, convention: str = "IEEE-RHCP", circular_order: str = "RL") -> np.ndarray:
    """Transform a [rx, tx, ...] circular Jones tensor back to linear basis."""

    array = _as_jones_tensor(jones_circular)
    transform = circular_transform(convention=convention, circular_order=circular_order)
    return np.einsum("ab,bc...,cd->ad...", transform, array, transform.conj().T, optimize=True)


def transform_contract_metrics(
    jones_linear: Any,
    *,
    convention: str = "IEEE-RHCP",
    circular_order: str = "RL",
) -> dict[str, float]:
    """Return unitarity and inverse-round-trip errors for a Jones tensor."""

    original = _as_jones_tensor(jones_linear)
    transform = circular_transform(convention=convention, circular_order=circular_order)
    circular = linear_to_circular(original, convention=convention, circular_order=circular_order)
    restored = circular_to_linear(circular, convention=convention, circular_order=circular_order)
    denom = max(float(np.linalg.norm(original)), np.finfo(float).tiny)
    return {
        "unitarity_max_abs_error": float(np.max(np.abs(transform.conj().T @ transform - np.eye(2)))),
        "round_trip_relative_error": float(np.linalg.norm(restored - original) / denom),
    }
