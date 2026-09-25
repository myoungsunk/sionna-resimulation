"""Deterministic split, likelihood, bootstrap, and manifest helpers for Part 4 v3.

All helpers are additive and outcome-independent unless their docstring says
otherwise.  They deliberately use room clusters rather than rows for primary
intervals.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PairedEstimate:
    estimate: float
    ci_low: float
    ci_high: float
    n_case: int
    n_room: int
    positive_boot_fraction: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_room_calibration_split(
    rooms: Iterable[object], calibration_fraction: float = 0.20, seed: int = 20260728,
) -> tuple[set[str], set[str]]:
    """Return deterministic disjoint model-train and calibration room sets.

    The decision depends only on room identity and the predeclared seed; labels,
    residuals, and features cannot influence this split.
    """
    unique = sorted({str(room) for room in rooms})
    if len(unique) < 2:
        raise ValueError("at least two rooms are required for train/calibration split")
    scored = []
    for room in unique:
        token = f"{seed}:{room}".encode("utf-8")
        scored.append((int(hashlib.sha256(token).hexdigest()[:16], 16), room))
    scored.sort()
    n_cal = max(1, min(len(unique) - 1, int(round(len(unique) * calibration_fraction))))
    calibration = {room for _, room in scored[:n_cal]}
    return set(unique).difference(calibration), calibration


def assert_room_disjoint(train: pd.DataFrame, calibration: pd.DataFrame, test: pd.DataFrame, room_col: str = "room_id") -> None:
    partitions = [set(x[room_col].astype(str)) for x in (train, calibration, test)]
    if partitions[0] & partitions[1] or partitions[0] & partitions[2] or partitions[1] & partitions[2]:
        raise ValueError("room leakage across model-train/calibration/test")


def room_cluster_bootstrap(
    values: Sequence[float] | np.ndarray,
    rooms: Sequence[object] | np.ndarray,
    n_boot: int,
    seed: int,
) -> PairedEstimate:
    values_a = np.asarray(values, dtype=float)
    rooms_a = np.asarray(rooms).astype(str)
    finite = np.isfinite(values_a)
    values_a, rooms_a = values_a[finite], rooms_a[finite]
    if not len(values_a):
        return PairedEstimate(math.nan, math.nan, math.nan, 0, 0, math.nan)
    unique = np.unique(rooms_a)
    indices = {room: np.flatnonzero(rooms_a == room) for room in unique}
    rng = np.random.default_rng(seed)
    draws = np.empty(int(n_boot), dtype=float)
    for draw_idx in range(int(n_boot)):
        selected = rng.choice(unique, len(unique), replace=True)
        idx = np.concatenate([indices[room] for room in selected])
        draws[draw_idx] = float(values_a[idx].mean())
    return PairedEstimate(
        estimate=float(values_a.mean()),
        ci_low=float(np.percentile(draws, 2.5)),
        ci_high=float(np.percentile(draws, 97.5)),
        n_case=int(len(values_a)),
        n_room=int(len(unique)),
        positive_boot_fraction=float(np.mean(draws > 0.0)),
    )


def gaussian_logpdf(x: np.ndarray, mean: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
    z = (np.asarray(x, dtype=float) - np.asarray(mean, dtype=float)) / sigma
    return -0.5 * z * z - np.log(sigma) - 0.5 * math.log(2.0 * math.pi)


def mixture_nll(residual: np.ndarray, weight: np.ndarray, sigma_c: np.ndarray, sigma_x: np.ndarray, mu_c: np.ndarray | float, mu_x: np.ndarray | float) -> np.ndarray:
    log_a = np.log(np.clip(weight, 1e-12, 1.0 - 1e-12)) + gaussian_logpdf(residual, mu_c, sigma_c)
    log_b = np.log(np.clip(1.0 - weight, 1e-12, 1.0 - 1e-12)) + gaussian_logpdf(residual, mu_x, sigma_x)
    return -np.logaddexp(log_a, log_b)


def mixture_cdf(x: np.ndarray, weight: np.ndarray, sigma_c: np.ndarray, sigma_x: np.ndarray, mu_c: np.ndarray | float, mu_x: np.ndarray | float) -> np.ndarray:
    from scipy.special import ndtr
    return np.asarray(weight) * ndtr((np.asarray(x) - np.asarray(mu_c)) / np.maximum(np.asarray(sigma_c), 1e-12)) + (1.0 - np.asarray(weight)) * ndtr((np.asarray(x) - np.asarray(mu_x)) / np.maximum(np.asarray(sigma_x), 1e-12))


def mixture_interval(weight: np.ndarray, sigma_c: np.ndarray, sigma_x: np.ndarray, mu_c: np.ndarray | float, mu_x: np.ndarray | float, coverage: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
    """Numerical central interval for a two-Gaussian mixture."""
    lo_q, hi_q = (1.0 - coverage) / 2.0, (1.0 + coverage) / 2.0
    w = np.asarray(weight, dtype=float)
    sc, sx = np.asarray(sigma_c, dtype=float), np.asarray(sigma_x, dtype=float)
    mc, mx = np.asarray(mu_c, dtype=float), np.asarray(mu_x, dtype=float)
    lower = np.minimum(mc - 10 * sc, mx - 10 * sx)
    upper = np.maximum(mc + 10 * sc, mx + 10 * sx)
    def quantile(q: float) -> np.ndarray:
        left, right = lower.copy(), upper.copy()
        for _ in range(70):
            mid = (left + right) / 2.0
            below = mixture_cdf(mid, w, sc, sx, mc, mx) < q
            left[below] = mid[below]
            right[~below] = mid[~below]
        return (left + right) / 2.0
    return quantile(lo_q), quantile(hi_q)


def normal_crps(observation: np.ndarray, mean: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    from scipy.special import ndtr
    z = (np.asarray(observation) - np.asarray(mean)) / np.maximum(np.asarray(sigma), 1e-12)
    phi = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return np.asarray(sigma) * (z * (2 * ndtr(z) - 1) + 2 * phi - 1 / math.sqrt(math.pi))


def mixture_crps(observation: np.ndarray, weight: np.ndarray, sigma_c: np.ndarray, sigma_x: np.ndarray, mu_c: np.ndarray | float, mu_x: np.ndarray | float) -> np.ndarray:
    """Exact two-normal-mixture CRPS using E|X-y|-0.5E|X-X'|."""
    from scipy.special import ndtr
    obs, w = np.asarray(observation), np.asarray(weight)
    sc, sx, mc, mx = (np.asarray(sigma_c), np.asarray(sigma_x), np.asarray(mu_c), np.asarray(mu_x))
    def a_fn(mean_delta: np.ndarray, sd: np.ndarray) -> np.ndarray:
        z = mean_delta / np.maximum(sd, 1e-12)
        return 2 * sd * np.exp(-0.5 * z*z) / math.sqrt(2*math.pi) + mean_delta * (2 * ndtr(z) - 1)
    e_xy = w * a_fn(mc - obs, sc) + (1-w) * a_fn(mx - obs, sx)
    e_cc = a_fn(np.zeros_like(sc), np.sqrt(2)*sc)
    e_xx = a_fn(np.zeros_like(sx), np.sqrt(2)*sx)
    e_cx = a_fn(mc - mx, np.sqrt(sc*sc + sx*sx))
    e_pair = w*w*e_cc + (1-w)*(1-w)*e_xx + 2*w*(1-w)*e_cx
    return e_xy - 0.5 * e_pair


