"""Filesystem, schema, and readiness helpers for the CP-PH4 program.

This module is intentionally outcome-blind.  It validates inputs and records
the conditions under which later physics-head experiments may be launched.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results"
G0_PREFIX = "cp_four_axis_g0_"
PROTECTED_RELATIVE_ROOTS = (
    Path("data/raw"),
    Path("results/frozen"),
    Path("reports/release"),
    Path("_archive/pre_cleanup_snapshot"),
)


class CPPhysicsContractError(RuntimeError):
    """Raised for a frozen CP-PH4 contract violation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    resolved = resolve_project_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    value = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CPPhysicsContractError(f"config root must be a mapping: {resolved}")
    return value


def validate_config(config: Mapping[str, Any]) -> None:
    required_top = {
        "schema_version",
        "program_id",
        "seed",
        "claim_boundary",
        "inputs",
        "resource_contract",
        "partition_contract",
        "feature_dependency",
        "physics_heads",
        "modality_arms",
        "output_contract",
    }
    missing = sorted(required_top - set(config))
    if missing:
        raise CPPhysicsContractError(f"config missing top-level keys: {missing}")
    if config["schema_version"] != "cp_four_latent_physics_v1":
        raise CPPhysicsContractError(f"unexpected schema_version: {config['schema_version']!r}")
    if config["program_id"] != "CP-PH4":
        raise CPPhysicsContractError(f"unexpected program_id: {config['program_id']!r}")
    required_inputs = {"rt_path_long", "path_summary", "feature_table", "case_manifest", "cir_bank_manifest", "cir_bank"}
    absent_inputs = sorted(required_inputs - set(config["inputs"]))
    if absent_inputs:
        raise CPPhysicsContractError(f"config inputs missing: {absent_inputs}")
    heads = config["physics_heads"]
    if set(heads) != {"D", "C", "M", "A"}:
        raise CPPhysicsContractError("physics_heads must be exactly D, C, M, A")
    required_resource = {"tensor_order", "case_id_key", "frequency_key", "cp_tensor_key", "lp_tensor_key"}
    absent_resource = sorted(required_resource - set(config["resource_contract"]))
    if absent_resource:
        raise CPPhysicsContractError(f"resource_contract missing: {absent_resource}")
    if config["resource_contract"]["tensor_order"] != ["case", "rx", "tx", "freq"]:
        raise CPPhysicsContractError("resource_contract.tensor_order must be [case, rx, tx, freq]")
    if not config["feature_dependency"].get("learner_feature_columns"):
        raise CPPhysicsContractError("feature_dependency.learner_feature_columns cannot be empty")
    validate_coherent_specular_contract(config["physics_heads"]["C"])


def validate_coherent_specular_contract(spec: Mapping[str, Any]) -> None:
    """Validate the frozen, outcome-blind C-head path-mask contract."""

    contract = spec.get("contract")
    if not isinstance(contract, Mapping):
        raise CPPhysicsContractError("C head requires a pre-registered contract mapping")
    required = {
        "version",
        "scope",
        "direct_reference_rule",
        "specular_set_rule",
        "early_power_window_s",
        "prior_delay_window_s",
        "minimum_path_power_linear",
        "fixed_tx_state",
        "rx_jones_components",
        "formula",
        "prohibited_interpretations",
    }
    missing = sorted(required - set(contract))
    if missing:
        raise CPPhysicsContractError(f"C contract missing keys: {missing}")
    if contract["version"] != "C_V1":
        raise CPPhysicsContractError(f"unsupported C contract version: {contract['version']!r}")
    if contract["direct_reference_rule"] != "MIN_LOS_DELAY_PER_CASE":
        raise CPPhysicsContractError("C contract must use MIN_LOS_DELAY_PER_CASE")
    if contract["specular_set_rule"] != "NON_LOS_SINGLE_BOUNCE_SURFACE_NORMAL":
        raise CPPhysicsContractError("C contract must use NON_LOS_SINGLE_BOUNCE_SURFACE_NORMAL")
    early = float(contract["early_power_window_s"])
    prior = float(contract["prior_delay_window_s"])
    floor = float(contract["minimum_path_power_linear"])
    if not (0.0 < early <= prior):
        raise CPPhysicsContractError("C contract requires 0 < early_power_window_s <= prior_delay_window_s")
    if not floor > 0.0:
        raise CPPhysicsContractError("C contract minimum_path_power_linear must be positive")
    if contract["fixed_tx_state"] != "RHCP" or list(contract["rx_jones_components"]) != ["cp_rr", "cp_lr"]:
        raise CPPhysicsContractError("C contract must use the fixed-RHCP [cp_rr, cp_lr] receive Jones vector")


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(next(csv.reader(stream), []))


def required_columns_audit(headers: Iterable[str], required: Iterable[str]) -> dict[str, Any]:
    observed = set(headers)
    expected = list(required)
    missing = [column for column in expected if column not in observed]
    return {"required_columns": expected, "missing_columns": missing, "pass": not missing}


def feature_dependency_audit(learner_columns: Iterable[str], forbidden_columns: Iterable[str]) -> dict[str, Any]:
    learner = list(learner_columns)
    forbidden = set(forbidden_columns)
    overlap = sorted(set(learner) & forbidden)
    return {"learner_feature_columns": learner, "forbidden_overlap": overlap, "pass": not overlap}


def deterministic_fold(value: str, *, seed: int, fold_count: int) -> int:
    if fold_count < 2:
        raise CPPhysicsContractError("fold_count must be at least 2")
    digest = hashlib.sha256(f"{seed}:{value}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % fold_count


def ensure_g0_output_root(path: str | Path) -> Path:
    return ensure_timestamped_result_root(path, prefix=G0_PREFIX)


def ensure_timestamped_result_root(path: str | Path, *, prefix: str) -> Path:
    resolved = resolve_project_path(path)
    try:
        relative = resolved.relative_to(RESULTS_ROOT.resolve())
    except ValueError as exc:
        raise CPPhysicsContractError(f"G0 output root must be under results/: {resolved}") from exc
    if len(relative.parts) != 1 or not relative.name.startswith(prefix):
        raise CPPhysicsContractError(f"unexpected result root for {prefix!r}: {resolved}")
    for protected in PROTECTED_RELATIVE_ROOTS:
        protected_path = (PROJECT_ROOT / protected).resolve()
        if resolved == protected_path or protected_path in resolved.parents:
            raise CPPhysicsContractError(f"result output overlaps protected path: {resolved}")
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite existing result output root: {resolved}")
    return resolved


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_bytes(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n")


def atomic_write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[Mapping[str, Any]]) -> None:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(fieldnames), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    atomic_write_bytes(path, buffer.getvalue().encode("utf-8"))


def file_record(path: Path, *, include_header: bool = False) -> dict[str, Any]:
    exists = path.is_file()
    record: dict[str, Any] = {
        "path": project_relative(path),
        "exists": exists,
        "bytes": path.stat().st_size if exists else None,
        "sha256": sha256_file(path) if exists else None,
    }
    if include_header and exists and path.suffix.lower() == ".csv":
        record["columns"] = csv_header(path)
    return record
