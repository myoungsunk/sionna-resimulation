"""Config snapshot, hash and manifest helpers for the corridor driving simulation.

Every leaf parameter is ``{"value", "status", "source"[, "unit"]}``.  ``status`` says how far the value can be trusted:
``adopted`` (taken from a project artifact), ``derived`` (computed from adopted values), ``assumption`` (placeholder, swept or
replaced later) or ``deferred`` (not fixed yet; must be fixed before the stage named in ``source``).
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

STATUSES = ("adopted", "derived", "assumption", "deferred")


def param(value, status: str, source: str, unit: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"UNKNOWN_PARAM_STATUS {status!r}")
    out = {"value": value, "status": status, "source": source}
    if unit is not None:
        out["unit"] = unit
    return out


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def config_sha256(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf8")).hexdigest()


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_params(cfg, path: str = "") -> list[str]:
    """Return error strings for every leaf-parameter dict that lacks a valid status/source."""
    errors: list[str] = []
    if isinstance(cfg, dict):
        if "value" in cfg:
            if cfg.get("status") not in STATUSES:
                errors.append(f"{path or '<root>'}: status must be one of {STATUSES}")
            if not cfg.get("source"):
                errors.append(f"{path or '<root>'}: source missing")
            return errors
        for key, val in cfg.items():
            errors += validate_params(val, f"{path}.{key}" if path else str(key))
    elif isinstance(cfg, (list, tuple)):
        for i, val in enumerate(cfg):
            errors += validate_params(val, f"{path}[{i}]")
    return errors


def build_manifest(*, config: dict, inputs: list, outputs: list, command: list | None = None, timestamp: float | None = None) -> dict:
    """Manifest with config hash+snapshot, input/output SHA256, timestamp and command line."""
    def entry(p):
        p = Path(p)
        return {"path": str(p), "sha256": file_sha256(p), "bytes": p.stat().st_size}

    ts = time.time() if timestamp is None else timestamp
    return {
        "config_sha256": config_sha256(config),
        "config": config,
        "inputs": [entry(p) for p in inputs],
        "outputs": [entry(p) for p in outputs],
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "command": list(sys.argv if command is None else command),
    }
