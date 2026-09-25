"""Outcome-blind C_V1 synthetic RT specular-proxy labels."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


REQUIRED_PATH_COLUMNS = {
    "case_id", "path_id", "is_los", "bounce_count", "path_delay_s", "power", "surface_ids", "material_interaction",
    "first_normal_x", "first_normal_y", "first_normal_z", "launch_dir_x", "launch_dir_y", "launch_dir_z",
    "arrival_dir_x", "arrival_dir_y", "arrival_dir_z",
}
WINDOW_EPS_NS = 1e-9


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _vector(row: Mapping[str, Any], names: tuple[str, str, str]) -> np.ndarray | None:
    values = np.asarray([pd.to_numeric(row[name], errors="coerce") for name in names], dtype=float)
    norm = float(np.linalg.norm(values))
    if not np.all(np.isfinite(values)) or not np.isfinite(norm) or norm <= 0.0:
        return None
    return values / norm


def reflection_residual_deg(u_in: np.ndarray, normal: np.ndarray, u_out: np.ndarray) -> float:
    """Return the frozen reflection-law residual in degrees."""

    u_pred = u_in - 2.0 * float(np.dot(u_in, normal)) * normal
    dot = float(np.clip(np.dot(u_pred, u_out), -1.0, 1.0))
    return float(np.degrees(np.arccos(dot)))


def _single_surface(value: Any) -> bool:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return False
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            return isinstance(parsed, list) and len(parsed) == 1 and bool(str(parsed[0]).strip())
        except json.JSONDecodeError:
            return False
    tokens = [token.strip() for token in text.replace(";", ",").replace("|", ",").split(",") if token.strip()]
    return len(tokens) == 1


def _candidate(row: Mapping[str, Any], *, los_delay_s: float, los_power: float, tolerance_deg: float, materials: set[str]) -> tuple[dict[str, Any] | None, str]:
    if _is_true(row["is_los"]):
        return None, "LOS_PATH"
    bounce = pd.to_numeric(row["bounce_count"], errors="coerce")
    if not np.isfinite(bounce) or int(bounce) != 1:
        return None, "NOT_SINGLE_BOUNCE"
    if not _single_surface(row["surface_ids"]):
        return None, "NOT_EXACTLY_ONE_SURFACE"
    if str(row["material_interaction"]).strip().lower() not in materials:
        return None, "NON_SPECULAR_INTERACTION"
    normal = _vector(row, ("first_normal_x", "first_normal_y", "first_normal_z"))
    if normal is None:
        return None, "INVALID_NORMAL"
    u_in = _vector(row, ("launch_dir_x", "launch_dir_y", "launch_dir_z"))
    u_out = _vector(row, ("arrival_dir_x", "arrival_dir_y", "arrival_dir_z"))
    if u_in is None or u_out is None:
        return None, "INVALID_GEOMETRY"
    delay = float(pd.to_numeric(row["path_delay_s"], errors="coerce"))
    power = float(pd.to_numeric(row["power"], errors="coerce"))
    if not np.isfinite(delay) or delay <= los_delay_s:
        return None, "NONPOSITIVE_DELAY_OFFSET"
    if not np.isfinite(power) or power <= 0.0:
        return None, "INVALID_POWER"
    theta = reflection_residual_deg(u_in, normal, u_out)
    if theta > tolerance_deg:
        return None, "REFLECTION_RESIDUAL_EXCEEDS_TOLERANCE"
    relative_power_db = float(10.0 * np.log10(power / los_power)) if los_power > 0.0 else np.nan
    return {
        "path_id": str(row["path_id"]),
        "theta_spec_deg": theta,
        "delta_tau_ns": (delay - los_delay_s) * 1e9,
        "power": power,
        "relative_power_db": relative_power_db,
    }, "CANDIDATE"


def build_c_v1_labels(path_rows: pd.DataFrame, *, tolerance_deg: float, specular_capable_materials: Iterable[str], prior_upper_ns: float = 50.0, early_upper_ns: float = 5.0) -> pd.DataFrame:
    """Build one C_V1 label row per case using path metadata only.

    This module intentionally receives no tensor, feature, prediction, or q_clean
    input.  No-LoS cases are inapplicable rather than primary-analysis negatives.
    """

    missing = sorted(REQUIRED_PATH_COLUMNS - set(path_rows.columns))
    if missing:
        raise ValueError(f"C_V1 path input missing columns: {missing}")
    if not (0.0 < early_upper_ns < prior_upper_ns):
        raise ValueError("C_V1 delay windows must satisfy 0 < early < prior")
    materials = {str(item).strip().lower() for item in specular_capable_materials}
    records: list[dict[str, Any]] = []
    for case_id, group in path_rows.groupby("case_id", sort=True):
        work = group.copy()
        work["path_delay_s"] = pd.to_numeric(work["path_delay_s"], errors="coerce")
        work["power"] = pd.to_numeric(work["power"], errors="coerce")
        los = work.loc[work["is_los"].map(_is_true) & np.isfinite(work["path_delay_s"]) & np.isfinite(work["power"])]
        if los.empty:
            records.append({"case_id": int(case_id), "c_v1_applicable": False, "c_v1_any_50ns": np.nan, "c_v1_early": np.nan, "c_v1_prior": np.nan, "c_v1_candidate_count": 0, "c_v1_best_path_id": "", "c_v1_best_theta_residual_deg": np.nan, "c_v1_best_delta_tau_ns": np.nan, "c_v1_best_relative_power_db": np.nan, "c_v1_exclusion_reason": "NOT_APPLICABLE_NO_LOS"})
            continue
        los_row = los.assign(_path_id=los["path_id"].astype(str)).sort_values(["path_delay_s", "_path_id"], kind="mergesort").iloc[0]
        candidates: list[dict[str, Any]] = []
        for _, row in work.iterrows():
            candidate, _ = _candidate(row, los_delay_s=float(los_row["path_delay_s"]), los_power=float(los_row["power"]), tolerance_deg=tolerance_deg, materials=materials)
            if candidate is not None and candidate["delta_tau_ns"] <= prior_upper_ns + WINDOW_EPS_NS:
                candidates.append(candidate)
        candidates.sort(key=lambda item: (item["theta_spec_deg"], item["delta_tau_ns"], -item["power"], item["path_id"]))
        best = candidates[0] if candidates else None
        early = bool(any(0.0 < item["delta_tau_ns"] <= early_upper_ns + WINDOW_EPS_NS for item in candidates))
        prior = bool(any(early_upper_ns + WINDOW_EPS_NS < item["delta_tau_ns"] <= prior_upper_ns + WINDOW_EPS_NS for item in candidates))
        records.append({
            "case_id": int(case_id), "c_v1_applicable": True, "c_v1_any_50ns": bool(candidates), "c_v1_early": early, "c_v1_prior": prior,
            "c_v1_candidate_count": int(len(candidates)), "c_v1_best_path_id": best["path_id"] if best else "",
            "c_v1_best_theta_residual_deg": best["theta_spec_deg"] if best else np.nan,
            "c_v1_best_delta_tau_ns": best["delta_tau_ns"] if best else np.nan,
            "c_v1_best_relative_power_db": best["relative_power_db"] if best else np.nan,
            "c_v1_exclusion_reason": "VALID_POSITIVE" if prior else "VALID_NEGATIVE_NO_PRIOR_CANDIDATE",
        })
    return pd.DataFrame(records).sort_values("case_id", kind="mergesort").reset_index(drop=True)
