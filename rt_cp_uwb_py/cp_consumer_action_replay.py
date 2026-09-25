"""Matched, truth-separated action replay for the CP consumer Lane C contract.

The runtime policy sees only a frozen OOF harm score and range observations.
Pose truth is supplied in a separate evaluator frame after each action has
already been selected and applied by the simulator.  This module establishes a
simulation action contract; it does not imply hardware or AMR superiority.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .localization import ekf_update_range, parse_xyz


ACTION_SPACE = (
    "ACCEPT_NOMINAL",
    "ACCEPT_INFLATED",
    "REJECT_FALLBACK",
)
POLICY_FAMILIES = ("CP", "DLP", "RANDOM")


def _uniform(seed: int, *parts: object) -> float:
    text = "|".join(str(part) for part in (seed, *parts)).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(text).digest()[:8], "big")
    return value / float(2**64)


def target_action(score_harm: float, accepted: bool, inflation_threshold: float) -> str:
    if not accepted:
        return "REJECT_FALLBACK"
    if score_harm >= inflation_threshold:
        return "ACCEPT_INFLATED"
    return "ACCEPT_NOMINAL"


def action_distribution(
    family: str,
    target: str,
    exploration_probability: float,
) -> dict[str, float]:
    """Return a frozen exploration distribution with support for every action."""

    if not 0.0 < exploration_probability < 1.0:
        raise ValueError("exploration_probability must be in (0, 1)")
    if family == "RANDOM":
        return {action: 1.0 / len(ACTION_SPACE) for action in ACTION_SPACE}
    if target not in ACTION_SPACE:
        raise ValueError(f"unknown target action: {target}")
    base = exploration_probability / len(ACTION_SPACE)
    out = {action: base for action in ACTION_SPACE}
    out[target] += 1.0 - exploration_probability
    return out


def sample_action(distribution: Mapping[str, float], draw: float) -> str:
    cumulative = 0.0
    for action in ACTION_SPACE:
        cumulative += float(distribution[action])
        if draw < cumulative:
            return action
    return ACTION_SPACE[-1]


def _score_columns(family: str) -> tuple[str, str]:
    if family == "CP":
        return "cp_p_harm_oof", "cp_accept"
    if family == "DLP":
        return "dlp_p_harm_oof", "dlp_accept"
    return "", ""


def replay_matched_action_policies(
    runtime_measurements: pd.DataFrame,
    oof_scores: pd.DataFrame,
    evaluator_pose: pd.DataFrame,
    *,
    config: Mapping[str, Any],
) -> dict[str, pd.DataFrame]:
    """Replay CP/DLP/RANDOM policies with common measurement support.

    ``runtime_measurements`` must exclude truth labels and coordinates.  The
    evaluator frame is indexed only after each selected action has been applied.
    """

    required_runtime = {
        "trajectory_id", "step_idx", "case_id", "anchor_id",
        "anchor_pose_xyz", "range_meas_rt_fp_m", "measurement_variance_nominal",
    }
    required_scores = {"case_id", "cp_p_harm_oof", "dlp_p_harm_oof", "cp_accept", "dlp_accept"}
    required_evaluator = {"trajectory_id", "step_idx", "truth_x_m", "truth_y_m"}
    missing_runtime = sorted(required_runtime - set(runtime_measurements.columns))
    missing_scores = sorted(required_scores - set(oof_scores.columns))
    missing_evaluator = sorted(required_evaluator - set(evaluator_pose.columns))
    if missing_runtime or missing_scores or missing_evaluator:
        raise ValueError(
            f"action replay schema gap: runtime={missing_runtime}, scores={missing_scores}, evaluator={missing_evaluator}"
        )
    if oof_scores["case_id"].duplicated().any():
        raise ValueError("OOF score table has duplicate case_id values")
    runtime = runtime_measurements.merge(
        oof_scores[list(required_scores)], on="case_id", how="left", validate="many_to_one"
    )
    if runtime[["cp_p_harm_oof", "dlp_p_harm_oof", "cp_accept", "dlp_accept"]].isna().any().any():
        missing = runtime.loc[
            runtime["cp_p_harm_oof"].isna() | runtime["dlp_p_harm_oof"].isna(), "case_id"
        ].astype(int).tolist()
        raise ValueError(f"OOF score coverage is incomplete: {missing[:10]}")
    pose_lookup = evaluator_pose.set_index(["trajectory_id", "step_idx"])[["truth_x_m", "truth_y_m"]]
    if pose_lookup.index.duplicated().any():
        raise ValueError("evaluator pose must have one row per trajectory/step")

    seed = int(config["seed"])
    exploration = float(config["exploration_probability"])
    inflation_threshold = float(config["inflation_harm_threshold"])
    inflation_scale = float(config["inflated_variance_scale"])
    initial_covariance = float(config["initial_covariance"])
    known_z_m = float(config["known_tag_z_m"])

    runtime_rows: list[dict[str, Any]] = []
    evaluator_rows: list[dict[str, Any]] = []
    optimized_rows: list[dict[str, Any]] = []
    for family in POLICY_FAMILIES:
        for trajectory_id, trajectory in runtime.sort_values(
            ["trajectory_id", "step_idx", "case_id"], kind="mergesort"
        ).groupby("trajectory_id", sort=True):
            state = np.zeros(2, dtype=float)
            covariance = np.eye(2, dtype=float) * initial_covariance
            for row in trajectory.itertuples(index=False):
                case_id = int(row.case_id)
                if family == "RANDOM":
                    score_harm = float("nan")
                    target = "ACCEPT_NOMINAL"
                else:
                    score_column, accept_column = _score_columns(family)
                    score_harm = float(getattr(row, score_column))
                    target = target_action(
                        score_harm,
                        bool(int(getattr(row, accept_column))),
                        inflation_threshold,
                    )
                distribution = action_distribution(family, target, exploration)
                draw = _uniform(seed, family, trajectory_id, int(row.step_idx), case_id)
                action = sample_action(distribution, draw)
                propensity = float(distribution[action])
                decision_id = f"C2_{family}_{trajectory_id}_s{int(row.step_idx):04d}_c{case_id:06d}"
                post_id = f"POST_{decision_id}"
                update_status = "REJECTED_BY_POLICY"
                if action != "REJECT_FALLBACK":
                    variance = float(row.measurement_variance_nominal)
                    if not np.isfinite(variance) or variance <= 0.0:
                        variance = 1e-4
                    if action == "ACCEPT_INFLATED":
                        variance *= inflation_scale
                    update = ekf_update_range(
                        state,
                        covariance,
                        parse_xyz(row.anchor_pose_xyz),
                        float(row.range_meas_rt_fp_m),
                        variance,
                        known_z_m,
                    )
                    update_status = str(update.status)
                    if update.status == "OK":
                        state = update.state
                        covariance = update.covariance
                try:
                    truth = pose_lookup.loc[(str(trajectory_id), int(row.step_idx))]
                except KeyError as exc:
                    raise ValueError(
                        f"missing evaluator pose for trajectory={trajectory_id}, step={row.step_idx}"
                    ) from exc
                pose_error = float(np.linalg.norm(state - np.array([float(truth.truth_x_m), float(truth.truth_y_m)])))
                runtime_rows.append(
                    {
                        "decision_id": decision_id,
                        "case_id": case_id,
                        "trajectory_id": str(trajectory_id),
                        "step_idx": int(row.step_idx),
                        "split": "development_simulation",
                        "policy_family": family,
                        "score_harm": score_harm,
                        "policy_target_action": target,
                        "action_id": action,
                        "baseline_action_id": "ACCEPT_NOMINAL",
                        "propensity": propensity,
                        "target_probability": propensity,
                        "random_draw": draw,
                        "assignment_seed": seed,
                        "action_space_id": "lane_c_accept_inflate_reject_v1",
                    }
                )
                evaluator_rows.append(
                    {
                        "decision_id": decision_id,
                        "post_action_observation_id": post_id,
                        "reward": -pose_error,
                        "post_action_pose_error_m": pose_error,
                        "trajectory_id": str(trajectory_id),
                        "step_idx": int(row.step_idx),
                        "post_action_timestamp": int(row.step_idx),
                    }
                )
                optimized_rows.append(
                    {
                        "arm_id": {"CP": "CP_FULL_PRE", "DLP": "DLP_FULL_PRE", "RANDOM": "RANDOM_POLICY"}[family],
                        "decision_id": decision_id,
                        "action_id": action,
                        "policy_family": family,
                        "post_action_observation_id": post_id,
                        "trajectory_id": str(trajectory_id),
                        "step_idx": int(row.step_idx),
                        "update_status": update_status,
                    }
                )

    action_runtime = pd.DataFrame(runtime_rows).sort_values("decision_id", kind="mergesort").reset_index(drop=True)
    action_evaluator = pd.DataFrame(evaluator_rows).sort_values("decision_id", kind="mergesort").reset_index(drop=True)
    optimized = pd.DataFrame(optimized_rows).sort_values("decision_id", kind="mergesort").reset_index(drop=True)
    action_support = (
        action_runtime.groupby(["policy_family", "action_id"], as_index=False)
        .agg(support_count=("decision_id", "size"), propensity=("propensity", "mean"))
        .sort_values(["policy_family", "action_id"], kind="mergesort")
        .reset_index(drop=True)
    )
    outcome_join = action_runtime[["decision_id", "policy_family", "trajectory_id"]].merge(
        action_evaluator[["decision_id", "post_action_pose_error_m", "reward"]],
        on="decision_id",
        how="inner",
        validate="one_to_one",
    )
    outcomes = (
        outcome_join.groupby(["policy_family", "trajectory_id"], as_index=False)
        .agg(
            mean_post_action_pose_error_m=("post_action_pose_error_m", "mean"),
            final_post_action_pose_error_m=("post_action_pose_error_m", "last"),
            mean_reward=("reward", "mean"),
            decision_count=("decision_id", "size"),
        )
        .sort_values(["policy_family", "trajectory_id"], kind="mergesort")
        .reset_index(drop=True)
    )
    return {
        "action_runtime": action_runtime,
        "action_evaluator": action_evaluator,
        "action_support": action_support,
        "optimized_trajectory": optimized,
        "trajectory_policy_outcomes": outcomes,
    }
