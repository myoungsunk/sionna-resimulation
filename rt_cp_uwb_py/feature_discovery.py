from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TargetSpec:
    name: str
    label_col: str
    mask: str
    weight: float


@dataclass(frozen=True)
class SplitSpec:
    name: str
    train_idx: np.ndarray
    test_idx: np.ndarray


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_seed(seed: int, *parts: object) -> int:
    payload = "|".join(map(str, parts)).encode("utf-8")
    return int(seed + zlib.crc32(payload) % 1_000_000)


def unique(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def read_yaml(path: Path) -> dict:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("PyYAML is required for feature discovery configs") from exc
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Config is not a mapping: {path}")
    return data


def repo_path(path_like: str | Path, root: Path = ROOT) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return root / path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def target_specs(config: dict) -> list[TargetSpec]:
    specs = []
    for item in config.get("targets", []):
        specs.append(
            TargetSpec(
                name=str(item["name"]),
                label_col=str(item["label_col"]),
                mask=str(item.get("mask", "all")),
                weight=float(item.get("weight", 0.0)),
            )
        )
    if not specs:
        raise ValueError("No targets configured")
    return specs


def target_mask(df: pd.DataFrame, spec: TargetSpec) -> np.ndarray:
    if spec.mask == "all":
        return np.ones(len(df), dtype=bool)
    if spec.mask == "has_los":
        if "has_los" in df.columns:
            return df["has_los"].astype(bool).to_numpy()
        if "has_los_path" in df.columns:
            return df["has_los_path"].astype(bool).to_numpy()
        return np.ones(len(df), dtype=bool)
    raise ValueError(f"Unknown target mask: {spec.mask}")


def safe_auc(y: np.ndarray, score: np.ndarray) -> float:
    mask = np.isfinite(score)
    if int(mask.sum()) < 3 or len(np.unique(y[mask])) < 2:
        return float("nan")
    return float(roc_auc_score(y[mask], score[mask]))


def safe_pr_auc(y: np.ndarray, score: np.ndarray) -> float:
    mask = np.isfinite(score)
    if int(mask.sum()) < 3 or len(np.unique(y[mask])) < 2:
        return float("nan")
    return float(average_precision_score(y[mask], score[mask]))


def safe_balanced_accuracy(y: np.ndarray, score: np.ndarray, threshold: float = 0.5) -> float:
    mask = np.isfinite(score)
    if int(mask.sum()) < 3 or len(np.unique(y[mask])) < 2:
        return float("nan")
    return float(balanced_accuracy_score(y[mask], (score[mask] >= threshold).astype(int)))


def score_to_probability(score: np.ndarray) -> np.ndarray:
    out = np.asarray(score, dtype=float).copy()
    finite = np.isfinite(out)
    if not finite.any():
        return out
    if np.nanmin(out) >= -1e-9 and np.nanmax(out) <= 1.0 + 1e-9:
        return np.clip(out, 0.0, 1.0)
    clipped = np.clip(out[finite], -35.0, 35.0)
    out[finite] = 1.0 / (1.0 + np.exp(-clipped))
    return out


def make_model(name: str, seed: int, hgb_iter: int = 60):
    name_u = name.strip().upper()
    if name_u in {"LOGREG", "LOGISTIC", "LR"}:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=3000, class_weight="balanced", random_state=seed),
        )
    if name_u in {"HGB", "HISTGRADIENTBOOSTING"}:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            HistGradientBoostingClassifier(max_iter=hgb_iter, learning_rate=0.06, random_state=seed),
        )
    if name_u in {"LINEARSVM", "SVM"}:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LinearSVC(class_weight="balanced", dual=False, max_iter=5000, random_state=seed),
        )
    if name_u in {"RF", "RANDOMFOREST"}:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=120,
                max_depth=8,
                min_samples_leaf=5,
                class_weight="balanced_subsample",
                n_jobs=1,
                random_state=seed,
            ),
        )
    raise ValueError(f"Unknown model: {name}")


def model_scores(model, x: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(x)[:, 1], dtype=float)
    if hasattr(model, "decision_function"):
        return score_to_probability(np.asarray(model.decision_function(x), dtype=float))
    return np.asarray(model.predict(x), dtype=float)


