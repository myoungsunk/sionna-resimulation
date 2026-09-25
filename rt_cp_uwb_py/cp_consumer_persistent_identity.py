"""Truth-free geometric identity recovery for step-local T0X VA proposals.

Runtime functions in this module accept proposal geometry only.  Evaluator
truth is consumed by a separate function after runtime identities are frozen.
"""

from __future__ import annotations

from itertools import combinations, permutations
from typing import Any

import numpy as np
import pandas as pd

from .cp_consumer_thread2_common import SchemaError, require_columns, require_no_runtime_truth


SCHEMA_VERSION = "cp_consumer_persistent_identity_20260714.v2"
PROPOSAL_COLUMNS = (
    "sequence_id", "scene_id", "candidate_id", "candidate_type",
    "candidate_state_x", "candidate_state_y", "candidate_state_z",
    "created_at_timestep",
    "parent_measurement_id", "source_detection_track_id",
    "runtime_surface_track_id",
)


def _canonical_plane(pa: np.ndarray, va: np.ndarray, eps: float) -> tuple[np.ndarray, float] | None:
    delta = va - pa
    length = float(np.linalg.norm(delta))
    if length <= eps:
        return None
    normal = delta / length
    first = next((value for value in normal if abs(value) > eps), 1.0)
    if first < 0.0:
        normal = -normal
    offset = float(normal @ ((pa + va) / 2.0))
    return normal, offset


def _scene_for_sequence(sequence_id: str, scene_ids: list[str]) -> str:
    matches = [scene for scene in scene_ids if sequence_id.lower().endswith(scene.lower())]
    if len(matches) != 1:
        raise SchemaError(f"cannot resolve one scene for sequence {sequence_id!r}: {matches}")
    return matches[0]


def _parent_pa_from_measurement_id(measurement_id: Any) -> str:
    """Derive the surveyed-parent ID from the runtime measurement namespace.

    The exporter owns the measurement-ID format.  This parser intentionally
    consumes only that runtime identifier; it must never consult condition or
    RT evaluator columns to reconstruct the parent anchor.
    """

    text = str(measurement_id)
    marker = "_s"
    if marker not in text or "_c" not in text:
        raise SchemaError(f"invalid parent_measurement_id: {text!r}")
    tail = text.split(marker, 1)[1]
    try:
        _, anchor_and_case = tail.split("_", 1)
        anchor, _ = anchor_and_case.rsplit("_c", 1)
    except ValueError as exc:
        raise SchemaError(f"invalid parent_measurement_id: {text!r}") from exc
    if not anchor:
        raise SchemaError(f"parent_measurement_id has no anchor: {text!r}")
    return f"A_{anchor}"


def runtime_mapping_from_lineage(proposals: pd.DataFrame) -> pd.DataFrame:
    """Build the primary identity map from producer-owned runtime lineage.

    `source_detection_track_id` is a causal frontend track and
    `runtime_surface_track_id` is an online surface-tracker output.  Both are
    frozen before evaluator truth is opened.  Geometry-only reconstruction
    remains available below as a diagnostic, but is not allowed to silently
    replace the producer linkage for the readiness decision.
    """

    require_no_runtime_truth(proposals, table_name="runtime_candidate_proposals")
    require_columns(proposals, PROPOSAL_COLUMNS, table_name="runtime_candidate_proposals")
    va = proposals.loc[
        proposals["candidate_type"].astype(str).str.upper().eq("VA")
    ].copy()
    if va.empty:
        raise SchemaError("runtime candidate proposals contain no VA rows")
    if va["candidate_id"].astype(str).duplicated().any():
        raise SchemaError("VA candidate_id must be unique for lineage evaluation")
    lineage_columns = (
        "parent_measurement_id", "source_detection_track_id", "runtime_surface_track_id",
    )
    missing = [
        column for column in lineage_columns
        if va[column].isna().any() or va[column].astype(str).str.strip().eq("").any()
    ]
    if missing:
        raise SchemaError(f"runtime lineage is incomplete: {missing}")

    out = va[
        [
            "sequence_id", "created_at_timestep", "candidate_id",
            "parent_measurement_id", "source_detection_track_id",
            "runtime_surface_track_id",
        ]
    ].copy()
    out = out.rename(columns={"created_at_timestep": "time_id"})
    out["sequence_id"] = out["sequence_id"].astype(str)
    out["time_id"] = pd.to_numeric(out["time_id"], errors="raise").astype(int)
    out["parent_measurement_id"] = out["parent_measurement_id"].astype(str)
    out["source_detection_track_id"] = out["source_detection_track_id"].astype(str)
    out["runtime_surface_track_id"] = out["runtime_surface_track_id"].astype(str)
    out["parent_pa_candidate_id"] = out["parent_measurement_id"].map(
        _parent_pa_from_measurement_id
    )
    out["surface_observation_id"] = out["source_detection_track_id"]
    out["surface_track_id"] = out["runtime_surface_track_id"]
    out["runtime_persistent_id"] = (
        out["sequence_id"]
        + "::"
        + out["parent_pa_candidate_id"]
        + "::"
        + out["runtime_surface_track_id"]
    )
    out = out.sort_values(
        ["sequence_id", "time_id", "candidate_id"], kind="mergesort"
    ).reset_index(drop=True)
    require_no_runtime_truth(out, table_name="runtime_lineage_identity")
    return out


