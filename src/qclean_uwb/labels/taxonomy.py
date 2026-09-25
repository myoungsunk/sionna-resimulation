from __future__ import annotations

from collections.abc import Mapping


PATH2H_LABELS = ("NoLoS", "RD-LoS")
PATH3H_LABELS = ("NoLoS", "HB-near-delay", "HB-prior")

TRUE_STRINGS = {"1", "true", "t", "yes", "y"}
FALSE_STRINGS = {"0", "false", "f", "no", "n", ""}


def parse_bool(value: object) -> bool:
    """Parse label-table boolean cells without depending on pandas."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in TRUE_STRINGS:
        return True
    if text in FALSE_STRINGS:
        return False
    raise ValueError(f"cannot parse boolean label value: {value!r}")


def _flag(row: Mapping[str, object], column: str) -> bool:
    if column not in row:
        raise KeyError(f"missing label column: {column}")
    return parse_bool(row[column])


def label_partition_issues(row: Mapping[str, object], head: str) -> list[str]:
    """Return label partition issues for the frozen PATH-2H or PATH-3H heads."""
    head_normalized = head.strip().upper()
    clean = _flag(row, "Clean-LoS")
    nolos = _flag(row, "NoLoS")

    if head_normalized == "PATH-2H":
        rd = _flag(row, "RD-LoS")
        active = [clean, nolos, rd]
        not_clean = row.get("not-clean_2H")
        expected_not_clean = nolos or rd
    elif head_normalized == "PATH-3H":
        hb_near = _flag(row, "HB-near-delay")
        hb_prior = _flag(row, "HB-prior")
        active = [clean, nolos, hb_near, hb_prior]
        not_clean = row.get("not-clean_3H")
        expected_not_clean = nolos or hb_near or hb_prior
    else:
        raise ValueError(f"unknown label head: {head!r}")

    issues: list[str] = []
    if sum(1 for value in active if value) != 1:
        issues.append(f"{head_normalized} must have exactly one active branch")
    if not_clean is not None and parse_bool(not_clean) != expected_not_clean:
        issues.append(f"{head_normalized} not-clean flag does not match branch labels")
    return issues


def require_valid_label_partition(row: Mapping[str, object], head: str) -> None:
    issues = label_partition_issues(row, head)
    if issues:
        raise ValueError("; ".join(issues))
