"""Trace-only HF-KI prediction and donor-only A3 range-noise fitting."""

import numpy as np


ROUTES = ("R2", "R4", "R5")
SIGMA_GRID_DEG = (2, 3, 4, 6, 8)
DISTANCE_EDGES_M = (0., 1.5, 3., 6., 10.)
DISTANCE_LENGTH_M = 1.
YAW_LENGTH_DEG = 10.
HISTORY_SECONDS = 10.
HISTORY_LIMIT = 100
A3_MIN_CENTERS = 30
A3_WINDOW_SECONDS = 20.
A3_MIN_COMPLETE_WINDOWS = 2
C1_REFERENCE_MEDIAN = 20.4


def distance_bin_contract():
    """Return the outcome-independent A3 fit and lookup conventions."""
    return {"distance_edges_m": list(DISTANCE_EDGES_M),
            "bin_closure": "left closed, right open",
            "fit_coordinate": "E0-LORO prior horizontal distance to anchor",
            "replay_coordinate": "own-arm prior horizontal distance to anchor",
            "fit": "Equal-weight mean of two donor population variances of D3 slow range residual",
            "eligibility": "D3-supported, E0-accepted donor rows",
            "min_centers_per_donor_bin": A3_MIN_CENTERS,
            "window_seconds": A3_WINDOW_SECONDS,
            "min_occupied_complete_windows_per_donor_bin": A3_MIN_COMPLETE_WINDOWS,
            "outside_distance_bins": "No range-channel addition; report usage"}


def _grid(reference, candidate, label):
    for name in ("t", "pose_id"):
        if not np.array_equal(reference[name], candidate[name]):
            raise ValueError(f"{label} {name} does not match the frozen grid")
    if "mask" in candidate and not np.array_equal(reference["mask"], candidate["mask"]):
        raise ValueError(f"{label} differs from the frozen acceptance mask")


def _distribution(values):
    summary = {"packets": int(values.size)}
    quantiles = (("p05", .05), ("p25", .25), ("median", .50), ("p75", .75), ("p95", .95))
    values_at_quantiles = np.quantile(values, [value for _, value in quantiles]) if values.size else [None] * len(quantiles)
    summary.update(zip((name for name, _ in quantiles), values_at_quantiles, strict=True))
    return summary


def _cell_information(t, arc, yaw, mask, g, r_ss):
    """Include the current packet at unit kernel weight and the causal accepted history."""
    if (not all(a.shape == t.shape and np.isfinite(a).all() for a in (arc, yaw, mask, g, r_ss))
            or not np.isfinite(t).all() or np.any(np.diff(t) <= 0.) or np.any(np.diff(arc) < 0.)
            or np.any(np.diff(yaw) < 0.) or np.any(r_ss <= 0.) or mask.dtype != bool):
        raise ValueError("Invalid geometry, mask, or variance in the Stage 1 baseline")
    precision = g**2 / r_ss
    hazard = arc / DISTANCE_LENGTH_M + yaw / np.deg2rad(YAW_LENGTH_DEG)
    accepted = np.flatnonzero(mask)
    lo = np.searchsorted(t[accepted], t - HISTORY_SECONDS, side="left")
    hi = np.searchsorted(accepted, np.arange(t.size), side="left")
    result = precision.copy()
    for i, (start, end) in enumerate(zip(lo, hi, strict=True)):
        past = accepted[max(start, end - HISTORY_LIMIT):end]
        result[i] += np.exp(hazard[past] - hazard[i]) @ precision[past]
    return result


def _segments(route, t):
    elapsed = t - t[0]
    intervals = {"all": np.ones(t.size, dtype=bool)}
    if route == "R2":
        inside = (120. <= elapsed) & (elapsed <= 140.)
        intervals.update(elapsed_120_to_140_s=inside, rest=~inside)
    if route == "R5":
        inside = elapsed <= 44.
        intervals.update(approach_elapsed_0_to_44_s=inside, after_approach=~inside)
    return intervals


def _information_report(information, groups, mask):
    reports = {}
    for label, segment in groups.items():
        reports[label] = {}
        for population, use in (("full_grid", segment), ("accepted", segment & mask)):
            sample = information[use]
            reports[label][population] = {
                "I_cell_rad_inverse_square": _distribution(sample),
                "predicted_F_by_sigma_deg": {str(sigma): _distribution(1. + sample * np.deg2rad(sigma)**2)
                                             for sigma in SIGMA_GRID_DEG},
            }
    return reports


