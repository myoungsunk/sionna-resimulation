"""OOF MDN utilities used only by the additive predictability-deficit v3 runner."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .predictability_stats import assert_room_disjoint, mixture_nll, stable_room_calibration_split


@dataclass(frozen=True)
class MDNConfig:
    hidden: int
    epochs: int
    batch_size: int
    learning_rate: float
    mu_clean_m: float
    mu_contam_m: float
    calibration_fraction: float
    calibration_hash_seed: int


def encode_features(train: pd.DataFrame, other: pd.DataFrame, columns: Sequence[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Train-only one-hot encoding and train-only standardisation."""
    train_work, other_work = train.loc[:, columns].copy(), other.loc[:, columns].copy()
    combined_train = pd.get_dummies(train_work, dummy_na=True, dtype=float)
    combined_other = pd.get_dummies(other_work, dummy_na=True, dtype=float).reindex(columns=combined_train.columns, fill_value=0.0)
    x_train = combined_train.to_numpy(dtype=float)
    x_other = combined_other.to_numpy(dtype=float)
    finite_train = np.where(np.isfinite(x_train), x_train, np.nan)
    med = np.nanmedian(finite_train, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    x_train = np.where(np.isfinite(x_train), x_train, med)
    x_other = np.where(np.isfinite(x_other), x_other, med)
    scale = np.nanstd(x_train, axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    return (x_train - x_train.mean(axis=0)) / scale, (x_other - x_train.mean(axis=0)) / scale, list(combined_train.columns)


def _fit_model(x_train: np.ndarray, residual_train: np.ndarray, cfg: MDNConfig, seed: int):
    from scripts.exp5_mdn_head import MDNHead
    model = MDNHead(n_hidden=cfg.hidden, lr=cfg.learning_rate, n_epochs=cfg.epochs, batch_size=cfg.batch_size, seed=seed, n_input=x_train.shape[1], mu_c=cfg.mu_contam_m, mu_0=cfg.mu_clean_m)
    model.fit(x_train, residual_train)
    return model


def fit_oof_mdn(
    frame: pd.DataFrame,
    features: Sequence[str],
    cfg: MDNConfig,
    seeds: Iterable[int],
    arm: str,
    experiment_id: str,
    outer_fold_column: str = "fold",
    room_column: str = "room_id",
    residual_column: str = "r_residual",
    sample_balance_column: str | None = None,
    shuffle_feature_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """Fit 80% room-train MDNs and export calibration/test parameters per seed.

    The 20% calibration rooms are never used in model fitting.  If balance is
    requested, deterministic inverse-prevalence resampling is applied to the
    model-training partition only.
    """
    required = set(features) | {outer_fold_column, room_column, residual_column, "case_id"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"MDN arm {arm} missing features: {sorted(missing)}")
    records: list[dict[str, object]] = []
    for fold in sorted(frame[outer_fold_column].unique()):
        outer_test = frame.loc[frame[outer_fold_column] == fold].copy()
        outer_train = frame.loc[frame[outer_fold_column] != fold].copy()
        model_rooms, calibration_rooms = stable_room_calibration_split(outer_train[room_column], cfg.calibration_fraction, cfg.calibration_hash_seed)
        model_train = outer_train.loc[outer_train[room_column].astype(str).isin(model_rooms)].copy()
        calibration = outer_train.loc[outer_train[room_column].astype(str).isin(calibration_rooms)].copy()
        assert_room_disjoint(model_train, calibration, outer_test, room_column)
        # Negative-control shuffling is performed inside each outer fold after
        # the split has been fixed.  Train, calibration, and test partitions
        # use independent deterministic permutations, so no true oracle value
        # survives as a feature in any partition.
        for column in shuffle_feature_columns:
            if column not in model_train or column not in calibration or column not in outer_test:
                raise ValueError(f"shuffle feature unavailable: {column}")
            for partition_name, partition in (("model_train", model_train), ("calibration", calibration), ("test", outer_test)):
                token = int(hashlib.sha256(f"{experiment_id}:{arm}:{fold}:{column}:{partition_name}".encode()).hexdigest()[:16], 16)
                rng = np.random.default_rng(token)
                partition[column] = rng.permutation(partition[column].to_numpy())
        if sample_balance_column is not None:
            if sample_balance_column not in model_train:
                raise ValueError(f"balance column unavailable: {sample_balance_column}")
            counts = model_train[sample_balance_column].astype(str).value_counts()
            weights = model_train[sample_balance_column].astype(str).map(lambda x: 1.0 / counts[x]).to_numpy(float)
            token = int(hashlib.sha256(f"{experiment_id}:{arm}:{fold}".encode()).hexdigest()[:16], 16)
            rng = np.random.default_rng(token)
            choose = rng.choice(np.arange(len(model_train)), size=len(model_train), replace=True, p=weights / weights.sum())
            model_train = model_train.iloc[choose].copy()
        x_train, x_calibration, encoded = encode_features(model_train, calibration, features)
        _, x_test, _ = encode_features(model_train, outer_test, features)
        for seed in seeds:
            model = _fit_model(x_train, model_train[residual_column].to_numpy(float), cfg, int(seed))
            w_cal, sc_cal, sx_cal = model.predict(x_calibration)
            w_test, sc_test, sx_test = model.predict(x_test)
            for partition, subset, w, sc, sx in (("calibration", calibration, w_cal, sc_cal, sx_cal), ("test", outer_test, w_test, sc_test, sx_test)):
                nll = mixture_nll(subset[residual_column].to_numpy(float), w, sc, sx, cfg.mu_contam_m, cfg.mu_clean_m)
                for row_idx, (_, row) in enumerate(subset.iterrows()):
                    records.append({
                        "experiment_id": experiment_id, "arm": arm, "case_id": int(row.case_id),
                        "room_id": str(row[room_column]), "fold": int(fold), "seed": int(seed),
                        "partition": partition, "nll": float(nll[row_idx]), "w": float(w[row_idx]),
                        "sigma_c": float(sc[row_idx]), "sigma_x": float(sx[row_idx]),
                        "mu_c": float(cfg.mu_contam_m), "mu_x": float(cfg.mu_clean_m),
                        "encoded_feature_count": len(encoded), "encoded_feature_list": ";".join(encoded),
                    })
    return pd.DataFrame(records).sort_values(["case_id", "seed", "arm", "partition"]).reset_index(drop=True)
