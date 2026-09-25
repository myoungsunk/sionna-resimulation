from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from .ds1v5_bridge_schema import SplitLeakageAuditRow


REQUIRED_GROUP_KEYS = ["case_id", "pose_group_id", "cad_variant_family", "source_geometry_family"]

CIR_FEATURE_NAMES = {
    "idx_fp",
    "t_fp_s",
    "fp_peak_val",
    "a_fp_2_peak_to_total",
    "a_fp_6_fp_to_2nd_peak",
    "rms_delay_spread",
    "mean_excess_delay",
    "max_excess_delay",
    "fp_to_total_ratio",
    "rise_time_fp",
    "fp_kurtosis",
    "kurtosis_total",
    "skewness_total",
    "energy_concentration_50ns",
    "num_significant_peaks",
    "peak_to_avg_ratio",
    "k_factor_estimate",
    "snr_db",
}

CP_FEATURE_NAMES = {
    "xpr_fp_db",
    "xpr_late_db",
    "xpr_all_db",
    "s3_fp",
    "s3_late",
    "s3_all",
    "delta_tau_l_given_r_s",
    "delta_p_l_given_r_db",
    "f_r_fp",
    "f_l_fp",
    "delta_f_l_minus_r_fp",
    "lambda_l_late_fraction",
    "gamma_anchor_linear",
    "gamma_delay_linear",
    "cp_phase_slope_delay_s",
    "cp_phase_residual_circvar",
}


@dataclass(frozen=True)
class ClassificationArm:
    name: str
    feature_mode: str
    source_kind: str


def stable_seed(seed: int, *parts: object) -> int:
    payload = "|".join(map(str, parts)).encode("utf-8")
    return int(seed + zlib.crc32(payload) % 1_000_000)


def feature_columns(df: pd.DataFrame, mode: str) -> list[str]:
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    cir = [c for c in numeric if c.startswith("cir_") or c in CIR_FEATURE_NAMES]
    cp = [c for c in numeric if c.startswith("cp_") or c in CP_FEATURE_NAMES]
    if mode == "CIR":
        return cir
    if mode == "CP-only":
        return cp
    if mode in {"CIR+CP", "shuffled-CP", "residualized-CP"}:
        return cir + cp
    raise ValueError(f"Unknown feature mode: {mode}")


def default_arms() -> list[ClassificationArm]:
    return [
        ClassificationArm("PY-CIR", "CIR", "SOMI_PY_RT"),
        ClassificationArm("PY-CIR+CP", "CIR+CP", "SOMI_PY_RT"),
        ClassificationArm("PY-CP-only", "CP-only", "SOMI_PY_RT"),
        ClassificationArm("PY-shuffled-CP", "shuffled-CP", "SOMI_PY_RT"),
        ClassificationArm("PY-residualized-CP", "residualized-CP", "SOMI_PY_RT"),
        ClassificationArm("ANSYS-CIR", "CIR", "SOMI_ANSYS"),
        ClassificationArm("ANSYS-CIR+CP", "CIR+CP", "SOMI_ANSYS"),
        ClassificationArm("ANSYS-CP-only", "CP-only", "SOMI_ANSYS"),
        ClassificationArm("ANSYS-shuffled-CP", "shuffled-CP", "SOMI_ANSYS"),
        ClassificationArm("ANSYS-residualized-CP", "residualized-CP", "SOMI_ANSYS"),
    ]


def make_model(name: str, seed: int):
    name_u = name.upper()
    if name_u in {"LOGREG", "LOGISTIC", "LR"}:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=3000, class_weight="balanced", random_state=seed),
        )
    if name_u in {"LINEARSVM", "SVM"}:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LinearSVC(class_weight="balanced", dual=False, max_iter=5000, random_state=seed),
        )
    if name_u in {"GB", "GRADIENTBOOSTING"}:
        return make_pipeline(SimpleImputer(strategy="median"), GradientBoostingClassifier(random_state=seed))
    if name_u in {"RF", "RANDOMFOREST"}:
        return make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=80,
                max_depth=6,
                min_samples_leaf=3,
                class_weight="balanced_subsample",
                random_state=seed,
                n_jobs=1,
            ),
        )
    raise ValueError(f"Unknown model={name}")


def model_score(model, X: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(X)[:, 1], dtype=float)
    if hasattr(model, "decision_function"):
        raw = np.asarray(model.decision_function(X), dtype=float)
        return 1.0 / (1.0 + np.exp(-np.clip(raw, -35.0, 35.0)))
    return np.asarray(model.predict(X), dtype=float)


