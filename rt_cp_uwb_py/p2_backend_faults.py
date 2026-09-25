"""Feature-blind Paper 2 backend fault-control helpers.

The helpers in this module are intentionally pure DataFrame/array transforms.
They operate after CP/CIR prediction tables have been frozen and never inspect
feature, label, truth, or arm columns when constructing fault assignments.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Literal, Sequence

import numpy as np
import pandas as pd


EquivalenceDecision = Literal["EQUIVALENT_WITHIN_MARGIN", "NOT_ESTABLISHED"]
TimestampTarget = Literal[
    "range_only",
    "anchor_pose_only",
    "whole_measurement_packet",
]

_DEFAULT_EVALUATOR_COLUMNS = frozenset(
    {
        "arm_id",
        "evidence_arm",
        "cp_risk",
        "q_clean",
        "label",
        "truth_x_m",
        "truth_y_m",
        "true_range_m",
        "range_error_m",
    }
)


@dataclass(frozen=True)
class EvidenceFreeze:
    """Immutable digest of prediction columns before B4 fault injection."""

    columns: tuple[str, ...]
    row_count: int
    digest: str


@dataclass(frozen=True)
class FaultAssignment:
    """Deterministic, arm-independent fault assignment."""

    row_key_column: str
    mask: np.ndarray
    digest: str
    salt: str


@dataclass(frozen=True)
class GeometryAvailability:
    """Per-row geometry validity accounting for an observed anchor subset."""

    available: np.ndarray
    condition_number: np.ndarray
    min_eigenvalue: np.ndarray
    unavailable_count: int


def _require_columns(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")


def _stable_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def freeze_prediction_table(
    frame: pd.DataFrame,
    prediction_columns: Sequence[str],
) -> EvidenceFreeze:
    """Hash only frozen prediction/evidence columns in their current row order."""

    columns = tuple(prediction_columns)
    _require_columns(frame, columns)
    payload = {
        "columns": columns,
        "rows": frame.loc[:, list(columns)].to_dict(orient="split"),
    }
    return EvidenceFreeze(
        columns=columns,
        row_count=len(frame),
        digest=hashlib.sha256(_stable_json(payload)).hexdigest(),
    )


def assert_evidence_freeze_unchanged(
    before: EvidenceFreeze,
    frame: pd.DataFrame,
) -> None:
    """Raise if a post-fault table changed frozen prediction bytes."""

    after = freeze_prediction_table(frame, before.columns)
    if after != before:
        raise AssertionError(
            "prediction hash changed after feature-blind fault injection: "
            f"{before.digest} != {after.digest}"
        )


def deterministic_fault_assignment(
    frame: pd.DataFrame,
    *,
    row_key_column: str,
    fraction: float,
    seed: int,
    salt: str,
    exclude_columns: Iterable[str] = _DEFAULT_EVALUATOR_COLUMNS,
) -> FaultAssignment:
    """Create a deterministic assignment without using arm/evaluator columns."""

    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must lie in [0, 1]")
    _require_columns(frame, [row_key_column])
    forbidden = set(exclude_columns)
    if row_key_column in forbidden:
        raise ValueError(f"row_key_column cannot be evaluator-only: {row_key_column}")

    keys = [str(value) for value in frame[row_key_column].tolist()]
    scores = []
    for key in keys:
        digest = hashlib.sha256(f"{seed}|{salt}|{key}".encode("utf-8")).digest()
        scores.append(int.from_bytes(digest[:8], "big") / float(2**64))
    mask = np.asarray(scores, dtype=float) < fraction
    digest_payload = {
        "row_key_column": row_key_column,
        "salt": salt,
        "selected_keys": [key for key, selected in zip(keys, mask) if selected],
    }
    return FaultAssignment(
        row_key_column=row_key_column,
        mask=mask,
        digest=hashlib.sha256(_stable_json(digest_payload)).hexdigest(),
        salt=salt,
    )


def assert_same_fault_pairing(assignments: Sequence[FaultAssignment]) -> None:
    """Assert that all arms received the same feature-blind fault mask."""

    if not assignments:
        raise ValueError("at least one assignment is required")
    first = assignments[0]
    for assignment in assignments[1:]:
        if assignment.digest != first.digest or not np.array_equal(
            assignment.mask, first.mask
        ):
            raise AssertionError("fault assignment hash/mask differs across arms")


def apply_anchor_dropout(
    frame: pd.DataFrame,
    assignment: FaultAssignment,
    *,
    availability_column: str = "measurement_available",
) -> pd.DataFrame:
    """Mark assigned measurements unavailable in a copied frame."""

    if len(assignment.mask) != len(frame):
        raise ValueError("assignment length does not match frame")
    result = frame.copy(deep=True)
    if availability_column not in result.columns:
        result[availability_column] = True
    result.loc[assignment.mask, availability_column] = False
    return result


def inject_range_bias(
    frame: pd.DataFrame,
    assignment: FaultAssignment,
    *,
    range_column: str,
    bias_m: float,
) -> pd.DataFrame:
    """Add a feature-blind range bias to only the measured range column."""

    _require_columns(frame, [range_column])
    if len(assignment.mask) != len(frame):
        raise ValueError("assignment length does not match frame")
    result = frame.copy(deep=True)
    result.loc[assignment.mask, range_column] = (
        result.loc[assignment.mask, range_column].astype(float) + float(bias_m)
    )
    return result


def apply_backend_anchor_offset(
    frame: pd.DataFrame,
    assignment: FaultAssignment,
    *,
    x_column: str,
    y_column: str,
    offset_xy_m: tuple[float, float],
) -> pd.DataFrame:
    """Corrupt only backend anchor-coordinate metadata columns."""

    _require_columns(frame, [x_column, y_column])
    if len(assignment.mask) != len(frame):
        raise ValueError("assignment length does not match frame")
    result = frame.copy(deep=True)
    dx, dy = offset_xy_m
    result.loc[assignment.mask, x_column] = (
        result.loc[assignment.mask, x_column].astype(float) + float(dx)
    )
    result.loc[assignment.mask, y_column] = (
        result.loc[assignment.mask, y_column].astype(float) + float(dy)
    )
    return result


def shift_timestamp_packets(
    frame: pd.DataFrame,
    *,
    shift_steps: int,
    target: TimestampTarget,
    time_column: str = "step",
    packet_columns: Sequence[str] = (),
    group_columns: Sequence[str] = (),
    required_mask: Sequence[bool] | None = None,
) -> pd.DataFrame:
    """Shift selected packet columns within packet streams.

    ``group_columns`` identifies independent streams such as
    trajectory/schedule/replay/anchor.  The full ``group + time`` key must be
    unique, preventing accidental cross-trajectory packet joins.
    """

    if shift_steps == 0:
        return frame.copy(deep=True)
    group_columns = tuple(group_columns)
    merge_columns = [*group_columns, time_column]
    _require_columns(frame, [*merge_columns, *packet_columns])
    if not packet_columns:
        raise ValueError("packet_columns must name the columns to shift")
    if frame.duplicated(merge_columns).any():
        raise ValueError(
            f"packet stream key must be unique: {merge_columns}"
        )
    if required_mask is None:
        required = np.ones(len(frame), dtype=bool)
    else:
        required = np.asarray(required_mask, dtype=bool)
        if required.shape != (len(frame),):
            raise ValueError("required_mask length must match frame")

    packet_columns = tuple(packet_columns)
    result = frame.copy(deep=True)
    source = frame.loc[:, [*merge_columns, *packet_columns]].copy()
    source[time_column] = source[time_column] - shift_steps
    shifted = result[merge_columns].merge(
        source,
        on=merge_columns,
        how="left",
        validate="one_to_one",
    )
    missing = shifted.loc[:, list(packet_columns)].isna().any(axis=1).to_numpy()
    missing &= required
    if np.any(missing):
        missing_steps = result.loc[missing, time_column].tolist()
        raise ValueError(
            f"missing shifted {target} packets for steps: {missing_steps}"
        )
    for column in packet_columns:
        values = result[column].to_numpy(copy=True)
        values[required] = shifted.loc[required, column].to_numpy()
        result[column] = values
    return result


def geometry_availability_accounting(
    receiver_xy: np.ndarray,
    anchor_xy_by_row: Sequence[np.ndarray],
    *,
    min_anchor_count: int = 3,
    condition_limit: float = 1.0e8,
) -> GeometryAvailability:
    """Compute rank/conditioning availability without inventing geometry."""

    receiver = np.asarray(receiver_xy, dtype=float)
    if receiver.ndim != 2 or receiver.shape[1] != 2:
        raise ValueError("receiver_xy must have shape (n, 2)")
    if len(anchor_xy_by_row) != len(receiver):
        raise ValueError("anchor_xy_by_row length must match receiver rows")

    available = np.zeros(len(receiver), dtype=bool)
    condition_number = np.full(len(receiver), np.inf, dtype=float)
    min_eigenvalue = np.full(len(receiver), np.nan, dtype=float)

    for idx, anchors_value in enumerate(anchor_xy_by_row):
        anchors = np.asarray(anchors_value, dtype=float)
        if anchors.ndim != 2 or anchors.shape[1] != 2 or len(anchors) < min_anchor_count:
            continue
        delta = receiver[idx] - anchors
        ranges = np.linalg.norm(delta, axis=1)
        if np.any(ranges <= 0.0) or not np.all(np.isfinite(ranges)):
            continue
        jacobian = delta / ranges[:, None]
        normal = jacobian.T @ jacobian
        eigvals = np.linalg.eigvalsh(normal)
        min_eigenvalue[idx] = float(eigvals.min())
        if min_eigenvalue[idx] <= 0.0:
            continue
        condition_number[idx] = float(eigvals.max() / eigvals.min())
        available[idx] = condition_number[idx] <= condition_limit

    return GeometryAvailability(
        available=available,
        condition_number=condition_number,
        min_eigenvalue=min_eigenvalue,
        unavailable_count=int((~available).sum()),
    )


def equivalence_decision(
    *,
    ci_low: float,
    ci_high: float,
    margin_low: float,
    margin_high: float,
) -> EquivalenceDecision:
    """Return equivalence only when the full CI lies inside the pre-set margin."""

    values = np.asarray([ci_low, ci_high, margin_low, margin_high], dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("CI and margin values must be finite")
    if ci_low > ci_high:
        raise ValueError("ci_low must be <= ci_high")
    if margin_low > margin_high:
        raise ValueError("margin_low must be <= margin_high")
    if ci_low >= margin_low and ci_high <= margin_high:
        return "EQUIVALENT_WITHIN_MARGIN"
    return "NOT_ESTABLISHED"
