from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .operations import list_operations
from .parity import run_parity_suite


HELPER_SKIP = {"sanity.ensureOutputDir", "sanity.savePlot"}


def active_matlab_package_functions(project_root: str | Path) -> list[str]:
    root = Path(project_root)
    out = []
    for path in sorted(root.glob("+*/*.m")):
        out.append(f"{path.parent.name[1:]}.{path.stem}")
    return out


def active_matlab_scripts(project_root: str | Path) -> list[Path]:
    return sorted(Path(project_root, "scripts").glob("*.m"))


def operation_coverage(project_root: str | Path) -> pd.DataFrame:
    matlab_ops = active_matlab_package_functions(project_root)
    py_ops = set(list_operations())
    rows = []
    if not matlab_ops:
        for op in sorted(py_ops):
            rows.append({
                "matlab_operation": "",
                "python_available": True,
                "python_operation": op,
                "note": "matlab_source_not_present_python_registry_available",
            })
        return pd.DataFrame(rows)
    for op in matlab_ops:
        rows.append({
            "matlab_operation": op,
            "python_available": bool(op in py_ops or op in HELPER_SKIP),
            "python_operation": op if op in py_ops else "",
            "note": "matlab_output_helper_not_needed" if op in HELPER_SKIP else "",
        })
    return pd.DataFrame(rows)


def create_script_wrappers(project_root: str | Path, wrapper_dir: str | Path | None = None) -> pd.DataFrame:
    root = Path(project_root)
    out_dir = Path(wrapper_dir) if wrapper_dir else root / "scripts_py_matlab_replacements"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    scripts = active_matlab_scripts(root)
    if not scripts:
        existing = sorted(p for p in out_dir.glob("*.py") if p.name != "__init__.py")
        rows = [{"matlab_script": "", "python_wrapper": str(path), "created": True, "note": "matlab_source_not_present_existing_wrapper"} for path in existing]
        df = pd.DataFrame(rows, columns=["matlab_script", "python_wrapper", "created", "note"])
        df.to_csv(out_dir / "script_wrapper_inventory.csv", index=False)
        return df
    for script in scripts:
        py_path = out_dir / f"{script.stem}.py"
        rel_project = root.as_posix()
        content = f'''from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"{rel_project}")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rt_cp_uwb_py.script_replacements import run_script_replacement


def main() -> None:
    parser = argparse.ArgumentParser(description="Python replacement for {script.name}")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    status = run_script_replacement("{script.name}", project_root=PROJECT_ROOT, out_dir=args.out_dir)
    print(status["out_dir"])


if __name__ == "__main__":
    main()
'''
        py_path.write_text(content, encoding="utf-8")
        rows.append({"matlab_script": str(script), "python_wrapper": str(py_path), "created": True})
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "script_wrapper_inventory.csv", index=False)
    return df


def build_migration_comparison(project_root: str | Path, out_dir: str | Path | None = None, run_parity: bool = True) -> dict:
    root = Path(project_root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(out_dir) if out_dir else root / "results" / f"python_full_migration_compare_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    coverage = operation_coverage(root)
    coverage.to_csv(out / "matlab_package_operation_coverage.csv", index=False)
    wrappers = create_script_wrappers(root)
    wrappers.to_csv(out / "matlab_script_wrapper_coverage.csv", index=False)
    parity_manifest = None
    if run_parity:
        parity_manifest = run_parity_suite(root / "results", out / "parity")
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "matlab_package_functions": int(len(coverage)),
        "matlab_package_functions_python_available": int(coverage["python_available"].sum()),
        "matlab_scripts": int(len(wrappers)),
        "matlab_script_wrappers_created": int(wrappers["created"].sum()),
        "wrapper_dir": str(root / "scripts_py_matlab_replacements"),
        "parity_manifest": parity_manifest,
    }
    (out / "migration_comparison_manifest.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    lines = [
        "# MATLAB to Python Migration Comparison",
        "",
        f"- MATLAB package operations: `{summary['matlab_package_functions_python_available']}/{summary['matlab_package_functions']}` Python-covered",
        f"- MATLAB scripts: `{summary['matlab_script_wrappers_created']}/{summary['matlab_scripts']}` Python wrappers created",
        f"- Wrapper directory: `{summary['wrapper_dir']}`",
        "",
        "## Data Comparison",
        "",
    ]
    if run_parity:
        metrics = pd.read_csv(out / "parity" / "metric_delta_table.csv")
        for _, row in metrics.iterrows():
            lines.append(f"- `{row['metric']}`: `{row['value']}`")
        lines.append("")
        lines.append("Detailed feature deltas are in `parity/feature_delta_table.csv`.")
    (out / "python_vs_previous_results_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
