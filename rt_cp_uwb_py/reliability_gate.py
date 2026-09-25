from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


FIX_VALID = "FIX_VALID"
FIX_LOW_CONFIDENCE = "FIX_LOW_CONFIDENCE"
CIRCLE_ONLY = "CIRCLE_ONLY"


@dataclass(frozen=True)
class ReliabilityGateConfig:
    N_min: int = 5
    N_ref: int = 20
    roomC_noLos_weight: float = 0.25
    high_residual_weight: float = 0.30
    bad_geometry_weight: float = 0.20
    condition_max: float = 10.0
    min_weight_for_fix: float = 0.4
    max_rssd_rmse_db: float = 3.0
    allow_ground_truth_los: bool = False
    nlos_score_threshold: float = 0.5
    direct_power_ratio_min: float = 0.2
    path_quality_score_min: float = 0.5
    low_path_quality_weight: float = 0.25


@dataclass(frozen=True)
class ReliabilityWeightResult:
    reliability_weight: float
    w_lut: float
    w_los: float
    w_resid: float
    w_geom: float
    w_path: float
    reliability_reason: str
    los_label_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "reliability_weight": self.reliability_weight,
            "w_lut": self.w_lut,
            "w_los": self.w_los,
            "w_resid": self.w_resid,
            "w_geom": self.w_geom,
            "w_path": self.w_path,
            "reliability_reason": self.reliability_reason,
            "los_label_source": self.los_label_source,
        }


def compute_reliability_weight(
    sample: Mapping[str, Any] | pd.Series,
    result: Mapping[str, Any] | pd.Series,
    cfg: ReliabilityGateConfig | Mapping[str, Any] | None = None,
) -> ReliabilityWeightResult:
    """Compute support-aware reliability weight before localization error is known.

    The function intentionally ignores ground-truth localization error columns
    such as ``xy_error_m`` and ``phi_error_deg``.
    """

    config = _coerce_cfg(cfg)
    sample_row = _to_dict(sample)
    result_row = _to_dict(result)
    reasons: list[str] = []

    train_n = _train_n(result_row)
    w_lut = _component_or_default(result_row, "w_lut", min(1.0, train_n / float(config.N_ref)) if config.N_ref else 1.0)
    if train_n < config.N_min:
        reasons.append("low_lut_support")

    los_label, los_source = _observable_los_label(sample_row, result_row, config)
    hard_room_c_no_los = _is_room_c(sample_row, result_row) and los_label == "no_los"
    w_los = _component_or_default(result_row, "w_los", config.roomC_noLos_weight if hard_room_c_no_los else 1.0)
    if hard_room_c_no_los:
        reasons.append("roomC_noLos_hard_regime")

    rssd_rmse = _first_finite(
        result_row.get("rssd_rmse_db"),
        sample_row.get("rssd_rmse_db"),
        result_row.get("rssd_residual_db"),
        sample_row.get("rssd_residual_db"),
    )
    high_residual = np.isfinite(rssd_rmse) and rssd_rmse > config.max_rssd_rmse_db
    w_resid = _component_or_default(result_row, "w_resid", config.high_residual_weight if high_residual else 1.0)
    if high_residual:
        reasons.append("high_rssd_residual")

    rank = _as_int(result_row.get("jacobian_rank", sample_row.get("jacobian_rank")), default=0)
    condition = _as_float(result_row.get("jacobian_condition", sample_row.get("jacobian_condition")))
    bad_geometry = rank < 2 or not np.isfinite(condition) or condition > config.condition_max
    w_geom = _component_or_default(result_row, "w_geom", config.bad_geometry_weight if bad_geometry else 1.0)
    if bad_geometry:
        reasons.append("bad_identifiability")

    direct_power_ratio = _first_finite(result_row.get("direct_power_ratio"), sample_row.get("direct_power_ratio"))
    path_quality_score = _first_finite(result_row.get("path_quality_score"), sample_row.get("path_quality_score"))
    low_direct_power = np.isfinite(direct_power_ratio) and direct_power_ratio < config.direct_power_ratio_min
    low_path_quality = np.isfinite(path_quality_score) and path_quality_score < config.path_quality_score_min
    w_path = _component_or_default(
        result_row,
        "w_path",
        config.low_path_quality_weight if low_direct_power or low_path_quality else 1.0,
    )
    if low_direct_power:
        reasons.append("low_direct_power_ratio")
    if low_path_quality:
        reasons.append("low_path_quality")

    weight = float(w_lut * w_los * w_resid * w_geom * w_path)
    return ReliabilityWeightResult(
        reliability_weight=weight,
        w_lut=float(w_lut),
        w_los=float(w_los),
        w_resid=float(w_resid),
        w_geom=float(w_geom),
        w_path=float(w_path),
        reliability_reason=";".join(reasons) if reasons else "ok",
        los_label_source=los_source,
    )


