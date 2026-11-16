"""Offline branch, information, coverage and accuracy scores for M1/M4."""

import numpy as np

from d2 import yaw_information
from ks_diagnostics import COVERAGE, RMSE, scores_with_blocks
from verify_s2 import from_trace


ARMS = ("BASE", "D05", "D10", "D20", "D025", "G05", "I05")
ROUTE_PASSES = {"R2": 2, "R4": 1, "R5": 3}
TOLERANCE = 1e-10


def crossings(truth, t):
    """Return audited x=10 passage indices and linearly interpolated times."""
    offset = truth[:, 0] - 10.
    indices = np.flatnonzero(offset[:-1] * offset[1:] <= 0.)
    result = []
    for i in indices:
        if offset[i + 1] == offset[i]:
            raise ValueError("Cannot locate a unique anchor passage while truth stays at x=10 m")
        time = float(t[i] - offset[i] * (t[i + 1] - t[i]) / (offset[i + 1] - offset[i]))
        if not result or time != result[-1]["time_s"]:
            result.append({"packet_index": int(i + 1), "time_s": time})
    return result


def branch_metrics(trace, truth, t):
    passages = crossings(truth, t)
    y_truth = truth[:, 1]
    y_est = trace["x"][:, 1]
    y_error = y_est - y_truth
    sd_y = np.sqrt(trace["P"][:, 1, 1])
    opposite = (y_est * y_truth < 0.) & (abs(y_truth) >= .2)
    for i, passage in enumerate(passages):
        start = passage["time_s"]
        after = t >= start
        stop = float(t[-1])
        if i + 1 < len(passages):
            stop = passages[i + 1]["time_s"]
            after &= t < stop
        switches = np.flatnonzero(np.diff(np.r_[False, after & opposite, False]))
        runs = [{"start_s": float(t[first]), "end_s": float(t[last - 1]),
                 "duration_s": float(t[last - 1] - t[first])} for first, last in switches.reshape(-1, 2)]
        longest = max((run["duration_s"] for run in runs), default=0.)
        pre = start - 5.
        z_pre = None
        if pre >= t[0]:
            z_pre = float(np.interp(pre, t, y_error) / np.interp(pre, t, sd_y))
        pre_window = (t >= pre) & (t < start)
        # Include the bracketing sample to reproduce interpolation at t_cross - 5 s.
        if pre >= t[0]:
            pre_window[np.searchsorted(t, pre, side="right") - 1] = True
        sample_z = y_error / sd_y
        pre_exceedance = t[(t >= pre) & (t < start) & (abs(sample_z) > 3.)]
        passage.update({"post_support_end_s": stop, "longest_mirror_duration_s": longest,
                        "mirror_runs": runs, "mirror_duration_margin_s": longest - 2.,
                        "MIRROR_FAIL": longest >= 2. - 1e-12,
                        "warning_target_time_s": pre, "warning_y_z": z_pre,
                        "warning_abs_z_margin": None if z_pre is None else abs(z_pre) - 3.,
                        "pre_pass_first_sample_abs_z_gt_3_s": float(pre_exceedance[0]) if len(pre_exceedance) else None,
                        "PRE_PASS_OVERCONFIDENT": None if z_pre is None else abs(z_pre) > 3.,
                        "pre_pass_series": {"time_s": t[pre_window].tolist(),
                                            "truth_y_m": y_truth[pre_window].tolist(),
                                            "estimate_y_m": y_est[pre_window].tolist(),
                                            "error_y_m": y_error[pre_window].tolist(),
                                            "sd_y_m": sd_y[pre_window].tolist(),
                                            "error_over_sd": sample_z[pre_window].tolist()}})
    return {"passages": passages,
            "mirror_fail_count": sum(p["MIRROR_FAIL"] for p in passages),
            "overconfidence_warning_count": sum(p["PRE_PASS_OVERCONFIDENT"] is True for p in passages)}


def _packet_information(trace):
    mask, full = trace["mask"], trace["s_updated"]
    if np.any(full & ~mask):
        raise ValueError("Rejected packet has a polarization update")
    info = np.zeros((len(mask), 2))
    checks = {}
    if np.any(full):
        subset = {key: trace[key][full] for key in ("mask", "Pprior", "H", "Reff", "P", "K")}
        info[full], _, checks = yaw_information(subset, TOLERANCE)
    range_only = mask & ~full
    before = 1. / trace["Pprior"][range_only, 2, 2]
    after = 1. / trace["P"][range_only, 2, 2]
    info[range_only, 0] = after - before
    if np.any((after - before) / np.maximum(1., after) < -TOLERANCE):
        raise ValueError("Range-only update decreased marginal heading precision")
    return info, checks


def _information_summary(info, accepted, updated, dwell, z2, heading95):
    total = info.sum(axis=0)
    groups = {}
    for label, select in (("lt_0.2", dwell < .2), ("0.2_to_lt_0.6", (.2 <= dwell) & (dwell < .6)),
                          ("ge_0.6", dwell >= .6)):
        n = int(select.sum())
        groups[label] = {"packets": n, "heading95_coverage": float(heading95[select].mean()) if n else None,
                         "mean_heading_z2": float(z2[select].mean()) if n else None}
    return {"accepted": int(accepted.sum()), "s_updated": int(updated.sum()),
            "s_updated_fraction": float(updated.sum() / accepted.sum()) if accepted.any() else None,
            "yaw_information_r_s_rad_inverse_square": total.tolist(),
            "kappa_s": float(total[1] / total.sum()) if total.sum() > 0. else None,
            "dwell_bins": groups}


