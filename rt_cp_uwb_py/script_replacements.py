from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .parity import run_parity_suite
from .sanity import run_implemented_checks


def classify_script(script_name: str) -> str:
    stem = Path(script_name).stem.lower()
    if stem.startswith("test_") or "sanity" in stem or "convention" in stem or "phase2_ffd" in stem or "phase3_handedness" in stem or "phase4_reflection" in stem:
        return "sanity"
    if any(token in stem for token in ["stage", "h10", "dual_tag", "anchor", "path", "exp", "theta0", "lp_xpol", "paper_metrics", "current0p20"]):
        return "parity"
    if stem.startswith("diag") or stem.startswith("diagnose") or stem.startswith("compare") or stem.startswith("visualize"):
        return "sanity"
    return "parity"


def run_script_replacement(script_name: str, project_root: str | Path | None = None, out_dir: str | Path | None = None) -> dict:
    root = Path(project_root or Path(__file__).resolve().parents[1])
    stem = Path(script_name).stem
    mode = classify_script(script_name)
    out = Path(out_dir) if out_dir else root / "results" / "python_script_replacements" / stem
    out.mkdir(parents=True, exist_ok=True)
    status = {
        "script_name": script_name,
        "python_replacement_mode": mode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "out_dir": str(out),
    }
    if mode == "sanity":
        df = run_implemented_checks(out)
        status.update({"artifact": str(out / "sanity_checks.csv"), "passed": bool(df["passed"].astype(bool).all()), "rows": int(len(df))})
    else:
        manifest = run_parity_suite(root / "results", out)
        metrics = pd.read_csv(out / "metric_delta_table.csv")
        status.update({
            "artifact": str(out / "python_vs_matlab_parity_summary.md"),
            "passed": bool(int(metrics.loc[metrics.metric == "python_failed_cases", "value"].iloc[0]) == 0),
            "matched_cases": int(metrics.loc[metrics.metric == "merged_cases", "value"].iloc[0]),
            "feature_columns_passed": int(metrics.loc[metrics.metric == "feature_columns_passed", "value"].iloc[0]),
            "manifest": manifest,
        })
    (out / "script_replacement_status.json").write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
    return status
