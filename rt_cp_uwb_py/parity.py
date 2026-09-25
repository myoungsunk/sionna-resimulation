from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import cv_logistic_auc
from .config import default_config
from .features import CANONICAL_FEATURE_NAMES, CP16_FEATURE_NAMES
from .sweep import run_sweep_batch


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def representative_cases() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"case_id": 1, "seed_case_id": 1, "tx_slab_dist_m": 1.0, "rx_slab_dist_m": 1.5, "eps_r": 4.0, "tan_delta": 0.01, "snr_db": 999.0},
            {"case_id": 2, "seed_case_id": 2, "tx_slab_dist_m": 0.8, "rx_slab_dist_m": 2.0, "eps_r": 5.5, "tan_delta": 0.05, "snr_db": 40.0},
            {"case_id": 3, "seed_case_id": 3, "room_type": "A", "eps_r": 3.0, "tan_delta": 0.02, "snr_db": 30.0},
        ]
    )


def _select_baseline_cases(baseline_df: pd.DataFrame, max_cases: int = 30) -> pd.DataFrame:
    if baseline_df is None or baseline_df.empty:
        return representative_cases()
    df = baseline_df.copy()
    if "rx_azimuth_deg" in df.columns:
        sort_cols = ["source_case_id" if "source_case_id" in df.columns else "case_id", "rx_azimuth_deg"]
        ordered = df.sort_values(sort_cols).reset_index(drop=True)
        if "source_case_id" in ordered.columns and len(ordered) > max_cases:
            source_ids = ordered["source_case_id"].drop_duplicates().to_numpy()
            rows_per_source = max(1, int(np.ceil(len(ordered) / max(len(source_ids), 1))))
            n_sources = max(1, int(np.ceil(max_cases / rows_per_source)))
            source_idx = np.unique(np.linspace(0, len(source_ids) - 1, min(n_sources, len(source_ids))).round().astype(int))
            chosen = set(source_ids[source_idx].tolist())
            cases = ordered[ordered["source_case_id"].isin(chosen)].head(max_cases).copy()
        else:
            cases = ordered.head(max_cases).copy()
    elif len(df) > max_cases:
        row_idx = np.unique(np.linspace(0, len(df) - 1, max_cases).round().astype(int))
        cases = df.iloc[row_idx].copy()
    else:
        cases = df.copy()
    for col in ["case_id", "source_case_id", "seed_case_id"]:
        if col in cases.columns:
            cases[col] = pd.to_numeric(cases[col], errors="coerce").astype("Int64")
    if "source_case_id" in cases.columns and "seed_case_id" not in cases.columns:
        cases["seed_case_id"] = cases["source_case_id"]
    if "case_id" not in cases.columns and "source_case_id" in cases.columns:
        cases["case_id"] = cases["source_case_id"]
    return cases.reset_index(drop=True)


def _merge_for_delta(py_df: pd.DataFrame, baseline_df: pd.DataFrame | None) -> tuple[pd.DataFrame, list[str]]:
    if baseline_df is None or baseline_df.empty:
        return pd.DataFrame(), []
    candidates = []
    if "case_id" in py_df.columns and "case_id" in baseline_df.columns:
        candidates.append(["case_id"])
    if all(c in py_df.columns for c in ["source_case_id", "rx_azimuth_deg"]) and all(c in baseline_df.columns for c in ["source_case_id", "rx_azimuth_deg"]):
        candidates.append(["source_case_id", "rx_azimuth_deg"])
    for keys in candidates:
        merged = py_df.merge(baseline_df, on=keys, suffixes=("_py", "_matlab"))
        if not merged.empty:
            return merged, keys
    if "seed_case_id" in py_df.columns and "source_case_id" in baseline_df.columns:
        left = py_df.rename(columns={"seed_case_id": "_merge_source_case_id"})
        right = baseline_df.rename(columns={"source_case_id": "_merge_source_case_id"})
        merged = left.merge(right, on="_merge_source_case_id", suffixes=("_py", "_matlab"))
        if not merged.empty:
            return merged, ["seed_case_id", "source_case_id"]
    return pd.DataFrame(), []


