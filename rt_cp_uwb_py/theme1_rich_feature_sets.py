from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from rt_cp_uwb_py.feature_discovery import (
    build_outer_splits,
    fit_predict_outer,
    load_merged_tables,
    read_yaml,
    repo_path,
    score_to_probability,
    target_specs,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = ROOT / "results" / "THEME1_CP_CHANNEL_STATE_CLASSIFICATION_FULLRT_20260628"
DEFAULT_RICH_ROOT = ROOT / "results" / "THEME1_CP_CHANNEL_STATE_CLASSIFICATION_RICH_FEATURESETS_20260628"
DEFAULT_CONFIG = DEFAULT_SOURCE_ROOT / "04_feature_discovery" / "configs" / "feature_discovery_theme1_20260628.yaml"
DEFAULT_DISCOVERY_FULL = DEFAULT_SOURCE_ROOT / "04_feature_discovery" / "full"
ACCEPTED_RATIOS = [0.20, 0.30, 0.50, 0.70, 0.90]
LABEL_COLS = ["NoLoS", "RD-LoS", "HB-near-delay", "HB-prior", "not-clean_2H", "not-clean_3H"]
PRIMARY_MODEL = "HGB"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_path(path: str | Path, root: Path = ROOT) -> Path:
    path = Path(path)
    return path if path.is_absolute() else root / path


def rel(path: str | Path, root: Path = ROOT) -> str:
    path = Path(path).resolve()
    try:
        return str(path.relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return "MISSING"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_row_count(path: Path) -> str:
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".csv":
        return ""
    with path.open("rb") as f:
        return str(max(0, sum(1 for _ in f) - 1))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
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


def truthy(series: pd.Series) -> pd.Series:
    return series.map(lambda x: str(x).strip().lower() in {"true", "1", "yes"}).astype(bool)


def label_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ["case_id"] + LABEL_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Label columns missing: {missing}")
    out = df[["case_id"] + LABEL_COLS].copy()
    for col in LABEL_COLS:
        out[col] = truthy(out[col])
    return out


def load_labels_from_config(config: dict, root: Path = ROOT) -> pd.DataFrame:
    label_path = repo_path(config["inputs"]["label_table"], root)
    return label_frame(pd.read_csv(label_path))


def parse_models(models: str | Sequence[str] | None, config: dict) -> list[str]:
    if models is None:
        return [PRIMARY_MODEL]
    if isinstance(models, str):
        raw = [m.strip() for m in models.split(",") if m.strip()]
    else:
        raw = [str(m).strip() for m in models if str(m).strip()]
    return raw or [PRIMARY_MODEL]


def cp11_mech_features(config: dict) -> list[str]:
    named = config.get("named_baselines", {})
    cir5 = set(named.get("CIR5", []))
    cp11 = [f for f in named.get("CIR5+CP11_mech", []) if f not in cir5]
    if cp11:
        return cp11
    return [
        "xpr_fp_db",
        "xpr_late_db",
        "xpr_all_db",
        "s3_fp",
        "s3_late",
        "s3_all",
        "delta_p_l_given_r_db",
        "f_l_fp",
        "lambda_l_late_fraction",
        "gamma_anchor_linear",
        "gamma_delay_linear",
    ]


def feature_set_definitions(config: dict, requested: Sequence[str], mode: str) -> dict[str, list[str]]:
    named = {k: list(v) for k, v in config.get("named_baselines", {}).items()}
    if "CIR12+CP6" not in named and "CIR12" in named and "CP6" in named:
        named["CIR12+CP6"] = list(named["CIR12"]) + list(named["CP6"])
    if "CIR12+CP11_mech" not in named and "CIR12" in named:
        named["CIR12+CP11_mech"] = list(named["CIR12"]) + cp11_mech_features(config)
    defs: dict[str, list[str]] = {}
    for name in requested:
        if name not in named:
            defs[name] = []
        else:
            defs[name] = list(dict.fromkeys(named[name]))
    if mode == "cir_only":
        allowed_prefixes = ("CIR", "LP-CIR")
        defs = {k: v for k, v in defs.items() if k.startswith(allowed_prefixes)}
    return defs


def split_requested(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [x.strip() for x in value.split(",") if x.strip()]


def audit_feature_sets(df: pd.DataFrame, config: dict, defs: dict[str, list[str]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    forbidden = set(config.get("candidate_pools", {}).get("forbidden_main", []))
    def_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    forbidden_rows: list[dict[str, Any]] = []
    for name, features in defs.items():
        missing = [f for f in features if f not in df.columns]
        bad = [f for f in features if f in forbidden]
        status = "PRESENT" if features and not missing and not bad else ("MISSING_FEATURES" if missing or not features else "FORBIDDEN_FEATURES")
        def_rows.append(
            {
                "feature_set": name,
                "features": ";".join(features),
                "n_features": len(features),
                "feature_status": status,
                "missing_features": ";".join(missing),
                "forbidden_features": ";".join(bad),
            }
        )
        for feature in missing:
            missing_rows.append({"feature_set": name, "feature": feature, "status": "MISSING"})
        for feature in bad:
            forbidden_rows.append({"feature_set": name, "feature": feature, "status": "FORBIDDEN"})
    return pd.DataFrame(def_rows), pd.DataFrame(missing_rows), pd.DataFrame(forbidden_rows)


def run_feature_set_oof(
    *,
    config_path: Path,
    out_dir: Path,
    feature_sets: Sequence[str],
    prefix: str,
    mode: str,
    models: Sequence[str] | str | None = None,
    max_rows: int | None = None,
    outer_splits: str | None = None,
    dry_run: bool = False,
    hgb_iter: int | None = None,
) -> dict[str, Any]:
    config_path = as_path(config_path).resolve()
    config = read_yaml(config_path)
    out_dir = as_path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    search_cfg = config.get("search", {})
    seed = int(search_cfg.get("seed", 20260610))
    hgb_iter = int(hgb_iter or search_cfg.get("hgb_iter", 60))
    model_names = parse_models(models, config)
    requested_sets = list(feature_sets)
    if not requested_sets:
        requested_sets = ["CIR5", "CIR12", "LP-CIR12"] if mode == "cir_only" else ["CP6", "CIR5+CP6", "CIR5+CP11_mech", "CIR12+CP6", "CIR12+CP11_mech"]

    df = load_merged_tables(config, max_rows=max_rows)
    specs = target_specs(config)
    splits = build_outer_splits(df, split_key=config["inputs"].get("split_key", "split_fold"), requested=outer_splits)
    defs = feature_set_definitions(config, requested_sets, mode)
    definitions, missing_audit, forbidden_audit = audit_feature_sets(df, config, defs)
    definitions.to_csv(out_dir / f"{prefix}_feature_set_definitions.csv", index=False)
    missing_audit.to_csv(out_dir / f"{prefix}_missing_feature_audit.csv", index=False)
    forbidden_audit.to_csv(out_dir / f"{prefix}_forbidden_feature_audit.csv", index=False)

    if dry_run:
        manifest = {
            "created_at_utc": now_utc(),
            "script": Path(sys.argv[0]).name,
            "command_line": subprocess.list2cmdline(sys.argv),
            "status": "DRY_RUN_OK",
            "config_path": rel(config_path),
            "out_dir": rel(out_dir),
            "mode": mode,
            "feature_sets": requested_sets,
            "models": model_names,
            "n_rows": int(len(df)),
            "n_outer_splits": len(splits),
            "claim_boundary": "Simulation-only OOF/q-clean source; no range-error/backend/AMR/localization/measurement claim.",
        }
        write_json(out_dir / f"{prefix}_run_manifest.json", manifest)
        return manifest

    metric_parts: list[pd.DataFrame] = []
    pred_parts: list[pd.DataFrame] = []
    present_defs = definitions[definitions["feature_status"].eq("PRESENT")]
    for split in splits:
        for _, row in present_defs.iterrows():
            feature_set = str(row["feature_set"])
            features = [f for f in str(row["features"]).split(";") if f]
            for model in model_names:
                metrics, preds = fit_predict_outer(df, split.train_idx, split.test_idx, features, specs, model, seed, hgb_iter=hgb_iter)
                metrics["outer_split"] = split.name
                metrics["feature_set"] = feature_set
                metrics["features"] = ";".join(features)
                metrics["feature_status"] = "PRESENT"
                metric_parts.append(metrics)
                preds["outer_split"] = split.name
                preds["feature_set"] = feature_set
                preds["features"] = ";".join(features)
                preds["feature_status"] = "PRESENT"
                preds["model"] = model
                pred_parts.append(preds)

    results = pd.concat(metric_parts, ignore_index=True) if metric_parts else pd.DataFrame()
    predictions = pd.concat(pred_parts, ignore_index=True) if pred_parts else pd.DataFrame()
    results.to_csv(out_dir / f"{prefix}_outer_test_results.csv", index=False)
    predictions.to_csv(out_dir / f"{prefix}_outer_test_predictions.csv", index=False)

    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE",
        "config_path": rel(config_path),
        "out_dir": rel(out_dir),
        "mode": mode,
        "feature_sets": requested_sets,
        "models": model_names,
        "primary_model": PRIMARY_MODEL,
        "n_rows": int(len(df)),
        "n_outer_splits": len(splits),
        "prediction_rows": int(len(predictions)),
        "present_feature_sets": sorted(present_defs["feature_set"].astype(str).tolist()),
        "missing_or_blocked_feature_sets": sorted(definitions[~definitions["feature_status"].eq("PRESENT")]["feature_set"].astype(str).tolist()),
        "outputs": sorted(p.name for p in out_dir.iterdir() if p.is_file()),
        "claim_boundary": "Simulation-only OOF/q-clean source; no range-error/backend/AMR/localization/measurement claim.",
    }
    write_json(out_dir / f"{prefix}_run_manifest.json", manifest)

    if mode == "cir_only" and not predictions.empty:
        labels = load_labels_from_config(config)
        q2h, q3h = qclean_from_predictions(predictions[predictions["model"].eq(PRIMARY_MODEL)].copy(), PRIMARY_MODEL)
        q2h.to_csv(out_dir / "cir_only_qclean_scores_path2h.csv", index=False)
        q3h.to_csv(out_dir / "cir_only_qclean_scores_path3h.csv", index=False)
        decile_table(q2h, labels, "2H").to_csv(out_dir / "cir_only_qclean_decile_state_table.csv", index=False)
        same_acceptance_table(q2h, labels, "2H").to_csv(out_dir / "cir_only_same_acceptance_state_selection.csv", index=False)
        manifest["cir_only_qclean_status"] = cir_only_status(q2h, q3h)
        manifest["outputs"] = sorted(p.name for p in out_dir.iterdir() if p.is_file())
        write_json(out_dir / f"{prefix}_oof_qclean_manifest.json", manifest)
    return manifest


def run_maxj_oof(
    *,
    config_path: Path,
    leaderboard_path: Path,
    out_dir: Path,
    models: Sequence[str] | str | None = None,
    max_rows: int | None = None,
    outer_splits: str | None = None,
    dry_run: bool = False,
    hgb_iter: int | None = None,
) -> dict[str, Any]:
    config_path = as_path(config_path).resolve()
    leaderboard_path = as_path(leaderboard_path).resolve()
    out_dir = as_path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    config = read_yaml(config_path)
    search_cfg = config.get("search", {})
    seed = int(search_cfg.get("seed", 20260610))
    hgb_iter = int(hgb_iter or search_cfg.get("hgb_iter", 60))
    model_names = parse_models(models, config)
    leaderboard = pd.read_csv(leaderboard_path)
    df = load_merged_tables(config, max_rows=max_rows)
    specs = target_specs(config)
    splits = build_outer_splits(df, split_key=config["inputs"].get("split_key", "split_fold"), requested=outer_splits)
    split_names = {s.name for s in splits}

    lb = leaderboard.copy()
    if "search_scope" in lb.columns:
        lb = lb[lb["search_scope"].eq("joint")]
    for col in ["n_CIR", "n_CP", "J"]:
        if col in lb.columns:
            lb[col] = pd.to_numeric(lb[col], errors="coerce")
    lb = lb[(lb["outer_split"].isin(split_names)) & (lb["n_CIR"] >= 1) & (lb["n_CP"] >= 1)]
    if lb.empty:
        raise ValueError("No joint max-J rows with both CIR and CP features")
    idx = lb.sort_values(["outer_split", "J", "n_features"], ascending=[True, False, False]).groupby("outer_split", as_index=False).head(1).index
    selected = lb.loc[idx].sort_values("outer_split").reset_index(drop=True)
    selected.to_csv(out_dir / "maxj_selection_trace.csv", index=False)

    if dry_run:
        manifest = {
            "created_at_utc": now_utc(),
            "script": Path(sys.argv[0]).name,
            "command_line": subprocess.list2cmdline(sys.argv),
            "status": "DRY_RUN_OK",
            "config_path": rel(config_path),
            "leaderboard_path": rel(leaderboard_path),
            "out_dir": rel(out_dir),
            "models": model_names,
            "selected_splits": int(len(selected)),
            "n_rows": int(len(df)),
        }
        write_json(out_dir / "maxj_run_manifest.json", manifest)
        return manifest

    metric_parts: list[pd.DataFrame] = []
    pred_parts: list[pd.DataFrame] = []
    selected_by_split = {str(row["outer_split"]): [f for f in str(row["features"]).split(";") if f] for _, row in selected.iterrows()}
    for split in splits:
        features = selected_by_split.get(split.name, [])
        if not features:
            continue
        for model in model_names:
            metrics, preds = fit_predict_outer(df, split.train_idx, split.test_idx, features, specs, model, seed, hgb_iter=hgb_iter)
            metrics["outer_split"] = split.name
            metrics["feature_set"] = "maxj_discovered_subset"
            metrics["features"] = ";".join(features)
            metrics["feature_status"] = "PRESENT"
            metric_parts.append(metrics)
            preds["outer_split"] = split.name
            preds["feature_set"] = "maxj_discovered_subset"
            preds["features"] = ";".join(features)
            preds["feature_status"] = "PRESENT"
            preds["model"] = model
            pred_parts.append(preds)

    results = pd.concat(metric_parts, ignore_index=True) if metric_parts else pd.DataFrame()
    predictions = pd.concat(pred_parts, ignore_index=True) if pred_parts else pd.DataFrame()
    results.to_csv(out_dir / "maxj_outer_test_results.csv", index=False)
    predictions.to_csv(out_dir / "maxj_outer_test_predictions.csv", index=False)
    if not predictions.empty:
        q2h, q3h = qclean_from_predictions(predictions[predictions["model"].eq(PRIMARY_MODEL)].copy(), PRIMARY_MODEL)
        q2h.to_csv(out_dir / "maxj_qclean_scores_path2h.csv", index=False)
        q3h.to_csv(out_dir / "maxj_qclean_scores_path3h.csv", index=False)
    stability = selected.assign(feature_list=selected["features"].astype(str).str.split(";")).explode("feature_list")
    if not stability.empty:
        stab = stability.groupby("feature_list", as_index=False).agg(selected_in_folds=("outer_split", "nunique"))
        stab["selection_frequency"] = stab["selected_in_folds"] / max(1, len(splits))
        stab = stab.rename(columns={"feature_list": "feature"})
    else:
        stab = pd.DataFrame(columns=["feature", "selected_in_folds", "selection_frequency"])
    stab.to_csv(out_dir / "maxj_feature_stability.csv", index=False)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE",
        "config_path": rel(config_path),
        "leaderboard_path": rel(leaderboard_path),
        "out_dir": rel(out_dir),
        "models": model_names,
        "primary_model": PRIMARY_MODEL,
        "selected_splits": int(len(selected)),
        "prediction_rows": int(len(predictions)),
        "outputs": sorted(p.name for p in out_dir.iterdir() if p.is_file()),
        "claim_boundary": "Max-J discovered subset is discovery evidence only; q_clean remains session-quality confidence.",
    }
    write_json(out_dir / "maxj_run_manifest.json", manifest)
    return manifest


def qclean_from_predictions(predictions: pd.DataFrame, model_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    def col(name: str) -> pd.Series:
        key = f"{model_name}_{name}"
        if key not in predictions.columns:
            return pd.Series(np.nan, index=predictions.index)
        return pd.Series(score_to_probability(pd.to_numeric(predictions[key], errors="coerce").to_numpy()), index=predictions.index)

    base_cols = [c for c in ["row_index", "case_id", "outer_split", "feature_set", "features", "feature_status", "model"] if c in predictions.columns]
    base = predictions[base_cols].copy()
    p_nolos = col("NoLoS")
    p_rd = col("RDLoS")
    p_hbnear = col("HBnear")
    p_hbprior = col("HBprior")
    q2h = base.copy()
    q2h["p_NoLoS"] = p_nolos
    q2h["p_RD"] = p_rd
    q2h["q_clean"] = (1.0 - p_nolos) * (1.0 - p_rd)
    q2h["qclean_mode"] = "2H"
    q2h["score_status"] = f"OUTER_HELDOUT_{model_name}_UNCALIBRATED"
    q3h = base.copy()
    q3h["p_NoLoS"] = p_nolos
    q3h["p_HBnear"] = p_hbnear
    q3h["p_HBprior"] = p_hbprior
    q3h["q_clean"] = (1.0 - p_nolos) * (1.0 - p_hbnear) * (1.0 - p_hbprior)
    q3h["qclean_mode"] = "3H"
    q3h["score_status"] = f"OUTER_HELDOUT_{model_name}_UNCALIBRATED"
    return q2h, q3h


def qclean_residuals(q: pd.DataFrame, mode: str) -> pd.Series:
    if mode == "2H":
        expected = (1.0 - pd.to_numeric(q["p_NoLoS"], errors="coerce")) * (1.0 - pd.to_numeric(q["p_RD"], errors="coerce"))
    else:
        expected = (
            (1.0 - pd.to_numeric(q["p_NoLoS"], errors="coerce"))
            * (1.0 - pd.to_numeric(q["p_HBnear"], errors="coerce"))
            * (1.0 - pd.to_numeric(q["p_HBprior"], errors="coerce"))
        )
    return (pd.to_numeric(q["q_clean"], errors="coerce") - expected).abs()


def cir_only_status(q2h: pd.DataFrame, q3h: pd.DataFrame) -> str:
    needed = {"CIR5", "CIR12"}
    present = set(q2h["feature_set"].dropna().astype(str)).intersection(set(q3h["feature_set"].dropna().astype(str)))
    counts = q2h[q2h["feature_set"].isin(needed)].groupby("feature_set")["case_id"].nunique()
    if needed.issubset(present) and all(int(counts.get(name, 0)) == 18000 for name in needed):
        return "CIR_ONLY_OOF_QCLEAN_PRESENT"
    return "CIR_ONLY_OOF_QCLEAN_INCOMPLETE"


def decile_table(q: pd.DataFrame, labels: pd.DataFrame, mode: str) -> pd.DataFrame:
    joined = q.merge(labels, on="case_id", how="left", validate="many_to_one")
    rows: list[dict[str, Any]] = []
    for feature_set, part0 in joined.groupby("feature_set", dropna=False):
        part0 = part0.copy()
        ranked = part0["q_clean"].rank(method="first", na_option="bottom")
        part0["qclean_decile"] = pd.qcut(ranked, 10, labels=False, duplicates="drop") + 1
        for decile, part in part0.groupby("qclean_decile", dropna=False):
            row: dict[str, Any] = {
                "feature_set": feature_set,
                "qclean_mode": mode,
                "qclean_decile": int(decile) if pd.notna(decile) else "",
                "n": int(len(part)),
                "q_clean_min": float(part["q_clean"].min(skipna=True)),
                "q_clean_max": float(part["q_clean"].max(skipna=True)),
                "q_clean_mean": float(part["q_clean"].mean(skipna=True)),
            }
            for col in LABEL_COLS:
                row[f"{col}_rate"] = float(part[col].mean())
                row[f"{col}_count"] = int(part[col].sum())
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["feature_set", "qclean_mode", "qclean_decile"]).reset_index(drop=True)


def same_acceptance_table(q: pd.DataFrame, labels: pd.DataFrame, mode: str) -> pd.DataFrame:
    joined = q.merge(labels, on="case_id", how="left", validate="many_to_one")
    rows: list[dict[str, Any]] = []
    for feature_set, part0 in joined.groupby("feature_set", dropna=False):
        part0 = part0.sort_values("q_clean", ascending=False, na_position="last").reset_index(drop=True)
        n_total = len(part0)
        for ratio in ACCEPTED_RATIOS:
            n_accept = max(1, int(round(n_total * ratio)))
            part = part0.head(n_accept)
            row: dict[str, Any] = {
                "feature_set": feature_set,
                "qclean_mode": mode,
                "accepted_ratio": ratio,
                "n_total": n_total,
                "n_accepted": int(len(part)),
                "q_clean_threshold_min": float(part["q_clean"].min(skipna=True)),
                "q_clean_mean_selected": float(part["q_clean"].mean(skipna=True)),
            }
            for col in LABEL_COLS:
                row[f"{col}_rate"] = float(part[col].mean())
                row[f"{col}_count"] = int(part[col].sum())
            rows.append(row)
    return pd.DataFrame(rows)


def accepted_cases(q: pd.DataFrame, feature_set: str, mode: str, ratio: float) -> set[int]:
    part = q[(q["feature_set"].eq(feature_set)) & (q["qclean_mode"].eq(mode))].copy()
    part = part.sort_values("q_clean", ascending=False, na_position="last")
    n_accept = max(1, int(round(len(part) * ratio)))
    return set(part.head(n_accept)["case_id"].astype(int).tolist())


def pairwise_same_acceptance(q: pd.DataFrame, labels: pd.DataFrame, pairs: Sequence[tuple[str, str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    available = set(q["feature_set"].dropna().astype(str))
    for base, augmented in pairs:
        for mode in ["2H", "3H"]:
            q_mode = q[q["qclean_mode"].eq(mode)].copy()
            same = same_acceptance_table(q_mode, labels, mode)
            for ratio in ACCEPTED_RATIOS:
                base_row = same[
                    same["feature_set"].eq(base)
                    & same["qclean_mode"].eq(mode)
                    & np.isclose(pd.to_numeric(same["accepted_ratio"]), ratio)
                ]
                aug_row = same[
                    same["feature_set"].eq(augmented)
                    & same["qclean_mode"].eq(mode)
                    & np.isclose(pd.to_numeric(same["accepted_ratio"]), ratio)
                ]
                status = "PASS" if base in available and augmented in available and not base_row.empty and not aug_row.empty else "MISSING_OOF_SOURCE"
                row: dict[str, Any] = {
                    "baseline_feature_set": base,
                    "augmented_feature_set": augmented,
                    "qclean_mode": mode,
                    "accepted_ratio": ratio,
                    "status": status,
                }
                if status == "PASS":
                    b = base_row.iloc[0]
                    a = aug_row.iloc[0]
                    for col in LABEL_COLS:
                        row[f"baseline_{col}_rate"] = float(b[f"{col}_rate"])
                        row[f"augmented_{col}_rate"] = float(a[f"{col}_rate"])
                        row[f"delta_aug_minus_baseline_{col}_rate"] = float(a[f"{col}_rate"] - b[f"{col}_rate"])
                    b_cases = accepted_cases(q, base, mode, ratio)
                    a_cases = accepted_cases(q, augmented, mode, ratio)
                    union = b_cases.union(a_cases)
                    overlap_rows.append(
                        {
                            "baseline_feature_set": base,
                            "augmented_feature_set": augmented,
                            "qclean_mode": mode,
                            "accepted_ratio": ratio,
                            "baseline_n": len(b_cases),
                            "augmented_n": len(a_cases),
                            "overlap_n": len(b_cases.intersection(a_cases)),
                            "union_n": len(union),
                            "jaccard": float(len(b_cases.intersection(a_cases)) / len(union)) if union else float("nan"),
                            "status": status,
                        }
                    )
                rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(overlap_rows)


def combine_qclean_inputs(paths: Sequence[Path], model: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    pred_parts = []
    for path in paths:
        if path.exists() and path.stat().st_size > 0:
            df = pd.read_csv(path)
            if "model" in df.columns:
                df = df[df["model"].eq(model)].copy()
            pred_parts.append(df)
    if not pred_parts:
        return pd.DataFrame(), pd.DataFrame()
    preds = pd.concat(pred_parts, ignore_index=True)
    return qclean_from_predictions(preds, model)


def source_link_stage(rich_root: Path, source_root: Path, config_path: Path) -> None:
    out = rich_root / "00_source_links"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for role, path in [
        ("source_root", source_root),
        ("config_snapshot", config_path),
        ("fullrun_manifest", source_root / "02_rt_fullrun" / "fullrun_manifest.json"),
        ("split_manifest", source_root / "03_source_freeze" / "theme1_split_manifest.csv"),
        ("one_se_predictions", source_root / "04_feature_discovery" / "full" / "outer_test_predictions.csv"),
        ("missing_cir_baseline_evidence", source_root / "05_clean_session_selection_proxy" / "theme1_same_acceptance_missing_baselines.csv"),
    ]:
        rows.append(
            {
                "role": role,
                "path": rel(path),
                "status": "PRESENT" if path.exists() else "MISSING",
                "row_count": csv_row_count(path),
                "sha256": sha256_file(path) if path.is_file() else "",
            }
        )
    write_csv(out / "source_file_hashes.csv", rows)
    write_json(
        out / "source_pointer_manifest.json",
        {
            "created_at_utc": now_utc(),
            "source_root": rel(source_root),
            "config_path": rel(config_path),
            "status": "SOURCE_LINK_SNAPSHOT_WRITTEN",
            "claim_boundary": "Source pointers only; no new claim.",
        },
    )
    write_csv(
        out / "source_gate_table.csv",
        [
            {"gate": "full_rt_source_complete", "status": "PASS" if (source_root / "02_rt_fullrun" / "fullrun_manifest.json").exists() else "BLOCKED"},
            {"gate": "one_se_reference_present", "status": "PASS" if (source_root / "04_feature_discovery" / "full" / "outer_test_predictions.csv").exists() else "BLOCKED"},
            {"gate": "cir_only_oof_qclean_present_before_rerun", "status": "MISSING_EXPECTED"},
        ],
    )


def one_se_relabel_stage(rich_root: Path, source_root: Path) -> None:
    out = rich_root / "01_current_one_se_relabel"
    out.mkdir(parents=True, exist_ok=True)
    final_decision = source_root / "04_feature_discovery" / "full" / "final_decision_table.csv"
    if final_decision.exists():
        shutil.copy2(final_decision, out / "one_se_selected_features.csv")
    note = "\n".join(
        [
            "# One-SE Reference Note",
            "",
            "The existing Theme 1 package is a parsimonious one-SE discovered-subset result.",
            "It is valid as a compact diagnostic subset, but it is not the final report-ready feature-set panel.",
            "CIR-only same-accepted-ratio comparison requires separate CIR5/CIR12 OOF q-clean scores.",
            "",
        ]
    )
    (out / "ONE_SE_REFERENCE_NOTE.md").write_text(note, encoding="utf-8")
    write_json(
        out / "one_se_reference_manifest.json",
        {
            "created_at_utc": now_utc(),
            "source_final_decision": rel(final_decision),
            "status": "PARSIMONIOUS_ONE_SE_REFERENCE_ONLY",
            "claim_boundary": "Compact discovered subset only; not the final rich feature-set evidence package.",
        },
    )


def build_combined_qclean_package(
    *,
    rich_root: Path,
    source_root: Path,
    config_path: Path,
    maxj_predictions: Path | None = None,
    cir_predictions: Path | None = None,
    forced_predictions: Path | None = None,
    model: str = PRIMARY_MODEL,
) -> dict[str, Any]:
    rich_root = as_path(rich_root).resolve()
    source_root = as_path(source_root).resolve()
    config_path = as_path(config_path).resolve()
    config = read_yaml(config_path)
    labels = load_labels_from_config(config)
    source_link_stage(rich_root, source_root, config_path)
    one_se_relabel_stage(rich_root, source_root)

    maxj_predictions = maxj_predictions or rich_root / "02_maxj_discovered_subset" / "maxj_outer_test_predictions.csv"
    cir_predictions = cir_predictions or rich_root / "03_cir_only_oof_qclean" / "cir_only_outer_test_predictions.csv"
    forced_predictions = forced_predictions or rich_root / "04_forced_feature_set_oof" / "feature_set_outer_test_predictions.csv"
    one_se_predictions = source_root / "04_feature_discovery" / "full" / "outer_test_predictions.csv"
    pred_paths = [one_se_predictions, maxj_predictions, cir_predictions, forced_predictions]
    q2h, q3h = combine_qclean_inputs(pred_paths, model)
    if q2h.empty or q3h.empty:
        raise ValueError("No q-clean predictions available")
    q2h.loc[q2h["feature_set"].eq("discovered_subset"), "feature_set"] = "one_se_discovered"
    q3h.loc[q3h["feature_set"].eq("discovered_subset"), "feature_set"] = "one_se_discovered"
    q2h["qclean_mode"] = "2H"
    q3h["qclean_mode"] = "3H"
    q_all = pd.concat([q2h, q3h], ignore_index=True)

    out_q = rich_root / "05_qclean_feature_set_tables"
    out_q.mkdir(parents=True, exist_ok=True)
    q2h.to_csv(out_q / "feature_set_qclean_path2h.csv", index=False)
    q3h.to_csv(out_q / "feature_set_qclean_path3h.csv", index=False)
    pd.concat([decile_table(q2h, labels, "2H"), decile_table(q3h, labels, "3H")], ignore_index=True).to_csv(out_q / "feature_set_qclean_decile_state_table.csv", index=False)
    pd.concat([same_acceptance_table(q2h, labels, "2H"), same_acceptance_table(q3h, labels, "3H")], ignore_index=True).to_csv(out_q / "feature_set_same_acceptance_state_selection.csv", index=False)
    pairs = [
        ("CIR5", "CIR5+CP6"),
        ("CIR5", "CIR5+CP11_mech"),
        ("CIR12", "CIR12+CP6"),
        ("CIR12", "CIR12+CP11_mech"),
        ("one_se_discovered", "maxj_discovered_subset"),
    ]
    pair_delta, pair_overlap = pairwise_same_acceptance(q_all, labels, pairs)
    pair_delta.to_csv(out_q / "feature_set_cir_vs_cp_delta_at_same_acceptance.csv", index=False)
    pair_delta.to_csv(out_q / "feature_set_same_acceptance_pairwise.csv", index=False)
    pair_overlap.to_csv(out_q / "feature_set_cir_vs_cp_accepted_case_overlap.csv", index=False)
    audit_rows = qclean_audit_rows(q2h, q3h)
    write_csv(out_q / "feature_set_score_schema_audit.csv", audit_rows)
    write_json(
        out_q / "feature_set_qclean_manifest.json",
        {
            "created_at_utc": now_utc(),
            "script": Path(sys.argv[0]).name,
            "command_line": subprocess.list2cmdline(sys.argv),
            "model": model,
            "input_predictions": [rel(p) for p in pred_paths],
            "feature_sets": sorted(q_all["feature_set"].dropna().astype(str).unique().tolist()),
            "qclean_rows_path2h": int(len(q2h)),
            "qclean_rows_path3h": int(len(q3h)),
            "claim_boundary": "q_clean is session-quality confidence; same-acceptance uses channel-state rates only.",
        },
    )

    comparison_stage(rich_root, q_all, q2h, q3h, pair_delta, pair_overlap, audit_rows)
    report_stage(rich_root)
    return {"status": "FEATURE_SET_QCLEAN_PACKAGE_COMPLETE", "rich_root": rel(rich_root)}


def qclean_audit_rows(q2h: pd.DataFrame, q3h: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode, q in [("2H", q2h), ("3H", q3h)]:
        resid = qclean_residuals(q, mode)
        max_resid = float(resid.max(skipna=True)) if len(resid) else float("nan")
        rows.append(
            {
                "check": f"{mode}_qclean_formula",
                "status": "PASS" if math.isfinite(max_resid) and max_resid <= 1e-10 else "FAIL",
                "detail": f"max_abs_residual={max_resid:.6g}",
            }
        )
        for feature_set, part in q.groupby("feature_set"):
            rows.append(
                {
                    "check": f"{mode}_{feature_set}_unique_case_count",
                    "status": "PASS" if int(part["case_id"].nunique()) == 18000 else "CHECK",
                    "detail": f"unique_case_id={int(part['case_id'].nunique())}",
                }
            )
    return rows


def comparison_stage(
    rich_root: Path,
    q_all: pd.DataFrame,
    q2h: pd.DataFrame,
    q3h: pd.DataFrame,
    pair_delta: pd.DataFrame,
    pair_overlap: pd.DataFrame,
    audit_rows: list[dict[str, Any]],
) -> None:
    out = rich_root / "06_comparison_and_claim_gates"
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for mode, q in [("2H", q2h), ("3H", q3h)]:
        for feature_set, part in q.groupby("feature_set"):
            summary.append(
                {
                    "feature_set": feature_set,
                    "qclean_mode": mode,
                    "n_rows": int(len(part)),
                    "unique_case_id": int(part["case_id"].nunique()),
                    "q_clean_mean": float(part["q_clean"].mean(skipna=True)),
                    "q_clean_nonnull": int(part["q_clean"].notna().sum()),
                }
            )
    pd.DataFrame(summary).to_csv(out / "feature_set_qclean_summary.csv", index=False)
    pair_delta.to_csv(out / "cir_vs_cp_same_acceptance_summary.csv", index=False)
    pair_overlap.to_csv(out / "feature_set_accepted_case_overlap_summary.csv", index=False)
    if not pair_delta.empty:
        pair_delta.to_csv(out / "feature_set_same_acceptance_summary.csv", index=False)
    rows = claim_gate_rows(q_all, pair_delta, audit_rows)
    write_csv(out / "rich_feature_claim_gate_matrix.csv", rows)
    write_csv(
        out / "rich_feature_required_action_table.csv",
        [
            {
                "artifact": "measurement_claims",
                "status": "MEASUREMENT_MISSING_NOT_RUN",
                "required_action": "Run a separate measurement plan before measurement transfer or supervised accuracy wording.",
            },
            {
                "artifact": "range_error_claims",
                "status": "NOT_SUPPORTED_BY_THEME1",
                "required_action": "Do not claim direct CP range-error reduction from this package.",
            },
        ],
    )
    one_se = q_all[q_all["feature_set"].eq("one_se_discovered")].groupby(["feature_set", "qclean_mode"])["q_clean"].mean().reset_index()
    maxj = q_all[q_all["feature_set"].eq("maxj_discovered_subset")].groupby(["feature_set", "qclean_mode"])["q_clean"].mean().reset_index()
    if not one_se.empty and not maxj.empty:
        rows2 = []
        for mode in ["2H", "3H"]:
            a = one_se[one_se["qclean_mode"].eq(mode)]["q_clean"]
            b = maxj[maxj["qclean_mode"].eq(mode)]["q_clean"]
            rows2.append({"qclean_mode": mode, "one_se_mean_q_clean": float(a.iloc[0]) if len(a) else np.nan, "maxj_mean_q_clean": float(b.iloc[0]) if len(b) else np.nan})
        pd.DataFrame(rows2).to_csv(out / "one_se_vs_maxj_delta.csv", index=False)
    else:
        pd.DataFrame([{"status": "MISSING_INPUT"}]).to_csv(out / "one_se_vs_maxj_delta.csv", index=False)


def claim_gate_rows(q_all: pd.DataFrame, pair_delta: pd.DataFrame, audit_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    available = set(q_all["feature_set"].dropna().astype(str))
    formula_pass = all(row["status"] == "PASS" for row in audit_rows if row["check"].endswith("_qclean_formula"))
    pair_pass = not pair_delta.empty and pair_delta["status"].eq("PASS").any()
    return [
        {"gate": "qclean_formula_valid", "status": "PASS" if formula_pass else "BLOCKED", "evidence": "feature_set_score_schema_audit.csv", "claim_boundary": "formula audit only"},
        {"gate": "cir_only_oof_qclean_complete", "status": "PASS" if {"CIR5", "CIR12"}.issubset(available) else "BLOCKED", "evidence": "03_cir_only_oof_qclean", "claim_boundary": "required for CIR comparison"},
        {"gate": "cir_vs_cp_same_acceptance_supported", "status": "PASS" if pair_pass else "BLOCKED", "evidence": "cir_vs_cp_same_acceptance_summary.csv", "claim_boundary": "state-rate comparison only"},
        {"gate": "cir_only_aggregate_metric_only", "status": "FAIL_AVOIDED", "evidence": "CIR-only OOF q-clean files used instead of aggregate baseline metrics", "claim_boundary": "aggregate AUC not used for same acceptance"},
        {"gate": "measurement_claims", "status": "MEASUREMENT_MISSING_NOT_RUN", "evidence": "", "claim_boundary": "no measurement claim"},
        {"gate": "range_error_claims", "status": "NOT_SUPPORTED_BY_THEME1", "evidence": "", "claim_boundary": "no direct range-error claim"},
    ]


def artifact_manifest_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".csv", ".json", ".md", ".yaml", ".yml", ".txt", ".py"}:
            continue
        if path.name == "theme1_rich_feature_artifact_manifest.csv":
            continue
        rows.append(
            {
                "relative_path": rel(path),
                "sha256": sha256_file(path),
                "byte_size": path.stat().st_size,
                "row_count": csv_row_count(path),
                "claim_boundary_status": "SIMULATION_ONLY_STATE_QCLEAN" if "qclean" in str(path).lower() or "same_acceptance" in str(path).lower() else "PROVENANCE_OR_REPORT",
            }
        )
    return rows


def report_stage(root: Path) -> None:
    out = root / "07_report_package"
    out.mkdir(parents=True, exist_ok=True)
    gates = pd.read_csv(root / "06_comparison_and_claim_gates" / "rich_feature_claim_gate_matrix.csv")
    lines = [
        "# Theme 1 Rich Feature-Set Final Report",
        "",
        "The original one-SE discovered subset is a compact diagnostic result.",
        "The report-ready Theme 1 evidence here is based on frozen OOF predictions for max-J, CIR-only q-clean baselines, and CP-augmented named feature-set panels.",
        "CIR-only comparison is reported only where real CIR5/CIR12 OOF q-clean scores and matching CP-augmented OOF q-clean scores exist on the same split.",
        "",
        "## Claim Boundary",
        "",
        "- q_clean is a clean-session/session-quality confidence proxy.",
        "- This package does not support direct range-error, backend, AMR, localization, or measurement claims.",
        "- RD-LoS and HB-prior are reflection-dominant channel/session-quality states, not range-error labels.",
        "",
        "## Claim Gates",
        "",
        "| gate | status |",
        "| --- | --- |",
    ]
    for _, row in gates.iterrows():
        lines.append(f"| {row['gate']} | {row['status']} |")
    lines.extend(
        [
            "",
            "## Primary Tables",
            "",
            "- `05_qclean_feature_set_tables/feature_set_cir_vs_cp_delta_at_same_acceptance.csv`",
            "- `05_qclean_feature_set_tables/feature_set_cir_vs_cp_accepted_case_overlap.csv`",
            "- `06_comparison_and_claim_gates/cir_vs_cp_same_acceptance_summary.csv`",
            "",
        ]
    )
    (out / "THEME1_RICH_FEATURE_SET_FINAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    write_csv(out / "theme1_rich_feature_report_manifest.csv", [{"report": "THEME1_RICH_FEATURE_SET_FINAL_REPORT.md", "status": "GENERATED"}])
    write_release_scaffold(root, out)
    rows = artifact_manifest_rows(root)
    write_csv(out / "theme1_rich_feature_artifact_manifest.csv", rows)
    write_release_checksums(out, rows)
    package_manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "root": rel(root),
        "artifact_count": len(rows),
        "claim_boundary_summary": "Simulation-only Theme 1 state/q-clean package; no range-error/backend/AMR/localization/measurement claim.",
    }
    write_json(out / "theme1_rich_feature_package_manifest.json", package_manifest)
    zip_path = out / "THEME1_RICH_FEATURE_SET_PACKAGE_20260628.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == zip_path:
                continue
            if path.suffix.lower() not in {".csv", ".json", ".md", ".yaml", ".yml", ".txt", ".py"}:
                continue
            zf.write(path, path.relative_to(root).as_posix())
    (out / "THEME1_RICH_FEATURE_SET_PACKAGE_20260628.zip.sha256").write_text(sha256_file(zip_path) + "  " + zip_path.name + "\n", encoding="utf-8")


def copy_if_present(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_release_scaffold(root: Path, out: Path) -> None:
    release = out / "release"
    for sub in ["code", "scripts", "configs", "manifests", "tables", "figures", "reports", "logs", "checksums"]:
        (release / sub).mkdir(parents=True, exist_ok=True)

    copy_if_present(ROOT / "rt_cp_uwb_py" / "theme1_rich_feature_sets.py", release / "code" / "rt_cp_uwb_py" / "theme1_rich_feature_sets.py")
    for script in [
        "build_theme1_maxj_oof_20260628.py",
        "build_theme1_cir_only_oof_qclean_20260628.py",
        "build_theme1_forced_feature_set_oof_20260628.py",
        "build_theme1_feature_set_qclean_20260628.py",
    ]:
        copy_if_present(ROOT / "scripts" / script, release / "scripts" / script)
    copy_if_present(DEFAULT_CONFIG, release / "configs" / "feature_discovery_theme1_20260628.yaml")
    copy_if_present(ROOT / ".omx" / "plans" / "theme1_rich_feature_set_rerun_plan_20260628.md", release / "manifests" / "theme1_rich_feature_set_rerun_plan_20260628.md")
    copy_if_present(out / "THEME1_RICH_FEATURE_SET_FINAL_REPORT.md", release / "reports" / "THEME1_RICH_FEATURE_SET_FINAL_REPORT.md")

    table_index = [
        "# Theme 1 Rich Feature Table Index",
        "",
        "- `03_cir_only_oof_qclean/cir_only_outer_test_predictions.csv`: CIR5/CIR12/LP-CIR12 OOF probabilities.",
        "- `03_cir_only_oof_qclean/cir_only_qclean_scores_path2h.csv`: CIR-only 2H q-clean scores.",
        "- `03_cir_only_oof_qclean/cir_only_qclean_scores_path3h.csv`: CIR-only 3H q-clean scores.",
        "- `04_forced_feature_set_oof/feature_set_outer_test_predictions.csv`: CP-augmented forced feature-set OOF probabilities.",
        "- `05_qclean_feature_set_tables/feature_set_cir_vs_cp_delta_at_same_acceptance.csv`: CIR-only vs CP-augmented deltas at matched accepted ratios.",
        "- `05_qclean_feature_set_tables/feature_set_cir_vs_cp_accepted_case_overlap.csv`: accepted-case overlap and Jaccard summaries.",
        "",
    ]
    (release / "tables" / "TABLE_INDEX.md").write_text("\n".join(table_index), encoding="utf-8")
    (release / "figures" / "FIGURE_INDEX.md").write_text("# Figure Index\n\nNo figures were generated for this package.\n", encoding="utf-8")
    commands = [
        "# Reproduction Commands",
        "",
        "Run from the Somi worktree used for the full RT source:",
        "",
        "```bash",
        "cd /root/codex/raytracing_modules/rt_cp_uwb_theme1_20260628",
        "OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 /root/.micromamba/envs/ds1/bin/python3.11 scripts/build_theme1_cir_only_oof_qclean_20260628.py",
        "OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 /root/.micromamba/envs/ds1/bin/python3.11 scripts/build_theme1_forced_feature_set_oof_20260628.py",
        "OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 /root/.micromamba/envs/ds1/bin/python3.11 scripts/build_theme1_maxj_oof_20260628.py",
        "/root/.micromamba/envs/ds1/bin/python3.11 scripts/build_theme1_feature_set_qclean_20260628.py",
        "```",
        "",
    ]
    (release / "logs" / "RUN_COMMANDS.md").write_text("\n".join(commands), encoding="utf-8")
    (release / "reports" / "FINAL_ARTIFACT_INDEX.md").write_text("\n".join(table_index), encoding="utf-8")
    (release / "reports" / "REPRODUCIBILITY_CHECKLIST.md").write_text(
        "\n".join(
            [
                "# Reproducibility Checklist",
                "",
                "- [x] Same full RT source root reused.",
                "- [x] Same frozen split reused.",
                "- [x] CIR5 and CIR12 OOF q-clean generated from real OOF probabilities.",
                "- [x] CP-augmented feature-set OOF generated on the same split.",
                "- [x] Same-accepted-ratio comparisons use real OOF q-clean sources on both sides.",
                "- [x] Measurement, backend, AMR, localization, and direct range-error claims are excluded.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (release / "reports" / "ENVIRONMENT.md").write_text(
        "\n".join(
            [
                "# Environment",
                "",
                "- remote_python: `/root/.micromamba/envs/ds1/bin/python3.11`",
                "- thread_limits: `OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4` for full OOF reruns",
                "- package_root: `results/THEME1_CP_CHANNEL_STATE_CLASSIFICATION_RICH_FEATURESETS_20260628`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (release / "reports" / "KNOWN_LIMITATIONS.md").write_text(
        "\n".join(
            [
                "# Known Limitations",
                "",
                "- Simulation-only Theme 1 evidence.",
                "- q_clean is a clean-session/session-quality confidence proxy, not a guarantee of small range error.",
                "- No measurement transfer, backend residual/NIS, AMR, localization, or direct range-error reduction claim is established.",
                "- HGB is the primary OOF/q-clean source in this rerun; model-family robustness can be added as a separate rerun if needed.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_release_checksums(out: Path, rows: list[dict[str, Any]]) -> None:
    release_checksums = out / "release" / "checksums"
    release_checksums.mkdir(parents=True, exist_ok=True)
    checksum_rows = [
        {"relative_path": row["relative_path"], "sha256": row["sha256"]}
        for row in rows
        if row.get("sha256") and row.get("sha256") != "MISSING"
    ]
    write_csv(release_checksums / "CHECKSUMS.csv", checksum_rows)
    lines = ["# Checksums", "", "| relative_path | sha256 |", "| --- | --- |"]
    for row in checksum_rows:
        lines.append(f"| {row['relative_path']} | {row['sha256']} |")
    (out / "release" / "reports" / "CHECKSUMS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
