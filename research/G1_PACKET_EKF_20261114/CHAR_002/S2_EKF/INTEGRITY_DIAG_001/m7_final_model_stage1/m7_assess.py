"""Pure M7 §5–7 assessment helpers; no file loading, fitting or replay.

Callers supply point scores and 10 s bootstrap lower bounds from the existing
scorer, with H2 references matched by condition/Q/seed/gate. Coverage is a
fraction; heading RMSE is degrees and XY RMSE is centimetres. Outputs are JSON
safe. These helpers assess supplied summaries and do not compute bootstrap CIs.
"""
from __future__ import annotations

import math
from numbers import Real

import numpy as np

ROUTES = ("R2", "R4", "R5")
GROUPS = (*ROUTES, "pooled")
PRIMARY = ("B0", "L2_GYRO_ARW")
STRESS = "L2_GYRO_ARW_Q_B0_STRESS"
COVERAGE = ("pose95_coverage", "heading95_coverage", "xy95_coverage")
RMSE = ("heading_rmse_deg", "xy_rmse_cm")


def _number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric data")
    return float(value)


def _count(value, name):
    value = _number(value, name)
    if value < 0 or not value.is_integer():
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def _summary(values, required, name):
    if not isinstance(values, dict) or any(key not in values for key in required):
        raise ValueError(f"Missing {name} metrics: {required}")
    result = {key: _number(value, f"{name}.{key}") for key, value in values.items()}
    for key, value in result.items():
        if "coverage" in key and not 0 <= value <= 1:
            raise ValueError(f"{name}.{key} must be a fraction in [0,1]")
        if (key in RMSE or key == "mean_nees3") and value < 0:
            raise ValueError(f"{name}.{key} must be nonnegative")
    return result


def assess_group(point, ci10_lower, reference, *, pooled=False, effective_blocks=8,
                 reference_only=False, mirror_fail=0):
    """Assess one route or pooled group, preserving separate I/A decisions."""
    if type(pooled) is not bool or type(reference_only) is not bool:
        raise ValueError("pooled/reference_only must be booleans")
    coverage = COVERAGE[:2] if pooled else COVERAGE
    required = (*COVERAGE, *RMSE, *(("mean_nees3",) if pooled else ()))
    point = _summary(point, required, "point")
    lower = _summary(ci10_lower, coverage, "ci10_lower")
    reference = _summary(reference, RMSE, "reference_H2")
    blocks = _count(effective_blocks, "effective_blocks")
    mirrors = _count(mirror_fail, "mirror_fail")
    point_min, lower_min, rmse_factor = (.90, .80, 1.10) if pooled else (.75, .60, 1.25)
    margins = {key: point[key] - point_min for key in coverage}
    margins.update({f"{key}_ci10_lower": lower[key] - lower_min for key in coverage})
    integrity_failures = [key for key, margin in margins.items() if margin < 0]
    if pooled:
        margins["mean_nees3_lower"] = point["mean_nees3"] - 1.5
        margins["mean_nees3_upper"] = 6.0 - point["mean_nees3"]
        if not 1.5 <= point["mean_nees3"] <= 6.0:
            integrity_failures.append("mean_nees3")
    if mirrors:
        integrity_failures.append("mirror_fail")
    if blocks < 8 or reference_only:
        integrity_failures.append("reference_only")
    accuracy_failures = []
    costs = {}
    for key in RMSE:
        limit = rmse_factor * reference[key]
        margins[f"{key}_limit"] = limit - point[key]
        if point[key] > limit:
            accuracy_failures.append(key)
        costs[key] = None if reference[key] == 0 else 100 * (point[key] / reference[key] - 1)
    integrity, accuracy = not integrity_failures, not accuracy_failures
    return dict(pooled=pooled, integrity_pass=integrity, accuracy_pass=accuracy,
                joint_pass=integrity and accuracy, mirror_fail=mirrors,
                effective_blocks=blocks, reference_only=reference_only or blocks < 8,
                integrity_failures=integrity_failures, accuracy_failures=accuracy_failures,
                margins=margins, rmse_cost_percent=costs, point=point, ci10_lower=lower,
                reference_H2=reference)