def reconstruct_surface_observations(
    proposals: pd.DataFrame,
    *,
    expected_anchor_count: int = 3,
    expected_surface_count: int = 3,
    descriptor_round_decimals: int = 6,
    zero_distance_epsilon_m: float = 1e-7,
) -> pd.DataFrame:
    """Recover mirror planes and parent PA assignments from runtime geometry.

    A valid surface observation is a set of one VA per surveyed PA that shares
    the same mirror plane.  If a PA lies on the plane, its VA equals the PA and
    is completed only after the other anchors identify that plane.
    """

    require_no_runtime_truth(proposals, table_name="runtime_candidate_proposals")
    require_columns(proposals, PROPOSAL_COLUMNS, table_name="runtime_candidate_proposals")
    frame = proposals.copy()
    for column in ("candidate_state_x", "candidate_state_y", "candidate_state_z"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["created_at_timestep"] = pd.to_numeric(frame["created_at_timestep"], errors="raise").astype(int)
    pa = frame[frame["candidate_type"].astype(str).str.upper().eq("PA")].copy()
    va = frame[frame["candidate_type"].astype(str).str.upper().eq("VA")].copy()
    if pa.empty or va.empty:
        raise SchemaError("both PA and VA runtime proposals are required")
    scene_ids = sorted(pa["scene_id"].dropna().astype(str).unique())
    rows: list[dict[str, Any]] = []

    for (sequence_id, time_id), step in va.groupby(["sequence_id", "created_at_timestep"], sort=True):
        sequence_id = str(sequence_id)
        scene = _scene_for_sequence(sequence_id, scene_ids)
        anchors = pa[pa["scene_id"].astype(str).eq(scene)].sort_values("candidate_id", kind="mergesort")
        if len(anchors) != expected_anchor_count or len(step) != expected_anchor_count * expected_surface_count:
            raise SchemaError(
                f"unexpected proposal cardinality at {sequence_id}/{time_id}: "
                f"PA={len(anchors)}, VA={len(step)}"
            )
        xyz = ("candidate_state_x", "candidate_state_y", "candidate_state_z")
        anchor_pos = {str(r.candidate_id): np.array([getattr(r, c) for c in xyz], dtype=float) for r in anchors.itertuples(index=False)}
        va_pos = {str(r.candidate_id): np.array([getattr(r, c) for c in xyz], dtype=float) for r in step.itertuples(index=False)}
        by_descriptor: dict[tuple[float, ...], list[tuple[str, str, np.ndarray, float]]] = {}
        zero_pairs: set[tuple[str, str]] = set()
        for va_id, vpos in va_pos.items():
            for pa_id, ppos in anchor_pos.items():
                plane = _canonical_plane(ppos, vpos, zero_distance_epsilon_m)
                if plane is None:
                    zero_pairs.add((va_id, pa_id))
                    continue
                normal, offset = plane
                key = tuple(np.round(np.r_[normal, offset], descriptor_round_decimals).tolist())
                by_descriptor.setdefault(key, []).append((va_id, pa_id, normal, offset))

        candidates: list[dict[str, Any]] = []
        for key, pairs in by_descriptor.items():
            target = expected_anchor_count if len(pairs) >= expected_anchor_count else expected_anchor_count - 1
            if target < 2:
                continue
            for subset in combinations(pairs, target):
                va_ids = {item[0] for item in subset}
                pa_ids = {item[1] for item in subset}
                if len(va_ids) != target or len(pa_ids) != target:
                    continue
                completed = list(subset)
                used_zero = False
                if target == expected_anchor_count - 1:
                    missing = set(anchor_pos) - pa_ids
                    options = sorted(pair for pair in zero_pairs if pair[1] in missing and pair[0] not in va_ids)
                    if len(missing) != 1 or len(options) != 1:
                        continue
                    zero_va, zero_pa = options[0]
                    normal = np.array(key[:3], dtype=float)
                    completed.append((zero_va, zero_pa, normal, float(key[3])))
                    used_zero = True
                if len(completed) == expected_anchor_count:
                    candidates.append({"key": key, "pairs": completed, "zero": used_zero})

        # Deduplicate equivalent subsets, then require a unique exact cover of all VA rows.
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for candidate in candidates:
            signature = (candidate["key"], tuple(sorted((p[0], p[1]) for p in candidate["pairs"])))
            unique[signature] = candidate
        candidates = list(unique.values())
        solutions = []
        all_va = set(va_pos)
        for subset in combinations(candidates, expected_surface_count):
            sets = [{pair[0] for pair in candidate["pairs"]} for candidate in subset]
            if len(set().union(*sets)) == len(all_va) and sum(map(len, sets)) == len(all_va):
                solutions.append(subset)
        if len(solutions) != 1:
            raise SchemaError(f"surface decomposition is not unique at {sequence_id}/{time_id}: {len(solutions)} solutions")
        ordered = sorted(solutions[0], key=lambda item: (item["key"], sorted(p[0] for p in item["pairs"])))
        for surface_index, candidate in enumerate(ordered):
            normal = np.array(candidate["key"][:3], dtype=float)
            offset = float(candidate["key"][3])
            observation_id = f"{sequence_id}::t{int(time_id):04d}::obs{surface_index}"
            for va_id, pa_id, _, _ in sorted(candidate["pairs"]):
                rows.append({
                    "sequence_id": sequence_id,
                    "time_id": int(time_id),
                    "candidate_id": va_id,
                    "parent_pa_candidate_id": pa_id,
                    "surface_observation_id": observation_id,
                    "plane_normal_x": float(normal[0]),
                    "plane_normal_y": float(normal[1]),
                    "plane_normal_z": float(normal[2]),
                    "plane_offset_m": offset,
                    "zero_displacement_completion": bool(candidate["zero"]),
                })
    output = pd.DataFrame(rows).sort_values(["sequence_id", "time_id", "candidate_id"], kind="mergesort").reset_index(drop=True)
    require_no_runtime_truth(output, table_name="runtime_surface_observations")
    return output


def track_surface_observations(
    observations: pd.DataFrame,
    *,
    expected_surface_count: int = 3,
    velocity_alpha: float = 0.5,
    normal_penalty: float = 10000.0,
) -> pd.DataFrame:
    """Assign persistent runtime track IDs using only plane continuity."""

    require_no_runtime_truth(observations, table_name="runtime_surface_observations")
    required = (
        "sequence_id", "time_id", "candidate_id", "parent_pa_candidate_id",
        "surface_observation_id", "plane_normal_x", "plane_normal_y",
        "plane_normal_z", "plane_offset_m",
    )
    require_columns(observations, required, table_name="runtime_surface_observations")
    out_parts: list[pd.DataFrame] = []
    for sequence_id, sequence in observations.groupby("sequence_id", sort=True):
        states: dict[int, dict[str, Any]] = {}
        for time_id, step_rows in sequence.groupby("time_id", sort=True):
            obs = step_rows.drop_duplicates("surface_observation_id").sort_values(
                ["plane_normal_x", "plane_normal_y", "plane_normal_z", "plane_offset_m"], kind="mergesort"
            )
            if len(obs) != expected_surface_count:
                raise SchemaError(f"expected {expected_surface_count} surfaces at {sequence_id}/{time_id}")
            records = list(obs.itertuples(index=False))
            if not states:
                assignment = {record.surface_observation_id: index for index, record in enumerate(records)}
            else:
                best: tuple[float, tuple[int, ...]] | None = None
                for perm in permutations(range(expected_surface_count)):
                    cost = 0.0
                    for record, track_id in zip(records, perm):
                        state = states[track_id]
                        normal = np.array([record.plane_normal_x, record.plane_normal_y, record.plane_normal_z], dtype=float)
                        alignment = float(np.clip(abs(normal @ state["normal"]), 0.0, 1.0))
                        predicted_offset = state["offset"] + state["velocity"]
                        cost += normal_penalty * (1.0 - alignment) + abs(float(record.plane_offset_m) - predicted_offset)
                    candidate = (cost, perm)
                    if best is None or candidate < best:
                        best = candidate
                assert best is not None
                assignment = {record.surface_observation_id: track_id for record, track_id in zip(records, best[1])}
            for record in records:
                track_id = assignment[record.surface_observation_id]
                normal = np.array([record.plane_normal_x, record.plane_normal_y, record.plane_normal_z], dtype=float)
                offset = float(record.plane_offset_m)
                previous = states.get(track_id)
                delta = 0.0 if previous is None else offset - float(previous["offset"])
                old_velocity = 0.0 if previous is None else float(previous["velocity"])
                states[track_id] = {
                    "normal": normal,
                    "offset": offset,
                    "velocity": velocity_alpha * delta + (1.0 - velocity_alpha) * old_velocity,
                }
            mapped = step_rows.copy()
            mapped["surface_track_id"] = mapped["surface_observation_id"].map(assignment).astype(int)
            mapped["runtime_persistent_id"] = mapped.apply(
                lambda row: f"{row['sequence_id']}::{row['parent_pa_candidate_id']}::surface_track_{int(row['surface_track_id'])}",
                axis=1,
            )
            out_parts.append(mapped)
    output = pd.concat(out_parts, ignore_index=True).sort_values(
        ["sequence_id", "time_id", "candidate_id"], kind="mergesort"
    ).reset_index(drop=True)
    require_no_runtime_truth(output, table_name="runtime_persistent_identity")
    return output


def evaluate_identity_readiness(
    runtime_mapping: pd.DataFrame,
    va_truth: pd.DataFrame,
    lifecycle_truth: pd.DataFrame,
    *,
    readiness_contract: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate a frozen runtime mapping; never returns truth into runtime APIs."""

    require_no_runtime_truth(runtime_mapping, table_name="runtime_persistent_identity")
    require_columns(runtime_mapping, ("candidate_id", "runtime_persistent_id", "parent_pa_candidate_id"), table_name="runtime_persistent_identity")
    require_columns(va_truth, ("candidate_id", "anchor_id", "condition_id", "condition_surface_id"), table_name="va_evaluation_truth")
    require_columns(lifecycle_truth, ("trajectory_id", "time_id", "persistent_truth_id", "truth_active"), table_name="lifecycle_evaluation_truth")
    truth = va_truth[["candidate_id", "anchor_id", "condition_id", "condition_surface_id"]].copy()
    truth["external_persistent_id"] = (
        truth["anchor_id"].astype(str) + "::" + truth["condition_id"].astype(str) + "::" + truth["condition_surface_id"].astype(str)
    )
    joined = runtime_mapping.merge(truth, on="candidate_id", how="left", validate="one_to_one")
    joined["runtime_anchor_norm"] = joined["parent_pa_candidate_id"].astype(str).str.replace(r"^A_", "", regex=True).str.replace("_", "-", regex=False).str.lower()
    joined["truth_anchor_norm"] = joined["anchor_id"].astype(str).str.lower()
    joined["parent_anchor_match"] = joined["runtime_anchor_norm"].eq(joined["truth_anchor_norm"])
    mapping_coverage = float(joined["external_persistent_id"].notna().mean())
    contingency = (
        joined.groupby(["runtime_persistent_id", "external_persistent_id"], dropna=False)
        .size().rename("row_count").reset_index()
    )
    runtime_degree = contingency.groupby("runtime_persistent_id")["external_persistent_id"].nunique()
    truth_degree = contingency.groupby("external_persistent_id")["runtime_persistent_id"].nunique()
    bijective_runtime = [rid for rid in runtime_degree[runtime_degree.eq(1)].index if truth_degree.get(contingency.loc[contingency["runtime_persistent_id"].eq(rid), "external_persistent_id"].iloc[0], 0) == 1]
    purity = contingency.groupby("runtime_persistent_id")["row_count"].max() / contingency.groupby("runtime_persistent_id")["row_count"].sum()
    transitions = 0
    life = lifecycle_truth.copy()
    life["truth_active"] = pd.to_numeric(life["truth_active"], errors="coerce").fillna(0).gt(0)
    for _, group in life.sort_values("time_id").groupby(["trajectory_id", "persistent_truth_id"], sort=False):
        transitions += int(group["truth_active"].astype(int).diff().fillna(0).ne(0).sum())
    contract = readiness_contract or {}
    expected_identity_count = int(contract.get("expected_external_identity_count", truth_degree.size))
    expected_transitions = int(contract.get("expected_external_transition_count", transitions))
    minimum_coverage = float(contract.get("minimum_mapping_coverage", 1.0))
    require_bijection = bool(contract.get("require_bijection", True))
    bijection_ok = (
        len(bijective_runtime) == runtime_degree.size == truth_degree.size
        if require_bijection
        else True
    )
    readiness_ok = bool(
        len(runtime_mapping)
        and mapping_coverage >= minimum_coverage
        and truth_degree.size == expected_identity_count
        and runtime_degree.size == expected_identity_count
        and len(bijective_runtime) == expected_identity_count
        and int(transitions) == expected_transitions
        and int(runtime_degree.gt(1).sum()) == 0
        and int(truth_degree.gt(1).sum()) == 0
        and float(joined["parent_anchor_match"].mean()) == 1.0
        and bijection_ok
    )
    metrics = pd.DataFrame([{
        "runtime_row_count": int(len(runtime_mapping)),
        "mapping_coverage": mapping_coverage,
        "runtime_persistent_id_count": int(runtime_degree.size),
        "external_persistent_id_count": int(truth_degree.size),
        "bijective_runtime_id_count": int(len(bijective_runtime)),
        "bijective_runtime_id_rate": float(len(bijective_runtime) / max(runtime_degree.size, 1)),
        "mixed_runtime_id_count": int(runtime_degree.gt(1).sum()),
        "fragmented_external_id_count": int(truth_degree.gt(1).sum()),
        "mean_dominant_identity_purity": float(purity.mean()),
        "minimum_dominant_identity_purity": float(purity.min()),
        "parent_anchor_accuracy": float(joined["parent_anchor_match"].mean()),
        "external_birth_death_transition_count": int(transitions),
        "mechanics_status": "PASS" if len(runtime_mapping) and mapping_coverage == 1.0 else "BLOCKED",
        "expected_external_identity_count": expected_identity_count,
        "expected_external_transition_count": expected_transitions,
        "minimum_mapping_coverage_required": minimum_coverage,
        "readiness_status": "PASS" if readiness_ok else "BLOCKED_RUNTIME_IDENTITY_OBSERVABILITY",
        "scientific_claim": "NOT_COMPUTED",
    }])
    return metrics, contingency, joined
