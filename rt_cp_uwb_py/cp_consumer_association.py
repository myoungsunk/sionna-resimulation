"""Phase-free candidate association adapter for CP consumer Thread 2.

The solver table produced here never contains evaluator truth.  Truth joins are
performed only by :func:`evaluate_candidate_predictions` after scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .cp_consumer_thread2_common import SchemaError, require_columns, require_no_runtime_truth, sha256_json


SCHEMA_VERSION = "cp_consumer_association_20260713.v3"
GROUP_KEYS = ("case_id", "trajectory_id", "time_id", "measurement_id")
CANDIDATE_KEY = "candidate_id"
PHASE_TOKENS = ("phase", "complex", "real_part", "imag_part", "iq_")
NULL_CANDIDATE_ID = "NULL"


def _scene_from_anchor(anchor_id: pd.Series) -> pd.Series:
    """Return the T0X scene token without consulting evaluator truth."""

    return anchor_id.astype(str).str.replace(r"-P[^-]*$", "", regex=True)


def normalize_t0x_association_truth(truth: pd.DataFrame) -> pd.DataFrame:
    """Normalize the evaluator-only T0X DA sidecar.

    This function is intentionally separate from candidate materialization so
    a solver process never needs to open the evaluator sidecar.
    """

    require_columns(
        truth,
        ("sequence_id", "time_idx", "measurement_id", "case_id", "truth_feature_id"),
        table_name="t0x_association_truth",
    )
    out = truth.rename(columns={"sequence_id": "trajectory_id", "time_idx": "time_id"}).copy()
    out["case_id"] = out["case_id"].astype(str)
    out["trajectory_id"] = out["trajectory_id"].astype(str)
    out["measurement_id"] = out["measurement_id"].astype(str)
    out["time_id"] = pd.to_numeric(out["time_id"], errors="raise").astype(int)
    truth_id = out["truth_feature_id"].fillna("").astype(str)
    is_null = truth_id.str.upper().isin({"", "CLUTTER", "NO_ASSOCIATION", "NONE", "NULL"})
    for column in ("truth_is_clutter", "truth_is_missed"):
        if column in out:
            is_null = is_null | out[column].fillna(False).astype(bool)
    out["truth_candidate_id"] = truth_id.mask(is_null, NULL_CANDIDATE_ID)
    keep = [*GROUP_KEYS, "truth_candidate_id"]
    optional = [
        column
        for column in ("truth_feature_type", "truth_is_clutter", "truth_is_missed", "truth_clean_association_possible")
        if column in out
    ]
    out = out[keep + optional].copy()
    if out.duplicated(list(GROUP_KEYS)).any():
        raise SchemaError("T0X evaluator truth contains duplicate measurement groups")
    return out


def materialize_t0x_candidate_features(
    measurements: pd.DataFrame,
    candidate_proposals: pd.DataFrame,
    matched_features: pd.DataFrame,
    *,
    trajectory_partitions: pd.DataFrame | None = None,
    source_join_registry: pd.DataFrame | None = None,
    runtime_pose_estimates: pd.DataFrame | None = None,
    measurement_feature_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """Build a truth-free, phase-free candidate table from T0X sources.

    Candidate proposals deliberately have no ``case_id``.  They are joined by
    scene plus ``(sequence_id, time_idx/created_at_timestep)`` only.  The
    encoded case suffix in a VA candidate ID is never parsed.  A NULL candidate
    is added to every measurement before scoring.
    """

    requested = validate_phase_free_features(measurement_feature_columns)
    require_no_runtime_truth(measurements, table_name="measurement_stream")
    require_no_runtime_truth(candidate_proposals, table_name="candidate_proposals")
    require_no_runtime_truth(matched_features, table_name="matched_cp_dlp_features")
    require_columns(
        measurements,
        (
            "sequence_id",
            "time_idx",
            "timestamp",
            "measurement_id",
            "case_id",
            "anchor_id",
            "range_m",
            "range_sigma_m",
        ),
        table_name="measurement_stream",
    )
    require_columns(
        candidate_proposals,
        ("timestamp", "sequence_id", "scene_id", "candidate_id", "candidate_type"),
        table_name="candidate_proposals",
    )
    require_columns(matched_features, ("case_id", *requested), table_name="matched_cp_dlp_features")

    measurement = measurements.rename(columns={"sequence_id": "trajectory_id", "time_idx": "time_id"}).copy()
    measurement["case_id"] = measurement["case_id"].astype(str)
    measurement["trajectory_id"] = measurement["trajectory_id"].astype(str)
    measurement["scene_id"] = _scene_from_anchor(measurement["anchor_id"])
    measurement["time_key"] = pd.to_numeric(measurement["time_id"], errors="raise").astype(int)
    if measurement.duplicated(["measurement_id"]).any():
        raise SchemaError("measurement_id must be unique")

    if source_join_registry is not None:
        require_no_runtime_truth(source_join_registry, table_name="static_trajectory_join_registry")
        require_columns(
            source_join_registry,
            ("case_id", "trajectory_id", "measurement_id", "source_manifest_hash"),
            table_name="static_trajectory_join_registry",
        )
        registry = source_join_registry[["case_id", "trajectory_id", "measurement_id", "source_manifest_hash"]].copy()
        registry["case_id"] = registry["case_id"].astype(str)
        registry["trajectory_id"] = registry["trajectory_id"].astype(str)
        registry["measurement_id"] = registry["measurement_id"].astype(str)
        if registry.duplicated(["measurement_id"]).any() or registry["source_manifest_hash"].fillna("").astype(str).eq("").any():
            raise SchemaError("source join registry requires unique measurements and non-empty source hashes")
        expected = measurement[["case_id", "trajectory_id", "measurement_id"]].astype(str)
        joined_registry = expected.merge(
            registry,
            on=["case_id", "trajectory_id", "measurement_id"],
            how="left",
            validate="one_to_one",
        )
        if joined_registry["source_manifest_hash"].isna().any():
            raise SchemaError("source join registry does not cover every measurement")

    features = matched_features[["case_id", *requested]].copy()
    features["case_id"] = features["case_id"].astype(str)
    if features.duplicated(["case_id"]).any():
        raise SchemaError("matched CP/DLP features must be one row per case_id")
    measurement = measurement.merge(features, on="case_id", how="left", validate="one_to_one", indicator=True)
    if not measurement["_merge"].eq("both").all():
        missing = int(measurement["_merge"].ne("both").sum())
        raise SchemaError(f"{missing} measurements lack matched CP/DLP features")
    measurement = measurement.drop(columns=["_merge"])

    proposals = candidate_proposals.copy()
    proposals["candidate_type"] = proposals["candidate_type"].fillna("UNKNOWN").astype(str).str.upper()
    proposals["scene_id"] = proposals["scene_id"].fillna("").astype(str)
    proposals["sequence_key"] = proposals["sequence_id"].fillna("").astype(str)
    inferred_scene = proposals["sequence_key"].str.replace(r"^(?:T0X_)?t0x_", "", regex=True)
    proposals["scene_id"] = proposals["scene_id"].mask(proposals["scene_id"].eq(""), inferred_scene)
    proposal_time = proposals["created_at_timestep"] if "created_at_timestep" in proposals else proposals["timestamp"]
    proposals["time_key"] = pd.to_numeric(proposal_time, errors="raise").astype(int)
    proposal_columns = [
        column
        for column in (
            "candidate_id",
            "candidate_type",
            "candidate_state_x",
            "candidate_state_y",
            "candidate_state_z",
            "support_count",
            "prior_logprob",
            "birth_source",
            "status",
        )
        if column in proposals
    ]

    # Surveyed PA rows are scene-level resources; VA rows are only eligible at
    # their own sequence/time.  This is the strongest join available without
    # inspecting candidate IDs or evaluator truth.
    base_columns = [
        "case_id",
        "trajectory_id",
        "time_id",
        "measurement_id",
        "scene_id",
        "anchor_id",
        "range_m",
        "range_sigma_m",
        "time_key",
        *requested,
    ]
    pa = proposals[proposals["candidate_type"].eq("PA")][["scene_id", *proposal_columns]].drop_duplicates()
    pa_rows = measurement[base_columns].merge(pa, on="scene_id", how="inner", validate="many_to_many")

    dynamic = proposals[~proposals["candidate_type"].eq("PA")][
        ["scene_id", "sequence_key", "time_key", *proposal_columns]
    ].drop_duplicates()
    dynamic_rows = measurement[base_columns].merge(
        dynamic,
        left_on=["scene_id", "trajectory_id", "time_key"],
        right_on=["scene_id", "sequence_key", "time_key"],
        how="inner",
        validate="many_to_many",
    )
    dynamic_rows = dynamic_rows.drop(columns=["sequence_key"])

    null_rows = measurement[base_columns].copy()
    null_rows["candidate_id"] = NULL_CANDIDATE_ID
    null_rows["candidate_type"] = "NULL"
    for column, value in (
        ("candidate_state_x", np.nan),
        ("candidate_state_y", np.nan),
        ("candidate_state_z", np.nan),
        ("support_count", 0),
        ("prior_logprob", 0.0),
        ("birth_source", "thread2_explicit_null"),
        ("status", "active"),
    ):
        if column in proposal_columns:
            null_rows[column] = value

    candidates = pd.concat([pa_rows, dynamic_rows, null_rows], ignore_index=True, sort=False)
    if candidates.empty:
        raise SchemaError("candidate adapter produced no rows")
    if candidates.duplicated([*GROUP_KEYS, CANDIDATE_KEY]).any():
        raise SchemaError("candidate adapter produced duplicate candidate IDs within a measurement")
    if not candidates.groupby(list(GROUP_KEYS))["candidate_id"].apply(
        lambda values: NULL_CANDIDATE_ID in set(values.astype(str))
    ).all():
        raise SchemaError("every measurement must contain an explicit NULL candidate")

    candidates["candidate_is_pa"] = candidates["candidate_type"].astype(str).eq("PA").astype(float)
    candidates["candidate_is_va"] = candidates["candidate_type"].astype(str).eq("VA").astype(float)
    candidates["candidate_is_null"] = candidates["candidate_type"].astype(str).eq("NULL").astype(float)
    expected_anchor = "A_" + candidates["anchor_id"].astype(str).str.replace("-", "_", regex=False)
    candidates["candidate_matches_anchor"] = candidates["candidate_id"].astype(str).eq(expected_anchor).astype(float)
    support_source = candidates["support_count"] if "support_count" in candidates else pd.Series(0.0, index=candidates.index)
    prior_source = candidates["prior_logprob"] if "prior_logprob" in candidates else pd.Series(0.0, index=candidates.index)
    candidates["candidate_support_log1p"] = np.log1p(
        pd.to_numeric(support_source, errors="coerce").fillna(0).clip(lower=0)
    )
    candidates["candidate_prior_logprob"] = pd.to_numeric(prior_source, errors="coerce").fillna(0.0)

    if runtime_pose_estimates is not None:
        require_no_runtime_truth(runtime_pose_estimates, table_name="runtime_pose_estimates")
        pose = runtime_pose_estimates.rename(
            columns={
                "sequence_id": "trajectory_id",
                "time_idx": "time_id",
                "x_m": "pose_x_m",
                "y_m": "pose_y_m",
                "z_m": "pose_z_m",
            }
        ).copy()
        require_columns(
            pose,
            ("trajectory_id", "time_id", "pose_x_m", "pose_y_m", "pose_z_m"),
            table_name="runtime_pose_estimates",
        )
        pose["trajectory_id"] = pose["trajectory_id"].astype(str)
        pose["time_id"] = pd.to_numeric(pose["time_id"], errors="raise").astype(int)
        if pose.duplicated(["trajectory_id", "time_id"]).any():
            raise SchemaError("runtime pose estimates must be one row per trajectory/time")
        candidates = candidates.merge(
            pose[["trajectory_id", "time_id", "pose_x_m", "pose_y_m", "pose_z_m"]],
            on=["trajectory_id", "time_id"],
            how="left",
            validate="many_to_one",
        )
        if candidates[["pose_x_m", "pose_y_m", "pose_z_m"]].isna().any().any():
            raise SchemaError("runtime pose estimates do not cover every candidate row")
        candidate_position = candidates[["candidate_state_x", "candidate_state_y", "candidate_state_z"]].apply(
            pd.to_numeric, errors="coerce"
        )
        pose_position = candidates[["pose_x_m", "pose_y_m", "pose_z_m"]].apply(pd.to_numeric, errors="coerce")
        pose_position.columns = candidate_position.columns
        distance = np.sqrt(np.square(candidate_position - pose_position).sum(axis=1))
        physical = candidates["candidate_type"].astype(str).isin({"PA", "VA"}) & np.isfinite(distance)
        observed_range = pd.to_numeric(candidates["range_m"], errors="coerce")
        sigma = pd.to_numeric(candidates["range_sigma_m"], errors="coerce").clip(lower=1e-3)
        residual = (observed_range - distance).abs()
        candidates["candidate_geometry_available"] = physical.astype(float)
        candidates["candidate_range_residual_abs_m"] = residual.where(physical, 0.0)
        candidates["candidate_range_log_score"] = (-0.5 * np.square(residual / sigma)).where(physical, 0.0)
    else:
        candidates["candidate_geometry_available"] = 0.0
        candidates["candidate_range_residual_abs_m"] = 0.0
        candidates["candidate_range_log_score"] = 0.0
    for column in requested:
        values = pd.to_numeric(candidates[column], errors="coerce")
        if not np.isfinite(values).all():
            raise SchemaError(f"measurement feature is non-finite: {column}")
        for candidate_type in ("pa", "va", "null"):
            candidates[f"{column}__x_{candidate_type}"] = values * candidates[f"candidate_is_{candidate_type}"]

    if trajectory_partitions is None:
        candidates["fold_id"] = "UNASSIGNED"
        candidates["split_role"] = "UNASSIGNED"
    else:
        require_columns(
            trajectory_partitions,
            ("trajectory_id", "fold_id", "split_role"),
            table_name="trajectory_partition_registry",
        )
        registry = trajectory_partitions[["trajectory_id", "fold_id", "split_role"]].copy()
        registry["trajectory_id"] = registry["trajectory_id"].astype(str)
        if registry.duplicated(["trajectory_id"]).any():
            raise SchemaError("trajectory partition registry must be one row per trajectory")
        candidates = candidates.merge(registry, on="trajectory_id", how="left", validate="many_to_one")
        if candidates[["fold_id", "split_role"]].isna().any().any():
            raise SchemaError("trajectory partition registry does not cover every candidate row")

    drop_columns = ["time_key"]
    candidates = candidates.drop(columns=[column for column in drop_columns if column in candidates])
    require_no_runtime_truth(candidates, table_name="candidate_features")
    return candidates.sort_values([*GROUP_KEYS, "candidate_id"], kind="mergesort").reset_index(drop=True)


@dataclass(frozen=True)
class AssociationModel:
    arm_id: str
    feature_columns: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coefficient: tuple[float, ...]
    intercept: float

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "arm_id": self.arm_id,
            "model_type": "standardized_logistic_candidate_ranker",
            "phase_free": True,
            "feature_columns": list(self.feature_columns),
            "mean": list(self.mean),
            "scale": list(self.scale),
            "coefficient": list(self.coefficient),
            "intercept": self.intercept,
        }
        payload["model_hash"] = sha256_json(payload)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssociationModel":
        return cls(
            arm_id=str(payload["arm_id"]),
            feature_columns=tuple(str(item) for item in payload["feature_columns"]),
            mean=tuple(float(item) for item in payload["mean"]),
            scale=tuple(float(item) for item in payload["scale"]),
            coefficient=tuple(float(item) for item in payload["coefficient"]),
            intercept=float(payload["intercept"]),
        )


@dataclass(frozen=True)
class AssociationCalibrator:
    temperature: float
    source_partition: str
    candidate_universe_hash: str
    model_hash: str

    def __post_init__(self) -> None:
        if not np.isfinite(self.temperature) or self.temperature <= 0.0:
            raise ValueError("calibration temperature must be finite and positive")

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "calibrator_type": "candidate_group_temperature_scaling",
            "temperature": float(self.temperature),
            "source_partition": self.source_partition,
            "candidate_universe_hash": self.candidate_universe_hash,
            "model_hash": self.model_hash,
        }
        payload["calibrator_hash"] = sha256_json(payload)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssociationCalibrator":
        return cls(
            temperature=float(payload["temperature"]),
            source_partition=str(payload["source_partition"]),
            candidate_universe_hash=str(payload["candidate_universe_hash"]),
            model_hash=str(payload["model_hash"]),
        )


def validate_phase_free_features(feature_columns: Sequence[str]) -> tuple[str, ...]:
    columns = tuple(str(column) for column in feature_columns)
    if not columns:
        raise SchemaError("at least one association feature is required")
    forbidden = [column for column in columns if any(token in column.lower() for token in PHASE_TOKENS)]
    if forbidden:
        raise SchemaError(f"phase-bearing features are excluded from the primary adapter: {forbidden}")
    return columns


def _training_rows(candidates: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    require_columns(candidates, (*GROUP_KEYS, CANDIDATE_KEY), table_name="candidate_features")
    require_no_runtime_truth(candidates, table_name="candidate_features")
    require_columns(truth, (*GROUP_KEYS, "truth_candidate_id"), table_name="association_truth")
    joined = candidates.merge(truth[list(GROUP_KEYS) + ["truth_candidate_id"]], on=list(GROUP_KEYS), how="inner", validate="many_to_one")
    if joined.empty:
        raise SchemaError("candidate/truth join is empty")
    joined["is_truth_candidate"] = joined[CANDIDATE_KEY].astype(str).eq(joined["truth_candidate_id"].astype(str)).astype(int)
    if joined["is_truth_candidate"].nunique() < 2:
        raise SchemaError("association training needs both positive and negative candidate rows")
    expected_groups = truth[list(GROUP_KEYS)].drop_duplicates().shape[0]
    positive_by_group = joined.groupby(list(GROUP_KEYS), sort=False)["is_truth_candidate"].sum()
    if len(positive_by_group) != expected_groups or not positive_by_group.eq(1).all():
        covered = int(positive_by_group.eq(1).sum())
        raise SchemaError(
            f"candidate coverage gate failed: {covered}/{expected_groups} groups have exactly one truth candidate"
        )
    return joined


def fit_candidate_ranker(
    candidates: pd.DataFrame,
    truth: pd.DataFrame,
    *,
    arm_id: str,
    feature_columns: Sequence[str],
) -> AssociationModel:
    columns = validate_phase_free_features(feature_columns)
    require_columns(candidates, columns, table_name="candidate_features")
    joined = _training_rows(candidates, truth)
    x = joined[list(columns)].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    if x.isna().any().any():
        raise SchemaError("association features must be finite after the frozen preprocessing step")
    mean = x.mean(axis=0).to_numpy(dtype=float)
    scale = x.std(axis=0, ddof=0).to_numpy(dtype=float)
    scale = np.where(scale > 1e-12, scale, 1.0)
    xz = (x.to_numpy(dtype=float) - mean) / scale
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)
    model.fit(xz, joined["is_truth_candidate"].to_numpy(dtype=int))
    return AssociationModel(
        arm_id=str(arm_id),
        feature_columns=columns,
        mean=tuple(float(value) for value in mean),
        scale=tuple(float(value) for value in scale),
        coefficient=tuple(float(value) for value in model.coef_[0]),
        intercept=float(model.intercept_[0]),
    )


def candidate_universe_hash(candidates: pd.DataFrame) -> str:
    require_columns(candidates, (*GROUP_KEYS, CANDIDATE_KEY, "candidate_type"), table_name="candidate_features")
    identity = candidates[[*GROUP_KEYS, CANDIDATE_KEY, "candidate_type"]].copy()
    identity = identity.astype(str).sort_values([*GROUP_KEYS, CANDIDATE_KEY], kind="mergesort")
    return sha256_json(identity.to_dict(orient="records"))


def candidate_truth_coverage_audit(candidates: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Audit label/universe coverage without evaluating model correctness.

    This is safe for Pre-P0 because it checks only whether the externally
    defined candidate identity is representable in the frozen runtime
    universe.  It does not inspect which candidate an arm selected and does
    not compute NLL or accuracy.
    """

    require_columns(candidates, (*GROUP_KEYS, CANDIDATE_KEY), table_name="candidate_features")
    require_no_runtime_truth(candidates, table_name="candidate_features")
    require_columns(truth, (*GROUP_KEYS, "truth_candidate_id"), table_name="association_truth")
    universe = candidates[[*GROUP_KEYS, CANDIDATE_KEY]].copy()
    evaluator = truth[[*GROUP_KEYS, "truth_candidate_id"]].drop_duplicates().copy()
    joined = evaluator.merge(universe, on=list(GROUP_KEYS), how="left", validate="one_to_many")
    matching = joined[CANDIDATE_KEY].astype(str).eq(joined["truth_candidate_id"].astype(str))
    covered = joined.loc[matching, list(GROUP_KEYS)].drop_duplicates()
    total = evaluator[list(GROUP_KEYS)].drop_duplicates()
    explicit_null = candidates.groupby(list(GROUP_KEYS), sort=False)[CANDIDATE_KEY].apply(
        lambda values: NULL_CANDIDATE_ID in set(values.astype(str).str.upper())
    )
    return pd.DataFrame(
        [
            {
                "measurement_group_count": int(len(total)),
                "covered_truth_group_count": int(len(covered)),
                "candidate_truth_coverage": float(len(covered) / max(len(total), 1)),
                "explicit_null_group_count": int(explicit_null.sum()),
                "explicit_null_coverage": float(explicit_null.mean()) if len(explicit_null) else 0.0,
                "status": "PASS"
                if len(covered) == len(total) and bool(explicit_null.all())
                else "BLOCKED_CANDIDATE_COVERAGE",
                "efficacy_values_read": 0,
            }
        ]
    )