def _gates(point, ci, arm, pooled, mirror_count):
    metrics = ("pose95_coverage", "heading95_coverage") if pooled else COVERAGE
    coverage_min, lo_min, rmse_max = (.90, .80, 1.10) if pooled else (.75, .60, 1.25)
    lower = {name: ci["absolute_ci95"][arm][name][0] for name in metrics}
    coverage_ok = {name: point[arm][name] >= coverage_min for name in metrics}
    lower_ok = {name: lower[name] >= lo_min for name in metrics}
    rmse_ok = {name: point[arm][name] <= rmse_max * point["BASE"][name] for name in RMSE}
    increase = {name: float(100. * (point[arm][name] / point["BASE"][name] - 1.))
                if point["BASE"][name] > 0. else None for name in RMSE}
    nees_ok = 1.5 <= point[arm]["mean_nees3"] <= 6. if pooled else None
    integrity_ok = (all(coverage_ok.values()) and all(lower_ok.values()) and not ci["reference_only"]
                    and nees_ok is not False and mirror_count == 0)
    accuracy_ok = all(rmse_ok.values())
    return {"coverage_min": coverage_min, "coverage_ok": coverage_ok,
            "block_10s_lower_min": lo_min, "block_10s_lower": lower, "block_10s_lower_ok": lower_ok,
            "block_10s_reference_only": ci["reference_only"], "rmse_ratio_max": rmse_max,
            "rmse_increase_pct": increase, "rmse_ok": rmse_ok, "nees3_ok": nees_ok,
            "mirror_fail_count": mirror_count, "accuracy_ok": accuracy_ok,
            "integrity_ok": integrity_ok, "pass": integrity_ok and accuracy_ok}


def evaluate(traces_by_route, truth_by_route, t_by_route):
    """Score the frozen three-route, seven-arm comparison, with BASE = E0-LORO."""
    if set(traces_by_route) != set(truth_by_route) or set(traces_by_route) != set(t_by_route) or set(traces_by_route) != set(ROUTE_PASSES):
        raise ValueError("Expected the frozen R2/R4/R5 grid")
    rows, branches, packet_info, checks = {}, {}, {}, {}
    for route, expected in ROUTE_PASSES.items():
        traces, truth, t = traces_by_route[route], truth_by_route[route], t_by_route[route]
        if set(traces) != set(ARMS) or not np.all(np.diff(t) > 0.):
            raise ValueError(f"Unexpected arm grid or time order for {route}")
        passages = crossings(truth, t)
        if len(passages) != expected:
            raise ValueError(f"{route} has {len(passages)} anchor passages, expected {expected}")
        rows[route], branches[route], packet_info[route], checks[route] = {}, {}, {}, {}
        for arm in ARMS:
            trace = traces[arm]
            if not np.array_equal(trace["mask"], traces["BASE"]["mask"]):
                raise ValueError(f"{route}/{arm} gate differs from BASE")
            rows[route][arm] = from_trace(trace, truth)
            branches[route][arm] = branch_metrics(trace, truth, t)
            info, checks[route][arm] = _packet_information(trace)
            r = rows[route][arm]
            z2 = r[:, 0] / np.rad2deg(np.sqrt(trace["P"][:, 2, 2]))**2
            packet_info[route][arm] = (info, trace["mask"], trace["s_updated"], trace["dwell"], z2, r[:, 5])
    contrasts = [(arm, "BASE") for arm in ARMS if arm != "BASE"]
    result = scores_with_blocks(rows, {route: t_by_route[route] for route in ROUTE_PASSES}, contrasts, blocks=(5, 10, 20))
    information = {route: {arm: _information_summary(*packet_info[route][arm]) for arm in ARMS} for route in ROUTE_PASSES}
    information["pooled"] = {arm: _information_summary(*[np.concatenate(values) for values in
                              zip(*(packet_info[route][arm] for route in ROUTE_PASSES))]) for arm in ARMS}
    gates = {}
    for arm in ARMS:
        gates[arm] = {}
        for group, point in result["point"].items():
            pooled = group == "pooled"
            mirror = (sum(branches[route][arm]["mirror_fail_count"] for route in ROUTE_PASSES) if pooled
                      else branches[group][arm]["mirror_fail_count"])
            gates[arm][group] = _gates(point, result["blocks"]["10"]["by_group"][group], arm, pooled, mirror)
    decisions = {}
    for arm, groups in gates.items():
        m4_groups = [groups[name] for name in ("R2", "R5", "pooled")]
        m4 = "M4_PASS"
        if not all(group["integrity_ok"] for group in m4_groups):
            m4 = "M4_INTEGRITY_FAIL"
        elif not all(group["accuracy_ok"] for group in m4_groups):
            m4 = "M4_ACCURACY_FAIL"
        r4_pass = groups["R4"]["pass"]
        decisions[arm] = {"R4_pass": r4_pass, "M4": m4, "all_pass": r4_pass and m4 == "M4_PASS"}
    m1 = "M1_FAIL"
    if decisions["D05"]["R4_pass"]:
        m1 = "M1_PASS"
    elif decisions["D10"]["R4_pass"] or decisions["D20"]["R4_pass"]:
        m1 = "M1_LENGTH_SENSITIVE"
    result.update(branch=branches, information=information, d2_checks=checks, gates=gates,
                  decisions={"M1": m1, "M4": decisions["D05"]["M4"], "by_arm": decisions})
    return result