def safe_auc(y: np.ndarray, score: np.ndarray) -> float:
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, score))


def safe_pr_auc(y: np.ndarray, score: np.ndarray) -> float:
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(average_precision_score(y, score))


def audit_split_leakage(
    df: pd.DataFrame,
    train_idx: Sequence[int],
    test_idx: Sequence[int],
    *,
    eval_arm: str,
    fold_id: str,
    split_kind: str = "within_domain_primary",
    group_keys: Sequence[str] = REQUIRED_GROUP_KEYS,
) -> pd.DataFrame:
    rows = []
    train = df.iloc[list(train_idx)]
    test = df.iloc[list(test_idx)]
    diagnostic = split_kind == "same_cad_cross_domain_diagnostic"
    for key in group_keys:
        if key not in df.columns:
            rows.append(
                SplitLeakageAuditRow(
                    eval_arm=eval_arm,
                    fold_id=str(fold_id),
                    split_kind=split_kind,
                    group_key=key,
                    n_train_unique=0,
                    n_test_unique=0,
                    n_overlap=0,
                    overlap_examples="",
                    status="BLOCKED_FOR_PRIMARY",
                ).to_dict()
            )
            continue
        train_values = set(train[key].astype(str))
        test_values = set(test[key].astype(str))
        overlap = sorted(train_values & test_values)
        status = "DIAGNOSTIC_NOT_PRIMARY" if diagnostic and overlap else ("PASS" if not overlap else "BLOCKED_FOR_PRIMARY")
        rows.append(
            SplitLeakageAuditRow(
                eval_arm=eval_arm,
                fold_id=str(fold_id),
                split_kind=split_kind,
                group_key=key,
                n_train_unique=len(train_values),
                n_test_unique=len(test_values),
                n_overlap=len(overlap),
                overlap_examples=";".join(overlap[:5]),
                status=status,
            ).to_dict()
        )
    return pd.DataFrame(rows)


def deterministic_group_split(df: pd.DataFrame, *, group_col: str = "case_id", fold_mod: int = 5, test_fold: int = 0) -> tuple[np.ndarray, np.ndarray]:
    keys = df[group_col].astype(str).to_numpy()
    folds = np.array([zlib.crc32(k.encode("utf-8")) % fold_mod for k in keys])
    test_mask = folds == test_fold
    if test_mask.sum() == 0 or (~test_mask).sum() == 0:
        order = np.arange(len(df))
        test_mask = order % fold_mod == test_fold
    return np.flatnonzero(~test_mask), np.flatnonzero(test_mask)


def bridge_train_test_split(df: pd.DataFrame, *, test_fold: int = 0, group_col: str = "pose_group_id") -> tuple[np.ndarray, np.ndarray]:
    if "split_fold" in df.columns:
        folds = pd.to_numeric(df["split_fold"], errors="coerce")
        test_mask = folds.eq(test_fold).to_numpy()
        if test_mask.sum() > 0 and (~test_mask).sum() > 0:
            return np.flatnonzero(~test_mask), np.flatnonzero(test_mask)
    if "calibration_split" in df.columns:
        values = df["calibration_split"].astype(str).str.lower()
        test_mask = values.eq("test").to_numpy()
        if test_mask.sum() > 0 and (~test_mask).sum() > 0:
            return np.flatnonzero(~test_mask), np.flatnonzero(test_mask)
    if group_col in df.columns:
        return deterministic_group_split(df, group_col=group_col, test_fold=test_fold)
    return deterministic_group_split(df, test_fold=test_fold)


def bridge_split_plan(
    df: pd.DataFrame,
    *,
    evaluation_fold_mode: str = "single_fold0",
    group_col: str = "pose_group_id",
) -> list[tuple[str, np.ndarray, np.ndarray]]:
    if evaluation_fold_mode == "single_fold0":
        train_idx, test_idx = bridge_train_test_split(df, test_fold=0, group_col=group_col)
        return [("fold0", train_idx, test_idx)]
    if evaluation_fold_mode != "all_folds":
        raise ValueError(f"Unknown evaluation_fold_mode={evaluation_fold_mode!r}")
    splits: list[tuple[str, np.ndarray, np.ndarray]] = []
    if "split_fold" in df.columns:
        folds = pd.to_numeric(df["split_fold"], errors="coerce")
        for fold in sorted(int(value) for value in folds.dropna().unique()):
            test_mask = folds.eq(fold).to_numpy()
            if test_mask.sum() > 0 and (~test_mask).sum() > 0:
                splits.append((f"fold{fold}", np.flatnonzero(~test_mask), np.flatnonzero(test_mask)))
    if splits:
        return splits
    for fold in range(5):
        train_idx, test_idx = bridge_train_test_split(df, test_fold=fold, group_col=group_col)
        if len(test_idx) and len(train_idx):
            splits.append((f"fold{fold}", train_idx, test_idx))
    return splits or [("fold0", *bridge_train_test_split(df, test_fold=0, group_col=group_col))]


