from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from rt_cp_uwb_py.feature_discovery import (
    SplitSpec,
    build_outer_splits,
    load_merged_tables,
    make_model,
    model_scores,
    numeric_frame,
    read_yaml,
    safe_auc,
    safe_balanced_accuracy,
    safe_pr_auc,
    score_to_probability,
    stable_seed,
    target_mask,
    target_specs,
)
from rt_cp_uwb_py.theme1_rich_feature_sets import (
    ACCEPTED_RATIOS,
    DEFAULT_CONFIG as RICH_DEFAULT_CONFIG,
    DEFAULT_RICH_ROOT,
    DEFAULT_SOURCE_ROOT,
    LABEL_COLS,
    PRIMARY_MODEL,
    audit_feature_sets,
    feature_set_definitions,
    label_frame,
    load_labels_from_config,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "results" / "THEME1_SUBMISSION_STRENGTHENING_20260629"
NEGATIVE_PANELS = ["CIR5+CP6", "CIR5+CP11_mech", "CIR12+CP6", "CIR12+CP11_mech"]
LEAVE_PANELS = ["CIR5", "CIR12", *NEGATIVE_PANELS]
SNR_BASELINES = {
    "SNR_ONLY": ["snr_db"],
    "FP_POWER_ONLY": ["fp_peak_val"],
    "SNR+FP_POWER": ["snr_db", "fp_peak_val"],
    "FP_CIR_DIAGNOSTIC": ["idx_fp", "t_fp_s", "fp_peak_val", "snr_db"],
}
CP_FEATURE_POOL = {
    "xpr_fp_db",
    "xpr_late_db",
    "xpr_all_db",
    "s3_fp",
    "s3_late",
    "s3_all",
    "delta_p_l_given_r_db",
    "f_r_fp",
    "f_l_fp",
    "lambda_l_late_fraction",
    "cp_phase_slope_delay_s",
    "cp_phase_residual_circvar",
    "delta_tau_l_given_r_s",
    "delta_f_l_minus_r_fp",
    "gamma_anchor_linear",
    "gamma_delay_linear",
}
REPORT_CLAIM_BOUNDARY = (
    "Simulation-only channel-state/q_clean evidence. q_clean is clean-session/session-quality "
    "confidence only; no measurement transfer, backend utility, localization accuracy, or direct "
    "range-error reduction is established."
)


@dataclass(frozen=True)
class SourcePaths:
    source_root: Path
    rich_root: Path
    config_path: Path
    feature_table: Path
    label_table: Path
    split_table: Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_path(path: str | Path | None, default: Path) -> Path:
    if path is None:
        return default
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: str | Path, root: Path = ROOT) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return "MISSING"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_row_count(path: Path) -> str:
    if not path.exists() or path.suffix.lower() != ".csv":
        return ""
    with path.open("rb") as f:
        return str(max(0, sum(1 for _ in f) - 1))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["status"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: Any) -> float:
    try:
        out = float(value)
    except Exception:
        return float("nan")
    return out


