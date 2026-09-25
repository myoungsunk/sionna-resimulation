"""Shared, lane-local utilities for the CP consumer Thread 2 runners.

This module deliberately has no dependency on the shared Thread 1 contract
implementation.  It validates the published JSON surface, keeps runtime and
evaluator namespaces separate, and writes every leaf through an atomic output
directory.  Thread 2 runners must never append to legacy result files.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pandas as pd


THREAD_ID = "thread_2"
SCHEMA_VERSION = "cp_consumer_thread2_common_20260713.v2"

# These names are forbidden in solver/runtime tables.  Evaluator sidecars may
# contain them, but their paths must not be passed to the lifecycle backend.
FORBIDDEN_RUNTIME_TOKENS = (
    "truth",
    "oracle",
    "ground_truth",
    "target_label",
    "correct_flag",
    "da_correct",
)


class ContractError(RuntimeError):
    """Raised when a shared launch/freeze contract is absent or inconsistent."""


class SchemaError(ValueError):
    """Raised when a lane input violates a frozen schema."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SchemaError(f"JSON object required: {path}")
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish one JSON artifact without exposing a partially written file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(dict(payload), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_csv_atomic(path: Path, frame: pd.DataFrame) -> None:
    """Publish one CSV artifact without exposing a partially written file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    tmp = Path(raw_tmp)
    try:
        frame.to_csv(tmp, index=False, lineterminator="\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_table(path: Path, *, nrows: int | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, nrows=nrows)
    if suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
        return frame.head(nrows) if nrows is not None else frame
    if suffix in {".jsonl", ".ndjson"}:
        frame = pd.read_json(path, lines=True)
        return frame.head(nrows) if nrows is not None else frame
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            frame = pd.DataFrame(value)
        elif isinstance(value, dict) and isinstance(value.get("rows"), list):
            frame = pd.DataFrame(value["rows"])
        else:
            raise SchemaError(f"tabular JSON must be a list or contain rows: {path}")
        return frame.head(nrows) if nrows is not None else frame
    raise SchemaError(f"unsupported table format: {path}")


def table_columns(path: Path) -> list[str]:
    """Return a schema-only view without reading efficacy values."""

    return [str(column) for column in read_table(path, nrows=0).columns]


def forbidden_runtime_columns(columns: Sequence[str]) -> list[str]:
    bad: list[str] = []
    for column in columns:
        lowered = str(column).lower()
        if any(token in lowered for token in FORBIDDEN_RUNTIME_TOKENS):
            bad.append(str(column))
    return sorted(set(bad))


def require_no_runtime_truth(frame: pd.DataFrame, *, table_name: str) -> None:
    bad = forbidden_runtime_columns([str(column) for column in frame.columns])
    if bad:
        raise SchemaError(f"runtime truth leakage in {table_name}: {bad}")


def resolve_manifest_path(raw: str | os.PathLike[str], *, manifest_path: Path, repo_root: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    candidate = (manifest_path.parent / path).resolve()
    if candidate.exists():
        return candidate
    return (repo_root / path).resolve()


def relative_to_or_absolute(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def ensure_output_is_lane_owned(out_dir: Path, run_root: Path, *, thread_id: str) -> None:
    if thread_id != THREAD_ID:
        raise ContractError(f"Thread 2 runner requires --thread-id {THREAD_ID!r}")
    resolved_out = out_dir.resolve()
    resolved_root = run_root.resolve()
    try:
        rel = resolved_out.relative_to(resolved_root)
    except ValueError as exc:
        raise ContractError(f"output must stay under run root: {resolved_out}") from exc
    text = rel.as_posix().lower()
    allowed = (
        "00_preflight/thread_2",
        "20_selection/thread_2",
        "40_confirmation/thread_2_assoc_lifecycle",
        "80_measurement/thread_2_m1",
    )
    if not any(text == prefix or text.startswith(prefix + "/") for prefix in allowed):
        raise ContractError(f"output is not owned by Thread 2: {rel.as_posix()}")


def ensure_recovery_output_is_lane_owned(out_dir: Path, recovery_root: Path) -> None:
    """Restrict recovery writes to ``20_thread_r2``.

    Recovery work happens before a scientific RUN exists, so it cannot use the
    normal run-root directory contract above.  This narrower check prevents a
    Thread 2 builder from modifying the shared ``10_contract`` directory or a
    sibling lane.
    """

    resolved_out = out_dir.resolve()
    resolved_root = recovery_root.resolve()
    try:
        rel = resolved_out.relative_to(resolved_root).as_posix().lower()
    except ValueError as exc:
        raise ContractError(f"recovery output must stay under recovery root: {resolved_out}") from exc
    if rel != "20_thread_r2" and not rel.startswith("20_thread_r2/"):
        raise ContractError(f"recovery output is not owned by Thread 2: {rel}")


@contextlib.contextmanager
def atomic_output_directory(out_dir: Path, run_root: Path, *, thread_id: str) -> Iterator[Path]:
    """Create a private partial directory and publish it with one rename."""

    ensure_output_is_lane_owned(out_dir, run_root, thread_id=thread_id)
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {out_dir}")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.partial.", dir=out_dir.parent))
    try:
        yield partial
        os.replace(partial, out_dir)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise


def validate_contract(
    contract_path: Path,
    *,
    expected_thread_id: str = THREAD_ID,
    required_phase: str = "p0",
) -> tuple[dict[str, Any], str]:
    if not contract_path.exists():
        raise ContractError(f"contract manifest missing: {contract_path}")
    contract = load_json(contract_path)
    contract_thread = str(contract.get("thread_id") or contract.get("lane_id") or "")
    allowed_threads = contract.get("allowed_thread_ids") or contract.get("lane_ids") or contract.get("lanes") or []
    if contract_thread and contract_thread not in {"coordinator", "thread_1", expected_thread_id}:
        raise ContractError(f"contract thread mismatch: {contract_thread}")
    if isinstance(allowed_threads, list) and allowed_threads and expected_thread_id not in {
        str(item.get("thread_id") if isinstance(item, dict) else item) for item in allowed_threads
    }:
        raise ContractError(f"{expected_thread_id} is not authorized by contract")

    flattened = canonical_json(contract).lower()
    phase = required_phase.lower()
    if phase == "freeze-a" and not any(token in flattened for token in ("freeze-a", "freeze_a", "semantic_contract")):
        raise ContractError("Freeze-A marker/hash missing from contract")
    if phase == "freeze-b":
        has_freeze = any(token in flattened for token in ("freeze-b", "freeze_b", "global_executable"))
        release_values = [
            contract.get("confirmation_release"),
            contract.get("confirmation_release_token"),
            contract.get("remote_confirmation_ready"),
            contract.get("release_token"),
        ]
        has_release = any(
            value is True
            or (
                isinstance(value, str)
                and value.strip().lower() not in {"", "false", "0", "none", "null", "blocked", "not_released"}
            )
            for value in release_values
        )
        if not (has_freeze and has_release):
            raise ContractError("Freeze-B confirmation release token missing")
    return contract, sha256_file(contract_path)


def output_checksums(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def dataframe_hash(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256_bytes(payload)


def require_columns(frame: pd.DataFrame, required: Sequence[str], *, table_name: str) -> None:
    missing = sorted(set(required) - set(str(column) for column in frame.columns))
    if missing:
        raise SchemaError(f"missing columns in {table_name}: {missing}")
