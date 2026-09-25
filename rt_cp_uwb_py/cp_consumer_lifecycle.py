"""Truth-free persistent candidate lifecycle and factor intervention adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .cp_consumer_thread2_common import SchemaError, require_columns, require_no_runtime_truth, sha256_json


SCHEMA_VERSION = "cp_consumer_lifecycle_20260713.v2"


@dataclass(frozen=True)
class LifecyclePolicy:
    active_threshold: float
    dormant_threshold: float
    prune_threshold: float
    min_support_count: int
    dormant_after_steps: int
    prune_after_steps: int
    factor_weight_floor: float = 0.05

    def __post_init__(self) -> None:
        probabilities = (self.active_threshold, self.dormant_threshold, self.prune_threshold, self.factor_weight_floor)
        if not all(0.0 <= value <= 1.0 for value in probabilities):
            raise ValueError("lifecycle probabilities must be in [0, 1]")
        if not self.active_threshold > self.dormant_threshold >= self.prune_threshold:
            raise ValueError("require active_threshold > dormant_threshold >= prune_threshold")
        if self.min_support_count < 1 or self.dormant_after_steps < 1 or self.prune_after_steps < self.dormant_after_steps:
            raise ValueError("invalid lifecycle count/age ordering")

    def as_dict(self) -> dict[str, Any]:
        payload = {"schema_version": SCHEMA_VERSION, **asdict(self)}
        payload["policy_hash"] = sha256_json(payload)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LifecyclePolicy":
        return cls(
            active_threshold=float(payload["active_threshold"]),
            dormant_threshold=float(payload["dormant_threshold"]),
            prune_threshold=float(payload["prune_threshold"]),
            min_support_count=int(payload["min_support_count"]),
            dormant_after_steps=int(payload["dormant_after_steps"]),
            prune_after_steps=int(payload["prune_after_steps"]),
            factor_weight_floor=float(payload.get("factor_weight_floor", 0.05)),
        )


@dataclass
class LandmarkState:
    candidate_id: str
    state: str = "birth"
    existence_prob: float = 0.0
    support_count: int = 0
    last_seen_step: int = -1
    factor_present: bool = False


def _factor_action(before: LandmarkState, after: LandmarkState, policy: LifecyclePolicy) -> tuple[str, float]:
    eligible = after.state in {"active", "reactivated"} and after.existence_prob >= policy.active_threshold
    if eligible and not before.factor_present:
        return "insert", max(policy.factor_weight_floor, after.existence_prob)
    if eligible and before.factor_present:
        return "reweight", max(policy.factor_weight_floor, after.existence_prob)
    if not eligible and before.factor_present:
        return "remove", 0.0
    return "none", 0.0


def run_lifecycle(
    solver_candidates: pd.DataFrame,
    policy: LifecyclePolicy,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Consume solver candidates only and return state/factor interventions.

    State is isolated per ``(arm_id, trajectory_id, candidate_id)``.  No truth
    table or evaluator callback is accepted by this API.
    """

    require_no_runtime_truth(solver_candidates, table_name="candidate_solver_input")
    required = (
        "arm_id",
        "trajectory_id",
        "time_id",
        "candidate_id",
        "selected_candidate",
    )
    require_columns(solver_candidates, required, table_name="candidate_solver_input")
    frame = solver_candidates.copy()
    posterior_column = "posterior_calibrated" if "posterior_calibrated" in frame else "posterior_raw"
    require_columns(frame, (posterior_column,), table_name="candidate_solver_input")
    duplicate_keys = ["arm_id", "trajectory_id", "time_id", "candidate_id"]
    if frame.duplicated(duplicate_keys).any():
        raise SchemaError("candidate solver input has duplicate arm/trajectory/time/candidate rows")
    selected_text = frame["selected_candidate"].astype(str).str.strip().str.lower()
    allowed_boolean = {"true", "false", "1", "0"}
    if not set(selected_text) <= allowed_boolean:
        raise SchemaError("selected_candidate must contain boolean values")
    frame["selected_candidate"] = selected_text.isin({"true", "1"})
    frame[posterior_column] = pd.to_numeric(frame[posterior_column], errors="raise")
    if not np.isfinite(frame[posterior_column]).all() or not frame[posterior_column].between(0.0, 1.0).all():
        raise SchemaError(f"{posterior_column} must be finite and in [0, 1]")
    if "candidate_type" in frame:
        # Surveyed PA and NULL are association alternatives, not persistent
        # landmarks controlled by this lifecycle adapter.
        frame = frame[frame["candidate_type"].astype(str).str.upper().eq("VA")].copy()
    else:
        frame = frame[~frame["candidate_id"].astype(str).str.upper().isin({"NULL", "CLUTTER", "NONE"})].copy()
    frame["time_id"] = pd.to_numeric(frame["time_id"], errors="raise").astype(int)
    frame = frame.sort_values(["arm_id", "trajectory_id", "time_id", "candidate_id"], kind="mergesort")

    states: dict[tuple[str, str, str], LandmarkState] = {}
    transition_rows: list[dict[str, Any]] = []
    factor_rows: list[dict[str, Any]] = []

    for row in frame.itertuples(index=False):
        key = (str(row.arm_id), str(row.trajectory_id), str(row.candidate_id))
        current = states.get(key, LandmarkState(candidate_id=key[2]))
        before = LandmarkState(**asdict(current))
        step = int(row.time_id)
        posterior = float(getattr(row, posterior_column))
        selected = bool(row.selected_candidate)
        if selected:
            current.support_count += 1
            current.last_seen_step = step
            current.existence_prob = posterior
            if current.support_count >= policy.min_support_count and posterior >= policy.active_threshold:
                current.state = "reactivated" if before.state in {"dormant", "pruned"} else "active"
            elif current.state == "birth":
                current.state = "tentative"
        else:
            age = step - current.last_seen_step if current.last_seen_step >= 0 else step + 1
            current.existence_prob = posterior
            if age >= policy.prune_after_steps and posterior <= policy.prune_threshold:
                current.state = "pruned"
            elif age >= policy.dormant_after_steps and posterior <= policy.dormant_threshold:
                current.state = "dormant"

        action, factor_weight = _factor_action(before, current, policy)
        current.factor_present = action in {"insert", "reweight"} or (action == "none" and before.factor_present)
        if action == "remove":
            current.factor_present = False
        states[key] = current

        transition_rows.append(
            {
                "arm_id": key[0],
                "trajectory_id": key[1],
                "time_id": step,
                "candidate_id": key[2],
                "state_before": before.state,
                "state_after": current.state,
                "existence_before": before.existence_prob,
                "existence_after": current.existence_prob,
                "support_before": before.support_count,
                "support_after": current.support_count,
                "selected_candidate": selected,
                "posterior_source_column": posterior_column,
                "transition_changed": before.state != current.state,
            }
        )
        factor_rows.append(
            {
                "arm_id": key[0],
                "trajectory_id": key[1],
                "time_id": step,
                "candidate_id": key[2],
                "factor_action": action,
                "factor_weight": factor_weight,
                "factor_present_before": before.factor_present,
                "factor_present_after": current.factor_present,
            }
        )

    state_rows = [
        {
            "arm_id": arm_id,
            "trajectory_id": trajectory_id,
            "candidate_id": candidate_id,
            **asdict(state),
        }
        for (arm_id, trajectory_id, candidate_id), state in sorted(states.items())
    ]
    transitions = pd.DataFrame(transition_rows)
    factors = pd.DataFrame(factor_rows)
    final_states = pd.DataFrame(state_rows)
    for name, output in (("lifecycle_transition_log", transitions), ("factor_intervention_log", factors), ("landmark_state", final_states)):
        require_no_runtime_truth(output, table_name=name)
    return transitions, factors, final_states