def arm_selection_change_audit(cp_solver: pd.DataFrame, dlp_solver: pd.DataFrame) -> pd.DataFrame:
    """Compare solver actions without opening evaluator truth."""

    rows: list[pd.DataFrame] = []
    for arm, solver in (("CP", cp_solver), ("DLP", dlp_solver)):
        require_no_runtime_truth(solver, table_name=f"{arm}_candidate_solver_input")
        require_columns(solver, (*GROUP_KEYS, CANDIDATE_KEY, "selected_candidate"), table_name=f"{arm}_solver")
        selected = solver[solver["selected_candidate"].astype(bool)][[*GROUP_KEYS, CANDIDATE_KEY]].copy()
        if selected.duplicated(list(GROUP_KEYS)).any():
            raise SchemaError(f"{arm} solver selected multiple candidates in one group")
        selected = selected.rename(columns={CANDIDATE_KEY: f"{arm.lower()}_candidate_id"})
        rows.append(selected)
    joined = rows[0].merge(rows[1], on=list(GROUP_KEYS), how="outer", validate="one_to_one", indicator=True)
    if not joined["_merge"].eq("both").all():
        raise SchemaError("CP/DLP solver action universes differ")
    changed = joined["cp_candidate_id"].astype(str).ne(joined["dlp_candidate_id"].astype(str))
    return pd.DataFrame(
        [
            {
                "measurement_group_count": int(len(joined)),
                "selected_object_change_count": int(changed.sum()),
                "selected_object_change_rate": float(changed.mean()) if len(joined) else 0.0,
                "status": "PASS" if bool(changed.any()) else "BLOCKED_CONSUMER_NOOP",
                "efficacy_values_read": 0,
            }
        ]
    )


