"""Pure helpers for Paper 2 backend gain attribution.

The functions in this module implement the local math contracts from
``paper2_backend_gain_attribution_validation_plan_20260728_v2``.  They do not
read experiment tables, fit models, or inspect evaluator-only truth columns.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from rt_cp_uwb_py import p2_backend_faults
from rt_cp_uwb_py.p2_mixture_reduction import (
    MixtureReductionDiagnostics,
    ReductionPolicy,
    reduce_mixture,
)
from rt_cp_uwb_py.cp_mdn_runtime import (
    MomentMatchedGaussian,
    TwoComponentMixture,
    gaussian_measurement_update,
    moment_match_two_component,
    two_component_log_density,
)


_LOG_2PI = float(np.log(2.0 * np.pi))
_VALID_CONTRACTS = frozenset(
    {"density_prior", "joint_posterior", "evaluator_oracle_diagnostic"}
)
_HYBRID_GROUPS = ("w", "sigma_c", "sigma_x")
_STAGES = frozenset({"smoke", "B1", "B2", "B3", "B4", "full"})
_LINK_KEY = (
    "trajectory_id",
    "schedule_id",
    "replay_seed",
    "step_idx",
    "case_id",
    "anchor_id",
    "condition_id",
)
_STEP_KEY = ("trajectory_id", "schedule_id", "replay_seed", "step_idx")
_TRAJ_KEY = ("trajectory_id", "schedule_id", "replay_seed")
_TRUTH_NAMES = frozenset(
    {
        "truth_x_m",
        "truth_y_m",
        "truth_z_m",
        "true_range_m",
        "true_geometry_range_m",
        "range_error_m",
        "range_error_rt_fp_m",
        "oracle_component",
        "q_clean",
        "q_clean_2H_CP",
        "q_clean_3H_CP",
        "q_clean_2H_CIR_only",
        "q_clean_3H_CIR_only",
    }
)

_BACKEND_WORKER_THREADPOOL_CONTROLLER: Any | None = None
_V3_SCHEMA_VERSION = "p2_backend_gain_attribution.v3"
_V3_REALIZATION_COLUMNS = (
    "stochastic_realization_hash",
    "realization_duplicate_status",
)
_V3_SELECTION_OUTPUT_COLUMNS = (
    "capacity_selected_k",
    "capacity_reference_k",
    "population_scope_id",
)


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


def logsumexp(values: Any, *, axis: int | None = None) -> np.ndarray | float:
    """Stable log-sum-exp with explicit all-zero-mass rejection."""

    array = np.asarray(values, dtype=float)
    _require_finite("values", array)
    if array.size == 0:
        raise ValueError("values must be non-empty")
    maximum = np.max(array, axis=axis, keepdims=True)
    if not np.all(np.isfinite(maximum)):
        raise FloatingPointError("all entries have zero numerical mass")
    result = maximum + np.log(np.sum(np.exp(array - maximum), axis=axis, keepdims=True))
    if axis is None:
        return float(np.squeeze(result))
    return np.squeeze(result, axis=axis)


def gaussian_logpdf(x: Any, mean: Any, covariance: Any) -> float:
    """Log density of a multivariate Gaussian using Cholesky factorization."""

    x_array = np.asarray(x, dtype=float)
    mean_array = np.asarray(mean, dtype=float)
    covariance_array = np.asarray(covariance, dtype=float)
    if x_array.ndim != 1 or mean_array.shape != x_array.shape:
        raise ValueError("x and mean must be 1-D arrays with identical shape")
    if covariance_array.shape != (len(x_array), len(x_array)):
        raise ValueError("covariance shape must match x")
    _require_finite("x", x_array)
    _require_finite("mean", mean_array)
    _validate_covariance(covariance_array, name="covariance")
    try:
        chol = np.linalg.cholesky(covariance_array)
    except np.linalg.LinAlgError as exc:
        raise ValueError("covariance must be positive definite for logpdf") from exc
    delta = x_array - mean_array
    solved = np.linalg.solve(chol, delta)
    logdet = 2.0 * float(np.log(np.diag(chol)).sum())
    return float(-0.5 * (solved @ solved + logdet + len(x_array) * _LOG_2PI))


@dataclass(frozen=True)
class EvidenceContractCheck:
    """Evidence semantics gate result for an arm."""

    evidence_contract: str
    innovation_consumed_by_model: bool
    innovation_multiplied_in_filter: bool
    status: Literal["PASS", "FAIL"]
    gate: str | None = None


def validate_evidence_contract(
    evidence_contract: str,
    *,
    innovation_consumed_by_model: bool,
    innovation_multiplied_in_filter: bool,
) -> EvidenceContractCheck:
    """Validate likelihood evidence and explicit evaluator-only oracle contracts."""

    if evidence_contract not in _VALID_CONTRACTS:
        raise ValueError(f"unknown evidence contract: {evidence_contract!r}")
    valid = (
        evidence_contract in {"density_prior", "evaluator_oracle_diagnostic"}
        and not innovation_consumed_by_model
        and innovation_multiplied_in_filter
    ) or (
        evidence_contract == "joint_posterior"
        and innovation_consumed_by_model
        and not innovation_multiplied_in_filter
    )
    return EvidenceContractCheck(
        evidence_contract=evidence_contract,
        innovation_consumed_by_model=innovation_consumed_by_model,
        innovation_multiplied_in_filter=innovation_multiplied_in_filter,
        status="PASS" if valid else "FAIL",
        gate=None if valid else "P0_DOUBLE_COUNT_OR_OMISSION",
    )


def scalar_zero_mean_variance(mixture: TwoComponentMixture) -> np.ndarray:
    """Within-component variance for the scale-only scalar covariance arm."""

    return mixture.w * mixture.sigma_c**2 + (1.0 - mixture.w) * mixture.sigma_x**2


def mixture_component_arrays(
    mixture: TwoComponentMixture,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return component ``(weights, means, sigmas)`` in contaminated, clean order."""

    if mixture.w.size != 1:
        raise ValueError("one scalar link likelihood is required")
    w = float(mixture.w.reshape(-1)[0])
    return (
        np.array([w, 1.0 - w], dtype=float),
        np.array(
            [float(mixture.mu_c.reshape(-1)[0]), float(mixture.mu_0.reshape(-1)[0])],
            dtype=float,
        ),
        np.array(
            [
                float(mixture.sigma_c.reshape(-1)[0]),
                float(mixture.sigma_x.reshape(-1)[0]),
            ],
            dtype=float,
        ),
    )


@dataclass(frozen=True)
class GSFComponent:
    """One persistent 2D range-EKF Gaussian-sum component."""

    component_id: str
    parent_component_id: str | None
    weight: float
    mean: np.ndarray
    covariance: np.ndarray
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        mean = np.array(self.mean, dtype=float, copy=True)
        covariance = np.array(self.covariance, dtype=float, copy=True)
        if mean.shape != (2,):
            raise ValueError("GSFComponent mean must be a 2-D position")
        if not np.isfinite(self.weight) or self.weight < 0.0:
            raise ValueError("component weight must be finite and nonnegative")
        _require_finite("component mean", mean)
        _validate_covariance(covariance, name="component covariance")
        mean.setflags(write=False)
        covariance.setflags(write=False)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "covariance", covariance)
        if not self.lineage:
            object.__setattr__(self, "lineage", (self.component_id,))


