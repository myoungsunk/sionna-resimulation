"""Verify downloaded Office publication files using only Python's standard library."""
import hashlib
import json
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "FILES_SHA256.json").read_text(encoding="utf-8"))
    issues = []
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            issues.append(f"unsafe path: {name}")
        elif not path.is_file():
            issues.append(f"missing: {name}")
        elif path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
            issues.append(f"size/hash mismatch: {name} (download the actual Git LFS object)")
    print(json.dumps(dict(ok=not issues, files_checked=len(manifest["files"]), issues=issues), indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
