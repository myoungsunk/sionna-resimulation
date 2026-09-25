"""Shared contracts for the B-prime measured/simulated two-ray analysis.

The B-prime comparison has two non-negotiable admission rules:

* each simulated case uses the native frequency grid of its measured pair;
* an incomplete polarization-switch acquisition remains ``MISSING``.

This module keeps those rules out of the command-line scripts so they can be
unit-tested without loading the full measurement campaign.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from .config import RtConfig
from .measured_lp_cp import AnalysisError, read_touchstone


MISSING_STATE_RE = re.compile(
    r"state\s+(?P<state>\S+)\s+has\s+(?P<actual>\d+)\s+file\(s\),\s+"
    r"expected\s+>=\s+(?P<expected>\d+)",
    re.IGNORECASE,
)


def native_frequency_grid(folder: str | Path) -> np.ndarray:
    """Read the native frequency grid from any Touchstone file in ``folder``."""
    root = Path(folder)
    files = sorted(root.glob("*.s2p"))
    if not files:
        raise AnalysisError(f"{root}: no .s2p files available for frequency-grid recovery")
    frequency_hz, _, _ = read_touchstone(files[0])
    validate_frequency_grid(frequency_hz)
    return np.asarray(frequency_hz, dtype=float)


def validate_frequency_grid(frequency_hz: np.ndarray) -> None:
    """Require a finite, strictly increasing, uniformly spaced grid."""
    grid = np.asarray(frequency_hz, dtype=float).reshape(-1)
    if len(grid) < 2:
        raise ValueError("frequency grid must contain at least two points")
    if not np.isfinite(grid).all():
        raise ValueError("frequency grid contains non-finite values")
    delta = np.diff(grid)
    if not np.all(delta > 0):
        raise ValueError("frequency grid must be strictly increasing")
    atol = max(1e-3, float(np.median(delta)) * 1e-9)
    if not np.allclose(delta, np.median(delta), rtol=0.0, atol=atol):
        raise ValueError("frequency grid must be uniformly spaced")


def grid_matched_config(base: RtConfig, frequency_hz: np.ndarray) -> RtConfig:
    """Return an ``RtConfig`` whose generated grid matches measured native bins."""
    grid = np.asarray(frequency_hz, dtype=float).reshape(-1)
    validate_frequency_grid(grid)
    matched = replace(
        base,
        f_center=float((grid[0] + grid[-1]) / 2.0),
        bw=float(grid[-1] - grid[0]),
        n_freq=int(len(grid)),
    )
    if not np.allclose(matched.freqs, grid, rtol=0.0, atol=1e-3):
        raise ValueError("RtConfig cannot reproduce the measured native frequency grid")
    return matched


def frequency_grid_metadata(frequency_hz: np.ndarray) -> dict[str, object]:
    """Return stable metadata used to prove measured/simulated grid equality."""
    grid = np.asarray(frequency_hz, dtype="<f8").reshape(-1)
    validate_frequency_grid(grid)
    return {
        "freq_start_hz": float(grid[0]),
        "freq_stop_hz": float(grid[-1]),
        "freq_step_hz": float(np.median(np.diff(grid))),
        "n_freq": int(len(grid)),
        "freq_grid_sha256": sha256(grid.tobytes()).hexdigest(),
    }


def classify_measurement_exception(exc: BaseException) -> tuple[str, str]:
    """Map acquisition failures to literal admission states.

    Missing switch states or missing ABBA repeats are never imputed.  Other
    failures remain ``ERROR`` so data absence is not conflated with a code or
    parsing defect.
    """
    message = str(exc)
    match = MISSING_STATE_RE.search(message)
    if match:
        state = match.group("state")
        actual = match.group("actual")
        expected = match.group("expected")
        return "MISSING", f"MISSING_SWITCH_STATE:{state}:{actual}_OF_{expected}"
    return "ERROR", f"{type(exc).__name__}"


def freeze_campaign_null_gates(
    null_rows: pd.DataFrame,
    *,
    margin_db: float,
    minimum_rows: int = 1,
) -> pd.DataFrame:
    """Freeze one measured bounce gate per campaign from LoS controls.

    The rule is deliberately outcome-blind with respect to reflector cases:
    ``gate = max(LoS fitted refl/LoS) + margin_db``.  The maximum makes the
    small control set fail-closed; the fixed guard is recorded in the config.
    """
    required = {"campaign", "admission_status", "null_refl_to_los_db"}
    missing = required.difference(null_rows.columns)
    if missing:
        raise ValueError(f"null table missing columns: {sorted(missing)}")
    eligible = null_rows[
        (null_rows["admission_status"] == "ELIGIBLE")
        & np.isfinite(pd.to_numeric(null_rows["null_refl_to_los_db"], errors="coerce"))
    ].copy()
    if eligible.empty:
        raise ValueError("no eligible LoS null fits available")
    eligible["null_refl_to_los_db"] = pd.to_numeric(
        eligible["null_refl_to_los_db"], errors="raise"
    )

    rows: list[dict[str, object]] = []
    for campaign, group in eligible.groupby("campaign", sort=True):
        if len(group) < int(minimum_rows):
            raise ValueError(
                f"campaign {campaign} has {len(group)} null rows; "
                f"requires >= {minimum_rows}"
            )
        null_max = float(group["null_refl_to_los_db"].max())
        rows.append(
            {
                "campaign": int(campaign),
                "n_null_rows": int(len(group)),
                "null_max_refl_to_los_db": null_max,
                "guard_margin_db": float(margin_db),
                "measured_bounce_gate_db": null_max + float(margin_db),
                "gate_rule": "CAMPAIGN_MAX_LOS_NULL_PLUS_FIXED_MARGIN",
            }
        )
    return pd.DataFrame(rows)


def eligible_artifact_rows(
    paths: Iterable[Path],
    *,
    roles: Mapping[str, str] | None = None,
    metadata_only_suffixes: Iterable[str] = (),
) -> list[dict[str, object]]:
    """Build deterministic file rows for run/input manifests."""
    role_map = dict(roles or {})
    metadata_suffixes = {str(item).lower() for item in metadata_only_suffixes}
    rows: list[dict[str, object]] = []
    # ``Path.resolve`` performs a filesystem round-trip for every component on
    # Windows.  The measurement authority lives on OneDrive, where resolving a
    # few hundred already-absolute paths can stall before the run begins.
    # ``absolute`` keeps the same identity without triggering that hydration.
    normalized = {Path(item).absolute() for item in paths}
    for path in sorted(normalized, key=str):
        if not path.is_file():
            continue
        stat = path.stat()
        if path.suffix.lower() in metadata_suffixes:
            identity = (
                f"{path}|{int(stat.st_size)}|{int(stat.st_mtime_ns)}"
            ).encode("utf-8")
            digest_text = sha256(identity).hexdigest()
            hash_policy = "PATH_SIZE_MTIME_METADATA_SHA256"
        else:
            digest = sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest_text = digest.hexdigest()
            hash_policy = "CONTENT_SHA256"
        rows.append(
            {
                "path": str(path),
                "role": role_map.get(str(path), "input"),
                "size_bytes": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
                "sha256": digest_text,
                "hash_policy": hash_policy,
            }
        )
    return rows