def prepare_stage_dir(out_root: Path, stage_name: str, overwrite_stage: bool = False) -> Path:
    stage_dir = out_root / stage_name
    if stage_dir.exists() and any(stage_dir.iterdir()) and not overwrite_stage:
        raise FileExistsError(f"Stage output exists; pass --overwrite-stage to replace: {stage_dir}")
    if overwrite_stage and stage_dir.exists():
        for path in sorted(stage_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    stage_dir.mkdir(parents=True, exist_ok=True)
    return stage_dir


def resolve_source_paths(
    source_root: str | Path | None = None,
    rich_root: str | Path | None = None,
    config_path: str | Path | None = None,
) -> SourcePaths:
    src = as_path(source_root, DEFAULT_SOURCE_ROOT).resolve()
    rich = as_path(rich_root, DEFAULT_RICH_ROOT).resolve()
    cfg = as_path(config_path, src / "04_feature_discovery" / "configs" / "feature_discovery_theme1_20260628.yaml").resolve()
    if cfg.exists():
        config = read_yaml(cfg)
        inputs = config.get("inputs", {})
        feature_table = as_path(inputs.get("feature_table"), src / "02_rt_fullrun" / "feature_table.csv").resolve()
        label_table = as_path(inputs.get("label_table"), src / "02_rt_fullrun" / "label_table.csv").resolve()
        split_table = as_path(inputs.get("split_table"), src / "03_source_freeze" / "theme1_split_manifest.csv").resolve()
    else:
        feature_table = src / "02_rt_fullrun" / "feature_table.csv"
        label_table = src / "02_rt_fullrun" / "label_table.csv"
        split_table = src / "03_source_freeze" / "theme1_split_manifest.csv"
    return SourcePaths(src, rich, cfg, feature_table, label_table, split_table)


def output_root(path: str | Path | None = None) -> Path:
    return as_path(path, DEFAULT_OUTPUT_ROOT).resolve()


def load_config(paths: SourcePaths) -> dict:
    if not paths.config_path.exists():
        raise FileNotFoundError(paths.config_path)
    return read_yaml(paths.config_path)


def load_dataset(paths: SourcePaths, max_rows: int | None = None) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    config = load_config(paths)
    df = load_merged_tables(config, max_rows=max_rows)
    labels = load_labels_from_config(config)
    return config, df, labels


def load_rich_qclean(paths: SourcePaths) -> tuple[pd.DataFrame, pd.DataFrame]:
    q2_path = paths.rich_root / "05_qclean_feature_set_tables" / "feature_set_qclean_path2h.csv"
    q3_path = paths.rich_root / "05_qclean_feature_set_tables" / "feature_set_qclean_path3h.csv"
    if not q2_path.exists() or not q3_path.exists():
        raise FileNotFoundError(f"Missing rich q_clean files under {paths.rich_root}")
    q2 = pd.read_csv(q2_path)
    q3 = pd.read_csv(q3_path)
    return q2, q3


def selector_value(row: pd.Series | dict[str, Any]) -> str:
    feature_set = str(row.get("feature_set", "unknown"))
    for col in ["control_type", "baseline_type", "analysis_source"]:
        val = row.get(col, "")
        if pd.notna(val) and str(val):
            return f"{val}:{feature_set}"
    return feature_set


def qclean_from_predictions_preserve(predictions: pd.DataFrame, model_name: str = PRIMARY_MODEL) -> tuple[pd.DataFrame, pd.DataFrame]:
    def col(name: str) -> pd.Series:
        key = f"{model_name}_{name}"
        if key not in predictions.columns:
            return pd.Series(np.nan, index=predictions.index)
        return pd.Series(score_to_probability(pd.to_numeric(predictions[key], errors="coerce").to_numpy()), index=predictions.index)

    base_cols = [
        "row_index",
        "case_id",
        "outer_split",
        "split_name",
        "heldout_key",
        "heldout_value",
        "feature_set",
        "features",
        "feature_status",
        "model",
        "control_type",
        "baseline_type",
        "analysis_source",
    ]
    base = predictions[[c for c in base_cols if c in predictions.columns]].copy()
    if "selector" not in base.columns:
        base["selector"] = base.apply(selector_value, axis=1)
    p_nolos = col("NoLoS")
    p_rd = col("RDLoS")
    p_hbnear = col("HBnear")
    p_hbprior = col("HBprior")
    q2 = base.copy()
    q2["p_NoLoS"] = p_nolos
    q2["p_RD"] = p_rd
    q2["q_clean"] = (1.0 - p_nolos) * (1.0 - p_rd)
    q2["qclean_mode"] = "2H"
    q2["score_status"] = f"OUTER_HELDOUT_{model_name}_UNCALIBRATED"
    q3 = base.copy()
    q3["p_NoLoS"] = p_nolos
    q3["p_HBnear"] = p_hbnear
    q3["p_HBprior"] = p_hbprior
    q3["q_clean"] = (1.0 - p_nolos) * (1.0 - p_hbnear) * (1.0 - p_hbprior)
    q3["qclean_mode"] = "3H"
    q3["score_status"] = f"OUTER_HELDOUT_{model_name}_UNCALIBRATED"
    return q2, q3


def same_acceptance_summary(
    q: pd.DataFrame,
    labels: pd.DataFrame,
    mode: str,
    group_cols: Sequence[str] = ("selector",),
) -> pd.DataFrame:
    joined = q.merge(labels, on="case_id", how="left", validate="many_to_one")
    rows: list[dict[str, Any]] = []
    keys = [c for c in group_cols if c in joined.columns]
    if not keys:
        keys = ["feature_set"]
    for key_vals, part0 in joined.groupby(keys, dropna=False):
        if not isinstance(key_vals, tuple):
            key_vals = (key_vals,)
        context = {k: v for k, v in zip(keys, key_vals)}
        part0 = part0.sort_values("q_clean", ascending=False, na_position="last").reset_index(drop=True)
        n_total = len(part0)
        for ratio in ACCEPTED_RATIOS:
            n_accept = max(1, int(round(n_total * ratio)))
            part = part0.head(n_accept)
            row: dict[str, Any] = {
                **context,
                "qclean_mode": mode,
                "accepted_ratio": ratio,
                "n_total": n_total,
                "n_accepted": int(len(part)),
                "q_clean_threshold_min": float(part["q_clean"].min(skipna=True)),
                "q_clean_mean_selected": float(part["q_clean"].mean(skipna=True)),
            }
            if "feature_set" not in row and "feature_set" in part.columns:
                row["feature_set"] = str(part["feature_set"].iloc[0])
            for col in LABEL_COLS:
                row[f"{col}_rate"] = float(part[col].mean())
                row[f"{col}_count"] = int(part[col].sum())
            rows.append(row)
    return pd.DataFrame(rows)


def pairwise_delta_from_same(
    same: pd.DataFrame,
    pairs: Sequence[tuple[str, str]],
    context_cols: Sequence[str] = (),
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for base, candidate in pairs:
        context_groups = [()] if not context_cols else same[list(context_cols)].drop_duplicates().itertuples(index=False, name=None)
        for context_values in context_groups:
            part = same.copy()
            context: dict[str, Any] = {}
            if context_cols:
                for col, value in zip(context_cols, context_values):
                    part = part[part[col].eq(value)]
                    context[col] = value
            for mode in sorted(part["qclean_mode"].dropna().astype(str).unique()):
                for ratio in ACCEPTED_RATIOS:
                    b = part[part["selector"].eq(base) & part["qclean_mode"].eq(mode) & np.isclose(pd.to_numeric(part["accepted_ratio"]), ratio)]
                    c = part[part["selector"].eq(candidate) & part["qclean_mode"].eq(mode) & np.isclose(pd.to_numeric(part["accepted_ratio"]), ratio)]
                    status = "PASS" if not b.empty and not c.empty else "MISSING_QCLEAN_SOURCE"
                    row: dict[str, Any] = {
                        **context,
                        "baseline_selector": base,
                        "candidate_selector": candidate,
                        "qclean_mode": mode,
                        "accepted_ratio": ratio,
                        "status": status,
                    }
                    if status == "PASS":
                        brow = b.iloc[0]
                        crow = c.iloc[0]
                        for col in LABEL_COLS:
                            row[f"baseline_{col}_rate"] = float(brow[f"{col}_rate"])
                            row[f"candidate_{col}_rate"] = float(crow[f"{col}_rate"])
                            row[f"delta_candidate_minus_baseline_{col}_rate"] = float(crow[f"{col}_rate"] - brow[f"{col}_rate"])
                    rows.append(row)
    return pd.DataFrame(rows)


def _target_metric_row(spec: Any, model_name: str, status: str, n: int = 0, n_pos: Any = np.nan) -> dict[str, Any]:
    return {
        "target": spec.name,
        "model": model_name,
        "AUC": np.nan,
        "PR_AUC": np.nan,
        "balanced_accuracy": np.nan,
        "n": int(n),
        "n_pos": n_pos,
        "fit_status": status,
    }


def residualized_frames(
    df: pd.DataFrame,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    cir_features: Sequence[str],
    cp_features: Sequence[str],
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    x_train_cir = numeric_frame(df.iloc[train_idx], cir_features).reset_index(drop=True)
    x_test_cir = numeric_frame(df.iloc[test_idx], cir_features).reset_index(drop=True)
    x_train_cir.index = train_idx
    x_test_cir.index = test_idx
    train_parts = [x_train_cir]
    test_parts = [x_test_cir]
    x_reg_train = numeric_frame(df.iloc[train_idx], cir_features)
    x_reg_test = numeric_frame(df.iloc[test_idx], cir_features)
    for cp in cp_features:
        y_train = pd.to_numeric(df.iloc[train_idx][cp], errors="coerce")
        y_test = pd.to_numeric(df.iloc[test_idx][cp], errors="coerce")
        col = f"resid_{cp}"
        if y_train.notna().sum() < 3:
            tr = pd.Series(np.nan, index=train_idx, name=col)
            te = pd.Series(np.nan, index=test_idx, name=col)
        else:
            reg = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))
            reg.fit(x_reg_train, y_train.fillna(float(y_train.median())))
            tr = pd.Series(y_train.to_numpy(dtype=float) - reg.predict(x_reg_train), index=train_idx, name=col)
            te = pd.Series(y_test.to_numpy(dtype=float) - reg.predict(x_reg_test), index=test_idx, name=col)
        train_parts.append(tr.to_frame())
        test_parts.append(te.to_frame())
    x_train = pd.concat(train_parts, axis=1)
    x_test = pd.concat(test_parts, axis=1)
    return x_train, x_test, list(x_train.columns)


def panel_components(config: dict, panel: str) -> tuple[list[str], list[str], list[str]]:
    defs = feature_set_definitions(config, [panel], "forced")
    features = defs.get(panel, [])
    cp_features = [f for f in features if f in CP_FEATURE_POOL or f.startswith(("xpr_", "s3_", "gamma_", "delta_p_l", "f_l", "lambda_", "cp_"))]
    cir_features = [f for f in features if f not in cp_features]
    return features, cir_features, cp_features


def fit_predict_outer_control(
    df: pd.DataFrame,
    split: SplitSpec,
    features: Sequence[str],
    specs: Sequence[Any],
    model_name: str,
    seed: int,
    hgb_iter: int,
    *,
    control_type: str,
    feature_set: str,
    cir_features: Sequence[str] = (),
    cp_features: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    test_idx = split.test_idx
    pred = pd.DataFrame({"row_index": test_idx, "case_id": df.iloc[test_idx]["case_id"].to_numpy()})
    metric_rows: list[dict[str, Any]] = []
    residual_train = residual_test = None
    residual_cols: list[str] = []
    if control_type == "residualized_cp_control":
        residual_train, residual_test, residual_cols = residualized_frames(df, split.train_idx, split.test_idx, cir_features, cp_features, seed)

    for spec in specs:
        scores = np.full(len(test_idx), np.nan, dtype=float)
        mask_all = target_mask(df, spec)
        tr = np.asarray([i for i in split.train_idx if mask_all[i]], dtype=int)
        te = np.asarray([i for i in split.test_idx if mask_all[i]], dtype=int)
        y_train = df.iloc[tr][spec.label_col].astype(bool).astype(int).to_numpy() if len(tr) else np.asarray([])
        y_test = df.iloc[te][spec.label_col].astype(bool).astype(int).to_numpy() if len(te) else np.asarray([])
        if len(tr) < 10 or len(te) < 3:
            metric_rows.append(_target_metric_row(spec, model_name, "INSUFFICIENT_SUPPORT", len(te), int(y_test.sum()) if len(y_test) else 0))
            pred[f"{model_name}_{spec.name}"] = scores
            continue
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            metric_rows.append(_target_metric_row(spec, model_name, "INSUFFICIENT_CLASS_SUPPORT", len(te), int(y_test.sum())))
            pred[f"{model_name}_{spec.name}"] = scores
            continue
        if control_type == "residualized_cp_control":
            assert residual_train is not None and residual_test is not None
            x_train = residual_train.loc[tr, residual_cols]
            x_test = residual_test.loc[te, residual_cols]
            fit_features = residual_cols
        else:
            if not all(f in df.columns for f in features):
                metric_rows.append(_target_metric_row(spec, model_name, "MISSING_FEATURES", len(te), int(y_test.sum())))
                pred[f"{model_name}_{spec.name}"] = scores
                continue
            x_train = numeric_frame(df.iloc[tr], features).reset_index(drop=True)
            x_test = numeric_frame(df.iloc[te], features).reset_index(drop=True)
            fit_features = list(features)
            if control_type == "cp_feature_shuffle_control":
                for cp in cp_features:
                    if cp in x_train.columns:
                        rng_tr = np.random.default_rng(stable_seed(seed, split.name, feature_set, spec.name, cp, "train_shuffle"))
                        rng_te = np.random.default_rng(stable_seed(seed, split.name, feature_set, spec.name, cp, "test_shuffle"))
                        x_train[cp] = rng_tr.permutation(x_train[cp].to_numpy())
                        x_test[cp] = rng_te.permutation(x_test[cp].to_numpy())
            if control_type == "label_permutation_control":
                rng_y = np.random.default_rng(stable_seed(seed, split.name, feature_set, spec.name, "label_permutation"))
                y_train = rng_y.permutation(y_train)
        model = make_model(model_name, stable_seed(seed, control_type, split.name, feature_set, spec.name), hgb_iter=hgb_iter)
        model.fit(x_train.loc[:, fit_features], y_train)
        score_te = model_scores(model, x_test.loc[:, fit_features])
        pos = {idx: j for j, idx in enumerate(test_idx)}
        for idx, score in zip(te, score_te):
            scores[pos[idx]] = score
        metric_rows.append(
            {
                "target": spec.name,
                "model": model_name,
                "AUC": safe_auc(y_test, score_te),
                "PR_AUC": safe_pr_auc(y_test, score_te),
                "balanced_accuracy": safe_balanced_accuracy(y_test, score_te),
                "n": int(len(y_test)),
                "n_pos": int(y_test.sum()),
                "fit_status": "PASS",
            }
        )
        pred[f"{model_name}_{spec.name}"] = scores
    metrics = pd.DataFrame(metric_rows)
    metrics["outer_split"] = split.name
    metrics["feature_set"] = feature_set
    metrics["features"] = ";".join(features)
    metrics["control_type"] = control_type
    metrics["feature_status"] = "PRESENT"
    pred["outer_split"] = split.name
    pred["feature_set"] = feature_set
    pred["features"] = ";".join(features)
    pred["control_type"] = control_type
    pred["feature_status"] = "PRESENT"
    pred["model"] = model_name
    return metrics, pred


def build_source_audit(
    *,
    out_root_arg: str | Path | None = None,
    source_root_arg: str | Path | None = None,
    rich_root_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    paths = resolve_source_paths(source_root_arg, rich_root_arg, config_arg)
    roles = [
        ("source_root", paths.source_root),
        ("rich_root", paths.rich_root),
        ("config", paths.config_path),
        ("feature_table", paths.feature_table),
        ("label_table", paths.label_table),
        ("split_table", paths.split_table),
        ("fullrun_manifest", paths.source_root / "02_rt_fullrun" / "fullrun_manifest.json"),
        ("rich_forced_predictions", paths.rich_root / "04_forced_feature_set_oof" / "feature_set_outer_test_predictions.csv"),
        ("rich_qclean_path2h", paths.rich_root / "05_qclean_feature_set_tables" / "feature_set_qclean_path2h.csv"),
        ("rich_qclean_path3h", paths.rich_root / "05_qclean_feature_set_tables" / "feature_set_qclean_path3h.csv"),
        ("rich_cir_only_qclean_path2h", paths.rich_root / "03_cir_only_oof_qclean" / "cir_only_qclean_scores_path2h.csv"),
    ]
    file_rows: list[dict[str, Any]] = []
    for role, path in roles:
        file_rows.append(
            {
                "role": role,
                "path": rel(path),
                "status": "PRESENT" if path.exists() else "MISSING",
                "bytes": path.stat().st_size if path.exists() and path.is_file() else "",
                "row_count": csv_row_count(path),
                "sha256": sha256_file(path) if path.exists() and path.is_file() else "",
            }
        )
    source_path_rows = [{"role": role, "resolved_path": rel(path), "exists": bool(path.exists())} for role, path in roles]
    column_rows: list[dict[str, Any]] = []
    required_columns = [
        "case_id",
        "space_id",
        "space_type",
        "room_type",
        "snr_db",
        "fp_peak_val",
        "fp_to_total_ratio",
    ]
    config: dict[str, Any] = {}
    if paths.config_path.exists():
        config = read_yaml(paths.config_path)
        for panel in NEGATIVE_PANELS:
            required_columns.extend(panel_components(config, panel)[0])
    feature_rows = label_rows = 0
    if paths.feature_table.exists():
        feature_head = pd.read_csv(paths.feature_table, nrows=5)
        feature_rows = int(csv_row_count(paths.feature_table) or 0)
        for col in list(dict.fromkeys(required_columns)):
            column_rows.append({"column": col, "role": "feature_table", "status": "PRESENT" if col in feature_head.columns else "MISSING"})
    if paths.label_table.exists():
        label_head = pd.read_csv(paths.label_table, nrows=5)
        label_rows = int(csv_row_count(paths.label_table) or 0)
        for col in LABEL_COLS:
            column_rows.append({"column": col, "role": "label_table", "status": "PRESENT" if col in label_head.columns else "MISSING"})
    all_files_present = all(row["status"] == "PRESENT" for row in file_rows)
    all_columns_present = bool(column_rows) and all(row["status"] == "PRESENT" for row in column_rows)
    source_reuse_ok = all_files_present and all_columns_present and feature_rows == 18000 and label_rows == 18000
    source_path_resolution_ok = all(row["exists"] for row in source_path_rows)
    gate_rows = [
        {"gate": "source_reuse_ok", "status": "PASS" if source_reuse_ok else "BLOCKED"},
        {"gate": "source_path_resolution_ok", "status": "PASS" if source_path_resolution_ok else "BLOCKED"},
        {"gate": "rt_rerun_required", "status": "PASS", "value": "false"},
    ]
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "DRY_RUN_OK" if dry_run and source_reuse_ok else ("SOURCE_REUSE_GATE_PASS" if source_reuse_ok else "SOURCE_REUSE_GATE_BLOCKED"),
        "source_root": rel(paths.source_root),
        "rich_root": rel(paths.rich_root),
        "config_path": rel(paths.config_path),
        "feature_rows": feature_rows,
        "label_rows": label_rows,
        "source_reuse_ok": source_reuse_ok,
        "source_path_resolution_ok": source_path_resolution_ok,
        "rt_rerun_required": False,
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    if not dry_run:
        stage = prepare_stage_dir(out, "00_source_snapshot", overwrite_stage)
        write_json(stage / "source_pointer_manifest.json", manifest)
        write_csv(stage / "source_file_hashes.csv", file_rows)
        write_csv(stage / "column_availability_audit.csv", column_rows)
        write_csv(stage / "reuse_gate_table.csv", gate_rows)
        write_csv(stage / "source_path_resolution.csv", source_path_rows)
    if not source_reuse_ok:
        raise RuntimeError(json.dumps(manifest, indent=2))
    return manifest


def _write_qclean_tables(stage: Path, prefix: str, preds: pd.DataFrame, model: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    q2, q3 = qclean_from_predictions_preserve(preds[preds["model"].eq(model)].copy(), model)
    q2.to_csv(stage / f"{prefix}_qclean_path2h.csv", index=False)
    q3.to_csv(stage / f"{prefix}_qclean_path3h.csv", index=False)
    return q2, q3


def build_negative_controls(
    *,
    out_root_arg: str | Path | None = None,
    source_root_arg: str | Path | None = None,
    rich_root_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
    max_rows: int | None = None,
    hgb_iter: int | None = None,
    model: str = PRIMARY_MODEL,
) -> dict[str, Any]:
    paths = resolve_source_paths(source_root_arg, rich_root_arg, config_arg)
    config, df, labels = load_dataset(paths, max_rows=max_rows)
    specs = target_specs(config)
    splits = build_outer_splits(df, split_key=config["inputs"].get("split_key", "split_fold"))
    hgb_iter = int(hgb_iter or config.get("search", {}).get("hgb_iter", 60))
    seed = int(config.get("search", {}).get("seed", 20260610))
    stage = prepare_stage_dir(output_root(out_root_arg), "01_negative_controls", overwrite_stage)
    definitions, missing_audit, forbidden_audit = audit_feature_sets(df, config, feature_set_definitions(config, NEGATIVE_PANELS, "forced"))
    definitions.to_csv(stage / "negative_control_feature_set_definitions.csv", index=False)
    missing_audit.to_csv(stage / "negative_control_missing_feature_audit.csv", index=False)
    forbidden_audit.to_csv(stage / "negative_control_forbidden_feature_audit.csv", index=False)
    metric_parts: list[pd.DataFrame] = []
    pred_parts: list[pd.DataFrame] = []
    for split in splits:
        for panel in NEGATIVE_PANELS:
            features, cir_features, cp_features = panel_components(config, panel)
            if not features or not all(f in df.columns for f in features):
                continue
            for control in ["cp_feature_shuffle_control", "label_permutation_control", "residualized_cp_control"]:
                metrics, preds = fit_predict_outer_control(
                    df,
                    split,
                    features,
                    specs,
                    model,
                    seed,
                    hgb_iter,
                    control_type=control,
                    feature_set=panel,
                    cir_features=cir_features,
                    cp_features=cp_features,
                )
                metric_parts.append(metrics)
                pred_parts.append(preds)
    metrics_all = pd.concat(metric_parts, ignore_index=True) if metric_parts else pd.DataFrame()
    preds_all = pd.concat(pred_parts, ignore_index=True) if pred_parts else pd.DataFrame()
    metrics_all.to_csv(stage / "negative_control_outer_test_results.csv", index=False)
    preds_all.to_csv(stage / "negative_control_outer_test_predictions.csv", index=False)
    q2, q3 = _write_qclean_tables(stage, "negative_control", preds_all, model)
    q2_ref, q3_ref = load_rich_qclean(paths)
    ref_frames = []
    for mode, qref in [("2H", q2_ref), ("3H", q3_ref)]:
        ref = qref[qref["feature_set"].isin(["CIR5", "CIR12", *NEGATIVE_PANELS])].copy()
        ref["control_type"] = np.where(ref["feature_set"].isin(["CIR5", "CIR12"]), "cir_only_reference", "original_reference")
        ref["selector"] = ref.apply(selector_value, axis=1)
        ref["qclean_mode"] = mode
        ref_frames.append(ref)
    q_all = pd.concat([q2, q3, *ref_frames], ignore_index=True, sort=False)
    same = pd.concat(
        [
            same_acceptance_summary(q_all[q_all["qclean_mode"].eq("2H")], labels, "2H"),
            same_acceptance_summary(q_all[q_all["qclean_mode"].eq("3H")], labels, "3H"),
        ],
        ignore_index=True,
    )
    same.to_csv(stage / "negative_control_same_acceptance_state_selection.csv", index=False)
    pairs: list[tuple[str, str]] = []
    for panel in NEGATIVE_PANELS:
        base = "CIR12" if panel.startswith("CIR12") else "CIR5"
        pairs.append((f"cir_only_reference:{base}", f"original_reference:{panel}"))
        for control in ["cp_feature_shuffle_control", "label_permutation_control", "residualized_cp_control"]:
            pairs.append((f"cir_only_reference:{base}", f"{control}:{panel}"))
    delta = pairwise_delta_from_same(same, pairs)
    delta.to_csv(stage / "negative_control_same_acceptance_delta.csv", index=False)
    transform_rows = []
    for panel in NEGATIVE_PANELS:
        features, cir_features, cp_features = panel_components(config, panel)
        for control in ["cp_feature_shuffle_control", "label_permutation_control", "residualized_cp_control"]:
            transform_rows.append(
                {
                    "feature_set": panel,
                    "control_type": control,
                    "features": ";".join(features),
                    "cir_features": ";".join(cir_features),
                    "cp_features": ";".join(cp_features),
                    "seed_policy": "stable_seed(search_seed, split, feature_set, target, control)",
                }
            )
    write_json(stage / "negative_control_feature_transform_manifest.json", {"created_at_utc": now_utc(), "transforms": transform_rows})
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE",
        "prediction_rows": int(len(preds_all)),
        "metric_rows": int(len(metrics_all)),
        "feature_sets": NEGATIVE_PANELS,
        "controls": ["cp_feature_shuffle_control", "label_permutation_control", "residualized_cp_control"],
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "negative_control_run_manifest.json", manifest)
    return manifest


def build_leave_space_splits(df: pd.DataFrame) -> tuple[list[SplitSpec], pd.DataFrame, pd.DataFrame]:
    specs: list[SplitSpec] = []
    manifest_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for key in ["space_id", "space_type"]:
        if key not in df.columns:
            continue
        values = sorted(pd.Series(df[key]).dropna().astype(str).unique().tolist())
        for value in values:
            mask = df[key].astype(str).eq(value).to_numpy()
            test_idx = np.flatnonzero(mask)
            train_idx = np.flatnonzero(~mask)
            if len(test_idx) == 0 or len(train_idx) == 0:
                continue
            split_name = f"leave_{key}_{value}".replace("/", "_").replace(" ", "_")
            specs.append(SplitSpec(split_name, train_idx, test_idx))
            train_cases = set(df.iloc[train_idx]["case_id"].astype(str))
            test_cases = set(df.iloc[test_idx]["case_id"].astype(str))
            train_groups = set(df.iloc[train_idx]["pose_group_id"].astype(str)) if "pose_group_id" in df.columns else set()
            test_groups = set(df.iloc[test_idx]["pose_group_id"].astype(str)) if "pose_group_id" in df.columns else set()
            audit_rows.append(
                {
                    "split_name": split_name,
                    "heldout_key": key,
                    "heldout_value": value,
                    "train_n": int(len(train_idx)),
                    "test_n": int(len(test_idx)),
                    "case_id_overlap_n": len(train_cases.intersection(test_cases)),
                    "pose_group_id_overlap_n": len(train_groups.intersection(test_groups)) if train_groups or test_groups else "",
                    "heldout_value_in_train_n": int((df.iloc[train_idx][key].astype(str) == value).sum()),
                    "status": "PASS" if not train_cases.intersection(test_cases) and int((df.iloc[train_idx][key].astype(str) == value).sum()) == 0 else "FAIL",
                }
            )
            for role, idxs in [("train", train_idx), ("test", test_idx)]:
                part = df.iloc[idxs]
                for _, row in part.iterrows():
                    manifest_rows.append(
                        {
                            "split_name": split_name,
                            "heldout_key": key,
                            "heldout_value": value,
                            "case_id": row.get("case_id", ""),
                            "pose_group_id": row.get("pose_group_id", ""),
                            "split_role": role,
                            "space_id": row.get("space_id", ""),
                            "space_type": row.get("space_type", ""),
                            "room_type": row.get("room_type", ""),
                        }
                    )
    return specs, pd.DataFrame(manifest_rows), pd.DataFrame(audit_rows)


def label_support_table(df: pd.DataFrame, splits: Sequence[SplitSpec], config: dict) -> pd.DataFrame:
    specs = target_specs(config)
    rows: list[dict[str, Any]] = []
    for split in splits:
        if split.name.startswith("leave_space_id_"):
            heldout_key = "space_id"
            heldout_value = split.name.removeprefix("leave_space_id_")
        elif split.name.startswith("leave_space_type_"):
            heldout_key = "space_type"
            heldout_value = split.name.removeprefix("leave_space_type_")
        else:
            heldout_key = ""
            heldout_value = ""
        for role, idxs in [("train", split.train_idx), ("test", split.test_idx)]:
            part = df.iloc[idxs]
            for spec in specs:
                mask = target_mask(part, spec)
                y = part.loc[mask, spec.label_col].astype(bool).astype(int) if spec.label_col in part.columns else pd.Series(dtype=int)
                rows.append(
                    {
                        "split_name": split.name,
                        "heldout_key": heldout_key,
                        "heldout_value": heldout_value,
                        "split_role": role,
                        "target": spec.name,
                        "n": int(len(y)),
                        "n_pos": int(y.sum()) if len(y) else 0,
                        "n_neg": int((1 - y).sum()) if len(y) else 0,
                        "status": "PASS" if len(y) >= 3 and y.nunique() >= 2 else "INSUFFICIENT_SUPPORT",
                    }
                )
    return pd.DataFrame(rows)


def fit_predict_outer_standard(
    df: pd.DataFrame,
    split: SplitSpec,
    features: Sequence[str],
    specs: Sequence[Any],
    model: str,
    seed: int,
    hgb_iter: int,
    feature_set: str,
    extra: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics, preds = fit_predict_outer_control(
        df,
        split,
        features,
        specs,
        model,
        seed,
        hgb_iter,
        control_type="",
        feature_set=feature_set,
        cir_features=[],
        cp_features=[],
    )
    metrics["control_type"] = ""
    preds["control_type"] = ""
    if extra:
        for key, value in extra.items():
            metrics[key] = value
            preds[key] = value
    return metrics, preds


def build_leave_space_out(
    *,
    out_root_arg: str | Path | None = None,
    source_root_arg: str | Path | None = None,
    rich_root_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
    max_rows: int | None = None,
    hgb_iter: int | None = None,
    model: str = PRIMARY_MODEL,
) -> dict[str, Any]:
    paths = resolve_source_paths(source_root_arg, rich_root_arg, config_arg)
    config, df, labels = load_dataset(paths, max_rows=max_rows)
    specs = target_specs(config)
    hgb_iter = int(hgb_iter or config.get("search", {}).get("hgb_iter", 60))
    seed = int(config.get("search", {}).get("seed", 20260610))
    splits, split_manifest, split_audit = build_leave_space_splits(df)
    stage = prepare_stage_dir(output_root(out_root_arg), "02_leave_space_out", overwrite_stage)
    split_manifest.to_csv(stage / "leave_space_split_manifest.csv", index=False)
    split_audit.to_csv(stage / "leave_space_split_audit.csv", index=False)
    support = label_support_table(df, splits, config)
    support.to_csv(stage / "leave_space_label_support.csv", index=False)
    definitions, missing_audit, forbidden_audit = audit_feature_sets(df, config, feature_set_definitions(config, LEAVE_PANELS, "forced"))
    definitions.to_csv(stage / "leave_space_feature_set_definitions.csv", index=False)
    missing_audit.to_csv(stage / "leave_space_missing_feature_audit.csv", index=False)
    forbidden_audit.to_csv(stage / "leave_space_forbidden_feature_audit.csv", index=False)
    metric_parts: list[pd.DataFrame] = []
    pred_parts: list[pd.DataFrame] = []
    for split in splits:
        heldout = split_manifest[split_manifest["split_name"].eq(split.name)].iloc[0]
        extra = {"split_name": split.name, "heldout_key": heldout["heldout_key"], "heldout_value": heldout["heldout_value"]}
        for panel in LEAVE_PANELS:
            features, _, _ = panel_components(config, panel)
            if not features or not all(f in df.columns for f in features):
                continue
            metrics, preds = fit_predict_outer_standard(df, split, features, specs, model, seed, hgb_iter, panel, extra)
            metric_parts.append(metrics)
            pred_parts.append(preds)
    metrics_all = pd.concat(metric_parts, ignore_index=True) if metric_parts else pd.DataFrame()
    preds_all = pd.concat(pred_parts, ignore_index=True) if pred_parts else pd.DataFrame()
    metrics_all.to_csv(stage / "leave_space_outer_test_results.csv", index=False)
    preds_all.to_csv(stage / "leave_space_outer_test_predictions.csv", index=False)
    q2, q3 = _write_qclean_tables(stage, "leave_space", preds_all, model)
    group_cols = ["split_name", "heldout_key", "heldout_value", "selector"]
    same = pd.concat(
        [
            same_acceptance_summary(q2, labels, "2H", group_cols),
            same_acceptance_summary(q3, labels, "3H", group_cols),
        ],
        ignore_index=True,
    )
    same.to_csv(stage / "leave_space_same_acceptance_state_selection.csv", index=False)
    pairs: list[tuple[str, str]] = []
    for panel in NEGATIVE_PANELS:
        base = "CIR12" if panel.startswith("CIR12") else "CIR5"
        pairs.append((base, panel))
    delta = pairwise_delta_from_same(same, pairs, context_cols=["split_name", "heldout_key", "heldout_value"])
    delta.to_csv(stage / "leave_space_same_acceptance_delta.csv", index=False)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE",
        "n_splits": len(splits),
        "prediction_rows": int(len(preds_all)),
        "metric_rows": int(len(metrics_all)),
        "split_audit_status": "PASS" if not split_audit.empty and split_audit["status"].eq("PASS").all() else "CHECK_REQUIRED",
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "leave_space_run_manifest.json", manifest)
    return manifest


def build_snr_fp_baselines(
    *,
    out_root_arg: str | Path | None = None,
    source_root_arg: str | Path | None = None,
    rich_root_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
    max_rows: int | None = None,
    hgb_iter: int | None = None,
    model: str = PRIMARY_MODEL,
) -> dict[str, Any]:
    paths = resolve_source_paths(source_root_arg, rich_root_arg, config_arg)
    config, df, labels = load_dataset(paths, max_rows=max_rows)
    specs = target_specs(config)
    splits = build_outer_splits(df, split_key=config["inputs"].get("split_key", "split_fold"))
    hgb_iter = int(hgb_iter or config.get("search", {}).get("hgb_iter", 60))
    seed = int(config.get("search", {}).get("seed", 20260610))
    stage = prepare_stage_dir(output_root(out_root_arg), "04_snr_fp_baselines", overwrite_stage)
    def_rows = []
    metric_parts: list[pd.DataFrame] = []
    pred_parts: list[pd.DataFrame] = []
    for name, features in SNR_BASELINES.items():
        missing = [f for f in features if f not in df.columns]
        def_rows.append({"feature_set": name, "features": ";".join(features), "n_features": len(features), "feature_status": "PRESENT" if not missing else "MISSING_FEATURES", "missing_features": ";".join(missing)})
        if missing:
            continue
        for split in splits:
            metrics, preds = fit_predict_outer_standard(df, split, features, specs, model, seed, hgb_iter, name, {"baseline_type": "snr_fp_baseline"})
            metric_parts.append(metrics)
            pred_parts.append(preds)
    pd.DataFrame(def_rows).to_csv(stage / "snr_fp_feature_set_definitions.csv", index=False)
    metrics_all = pd.concat(metric_parts, ignore_index=True) if metric_parts else pd.DataFrame()
    preds_all = pd.concat(pred_parts, ignore_index=True) if pred_parts else pd.DataFrame()
    metrics_all.to_csv(stage / "snr_fp_outer_test_results.csv", index=False)
    preds_all.to_csv(stage / "snr_fp_outer_test_predictions.csv", index=False)
    q2, q3 = _write_qclean_tables(stage, "snr_fp", preds_all, model)
    q2_ref, q3_ref = load_rich_qclean(paths)
    refs = []
    for mode, qref in [("2H", q2_ref), ("3H", q3_ref)]:
        ref = qref[qref["feature_set"].isin(["CIR5", "CIR12", *NEGATIVE_PANELS])].copy()
        ref["baseline_type"] = "rich_reference"
        ref["selector"] = ref.apply(selector_value, axis=1)
        ref["qclean_mode"] = mode
        refs.append(ref)
    q_all = pd.concat([q2, q3, *refs], ignore_index=True, sort=False)
    same = pd.concat(
        [
            same_acceptance_summary(q_all[q_all["qclean_mode"].eq("2H")], labels, "2H"),
            same_acceptance_summary(q_all[q_all["qclean_mode"].eq("3H")], labels, "3H"),
        ],
        ignore_index=True,
    )
    same.to_csv(stage / "snr_fp_same_acceptance_state_selection.csv", index=False)
    pairs = []
    for base in SNR_BASELINES:
        for candidate in ["rich_reference:CIR5", "rich_reference:CIR12", "rich_reference:CIR5+CP6", "rich_reference:CIR5+CP11_mech", "rich_reference:CIR12+CP6", "rich_reference:CIR12+CP11_mech"]:
            pairs.append((f"snr_fp_baseline:{base}", candidate))
    delta = pairwise_delta_from_same(same, pairs)
    delta.to_csv(stage / "snr_fp_same_acceptance_pairwise.csv", index=False)
    snr_sufficient = "NOT_SUPPORTED"
    if not delta.empty:
        target_cols = [c for c in delta.columns if c.startswith("delta_candidate_minus_baseline_") and ("RD-LoS_rate" in c or "HB-prior_rate" in c)]
        if target_cols and (delta[target_cols].apply(pd.to_numeric, errors="coerce") <= 0).all().all():
            snr_sufficient = "PASS"
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE",
        "prediction_rows": int(len(preds_all)),
        "metric_rows": int(len(metrics_all)),
        "snr_only_sufficient": snr_sufficient,
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "snr_fp_run_manifest.json", manifest)
    return manifest


def scan_qclean_inputs(out: Path, paths: SourcePaths) -> list[tuple[str, str, Path]]:
    candidates = [
        ("rich_feature_sets", "2H", paths.rich_root / "05_qclean_feature_set_tables" / "feature_set_qclean_path2h.csv"),
        ("rich_feature_sets", "3H", paths.rich_root / "05_qclean_feature_set_tables" / "feature_set_qclean_path3h.csv"),
        ("negative_controls", "2H", out / "01_negative_controls" / "negative_control_qclean_path2h.csv"),
        ("negative_controls", "3H", out / "01_negative_controls" / "negative_control_qclean_path3h.csv"),
        ("leave_space_out", "2H", out / "02_leave_space_out" / "leave_space_qclean_path2h.csv"),
        ("leave_space_out", "3H", out / "02_leave_space_out" / "leave_space_qclean_path3h.csv"),
        ("snr_fp_baselines", "2H", out / "04_snr_fp_baselines" / "snr_fp_qclean_path2h.csv"),
        ("snr_fp_baselines", "3H", out / "04_snr_fp_baselines" / "snr_fp_qclean_path3h.csv"),
    ]
    return [(src, mode, p) for src, mode, p in candidates if p.exists()]


def ece_and_bins(q: pd.DataFrame, labels: pd.DataFrame, mode: str, n_bins: int, source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    label_col = "not-clean_2H" if mode == "2H" else "not-clean_3H"
    data = q.merge(labels[["case_id", label_col]], on="case_id", how="left")
    data["pred_clean"] = pd.to_numeric(data["q_clean"], errors="coerce")
    data["actual_clean"] = 1.0 - data[label_col].astype(bool).astype(float)
    valid = data["pred_clean"].notna() & data["actual_clean"].notna()
    data = data[valid].copy()
    rows: list[dict[str, Any]] = []
    if data.empty:
        return {"brier_notclean": np.nan, "ece_clean": np.nan, "n_valid": 0}, rows
    data["pred_notclean"] = 1.0 - data["pred_clean"]
    data["actual_notclean"] = 1.0 - data["actual_clean"]
    brier = float(np.mean((data["pred_notclean"] - data["actual_notclean"]) ** 2))
    data["bin"] = pd.cut(data["pred_clean"], bins=np.linspace(0, 1, n_bins + 1), include_lowest=True, labels=False)
    ece = 0.0
    for b, part in data.groupby("bin", dropna=False):
        if pd.isna(b):
            continue
        conf = float(part["pred_clean"].mean())
        acc = float(part["actual_clean"].mean())
        weight = len(part) / len(data)
        ece += weight * abs(acc - conf)
        rows.append(
            {
                "analysis_source": source,
                "qclean_mode": mode,
                "selector": str(part["selector"].iloc[0]) if "selector" in part.columns else str(part["feature_set"].iloc[0]),
                "n_bins": n_bins,
                "bin": int(b),
                "n": int(len(part)),
                "pred_clean_mean": conf,
                "actual_clean_rate": acc,
                "abs_gap": abs(acc - conf),
            }
        )
    return {"brier_notclean": brier, "ece_clean": float(ece), "n_valid": int(len(data))}, rows


def build_qclean_calibration(
    *,
    out_root_arg: str | Path | None = None,
    source_root_arg: str | Path | None = None,
    rich_root_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    paths = resolve_source_paths(source_root_arg, rich_root_arg, config_arg)
    config = load_config(paths)
    labels = load_labels_from_config(config)
    stage = prepare_stage_dir(out, "03_qclean_calibration", overwrite_stage)
    metric_rows: list[dict[str, Any]] = []
    bin_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    for source, mode, path in scan_qclean_inputs(out, paths):
        q = pd.read_csv(path)
        if "selector" not in q.columns:
            q["analysis_source"] = source
            q["selector"] = q.apply(selector_value, axis=1)
        q["qclean_mode"] = mode
        for selector, part in q.groupby("selector", dropna=False):
            valid = pd.to_numeric(part["q_clean"], errors="coerce").notna()
            exclusion_rows.append(
                {
                    "analysis_source": source,
                    "qclean_mode": mode,
                    "selector": selector,
                    "n_total": int(len(part)),
                    "n_valid": int(valid.sum()),
                    "n_excluded_nan_qclean": int((~valid).sum()),
                }
            )
            for bins in [10, 15]:
                metrics, rows = ece_and_bins(part.copy(), labels, mode, bins, source)
                metric_rows.append(
                    {
                        "analysis_source": source,
                        "qclean_mode": mode,
                        "selector": selector,
                        "n_bins": bins,
                        **metrics,
                    }
                )
                for row in rows:
                    row["selector"] = selector
                bin_rows.extend(rows)
    metrics_df = pd.DataFrame(metric_rows)
    bins_df = pd.DataFrame(bin_rows)
    exclusions_df = pd.DataFrame(exclusion_rows)
    metrics_df.to_csv(stage / "qclean_calibration_metrics.csv", index=False)
    bins_df.to_csv(stage / "qclean_reliability_bins.csv", index=False)
    metrics_df.to_csv(stage / "qclean_brier_ece_summary.csv", index=False)
    exclusions_df.to_csv(stage / "qclean_calibration_exclusion_table.csv", index=False)
    figure_rows = build_calibration_figures(stage, metrics_df, bins_df)
    write_csv(stage / "qclean_calibration_figure_manifest.csv", figure_rows)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE" if not metrics_df.empty else "BLOCKED_NO_QCLEAN_INPUTS",
        "metric_rows": int(len(metrics_df)),
        "reliability_bin_rows": int(len(bins_df)),
        "confidence_wording_supported": bool(not metrics_df.empty),
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "qclean_calibration_manifest.json", manifest)
    if metrics_df.empty:
        raise RuntimeError("No q_clean inputs found for calibration")
    return manifest


def build_calibration_figures(stage: Path, metrics: pd.DataFrame, bins: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        return [{"figure": "ALL", "status": "MISSING_MATPLOTLIB", "detail": str(exc)}]
    for mode in ["2H", "3H"]:
        part = bins[(bins["qclean_mode"].eq(mode)) & (bins["n_bins"].eq(10))].copy()
        if part.empty:
            rows.append({"figure": f"qclean_reliability_{mode.lower()}.png", "status": "MISSING_INPUT"})
            continue
        top_selectors = part.groupby("selector")["n"].sum().sort_values(ascending=False).head(8).index
        fig, ax = plt.subplots(figsize=(6, 4))
        for selector in top_selectors:
            s = part[part["selector"].eq(selector)].sort_values("pred_clean_mean")
            ax.plot(s["pred_clean_mean"], s["actual_clean_rate"], marker="o", linewidth=1, label=str(selector)[:36])
        ax.plot([0, 1], [0, 1], color="#555555", linestyle="--", linewidth=1)
        ax.set_xlabel("predicted clean confidence")
        ax.set_ylabel("empirical clean rate")
        ax.set_title(f"q_clean reliability {mode}")
        ax.legend(fontsize=6, loc="best")
        fig.tight_layout()
        name = f"qclean_reliability_{mode.lower()}.png"
        fig.savefig(stage / name, dpi=180)
        plt.close(fig)
        rows.append({"figure": name, "status": "PRESENT", "sha256": sha256_file(stage / name)})
    if not metrics.empty:
        part = metrics[metrics["n_bins"].eq(10)].sort_values("ece_clean").head(24)
        fig, ax = plt.subplots(figsize=(8, 4))
        labels = [f"{r.qclean_mode}:{str(r.selector)[:18]}" for r in part.itertuples()]
        ax.bar(range(len(part)), part["ece_clean"].astype(float))
        ax.set_xticks(range(len(part)))
        ax.set_xticklabels(labels, rotation=75, ha="right", fontsize=6)
        ax.set_ylabel("ECE")
        ax.set_title("q_clean ECE by selector")
        fig.tight_layout()
        name = "qclean_ece_bar_by_feature_set.png"
        fig.savefig(stage / name, dpi=180)
        plt.close(fig)
        rows.append({"figure": name, "status": "PRESENT", "sha256": sha256_file(stage / name)})
    return rows


def build_claim_tables(out: Path, stage5: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    expected = {
        "negative_controls_complete": out / "01_negative_controls" / "negative_control_run_manifest.json",
        "leave_space_out_complete": out / "02_leave_space_out" / "leave_space_run_manifest.json",
        "calibration_complete": out / "03_qclean_calibration" / "qclean_calibration_manifest.json",
        "snr_fp_baseline_complete": out / "04_snr_fp_baselines" / "snr_fp_run_manifest.json",
    }
    gate_rows: list[dict[str, Any]] = []
    for gate, path in expected.items():
        status = "PASS"
        if not path.exists():
            status = "BLOCKED_MISSING"
        else:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if str(payload.get("status", "")).startswith("BLOCKED"):
                    status = str(payload.get("status"))
            except Exception:
                status = "CHECK_REQUIRED"
        gate_rows.append({"gate": gate, "status": status, "evidence": rel(path), "claim_boundary": REPORT_CLAIM_BOUNDARY})
    ready = all(row["status"] == "PASS" for row in gate_rows)
    gate_rows.extend(
        [
            {"gate": "submission_strengthening_ready", "status": "PASS" if ready else "PARTIAL", "evidence": rel(stage5), "claim_boundary": REPORT_CLAIM_BOUNDARY},
            {"gate": "measurement_claims", "status": "MEASUREMENT_MISSING_NOT_RUN", "evidence": "", "claim_boundary": "No measurement transfer claim."},
            {"gate": "range_error_claims", "status": "NOT_SUPPORTED_BY_THEME1", "evidence": "", "claim_boundary": "No direct CP range-error reduction claim."},
        ]
    )
    objection_rows = [
        {"reviewer_objection": "leakage_or_random_cp", "evidence_stage": "01_negative_controls", "status": "ANSWERED_IF_GATE_PASS"},
        {"reviewer_objection": "cir_predictable_cp_component", "evidence_stage": "01_negative_controls", "status": "ANSWERED_IF_GATE_PASS"},
        {"reviewer_objection": "geometry_memorization", "evidence_stage": "02_leave_space_out", "status": "ANSWERED_IF_GATE_PASS_OR_INSUFFICIENT_SUPPORT_VISIBLE"},
        {"reviewer_objection": "confidence_calibration", "evidence_stage": "03_qclean_calibration", "status": "ANSWERED_IF_GATE_PASS"},
        {"reviewer_objection": "snr_sufficient", "evidence_stage": "04_snr_fp_baselines", "status": "ANSWERED_IF_GATE_PASS"},
    ]
    action_rows = [
        {"item": "measurement_transfer", "status": "MISSING_NOT_RUN", "required_action": "Run controlled measurement protocol before measurement claims."},
        {"item": "backend_utility", "status": "MISSING_NOT_RUN", "required_action": "Run backend/AMR/proxy trajectory validation before operational claims."},
        {"item": "range_error_reduction", "status": "NOT_SUPPORTED_BY_THEME1", "required_action": "Do not claim direct range-error reduction from Theme 1."},
    ]
    gates = pd.DataFrame(gate_rows)
    objections = pd.DataFrame(objection_rows)
    actions = pd.DataFrame(action_rows)
    gates.to_csv(stage5 / "submission_strengthening_gate_matrix.csv", index=False)
    objections.to_csv(stage5 / "reviewer_objection_response_table.csv", index=False)
    actions.to_csv(stage5 / "required_action_table.csv", index=False)
    return gates, objections, actions


def artifact_manifest(root: Path, package_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".zip":
            continue
        rows.append(
            {
                "relative_path": rel(path, root),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "artifact_role": "theme1_submission_strengthening",
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(package_dir / "theme1_submission_strengthening_artifact_manifest.csv", index=False)
    return df


def write_report(package_dir: Path, gates: pd.DataFrame) -> Path:
    status = "PASS" if gates[gates["gate"].eq("submission_strengthening_ready")]["status"].astype(str).eq("PASS").any() else "PARTIAL"
    text = f"""# Theme 1 Submission Strengthening Report

Generated: {now_utc()}

## Scope

These additional simulation-only controls test whether CP-augmented q_clean/state-selection evidence survives leakage, CIR-explainability, geometry-generalization, calibration, and SNR/first-path-power objections.

They do not establish measurement transfer, backend utility, localization accuracy, or direct range-error reduction.

## Gate Status

Overall status: `{status}`

See `../05_integrated_claim_gates/submission_strengthening_gate_matrix.csv` for machine-readable gates.

## Claim Boundary

{REPORT_CLAIM_BOUNDARY}
"""
    path = package_dir / "THEME1_SUBMISSION_STRENGTHENING_REPORT.md"
    path.write_text(text, encoding="utf-8")
    return path


def build_package(
    *,
    out_root_arg: str | Path | None = None,
    overwrite_stage: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    stage5 = prepare_stage_dir(out, "05_integrated_claim_gates", overwrite_stage)
    gates, objections, actions = build_claim_tables(out, stage5)
    package_dir = prepare_stage_dir(out, "06_report_package", overwrite_stage)
    report_path = write_report(package_dir, gates)
    manifest_df = artifact_manifest(out, package_dir)
    report_manifest = pd.DataFrame(
        [
            {"path": report_path.name, "bytes": report_path.stat().st_size, "sha256": sha256_file(report_path)},
            {"path": "theme1_submission_strengthening_artifact_manifest.csv", "bytes": (package_dir / "theme1_submission_strengthening_artifact_manifest.csv").stat().st_size, "sha256": sha256_file(package_dir / "theme1_submission_strengthening_artifact_manifest.csv")},
        ]
    )
    report_manifest.to_csv(package_dir / "theme1_submission_strengthening_report_manifest.csv", index=False)
    zip_path = package_dir / "THEME1_SUBMISSION_STRENGTHENING_PACKAGE_20260629.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out.rglob("*")):
            if not path.is_file() or path == zip_path or path.name.endswith(".sha256"):
                continue
            zf.write(path, f"release/results/{rel(path, out)}")
        for path in [
            ROOT / "rt_cp_uwb_py" / "theme1_submission_strengthening.py",
            ROOT / ".omx" / "plans" / "theme1_submission_strengthening_experiments_plan_20260629.md",
        ]:
            if path.exists():
                zf.write(path, f"release/code/{path.name}")
        for path in sorted((ROOT / "scripts").glob("build_theme1_*20260629.py")):
            if path.name in {
                "build_theme1_submission_strengthening_source_audit_20260629.py",
                "build_theme1_negative_controls_20260629.py",
                "build_theme1_leave_space_out_20260629.py",
                "build_theme1_qclean_calibration_20260629.py",
                "build_theme1_snr_fp_baselines_20260629.py",
                "build_theme1_submission_strengthening_package_20260629.py",
            }:
                zf.write(path, f"release/scripts/{path.name}")
    checksum = sha256_file(zip_path)
    (zip_path.with_suffix(zip_path.suffix + ".sha256")).write_text(f"{checksum}  {zip_path.name}\n", encoding="utf-8")
    package_manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE",
        "package_path": rel(zip_path),
        "sha256": checksum,
        "artifact_count": int(len(manifest_df)),
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(package_dir / "theme1_submission_strengthening_package_manifest.json", package_manifest)
    return package_manifest