def noop_audit(transitions: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    transition_count = int(transitions.get("transition_changed", pd.Series(dtype=bool)).astype(bool).sum())
    factor_count = int(factors.get("factor_action", pd.Series(dtype=str)).astype(str).isin({"insert", "remove", "reweight"}).sum())
    return pd.DataFrame(
        [
            {
                "transition_intervention_count": transition_count,
                "factor_intervention_count": factor_count,
                "consumer_noop": transition_count == 0 or factor_count == 0,
                "status": "PASS" if transition_count > 0 and factor_count > 0 else "BLOCKED_CONSUMER_NOOP",
            }
        ]
    )


def persistent_identity_support_audit(
    runtime_candidates: pd.DataFrame,
    evaluator_truth: pd.DataFrame,
    *,
    runtime_id_column: str = "candidate_id",
    runtime_trajectory_column: str = "sequence_id",
    runtime_time_column: str = "created_at_timestep",
    truth_id_column: str = "persistent_truth_id",
    truth_trajectory_column: str = "trajectory_id",
    truth_time_column: str = "time_id",
    truth_active_column: str = "truth_active",
) -> pd.DataFrame:
    """Separate external truth availability from runtime identity support."""

    require_no_runtime_truth(runtime_candidates, table_name="runtime_candidate_proposals")
    require_columns(
        runtime_candidates,
        (runtime_id_column, runtime_trajectory_column, runtime_time_column),
        table_name="runtime_candidate_proposals",
    )
    require_columns(
        evaluator_truth,
        (truth_id_column, truth_trajectory_column, truth_time_column, truth_active_column),
        table_name="persistent_lifecycle_truth",
    )
    runtime = runtime_candidates[[runtime_id_column, runtime_trajectory_column, runtime_time_column]].copy()
    runtime[runtime_time_column] = pd.to_numeric(runtime[runtime_time_column], errors="raise").astype(int)
    runtime_span = runtime.groupby([runtime_trajectory_column, runtime_id_column], sort=False)[runtime_time_column].nunique()
    repeated_runtime = int(runtime_span.gt(1).sum())

    truth = evaluator_truth[[truth_id_column, truth_trajectory_column, truth_time_column, truth_active_column]].copy()
    truth[truth_time_column] = pd.to_numeric(truth[truth_time_column], errors="raise").astype(int)
    truth[truth_active_column] = pd.to_numeric(truth[truth_active_column], errors="coerce").fillna(0).gt(0)
    truth_span = truth.groupby([truth_trajectory_column, truth_id_column], sort=False)[truth_time_column].nunique()
    repeated_truth = int(truth_span.gt(1).sum())
    transitions = 0
    for _, group in truth.sort_values(truth_time_column).groupby(
        [truth_trajectory_column, truth_id_column], sort=False
    ):
        transitions += int(group[truth_active_column].astype(int).diff().fillna(0).ne(0).sum())

    runtime_ready = repeated_runtime > 0
    truth_ready = repeated_truth > 0 and transitions > 0
    if runtime_ready and truth_ready:
        status = "PASS"
        blocker = ""
    elif not runtime_ready:
        status = "BLOCKED_MISSING_RUNTIME_PERSISTENT_IDENTITY"
        blocker = "MISSING_RUNTIME_PERSISTENT_LANDMARK_IDENTITY"
    else:
        status = "BLOCKED_MISSING_EXTERNAL_EXISTENCE_HISTORY"
        blocker = "MISSING_EXTERNAL_PERSISTENT_EXISTENCE_HISTORY"
    return pd.DataFrame(
        [
            {
                "runtime_candidate_id_count": int(len(runtime_span)),
                "runtime_ids_spanning_multiple_steps": repeated_runtime,
                "external_persistent_id_count": int(len(truth_span)),
                "external_ids_spanning_multiple_steps": repeated_truth,
                "external_birth_death_transition_count": transitions,
                "runtime_identity_ready": runtime_ready,
                "external_truth_ready": truth_ready,
                "status": status,
                "blocker_code": blocker,
                "efficacy_values_read": 0,
            }
        ]
    )


def evaluate_persistent_lifecycle(
    transitions: pd.DataFrame,
    evaluator_mapping: pd.DataFrame,
    evaluator_truth: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate persistent lifecycle decisions after a valid identity join exists.

    ``evaluator_mapping`` is evaluator-only and must provide a stable mapping
    from a runtime candidate ID to one external persistent identity.  This
    function is intentionally separate from :func:`run_lifecycle`, so runtime
    code cannot access the mapping or truth.
    """

    require_no_runtime_truth(transitions, table_name="lifecycle_transition_log")
    require_columns(
        transitions,
        ("arm_id", "trajectory_id", "time_id", "candidate_id", "state_after"),
        table_name="lifecycle_transition_log",
    )
    require_columns(
        evaluator_mapping,
        ("trajectory_id", "candidate_id", "persistent_truth_id"),
        table_name="lifecycle_evaluator_mapping",
    )
    require_columns(
        evaluator_truth,
        ("trajectory_id", "time_id", "persistent_truth_id", "truth_active"),
        table_name="persistent_lifecycle_truth",
    )
    mapping = evaluator_mapping[["trajectory_id", "candidate_id", "persistent_truth_id"]].drop_duplicates()
    if mapping.duplicated(["trajectory_id", "candidate_id"]).any():
        raise SchemaError("runtime candidate maps to multiple persistent truth identities")
    decision = transitions.merge(mapping, on=["trajectory_id", "candidate_id"], how="left", validate="many_to_one")
    if decision["persistent_truth_id"].isna().any():
        raise SchemaError("persistent lifecycle evaluator mapping is incomplete")
    truth = evaluator_truth[["trajectory_id", "time_id", "persistent_truth_id", "truth_active"]].copy()
    truth["truth_active"] = pd.to_numeric(truth["truth_active"], errors="coerce").fillna(0).gt(0)
    joined = decision.merge(
        truth,
        on=["trajectory_id", "time_id", "persistent_truth_id"],
        how="left",
        validate="many_to_one",
    )
    if joined["truth_active"].isna().any():
        raise SchemaError("persistent lifecycle truth does not cover every runtime decision")
    joined["runtime_active"] = joined["state_after"].astype(str).isin({"active", "reactivated"})
    rows: list[dict[str, Any]] = []
    for arm_id, group in joined.groupby("arm_id", sort=True):
        false_active = (~group["truth_active"] & group["runtime_active"]).sum()
        truth_active = group["truth_active"].sum()
        recalled = (group["truth_active"] & group["runtime_active"]).sum()
        rows.append(
            {
                "arm_id": str(arm_id),
                "decision_count": int(len(group)),
                "false_active_duration_per_100_updates": float(100.0 * false_active / max(len(group), 1)),
                "map_recall": float(recalled / max(int(truth_active), 1)),
                "evaluator_join_coverage": 1.0,
            }
        )
    return pd.DataFrame(rows)


def synthetic_lifecycle_fixture() -> tuple[pd.DataFrame, LifecyclePolicy]:
    rows: list[dict[str, Any]] = []
    for time_id, posterior, selected in (
        (0, 0.60, True),
        (1, 0.85, True),
        (2, 0.10, False),
        (3, 0.05, False),
        (4, 0.90, True),
    ):
        rows.append(
            {
                "case_id": f"fixture_{time_id}",
                "arm_id": "CP_ALIGNED",
                "trajectory_id": "fixture",
                "time_id": time_id,
                "candidate_id": "va_1",
                "posterior_calibrated": posterior,
                "selected_candidate": selected,
            }
        )
    policy = LifecyclePolicy(
        active_threshold=0.70,
        dormant_threshold=0.30,
        prune_threshold=0.10,
        min_support_count=2,
        dormant_after_steps=1,
        prune_after_steps=2,
        factor_weight_floor=0.05,
    )
    return pd.DataFrame(rows), policy
