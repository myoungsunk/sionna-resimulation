"""OOF and paired-gain helpers for CP-PH4 replacement experiments."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd


def oof_ridge_predictions(features: Any, targets: Any, folds: Any, *, ridge: float = 1.0e-8) -> np.ndarray:
    """Return fold-held-out ridge predictions without using a validation target."""

    x = np.asarray(features, dtype=float)
    y = np.asarray(targets, dtype=float).reshape(-1)
    fold = np.asarray(folds, dtype=int).reshape(-1)
    if x.ndim != 2 or len(x) != len(y) or len(y) != len(fold):
        raise ValueError(f"OOF shape mismatch: x={x.shape}, y={y.shape}, folds={fold.shape}")
    if len(np.unique(fold)) < 2:
        raise ValueError("at least two OOF folds are required")
    if not np.all(np.isfinite(y)):
        raise ValueError("OOF targets must be finite")
    predictions = np.full(len(y), np.nan, dtype=float)
    for held_out in sorted(np.unique(fold)):
        train = fold != held_out
        test = ~train
        if not train.any() or not test.any():
            raise ValueError(f"invalid fold {held_out}")
        train_x = x[train].copy()
        test_x = x[test].copy()
        median = np.nanmedian(train_x, axis=0)
        median[~np.isfinite(median)] = 0.0
        train_x = np.where(np.isfinite(train_x), train_x, median)
        test_x = np.where(np.isfinite(test_x), test_x, median)
        scale = np.nanstd(train_x, axis=0)
        scale[~np.isfinite(scale) | (scale < 1.0e-12)] = 1.0
        mean = np.mean(train_x, axis=0)
        train_z = (train_x - mean) / scale
        test_z = (test_x - mean) / scale
        design = np.column_stack([np.ones(train_z.shape[0]), train_z])
        penalty = np.eye(design.shape[1]) * ridge
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ y[train])
        predictions[test] = np.column_stack([np.ones(test_z.shape[0]), test_z]) @ beta
    return predictions


def spearman_rank_correlation(values: Any, targets: Any) -> float:
    x = pd.Series(np.asarray(values, dtype=float))
    y = pd.Series(np.asarray(targets, dtype=float))
    valid = x.notna() & y.notna()
    if int(valid.sum()) < 3:
        return float("nan")
    return float(x.loc[valid].corr(y.loc[valid], method="spearman"))


def paired_cluster_bootstrap_mean_ci(
    deltas: Any,
    clusters: Iterable[Any],
    *,
    reps: int,
    seed: int,
    alpha: float = 0.05,
) -> dict[str, float | int]:
    """Cluster-bootstrap a paired mean delta and return a two-sided CI."""

    data = pd.DataFrame({"delta": np.asarray(deltas, dtype=float), "cluster": list(clusters)}).dropna(subset=["delta", "cluster"])
    if data.empty:
        return {"n_cases": 0, "n_clusters": 0, "mean_delta": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    by_cluster = data.groupby("cluster", sort=True)["delta"].mean().to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(by_cluster), size=(reps, len(by_cluster)))
    boot = by_cluster[draws].mean(axis=1)
    return {
        "n_cases": int(len(data)),
        "n_clusters": int(len(by_cluster)),
        "mean_delta": float(data["delta"].mean()),
        "ci_low": float(np.quantile(boot, alpha / 2.0)),
        "ci_high": float(np.quantile(boot, 1.0 - alpha / 2.0)),
    }
