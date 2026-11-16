"""M6 offline characterization for G1-INT-001/M6."""
import numpy as np


ROUTES = ("R2", "R4", "R5")
DISTANCE_EDGES_M = (0., 1.5, 3., 6., 10.)
BLOCK_SECONDS = 10.
MIN_PACKETS = 30
MIN_BLOCKS = 2
MIN_G_RATIO = 1.2
BOOTSTRAP_REPLICATES = 1500
BOOTSTRAP_SEED = 20261115
MIN_G_REF = 1.
MAD_FACTOR = 1.4826
KERNEL_DISTANCE_M = 1.
KERNEL_YAW_RAD = np.deg2rad(10.)
PAIR_LAG_SECONDS = (.4, 5.)
MIN_PAIRS = 10


def _ordered_cases(cases):
    if set(cases) != set(ROUTES):
        raise ValueError("Expected exactly the R2/R4/R5 seed 10 cases")
    prepared = {}
    keys = ("t", "mask", "g_truth", "truth_distance", "prior_distance", "a_ref",
            "slow_s", "raw_s", "support", "arc", "yaw_arc", "window_a_ref")
    for route in ROUTES:
        data = dict(cases[route])
        data.update({key: np.asarray(data[key]) for key in keys})
        t = data["t"]
        if t.ndim != 1 or not t.size:
            raise ValueError(f"{route}: invalid grid size")
        if any(data[key].shape != t.shape or not np.isfinite(data[key]).all() for key in keys):
            raise ValueError(f"{route}: mismatched or nonfinite case arrays")
        if any(data[k].dtype != bool for k in ("mask", "support")):
            raise ValueError(f"{route}: support and mask must be boolean")
        if np.any(np.diff(t) <= 0) or any(np.any(np.diff(data[k]) < 0) for k in ("arc", "yaw_arc")):
            raise ValueError(f"{route}: invalid time or motion order")
        if any(np.any(data[k] < 0) for k in ("g_truth", "truth_distance", "prior_distance")):
            raise ValueError(f"{route}: negative distance or unsigned truth sensitivity")
        if not np.isfinite(data["route_mean_s"]).all() or np.asarray(data["route_mean_s"]).ndim != 0:
            raise ValueError(f"{route}: invalid D3 route mean")
        data["elapsed"] = t - t[0]
        data["block"] = np.floor(data["elapsed"] / BLOCK_SECONDS).astype(int)
        data["g_ref"] = np.abs(data["a_ref"])
        prepared[route] = data
    return prepared


def _distance_bins(distance):
    return np.searchsorted(DISTANCE_EDGES_M, distance, side="right") - 1


def _tertiles(values):
    return np.quantile(values, (1. / 3., 2. / 3.)) if len(values) else None


def _group(g, edges):
    return np.searchsorted(edges, g, side="left")


def _nblocks(data, use):
    return int(np.unique(data["block"][use]).size)


def _var_row(data, use):
    g, slow = data["g_truth"][use], data["slow_s"][use]
    blocks = _nblocks(data, use)
    if not len(slow):
        return dict(n=0, n_blocks=blocks, mean_s=None, variance_s=None, g_rms=None, eligible=False)
    variance = float(slow.var())
    g_rms = float(np.sqrt(np.mean(g * g)))
    eligible = len(slow) >= MIN_PACKETS and blocks >= MIN_BLOCKS and variance > 0. and g_rms > 0.
    return dict(n=int(len(slow)), n_blocks=blocks, mean_s=float(slow.mean()), variance_s=variance,
                g_rms=g_rms, eligible=bool(eligible))