def classify_fix_status(result: Mapping[str, Any] | pd.Series, cfg: ReliabilityGateConfig | Mapping[str, Any] | None = None) -> str:
    """Classify a localization output without using localization error columns."""

    config = _coerce_cfg(cfg)
    row = _to_dict(result)
    rank = _as_int(row.get("jacobian_rank"), default=0)
    if rank < 2:
        return CIRCLE_ONLY
    reliability_weight = _as_float(row.get("reliability_weight"))
    if not np.isfinite(reliability_weight):
        reliability_weight = 0.0
    if reliability_weight < config.min_weight_for_fix:
        return FIX_LOW_CONFIDENCE
    rssd_rmse = _first_finite(row.get("rssd_rmse_db"), row.get("rssd_residual_db"))
    if np.isfinite(rssd_rmse) and rssd_rmse > config.max_rssd_rmse_db:
        return FIX_LOW_CONFIDENCE
    return FIX_VALID


def apply_reliability_gate(
    sample: Mapping[str, Any] | pd.Series,
    result: Mapping[str, Any] | pd.Series,
    cfg: ReliabilityGateConfig | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    weight = compute_reliability_weight(sample, result, cfg)
    merged = {**_to_dict(result), **weight.as_dict()}
    merged["fix_status"] = classify_fix_status(merged, cfg)
    return merged


def _coerce_cfg(cfg: ReliabilityGateConfig | Mapping[str, Any] | None) -> ReliabilityGateConfig:
    if cfg is None:
        return ReliabilityGateConfig()
    if isinstance(cfg, ReliabilityGateConfig):
        return cfg
    kwargs = {field: cfg[field] for field in ReliabilityGateConfig.__dataclass_fields__ if field in cfg}
    return ReliabilityGateConfig(**kwargs)


def _to_dict(values: Mapping[str, Any] | pd.Series) -> dict[str, Any]:
    if isinstance(values, pd.Series):
        return values.to_dict()
    return dict(values)


def _train_n(result: Mapping[str, Any]) -> float:
    for col in ("min_train_samples_per_obs", "train_n", "train_samples_in_selected_bin"):
        value = _as_float(result.get(col))
        if np.isfinite(value):
            return max(0.0, value)
    return 0.0


def _component_or_default(result: Mapping[str, Any], key: str, default: float) -> float:
    value = _as_float(result.get(key))
    if not np.isfinite(value):
        return float(default)
    return float(value)


def _observable_los_label(sample: Mapping[str, Any], result: Mapping[str, Any], cfg: ReliabilityGateConfig) -> tuple[str | None, str]:
    for col in ("estimated_los_label", "estimated_los_state"):
        text = _nonempty(sample.get(col, result.get(col)))
        if text is not None:
            return _norm_los(text), col
    nlos_score = _as_float(sample.get("nlos_score", result.get("nlos_score")))
    if np.isfinite(nlos_score):
        return ("no_los" if nlos_score >= cfg.nlos_score_threshold else "los"), "nlos_score"
    if cfg.allow_ground_truth_los:
        text = _nonempty(sample.get("los_label", result.get("los_label")))
        if text is not None:
            return _norm_los(text), "ground_truth_los_label"
    return None, "none"


def _is_room_c(sample: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    room = sample.get("room_type", result.get("room_type"))
    return str(room).strip().upper() == "C"


def _nonempty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "unknown", "unknown_los"}:
        return None
    return text


def _norm_los(value: Any) -> str:
    text = str(value).strip().lower().replace("-", "_")
    if text in {"nlos", "no_los", "non_los", "blocked"}:
        return "no_los"
    if text in {"los", "line_of_sight"}:
        return "los"
    return text


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _first_finite(*values: Any) -> float:
    for value in values:
        number = _as_float(value)
        if np.isfinite(number):
            return number
    return np.nan


def _as_int(value: Any, *, default: int) -> int:
    number = _as_float(value)
    if not np.isfinite(number):
        return default
    return int(number)
