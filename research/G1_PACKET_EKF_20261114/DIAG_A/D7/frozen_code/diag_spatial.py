"""G1-DIAG-003 D4 and the common D3/D4 distance-window operation."""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares


MIN_WINDOW_M = 2.0
FIT_MIN_PAIRS_PER_BIN = 10
ROTATION_BIN_EDGES_DEG = np.array([0, 1, 2, 5, 10, 20, 40, 60, 90, 120, 180])


def wrap_radians(angle):
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def clean_channels(full_h, los_h, freqs_hz, *, tx=0):
    """Run the pinned first-path observation separately on clean full/LoS H."""
    from qclean_uwb.drivesim.observation import observe

    if full_h.shape != los_h.shape or full_h.ndim != 4:
        raise ValueError("D4 requires matching four-dimensional RF tensors")
    if len(freqs_hz) != full_h.shape[1]:
        raise ValueError("D4 frequency grid and channel lengths disagree")
    full = observe(full_h, freqs_hz, noise_var=None, rng=None, tx=tx)
    los = observe(los_h, freqs_hz, noise_var=None, rng=None, tx=tx)
    valid = full["detected"] & los["detected"]
    valid &= np.isfinite(full["s"]) & np.isfinite(los["s"])
    return {
        "s_full": full["s"], "s_los": los["s"],
        "tap_full": full["index"], "tap_los": los["index"],
        "range_full_m": full["range_m"], "range_los_m": los["range_m"],
        "valid": valid, "error": np.where(valid, full["s"] - los["s"], np.nan),
    }


def trajectory_inputs(distance, pose_xyyaw_rad, error):
    distance = np.asarray(distance, dtype=float)
    pose = np.asarray(pose_xyyaw_rad, dtype=float).copy()
    error = np.asarray(error, dtype=float)
    if distance.ndim != 1 or len(distance) == 0 or pose.shape != (len(distance), 3):
        raise ValueError("Expected a nonempty distance vector and matching XY-yaw poses")
    if error.shape != distance.shape:
        raise ValueError("Expected one error per pose")
    if not (np.isfinite(distance).all() and np.isfinite(pose).all()):
        raise ValueError("Distance and pose must be finite")
    if np.any(np.diff(distance) < 0):
        raise ValueError("Accumulated distance must be nondecreasing")
    pose[:, 2] = wrap_radians(pose[:, 2])
    return distance, pose, error


def unique_pose_indices(pose, indices):
    """Keep the earliest valid packet at each exact XY/wrapped-yaw pose."""
    _, first = np.unique(pose[indices], axis=0, return_index=True)
    return indices[np.sort(first)]


def moving_mean(distance, pose_xyyaw_rad, error, width_m):
    """Centered total-width window clipped at path ends, with a 2 m minimum."""
    distance, pose, error = trajectory_inputs(distance, pose_xyyaw_rad, error)
    if not np.isfinite(width_m) or width_m <= 0:
        raise ValueError("Window width must be positive and finite")
    width_m = max(float(width_m), MIN_WINDOW_M)
    start, end = distance[0], distance[-1]
    result = {
        "mean": np.full(len(distance), np.nan),
        "width_m": np.full(len(distance), np.nan),
        "n_pose": np.zeros(len(distance), dtype=int),
    }
    if end - start < MIN_WINDOW_M:
        return result
    left = np.maximum(distance - width_m / 2.0, start)
    right = np.minimum(distance + width_m / 2.0, end)
    too_narrow = right - left < MIN_WINDOW_M
    extend_right = too_narrow & (left == start)
    extend_left = too_narrow & (right == end)
    right[extend_right] = start + MIN_WINDOW_M
    left[extend_left] = end - MIN_WINDOW_M
    result["width_m"][:] = right - left
    lower = np.searchsorted(distance, left, side="left")
    upper = np.searchsorted(distance, right, side="right")
    valid = np.flatnonzero(np.isfinite(error))
    for row, (lo, hi) in enumerate(zip(lower, upper)):
        a, b = np.searchsorted(valid, [lo, hi])
        representatives = unique_pose_indices(pose, valid[a:b])
        result["n_pose"][row] = len(representatives)
        if len(representatives):
            result["mean"][row] = np.mean(error[representatives])
    return result


def moments(values):
    if len(values) == 0:
        return {"n": 0, "mean": None, "variance": None, "mean_square": None}
    return {
        "n": len(values), "mean": float(np.mean(values)),
        "variance": float(np.var(values)), "mean_square": float(np.mean(values**2)),
    }


def ratio(numerator, denominator):
    return None if denominator in (None, 0) else numerator / denominator


