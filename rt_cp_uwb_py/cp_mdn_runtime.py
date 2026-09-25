"""Frozen two-component MDN inference and scalar Gaussian-sum updates.

This module is the production, inference-only counterpart of
``scripts/exp5_mdn_head.py``.  It deliberately accepts only the feature columns
declared by the frozen standardization artifact.  Ground-truth poses, residual
labels, and channel-state labels are neither required nor inspected.

The MDN component order is always:

1. contaminated: ``(w, mu_c, sigma_c)``
2. clean: ``(1 - w, mu_0, sigma_x)``

The same implementation can load a CP-compact or CIR-shape model as long as its
weight and standardization artifacts follow the verified Exp5 NPZ schema.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


_LOG_2PI = float(np.log(2.0 * np.pi))
_PROHIBITED_FEATURE_NAMES = frozenset(
    {
        "truth_x_m",
        "truth_y_m",
        "true_range_m",
        "range_error_m",
        "r_residual",
        "nolos",
        "rd-los",
        "rd_los",
        "ps_gt",
        "oracle_mode",
    }
)


def _readonly_float_array(value: Any) -> np.ndarray:
    array = np.array(value, dtype=float, copy=True)
    array.setflags(write=False)
    return array


def _require_finite(name: str, value: np.ndarray) -> None:
    if not np.all(np.isfinite(value)):
        raise ValueError(f"{name} must contain only finite values")


def _validate_covariance(covariance: np.ndarray, *, name: str) -> None:
    _require_finite(name, covariance)
    if covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]:
        raise ValueError(f"{name} must be a square matrix")
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1.0e-12):
        raise ValueError(f"{name} must be symmetric")
    if float(np.linalg.eigvalsh(covariance).min()) < -1.0e-10:
        raise ValueError(f"{name} must be positive semidefinite")


@dataclass(frozen=True)
class TwoComponentMixture:
    """Batch of two-component residual likelihood parameters."""

    w: np.ndarray
    sigma_c: np.ndarray
    sigma_x: np.ndarray
    mu_c: np.ndarray
    mu_0: np.ndarray

    def __post_init__(self) -> None:
        arrays = [
            _readonly_float_array(self.w),
            _readonly_float_array(self.sigma_c),
            _readonly_float_array(self.sigma_x),
            _readonly_float_array(self.mu_c),
            _readonly_float_array(self.mu_0),
        ]
        arrays = list(np.broadcast_arrays(*arrays))
        for name, array in zip(
            ("w", "sigma_c", "sigma_x", "mu_c", "mu_0"), arrays
        ):
            frozen = np.array(array, dtype=float, copy=True)
            frozen.setflags(write=False)
            object.__setattr__(self, name, frozen)
            _require_finite(name, frozen)
        if np.any((self.w < 0.0) | (self.w > 1.0)):
            raise ValueError("w must lie in [0, 1]")
        if np.any(self.sigma_c <= 0.0) or np.any(self.sigma_x <= 0.0):
            raise ValueError("component sigmas must be strictly positive")

    @property
    def shape(self) -> tuple[int, ...]:
        return self.w.shape

    def as_tuple(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return ``(w, sigma_c, sigma_x, mu_c, mu_0)``."""

        return self.w, self.sigma_c, self.sigma_x, self.mu_c, self.mu_0


@dataclass(frozen=True)
class MomentMatchedGaussian:
    """Gaussian having the same first two moments as a two-component mixture."""

    mean: np.ndarray
    variance: np.ndarray

    @property
    def sigma(self) -> np.ndarray:
        return np.sqrt(self.variance)


@dataclass(frozen=True)
class GaussianUpdate:
    """Result of one scalar Gaussian measurement update."""

    mean: np.ndarray
    covariance: np.ndarray
    innovation_variance: float
    log_likelihood: float


@dataclass(frozen=True)
class GaussianSumUpdate:
    """A normalized Gaussian-sum posterior with reduction audit metadata."""

    weights: np.ndarray
    means: np.ndarray
    covariances: np.ndarray
    log_evidence: float
    discarded_mass: float
    merge_kl_bound: float = 0.0
    n_merge_ops: int = 0
    n_sibling_merge_ops: int = 0
    n_threshold_merge_ops: int = 0
    emergency_truncation: bool = False
    reduced_vs_full_mean_error: float = 0.0
    reduced_vs_full_second_moment_error: float = 0.0
    reduced_vs_full_moment_error: float = 0.0


@dataclass(frozen=True)
class GaussianSumReduction:
    """Mass-preserving Gaussian-mixture reduction and its fidelity audit."""

    weights: np.ndarray
    means: np.ndarray
    covariances: np.ndarray
    discarded_mass: float
    merge_kl_bound: float
    n_merge_ops: int
    n_sibling_merge_ops: int
    n_threshold_merge_ops: int
    emergency_truncation: bool
    reduced_vs_full_mean_error: float
    reduced_vs_full_second_moment_error: float
    reduced_vs_full_moment_error: float


