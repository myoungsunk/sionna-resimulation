"""Central multiplicity and intersection-union tests for CP consumer axes."""

from __future__ import annotations

import math
import hashlib
from typing import Mapping, Sequence

import numpy as np


AXES = ("F", "A", "M", "T", "C")


def valid_p(value: float | int | None, *, missing: float = 1.0) -> float:
    if value is None:
        return float(missing)
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ValueError(f"p-value must be finite and within [0,1], got {value!r}")
    return number


def iut_max(*components: float | int | None, missing: float = 1.0) -> float:
    if not components:
        raise ValueError("at least one IUT component is required")
    return max(valid_p(value, missing=missing) for value in components)


def operational_p(p_cp_vs_dlp: float | None, p_cp_aligned_vs_shuffle: float | None) -> float:
    return iut_max(p_cp_vs_dlp, p_cp_aligned_vs_shuffle)


def g2_p(p_pair_did: float | None, p_cp_content: float | None, p_dlp_content: float | None) -> float:
    return iut_max(p_pair_did, p_cp_content, p_dlp_content)


def g2_cp_specific_p(p_pair_did: float | None, p_cp_aligned_vs_shuffle: float | None) -> float:
    """IUT for CP-specific alignment benefit.

    DLP aligned-vs-shuffle is a comparator-validity guard and must be reported
    separately; it is not a third success component that can replace either
    the CP-vs-DLP interaction or CP content test.
    """

    return iut_max(p_pair_did, p_cp_aligned_vs_shuffle)


def physics_mediated_p(p_operational: float | None, p_g2: float | None, p_g1: float | None) -> float:
    return iut_max(p_operational, p_g2, p_g1)


def holm_adjust(p_values: Mapping[str, float | int | None]) -> dict[str, float]:
    """Return Holm step-down adjusted p-values, retaining missing tests as p=1."""

    normalized = {str(key): valid_p(value) for key, value in p_values.items()}
    ordered = sorted(normalized.items(), key=lambda item: (item[1], item[0]))
    total = len(ordered)
    running = 0.0
    adjusted: dict[str, float] = {}
    for rank, (key, value) in enumerate(ordered):
        candidate = min(1.0, (total - rank) * value)
        running = max(running, candidate)
        adjusted[key] = running
    return {key: adjusted[key] for key in normalized}


def stable_seed(global_contract_hash: str, family_id: str, replicate_id: str | int = 0) -> int:
    payload = f"{global_contract_hash}|{family_id}|{replicate_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def bootstrap_draw_indices(n_clusters: int, replicates: int, seed: int) -> np.ndarray:
    if n_clusters < 2:
        raise ValueError("paired cluster bootstrap requires at least two clusters")
    if replicates < 1:
        raise ValueError("replicates must be positive")
    generator = np.random.default_rng(int(seed))
    return generator.integers(0, n_clusters, size=(replicates, n_clusters), endpoint=False)


def paired_cluster_bootstrap(
    paired_cluster_deltas: Sequence[float],
    *,
    replicates: int,
    seed: int,
    null_margin: float = 0.0,
) -> dict[str, float]:
    """Bootstrap a paired cluster contrast from one delta per frozen cluster."""

    values = np.asarray(paired_cluster_deltas, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        raise ValueError("paired cluster bootstrap requires at least two finite deltas")
    draws = bootstrap_draw_indices(int(values.size), int(replicates), int(seed))
    means = values[draws].mean(axis=1)
    estimate = float(values.mean())
    return {
        "estimate": estimate,
        "ci_low": float(np.quantile(means, 0.025)),
        "ci_high": float(np.quantile(means, 0.975)),
        "null_margin": float(null_margin),
        "p_one_sided_greater": float((1 + np.count_nonzero(means <= float(null_margin))) / (len(means) + 1)),
        "p_one_sided_less": float((1 + np.count_nonzero(means >= float(null_margin))) / (len(means) + 1)),
        "n_clusters": float(values.size),
        "replicates": float(replicates),
    }


def early_axis_status(
    p_operational: float | None,
    *,
    pass_power: bool,
    intervention_nonzero: bool,
    guards_pass: bool,
    technical_status: str = "READY",
    alpha: float = 0.01,
) -> str:
    if technical_status != "READY":
        return "BLOCKED_TERMINAL"
    value = valid_p(p_operational)
    if value <= alpha and pass_power and intervention_nonzero and guards_pass:
        return "EARLY_FWER_SAFE_PASS"
    if value > alpha:
        return "PENDING_FINAL_HOLM"
    return "EARLY_GUARD_BLOCKED"


def diversified_early_status(axis_rows: Mapping[str, Mapping[str, object]]) -> str:
    passed = []
    for axis, row in axis_rows.items():
        if row.get("early_status") == "EARLY_FWER_SAFE_PASS":
            passed.append((axis, row.get("changed_object_id"), row.get("evidence_family_id")))
    for left_index, left in enumerate(passed):
        for right in passed[left_index + 1 :]:
            if left[1] and right[1] and left[1] != right[1] and left[2] and right[2] and left[2] != right[2]:
                return "DIVERSIFIED_OPERATIONAL_CONSUMER_UTILITY"
    return "NOT_YET_DIVERSIFIED"
