"""Paired scores and seed/site bootstrap for G1-DIAG-003 (§3)."""

from __future__ import annotations

import numpy as np


CHI1_95 = 3.841458820694124
CHI2_95 = 5.991464547107979
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20261114
STAT_COLUMNS = (
    "n", "heading_sq_rad2", "xy_sq_m2", "bias_sq_rad2_s2",
    "heading_nees", "xy_nees", "bias_nees",
    "heading95", "xy95", "bias95",
    "range_proposed", "range_accepted", "s_proposed", "s_accepted",
    "joint_proposed", "joint_accepted", "range_only_proposed", "range_only_accepted",
)
RATE_COLUMNS = (
    "heading_rmse_deg", "xy_rmse_m", "bias_rmse_dps",
    "heading_nees_mean", "xy_nees_mean", "bias_nees_mean",
    "heading95_coverage", "xy95_coverage", "bias95_coverage",
    "range_gate_reject_rate", "s_gate_reject_rate", "joint_gate_reject_rate",
    "range_only_gate_reject_rate",
)
COUNT_COLUMNS = STAT_COLUMNS[10:]


def checkpoints(t, pose):
    """Route-wide 1 m distance targets; match the nearest packet before t>=30."""
    t = np.asarray(t, dtype=float)
    pose = np.asarray(pose, dtype=float)
    if (t.ndim != 1 or t.size == 0 or pose.shape != (len(t), 3)
            or not np.isfinite(t).all() or not np.isfinite(pose).all()
            or np.any(np.diff(t) <= 0)):
        raise ValueError("checkpoint times must increase and truth must be [frame,3]")
    distance = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pose[:, :2], axis=0), axis=1))]
    targets = np.arange(int(np.floor(distance[-1])) + 1, dtype=float)
    upper = np.searchsorted(distance, targets, side="left")
    lower = np.maximum(upper - 1, 0)
    upper = np.minimum(upper, len(t) - 1)
    use_lower = (targets - distance[lower]) <= (distance[upper] - targets)
    nearest = np.where(use_lower, lower, upper)
    # On constant-distance plateaus use the earliest packet among exact ties.
    nearest = np.searchsorted(distance, distance[nearest], side="left")
    include = t[nearest] >= 30.0
    indices = nearest[include]
    return {
        "distance_m": distance,
        "checkpoint_index": indices,
        "site_id": np.floor(distance[indices]).astype(int),
        "checkpoint_distance_m": targets[include],
    }


def trajectory_statistics(state, covariance, accepted, joint, t, pose, true_bias,
                          checkpoint_index, proposal=None):
    """Return per-trajectory frame sums and per-trajectory checkpoint rows.

    The true bias is rad/s, scalar or one value per trajectory. Joint is the
    scheduled range+s mask; proposal is the range or range+s gate opportunity.
    DR may use proposal=False and accepted=False.
    """
    state = np.asarray(state)
    covariance = np.asarray(covariance)
    accepted = np.asarray(accepted)
    joint = np.asarray(joint)
    t = np.asarray(t)
    pose = np.asarray(pose)
    bias = np.asarray(true_bias)
    cp = np.asarray(checkpoint_index)
    if state.ndim != 3 or state.shape[-1] != 4:
        raise ValueError("state must be [trajectory,frame,4]")
    n_traj, n_frame, _ = state.shape
    shape = (n_traj, n_frame)
    if covariance.shape != (*shape, 4, 4) or pose.shape != (n_frame, 3) or t.shape != (n_frame,):
        raise ValueError("state, covariance, and truth frames must align")
    if bias.shape not in ((), (n_traj,)) or not np.isfinite(bias).all():
        raise ValueError("true_bias must be scalar or one finite rad/s value per trajectory")
    mask = t >= 30.0
    if not np.any(mask) or cp.ndim != 1 or cp.dtype.kind not in "iu":
        raise ValueError("no eligible evaluation frames or invalid checkpoint index")
    if np.any(cp < 0) or np.any(cp >= n_frame) or not np.all(mask[cp]):
        raise ValueError("checkpoint index lies outside t >= 30s evaluation")
    proposal = np.asarray(True if proposal is None else proposal)
    if any(a.dtype.kind != "b" for a in (accepted, joint, proposal)):
        raise ValueError("accepted, joint, proposal must be bool")
    accepted = np.broadcast_to(accepted, shape)
    joint = np.broadcast_to(joint, shape)
    proposal = np.broadcast_to(proposal, shape)
    if np.any(accepted & ~proposal):
        raise ValueError("accepted gate outside proposal mask")

    error = state[:, mask, :3] - pose[None, mask]
    error[..., 2] = (error[..., 2] + np.pi) % (2 * np.pi) - np.pi
    bias_error = state[:, mask, 3] - bias[..., None]
    c = covariance[:, mask]
    if not np.isfinite(error).all() or not np.isfinite(bias_error).all() or not np.isfinite(c).all():
        raise ValueError("nonfinite state or covariance in scoring window")
    heading_sq = error[..., 2]**2
    xy_sq = np.sum(error[..., :2]**2, axis=-1)
    bias_sq = bias_error**2
    xy = c[..., :2, :2]
    if (np.any(c[..., 2, 2] <= 0) or np.any(c[..., 3, 3] <= 0)
            or np.any(xy[..., 0, 0] <= 0) or np.any(np.linalg.det(xy) <= 0)):
        raise ValueError("non-positive marginal covariance in scoring window")
    heading_nees = heading_sq / c[..., 2, 2]
    xy_nees = np.sum(error[..., :2] * np.linalg.solve(xy, error[..., :2, None])[..., 0], axis=-1)
    bias_nees = bias_sq / c[..., 3, 3]
    proposed = proposal[:, mask]
    applied = accepted[:, mask]
    jointly = joint[:, mask]
    joint_proposed, joint_accepted = proposed & jointly, applied & jointly
    range_only_proposed, range_only_accepted = proposed & ~jointly, applied & ~jointly
    packet = np.stack((
        np.ones_like(heading_sq), heading_sq, xy_sq, bias_sq,
        heading_nees, xy_nees, bias_nees,
        heading_nees <= CHI1_95, xy_nees <= CHI2_95, bias_nees <= CHI1_95,
        proposed, applied, joint_proposed, joint_accepted,
        joint_proposed, joint_accepted, range_only_proposed, range_only_accepted,
    ), axis=-1)
    cp_mask_position = np.cumsum(mask) - 1
    return {
        "frame": packet.sum(axis=1),
        "checkpoint": packet[:, cp_mask_position[cp]],
        "columns": STAT_COLUMNS,
    }


