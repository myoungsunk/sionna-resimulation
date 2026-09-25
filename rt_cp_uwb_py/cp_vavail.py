"""Strict fail-closed validation for independent availability truth."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


def validate_vavail_sequence(frame: pd.DataFrame, contract: Mapping[str, Any]) -> dict[str, Any]:
    required = [str(name) for name in contract["required_columns"]]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        return {"pass": False, "status": "A_CONTRACT_FROZEN_DATA_BLOCKED", "missing_columns": missing, "errors": ["required sequence-truth schema is incomplete"]}
    work = frame.copy()
    errors: list[str] = []
    forbidden = {str(item).lower() for item in contract["forbidden_truth_sources"]}
    if work["availability_truth_source"].astype(str).str.lower().str.contains("|".join(forbidden), regex=True).any():
        errors.append("availability truth is q-clean/proposal/shuffle derived")
    if work[["availability_truth", "q_clean_join_key", "external_track_id", "association_truth"]].isna().any().any():
        errors.append("missing independent truth or stable join")
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
    work["feature_cutoff_timestamp"] = pd.to_datetime(work["feature_cutoff_timestamp"], errors="coerce", utc=True)
    work["outcome_window_start"] = pd.to_datetime(work["outcome_window_start"], errors="coerce", utc=True)
    work["outcome_window_end"] = pd.to_datetime(work["outcome_window_end"], errors="coerce", utc=True)
    if work[["timestamp", "feature_cutoff_timestamp", "outcome_window_start", "outcome_window_end"]].isna().any().any():
        errors.append("invalid temporal fields")
    if work.duplicated(["sequence_id", "frame_id"]).any() or work.duplicated(["sequence_id", "timestamp"]).any():
        errors.append("non-unique frame/time")
    if any(not group["timestamp"].is_monotonic_increasing for _, group in work.sort_values("timestamp").groupby("sequence_id", sort=False)):
        errors.append("non-monotonic sequence time")
    if (work["feature_cutoff_timestamp"] > work["timestamp"]).any() or (work["outcome_window_start"] < work["timestamp"]).any() or (work["outcome_window_end"] < work["outcome_window_start"]).any():
        errors.append("future leakage or invalid outcome window")
    if work.groupby("sequence_id")["split_name"].nunique().gt(1).any():
        errors.append("sequence-level split overlap")
    if work.groupby("external_track_id")["split_name"].nunique().gt(1).any():
        errors.append("external-track leakage across splits")
    if work.duplicated(["measurement_id", "candidate_path_id"]).any():
        errors.append("ambiguous measurement/path join")
    return {"pass": not errors, "status": "A_DATA_GATE_PASS" if not errors else "A_CONTRACT_FROZEN_DATA_BLOCKED", "missing_columns": [], "errors": errors, "sequence_count": int(work["sequence_id"].nunique())}
