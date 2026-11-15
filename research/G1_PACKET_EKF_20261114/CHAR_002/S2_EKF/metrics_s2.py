"""Evaluator-only metrics for G1-CHAR-002 S2; see SPEC_S2_EKF_KO.md §§5–6."""

from dataclasses import dataclass

import numpy as np
from scipy.stats import chi2


ARMS = ("E0", "E1", "E2", "E3", "E4", "E5")
MOTION_TYPES = ("straight", "in_place", "curve", "stationary")
METRICS = (
    "heading_rmse_deg", "xy_rmse_cm", "mean_nees3", "pose95_coverage",
    "xy95_coverage", "heading95_coverage",
)
CONTRASTS = {
    ("E3", "E0"): METRICS,
    ("E2", "E1"): ("pose95_coverage", "heading_rmse_deg"),
    ("E3", "E2"): ("pose95_coverage", "heading_rmse_deg"),
}
POSE95_CUTOFF = chi2.ppf(0.95, 3)
XY95_CUTOFF = chi2.ppf(0.95, 2)


@dataclass(frozen=True)
class Trace:
    """Packet-aligned posterior and evaluator arrays. State angles are in rad."""

    time_s: np.ndarray
    x_hat: np.ndarray
    covariance: np.ndarray
    truth: np.ndarray
    extrapolated: np.ndarray
    folded_bearing_deg: np.ndarray
    segments: np.ndarray | None = None
    accepted: np.ndarray | None = None


def _wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


def classify_motion(truth):
    """Apply the CHAR-001 BLOCK_C thresholds to consecutive evaluator poses.

    The first row has no preceding interval and follows CHAR-001's stationary
    convention. For classification on the full RF grid, call before subsetting.
    """
    truth = np.asarray(truth, dtype=float)
    if truth.ndim != 2 or truth.shape[1] != 3 or not len(truth) or not np.isfinite(truth).all():
        raise ValueError("Motion classification needs finite (x, y, heading) rows")
    step = np.r_[0, np.linalg.norm(np.diff(truth[:, :2], axis=0), axis=1)]
    turn = np.r_[0, np.abs(np.degrees(_wrap(np.diff(truth[:, 2]))))]
    return np.where(
        step < 0.01,
        np.where(turn > 0.5, "in_place", "stationary"),
        np.where(turn > 0.5, "curve", "straight"),
    )


def _packet_rows(trace):
    time = np.asarray(trace.time_s, dtype=float)
    truth = np.asarray(trace.truth, dtype=float)
    x = np.asarray(trace.x_hat, dtype=float)
    covariance = np.asarray(trace.covariance, dtype=float)
    extrapolated = np.asarray(trace.extrapolated)
    bearing = np.asarray(trace.folded_bearing_deg, dtype=float)
    if time.ndim != 1 or len(time) == 0 or not (np.diff(time) > 0).all():
        raise ValueError("Packet times must be a nonempty, strictly increasing vector")
    n = len(time)
    if x.shape not in ((n, 4), (n, 5)) or covariance.shape != (n, x.shape[1], x.shape[1]):
        raise ValueError("Trace posterior must contain aligned four- or five-state rows")
    if truth.shape != (n, 3) or bearing.shape != (n,) or extrapolated.shape != (n,):
        raise ValueError("Truth, prior bearing and extrapolation mask must align with packets")
    if extrapolated.dtype.kind != "b" or not ((bearing >= 0) & (bearing < 180)).all():
        raise ValueError("Extrapolation must be boolean and folded bearing must lie in [0, 180)")
    if not all(np.isfinite(value).all() for value in (time, x, covariance, truth)):
        raise ValueError("Trace contains nonfinite times, states, covariance or truth")
    for field, value, valid in (
        ("segments", trace.segments, lambda v: np.isin(v, MOTION_TYPES).all()),
        ("accepted", trace.accepted, lambda v: v.dtype.kind == "b"),
    ):
        if value is not None:
            value = np.asarray(value)
            if value.shape != (n,) or not valid(value):
                raise ValueError(f"Invalid packet {field}")

    error = x[:, :3] - truth
    error[:, 2] = _wrap(error[:, 2])
    pose_covariance = covariance[:, :3, :3]
    if not np.allclose(pose_covariance, pose_covariance.swapaxes(1, 2), atol=1e-12, rtol=1e-10):
        raise ValueError("Pose covariance is asymmetric")
    np.linalg.cholesky(pose_covariance)
    xy_error = error[:, :2]
    pose_nees = np.einsum("ni,ni->n", error, np.linalg.solve(pose_covariance, error[..., None])[..., 0])
    xy_nees = np.einsum(
        "ni,ni->n", xy_error, np.linalg.solve(pose_covariance[:, :2, :2], xy_error[..., None])[..., 0],
    )
    rows = np.column_stack((
        np.degrees(error[:, 2]) ** 2,
        10000 * np.sum(xy_error ** 2, axis=1),
        pose_nees,
        pose_nees <= POSE95_CUTOFF,
        xy_nees <= XY95_CUTOFF,
        np.abs(error[:, 2]) <= 1.96 * np.sqrt(pose_covariance[:, 2, 2]),
    ))
    if not np.isfinite(rows).all():
        raise ValueError("Nonfinite per-packet metrics")
    return rows