def numeric_frame(df: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    return df.loc[:, list(features)].apply(pd.to_numeric, errors="coerce")


def load_merged_tables(config: dict, root: Path = ROOT, max_rows: int | None = None) -> pd.DataFrame:
    inputs = config["inputs"]
    case_key = inputs.get("case_key", "case_id")
    feature_path = repo_path(inputs["feature_table"], root)
    label_path = repo_path(inputs["label_table"], root)
    split_path = repo_path(inputs["split_table"], root)

    feature = pd.read_csv(feature_path, nrows=max_rows)
    label = pd.read_csv(label_path)
    split = pd.read_csv(split_path)

    keep_label = [case_key] + [c for c in label.columns if c != case_key and c not in feature.columns]
    merged = feature.merge(label[keep_label], on=case_key, how="left", validate="one_to_one")

    split_cols = [case_key] + [c for c in split.columns if c != case_key]
    for col in split_cols:
        if col != case_key and col in merged.columns:
            merged = merged.drop(columns=[col])
    merged = merged.merge(split[split_cols], on=case_key, how="left", validate="one_to_one")
    return merged


def input_file_manifest(config: dict, root: Path = ROOT) -> pd.DataFrame:
    rows = []
    for role, value in config.get("inputs", {}).items():
        if not str(role).endswith("_table"):
            continue
        path = repo_path(value, root)
        rows.append(
            {
                "role": role,
                "path": str(path.relative_to(root) if path.is_relative_to(root) else path),
                "status": "PRESENT" if path.exists() else "MISSING",
                "bytes": path.stat().st_size if path.exists() else "",
                "sha256": sha256_file(path) if path.exists() else "",
            }
        )
    return pd.DataFrame(rows)


def audit_candidate_pools(df: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    pools = config.get("candidate_pools", {})
    rows = []
    routed: dict[str, list[str]] = {}
    forbidden = set(pools.get("forbidden_main", []))
    for route, features in pools.items():
        routed[route] = []
        for feature in unique(features):
            present = feature in df.columns
            numeric_ok = False
            missing_rate = float("nan")
            variance = float("nan")
            if present:
                values = pd.to_numeric(df[feature], errors="coerce")
                numeric_ok = values.notna().sum() > 0
                missing_rate = float(values.isna().mean())
                variance = float(values.var(skipna=True)) if numeric_ok else float("nan")
            main_allowed = (
                present
                and numeric_ok
                and feature not in forbidden
                and route in {"cir_main_observable", "cp_main_observable"}
            )
            if main_allowed:
                routed[route].append(feature)
            rows.append(
                {
                    "feature": feature,
                    "route": route,
                    "present": bool(present),
                    "numeric_ok": bool(numeric_ok),
                    "missing_rate": missing_rate,
                    "variance": variance,
                    "main_allowed": bool(main_allowed),
                    "decision": "main_candidate" if main_allowed else ("missing_or_non_numeric" if not present or not numeric_ok else route),
                }
            )
    return pd.DataFrame(rows), routed


def forbidden_feature_audit(df: pd.DataFrame, config: dict, main_features: Sequence[str]) -> pd.DataFrame:
    forbidden = set(config.get("candidate_pools", {}).get("forbidden_main", []))
    rows = []
    for feature in sorted(forbidden):
        rows.append(
            {
                "feature": feature,
                "present": bool(feature in df.columns),
                "in_main_pool": bool(feature in set(main_features)),
                "decision": "FAIL_IN_MAIN_POOL" if feature in set(main_features) else "excluded",
            }
        )
    return pd.DataFrame(rows)


def build_outer_splits(df: pd.DataFrame, split_key: str = "split_fold", requested: str | None = None) -> list[SplitSpec]:
    if split_key not in df.columns:
        raise ValueError(f"Missing split key: {split_key}")
    folds = sorted(pd.Series(df[split_key]).dropna().unique().tolist())
    if requested:
        wanted: list[object] = []
        for item in requested.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                key, val = item.split(":", 1)
                if key != split_key:
                    raise ValueError(f"Unsupported outer split selector: {item}")
                item = val
            try:
                wanted.append(int(item))
            except ValueError:
                wanted.append(item)
        folds = [f for f in folds if f in wanted or str(f) in {str(w) for w in wanted}]
    splits = []
    values = df[split_key].to_numpy()
    for fold in folds:
        test_idx = np.flatnonzero(values == fold)
        train_idx = np.flatnonzero(values != fold)
        if len(test_idx) == 0 or len(train_idx) == 0:
            continue
        splits.append(SplitSpec(name=f"{split_key}_{fold}", train_idx=train_idx, test_idx=test_idx))
    if not splits:
        raise ValueError("No outer splits built")
    return splits


def build_inner_splits(df: pd.DataFrame, train_idx: np.ndarray, split_key: str = "split_fold") -> list[tuple[np.ndarray, np.ndarray]]:
    train_idx = np.asarray(train_idx, dtype=int)
    fold_values = df.iloc[train_idx][split_key].to_numpy()
    folds = sorted(pd.Series(fold_values).dropna().unique().tolist())
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for fold in folds:
        val_local = np.flatnonzero(fold_values == fold)
        tr_local = np.flatnonzero(fold_values != fold)
        if len(val_local) == 0 or len(tr_local) == 0:
            continue
        splits.append((train_idx[tr_local], train_idx[val_local]))
    if len(splits) >= 2:
        return splits
    # Fallback for smoke subsets where only one frozen fold remains.
    n = len(train_idx)
    if n < 20:
        return [(train_idx, train_idx)]
    chunks = np.array_split(train_idx, min(3, n))
    for chunk in chunks:
        val = np.asarray(chunk, dtype=int)
        tr = np.setdiff1d(train_idx, val, assume_unique=False)
        if len(tr) and len(val):
            splits.append((tr, val))
    return splits


def split_preflight(df: pd.DataFrame, config: dict, outer_splits: Sequence[SplitSpec]) -> pd.DataFrame:
    specs = target_specs(config)
    group_key = config["inputs"].get("group_key", "pose_group_id")
    rows = []
    for split in outer_splits:
        train_groups = set(df.iloc[split.train_idx][group_key].tolist()) if group_key in df.columns else set()
        test_groups = set(df.iloc[split.test_idx][group_key].tolist()) if group_key in df.columns else set()
        overlap = len(train_groups.intersection(test_groups)) if train_groups and test_groups else 0
        base = {
            "outer_split": split.name,
            "n_train": int(len(split.train_idx)),
            "n_test": int(len(split.test_idx)),
            "group_overlap": int(overlap),
        }
        for spec in specs:
            for part, idx in [("train", split.train_idx), ("test", split.test_idx)]:
                sub = df.iloc[idx]
                mask = target_mask(sub, spec)
                if spec.label_col not in sub.columns:
                    n_pos = np.nan
                    n = int(mask.sum())
                else:
                    y = sub.loc[mask, spec.label_col].astype(bool).astype(int)
                    n_pos = int(y.sum())
                    n = int(len(y))
                rows.append({**base, "target": spec.name, "part": part, "n": n, "n_pos": n_pos})
    return pd.DataFrame(rows)


def fit_predict_cv(
    df: pd.DataFrame,
    features: Sequence[str],
    spec: TargetSpec,
    splits: Sequence[tuple[np.ndarray, np.ndarray]],
    model_name: str,
    seed: int,
    hgb_iter: int = 60,
) -> np.ndarray:
    pred = np.full(len(df), np.nan, dtype=float)
    if not features or any(f not in df.columns for f in features) or spec.label_col not in df.columns:
        return pred
    mask_all = target_mask(df, spec)
    for fold_i, (train_idx, val_idx) in enumerate(splits):
        tr = np.asarray([i for i in train_idx if mask_all[i]], dtype=int)
        va = np.asarray([i for i in val_idx if mask_all[i]], dtype=int)
        if len(tr) < 10 or len(va) < 3:
            continue
        y_train = df.iloc[tr][spec.label_col].astype(bool).astype(int).to_numpy()
        y_val = df.iloc[va][spec.label_col].astype(bool).astype(int).to_numpy()
        if len(np.unique(y_train)) < 2 or len(np.unique(y_val)) < 2:
            continue
        x_train = numeric_frame(df.iloc[tr], features)
        x_val = numeric_frame(df.iloc[va], features)
        model = make_model(model_name, stable_seed(seed, spec.name, tuple(features), fold_i), hgb_iter=hgb_iter)
        model.fit(x_train, y_train)
        pred[va] = model_scores(model, x_val)
    return pred


def evaluate_cv(
    df: pd.DataFrame,
    features: Sequence[str],
    specs: Sequence[TargetSpec],
    splits: Sequence[tuple[np.ndarray, np.ndarray]],
    model_name: str,
    seed: int,
    hgb_iter: int = 60,
) -> tuple[dict[str, dict[str, float]], dict[str, np.ndarray]]:
    metrics: dict[str, dict[str, float]] = {}
    preds: dict[str, np.ndarray] = {}
    for spec in specs:
        pred = fit_predict_cv(df, features, spec, splits, model_name, seed, hgb_iter=hgb_iter)
        mask = target_mask(df, spec) & np.isfinite(pred)
        if spec.label_col in df.columns and mask.sum() > 0:
            y = df.loc[mask, spec.label_col].astype(bool).astype(int).to_numpy()
            score = pred[mask]
        else:
            y = np.array([], dtype=int)
            score = np.array([], dtype=float)
        metrics[spec.name] = {
            "AUC": safe_auc(y, score),
            "PR_AUC": safe_pr_auc(y, score),
            "balanced_accuracy": safe_balanced_accuracy(y, score),
            "n": int(len(y)),
            "n_pos": int(y.sum()) if len(y) else 0,
        }
        preds[spec.name] = pred
    return metrics, preds


def mean_abs_corr(df: pd.DataFrame, features: Sequence[str]) -> float:
    present = [f for f in features if f in df.columns]
    if len(present) < 2:
        return 0.0
    corr = numeric_frame(df, present).corr(method="spearman").abs()
    vals = corr.to_numpy(dtype=float)
    mask = np.triu(np.ones(vals.shape, dtype=bool), k=1)
    selected = vals[mask]
    selected = selected[np.isfinite(selected)]
    return float(np.nanmean(selected)) if len(selected) else 0.0


def rescue_stats(
    df: pd.DataFrame,
    spec: TargetSpec,
    base_pred: np.ndarray | None,
    cand_pred: np.ndarray,
) -> dict[str, float]:
    if base_pred is None or spec.label_col not in df.columns:
        return {"rescue": float("nan"), "clean_false_alarm": float("nan"), "harm": float("nan")}
    mask = target_mask(df, spec) & np.isfinite(base_pred) & np.isfinite(cand_pred)
    if mask.sum() == 0:
        return {"rescue": float("nan"), "clean_false_alarm": float("nan"), "harm": float("nan")}
    y = df.loc[mask, spec.label_col].astype(bool).astype(int).to_numpy()
    b = (base_pred[mask] >= 0.5).astype(int)
    c = (cand_pred[mask] >= 0.5).astype(int)
    base_wrong = b != y
    base_correct = b == y
    rescue_den = int(base_wrong.sum())
    rescue = float(((base_wrong) & (c == y)).sum() / rescue_den) if rescue_den else 0.0
    clean_mask = y == 0
    clean_correct = clean_mask & base_correct
    clean_den = int(clean_correct.sum())
    clean_false_alarm = float((clean_correct & (c != y)).sum() / clean_den) if clean_den else 0.0
    harm_den = int(base_correct.sum())
    harm = float((base_correct & (c != y)).sum() / harm_den) if harm_den else 0.0
    return {"rescue": rescue, "clean_false_alarm": clean_false_alarm, "harm": harm}


def objective_score(
    df: pd.DataFrame,
    features: Sequence[str],
    metrics: dict[str, dict[str, float]],
    specs: Sequence[TargetSpec],
    cp_features: Sequence[str],
    search_cfg: dict,
    rescue_by_target: dict[str, dict[str, float]] | None = None,
) -> float:
    j = 0.0
    total_w = 0.0
    for spec in specs:
        if spec.weight <= 0:
            continue
        auc = metrics.get(spec.name, {}).get("AUC", float("nan"))
        if math.isfinite(auc):
            j += spec.weight * auc
            total_w += spec.weight
    if total_w > 0:
        j /= total_w
    redundancy = mean_abs_corr(df, features)
    j -= float(search_cfg.get("lambda_size", 0.003)) * len(features)
    j -= float(search_cfg.get("mu_redundancy", 0.010)) * redundancy
    if rescue_by_target:
        rescue_rd = rescue_by_target.get("RDLoS", {}).get("rescue", 0.0)
        rescue_hb = rescue_by_target.get("HBprior", {}).get("rescue", 0.0)
        penalty_clean = rescue_by_target.get("notclean3H", {}).get("clean_false_alarm", 0.0)
        rescue_term = (0.0 if not math.isfinite(rescue_rd) else rescue_rd)
        rescue_term += (0.0 if not math.isfinite(rescue_hb) else rescue_hb)
        rescue_term -= (0.0 if not math.isfinite(penalty_clean) else penalty_clean)
        rescue_term -= float(search_cfg.get("lambda_cp", 0.002)) * len([f for f in features if f in set(cp_features)])
        j += float(search_cfg.get("alpha_rescue", 0.10)) * rescue_term
    return float(j)


def subset_counts(features: Sequence[str], cir_features: Sequence[str], cp_features: Sequence[str]) -> tuple[int, int]:
    cir = set(cir_features)
    cp = set(cp_features)
    return sum(1 for f in features if f in cir), sum(1 for f in features if f in cp)


def subset_id(features: Sequence[str]) -> str:
    payload = ";".join(sorted(features)).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def univariate_screening(
    df: pd.DataFrame,
    features: Sequence[str],
    specs: Sequence[TargetSpec],
    splits: Sequence[tuple[np.ndarray, np.ndarray]],
    model_name: str,
    seed: int,
    outer_split: str,
    feature_group: str,
    hgb_iter: int = 60,
) -> pd.DataFrame:
    rows = []
    for feature in features:
        metrics, _ = evaluate_cv(df, [feature], specs, splits, model_name, seed, hgb_iter=hgb_iter)
        values = pd.to_numeric(df[feature], errors="coerce")
        for spec in specs:
            rows.append(
                {
                    "outer_split": outer_split,
                    "feature": feature,
                    "group": feature_group,
                    "target": spec.name,
                    "AUC": metrics[spec.name]["AUC"],
                    "PR_AUC": metrics[spec.name]["PR_AUC"],
                    "balanced_accuracy": metrics[spec.name]["balanced_accuracy"],
                    "missing_rate": float(values.isna().mean()),
                    "variance": float(values.var(skipna=True)) if values.notna().sum() else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def select_screened_features(
    ranking: pd.DataFrame,
    group: str,
    top_n: int,
    auc_keep: float,
) -> list[str]:
    sub = ranking[ranking["group"].eq(group)].copy()
    if sub.empty:
        return []
    agg = (
        sub.groupby("feature", as_index=False)
        .agg(max_auc=("AUC", "max"), max_pr_auc=("PR_AUC", "max"), missing_rate=("missing_rate", "max"))
        .sort_values(["max_auc", "max_pr_auc"], ascending=False)
    )
    keep = agg[(agg["max_auc"] >= auc_keep) & (agg["missing_rate"] <= 0.80)]["feature"].tolist()
    if len(keep) < min(top_n, len(agg)):
        keep = unique(keep + agg.head(top_n)["feature"].tolist())
    return keep[:top_n]


def correlation_clusters(df: pd.DataFrame, features: Sequence[str], threshold: float, outer_split: str) -> pd.DataFrame:
    rows = []
    present = [f for f in features if f in df.columns]
    if len(present) < 2:
        return pd.DataFrame(columns=["outer_split", "feature_a", "feature_b", "abs_spearman", "cluster_decision"])
    corr = numeric_frame(df, present).corr(method="spearman").abs()
    for a, b in combinations(present, 2):
        value = float(corr.loc[a, b])
        rows.append(
            {
                "outer_split": outer_split,
                "feature_a": a,
                "feature_b": b,
                "abs_spearman": value,
                "cluster_decision": "redundant_pair" if math.isfinite(value) and value >= threshold else "kept_pair",
            }
        )
    return pd.DataFrame(rows)


def evaluate_subset_row(
    df: pd.DataFrame,
    features: Sequence[str],
    specs: Sequence[TargetSpec],
    splits: Sequence[tuple[np.ndarray, np.ndarray]],
    model_name: str,
    seed: int,
    outer_split: str,
    cir_features: Sequence[str],
    cp_features: Sequence[str],
    search_cfg: dict,
    base_preds: dict[str, np.ndarray] | None = None,
    hgb_iter: int = 60,
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    metrics, preds = evaluate_cv(df, features, specs, splits, model_name, seed, hgb_iter=hgb_iter)
    rescue: dict[str, dict[str, float]] = {}
    if base_preds:
        for spec in specs:
            rescue[spec.name] = rescue_stats(df, spec, base_preds.get(spec.name), preds[spec.name])
    j = objective_score(df, features, metrics, specs, cp_features, search_cfg, rescue)
    n_cir, n_cp = subset_counts(features, cir_features, cp_features)
    row: dict[str, object] = {
        "outer_split": outer_split,
        "subset_id": subset_id(features),
        "features": ";".join(features),
        "CIR_features": ";".join([f for f in features if f in set(cir_features)]),
        "CP_features": ";".join([f for f in features if f in set(cp_features)]),
        "n_features": int(len(features)),
        "n_CIR": int(n_cir),
        "n_CP": int(n_cp),
        "J": j,
        "mean_corr": mean_abs_corr(df, features),
    }
    for spec in specs:
        prefix = spec.name
        row[f"AUC_{prefix}"] = metrics[spec.name]["AUC"]
        row[f"PR_AUC_{prefix}"] = metrics[spec.name]["PR_AUC"]
        if rescue:
            row[f"rescue_{prefix}"] = rescue[spec.name]["rescue"]
            row[f"clean_false_alarm_{prefix}"] = rescue[spec.name]["clean_false_alarm"]
    return row, preds


def beam_search(
    df: pd.DataFrame,
    candidate_features: Sequence[str],
    specs: Sequence[TargetSpec],
    splits: Sequence[tuple[np.ndarray, np.ndarray]],
    model_name: str,
    seed: int,
    outer_split: str,
    cir_features: Sequence[str],
    cp_features: Sequence[str],
    search_cfg: dict,
    require_cp: bool = False,
    require_cir: bool = False,
    base_preds: dict[str, np.ndarray] | None = None,
    hgb_iter: int = 60,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    max_total = int(search_cfg.get("max_total_features", 8))
    max_cir = int(search_cfg.get("max_cir_features", 5))
    max_cp = int(search_cfg.get("max_cp_features", 5))
    beam_width = int(search_cfg.get("beam_width", 20))

    candidate_features = unique([f for f in candidate_features if f in df.columns])
    cache: dict[tuple[str, ...], tuple[dict[str, object], dict[str, np.ndarray]]] = {}
    rows: list[dict[str, object]] = []

    def valid(features: Sequence[str]) -> bool:
        n_cir, n_cp = subset_counts(features, cir_features, cp_features)
        if n_cir > max_cir or n_cp > max_cp or len(features) > max_total:
            return False
        return True

    def eval_features(features: Sequence[str]) -> tuple[dict[str, object], dict[str, np.ndarray]]:
        key = tuple(sorted(features))
        if key not in cache:
            cache[key] = evaluate_subset_row(
                df,
                list(key),
                specs,
                splits,
                model_name,
                seed,
                outer_split,
                cir_features,
                cp_features,
                search_cfg,
                base_preds=base_preds,
                hgb_iter=hgb_iter,
            )
        return cache[key]

    beam: list[tuple[str, ...]] = []
    for feature in candidate_features:
        if not valid([feature]):
            continue
        row, _ = eval_features([feature])
        rows.append(row)
        beam.append(tuple([feature]))
    beam = [tuple(str(x) for x in r["features"].split(";") if x) for r in sorted(rows, key=lambda r: r["J"], reverse=True)[:beam_width]]

    for _size in range(2, max_total + 1):
        candidates: set[tuple[str, ...]] = set()
        for subset in beam:
            for feature in candidate_features:
                if feature in subset:
                    continue
                new_subset = tuple(sorted(set(subset).union([feature])))
                if valid(new_subset):
                    candidates.add(new_subset)
        if not candidates:
            break
        scored: list[dict[str, object]] = []
        for features in sorted(candidates):
            row, _ = eval_features(features)
            rows.append(row)
            scored.append(row)
        beam = [tuple(str(x) for x in r["features"].split(";") if x) for r in sorted(scored, key=lambda r: r["J"], reverse=True)[:beam_width]]

    out = pd.DataFrame(rows).drop_duplicates(subset=["outer_split", "subset_id"])
    if out.empty:
        return out, {}
    if require_cp:
        out = out[out["n_CP"] > 0]
    if require_cir:
        out = out[out["n_CIR"] > 0]
    if out.empty:
        return out, {}
    out = out.sort_values(["J", "n_features"], ascending=[False, True]).reset_index(drop=True)
    best_features = [x for x in str(out.iloc[0]["features"]).split(";") if x]
    _, best_preds = eval_features(best_features)
    return out, best_preds


def pareto_front(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    metric_cols = [c for c in ["J", "AUC_RDLoS", "AUC_HBprior"] if c in df.columns]
    front = []
    for idx, row in df.iterrows():
        dominated = False
        for jdx, other in df.iterrows():
            if idx == jdx:
                continue
            better_or_equal = all(float(other[c]) >= float(row[c]) for c in metric_cols if pd.notna(other[c]) and pd.notna(row[c]))
            strictly_better = any(float(other[c]) > float(row[c]) for c in metric_cols if pd.notna(other[c]) and pd.notna(row[c]))
            no_more_features = int(other["n_features"]) <= int(row["n_features"])
            if better_or_equal and strictly_better and no_more_features:
                dominated = True
                break
        if not dominated:
            front.append(row.to_dict())
    return pd.DataFrame(front).sort_values(["J", "n_features"], ascending=[False, True]).reset_index(drop=True)


def choose_one_se(leaderboard: pd.DataFrame, tolerance: float) -> pd.Series:
    if leaderboard.empty:
        raise ValueError("Empty leaderboard")
    best = float(leaderboard["J"].max())
    eligible = leaderboard[leaderboard["J"] >= best - tolerance].copy()
    eligible = eligible.sort_values(["n_features", "n_CP", "mean_corr", "J"], ascending=[True, True, True, False])
    return eligible.iloc[0]


def pair_synergy_map(
    df: pd.DataFrame,
    cir_features: Sequence[str],
    cp_features: Sequence[str],
    specs: Sequence[TargetSpec],
    splits: Sequence[tuple[np.ndarray, np.ndarray]],
    model_name: str,
    seed: int,
    outer_split: str,
    search_cfg: dict,
    hgb_iter: int = 60,
) -> dict[str, pd.DataFrame]:
    single_cache: dict[str, dict[str, float]] = {}
    for feature in unique(list(cir_features) + list(cp_features)):
        metrics, _ = evaluate_cv(df, [feature], specs, splits, model_name, seed, hgb_iter=hgb_iter)
        single_cache[feature] = {spec.name: metrics[spec.name]["AUC"] for spec in specs}
    by_target: dict[str, list[dict[str, object]]] = {spec.name: [] for spec in specs}
    for cir in cir_features:
        for cp in cp_features:
            row, _ = evaluate_subset_row(
                df,
                [cir, cp],
                specs,
                splits,
                model_name,
                seed,
                outer_split,
                cir_features,
                cp_features,
                search_cfg,
                hgb_iter=hgb_iter,
            )
            for spec in specs:
                auc_pair = row.get(f"AUC_{spec.name}", float("nan"))
                auc_cir = single_cache.get(cir, {}).get(spec.name, float("nan"))
                auc_cp = single_cache.get(cp, {}).get(spec.name, float("nan"))
                if math.isfinite(float(auc_pair)) and math.isfinite(float(auc_cir)) and math.isfinite(float(auc_cp)):
                    synergy = float(auc_pair) - max(float(auc_cir), float(auc_cp))
                    gain = float(auc_pair) - float(auc_cir)
                else:
                    synergy = float("nan")
                    gain = float("nan")
                by_target[spec.name].append(
                    {
                        "outer_split": outer_split,
                        "CIR_feature": cir,
                        "CP_feature": cp,
                        "AUC_pair": auc_pair,
                        "AUC_CIR": auc_cir,
                        "AUC_CP": auc_cp,
                        "synergy": synergy,
                        "gain_cp_given_cir": gain,
                    }
                )
    return {target: pd.DataFrame(rows) for target, rows in by_target.items()}


def fit_predict_outer(
    df: pd.DataFrame,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    features: Sequence[str],
    specs: Sequence[TargetSpec],
    model_name: str,
    seed: int,
    hgb_iter: int = 60,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows = []
    pred = pd.DataFrame({"row_index": test_idx, "case_id": df.iloc[test_idx]["case_id"].to_numpy() if "case_id" in df.columns else test_idx})
    for spec in specs:
        scores = np.full(len(test_idx), np.nan, dtype=float)
        mask_all = target_mask(df, spec)
        tr = np.asarray([i for i in train_idx if mask_all[i]], dtype=int)
        te = np.asarray([i for i in test_idx if mask_all[i]], dtype=int)
        if len(tr) >= 10 and len(te) >= 3 and spec.label_col in df.columns and all(f in df.columns for f in features):
            y_train = df.iloc[tr][spec.label_col].astype(bool).astype(int).to_numpy()
            y_test = df.iloc[te][spec.label_col].astype(bool).astype(int).to_numpy()
            if len(np.unique(y_train)) >= 2 and len(np.unique(y_test)) >= 2:
                model = make_model(model_name, stable_seed(seed, model_name, spec.name, tuple(features)), hgb_iter=hgb_iter)
                model.fit(numeric_frame(df.iloc[tr], features), y_train)
                score_te = model_scores(model, numeric_frame(df.iloc[te], features))
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
                    }
                )
            else:
                metric_rows.append({"target": spec.name, "model": model_name, "AUC": np.nan, "PR_AUC": np.nan, "balanced_accuracy": np.nan, "n": int(len(te)), "n_pos": int(y_test.sum()) if len(te) else 0})
        else:
            metric_rows.append({"target": spec.name, "model": model_name, "AUC": np.nan, "PR_AUC": np.nan, "balanced_accuracy": np.nan, "n": int(len(te)), "n_pos": np.nan})
        pred[f"{model_name}_{spec.name}"] = scores
    return pd.DataFrame(metric_rows), pred


def residualize_cp(
    df: pd.DataFrame,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    cir_features: Sequence[str],
    cp_features: Sequence[str],
    shuffled: bool,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts = [numeric_frame(df.iloc[train_idx], cir_features).reset_index(drop=True)]
    test_parts = [numeric_frame(df.iloc[test_idx], cir_features).reset_index(drop=True)]
    rng = np.random.default_rng(seed)
    x_train = numeric_frame(df.iloc[train_idx], cir_features)
    x_test = numeric_frame(df.iloc[test_idx], cir_features)
    for cp in cp_features:
        y_train = pd.to_numeric(df.iloc[train_idx][cp], errors="coerce").reset_index(drop=True)
        y_test = pd.to_numeric(df.iloc[test_idx][cp], errors="coerce").reset_index(drop=True)
        if shuffled:
            y_train = pd.Series(rng.permutation(y_train.to_numpy()), index=y_train.index)
        if y_train.notna().sum() < 3:
            tr_resid = pd.Series(np.nan, index=range(len(train_idx)))
            te_resid = pd.Series(np.nan, index=range(len(test_idx)))
        else:
            reg = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))
            reg.fit(x_train, y_train.fillna(float(y_train.median())))
            tr_resid = pd.Series(y_train.to_numpy(dtype=float) - reg.predict(x_train))
            te_resid = pd.Series(y_test.to_numpy(dtype=float) - reg.predict(x_test))
        name = ("resid_shuf_" if shuffled else "resid_") + cp
        train_parts.append(pd.DataFrame({name: tr_resid}))
        test_parts.append(pd.DataFrame({name: te_resid}))
    return pd.concat(train_parts, axis=1), pd.concat(test_parts, axis=1)


def outer_residual_control(
    df: pd.DataFrame,
    split: SplitSpec,
    selected_cir: Sequence[str],
    selected_cp: Sequence[str],
    specs: Sequence[TargetSpec],
    model_name: str,
    seed: int,
    shuffled: bool = False,
    hgb_iter: int = 60,
) -> pd.DataFrame:
    if not selected_cp or not selected_cir:
        return pd.DataFrame()
    x_train, x_test = residualize_cp(df, split.train_idx, split.test_idx, selected_cir, selected_cp, shuffled, seed)
    feature_cols = list(x_train.columns)
    rows = []
    for spec in specs:
        tr_mask = target_mask(df.iloc[split.train_idx], spec)
        te_mask = target_mask(df.iloc[split.test_idx], spec)
        tr_pos = np.flatnonzero(tr_mask)
        te_pos = np.flatnonzero(te_mask)
        if len(tr_pos) < 10 or len(te_pos) < 3:
            continue
        y_train = df.iloc[split.train_idx[tr_pos]][spec.label_col].astype(bool).astype(int).to_numpy()
        y_test = df.iloc[split.test_idx[te_pos]][spec.label_col].astype(bool).astype(int).to_numpy()
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            continue
        model = make_model(model_name, stable_seed(seed, "residual", split.name, spec.name, shuffled), hgb_iter=hgb_iter)
        model.fit(x_train.iloc[tr_pos][feature_cols], y_train)
        score = model_scores(model, x_test.iloc[te_pos][feature_cols])
        rows.append(
            {
                "outer_split": split.name,
                "control": "residual_shuffled_cp" if shuffled else "residual_cp",
                "target": spec.name,
                "model": model_name,
                "AUC": safe_auc(y_test, score),
                "PR_AUC": safe_pr_auc(y_test, score),
                "balanced_accuracy": safe_balanced_accuracy(y_test, score),
                "n": int(len(y_test)),
                "n_pos": int(y_test.sum()),
            }
        )
    return pd.DataFrame(rows)


def qclean_tables(predictions: pd.DataFrame, model_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    def col(name: str) -> pd.Series:
        key = f"{model_name}_{name}"
        if key not in predictions.columns:
            return pd.Series(np.nan, index=predictions.index)
        return score_to_probability(pd.to_numeric(predictions[key], errors="coerce").to_numpy())

    p_nolos = col("NoLoS")
    p_rd = col("RDLoS")
    p_hbnear = col("HBnear")
    p_hbprior = col("HBprior")
    path2h = pd.DataFrame(
        {
            "case_id": predictions["case_id"],
            "p_NoLoS": p_nolos,
            "p_RD": p_rd,
            "q_clean": (1.0 - p_nolos) * (1.0 - p_rd),
            "score_status": f"OUTER_HELDOUT_{model_name}_UNCALIBRATED",
        }
    )
    path3h = pd.DataFrame(
        {
            "case_id": predictions["case_id"],
            "p_NoLoS": p_nolos,
            "p_HBnear": p_hbnear,
            "p_HBprior": p_hbprior,
            "q_clean": (1.0 - p_nolos) * (1.0 - p_hbnear) * (1.0 - p_hbprior),
            "score_status": f"OUTER_HELDOUT_{model_name}_UNCALIBRATED",
        }
    )
    return path2h, path3h


def ensure_output_dir(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()) and not overwrite:
        raise FileExistsError(f"Output directory exists and is non-empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def write_report_manifest(out_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file():
            rows.append(
                {
                    "path": str(path.relative_to(out_dir)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = pd.DataFrame(rows)
    manifest.to_csv(out_dir / "report_manifest.csv", index=False)
    return manifest


def run_discovery(
    config_path: Path,
    out_dir: Path | None = None,
    max_rows: int | None = None,
    outer_selector: str | None = None,
    models: Sequence[str] | None = None,
    search_model: str | None = None,
    beam_width: int | None = None,
    screen_top_cir: int | None = None,
    screen_top_cp: int | None = None,
    max_total_features: int | None = None,
    max_cir_features: int | None = None,
    max_cp_features: int | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    hgb_iter: int = 60,
    root: Path = ROOT,
) -> dict[str, object]:
    config_path = repo_path(config_path, root)
    config = read_yaml(config_path)
    search_cfg = dict(config.get("search", {}))
    if beam_width is not None:
        search_cfg["beam_width"] = int(beam_width)
    if screen_top_cir is not None:
        search_cfg["screen_top_cir"] = int(screen_top_cir)
    if screen_top_cp is not None:
        search_cfg["screen_top_cp"] = int(screen_top_cp)
    if max_total_features is not None:
        search_cfg["max_total_features"] = int(max_total_features)
    if max_cir_features is not None:
        search_cfg["max_cir_features"] = int(max_cir_features)
    if max_cp_features is not None:
        search_cfg["max_cp_features"] = int(max_cp_features)
    seed = int(search_cfg.get("seed", 20260610))
    search_model = search_model or str(search_cfg.get("search_model", "LogReg"))
    eval_models = list(models or search_cfg.get("evaluation_models", ["HGB", "LogReg"]))
    out = repo_path(out_dir or config.get("outputs", {}).get("default_out_dir"), root)
    ensure_output_dir(out, overwrite=overwrite or dry_run)

    df = load_merged_tables(config, root=root, max_rows=max_rows)
    specs = target_specs(config)
    split_key = config["inputs"].get("split_key", "split_fold")
    outer_splits = build_outer_splits(df, split_key=split_key, requested=outer_selector)

    input_manifest = input_file_manifest(config, root=root)
    input_manifest.to_csv(out / "input_hashes.csv", index=False)
    source_manifest = {
        "experiment_id": config.get("experiment_id"),
        "created_at_utc": now_utc(),
        "config_path": str(config_path.relative_to(root) if config_path.is_relative_to(root) else config_path),
        "config_sha256": sha256_file(config_path),
        "row_count": int(len(df)),
        "max_rows": max_rows,
        "outer_selector": outer_selector,
        "search_model": search_model,
        "evaluation_models": eval_models,
        "search_config": search_cfg,
        "dry_run": bool(dry_run),
        "claim_boundary": "Paper 1 CP feature discovery only; no direct range-error reduction claim.",
    }
    write_json(out / "source_manifest.json", source_manifest)
    split_preflight(df, config, outer_splits).to_csv(out / "split_preflight.csv", index=False)

    candidate_audit, routed = audit_candidate_pools(df, config)
    candidate_audit.to_csv(out / "candidate_pool_audit.csv", index=False)
    cir_all = routed.get("cir_main_observable", [])
    cp_all = routed.get("cp_main_observable", [])
    forbidden_feature_audit(df, config, cir_all + cp_all).to_csv(out / "forbidden_feature_audit.csv", index=False)

    if dry_run:
        write_json(
            out / "run_manifest.json",
            {
                **source_manifest,
                "status": "DRY_RUN_OK",
                "n_outer_splits": len(outer_splits),
                "n_cir_main": len(cir_all),
                "n_cp_main": len(cp_all),
            },
        )
        write_report_manifest(out)
        return {"status": "DRY_RUN_OK", "out_dir": str(out), "n_outer_splits": len(outer_splits), "n_rows": len(df)}

    all_univariate: list[pd.DataFrame] = []
    all_screen_decisions: list[pd.DataFrame] = []
    all_corr: list[pd.DataFrame] = []
    all_pair: dict[str, list[pd.DataFrame]] = {}
    all_cir_leader: list[pd.DataFrame] = []
    all_cp_leader: list[pd.DataFrame] = []
    all_joint_leader: list[pd.DataFrame] = []
    all_pareto: list[pd.DataFrame] = []
    one_se_rows: list[dict[str, object]] = []
    outer_rows: list[pd.DataFrame] = []
    outer_pred_parts: list[pd.DataFrame] = []
    baseline_rows: list[pd.DataFrame] = []
    residual_rows: list[pd.DataFrame] = []
    shuffled_rows: list[pd.DataFrame] = []
    selected_rows: list[dict[str, object]] = []
    pair_freq_rows: list[dict[str, object]] = []
    cp_gain_rows: list[dict[str, object]] = []
    cir_gain_rows: list[dict[str, object]] = []

    for split in outer_splits:
        train_df = df.iloc[split.train_idx].copy()
        inner_splits = build_inner_splits(df, split.train_idx, split_key=split_key)

        uni_cir = univariate_screening(df, cir_all, specs, inner_splits, search_model, seed, split.name, "CIR", hgb_iter=hgb_iter)
        uni_cp = univariate_screening(df, cp_all, specs, inner_splits, search_model, seed, split.name, "CP", hgb_iter=hgb_iter)
        ranking = pd.concat([uni_cir, uni_cp], ignore_index=True)
        all_univariate.append(ranking)

        screen_top_cir = int(search_cfg.get("screen_top_cir", 12))
        screen_top_cp = int(search_cfg.get("screen_top_cp", 10))
        auc_keep = float(search_cfg.get("univariate_auc_keep", 0.55))
        cir_screened = select_screened_features(ranking, "CIR", screen_top_cir, auc_keep)
        cp_screened = select_screened_features(ranking, "CP", screen_top_cp, auc_keep)
        all_screen_decisions.append(
            pd.DataFrame(
                [
                    {"outer_split": split.name, "feature": f, "group": "CIR", "decision": "screened_keep" if f in cir_screened else "screened_drop"}
                    for f in cir_all
                ]
                + [
                    {"outer_split": split.name, "feature": f, "group": "CP", "decision": "screened_keep" if f in cp_screened else "screened_drop"}
                    for f in cp_all
                ]
            )
        )
        all_corr.append(correlation_clusters(train_df, cir_screened + cp_screened, float(search_cfg.get("corr_redundancy_threshold", 0.90)), split.name))

        pair_maps = pair_synergy_map(df, cir_screened, cp_screened, specs, inner_splits, search_model, seed, split.name, search_cfg, hgb_iter=hgb_iter)
        for target, table in pair_maps.items():
            all_pair.setdefault(target, []).append(table)

        cir_leader, cir_best_preds = beam_search(
            df,
            cir_screened,
            specs,
            inner_splits,
            search_model,
            seed,
            split.name,
            cir_screened,
            cp_screened,
            search_cfg,
            hgb_iter=hgb_iter,
        )
        cp_leader, cp_best_preds = beam_search(
            df,
            cp_screened,
            specs,
            inner_splits,
            search_model,
            seed,
            split.name,
            cir_screened,
            cp_screened,
            search_cfg,
            hgb_iter=hgb_iter,
        )
        all_cir_leader.append(cir_leader.assign(search_scope="CIR_only"))
        all_cp_leader.append(cp_leader.assign(search_scope="CP_only"))

        if not cir_leader.empty:
            cir_best = [x for x in str(cir_leader.iloc[0]["features"]).split(";") if x]
        else:
            cir_best = cir_screened[: min(3, len(cir_screened))]
        if not cp_leader.empty:
            cp_best = [x for x in str(cp_leader.iloc[0]["features"]).split(";") if x]
        else:
            cp_best = cp_screened[: min(3, len(cp_screened))]

        for cp in cp_screened:
            features = unique(cir_best + [cp])
            row, preds = evaluate_subset_row(df, features, specs, inner_splits, search_model, seed, split.name, cir_screened, cp_screened, search_cfg, base_preds=cir_best_preds, hgb_iter=hgb_iter)
            for spec in specs:
                cp_gain_rows.append(
                    {
                        "outer_split": split.name,
                        "CP_feature": cp,
                        "target": spec.name,
                        "delta_vs_best_cir_AUC": row.get(f"AUC_{spec.name}", np.nan)
                        - (cir_leader.iloc[0].get(f"AUC_{spec.name}", np.nan) if not cir_leader.empty else np.nan),
                        "rescue": row.get(f"rescue_{spec.name}", np.nan),
                        "clean_false_alarm": row.get(f"clean_false_alarm_{spec.name}", np.nan),
                    }
                )
        for cir in cir_screened:
            features = unique(cp_best + [cir])
            row, _ = evaluate_subset_row(df, features, specs, inner_splits, search_model, seed, split.name, cir_screened, cp_screened, search_cfg, base_preds=cp_best_preds, hgb_iter=hgb_iter)
            for spec in specs:
                cir_gain_rows.append(
                    {
                        "outer_split": split.name,
                        "CIR_feature": cir,
                        "target": spec.name,
                        "delta_vs_best_cp_AUC": row.get(f"AUC_{spec.name}", np.nan)
                        - (cp_leader.iloc[0].get(f"AUC_{spec.name}", np.nan) if not cp_leader.empty else np.nan),
                    }
                )

        joint_features = unique(cir_screened + cp_screened)
        joint_leader, _ = beam_search(
            df,
            joint_features,
            specs,
            inner_splits,
            search_model,
            seed,
            split.name,
            cir_screened,
            cp_screened,
            search_cfg,
            require_cp=True,
            require_cir=True,
            base_preds=cir_best_preds,
            hgb_iter=hgb_iter,
        )
        all_joint_leader.append(joint_leader.assign(search_scope="joint"))
        pf = pareto_front(joint_leader)
        all_pareto.append(pf)
        selected = choose_one_se(pf if not pf.empty else joint_leader, float(search_cfg.get("one_se_tolerance", 0.005)))
        selected_features = [x for x in str(selected["features"]).split(";") if x]
        selected_cir = [f for f in selected_features if f in set(cir_screened)]
        selected_cp = [f for f in selected_features if f in set(cp_screened)]
        one_se_rows.append({"outer_split": split.name, **selected.to_dict(), "selection_rule": "one_se_smallest_stable"})
        for f in selected_features:
            selected_rows.append(
                {
                    "outer_split": split.name,
                    "feature": f,
                    "group": "CP" if f in set(cp_screened) else "CIR",
                    "subset_id": selected["subset_id"],
                    "rank": 1,
                }
            )
        for cir in selected_cir:
            for cp in selected_cp:
                pair_freq_rows.append({"outer_split": split.name, "CIR_feature": cir, "CP_feature": cp})

        model_metric_parts = []
        primary_pred = None
        for model_name in eval_models:
            metrics, preds = fit_predict_outer(df, split.train_idx, split.test_idx, selected_features, specs, model_name, seed, hgb_iter=hgb_iter)
            metrics["outer_split"] = split.name
            metrics["feature_set"] = "discovered_subset"
            metrics["features"] = ";".join(selected_features)
            model_metric_parts.append(metrics)
            if primary_pred is None:
                primary_pred = preds
        outer_rows.append(pd.concat(model_metric_parts, ignore_index=True))
        if primary_pred is not None:
            primary_pred["outer_split"] = split.name
            primary_pred["feature_set"] = "discovered_subset"
            primary_pred["features"] = ";".join(selected_features)
            outer_pred_parts.append(primary_pred)

        for name, features in config.get("named_baselines", {}).items():
            present = [f for f in features if f in df.columns]
            status = "PRESENT" if len(present) == len(features) else "MISSING_FEATURES"
            if status == "PRESENT":
                metrics, _preds = fit_predict_outer(df, split.train_idx, split.test_idx, present, specs, eval_models[0], seed, hgb_iter=hgb_iter)
            else:
                metrics = pd.DataFrame([{"target": spec.name, "model": eval_models[0], "AUC": np.nan, "PR_AUC": np.nan, "balanced_accuracy": np.nan, "n": 0, "n_pos": 0} for spec in specs])
            metrics["outer_split"] = split.name
            metrics["feature_set"] = name
            metrics["features"] = ";".join(present)
            metrics["feature_status"] = status
            baseline_rows.append(metrics)

        if selected_cp and selected_cir:
            residual_rows.append(outer_residual_control(df, split, selected_cir, selected_cp, specs, eval_models[0], seed, shuffled=False, hgb_iter=hgb_iter))
            residual_rows.append(outer_residual_control(df, split, selected_cir, selected_cp, specs, eval_models[0], seed, shuffled=True, hgb_iter=hgb_iter))

            shuffled_df = df.copy()
            rng = np.random.default_rng(stable_seed(seed, "shuffle", split.name))
            for cp in selected_cp:
                train_values = shuffled_df.iloc[split.train_idx][cp].to_numpy()
                shuffled_values = rng.permutation(train_values)
                shuffled_df.iloc[split.train_idx, shuffled_df.columns.get_loc(cp)] = shuffled_values
                # Test CP is permuted independently so no test label information enters selection.
                test_values = shuffled_df.iloc[split.test_idx][cp].to_numpy()
                shuffled_df.iloc[split.test_idx, shuffled_df.columns.get_loc(cp)] = rng.permutation(test_values)
            metrics, _ = fit_predict_outer(shuffled_df, split.train_idx, split.test_idx, selected_features, specs, eval_models[0], seed, hgb_iter=hgb_iter)
            metrics["outer_split"] = split.name
            metrics["control"] = "shuffled_selected_cp"
            metrics["feature_set"] = "discovered_subset_shuffled_cp"
            shuffled_rows.append(metrics)

    pd.concat(all_univariate, ignore_index=True).to_csv(out / "feature_univariate_ranking.csv", index=False)
    pd.concat(all_screen_decisions, ignore_index=True).to_csv(out / "feature_screening_decisions.csv", index=False)
    pd.concat(all_corr, ignore_index=True).to_csv(out / "feature_correlation_clusters.csv", index=False)
    for target, tables in all_pair.items():
        name = "notclean" if target == "notclean3H" else target
        pd.concat(tables, ignore_index=True).to_csv(out / f"pair_synergy_{name}.csv", index=False)
    pd.concat(all_cir_leader, ignore_index=True).to_csv(out / "cir_only_leaderboard_innercv.csv", index=False)
    pd.concat(all_cp_leader, ignore_index=True).to_csv(out / "cp_only_leaderboard_innercv.csv", index=False)
    joint = pd.concat(all_joint_leader, ignore_index=True)
    joint.to_csv(out / "subset_leaderboard_innercv.csv", index=False)
    pd.concat(all_pareto, ignore_index=True).to_csv(out / "pareto_front_innercv.csv", index=False)
    pd.DataFrame(one_se_rows).to_csv(out / "one_se_selection_trace.csv", index=False)
    pd.DataFrame(cp_gain_rows).to_csv(out / "conditional_cp_gain_over_best_cir.csv", index=False)
    pd.DataFrame(cir_gain_rows).to_csv(out / "conditional_cir_gain_over_best_cp.csv", index=False)

    outer_results = pd.concat(outer_rows, ignore_index=True)
    outer_results.to_csv(out / "outer_test_results.csv", index=False)
    predictions = pd.concat(outer_pred_parts, ignore_index=True) if outer_pred_parts else pd.DataFrame()
    predictions.to_csv(out / "outer_test_predictions.csv", index=False)
    pd.concat(baseline_rows, ignore_index=True).to_csv(out / "baseline_comparison_outer.csv", index=False)
    if residual_rows:
        pd.concat(residual_rows, ignore_index=True).to_csv(out / "control_residualized_cp_results.csv", index=False)
    else:
        pd.DataFrame().to_csv(out / "control_residualized_cp_results.csv", index=False)
    if shuffled_rows:
        pd.concat(shuffled_rows, ignore_index=True).to_csv(out / "control_shuffled_cp_results.csv", index=False)
    else:
        pd.DataFrame().to_csv(out / "control_shuffled_cp_results.csv", index=False)

    model_robustness = outer_results.groupby(["feature_set", "model", "target"], as_index=False).agg(
        mean_AUC=("AUC", "mean"),
        mean_PR_AUC=("PR_AUC", "mean"),
        n_outer=("outer_split", "nunique"),
    )
    model_robustness.to_csv(out / "model_family_robustness.csv", index=False)

    selected_df = pd.DataFrame(selected_rows)
    if not selected_df.empty:
        n_splits = len(outer_splits)
        stability = selected_df.groupby(["feature", "group"], as_index=False).agg(selected_in_folds=("outer_split", "nunique"))
        stability["selection_frequency"] = stability["selected_in_folds"] / n_splits
        cp_gain = pd.DataFrame(cp_gain_rows)
        if not cp_gain.empty:
            gain_agg = cp_gain[cp_gain["target"].isin(["RDLoS", "HBprior"])].pivot_table(
                index="CP_feature", columns="target", values="delta_vs_best_cir_AUC", aggfunc="mean"
            )
            gain_agg = gain_agg.rename(columns={"RDLoS": "mean_delta_RDLoS", "HBprior": "mean_delta_HBprior"}).reset_index()
            stability = stability.merge(gain_agg, left_on="feature", right_on="CP_feature", how="left").drop(columns=["CP_feature"], errors="ignore")
        stability["final_decision"] = np.where(stability["selection_frequency"] >= 0.60, "paper_main_candidate", "unstable_or_supporting")
    else:
        stability = pd.DataFrame(columns=["feature", "group", "selected_in_folds", "selection_frequency", "final_decision"])
    stability.to_csv(out / "final_feature_stability.csv", index=False)

    pair_freq = pd.DataFrame(pair_freq_rows)
    if not pair_freq.empty:
        pair_frequency = pair_freq.groupby(["CIR_feature", "CP_feature"], as_index=False).agg(selected_in_folds=("outer_split", "nunique"))
        pair_frequency["pair_frequency"] = pair_frequency["selected_in_folds"] / len(outer_splits)
    else:
        pair_frequency = pd.DataFrame(columns=["CIR_feature", "CP_feature", "selected_in_folds", "pair_frequency"])
    pair_frequency.to_csv(out / "selection_frequency_by_pair.csv", index=False)
    stability.to_csv(out / "selection_frequency_by_feature.csv", index=False)

    final_decision = stability.copy()
    if not final_decision.empty:
        final_decision["decision_class"] = np.where(
            (final_decision["group"].eq("CP")) & (final_decision["selection_frequency"] >= 0.60),
            "paper_main_selected",
            np.where(final_decision["selection_frequency"] >= 0.60, "paper_main_selected", "supporting_or_unstable"),
        )
    final_decision.to_csv(out / "final_decision_table.csv", index=False)

    if not predictions.empty:
        primary_model = eval_models[0]
        q2h, q3h = qclean_tables(predictions, primary_model)
        q2h.to_csv(out / "outer_qclean_scores_path2h.csv", index=False)
        q3h.to_csv(out / "outer_qclean_scores_path3h.csv", index=False)

    run_manifest = {
        **source_manifest,
        "status": "COMPLETE",
        "completed_at_utc": now_utc(),
        "n_outer_splits": len(outer_splits),
        "n_cir_main": len(cir_all),
        "n_cp_main": len(cp_all),
        "outputs": sorted([str(p.relative_to(out)) for p in out.glob("*") if p.is_file()]),
        "command_line": " ".join([Path(sys.argv[0]).name] + sys.argv[1:]),
    }
    write_json(out / "run_manifest.json", run_manifest)
    write_report_manifest(out)
    return {"status": "COMPLETE", "out_dir": str(out), "n_outer_splits": len(outer_splits), "n_rows": len(df)}


def markdown_table(df: pd.DataFrame, columns: Sequence[str], max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._\n"
    sub = df.loc[:, [c for c in columns if c in df.columns]].head(max_rows).copy()
    headers = list(sub.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in sub.iterrows():
        vals = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                vals.append("" if not math.isfinite(value) else f"{value:.4f}")
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"
