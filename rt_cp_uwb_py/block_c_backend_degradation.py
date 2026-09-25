"""Backend-evidence degradation helpers for Paper 2 Block C.

The helpers here bind the STEP 2 channel-level CP margin drop to backend
evidence weights as a smoke diagnostic only.  They do not define grounded
hardware limits or a failure threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd


DEGRADATION_BINDING_METHOD = "SMOKE_PROBABILITY_RETENTION_FROM_STEP2_CP_MARGIN_PROXY"


@dataclass(frozen=True)
class BackendDegradationProfile:
    """A STEP 2 worst-phase profile bound to backend evidence retention."""

    profile_id: str
    knob: str
    level_id: str
    phase_rad: float
    cp_margin_proxy_db: float
    cp_margin_drop_from_ideal_db: float
    state_nll_proxy: float
    retention: float
    binding_method: str = DEGRADATION_BINDING_METHOD


def retention_from_margin_drop_db(drop_db: float, db_scale: float = 10.0) -> float:
    """Convert a CP-margin drop in dB to a clipped evidence-retention factor.

    ``cp_margin_proxy_db`` is a 10log10 power-ratio proxy in STEP 2, so the
    default scale is 10 dB per decade.  Non-negative drops keep full retention.
    """

    drop = float(drop_db)
    scale = float(db_scale)
    if not isfinite(drop):
        raise ValueError("drop_db must be finite")
    if not isfinite(scale) or scale <= 0.0:
        raise ValueError("db_scale must be finite and positive")
    if drop >= 0.0:
        return 1.0
    return float(np.clip(10.0 ** (drop / scale), 0.0, 1.0))


def degrade_probability_to_neutral(probability: Any, retention: float, neutral: float = 0.5) -> np.ndarray:
    """Move backend evidence probabilities toward a neutral probability."""

    p = np.asarray(probability, dtype=float)
    r = float(retention)
    n = float(neutral)
    if not isfinite(r) or r < 0.0 or r > 1.0:
        raise ValueError("retention must be finite and within [0, 1]")
    if not isfinite(n) or n <= 0.0 or n >= 1.0:
        raise ValueError("neutral must be finite and within (0, 1)")
    degraded = n + r * (p - n)
    return np.clip(degraded, 1.0e-6, 1.0 - 1.0e-6)


def sanitize_profile_id(value: str) -> str:
    """Return a filesystem-safe profile identifier."""

    text = str(value).strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("_") or "profile"


def profiles_from_worst_phase_table(
    worst: pd.DataFrame,
    requested: Iterable[str],
    db_scale: float = 10.0,
) -> list[BackendDegradationProfile]:
    """Select STEP 2 worst-phase rows and attach retention factors."""

    required = {
        "knob",
        "level_id",
        "phase_rad",
        "cp_margin_proxy_db",
        "cp_margin_drop_from_ideal_db",
        "state_nll_proxy",
    }
    missing = sorted(required.difference(worst.columns))
    if missing:
        raise ValueError(f"STEP 2 worst-phase table is missing columns: {missing}")
    frame = worst.copy()
    frame["level_id"] = frame["level_id"].astype(str)
    tokens = [str(item).strip() for item in requested if str(item).strip()]
    if len(tokens) == 1 and tokens[0].lower() in {"all", "all_worst"}:
        selected = frame.sort_values(["knob", "severity_order", "level_id"], na_position="last").copy()
    else:
        wanted = set(tokens)
        selected = frame[frame["level_id"].isin(wanted)].copy()
        missing_levels = sorted(wanted.difference(set(selected["level_id"].astype(str))))
        if missing_levels:
            raise ValueError(f"Requested profiles are missing from STEP 2 worst-phase table: {missing_levels}")
        selected["_request_order"] = selected["level_id"].map({level: i for i, level in enumerate(tokens)})
        selected = selected.sort_values("_request_order").drop(columns=["_request_order"])

    profiles: list[BackendDegradationProfile] = []
    seen: set[str] = set()
    for row in selected.to_dict("records"):
        level = str(row["level_id"])
        profile_id = sanitize_profile_id(level)
        if profile_id in seen:
            profile_id = sanitize_profile_id(f"{row['knob']}_{level}")
        seen.add(profile_id)
        drop = float(row["cp_margin_drop_from_ideal_db"])
        profiles.append(
            BackendDegradationProfile(
                profile_id=profile_id,
                knob=str(row["knob"]),
                level_id=level,
                phase_rad=float(row["phase_rad"]),
                cp_margin_proxy_db=float(row["cp_margin_proxy_db"]),
                cp_margin_drop_from_ideal_db=drop,
                state_nll_proxy=float(row["state_nll_proxy"]),
                retention=retention_from_margin_drop_db(drop, db_scale=db_scale),
            )
        )
    return profiles
