"""Gate utilities for Paper 2 Block C hardware-imperfection runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


PASS_PREFIX = "PASS"
NOT_STARTED = "NOT_STARTED"
MATLAB_STARTUP_BLOCKED = "MATLAB_STARTUP_BLOCKED"
PYTHON_ENGINE_STARTUP_BLOCKED = "PYTHON_ENGINE_STARTUP_BLOCKED"
SWEEP_FORBIDDEN_GATE_NOT_PASSED = "SWEEP_FORBIDDEN_GATE_NOT_PASSED"
MISSING_GROUNDED_HW_RANGE = "MISSING_GROUNDED_HW_RANGE"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return (not self.timed_out) and self.returncode == 0

    @property
    def status(self) -> str:
        if self.timed_out:
            return "TIMEOUT"
        if self.returncode == 0:
            return "PASS"
        return "FAIL"


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def ensure_standard_dirs(out_dir: Path) -> dict[str, Path]:
    dirs = {
        "root": out_dir,
        "tables": out_dir / "tables",
        "reports": out_dir / "reports",
        "configs": out_dir / "configs",
        "logs": out_dir / "logs",
        "stage_results": out_dir / "stage_results",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def write_json(path: Path, payload: MappingLike) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if rows:
        fieldnames = sorted({key for row in rows for key in row})
    else:
        fieldnames = ["item", "status", "detail"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def run_command(command: Sequence[str], cwd: Path, timeout_s: int) -> CommandResult:
    proc = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = proc.communicate(timeout=max(1, int(timeout_s)))
        return CommandResult(list(command), proc.returncode, stdout, stderr, False)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc.pid)
        stdout, stderr = proc.communicate()
        return CommandResult(list(command), None, stdout, stderr, True)


def kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["kill", "-TERM", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def save_command_logs(result: CommandResult, logs_dir: Path, stem: str) -> dict[str, str]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"{stem}.stdout.txt"
    stderr_path = logs_dir / f"{stem}.stderr.txt"
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return {"stdout": str(stdout_path), "stderr": str(stderr_path)}


def command_display(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def gate_passed(status: str) -> bool:
    return str(status).startswith(PASS_PREFIX)


def compare_gate_ledgers(reference_csv: Path, candidate_csv: Path, atol: float = 1e-12) -> pd.DataFrame:
    required = [
        "GATE_B1_RD_BLIND_BASELINE_INTERACTION",
        "GATE_C_CP_SPECIFICITY",
        "OVERALL_RD_BLIND_REFLECTION",
    ]
    if not reference_csv.exists():
        return missing_gate_comparison(required, f"missing reference gate ledger: {reference_csv}")
    if not candidate_csv.exists():
        return missing_gate_comparison(required, f"missing candidate gate ledger: {candidate_csv}")

    ref = pd.read_csv(reference_csv)
    cand = pd.read_csv(candidate_csv)
    rows: list[dict[str, Any]] = []
    for gate_id in required:
        r = ref[ref["gate_id"].astype(str).eq(gate_id)]
        c = cand[cand["gate_id"].astype(str).eq(gate_id)]
        if r.empty or c.empty:
            rows.append(
                {
                    "gate_id": gate_id,
                    "status": "FAIL_MISSING_GATE_ROW",
                    "detail": f"reference_rows={len(r)}; candidate_rows={len(c)}",
                }
            )
            continue
        r0 = r.iloc[0]
        c0 = c.iloc[0]
        status_match = str(r0.get("status", "")) == str(c0.get("status", ""))
        numeric_match, numeric_detail = numeric_fields_match(r0, c0, ["observed", "ci_low", "ci_high"], atol)
        status = "PASS_GATE_RESTORED" if status_match and numeric_match else "FAIL_GATE_CHANGED"
        rows.append(
            {
                "gate_id": gate_id,
                "status": status,
                "reference_status": str(r0.get("status", "")),
                "candidate_status": str(c0.get("status", "")),
                "numeric_detail": numeric_detail,
            }
        )
    return pd.DataFrame(rows)


def missing_gate_comparison(gate_ids: list[str], detail: str) -> pd.DataFrame:
    return pd.DataFrame([{"gate_id": gate_id, "status": "FAIL_MISSING_GATE_LEDGER", "detail": detail} for gate_id in gate_ids])


def numeric_fields_match(left: pd.Series, right: pd.Series, fields: list[str], atol: float) -> tuple[bool, str]:
    details = []
    ok = True
    for field in fields:
        lv = as_float(left.get(field, math.nan))
        rv = as_float(right.get(field, math.nan))
        if math.isnan(lv) and math.isnan(rv):
            details.append(f"{field}=both_nan")
            continue
        diff = abs(lv - rv)
        field_ok = diff <= atol
        ok = ok and field_ok
        details.append(f"{field}:ref={lv:.17g},cand={rv:.17g},diff={diff:.3g},ok={field_ok}")
    return ok, "; ".join(details)


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def overall_from_gate_rows(rows: Iterable[dict[str, Any]]) -> str:
    by_item = {str(row.get("item", "")): str(row.get("status", "")) for row in rows}
    if by_item.get("MATLAB_STARTUP") == MATLAB_STARTUP_BLOCKED:
        return MATLAB_STARTUP_BLOCKED
    if by_item.get("PYTHON_ENGINE_STARTUP") == PYTHON_ENGINE_STARTUP_BLOCKED:
        return PYTHON_ENGINE_STARTUP_BLOCKED
    if gate_passed(by_item.get("V1_IDENTITY_GATE", "")) and gate_passed(by_item.get("V_HV1_GATE", "")):
        return "PASS_STEP1_DUAL_RESTORATION_GATES"
    return "STEP1_DUAL_RESTORATION_NOT_PASSED"


def sweep_allowed_from_gate_rows(rows: Iterable[dict[str, Any]]) -> bool:
    by_item = {str(row.get("item", "")): str(row.get("status", "")) for row in rows}
    return gate_passed(by_item.get("V1_IDENTITY_GATE", "")) and gate_passed(by_item.get("V_HV1_GATE", ""))


def write_markdown_report(path: Path, title: str, rows: list[dict[str, Any]], manifest_rel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        "Scope: Paper 2 Block C gated execution. No degradation sweep is authorized unless V1 and V-HV1 both pass.",
        "",
        "## Status",
        "",
        "| item | status | detail |",
        "|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| `{row.get('item', '')}` | `{row.get('status', '')}` | {str(row.get('detail', '')).replace('|', '/')} |")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- `q_clean` remains a clean-session/session-quality confidence score.",
            "- Failure-threshold reality/irreality remains forbidden while grounded HW range is `MISSING_GROUNDED_HW_RANGE`.",
            "- The active Block C engine is Python ray-tracing; no MATLAB preflight is required in this run family.",
            "",
            f"Manifest: `{manifest_rel}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_stage_result(stage_results_dir: Path, stage_name: str, payload: Mapping[str, Any]) -> Path:
    path = stage_results_dir / stage_name / "STEP_RESULT.json"
    write_json(path, dict(payload))
    return path


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    return value


MappingLike = Mapping[str, Any]
