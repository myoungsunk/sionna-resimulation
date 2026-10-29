"""Run manifest + hashing utilities (config/MANIFEST_SCHEMA.json, validated without external packages)."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
REPO = EXP.parents[2]
CONTRACT = EXP / "contracts" / "EXPERIMENT_CONTRACT_MBVAR-INFO-001.md"
SCHEMA = EXP / "config" / "MANIFEST_SCHEMA.json"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def git_blob_sha(p) -> str:
    data = Path(p).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def git_head() -> str:
    env = os.environ.get("GITHUB_SHA")
    if env and re.fullmatch(r"[0-9a-f]{40}", env):
        return env
    try:
        return subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "0" * 40


def governance_sha() -> str:
    g = os.environ.get("MBVAR_GOVERNANCE_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", g):
        raise SystemExit("ERR_ROLE_ROUTING: MBVAR_GOVERNANCE_SHA (40 hex) required")
    return g


def code_hashes() -> dict:
    out = {}
    for sub in ("code", "scripts", "tests", "audit"):
        for p in sorted((EXP / sub).glob("*.py")):
            out[str(p.relative_to(EXP))] = sha256_file(p)
    return out


def validate_manifest(m: dict) -> list[str]:
    s = json.loads(SCHEMA.read_text()); errs = []
    for k in s["required"]:
        if k not in m:
            errs.append(f"missing:{k}")
    for k, spec in s["properties"].items():
        if k not in m:
            continue
        v = m[k]
        if "const" in spec and v != spec["const"]:
            errs.append(f"const:{k}")
        if "enum" in spec and v not in spec["enum"]:
            errs.append(f"enum:{k}={v}")
        if spec.get("type") == "string" and "pattern" in spec and not (isinstance(v, str) and re.fullmatch(spec["pattern"], v)):
            errs.append(f"pattern:{k}")
        if spec.get("type") == "object" and "additionalProperties" in spec:
            pat = spec["additionalProperties"].get("pattern")
            if not isinstance(v, dict) or (pat and any(not re.fullmatch(pat, str(x)) for x in v.values())):
                errs.append(f"object:{k}")
        if spec.get("type") == "array" and (not isinstance(v, list) or len(v) < spec.get("minItems", 0)):
            errs.append(f"array:{k}")
    for cond in s.get("allOf", []):
        if m.get("phase") in cond["if"]["properties"]["phase"]["enum"]:
            for k in cond["then"]["required"]:
                if k not in m:
                    errs.append(f"missing_rt:{k}")
    return errs


def write_manifest(out: Path, *, phase, status, contract_sha, config_files, input_lock, outputs, seed_ledger, verdict,
                   unit, limitations, extra=None):
    out = Path(out)
    cfg = {str(p): sha256_file(p) for p in config_files}
    m = dict(contract_id="MBVAR-INFO-001", phase=phase, execution_status=status,
             utc_completed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), source_git_sha=git_head(),
             governance_git_sha=governance_sha(), contract_sha256=contract_sha,
             config_sha256=sha256_bytes(json.dumps(cfg, sort_keys=True).encode()), config_files=cfg,
             input_lock_sha256=sha256_file(input_lock) if input_lock and Path(input_lock).exists() else sha256_bytes(b"NO_INPUT_LOCK"),
             source_code_sha256=code_hashes(),
             output_sha256={str(p.name): sha256_file(p) for p in outputs if Path(p).exists()},
             seed_ledger_sha256=sha256_file(seed_ledger) if seed_ledger and Path(seed_ledger).exists() else sha256_bytes(b"NO_SEEDS"),
             run_command=" ".join([sys.executable] + sys.argv), scientific_verdict=verdict, independence_unit=unit,
             limitations=list(limitations), python=platform.python_version(), platform=platform.platform(),
             github_run_id=os.environ.get("GITHUB_RUN_ID"), reviewer_status="SELF_REVIEW_ONLY")
    if extra:
        m.update(extra)
    errs = validate_manifest(m)
    m["manifest_schema_errors"] = errs
    (out / "MANIFEST.json").write_text(json.dumps(m, indent=1, default=str))
    if errs:
        raise SystemExit(f"ERR_MANIFEST {errs}")
    return m