def _python_feature_view(py_df: pd.DataFrame) -> pd.DataFrame:
    feature_cols = CANONICAL_FEATURE_NAMES + CP16_FEATURE_NAMES
    keep = [
        c
        for c in [
            "case_id",
            "source_case_id",
            "seed_case_id",
            "rx_azimuth_deg",
            "snr_db",
            "room_type",
            "room_type_cases_tbl",
            "room_type_results_tbl",
            "dominant_wall_material",
            "dominant_wall_material_cases_tbl",
            "source_lineage",
        ]
        if c in py_df.columns
    ]
    out = py_df[keep].copy()
    for col in feature_cols:
        generated = f"{col}_py"
        if generated in py_df.columns:
            values = py_df.loc[:, generated]
            out[col] = values.iloc[:, -1] if isinstance(values, pd.DataFrame) else values
        elif col in py_df.columns:
            values = py_df.loc[:, col]
            out[col] = values.iloc[:, -1] if isinstance(values, pd.DataFrame) else values
    for col in [
        "failed",
        "error_msg",
        "idx_fp",
        "cp16_idx_same_fp",
        "cp16_idx_rev_fp",
        "num_paths",
        "bounce_count_min",
        "bounce_count_max",
        "has_los_path",
        "is_los",
        "is_nlos",
        "tx_rx_dist_m",
        "material_kind",
        "tx_hand",
        "rx_port_order",
    ]:
        generated = f"{col}_py"
        if generated in py_df.columns:
            values = py_df.loc[:, generated]
            out[col] = values.iloc[:, -1] if isinstance(values, pd.DataFrame) else values
        elif col in py_df.columns:
            values = py_df.loc[:, col]
            out[col] = values.iloc[:, -1] if isinstance(values, pd.DataFrame) else values
    return out


def _near_tolerance(column: str) -> float:
    if column in {"num_significant_peaks"}:
        return 1.0
    if column == "peak_to_avg_ratio":
        return 3.5
    if column == "kurtosis_total":
        return 3.0
    if column in {"fp_kurtosis", "skewness_total", "a_fp_6_fp_to_2nd_peak"}:
        return 0.5
    if column in {"xpr_fp_db", "delta_p_l_given_r_db"}:
        return 2.5
    if column in {"xpr_late_db", "gamma_cp_2_freq_db"}:
        return 1.5
    if column == "xpr_all_db":
        return 0.75
    if column in {"cp_phase_residual_circvar", "gamma_cp_6_phase_circvar"}:
        return 1.0
    if column in {"gamma_delay_linear", "gamma_anchor_linear", "gamma_cp_1_freq_avg"}:
        return 0.5
    if column.endswith("_s") or "delay" in column or "tau" in column:
        return 5e-9
    if column in {"s3_fp", "gamma_cp_3_fp_only"}:
        return 0.075
    if column in {
        "s3_late",
        "s3_all",
        "a_fp_2_peak_to_total",
        "fp_to_total_ratio",
        "k_factor_estimate",
        "f_r_fp",
        "f_l_fp",
        "delta_f_l_minus_r_fp",
        "lambda_l_late_fraction",
        "energy_concentration_50ns",
    }:
        return 0.05
    return 0.05


