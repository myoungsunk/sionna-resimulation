"""G1-MODEL-003 S2-F calculations on one chronological path at a time."""

import json

import numpy as np


def trailing_distance_mean(distance_m, e_mp, checkpoint_rows, window_m=5.0):
    """Return distance-weighted residual means and the full-window mask.

    Distance is cumulative travelled distance, in timeline order for one path.
    Packet k supplies the residual on [distance[k], distance[k+1]). Zero-distance
    intervals contribute no weight, so the last packet before movement supplies
    the next interval. The first interval can be clipped at the left boundary.
    Concatenated TEACH and REPEAT share distance history, with no weight for a
    zero-distance session transition. Each P-C path has its own distance origin.
    """
    distance = np.asarray(distance_m, dtype=float)
    residual = np.asarray(e_mp, dtype=float)
    rows = np.asarray(checkpoint_rows)
    if (distance.ndim != 1 or not distance.size or residual.shape != distance.shape
            or not np.isfinite(distance).all() or not np.isfinite(residual).all()
            or np.any(np.diff(distance) < 0)):
        raise ValueError("Expected finite ordered path distances and matching residuals")
    if (rows.ndim != 1 or (rows.size and not np.issubdtype(rows.dtype, np.integer))
            or np.any(rows < 0) or np.any(rows >= distance.size) or np.any(rows[1:] <= rows[:-1])):
        raise ValueError("Expected unique, increasing checkpoint row indices")
    if not np.isfinite(window_m) or window_m <= 0:
        raise ValueError("Window distance must be finite and positive")
    rows = rows.astype(np.intp)
    distance = distance - distance[0]
    at = distance[rows]
    # Cumulative summation at 0.2 s packet cadence can put an exact boundary
    # just below 5 m in binary64 arithmetic.
    tolerance_m = min(1e-12, 1e-12 * window_m)
    complete = at >= window_m - tolerance_m
    means = np.full(rows.shape, np.nan)
    prefix = np.r_[0.0, np.cumsum(np.diff(distance) * residual[:-1])]
    left = np.maximum(0.0, at[complete] - window_m)
    segment = np.searchsorted(distance, left, side="right") - 1
    left_integral = prefix[segment] + (left - distance[segment]) * residual[segment]
    means[complete] = (prefix[rows[complete]] - left_integral) / (at[complete] - left)
    return means, complete


def heading_rms(heading_rad):
    """Mean, population variance, and RMS about zero for signed headings."""
    h = np.asarray(heading_rad, dtype=float)
    if h.ndim != 1 or not np.isfinite(h).all():
        raise ValueError("Expected finite heading errors in radians")
    if not h.size:
        return dict(mean_rad=None, variance_rad2=None, rms_rad=None)
    return dict(mean_rad=float(h.mean()), variance_rad2=float(h.var()), rms_rad=float(np.sqrt(np.mean(h**2))))


def evaluate_path(anchors, g_min_s_per_rad):
    """Evaluate one path and one observation chain across all three anchors.

    Each anchor provides checkpoint_ids, mean_e_mp, boolean window_complete,
    sensitivity_s_per_rad, and dr_errors_rad. The last is a mapping from bias
    level or TB3 label to a (checkpoint, seed, sign) array. Checkpoints are in
    the same order in all arrays for that anchor. No filtering or angle wrapping
    is applied to the signed, already wrapped DR errors supplied in radians.
    """
    if len(anchors) != 3 or not np.isfinite(g_min_s_per_rad) or g_min_s_per_rad <= 0:
        raise ValueError("Expected three anchors and a positive sensitivity threshold in s/rad")
    levels = tuple(next(iter(anchors.values()))["dr_errors_rad"])
    if not levels or any(not isinstance(name, str) or not name for name in levels):
        raise ValueError("Expected named DR levels and TB3 points")
    levels = tuple(sorted(levels))
    pooled_h, pooled_dr = [], {level: [] for level in levels}
    dr_shapes, report = {}, {}
    for anchor, data in anchors.items():
        ids = [value.item() if isinstance(value, np.integer) else value
               for value in data["checkpoint_ids"]]
        complete = np.asarray(data["window_complete"])
        mean_e = np.asarray(data["mean_e_mp"], dtype=float)
        g = np.asarray(data["sensitivity_s_per_rad"], dtype=float)
        if (len(set(ids)) != len(ids) or complete.dtype != np.bool_
                or any(a.shape != (len(ids),) for a in (complete, mean_e, g))
                or not np.isfinite(mean_e[complete]).all() or not np.isfinite(g[complete]).all()):
            raise ValueError(f"Invalid S2-F checkpoint inputs for {anchor}")
        excluded = complete & (np.abs(g) < g_min_s_per_rad)
        valid = complete & ~excluded
        h = mean_e[valid] / g[valid]
        pooled_h.extend(h.tolist())
        n_window = int(complete.sum())
        n_excluded = int(excluded.sum())
        kept = np.flatnonzero(valid)
        report[anchor] = dict(
            total=len(ids), window_insufficient=int((~complete).sum()), sensitivity_excluded=n_excluded,
            sensitivity_exclusion_fraction=n_excluded / n_window if n_window else None,
            valid=len(kept), heading=heading_rms(h),
            checkpoints=[dict(id=ids[k], heading_error_rad=float(value))
                         for k, value in zip(kept, h, strict=True)],
        )
        dr = data["dr_errors_rad"]
        if set(dr) != set(levels):
            raise ValueError(f"DR comparison levels differ at {anchor}")
        for level in levels:
            errors = np.asarray(dr[level], dtype=float)
            if (errors.ndim != 3 or errors.shape[0] != len(ids) or not all(errors.shape[1:])
                    or dr_shapes.setdefault(level, errors.shape[1:]) != errors.shape[1:]
                    or not np.isfinite(errors[valid]).all()):
                raise ValueError(f"Invalid matched DR errors at {anchor}/{level}")
            means = np.mean(errors[valid] ** 2, axis=(1, 2))
            pooled_dr[level].extend(means.tolist())
            for checkpoint, mse in zip(report[anchor]["checkpoints"], means, strict=True):
                checkpoint.setdefault("dr_mse_rad2", {})[level] = float(mse)

    summary = heading_rms(pooled_h)
    levels_report = {}
    for level, means in pooled_dr.items():
        dr_rms = float(np.sqrt(np.mean(means))) if means else None
        if dr_rms is None:
            decision = "NOT_EVALUABLE"
        else:
            decision = "INCLUDE" if summary["rms_rad"] < dr_rms else "EXCLUDE"
        levels_report[level] = dict(dr_rmse_rad=dr_rms, accuracy_scope=decision)
    return dict(g_min_s_per_rad=float(g_min_s_per_rad), anchors=report, heading=summary,
                valid_checkpoints=len(pooled_h), levels=levels_report)


