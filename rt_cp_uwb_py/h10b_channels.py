from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import math
from typing import Any, Iterable


SCHEMA_VERSION = "h10b_four_channel_v1"


@dataclass(frozen=True)
class H10BChannel:
    channel_id: str
    index: int
    tilt_set: str
    polarization: str
    legacy_antenna: str
    legacy_raw_channel: str
    legacy_suffix: str

    @property
    def canonical_suffix(self) -> str:
        return self.channel_id


CANONICAL_H10B_CHANNELS: tuple[H10BChannel, ...] = (
    H10BChannel("tiltA_lhcp", 0, "tiltA", "LHCP", "ant1", "ANT1_LHCP", "ant1_lhcp"),
    H10BChannel("tiltA_rhcp", 1, "tiltA", "RHCP", "ant1", "ANT1_RHCP", "ant1_rhcp"),
    H10BChannel("tiltB_lhcp", 2, "tiltB", "LHCP", "ant2", "ANT2_LHCP", "ant2_lhcp"),
    H10BChannel("tiltB_rhcp", 3, "tiltB", "RHCP", "ant2", "ANT2_RHCP", "ant2_rhcp"),
)

CANONICAL_H10B_CHANNEL_ORDER: tuple[str, ...] = tuple(channel.channel_id for channel in CANONICAL_H10B_CHANNELS)
LEGACY_H10B_RAW_CIR_CHANNEL_ORDER: tuple[str, ...] = tuple(channel.legacy_raw_channel for channel in CANONICAL_H10B_CHANNELS)
LEGACY_H10B_SUFFIX_ORDER: tuple[str, ...] = tuple(channel.legacy_suffix for channel in CANONICAL_H10B_CHANNELS)

H10B_MAIN_CONTRASTS: tuple[dict[str, str], ...] = (
    {
        "contrast_id": "pol_contrast_tiltA_db",
        "left_channel": "tiltA_rhcp",
        "right_channel": "tiltA_lhcp",
        "meaning": "same-tilt polarization contrast: RHCP - LHCP on tilt set A",
    },
    {
        "contrast_id": "pol_contrast_tiltB_db",
        "left_channel": "tiltB_rhcp",
        "right_channel": "tiltB_lhcp",
        "meaning": "same-tilt polarization contrast: RHCP - LHCP on tilt set B",
    },
    {
        "contrast_id": "tilt_contrast_lhcp_db",
        "left_channel": "tiltA_lhcp",
        "right_channel": "tiltB_lhcp",
        "meaning": "same-polarization tilt contrast: tilt A - tilt B for LHCP",
    },
    {
        "contrast_id": "tilt_contrast_rhcp_db",
        "left_channel": "tiltA_rhcp",
        "right_channel": "tiltB_rhcp",
        "meaning": "same-polarization tilt contrast: tilt A - tilt B for RHCP",
    },
)

H10B_AUXILIARY_CONTRASTS: tuple[dict[str, str], ...] = (
    {
        "contrast_id": "cross_tilt_pol_A_lhcp_minus_B_rhcp_db",
        "left_channel": "tiltA_lhcp",
        "right_channel": "tiltB_rhcp",
        "meaning": "auxiliary cross tilt/polarization contrast: tilt A LHCP - tilt B RHCP",
    },
    {
        "contrast_id": "cross_tilt_pol_A_rhcp_minus_B_lhcp_db",
        "left_channel": "tiltA_rhcp",
        "right_channel": "tiltB_lhcp",
        "meaning": "auxiliary cross tilt/polarization contrast: tilt A RHCP - tilt B LHCP",
    },
)

_CHANNEL_BY_ID = {channel.channel_id.lower(): channel for channel in CANONICAL_H10B_CHANNELS}
_CHANNEL_BY_LEGACY_RAW = {channel.legacy_raw_channel.lower(): channel for channel in CANONICAL_H10B_CHANNELS}
_CHANNEL_BY_LEGACY_SUFFIX = {channel.legacy_suffix.lower(): channel for channel in CANONICAL_H10B_CHANNELS}


