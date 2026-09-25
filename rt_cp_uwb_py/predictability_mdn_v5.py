"""Leakage-safe, early-stopped MDN training utilities for v5.

This module is additive.  It does not change the historical v3/v4 MDN helper.
Every fit uses an outer room-disjoint test fold and an outer-train-only,
room-disjoint calibration split.  The calibration NLL is the sole
early-stopping signal.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .predictability_mdn import MDNConfig, encode_features
from .predictability_stats import (
    assert_room_disjoint,
    mixture_nll,
    stable_room_calibration_split,
)


@dataclass(frozen=True)
class EarlyStoppingContract:
    max_epochs: int
    patience: int
    min_delta: float


def _schema_hash(encoded: Sequence[str]) -> str:
    return hashlib.sha256(
        json.dumps(list(encoded), ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _stable_seed(*parts: object) -> int:
    token = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:16], 16)


def _is_anchor_column(encoded_name: str, anchor_features: Sequence[str]) -> bool:
    return any(
        encoded_name == feature or encoded_name.startswith(f"{feature}_")
        for feature in anchor_features
    )


def _apply_schema_nested_initialization(
    model: object,
    encoded_features: Sequence[str],
    anchor_features: Sequence[str],
    seed: int,
) -> dict[str, object]:
    """Make the E8 nested arms identical at the shared-feature null model.

    The historical ``MDNHead`` consumes one RNG stream whose draw count changes
    with the input dimension.  Consequently, the same seed does not preserve
    the parameters of an existing feature when a nested feature is appended.
    This additive v5 repair assigns the CIR-anchor columns and downstream
    layers from name/layer-keyed streams, while every newly appended column is
    initialized at zero.  The appended columns remain trainable because the
    non-zero anchor path supplies hidden-layer gradients.
    """

    encoded = list(encoded_features)
    anchor_indices = [
        index
        for index, name in enumerate(encoded)
        if _is_anchor_column(str(name), anchor_features)
    ]
    if not anchor_indices:
        raise ValueError("V5_SCHEMA_NESTED_INITIALIZATION_WITHOUT_ANCHOR")
    hidden = int(model.W1.shape[0])
    model.W1[:] = 0.0
    scale = float(np.sqrt(2.0 / len(anchor_indices)))
    for index in anchor_indices:
        rng = np.random.default_rng(
            _stable_seed("v5-schema-nested-w1", int(seed), encoded[index])
        )
        model.W1[:, index] = rng.normal(0.0, scale, hidden)
    model.b1[:] = 0.0
    rng_w2 = np.random.default_rng(
        _stable_seed("v5-schema-nested-w2", int(seed))
    )
    model.W2[:] = rng_w2.normal(
        0.0, np.sqrt(2.0 / hidden), model.W2.shape
    )
    model.b2[:] = 0.0
    rng_w3 = np.random.default_rng(
        _stable_seed("v5-schema-nested-w3", int(seed))
    )
    model.W3[:] = rng_w3.normal(
        0.0, np.sqrt(2.0 / hidden), model.W3.shape
    )
    model.b3[:] = 0.0

    shared_digest = hashlib.sha256()
    for index in sorted(anchor_indices, key=lambda value: encoded[value]):
        shared_digest.update(encoded[index].encode("utf-8"))
        shared_digest.update(
            np.ascontiguousarray(model.W1[:, index], dtype=np.float64).tobytes()
        )
    for value in (model.b1, model.W2, model.b2, model.W3, model.b3):
        shared_digest.update(
            np.ascontiguousarray(value, dtype=np.float64).tobytes()
        )
    appended_indices = sorted(set(range(len(encoded))) - set(anchor_indices))
    appended_max = (
        float(np.max(np.abs(model.W1[:, appended_indices])))
        if appended_indices
        else 0.0
    )
    return {
        "initialization_mode": "schema_nested_null_v1",
        "initial_anchor_encoded_count": int(len(anchor_indices)),
        "initial_appended_encoded_count": int(len(appended_indices)),
        "initial_appended_weight_max_abs": appended_max,
        "initial_shared_parameter_sha256": shared_digest.hexdigest(),
        "initialization_contract_pass": bool(appended_max == 0.0),
    }


def _copy_parameters(model) -> tuple[np.ndarray, ...]:
    return tuple(
        np.array(value, copy=True)
        for value in (model.W1, model.b1, model.W2, model.b2, model.W3, model.b3)
    )


def _restore_parameters(model, values: Sequence[np.ndarray]) -> None:
    (
        model.W1,
        model.b1,
        model.W2,
        model.b2,
        model.W3,
        model.b3,
    ) = tuple(np.array(value, copy=True) for value in values)


def _mean_nll(
    model,
    x: np.ndarray,
    residual: np.ndarray,
    cfg: MDNConfig,
) -> float:
    weight, sigma_c, sigma_x = model.predict(x)
    values = mixture_nll(
        residual,
        weight,
        sigma_c,
        sigma_x,
        cfg.mu_contam_m,
        cfg.mu_clean_m,
    )
    return float(np.mean(values))


def _fit_early_stopped(
    x_train: np.ndarray,
    residual_train: np.ndarray,
    x_calibration: np.ndarray,
    residual_calibration: np.ndarray,
    *,
    cfg: MDNConfig,
    early: EarlyStoppingContract,
    seed: int,
    encoded_features: Sequence[str],
    initialization_mode: str,
    initialization_anchor_features: Sequence[str],
) -> tuple[object, list[dict[str, object]], dict[str, object]]:
    from scripts.exp5_mdn_head import MDNHead

    model = MDNHead(
        n_hidden=cfg.hidden,
        lr=cfg.learning_rate,
        n_epochs=early.max_epochs,
        batch_size=cfg.batch_size,
        seed=int(seed),
        n_input=x_train.shape[1],
        mu_c=cfg.mu_contam_m,
        mu_0=cfg.mu_clean_m,
    )
    if initialization_mode == "schema_nested_null_v1":
        initialization = _apply_schema_nested_initialization(
            model,
            encoded_features,
            initialization_anchor_features,
            int(seed),
        )
    elif initialization_mode == "legacy_dimension_dependent":
        initialization = {
            "initialization_mode": initialization_mode,
            "initial_anchor_encoded_count": np.nan,
            "initial_appended_encoded_count": np.nan,
            "initial_appended_weight_max_abs": np.nan,
            "initial_shared_parameter_sha256": "",
            "initialization_contract_pass": True,
        }
    else:
        raise ValueError(f"V5_UNKNOWN_INITIALIZATION_MODE:{initialization_mode}")
    rng = np.random.default_rng(int(seed))
    params = [model.W1, model.b1, model.W2, model.b2, model.W3, model.b3]
    first = [np.zeros_like(value) for value in params]
    second = [np.zeros_like(value) for value in params]
    beta1, beta2, epsilon = 0.9, 0.999, 1e-8
    update_index = 0
    best_loss = np.inf
    best_epoch = 0
    best_parameters: tuple[np.ndarray, ...] | None = None
    epochs_without_improvement = 0
    log_rows: list[dict[str, object]] = []
    stop_reason = "MAX_EPOCHS"

    for epoch_index in range(int(early.max_epochs)):
        indices = rng.permutation(len(x_train))
        for start in range(0, len(indices), int(cfg.batch_size)):
            batch = indices[start : start + int(cfg.batch_size)]
            _, gradients = model.loss_and_grad(
                x_train[batch], residual_train[batch]
            )
            update_index += 1
            for parameter, gradient, moment1, moment2 in zip(
                params, gradients, first, second
            ):
                moment1[:] = beta1 * moment1 + (1.0 - beta1) * gradient
                moment2[:] = beta2 * moment2 + (1.0 - beta2) * gradient**2
                corrected1 = moment1 / (1.0 - beta1**update_index)
                corrected2 = moment2 / (1.0 - beta2**update_index)
                parameter -= cfg.learning_rate * corrected1 / (
                    np.sqrt(corrected2) + epsilon
                )

        train_loss = _mean_nll(model, x_train, residual_train, cfg)
        calibration_loss = _mean_nll(
            model, x_calibration, residual_calibration, cfg
        )
        improved = bool(
            np.isfinite(calibration_loss)
            and calibration_loss < best_loss - float(early.min_delta)
        )
        if improved:
            best_loss = calibration_loss
            best_epoch = epoch_index + 1
            best_parameters = _copy_parameters(model)
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        log_rows.append(
            {
                "epoch": epoch_index + 1,
                "train_loss": train_loss,
                "calibration_loss": calibration_loss,
                "best_calibration_loss": best_loss,
                "improved": improved,
            }
        )
        if epochs_without_improvement >= int(early.patience):
            stop_reason = "PATIENCE"
            break

    if best_parameters is not None:
        _restore_parameters(model, best_parameters)
    finite_best = bool(np.isfinite(best_loss) and best_parameters is not None)
    summary = {
        "best_epoch": int(best_epoch),
        "epochs_ran": int(len(log_rows)),
        "best_calibration_loss": float(best_loss),
        "stop_reason": stop_reason,
        "finite_best_loss": finite_best,
        "convergence_pass": finite_best,
        **initialization,
    }
    return model, log_rows, summary


def _fold_task(
    payload: tuple[
        pd.DataFrame,
        int,
        str,
        list[str],
        MDNConfig,
        EarlyStoppingContract,
        list[int],
        str,
        str,
        list[str],
    ]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    (
        frame,
        fold,
        arm,
        features,
        cfg,
        early,
        seeds,
        experiment_id,
        initialization_mode,
        initialization_anchor_features,
    ) = payload
    outer_test = frame.loc[frame.fold.eq(fold)].copy()
    outer_train = frame.loc[~frame.fold.eq(fold)].copy()
    model_rooms, calibration_rooms = stable_room_calibration_split(
        outer_train.room_id,
        cfg.calibration_fraction,
        cfg.calibration_hash_seed,
    )
    model_train = outer_train.loc[
        outer_train.room_id.astype(str).isin(model_rooms)
    ].copy()
    calibration = outer_train.loc[
        outer_train.room_id.astype(str).isin(calibration_rooms)
    ].copy()
    assert_room_disjoint(model_train, calibration, outer_test, "room_id")
    x_train, x_calibration, encoded = encode_features(
        model_train, calibration, features
    )
    _, x_test, encoded_test = encode_features(model_train, outer_test, features)
    if encoded != encoded_test:
        raise ValueError("V5_ENCODED_SCHEMA_MISMATCH")
    schema_hash = _schema_hash(encoded)
    prediction_rows: list[dict[str, object]] = []
    history_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    residual_train = model_train.r_residual.to_numpy(float)
    residual_calibration = calibration.r_residual.to_numpy(float)
    residual_test = outer_test.r_residual.to_numpy(float)

    for seed in seeds:
        model, history, summary = _fit_early_stopped(
            x_train,
            residual_train,
            x_calibration,
            residual_calibration,
            cfg=cfg,
            early=early,
            seed=int(seed),
            encoded_features=encoded,
            initialization_mode=initialization_mode,
            initialization_anchor_features=initialization_anchor_features,
        )
        for row in history:
            row.update(
                {
                    "experiment_id": experiment_id,
                    "arm": arm,
                    "fold": int(fold),
                    "seed": int(seed),
                    "encoded_schema_sha256": schema_hash,
                }
            )
            history_rows.append(row)
        summary_rows.append(
            {
                "experiment_id": experiment_id,
                "arm": arm,
                "fold": int(fold),
                "seed": int(seed),
                "feature_count_raw": int(len(features)),
                "features": ";".join(features),
                "encoded_feature_count": int(len(encoded)),
                "encoded_feature_list": ";".join(encoded),
                "encoded_schema_sha256": schema_hash,
                "model_room_count": int(model_train.room_id.nunique()),
                "calibration_room_count": int(calibration.room_id.nunique()),
                "test_room_count": int(outer_test.room_id.nunique()),
                **summary,
            }
        )
        weight, sigma_c, sigma_x = model.predict(x_test)
        nll = mixture_nll(
            residual_test,
            weight,
            sigma_c,
            sigma_x,
            cfg.mu_contam_m,
            cfg.mu_clean_m,
        )
        for index, (_, source) in enumerate(outer_test.iterrows()):
            prediction_rows.append(
                {
                    "experiment_id": experiment_id,
                    "arm": arm,
                    "case_id": int(source.case_id),
                    "room_id": str(source.room_id),
                    "fold": int(fold),
                    "seed": int(seed),
                    "partition": "test",
                    "nll": float(nll[index]),
                    "w": float(weight[index]),
                    "sigma_c": float(sigma_c[index]),
                    "sigma_x": float(sigma_x[index]),
                    "mu_c": float(cfg.mu_contam_m),
                    "mu_x": float(cfg.mu_clean_m),
                    "encoded_schema_sha256": schema_hash,
                }
            )
    return (
        pd.DataFrame(prediction_rows),
        pd.DataFrame(history_rows),
        pd.DataFrame(summary_rows),
    )


def fit_oof_mdn_v5(
    frame: pd.DataFrame,
    arm_features: Mapping[str, Sequence[str]],
    *,
    cfg: MDNConfig,
    early: EarlyStoppingContract,
    seeds: Iterable[int],
    experiment_id: str,
    workers: int,
    per_fold_features: Mapping[tuple[str, int], Sequence[str]] | None = None,
    initialization_mode: str = "legacy_dimension_dependent",
    initialization_anchor_features: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit every arm/fold/seed with one shared training contract.

    ``per_fold_features`` supports fold-local E16 state columns.  Static E8
    arms use ``arm_features`` directly.
    """

    required = {"case_id", "room_id", "fold", "r_residual"}
    if not required.issubset(frame.columns):
        raise ValueError(f"V5_FRAME_MISSING:{sorted(required - set(frame.columns))}")
    tasks = []
    folds = [int(value) for value in sorted(frame.fold.unique())]
    seed_values = [int(value) for value in seeds]
    for arm, default_features in arm_features.items():
        for fold in folds:
            features = list(
                per_fold_features.get((arm, fold), default_features)
                if per_fold_features is not None
                else default_features
            )
            missing = set(features) - set(frame.columns)
            if missing:
                raise ValueError(f"V5_ARM_MISSING:{arm}:{sorted(missing)}")
            keep = sorted(required | set(features))
            tasks.append(
                (
                    frame.loc[:, keep].copy(),
                    fold,
                    str(arm),
                    features,
                    cfg,
                    early,
                    seed_values,
                    experiment_id,
                    str(initialization_mode),
                    list(initialization_anchor_features),
                )
            )
    if int(workers) > 1:
        with ProcessPoolExecutor(max_workers=min(int(workers), len(tasks))) as pool:
            results = list(pool.map(_fold_task, tasks, chunksize=1))
    else:
        results = [_fold_task(task) for task in tasks]
    predictions = pd.concat([item[0] for item in results], ignore_index=True)
    history = pd.concat([item[1] for item in results], ignore_index=True)
    summary = pd.concat([item[2] for item in results], ignore_index=True)
    return predictions, history, summary


def seed_ensemble(predictions: pd.DataFrame) -> pd.DataFrame:
    required = {"experiment_id", "arm", "case_id", "room_id", "fold", "nll"}
    if not required.issubset(predictions.columns):
        raise ValueError("V5_PREDICTION_SCHEMA")
    return (
        predictions.loc[predictions.partition.eq("test")]
        .groupby(
            ["experiment_id", "arm", "case_id", "room_id", "fold"],
            as_index=False,
        )[["nll", "w", "sigma_c", "sigma_x", "mu_c", "mu_x"]]
        .mean()
    )
