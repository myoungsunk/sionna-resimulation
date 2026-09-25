"""Fail-closed action-support and logged-policy evaluation helpers.

The helpers in this module keep runtime policy inputs separate from evaluator
outcomes.  They may establish that an action log is evaluable, but they do not
turn a deterministic replay or a structural pose smoke into a causal control
experiment.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .cp_consumer_control import effective_sample_size
from .cp_consumer_integration import truth_like_columns


REQUIRED_POLICY_FAMILIES = ("CP", "DLP", "RANDOM")
ACTION_RUNTIME_COLUMNS = (
    "decision_id",
    "case_id",
    "policy_family",
    "action_id",
    "baseline_action_id",
    "propensity",
    "target_probability",
)
ACTION_EVALUATOR_COLUMNS = (
    "decision_id",
    "post_action_observation_id",
    "reward",
)
ACTION_SUPPORT_COLUMNS = (
    "policy_family",
    "action_id",
    "support_count",
    "propensity",
)


def _missing(frame: pd.DataFrame, required: Sequence[str]) -> list[str]:
    return sorted(set(required) - set(frame.columns))


def audit_policy_support(
    runtime: pd.DataFrame,
    *,
    required_families: Sequence[str] = REQUIRED_POLICY_FAMILIES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit action-space parity and positivity without opening outcomes."""

    missing = _missing(runtime, ACTION_RUNTIME_COLUMNS)
    leaked = truth_like_columns(runtime.columns)
    if missing or leaked:
        return [], {
            "status": "BLOCKED",
            "missing_columns": missing,
            "runtime_truth_columns": leaked,
            "family_set": [],
            "action_space_parity": False,
            "positivity": False,
            "minimum_positive_propensity": None,
        }

    data = runtime.copy()
    data["policy_family"] = data["policy_family"].astype(str).str.upper()
    data["action_id"] = data["action_id"].astype(str)
    data["propensity"] = pd.to_numeric(data["propensity"], errors="coerce")
    data["target_probability"] = pd.to_numeric(
        data["target_probability"], errors="coerce"
    )
    rows: list[dict[str, Any]] = []
    action_sets: dict[str, tuple[str, ...]] = {}
    positivity_ok = True
    min_positive: list[float] = []
    for family in required_families:
        family_key = str(family).upper()
        part = data.loc[data["policy_family"] == family_key]
        actions = tuple(sorted(part["action_id"].dropna().unique()))
        action_sets[family_key] = actions
        target_supported = part["target_probability"] > 0.0
        finite = np.isfinite(part["propensity"].to_numpy(float))
        probability_range = part["propensity"].between(0.0, 1.0, inclusive="both")
        positive = bool(
            len(part)
            and finite.all()
            and probability_range.all()
            and (part.loc[target_supported, "propensity"] > 0.0).all()
        )
        positivity_ok = positivity_ok and positive
        positive_values = part.loc[part["propensity"] > 0.0, "propensity"]
        if not positive_values.empty:
            min_positive.append(float(positive_values.min()))
        rows.append(
            {
                "policy_family": family_key,
                "row_count": int(len(part)),
                "action_count": len(actions),
                "action_space": "|".join(actions),
                "target_supported_row_count": int(target_supported.sum()),
                "positivity_status": "PASS" if positive else "FAIL",
            }
        )

    required = {str(item).upper() for item in required_families}
    observed = set(data["policy_family"].dropna().unique())
    family_ready = required.issubset(observed)
    action_space_parity = bool(
        family_ready
        and action_sets
        and all(action_sets[item] for item in required)
        and len({action_sets[item] for item in required}) == 1
    )
    return rows, {
        "status": "PASS" if family_ready and action_space_parity and positivity_ok else "BLOCKED",
        "missing_columns": [],
        "runtime_truth_columns": [],
        "family_set": sorted(observed),
        "missing_families": sorted(required - observed),
        "action_space_parity": action_space_parity,
        "positivity": positivity_ok,
        "minimum_positive_propensity": min(min_positive) if min_positive else None,
    }


def audit_runtime_evaluator_join(
    runtime: pd.DataFrame,
    evaluator: pd.DataFrame,
    *,
    decision_column: str = "decision_id",
) -> dict[str, Any]:
    """Require an explicit one-to-one action-to-post-action observation join."""

    runtime_missing = _missing(runtime, ACTION_RUNTIME_COLUMNS)
    evaluator_missing = _missing(evaluator, ACTION_EVALUATOR_COLUMNS)
    runtime_truth = truth_like_columns(runtime.columns)
    if runtime_missing or evaluator_missing or runtime_truth:
        return {
            "status": "BLOCKED",
            "runtime_missing_columns": runtime_missing,
            "evaluator_missing_columns": evaluator_missing,
            "runtime_truth_columns": runtime_truth,
            "runtime_key_unique": False,
            "evaluator_key_unique": False,
            "matched_row_count": 0,
        }
    runtime_unique = not runtime[decision_column].duplicated().any()
    evaluator_unique = not evaluator[decision_column].duplicated().any()
    matched = runtime[[decision_column]].merge(
        evaluator[[decision_column]], on=decision_column, how="inner"
    )
    complete = len(matched) == len(runtime) == len(evaluator)
    return {
        "status": "PASS" if runtime_unique and evaluator_unique and complete else "BLOCKED",
        "runtime_missing_columns": [],
        "evaluator_missing_columns": [],
        "runtime_truth_columns": [],
        "runtime_key_unique": runtime_unique,
        "evaluator_key_unique": evaluator_unique,
        "matched_row_count": int(len(matched)),
        "runtime_row_count": int(len(runtime)),
        "evaluator_row_count": int(len(evaluator)),
        "complete_join": complete,
    }