def _reduce(means):
    reduced = means.copy()
    reduced[..., :2] = np.sqrt(reduced[..., :2])
    return reduced


def _summarize(rows):
    if not len(rows):
        return {"n": 0, **dict.fromkeys(METRICS)}
    return {"n": len(rows), **dict(zip(METRICS, _reduce(rows.mean(axis=0)).tolist()))}


def _summarize_groups(rows, traces):
    extrapolated = np.concatenate([trace.extrapolated for trace in traces])
    bearings = np.concatenate([trace.folded_bearing_deg for trace in traces])
    segments = [trace.segments for trace in traces]
    summary = _summarize(rows)
    summary["extrapolated"] = {
        "n": int(extrapolated.sum()), "fraction": float(extrapolated.mean()),
        "pose95_coverage": float(rows[extrapolated, 3].mean()) if extrapolated.any() else None,
    }
    if all(segment is not None for segment in segments):
        labels = np.concatenate(segments)
        summary["by_motion"] = {label: _summarize(rows[labels == label]) for label in MOTION_TYPES}
    else:
        summary["by_motion"] = None
    summary["by_prior_folded_bearing_deg"] = {}
    for low in range(0, 180, 15):
        mask = (bearings >= low) & (bearings < low + 15)
        summary["by_prior_folded_bearing_deg"][f"{low}-{low + 15}"] = {
            "n": int(mask.sum()),
            "heading95_coverage": float(rows[mask, 5].mean()) if mask.any() else None,
        }
    masks = [trace.accepted for trace in traces]
    summary["accepted"] = int(np.concatenate(masks).sum()) if all(m is not None for m in masks) else None
    return summary