def _eligible_rows(cases, accepted):
    strata, all_rows, distance_rows = [], [], []
    for route, data in cases.items():
        use_population = data["support"] & data["mask"] if accepted else data["support"]
        distance = _distance_bins(data["truth_distance"])
        for k in range(len(DISTANCE_EDGES_M) - 1):
            use_bin = use_population & (distance == k)
            edges = _tertiles(data["g_truth"][use_bin])
            base = dict(route=route, distance_bin=k)
            distance_rows.append({**base, **_var_row(data, use_bin)})
            if edges is None:
                strata.append({**base, "g_tertiles": None, "accepted_stratum": False, "g_rms_ratio": None})
                continue
            groups = _group(data["g_truth"], edges)
            rows = []
            for subgroup in range(3):
                use = use_bin & (groups == subgroup)
                row = {**base, "g_group": subgroup, **_var_row(data, use)}
                rows.append((row, use))
            grms = [row["g_rms"] for row, _ in rows if row["eligible"]]
            ratio = max(grms) / min(grms) if len(grms) >= 2 else None
            good = ratio is not None and ratio >= MIN_G_RATIO
            strata.append({**base, "g_tertiles": edges.tolist(), "accepted_stratum": good, "g_rms_ratio": ratio})
            all_rows.extend((dict(row, accepted_stratum=good), use) for row, use in rows)
    return strata, all_rows, distance_rows


def _fixed_effect_slope(x, y, groups):
    # Each variance row has identical weight, including during resampling.
    numerator = np.zeros(x.shape[:-1])
    denominator = np.zeros_like(numerator)
    for group in sorted(set(groups)):
        use = np.asarray([value == group for value in groups])
        x_subset, y_subset = x[..., use], y[..., use]
        centered_x = x_subset - x_subset.mean(axis=-1, keepdims=True)
        centered_y = y_subset - y_subset.mean(axis=-1, keepdims=True)
        numerator += np.sum(centered_x * centered_y, axis=-1)
        denominator += np.sum(centered_x * centered_x, axis=-1)
    return np.divide(numerator, denominator, out=np.full_like(numerator, np.nan), where=denominator > 0)


def _slope(rows, strata=("route", "distance_bin")):
    if not rows:
        return None
    groups = [tuple(row[key] for key in strata) for row, _ in rows]
    x = np.log([row["g_rms"] for row, _ in rows])
    y = np.log([row["variance_s"] for row, _ in rows])
    slope = _fixed_effect_slope(x, y, groups)
    return float(slope) if np.isfinite(slope) else None


def _bootstrap(cases, rows):
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    weights = {route: rng.exponential(size=(BOOTSTRAP_REPLICATES, int(data["block"].max()) + 1))
               for route, data in cases.items()}
    x, y, groups = [], [], []
    for row, use in rows:
        route = row["route"]
        data = cases[route]
        block = data["block"][use]
        w = weights[route]
        # Center around the fixed row mean to reduce cancellation when computing weighted variances.
        slow = data["slow_s"][use] - row["mean_s"]
        g = data["g_truth"][use]
        stats = [np.bincount(block, weights=v, minlength=w.shape[1])
                 for v in (np.ones(len(slow)), slow, slow * slow, g * g)]
        n, s, s2, g2 = (w @ np.column_stack(stats)).T
        variance = s2 / n - (s / n)**2
        with np.errstate(divide="ignore", invalid="ignore"):
            x.append(.5 * np.log(g2 / n))
            y.append(np.log(variance))
        groups.append((route, row["distance_bin"]))
    slopes = _fixed_effect_slope(np.column_stack(x), np.column_stack(y), groups)
    finite = int(np.count_nonzero(np.isfinite(slopes)))
    return (np.quantile(slopes, [.025, .975]).tolist() if finite == BOOTSTRAP_REPLICATES else None, finite)


def _ratio_rows(rows):
    ratios = []
    for k in range(len(DISTANCE_EDGES_M) - 1):
        reports = {row["route"]: row for row in rows if row["distance_bin"] == k}
        for i, first in enumerate(ROUTES):
            for second in ROUTES[:i]:
                a, b = reports[first], reports[second]
                ratios.append(dict(distance_bin=k, numerator=first, denominator=second,
                                   n=[a["n"], b["n"]],
                                   variance_ratio=a["variance_s"] / b["variance_s"]
                                   if a["variance_s"] is not None and b["variance_s"] else None,
                                   mean_g_squared_ratio=(a["g_rms"] / b["g_rms"])**2
                                   if a["g_rms"] is not None and b["g_rms"] else None))
    return ratios


