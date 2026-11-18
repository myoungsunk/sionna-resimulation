"""Verify a fresh local copy against the run and archive SHA-256 receipts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("expected_archive_sha256")
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / "LOCAL_TRANSFER_CHECK.json"
    if target.exists():
        raise FileExistsError(target)
    issues = []
    archive_sha = sha256(args.archive)
    if archive_sha != args.expected_archive_sha256:
        issues.append("archive SHA-256 differs from remote receipt")
    hashes = read(root / "RESULT_SHA256.json")
    byte_count = 0
    for name, expected in hashes.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            issues.append(f"unsafe manifest path: {name}")
        elif not path.is_file():
            issues.append(f"missing: {name}")
        else:
            byte_count += path.stat().st_size
            if sha256(path) != expected:
                issues.append(f"file SHA-256 differs: {name}")
    success = read(root / "RUN_SUCCESS.json")
    if success.get("ok") is not True:
        issues.append("run success receipt is not true")
    if sha256(root / "RESULT_SHA256.json") != success["result_manifest_sha256"]:
        issues.append("result manifest SHA-256 differs")
    if sha256(root / "RUN_CONTRACT.json") != success["contract_sha256"]:
        issues.append("run contract SHA-256 differs")
    validation = read(root / "VALIDATION.json")
    if (validation.get("ok") is not True or len(validation.get("tasks", {})) != 70
            or any(validation["tasks"].values())):
        issues.append("original chunk validation receipt is not all 70 PASS")
    overlap = read(root / "ORIGINAL_OVERLAP_CHECK.json")
    if overlap.get("ok") is not True:
        issues.append("original overlap check is not PASS")
    for name, expected in overlap["input_sha256"].items():
        if sha256(root / name) != expected:
            issues.append(f"postcheck input changed: {name}")
    report = dict(ok=not issues, status="FAIL" if issues else "PASS", issues=issues,
                  checked_utc=datetime.now(timezone.utc).isoformat(),
                  root=str(root), archive=str(args.archive.resolve()),
                  archive_sha256=archive_sha, manifest_files_checked=len(hashes),
                  manifest_file_bytes=byte_count,
                  result_manifest_sha256=sha256(root / "RESULT_SHA256.json"),
                  overlap_report_sha256=sha256(root / "ORIGINAL_OVERLAP_CHECK.json"),
                  script_sha256=sha256(Path(__file__)))
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
