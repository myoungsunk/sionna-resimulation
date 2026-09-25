"""Deterministic, moment-preserving Gaussian-mixture reduction helpers.

This module deliberately has no dependency on the Paper 2 runner.  It works
with component objects exposing ``component_id``, ``weight``, ``mean`` and
``covariance`` attributes; the caller supplies the factory that constructs a
merged component.  Keeping the numerical reduction here makes it possible for
the runner and an independent auditor to use separate integration paths.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import heapq
from typing import Any, Literal, TypeVar

import numpy as np


ComponentT = TypeVar("ComponentT")
ReductionPolicy = Literal[
    "RUNNALLS_MERGE",
    "TRUNCATE_LEGACY",
    "NO_REDUCTION_REFERENCE",
]
ComponentFactory = Callable[[ComponentT, ComponentT, float, np.ndarray, np.ndarray, str], ComponentT]


@dataclass(frozen=True)
class MixtureReductionDiagnostics:
    """Per-update reduction ledger, including a partition-based mass account."""

    reduction_policy: ReductionPolicy
    pre_reduction_component_count: int
    post_reduction_component_count: int
    surviving_mass: float
    merged_mass: float
    discarded_mass: float
    floor_triggered_merge_count: int
    floor_triggered_mass: float
    merge_operation_count: int
    pair_cost_evaluation_count: int
    max_pairwise_merge_cost: float
    total_merge_cost: float
    mixture_mean_shift_l2: float
    mixture_cov_frobenius_shift: float
    max_pairwise_mahalanobis_separation: float
    separation_excluded_mass: float
    lineage_map: Mapping[str, str | None]


@dataclass(frozen=True)
class MixtureReductionResult:
    """Reduced components and their reproducibility diagnostics."""

    components: tuple[Any, ...]
    diagnostics: MixtureReductionDiagnostics


def _as_covariance(value: Any) -> np.ndarray:
    covariance = np.asarray(value, dtype=float)
    if covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]:
        raise ValueError("component covariance must be square")
    if not np.all(np.isfinite(covariance)):
        raise ValueError("component covariance must be finite")
    covariance = 0.5 * (covariance + covariance.T)
    if float(np.linalg.eigvalsh(covariance).min()) < -1.0e-10:
        raise ValueError("component covariance must be positive semidefinite")
    return covariance


def _stable_logdet(covariance: np.ndarray) -> float:
    """Log determinant used only for ranking merge costs.

    Posterior covariances should be positive definite.  The tiny jitter is
    confined to cost ranking so it cannot change the moment-preserving merged
    covariance returned to the caller.
    """

    dimension = covariance.shape[0]
    scale = max(1.0, float(np.max(np.abs(covariance))))
    sign, logdet = np.linalg.slogdet(covariance + (1.0e-12 * scale) * np.eye(dimension))
    if sign <= 0.0 or not np.isfinite(logdet):
        raise FloatingPointError("Runnalls cost requires finite positive covariance determinant")
    return float(logdet)


def mixture_moments(components: Sequence[Any]) -> tuple[np.ndarray, np.ndarray]:
    """Return mixture mean and total covariance for normalized components."""

    if not components:
        raise ValueError("components must be non-empty")
    weights = np.asarray([float(component.weight) for component in components], dtype=float)
    if not np.all(np.isfinite(weights)) or np.any(weights < 0.0):
        raise ValueError("component weights must be finite and nonnegative")
    total = float(weights.sum())
    if total <= 0.0:
        raise ValueError("component weights must have positive total mass")
    weights = weights / total
    means = np.stack([np.asarray(component.mean, dtype=float) for component in components])
    if not np.all(np.isfinite(means)):
        raise ValueError("component means must be finite")
    mean = weights @ means
    covariance = np.zeros((means.shape[1], means.shape[1]), dtype=float)
    for weight, component in zip(weights, components):
        component_covariance = _as_covariance(component.covariance)
        delta = np.asarray(component.mean, dtype=float) - mean
        covariance += weight * (component_covariance + np.outer(delta, delta))
    return mean, 0.5 * (covariance + covariance.T)


def merged_moments(left: Any, right: Any) -> tuple[float, np.ndarray, np.ndarray]:
    """Moment-preserving replacement for two Gaussian mixture components."""

    left_weight = float(left.weight)
    right_weight = float(right.weight)
    merged_weight = left_weight + right_weight
    if not np.isfinite(merged_weight) or merged_weight <= 0.0:
        raise ValueError("a merge pair must have positive total weight")
    left_mean = np.asarray(left.mean, dtype=float)
    right_mean = np.asarray(right.mean, dtype=float)
    if left_mean.shape != right_mean.shape:
        raise ValueError("merge component means must have equal shape")
    merged_mean = (left_weight * left_mean + right_weight * right_mean) / merged_weight
    left_covariance = _as_covariance(left.covariance)
    right_covariance = _as_covariance(right.covariance)
    left_delta = left_mean - merged_mean
    right_delta = right_mean - merged_mean
    merged_covariance = (
        (left_weight / merged_weight) * (left_covariance + np.outer(left_delta, left_delta))
        + (right_weight / merged_weight) * (right_covariance + np.outer(right_delta, right_delta))
    )
    return merged_weight, merged_mean, 0.5 * (merged_covariance + merged_covariance.T)


def runnalls_upper_bound(left: Any, right: Any) -> float:
    """Return the nonnegative Runnalls pairwise KL upper-bound cost."""

    left_weight = float(left.weight)
    right_weight = float(right.weight)
    if left_weight < 0.0 or right_weight < 0.0:
        raise ValueError("component weights must be nonnegative")
    if left_weight == 0.0 or right_weight == 0.0:
        return 0.0
    merged_weight, _, merged_covariance = merged_moments(left, right)
    value = 0.5 * (
        merged_weight * _stable_logdet(merged_covariance)
        - left_weight * _stable_logdet(_as_covariance(left.covariance))
        - right_weight * _stable_logdet(_as_covariance(right.covariance))
    )
    # Numerical noise can make an analytically nonnegative cost slightly negative.
    return float(max(0.0, value))


def max_pairwise_mahalanobis_separation(
    components: Sequence[Any],
    *,
    min_weight: float = 1.0e-3,
    regularization: float = 1.0e-9,
) -> tuple[float, float]:
    """Compute the preregistered post-update/pre-reduction state separation."""

    if min_weight < 0.0 or regularization <= 0.0:
        raise ValueError("min_weight must be nonnegative and regularization positive")
    total_weight = float(sum(float(component.weight) for component in components))
    if total_weight <= 0.0:
        raise ValueError("component weights must have positive total mass")
    included = [component for component in components if float(component.weight) >= min_weight]
    excluded_mass = max(0.0, 1.0 - sum(float(component.weight) for component in included) / total_weight)
    if len(included) <= 1:
        return 0.0, excluded_mass
    weights = np.asarray([float(component.weight) for component in included], dtype=float)
    weights = weights / float(weights.sum())
    covariance = np.zeros_like(_as_covariance(included[0].covariance))
    for weight, component in zip(weights, included):
        covariance += weight * _as_covariance(component.covariance)
    covariance = 0.5 * (covariance + covariance.T) + regularization * np.eye(covariance.shape[0])
    inverse = np.linalg.inv(covariance)
    maximum = 0.0
    for left_index, left in enumerate(included[:-1]):
        for right in included[left_index + 1 :]:
            delta = np.asarray(left.mean, dtype=float) - np.asarray(right.mean, dtype=float)
            distance_squared = float(delta @ inverse @ delta)
            maximum = max(maximum, float(np.sqrt(max(0.0, distance_squared))))
    return maximum, excluded_mass


def _merge_id(left: Any, right: Any) -> str:
    token = "|".join(sorted((str(left.component_id), str(right.component_id))))
    return "merge_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _select_minimum_pair(nodes: Sequence[tuple[Any, tuple[str, ...]]]) -> tuple[int, int, float]:
    best: tuple[float, str, str, int, int] | None = None
    for left_index, (left, _) in enumerate(nodes[:-1]):
        for right_index, (right, _) in enumerate(nodes[left_index + 1 :], start=left_index + 1):
            cost = runnalls_upper_bound(left, right)
            ordered_ids = tuple(sorted((str(left.component_id), str(right.component_id))))
            candidate = (cost, ordered_ids[0], ordered_ids[1], left_index, right_index)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        raise ValueError("at least two components are required to select a merge pair")
    return best[3], best[4], float(best[0])


def reduce_mixture(
    components: Sequence[ComponentT],
    *,
    max_components: int,
    merge_weight_floor: float,
    policy: ReductionPolicy = "RUNNALLS_MERGE",
    reduction_free_component_limit: int = 4096,
    component_factory: ComponentFactory[ComponentT],
) -> MixtureReductionResult:
    """Reduce a normalized mixture by deterministic merge or legacy truncation.

    ``RUNNALLS_MERGE`` never discards mass.  ``TRUNCATE_LEGACY`` is retained
    solely as a diagnostic control and intentionally preserves the old
    truncate-and-renormalize behavior.  ``NO_REDUCTION_REFERENCE`` is only
    for a preregistered bounded reference window; its component ceiling makes
    an accidental unbounded persistent branch fail loudly.
    """

    if max_components < 1:
        raise ValueError("max_components must be at least one")
    if reduction_free_component_limit < 1:
        raise ValueError("reduction_free_component_limit must be at least one")
    if not np.isfinite(merge_weight_floor) or merge_weight_floor < 0.0:
        raise ValueError("merge_weight_floor must be finite and nonnegative")
    if policy not in {"RUNNALLS_MERGE", "TRUNCATE_LEGACY", "NO_REDUCTION_REFERENCE"}:
        raise ValueError(f"unsupported reduction policy: {policy!r}")
    if not components:
        raise ValueError("components must be non-empty")

    raw_weights = np.asarray([float(component.weight) for component in components], dtype=float)
    if not np.all(np.isfinite(raw_weights)) or np.any(raw_weights < 0.0):
        raise ValueError("component weights must be finite and nonnegative")
    raw_total = float(raw_weights.sum())
    if raw_total <= 0.0:
        raise ValueError("component weights must have positive total mass")

    # The caller normally supplies normalized weights.  Normalize once here so
    # diagnostics always have the declared probability-mass interpretation.
    normalized: list[tuple[ComponentT, tuple[str, ...]]] = []
    for component, raw_weight in zip(components, raw_weights):
        normalized_weight = float(raw_weight / raw_total)
        if abs(normalized_weight - float(component.weight)) > 1.0e-15:
            component = component_factory(
                component,
                component,
                normalized_weight,
                np.asarray(component.mean, dtype=float),
                _as_covariance(component.covariance),
                str(component.component_id),
            )
        normalized.append((component, (str(component.component_id),)))

    pre_components = [component for component, _ in normalized]
    pre_mean, pre_covariance = mixture_moments(pre_components)
    if policy == "NO_REDUCTION_REFERENCE" and len(pre_components) > reduction_free_component_limit:
        raise RuntimeError(
            "bounded no-reduction reference exceeded its component limit "
            f"({len(pre_components)} > {reduction_free_component_limit})"
        )
    separation, excluded_mass = max_pairwise_mahalanobis_separation(pre_components)

    if policy == "NO_REDUCTION_REFERENCE":
        lineage_map = {str(component.component_id): str(component.component_id) for component in pre_components}
        return MixtureReductionResult(
            tuple(pre_components),
            MixtureReductionDiagnostics(
                reduction_policy=policy,
                pre_reduction_component_count=len(pre_components),
                post_reduction_component_count=len(pre_components),
                surviving_mass=1.0,
                merged_mass=0.0,
                discarded_mass=0.0,
                floor_triggered_merge_count=0,
                floor_triggered_mass=0.0,
                merge_operation_count=0,
                pair_cost_evaluation_count=0,
                max_pairwise_merge_cost=0.0,
                total_merge_cost=0.0,
                mixture_mean_shift_l2=0.0,
                mixture_cov_frobenius_shift=0.0,
                max_pairwise_mahalanobis_separation=separation,
                separation_excluded_mass=excluded_mass,
                lineage_map=lineage_map,
            ),
        )

    if policy == "TRUNCATE_LEGACY":
        eligible = [node for node in normalized if float(node[0].weight) >= merge_weight_floor]
        if not eligible:
            eligible = [max(normalized, key=lambda node: (float(node[0].weight), str(node[0].component_id)))]
        eligible.sort(key=lambda node: (-float(node[0].weight), str(node[0].component_id)))
        retained = eligible[:max_components]
        retained_mass = float(sum(float(node[0].weight) for node in retained))
        discarded_mass = max(0.0, 1.0 - retained_mass)
        post_components: list[ComponentT] = []
        lineage_map: dict[str, str | None] = {}
        for component, members in retained:
            weight = float(component.weight) / retained_mass
            rebuilt = component_factory(
                component,
                component,
                weight,
                np.asarray(component.mean, dtype=float),
                _as_covariance(component.covariance),
                str(component.component_id),
            )
            post_components.append(rebuilt)
            for member in members:
                lineage_map[member] = str(rebuilt.component_id)
        retained_ids = set(lineage_map)
        for component, members in normalized:
            for member in members:
                if member not in retained_ids:
                    lineage_map[member] = None
        post_mean, post_covariance = mixture_moments(post_components)
        return MixtureReductionResult(
            tuple(post_components),
            MixtureReductionDiagnostics(
                reduction_policy=policy,
                pre_reduction_component_count=len(pre_components),
                post_reduction_component_count=len(post_components),
                surviving_mass=retained_mass,
                merged_mass=0.0,
                discarded_mass=discarded_mass,
                floor_triggered_merge_count=0,
                floor_triggered_mass=0.0,
                merge_operation_count=0,
                pair_cost_evaluation_count=0,
                max_pairwise_merge_cost=0.0,
                total_merge_cost=0.0,
                mixture_mean_shift_l2=float(np.linalg.norm(post_mean - pre_mean)),
                mixture_cov_frobenius_shift=float(np.linalg.norm(post_covariance - pre_covariance, ord="fro")),
                max_pairwise_mahalanobis_separation=separation,
                separation_excluded_mass=excluded_mass,
                lineage_map=lineage_map,
            ),
        )

    # Cache every pair cost exactly once.  The heap holds stale entries after a
    # merge, which are discarded lazily; only pairs incident to a newly merged
    # component need to be evaluated.  This changes selection from repeatedly
    # scanning all active pairs (cubic) to O(K^2 log K) heap work.
    nodes: dict[str, tuple[ComponentT, tuple[str, ...]]] = {}
    for component, members in normalized:
        component_id = str(component.component_id)
        if component_id in nodes:
            raise ValueError("component_id must be unique for deterministic reduction")
        nodes[component_id] = (component, members)
    pair_heap: list[tuple[float, str, str]] = []
    floor_heap: list[tuple[float, str]] = []
    pair_cost_cache: dict[tuple[str, str], float] = {}

    def _pair_key(left_id: str, right_id: str) -> tuple[str, str]:
        return (left_id, right_id) if left_id < right_id else (right_id, left_id)

    def _cache_pair(left_id: str, right_id: str) -> float:
        key = _pair_key(left_id, right_id)
        cached = pair_cost_cache.get(key)
        if cached is None:
            cached = runnalls_upper_bound(nodes[key[0]][0], nodes[key[1]][0])
            pair_cost_cache[key] = cached
            heapq.heappush(pair_heap, (cached, key[0], key[1]))
        return cached

    initial_ids = sorted(nodes)
    for left_offset, left_id in enumerate(initial_ids[:-1]):
        heapq.heappush(floor_heap, (float(nodes[left_id][0].weight), left_id))
        for right_id in initial_ids[left_offset + 1 :]:
            _cache_pair(left_id, right_id)
    if initial_ids:
        last_id = initial_ids[-1]
        heapq.heappush(floor_heap, (float(nodes[last_id][0].weight), last_id))

    def _next_floor_id() -> str | None:
        while floor_heap:
            weight, component_id = floor_heap[0]
            active = nodes.get(component_id)
            if active is None or weight != float(active[0].weight):
                heapq.heappop(floor_heap)
                continue
            return component_id if weight < merge_weight_floor else None
        return None

    def _next_cap_pair() -> tuple[str, str, float]:
        while pair_heap:
            cost, left_id, right_id = heapq.heappop(pair_heap)
            if left_id in nodes and right_id in nodes:
                return left_id, right_id, cost
        raise RuntimeError("active mixture has no available Runnalls merge pair")

    merge_costs: list[float] = []
    floor_triggered_count = 0
    floor_triggered_mass = 0.0
    while True:
        floor_id = _next_floor_id()
        if floor_id is not None:
            partner_candidates = [
                (_cache_pair(floor_id, other_id), other_id)
                for other_id in nodes
                if other_id != floor_id
            ]
            _, other_id = min(partner_candidates)
            floor_triggered_count += 1
            floor_triggered_mass += float(nodes[floor_id][0].weight)
        elif len(nodes) > max_components:
            floor_id, other_id, _ = _next_cap_pair()
        else:
            break

        left_id, right_id = _pair_key(floor_id, other_id)
        left, left_members = nodes[left_id]
        right, right_members = nodes[right_id]
        cost = _cache_pair(left_id, right_id)
        weight, mean, covariance = merged_moments(left, right)
        merged_id = _merge_id(left, right)
        if merged_id in nodes:
            raise RuntimeError("deterministic merged component id collision")
        merged = component_factory(left, right, weight, mean, covariance, merged_id)
        members = tuple(sorted(left_members + right_members))
        del nodes[left_id]
        del nodes[right_id]
        nodes[merged_id] = (merged, members)
        heapq.heappush(floor_heap, (float(merged.weight), merged_id))
        for existing_id in nodes:
            if existing_id != merged_id:
                _cache_pair(existing_id, merged_id)
        merge_costs.append(cost)

    post_components = [component for component, _ in nodes.values()]
    post_mean, post_covariance = mixture_moments(post_components)
    lineage_map = {
        member: str(component.component_id)
        for component, members in nodes.values()
        for member in members
    }
    surviving_mass = float(
        sum(float(component.weight) for component, members in nodes.values() if len(members) == 1)
    )
    merged_mass = float(
        sum(float(component.weight) for component, members in nodes.values() if len(members) >= 2)
    )
    return MixtureReductionResult(
        tuple(post_components),
        MixtureReductionDiagnostics(
            reduction_policy=policy,
            pre_reduction_component_count=len(pre_components),
            post_reduction_component_count=len(post_components),
            surviving_mass=surviving_mass,
            merged_mass=merged_mass,
            discarded_mass=0.0,
            floor_triggered_merge_count=floor_triggered_count,
            floor_triggered_mass=floor_triggered_mass,
            merge_operation_count=len(merge_costs),
            pair_cost_evaluation_count=len(pair_cost_cache),
            max_pairwise_merge_cost=float(max(merge_costs, default=0.0)),
            total_merge_cost=float(sum(merge_costs)),
            mixture_mean_shift_l2=float(np.linalg.norm(post_mean - pre_mean)),
            mixture_cov_frobenius_shift=float(np.linalg.norm(post_covariance - pre_covariance, ord="fro")),
            max_pairwise_mahalanobis_separation=separation,
            separation_excluded_mass=excluded_mass,
            lineage_map=lineage_map,
        ),
    )