def _k1(cases, accepted):
    strata, rows, distance_rows = _eligible_rows(cases, accepted)
    eligible = [(row, use) for row, use in rows if row["eligible"]]
    model_rows = [(row, use) for row, use in eligible if row["accepted_stratum"]]
    supported_routes = sorted({row["route"] for row, _ in model_rows})
    supported_bins = sorted({row["distance_bin"] for row, _ in model_rows})
    descriptive = _slope(model_rows)
    slope = descriptive if len(supported_routes) >= 2 and len(supported_bins) >= 2 else None
    ci, replicates = _bootstrap(cases, model_rows) if slope is not None else (None, 0)
    verdict = "K1_PRIME_INCONCLUSIVE"
    if ci is not None:
        if ci[1] < 2.:
            verdict = "UPPER_95_LT_2"
        elif ci[0] > 2.:
            verdict = "LOWER_95_GT_2"
        else:
            verdict = "CI_95_CONTAINS_2"
    r2 = cases["R2"]
    elapsed = r2["elapsed"]
    local_use = r2["support"] & (elapsed >= 120.) & (elapsed <= 140.)
    if accepted:
        local_use &= r2["mask"]
    local = {"R2_120_to_140_s": _var_row(r2, local_use)}
    r5 = cases["R5"]
    for i, pass_time in enumerate(r5.get("pass_times", []), start=1):
        local_use = r5["support"] & (np.abs(r5["t"] - pass_time) <= 10.)
        if accepted:
            local_use &= r5["mask"]
        local[f"R5_pass_{i}"] = {"t_pass": float(pass_time), **_var_row(r5, local_use)}
    return dict(verdict=verdict, trigger_hybrid=verdict == "UPPER_95_LT_2", slope=slope, ci_95=ci,
                bootstrap_finite_replicates=replicates, eligible_routes=supported_routes,
                eligible_distance_bins=supported_bins, descriptive_slope_if_support_insufficient=descriptive,
                slopes_by_distance_bin={str(k): _slope([(row, use) for row, use in model_rows
                                                        if row["distance_bin"] == k])
                                        for k in range(len(DISTANCE_EDGES_M) - 1)},
                distance_only_intercept_slope=_slope(eligible, strata=("distance_bin",)),
                strata=strata, rows=[row for row, _ in rows], route_distance_rows=distance_rows,
                cross_route_ratios=_ratio_rows(distance_rows), local=local,
                d3_route_mean_s={route: float(data["route_mean_s"]) for route, data in cases.items()})


def _heading_equivalent(data, supported):
    a_ref = data["a_ref"]
    use = supported & (np.abs(a_ref) >= MIN_G_REF)
    return use, data["slow_s"][use] / a_ref[use]


def _scale(values):
    return float(MAD_FACTOR * np.median(np.abs(values))) if len(values) else None


def _heading_summary(values):
    if not len(values):
        return dict(n=0, sigma_rad=None, signed_median_rad=None, centered_mad_rad=None,
                    abs_p75_rad=None, abs_p95_rad=None, signed_p75_rad=None, signed_p95_rad=None)
    median = np.median(values)
    p75, p95 = np.quantile(np.abs(values), [.75, .95])
    signed_p75, signed_p95 = np.quantile(values, [.75, .95])
    return dict(n=int(len(values)), sigma_rad=_scale(values), signed_median_rad=float(median),
                centered_mad_rad=_scale(values - median), abs_p75_rad=float(p75), abs_p95_rad=float(p95),
                signed_p75_rad=float(signed_p75), signed_p95_rad=float(signed_p95))


