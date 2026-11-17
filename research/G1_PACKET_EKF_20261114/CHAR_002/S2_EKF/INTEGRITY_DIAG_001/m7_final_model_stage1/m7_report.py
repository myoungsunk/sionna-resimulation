"""Pure M7 report aggregation; summaries retain the per-seed unit and denominator.

Inputs are complete score_comparison outputs. No files, data sources or replays
are loaded here. Distributions describe seed variation, not bootstrap intervals.
Zero RMSE references leave ratios undefined without dropping the seed count.
"""
import math

import numpy as np

from m7_assess import COVERAGE, RMSE, overall_m7, summarize_condition
from m7_spec import ARMS, CONDITIONS, FIXED_SEEDS, MAIN_CONDITIONS, ROUTES, SEEDS, STRESS
from m7_spec import expected_cells, validate_cell_index

GROUPS = (*ROUTES, "pooled")
METRICS = (*COVERAGE, *RMSE, "mean_nees3")
BIAS_STATS = ("signed_mean", "rmse", "abs_p95", "abs_max", "endpoint")
H5_CLAIM_LIMIT = "Failure with residual q_s does not establish b_theta necessity"


def _finite(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError("Report metric must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite report metric")
    return result


def _distribution(values):
    """None denotes an undefined ratio; the original seed denominator remains."""
    valid = np.array([_finite(v) for v in values if v is not None], dtype=float)
    result = dict(summary_unit="per_seed", seed_denominator=len(values),
                  defined_count=len(valid), undefined_count=len(values) - len(valid))
    for key, function in (("min", np.min), ("max", np.max), ("median", np.median), ("mean", np.mean)):
        result[key] = float(function(valid)) if len(valid) else None
    result.update(p05=float(np.percentile(valid, 5)) if len(valid) else None,
                  p95=float(np.percentile(valid, 95)) if len(valid) else None)
    return result


def _ratio(value, reference, improvement=False):
    value, reference = _finite(value), _finite(reference)
    if value < 0 or reference < 0:
        raise ValueError("RMSE cannot be negative")
    if reference == 0:
        return None
    return 100 * (1 - value / reference if improvement else value / reference - 1)


def _cohorts(rows, mode):
    result = {"all_seeds": rows, "seed10_14": [r for r in rows if r["seed"] < 15]}
    if mode == "own":
        result["seed15_29"] = [r for r in rows if r["seed"] >= 15]
    return result


def _group_summary(rows, arm, group):
    def point(row, selected_arm=arm):
        return row["scores"]["point"][group][selected_arm]

    metrics = {name: _distribution([point(row)[name] for row in rows]) for name in METRICS}
    costs = {name: _distribution([_ratio(point(r)[name], point(r, "H2")[name]) for r in rows])
             for name in RMSE}
    improvement = {
        baseline: {name: _distribution([_ratio(point(r)[name], point(r, baseline)[name], True)
                                        for r in rows]) for name in RMSE}
        for baseline in ("H0", "H1")}
    mirrors = [row["seed_assessments"][arm]["groups"][group]["mirror_fail"] for row in rows]
    return dict(metrics=metrics, rmse_cost_vs_H2_percent=costs,
                rmse_improvement_percent=improvement,
                mirror=dict(seed_denominator=len(rows), event_count=sum(mirrors),
                            affected_seed_count=sum(n > 0 for n in mirrors),
                            affected_seeds=[row["seed"] for row, n in zip(rows, mirrors) if n > 0]))


def summarize_campaign(comparisons, condition, mode="own"):
    """One exact 20-seed own or five-seed fixed campaign, no new thresholds."""
    if condition not in CONDITIONS or mode not in ("own", "fixed") or (condition == STRESS and mode == "fixed"):
        raise ValueError("Unknown/unplanned condition and gate mode")
    rows = list(comparisons)
    expected = SEEDS if mode == "own" else FIXED_SEEDS
    if (any(row.get("condition") != condition or row.get("mode") != mode for row in rows)
            or any(type(row.get("seed")) is not int for row in rows)
            or sorted(row["seed"] for row in rows) != list(expected)):
        raise ValueError("Missing/duplicate/extra seeds or campaign identity mismatch")
    rows.sort(key=lambda row: row["seed"])
    for row in rows:
        if set(row["seed_assessments"]) != set(ARMS) or set(row["scores"]["point"]) != set(GROUPS):
            raise ValueError("Report requires every planned arm and group")
        for group in GROUPS:
            if set(row["scores"]["point"][group]) != set(ARMS):
                raise ValueError("Missing/extra score arm")
            for arm in ARMS:
                assessment = row["seed_assessments"][arm]
                if assessment["seed"] != row["seed"]:
                    raise ValueError("Seed assessment identity mismatch")
                point = row["scores"]["point"][group][arm]
                recorded = assessment["groups"][group]
                for metric in METRICS:
                    if _finite(point[metric]) != _finite(recorded["point"][metric]):
                        raise ValueError("Reported scores differ from assessed scores")
                for metric in RMSE:
                    reference = row["scores"]["point"][group]["H2"][metric]
                    if _finite(reference) != _finite(recorded["reference_H2"][metric]):
                        raise ValueError("Accuracy reference is not the same-condition H2")
    arms = {}
    for arm in ARMS:
        decision = summarize_condition([row["seed_assessments"][arm] for row in rows], condition, arm, mode)
        cohorts = {}
        for name, cohort in _cohorts(rows, mode).items():
            cohorts[name] = dict(seeds=[r["seed"] for r in cohort], seed_denominator=len(cohort),
                groups={g: _group_summary(cohort, arm, g) for g in GROUPS},
                bias_error_deg_s={route: {stat: _distribution([
                    r["bias"][route][arm]["bias_error_deg_s"][stat] for r in cohort])
                    for stat in BIAS_STATS} for route in ROUTES},
                sqrt_P_bg_deg_s={route: {stat: _distribution([
                    r["bias"][route][arm]["sqrt_P_bg_deg_s"][stat] for r in cohort])
                    for stat in BIAS_STATS} for route in ROUTES},
                normalized_error={route: {stat: _distribution([
                    (None if r["bias"][route][arm]["normalized_error"] is None
                     else r["bias"][route][arm]["normalized_error"][stat]) for r in cohort])
                    for stat in BIAS_STATS} for route in ROUTES})
        arms[arm] = dict(assessment=decision, cohorts=cohorts)
    return dict(condition=condition, mode=mode, seed_denominator=len(rows),
                report_only=condition == STRESS or mode == "fixed", arms=arms,
                distribution_note="Per-seed descriptive distribution; not a confidence interval",
                H5_claim_limit=H5_CLAIM_LIMIT)


def summarize_all(comparisons):
    """Require all five campaigns/70 seed groups; stress never gates M7."""
    rows = list(comparisons)
    keys = [(condition, mode) for condition in MAIN_CONDITIONS for mode in ("own", "fixed")]
    keys.append((STRESS, "own"))
    grouped = {key: [] for key in keys}
    for row in rows:
        key = (row.get("condition"), row.get("mode"))
        if key not in grouped:
            raise ValueError("Unplanned campaign")
        grouped[key].append(row)
    campaigns = {f"{condition}/{mode}": summarize_campaign(grouped[(condition, mode)], condition, mode)
                 for condition, mode in keys}
    overall = {arm: overall_m7([campaign["arms"][arm]["assessment"] for campaign in campaigns.values()])
               for arm in ARMS}
    counts = validate_cell_index(expected_cells())
    return dict(campaigns=campaigns, overall_by_arm=overall,
                comparison_groups=len(rows), expected_plan_counts=counts,
                expected_logical_cells=1470, expected_physical_replays=1440,
                expected_input_packets=120, H5_claim_limit=H5_CLAIM_LIMIT,
                execution_claim="Counts describe the complete score grid, not independent execution receipts")