def exponential_fit(lags, variances):
    """Equal-bin least squares for 0.5 E[(e_i-e_j)^2], with a nonnegative nugget."""
    if len(lags) < 4 or not np.any(variances > 0):
        return {"status": "UNDEFINED_INSUFFICIENT_VARIATION", "length_m": None}
    smallest_lag, largest_lag = float(lags.min()), float(lags.max())
    lower_length, upper_length = smallest_lag / 10.0, largest_lag * 10.0
    scale = float(variances.max())
    y = variances / scale

    def residual(parameters):
        nugget, partial_sill, log_length = parameters
        return nugget - partial_sill * np.expm1(-lags / np.exp(log_length)) - y

    limits = ([0.0, 0.0, np.log(lower_length)], [np.inf, np.inf, np.log(upper_length)])
    attempts = [
        least_squares(
            residual, [0.1, 0.8, np.log(initial_length)], bounds=limits,
            ftol=1e-10, xtol=1e-10, gtol=1e-10,
        )
        for initial_length in [smallest_lag, np.sqrt(smallest_lag * largest_lag), largest_lag]
    ]
    result = min(attempts, key=lambda attempt: attempt.cost)
    nugget, partial_sill, log_length = result.x
    length = float(np.exp(log_length))
    status = "OK"
    if (
        not result.success
        or partial_sill <= 1e-8
        or np.isclose(length, lower_length, rtol=1e-5)
        or np.isclose(length, upper_length, rtol=1e-5)
    ):
        status = "UNDEFINED_UNIDENTIFIED_LENGTH"
    return {
        "status": status,
        "length_m": length if status == "OK" else None,
        "fit_candidate_length_m": length,
        "length_fit_bounds_m": [lower_length, upper_length],
        "nugget": float(nugget * scale), "partial_sill": float(partial_sill * scale),
        "fit_rmse": float(np.sqrt(np.mean(result.fun**2)) * scale),
    }


def distance_variogram(distance, pose, error):
    """Semivariance against along-path lag using positive-distance pose pairs."""
    indices = unique_pose_indices(pose, np.flatnonzero(np.isfinite(error)))
    i, j = np.triu_indices(len(indices), k=1)
    i, j = indices[i], indices[j]
    lags = distance[j] - distance[i]
    keep = lags > 0
    lags = lags[keep]
    semivariances = 0.5 * (error[j[keep]] - error[i[keep]]) ** 2
    edges = np.r_[np.arange(21) * 0.05, np.arange(5, 21) * 0.25,
                  np.arange(6.0, np.ceil(distance[-1] - distance[0]) + 1.0)]
    labels = np.searchsorted(edges, lags, side="right") - 1
    labels = np.minimum(labels, len(edges) - 2)
    counts = np.bincount(labels, minlength=len(edges) - 1)
    summed_lag = np.bincount(labels, weights=lags, minlength=len(counts))
    summed_semivariance = np.bincount(labels, weights=semivariances, minlength=len(counts))
    bins = []
    for k, count in enumerate(counts):
        bins.append({
            "from_m": float(edges[k]), "to_m": float(edges[k + 1]),
            "n_pairs": int(count),
            "mean_lag_m": float(summed_lag[k] / count) if count else None,
            "semivariance": float(summed_semivariance[k] / count) if count else None,
        })
    fit = counts >= FIT_MIN_PAIRS_PER_BIN
    fit_result = exponential_fit(summed_lag[fit] / counts[fit],
                                 summed_semivariance[fit] / counts[fit])
    return {
        "n_unique_pose": len(indices), "n_pairs": len(lags),
        "n_zero_distance_pairs_excluded": int((~keep).sum()),
        "fit_bin_min_pairs": FIT_MIN_PAIRS_PER_BIN, "n_fit_bins": int(fit.sum()),
        "lag_definition": "positive lag in cumulative path distance",
        "fit_definition": "equal-weight bin mean semivariance; nugget + partial_sill * (1 - exp(-lag / length))",
        "bins": bins, "exponential_fit": fit_result,
    }


def angular_exponential_fit(lags_deg, correlation):
    """Fit the nonnegative decaying correlation model to signed bin estimates."""
    if len(lags_deg) < 4 or not np.any(correlation > 0):
        return {"status": "UNDEFINED_INSUFFICIENT_VARIATION", "length_deg": None}
    smallest_lag, largest_lag = float(lags_deg.min()), float(lags_deg.max())
    lower_length, upper_length = smallest_lag / 10.0, largest_lag * 10.0

    def residual(parameters):
        amplitude, log_length = parameters
        return amplitude * np.exp(-lags_deg / np.exp(log_length)) - correlation

    limits = ([0.0, np.log(lower_length)], [1.0, np.log(upper_length)])
    attempts = [
        least_squares(
            residual, [0.5, np.log(initial_length)], bounds=limits,
            ftol=1e-10, xtol=1e-10, gtol=1e-10,
        )
        for initial_length in [smallest_lag, np.sqrt(smallest_lag * largest_lag), largest_lag]
    ]
    result = min(attempts, key=lambda attempt: attempt.cost)
    amplitude, log_length = result.x
    length = float(np.exp(log_length))
    status = "OK"
    if (
        not result.success or amplitude <= 1e-8
        or np.isclose(length, lower_length, rtol=1e-5)
        or np.isclose(length, upper_length, rtol=1e-5)
    ):
        status = "UNDEFINED_UNIDENTIFIED_LENGTH"
    return {
        "status": status,
        "length_deg": length if status == "OK" else None,
        "fit_candidate_length_deg": length,
        "length_fit_bounds_deg": [lower_length, upper_length],
        "amplitude": float(amplitude),
        "fit_rmse_correlation": float(np.sqrt(np.mean(result.fun**2))),
    }


