"""G1-MODEL-001 v3.3 paired G-E2E calculations, conditional on the fixed RF bank."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from scipy.stats import beta

MODELS = ("independent", "markov")
CASE = "R5_aA_m0"
STATIONS = 17
PILOT_PATHS = 50
PATHS = 250
BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 2026111340
MARGINS = {
    "coverage_1_to_17": 0.02,
    "coverage_at_17": 0.04,
    "rmse_ratio_1_to_17": 0.05,
    "mean_nees_1_to_17": 0.25,
    "g1_rmse_1_to_17_deg": 0.15,
    "gate_rejection_1_to_17": 0.03,
}


def check_paths(snap, continuous, dr, expected_paths):
    """Raise ValueError for missing or invalid paths before computing metrics."""
    shape = (expected_paths, STATIONS)
    dr = np.asarray(dr)
    if dr.shape != shape or not np.isfinite(dr).all():
        raise ValueError(f"Expected {shape} finite paired DR-cal errors")
    for name, arm in (("snap", snap), ("continuous", continuous)):
        for key in ("err", "nees", "p_ee", "covered", "used", "reject"):
            if key not in arm or np.shape(arm[key]) != shape:
                raise ValueError(f"{name}/{key}: expected shape {shape}")
        for key in ("err", "nees", "p_ee"):
            if not np.isfinite(arm[key]).all():
                raise ValueError(f"{name}/{key}: nonfinite filter output")
        if (arm["p_ee"] <= 0).any() or (arm["nees"] < 0).any():
            raise ValueError(f"{name}: nonpositive heading variance or negative NEES")
        for key in ("covered", "used", "reject"):
            if np.asarray(arm[key]).dtype.kind != "b":
                raise ValueError(f"{name}/{key}: expected boolean flags")
        if (arm["used"] & arm["reject"]).any():
            raise ValueError(f"{name}: a station cannot both update and reject")


def _summaries(arm):
    """Path-level sufficient statistics for all six G-E2E estimands."""
    return {
        "covered": arm["covered"].sum(axis=1),
        "covered_at_17": arm["covered"][:, -1],
        "g1_mse": np.mean(np.square(arm["err"]), axis=1),
        "mean_nees": np.mean(arm["nees"], axis=1),
        "rejected": arm["reject"].sum(axis=1),
        "eligible": (arm["used"] | arm["reject"]).sum(axis=1),
    }


def _divide(numerator, denominator):
    return np.divide(
        numerator, denominator, out=np.full(np.shape(numerator), np.nan),
        where=np.isfinite(denominator) & (denominator > 0),
    )


def _metrics(summary, dr_mse, sample=slice(None)):
    g1_rmse = np.sqrt(summary["g1_mse"][sample].mean(axis=-1))
    dr_rmse = np.sqrt(dr_mse[sample].mean(axis=-1))
    return {
        "coverage_1_to_17": summary["covered"][sample].mean(axis=-1) / STATIONS,
        "coverage_at_17": summary["covered_at_17"][sample].mean(axis=-1),
        "rmse_ratio_1_to_17": _divide(g1_rmse, dr_rmse),
        "mean_nees_1_to_17": summary["mean_nees"][sample].mean(axis=-1),
        "g1_rmse_1_to_17_deg": g1_rmse,
        "gate_rejection_1_to_17": _divide(
            summary["rejected"][sample].sum(axis=-1),
            summary["eligible"][sample].sum(axis=-1),
        ),
    }


def _cp_upper(count, n, alpha):
    return 1.0 if count == n else float(beta.ppf(1.0 - alpha, count + 1, n - count))


def _cp_interval(count, n, confidence):
    alpha = (1.0 - confidence) / 2.0
    lower = 0.0 if count == 0 else float(beta.ppf(alpha, count, n - count + 1))
    return lower, _cp_upper(count, n, alpha)


def _endpoint_interval(snap, direct):
    a, b = snap["covered_at_17"], direct["covered_at_17"]
    plus = int(np.count_nonzero(a & ~b))
    minus = int(np.count_nonzero(b & ~a))
    lo_plus, hi_plus = _cp_interval(plus, len(a), 0.975)
    lo_minus, hi_minus = _cp_interval(minus, len(a), 0.975)
    return (lo_plus - hi_minus, hi_plus - lo_minus), plus, minus


def _bootstrap_interval(samples):
    if not np.isfinite(samples).all():
        return None, "undefined_bootstrap_denominator"
    lo, hi = (float(x) for x in np.quantile(samples, [0.025, 0.975]))
    if lo == hi:
        return None, "zero_width_bootstrap_interval"
    return (lo, hi), None


def _entry(snap, continuous, ci, margin, method, reason=None):
    point = [float(v) if np.isfinite(v) else None for v in (snap, continuous)]
    if None in point:
        ci, reason = None, "undefined_point_denominator"
    if ci is None:
        status = "INCONCLUSIVE"
    elif -margin <= ci[0] and ci[1] <= margin:
        status = "PASS"
    elif ci[1] < -margin or ci[0] > margin:
        status = "FAIL"
    else:
        status = "INCONCLUSIVE"
        reason = "interval_crosses_margin"
    return {
        "snap": point[0],
        "continuous": point[1],
        "difference": None if None in point else point[0] - point[1],
        "ci95": ci,
        "margin": margin,
        "ci_method": method,
        "status": status,
        "reason": reason,
    }


def _combined_status(statuses):
    statuses = set(statuses)
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS" if statuses == {"PASS"} else "INCONCLUSIVE"


def _model_result(snap, direct, dr_mse, sample):
    point_snap = _metrics(snap, dr_mse)
    point_direct = _metrics(direct, dr_mse)
    boot_snap = _metrics(snap, dr_mse, sample)
    boot_direct = _metrics(direct, dr_mse, sample)
    n = len(dr_mse)
    coverage_discordant = int(np.count_nonzero(snap["covered"] != direct["covered"]))
    gate_discordant = int(np.count_nonzero(
        (snap["rejected"] != direct["rejected"]) | (snap["eligible"] != direct["eligible"])
    ))
    endpoint_ci, endpoint_plus, endpoint_minus = _endpoint_interval(snap, direct)
    diagnostics = {
        "coverage_discordant_paths": coverage_discordant,
        "gate_discordant_paths": gate_discordant,
        "endpoint_snap_only": endpoint_plus,
        "endpoint_continuous_only": endpoint_minus,
    }

    metrics = {}
    for key, margin in MARGINS.items():
        method = "paired_path_percentile_bootstrap"
        reason = None
        boot_difference = boot_snap[key] - boot_direct[key]
        if key == "coverage_at_17":
            ci, method = endpoint_ci, "paired_bonferroni_clopper_pearson"
        elif key == "coverage_1_to_17" and coverage_discordant < 5:
            limit = _cp_upper(coverage_discordant, n, 0.05)
            ci, method = (-limit, limit), "sparse_clopper_pearson_disagreement_bound"
        elif key == "gate_rejection_1_to_17" and gate_discordant < 5:
            method = "sparse_clopper_pearson_hoeffding_bound"
            q_lower = float(snap["eligible"].mean() / STATIONS - np.sqrt(np.log(40) / (2 * n)))
            diagnostics["gate_snap_eligible_expectation_lower"] = q_lower
            if not np.isfinite(boot_difference).all():
                ci, reason = None, "undefined_bootstrap_denominator"
            elif q_lower <= 0:
                ci, reason = None, "nonpositive_eligible_expectation_lower"
            else:
                limit = min(1.0, _cp_upper(gate_discordant, n, 0.025) / q_lower)
                ci = (-limit, limit)
        else:
            ci, reason = _bootstrap_interval(boot_difference)
        metrics[key] = _entry(point_snap[key], point_direct[key], ci, margin, method, reason)
    return {
        "status": _combined_status(entry["status"] for entry in metrics.values()),
        "metrics": metrics,
        "diagnostics": diagnostics,
    }


def evaluate(results, dr):
    """Evaluate §5.4 once, after all 250 paths for each frozen RF model."""
    if set(results) != set(MODELS):
        raise ValueError(f"Expected exactly the G-E2E models {MODELS}")
    for model in MODELS:
        check_paths(*results[model], dr, PATHS)
    dr_mse = np.mean(np.square(dr), axis=1)
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    by_model = {}
    for model in MODELS:
        snap, direct = results[model]
        sample = rng.integers(0, PATHS, size=(BOOTSTRAP, PATHS))
        by_model[model] = _model_result(_summaries(snap), _summaries(direct), dr_mse, sample)
    return {
        "status": _combined_status(entry["status"] for entry in by_model.values()),
        "case": CASE,
        "stations": STATIONS,
        "paths_per_model": PATHS,
        "pilot_paths_per_model": PILOT_PATHS,
        "additional_paths_per_model": PATHS - PILOT_PATHS,
        "bootstrap_replicates": BOOTSTRAP,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "difference_direction": "snap - continuous",
        "models": by_model,
    }


def write_paths(path, results, dr):
    """Write the paired sufficient statistics used by evaluate to a new CSV."""
    if set(results) != set(MODELS):
        raise ValueError(f"Expected exactly the G-E2E models {MODELS}")
    for model in MODELS:
        check_paths(*results[model], dr, PATHS)
    dr_mse = np.mean(np.square(dr), axis=1)
    with Path(path).open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        for model in MODELS:
            snap, direct = map(_summaries, results[model])
            if model == MODELS[0]:
                writer.writerow(
                    ["model", "path_id", "dr_mse"]
                    + [f"snap_{key}" for key in snap]
                    + [f"continuous_{key}" for key in direct]
                )
            for path_id, mse in enumerate(dr_mse):
                writer.writerow(
                    [model, path_id, float(mse)]
                    + [value[path_id].item() for value in snap.values()]
                    + [value[path_id].item() for value in direct.values()]
                )