def _heading_cells(cases):
    geometry_support = [data["g_ref"][data["support"]] for data in cases.values()]
    edges = _tertiles(np.concatenate(geometry_support))
    if edges is None:
        raise ValueError("No D3-supported packets for K2 geometry edges")
    rows = []
    for route, data in cases.items():
        g_group = _group(data["g_ref"], edges)
        distance_bin = _distance_bins(data["prior_distance"])
        for k in range(len(DISTANCE_EDGES_M) - 1):
            for group in range(3):
                candidates = data["support"] & (g_group == group) & (distance_bin == k)
                use, values = _heading_equivalent(data, candidates)
                n_blocks = _nblocks(data, use)
                summary = _heading_summary(values)
                eligible = (len(values) >= MIN_PACKETS and n_blocks >= MIN_BLOCKS and summary["sigma_rad"] > 0.)
                rows.append(dict(route=route, distance_bin=k, g_group=group, **summary,
                                 n_blocks=n_blocks, candidates=int(candidates.sum()),
                                 cutoff_excluded_fraction=float(1. - len(values) / candidates.sum())
                                 if np.any(candidates) else None, eligible=bool(eligible)))
    common = []
    for k in range(len(DISTANCE_EDGES_M) - 1):
        for group in range(3):
            cell = [r for r in rows if (r["distance_bin"], r["g_group"]) == (k, group) and r["eligible"]]
            if len(cell) == len(cases):
                scales = [r["sigma_rad"] for r in cell]
                common.append(dict(distance_bin=k, g_group=group, max_min_ratio=max(scales) / min(scales),
                                   scales_rad={r["route"]: r["sigma_rad"] for r in cell}))
    return dict(g_tertiles=edges.tolist(), rows=rows, common_cells=common,
                n_eligible_rows=sum(r["eligible"] for r in rows))


def _distance_table(donors):
    rows = []
    for k, (left, right) in enumerate(zip(DISTANCE_EDGES_M[:-1], DISTANCE_EDGES_M[1:], strict=True)):
        entries, values = {}, []
        for route, data in donors.items():
            use, b = _heading_equivalent(data, data["support"] & (_distance_bins(data["prior_distance"]) == k))
            blocks = _nblocks(data, use)
            record = _heading_summary(b)
            supported = len(b) >= MIN_PACKETS and blocks >= MIN_BLOCKS and record["sigma_rad"] > 0.
            entries[route] = dict(**record, n_blocks=blocks, eligible=bool(supported))
            values.append(b)
        valid = all(row["eligible"] for row in entries.values())
        rows.append(dict(distance_bin=k, midpoint_m=(left + right) / 2., donors=entries,
                         sigma_rad=_scale(np.concatenate(values)) if valid else None))
    valid = [r for r in rows if r["sigma_rad"] is not None]
    # A single joint donor bin cannot establish a distance-dependent curve.
    table = dict(knots_m=[r["midpoint_m"] for r in valid], sigma_rad=[r["sigma_rad"] for r in valid]) if len(valid) >= 2 else None
    return table, rows


def _k2(cases):
    main = _heading_cells(cases)
    common = main["common_cells"]
    verdict = "NO_COMMON_SUPPORT" if not common else (
        "DISTANCE_TABLE_BRANCH" if max(r["max_min_ratio"] for r in common) > 2. else "CONSTANT_SUPPORTED")
    folds = {}
    for held in ROUTES:
        donors = {route: data for route, data in cases.items() if route != held}
        samples, accepted, window, by_donor = {}, {}, {}, {}
        for route, data in donors.items():
            use, sample = _heading_equivalent(data, data["support"])
            _, accepted_sample = _heading_equivalent(data, data["support"] & data["mask"])
            a_window = data["window_a_ref"]
            window_use = data["support"] & (np.abs(a_window) >= MIN_G_REF)
            window_sample = data["slow_s"][window_use] / a_window[window_use]
            samples[route] = sample
            accepted[route] = accepted_sample
            window[route] = window_sample
            eligible_count = int(use.sum())
            supported_count = int(data["support"].sum())
            by_donor[route] = dict(primary=_heading_summary(sample), accepted=_heading_summary(accepted_sample),
                                   window_mean_denominator=_heading_summary(window_sample),
                                   n_d3_supported=supported_count,
                                   n_excluded_by_g_cutoff=supported_count - eligible_count)
        primary = _heading_summary(np.concatenate(list(samples.values())))
        if primary["sigma_rad"] is None or primary["sigma_rad"] <= 0.:
            raise ValueError(f"{held}: LORO heading scale is not estimable")
        centered = [sample - np.median(sample) for sample in samples.values() if len(sample)]
        table, table_rows = _distance_table(donors) if verdict == "DISTANCE_TABLE_BRANCH" else (None, None)
        folds[held] = dict(sigma_rad=primary["sigma_rad"], primary=primary, donors=by_donor,
                           centered_per_donor_sensitivity=_heading_summary(np.concatenate(centered)),
                           accepted_sensitivity=_heading_summary(np.concatenate(list(accepted.values()))),
                           window_mean_sensitivity=_heading_summary(np.concatenate(list(window.values()))),
                           donor_cells=_heading_cells(donors), distance_table=table, distance_rows=table_rows,
                           distance_status=("SUPPORTED" if table is not None else "NOT_ESTIMABLE")
                           if verdict == "DISTANCE_TABLE_BRANCH" else "NOT_TRIGGERED")
    return dict(verdict=verdict, minimum_g_rad_inverse=MIN_G_REF,
                primary_centering="D3 route mean and supported slow mean only",
                main_cells=main, folds=folds)