def holm_adjust(p_values: Sequence[float]) -> np.ndarray:
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(np.nan_to_num(p, nan=np.inf))
    adjusted = np.full(len(p), np.nan)
    running = 0.0
    for rank, index in enumerate(order):
        if not np.isfinite(p[index]):
            continue
        value = min(1.0, (len(p) - rank) * p[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def component_row(component_id: str, *, execution_status: str, hypothesis_outcome: str, adoption_status: str, primary_estimand: str, estimate: float = math.nan, ci_low: float = math.nan, ci_high: float = math.nan, n_case: int = 0, n_room: int = 0, controlled_comparison: bool = False, hard_gate_pass: bool = False, limitation_code: str = "", evidence_files: str = "") -> dict[str, object]:
    return {
        "component_id": component_id, "execution_status": execution_status,
        "hypothesis_outcome": hypothesis_outcome, "adoption_status": adoption_status,
        "primary_estimand": primary_estimand, "estimate": estimate, "ci_low": ci_low,
        "ci_high": ci_high, "n_case": int(n_case), "n_room": int(n_room),
        "controlled_comparison": bool(controlled_comparison), "hard_gate_pass": bool(hard_gate_pass),
        "limitation_code": limitation_code, "evidence_files": evidence_files,
    }


@dataclass(frozen=True)
class ComponentVerdict:
    """Outcome-independent v4 component decision.

    v3 permitted callers to place an arbitrary string in ``hypothesis_outcome``.
    Part 4 v4 instead derives that field from the preregistered interval and
    support gates.  ``adoption_status`` deliberately remains a separate manual
    claim-boundary decision: passing a numerical test never promotes a paper
    claim by itself.
    """

    execution_status: str
    hypothesis_outcome: str
    adoption_status: str
    decision_rule_id: str
    reason_code: str


def derive_h5_router_verdict(
    *,
    no_oracle: PairedEstimate,
    after_oracle: PairedEstimate,
    all_arms_complete: bool,
    shuffle_sanity_pass: bool,
) -> ComponentVerdict:
    """Apply the preregistered H5 router-versus-within-regime rule."""
    if not all_arms_complete or not shuffle_sanity_pass:
        return ComponentVerdict("SUPPORT_FAILURE", "NOT_EVALUATED", "NOT_ADOPTED", "V4_H5_ROUTER_RULE", "MISSING_ARM_OR_SHUFFLE_SANITY_FAILURE")
    finite = np.asarray([no_oracle.estimate, no_oracle.ci_low, no_oracle.ci_high, after_oracle.estimate, after_oracle.ci_low, after_oracle.ci_high], dtype=float)
    if not np.isfinite(finite).all() or no_oracle.n_room < 1 or after_oracle.n_room < 1:
        return ComponentVerdict("INFRASTRUCTURE_FAIL", "NOT_EVALUATED", "NOT_ADOPTED", "V4_H5_ROUTER_RULE", "NONFINITE_H5_DECISION_INPUT")
    if no_oracle.ci_low <= 0.0:
        return ComponentVerdict("COMPLETED", "NOT_ESTABLISHED", "NOT_ADOPTED", "V4_H5_ROUTER_RULE", "NO_ORACLE_INCREMENT_NOT_POSITIVE")
    router_fraction = 1.0 - after_oracle.estimate / no_oracle.estimate if no_oracle.estimate > 0.0 else math.nan
    if after_oracle.estimate <= .20 * no_oracle.estimate and after_oracle.ci_low <= 0.0 <= after_oracle.ci_high:
        return ComponentVerdict("COMPLETED", "SUPPORTED_ROUTER_DOMINANT", "NOT_ADOPTED", "V4_H5_ROUTER_RULE", "ORACLE_INCREMENT_SMALL_AND_NULL_COMPATIBLE")
    if router_fraction >= .80 and after_oracle.ci_low > 0.0:
        return ComponentVerdict("COMPLETED", "MIXED_ROUTER_MAJORITY_AND_WITHIN_REGIME", "NOT_ADOPTED", "V4_H5_ROUTER_RULE", "ROUTER_MAJORITY_WITH_POSITIVE_RESIDUAL_INCREMENT")
    if after_oracle.ci_low > .20 * no_oracle.estimate:
        return ComponentVerdict("COMPLETED", "REFUTED_ROUTER_DOMINANT", "NOT_ADOPTED", "V4_H5_ROUTER_RULE", "ORACLE_INCREMENT_REMAINS_LARGE")
    return ComponentVerdict("COMPLETED", "NOT_ESTABLISHED", "NOT_ADOPTED", "V4_H5_ROUTER_RULE", "PREREGISTERED_ROUTER_RULE_INCONCLUSIVE")


def derive_component_verdict(
    *,
    execution_status: str,
    required_inputs_present: bool,
    hard_gate_pass: bool,
    estimate: float = math.nan,
    ci_low: float = math.nan,
    ci_high: float = math.nan,
    positive_boot_fraction: float = math.nan,
    n_room: int = 0,
    minimum_rooms: int = 1,
    direction: int = 1,
    decision_rule_id: str = "V4_CLUSTERED_CI_SIGN",
    gate_failure_kind: str = "INFRASTRUCTURE_FAIL",
    execution_reason: str = "",
) -> ComponentVerdict:
    """Map execution, quality gates, and paired evidence to a v4 verdict.

    ``direction=1`` means positive estimates support the registered
    alternative; ``direction=-1`` reverses the comparison before applying the
    same rule.  No argument accepts a caller-supplied hypothesis label.
    """
    if str(execution_status).upper() == "SMOKE_COMPLETED":
        return ComponentVerdict("SMOKE_COMPLETED", "NOT_EVALUATED", "NOT_ADOPTED", decision_rule_id, execution_reason or "SMOKE_NOT_PRIMARY_ESTIMAND")
    completed = str(execution_status).upper() == "COMPLETED"
    if not required_inputs_present:
        return ComponentVerdict("NOT_RUN", "NOT_EVALUATED", "NOT_ADOPTED", decision_rule_id, execution_reason or "REQUIRED_INPUT_MISSING")
    if not completed:
        status = "BLOCKED" if str(execution_status).upper() == "BLOCKED" else str(execution_status)
        return ComponentVerdict(status, "NOT_EVALUATED", "NOT_ADOPTED", decision_rule_id, execution_reason or "EXECUTION_NOT_COMPLETED")
    if not hard_gate_pass or int(n_room) < int(minimum_rooms):
        kind = str(gate_failure_kind).upper()
        if kind not in {"INFRASTRUCTURE_FAIL", "SUPPORT_FAILURE"}:
            raise ValueError("gate_failure_kind must be INFRASTRUCTURE_FAIL or SUPPORT_FAILURE")
        reason = execution_reason or ("INSUFFICIENT_ROOM_SUPPORT" if int(n_room) < int(minimum_rooms) else "HARD_GATE_FAILED")
        return ComponentVerdict(kind, "NOT_EVALUATED", "NOT_ADOPTED", decision_rule_id, reason)
    values = np.asarray([estimate, ci_low, ci_high, positive_boot_fraction], dtype=float)
    if not np.isfinite(values).all():
        return ComponentVerdict("INFRASTRUCTURE_FAIL", "NOT_EVALUATED", "NOT_ADOPTED", decision_rule_id, execution_reason or "NONFINITE_DECISION_INPUT")
    sign = 1 if int(direction) >= 0 else -1
    adjusted_estimate, adjusted_low, adjusted_high = sign * float(estimate), sign * float(ci_low), sign * float(ci_high)
    positive = float(positive_boot_fraction) if sign > 0 else 1.0 - float(positive_boot_fraction)
    if adjusted_low > 0.0 and positive >= 0.975:
        outcome, reason = "SUPPORTED", "CI_AND_BOOTSTRAP_POSITIVE"
    elif adjusted_high < 0.0 and positive <= 0.025:
        outcome, reason = "REFUTED", "CI_AND_BOOTSTRAP_NEGATIVE"
    elif adjusted_low <= 0.0 <= adjusted_high:
        outcome, reason = "NOT_ESTABLISHED", "CI_CROSSES_NULL"
    else:
        outcome, reason = "MIXED", "CI_BOOTSTRAP_DISAGREEMENT"
    return ComponentVerdict("COMPLETED", outcome, "NOT_ADOPTED", decision_rule_id, execution_reason or reason)


def v4_component_row(
    component_id: str,
    *,
    primary_estimand: str,
    verdict: ComponentVerdict,
    estimate: float = math.nan,
    ci_low: float = math.nan,
    ci_high: float = math.nan,
    positive_boot_fraction: float = math.nan,
    n_case: int = 0,
    n_room: int = 0,
    controlled_comparison: bool = False,
    hard_gate_pass: bool = False,
    limitation_code: str = "",
    evidence_files: str = "",
) -> dict[str, object]:
    """Build a v4 status row from a centrally derived verdict only."""
    return {
        "component_id": component_id,
        "execution_status": verdict.execution_status,
        "hypothesis_outcome": verdict.hypothesis_outcome,
        "adoption_status": verdict.adoption_status,
        "decision_rule_id": verdict.decision_rule_id,
        "decision_reason": verdict.reason_code,
        "primary_estimand": primary_estimand,
        "estimate": float(estimate),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "positive_boot_fraction": float(positive_boot_fraction),
        "n_case": int(n_case),
        "n_room": int(n_room),
        "controlled_comparison": bool(controlled_comparison),
        "hard_gate_pass": bool(hard_gate_pass),
        "limitation_code": limitation_code,
        "evidence_files": evidence_files,
    }


def environment_record() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(), "numpy": np.__version__, "pandas": pd.__version__}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