@dataclass(frozen=True)
class FrozenMDNRuntime:
    """Validated frozen standardizer and two-hidden-layer NumPy MDN."""

    feature_names: tuple[str, ...]
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    W1: np.ndarray
    b1: np.ndarray
    W2: np.ndarray
    b2: np.ndarray
    W3: np.ndarray
    b3: np.ndarray
    mu_c: float
    mu_0: float
    sigma_c_min: float
    sigma_x_min: float

    def _feature_matrix(
        self,
        frame: Any,
        feature_columns: Sequence[str] | None,
    ) -> np.ndarray:
        columns = self.feature_names if feature_columns is None else tuple(feature_columns)
        if columns != self.feature_names:
            raise ValueError(
                "feature_columns must exactly match frozen artifact order: "
                f"{self.feature_names!r}"
            )

        if isinstance(frame, Mapping):
            missing = [name for name in columns if name not in frame]
            if missing:
                raise ValueError(f"missing feature columns: {missing}")
            column_arrays = [np.asarray(frame[name], dtype=float) for name in columns]
            column_arrays = [
                value.reshape(1) if value.ndim == 0 else value for value in column_arrays
            ]
            if any(value.ndim != 1 for value in column_arrays):
                raise ValueError("mapping feature values must be scalars or 1-D arrays")
            lengths = {len(value) for value in column_arrays}
            if len(lengths) != 1:
                raise ValueError("mapping feature columns must have equal lengths")
            matrix = np.column_stack(column_arrays)
        elif hasattr(frame, "columns") and hasattr(frame, "loc"):
            available = set(str(name) for name in frame.columns)
            missing = [name for name in columns if name not in available]
            if missing:
                raise ValueError(f"missing feature columns: {missing}")
            matrix = np.asarray(frame.loc[:, list(columns)], dtype=float)
        else:
            matrix = np.asarray(frame, dtype=float)
            if matrix.ndim == 1:
                matrix = matrix.reshape(1, -1)

        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError(
                f"feature matrix must have shape (n, {len(self.feature_names)})"
            )
        _require_finite("feature matrix", matrix)
        return matrix

    def standardize(
        self,
        frame: Any,
        feature_columns: Sequence[str] | None = None,
    ) -> np.ndarray:
        """Apply the frozen training mean and scale without refitting."""

        matrix = self._feature_matrix(frame, feature_columns)
        standardized = (matrix - self.feature_mean) / self.feature_scale
        _require_finite("standardized feature matrix", standardized)
        return standardized

    def predict_parameters(
        self,
        frame: Any,
        feature_columns: Sequence[str] | None = None,
    ) -> TwoComponentMixture:
        """Evaluate frozen MDN parameters for CP or CIR feature rows."""

        X = self.standardize(frame, feature_columns)
        z1 = np.maximum(0.0, X @ self.W1.T + self.b1)
        z2 = np.maximum(0.0, z1 @ self.W2.T + self.b2)
        output = z2 @ self.W3.T + self.b3

        w = 1.0 / (1.0 + np.exp(-np.clip(output[:, 0], -30.0, 30.0)))
        sigma_c = np.log1p(np.exp(np.clip(output[:, 1], -30.0, 30.0)))
        sigma_x = np.log1p(np.exp(np.clip(output[:, 2], -30.0, 30.0)))
        return TwoComponentMixture(
            w=w,
            sigma_c=sigma_c + self.sigma_c_min,
            sigma_x=sigma_x + self.sigma_x_min,
            mu_c=np.full(len(X), self.mu_c),
            mu_0=np.full(len(X), self.mu_0),
        )

    def predict(
        self,
        frame: Any,
        feature_columns: Sequence[str] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Integration API returning ``(w, sigma_c, sigma_x, mu_c, mu_0)``."""

        return self.predict_parameters(frame, feature_columns).as_tuple()


def load_mdn_runtime(
    model_path: str | Path,
    scaler_path: str | Path,
) -> FrozenMDNRuntime:
    """Load and validate frozen Exp5-compatible model/scaler NPZ artifacts."""

    model_path = Path(model_path)
    scaler_path = Path(scaler_path)
    required_model = {
        "W1",
        "b1",
        "W2",
        "b2",
        "W3",
        "b3",
        "mu_c",
        "mu_0",
        "n_input",
        "n_hidden",
        "sigma_c_min",
        "sigma_x_min",
    }
    required_scaler = {"mu_x", "std_x", "feats"}

    with np.load(model_path, allow_pickle=False) as artifact:
        missing = sorted(required_model.difference(artifact.files))
        if missing:
            raise ValueError(f"model artifact is missing keys: {missing}")
        n_input = int(np.asarray(artifact["n_input"]).item())
        n_hidden = int(np.asarray(artifact["n_hidden"]).item())
        model_values = {
            name: _readonly_float_array(artifact[name])
            for name in ("W1", "b1", "W2", "b2", "W3", "b3")
        }
        scalar_values = {
            name: float(np.asarray(artifact[name]).item())
            for name in ("mu_c", "mu_0", "sigma_c_min", "sigma_x_min")
        }

    with np.load(scaler_path, allow_pickle=False) as artifact:
        missing = sorted(required_scaler.difference(artifact.files))
        if missing:
            raise ValueError(f"scaler artifact is missing keys: {missing}")
        feature_mean = _readonly_float_array(artifact["mu_x"])
        feature_scale = _readonly_float_array(artifact["std_x"])
        feature_names = tuple(str(value) for value in artifact["feats"].tolist())

    expected_shapes = {
        "W1": (n_hidden, n_input),
        "b1": (n_hidden,),
        "W2": (n_hidden, n_hidden),
        "b2": (n_hidden,),
        "W3": (3, n_hidden),
        "b3": (3,),
    }
    for name, expected in expected_shapes.items():
        if model_values[name].shape != expected:
            raise ValueError(
                f"{name} has shape {model_values[name].shape}, expected {expected}"
            )
        _require_finite(name, model_values[name])
    if feature_mean.shape != (n_input,) or feature_scale.shape != (n_input,):
        raise ValueError("frozen scaler vectors must match model n_input")
    _require_finite("feature_mean", feature_mean)
    _require_finite("feature_scale", feature_scale)
    if np.any(feature_scale <= 0.0):
        raise ValueError("frozen feature scales must be strictly positive")
    if len(feature_names) != n_input or len(set(feature_names)) != n_input:
        raise ValueError("frozen feature names must be unique and match n_input")
    prohibited = sorted(
        name for name in feature_names if name.casefold() in _PROHIBITED_FEATURE_NAMES
    )
    if prohibited:
        raise ValueError(f"evaluator-only features are prohibited: {prohibited}")
    if not all(np.isfinite(value) for value in scalar_values.values()):
        raise ValueError("model scalar parameters must be finite")
    if scalar_values["sigma_c_min"] <= 0.0 or scalar_values["sigma_x_min"] <= 0.0:
        raise ValueError("model sigma floors must be strictly positive")

    return FrozenMDNRuntime(
        feature_names=feature_names,
        feature_mean=feature_mean,
        feature_scale=feature_scale,
        **model_values,
        **scalar_values,
    )


def load_frozen_mdn(
    weights_path: str | Path,
    standardization_path: str | Path,
) -> FrozenMDNRuntime:
    """Descriptive alias for :func:`load_mdn_runtime`."""

    return load_mdn_runtime(weights_path, standardization_path)


def two_component_log_density(
    residual: Any,
    mixture: TwoComponentMixture,
) -> np.ndarray:
    """Stable elementwise log density of the actual two-component mixture."""

    residual_array = np.asarray(residual, dtype=float)
    _require_finite("residual", residual_array)
    residual_array, w, sigma_c, sigma_x, mu_c, mu_0 = np.broadcast_arrays(
        residual_array,
        mixture.w,
        mixture.sigma_c,
        mixture.sigma_x,
        mixture.mu_c,
        mixture.mu_0,
    )
    log_pc = (
        -0.5 * ((residual_array - mu_c) / sigma_c) ** 2
        - np.log(sigma_c)
        - 0.5 * _LOG_2PI
    )
    log_p0 = (
        -0.5 * ((residual_array - mu_0) / sigma_x) ** 2
        - np.log(sigma_x)
        - 0.5 * _LOG_2PI
    )
    log_w = np.full(w.shape, -np.inf, dtype=float)
    log_1mw = np.full(w.shape, -np.inf, dtype=float)
    positive_w = w > 0.0
    positive_1mw = w < 1.0
    log_w[positive_w] = np.log(w[positive_w])
    log_1mw[positive_1mw] = np.log1p(-w[positive_1mw])
    return np.logaddexp(log_w + log_pc, log_1mw + log_p0)


def two_component_nll(
    residual: Any,
    mixture: TwoComponentMixture,
) -> np.ndarray:
    """Elementwise negative log likelihood; no averaging or filtering."""

    return -two_component_log_density(residual, mixture)


def moment_match_two_component(
    mixture: TwoComponentMixture,
) -> MomentMatchedGaussian:
    """Apply the law of total variance without collapsing between-mode spread."""

    mean = mixture.w * mixture.mu_c + (1.0 - mixture.w) * mixture.mu_0
    second_moment = mixture.w * (
        mixture.sigma_c**2 + mixture.mu_c**2
    ) + (1.0 - mixture.w) * (mixture.sigma_x**2 + mixture.mu_0**2)
    variance = np.maximum(second_moment - mean**2, 0.0)
    return MomentMatchedGaussian(mean=mean, variance=variance)


def gaussian_measurement_update(
    prior_mean: Any,
    prior_covariance: Any,
    innovation: float,
    measurement_jacobian: Any,
    *,
    residual_mean: float,
    residual_sigma: float,
) -> GaussianUpdate:
    """Update one Gaussian with one scalar residual-likelihood component.

    ``innovation`` is ``z - h(prior_mean)``.  ``residual_mean`` is subtracted
    before applying the Kalman gain.  A Joseph-form covariance update is used.
    """

    mean = np.asarray(prior_mean, dtype=float)
    covariance = np.asarray(prior_covariance, dtype=float)
    jacobian = np.asarray(measurement_jacobian, dtype=float)
    if mean.ndim != 1:
        raise ValueError("prior_mean must be 1-D")
    if jacobian.shape != mean.shape:
        raise ValueError("measurement_jacobian must match prior_mean shape")
    if covariance.shape != (len(mean), len(mean)):
        raise ValueError("prior_covariance shape must match prior_mean")
    _require_finite("prior_mean", mean)
    _require_finite("measurement_jacobian", jacobian)
    _validate_covariance(covariance, name="prior_covariance")
    if not np.isfinite(innovation) or not np.isfinite(residual_mean):
        raise ValueError("innovation and residual_mean must be finite")
    if not np.isfinite(residual_sigma) or residual_sigma <= 0.0:
        raise ValueError("residual_sigma must be finite and strictly positive")

    measurement_variance = float(residual_sigma**2)
    innovation_variance = float(
        jacobian @ covariance @ jacobian + measurement_variance
    )
    if not np.isfinite(innovation_variance) or innovation_variance <= 0.0:
        raise ValueError("innovation variance must be finite and positive")
    centered_innovation = float(innovation - residual_mean)
    gain = covariance @ jacobian / innovation_variance
    posterior_mean = mean + gain * centered_innovation
    identity_minus_kh = np.eye(len(mean)) - np.outer(gain, jacobian)
    posterior_covariance = (
        identity_minus_kh @ covariance @ identity_minus_kh.T
        + measurement_variance * np.outer(gain, gain)
    )
    posterior_covariance = 0.5 * (
        posterior_covariance + posterior_covariance.T
    )
    log_likelihood = (
        -0.5 * centered_innovation**2 / innovation_variance
        - 0.5 * np.log(innovation_variance)
        - 0.5 * _LOG_2PI
    )
    return GaussianUpdate(
        mean=posterior_mean,
        covariance=posterior_covariance,
        innovation_variance=innovation_variance,
        log_likelihood=float(log_likelihood),
    )


def prune_gaussian_sum(
    weights: Any,
    means: Any,
    covariances: Any,
    *,
    min_weight: float = 1.0e-4,
    max_components: int = 16,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Prune normalized components and return the discarded probability mass."""

    weight_array = np.asarray(weights, dtype=float)
    mean_array = np.asarray(means, dtype=float)
    covariance_array = np.asarray(covariances, dtype=float)
    if weight_array.ndim != 1 or len(weight_array) == 0:
        raise ValueError("weights must be a non-empty 1-D array")
    if mean_array.ndim != 2 or mean_array.shape[0] != len(weight_array):
        raise ValueError("means must have shape (components, state_dim)")
    if covariance_array.shape != (
        len(weight_array),
        mean_array.shape[1],
        mean_array.shape[1],
    ):
        raise ValueError("covariances must have shape (components, state_dim, state_dim)")
    _require_finite("weights", weight_array)
    _require_finite("means", mean_array)
    _require_finite("covariances", covariance_array)
    if np.any(weight_array < 0.0) or float(weight_array.sum()) <= 0.0:
        raise ValueError("weights must be nonnegative with positive total mass")
    if not np.isfinite(min_weight) or min_weight < 0.0:
        raise ValueError("min_weight must be finite and nonnegative")
    if max_components < 1:
        raise ValueError("max_components must be at least one")

    normalized = weight_array / weight_array.sum()
    keep = np.flatnonzero(normalized >= min_weight)
    if len(keep) == 0:
        keep = np.array([int(np.argmax(normalized))])
    ranked = keep[np.argsort(-normalized[keep], kind="stable")]
    keep = ranked[:max_components]
    kept_mass = float(normalized[keep].sum())
    discarded_mass = max(0.0, 1.0 - kept_mass)
    kept_weights = normalized[keep] / kept_mass
    return (
        kept_weights,
        mean_array[keep].copy(),
        covariance_array[keep].copy(),
        discarded_mass,
    )


@dataclass
class _ReductionComponent:
    weight: float
    mean: np.ndarray
    covariance: np.ndarray
    lineage: tuple[int, ...]
    sibling_group: int | None
    regularized_logdet: float


def _mixture_first_and_second_moments(
    components: Sequence[_ReductionComponent],
) -> tuple[np.ndarray, np.ndarray]:
    mean = sum(
        (component.weight * component.mean for component in components),
        start=np.zeros_like(components[0].mean),
    )
    second = sum(
        (
            component.weight
            * (
                component.covariance
                + np.outer(component.mean, component.mean)
            )
            for component in components
        ),
        start=np.zeros_like(components[0].covariance),
    )
    return mean, second


def _regularized_logdet(covariance: np.ndarray, eigenvalue_floor: float) -> float:
    symmetric = 0.5 * (covariance + covariance.T)
    regularized = symmetric + np.eye(len(symmetric)) * eigenvalue_floor
    if regularized.shape == (2, 2):
        determinant = float(
            regularized[0, 0] * regularized[1, 1]
            - regularized[0, 1] * regularized[1, 0]
        )
        if determinant > 0.0:
            return float(np.log(determinant))
    sign, logdet = np.linalg.slogdet(regularized)
    if sign <= 0.0 or not np.isfinite(logdet):
        raise FloatingPointError("regularized covariance log determinant is invalid")
    return float(logdet)


def _merge_components(
    left: _ReductionComponent,
    right: _ReductionComponent,
    *,
    covariance_eigenvalue_floor: float,
) -> tuple[_ReductionComponent, float]:
    weight = left.weight + right.weight
    mean = (left.weight * left.mean + right.weight * right.mean) / weight
    left_delta = left.mean - mean
    right_delta = right.mean - mean
    covariance = (
        left.weight
        * (left.covariance + np.outer(left_delta, left_delta))
        + right.weight
        * (right.covariance + np.outer(right_delta, right_delta))
    ) / weight
    covariance = 0.5 * (covariance + covariance.T)
    sibling_group = (
        left.sibling_group
        if left.sibling_group is not None
        and left.sibling_group == right.sibling_group
        else None
    )
    merged = _ReductionComponent(
        weight=weight,
        mean=mean,
        covariance=covariance,
        lineage=tuple(sorted(left.lineage + right.lineage)),
        sibling_group=sibling_group,
        regularized_logdet=_regularized_logdet(
            covariance, covariance_eigenvalue_floor
        ),
    )
    score = 0.5 * (
        weight * merged.regularized_logdet
        - left.weight * left.regularized_logdet
        - right.weight * right.regularized_logdet
    )
    if not np.isfinite(score):
        raise FloatingPointError("Runnalls merge score is not finite")
    return merged, max(0.0, float(score))


def _mahalanobis_distance(
    left: _ReductionComponent,
    right: _ReductionComponent,
    *,
    covariance_eigenvalue_floor: float,
) -> float:
    pooled = 0.5 * (left.covariance + right.covariance)
    pooled = 0.5 * (pooled + pooled.T)
    eigenvalues, eigenvectors = np.linalg.eigh(pooled)
    inverse = (eigenvectors * (1.0 / np.maximum(
        eigenvalues, covariance_eigenvalue_floor
    ))) @ eigenvectors.T
    delta = left.mean - right.mean
    squared = max(0.0, float(delta @ inverse @ delta))
    return float(np.sqrt(squared))


def _best_merge_pair(
    components: Sequence[_ReductionComponent],
    *,
    covariance_eigenvalue_floor: float,
    require_sibling: bool = False,
    sibling_mahalanobis_epsilon: float | None = None,
    required_index: int | None = None,
    score_cache: dict[
        tuple[tuple[int, ...], tuple[int, ...]], float
    ] | None = None,
) -> tuple[int, int, float] | None:
    candidates: list[tuple[float, tuple[int, ...], tuple[int, ...], int, int]] = []
    for left_index in range(len(components) - 1):
        for right_index in range(left_index + 1, len(components)):
            if required_index is not None and required_index not in (
                left_index,
                right_index,
            ):
                continue
            left = components[left_index]
            right = components[right_index]
            if require_sibling:
                if (
                    left.sibling_group is None
                    or left.sibling_group != right.sibling_group
                ):
                    continue
                distance = _mahalanobis_distance(
                    left,
                    right,
                    covariance_eigenvalue_floor=covariance_eigenvalue_floor,
                )
                if (
                    sibling_mahalanobis_epsilon is None
                    or distance >= sibling_mahalanobis_epsilon
                ):
                    continue
            cache_key = (left.lineage, right.lineage)
            score = None if score_cache is None else score_cache.get(cache_key)
            if score is None:
                _, score = _merge_components(
                    left,
                    right,
                    covariance_eigenvalue_floor=covariance_eigenvalue_floor,
                )
                if score_cache is not None:
                    score_cache[cache_key] = score
            candidates.append(
                (
                    score,
                    left.lineage,
                    right.lineage,
                    left_index,
                    right_index,
                )
            )
    if not candidates:
        return None
    score, _, _, left_index, right_index = min(candidates)
    return left_index, right_index, score


def _apply_merge(
    components: list[_ReductionComponent],
    left_index: int,
    right_index: int,
    *,
    covariance_eigenvalue_floor: float,
) -> tuple[list[_ReductionComponent], float]:
    merged, score = _merge_components(
        components[left_index],
        components[right_index],
        covariance_eigenvalue_floor=covariance_eigenvalue_floor,
    )
    retained = [
        component
        for index, component in enumerate(components)
        if index not in (left_index, right_index)
    ]
    retained.append(merged)
    retained.sort(key=lambda component: component.lineage)
    return retained, score


def reduce_gaussian_sum(
    weights: Any,
    means: Any,
    covariances: Any,
    *,
    min_weight: float = 1.0e-4,
    max_components: int = 16,
    sibling_groups: Any | None = None,
    sibling_mahalanobis_epsilon: float = 1.0e-6,
    covariance_eigenvalue_floor: float = 1.0e-12,
) -> GaussianSumReduction:
    """Reduce a Gaussian sum by deterministic, mass-preserving Runnalls merges.

    Qualifying sibling pairs are merged first.  Components below ``min_weight``
    are merged, rather than discarded, into their minimum-bound partner.  The
    remaining mixture is reduced to ``max_components`` using the Runnalls
    pairwise KL upper bound.  Scores are tied deterministically by immutable
    input lineage.  Covariance eigenvalue regularization is used only while
    computing merge scores and Mahalanobis distances; output moments retain the
    exact moment-matched covariance.

    The legacy top-K truncation is retained solely as an emergency fallback.
    Its use is exposed by ``emergency_truncation`` and nonzero
    ``discarded_mass`` so callers can terminate the run.
    """

    weight_array = np.asarray(weights, dtype=float)
    mean_array = np.asarray(means, dtype=float)
    covariance_array = np.asarray(covariances, dtype=float)
    if weight_array.ndim != 1 or len(weight_array) == 0:
        raise ValueError("weights must be a non-empty 1-D array")
    if mean_array.ndim != 2 or mean_array.shape[0] != len(weight_array):
        raise ValueError("means must have shape (components, state_dim)")
    if covariance_array.shape != (
        len(weight_array),
        mean_array.shape[1],
        mean_array.shape[1],
    ):
        raise ValueError(
            "covariances must have shape (components, state_dim, state_dim)"
        )
    _require_finite("weights", weight_array)
    _require_finite("means", mean_array)
    _require_finite("covariances", covariance_array)
    if np.any(weight_array < 0.0) or float(weight_array.sum()) <= 0.0:
        raise ValueError("weights must be nonnegative with positive total mass")
    if not np.isfinite(min_weight) or min_weight < 0.0:
        raise ValueError("min_weight must be finite and nonnegative")
    if max_components < 1:
        raise ValueError("max_components must be at least one")
    if (
        not np.isfinite(sibling_mahalanobis_epsilon)
        or sibling_mahalanobis_epsilon < 0.0
    ):
        raise ValueError(
            "sibling_mahalanobis_epsilon must be finite and nonnegative"
        )
    if (
        not np.isfinite(covariance_eigenvalue_floor)
        or covariance_eigenvalue_floor <= 0.0
    ):
        raise ValueError(
            "covariance_eigenvalue_floor must be finite and positive"
        )
    for index, covariance in enumerate(covariance_array):
        _validate_covariance(covariance, name=f"covariances[{index}]")

    if sibling_groups is None:
        group_array = np.full(len(weight_array), -1, dtype=int)
    else:
        group_array = np.asarray(sibling_groups)
        if group_array.shape != (len(weight_array),):
            raise ValueError("sibling_groups must have one value per component")

    normalized = weight_array / weight_array.sum()
    components = [
        _ReductionComponent(
            weight=float(weight),
            mean=mean_array[index].copy(),
            covariance=covariance_array[index].copy(),
            lineage=(index,),
            sibling_group=(
                None if sibling_groups is None else int(group_array[index])
            ),
            regularized_logdet=_regularized_logdet(
                covariance_array[index], covariance_eigenvalue_floor
            ),
        )
        for index, weight in enumerate(normalized)
        if weight > 0.0
    ]
    full_mean, full_second = _mixture_first_and_second_moments(components)
    merge_kl_bound = 0.0
    n_merge_ops = 0
    n_sibling_merge_ops = 0
    n_threshold_merge_ops = 0
    emergency_truncation = False
    discarded_mass = 0.0
    score_cache: dict[
        tuple[tuple[int, ...], tuple[int, ...]], float
    ] = {}

    try:
        while len(components) > 1:
            pair = _best_merge_pair(
                components,
                covariance_eigenvalue_floor=covariance_eigenvalue_floor,
                require_sibling=True,
                sibling_mahalanobis_epsilon=sibling_mahalanobis_epsilon,
                score_cache=score_cache,
            )
            if pair is None:
                break
            components, score = _apply_merge(
                components,
                pair[0],
                pair[1],
                covariance_eigenvalue_floor=covariance_eigenvalue_floor,
            )
            merge_kl_bound += score
            n_merge_ops += 1
            n_sibling_merge_ops += 1

        while len(components) > 1:
            below = [
                (component.weight, component.lineage, index)
                for index, component in enumerate(components)
                if component.weight < min_weight
            ]
            if not below:
                break
            _, _, required_index = min(below)
            pair = _best_merge_pair(
                components,
                covariance_eigenvalue_floor=covariance_eigenvalue_floor,
                required_index=required_index,
                score_cache=score_cache,
            )
            if pair is None:
                raise FloatingPointError(
                    "no finite partner for a below-threshold component"
                )
            components, score = _apply_merge(
                components,
                pair[0],
                pair[1],
                covariance_eigenvalue_floor=covariance_eigenvalue_floor,
            )
            merge_kl_bound += score
            n_merge_ops += 1
            n_threshold_merge_ops += 1

        while len(components) > max_components:
            pair = _best_merge_pair(
                components,
                covariance_eigenvalue_floor=covariance_eigenvalue_floor,
                score_cache=score_cache,
            )
            if pair is None:
                raise FloatingPointError("no finite Runnalls merge pair")
            components, score = _apply_merge(
                components,
                pair[0],
                pair[1],
                covariance_eigenvalue_floor=covariance_eigenvalue_floor,
            )
            merge_kl_bound += score
            n_merge_ops += 1
    except (FloatingPointError, np.linalg.LinAlgError):
        emergency_truncation = True
        current_weights = np.asarray(
            [component.weight for component in components], dtype=float
        )
        current_means = np.asarray(
            [component.mean for component in components], dtype=float
        )
        current_covariances = np.asarray(
            [component.covariance for component in components], dtype=float
        )
        (
            fallback_weights,
            fallback_means,
            fallback_covariances,
            discarded_mass,
        ) = prune_gaussian_sum(
            current_weights,
            current_means,
            current_covariances,
            min_weight=min_weight,
            max_components=max_components,
        )
        components = [
            _ReductionComponent(
                weight=float(weight),
                mean=fallback_means[index],
                covariance=fallback_covariances[index],
                lineage=(index,),
                sibling_group=None,
                regularized_logdet=_regularized_logdet(
                    fallback_covariances[index],
                    covariance_eigenvalue_floor,
                ),
            )
            for index, weight in enumerate(fallback_weights)
        ]

    components.sort(key=lambda component: (-component.weight, component.lineage))
    reduced_mean, reduced_second = _mixture_first_and_second_moments(components)
    mean_error = float(
        np.linalg.norm(reduced_mean - full_mean)
        / max(1.0, float(np.linalg.norm(full_mean)))
    )
    second_error = float(
        np.linalg.norm(reduced_second - full_second, ord="fro")
        / max(1.0, float(np.linalg.norm(full_second, ord="fro")))
    )
    return GaussianSumReduction(
        weights=np.asarray(
            [component.weight for component in components], dtype=float
        ),
        means=np.asarray(
            [component.mean for component in components], dtype=float
        ),
        covariances=np.asarray(
            [component.covariance for component in components], dtype=float
        ),
        discarded_mass=float(discarded_mass),
        merge_kl_bound=float(merge_kl_bound),
        n_merge_ops=n_merge_ops,
        n_sibling_merge_ops=n_sibling_merge_ops,
        n_threshold_merge_ops=n_threshold_merge_ops,
        emergency_truncation=emergency_truncation,
        reduced_vs_full_mean_error=mean_error,
        reduced_vs_full_second_moment_error=second_error,
        reduced_vs_full_moment_error=max(mean_error, second_error),
    )


def _logsumexp_1d(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    if not np.isfinite(maximum):
        raise FloatingPointError("all Gaussian-sum branches have zero numerical mass")
    return maximum + float(np.log(np.exp(values - maximum).sum()))


def gaussian_sum_measurement_update(
    prior_weights: Any,
    prior_means: Any,
    prior_covariances: Any,
    innovations: Any,
    measurement_jacobians: Any,
    mixture: TwoComponentMixture,
    *,
    min_weight: float = 1.0e-4,
    max_components: int = 16,
    sibling_mahalanobis_epsilon: float = 1.0e-6,
    covariance_eigenvalue_floor: float = 1.0e-12,
) -> GaussianSumUpdate:
    """Preserve both MDN modes while updating a scalar-measurement GSF.

    Each prior component is split into contaminated and clean children.  The
    Children are reduced by deterministic, mass-preserving Runnalls merges.
    ``discarded_mass`` remains zero unless the emergency top-K fallback is
    activated, in which case ``emergency_truncation`` is also true.
    """

    weights = np.asarray(prior_weights, dtype=float)
    means = np.asarray(prior_means, dtype=float)
    covariances = np.asarray(prior_covariances, dtype=float)
    innovation_array = np.asarray(innovations, dtype=float)
    jacobians = np.asarray(measurement_jacobians, dtype=float)
    if mixture.w.size != 1:
        raise ValueError("gaussian_sum_measurement_update requires one link likelihood")
    if weights.ndim != 1 or len(weights) == 0:
        raise ValueError("prior_weights must be a non-empty 1-D array")
    if means.ndim != 2 or means.shape[0] != len(weights):
        raise ValueError("prior_means must have shape (components, state_dim)")
    state_dim = means.shape[1]
    if covariances.shape != (len(weights), state_dim, state_dim):
        raise ValueError(
            "prior_covariances must have shape (components, state_dim, state_dim)"
        )
    if innovation_array.shape != (len(weights),):
        raise ValueError("innovations must have one value per prior component")
    if jacobians.ndim == 1:
        jacobians = np.broadcast_to(jacobians, (len(weights), state_dim))
    if jacobians.shape != (len(weights), state_dim):
        raise ValueError(
            "measurement_jacobians must have shape (components, state_dim)"
        )
    _require_finite("prior_weights", weights)
    _require_finite("prior_means", means)
    _require_finite("prior_covariances", covariances)
    _require_finite("innovations", innovation_array)
    _require_finite("measurement_jacobians", jacobians)
    if np.any(weights < 0.0) or float(weights.sum()) <= 0.0:
        raise ValueError("prior_weights must be nonnegative with positive total mass")
    normalized_prior = weights / weights.sum()
    for index, covariance in enumerate(covariances):
        _validate_covariance(covariance, name=f"prior_covariances[{index}]")

    link_weights = np.array(
        [float(mixture.w.reshape(-1)[0]), 1.0 - float(mixture.w.reshape(-1)[0])]
    )
    link_means = np.array(
        [float(mixture.mu_c.reshape(-1)[0]), float(mixture.mu_0.reshape(-1)[0])]
    )
    link_sigmas = np.array(
        [
            float(mixture.sigma_c.reshape(-1)[0]),
            float(mixture.sigma_x.reshape(-1)[0]),
        ]
    )

    child_log_weights: list[float] = []
    child_means: list[np.ndarray] = []
    child_covariances: list[np.ndarray] = []
    child_sibling_groups: list[int] = []
    for prior_index, prior_weight in enumerate(normalized_prior):
        if prior_weight == 0.0:
            continue
        for link_weight, residual_mean, residual_sigma in zip(
            link_weights, link_means, link_sigmas
        ):
            if link_weight == 0.0:
                continue
            update = gaussian_measurement_update(
                means[prior_index],
                covariances[prior_index],
                float(innovation_array[prior_index]),
                jacobians[prior_index],
                residual_mean=float(residual_mean),
                residual_sigma=float(residual_sigma),
            )
            child_log_weights.append(
                float(np.log(prior_weight) + np.log(link_weight) + update.log_likelihood)
            )
            child_means.append(update.mean)
            child_covariances.append(update.covariance)
            child_sibling_groups.append(prior_index)

    log_joint = np.asarray(child_log_weights, dtype=float)
    log_evidence = _logsumexp_1d(log_joint)
    posterior_weights = np.exp(log_joint - log_evidence)
    reduction = reduce_gaussian_sum(
        posterior_weights,
        np.asarray(child_means),
        np.asarray(child_covariances),
        min_weight=min_weight,
        max_components=max_components,
        sibling_groups=np.asarray(child_sibling_groups, dtype=int),
        sibling_mahalanobis_epsilon=sibling_mahalanobis_epsilon,
        covariance_eigenvalue_floor=covariance_eigenvalue_floor,
    )
    return GaussianSumUpdate(
        weights=reduction.weights,
        means=reduction.means,
        covariances=reduction.covariances,
        log_evidence=log_evidence,
        discarded_mass=reduction.discarded_mass,
        merge_kl_bound=reduction.merge_kl_bound,
        n_merge_ops=reduction.n_merge_ops,
        n_sibling_merge_ops=reduction.n_sibling_merge_ops,
        n_threshold_merge_ops=reduction.n_threshold_merge_ops,
        emergency_truncation=reduction.emergency_truncation,
        reduced_vs_full_mean_error=reduction.reduced_vs_full_mean_error,
        reduced_vs_full_second_moment_error=(
            reduction.reduced_vs_full_second_moment_error
        ),
        reduced_vs_full_moment_error=reduction.reduced_vs_full_moment_error,
    )


__all__ = [
    "FrozenMDNRuntime",
    "GaussianSumReduction",
    "GaussianSumUpdate",
    "GaussianUpdate",
    "MomentMatchedGaussian",
    "TwoComponentMixture",
    "gaussian_measurement_update",
    "gaussian_sum_measurement_update",
    "load_frozen_mdn",
    "load_mdn_runtime",
    "moment_match_two_component",
    "prune_gaussian_sum",
    "reduce_gaussian_sum",
    "two_component_log_density",
    "two_component_nll",
]