def _pair_blocks(data, k, sigma_rad):
    distance = _distance_bins(data["prior_distance"])
    use = data["mask"] & (distance == k)
    hazard = data["arc"] / KERNEL_DISTANCE_M + data["yaw_arc"] / KERNEL_YAW_RAD
    residual = data["raw_s"] - data["route_mean_s"]
    a_ref = data["a_ref"]
    reports = []
    for block in np.unique(data["block"][use]):
        ids = np.flatnonzero(use & (data["block"] == block))
        local_i, local_j = np.triu_indices(len(ids), k=1)
        i, j = ids[local_i], ids[local_j]
        dt = data["t"][j] - data["t"][i]
        pair = (PAIR_LAG_SECONDS[0] <= dt) & (dt <= PAIR_LAG_SECONDS[1])
        i, j = i[pair], j[pair]
        out = dict(block=int(block), n_pairs=int(len(i)), numerator=None, denominator=None)
        if len(i) >= MIN_PAIRS:
            kernel = np.exp(hazard[i] - hazard[j])
            leftover = residual[i] * residual[j] - sigma_rad**2 * a_ref[i] * a_ref[j] * kernel
            out.update(numerator=float(np.mean(kernel * leftover)), denominator=float(np.mean(kernel**2)))
        reports.append(out)
    good = [row for row in reports if row["numerator"] is not None]
    return dict(blocks=reports, supported_blocks=len(good),
                numerator=float(np.mean([row["numerator"] for row in good])) if len(good) >= MIN_BLOCKS else None,
                denominator=float(np.mean([row["denominator"] for row in good])) if len(good) >= MIN_BLOCKS else None)


def _hybrid(cases, k2):
    folds = {}
    for held in ROUTES:
        sig = k2["folds"][held]["sigma_rad"]
        bins = []
        for k in range(len(DISTANCE_EDGES_M) - 1):
            donors = {route: _pair_blocks(data, k, sig) for route, data in cases.items() if route != held}
            supported = all(row["numerator"] is not None for row in donors.values())
            q = None
            if supported:
                q = sum(row["numerator"] for row in donors.values()) / sum(row["denominator"] for row in donors.values())
            bins.append(dict(distance_bin=k, donors=donors, supported=supported, unconstrained_q_s=q,
                             q_s=max(0., q) if supported else 0., clamped_to_zero=bool(supported and q < 0.)))
        folds[held] = dict(bins=bins, status="ESTIMABLE" if any(row["supported"] for row in bins) else "NOT_ESTIMABLE",
                           q_s=[row["q_s"] for row in bins], supported_bins=[row["supported"] for row in bins])
    return dict(folds=folds)


def characterize(cases):
    """Run offline K1′ then K2, followed by any conditional LORO donor fit."""
    cases = _ordered_cases(cases)
    k1 = _k1(cases, accepted=True)
    k1["all_d3_supported_sensitivity"] = _k1(cases, accepted=False)
    k2 = _k2(cases)
    return dict(distance_edges_m=list(DISTANCE_EDGES_M), k1=k1, k2=k2,
                period_definition="floor((t - t_at_first_packet) / 10 s), within each route",
                tie_assignment="All values equal to a tertile cut enter the same lower group",
                hybrid=_hybrid(cases, k2) if k1["trigger_hybrid"] else None)
