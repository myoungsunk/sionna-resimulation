from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from rt_cp_uwb_py.h10b_channels import (
    CANONICAL_H10B_CHANNEL_ORDER,
    SCHEMA_VERSION,
    compute_h10b_contrast_features,
    h10b_column_name,
    normalize_h10b_observation_payload,
)
from rt_cp_uwb_py.h10b_vector_likelihood import extract_h10b_observation_vectors


FORBIDDEN_SOLVER_COLUMN_PATTERNS: tuple[str, ...] = (
    "truth",
    "gt",
    "ground_truth",
    "oracle",
    "path_truth",
    "va_catalog_truth",
    "matched_path_truth_id",
    "truth_assoc",
    "is_true_candidate",
    "true_candidate",
    "da_truth",
    "va_truth",
    "feature_result_truth",
    "beta_body_deg_truth",
    "theta_elevation_deg_truth",
)


@dataclass(frozen=True)
class H10BQCleanFeatureConfig:
    range_consistency_sigma_m: float = 0.25
    amplitude_scale_db: float = 12.0


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _finite_stats(values: np.ndarray) -> dict[str, float | None]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {"mean": None, "std": None, "span": None}
    return {
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "span": float(np.max(finite) - np.min(finite)),
    }


def h10b_range_consistency_score(range_vec: np.ndarray, *, sigma_m: float = 0.25) -> float | None:
    finite = np.asarray(range_vec, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        return None
    if sigma_m <= 0:
        raise ValueError("sigma_m must be positive")
    return float(math.exp(-float(np.std(finite)) / float(sigma_m)))


def qclean_4ch_calibration_proxy(feature_row: dict[str, Any]) -> float | None:
    """Truth-free q-clean suitability proxy for calibration surface only.

    This is not a trained classifier and must not be interpreted as range-error
    probability. It combines the existing q_clean clean-session score with
    four-channel availability and range consistency so downstream reports can
    quantify whether retraining inputs are present.
    """
    q_old = _float_or_none(feature_row.get("q_clean_old"))
    if q_old is None:
        return None
    valid_ratio = float(feature_row.get("h10b_valid_channel_count", 0) or 0) / 4.0
    if valid_ratio <= 0.0:
        return None
    range_score = _float_or_none(feature_row.get("range_consistency_score"))
    if range_score is None:
        range_score = 0.0
    availability = 0.5 + 0.5 * _clip01(valid_ratio)
    consistency = 0.5 + 0.5 * _clip01(range_score)
    return _clip01(q_old * availability * consistency)


def compute_h10b_qclean_feature_row(
    payload: dict[str, Any],
    *,
    profile_key: str | None = None,
    config: H10BQCleanFeatureConfig | None = None,
) -> dict[str, Any]:
    config = config or H10BQCleanFeatureConfig()
    normalized = normalize_h10b_observation_payload(payload, fields=("range_m", "amplitude_db"))
    vectors = extract_h10b_observation_vectors(normalized)
    contrasts = compute_h10b_contrast_features(normalized, include_auxiliary=True)
    range_stats = _finite_stats(vectors.range_vec)
    amp_stats = _finite_stats(vectors.amplitude_vec)
    range_score = h10b_range_consistency_score(
        vectors.range_vec,
        sigma_m=config.range_consistency_sigma_m,
    )
    amp_finite = vectors.amplitude_vec[np.isfinite(vectors.amplitude_vec)]
    if amp_finite.size:
        amp_centered = amp_finite - float(np.mean(amp_finite))
        amplitude_normalized_l2 = float(np.linalg.norm(amp_centered))
    else:
        amplitude_normalized_l2 = None

    out: dict[str, Any] = {
        "profile_key": profile_key,
        "dataset_slice": payload.get("dataset_slice") or profile_key,
        "sequence_id": payload.get("sequence_id"),
        "measurement_id": payload.get("measurement_id"),
        "timestamp": payload.get("timestamp"),
        "time_idx": payload.get("time_idx"),
        "anchor_id": payload.get("anchor_id"),
        "q_clean_old": payload.get("q_clean"),
        "cp_score": payload.get("cp_score"),
        "p_NoLoS": payload.get("p_NoLoS"),
        "p_RD": payload.get("p_RD"),
        "p_HB_prior": payload.get("p_HB_prior"),
        "late_leakage": payload.get("late_leakage"),
        "cp_parity_confidence": payload.get("cp_parity_confidence"),
        "h10b_channel_order_id": SCHEMA_VERSION,
        "h10b_valid_channel_count": int(np.isfinite(vectors.amplitude_vec).sum()),
        "h10b_valid_range_channel_count": int(np.isfinite(vectors.range_vec).sum()),
        "h10b_4ch_feature_available": bool(np.isfinite(vectors.amplitude_vec).sum() == 4),
        "range_mean_m": range_stats["mean"],
        "range_std_m": range_stats["std"],
        "range_span_m": range_stats["span"],
        "range_consistency_score": range_score,
        "amplitude_mean_db": amp_stats["mean"],
        "amplitude_std_db": amp_stats["std"],
        "amplitude_span_db": amp_stats["span"],
        "amplitude_normalized_l2": amplitude_normalized_l2,
    }

    for channel in CANONICAL_H10B_CHANNEL_ORDER:
        out[h10b_column_name(channel, "range_m")] = normalized.get(h10b_column_name(channel, "range_m"))
        out[h10b_column_name(channel, "amplitude_db")] = normalized.get(h10b_column_name(channel, "amplitude_db"))

    for key, value in contrasts.items():
        out[key] = value

    out["q_clean_4ch_calibration_proxy"] = qclean_4ch_calibration_proxy(out)
    return out


def audit_solver_facing_columns(columns: list[str], *, table_name: str, namespace: str = "solver_input") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in columns:
        lower = column.lower()
        for pattern in FORBIDDEN_SOLVER_COLUMN_PATTERNS:
            if pattern in lower:
                is_solver = namespace == "solver_input"
                rows.append(
                    {
                        "table_name": table_name,
                        "namespace": namespace,
                        "column_name": column,
                        "forbidden_pattern": pattern,
                        "allowed": not is_solver,
                        "severity": "high" if is_solver else "low",
                        "action": "remove_from_solver_input" if is_solver else "evaluation_only_allowed",
                    }
                )
    if not rows:
        rows.append(
            {
                "table_name": table_name,
                "namespace": namespace,
                "column_name": "",
                "forbidden_pattern": "",
                "allowed": True,
                "severity": "none",
                "action": "pass",
            }
        )
    return rows