def _candidate_logits(candidates: pd.DataFrame, model: AssociationModel) -> np.ndarray:
    require_no_runtime_truth(candidates, table_name="candidate_features")
    require_columns(candidates, (*GROUP_KEYS, CANDIDATE_KEY, *model.feature_columns), table_name="candidate_features")
    x = candidates[list(model.feature_columns)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(x).all():
        raise SchemaError("candidate scoring features contain non-finite values")
    mean = np.asarray(model.mean, dtype=float)
    scale = np.asarray(model.scale, dtype=float)
    coefficient = np.asarray(model.coefficient, dtype=float)
    return ((x - mean) / scale) @ coefficient + model.intercept


def _group_softmax(frame: pd.DataFrame, logits: np.ndarray, *, temperature: float) -> np.ndarray:
    work = frame[list(GROUP_KEYS)].copy()
    work["_logit"] = np.asarray(logits, dtype=float) / float(temperature)
    maximum = work.groupby(list(GROUP_KEYS), sort=False)["_logit"].transform("max")
    exp_score = np.exp(np.clip(work["_logit"] - maximum, -80.0, 0.0))
    denominator = exp_score.groupby([work[key] for key in GROUP_KEYS], sort=False).transform("sum")
    return (exp_score / denominator.clip(lower=1e-15)).to_numpy(dtype=float)


def fit_temperature_calibrator(
    candidates: pd.DataFrame,
    truth: pd.DataFrame,
    model: AssociationModel,
    *,
    source_partition: str,
    temperature_grid: Sequence[float] = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0),
) -> AssociationCalibrator:
    """Fit a frozen scalar temperature on a calibration-only partition."""

    joined = _training_rows(candidates, truth)
    scoring_rows = joined.drop(columns=["truth_candidate_id", "is_truth_candidate"])
    logits = _candidate_logits(scoring_rows, model)
    best: tuple[float, float] | None = None
    for value in temperature_grid:
        temperature = float(value)
        if not np.isfinite(temperature) or temperature <= 0.0:
            raise ValueError("temperature grid must contain positive finite values")
        probability = _group_softmax(joined, logits, temperature=temperature)
        truth_probability = probability[joined["is_truth_candidate"].to_numpy(dtype=bool)]
        if len(truth_probability) != joined[list(GROUP_KEYS)].drop_duplicates().shape[0]:
            raise SchemaError("calibration partition lacks exactly one truth candidate per measurement")
        nll = float(-np.log(np.clip(truth_probability, 1e-15, 1.0)).mean())
        candidate = (nll, temperature)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise SchemaError("temperature calibration grid is empty")
    return AssociationCalibrator(
        temperature=best[1],
        source_partition=str(source_partition),
        candidate_universe_hash=candidate_universe_hash(candidates),
        model_hash=str(model.as_dict()["model_hash"]),
    )


