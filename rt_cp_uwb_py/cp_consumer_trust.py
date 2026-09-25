"""Trust/admission primitives for the Thread-3 CP consumer lane."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .cp_consumer_integration import audit_truth_separation, inspect_table_spec


@dataclass(frozen=True)
class TrustPolicy:
    score_column: str
    threshold: float
    mode: str = "weight"
    minimum_weight: float = 0.05

    def __post_init__(self) -> None:
        if self.mode not in {"accept", "weight", "covariance"}:
            raise ValueError(f"unsupported trust intervention mode: {self.mode}")
        if not 0.0 <= self.minimum_weight <= 1.0:
            raise ValueError("minimum_weight must be in [0, 1]")


def apply_trust_policy(frame: pd.DataFrame, policy: TrustPolicy) -> pd.DataFrame:
    if policy.score_column not in frame:
        raise KeyError(f"score column is missing: {policy.score_column}")
    score = pd.to_numeric(frame[policy.score_column], errors="coerce")
    if score.isna().any():
        raise ValueError("trust score contains missing or non-numeric values")
    result = frame.copy()
    accepted = score >= float(policy.threshold)
    result["trust_accept"] = accepted
    if policy.mode == "accept":
        result["trust_weight"] = accepted.astype(float)
        result["trust_covariance_scale"] = np.where(accepted, 1.0, np.inf)
    else:
        normalized = np.clip(score.to_numpy(dtype=float), policy.minimum_weight, 1.0)
        result["trust_weight"] = normalized
        result["trust_covariance_scale"] = 1.0 / np.square(normalized)
    return result


def intervention_summary(frame: pd.DataFrame) -> dict[str, Any]:
    required = {"trust_accept", "trust_weight", "trust_covariance_scale"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"trust intervention columns are missing: {missing}")
    accepted = frame["trust_accept"].astype(bool)
    weights = pd.to_numeric(frame["trust_weight"], errors="coerce")
    covariance = pd.to_numeric(frame["trust_covariance_scale"], errors="coerce")
    changed = (~accepted) | (~np.isclose(weights, 1.0)) | (~np.isclose(covariance, 1.0))
    return {
        "row_count": int(len(frame)),
        "accepted_count": int(accepted.sum()),
        "rejected_count": int((~accepted).sum()),
        "changed_object_count": int(changed.sum()),
        "intervention_nonzero": bool(changed.any()),
    }


def audit_trust_readiness(
    input_manifest_path: str | Path,
    input_manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runtime, runtime_row = inspect_table_spec(
        input_manifest_path,
        input_manifest,
        "trust_runtime",
        default_required=("case_id", "split", "q_clean"),
    )
    evaluator, evaluator_row = inspect_table_spec(
        input_manifest_path,
        input_manifest,
        "trust_evaluator",
        default_required=("case_id", "split", "update_harm"),
    )
    backend, backend_row = inspect_table_spec(
        input_manifest_path,
        input_manifest,
        "backend_intervention",
        default_required=("case_id", "split"),
    )
    matched, matched_row = inspect_table_spec(
        input_manifest_path,
        input_manifest,
        "matched_resource",
        default_required=("case_id", "split", "sensor_family"),
    )

    separation = audit_truth_separation(
        runtime.columns if runtime else (), evaluator.columns if evaluator else ()
    )
    backend_columns = set(backend.columns if backend else ())
    intervention_candidates = {
        "accept",
        "accepted",
        "trust_accept",
        "weight",
        "factor_weight",
        "measurement_weight",
        "covariance_scale",
        "range_var_est_m2",
        "factor_inserted",
        "accepted_update",
        "effective_weight",
        "used_variance_m2",
        "range_variance_scale",
    }
    available_interventions = sorted(intervention_candidates & backend_columns)
    intervention_gate = {
        "table": "backend_intervention_path",
        "status": "PASS" if available_interventions else "FAIL",
        "detail": (
            f"backend intervention columns available: {available_interventions}"
            if available_interventions
            else "no accept/weight/R/factor intervention column is available"
        ),
    }
    comparator = input_manifest.get("matched_comparator")
    comparator = comparator if isinstance(comparator, Mapping) else {}
    comparator_checks = {
        "cp_score_available": bool(comparator.get("cp_score_available")),
        "dlp_score_available": bool(comparator.get("dlp_score_available")),
        "same_case_and_split": bool(comparator.get("same_case_and_split")),
        "same_aperture": bool(comparator.get("same_aperture")),
        "same_rf_chain_budget": bool(comparator.get("same_rf_chain_budget")),
        "fixed_one_tx_equivalent": bool(comparator.get("fixed_one_tx_equivalent")),
    }
    comparator_gate = {
        "table": "matched_cp_dlp_comparator",
        "status": "PASS" if all(comparator_checks.values()) else "FAIL",
        "detail": f"outcome-blind comparator checks: {comparator_checks}",
    }
    endpoint = input_manifest.get("trust_endpoint")
    endpoint = endpoint if isinstance(endpoint, Mapping) else {}
    endpoint_gate = {
        "table": "external_harm_endpoint_contract",
        "status": "PASS" if bool(endpoint.get("external_to_qclean")) and bool(endpoint.get("uncertainty_available")) else "FAIL",
        "detail": (
            "external endpoint is separated from q_clean and carries uncertainty"
            if bool(endpoint.get("external_to_qclean")) and bool(endpoint.get("uncertainty_available"))
            else "external harm endpoint/uncertainty contract is not established"
        ),
    }
    rows = [
        runtime_row,
        evaluator_row,
        backend_row,
        matched_row,
        {"table": "truth_separation", **separation},
        intervention_gate,
        comparator_gate,
        endpoint_gate,
    ]
    status = "READY" if all(row.get("status") == "PASS" for row in rows) else "BLOCKED"
    blocker = "" if status == "READY" else _trust_blocker(rows)
    return rows, {
        "axis": "T",
        "status": status,
        "blocker_code": blocker,
        "changed_object_candidates": available_interventions,
        "runtime_table_hash": runtime.sha256 if runtime else "",
        "evaluator_table_hash": evaluator.sha256 if evaluator else "",
        "matched_table_hash": matched.sha256 if matched else "",
        "matched_comparator_checks": comparator_checks,
    }


def _trust_blocker(rows: Sequence[Mapping[str, Any]]) -> str:
    by_name = {str(row.get("table")): str(row.get("status")) for row in rows}
    if by_name.get("trust_evaluator") != "PASS":
        return "LANE_BLOCKED_T_LABEL_REQUIRED"
    if by_name.get("truth_separation") != "PASS":
        return "GLOBAL_INVALID_TRUTH_LEAKAGE"
    if by_name.get("backend_intervention_path") != "PASS":
        return "LANE_BLOCKED_CONSUMER_INTERFACE_REQUIRED"
    if by_name.get("matched_cp_dlp_comparator") != "PASS":
        return "LANE_BLOCKED_MATCHED_DLP_COMPARATOR_REQUIRED"
    if by_name.get("external_harm_endpoint_contract") != "PASS":
        return "LANE_BLOCKED_T_LABEL_REQUIRED"
    return "LANE_BLOCKED_T_INPUT_REQUIRED"
