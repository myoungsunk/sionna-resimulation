from __future__ import annotations

import csv
from pathlib import Path


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_manifest_paths(root: Path, manifest: Path, path_field: str = "path") -> list[str]:
    issues: list[str] = []
    for idx, row in enumerate(read_manifest(manifest), start=2):
        rel = row.get(path_field, "")
        status = row.get("status", "")
        required_action = row.get("required_action", "")
        if status == "PRESENT" and not (root / rel).exists():
            issues.append(f"{manifest}:{idx} marked PRESENT but path is missing: {rel}")
        if status == "MISSING" and not required_action:
            issues.append(f"{manifest}:{idx} marked MISSING without required_action: {rel}")
        if status not in {"PRESENT", "MISSING"}:
            issues.append(f"{manifest}:{idx} invalid status: {status}")
    return issues
