#!/usr/bin/env python3
"""Fail-closed native FFD and runner preflight, with ZERO Sionna/physics execution.

Checks source checkout, external bank path+manifest SHA256, frequency grid,
platform version metadata and config. Outputs a JSON receipt to stdout and
optionally a new file. Does not write an output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_body_probe_v2_native import prerequisite_report

EXPECTED_VERSIONS = {
    "sionna-rt": "2.0.1",
    "mitsuba": "3.8.0",
    "drjit": "1.3.1",
}
PORTS = ("LP_plus45", "LP_minus45")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(2**20), b""):
            h.update(part)
    return h.hexdigest()


def git_state(root: Path) -> dict:
    def run(*args):
        return subprocess.run(("git", "-C", str(root), *args),
                              capture_output=True, text=True, check=True).stdout.strip()
    try:
        return {
            "head": run("rev-parse", "HEAD"),
            "branch": run("branch", "--show-current"),
            "worktree_clean": not bool(run("status", "--porcelain", "--untracked-files=no")),
        }
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        return {"error": type(e).__name__, "message": str(e)}


def validate_native_inputs(config: dict, *, config_path: Path | None = None,
                           output_path: Path | None = None,
                           expected_head: str | None = None) -> dict:
    issues: list[str] = []
    basic = prerequisite_report(config)
    issues.extend(basic["issues"])
    evidence = {
        "run_mode": "PRECHECK_NO_SIONNA_NO_MOTION",
        "scope": "single-station range_only neutral physical slip",
        "config_sha256": digest(config_path) if config_path and config_path.is_file() else None,
        "git": git_state(ROOT),
        "actual_packages": {},
        "native_banks": {},
        "rf_source": "pinned dual-LP FFD bank from MANIFEST",
        "known_claim_limits": ["NO_ACTIVE_S_HEADING_UPDATE", "NO_PHYSICAL_SLIP",
                               "NO_CROSS_ANGLE_RF_COVARIANCE", "NO_SCIENTIFIC_PASS"],
    }
    git=evidence["git"]
    if "error" in git:
        issues.append("GIT_SOURCE_UNAVAILABLE")
    elif not git["worktree_clean"]:
        issues.append("TRACKED_GIT_WORKTREE_DIRTY")
    if expected_head is not None and git.get("head") != expected_head:
        issues.append("SOURCE_HEAD_MISMATCH")
    if config.get("rf", {}).get("mode") != "range_only":
        issues.append("NOT_RANGE_ONLY_PRECHECK_CONTRACT")
    if config.get("physical", {}).get("slip_mode") != "neutral":
        issues.append("NOT_NEUTRAL_SLIP_PRECHECK_CONTRACT")
    for package, version in EXPECTED_VERSIONS.items():
        try:
            actual=metadata.version(package)
            evidence["actual_packages"][package]=actual
            if actual!=version:
                issues.append(f"PINNED_PACKAGE_VERSION_MISMATCH_{package}")
        except metadata.PackageNotFoundError:
            evidence["actual_packages"][package]="NOT_INSTALLED"
            issues.append(f"REQUIRED_PACKAGE_NOT_INSTALLED_{package}")
    if output_path is not None:
        evidence["requested_out"]=str(output_path)
        if output_path.exists():
            issues.append("OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
        elif not output_path.parent.is_dir() or not os.access(output_path.parent, os.W_OK):
            issues.append("OUTPUT_PARENT_NOT_WRITABLE")
    rf=config.get("rf",{})
    manifest=rf.get("bank_manifest")
    bank_dir=rf.get("bank_dir")
    if manifest and bank_dir and Path(manifest).is_file() and Path(bank_dir).is_dir():
        try:
            m=json.loads(Path(manifest).read_text(encoding="utf-8"))
            refs=m["npz_sha256"]
            evidence["bank_manifest_sha256"]=digest(Path(manifest))
            frequencies=[]
            for port in PORTS:
                name=port+"_bank.npz"
                path=Path(bank_dir)/name
                if not path.is_file():
                    issues.append(f"BANK_FILE_MISSING_{name}")
                    continue
                expected=refs.get(name)
                actual=digest(path)
                evidence["native_banks"][name]={
                    "size_bytes":path.stat().st_size,
                    "expected_sha256":expected,
                    "actual_sha256":actual,
                    "sha256_matches":expected==actual,
                }
                if not expected or actual!=expected:
                    issues.append(f"BANK_HASH_MISMATCH_{name}")
                    continue
                with np.load(path,allow_pickle=False) as data:
                    required=("freqs_hz","theta_deg","phi_deg","e_theta","e_phi")
                    missing=[k for k in required if k not in data.files]
                    if missing:
                        issues.append(f"BANK_KEYS_MISSING_{name}:{','.join(missing)}")
                        continue
                    freq=np.asarray(data["freqs_hz"],dtype=float)
                    if (freq.shape!=(257,) or not np.isfinite(freq).all()
                        or not np.all(np.diff(freq)>0)):
                        issues.append(f"BANK_FREQ_AXIS_INVALID_{name}")
                        continue
                    frequencies.append(freq)
                    shapes={k:list(data[k].shape) for k in required}
                    evidence["native_banks"][name]["shapes"]=shapes
                    if (data["e_theta"].shape[0]!=257 or
                        data["e_phi"].shape!=data["e_theta"].shape):
                        issues.append(f"BANK_FFD_ARRAY_SHAPE_INVALID_{name}")
            if len(frequencies)==2:
                if not np.array_equal(frequencies[0],frequencies[1]):
                    issues.append("PORT_FREQUENCY_GRID_MISMATCH")
                else:
                    evidence["frequency_grid"]={
                        "count":len(frequencies[0]),
                        "first_hz":float(frequencies[0][0]),
                        "last_hz":float(frequencies[0][-1]),
                    }
        except (OSError,KeyError,ValueError,TypeError) as exc:
            issues.append(f"BANK_VALIDATION_FAILED:{type(exc).__name__}:{exc}")
    else:
        issues.append("NATIVE_BANK_PATHS_NOT_ACCESSIBLE")
    issues=list(dict.fromkeys(issues))
    evidence["issues"]=issues
    evidence["ready"]=not issues
    evidence["status"]="PREFLIGHT_PASS_NOT_EXECUTED" if not issues else "BLOCKED"
    evidence["scientific_PASS"]=False
    return evidence


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",type=Path,required=True)
    ap.add_argument("--out",type=Path,help="new result directory; checked but never created")
    ap.add_argument("--expected-head",type=str,help="exact source commit SHA to require")
    ap.add_argument("--receipt",type=Path,help="NEW receipt path; no overwrite")
    args=ap.parse_args()
    cfg=json.loads(args.config.read_text(encoding="utf-8"))
    report=validate_native_inputs(cfg,config_path=args.config,
                                  output_path=args.out,expected_head=args.expected_head)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    if args.receipt is not None:
        if args.receipt.exists() or not args.receipt.parent.is_dir():
            raise ValueError("preflight receipt path must be new in an existing directory")
        args.receipt.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return 0 if report["ready"] else 2


if __name__=="__main__":
    raise SystemExit(main())
