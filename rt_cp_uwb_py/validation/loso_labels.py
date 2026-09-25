"""Leakage-safe residual labels for leave-one-group-out validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

import numpy as np
from sklearn.mixture import GaussianMixture


@dataclass(frozen=True)
class TrainOnlyGmmFold:
    """Binary labels produced by a GMM fitted on the training rows only."""

    train_labels: np.ndarray
    test_labels: np.ndarray
    component_means: tuple[float, float]
    high_component: int


@dataclass(frozen=True)
class LosoGmmLabels:
    """OOF labels plus the matching training labels for every held-out group."""

    oof_labels: np.ndarray
    folds: dict[Hashable, TrainOnlyGmmFold]


def fit_binary_gmm_train_only(
    residual_train: np.ndarray,
    residual_test: np.ndarray,
    *,
    random_state: int,
) -> TrainOnlyGmmFold:
    """Fit a two-mode residual GMM without exposing held-out residuals to it."""
    train = np.asarray(residual_train, dtype=float).reshape(-1)
    test = np.asarray(residual_test, dtype=float).reshape(-1)
    if train.size < 2 or np.unique(train).size < 2:
        raise ValueError("training residuals need at least two distinct finite values")
    if not np.isfinite(train).all() or not np.isfinite(test).all():
        raise ValueError("training and test residuals must be finite")

    model = GaussianMixture(2, random_state=random_state).fit(train.reshape(-1, 1))
    means = model.means_.ravel()
    high = int(np.argmax(means))

    def label(values: np.ndarray) -> np.ndarray:
        prob = model.predict_proba(values.reshape(-1, 1))[:, high]
        return (prob > 0.5).astype(int)

    return TrainOnlyGmmFold(
        train_labels=label(train),
        test_labels=label(test),
        component_means=tuple(float(x) for x in sorted(means)),
        high_component=high,
    )


def build_loso_gmm_labels(
    residuals: np.ndarray,
    groups: np.ndarray,
    *,
    random_state: int,
) -> LosoGmmLabels:
    """Build group-held-out residual labels and retain fold-specific train labels."""
    residual = np.asarray(residuals, dtype=float).reshape(-1)
    group = np.asarray(groups).reshape(-1)
    if residual.shape != group.shape:
        raise ValueError("residuals and groups must have the same one-dimensional shape")
    if residual.size == 0:
        raise ValueError("at least one residual is required")
    if not np.isfinite(residual).all():
        raise ValueError("residuals must be finite")

    oof = np.full(residual.size, -1, dtype=int)
    folds: dict[Hashable, TrainOnlyGmmFold] = {}
    for held_out in np.unique(group):
        test_mask = group == held_out
        train_mask = ~test_mask
        if not train_mask.any() or not test_mask.any():
            raise ValueError("each LOSO fold needs non-empty training and test rows")
        fold = fit_binary_gmm_train_only(
            residual[train_mask], residual[test_mask], random_state=random_state
        )
        oof[test_mask] = fold.test_labels
        folds[held_out] = fold

    if (oof < 0).any():
        raise RuntimeError("LOSO label construction left rows unlabeled")
    return LosoGmmLabels(oof_labels=oof, folds=folds)
