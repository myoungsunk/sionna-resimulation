from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from rt_cp_uwb_py.h10b_channels import (
    SCHEMA_VERSION,
    compute_h10b_contrast_features,
    h10b_column_name,
    h10b_contrast_column_names,
    h10b_vector_column_names,
    normalize_h10b_observation_payload,
)


@dataclass(frozen=True)
class H10BObservationVectors:
    channel_order_id: str
    contrast_order: tuple[str, ...]
    range_vec: np.ndarray
    amplitude_vec: np.ndarray
    contrast_vec: np.ndarray
    range_valid_mask: np.ndarray
    amplitude_valid_mask: np.ndarray
    contrast_valid_mask: np.ndarray


@dataclass(frozen=True)
class H10BVectorScore:
    valid_count: int
    mahalanobis: float | None
    log_score: float | None
    residual: np.ndarray
    valid_mask: np.ndarray


@dataclass(frozen=True)
class H10BVectorRSSDScore:
    control: str
    prediction_source: str
    contrast_order: tuple[str, ...]
    observed: np.ndarray
    predicted: np.ndarray
    residual: np.ndarray
    valid_mask: np.ndarray
    valid_count: int
    mahalanobis: float | None
    log_score: float | None


def _float_or_nan(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _vector_from_columns(payload: dict[str, Any], columns: list[str]) -> tuple[np.ndarray, np.ndarray]:
    values = np.array([_float_or_nan(payload.get(column)) for column in columns], dtype=float)
    return values, np.isfinite(values)


def extract_h10b_observation_vectors(
    payload: dict[str, Any],
    *,
    include_auxiliary_contrasts: bool = False,
    saturation_low_db: float | None = None,
    saturation_high_db: float | None = None,
) -> H10BObservationVectors:
    """Extract range, amplitude, and contrast vectors from solver-facing H10B columns.

    Missing legacy columns are normalized into canonical names before extraction.
    Contrast vectors are derived from amplitude columns and remain truth-free.
    """
    normalized = normalize_h10b_observation_payload(payload, fields=("range_m", "amplitude_db"))
    contrast_payload = compute_h10b_contrast_features(
        normalized,
        include_auxiliary=include_auxiliary_contrasts,
        saturation_low_db=saturation_low_db,
        saturation_high_db=saturation_high_db,
    )
    range_vec, range_mask = _vector_from_columns(normalized, h10b_vector_column_names("range_m", canonical=True))
    amp_vec, amp_mask = _vector_from_columns(normalized, h10b_vector_column_names("amplitude_db", canonical=True))
    contrast_columns = h10b_contrast_column_names(include_auxiliary=include_auxiliary_contrasts)
    contrast_vec, contrast_mask = _vector_from_columns(contrast_payload, contrast_columns)
    return H10BObservationVectors(
        channel_order_id=SCHEMA_VERSION,
        contrast_order=tuple(contrast_columns),
        range_vec=range_vec,
        amplitude_vec=amp_vec,
        contrast_vec=contrast_vec,
        range_valid_mask=range_mask,
        amplitude_valid_mask=amp_mask,
        contrast_valid_mask=contrast_mask,
    )


def build_diagonal_covariance(size: int, sigma: float, *, jitter: float = 1e-9) -> np.ndarray:
    if size <= 0:
        raise ValueError("size must be positive")
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    if jitter < 0:
        raise ValueError("jitter must be non-negative")
    return np.eye(size, dtype=float) * (float(sigma) ** 2 + float(jitter))


def build_common_mode_covariance(
    size: int,
    sigma_ind: float,
    sigma_common: float,
    *,
    jitter: float = 1e-9,
) -> np.ndarray:
    if size <= 0:
        raise ValueError("size must be positive")
    if sigma_ind <= 0:
        raise ValueError("sigma_ind must be positive")
    if sigma_common < 0:
        raise ValueError("sigma_common must be non-negative")
    if jitter < 0:
        raise ValueError("jitter must be non-negative")
    eye = np.eye(size, dtype=float)
    ones = np.ones((size, size), dtype=float)
    return (float(sigma_ind) ** 2) * eye + (float(sigma_common) ** 2) * ones + float(jitter) * eye


def h10b_mahalanobis_log_score(
    observed: np.ndarray,
    predicted: np.ndarray,
    covariance: np.ndarray,
    *,
    valid_mask: np.ndarray | None = None,
) -> H10BVectorScore:
    observed_arr = np.asarray(observed, dtype=float)
    predicted_arr = np.asarray(predicted, dtype=float)
    covariance_arr = np.asarray(covariance, dtype=float)
    if observed_arr.shape != predicted_arr.shape:
        raise ValueError("observed and predicted must have the same shape")
    if covariance_arr.shape != (observed_arr.size, observed_arr.size):
        raise ValueError("covariance shape must match vector length")
    finite_mask = np.isfinite(observed_arr) & np.isfinite(predicted_arr)
    if valid_mask is not None:
        finite_mask &= np.asarray(valid_mask, dtype=bool)
    residual = observed_arr - predicted_arr
    if not finite_mask.any():
        return H10BVectorScore(0, None, None, residual, finite_mask)

    residual_valid = residual[finite_mask]
    covariance_valid = covariance_arr[np.ix_(finite_mask, finite_mask)]
    try:
        solved = np.linalg.solve(covariance_valid, residual_valid)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(covariance_valid) @ residual_valid
    mahalanobis = float(residual_valid.T @ solved)
    return H10BVectorScore(
        valid_count=int(finite_mask.sum()),
        mahalanobis=mahalanobis,
        log_score=-0.5 * mahalanobis,
        residual=residual,
        valid_mask=finite_mask,
    )


def predict_h10b_amplitude_vector_db(amp_pred_db: float, bearing_deg: float, yaw_deg: float) -> np.ndarray:
    """Proxy 4-channel H10B amplitude prediction.

    This is a deployable fallback until measured-pattern interpolation is wired.
    It preserves the canonical order: tiltA_lhcp, tiltA_rhcp, tiltB_lhcp,
    tiltB_rhcp.
    """
    rel = np.deg2rad(((float(bearing_deg) - float(yaw_deg) + 180.0) % 360.0) - 180.0)
    pol_offset = 0.8 * np.sin(rel)
    tilt_offset = 0.6 * np.cos(rel)
    return np.asarray(
        [
            float(amp_pred_db) - pol_offset - tilt_offset,
            float(amp_pred_db) + pol_offset - tilt_offset,
            float(amp_pred_db) - pol_offset + tilt_offset,
            float(amp_pred_db) + pol_offset + tilt_offset,
        ],
        dtype=float,
    )


def h10b_contrast_vector_from_amplitude_vector(
    amplitude_vec: np.ndarray,
    *,
    include_auxiliary_contrasts: bool = False,
) -> tuple[tuple[str, ...], np.ndarray]:
    amp = np.asarray(amplitude_vec, dtype=float)
    if amp.shape != (4,):
        raise ValueError("amplitude_vec must have four H10B channels")
    payload = {
        h10b_column_name("tiltA_lhcp", "amplitude_db"): float(amp[0]),
        h10b_column_name("tiltA_rhcp", "amplitude_db"): float(amp[1]),
        h10b_column_name("tiltB_lhcp", "amplitude_db"): float(amp[2]),
        h10b_column_name("tiltB_rhcp", "amplitude_db"): float(amp[3]),
    }
    vectors = extract_h10b_observation_vectors(payload, include_auxiliary_contrasts=include_auxiliary_contrasts)
    return vectors.contrast_order, vectors.contrast_vec


def predict_h10b_contrast_vector_db(
    amp_pred_db: float,
    bearing_deg: float,
    yaw_deg: float,
    *,
    include_auxiliary_contrasts: bool = False,
) -> tuple[tuple[str, ...], np.ndarray]:
    amp_vec = predict_h10b_amplitude_vector_db(amp_pred_db, bearing_deg, yaw_deg)
    return h10b_contrast_vector_from_amplitude_vector(
        amp_vec,
        include_auxiliary_contrasts=include_auxiliary_contrasts,
    )


def apply_h10b_vector_rssd_control(
    observed_contrast_vec: np.ndarray,
    *,
    control: str,
    seed: int = 0,
) -> np.ndarray:
    """Apply deterministic negative controls to the H10B RSSD contrast vector."""
    vec = np.asarray(observed_contrast_vec, dtype=float).copy()
    if control in ("vector_nominal", "rssd_nominal", ""):
        return vec
    if control in ("vector_zero", "rssd_zero"):
        return np.zeros_like(vec)
    if control in ("vector_sign_flip", "rssd_sign_flip"):
        return -vec
    if control in ("vector_shuffle", "rssd_shuffle"):
        rng = np.random.default_rng(int(seed))
        order = np.arange(vec.size)
        rng.shuffle(order)
        return vec[order]
    if control == "vector_channel_order_corrupt":
        if vec.size == 4:
            return vec[[1, 0, 3, 2]]
        if vec.size == 6:
            return vec[[1, 0, 3, 2, 5, 4]]
        return vec[::-1]
    return vec


def h10b_vector_rssd_log_score(
    observed_contrast_vec: np.ndarray,
    predicted_contrast_vec: np.ndarray,
    *,
    valid_mask: np.ndarray | None = None,
    contrast_order: tuple[str, ...] | None = None,
    sigma_db: float = 4.0,
    control: str = "vector_nominal",
    seed: int = 0,
    prediction_source: str = "proxy_vector_baseline",
) -> H10BVectorRSSDScore:
    observed = apply_h10b_vector_rssd_control(observed_contrast_vec, control=control, seed=seed)
    predicted = np.asarray(predicted_contrast_vec, dtype=float)
    covariance = build_diagonal_covariance(predicted.size, sigma_db)
    score = h10b_mahalanobis_log_score(observed, predicted, covariance, valid_mask=valid_mask)
    order = contrast_order or tuple(f"contrast_{idx}" for idx in range(predicted.size))
    return H10BVectorRSSDScore(
        control=control,
        prediction_source=prediction_source,
        contrast_order=order,
        observed=observed,
        predicted=predicted,
        residual=score.residual,
        valid_mask=score.valid_mask,
        valid_count=score.valid_count,
        mahalanobis=score.mahalanobis,
        log_score=score.log_score,
    )
