"""Shared contracts for the 2026-07-29 predictability validation tracks.

This module intentionally contains no scientific outcome logic.  It provides
the common 12-column gate registry contract, deterministic seed identity,
three-axis component status validation, and provenance helpers used by v5,
R1, and S1.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


GATE_COLUMNS = (
    "gate_id",
    "component_id",
    "scope",
    "primary_or_diagnostic",
    "numerator_definition",
    "denominator_definition",
    "threshold",
    "comparison_operator",
    "missing_value_policy",
    "failure_code",
    "claim_effect",
    "config_key",
)

EXECUTION_STATES = {
    "NOT_EXECUTED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "INFRASTRUCTURE_FAIL",
}
HYPOTHESIS_STATES = {
    "NOT_EVALUATED",
    "SUPPORTED",
    "REFUTED",
    "MIXED",
    "NOT_ESTABLISHED",
}
ADOPTION_STATES = {
    "NOT_ADOPTED",
    "DIAGNOSTIC_ONLY",
    "INPUT_REUSE_RECOMPUTE",
    "ADOPTED",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def seed_identity(
    *,
    namespace: str,
    lane: str,
    arm: str,
    case_id: int | str,
    repeat_index: int,
) -> tuple[str, int]:
    material = f"20260729:{namespace}:{lane}:{arm}:{case_id}:{repeat_index}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    # NumPy accepts uint32 seeds consistently across the supported hosts.
    return digest, int(digest[:8], 16)


def realization_sha256(values: Any) -> str:
    """Hash a realized numeric payload without conflating it with its seed."""
    import numpy as np

    array = np.ascontiguousarray(np.asarray(values))
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.view("u1"))
    return digest.hexdigest()


def load_gate_registry(path: str | Path) -> pd.DataFrame:
    registry_path = Path(path)
    table = pd.read_csv(registry_path, dtype=str, keep_default_na=False)
    if tuple(table.columns) != GATE_COLUMNS:
        raise ValueError(
            "gate registry columns must exactly equal the 12-column contract; "
            f"got={list(table.columns)}"
        )
    if table.empty:
        raise ValueError("gate registry is empty")
    if table.gate_id.eq("").any() or table.gate_id.duplicated().any():
        raise ValueError("gate_id must be non-empty and unique")
    if table.failure_code.eq("").any() or table.config_key.eq("").any():
        raise ValueError("failure_code and config_key are required")
    allowed_ops = {"<", "<=", "==", ">=", ">"}
    invalid_ops = sorted(set(table.comparison_operator) - allowed_ops)
    if invalid_ops:
        raise ValueError(f"unsupported gate comparison operators: {invalid_ops}")
    return table


def gate_record(registry: pd.DataFrame, gate_id: str) -> dict[str, str]:
    selected = registry.loc[registry.gate_id.eq(str(gate_id))]
    if len(selected) != 1:
        raise KeyError(f"gate not found exactly once: {gate_id}")
    return {str(key): str(value) for key, value in selected.iloc[0].items()}


def gate_threshold(registry: pd.DataFrame, gate_id: str) -> float:
    record = gate_record(registry, gate_id)
    try:
        return float(record["threshold"])
    except ValueError as exc:
        raise ValueError(f"gate {gate_id} threshold is not numeric") from exc


def evaluate_gate(
    registry: pd.DataFrame,
    gate_id: str,
    value: float | int | bool | None,
) -> dict[str, Any]:
    record = gate_record(registry, gate_id)
    missing = value is None or (isinstance(value, float) and pd.isna(value))
    if missing:
        passed = record["missing_value_policy"] == "PASS"
    else:
        threshold = float(record["threshold"])
        numeric = float(value)
        op = record["comparison_operator"]
        passed = {
            "<": numeric < threshold,
            "<=": numeric <= threshold,
            "==": numeric == threshold,
            ">=": numeric >= threshold,
            ">": numeric > threshold,
        }[op]
    return {
        **record,
        "value": value,
        "pass": bool(passed),
        "failure": "" if passed else record["failure_code"],
    }


def validate_component_status(table: pd.DataFrame) -> None:
    required = {
        "component_id",
        "execution_status",
        "hypothesis_outcome",
        "adoption_status",
        "status_reason",
        "evidence_files",
    }
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"component status missing columns: {sorted(missing)}")
    bad_execution = sorted(set(table.execution_status) - EXECUTION_STATES)
    bad_hypothesis = sorted(set(table.hypothesis_outcome) - HYPOTHESIS_STATES)
    bad_adoption = sorted(set(table.adoption_status) - ADOPTION_STATES)
    if bad_execution or bad_hypothesis or bad_adoption:
        raise ValueError(
            "invalid three-axis state: "
            f"execution={bad_execution}, hypothesis={bad_hypothesis}, "
            f"adoption={bad_adoption}"
        )
    promoted_without_execution = table.adoption_status.eq("ADOPTED") & ~table.execution_status.eq(
        "COMPLETED"
    )
    if promoted_without_execution.any():
        raise ValueError("ADOPTED requires execution_status=COMPLETED")


def write_json(path: str | Path, value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def artifact_inventory(paths: Iterable[str | Path], root: str | Path) -> list[dict[str, Any]]:
    root_path = Path(root).resolve()
    rows: list[dict[str, Any]] = []
    for value in paths:
        path = Path(value).resolve()
        rows.append(
            {
                "path": path.relative_to(root_path).as_posix(),
                "bytes": int(path.stat().st_size),
                "sha256": sha256_file(path),
            }
        )
    return sorted(rows, key=lambda row: row["path"])


def runtime_provenance(command: list[str]) -> dict[str, Any]:
    return {
        "timestamp_utc": utc_now(),
        "command": command,
        "python": sys.version,
        "platform": platform.platform(),
    }
