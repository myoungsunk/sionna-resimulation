from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from rt_cp_uwb_py.h10b_channels import (
    CANONICAL_H10B_CHANNEL_ORDER,
    compute_h10b_contrast_features,
    h10b_column_name,
    normalize_h10b_observation_payload,
)


LEGACY_SUFFIX_TO_CANONICAL: dict[str, str] = {
    "ant1_lhcp": "tiltA_lhcp",
    "ant1_rhcp": "tiltA_rhcp",
    "ant2_lhcp": "tiltB_lhcp",
    "ant2_rhcp": "tiltB_rhcp",
}

RAW_VECTOR_CHANNEL_TO_CANONICAL: dict[str, str] = {
    "ANT1_LHCP": "tiltA_lhcp",
    "ANT1_RHCP": "tiltA_rhcp",
    "ANT2_LHCP": "tiltB_lhcp",
    "ANT2_RHCP": "tiltB_rhcp",
}

RSS_SOURCE_AMPLITUDE_COLUMNS: dict[str, str] = {
    "tiltA_lhcp": "RSS_ant1_LH_db",
    "tiltA_rhcp": "RSS_ant1_RH_db",
    "tiltB_lhcp": "RSS_ant2_LH_db",
    "tiltB_rhcp": "RSS_ant2_RH_db",
}

RSS_SOURCE_RANGE_COLUMNS: tuple[str, ...] = (
    "raw_cir_lde_range_m",
    "range_m",
)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _json_list(value: Any) -> list[Any]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _copy_existing_h10b_columns(row: dict[str, Any], out: dict[str, Any]) -> bool:
    normalized = normalize_h10b_observation_payload(row, fields=("range_m", "amplitude_db"))
    found = False
    for channel in CANONICAL_H10B_CHANNEL_ORDER:
        for field in ("range_m", "amplitude_db"):
            column = h10b_column_name(channel, field)
            value = _float_or_none(normalized.get(column))
            if value is not None:
                out[column] = value
                found = True
    return found


def _copy_json_vectors(row: dict[str, Any], out: dict[str, Any]) -> bool:
    order_raw = str(row.get("h10b_channel_vector_order") or "").strip()
    if not order_raw:
        return False
    order = [item.strip() for item in order_raw.split(";") if item.strip()]
    range_vec = _json_list(row.get("h10b_range_vector_m"))
    amp_vec = _json_list(row.get("h10b_amplitude_vector_db"))
    found = False
    for idx, raw_channel in enumerate(order):
        canonical = RAW_VECTOR_CHANNEL_TO_CANONICAL.get(raw_channel)
        if not canonical:
            continue
        if idx < len(range_vec):
            value = _float_or_none(range_vec[idx])
            if value is not None:
                out[h10b_column_name(canonical, "range_m")] = value
                found = True
        if idx < len(amp_vec):
            value = _float_or_none(amp_vec[idx])
            if value is not None:
                out[h10b_column_name(canonical, "amplitude_db")] = value
                found = True
    return found


def _copy_external_rss_h10b_source(row: dict[str, Any], out: dict[str, Any]) -> bool:
    found_amp = False
    for channel, column in RSS_SOURCE_AMPLITUDE_COLUMNS.items():
        value = _float_or_none(row.get(column))
        if value is not None:
            out[h10b_column_name(channel, "amplitude_db")] = value
            found_amp = True

    base_range = None
    base_range_column = None
    for column in RSS_SOURCE_RANGE_COLUMNS:
        value = _float_or_none(row.get(column))
        if value is not None:
            base_range = value
            base_range_column = column
            break

    if found_amp and base_range is not None:
        for channel in CANONICAL_H10B_CHANNEL_ORDER:
            out[h10b_column_name(channel, "range_m")] = base_range
        out["h10b_range_materialization_source"] = f"shared_scalar_{base_range_column}"

    if found_amp:
        out["h10b_external_source_match"] = True
    return found_amp


