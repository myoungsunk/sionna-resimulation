"""Strict fail-closed validation for CP complex-ensemble sources."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd


def validate_vmix_ensemble(frame: pd.DataFrame, contract: Mapping[str, Any]) -> dict[str, Any]:
    required = [str(name) for name in contract["required_columns"]]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        return {"pass": False, "status": "M_CONTRACT_FROZEN_DATA_BLOCKED", "missing_columns": missing, "errors": ["required ensemble schema is incomplete"]}
    work = frame.copy()
    errors: list[str] = []
    key = ["ensemble_id", "realization_id"]
    realizations = work[key + ["realization_type", "source_seed", "source_artifact_sha256", "signal_hash", "split_name", "split_group_id", "frequency_grid_id"]].drop_duplicates()
    if realizations.duplicated(key).any():
        errors.append("duplicate ensemble_id/realization_id")
    if realizations[["ensemble_id", "realization_id", "source_seed", "source_artifact_sha256", "signal_hash"]].isna().any().any():
        errors.append("missing realization provenance")
    if len(realizations) < int(contract["n_min_independent"]):
        errors.append("fewer than N_min_independent realizations")
    if realizations["source_seed"].duplicated().any():
        errors.append("same seed reuse")
    if realizations["source_artifact_sha256"].duplicated().any():
        errors.append("same complex artifact hash reused")
    if realizations["signal_hash"].duplicated().any():
        errors.append("near-duplicate signal hash")
    forbidden = {str(name).lower() for name in contract["forbidden_realization_types"]}
    allowed = {str(name).lower() for name in contract["allowed_realization_types"]}
    kinds = set(realizations["realization_type"].astype(str).str.lower())
    if kinds & forbidden or not kinds <= allowed:
        errors.append("forbidden or undocumented realization type")
    if work["frequency_grid_id"].nunique() != 1:
        errors.append("incompatible frequency grids")
    complex_columns = ["rr_real", "rr_imag", "rl_real", "rl_imag", "lr_real", "lr_imag", "ll_real", "ll_imag"]
    numeric = work[complex_columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        errors.append("non-finite full complex CP components")
    if work.groupby("split_group_id")["split_name"].nunique().gt(1).any():
        errors.append("train/validation/confirmation lineage overlap")
    return {"pass": not errors, "status": "M_DATA_GATE_PASS" if not errors else "M_CONTRACT_FROZEN_DATA_BLOCKED", "missing_columns": [], "errors": errors, "independent_realization_count": int(len(realizations)), "recommended_count_met": bool(len(realizations) >= int(contract["n_recommended_independent"]))}