def _fit_range_table(donors):
    """Use centered D3 variance within each bin and give each donor equal weight."""
    rows = []
    for left, right in zip(DISTANCE_EDGES_M[:-1], DISTANCE_EDGES_M[1:], strict=True):
        entries = {}
        for route, donor in donors.items():
            d = donor["distance_m"]
            use = donor["support"] & donor["mask"] & (left <= d) & (d < right)
            elapsed = donor["t"] - donor["t"][0]
            window = np.floor(elapsed[use] / A3_WINDOW_SECONDS).astype(int)
            complete = int(np.floor((elapsed[-1] + 1e-9) / A3_WINDOW_SECONDS))
            occupied = np.unique(window[window < complete]).size
            slow = donor["slow"][use, 0]
            if slow.size < A3_MIN_CENTERS or occupied < A3_MIN_COMPLETE_WINDOWS:
                raise ValueError(f"A3 unsupported donor bin: {route} [{left}, {right})")
            entries[route] = {"packets": int(slow.size), "complete_20s_windows": int(occupied),
                              "slow_range_variance_m2": float(slow.var())}
        mean = float(np.mean([d["slow_range_variance_m2"] for d in entries.values()]))
        rows.append({"distance_m": [left, right], "donors": entries, "variance_m2": mean})
    return {"bins": rows, "table": {"distance_edges_m": list(DISTANCE_EDGES_M),
                                   "variances_m2": [row["variance_m2"] for row in rows]}}


def _donor_heading_floor(donors):
    samples = {}
    for route, donor in donors.items():
        use = donor["support"] & (donor["g"] >= 1.)
        samples[route] = np.rad2deg(np.abs(donor["slow"][use, 1] / donor["g"][use]))
    return {"pool": _distribution(np.concatenate(list(samples.values()))),
            "per_donor": {label: _distribution(sample) for label, sample in samples.items()}}


def predict(cases, d3_records, c1_ki):
    """Stage 1 from authenticated E0-LORO, frozen D3, and matched C1 KI traces."""
    from d3 import motion_arcs

    if set(cases) != set(ROUTES) or set(d3_records) != set(ROUTES):
        raise ValueError("Expected exactly the R2/R4/R5 Stage 1 grid")
    forecasts, donors = {}, {}
    for route in ROUTES:
        case, d3 = cases[route], d3_records[route]
        packet, trace, spec = case["packet"], case["loro"], case["spec"]
        _grid(trace, packet, f"{route} packet")
        _grid(trace, d3, f"{route} D3")
        t, mask = trace["t"], trace["mask"]
        arc, yaw = motion_arcs(packet, trace)
        g = np.abs(trace["H"][:, 1, 2])
        information = _cell_information(t, arc, yaw, mask, g, trace["Reff"][:, 1, 1])
        forecasts[route] = _information_report(information, _segments(route, t), mask)
        slow, support = d3["slow"], d3["decomposition_support"]
        if (slow.shape != (t.size, 2) or support.shape != t.shape or support.dtype != bool
                or not np.isfinite(slow).all()):
            raise ValueError(f"{route} has invalid D3 slow or support fields")
        distance = np.linalg.norm(trace["prior"][:, :2] - np.asarray(spec["anchor"][:2]), axis=1)
        donors[route] = {"t": t, "g": g, "mask": mask, "distance_m": distance,
                         "slow": slow, "support": support}

    heading_floor, range_folds = {}, {}
    for evaluation_route in ROUTES:
        fold = {route: donors[route] for route in ROUTES if route != evaluation_route}
        heading_floor[evaluation_route] = _donor_heading_floor(fold)
        range_folds[evaluation_route] = _fit_range_table(fold)

    r4 = cases["R4"]["loro"]
    _grid(r4, c1_ki, "R4 C1 KI")
    mask = r4["mask"]
    actual_ratio = c1_ki["Reff"][mask, 1, 1] / r4["Reff"][mask, 1, 1]
    if not np.isfinite(actual_ratio).all() or np.any(actual_ratio <= 0.):
        raise ValueError("Invalid C1 KI realized variance ratio")
    c1_inflation = _distribution(actual_ratio)
    predicted = forecasts["R4"]["all"]["accepted"]["predicted_F_by_sigma_deg"]
    comparison = {sigma: {"predicted_median_over_20p4": result["median"] / C1_REFERENCE_MEDIAN,
                          "predicted_median_over_realized_C1": result["median"] / c1_inflation["median"]}
                  for sigma, result in predicted.items()}
    return {
        "status": "DESCRIPTIVE_ONLY", "scope": {"mount_deg": 0, "anchor": "B", "bias": "B0", "seed": 10},
        "sigma_grid_deg": list(SIGMA_GRID_DEG),
        "kernel": {"distance_length_m": DISTANCE_LENGTH_M, "yaw_length_deg": YAW_LENGTH_DEG,
                   "history_seconds_inclusive": HISTORY_SECONDS, "max_earlier_accepted": HISTORY_LIMIT},
        "forecasts": forecasts,
        "R4_C1_KI_comparison_accepted": {"reference_median_from_plan": C1_REFERENCE_MEDIAN,
                                         "realized_R_ss_over_R_ref": c1_inflation,
                                         "predicted_to_realized_by_sigma_deg": comparison},
        "sigma_theta_LORO_deg": {"definition": "|D3.slow_s / E0-LORO prior g| in degrees",
                                  "eligibility": "D3-supported donor rows with g >= 1.0, including gate-rejected rows",
                                  "folds": heading_floor},
        "A3_range_KI": {**distance_bin_contract(), "folds": range_folds},
    }
