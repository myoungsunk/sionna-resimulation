from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _normalized_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [dict(row) for row in rows]
    if not normalized:
        raise ValueError("claim matrix requires at least one row")
    for row in normalized:
        key = str(row.get("canonical_key") or "").strip()
        if not key:
            raise ValueError("every claim row requires canonical_key")
        row["canonical_key"] = key
    keys = [row["canonical_key"] for row in normalized]
    if len(keys) != len(set(keys)):
        raise ValueError("claim matrix canonical_key values must be unique")
    return sorted(normalized, key=lambda row: row["canonical_key"])


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _row_map(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["canonical_key"]): dict(row) for row in rows}


def diff_claim_rows(
    previous_rows: Iterable[Mapping[str, Any]],
    current_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    previous = _row_map(previous_rows)
    current = _row_map(current_rows)
    previous_keys = set(previous)
    current_keys = set(current)
    changed: list[dict[str, Any]] = []
    for key in sorted(previous_keys & current_keys):
        if canonical_sha256(previous[key]) != canonical_sha256(current[key]):
            changed.append(
                {"canonical_key": key, "before": previous[key], "after": current[key]}
            )
    return {
        "added": sorted(current_keys - previous_keys),
        "removed": sorted(previous_keys - current_keys),
        "changed": changed,
        "unchanged": sorted(
            key
            for key in previous_keys & current_keys
            if canonical_sha256(previous[key]) == canonical_sha256(current[key])
        ),
    }


def write_claim_matrix_version(
    root: Path,
    *,
    version_tag: str,
    rows: Iterable[Mapping[str, Any]],
    evidence_links: Mapping[str, list[str]],
    source_run_id: str,
) -> dict[str, Any]:
    if not version_tag or any(ch in version_tag for ch in "/\\"):
        raise ValueError("version_tag must be a non-empty path-safe label")
    normalized = _normalized_rows(rows)
    root.mkdir(parents=True, exist_ok=True)
    versions_root = root / "versions"
    versions_root.mkdir(exist_ok=True)
    version_root = versions_root / version_tag
    if version_root.exists():
        raise FileExistsError(f"claim matrix version already exists: {version_tag}")

    latest_path = root / "LATEST.json"
    previous_tag: str | None = None
    previous_rows: list[dict[str, Any]] = []
    if latest_path.exists():
        previous_tag = str(json.loads(latest_path.read_text(encoding="utf-8"))["version_tag"])
        previous_rows = _read_csv(versions_root / previous_tag / "CLAIM_MATRIX.csv")

    diff = diff_claim_rows(previous_rows, normalized)
    version_root.mkdir()
    _write_csv(version_root / "CLAIM_MATRIX.csv", normalized)
    (version_root / "EVIDENCE_LINKS.json").write_text(
        json.dumps(dict(evidence_links), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (version_root / "DIFF.json").write_text(
        json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    version_record = {
        "schema_version": 1,
        "version_tag": version_tag,
        "previous_version_tag": previous_tag,
        "source_run_id": source_run_id,
        "row_count": len(normalized),
        "claim_matrix_sha256": canonical_sha256(normalized),
        "evidence_links_sha256": canonical_sha256(dict(evidence_links)),
        "diff_sha256": canonical_sha256(diff),
    }
    (version_root / "VERSION.json").write_text(
        json.dumps(version_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    latest_path.write_text(
        json.dumps(version_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {**version_record, "diff": diff, "version_root": str(version_root)}
