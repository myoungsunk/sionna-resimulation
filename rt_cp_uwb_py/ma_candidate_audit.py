"""Pure candidate-admissibility checks for the M and A gate inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping


def missing_columns(headers: Iterable[str], required: Iterable[str]) -> list[str]:
    available = {str(name) for name in headers}
    return [str(name) for name in required if str(name) not in available]


def audit_m_headers(spec: Mapping[str, Any], headers: Iterable[str]) -> dict[str, Any]:
    """Classify a prospective V-MIX source without computing a mixing metric."""

    missing_complex = missing_columns(headers, spec["required_complex_columns"])
    missing_identity = missing_columns(headers, spec["required_identity_columns"])
    temporal_present = any(str(name) in set(headers) for name in spec["required_temporal_or_diffuse_columns"])
    static_scope = str(spec.get("declared_scope", "")).startswith("static_")
    reasons: list[str] = []
    if static_scope:
        reasons.append("declared_static_scope")
    if missing_complex:
        reasons.append("missing_complex=" + ",".join(missing_complex))
    if missing_identity:
        reasons.append("missing_identity=" + ",".join(missing_identity))
    if not temporal_present:
        reasons.append("missing_temporal_or_diffuse_identity")

    if static_scope:
        disposition = "CONTROL_ONLY"
    elif missing_complex or missing_identity or not temporal_present:
        disposition = "REJECTED"
    else:
        disposition = "ADMISSIBLE"
    return {
        "candidate_id": str(spec["candidate_id"]),
        "declared_scope": str(spec.get("declared_scope", "")),
        "complex_columns_complete": not missing_complex,
        "identity_columns_complete": not missing_identity,
        "temporal_or_diffuse_identity_present": temporal_present,
        "disposition": disposition,
        "reason": ";".join(reasons) if reasons else "all_requirements_present",
    }


def audit_a_headers(
    spec: Mapping[str, Any],
    *,
    trajectory_headers: Iterable[str],
    association_headers: Iterable[str],
    path_truth_headers: Iterable[str],
    feature_headers: Iterable[str],
    mapping_exists: bool,
) -> dict[str, Any]:
    """Classify a prospective V-AVAIL source without creating a label."""

    missing_sequence = missing_columns(trajectory_headers, spec["required_sequence_columns"])
    missing_association = missing_columns(association_headers, spec["required_association_columns"])
    missing_path_truth = missing_columns(path_truth_headers, spec["required_path_truth_columns"])
    missing_outcome = missing_columns(association_headers, spec["required_availability_outcome_columns"])
    join_spec = spec["qclean_join"]
    candidate_join_present = str(join_spec["candidate_column"]) in set(association_headers)
    feature_join_present = str(join_spec["feature_table_column"]) in set(feature_headers)
    shuffled_control = bool(spec.get("is_shuffled_control", False))
    reasons: list[str] = []
    if shuffled_control:
        reasons.append("declared_shuffled_control")
    if missing_sequence:
        reasons.append("missing_sequence=" + ",".join(missing_sequence))
    if missing_association:
        reasons.append("missing_association=" + ",".join(missing_association))
    if missing_path_truth:
        reasons.append("missing_path_truth=" + ",".join(missing_path_truth))
    if missing_outcome:
        reasons.append("missing_availability_outcome=" + ",".join(missing_outcome))
    if not candidate_join_present or not feature_join_present or not mapping_exists:
        reasons.append("missing_qclean_join_mapping")

    incomplete = bool(missing_sequence or missing_association or missing_path_truth or missing_outcome)
    join_complete = candidate_join_present and feature_join_present and mapping_exists
    if shuffled_control:
        disposition = "CONTROL_ONLY"
    elif incomplete or not join_complete:
        disposition = "REJECTED"
    else:
        disposition = "ADMISSIBLE"
    return {
        "candidate_id": str(spec["candidate_id"]),
        "source_role": str(spec.get("source_role", "")),
        "sequence_columns_complete": not missing_sequence,
        "association_columns_complete": not missing_association,
        "path_truth_columns_complete": not missing_path_truth,
        "availability_outcome_complete": not missing_outcome,
        "qclean_join_mapping_complete": join_complete,
        "is_shuffled_control": shuffled_control,
        "disposition": disposition,
        "reason": ";".join(reasons) if reasons else "all_requirements_present",
    }


def gate_terminal(m_rows: Iterable[Mapping[str, Any]], a_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a fail-closed terminal based only on candidate admissibility."""

    m_open = any(str(row.get("disposition")) == "ADMISSIBLE" for row in m_rows)
    a_open = any(str(row.get("disposition")) == "ADMISSIBLE" for row in a_rows)
    return {
        "audit_status": "COMPLETE",
        "M": {
            "launch_status": "READY_FOR_V_MIX_INPUT_CONTRACT" if m_open else "BLOCKED_COMPLEX_ENSEMBLE",
            "admissible_candidate_present": m_open,
        },
        "A": {
            "launch_status": "READY_FOR_V_AVAIL_INPUT_CONTRACT" if a_open else "BLOCKED_SEQUENCE_TRUTH",
            "admissible_candidate_present": a_open,
        },
        "next_allowed": [
            *( ["FREEZE_M_ENSEMBLE_CONTRACT"] if m_open else ["ACQUIRE_OR_MATERIALIZE_INDEPENDENT_COMPLEX_ENSEMBLE"] ),
            *( ["FREEZE_A_SEQUENCE_TRUTH_CONTRACT"] if a_open else ["ACQUIRE_OR_MATERIALIZE_UNSHUFFLED_SEQUENCE_AND_EXTERNAL_TRUTH"] ),
        ],
        "scope": "INPUT_ADMISSIBILITY_AUDIT_ONLY",
    }


def csv_headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        line = handle.readline().rstrip("\r\n")
    return line.split(",") if line else []