def assess_seed(seed, groups):
    """Combine exactly R2/R4/R5/pooled, checking pooled mirror duplication."""
    seed = _count(seed, "seed")
    if seed not in range(10, 30) or not isinstance(groups, dict) or set(groups) != set(GROUPS):
        raise ValueError("Require a seed 10–29 and exactly R2/R4/R5/pooled")
    for name, group in groups.items():
        if group.get("pooled") is not (name == "pooled"):
            raise ValueError(f"Incorrect group role: {name}")
        recomputed = assess_group(group["point"], group["ci10_lower"], group["reference_H2"],
                                  pooled=name == "pooled", effective_blocks=group["effective_blocks"],
                                  reference_only=group["reference_only"], mirror_fail=group["mirror_fail"])
        for field in ("integrity_pass", "accuracy_pass", "joint_pass"):
            if type(group.get(field)) is not bool or group[field] != recomputed[field]:
                raise ValueError(f"Missing/invalid {name}.{field}")
        if group["joint_pass"] != (group["integrity_pass"] and group["accuracy_pass"]):
            raise ValueError("Group joint flag must be I AND A")
        if _count(group["mirror_fail"], f"{name}.mirror_fail") and group["integrity_pass"]:
            raise ValueError("Mirror failure cannot pass integrity")
    mirrors = sum(group["mirror_fail"] for name, group in groups.items() if name in ROUTES)
    if groups["pooled"]["mirror_fail"] != mirrors:
        raise ValueError("Pooled mirror count must equal route sum, not an extra set of events")
    integrity = all(group["integrity_pass"] for group in groups.values())
    accuracy = all(group["accuracy_pass"] for group in groups.values())
    return dict(seed=seed, I_seed=integrity, A_seed=accuracy, J_seed=integrity and accuracy,
                mirror_fail=int(mirrors),
                mirror_routes=sum(groups[route]["mirror_fail"] > 0 for route in ROUTES),
                groups=groups)


