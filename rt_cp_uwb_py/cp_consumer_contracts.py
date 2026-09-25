"""Shared, outcome-blind contracts for the CP consumer parallel run.

This module owns filesystem safety, canonical hashes, atomic publication, and
deadline/terminal validation.  It deliberately contains no efficacy metric.
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
RUN_ROOT_PREFIX = "cp_consumer_parallel_"
RECOVERY_ROOT_PREFIX = "cp_consumer_recovery_"
PROTECTED_RELATIVE_ROOTS = (
    Path("data/raw"),
    Path("results/frozen"),
    Path("reports/release"),
    Path("_archive/pre_cleanup_snapshot"),
)


class ContractError(RuntimeError):
    """Raised when a frozen execution or filesystem contract is violated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError(f"UTC timestamp must include timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


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


def ensure_run_root(path: str | Path) -> Path:
    resolved = resolve_project_path(path)
    try:
        relative = resolved.relative_to(RESULTS_ROOT.resolve())
    except ValueError as exc:
        raise ContractError(f"run root must be under {RESULTS_ROOT}: {resolved}") from exc
    if len(relative.parts) != 1 or not relative.name.startswith(RUN_ROOT_PREFIX):
        raise ContractError(f"unexpected run-root shape or prefix: {resolved}")
    for protected in PROTECTED_RELATIVE_ROOTS:
        protected_path = (PROJECT_ROOT / protected).resolve()
        if resolved == protected_path or protected_path in resolved.parents:
            raise ContractError(f"run root overlaps protected path: {resolved}")
    return resolved


def ensure_recovery_root(path: str | Path) -> Path:
    """Return a safe, single-level recovery root below ``results``.

    Recovery artifacts are deliberately separated from scientific run roots.
    The function rejects existing run names and every protected repository
    surface; callers still own no-overwrite publication of individual files.
    """

    resolved = resolve_project_path(path)
    try:
        relative = resolved.relative_to(RESULTS_ROOT.resolve())
    except ValueError as exc:
        raise ContractError(f"recovery root must be under {RESULTS_ROOT}: {resolved}") from exc
    if len(relative.parts) != 1 or not relative.name.startswith(RECOVERY_ROOT_PREFIX):
        raise ContractError(f"unexpected recovery-root shape or prefix: {resolved}")
    for protected in PROTECTED_RELATIVE_ROOTS:
        protected_path = (PROJECT_ROOT / protected).resolve()
        if resolved == protected_path or protected_path in resolved.parents:
            raise ContractError(f"recovery root overlaps protected path: {resolved}")
    return resolved


def ensure_under(root: Path, path: str | Path) -> Path:
    resolved_root = root.resolve()
    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ContractError(f"path escapes run root: path={resolved}, root={resolved_root}") from exc
    return resolved


def load_mapping(path: str | Path) -> dict[str, Any]:
    resolved = resolve_project_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    if resolved.suffix.lower() in {".yaml", ".yml"}:
        value = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    else:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"mapping root required: {resolved}")
    return value


def atomic_write_bytes(path: Path, payload: bytes, *, allow_identical: bool = False) -> bool:
    """Atomically publish *payload* and never replace non-identical evidence.

    Returns ``True`` when a new file was published and ``False`` when an
    identical file already existed and ``allow_identical`` was requested.
    """

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if allow_identical and path.is_file() and path.read_bytes() == payload:
            return False
        raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            if allow_identical and path.is_file() and path.read_bytes() == payload:
                return False
            raise FileExistsError(f"refusing to overwrite concurrently published artifact: {path}")
    finally:
        if temp.exists():
            temp.unlink()
    return True


def atomic_write_json(path: Path, value: Mapping[str, Any], *, allow_identical: bool = False) -> bool:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    return atomic_write_bytes(path, payload, allow_identical=allow_identical)


def atomic_write_csv(
    path: Path,
    fieldnames: Iterable[str],
    rows: Iterable[Mapping[str, Any]],
    *,
    allow_identical: bool = False,
) -> bool:
    from io import StringIO

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fieldnames), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    return atomic_write_bytes(path, stream.getvalue().encode("utf-8"), allow_identical=allow_identical)


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(next(csv.reader(stream), []))


def csv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        next(reader, None)
        return sum(1 for _ in reader)


def file_record(path: Path, *, with_rows: bool = False) -> dict[str, Any]:
    resolved = path.resolve()
    exists = resolved.is_file()
    record: dict[str, Any] = {
        "path": project_relative(resolved),
        "exists": exists,
        "bytes": resolved.stat().st_size if exists else None,
        "sha256": sha256_file(resolved) if exists else None,
    }
    if exists and resolved.suffix.lower() == ".csv":
        record["columns"] = csv_header(resolved)
        if with_rows:
            record["rows"] = csv_row_count(resolved)
    elif exists and resolved.suffix.lower() in {".json", ".yaml", ".yml"}:
        try:
            record["top_level_keys"] = sorted(load_mapping(resolved))
        except (ValueError, yaml.YAMLError, json.JSONDecodeError, ContractError):
            record["top_level_keys"] = []
    return record


def files_digest(paths: Iterable[Path]) -> str:
    records = [
        {"path": project_relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted((item.resolve() for item in paths), key=lambda item: item.as_posix())
    ]
    return canonical_sha256(records)


def validate_terminal(payload: Mapping[str, Any], *, lane_id: str | None = None) -> None:
    allowed = {
        "P0_READY",
        "P0_BLOCKED_TERMINAL",
        "P0_TIMEOUT_TERMINAL",
        "SELECTION_READY",
        "SELECTION_PARTIAL_READY",
        "SELECTION_BLOCKED_TERMINAL",
        "SELECTION_TIMEOUT_TERMINAL",
        "CONFIRMATION_READY",
        "CONFIRMATION_PARTIAL_READY",
        "CONFIRMATION_BLOCKED_TERMINAL",
        "CONFIRMATION_TIMEOUT_TERMINAL",
        "LANE_DONE",
        "INTEGRATION_DONE",
    }
    if payload.get("terminal_state") not in allowed:
        raise ContractError(f"invalid terminal_state: {payload.get('terminal_state')!r}")
    if lane_id is not None and payload.get("lane_id") != lane_id:
        raise ContractError(f"lane mismatch: expected={lane_id}, observed={payload.get('lane_id')}")
    if "run_id" not in payload or "launch_hash" not in payload:
        raise ContractError("terminal manifest is missing run_id or launch_hash")


def deadline_reached(deadline_utc: str, *, now: datetime | None = None) -> bool:
    current = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    return current >= parse_utc(deadline_utc)