def _moving_block_indices(time_s, block_s, repetitions, rng):
    """Draw full half-open time windows, then truncate each series to native length."""
    time_s = np.asarray(time_s, dtype=float)
    time_s = time_s - time_s[0]
    # Give the final packet one sample interval of support. Evaluate starts by
    # full elapsed time; no window crosses a trajectory boundary or wraps.
    end_time = time_s[-1] + (np.median(np.diff(time_s)) if len(time_s) > 1 else 0.0)
    tolerance = 16 * np.finfo(float).eps * max(end_time, block_s)
    starts = np.flatnonzero(time_s + block_s <= end_time + tolerance)
    if len(starts) == 0:
        raise ValueError(f"Trajectory is too short for {block_s:g} s moving blocks")
    stops = np.searchsorted(time_s, time_s[starts] + block_s - tolerance)
    length = len(time_s)
    if np.all(stops - starts == stops[0] - starts[0]):
        block_n = stops[0] - starts[0]
        starts_sampled = rng.choice(starts, size=(repetitions, (length + block_n - 1) // block_n))
        return (starts_sampled[..., None] + np.arange(block_n)).reshape(repetitions, -1)[:, :length]
    indices = np.empty((repetitions, length), dtype=np.intp)
    for replicate in indices:
        offset = 0
        while offset < length:
            draw = rng.integers(len(starts))
            count = min(stops[draw] - starts[draw], length - offset)
            replicate[offset:offset + count] = np.arange(starts[draw], starts[draw] + count)
            offset += count
    return indices


def _bootstrap(rows, times, pooled, *, seed, block_s, repetitions):
    rng = np.random.default_rng(seed)
    comparisons = tuple(dict.fromkeys(arm for pair in CONTRASTS for arm in pair))
    sums = {arm: np.zeros((repetitions, len(METRICS))) for arm in comparisons}
    n = 0
    for case, time in times.items():
        indices = _moving_block_indices(time, block_s, repetitions, rng)
        n += len(time)
        # Apply one common resample to all compared arms and all statistics.
        for arm in comparisons:
            for col in range(len(METRICS)):
                sums[arm][:, col] += rows[case][arm][:, col][indices].sum(axis=1)
    estimates = {arm: _reduce(values / n) for arm, values in sums.items()}
    result = {}
    for (first, second), metrics in CONTRASTS.items():
        diff = estimates[first] - estimates[second]
        lo, hi = np.quantile(diff, [0.025, 0.975], axis=0)
        result[f"{first}-{second}"] = {
            metric: {
                "difference": pooled[first][metric] - pooled[second][metric],
                "ci95": [float(lo[col]), float(hi[col])],
                "includes_zero": bool(lo[col] <= 0 <= hi[col]),
            }
            for col, metric in enumerate(METRICS) if metric in metrics
        }
    return result


def evaluate_stage(traces, *, expected_cases, bootstrap_seed):
    """Evaluate one complete stage from {case: {arm: Trace}}, with no arm filtering."""
    cases = tuple(expected_cases)
    if not cases or len(set(cases)) != len(cases) or set(traces) != set(cases):
        raise ValueError("Expected unique trajectory keys and exact stage input coverage")
    rows = {}
    by_case = {}
    for case in cases:
        if set(traces[case]) != set(ARMS):
            raise ValueError(f"{case}: expected exactly {', '.join(ARMS)}")
        base = traces[case]["E0"]
        rows[case] = {}
        by_case[case] = {}
        for arm in ARMS:
            trace = traces[case][arm]
            if not (np.array_equal(base.time_s, trace.time_s) and np.array_equal(base.truth, trace.truth)
                    and np.array_equal(base.segments, trace.segments)):
                raise ValueError(f"{case} {arm}: evaluator packet order, truth or segments differ from E0")
            rows[case][arm] = _packet_rows(trace)
            by_case[case][arm] = _summarize_groups(rows[case][arm], [trace])
    pooled = {
        arm: _summarize_groups(np.concatenate([rows[case][arm] for case in cases]),
                               [traces[case][arm] for case in cases])
        for arm in ARMS
    }
    times = {case: traces[case]["E0"].time_s for case in cases}
    e3_pose = pooled["E3"]["pose95_coverage"]
    e3_heading = pooled["E3"]["heading95_coverage"]
    severe = [case for case in cases if by_case[case]["E3"]["pose95_coverage"] < 0.75]
    costs = {}
    for metric in ("heading_rmse_deg", "xy_rmse_cm"):
        baseline, estimate = pooled["E0"][metric], pooled["E3"][metric]
        costs[metric] = {
            "delta_pct": 100 * (estimate / baseline - 1) if baseline else None,
            "verdict": "SMALL" if estimate <= 1.10 * baseline else "LARGE",
        }
    repetitions = 1500
    return {
        "by_case": by_case,
        "pooled": pooled,
        "bootstrap": {
            "repetitions": repetitions, "seed": int(bootstrap_seed),
            "blocks_s": {str(seconds): _bootstrap(rows, times, pooled, seed=bootstrap_seed,
                                                  block_s=seconds, repetitions=repetitions)
                         for seconds in (5, 10)},
        },
        "integrity": {
            "verdict": "INTEGRITY_PASS" if e3_pose >= 0.90 and not severe and e3_heading >= 0.90
                       else "INTEGRITY_FAIL",
            "pooled_pose95": e3_pose, "pooled_heading95": e3_heading, "severe_cases": severe,
        },
        "accuracy_cost": costs,
        "overconservatism_cost_e5_minus_e3_heading_rmse_deg":
            pooled["E5"]["heading_rmse_deg"] - pooled["E3"]["heading_rmse_deg"],
    }