def canonical_h10b_channel(alias: str) -> H10BChannel:
    key = str(alias).strip().lower()
    for lookup in (_CHANNEL_BY_ID, _CHANNEL_BY_LEGACY_RAW, _CHANNEL_BY_LEGACY_SUFFIX):
        if key in lookup:
            return lookup[key]
    raise KeyError(f"Unknown H10B channel alias: {alias!r}")


def h10b_column_name(channel_alias: str, field: str, *, canonical: bool = True) -> str:
    channel = canonical_h10b_channel(channel_alias)
    suffix = channel.canonical_suffix if canonical else channel.legacy_suffix
    return f"h10b_{suffix}_{field}"


def h10b_vector_column_names(field: str, *, canonical: bool = True) -> list[str]:
    return [h10b_column_name(channel.channel_id, field, canonical=canonical) for channel in CANONICAL_H10B_CHANNELS]


def h10b_candidate_column_names(field: str) -> list[str]:
    """Return canonical columns first, then legacy aliases, in canonical channel order."""
    return h10b_vector_column_names(field, canonical=True) + h10b_vector_column_names(field, canonical=False)


def h10b_raw_channel_for(channel_alias: str) -> str:
    return canonical_h10b_channel(channel_alias).legacy_raw_channel


def h10b_legacy_suffix_for(channel_alias: str) -> str:
    return canonical_h10b_channel(channel_alias).legacy_suffix