def angular_correlation(pose, error, rotation_mask):
    """Pearson correlation in yaw-separation bins within contiguous turn segments."""
    boundaries = np.flatnonzero(np.diff(np.r_[False, rotation_mask, False]))
    segments = boundaries.reshape(-1, 2)
    left = []
    right = []
    for start, stop in segments:
        indices = unique_pose_indices(pose, np.flatnonzero(np.isfinite(error[start:stop])) + start)
        i, j = np.triu_indices(len(indices), k=1)
        left.append(indices[i])
        right.append(indices[j])
    i = np.concatenate(left) if left else np.empty(0, dtype=int)
    j = np.concatenate(right) if right else np.empty(0, dtype=int)
    separation_deg = np.degrees(np.abs(wrap_radians(pose[j, 2] - pose[i, 2])))
    labels = np.searchsorted(ROTATION_BIN_EDGES_DEG, separation_deg, side="right") - 1
    labels = np.minimum(labels, len(ROTATION_BIN_EDGES_DEG) - 2)
    bins = []
    for k, (a, b) in enumerate(zip(ROTATION_BIN_EDGES_DEG[:-1], ROTATION_BIN_EDGES_DEG[1:])):
        selected = labels == k
        x, y = error[i[selected]], error[j[selected]]
        corr = None
        if len(x) >= 3 and np.var(x) > 0 and np.var(y) > 0:
            corr = float(np.corrcoef(x, y)[0, 1])
        bins.append({
            "from_deg": int(a), "to_deg": int(b), "n_pairs": len(x), "pearson": corr,
            "mean_lag_deg": float(np.mean(separation_deg[selected])) if len(x) else None,
        })
    fit_bins = [
        b for b in bins
        if b["n_pairs"] >= FIT_MIN_PAIRS_PER_BIN and b["pearson"] is not None and b["mean_lag_deg"] > 0
    ]
    fit = angular_exponential_fit(
        np.array([b["mean_lag_deg"] for b in fit_bins]),
        np.array([b["pearson"] for b in fit_bins]),
    )
    return {
        "n_segments": len(segments), "n_pairs": len(i), "bins": bins,
        "lag_definition": "abs(wrap_180(yaw_j - yaw_i)); distinct poses within the same contiguous turn",
        "fit_definition": "equal-weight signed Pearson bins; amplitude * exp(-lag / length), amplitude in [0,1]",
        "fit_bin_min_pairs": FIT_MIN_PAIRS_PER_BIN, "n_fit_bins": len(fit_bins),
        "exponential_fit": fit,
    }


def spatial_summary(distance, pose_xyyaw_rad, e_mp, ds_dyaw_per_rad, *,
                    evaluation_mask, rotation_mask):
    """Summarize D4. Inputs are aligned on the original packet timeline."""
    distance, pose, error = trajectory_inputs(distance, pose_xyyaw_rad, e_mp)
    evaluation_mask = np.asarray(evaluation_mask, dtype=bool)
    rotation_mask = np.asarray(rotation_mask, dtype=bool)
    sensitivity = np.abs(np.asarray(ds_dyaw_per_rad, dtype=float))
    if any(x.shape != distance.shape for x in (evaluation_mask, rotation_mask, sensitivity)):
        raise ValueError("D4 masks and Jacobian must match the packet timeline")
    window = moving_mean(distance, pose, error, width_m=5.0)
    mean = window["mean"]
    eligible = evaluation_mask & np.isfinite(error) & np.isfinite(mean) & np.isfinite(sensitivity)
    idx = unique_pose_indices(pose, np.flatnonzero(eligible))
    raw = moments(error[idx])
    long = moments(mean[idx])
    quantiles = (
        [float(x) for x in np.quantile(sensitivity[idx], [0, 0.05, 0.5, 0.95, 1])]
        if len(idx) else None
    )
    rms = float(np.sqrt(long["mean_square"])) if len(idx) else None
    floor = ratio(rms, quantiles[2] if quantiles is not None else None)
    return {
        "classification": "DIAGNOSTIC_ONLY",
        "n_timeline_packets": len(distance), "n_clean_pairs": int(np.isfinite(error).sum()),
        "n_evaluation_packets": int(evaluation_mask.sum()),
        "n_valid_evaluation_packets": int(eligible.sum()),
        "n_evaluation_unique_pose": len(idx),
        "distance_variogram": distance_variogram(distance, pose, error),
        "rotation_yaw_correlation": angular_correlation(pose, error, rotation_mask),
        "long_5m": {
            "raw_error": raw, "moving_average": long,
            "centered_variance_ratio": ratio(long["variance"], raw["variance"]),
            "zero_based_mean_square_ratio": ratio(long["mean_square"], raw["mean_square"]),
            "jacobian_abs_per_rad_quantiles_min_p05_p50_p95_max": quantiles,
            "heading_floor_radians": floor,
            "heading_floor_degrees": float(np.degrees(floor)) if floor is not None else None,
            "pose_weighting": "equal unique pose; first valid occurrence",
        },
    }