def score_candidates(
    candidates: pd.DataFrame,
    model: AssociationModel,
    *,
    fold_id: str,
    prediction_role: str,
    split_role: str,
    calibrator: AssociationCalibrator | None = None,
) -> pd.DataFrame:
    logit = _candidate_logits(candidates, model)

    out = candidates[list(GROUP_KEYS) + [CANDIDATE_KEY]].copy()
    if "candidate_type" in candidates:
        out["candidate_type"] = candidates["candidate_type"].astype(str)
    else:
        out["candidate_type"] = "unknown"
    out["arm_id"] = model.arm_id
    out["fold_id"] = str(fold_id)
    out["prediction_role"] = str(prediction_role)
    out["score_raw"] = logit
    out["posterior_raw"] = _group_softmax(out, logit, temperature=1.0)
    if calibrator is not None:
        if calibrator.model_hash != str(model.as_dict()["model_hash"]):
            raise SchemaError("calibrator/model hash mismatch")
        out["posterior_calibrated"] = _group_softmax(out, logit, temperature=calibrator.temperature)
        posterior_column = "posterior_calibrated"
        calibrator_hash = calibrator.as_dict()["calibrator_hash"]
    else:
        posterior_column = "posterior_raw"
        calibrator_hash = "UNAVAILABLE"
    rank = out.groupby(list(GROUP_KEYS), sort=False)[posterior_column].rank(method="first", ascending=False)
    out["selected_candidate"] = rank.eq(1.0)
    out["split_role"] = str(split_role)
    model_payload = model.as_dict()
    out["feature_manifest_hash"] = sha256_json({"features": list(model.feature_columns), "phase_free": True})
    out["model_hash"] = str(model_payload["model_hash"])
    out["calibrator_hash"] = calibrator_hash
    require_no_runtime_truth(out, table_name="candidate_solver_input")
    return out