def _safe_rate(numerator, denominator):
    rate = np.full_like(numerator, np.nan, dtype=float)
    np.divide(numerator, denominator, out=rate, where=denominator > 0)
    return rate


def score_sufficient(stats):
    """Score additive sufficient statistics over their final dimension."""
    stats = np.asarray(stats, dtype=float)
    if stats.shape[-1] != len(STAT_COLUMNS) or not np.isfinite(stats).all():
        raise ValueError("invalid score statistics")
    n, heading_sq, xy_sq, bias_sq, *terms = np.moveaxis(stats, -1, 0)
    nees_terms, coverage_terms = terms[:3], terms[3:6]
    range_p, range_a, s_p, s_a, joint_p, joint_a, range_only_p, range_only_a = terms[6:]
    output = {
        "n": n,
        "heading_rmse_deg": np.degrees(np.sqrt(_safe_rate(heading_sq, n))),
        "xy_rmse_m": np.sqrt(_safe_rate(xy_sq, n)),
        "bias_rmse_dps": np.degrees(np.sqrt(_safe_rate(bias_sq, n))),
    }
    output.update({key: _safe_rate(value, n) for key, value in
                   zip(RATE_COLUMNS[3:9], (*nees_terms, *coverage_terms))})
    pairs = ((range_p, range_a), (s_p, s_a), (joint_p, joint_a), (range_only_p, range_only_a))
    output.update({key: _safe_rate(proposed - applied, proposed)
                   for key, (proposed, applied) in zip(RATE_COLUMNS[9:], pairs)})
    output.update({key: value for key, value in zip(COUNT_COLUMNS, terms[6:])})
    return output


def site_totals(checkpoint, site_id):
    """Retain all checkpoints and group them by their shared traveled-distance site."""
    stats = np.asarray(checkpoint, dtype=float)
    site_id = np.asarray(site_id)
    if (stats.ndim != 3 or stats.shape[2] != len(STAT_COLUMNS)
            or site_id.shape != (stats.shape[1],) or site_id.dtype.kind not in "iu"
            or not np.isfinite(stats).all()):
        raise ValueError("checkpoint stats/site shape mismatch")
    sites, by_site = np.unique(site_id, return_inverse=True)
    totals = np.zeros((len(stats), len(sites), len(STAT_COLUMNS)))
    for i in range(len(sites)):
        totals[:, i] = stats[:, by_site == i].sum(axis=1)
    return totals


def bootstrap_design(seed_count, site_count, replicates=BOOTSTRAP_REPLICATES, seed=BOOTSTRAP_SEED):
    """Stage 1 resample seeds, stage 2 resample common site clusters."""
    if min(seed_count, site_count, replicates) < 1:
        raise ValueError("bootstrap requires seeds and sites")
    rng = np.random.default_rng(seed)
    seeds = rng.multinomial(seed_count, np.full(seed_count, 1 / seed_count), size=replicates)
    sites = rng.multinomial(site_count, np.full(site_count, 1 / site_count), size=replicates)
    return seeds, sites


def _scalar(value):
    return float(value) if np.isfinite(value) else None


