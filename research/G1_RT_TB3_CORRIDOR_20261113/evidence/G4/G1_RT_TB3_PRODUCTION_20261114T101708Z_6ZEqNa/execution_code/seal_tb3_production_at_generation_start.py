"""Record confirmation-data digests and the pre-freeze access history."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


SEALED_CASES = tuple(f"{geometry}_{anchor}" for geometry in ("G-T2", "G-V") for anchor in "ABC")
FILES = (
    "H/{case}/H_full.npy",
    "H/{case}/H_LoS.npy",
    "paths/{case}/PATHS_NEAR.npz",
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, obj):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write("\n")


def log(root, operation, **fields):
    log_path = root / "seal/ACCESS_LOG.jsonl"
    with log_path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(dict(utc=utc(), actor="KMS", operation=operation, **fields)) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def seal_case(root, case):
    marker = root / "seal" / "cases" / f"{case}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    if marker.exists():
        raise FileExistsError(marker)
    manifest = root / "H" / case / "MANIFEST.json"
    files = {}
    for name in FILES:
        relative = name.format(case=case)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or invalid production artifact: {relative}")
        files[relative] = dict(bytes=path.stat().st_size, sha256=sha256(path))
        path.chmod(path.stat().st_mode & ~0o222)
    write(marker, dict(case=case, sealed_utc=utc(), files=files, case_manifest_sha256=sha256(manifest)))
    log(root, "SEAL_CASE", case=case, purpose="SHA-256 and file size", paths=list(files))


def finalize(root):
    marker_root = root / "seal"
    cases = {case: read(marker_root / "cases" / f"{case}.json") for case in SEALED_CASES}
    write(marker_root / "SEAL_MANIFEST.json", dict(
        question_id="G1-RT-TB3-002", status="SEALED", created_utc=utc(),
        rule="SPEC_DIAG_KO.md §4.2",
        permitted_access=["G0–G9 gate", "storage and format checks"],
        g4_input="H_LoS only; M1-T observation parity; no heading estimation",
        cases=cases,
    ))
    log(root, "SEAL_FINALIZED", cases=list(cases), purpose="confirmation case manifest consolidation")


def g4_access(root, phase, tool, g4_report):
    manifest = read(root / "seal" / "SEAL_MANIFEST.json")
    paths = [f"H/{case}/H_LoS.npy" for case in SEALED_CASES]
    log(root, f"G4_{phase}", gate="G4", script=tool.name, script_sha256=sha256(tool),
        purpose="noise-free true-distance observation parity", paths=paths,
        seal_manifest_sha256=sha256(root / "seal" / "SEAL_MANIFEST.json"),
        seal_status=manifest["status"],
        report_sha256=sha256(g4_report) if g4_report.is_file() else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", choices=SEALED_CASES)
    group.add_argument("--finalize", action="store_true")
    group.add_argument("--g4-access", choices=("START", "FINISH"))
    parser.add_argument("--g4-tool", type=Path)
    parser.add_argument("--g4-report", type=Path)
    args = parser.parse_args()
    if args.case:
        seal_case(args.root, args.case)
    elif args.finalize:
        finalize(args.root)
    else:
        if args.g4_tool is None or args.g4_report is None:
            parser.error("G4 access needs its script and report paths")
        g4_access(args.root, args.g4_access, args.g4_tool, args.g4_report)


if __name__ == "__main__":
    main()