def evaluate_candidate_predictions(solver: pd.DataFrame, truth: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    require_no_runtime_truth(solver, table_name="candidate_solver_input")
    require_columns(solver, (*GROUP_KEYS, CANDIDATE_KEY, "selected_candidate"), table_name="candidate_solver_input")
    require_columns(truth, (*GROUP_KEYS, "truth_candidate_id"), table_name="candidate_evaluator_truth")
    selected = solver[solver["selected_candidate"].astype(bool)].copy()
    if selected.duplicated(list(GROUP_KEYS)).any():
        raise SchemaError("more than one selected candidate in a group")
    scored = selected.merge(truth, on=list(GROUP_KEYS), how="inner", validate="one_to_one")
    if scored.empty:
        raise SchemaError("solver/truth evaluator join is empty")
    scored["association_correct"] = scored[CANDIDATE_KEY].astype(str).eq(scored["truth_candidate_id"].astype(str))
    scored["null_selected"] = scored[CANDIDATE_KEY].astype(str).str.lower().isin({"null", "clutter", "none"})
    posterior_column = "posterior_calibrated" if "posterior_calibrated" in solver else "posterior_raw"
    require_columns(solver, (posterior_column,), table_name="candidate_solver_input")
    truth_scores = solver.merge(
        truth[[*GROUP_KEYS, "truth_candidate_id"]], on=list(GROUP_KEYS), how="right", validate="many_to_one"
    )
    truth_scores = truth_scores[truth_scores[CANDIDATE_KEY].astype(str).eq(truth_scores["truth_candidate_id"].astype(str))]
    covered_groups = truth_scores[list(GROUP_KEYS)].drop_duplicates()
    total_groups = truth[list(GROUP_KEYS)].drop_duplicates()
    coverage = len(covered_groups) / max(len(total_groups), 1)
    if truth_scores.duplicated(list(GROUP_KEYS)).any():
        raise SchemaError("evaluator found duplicate truth candidate rows")
    truth_probability = pd.to_numeric(truth_scores[posterior_column], errors="coerce").to_numpy(dtype=float)
    nll_sum = float(-np.log(np.clip(truth_probability, 1e-15, 1.0)).sum())
    nll_sum += float(len(total_groups) - len(covered_groups)) * float(-np.log(1e-15))
    metrics = {
        "n_groups": float(len(total_groups)),
        "candidate_coverage": float(coverage),
        "mean_posterior_nll": nll_sum / max(len(total_groups), 1),
        "association_accuracy": float(scored["association_correct"].mean()),
        "false_association_rate": float((~scored["association_correct"] & ~scored["null_selected"]).mean()),
        "null_selection_rate": float(scored["null_selected"].mean()),
        "selected_candidate_count": float(len(scored)),
    }
    return scored, metrics


def synthetic_association_fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    truth_rows: list[dict[str, Any]] = []
    for case_idx in range(8):
        truth_id = "va" if case_idx % 2 == 0 else "pa"
        truth_rows.append(
            {
                "case_id": f"c{case_idx}",
                "trajectory_id": "fixture",
                "time_id": case_idx,
                "measurement_id": f"m{case_idx}",
                "truth_candidate_id": truth_id,
            }
        )
        for candidate_id in ("pa", "va", "null"):
            is_truth = candidate_id == truth_id
            rows.append(
                {
                    "case_id": f"c{case_idx}",
                    "trajectory_id": "fixture",
                    "time_id": case_idx,
                    "measurement_id": f"m{case_idx}",
                    "candidate_id": candidate_id,
                    "candidate_type": candidate_id.upper(),
                    "cp_energy_ratio": 2.0 if is_truth else -1.0,
                    "cp_handedness_contrast": 1.0 if is_truth else -0.5,
                    "dlp_energy_ratio": 1.5 if is_truth else -0.8,
                }
            )
    candidates = pd.DataFrame(rows)
    truth = pd.DataFrame(truth_rows)
    train = candidates[candidates["time_id"] < 6].reset_index(drop=True)
    train_truth = truth[truth["time_id"] < 6].reset_index(drop=True)
    test = candidates[candidates["time_id"] >= 6].reset_index(drop=True)
    test_truth = truth[truth["time_id"] >= 6].reset_index(drop=True)
    return pd.concat([train, test], ignore_index=True), pd.concat([train_truth, test_truth], ignore_index=True), pd.DataFrame(
        [{"train_max_time": 5, "test_min_time": 6}]
    )
