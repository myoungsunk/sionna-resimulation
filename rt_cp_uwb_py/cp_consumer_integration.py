"""Thread-3 contract and integration helpers for CP consumer validation.

The module is deliberately independent from evaluator metrics.  Runtime inputs,
evaluator truth, contracts, and terminal manifests remain separate artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EXPECTED_INTEGRATION_ARMS = (
    "CP_FULL_PRE",
    "CP_FULL_SHUFFLE",
    "FULL_MINUS_F",
    "DLP_FULL_PRE",
    "FULL_MINUS_A",
    "FULL_MINUS_M",
    "FULL_MINUS_T",
    "FULL_MINUS_C",
    "CIR_ONLY",
    "RANDOM_POLICY",
)

_TRUTH_TOKENS = (
    "truth",
    "ground_truth",
    "oracle",
    "label",
    "update_harm",
    "harm_truth",
    "harm_label",
    "unsafe_update",
    "range_error",
    "pose_gt",
    "reward",
    "outcome",
)

_SELECTION_BINDING = re.compile(r"\$\{selection\.([A-Za-z0-9_]+)\}")


class ContractError(RuntimeError):
    """Raised when a frozen execution contract cannot be honored."""


@dataclass(frozen=True)
class TableSchema:
    path: Path
    columns: tuple[str, ...]
    row_count: int
    sha256: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Mapping[str, Any] | Sequence[Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def unresolved_selection_bindings(value: Any) -> list[str]:
    """Return unique ``${selection.KEY}`` placeholders in a JSON-like value."""

    found: set[str] = set()

    def _walk(item: Any) -> None:
        if isinstance(item, str):
            found.update(_SELECTION_BINDING.findall(item))
        elif isinstance(item, Mapping):
            for key, nested in item.items():
                _walk(key)
                _walk(nested)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for nested in item:
                _walk(nested)

    _walk(value)
    return sorted(found)


def bind_selection_placeholders(value: Any, bindings: Mapping[str, Any]) -> Any:
    """Resolve selection placeholders without evaluating or opening outcomes.

    Missing keys fail closed.  Non-string binding values may replace a complete
    placeholder, while placeholders embedded in a larger string require scalar
    stringification.
    """

    if isinstance(value, str):
        complete = _SELECTION_BINDING.fullmatch(value)
        if complete:
            key = complete.group(1)
            if key not in bindings or bindings[key] in (None, ""):
                raise ContractError(f"selection binding is absent: {key}")
            return bindings[key]

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in bindings or bindings[key] in (None, ""):
                raise ContractError(f"selection binding is absent: {key}")
            return str(bindings[key])

        return _SELECTION_BINDING.sub(_replace, value)
    if isinstance(value, Mapping):
        return {str(key): bind_selection_placeholders(nested, bindings) for key, nested in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [bind_selection_placeholders(nested, bindings) for nested in value]
    return value


def load_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ContractError(f"required JSON artifact is missing: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractError(f"JSON artifact must contain an object: {source}")
    return payload


def atomic_write_json(path: str | Path, payload: Mapping[str, Any], *, replace: bool = False) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing artifact: {target}")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def atomic_write_csv(path: str | Path, rows: Iterable[Mapping[str, Any]], fieldnames: Sequence[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {target}")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def ensure_fresh_output_dir(path: str | Path) -> Path:
    output = Path(path)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    return output


def is_within(path: str | Path, root: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


def resolve_input_path(manifest_path: str | Path, value: str | Path, payload: Mapping[str, Any]) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    base_raw = payload.get("base_dir") or payload.get("project_root")
    base = Path(base_raw) if base_raw else Path(manifest_path).resolve().parent
    return (base / candidate).resolve()


def inspect_csv_schema(path: str | Path) -> TableSchema:
    source = Path(path)
    if not source.is_file():
        raise ContractError(f"table is missing: {source}")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = tuple(str(item).strip() for item in next(reader))
        except StopIteration:
            header = ()
        row_count = sum(1 for _ in reader)
    return TableSchema(source.resolve(), header, row_count, sha256_file(source))


def inspect_table_spec(
    input_manifest_path: str | Path,
    input_manifest: Mapping[str, Any],
    key: str,
    *,
    default_required: Sequence[str] = (),
) -> tuple[TableSchema | None, dict[str, Any]]:
    tables = input_manifest.get("tables")
    if not isinstance(tables, Mapping):
        return None, {"table": key, "status": "MISSING", "detail": "input manifest has no tables object"}
    raw = tables.get(key)
    if not isinstance(raw, Mapping) or not raw.get("path"):
        return None, {"table": key, "status": "MISSING", "detail": "table spec/path is absent"}
    path = resolve_input_path(input_manifest_path, str(raw["path"]), input_manifest)
    try:
        schema = inspect_csv_schema(path)
    except ContractError as exc:
        return None, {"table": key, "status": "MISSING", "detail": str(exc)}
    required = tuple(str(item) for item in (raw.get("required_columns") or default_required))
    missing = sorted(set(required) - set(schema.columns))
    status = "PASS" if not missing and schema.row_count > 0 else "FAIL"
    detail = "schema and non-empty row support present"
    if missing:
        detail = f"missing columns: {missing}"
    elif schema.row_count == 0:
        detail = "table contains no data rows"
    return schema, {
        "table": key,
        "path": str(schema.path),
        "row_count": schema.row_count,
        "column_count": len(schema.columns),
        "missing_columns": missing,
        "status": status,
        "detail": detail,
        "sha256": schema.sha256,
    }


def truth_like_columns(columns: Iterable[str]) -> list[str]:
    found: list[str] = []
    for column in columns:
        normalized = str(column).strip().lower()
        if any(token in normalized for token in _TRUTH_TOKENS):
            found.append(str(column))
    return sorted(set(found))


def audit_truth_separation(runtime_columns: Iterable[str], evaluator_columns: Iterable[str]) -> dict[str, Any]:
    runtime_truth = truth_like_columns(runtime_columns)
    evaluator_truth = truth_like_columns(evaluator_columns)
    return {
        "status": "PASS" if not runtime_truth and bool(evaluator_truth) else "FAIL",
        "runtime_truth_columns": runtime_truth,
        "evaluator_truth_columns": evaluator_truth,
        "detail": (
            "runtime namespace is truth-free and evaluator truth is external"
            if not runtime_truth and evaluator_truth
            else "runtime truth leakage or missing external evaluator truth"
        ),
    }


def validate_common_contract(
    contract_path: str | Path,
    run_root: str | Path,
    thread_id: str,
    *,
    expected_stage: str | None = None,
) -> tuple[dict[str, Any], str]:
    contract_file = Path(contract_path).resolve()
    contract = load_json_object(contract_file)
    root = Path(run_root).resolve()
    if not is_within(contract_file, root):
        raise ContractError(f"contract must be inside run root: {contract_file}")
    run_id = str(contract.get("run_id") or contract.get("RUN_ID") or "").strip()
    if run_id and run_id not in root.name:
        raise ContractError(f"run_id mismatch: contract={run_id}, run_root={root.name}")
    lanes = contract.get("lane_ids") or contract.get("lanes")
    if isinstance(lanes, Mapping):
        lanes = list(lanes)
    if isinstance(lanes, list) and thread_id not in {str(item) for item in lanes}:
        raise ContractError(f"thread_id is not authorized by contract: {thread_id}")
    if expected_stage:
        stage = str(contract.get("stage") or contract.get("contract_stage") or contract.get("freeze_stage") or "")
        if stage and expected_stage.lower() not in stage.lower():
            raise ContractError(f"contract stage mismatch: expected {expected_stage}, got {stage}")
    return contract, sha256_file(contract_file)


def require_release_artifact(path: str | Path, label: str) -> tuple[dict[str, Any], str]:
    artifact = Path(path)
    payload = load_json_object(artifact)
    status = str(payload.get("status") or payload.get("state") or "READY").upper()
    if "READY" not in status and "RELEASE" not in status and status not in {"PASS", "OK"}:
        raise ContractError(f"{label} is not ready: {status}")
    return payload, sha256_file(artifact)


def resolve_manifest_artifact(
    manifest_path: str | Path,
    manifest: Mapping[str, Any],
    value: str | Path,
) -> Path:
    """Resolve an artifact path using the same base rules as table specs."""

    return resolve_input_path(manifest_path, value, manifest)


def require_confirmation_release(
    contract_path: str | Path,
    contract: Mapping[str, Any],
    input_manifest_path: str | Path,
    input_manifest: Mapping[str, Any],
    run_root: str | Path,
) -> dict[str, str]:
    """Verify both confirmation release artifacts before any outcome read.

    Paths may be supplied by the frozen contract or by the phase input manifest,
    but the referenced artifacts must live under the common run root.
    """

    token_sources: list[tuple[Mapping[str, Any], str | Path, Mapping[str, Any]]] = []
    for payload, source_path in ((contract, contract_path), (input_manifest, input_manifest_path)):
        nested = payload.get("release_tokens")
        if isinstance(nested, Mapping):
            token_sources.append((nested, source_path, payload))
        token_sources.append((payload, source_path, payload))

    aliases = {
        "CONFIRMATION_RELEASE_TOKEN": (
            "CONFIRMATION_RELEASE_TOKEN",
            "confirmation_release_token",
            "confirmation_release_token_path",
        ),
        "REMOTE_CONFIRMATION_READY": (
            "REMOTE_CONFIRMATION_READY",
            "remote_confirmation_ready",
            "remote_confirmation_ready_path",
        ),
    }
    resolved: dict[str, str] = {}
    for label, keys in aliases.items():
        raw: Any = None
        owner_path: str | Path = contract_path
        owner_payload: Mapping[str, Any] = contract
        for payload, source_path, source_payload in token_sources:
            for key in keys:
                if payload.get(key):
                    raw = payload[key]
                    owner_path, owner_payload = source_path, source_payload
                    break
            if raw is not None:
                break
        if isinstance(raw, Mapping):
            raw = raw.get("path") or raw.get("artifact")
        if not raw:
            raise ContractError(f"{label} path is absent; confirmation remains sealed")
        token_path = resolve_manifest_artifact(owner_path, owner_payload, str(raw)).resolve()
        if not is_within(token_path, run_root):
            raise ContractError(f"{label} must be inside run root: {token_path}")
        _, token_hash = require_release_artifact(token_path, label)
        resolved[f"{label}_path"] = str(token_path)
        resolved[f"{label}_sha256"] = token_hash
    return resolved


def verify_declared_hash(path: str | Path, expected: str, label: str) -> str:
    actual = sha256_file(path)
    if expected and actual != expected:
        raise ContractError(f"{label} hash mismatch: expected={expected}, actual={actual}")
    return actual


def command_provenance(argv: Sequence[str] | None = None) -> list[str]:
    return list(argv if argv is not None else sys.argv)


def execute_command_attempt(
    command: Sequence[str],
    *,
    cwd: str | Path,
    stdout_path: str | Path,
    environment: Mapping[str, str] | None = None,
) -> int:
    log = Path(stdout_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if environment:
        merged_env.update({str(key): str(value) for key, value in environment.items()})
    with log.open("w", encoding="utf-8", newline="\n") as handle:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=merged_env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
    return int(completed.returncode)


def arm_delta_target(arm_id: str) -> str | None:
    prefix = "FULL_MINUS_"
    if arm_id.startswith(prefix):
        return arm_id[len(prefix) :]
    return None


def validate_arm_registry(registry: Mapping[str, Any], requested_arms: Sequence[str]) -> list[dict[str, Any]]:
    arms = registry.get("arms") if isinstance(registry.get("arms"), Mapping) else {}
    rows: list[dict[str, Any]] = []
    common_hashes = registry.get("common_hashes") if isinstance(registry.get("common_hashes"), Mapping) else {}
    required_hashes = {
        "global_contract_hash",
        "full_policy_hash",
        "backend_hash",
        "trajectory_hash",
        "initialization_hash",
        "seed_hash",
        "draw_manifest_hash",
        "member_order_hash",
        "conflict_resolution_hash",
        "model_calibrator_bundle_hash",
        "backend_budget_hash",
        "action_budget_hash",
        "environment_hash",
    }
    missing_common = sorted(required_hashes - set(common_hashes))
    for arm_id in requested_arms:
        spec = arms.get(arm_id) if isinstance(arms, Mapping) else None
        status = "PASS"
        detail = "arm registered"
        if arm_id not in EXPECTED_INTEGRATION_ARMS:
            status, detail = "FAIL", "unknown arm id"
        elif not isinstance(spec, Mapping):
            status, detail = "FAIL", "arm spec missing"
        elif missing_common:
            status, detail = "FAIL", f"missing common hashes: {missing_common}"
        elif arm_id.startswith("FULL_MINUS_") and str(spec.get("disable_only") or "") != arm_delta_target(arm_id):
            status, detail = "FAIL", "Full-minus arm does not disable exactly its named adapter"
        rows.append({"arm_id": arm_id, "status": status, "detail": detail})
    return rows


def run_attempts_parallel(
    attempts: Sequence[Mapping[str, Any]],
    *,
    max_workers: int,
) -> list[dict[str, Any]]:
    """Execute fully materialized command attempts without sharing mutable state."""

    def _one(spec: Mapping[str, Any]) -> dict[str, Any]:
        exit_code = execute_command_attempt(
            [str(item) for item in spec["command"]],
            cwd=Path(str(spec["cwd"])),
            stdout_path=Path(str(spec["stdout_path"])),
            environment=spec.get("environment") if isinstance(spec.get("environment"), Mapping) else None,
        )
        return {**dict(spec), "exit_code": exit_code}

    workers = max(1, min(int(max_workers), len(attempts) or 1))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_one, spec): spec for spec in attempts}
        for future in as_completed(future_map):
            results.append(future.result())
    return sorted(results, key=lambda item: (str(item.get("arm_id")), str(item.get("shard_id"))))