@dataclass(frozen=True)
class PersistentGSFState:
    """Normalized persistent Gaussian-sum state."""

    components: tuple[GSFComponent, ...]
    discarded_mass: float = 0.0

    def __post_init__(self) -> None:
        if not self.components:
            raise ValueError("PersistentGSFState requires at least one component")
        total = float(sum(component.weight for component in self.components))
        if not np.isfinite(total) or total <= 0.0:
            raise ValueError("component weights must have positive total mass")
        normalized = tuple(
            GSFComponent(
                component_id=component.component_id,
                parent_component_id=component.parent_component_id,
                weight=component.weight / total,
                mean=component.mean,
                covariance=component.covariance,
                lineage=component.lineage,
            )
            for component in self.components
        )
        object.__setattr__(self, "components", normalized)
        if not np.isfinite(self.discarded_mass) or self.discarded_mass < 0.0:
            raise ValueError("discarded_mass must be finite and nonnegative")

    @property
    def weights(self) -> np.ndarray:
        return np.array([component.weight for component in self.components], dtype=float)

    @property
    def means(self) -> np.ndarray:
        return np.stack([component.mean for component in self.components])

    @property
    def covariances(self) -> np.ndarray:
        return np.stack([component.covariance for component in self.components])

    @property
    def active_component_count(self) -> int:
        return len(self.components)

    def moment_match(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the Gaussian moment match without mutating persistent state."""

        weights = self.weights
        means = self.means
        mean = weights @ means
        covariance = np.zeros((2, 2), dtype=float)
        for weight, component in zip(weights, self.components):
            delta = component.mean - mean
            covariance += weight * (component.covariance + np.outer(delta, delta))
        covariance = 0.5 * (covariance + covariance.T)
        _validate_covariance(covariance, name="moment matched covariance")
        return mean, covariance

    def mixture_nll(self, truth_xy: Any) -> float:
        """Posterior state NLL using the full mixture and log-sum-exp."""

        truth = np.asarray(truth_xy, dtype=float)
        terms = [
            np.log(component.weight)
            + gaussian_logpdf(truth, component.mean, component.covariance)
            for component in self.components
            if component.weight > 0.0
        ]
        return -float(logsumexp(np.asarray(terms, dtype=float)))

    def point_estimate(self) -> np.ndarray:
        """Posterior mean point estimate fixed by the validation plan."""

        return self.weights @ self.means


def make_persistent_gsf_state(
    weights: Any,
    means: Any,
    covariances: Any,
    *,
    component_prefix: str = "c",
) -> PersistentGSFState:
    """Build a normalized persistent state from arrays."""

    weight_array = np.asarray(weights, dtype=float)
    mean_array = np.asarray(means, dtype=float)
    covariance_array = np.asarray(covariances, dtype=float)
    if weight_array.ndim != 1 or len(weight_array) == 0:
        raise ValueError("weights must be a non-empty 1-D array")
    if mean_array.shape != (len(weight_array), 2):
        raise ValueError("means must have shape (components, 2)")
    if covariance_array.shape != (len(weight_array), 2, 2):
        raise ValueError("covariances must have shape (components, 2, 2)")
    return PersistentGSFState(
        tuple(
            GSFComponent(
                component_id=f"{component_prefix}{index}",
                parent_component_id=None,
                weight=float(weight),
                mean=mean_array[index],
                covariance=covariance_array[index],
            )
            for index, weight in enumerate(weight_array)
        )
    )


def predict_persistent_gsf(
    state: PersistentGSFState,
    odometry_xy: Any,
    process_covariance: Any,
) -> PersistentGSFState:
    """Apply the same odometry increment and process covariance to every component."""

    odometry = np.asarray(odometry_xy, dtype=float)
    process = np.asarray(process_covariance, dtype=float)
    if odometry.shape != (2,):
        raise ValueError("odometry_xy must be a 2-D increment")
    if process.shape != (2, 2):
        raise ValueError("process_covariance must be 2x2")
    _require_finite("odometry_xy", odometry)
    _validate_covariance(process, name="process_covariance")
    return PersistentGSFState(
        tuple(
            GSFComponent(
                component_id=component.component_id,
                parent_component_id=component.parent_component_id,
                weight=component.weight,
                mean=component.mean + odometry,
                covariance=component.covariance + process,
                lineage=component.lineage,
            )
            for component in state.components
        ),
        discarded_mass=state.discarded_mass,
    )


def range_innovation_and_jacobian(
    mean_xy: Any,
    anchor_xy: Any,
    measured_range_m: float,
) -> tuple[float, np.ndarray]:
    """Return scalar range innovation and 2D EKF measurement Jacobian."""

    mean = np.asarray(mean_xy, dtype=float)
    anchor = np.asarray(anchor_xy, dtype=float)
    if mean.shape != (2,) or anchor.shape != (2,):
        raise ValueError("mean_xy and anchor_xy must be 2-D vectors")
    if not np.isfinite(measured_range_m):
        raise ValueError("measured_range_m must be finite")
    delta = mean - anchor
    predicted = float(np.linalg.norm(delta))
    if predicted <= 1.0e-12:
        raise ValueError("range jacobian is undefined at the anchor position")
    return float(measured_range_m - predicted), delta / predicted


@dataclass(frozen=True)
class ComponentUpdateRecord:
    """Serializable per-child measurement update evidence."""

    parent_component_id: str
    component_id: str
    pre_reduction_component_id: str
    post_reduction_component_id: str | None
    is_post_reduction_representative: bool
    weight_pre: float
    link_component_weight: float
    innovation_m: float
    innovation_variance_m2: float
    component_log_likelihood: float
    weight_post_pre_prune: float
    weight_post: float
    state_x_m: float
    state_y_m: float
    cov_xx: float
    cov_xy: float
    cov_yy: float
    discarded_mass: float
    active_component_count: int
    reduction_policy: str = "RUNNALLS_MERGE"
    pre_reduction_component_count: int = 0
    post_reduction_component_count: int = 0
    surviving_mass: float = 0.0
    merged_mass: float = 0.0
    floor_triggered_merge_count: int = 0
    floor_triggered_mass: float = 0.0
    merge_operation_count: int = 0
    pair_cost_evaluation_count: int = 0
    max_pairwise_merge_cost: float = 0.0
    total_merge_cost: float = 0.0
    mixture_mean_shift_l2: float = 0.0
    mixture_cov_frobenius_shift: float = 0.0
    max_pairwise_mahalanobis_separation: float = 0.0
    separation_excluded_mass: float = 0.0


@dataclass(frozen=True)
class PersistentGSFUpdate:
    """Result of one persistent measurement branch/reduction operation."""

    state: PersistentGSFState
    records: tuple[ComponentUpdateRecord, ...]
    log_evidence: float
    pre_prune_component_count: int
    reduction: MixtureReductionDiagnostics | None = None


def _make_merged_gsf_component(
    left: GSFComponent,
    right: GSFComponent,
    weight: float,
    mean: np.ndarray,
    covariance: np.ndarray,
    component_id: str,
) -> GSFComponent:
    """Construct a bounded-provenance merged GSF component.

    ``lineage`` is intentionally *not* a transitive ancestry store.  A merge
    records only its two immediate input component ids, because carrying both
    full parent tuples causes exponential ancestry replication under repeated
    branch-and-merge.  The reduction result's update-local ``lineage_map`` is
    the authoritative many-to-one mapping from every pre-reduction child to
    its post-reduction component.  ``parent_component_id`` remains ``None``
    for a true merge because it has two parents rather than one.
    """

    if left is right:
        parent_id = left.parent_component_id
        lineage = left.lineage
    else:
        parent_id = None
        lineage = tuple(sorted((str(left.component_id), str(right.component_id))))
    return GSFComponent(
        component_id=component_id,
        parent_component_id=parent_id,
        weight=float(weight),
        mean=mean,
        covariance=covariance,
        lineage=lineage,
    )


def update_persistent_gsf_range(
    state: PersistentGSFState,
    measured_range_m: float,
    anchor_xy: Any,
    mixture: TwoComponentMixture,
    *,
    min_component_weight: float = 1.0e-4,
    max_components: int = 16,
    update_index: int = 0,
    reduction_policy: ReductionPolicy = "RUNNALLS_MERGE",
) -> PersistentGSFUpdate:
    """Branch every persistent component then apply the selected reduction policy."""

    if max_components < 1:
        raise ValueError("max_components must be at least one")
    if not np.isfinite(min_component_weight) or min_component_weight < 0.0:
        raise ValueError("min_component_weight must be finite and nonnegative")
    link_weights, residual_means, residual_sigmas = mixture_component_arrays(mixture)
    child_terms: list[tuple[float, GSFComponent, float, float, float, float]] = []
    for parent in state.components:
        innovation, jacobian = range_innovation_and_jacobian(
            parent.mean, anchor_xy, measured_range_m
        )
        for mode_index, (link_weight, residual_mean, residual_sigma) in enumerate(
            zip(link_weights, residual_means, residual_sigmas)
        ):
            if link_weight == 0.0 or parent.weight == 0.0:
                continue
            update = gaussian_measurement_update(
                parent.mean,
                parent.covariance,
                innovation,
                jacobian,
                residual_mean=float(residual_mean),
                residual_sigma=float(residual_sigma),
            )
            component_id = f"{parent.component_id}.u{update_index}m{mode_index}"
            log_raw = (
                np.log(parent.weight)
                + np.log(float(link_weight))
                + update.log_likelihood
            )
            child = GSFComponent(
                component_id=component_id,
                parent_component_id=parent.component_id,
                weight=1.0,
                mean=update.mean,
                covariance=update.covariance,
                lineage=parent.lineage + (component_id,),
            )
            child_terms.append(
                (
                    float(log_raw),
                    child,
                    float(link_weight),
                    float(innovation),
                    float(update.innovation_variance),
                    float(update.log_likelihood),
                )
            )
    if not child_terms:
        raise FloatingPointError("measurement update produced no child components")

    log_raw = np.array([term[0] for term in child_terms], dtype=float)
    log_evidence = float(logsumexp(log_raw))
    pre_reduction_weights = np.exp(log_raw - log_evidence)
    pre_reduction_components = tuple(
        GSFComponent(
            component_id=child.component_id,
            parent_component_id=child.parent_component_id,
            weight=float(weight),
            mean=child.mean,
            covariance=child.covariance,
            lineage=child.lineage,
        )
        for weight, (_, child, _, _, _, _) in zip(pre_reduction_weights, child_terms)
    )
    reduction_result = reduce_mixture(
        pre_reduction_components,
        max_components=max_components,
        merge_weight_floor=min_component_weight,
        policy=reduction_policy,
        component_factory=_make_merged_gsf_component,
    )
    reduction = reduction_result.diagnostics
    kept_components = tuple(reduction_result.components)
    post_by_id = {str(component.component_id): component for component in kept_components}
    members_by_post: dict[str, list[str]] = {}
    for pre_component_id, post_component_id in reduction.lineage_map.items():
        if post_component_id is not None:
            members_by_post.setdefault(str(post_component_id), []).append(
                str(pre_component_id)
            )
    representative_by_post = {
        post_component_id: min(member_ids)
        for post_component_id, member_ids in members_by_post.items()
    }
    records = []
    for index, (_, child, link_weight, innovation, s_var, log_likelihood) in enumerate(
        child_terms
    ):
        pre_component_id = str(child.component_id)
        mapped_post_id = reduction.lineage_map.get(pre_component_id)
        post_component_id = (
            str(mapped_post_id) if mapped_post_id is not None else None
        )
        is_representative = bool(
            post_component_id is not None
            and representative_by_post.get(post_component_id) == pre_component_id
        )
        # Every pre-reduction child remains present for evidence/provenance
        # accounting.  Exactly one row represents each post-reduction
        # component, however, so weight_post sums to one even when every child
        # participated in a merge.  The representative carries the actual
        # reduced state and covariance; non-representative source rows carry
        # zero post weight and retain their pre-reduction state.
        if is_representative:
            post_component = post_by_id[post_component_id]
            exported_component_id = post_component_id
            post_weight = float(post_component.weight)
            exported_mean = np.asarray(post_component.mean, dtype=float)
            exported_covariance = np.asarray(post_component.covariance, dtype=float)
        else:
            exported_component_id = pre_component_id
            post_weight = 0.0
            exported_mean = np.asarray(child.mean, dtype=float)
            exported_covariance = np.asarray(child.covariance, dtype=float)
        records.append(
            ComponentUpdateRecord(
                parent_component_id=str(child.parent_component_id),
                component_id=exported_component_id,
                pre_reduction_component_id=pre_component_id,
                post_reduction_component_id=post_component_id,
                is_post_reduction_representative=is_representative,
                weight_pre=float(
                    next(
                        parent.weight
                        for parent in state.components
                        if parent.component_id == child.parent_component_id
                    )
                ),
                link_component_weight=link_weight,
                innovation_m=innovation,
                innovation_variance_m2=s_var,
                component_log_likelihood=log_likelihood,
                weight_post_pre_prune=float(pre_reduction_weights[index]),
                weight_post=post_weight,
                state_x_m=float(exported_mean[0]),
                state_y_m=float(exported_mean[1]),
                cov_xx=float(exported_covariance[0, 0]),
                cov_xy=float(exported_covariance[0, 1]),
                cov_yy=float(exported_covariance[1, 1]),
                discarded_mass=reduction.discarded_mass,
                active_component_count=len(kept_components),
                reduction_policy=reduction.reduction_policy,
                pre_reduction_component_count=reduction.pre_reduction_component_count,
                post_reduction_component_count=reduction.post_reduction_component_count,
                surviving_mass=reduction.surviving_mass,
                merged_mass=reduction.merged_mass,
                floor_triggered_merge_count=reduction.floor_triggered_merge_count,
                floor_triggered_mass=reduction.floor_triggered_mass,
                merge_operation_count=reduction.merge_operation_count,
                pair_cost_evaluation_count=reduction.pair_cost_evaluation_count,
                max_pairwise_merge_cost=reduction.max_pairwise_merge_cost,
                total_merge_cost=reduction.total_merge_cost,
                mixture_mean_shift_l2=reduction.mixture_mean_shift_l2,
                mixture_cov_frobenius_shift=reduction.mixture_cov_frobenius_shift,
                max_pairwise_mahalanobis_separation=reduction.max_pairwise_mahalanobis_separation,
                separation_excluded_mass=reduction.separation_excluded_mass,
            )
        )
    return PersistentGSFUpdate(
        state=PersistentGSFState(kept_components, discarded_mass=reduction.discarded_mass),
        records=tuple(records),
        log_evidence=log_evidence,
        pre_prune_component_count=len(child_terms),
        reduction=reduction,
    )


def update_mm_before_range(
    mean_xy: Any,
    covariance_xy: Any,
    measured_range_m: float,
    anchor_xy: Any,
    mixture: TwoComponentMixture,
) -> tuple[np.ndarray, np.ndarray]:
    """Compress the residual mixture before one range update."""

    matched = moment_match_two_component(mixture)
    innovation, jacobian = range_innovation_and_jacobian(
        mean_xy, anchor_xy, measured_range_m
    )
    update = gaussian_measurement_update(
        mean_xy,
        covariance_xy,
        innovation,
        jacobian,
        residual_mean=float(matched.mean.reshape(-1)[0]),
        residual_sigma=float(np.sqrt(matched.variance.reshape(-1)[0])),
    )
    return update.mean, update.covariance


def branch_then_merge_range(
    mean_xy: Any,
    covariance_xy: Any,
    measured_range_m: float,
    anchor_xy: Any,
    mixture: TwoComponentMixture,
    *,
    min_component_weight: float = 0.0,
    max_components: int = 16,
    reduction_policy: ReductionPolicy = "RUNNALLS_MERGE",
) -> tuple[np.ndarray, np.ndarray, PersistentGSFUpdate]:
    """Update mixture branches, then moment-match immediately."""

    state = make_persistent_gsf_state(
        [1.0],
        np.asarray(mean_xy, dtype=float)[None, :],
        np.asarray(covariance_xy, dtype=float)[None, :, :],
    )
    update = update_persistent_gsf_range(
        state,
        measured_range_m,
        anchor_xy,
        mixture,
        min_component_weight=min_component_weight,
        max_components=max_components,
        reduction_policy=reduction_policy,
    )
    mean, covariance = update.state.moment_match()
    return mean, covariance, update


def deterministic_tuple_shuffle(
    rows: Sequence[Mapping[str, Any]],
    *,
    key_fields: Sequence[str],
    value_fields: Sequence[str] = ("w", "sigma_c", "sigma_x", "mu_c", "mu_0"),
    seed: int,
) -> list[dict[str, Any]]:
    """Derange prediction tuples across case keys while preserving tuple internals."""

    if len(rows) < 2:
        raise ValueError("at least two rows are required for a fixed-point-free shuffle")
    rng = np.random.default_rng(seed)
    order = np.arange(len(rows))
    for _ in range(128):
        perm = rng.permutation(order)
        if not np.any(perm == order):
            break
    else:
        shift = int(seed % (len(rows) - 1)) + 1
        perm = np.roll(order, shift)
    shuffled: list[dict[str, Any]] = []
    for target_index, source_index in enumerate(perm):
        row = dict(rows[target_index])
        source = rows[int(source_index)]
        for field in value_fields:
            row[field] = source[field]
        row["shuffle_source_key"] = tuple(source[field] for field in key_fields)
        shuffled.append(row)
    return shuffled


def stable_rows_hash(
    rows: Sequence[Mapping[str, Any]],
    *,
    fields: Sequence[str],
    sort: bool,
) -> str:
    """Hash selected row fields with deterministic JSON normalization."""

    payload = [
        {field: _jsonable(row[field]) for field in fields}
        for row in rows
    ]
    if sort:
        payload = sorted(payload, key=lambda item: json.dumps(item, sort_keys=True))
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fixed_point_count(
    original: Sequence[Mapping[str, Any]],
    shuffled: Sequence[Mapping[str, Any]],
    *,
    key_fields: Sequence[str],
) -> int:
    """Count rows whose shuffled source key equals their target key."""

    if len(original) != len(shuffled):
        raise ValueError("original and shuffled row counts must match")
    count = 0
    for row, shuffled_row in zip(original, shuffled):
        target_key = tuple(row[field] for field in key_fields)
        if tuple(shuffled_row["shuffle_source_key"]) == target_key:
            count += 1
    return count


def hybrid_mixture(
    candidate: TwoComponentMixture,
    baseline: TwoComponentMixture,
    mask: Mapping[str, bool],
) -> TwoComponentMixture:
    """Build a B3 hybrid using learned groups ``w``, ``sigma_c``, ``sigma_x``."""

    unknown = sorted(set(mask).difference(_HYBRID_GROUPS))
    if unknown:
        raise ValueError(f"unknown hybrid parameter groups: {unknown}")
    return TwoComponentMixture(
        w=candidate.w if mask.get("w", False) else baseline.w,
        sigma_c=candidate.sigma_c if mask.get("sigma_c", False) else baseline.sigma_c,
        sigma_x=candidate.sigma_x if mask.get("sigma_x", False) else baseline.sigma_x,
        mu_c=baseline.mu_c,
        mu_0=baseline.mu_0,
    )


def enumerate_hybrid_masks(
    groups: Sequence[str] = _HYBRID_GROUPS,
) -> tuple[dict[str, bool], ...]:
    """Enumerate the preregistered B3 learned-parameter masks."""

    groups = tuple(groups)
    unknown = sorted(set(groups).difference(_HYBRID_GROUPS))
    if unknown:
        raise ValueError(f"unknown hybrid parameter groups: {unknown}")
    masks: list[dict[str, bool]] = []
    for bits in range(1 << len(groups)):
        masks.append(
            {
                group: bool((bits >> index) & 1)
                for index, group in enumerate(groups)
            }
        )
    return tuple(masks)


def shapley_values(
    values_by_mask: Mapping[frozenset[str], float],
    *,
    groups: Sequence[str] = _HYBRID_GROUPS,
) -> dict[str, float]:
    """Exact Shapley attribution over the B3 hybrid mask lattice."""

    groups = tuple(groups)
    group_set = frozenset(groups)
    expected_masks = {
        frozenset(group for index, group in enumerate(groups) if (bits >> index) & 1)
        for bits in range(1 << len(groups))
    }
    missing = expected_masks.difference(values_by_mask)
    if missing:
        raise ValueError(f"missing mask values: {sorted(map(tuple, missing))}")
    factorial = math.factorial
    n_groups = len(groups)
    output: dict[str, float] = {}
    for group in groups:
        others = tuple(item for item in groups if item != group)
        contribution = 0.0
        for bits in range(1 << len(others)):
            subset = frozenset(
                item for index, item in enumerate(others) if (bits >> index) & 1
            )
            weight = (
                factorial(len(subset))
                * factorial(n_groups - len(subset) - 1)
                / factorial(n_groups)
            )
            contribution += weight * (
                float(values_by_mask[subset | {group}]) - float(values_by_mask[subset])
            )
        output[group] = float(contribution)
    closure = sum(output.values())
    expected = float(values_by_mask[group_set]) - float(values_by_mask[frozenset()])
    if not np.isclose(closure, expected, rtol=0.0, atol=1.0e-10):
        raise FloatingPointError("Shapley values failed exact closure")
    return output


class BackendAttributionContractError(RuntimeError):
    """Fail-closed stage execution blocker."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_authority_root(prefix: str, *, required_file: str) -> Path:
    if not prefix:
        raise BackendAttributionContractError("P0_AUTHORITY_PREFIX_MISSING")
    root = _repo_root()
    path = Path(prefix)
    exact = path if path.is_absolute() else root / path
    if (exact / required_file).is_file():
        return exact.resolve()
    parent = exact.parent
    pattern = f"{exact.name}_*"
    candidates = sorted(
        candidate
        for candidate in parent.glob(pattern)
        if (candidate / required_file).is_file()
    )
    if not candidates:
        raise BackendAttributionContractError(
            f"P0_AUTHORITY_TABLE_MISSING:{required_file}:{exact}"
        )
    return candidates[-1].resolve()


def _read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise BackendAttributionContractError(f"P0_REQUIRED_TABLE_MISSING:{path}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    if path.suffix == ".json":
        return pd.DataFrame([json.loads(path.read_text(encoding="utf-8"))])
    raise BackendAttributionContractError(f"P0_UNSUPPORTED_TABLE_FORMAT:{path}")


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], table: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise BackendAttributionContractError(f"P0_SCHEMA_MISSING:{table}:{missing}")


def _assert_runtime_truth_free(frame: pd.DataFrame) -> None:
    leaked = []
    for column in frame.columns:
        lower = str(column).lower()
        if column in _TRUTH_NAMES or any(
            token in lower
            for token in ("truth", "true_", "range_error", "oracle", "q_clean")
        ):
            leaked.append(str(column))
    if leaked:
        raise BackendAttributionContractError(f"P0_TRUTH_LEAKAGE:{leaked}")


def _parse_xy(value: Any) -> np.ndarray:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") or text.startswith("("):
            value = json.loads(text.replace("(", "[").replace(")", "]"))
        else:
            delimiter = ";" if ";" in text else ","
            value = [float(part) for part in text.split(delimiter)]
    array = np.asarray(value, dtype=float).reshape(-1)
    if len(array) < 2:
        raise BackendAttributionContractError("P0_GEOMETRY_XY_UNAVAILABLE")
    if not np.all(np.isfinite(array[:2])):
        raise BackendAttributionContractError("P0_GEOMETRY_XY_NONFINITE")
    return array[:2].astype(float)


def _get_measurement_column(runtime: pd.DataFrame, config: Mapping[str, Any]) -> str:
    declared = str(config.get("backend_authority", {}).get("measurement", ""))
    candidates = [declared, "range_meas_rt_fp_m", "measured_range_m", "range_m"]
    for column in candidates:
        if column and column in runtime.columns:
            return column
    raise BackendAttributionContractError("P0_MEASUREMENT_COLUMN_MISSING")


def _get_anchor_xy(row: Mapping[str, Any]) -> np.ndarray:
    if "anchor_pose_xyz" in row:
        return _parse_xy(row["anchor_pose_xyz"])
    if "anchor_x_m" in row and "anchor_y_m" in row:
        return np.array([float(row["anchor_x_m"]), float(row["anchor_y_m"])])
    raise BackendAttributionContractError("P0_ANCHOR_GEOMETRY_MISSING")


def _load_stage_authority(config: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    output = config.get("output_authority")
    if not isinstance(output, Mapping):
        raise BackendAttributionContractError("P0_OUTPUT_AUTHORITY_MISSING")
    model_root = _resolve_authority_root(
        str(output.get("model_root_prefix", "")),
        required_file="model_artifact_manifest.csv",
    )
    input_root = _resolve_authority_root(
        str(output.get("input_root_prefix", "")),
        required_file="runtime_link_table.parquet",
    )
    tables = {
        "MODEL_ARTIFACT_MANIFEST.csv": _read_table(model_root / "model_artifact_manifest.csv"),
        "runtime_link_table.parquet": _read_table(input_root / "runtime_link_table.parquet"),
        "density_prediction_table.parquet": _read_table(input_root / "density_prediction_table.parquet"),
        "arm_registry.csv": _read_table(input_root / "arm_registry.csv"),
        "evaluator_sidecar.parquet": _read_table(input_root / "evaluator_sidecar.parquet"),
        "odometry_runtime_table.csv": _read_table(input_root / "odometry_runtime_table.csv"),
    }
    optional = {
        "evaluator_oracle_sidecar.parquet": input_root / "evaluator_oracle_sidecar.parquet",
        "initial_pose_sidecar.parquet": input_root / "initial_pose_sidecar.parquet",
        "fault_assignment_table.parquet": input_root / "fault_assignment_table.parquet",
        "shuffle_assignment_table.parquet": input_root / "shuffle_assignment_table.parquet",
        "pairing_manifest.csv": input_root / "pairing_manifest.csv",
        "stage_arm_registry.csv": input_root / "stage_arm_registry.csv",
    }
    for name, path in optional.items():
        tables[name] = _read_table(path) if path.is_file() else pd.DataFrame()
    _require_columns(tables["runtime_link_table.parquet"], _LINK_KEY, "runtime_link_table")
    _require_columns(
        tables["density_prediction_table.parquet"],
        ("case_id", "evidence_source", "w", "sigma_c", "sigma_x", "mu_c", "mu_0"),
        "density_prediction_table",
    )
    _assert_runtime_truth_free(tables["runtime_link_table.parquet"])
    return tables


def _apply_smoke_caps(
    runtime: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    config: Mapping[str, Any],
) -> None:
    caps = (
        config.get("execution_caps", {}).get("smoke", {})
        if isinstance(config.get("execution_caps"), Mapping)
        else {}
    )
    is_v3 = config.get("schema_version") == _V3_SCHEMA_VERSION
    seeds = caps.get(
        "replay_seeds",
        config.get("seed_authority", {}).get("smoke_replay_seeds"),
    )
    schedules = (
        caps.get("regime_schedules")
        if is_v3
        else caps.get("schedules")
    )
    spaces = caps.get("spaces")
    max_steps = int(caps.get("max_steps_per_trajectory", caps.get("max_steps", 50)))
    mask = pd.Series(True, index=runtime.index)
    if is_v3:
        if not isinstance(schedules, list) or not schedules:
            raise BackendAttributionContractError(
                "P0_V3_SMOKE_SCHEDULES_MISSING"
            )
        randomized = caps.get("randomized_schedule_seeds")
        if not isinstance(randomized, list) or not randomized:
            raise BackendAttributionContractError(
                "P0_V3_SMOKE_RANDOMIZED_SEEDS_MISSING"
            )
        randomized_seeds = [int(seed) for seed in randomized]
        if len(set(randomized_seeds)) != len(randomized_seeds):
            raise BackendAttributionContractError(
                "P0_V3_SMOKE_RANDOMIZED_SEEDS_DUPLICATE"
            )
        deterministic = caps.get("deterministic_schedule_realizations", {})
        if not isinstance(deterministic, Mapping):
            raise BackendAttributionContractError(
                "P0_V3_SMOKE_DETERMINISTIC_REALIZATIONS_INVALID"
            )
        schedule_mask = pd.Series(False, index=runtime.index)
        for schedule in [str(item) for item in schedules]:
            if schedule in deterministic:
                if int(deterministic[schedule]) != 1:
                    raise BackendAttributionContractError(
                        "P0_V3_SMOKE_DETERMINISTIC_REALIZATIONS_INVALID:"
                        f"{schedule}"
                    )
                allowed_seeds = [0]
            else:
                allowed_seeds = randomized_seeds
            schedule_mask |= runtime["schedule_id"].astype(str).eq(
                schedule
            ) & runtime["replay_seed"].astype(int).isin(allowed_seeds)
        mask &= schedule_mask
    elif seeds:
        mask &= runtime["replay_seed"].astype(int).isin([int(seed) for seed in seeds])
    if schedules and not is_v3:
        mask &= runtime["schedule_id"].astype(str).isin([str(item) for item in schedules])
    if spaces and "space_id" in runtime.columns:
        mask &= runtime["space_id"].astype(str).isin([str(item) for item in spaces])
    rank_key = [*_TRAJ_KEY, "step_idx"] if is_v3 else ["trajectory_id", "step_idx"]
    rank_group = list(_TRAJ_KEY) if is_v3 else ["trajectory_id"]
    ranks = runtime.loc[mask, rank_key].drop_duplicates()
    ranks = ranks.sort_values(rank_key, kind="stable")
    ranks["_rank"] = ranks.groupby(rank_group).cumcount()
    allowed = ranks[ranks["_rank"] < max_steps].drop(columns="_rank")
    limited = runtime.loc[mask].merge(
        allowed,
        on=rank_key,
        how="inner",
        validate="many_to_one",
    )
    allowed_case = set(limited["case_id"].astype(str))
    allowed_step = set(map(tuple, limited.loc[:, list(_STEP_KEY)].drop_duplicates().to_numpy()))
    tables["runtime_link_table.parquet"] = limited.reset_index(drop=True)
    for name in (
        "density_prediction_table.parquet",
        "evaluator_oracle_sidecar.parquet",
        "fault_assignment_table.parquet",
        "shuffle_assignment_table.parquet",
    ):
        frame = tables.get(name, pd.DataFrame())
        if not frame.empty and "case_id" in frame.columns:
            if is_v3 and set(_LINK_KEY).issubset(frame.columns):
                allowed_link = limited.loc[
                    :, list(_LINK_KEY)
                ].drop_duplicates()
                tables[name] = frame.merge(
                    allowed_link,
                    on=list(_LINK_KEY),
                    how="inner",
                    validate="many_to_one",
                ).reset_index(drop=True)
            else:
                tables[name] = frame[
                    frame["case_id"].astype(str).isin(allowed_case)
                ].reset_index(drop=True)
    evaluator = tables["evaluator_sidecar.parquet"]
    if not evaluator.empty:
        step_mask = evaluator.loc[:, list(_STEP_KEY)].apply(tuple, axis=1).isin(allowed_step)
        tables["evaluator_sidecar.parquet"] = evaluator.loc[step_mask].reset_index(drop=True)


def _normal_evidence_name(value: Any) -> str:
    text = str(value)
    mapping = {
        "cp_compact_3f": "E_CP_MDN",
        "cir_shape_6f": "E_CIR_MDN",
        "none": "E_FIXED",
        "fixed": "E_FIXED",
        "oracle": "E_ORACLE",
        "E_CP_SHUFFLED": "E_CP_SHUFFLE_GLOBAL",
        "E_SHUFFLED_CP": "E_CP_SHUFFLE_GLOBAL",
        "E_CP_SHUFFLE_GLOBAL": "E_CP_SHUFFLE_GLOBAL",
        "E_CP_SHUFFLE_MATCHED": "E_CP_SHUFFLE_MATCHED",
        "cp_shuffle_global": "E_CP_SHUFFLE_GLOBAL",
        "cp_shuffle_matched": "E_CP_SHUFFLE_MATCHED",
        "SHUFFLE_GLOBAL": "E_CP_SHUFFLE_GLOBAL",
        "SHUFFLE_MATCHED": "E_CP_SHUFFLE_MATCHED",
    }
    return mapping.get(text, text)


def _consumer_name(value: Any) -> str:
    text = str(value)
    mapping = {
        "mixture_preserving_gsf": "PERSISTENT_GSF",
        "moment_matched_gaussian": "MM_BEFORE_UPDATE",
        "single_gaussian": "MM_BEFORE_UPDATE",
        "branch_then_merge": "BRANCH_THEN_MERGE",
        "hard_gate": "HARD_GATE",
        "scalar_zero_mean": "SCALAR_ZERO_MEAN",
    }
    return mapping.get(text, text)


def _require_gsf_cap(caps: Mapping[str, Any], key: str) -> Any:
    if key not in caps:
        raise BackendAttributionContractError(
            f"P0_CAPACITY_CLOSURE_MISSING:backend_authority.gsf_caps.{key}"
        )
    return caps[key]


def _default_mixture(config: Mapping[str, Any]) -> TwoComponentMixture:
    recipe = config.get("model_authority", {}).get("shared_mdn_recipe", {})
    return TwoComponentMixture(
        w=np.array([float(config.get("backend_authority", {}).get("fixed_w", 0.0))]),
        sigma_c=np.array([float(config.get("backend_authority", {}).get("fixed_sigma_c_m", 1.0))]),
        sigma_x=np.array([float(config.get("backend_authority", {}).get("default_range_sigma_m", 1.0))]),
        mu_c=np.array([float(recipe.get("mu_c", 0.0))]),
        mu_0=np.array([float(recipe.get("mu_0", 0.0))]),
    )


def _row_mixture(row: pd.Series) -> TwoComponentMixture:
    return TwoComponentMixture(
        w=np.array([float(row["w"])]),
        sigma_c=np.array([float(row["sigma_c"])]),
        sigma_x=np.array([float(row["sigma_x"])]),
        mu_c=np.array([float(row["mu_c"])]),
        mu_0=np.array([float(row["mu_0"])]),
    )


def _density_key_from_row(
    row: Mapping[str, Any],
    evidence: str,
    lane_id: Any | None = None,
) -> tuple[str, ...]:
    if all(column in row for column in _LINK_KEY):
        link_key = tuple(str(row[column]) for column in _LINK_KEY)
        if lane_id is not None:
            return (str(lane_id),) + link_key + (str(evidence),)
        return link_key + (str(evidence),)
    return (str(row["case_id"]), str(evidence))


def _density_lookup(density: pd.DataFrame) -> dict[tuple[str, ...], pd.Series]:
    frame = density.copy()
    frame["evidence_norm"] = frame["evidence_source"].map(_normal_evidence_name)
    key_columns = (
        (["lane_id"] if "lane_id" in frame.columns else [])
        + [column for column in _LINK_KEY if column in frame.columns]
        + ["evidence_norm"]
    )
    if "case_id" not in key_columns:
        key_columns = ["case_id", "evidence_norm"]
    if frame.duplicated(key_columns).any():
        raise BackendAttributionContractError(f"P0_DENSITY_DUPLICATE_KEY:{key_columns}")
    lookup = {
        tuple(str(getattr(row, column)) for column in key_columns): row
        for row in frame.itertuples(index=False)
    }
    legacy_key = ["case_id", "evidence_norm"]
    if not frame.duplicated(legacy_key).any():
        lookup.update({
            tuple(str(getattr(row, column)) for column in legacy_key): row
            for row in frame.itertuples(index=False)
        })
    return lookup


def _oracle_lookup(oracle: pd.DataFrame) -> dict[tuple[str, ...], str]:
    if oracle.empty:
        return {}
    _require_columns(oracle, (*_LINK_KEY, "oracle_component"), "evaluator_oracle_sidecar")
    if oracle.duplicated(list(_LINK_KEY)).any():
        raise BackendAttributionContractError("P0_ORACLE_DUPLICATE_LINK_KEY")
    return {
        tuple(str(getattr(row, column)) for column in _LINK_KEY): str(row.oracle_component)
        for row in oracle.itertuples(index=False)
    }


def _hybrid_mask_value(value: Any) -> dict[str, bool] | None:
    text = str(value)
    if not text or text.lower() in {"none", "nan"}:
        return None
    if text.startswith("{"):
        raw = json.loads(text)
        return {group: bool(raw.get(group, False)) for group in _HYBRID_GROUPS}
    bits = text.replace("mask", "").replace("_", "")
    if len(bits) == 3 and set(bits).issubset({"0", "1"}):
        return {group: bits[index] == "1" for index, group in enumerate(_HYBRID_GROUPS)}
    return None


def _source_key_from_shuffle_row(row: Mapping[str, Any]) -> tuple[str, ...] | None:
    prefixed = [f"source_{column}" for column in _LINK_KEY]
    shuffle_prefixed = [f"shuffle_source_{column}" for column in _LINK_KEY]
    for columns in (prefixed, shuffle_prefixed):
        if all(column in row and pd.notna(row[column]) for column in columns):
            return tuple(str(row[column]) for column in columns)
    if "source_case_id" in row and pd.notna(row["source_case_id"]):
        return (str(row["source_case_id"]),)
    if "shuffle_source_case_id" in row and pd.notna(row["shuffle_source_case_id"]):
        return (str(row["shuffle_source_case_id"]),)
    return None


def _generate_shuffle_mapping(
    runtime: pd.DataFrame,
    *,
    mode: str,
    seed: int,
) -> dict[tuple[str, ...], tuple[str, ...]]:
    rng = np.random.default_rng(seed)
    rows = runtime.loc[:, list(_LINK_KEY)].astype(str).to_dict("records")
    if mode == "E_CP_SHUFFLE_MATCHED":
        groups: dict[tuple[str, ...], list[int]] = {}
        for index, row in enumerate(rows):
            key = (row["trajectory_id"], row["schedule_id"], row["replay_seed"], row["step_idx"], row["condition_id"])
            groups.setdefault(key, []).append(index)
    else:
        groups = {("GLOBAL",): list(range(len(rows)))}
    mapping: dict[tuple[str, ...], tuple[str, ...]] = {}
    for indexes in groups.values():
        if len(indexes) < 2:
            raise BackendAttributionContractError("P0_SHUFFLE_ALIGNMENT_GROUP_LT2")
        index_array = np.asarray(indexes)
        for _ in range(128):
            permuted = rng.permutation(index_array)
            if not np.any(permuted == index_array):
                break
        else:
            permuted = np.roll(index_array, 1)
            if np.any(permuted == index_array):
                raise BackendAttributionContractError("P0_SHUFFLE_ALIGNMENT_FIXED_POINT")
        for target_index, source_index in zip(index_array, permuted):
            target = tuple(rows[int(target_index)][column] for column in _LINK_KEY)
            source = tuple(rows[int(source_index)][column] for column in _LINK_KEY)
            if target == source:
                raise BackendAttributionContractError("P0_SHUFFLE_ALIGNMENT_FIXED_POINT")
            mapping[target] = source
    return mapping


def _shuffle_lookup(
    runtime: pd.DataFrame,
    sidecar: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[dict[str, dict[tuple[str, ...], tuple[str, ...]]], pd.DataFrame]:
    modes = ("E_CP_SHUFFLE_GLOBAL", "E_CP_SHUFFLE_MATCHED")
    out: dict[str, dict[tuple[str, ...], tuple[str, ...]]] = {}
    records: list[dict[str, Any]] = []
    if not sidecar.empty and set(_LINK_KEY).issubset(sidecar.columns):
        for raw_id, group in sidecar.groupby("shuffle_id", sort=True) if "shuffle_id" in sidecar.columns else [("E_CP_SHUFFLE_GLOBAL", sidecar)]:
            if str(raw_id).lower() in {"shuffle_none", "none", "nan", ""}:
                continue
            shuffle_id = _normal_evidence_name(raw_id)
            if shuffle_id not in modes:
                shuffle_id = "E_CP_SHUFFLE_GLOBAL"
            mapping: dict[tuple[str, ...], tuple[str, ...]] = {}
            for row in group.to_dict("records"):
                target = tuple(str(row[column]) for column in _LINK_KEY)
                source = _source_key_from_shuffle_row(row)
                if source is None:
                    continue
                if len(source) == 1:
                    source_row = runtime[runtime["case_id"].astype(str).eq(source[0])]
                    if len(source_row) != 1:
                        raise BackendAttributionContractError(f"P0_SHUFFLE_SOURCE_CASE_AMBIGUOUS:{source[0]}")
                    source = tuple(str(source_row.iloc[0][column]) for column in _LINK_KEY)
                if target == source:
                    raise BackendAttributionContractError("P0_SHUFFLE_ALIGNMENT_FIXED_POINT")
                mapping[target] = source
                records.append({"shuffle_id": shuffle_id, **{column: target[index] for index, column in enumerate(_LINK_KEY)}, **{f"source_{column}": source[index] for index, column in enumerate(_LINK_KEY)}})
            if mapping:
                out[shuffle_id] = mapping
    seed = int(config.get("seed_authority", {}).get("schedule_seed", 2026072821))
    for mode in modes:
        if mode not in out:
            mapping = _generate_shuffle_mapping(runtime, mode=mode, seed=seed + (0 if mode.endswith("GLOBAL") else 1))
            out[mode] = mapping
            for target, source in mapping.items():
                records.append({"shuffle_id": mode, **{column: target[index] for index, column in enumerate(_LINK_KEY)}, **{f"source_{column}": source[index] for index, column in enumerate(_LINK_KEY)}})
    return out, pd.DataFrame(records)


def _mixture_for_arm_case(
    arm: Mapping[str, Any],
    row: Mapping[str, Any],
    density_by_case: Mapping[tuple[str, ...], pd.Series],
    oracle_by_case: Mapping[tuple[str, ...], str],
    shuffle_by_mode: Mapping[str, Mapping[tuple[str, ...], tuple[str, ...]]],
    config: Mapping[str, Any],
) -> TwoComponentMixture:
    evidence = _normal_evidence_name(arm.get("evidence_source", arm.get("feature_source", "E_FIXED")))
    case_id = str(row["case_id"])
    if evidence == "E_FIXED":
        return _default_mixture(config)
    if evidence in {"E_CP_MDN", "E_CIR_MDN"}:
        key = _density_key_from_row(row, evidence, arm.get("lane_id"))
        if key not in density_by_case:
            key = _density_key_from_row(row, evidence)
        if key not in density_by_case:
            key = (case_id, evidence)
        if key not in density_by_case:
            raise BackendAttributionContractError(f"P0_DENSITY_MISSING:{key}")
        return _row_mixture(pd.Series(density_by_case[key]._asdict() if hasattr(density_by_case[key], "_asdict") else density_by_case[key]))
    if evidence in {"E_CP_SHUFFLE_GLOBAL", "E_CP_SHUFFLE_MATCHED"}:
        target = tuple(str(row[column]) for column in _LINK_KEY)
        source = shuffle_by_mode.get(evidence, {}).get(target)
        if source is None:
            raise BackendAttributionContractError(f"P0_SHUFFLE_ASSIGNMENT_MISSING:{evidence}:{target}")
        lane_id = arm.get("lane_id")
        key = ((str(lane_id),) if lane_id is not None else ()) + tuple(source) + ("E_CP_MDN",)
        if key not in density_by_case:
            key = tuple(source) + ("E_CP_MDN",)
        if key not in density_by_case:
            raise BackendAttributionContractError(f"P0_SHUFFLE_DENSITY_MISSING:{key}")
        return _row_mixture(pd.Series(density_by_case[key]._asdict() if hasattr(density_by_case[key], "_asdict") else density_by_case[key]))
    if evidence == "E_ORACLE":
        oracle_key = tuple(str(row[column]) for column in _LINK_KEY)
        component = oracle_by_case.get(oracle_key)
        if component is None:
            raise BackendAttributionContractError(f"P0_ORACLE_MISSING:{oracle_key}")
        base = _default_mixture(config)
        contaminated = "contaminated" in component.lower() or component.lower() in {"c", "1"}
        return TwoComponentMixture(
            w=np.array([1.0 if contaminated else 0.0]),
            sigma_c=base.sigma_c,
            sigma_x=base.sigma_x,
            mu_c=base.mu_c,
            mu_0=base.mu_0,
        )
    raise BackendAttributionContractError(f"P0_UNKNOWN_EVIDENCE_SOURCE:{evidence}")


def _state_from_initial_pose(initial: pd.DataFrame, config: Mapping[str, Any]) -> dict[tuple[Any, Any, Any], PersistentGSFState]:
    if initial.empty:
        raise BackendAttributionContractError("P0_INITIAL_STATE_MISSING")
    x_col = "initial_x_m" if "initial_x_m" in initial.columns else "x_m"
    y_col = "initial_y_m" if "initial_y_m" in initial.columns else "y_m"
    if x_col not in initial.columns or y_col not in initial.columns:
        if "truth_x_m" in initial.columns or "truth_y_m" in initial.columns:
            raise BackendAttributionContractError("P0_INITIAL_STATE_TRUTH_ONLY")
        raise BackendAttributionContractError("P0_INITIAL_STATE_COLUMNS_MISSING")
    _require_columns(initial, (*_TRAJ_KEY, x_col, y_col), "initial_pose_sidecar")
    variance = float(config.get("backend_authority", {}).get("initial_variance_m2", 1.0))
    if not np.isfinite(variance) or variance <= 0.0:
        raise BackendAttributionContractError("P0_INITIAL_VARIANCE_INVALID")
    states = {}
    for row in initial.itertuples(index=False):
        key = (row.trajectory_id, row.schedule_id, int(row.replay_seed))
        states[key] = make_persistent_gsf_state(
            [1.0],
            [[float(getattr(row, x_col)), float(getattr(row, y_col))]],
            [variance * np.eye(2)],
            component_prefix="c",
        )
    return states


def _odometry_lookup(odometry: pd.DataFrame) -> dict[tuple[Any, Any, Any, int], np.ndarray]:
    if odometry.empty:
        return {}
    traj_cols = [column for column in _TRAJ_KEY if column in odometry.columns]
    target_col = "target_step_idx" if "target_step_idx" in odometry.columns else "to_step_idx" if "to_step_idx" in odometry.columns else "step_idx"
    dx_col = "dx_m" if "dx_m" in odometry.columns else "odom_dx_m"
    dy_col = "dy_m" if "dy_m" in odometry.columns else "odom_dy_m"
    _require_columns(odometry, (*traj_cols, target_col, dx_col, dy_col), "odometry_runtime_table")
    lookup = {}
    for row in odometry.itertuples(index=False):
        if len(traj_cols) == 3:
            key = (getattr(row, "trajectory_id"), getattr(row, "schedule_id"), int(getattr(row, "replay_seed")), int(getattr(row, target_col)))
        else:
            key = (getattr(row, "trajectory_id"), None, None, int(getattr(row, target_col)))
        lookup[key] = np.array([float(getattr(row, dx_col)), float(getattr(row, dy_col))])
    return lookup


def _odometry_for(
    lookup: Mapping[tuple[Any, Any, Any, int], np.ndarray],
    trajectory_id: Any,
    schedule_id: Any,
    replay_seed: Any,
    step_idx: int,
) -> np.ndarray:
    exact = (trajectory_id, schedule_id, int(replay_seed), int(step_idx))
    fallback = (trajectory_id, None, None, int(step_idx))
    return np.array(lookup.get(exact, lookup.get(fallback, np.zeros(2))), dtype=float)


def _apply_fault_if_needed(
    runtime: pd.DataFrame,
    arm: Mapping[str, Any],
    config: Mapping[str, Any],
    frozen_density: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fault_id = str(arm.get("fault_id", "none")).lower()
    if fault_id.startswith("fault_"):
        fault_id = fault_id.removeprefix("fault_")
    fault_id = fault_id.replace("-", "_")
    if fault_id in {"", "none", "nan"}:
        return runtime, pd.DataFrame()
    prediction_columns = [column for column in ("case_id", "evidence_source", "w", "sigma_c", "sigma_x", "mu_c", "mu_0", "prediction_hash") if column in frozen_density.columns]
    freeze = p2_backend_faults.freeze_prediction_table(frozen_density, prediction_columns)
    row_key = "case_id"
    seed = int(config.get("fault_authority", {}).get("assignment_seed", config.get("seed_authority", {}).get("dropout_seed", 2026072823)))
    fraction = float(config.get("fault_authority", {}).get("fraction", 0.5))
    assignment = p2_backend_faults.deterministic_fault_assignment(
        runtime,
        row_key_column=row_key,
        fraction=fraction,
        seed=seed,
        salt=fault_id,
    )
    candidate_mask = assignment.mask.copy()
    fault_metadata: dict[str, Any] = {}
    measurement = _get_measurement_column(runtime, config)
    if fault_id in {"range_bias", "range_bias_drift"}:
        biased = p2_backend_faults.inject_range_bias(
            runtime,
            assignment,
            range_column=measurement,
            bias_m=float(config.get("fault_authority", {}).get("range_bias_m", 0.25)),
        )
    elif fault_id == "anchor_dropout":
        biased = p2_backend_faults.apply_anchor_dropout(runtime, assignment)
    elif fault_id in {"anchor_offset", "backend_anchor_offset"}:
        biased = p2_backend_faults.apply_backend_anchor_offset(
            runtime,
            assignment,
            x_column="anchor_x_m",
            y_column="anchor_y_m",
            offset_xy_m=tuple(config.get("fault_authority", {}).get("anchor_offset_xy_m", (0.25, 0.0))),
        )
    elif fault_id in {"timestamp", "timestamp_corruption"}:
        packet_columns = tuple(config.get("fault_authority", {}).get("timestamp_packet_columns", ()))
        time_column = str(config.get("fault_authority", {}).get("timestamp_time_column", "step_idx"))
        group_columns = tuple(
            config.get("fault_authority", {}).get(
                "timestamp_group_columns",
                ("trajectory_id", "schedule_id", "replay_seed", "anchor_id"),
            )
        )
        shift_steps = int(config.get("fault_authority", {}).get("timestamp_shift_steps", 0))
        target = str(config.get("fault_authority", {}).get("timestamp_target", "whole_measurement_packet"))
        if not packet_columns or shift_steps == 0:
            raise BackendAttributionContractError("P0_TIMESTAMP_FAULT_SEMANTICS_MISSING")
        required_columns = [*group_columns, time_column, *packet_columns]
        missing_columns = [column for column in required_columns if column not in runtime.columns]
        if missing_columns:
            raise BackendAttributionContractError(
                f"P0_TIMESTAMP_FAULT_COLUMNS_MISSING:{missing_columns}"
            )
        available_source = {
            tuple(str(row[column]) for column in group_columns)
            + (int(row[time_column]),)
            for row in runtime.to_dict("records")
        }
        source_available = np.asarray(
            [
                tuple(str(row[column]) for column in group_columns)
                + (int(row[time_column]) + shift_steps,)
                in available_source
                for row in runtime.to_dict("records")
            ],
            dtype=bool,
        )
        restricted_mask = assignment.mask & source_available
        valid_target = (
            target
            if target in {"range_only", "anchor_pose_only", "whole_measurement_packet"}
            else "whole_measurement_packet"
        )
        fault_metadata = {
            "timestamp_shift_steps": shift_steps,
            "timestamp_target": valid_target,
            "timestamp_boundary_excluded": candidate_mask & ~source_available,
        }
        digest_payload = {
            "row_key_column": row_key,
            "row_keys": runtime[row_key].astype(str).tolist(),
            "mask": restricted_mask.astype(int).tolist(),
            "salt": fault_id,
            "boundary_rule": "source_packet_required",
        }
        assignment = p2_backend_faults.FaultAssignment(
            row_key_column=row_key,
            mask=restricted_mask,
            digest=hashlib.sha256(
                json.dumps(
                    digest_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            salt=fault_id,
        )
        biased = p2_backend_faults.shift_timestamp_packets(
            runtime,
            shift_steps=shift_steps,
            target=valid_target,
            time_column=time_column,
            packet_columns=packet_columns,
            group_columns=group_columns,
            required_mask=assignment.mask,
        )
    else:
        raise BackendAttributionContractError(f"P0_FAULT_UNSUPPORTED:{fault_id}")
    p2_backend_faults.assert_evidence_freeze_unchanged(freeze, frozen_density)
    assignment_frame = runtime.loc[:, list(_LINK_KEY)].copy()
    assignment_frame["prediction_hash_pre_fault"] = freeze.digest
    assignment_frame["prediction_hash_post_fault"] = freeze.digest
    assignment_frame["fault_id"] = fault_id
    assignment_frame["fault_seed"] = seed
    assignment_frame["fault_candidate_selected"] = candidate_mask
    assignment_frame["fault_selected"] = assignment.mask
    assignment_frame["fault_assignment_hash"] = assignment.digest
    for column, value in fault_metadata.items():
        assignment_frame[column] = value
    return biased, assignment_frame


def _arm_registry_for_stage(
    sidecar_registry: pd.DataFrame,
    stage: str,
) -> pd.DataFrame:
    if sidecar_registry.empty:
        raise BackendAttributionContractError("P0_ARM_REGISTRY_MISSING")
    frame = sidecar_registry.copy()
    rename = {"id": "arm_id", "feature_source": "evidence_source"}
    frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
    if "arm_id" not in frame.columns:
        raise BackendAttributionContractError("P0_ARM_REGISTRY_NO_ARM_ID")
    for column, default in {
        "lane_id": "R",
        "evidence_source": "E_FIXED",
        "consumer_id": "PERSISTENT_GSF",
        "fault_id": "none",
        "shuffle_id": "none",
        "hybrid_mask": "none",
        "evidence_contract": "density_prior",
        "runtime_truth_allowed": False,
        "primary_or_secondary": "primary",
    }.items():
        if column not in frame.columns:
            frame[column] = default
    frame["evidence_source"] = frame["evidence_source"].map(_normal_evidence_name)
    frame["consumer_id"] = frame["consumer_id"].map(_consumer_name)
    if frame["runtime_truth_allowed"].astype(str).str.lower().isin({"true", "1"}).any():
        raise BackendAttributionContractError("P0_RUNTIME_TRUTH_ARM_DECLARED")
    if stage == "smoke":
        return frame.reset_index(drop=True)
    if stage == "full":
        return frame.reset_index(drop=True)
    if stage in {"B1", "B2", "B3", "B4"}:
        if "stage_id" not in frame.columns:
            raise BackendAttributionContractError("P0_STAGE_ARM_REGISTRY_MISSING")
        selected = frame[frame["stage_id"].astype(str).eq(stage)].copy()
        if selected.empty:
            raise BackendAttributionContractError(f"P0_STAGE_ARM_REGISTRY_EMPTY:{stage}")
        return selected.reset_index(drop=True)
    raise BackendAttributionContractError(f"P0_STAGE_UNSUPPORTED:{stage}")


def _evaluate_step_metrics(
    state: PersistentGSFState,
    evaluator_step: Mapping[str, Any] | None,
) -> dict[str, Any]:
    mean, cov = state.moment_match()
    out: dict[str, Any] = {
        "posterior_mean_x_m": float(mean[0]),
        "posterior_mean_y_m": float(mean[1]),
        "cov_xx": float(cov[0, 0]),
        "cov_xy": float(cov[0, 1]),
        "cov_yy": float(cov[1, 1]),
        "active_component_count": state.active_component_count,
        "discarded_mass": float(state.discarded_mass),
        "diverged": False,
    }
    if evaluator_step and {"truth_x_m", "truth_y_m"}.issubset(evaluator_step):
        truth = np.array([float(evaluator_step["truth_x_m"]), float(evaluator_step["truth_y_m"])])
        out["pose_error_m"] = float(np.linalg.norm(mean - truth))
        out["mixture_state_nll"] = state.mixture_nll(truth)
        out["state_nll"] = out["mixture_state_nll"]
        out["coverage_95"] = bool((mean - truth) @ np.linalg.pinv(cov) @ (mean - truth) <= 5.991464547)
    else:
        out["pose_error_m"] = np.nan
        out["mixture_state_nll"] = np.nan
        out["state_nll"] = np.nan
        out["coverage_95"] = False
    return out


def _v3_capacity_selection(
    stage: str,
    config: Mapping[str, Any],
) -> dict[str, Any] | None:
    if config.get("schema_version") != _V3_SCHEMA_VERSION or stage not in {
        "smoke",
        "full",
    }:
        return None
    candidates: list[tuple[str, Mapping[str, Any]]] = []
    for namespace in ("selected_capacity", "capacity_selection"):
        value = config.get(namespace)
        if isinstance(value, Mapping):
            candidates.append((namespace, value))
    if not candidates:
        raise BackendAttributionContractError(
            "P0_V3_CAPACITY_SELECTION_MISSING:"
            "selected_capacity_or_capacity_selection"
        )

    resolved: list[tuple[str, dict[str, Any]]] = []
    for namespace, value in candidates:
        missing = [
            key
            for key in ("selected_k", "reference_k", "population_scope_id")
            if key not in value
        ]
        if missing:
            raise BackendAttributionContractError(
                f"P0_V3_CAPACITY_SELECTION_INCOMPLETE:{namespace}:{missing}"
            )
        try:
            selected_k = int(value["selected_k"])
            reference_k = int(value["reference_k"])
        except (TypeError, ValueError) as error:
            raise BackendAttributionContractError(
                f"P0_V3_CAPACITY_SELECTION_INVALID:{namespace}"
            ) from error
        population_scope_id = str(value["population_scope_id"]).strip()
        if (
            selected_k < 1
            or reference_k < selected_k
            or not population_scope_id
        ):
            raise BackendAttributionContractError(
                f"P0_V3_CAPACITY_SELECTION_INVALID:{namespace}"
            )
        resolved.append(
            (
                namespace,
                {
                    "capacity_selected_k": selected_k,
                    "capacity_reference_k": reference_k,
                    "population_scope_id": population_scope_id,
                },
            )
        )
    authority = resolved[0][1]
    if any(value != authority for _, value in resolved[1:]):
        raise BackendAttributionContractError(
            "P0_V3_CAPACITY_SELECTION_NAMESPACE_CONFLICT"
        )
    caps = config.get("backend_authority", {}).get("gsf_caps", {})
    configured_k = (
        caps.get("max_posterior_components")
        if isinstance(caps, Mapping)
        else None
    )
    if configured_k is None or int(configured_k) != authority["capacity_selected_k"]:
        raise BackendAttributionContractError(
            "P0_V3_SELECTED_K_CONFIG_MISMATCH:"
            f"selected={authority['capacity_selected_k']}:configured={configured_k}"
        )
    return authority


def _v3_realization_authority(runtime: pd.DataFrame) -> pd.DataFrame:
    required = {*_TRAJ_KEY, "space_id", "stochastic_realization_hash"}
    missing = sorted(required - set(runtime.columns))
    if missing:
        raise BackendAttributionContractError(
            f"P0_V3_REALIZATION_AUTHORITY_MISSING:{missing}"
        )
    rows = runtime.loc[
        :,
        [
            "space_id",
            *_TRAJ_KEY,
            "stochastic_realization_hash",
            *(
                ["realization_duplicate_status"]
                if "realization_duplicate_status" in runtime.columns
                else []
            ),
        ],
    ].copy()
    rows["stochastic_realization_hash"] = (
        rows["stochastic_realization_hash"].astype(str).str.strip()
    )
    if rows["stochastic_realization_hash"].isin({"", "nan", "None"}).any():
        raise BackendAttributionContractError(
            "P0_V3_REALIZATION_HASH_EMPTY"
        )
    trajectory_counts = rows.groupby(
        list(_TRAJ_KEY), sort=False
    )["stochastic_realization_hash"].nunique()
    if int(trajectory_counts.max()) != 1:
        raise BackendAttributionContractError(
            "P0_V3_REALIZATION_HASH_NOT_UNIQUE_PER_TRAJECTORY"
        )
    space_counts = rows.groupby(list(_TRAJ_KEY), sort=False)["space_id"].nunique()
    if int(space_counts.max()) != 1:
        raise BackendAttributionContractError(
            "P0_V3_REALIZATION_SPACE_NOT_UNIQUE_PER_TRAJECTORY"
        )

    realizations = rows.loc[
        :,
        ["space_id", *_TRAJ_KEY, "stochastic_realization_hash"],
    ].drop_duplicates()
    realizations = realizations.sort_values(
        ["space_id", "trajectory_id", "schedule_id", "replay_seed"],
        kind="stable",
    ).reset_index(drop=True)
    duplicate = realizations.duplicated(
        [
            "space_id",
            "trajectory_id",
            "schedule_id",
            "stochastic_realization_hash",
        ],
        keep="first",
    )
    realizations["realization_duplicate_status"] = np.where(
        duplicate,
        "DUPLICATE_REALIZATION",
        "CANONICAL_REALIZATION",
    )

    if "realization_duplicate_status" in rows.columns:
        declared = rows.loc[
            :, [*_TRAJ_KEY, "realization_duplicate_status"]
        ].copy()
        declared["realization_duplicate_status"] = (
            declared["realization_duplicate_status"].astype(str).str.strip()
        )
        if (
            declared.groupby(list(_TRAJ_KEY), sort=False)[
                "realization_duplicate_status"
            ].nunique().max()
            != 1
        ):
            raise BackendAttributionContractError(
                "P0_V3_REALIZATION_DUPLICATE_STATUS_NOT_UNIQUE"
            )
        declared = declared.drop_duplicates(list(_TRAJ_KEY))
        checked = realizations.merge(
            declared,
            on=list(_TRAJ_KEY),
            how="left",
            validate="one_to_one",
            suffixes=("_expected", "_declared"),
        )
        mismatch = checked[
            "realization_duplicate_status_expected"
        ].ne(checked["realization_duplicate_status_declared"])
        if bool(mismatch.any()):
            raise BackendAttributionContractError(
                "P0_V3_REALIZATION_DUPLICATE_STATUS_MISMATCH"
            )
    return realizations.loc[
        :, [*_TRAJ_KEY, *_V3_REALIZATION_COLUMNS]
    ].reset_index(drop=True)


def _attach_v3_output_columns(
    frame: pd.DataFrame,
    *,
    table_name: str,
    realization_authority: pd.DataFrame,
    selection: Mapping[str, Any],
) -> pd.DataFrame:
    out = frame.copy()
    if out.empty:
        for column in (*_V3_REALIZATION_COLUMNS, *_V3_SELECTION_OUTPUT_COLUMNS):
            if column not in out.columns:
                out[column] = pd.Series(dtype="object")
        return out
    missing_key = sorted(set(_TRAJ_KEY) - set(out.columns))
    if missing_key:
        raise BackendAttributionContractError(
            f"P0_V3_OUTPUT_KEY_MISSING:{table_name}:{missing_key}"
        )

    row_order = "__v3_output_row_order"
    while row_order in out.columns:
        row_order = f"_{row_order}"
    out[row_order] = np.arange(len(out), dtype=np.int64)
    expected = realization_authority.rename(
        columns={
            column: f"__expected_{column}"
            for column in _V3_REALIZATION_COLUMNS
        }
    )
    join_columns: list[str] = []
    for index, column in enumerate(_TRAJ_KEY):
        join_column = f"__v3_join_key_{index}"
        while join_column in out.columns or join_column in expected.columns:
            join_column = f"_{join_column}"
        out[join_column] = out[column].astype(str)
        expected[join_column] = expected[column].astype(str)
        join_columns.append(join_column)
    expected = expected.drop(columns=list(_TRAJ_KEY))
    out = out.merge(
        expected,
        on=join_columns,
        how="left",
        sort=False,
        validate="many_to_one",
    )
    for column in _V3_REALIZATION_COLUMNS:
        expected_column = f"__expected_{column}"
        if out[expected_column].isna().any():
            raise BackendAttributionContractError(
                f"P0_V3_OUTPUT_REALIZATION_UNRESOLVED:{table_name}:{column}"
            )
        if column in out.columns:
            mismatch = out[column].astype(str).ne(
                out[expected_column].astype(str)
            )
            if bool(mismatch.any()):
                raise BackendAttributionContractError(
                    f"P0_V3_OUTPUT_METADATA_MISMATCH:{table_name}:{column}"
                )
        out[column] = out[expected_column]
        out = out.drop(columns=expected_column)
    for column in _V3_SELECTION_OUTPUT_COLUMNS:
        expected_value = selection[column]
        if column in out.columns:
            if column in {"capacity_selected_k", "capacity_reference_k"}:
                numeric = pd.to_numeric(out[column], errors="coerce")
                mismatch = numeric.isna() | numeric.ne(int(expected_value))
            else:
                mismatch = out[column].astype(str).ne(str(expected_value))
            if bool(mismatch.any()):
                raise BackendAttributionContractError(
                    f"P0_V3_OUTPUT_METADATA_MISMATCH:{table_name}:{column}"
                )
        out[column] = expected_value
    return out.sort_values(row_order, kind="stable").drop(
        columns=[row_order, *join_columns]
    ).reset_index(drop=True)


def _finalize_v3_stage_outputs(
    frames: dict[str, pd.DataFrame],
    *,
    selection: Mapping[str, Any] | None,
    realization_authority: pd.DataFrame | None,
) -> dict[str, pd.DataFrame]:
    if selection is None:
        return frames
    if realization_authority is None:
        raise BackendAttributionContractError(
            "P0_V3_REALIZATION_AUTHORITY_NOT_RESOLVED"
        )
    for name in (
        "runtime_link_table.parquet",
        "evaluator_sidecar.parquet",
        "density_prediction_table.parquet",
        "posterior_component_table.parquet",
        "trajectory_step_posterior_metrics.parquet",
        "fault_assignment_table.parquet",
        "shuffle_assignment_table.parquet",
    ):
        if name in frames:
            frames[name] = _attach_v3_output_columns(
                frames[name],
                table_name=name,
                realization_authority=realization_authority,
                selection=selection,
            )
    return frames


def _resolve_backend_workers(workers: int | None) -> int:
    raw: Any = (
        os.environ.get("RT_CP_UWB_BACKEND_WORKERS", "1")
        if workers is None
        else workers
    )
    try:
        resolved = int(raw)
    except (TypeError, ValueError) as error:
        raise BackendAttributionContractError(
            f"P0_PARALLEL_WORKERS_INVALID:{raw!r}"
        ) from error
    if resolved < 1:
        raise BackendAttributionContractError(
            f"P0_PARALLEL_WORKERS_INVALID:{resolved}"
        )
    return resolved


def _initialize_backend_worker() -> None:
    """Pin each backend worker to one native numerical-library thread."""

    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "1"
    try:
        from threadpoolctl import threadpool_limits
    except ImportError as error:  # pragma: no cover - production dependency
        raise RuntimeError("P0_THREADPOOLCTL_MISSING") from error
    global _BACKEND_WORKER_THREADPOOL_CONTROLLER
    _BACKEND_WORKER_THREADPOOL_CONTROLLER = threadpool_limits(limits=1)


def _contiguous_partitions(
    values: Sequence[tuple[Any, ...]],
    count: int,
) -> list[tuple[tuple[Any, ...], ...]]:
    """Split an already sorted sequence without changing its concatenation order."""

    if count < 1:
        raise ValueError("count must be positive")
    if not values:
        return []
    partition_count = min(count, len(values))
    quotient, remainder = divmod(len(values), partition_count)
    out: list[tuple[tuple[Any, ...], ...]] = []
    start = 0
    for index in range(partition_count):
        width = quotient + (1 if index < remainder else 0)
        stop = start + width
        out.append(tuple(values[start:stop]))
        start = stop
    return out


def _declared_stage_for_arm(config: Mapping[str, Any], arm_id: str) -> str:
    registry = config.get("stage_arm_registry", {})
    if isinstance(registry, Mapping):
        for stage_id in ("B1", "B2", "B3", "B4"):
            rows = registry.get(stage_id, [])
            if isinstance(rows, Sequence) and any(
                isinstance(row, Mapping) and str(row.get("arm_id")) == arm_id
                for row in rows
            ):
                return stage_id
    return ""


def _parallel_stage_partition(
    payload: tuple[
        str,
        Mapping[str, Any],
        str,
        tuple[tuple[Any, ...], ...],
    ],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    stage, config, run_root, trajectory_keys = payload
    frames = run_backend_gain_attribution_stage(
        stage=stage,
        config=config,
        run_root=run_root,
        workers=1,
        _trajectory_keys=trajectory_keys,
    )
    return (
        frames["posterior_component_table.parquet"],
        frames["trajectory_step_posterior_metrics.parquet"],
    )


def run_backend_gain_attribution_stage(
    stage: str,
    config: Mapping[str, Any],
    run_root: str | Path,
    workers: int | None = None,
    *,
    _trajectory_keys: Sequence[tuple[Any, ...]] | None = None,
) -> dict[str, pd.DataFrame]:
    """Execute a backend attribution stage from frozen sidecar authority.

    The callable reads ``output_authority.model_root_prefix`` and
    ``output_authority.input_root_prefix`` exactly as authority roots.  Runtime
    updates consume only runtime, density, odometry, arm, shuffle, and fault
    sidecars.  Evaluator truth is joined only after each arm's state update has
    completed for a step.
    """

    resolved_workers = _resolve_backend_workers(workers)
    if _trajectory_keys is not None and resolved_workers != 1:
        raise BackendAttributionContractError(
            "P0_PARALLEL_NESTED_EXECUTION_FORBIDDEN"
        )
    if stage not in _STAGES:
        raise BackendAttributionContractError(f"P0_STAGE_UNSUPPORTED:{stage}")
    v3_selection = _v3_capacity_selection(stage, config)
    tables = _load_stage_authority(config)
    if stage == "smoke":
        _apply_smoke_caps(tables["runtime_link_table.parquet"], tables, config)

    runtime = tables["runtime_link_table.parquet"].sort_values(
        list(_LINK_KEY), kind="stable"
    ).reset_index(drop=True)
    if runtime.empty:
        raise BackendAttributionContractError("P0_RUNTIME_EMPTY")
    v3_realization_authority = (
        _v3_realization_authority(runtime)
        if v3_selection is not None
        else None
    )
    measurement_column = _get_measurement_column(runtime, config)
    density = tables["density_prediction_table.parquet"]
    density_by_case = _density_lookup(density)
    oracle_by_case = _oracle_lookup(tables.get("evaluator_oracle_sidecar.parquet", pd.DataFrame()))
    shuffle_by_mode, generated_shuffle_frame = _shuffle_lookup(
        runtime,
        tables.get("shuffle_assignment_table.parquet", pd.DataFrame()),
        config,
    )
    initial_states = _state_from_initial_pose(
        tables.get("initial_pose_sidecar.parquet", pd.DataFrame()),
        config,
    )
    odom = _odometry_lookup(tables["odometry_runtime_table.csv"])
    registry_source = tables.get("stage_arm_registry.csv", pd.DataFrame())
    if registry_source.empty:
        registry_source = tables["arm_registry.csv"]
    arms = _arm_registry_for_stage(registry_source, stage)
    if arms["arm_id"].astype(str).duplicated().any():
        raise BackendAttributionContractError("P0_STAGE_ARM_DUPLICATE_ID")
    if stage in {"smoke", "full"}:
        declared_registry = config.get("stage_arm_registry", {})
        expected_stage_ids = ("B1", "B2", "B3", "B4")
        expected_ids = {
            str(arm["arm_id"])
            for stage_id in expected_stage_ids
            for arm in declared_registry.get(stage_id, [])
        }
        actual_ids = set(arms["arm_id"].astype(str))
        if expected_ids and actual_ids != expected_ids:
            missing = sorted(expected_ids - actual_ids)
            extra = sorted(actual_ids - expected_ids)
            raise BackendAttributionContractError(
                f"P0_STAGE_ARM_SET_MISMATCH:missing={missing}:extra={extra}"
            )
    shard_execution = config.get("shard_execution", {})
    if isinstance(shard_execution, Mapping) and shard_execution.get("arm_id"):
        requested_arm = str(shard_execution["arm_id"])
        requested_stage = str(shard_execution.get("stage_id", ""))
        selected = arms[arms["arm_id"].astype(str).eq(requested_arm)].copy()
        if len(selected) != 1:
            raise BackendAttributionContractError(
                f"P0_SHARD_ARM_SELECTION_INVALID:{requested_arm}:matches={len(selected)}"
            )
        if requested_stage:
            declared_registry = config.get("stage_arm_registry", {})
            declared_for_stage = {
                str(row.get("arm_id"))
                for row in declared_registry.get(requested_stage, [])
                if isinstance(row, Mapping)
            }
            if requested_arm not in declared_for_stage:
                raise BackendAttributionContractError(
                    "P0_SHARD_STAGE_SELECTION_MISMATCH:"
                    f"requested={requested_stage}:arm={requested_arm}"
                )
            if (
                "stage_id" in selected.columns
                and str(selected["stage_id"].iloc[0]).strip()
                and str(selected["stage_id"].iloc[0]) != requested_stage
            ):
                raise BackendAttributionContractError(
                    "P0_SHARD_STAGE_SELECTION_MISMATCH:"
                    f"requested={requested_stage}:actual={selected['stage_id'].iloc[0]}"
                )
        arms = selected.reset_index(drop=True)
    evaluator = tables["evaluator_sidecar.parquet"]
    evaluator_by_step = {
        tuple(row[column] for column in _STEP_KEY): row
        for row in evaluator.drop_duplicates(list(_STEP_KEY)).to_dict("records")
    } if not evaluator.empty and set(_STEP_KEY).issubset(evaluator.columns) else {}

    component_rows: list[dict[str, Any]] = []
    step_rows: list[dict[str, Any]] = []
    fault_rows: list[pd.DataFrame] = []
    shuffle_rows: list[dict[str, Any]] = []
    backend_authority = config.get("backend_authority", {})
    caps = backend_authority.get("gsf_caps", {}) if isinstance(backend_authority, Mapping) else {}
    if not isinstance(caps, Mapping):
        raise BackendAttributionContractError("P0_CAPACITY_CLOSURE_MISSING:backend_authority.gsf_caps")
    max_components = int(_require_gsf_cap(caps, "max_posterior_components"))
    min_weight = float(_require_gsf_cap(caps, "merge_weight_floor"))
    reduction_policy = str(_require_gsf_cap(caps, "reduction_policy"))
    unit = str(_require_gsf_cap(caps, "unit"))
    _require_gsf_cap(caps, "max_discarded_mass_per_update")
    if unit != "per_update":
        raise BackendAttributionContractError(
            f"P0_UNIT_CONTRACT:backend_authority.gsf_caps.unit={unit!r}"
        )
    process_var = float(config.get("backend_authority", {}).get("process_variance_m2", 0.0))
    process_cov = process_var * np.eye(2)

    if resolved_workers > 1 and _trajectory_keys is None:
        posterior_parts: list[pd.DataFrame] = []
        step_parts: list[pd.DataFrame] = []
        for arm in arms.to_dict("records"):
            validate = validate_evidence_contract(
                str(arm.get("evidence_contract", "density_prior")),
                innovation_consumed_by_model=False,
                innovation_multiplied_in_filter=True,
            )
            if validate.status != "PASS":
                raise BackendAttributionContractError(
                    validate.gate or "P0_EVIDENCE_CONTRACT"
                )
            arm_runtime, fault_frame = _apply_fault_if_needed(
                runtime, arm, config, density
            )
            if not fault_frame.empty:
                fault_frame["arm_id"] = arm["arm_id"]
                fault_rows.append(fault_frame)
            trajectory_keys = [
                tuple(key) if isinstance(key, tuple) else (key,)
                for key in arm_runtime.groupby(list(_TRAJ_KEY), sort=True).groups
            ]
            partitions = _contiguous_partitions(
                trajectory_keys, resolved_workers
            )
            if not partitions:
                continue
            arm_id = str(arm["arm_id"])
            child_config = dict(config)
            child_config["shard_execution"] = {
                "arm_id": arm_id,
                "stage_id": str(arm.get("stage_id", ""))
                or _declared_stage_for_arm(config, arm_id),
            }
            payloads = [
                (stage, child_config, str(run_root), partition)
                for partition in partitions
            ]
            with ProcessPoolExecutor(
                max_workers=len(partitions),
                initializer=_initialize_backend_worker,
            ) as executor:
                for posterior_part, step_part in executor.map(
                    _parallel_stage_partition, payloads
                ):
                    posterior_parts.append(posterior_part)
                    step_parts.append(step_part)
        posterior = (
            pd.concat(posterior_parts, ignore_index=True)
            if posterior_parts
            else pd.DataFrame()
        )
        steps = (
            pd.concat(step_parts, ignore_index=True)
            if step_parts
            else pd.DataFrame()
        )
        if posterior.empty or steps.empty:
            raise BackendAttributionContractError("P0_BACKEND_OUTPUT_EMPTY")
        steps["hypothesis_outcome"] = (
            "NOT_TESTED" if stage == "smoke" else "NOT_ESTABLISHED"
        )
        steps["execution_status"] = "COMPLETED"
        return _finalize_v3_stage_outputs({
            "MODEL_ARTIFACT_MANIFEST.csv": tables["MODEL_ARTIFACT_MANIFEST.csv"],
            "ARM_REGISTRY.csv": arms,
            "runtime_link_table.parquet": runtime,
            "density_prediction_table.parquet": density,
            "evaluator_sidecar.parquet": evaluator,
            "posterior_component_table.parquet": posterior,
            "trajectory_step_posterior_metrics.parquet": steps,
            "fault_assignment_table.parquet": (
                pd.concat(fault_rows, ignore_index=True)
                if fault_rows
                else tables.get("fault_assignment_table.parquet", pd.DataFrame())
            ),
            "shuffle_assignment_table.parquet": generated_shuffle_frame,
            "PAIRING_MANIFEST.csv": tables.get(
                "pairing_manifest.csv", pd.DataFrame()
            ),
            "RUN_STAGE_METADATA.csv": pd.DataFrame(
                [
                    {
                        "stage": stage,
                        "run_root": str(run_root),
                        "execution_status": "COMPLETED",
                        "hypothesis_outcome": (
                            "NOT_TESTED"
                            if stage == "smoke"
                            else "NOT_ESTABLISHED"
                        ),
                    }
                ]
            ),
        }, selection=v3_selection, realization_authority=v3_realization_authority)

    selected_trajectory_keys = (
        {
            tuple(key) if isinstance(key, tuple) else (key,)
            for key in _trajectory_keys
        }
        if _trajectory_keys is not None
        else None
    )
    for arm in arms.to_dict("records"):
        validate = validate_evidence_contract(
            str(arm.get("evidence_contract", "density_prior")),
            innovation_consumed_by_model=False,
            innovation_multiplied_in_filter=True,
        )
        if validate.status != "PASS":
            raise BackendAttributionContractError(validate.gate or "P0_EVIDENCE_CONTRACT")
        arm_runtime, fault_frame = _apply_fault_if_needed(runtime, arm, config, density)
        if not fault_frame.empty:
            fault_frame["arm_id"] = arm["arm_id"]
            fault_rows.append(fault_frame)
        grouped = arm_runtime.groupby(list(_TRAJ_KEY), sort=True)
        for traj_key, group in grouped:
            normalized_traj_key = (
                tuple(traj_key) if isinstance(traj_key, tuple) else (traj_key,)
            )
            if (
                selected_trajectory_keys is not None
                and normalized_traj_key not in selected_trajectory_keys
            ):
                continue
            state = initial_states.get((traj_key[0], traj_key[1], int(traj_key[2])))
            if state is None:
                raise BackendAttributionContractError(f"P0_INITIAL_STATE_MISSING_FOR:{traj_key}")
            previous_step: int | None = None
            for step_idx, step_group in group.groupby("step_idx", sort=True):
                step_int = int(step_idx)
                if previous_step is None:
                    previous_step = step_int
                elif step_int != previous_step:
                    state = predict_persistent_gsf(
                        state,
                        _odometry_for(odom, traj_key[0], traj_key[1], traj_key[2], step_int),
                        process_cov,
                    )
                    previous_step = step_int
                available_group = step_group
                if "measurement_available" in available_group.columns:
                    available_group = available_group[available_group["measurement_available"].astype(bool)]
                update_index = 0
                for _, runtime_row in available_group.sort_values("anchor_id", kind="stable").iterrows():
                    mixture = _mixture_for_arm_case(
                        arm,
                        runtime_row,
                        density_by_case,
                        oracle_by_case,
                        shuffle_by_mode,
                        config,
                    )
                    mask = _hybrid_mask_value(arm.get("hybrid_mask", "none"))
                    if mask is not None:
                        cir = _mixture_for_arm_case(
                            {**arm, "evidence_source": "E_CIR_MDN"},
                            runtime_row,
                            density_by_case,
                            oracle_by_case,
                            shuffle_by_mode,
                            config,
                        )
                        mixture = hybrid_mixture(mixture, cir, mask)
                    measured = float(runtime_row[measurement_column])
                    anchor_xy = _get_anchor_xy(runtime_row)
                    consumer = _consumer_name(arm.get("consumer_id", "PERSISTENT_GSF"))
                    if consumer == "PERSISTENT_GSF":
                        update = update_persistent_gsf_range(
                            state,
                            measured,
                            anchor_xy,
                            mixture,
                            min_component_weight=min_weight,
                            max_components=max_components,
                            update_index=update_index,
                            reduction_policy=reduction_policy,  # type: ignore[arg-type]
                        )
                        state = update.state
                        for record in update.records:
                            component_rows.append(
                                {
                                    **{column: runtime_row[column] for column in _LINK_KEY},
                                    "arm_id": arm["arm_id"],
                                    "update_index_within_step": update_index,
                                    **record.__dict__,
                                }
                            )
                    elif consumer == "BRANCH_THEN_MERGE":
                        mean, cov = state.moment_match()
                        merged_mean, merged_cov, update = branch_then_merge_range(
                            mean,
                            cov,
                            measured,
                            anchor_xy,
                            mixture,
                            min_component_weight=min_weight,
                            max_components=max_components,
                            reduction_policy=reduction_policy,  # type: ignore[arg-type]
                        )
                        state = make_persistent_gsf_state([1.0], [merged_mean], [merged_cov])
                        component_rows.append(
                            {
                                **{column: runtime_row[column] for column in _LINK_KEY},
                                "arm_id": arm["arm_id"],
                                "update_index_within_step": update_index,
                                "parent_component_id": "BRANCH_THEN_MERGE",
                                "component_id": "BRANCH_THEN_MERGE",
                                "weight_pre": 1.0,
                                "link_component_weight": 1.0,
                                "innovation_m": float(np.nanmean([record.innovation_m for record in update.records])),
                                "innovation_variance_m2": float(np.nanmean([record.innovation_variance_m2 for record in update.records])),
                                "component_log_likelihood": float(update.log_evidence),
                                "weight_post_pre_prune": 1.0,
                                "weight_post": 1.0,
                                "state_x_m": float(merged_mean[0]),
                                "state_y_m": float(merged_mean[1]),
                                "cov_xx": float(merged_cov[0, 0]),
                                "cov_xy": float(merged_cov[0, 1]),
                                "cov_yy": float(merged_cov[1, 1]),
                                "discarded_mass": float(update.state.discarded_mass),
                                "active_component_count": 1,
                                "reduction_policy": update.reduction.reduction_policy if update.reduction else reduction_policy,
                                "pre_reduction_component_count": update.reduction.pre_reduction_component_count if update.reduction else len(update.records),
                                "post_reduction_component_count": update.reduction.post_reduction_component_count if update.reduction else len(update.records),
                                "surviving_mass": update.reduction.surviving_mass if update.reduction else 1.0,
                                "merged_mass": update.reduction.merged_mass if update.reduction else 0.0,
                                "floor_triggered_merge_count": update.reduction.floor_triggered_merge_count if update.reduction else 0,
                                "floor_triggered_mass": update.reduction.floor_triggered_mass if update.reduction else 0.0,
                                "merge_operation_count": update.reduction.merge_operation_count if update.reduction else 0,
                                "pair_cost_evaluation_count": update.reduction.pair_cost_evaluation_count if update.reduction else 0,
                                "max_pairwise_merge_cost": update.reduction.max_pairwise_merge_cost if update.reduction else 0.0,
                                "total_merge_cost": update.reduction.total_merge_cost if update.reduction else 0.0,
                                "mixture_mean_shift_l2": update.reduction.mixture_mean_shift_l2 if update.reduction else 0.0,
                                "mixture_cov_frobenius_shift": update.reduction.mixture_cov_frobenius_shift if update.reduction else 0.0,
                                "max_pairwise_mahalanobis_separation": update.reduction.max_pairwise_mahalanobis_separation if update.reduction else 0.0,
                                "separation_excluded_mass": update.reduction.separation_excluded_mass if update.reduction else 0.0,
                            }
                        )
                    elif consumer == "MM_BEFORE_UPDATE":
                        mean, cov = state.moment_match()
                        mm_mean, mm_cov = update_mm_before_range(
                            mean,
                            cov,
                            measured,
                            anchor_xy,
                            mixture,
                        )
                        state = make_persistent_gsf_state([1.0], [mm_mean], [mm_cov])
                        component_rows.append(
                            {
                                **{column: runtime_row[column] for column in _LINK_KEY},
                                "arm_id": arm["arm_id"],
                                "update_index_within_step": update_index,
                                "parent_component_id": "MM",
                                "component_id": "MM",
                                "weight_pre": 1.0,
                                "link_component_weight": 1.0,
                                "innovation_m": np.nan,
                                "innovation_variance_m2": np.nan,
                                "component_log_likelihood": np.nan,
                                "weight_post_pre_prune": 1.0,
                                "weight_post": 1.0,
                                "state_x_m": float(mm_mean[0]),
                                "state_y_m": float(mm_mean[1]),
                                "cov_xx": float(mm_cov[0, 0]),
                                "cov_xy": float(mm_cov[0, 1]),
                                "cov_yy": float(mm_cov[1, 1]),
                                "discarded_mass": 0.0,
                                "active_component_count": 1,
                            }
                        )
                    elif consumer == "SCALAR_ZERO_MEAN":
                        mean, cov = state.moment_match()
                        innovation, jacobian = range_innovation_and_jacobian(
                            mean,
                            anchor_xy,
                            measured,
                        )
                        variance = float(scalar_zero_mean_variance(mixture).reshape(-1)[0])
                        update = gaussian_measurement_update(
                            mean,
                            cov,
                            innovation,
                            jacobian,
                            residual_mean=0.0,
                            residual_sigma=float(np.sqrt(variance)),
                        )
                        state = make_persistent_gsf_state([1.0], [update.mean], [update.covariance])
                        component_rows.append(
                            {
                                **{column: runtime_row[column] for column in _LINK_KEY},
                                "arm_id": arm["arm_id"],
                                "update_index_within_step": update_index,
                                "parent_component_id": "SCALAR_ZERO_MEAN",
                                "component_id": "SCALAR_ZERO_MEAN",
                                "weight_pre": 1.0,
                                "link_component_weight": 1.0,
                                "innovation_m": float(innovation),
                                "innovation_variance_m2": float(update.innovation_variance),
                                "component_log_likelihood": float(update.log_likelihood),
                                "weight_post_pre_prune": 1.0,
                                "weight_post": 1.0,
                                "state_x_m": float(update.mean[0]),
                                "state_y_m": float(update.mean[1]),
                                "cov_xx": float(update.covariance[0, 0]),
                                "cov_xy": float(update.covariance[0, 1]),
                                "cov_yy": float(update.covariance[1, 1]),
                                "discarded_mass": 0.0,
                                "active_component_count": 1,
                            }
                        )
                    elif consumer == "HARD_GATE":
                        threshold = float(config.get("backend_authority", {}).get("hard_gate_w_threshold", config.get("backend_authority", {}).get("hard_gate_threshold", 0.5)))
                        gate_action = str(config.get("backend_authority", {}).get("hard_gate_action", "drop")).lower()
                        risk = float(mixture.w.reshape(-1)[0])
                        if risk >= threshold and gate_action == "drop":
                            component_rows.append(
                                {
                                    **{column: runtime_row[column] for column in _LINK_KEY},
                                    "arm_id": arm["arm_id"],
                                    "update_index_within_step": update_index,
                                    "parent_component_id": "HARD_GATE",
                                    "component_id": "HARD_GATE_DROPPED",
                                    "weight_pre": 1.0,
                                    "link_component_weight": 0.0,
                                    "innovation_m": np.nan,
                                    "innovation_variance_m2": np.nan,
                                    "component_log_likelihood": np.nan,
                                    "weight_post_pre_prune": 1.0,
                                    "weight_post": 1.0,
                                    "state_x_m": float(state.point_estimate()[0]),
                                    "state_y_m": float(state.point_estimate()[1]),
                                    "cov_xx": float(state.moment_match()[1][0, 0]),
                                    "cov_xy": float(state.moment_match()[1][0, 1]),
                                    "cov_yy": float(state.moment_match()[1][1, 1]),
                                    "discarded_mass": 0.0,
                                    "active_component_count": state.active_component_count,
                                }
                            )
                        else:
                            gate_mixture = mixture
                            if risk >= threshold:
                                large_sigma = float(config.get("backend_authority", {}).get("hard_gate_large_sigma_m", 10.0))
                                gate_mixture = TwoComponentMixture(
                                    w=np.array([0.0]),
                                    sigma_c=np.array([large_sigma]),
                                    sigma_x=np.array([large_sigma]),
                                    mu_c=np.array([0.0]),
                                    mu_0=np.array([0.0]),
                                )
                            mean, cov = state.moment_match()
                            mm_mean, mm_cov = update_mm_before_range(mean, cov, measured, anchor_xy, gate_mixture)
                            state = make_persistent_gsf_state([1.0], [mm_mean], [mm_cov])
                            component_rows.append(
                                {
                                    **{column: runtime_row[column] for column in _LINK_KEY},
                                    "arm_id": arm["arm_id"],
                                    "update_index_within_step": update_index,
                                    "parent_component_id": "HARD_GATE",
                                    "component_id": "HARD_GATE_UPDATED",
                                    "weight_pre": 1.0,
                                    "link_component_weight": 1.0,
                                    "innovation_m": np.nan,
                                    "innovation_variance_m2": np.nan,
                                    "component_log_likelihood": np.nan,
                                    "weight_post_pre_prune": 1.0,
                                    "weight_post": 1.0,
                                    "state_x_m": float(mm_mean[0]),
                                    "state_y_m": float(mm_mean[1]),
                                    "cov_xx": float(mm_cov[0, 0]),
                                    "cov_xy": float(mm_cov[0, 1]),
                                    "cov_yy": float(mm_cov[1, 1]),
                                    "discarded_mass": 0.0,
                                    "active_component_count": 1,
                                }
                            )
                    else:
                        raise BackendAttributionContractError(f"P0_CONSUMER_UNSUPPORTED:{consumer}")
                    update_index += 1
                eval_key = (traj_key[0], traj_key[1], traj_key[2], step_int)
                metrics = _evaluate_step_metrics(state, evaluator_by_step.get(eval_key))
                step_rows.append(
                    {
                        "trajectory_id": traj_key[0],
                        "schedule_id": traj_key[1],
                        "replay_seed": traj_key[2],
                        "arm_id": arm["arm_id"],
                        "step_idx": step_int,
                        "space_id": step_group["space_id"].iloc[0] if "space_id" in step_group.columns else "",
                        **metrics,
                    }
                )
    posterior = pd.DataFrame(component_rows)
    steps = pd.DataFrame(step_rows)
    if posterior.empty or steps.empty:
        raise BackendAttributionContractError("P0_BACKEND_OUTPUT_EMPTY")
    steps["hypothesis_outcome"] = "NOT_TESTED" if stage == "smoke" else "NOT_ESTABLISHED"
    steps["execution_status"] = "COMPLETED"
    return _finalize_v3_stage_outputs({
        "MODEL_ARTIFACT_MANIFEST.csv": tables["MODEL_ARTIFACT_MANIFEST.csv"],
        "ARM_REGISTRY.csv": arms,
        "runtime_link_table.parquet": runtime,
        "density_prediction_table.parquet": density,
        "evaluator_sidecar.parquet": evaluator,
        "posterior_component_table.parquet": posterior,
        "trajectory_step_posterior_metrics.parquet": steps,
        "fault_assignment_table.parquet": pd.concat(fault_rows, ignore_index=True) if fault_rows else tables.get("fault_assignment_table.parquet", pd.DataFrame()),
        "shuffle_assignment_table.parquet": generated_shuffle_frame,
        "PAIRING_MANIFEST.csv": tables.get("pairing_manifest.csv", pd.DataFrame()),
        "RUN_STAGE_METADATA.csv": pd.DataFrame(
            [
                {
                    "stage": stage,
                    "run_root": str(run_root),
                    "execution_status": "COMPLETED",
                    "hypothesis_outcome": "NOT_TESTED" if stage == "smoke" else "NOT_ESTABLISHED",
                }
            ]
        ),
    }, selection=v3_selection, realization_authority=v3_realization_authority)


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, tuple):
        return list(value)
    return value


__all__ = [
    "ComponentUpdateRecord",
    "EvidenceContractCheck",
    "GSFComponent",
    "MomentMatchedGaussian",
    "PersistentGSFState",
    "PersistentGSFUpdate",
    "TwoComponentMixture",
    "BackendAttributionContractError",
    "branch_then_merge_range",
    "deterministic_tuple_shuffle",
    "enumerate_hybrid_masks",
    "fixed_point_count",
    "gaussian_logpdf",
    "hybrid_mixture",
    "logsumexp",
    "make_persistent_gsf_state",
    "mixture_component_arrays",
    "predict_persistent_gsf",
    "range_innovation_and_jacobian",
    "run_backend_gain_attribution_stage",
    "scalar_zero_mean_variance",
    "shapley_values",
    "stable_rows_hash",
    "two_component_log_density",
    "update_mm_before_range",
    "update_persistent_gsf_range",
    "validate_evidence_contract",
]