def self_check():
    """Check the three spec cases, distance integration, and matched weighting."""
    fixtures = {
        "constant_bias": ([0.02, 0.02], [0.10, 0.20], [0.20, 0.10], np.sqrt(0.025)),
        "zero_mean_variation": ([0.02, -0.02], [0.10, 0.10], [0.20, -0.20], 0.20),
        "zero_error": ([0.0, 0.0], [0.10, 0.20], [0.0, 0.0], 0.0),
    }

    # Only anchor A has eligible checkpoints in the three specified examples.
    absent = dict(checkpoint_ids=[0], mean_e_mp=[np.nan], window_complete=[False],
                  sensitivity_s_per_rad=[np.nan], dr_errors_rad={"L1": [[[np.nan]]]})
    checks = {}
    for name, (e, g, expected, rms) in fixtures.items():
        data = dict(checkpoint_ids=[0, 1], mean_e_mp=e, window_complete=[True, True],
                    sensitivity_s_per_rad=g, dr_errors_rad={"L1": [[[0.25]], [[0.25]]]})
        result = evaluate_path({"A": data, "B": absent, "C": absent}, 0.01)
        heading = [c["heading_error_rad"] for c in result["anchors"]["A"]["checkpoints"]]
        np.testing.assert_allclose(heading, expected, atol=1e-14, rtol=0)
        np.testing.assert_allclose(result["heading"]["rms_rad"], rms, atol=1e-14, rtol=0)
        checks[name] = dict(heading_error_rad=heading, rms_rad=result["heading"]["rms_rad"])

    mean, mask = trailing_distance_mean([0, 2, 2, 5, 7], [1, 99, 3, 4, 999], [0, 3, 4])
    np.testing.assert_array_equal(mask, [False, True, True])
    np.testing.assert_allclose(mean, [np.nan, 11 / 5, 17 / 5], atol=1e-14, rtol=0)
    mean, mask = trailing_distance_mean([0, 3, 6], [1, 4, 999], [2])
    np.testing.assert_array_equal(mask, [True])
    np.testing.assert_allclose(mean, [14 / 5], atol=1e-14, rtol=0)

    data_a = dict(checkpoint_ids=[0, 1], mean_e_mp=[0.03, 99], window_complete=[True, True],
                  sensitivity_s_per_rad=[-0.10, 0.009], dr_errors_rad={"L1": [[[1, -3]], [[np.nan, np.nan]]]})
    data_b = dict(checkpoint_ids=[3, 4], mean_e_mp=[0.01, 0.02], window_complete=[True, True],
                  sensitivity_s_per_rad=[0.10, 0.10], dr_errors_rad={"L1": [[[0, 0]], [[2, -2]]]})
    absent["dr_errors_rad"]["L1"] = [[[np.nan, np.nan]]]
    unequal = evaluate_path({"A": data_a, "B": data_b, "C": absent}, 0.01)
    np.testing.assert_allclose(unequal["heading"]["rms_rad"], np.sqrt(0.14 / 3), atol=1e-14, rtol=0)
    np.testing.assert_allclose(unequal["levels"]["L1"]["dr_rmse_rad"], np.sqrt(3), atol=1e-14, rtol=0)
    np.testing.assert_equal(unequal["anchors"]["A"]["sensitivity_exclusion_fraction"], 0.5)
    np.testing.assert_equal(unequal["levels"]["L1"]["accuracy_scope"], "INCLUDE")
    no_checkpoint = evaluate_path(dict.fromkeys("ABC", absent), 0.01)
    np.testing.assert_equal(no_checkpoint["levels"]["L1"]["accuracy_scope"], "NOT_EVALUABLE")
    exact = dict(checkpoint_ids=[0], mean_e_mp=[0.125], window_complete=[True],
                 sensitivity_s_per_rad=[0.5], dr_errors_rad={"L1": [[[0.25, -0.25]]]})
    equality = evaluate_path({"A": exact, "B": absent, "C": absent}, 0.5)
    np.testing.assert_equal(equality["anchors"]["A"]["valid"], 1)
    np.testing.assert_equal(equality["levels"]["L1"]["accuracy_scope"], "EXCLUDE")
    return dict(status="PASS", required_cases=checks, distance_windows="PASS", paired_weighting="PASS")


if __name__ == "__main__":
    print(json.dumps(self_check(), indent=2, allow_nan=False))
