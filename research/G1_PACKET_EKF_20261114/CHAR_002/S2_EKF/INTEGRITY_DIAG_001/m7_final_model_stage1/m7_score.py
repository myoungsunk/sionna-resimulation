"""Offline adapter from the existing S2/block scorer to M7 assessments.

No files or evaluators are read at import. Callers supply the hash-verified
existing from_trace, scores_with_blocks and branch_metrics functions.
"""
import numpy as np

from m7_assess import COVERAGE, assess_group, assess_seed, bias_metrics
from m7_spec import ARMS, CONDITIONS, FIXED_SEEDS, MAIN_CONDITIONS, ROUTES, SEEDS

PASSES = {"R2": 2, "R4": 1, "R5": 3}


def score_comparison(seed, condition, mode, traces, truth, times, *,
                     from_trace, scores_with_blocks, branch_metrics,
                     controls=None, gyro_error_increments=None):
    """Score one complete 3-route/7-arm cell group, retaining different masks."""
    valid_seeds = SEEDS if mode == "own" else FIXED_SEEDS
    if (type(seed) is not int or seed not in valid_seeds or condition not in CONDITIONS
            or mode not in ("own", "fixed") or (mode == "fixed" and condition not in MAIN_CONDITIONS)):
        raise ValueError("Comparison is outside the planned M7 grid")
    if any(set(data) != set(ROUTES) for data in (traces, truth, times)):
        raise ValueError("Comparison requires R2/R4/R5 without exclusions")
    rows, branches, bias, endpoints = {}, {}, {}, {}
    for route in ROUTES:
        t, reference = np.asarray(times[route]), np.asarray(truth[route])
        if (t.ndim != 1 or len(t) < 2 or np.any(np.diff(t) <= 0.)
                or reference.shape != (len(t), 3) or not np.isfinite(t).all()
                or not np.isfinite(reference).all() or set(traces[route]) != set(ARMS)):
            raise ValueError(f"Incomplete/nonfinite score grid: {route}")
        rows[route], branches[route], bias[route], endpoints[route] = {}, {}, {}, {}
        for arm in ARMS:
            trace = traces[route][arm]
            if not np.array_equal(trace["t"], t):
                raise ValueError(f"Trace time grid differs: {route}/{arm}")
            if str(np.asarray(trace["metadata_condition"]).item()) != condition:
                raise ValueError(f"Condition/Q reference differs: {route}/{arm}")
            if str(np.asarray(trace["metadata_arm"]).item()) != arm:
                raise ValueError(f"Arm identity differs: {route}/{arm}")
            if str(np.asarray(trace["metadata_rref_policy"]).item()) != "own":
                raise ValueError(f"Parity-only R_ref schedule cannot be scored: {route}/{arm}")
            policy = CONDITIONS[condition]
            for field, target in (("injected_gyro_N_deg_sqrt_s", policy["injected_N_deg_sqrt_s"]),
                                  ("filter_gyro_N_deg_sqrt_s", policy["filter_N_deg_sqrt_s"])):
                if not np.all(np.asarray(trace[field]) == target):
                    raise ValueError(f"Gyro Q policy differs: {route}/{arm}/{field}")
            gate_mode = str(np.asarray(trace["metadata_gate_mode"]).item())
            if gate_mode != mode and not (mode == "fixed" and arm == "H0" and gate_mode == "own"):
                raise ValueError(f"Gate mode differs: {route}/{arm}")
            row = np.asarray(from_trace(trace, reference))
            if row.shape != (len(t), 6) or not np.isfinite(row).all():
                raise ValueError(f"Invalid scored rows: {route}/{arm}")
            rows[route][arm] = row
            branch = branch_metrics(trace, reference, t)
            if (len(branch["passages"]) != PASSES[route]
                    or sum(p["MIRROR_FAIL"] for p in branch["passages"]) != branch["mirror_fail_count"]):
                raise ValueError(f"Anchor passage accounting differs: {route}/{arm}")
            branches[route][arm] = branch
            bias[route][arm] = bias_metrics(trace,
                controls=None if controls is None else controls[route],
                gyro_error_increment=None if gyro_error_increments is None else gyro_error_increments[route])
            end = np.asarray(trace["x"])[-1, :3] - reference[-1]
            heading = np.degrees((end[2] + np.pi) % (2 * np.pi) - np.pi)
            endpoints[route][arm] = dict(heading_signed_deg=float(heading),
                                        heading_abs_deg=float(abs(heading)),
                                        xy_error_cm=float(100 * np.linalg.norm(end[:2])))
    pairs = [(arm, "H2") for arm in ARMS if arm != "H2"]
    pairs += [(arm, base) for arm in ARMS[2:] for base in ("H0", "H1")]
    pairs += [("H3", "H4"), ("H3", "H5"), ("H3", "H5P"), ("H5P", "H5")]
    scored = scores_with_blocks(rows, times, list(dict.fromkeys(pairs)), blocks=(5, 10, 20))
    point, block10 = scored["point"], scored["blocks"]["10"]
    if set(point) != {*ROUTES, "pooled"} or set(block10["full_blocks"]) != set(ROUTES):
        raise ValueError("Bootstrap output dropped a route or pooled group")
    assessed = {}
    for arm in ARMS:
        groups = {}
        for group in (*ROUTES, "pooled"):
            ci = block10["by_group"][group]
            lower = {metric: ci["absolute_ci95"][arm][metric][0] for metric in COVERAGE}
            pooled = group == "pooled"
            mirrors = (sum(branches[r][arm]["mirror_fail_count"] for r in ROUTES) if pooled
                       else branches[group][arm]["mirror_fail_count"])
            blocks = min(block10["full_blocks"].values()) if pooled else block10["full_blocks"][group]
            groups[group] = assess_group(point[group][arm], lower, point[group]["H2"],
                                         pooled=pooled, effective_blocks=blocks,
                                         reference_only=bool(ci["reference_only"]), mirror_fail=mirrors)
        assessed[arm] = assess_seed(seed, groups)
    return dict(seed=seed, condition=condition, mode=mode, scores=scored,
                branches=branches, bias=bias, endpoint=endpoints, seed_assessments=assessed,
                decision_role=CONDITIONS[condition]["decision_role"],
                H5_claim_limit="Failure with residual q_s does not establish b_theta necessity")
