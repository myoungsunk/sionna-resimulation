from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np


def finite_float(value: Any, default: float = np.nan) -> float:
    """Return a finite float or a fallback without importing solver scripts."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    return out if math.isfinite(out) else float(default)


def wrap_deg(angle_deg: float) -> float:
    return (float(angle_deg) + 180.0) % 360.0 - 180.0


def orientation_aware_rssd_prediction_db(
    pose: tuple[float, float, float],
    yaw_deg: float,
    candidate: tuple[float, float, float, str] | None,
    model_config: Mapping[str, Any] | None = None,
) -> float:
    """Truth-free orientation-aware RSSD proxy from pose yaw and candidate geometry.

    The helper intentionally uses only solver-facing pose/yaw/candidate geometry.
    It does not inspect truth association, path labels, or VA truth metadata.
    """
    if candidate is None:
        return np.nan
    if not math.isfinite(finite_float(candidate[0])) or not math.isfinite(finite_float(candidate[1])):
        return np.nan

    config = dict(model_config or {})
    x, y, _pose_yaw = pose
    cx, cy, _cz, candidate_type = candidate
    bearing_world = math.degrees(math.atan2(float(cy) - float(y), float(cx) - float(x)))
    bearing_body = wrap_deg(bearing_world - float(yaw_deg))

    scale_db = finite_float(config.get("bearing_scale_db"), 3.0)
    type_key = "va_bias_db" if "VA" in str(candidate_type).upper() else "pa_bias_db"
    type_bias = finite_float(config.get(type_key, config.get("type_bias_db", 0.0)), 0.0)
    value = type_bias + scale_db * math.cos(math.radians(2.0 * bearing_body))

    if bool(config.get("range_attenuation", True)):
        min_range_m = max(finite_float(config.get("min_range_m"), 0.25), 1e-6)
        range_norm = max(math.hypot(float(cx) - float(x), float(cy) - float(y)), min_range_m)
        value = type_bias + (scale_db * math.cos(math.radians(2.0 * bearing_body)) / math.sqrt(range_norm))

    return float(value)


def rssd_prediction_model_label(model_config: Mapping[str, Any] | None = None) -> str:
    config = dict(model_config or {})
    if config.get("antenna_model_mode"):
        return f"orientation_aware_proxy:{config['antenna_model_mode']}"
    if config.get("range_attenuation", True):
        return "orientation_aware_cosine_range_attenuated_v1"
    return "orientation_aware_cosine_no_range_attenuation_v1"
