"""Action-support and control-tier primitives for the Thread-3 lane."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .cp_consumer_integration import audit_truth_separation, inspect_table_spec


def effective_sample_size(weights: Sequence[float]) -> float:
    values = np.asarray(weights, dtype=float)
    values = values[np.isfinite(values) & (values >= 0.0)]
    if values.size == 0 or float(values.sum()) <= 0.0:
        return 0.0
    return float(np.square(values.sum()) / np.square(values).sum())


def fixed_policy_action(
    candidates: pd.DataFrame,
    *,
    group_columns: Sequence[str],
    score_column: str,
    action_column: str = "action_id",
) -> pd.DataFrame:
    required = set(group_columns) | {score_column, action_column}
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise KeyError(f"control policy columns are missing: {missing}")
    ranked = candidates.copy()
    ranked[score_column] = pd.to_numeric(ranked[score_column], errors="coerce")
    if ranked[score_column].isna().any():
        raise ValueError("control policy score contains missing/non-numeric values")
    sort_columns = list(group_columns) + [score_column, action_column]
    ascending = [True] * len(group_columns) + [False, True]
    ranked = ranked.sort_values(sort_columns, ascending=ascending)
    selected = ranked.groupby(list(group_columns), dropna=False, as_index=False).head(1).copy()
    return selected.reset_index(drop=True)


def action_intervention_summary(
    selected: pd.DataFrame,
    *,
    selected_action_column: str = "action_id",
    baseline_action_column: str = "baseline_action_id",
) -> dict[str, Any]:
    missing = sorted({selected_action_column, baseline_action_column} - set(selected.columns))
    if missing:
        raise KeyError(f"action intervention columns are missing: {missing}")
    changed = selected[selected_action_column].astype(str) != selected[baseline_action_column].astype(str)
    return {
        "row_count": int(len(selected)),
        "changed_action_count": int(changed.sum()),
        "intervention_nonzero": bool(changed.any()),
    }


def classify_control_tier(structure: Mapping[str, Any]) -> tuple[str, str]:
    if bool(structure.get("closed_loop")) and bool(structure.get("post_action_observation")):
        return "C3", "ACTIVE_SENSING_CONTROL_UTILITY"
    if bool(structure.get("validated_simulator_or_counterfactual")) and bool(structure.get("post_action_observation")):
        return "C2", "COUNTERFACTUAL_CONTROL_UTILITY"
    if bool(structure.get("offline_ranking")):
        return "C1", "OFFLINE_ACTION_RANKING_UTILITY"
    return "C0", "ACTION_SUPPORT_READINESS_ONLY"


def audit_control_readiness(
    input_manifest_path: str | Path,
    input_manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime, runtime_row = inspect_table_spec(
        input_manifest_path,
        input_manifest,
        "action_runtime",
        default_required=("decision_id", "action_id", "baseline_action_id", "propensity"),
    )
    evaluator, evaluator_row = inspect_table_spec(
        input_manifest_path,
        input_manifest,
        "action_evaluator",
        default_required=("decision_id", "post_action_observation_id"),
    )
    support, support_row = inspect_table_spec(
        input_manifest_path,
        input_manifest,
        "action_support",
        default_required=("action_id", "support_count", "propensity"),
    )
    separation = audit_truth_separation(
        runtime.columns if runtime else (), evaluator.columns if evaluator else ()
    )
    structure = input_manifest.get("control_structure")
    structure = structure if isinstance(structure, Mapping) else {}
    tier, claim = classify_control_tier(structure)
    tier_gate = {
        "table": "control_primary_tier",
        "status": "PASS" if tier in {"C2", "C3"} else "FAIL",
        "detail": f"outcome-blind structural tier={tier}; claim={claim}",
    }
    rows = [runtime_row, evaluator_row, support_row, {"table": "truth_separation", **separation}, tier_gate]
    ready = all(row.get("status") == "PASS" for row in rows)
    blocker = "" if ready else _control_blocker(rows, tier)
    return rows, {
        "axis": "C",
        "status": "READY" if ready else "BLOCKED",
        "blocker_code": blocker,
        "control_evidence_tier": tier,
        "allowed_claim": claim,
        "runtime_table_hash": runtime.sha256 if runtime else "",
        "evaluator_table_hash": evaluator.sha256 if evaluator else "",
        "support_table_hash": support.sha256 if support else "",
    }


def _control_blocker(rows: Sequence[Mapping[str, Any]], tier: str) -> str:
    by_name = {str(row.get("table")): str(row.get("status")) for row in rows}
    separation = next((row for row in rows if str(row.get("table")) == "truth_separation"), {})
    if separation.get("runtime_truth_columns"):
        return "GLOBAL_INVALID_TRUTH_LEAKAGE"
    if by_name.get("action_support") != "PASS":
        return "LANE_BLOCKED_ACTION_SUPPORT"
    if tier not in {"C2", "C3"}:
        return "LANE_BLOCKED_COUNTERFACTUAL_IDENTIFICATION"
    return "LANE_BLOCKED_CONSUMER_INTERFACE_REQUIRED"