def clopper_pearson(successes, trials, confidence=.95):
    """Exact two-sided binomial interval via monotone CDF bisection (stdlib)."""
    k, n = _count(successes, "successes"), _count(trials, "trials")
    confidence = _number(confidence, "confidence")
    if n == 0 or k > n or not 0 < confidence < 1:
        raise ValueError("Require 0<=successes<=trials, trials>0, 0<confidence<1")
    alpha = (1 - confidence) / 2

    def cdf(stop, probability):
        return math.fsum(math.comb(n, i) * probability**i * (1 - probability)**(n - i)
                         for i in range(stop + 1))

    def root(stop, target):
        lo, hi = 0., 1.
        for _ in range(80):
            mid = (lo + hi) / 2
            if cdf(stop, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    return [0. if k == 0 else root(k - 1, 1 - alpha),
            1. if k == n else root(k, alpha)]


def _counts(seeds):
    n = len(seeds)
    result = dict(denominator=n, seeds=[row["seed"] for row in seeds])
    for label, field in (("integrity", "I_seed"), ("accuracy", "A_seed"), ("joint", "J_seed")):
        count = sum(row[field] for row in seeds)
        result[f"N_{label}"] = count
        result[f"{label}_rate"] = count / n
        result[f"{label}_ci95"] = clopper_pearson(count, n)
    result["IA_seed_lists"] = {
        f"I{int(i)}_A{int(a)}": [row["seed"] for row in seeds if row["I_seed"] == i and row["A_seed"] == a]
        for i in (False, True) for a in (False, True)}
    mirror_seeds = sum(row["mirror_fail"] > 0 for row in seeds)
    result.update(mirror_passage_events=sum(row["mirror_fail"] for row in seeds),
                  mirror_route_runs=sum(row["mirror_routes"] for row in seeds),
                  route_runs=3 * n, mirror_seed_count=mirror_seeds,
                  mirror_seed_rate=mirror_seeds / n,
                  mirror_seed_ci95=clopper_pearson(mirror_seeds, n))
    return result


def summarize_condition(seed_results, condition, arm, mode="own"):
    """Exact-grid seed counts; only full-20 primary own gates support adoption."""
    if condition not in (*PRIMARY, STRESS) or arm not in ("H0", "H1", "H2", "H3", "H4", "H5", "H5P"):
        raise ValueError("Unknown condition or arm")
    if mode not in ("own", "fixed") or (mode == "fixed" and condition == STRESS):
        raise ValueError("Only own/fixed modes; stress has no fixed-mask campaign")
    expected = list(range(10, 30 if mode == "own" else 15))
    checked = []
    for row in seed_results:
        assessed = assess_seed(row["seed"], row["groups"])
        for field in ("I_seed", "A_seed", "J_seed", "mirror_fail", "mirror_routes"):
            if row.get(field) != assessed[field]:
                raise ValueError(f"Inconsistent supplied seed summary: {field}")
        checked.append(assessed)
    if sorted(row["seed"] for row in checked) != expected:
        raise ValueError("Missing/duplicate/extra seeds; never reduce the denominator")
    checked.sort(key=lambda row: row["seed"])
    result = _counts(checked)
    result.update(condition=condition, arm=arm, mode=mode,
                  report_only=condition == STRESS or mode == "fixed")
    eligible = not result["report_only"]
    zero_mirrors = result["mirror_passage_events"] == 0
    result.update(CONDITION_PASS=eligible and result["N_joint"] >= 18 and zero_mirrors,
                  CONDITION_INTEGRITY_PASS=eligible and result["N_integrity"] >= 18 and zero_mirrors,
                  CONDITION_ACCURACY_PASS=eligible and result["N_accuracy"] >= 18)
    result["subsets"] = {"seed10_14": _counts([row for row in checked if row["seed"] < 15])}
    if mode == "own":
        result["subsets"]["seed15_29"] = _counts([row for row in checked if row["seed"] >= 15])
    return result


def overall_m7(condition_summaries):
    """Combine same-arm primary own campaigns; optional stress never gates M7."""
    summaries = list(condition_summaries)
    if not summaries or len({row["arm"] for row in summaries}) != 1:
        raise ValueError("Overall assessment requires one and the same arm")
    keys = [(row["condition"], row["mode"]) for row in summaries]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate condition/mode summaries")
    primary = {}
    for row in summaries:
        if row["condition"] in PRIMARY and row["mode"] == "own":
            if row["denominator"] != 20 or row["report_only"]:
                raise ValueError("Primary own campaign must contain all 20 seeds")
            primary[row["condition"]] = row
    if set(primary) != set(PRIMARY):
        raise ValueError("Missing complete B0 or Q-matched L2 primary own campaign")
    return dict(arm=summaries[0]["arm"], M7_PASS=all(row["CONDITION_PASS"] for row in primary.values()),
                primary_condition_pass={key: row["CONDITION_PASS"] for key, row in primary.items()},
                stress_required=False, adoption="Separate decision; this is the frozen numeric assessment")


def bias_metrics(trace, controls=None, window=None, *, gyro_error_increment=None):
    """Diagnose b_g,true=0; optional inclusive time window and control integrals.

    x[:,3] is rad/s and P[:,3,3] is (rad/s)^2. Cumulative series keep the
    original trace origin even for a window; window sums use increments ending
    at selected timestamps. Zero variance makes normalized summaries unavailable.
    No bias-based acceptance threshold is introduced.
    """
    t, x, p = (np.asarray(trace[key], dtype=float) for key in ("t", "x", "P"))
    n = len(t)
    if (t.ndim != 1 or n == 0 or x.ndim != 2 or x.shape[0] != n or x.shape[1] < 4
            or p.shape != (n, x.shape[1], x.shape[1]) or not np.isfinite(t).all()
            or not np.isfinite(x).all() or not np.isfinite(p).all()
            or np.any(np.diff(t) <= 0) or np.any(p[:, 3, 3] < 0)):
        raise ValueError("Invalid/nonfinite bias trace or negative bias variance")
    selected = np.ones(n, dtype=bool)
    if window is not None:
        if len(window) != 2:
            raise ValueError("window must be (start_s,end_s)")
        start, end = (_number(v, "window") for v in window)
        if start > end:
            raise ValueError("Reversed window")
        selected = (t >= start) & (t <= end)
        if not selected.any():
            raise ValueError("Empty bias window")
    error = np.degrees(x[selected, 3])
    sd = np.degrees(np.sqrt(p[selected, 3, 3]))

    def stats(values):
        values = dict(signed_mean=float(np.mean(values)), rmse=float(np.sqrt(np.mean(values**2))),
                      abs_p95=float(np.percentile(np.abs(values), 95)),
                      abs_max=float(np.max(np.abs(values))), endpoint=float(values[-1]))
        return {key: _number(value, f"bias_stats.{key}") for key, value in values.items()}

    valid = sd > 0
    normalized = [float(e / s) if s > 0 else None for e, s in zip(error, sd)]
    result = dict(true_bg_deg_s=0., units="deg/s; normalized error dimensionless",
                  samples=int(selected.sum()), start_s=float(t[selected][0]), end_s=float(t[selected][-1]),
                  bias_error_deg_s=stats(error), sqrt_P_bg_deg_s=stats(sd),
                  normalized_error=stats(error / sd) if valid.all() else None,
                  zero_variance_samples=int((~valid).sum()), acceptance_threshold=None,
                  time_series=dict(t=t[selected].tolist(), bias_error_deg_s=error.tolist(),
                                   sqrt_P_bg_deg_s=sd.tolist(), normalized_error=normalized))
    if controls is not None:
        dt = np.asarray(controls["dt"], dtype=float)
        if dt.shape != t.shape or not np.isfinite(dt).all() or not np.allclose(dt, np.r_[0., np.diff(t)], atol=1e-12, rtol=0):
            raise ValueError("Control dt must match trace timestamps")
        increments = -np.r_[x[0, 3], x[:-1, 3]] * dt
        result["bias_heading_correction_window_deg"] = float(np.degrees(increments[selected].sum()))
        result["time_series"]["bias_heading_correction_cumulative_deg"] = np.degrees(np.cumsum(increments))[selected].tolist()
    if gyro_error_increment is not None:
        noise = np.asarray(gyro_error_increment, dtype=float)
        if noise.shape != t.shape or not np.isfinite(noise).all() or noise[0] != 0:
            raise ValueError("Gyro error increments must match trace and begin at zero")
        result["direct_gyro_error_window_deg"] = float(np.degrees(noise[selected].sum()))
        result["time_series"]["direct_gyro_error_cumulative_deg"] = np.degrees(np.cumsum(noise))[selected].tolist()
    return result