def _intervals(point, replicates):
    result = {}
    for metric in RATE_COLUMNS:
        values = np.asarray(replicates[metric])
        finite = np.isfinite(values)
        ci = [_scalar(v) for v in np.percentile(values[finite], (2.5, 97.5))] if finite.any() else None
        result[metric] = {
            "point": _scalar(point[metric]),
            "ci95": ci,
            "replicates_valid": int(finite.sum()),
        }
    return result


def bootstrap_totals(grouped, design):
    """Per-replicate sums for reuse across paired arms and thinning phases."""
    seeds, sites = design
    if grouped.shape[:2] != (seeds.shape[1], sites.shape[1]):
        raise ValueError("bootstrap design does not match grouped inputs")
    site_sums = (seeds @ grouped.reshape(len(grouped), -1)).reshape(
        len(seeds), grouped.shape[1], grouped.shape[2])
    return np.einsum("bs,bsk->bk", sites, site_sums)


def paired_bootstrap(a, b=None, *, site_id, replicates=BOOTSTRAP_REPLICATES, seed=BOOTSTRAP_SEED):
    """Percentile intervals for checkpoint arms and paired score difference A−B."""
    a = np.asarray(a, dtype=float)
    first = site_totals(a, site_id)
    design = bootstrap_design(first.shape[0], first.shape[1], replicates, seed)
    a_point = score_sufficient(first.sum(axis=(0, 1)))
    a_boot = score_sufficient(bootstrap_totals(first, design))
    result = {
        "A": _intervals(a_point, a_boot),
        "replicates": replicates,
        "bootstrap_seed": seed,
        "n_seeds": first.shape[0],
        "n_sites": first.shape[1],
        "note": "Conditional on this RF trajectory. Seed and common site draws are paired across arms.",
    }
    if b is not None:
        b = np.asarray(b, dtype=float)
        if a.shape != b.shape:
            raise ValueError("paired checkpoint inputs must share seed/frame order and shape")
        second = site_totals(b, site_id)
        b_point = score_sufficient(second.sum(axis=(0, 1)))
        b_boot = score_sufficient(bootstrap_totals(second, design))
        point_delta = {k: a_point[k] - b_point[k] for k in RATE_COLUMNS}
        bootstrap_delta = {k: a_boot[k] - b_boot[k] for k in RATE_COLUMNS}
        result.update({"B": _intervals(b_point, b_boot),
                       "A_minus_B": _intervals(point_delta, bootstrap_delta)})
    return result


def synthetic_checks():
    t = np.arange(35, dtype=float)
    pose = np.c_[t, np.zeros_like(t), np.zeros_like(t)]
    cp = checkpoints(t, pose)
    np.testing.assert_array_equal(cp["checkpoint_index"], [30, 31, 32, 33, 34])
    np.testing.assert_array_equal(cp["site_id"], [30, 31, 32, 33, 34])
    state = np.broadcast_to(np.c_[pose, np.zeros_like(t)], (2, len(t), 4)).copy()
    state[..., 0] += 0.3
    state[..., 1] -= 0.4
    state[..., 2] += 2 * np.pi - 0.1
    state[..., 3] += 0.02
    c = np.eye(4)
    c[:2, :2] = np.array([[0.2, 0.1], [0.1, 0.4]])
    c[2, 2], c[3, 3] = 0.001, 0.05
    cov = np.broadcast_to(c, (2, len(t), 4, 4))
    joint = np.arange(len(t)) % 2 == 0
    accepted = np.arange(len(t)) % 3 == 0
    s = trajectory_statistics(state, cov, accepted, joint, t, pose, 0.02, cp["checkpoint_index"])
    score = score_sufficient(s["frame"].sum(axis=0))
    np.testing.assert_allclose(score["xy_rmse_m"], 0.5, atol=1e-14)
    np.testing.assert_allclose(score["heading_rmse_deg"], np.degrees(0.1), atol=1e-14)
    np.testing.assert_allclose(score["heading_nees_mean"], 10.0)
    np.testing.assert_allclose(score["heading95_coverage"], 0.0)
    np.testing.assert_allclose(score["xy_nees_mean"], np.array([0.3, -0.4]) @
                               np.linalg.solve(c[:2, :2], [0.3, -0.4]))
    np.testing.assert_allclose(score["bias_rmse_dps"], 0.0)
    np.testing.assert_allclose(score["range_gate_reject_rate"], 3/5)
    np.testing.assert_allclose(score["s_gate_reject_rate"], 2/3)
    interval = paired_bootstrap(s["checkpoint"], s["checkpoint"], site_id=cp["site_id"])
    assert interval["replicates"] == 2000
    assert interval["A_minus_B"]["heading_rmse_deg"]["ci95"] == [0.0, 0.0]
    assert interval["A_minus_B"]["heading_rmse_deg"]["replicates_valid"] == 2000
    return {"status": "PASS", "paired_identical_arm_delta_ci95": [0.0, 0.0]}