def logged_policy_estimates(
    runtime: pd.DataFrame,
    evaluator: pd.DataFrame,
    *,
    required_families: Sequence[str] = REQUIRED_POLICY_FAMILIES,
) -> list[dict[str, Any]]:
    """Compute descriptive self-normalized IPW estimates after contract checks.

    These estimates become causal only when the caller separately verifies the
    assignment mechanism, action consistency, post-action timing, and absence
    of unmeasured confounding.
    """

    support_rows, support = audit_policy_support(
        runtime, required_families=required_families
    )
    join = audit_runtime_evaluator_join(runtime, evaluator)
    if support["status"] != "PASS" or join["status"] != "PASS":
        raise ValueError(
            f"logged-policy contract is not ready: support={support}, join={join}, rows={support_rows}"
        )
    merged = runtime.merge(evaluator, on="decision_id", how="inner", validate="one_to_one")
    merged["policy_family"] = merged["policy_family"].astype(str).str.upper()
    rows: list[dict[str, Any]] = []
    for family in required_families:
        family_key = str(family).upper()
        part = merged.loc[merged["policy_family"] == family_key].copy()
        behavior = pd.to_numeric(part["propensity"], errors="coerce").to_numpy(float)
        target = pd.to_numeric(part["target_probability"], errors="coerce").to_numpy(float)
        reward = pd.to_numeric(part["reward"], errors="coerce").to_numpy(float)
        weights = target / behavior
        estimate = float(np.sum(weights * reward) / np.sum(weights))
        rows.append(
            {
                "policy_family": family_key,
                "row_count": int(len(part)),
                "self_normalized_ipw_reward": estimate,
                "effective_sample_size": effective_sample_size(weights),
                "interpretation": "DESCRIPTIVE_LOGGED_POLICY_ESTIMATE",
            }
        )
    return rows


def audit_registry_policy_parity(
    registry: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit CP/DLP/RANDOM template presence and action-execution metadata."""

    raw_arms = registry.get("arms")
    arms = raw_arms if isinstance(raw_arms, Mapping) else {}
    buckets: dict[str, list[tuple[str, Mapping[str, Any]]]] = {
        item: [] for item in REQUIRED_POLICY_FAMILIES
    }
    for arm_id, raw in arms.items():
        if not isinstance(raw, Mapping):
            continue
        family = str(raw.get("family") or "").upper()
        arm_upper = str(arm_id).upper()
        if "RANDOM" in arm_upper or family == "RANDOM":
            buckets["RANDOM"].append((str(arm_id), raw))
        elif family in {"CP", "DLP"}:
            buckets[family].append((str(arm_id), raw))

    rows: list[dict[str, Any]] = []
    for family in REQUIRED_POLICY_FAMILIES:
        members = buckets[family]
        action_space_declared = any(
            bool(raw.get("action_space") or raw.get("action_space_id"))
            for _, raw in members
        )
        action_executor_declared = False
        action_output_declared = False
        for _, raw in members:
            argv = raw.get("command_argv_template")
            argv = [str(item) for item in argv] if isinstance(argv, list) else []
            action_executor_declared = action_executor_declared or any(
                token.startswith("--action")
                or token in {"--policy", "--behavior-policy", "--target-policy"}
                for token in argv
            )
            outputs = raw.get("expected_outputs")
            outputs = [str(item).lower() for item in outputs] if isinstance(outputs, list) else []
            action_output_declared = action_output_declared or any(
                "action" in item or "propensity" in item for item in outputs
            )
        rows.append(
            {
                "policy_family": family,
                "arm_count": len(members),
                "arm_ids": "|".join(arm_id for arm_id, _ in members),
                "template_present": bool(members),
                "action_space_declared": action_space_declared,
                "action_executor_declared": action_executor_declared,
                "action_output_declared": action_output_declared,
                "status": "PASS"
                if members
                and action_space_declared
                and action_executor_declared
                and action_output_declared
                else "BLOCKED",
            }
        )
    by_family = {row["policy_family"]: row for row in rows}
    cp_dlp_templates = bool(by_family["CP"]["template_present"] and by_family["DLP"]["template_present"])
    ready = all(row["status"] == "PASS" for row in rows)
    return rows, {
        "status": "PASS" if ready else "BLOCKED",
        "cp_dlp_template_pair_present": cp_dlp_templates,
        "random_policy_template_present": bool(by_family["RANDOM"]["template_present"]),
        "action_space_support_parity_established": ready,
    }

