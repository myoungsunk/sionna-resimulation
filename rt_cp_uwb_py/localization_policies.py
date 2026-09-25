"""Branch-aware policy decisions for Paper 2 localization replays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


Q_FLOOR = 0.05
DEFAULT_Q_ACCEPT_THRESHOLD = 0.35
DEFAULT_NOLOS_REJECT_THRESHOLD = 0.85
DEFAULT_REFLECTION_SCAN_THRESHOLD = 0.55
DEFAULT_FALLBACK_Q_THRESHOLD = 0.20


@dataclass(frozen=True)
class PolicyConfig:
    q_floor: float = Q_FLOOR
    q_accept_threshold: float = DEFAULT_Q_ACCEPT_THRESHOLD
    nolos_reject_threshold: float = DEFAULT_NOLOS_REJECT_THRESHOLD
    reflection_scan_threshold: float = DEFAULT_REFLECTION_SCAN_THRESHOLD
    fallback_q_threshold: float = DEFAULT_FALLBACK_Q_THRESHOLD
    nolos_alpha: float = 3.0
    snr_floor: float = 0.05
    snr_low_db: float = 5.0
    snr_high_db: float = 30.0


@dataclass(frozen=True)
class PolicyDecision:
    policy_name: str
    accept_range: bool
    range_variance_scale: float
    scan_trigger: bool
    fallback_trigger: bool
    reflection_risk_flag: bool
    policy_status: str
    range_variance_scale_source: str
    reflection_range_multiplier_used: bool = False


POLICY_NAMES = (
    "nominal_no_weight",
    "snr_quality",
    "cir_only_qclean_gate",
    "cp_product_qclean_gate",
    "nolos_range_gate",
    "branch_aware_controller",
    "oracle_clean_gate",
    "reflection_wrong_range_weight_negative_control",
)


def _get(row: Mapping[str, object] | pd.Series, key: str, default: float = float("nan")) -> float:
    try:
        value = row[key]
    except KeyError:
        return default
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _prob(row: Mapping[str, object] | pd.Series, candidates: list[str], default: float = 0.5) -> float:
    for col in candidates:
        value = _get(row, col, float("nan"))
        if np.isfinite(value):
            return float(np.clip(value, 0.0, 1.0))
    return default


def _bool_prob(row: Mapping[str, object] | pd.Series, candidates: list[str], default: float = 0.0) -> float:
    for col in candidates:
        try:
            value = row[col]
        except KeyError:
            continue
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, str):
            low = value.strip().lower()
            if low in {"true", "t", "yes", "y", "1"}:
                return 1.0
            if low in {"false", "f", "no", "n", "0"}:
                return 0.0
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(f):
            return float(np.clip(f, 0.0, 1.0))
    return default


def _safe_q(value: float, floor: float) -> float:
    if not np.isfinite(value):
        return floor
    return float(np.clip(value, floor, 1.0))


def score_bundle(row: Mapping[str, object] | pd.Series) -> dict[str, float]:
    """Extract canonical score heads from a score row."""

    p_nolos = _prob(row, ["p_NoLoS_2H_CP", "p_NoLoS_3H_CP", "p_NoLoS_2H_CIR_only", "p_NoLoS_3H_CIR_only"], 0.5)
    p_nolos_cir = _prob(row, ["p_NoLoS_2H_CIR_only", "p_NoLoS_3H_CIR_only"], p_nolos)
    p_rd = _prob(row, ["p_RD_2H_CP", "p_RD_2H_CIR_only"], 0.0)
    p_hbprior = _prob(row, ["p_HBprior_3H_CP", "p_HBprior_3H_CIR_only"], 0.0)
    q_cp = _prob(
        row,
        [
            "q_clean_3H_CP_selected_calibrated",
            "q_clean_2H_CP_selected_calibrated",
            "q_clean_3H_CP",
            "q_clean_2H_CP",
        ],
        0.5,
    )
    q_cir = _prob(
        row,
        [
            "q_clean_3H_CIR_only_selected_calibrated",
            "q_clean_2H_CIR_only_selected_calibrated",
            "q_clean_3H_CIR_only",
            "q_clean_2H_CIR_only",
        ],
        0.5,
    )
    oracle = _bool_prob(row, ["oracle_clean_3H", "oracle_clean_2H", "Clean-LoS"], 0.0)
    snr_db = _get(row, "snr_db", float("nan"))
    return {
        "p_nolos": p_nolos,
        "p_nolos_cir": p_nolos_cir,
        "p_rd": p_rd,
        "p_hbprior": p_hbprior,
        "reflection_risk": max(p_rd, p_hbprior),
        "q_cp": q_cp,
        "q_cir": q_cir,
        "oracle_clean": oracle,
        "snr_db": snr_db,
    }


def snr_quality_score(snr_db: float, config: PolicyConfig = PolicyConfig()) -> float:
    if not np.isfinite(snr_db):
        return 0.5
    if config.snr_high_db <= config.snr_low_db:
        return 0.5
    return float(np.clip((snr_db - config.snr_low_db) / (config.snr_high_db - config.snr_low_db), config.snr_floor, 1.0))


def make_decision(policy_name: str, row: Mapping[str, object] | pd.Series, config: PolicyConfig = PolicyConfig()) -> PolicyDecision:
    scores = score_bundle(row)
    floor = config.q_floor

    if policy_name == "nominal_no_weight":
        return PolicyDecision(policy_name, True, 1.0, False, False, False, "OK", "constant")

    if policy_name == "snr_quality":
        quality = snr_quality_score(scores["snr_db"], config)
        accept = quality >= config.q_accept_threshold
        return PolicyDecision(policy_name, accept, 1.0 / _safe_q(quality, floor), False, not accept, False, "OK", "snr_quality")

    if policy_name == "cir_only_qclean_gate":
        q = _safe_q(scores["q_cir"], floor)
        accept = q >= config.q_accept_threshold
        return PolicyDecision(policy_name, accept, 1.0 / q, False, q < config.fallback_q_threshold, False, "OK", "q_clean_CIR_only")

    if policy_name == "cp_product_qclean_gate":
        q = _safe_q(scores["q_cp"], floor)
        accept = q >= config.q_accept_threshold
        reflection = scores["reflection_risk"] >= config.reflection_scan_threshold
        return PolicyDecision(policy_name, accept, 1.0 / q, False, q < config.fallback_q_threshold, reflection, "OK", "q_clean_CP_product")

    if policy_name == "nolos_range_gate":
        p_nolos = scores["p_nolos"]
        accept = p_nolos <= config.nolos_reject_threshold
        return PolicyDecision(
            policy_name,
            accept,
            1.0 + config.nolos_alpha * p_nolos,
            False,
            not accept,
            False,
            "OK",
            "p_NoLoS",
        )

    if policy_name == "branch_aware_controller":
        p_nolos = scores["p_nolos"]
        q = _safe_q(scores["q_cp"], floor)
        reflection = scores["reflection_risk"] >= config.reflection_scan_threshold
        accept = p_nolos <= config.nolos_reject_threshold
        fallback = (not accept) or q < config.fallback_q_threshold
        return PolicyDecision(
            policy_name,
            accept,
            1.0 + config.nolos_alpha * p_nolos,
            reflection,
            fallback,
            reflection,
            "OK",
            "p_NoLoS",
            reflection_range_multiplier_used=False,
        )

    if policy_name == "oracle_clean_gate":
        clean = scores["oracle_clean"] >= 0.5
        return PolicyDecision(policy_name, clean, 1.0 if clean else 20.0, False, not clean, False, "OK", "oracle_clean")

    if policy_name == "reflection_wrong_range_weight_negative_control":
        risk = scores["reflection_risk"]
        accept = risk <= config.nolos_reject_threshold
        return PolicyDecision(
            policy_name,
            accept,
            1.0 + config.nolos_alpha * risk,
            risk >= config.reflection_scan_threshold,
            not accept,
            risk >= config.reflection_scan_threshold,
            "NEGATIVE_CONTROL",
            "p_RD_or_p_HBprior",
            reflection_range_multiplier_used=True,
        )

    return PolicyDecision(policy_name, False, float("nan"), False, True, False, "UNKNOWN_POLICY", "unknown")


def all_policy_decisions(row: Mapping[str, object] | pd.Series, config: PolicyConfig = PolicyConfig()) -> list[PolicyDecision]:
    return [make_decision(policy, row, config) for policy in POLICY_NAMES]