def _shuffle_cp_columns(X: pd.DataFrame, seed: int) -> pd.DataFrame:
    out = X.copy()
    rng = np.random.default_rng(seed)
    for col in [c for c in out.columns if c.startswith("cp_")]:
        out[col] = rng.permutation(out[col].to_numpy())
    return out


def _residualize_cp_against_cir(X_train: pd.DataFrame, X_test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cir_cols = [c for c in X_train.columns if c.startswith("cir_")]
    cp_cols = [c for c in X_train.columns if c.startswith("cp_")]
    if not cir_cols or not cp_cols:
        return X_train, X_test
    train = X_train.copy()
    test = X_test.copy()
    cir_train = train[cir_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    cir_test = test[cir_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    for col in cp_cols:
        y = pd.to_numeric(train[col], errors="coerce").fillna(0.0).to_numpy()
        model = Ridge(alpha=1.0).fit(cir_train, y)
        train[col] = y - model.predict(cir_train)
        test[col] = pd.to_numeric(test[col], errors="coerce").fillna(0.0).to_numpy() - model.predict(cir_test)
    return train, test


def evaluate_classification(
    feature_df: pd.DataFrame,
    *,
    target_cols: Sequence[str] = ("label_rd_los", "label_hb_prior"),
    models: Sequence[str] = ("LOGREG",),
    seed: int = 20260628,
    evaluation_fold_mode: str = "single_fold0",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metrics_rows: list[dict[str, object]] = []
    pred_rows: list[dict[str, object]] = []
    audit_parts: list[pd.DataFrame] = []

    source_kind = feature_df["source_kind"].astype(str) if "source_kind" in feature_df.columns else pd.Series([""] * len(feature_df))
    source_id = feature_df["source_id"].astype(str) if "source_id" in feature_df.columns else pd.Series([""] * len(feature_df))
    selectors = {
        "PY": source_kind.eq("SOMI_PY_RT") | source_id.str.startswith("PY"),
        "ANSYS": source_kind.eq("SOMI_ANSYS") | source_id.str.startswith("ANSYS"),
    }
    modes = ["CIR", "CIR+CP", "CP-only", "shuffled-CP", "residualized-CP"]

    for source_label, source_selector in selectors.items():
        source_df = feature_df.loc[source_selector].reset_index(drop=True)
        if source_df.empty:
            continue
        split_plan = bridge_split_plan(source_df, evaluation_fold_mode=evaluation_fold_mode)
        for target_col in target_cols:
            if target_col not in source_df.columns:
                for mode in modes:
                    metrics_rows.append(
                        {
                            "source": source_label,
                            "target": target_col,
                            "arm": f"{source_label}-{mode}",
                            "model": "BLOCKED",
                            "roc_auc": np.nan,
                            "pr_auc": np.nan,
                            "balanced_accuracy": np.nan,
                            "delta_auc_vs_cir": np.nan,
                            "status": "BLOCKED_MISSING_TARGET",
                        }
                    )
                continue
            if source_df[target_col].nunique() < 2:
                for mode in modes:
                    metrics_rows.append(
                        {
                            "source": source_label,
                            "target": target_col,
                            "arm": f"{source_label}-{mode}",
                            "model": "BLOCKED",
                            "roc_auc": np.nan,
                            "pr_auc": np.nan,
                            "balanced_accuracy": np.nan,
                            "delta_auc_vs_cir": np.nan,
                            "status": "BLOCKED_LABEL_DEGENERATE",
                        }
                    )
                continue
            y = source_df[target_col].astype(int).to_numpy()
            for mode in modes:
                arm_name = f"{source_label}-{mode}"
                cols = feature_columns(source_df, mode)
                if not cols:
                    continue
                X = source_df[cols].apply(pd.to_numeric, errors="coerce")
                if mode == "shuffled-CP":
                    X = _shuffle_cp_columns(X, stable_seed(seed, arm_name, target_col))
                for model_name in models:
                    score_all = np.full(len(source_df), np.nan, dtype=float)
                    fold_ids_used: list[str] = []
                    blocked_status = ""
                    for fold_id, train_idx, test_idx in split_plan:
                        audit = audit_split_leakage(source_df, train_idx, test_idx, eval_arm=arm_name, fold_id=fold_id)
                        audit_parts.append(audit)
                        if not audit["status"].eq("PASS").all():
                            blocked_status = "BLOCKED_SPLIT_LEAKAGE"
                            break
                        X_train = X.iloc[train_idx].reset_index(drop=True)
                        X_test = X.iloc[test_idx].reset_index(drop=True)
                        if mode == "residualized-CP":
                            X_train, X_test = _residualize_cp_against_cir(X_train, X_test)
                        y_train = y[train_idx]
                        y_test = y[test_idx]
                        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
                            blocked_status = "BLOCKED_SPLIT_LABEL_DEGENERATE"
                            break
                        model = make_model(model_name, stable_seed(seed, arm_name, target_col, model_name, fold_id))
                        model.fit(X_train, y_train)
                        score = model_score(model, X_test)
                        score_all[test_idx] = score
                        fold_ids_used.append(str(fold_id))
                        for local_i, case_i in enumerate(test_idx):
                            pred_rows.append(
                                {
                                    "source": source_label,
                                    "target": target_col,
                                    "arm": arm_name,
                                    "model": model_name,
                                    "case_id": source_df.loc[case_i, "case_id"],
                                    "source_id": source_df.loc[case_i, "source_id"],
                                    "fold_id": str(fold_id),
                                    "y_true": int(y_test[local_i]),
                                    "score": float(score[local_i]),
                                }
                            )
                    if blocked_status:
                        metrics_rows.append(
                            {
                                "source": source_label,
                                "target": target_col,
                                "arm": arm_name,
                                "model": model_name,
                                "roc_auc": np.nan,
                                "pr_auc": np.nan,
                                "balanced_accuracy": np.nan,
                                "delta_auc_vs_cir": np.nan,
                                "status": blocked_status,
                                "evaluation_fold_mode": evaluation_fold_mode,
                                "fold_ids": ";".join(fold_ids_used),
                                "n_test": int(np.isfinite(score_all).sum()),
                            }
                        )
                        continue
                    eval_mask = np.isfinite(score_all)
                    y_eval = y[eval_mask]
                    score_eval = score_all[eval_mask]
                    if len(score_eval) == 0 or len(np.unique(y_eval)) < 2:
                        metrics_rows.append(
                            {
                                "source": source_label,
                                "target": target_col,
                                "arm": arm_name,
                                "model": model_name,
                                "roc_auc": np.nan,
                                "pr_auc": np.nan,
                                "balanced_accuracy": np.nan,
                                "delta_auc_vs_cir": np.nan,
                                "status": "BLOCKED_EVAL_LABEL_DEGENERATE",
                                "evaluation_fold_mode": evaluation_fold_mode,
                                "fold_ids": ";".join(fold_ids_used),
                                "n_test": int(len(score_eval)),
                            }
                        )
                        continue
                    roc = safe_auc(y_eval, score_eval)
                    pr = safe_pr_auc(y_eval, score_eval)
                    bal = float(balanced_accuracy_score(y_eval, (score_eval >= 0.5).astype(int)))
                    metrics_rows.append(
                        {
                            "source": source_label,
                            "target": target_col,
                            "arm": arm_name,
                            "model": model_name,
                            "roc_auc": roc,
                            "pr_auc": pr,
                            "balanced_accuracy": bal,
                            "delta_auc_vs_cir": np.nan,
                            "status": "PASS",
                            "evaluation_fold_mode": evaluation_fold_mode,
                            "fold_ids": ";".join(fold_ids_used),
                            "n_test": int(len(score_eval)),
                        }
                    )

    metrics = pd.DataFrame(metrics_rows)
    if not metrics.empty:
        cir = metrics[metrics["arm"].str.endswith("-CIR")][["source", "target", "model", "roc_auc"]].rename(columns={"roc_auc": "cir_auc"})
        metrics = metrics.merge(cir, on=["source", "target", "model"], how="left")
        metrics["delta_auc_vs_cir"] = metrics["roc_auc"] - metrics["cir_auc"]
        metrics = metrics.drop(columns=["cir_auc"])
    predictions = pd.DataFrame(pred_rows)
    audit_df = pd.concat(audit_parts, ignore_index=True) if audit_parts else pd.DataFrame()
    return metrics, predictions, audit_df