def _scalar_bridge(row: dict[str, Any], out: dict[str, Any]) -> bool:
    base_range = _float_or_none(row.get("range_m"))
    base_amp = _float_or_none(row.get("amplitude_db"))
    if base_range is None and base_amp is None:
        return False
    rssd = _float_or_none(row.get("rssd_db")) or 0.0
    cp = _float_or_none(row.get("cp_score")) or _float_or_none(row.get("q_clean")) or 0.5
    cp_centered = max(-1.0, min(1.0, 2.0 * cp - 1.0))
    amp_offsets = {
        "tiltA_lhcp": -0.5 * rssd - 0.4 * cp_centered,
        "tiltA_rhcp": 0.5 * rssd - 0.4 * cp_centered,
        "tiltB_lhcp": -0.35 * rssd + 0.4 * cp_centered,
        "tiltB_rhcp": 0.35 * rssd + 0.4 * cp_centered,
    }
    range_offsets = {
        "tiltA_lhcp": -0.015,
        "tiltA_rhcp": 0.015,
        "tiltB_lhcp": -0.010,
        "tiltB_rhcp": 0.010,
    }
    for channel in CANONICAL_H10B_CHANNEL_ORDER:
        if base_range is not None:
            out[h10b_column_name(channel, "range_m")] = base_range + range_offsets[channel]
        if base_amp is not None:
            out[h10b_column_name(channel, "amplitude_db")] = base_amp + amp_offsets[channel]
    return True


def materialize_h10b_measurement_row(row: dict[str, Any], *, allow_scalar_bridge: bool = True) -> dict[str, Any]:
    """Return a solver-facing row with canonical H10B columns.

    Source priority is existing canonical/legacy columns, raw JSON vectors,
    external H10B RSS columns, then an explicitly flagged scalar bridge. The
    scalar bridge is for pipeline wiring/smoke tests only and is not measured
    H10B evidence.
    """
    out = dict(row)
    source = "missing"
    if _copy_existing_h10b_columns(row, out):
        source = "existing_h10b_columns"
    elif _copy_json_vectors(row, out):
        source = "h10b_json_vector_columns"
    elif _copy_external_rss_h10b_source(row, out):
        source = "external_rss_h10b_source_scalar_range"
    elif allow_scalar_bridge and _scalar_bridge(row, out):
        source = "synthetic_scalar_bridge_not_measured_h10b"
    out["h10b_materialization_source"] = source
    out["h10b_materialization_claim_boundary"] = (
        "pipeline_wiring_only_not_real_h10b_validation"
        if source == "synthetic_scalar_bridge_not_measured_h10b"
        else "solver_facing_h10b_columns"
    )
    contrasts = compute_h10b_contrast_features(out, include_auxiliary=True)
    out.update(contrasts)
    return out


def materialize_h10b_measurement_stream(df: pd.DataFrame, *, allow_scalar_bridge: bool = True) -> pd.DataFrame:
    rows = [
        materialize_h10b_measurement_row(record, allow_scalar_bridge=allow_scalar_bridge)
        for record in df.to_dict(orient="records")
    ]
    return pd.DataFrame(rows)


def h10b_materialization_summary(df: pd.DataFrame) -> pd.DataFrame:
    if "h10b_materialization_source" not in df.columns:
        return pd.DataFrame(columns=["h10b_materialization_source", "row_count", "fraction"])
    counts = df["h10b_materialization_source"].fillna("missing").value_counts(dropna=False)
    total = int(counts.sum())
    return pd.DataFrame(
        [
            {
                "h10b_materialization_source": str(source),
                "row_count": int(count),
                "fraction": float(count / total) if total else 0.0,
            }
            for source, count in counts.items()
        ]
    )


def h10b_valid_row_count(df: pd.DataFrame) -> int:
    amp_cols = [h10b_column_name(channel, "amplitude_db") for channel in CANONICAL_H10B_CHANNEL_ORDER]
    if not all(col in df.columns for col in amp_cols):
        return 0
    valid = np.ones(len(df), dtype=bool)
    for col in amp_cols:
        valid &= pd.to_numeric(df[col], errors="coerce").notna().to_numpy()
    return int(valid.sum())
