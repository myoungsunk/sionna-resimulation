from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class AucResult:
    feature_set: str
    auc_mean: float
    auc_std: float
    n_rows: int
    n_features: int


def _as_numeric_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col in columns:
        out[col] = pd.to_numeric(df[col], errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def cv_logistic_auc(df: pd.DataFrame, feature_cols: list[str], label_col: str = "is_nlos", folds: int = 5, random_state: int = 0) -> AucResult:
    if label_col not in df.columns:
        raise KeyError(f"missing label column: {label_col}")
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise KeyError(f"missing feature columns: {missing}")
    y = pd.to_numeric(df[label_col], errors="coerce").fillna(0).astype(int).to_numpy()
    X = _as_numeric_frame(df, feature_cols).to_numpy()
    if len(np.unique(y)) < 2:
        return AucResult("custom", float("nan"), float("nan"), len(df), len(feature_cols))
    n_splits = max(2, min(int(folds), int(np.bincount(y).min())))
    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    aucs = []
    for train_idx, test_idx in splitter.split(X, y):
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, solver="liblinear"))
        model.fit(X[train_idx], y[train_idx])
        score = model.predict_proba(X[test_idx])[:, 1]
        aucs.append(float(roc_auc_score(y[test_idx], score)))
    return AucResult("custom", float(np.mean(aucs)), float(np.std(aucs, ddof=0)), len(df), len(feature_cols))


def compute_conditional_auc(df: pd.DataFrame, feature_cols: list[str], label_col: str = "is_nlos", group_col: str | None = None, folds: int = 5) -> pd.DataFrame:
    groups = [("all", df)] if not group_col or group_col not in df.columns else list(df.groupby(group_col, dropna=False))
    rows = []
    for group_value, group_df in groups:
        result = cv_logistic_auc(group_df.reset_index(drop=True), feature_cols, label_col=label_col, folds=folds)
        rows.append({
            "group": group_value,
            "label_col": label_col,
            "n_rows": result.n_rows,
            "n_features": result.n_features,
            "auc_mean": result.auc_mean,
            "auc_std": result.auc_std,
        })
    return pd.DataFrame(rows)


def compute_disagreement_analysis(df: pd.DataFrame, score_a: str, score_b: str, label_col: str = "is_nlos", threshold: float = 0.5) -> pd.DataFrame:
    for col in [score_a, score_b, label_col]:
        if col not in df.columns:
            raise KeyError(f"missing column: {col}")
    a = pd.to_numeric(df[score_a], errors="coerce").fillna(0.0) >= threshold
    b = pd.to_numeric(df[score_b], errors="coerce").fillna(0.0) >= threshold
    y = pd.to_numeric(df[label_col], errors="coerce").fillna(0).astype(bool)
    return pd.DataFrame([
        {"bucket": "agree_correct", "count": int(((a == b) & (a == y)).sum())},
        {"bucket": "agree_wrong", "count": int(((a == b) & (a != y)).sum())},
        {"bucket": "a_only_correct", "count": int(((a != b) & (a == y)).sum())},
        {"bucket": "b_only_correct", "count": int(((a != b) & (b == y)).sum())},
    ])