def h10b_channel_order_manifest(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "channel_order": list(CANONICAL_H10B_CHANNEL_ORDER),
        "legacy_raw_channel_order": list(LEGACY_H10B_RAW_CIR_CHANNEL_ORDER),
        "canonical_columns": {
            "range_m": h10b_vector_column_names("range_m", canonical=True),
            "amplitude_db": h10b_vector_column_names("amplitude_db", canonical=True),
        },
        "legacy_alias_columns": {
            "range_m": h10b_vector_column_names("range_m", canonical=False),
            "amplitude_db": h10b_vector_column_names("amplitude_db", canonical=False),
        },
        "channels": [{**asdict(channel), "canonical_suffix": channel.canonical_suffix} for channel in CANONICAL_H10B_CHANNELS],
        "solver_facing": True,
        "evaluation_truth": False,
        "q_clean_interpretation": "clean-session / UWB prior suitability; not range-error probability",
        "claim_boundary": "synthetic four-channel receiver schema; not real-AMR validation",
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_h10b_channel_order_manifest(path: str | Path, extra: dict[str, Any] | None = None) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(h10b_channel_order_manifest(extra), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def h10b_channel_schema_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for channel in CANONICAL_H10B_CHANNELS:
        rows.append(
            {
                "channel_index": channel.index,
                "channel_id": channel.channel_id,
                "tilt_set": channel.tilt_set,
                "polarization": channel.polarization,
                "legacy_antenna": channel.legacy_antenna,
                "legacy_raw_channel": channel.legacy_raw_channel,
                "legacy_suffix": channel.legacy_suffix,
                "range_column": h10b_column_name(channel.channel_id, "range_m", canonical=True),
                "amplitude_column": h10b_column_name(channel.channel_id, "amplitude_db", canonical=True),
                "legacy_range_column": h10b_column_name(channel.channel_id, "range_m", canonical=False),
                "legacy_amplitude_column": h10b_column_name(channel.channel_id, "amplitude_db", canonical=False),
            }
        )
    return rows


def h10b_contrast_column_names(*, include_auxiliary: bool = True) -> list[str]:
    contrast_defs = list(H10B_MAIN_CONTRASTS)
    if include_auxiliary:
        contrast_defs.extend(H10B_AUXILIARY_CONTRASTS)
    return [contrast["contrast_id"] for contrast in contrast_defs]


def h10b_contrast_feature_rows(*, include_auxiliary: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    contrast_defs = list(H10B_MAIN_CONTRASTS)
    if include_auxiliary:
        contrast_defs.extend(H10B_AUXILIARY_CONTRASTS)
    for contrast in contrast_defs:
        left = canonical_h10b_channel(contrast["left_channel"])
        right = canonical_h10b_channel(contrast["right_channel"])
        rows.append(
            {
                "contrast_id": contrast["contrast_id"],
                "left_channel": left.channel_id,
                "right_channel": right.channel_id,
                "formula": f"{h10b_column_name(left.channel_id, 'amplitude_db')} - {h10b_column_name(right.channel_id, 'amplitude_db')}",
                "left_legacy_column": h10b_column_name(left.channel_id, "amplitude_db", canonical=False),
                "right_legacy_column": h10b_column_name(right.channel_id, "amplitude_db", canonical=False),
                "contrast_group": "main" if contrast in H10B_MAIN_CONTRASTS else "auxiliary",
                "meaning": contrast["meaning"],
                "solver_facing": True,
                "evaluation_truth": False,
            }
        )
    return rows


def _h10b_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _h10b_saturated(value: float, *, saturation_low_db: float | None, saturation_high_db: float | None) -> bool:
    if saturation_low_db is not None and value <= saturation_low_db:
        return True
    if saturation_high_db is not None and value >= saturation_high_db:
        return True
    return False


def compute_h10b_contrast_features(
    payload: dict[str, Any],
    *,
    include_auxiliary: bool = True,
    saturation_low_db: float | None = None,
    saturation_high_db: float | None = None,
) -> dict[str, Any]:
    """Compute physically interpretable H10B amplitude contrast features.

    Contrast signs are fixed in canonical channel order. Missing or saturated
    channels invalidate only the contrasts that depend on those channels.
    """
    normalized = normalize_h10b_observation_payload(payload, fields=("amplitude_db",))
    amplitudes: dict[str, float | None] = {}
    missing_mask = 0
    saturated_mask = 0

    for channel in CANONICAL_H10B_CHANNELS:
        value = _h10b_float_or_none(normalized.get(h10b_column_name(channel.channel_id, "amplitude_db")))
        amplitudes[channel.channel_id] = value
        bit = 1 << channel.index
        if value is None:
            missing_mask |= bit
        elif _h10b_saturated(value, saturation_low_db=saturation_low_db, saturation_high_db=saturation_high_db):
            saturated_mask |= bit

    def valid(channel_id: str) -> bool:
        channel = canonical_h10b_channel(channel_id)
        bit = 1 << channel.index
        return bool(amplitudes[channel.channel_id] is not None and not (saturated_mask & bit))

    out: dict[str, Any] = {
        "h10b_channel_order_id": SCHEMA_VERSION,
        "h10b_valid_channel_count": sum(1 for channel in CANONICAL_H10B_CHANNELS if valid(channel.channel_id)),
        "h10b_missing_channel_mask": missing_mask,
        "h10b_saturated_channel_mask": saturated_mask,
    }
    contrast_defs = list(H10B_MAIN_CONTRASTS)
    if include_auxiliary:
        contrast_defs.extend(H10B_AUXILIARY_CONTRASTS)

    for contrast in contrast_defs:
        left = canonical_h10b_channel(contrast["left_channel"])
        right = canonical_h10b_channel(contrast["right_channel"])
        if valid(left.channel_id) and valid(right.channel_id):
            out[contrast["contrast_id"]] = amplitudes[left.channel_id] - amplitudes[right.channel_id]  # type: ignore[operator]
        else:
            out[contrast["contrast_id"]] = None

    out["h10b_main_contrast_valid_count"] = sum(
        1 for contrast in H10B_MAIN_CONTRASTS if out[contrast["contrast_id"]] is not None
    )
    return out


def normalize_h10b_observation_payload(payload: dict[str, Any], fields: Iterable[str] = ("range_m", "amplitude_db")) -> dict[str, Any]:
    """Copy legacy H10B observation columns to canonical column names when present."""
    out = dict(payload)
    for field in fields:
        for channel in CANONICAL_H10B_CHANNELS:
            canonical_col = h10b_column_name(channel.channel_id, field, canonical=True)
            legacy_col = h10b_column_name(channel.channel_id, field, canonical=False)
            if canonical_col not in out and legacy_col in out:
                out[canonical_col] = out[legacy_col]
    return out
