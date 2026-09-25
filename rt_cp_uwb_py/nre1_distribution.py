"""NR-E1 action-conditional range-error distribution utilities.

The module deliberately separates the already-confirmed NR-1 action policy from
the next scientific estimand.  Both CIRP and FUSED density arms predict the
same SINGLE and DUAL candidate errors.  The only arm difference is the frozen
six-column CP increment.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold


CIRP16: tuple[str, ...] = (
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
    "rx_power_db",
    "fp_power_db",
    "fp_minus_rx_power_db",
    "estimated_snr_db",
)

CP_INCREMENTAL6: tuple[str, ...] = (
    "xpr_fp_db",
    "xpr_late_db",
    "xpr_all_db",
    "delta_fp_time_s",
    "reverse_leads",
    "reverse_valid",
)

ACTION_FEATURE = "action_dual"
CIRP_DENSITY: tuple[str, ...] = CIRP16 + (ACTION_FEATURE,)
FUSED_DENSITY: tuple[str, ...] = CIRP_DENSITY + CP_INCREMENTAL6

FORBIDDEN_MODEL_FEATURES: frozenset[str] = frozenset(
    {
        "true_range_m",
        "measurement_range_m",
        "error_m",
        "range_error",
        "oracle_action",
        "stratum_truth",
        "NLOS_label",
        "RD_overlap",
        "bounce_count",
        "los_present",
        "material_truth",
        "path_truth",
        "surface_truth",
        "room_id",
        "ds_split",
    }
)

DEFAULT_MODEL_CONFIG: Mapping[str, object] = {
    "loss": "squared_error",
    "learning_rate": 0.05,
    "max_iter": 200,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 20,
    "l2_regularization": 1.0,
    "random_state": 20260829,
}

CALIBRATION_LEVELS: tuple[float, ...] = (0.50, 0.80, 0.90, 0.95)
CALIBRATION_BOUNDS: Mapping[float, tuple[float, float]] = {
    0.50: (0.45, 0.55),
    0.80: (0.75, 0.85),
    0.90: (0.85, 0.95),
    0.95: (0.90, 1.00),
}


@dataclass(frozen=True)
class DensityConfig:
    outer_folds: int = 5
    inner_folds: int = 4
    sigma_floor_m: float = 0.05
    sigma_cap_m: float = 100.0
    bootstrap_replicates: int = 2000
    bootstrap_seed: int = 20260829

    def validate(self) -> None:
        if self.outer_folds < 2 or self.inner_folds < 2:
            raise ValueError("outer_folds and inner_folds must both be at least two")
        if not 0.0 < self.sigma_floor_m < self.sigma_cap_m:
            raise ValueError("sigma bounds are invalid")
        if self.bootstrap_replicates < 1:
            raise ValueError("bootstrap_replicates must be positive")


def build_action_long(
    feature_table: pd.DataFrame,
    eligible_case_ids: Iterable[int],
    fold_assignments: pd.DataFrame,
) -> pd.DataFrame:
    """Create two identical-target candidate-action rows per eligible case."""

    required = {
        "case_id",
        "room_id",
        "ds_split",
        "stratum_truth",
        "primary_available",
        "single_range_fractional_m",
        "dual_range_fractional_m",
        "true_range_m",
        *CIRP16,
        *CP_INCREMENTAL6,
    }
    missing = sorted(required - set(feature_table.columns))
    if missing:
        raise ValueError(f"feature table is missing required columns: {missing}")
    if feature_table["case_id"].duplicated().any():
        raise ValueError("feature table has duplicate case_id")

    folds = fold_assignments.loc[:, ["case_id", "oof_fold"]].copy()
    if folds["case_id"].duplicated().any():
        raise ValueError("fold assignment has duplicate case_id")

    eligible = {int(value) for value in eligible_case_ids}
    work = feature_table.loc[feature_table["case_id"].astype(int).isin(eligible)].copy()
    work = work.merge(folds, on="case_id", how="inner", validate="one_to_one")
    work = work.loc[work["primary_available"].astype(bool)].copy()
    if set(work["ds_split"].astype(str)) != {"train"}:
        raise ValueError("NR-E1 scientific input must be development/train only")

    numeric_required = [
        "single_range_fractional_m",
        "dual_range_fractional_m",
        "true_range_m",
    ]
    if not np.isfinite(work[numeric_required].to_numpy(float)).all():
        raise ValueError("eligible range/truth rows must be finite")

    rows: list[pd.DataFrame] = []
    for action, range_column, action_value in (
        ("SINGLE", "single_range_fractional_m", 0.0),
        ("DUAL", "dual_range_fractional_m", 1.0),
    ):
        part = work.copy()
        part["action"] = action
        part[ACTION_FEATURE] = action_value
        part["measurement_range_m"] = part[range_column].to_numpy(float)
        part["error_m"] = (
            part["measurement_range_m"].to_numpy(float)
            - part["true_range_m"].to_numpy(float)
        )
        rows.append(part)

    long = pd.concat(rows, ignore_index=True)
    long = long.sort_values(["case_id", ACTION_FEATURE]).reset_index(drop=True)
    counts = long.groupby("case_id", sort=False).size()
    if len(long) != 2 * len(work) or not counts.eq(2).all():
        raise RuntimeError("every eligible case must produce exactly two action rows")
    if long.duplicated(["case_id", "action"]).any():
        raise RuntimeError("duplicate case/action row")

    room_fold = long.loc[:, ["room_id", "oof_fold"]].drop_duplicates()
    if room_fold["room_id"].duplicated().any():
        raise RuntimeError("a room appears in more than one outer fold")
    return long


def new_regressor(
    model_config: Mapping[str, object] = DEFAULT_MODEL_CONFIG,
) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(**dict(model_config))


def gaussian_nll(
    observation: np.ndarray,
    mean: np.ndarray,
    sigma: np.ndarray,
) -> np.ndarray:
    observation = np.asarray(observation, dtype=float)
    mean = np.asarray(mean, dtype=float)
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
    z = (observation - mean) / sigma
    return 0.5 * z * z + np.log(sigma) + 0.5 * math.log(2.0 * math.pi)


def gaussian_crps(
    observation: np.ndarray,
    mean: np.ndarray,
    sigma: np.ndarray,
) -> np.ndarray:
    observation = np.asarray(observation, dtype=float)
    mean = np.asarray(mean, dtype=float)
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
    z = (observation - mean) / sigma
    phi = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return sigma * (z * (2.0 * ndtr(z) - 1.0) + 2.0 * phi - 1.0 / math.sqrt(math.pi))


def gaussian_pit(
    observation: np.ndarray,
    mean: np.ndarray,
    sigma: np.ndarray,
) -> np.ndarray:
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
    return ndtr((np.asarray(observation, dtype=float) - np.asarray(mean, dtype=float)) / sigma)


def central_interval(
    mean: np.ndarray,
    sigma: np.ndarray,
    level: float,
) -> tuple[np.ndarray, np.ndarray]:
    tail = (1.0 - float(level)) / 2.0
    z = float(ndtri(1.0 - tail))
    mean = np.asarray(mean, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    return mean - z * sigma, mean + z * sigma


def _inner_mean_oof(
    train: pd.DataFrame,
    features: Sequence[str],
    config: DensityConfig,
    model_config: Mapping[str, object],
) -> tuple[np.ndarray, list[dict[str, object]]]:
    rooms = train["room_id"].astype(str).to_numpy()
    if np.unique(rooms).size < config.inner_folds:
        raise ValueError("not enough outer-train rooms for inner GroupKFold")
    x = train.loc[:, list(features)].to_numpy(float)
    y = train["error_m"].to_numpy(float)
    pred = np.full(len(train), np.nan, dtype=float)
    records: list[dict[str, object]] = []
    splitter = GroupKFold(n_splits=config.inner_folds)
    for inner_fold, (fit_idx, val_idx) in enumerate(splitter.split(x, y, groups=rooms)):
        fit_rooms = set(rooms[fit_idx])
        val_rooms = set(rooms[val_idx])
        overlap = fit_rooms & val_rooms
        if overlap:
            raise RuntimeError(f"inner room leakage: {sorted(overlap)}")
        model = new_regressor(model_config)
        model.fit(x[fit_idx], y[fit_idx])
        pred[val_idx] = model.predict(x[val_idx])
        records.append(
            {
                "inner_fold": int(inner_fold),
                "fit_rooms": int(len(fit_rooms)),
                "validation_rooms": int(len(val_rooms)),
                "overlap_rooms": 0,
                "fit_rows": int(len(fit_idx)),
                "validation_rows": int(len(val_idx)),
            }
        )
    if not np.isfinite(pred).all():
        raise RuntimeError("inner mean OOF is incomplete or non-finite")
    return pred, records


def fit_outer_fold(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: Sequence[str],
    config: DensityConfig,
    model_config: Mapping[str, object] = DEFAULT_MODEL_CONFIG,
) -> tuple[pd.DataFrame, HistGradientBoostingRegressor, HistGradientBoostingRegressor, list[dict[str, object]]]:
    """Fit nested mean/scale models and predict one outer held-out fold."""

    config.validate()
    train_rooms = set(train["room_id"].astype(str))
    test_rooms = set(test["room_id"].astype(str))
    overlap = train_rooms & test_rooms
    if overlap:
        raise RuntimeError(f"outer room leakage: {sorted(overlap)}")

    inner_mean, inner_records = _inner_mean_oof(
        train,
        features,
        config,
        model_config,
    )
    y_train = train["error_m"].to_numpy(float)
    squared = np.maximum(
        np.square(y_train - inner_mean),
        config.sigma_floor_m**2,
    )
    log_variance_target = np.log(squared)

    x_train = train.loc[:, list(features)].to_numpy(float)
    x_test = test.loc[:, list(features)].to_numpy(float)
    mean_model = new_regressor(model_config)
    scale_model = new_regressor(model_config)
    mean_model.fit(x_train, y_train)
    scale_model.fit(x_train, log_variance_target)

    mean = mean_model.predict(x_test)
    log_variance = scale_model.predict(x_test)
    log_variance = np.clip(
        log_variance,
        2.0 * math.log(config.sigma_floor_m),
        2.0 * math.log(config.sigma_cap_m),
    )
    sigma = np.clip(
        np.exp(0.5 * log_variance),
        config.sigma_floor_m,
        config.sigma_cap_m,
    )
    observation = test["error_m"].to_numpy(float)
    prediction = test.loc[
        :, ["case_id", "room_id", "stratum_truth", "action", "action_dual", "oof_fold", "error_m"]
    ].copy()
    prediction["pred_mu_m"] = mean
    prediction["pred_sigma_m"] = sigma
    prediction["nll"] = gaussian_nll(observation, mean, sigma)
    prediction["crps_m"] = gaussian_crps(observation, mean, sigma)
    prediction["pit"] = gaussian_pit(observation, mean, sigma)
    for level in CALIBRATION_LEVELS:
        lo, hi = central_interval(mean, sigma, level)
        tag = int(round(100.0 * level))
        prediction[f"lo_{tag}_m"] = lo
        prediction[f"hi_{tag}_m"] = hi
        prediction[f"covered_{tag}"] = (observation >= lo) & (observation <= hi)
    return prediction, mean_model, scale_model, inner_records


def paired_room_bootstrap(
    paired: pd.DataFrame,
    strata: Sequence[str],
    config: DensityConfig,
) -> pd.DataFrame:
    required = {
        "room_id",
        "stratum_truth",
        "action",
        "delta_nll_fused_minus_cirp",
        "delta_crps_fused_minus_cirp_m",
    }
    missing = sorted(required - set(paired.columns))
    if missing:
        raise ValueError(f"paired bootstrap input missing: {missing}")
    rng = np.random.default_rng(config.bootstrap_seed)
    rows: list[dict[str, object]] = []

    def subset(frame: pd.DataFrame, stratum: str) -> pd.DataFrame:
        if stratum == "ALL":
            return frame
        if stratum == "ACTION_SINGLE":
            return frame.loc[frame["action"].eq("SINGLE")]
        if stratum == "ACTION_DUAL":
            return frame.loc[frame["action"].eq("DUAL")]
        return frame.loc[frame["stratum_truth"].eq(stratum)]

    for stratum in strata:
        part = subset(paired, stratum)
        rooms = np.asarray(sorted(part["room_id"].astype(str).unique()), dtype=object)
        if rooms.size == 0:
            continue
        room_rows = {room: part.loc[part["room_id"].astype(str).eq(room)] for room in rooms}
        for replicate in range(config.bootstrap_replicates):
            selected = rng.choice(rooms, size=len(rooms), replace=True)
            sampled = pd.concat([room_rows[str(room)] for room in selected], ignore_index=True)
            rows.append(
                {
                    "replicate": int(replicate),
                    "stratum": stratum,
                    "n_sampled_rooms": int(len(selected)),
                    "n_rows": int(len(sampled)),
                    "delta_nll_fused_minus_cirp": float(
                        sampled["delta_nll_fused_minus_cirp"].mean()
                    ),
                    "delta_crps_fused_minus_cirp_m": float(
                        sampled["delta_crps_fused_minus_cirp_m"].mean()
                    ),
                }
            )
    return pd.DataFrame(rows)


def calibration_summary(prediction: pd.DataFrame) -> dict[str, float | bool | int]:
    pit = prediction["pit"].to_numpy(float)
    pit = pit[np.isfinite(pit)]
    if pit.size == 0:
        raise ValueError("PIT input is empty")
    ordered = np.sort(pit)
    n = len(ordered)
    empirical = np.arange(1, n + 1, dtype=float) / n
    empirical_prev = np.arange(0, n, dtype=float) / n
    ks = float(max(np.max(np.abs(empirical - ordered)), np.max(np.abs(ordered - empirical_prev))))
    result: dict[str, float | bool | int] = {
        "n_rows": int(len(prediction)),
        "n_rooms": int(prediction["room_id"].nunique()),
        "pit_ks_d": ks,
        "pit_mean": float(np.mean(pit)),
    }
    gate = ks < 0.05
    for level in CALIBRATION_LEVELS:
        tag = int(round(100.0 * level))
        observed = float(prediction[f"covered_{tag}"].mean())
        low, high = CALIBRATION_BOUNDS[level]
        result[f"coverage_{tag}"] = observed
        result[f"coverage_{tag}_abs_error"] = abs(observed - level)
        result[f"coverage_{tag}_gate"] = bool(low <= observed <= high)
        gate = gate and bool(low <= observed <= high)
    result["calibration_gate"] = bool(gate)
    return result


def percentile_ci(values: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return math.nan, math.nan
    alpha = 1.0 - float(level)
    low, high = np.quantile(values, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(low), float(high)