def _numeric_delta_table(py_df: pd.DataFrame, baseline_df: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    rows = []
    feature_cols = [c for c in CANONICAL_FEATURE_NAMES + CP16_FEATURE_NAMES if c in py_df.columns]
    if baseline_df is None or baseline_df.empty:
        for col in feature_cols:
            rows.append({"column": col, "baseline_available": False, "max_abs_delta": np.nan, "mean_abs_delta": np.nan, "strict_pass": False, "near_tolerance": _near_tolerance(col), "near_pass": False, "pass": False})
        return pd.DataFrame(rows), pd.DataFrame(), []
    merged, merge_keys = _merge_for_delta(py_df, baseline_df)
    if merged.empty:
        for col in feature_cols:
            rows.append({"column": col, "baseline_available": col in baseline_df.columns, "max_abs_delta": np.nan, "mean_abs_delta": np.nan, "strict_pass": False, "near_tolerance": _near_tolerance(col), "near_pass": False, "pass": False})
        return pd.DataFrame(rows), merged, merge_keys
    for col in feature_cols:
        py_col = f"{col}_py"
        if py_col not in merged and col in merged:
            py_col = col
        ml_col = f"{col}_matlab"
        if ml_col not in merged and col in baseline_df.columns and col in merged:
            ml_col = col
        if ml_col not in merged:
            for prefix in ("ant1_", "source_", "matlab_"):
                candidate = f"{prefix}{col}"
                if candidate in baseline_df.columns and candidate in merged.columns:
                    ml_col = candidate
                    break
        if py_col not in merged or ml_col not in merged:
            rows.append({"column": col, "baseline_available": False, "max_abs_delta": np.nan, "mean_abs_delta": np.nan, "strict_pass": False, "near_tolerance": _near_tolerance(col), "near_pass": False, "pass": False})
            continue
        py_values = merged.loc[:, py_col]
        ml_values = merged.loc[:, ml_col]
        if isinstance(py_values, pd.DataFrame):
            py_values = py_values.iloc[:, -1]
        if isinstance(ml_values, pd.DataFrame):
            ml_values = ml_values.iloc[:, -1]
        delta = (pd.to_numeric(py_values, errors="coerce") - pd.to_numeric(ml_values, errors="coerce")).abs()
        strict_pass = bool(delta.max() <= 1e-6)
        near_tol = _near_tolerance(col)
        rows.append({"column": col, "baseline_available": True, "max_abs_delta": float(delta.max()), "mean_abs_delta": float(delta.mean()), "strict_pass": strict_pass, "near_tolerance": near_tol, "near_pass": bool(strict_pass or delta.max() <= near_tol), "pass": strict_pass})
    return pd.DataFrame(rows), merged, merge_keys


def _downstream_auc_delta(merged: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame()
    label_col = "is_nlos_matlab" if "is_nlos_matlab" in merged.columns else "is_nlos"
    if label_col not in merged.columns:
        return pd.DataFrame(), pd.DataFrame()
    rows = []
    for set_name, cols in [
        ("canonical18", CANONICAL_FEATURE_NAMES),
        ("cp16", CP16_FEATURE_NAMES),
        ("joint34", CANONICAL_FEATURE_NAMES + CP16_FEATURE_NAMES),
    ]:
        py_cols = [f"{c}_py" for c in cols if f"{c}_py" in merged.columns and f"{c}_matlab" in merged.columns]
        ml_cols = [f"{c}_matlab" for c in cols if f"{c}_py" in merged.columns and f"{c}_matlab" in merged.columns]
        for side, side_cols, suffix_len in [("python", py_cols, 3), ("matlab", ml_cols, 7)]:
            if not side_cols:
                continue
            df = merged[side_cols + [label_col]].copy()
            rename = {c: c[:-suffix_len] for c in side_cols}
            rename[label_col] = "is_nlos"
            df = df.rename(columns=rename)
            feat_cols = [rename[c] for c in side_cols]
            try:
                result = cv_logistic_auc(df, feat_cols, label_col="is_nlos", folds=5, random_state=0)
            except Exception:
                continue
            rows.append({
                "feature_set": set_name,
                "side": side,
                "auc_mean": result.auc_mean,
                "auc_std": result.auc_std,
                "n_rows": result.n_rows,
                "n_features": result.n_features,
            })
    auc_by_side = pd.DataFrame(rows)
    if auc_by_side.empty:
        return auc_by_side, pd.DataFrame()
    auc_delta = auc_by_side.pivot(index="feature_set", columns="side", values="auc_mean").reset_index()
    if "python" in auc_delta.columns and "matlab" in auc_delta.columns:
        auc_delta["delta_python_minus_matlab"] = auc_delta["python"] - auc_delta["matlab"]
    return auc_by_side, auc_delta


def _merged_series(merged: pd.DataFrame, base: str, side: str | None = None) -> pd.Series:
    candidates: list[str] = []
    if side:
        candidates.append(f"{base}_{side}")
    candidates.extend([base, f"matlab_{base}", f"source_{base}", f"ant1_{base}"])
    for col in candidates:
        if col in merged.columns:
            values = merged.loc[:, col]
            if isinstance(values, pd.DataFrame):
                values = values.iloc[:, -1]
            return values
    return pd.Series([np.nan] * len(merged), index=merged.index)


def _numeric_merged_series(merged: pd.DataFrame, base: str, side: str | None = None) -> pd.Series:
    return pd.to_numeric(_merged_series(merged, base, side), errors="coerce")


def _diagnostic_delta_tables(merged: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    diag = pd.DataFrame(index=merged.index)
    for col in ["case_id", "source_case_id", "seed_case_id", "rx_azimuth_deg"]:
        diag[col] = _merged_series(merged, col)
    diag["snr_db"] = _numeric_merged_series(merged, "snr_db", "matlab")
    if diag["snr_db"].isna().all():
        diag["snr_db"] = _numeric_merged_series(merged, "snr_db")
    diag["room_type"] = _merged_series(merged, "room_type", "matlab")
    if diag["room_type"].isna().all():
        diag["room_type"] = _merged_series(merged, "room_type_results_tbl")
    diag["dominant_wall_material"] = _merged_series(merged, "dominant_wall_material", "matlab")
    if diag["dominant_wall_material"].isna().all():
        diag["dominant_wall_material"] = _merged_series(merged, "dominant_wall_material_cases_tbl")

    key_features = [
        "delta_p_l_given_r_db",
        "xpr_fp_db",
        "xpr_all_db",
        "peak_to_avg_ratio",
        "kurtosis_total",
        "cp_phase_residual_circvar",
        "gamma_cp_3_fp_only",
    ]
    for col in key_features:
        py = _numeric_merged_series(merged, col, "py")
        ml = _numeric_merged_series(merged, col, "matlab")
        diag[f"{col}_py"] = py
        diag[f"{col}_matlab"] = ml
        diag[f"{col}_abs_delta"] = (py - ml).abs()

    for col in ["num_paths", "idx_fp", "cp16_idx_same_fp", "cp16_idx_rev_fp"]:
        py = _numeric_merged_series(merged, col, "py")
        ml = _numeric_merged_series(merged, col, "matlab")
        diag[f"{col}_py"] = py
        diag[f"{col}_matlab"] = ml
        valid = py.notna() & ml.notna()
        diag[f"{col}_mismatch"] = valid & (py.round().astype("Int64") != ml.round().astype("Int64"))

    delta_cols = [f"{col}_abs_delta" for col in key_features]
    diag["max_key_feature_abs_delta"] = diag[delta_cols].max(axis=1)
    diag["snr_bin"] = pd.cut(
        diag["snr_db"],
        bins=[-np.inf, 15.0, 20.0, 25.0, 30.0, np.inf],
        labels=["<=15", "15-20", "20-25", "25-30", ">30"],
    )

    rows = []
    for snr_bin, group in diag.groupby("snr_bin", dropna=False, observed=False):
        row = {
            "snr_bin": str(snr_bin),
            "n_cases": int(len(group)),
            "mean_snr_db": float(group["snr_db"].mean()) if group["snr_db"].notna().any() else np.nan,
        }
        for col in ["num_paths", "idx_fp", "cp16_idx_same_fp", "cp16_idx_rev_fp"]:
            mm = group[f"{col}_mismatch"].fillna(False)
            row[f"{col}_mismatch_count"] = int(mm.sum())
        for col in key_features:
            d = group[f"{col}_abs_delta"]
            row[f"{col}_mean_abs_delta"] = float(d.mean()) if d.notna().any() else np.nan
            row[f"{col}_max_abs_delta"] = float(d.max()) if d.notna().any() else np.nan
        rows.append(row)
    by_snr = pd.DataFrame(rows)

    worst_cols = [
        "case_id",
        "source_case_id",
        "seed_case_id",
        "rx_azimuth_deg",
        "snr_db",
        "snr_bin",
        "room_type",
        "dominant_wall_material",
        "num_paths_py",
        "num_paths_matlab",
        "num_paths_mismatch",
        "idx_fp_py",
        "idx_fp_matlab",
        "idx_fp_mismatch",
        "cp16_idx_same_fp_py",
        "cp16_idx_same_fp_matlab",
        "cp16_idx_same_fp_mismatch",
        "cp16_idx_rev_fp_py",
        "cp16_idx_rev_fp_matlab",
        "cp16_idx_rev_fp_mismatch",
        "max_key_feature_abs_delta",
    ] + delta_cols
    worst = diag.sort_values("max_key_feature_abs_delta", ascending=False)[[c for c in worst_cols if c in diag.columns]].head(30)
    summary = {
        "diagnostic_cases": int(len(diag)),
        "diagnostic_path_count_mismatch": int(diag["num_paths_mismatch"].fillna(False).sum()),
        "diagnostic_idx_fp_mismatch": int(diag["idx_fp_mismatch"].fillna(False).sum()),
        "diagnostic_cp16_same_idx_mismatch": int(diag["cp16_idx_same_fp_mismatch"].fillna(False).sum()),
        "diagnostic_cp16_rev_idx_mismatch": int(diag["cp16_idx_rev_fp_mismatch"].fillna(False).sum()),
    }
    return by_snr, worst, summary


def find_latest_baseline_csv(baseline_root: Path, exclude_root: Path | None = None) -> Path | None:
    if not baseline_root.exists():
        return None
    candidates = []
    for pattern in ("stage3_*20260508*.csv", "azimuth_rx_yaw_h10b_*20260508*.csv", "dual_tag_h10b_*20260508*.csv", "sweep*.csv", "*features*.csv"):
        candidates.extend(baseline_root.rglob(pattern))
    exclude_resolved = exclude_root.resolve() if exclude_root is not None and exclude_root.exists() else None
    csvs = []
    for p in candidates:
        if not p.is_file() or p.stat().st_size <= 0:
            continue
        parts = {part.lower() for part in p.parts}
        if any(
            part.startswith("python_parity")
            or part.startswith("python_server_parity")
            or part.startswith("python_full_migration")
            or part.startswith("python_operation")
            or part.startswith("python_script_replacements")
            or part.startswith("matlab_raw_parity")
            for part in parts
        ):
            continue
        if exclude_resolved is not None:
            try:
                p.resolve().relative_to(exclude_resolved)
                continue
            except ValueError:
                pass
        csvs.append(p)
    if not csvs:
        return None
    return max(csvs, key=lambda p: p.stat().st_mtime)


def run_parity_suite(
    baseline_root: str | Path,
    out_dir: str | Path,
    cases_csv: str | Path | None = None,
    baseline_csv: str | Path | None = None,
    max_cases: int = 30,
    replay_fp_hints: bool = False,
) -> dict:
    baseline_root = Path(baseline_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = default_config(Path(__file__).resolve().parents[1])
    cfg.replay_fp_hints = bool(replay_fp_hints)
    baseline_csv = Path(baseline_csv) if baseline_csv else find_latest_baseline_csv(baseline_root, out_dir)
    baseline_df = None
    if baseline_csv is not None:
        try:
            baseline_df = pd.read_csv(baseline_csv)
        except Exception:
            baseline_df = None
    cases = pd.read_csv(cases_csv) if cases_csv else _select_baseline_cases(baseline_df, max_cases=max_cases)
    py_df = run_sweep_batch(cases, cfg, verbose=False)
    py_out = out_dir / "python_representative_features.csv"
    py_df.to_csv(py_out, index=False)
    py_compare_df = _python_feature_view(py_df)
    feat_delta, merged_delta, merge_keys = _numeric_delta_table(py_compare_df, baseline_df)
    feat_delta.to_csv(out_dir / "feature_delta_table.csv", index=False)
    auc_by_side, auc_delta = _downstream_auc_delta(merged_delta)
    if not auc_by_side.empty:
        auc_by_side.to_csv(out_dir / "downstream_auc_by_side.csv", index=False)
    if not auc_delta.empty:
        auc_delta.to_csv(out_dir / "downstream_auc_delta_table.csv", index=False)
    diagnostic_summary = {}
    if not merged_delta.empty:
        merged_delta.to_csv(out_dir / "matched_python_matlab_rows.csv", index=False)
        by_snr, worst_cases, diagnostic_summary = _diagnostic_delta_tables(merged_delta)
        if not by_snr.empty:
            by_snr.to_csv(out_dir / "diagnostic_delta_by_snr.csv", index=False)
        if not worst_cases.empty:
            worst_cases.to_csv(out_dir / "diagnostic_worst_cases.csv", index=False)
    max_auc_delta = float(auc_delta["delta_python_minus_matlab"].abs().max()) if "delta_python_minus_matlab" in auc_delta.columns else np.nan
    metric_rows = [
        {"metric": "python_cases", "value": len(py_df)},
        {"metric": "python_failed_cases", "value": int(pd.Series(py_df.get("failed", [])).fillna(False).astype(bool).sum())},
        {"metric": "baseline_csv_found", "value": bool(baseline_csv is not None)},
        {"metric": "baseline_cases", "value": int(0 if baseline_df is None else len(baseline_df))},
        {"metric": "merged_cases", "value": int(len(merged_delta))},
        {"metric": "merge_keys", "value": ",".join(merge_keys)},
        {"metric": "feature_columns_checked", "value": int(len(feat_delta))},
        {"metric": "feature_columns_passed", "value": int(feat_delta.get("pass", pd.Series(dtype=bool)).fillna(False).sum())},
        {"metric": "feature_columns_near_passed", "value": int(feat_delta.get("near_pass", pd.Series(dtype=bool)).fillna(False).sum())},
        {"metric": "downstream_auc_sets", "value": int(len(auc_delta))},
        {"metric": "downstream_auc_max_abs_delta", "value": max_auc_delta},
        {"metric": "replay_fp_hints", "value": bool(replay_fp_hints)},
    ]
    metric_rows.extend({"metric": key, "value": value} for key, value in diagnostic_summary.items())
    metric_delta = pd.DataFrame(metric_rows)
    metric_delta.to_csv(out_dir / "metric_delta_table.csv", index=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "python": sys.version,
        "baseline_root": str(baseline_root),
        "baseline_csv": str(baseline_csv) if baseline_csv else None,
        "python_output": str(py_out),
        "package_root": str(Path(__file__).resolve().parents[0]),
        "git_commit": _git_commit(),
        "max_cases": int(max_cases),
        "replay_fp_hints": bool(replay_fp_hints),
        "python_output_sha256": sha256_file(py_out),
    }
    (out_dir / "server_run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summary = _summary_text(manifest, metric_delta, feat_delta)
    (out_dir / "python_vs_matlab_parity_summary.md").write_text(summary, encoding="utf-8")
    return manifest


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True).strip()
    except Exception:
        return None


def _summary_text(manifest: dict, metric_delta: pd.DataFrame, feat_delta: pd.DataFrame) -> str:
    failed = int(metric_delta.loc[metric_delta.metric == "python_failed_cases", "value"].iloc[0])
    baseline_found = bool(metric_delta.loc[metric_delta.metric == "baseline_csv_found", "value"].iloc[0])
    merged_cases = int(metric_delta.loc[metric_delta.metric == "merged_cases", "value"].iloc[0])
    merge_keys = str(metric_delta.loc[metric_delta.metric == "merge_keys", "value"].iloc[0])
    checked = int(metric_delta.loc[metric_delta.metric == "feature_columns_checked", "value"].iloc[0])
    passed = int(metric_delta.loc[metric_delta.metric == "feature_columns_passed", "value"].iloc[0])
    near_passed = int(metric_delta.loc[metric_delta.metric == "feature_columns_near_passed", "value"].iloc[0])
    auc_rows = int(metric_delta.loc[metric_delta.metric == "downstream_auc_sets", "value"].iloc[0])
    auc_delta = metric_delta.loc[metric_delta.metric == "downstream_auc_max_abs_delta", "value"].iloc[0]
    if not baseline_found or merged_cases == 0:
        verdict = "ALIGNMENT_FAILED"
    else:
        verdict = "PASS" if failed == 0 and checked == passed else ("NEAR_PASS" if failed == 0 and checked == near_passed else "NEEDS_REVIEW")
    return "\n".join(
        [
            "# Python vs MATLAB Parity Summary",
            "",
            f"- Verdict: `{verdict}`",
            f"- Host: `{manifest['host']}`",
            f"- Baseline CSV: `{manifest['baseline_csv']}`",
            f"- Python output: `{manifest['python_output']}`",
            f"- Python failed cases: `{failed}`",
            f"- Matched cases: `{merged_cases}`",
            f"- Merge keys: `{merge_keys}`",
            f"- Feature columns passed: `{passed}/{checked}`",
            f"- Feature columns near-pass: `{near_passed}/{checked}`",
            f"- Downstream AUC sets: `{auc_rows}`",
            f"- Downstream max |Delta AUC|: `{auc_delta}`",
            f"- Replay FP hints: `{manifest.get('replay_fp_hints', False)}`",
            "",
            "See `feature_delta_table.csv`, `metric_delta_table.csv`, `diagnostic_delta_by_snr.csv`, `diagnostic_worst_cases.csv`, and `server_run_manifest.json` for evidence.",
            "",
        ]
    )
