"""V8 donor-only transfer and V1/V2 variogram diagnostics for KS."""

import numpy as np
from scipy.optimize import nnls
from scipy.sparse import csr_matrix

from d3 import component_summary, decompose


ROUTES = ("R2", "R4", "R5")
DISTANCE_EDGES = np.array([1.5, 3., 6., 10.])
LAG_EDGES = np.geomspace(.02, 4., 17)
FAST_LENGTHS = np.geomspace(.02, .5, 25)
SLOW_LENGTHS = np.geomspace(.5, 8., 25)
MIN_VARIANCE = 1e-12
MIN_PAIRS = 50
D3_CONFIG = dict(half_seconds=5., half_distance_m=.25, half_yaw_deg=5.,
                 min_window_packets=10)


def _channel(values):
    values = np.asarray(values, dtype=float)
    if values.ndim == 2 and values.shape[1] == 2:
        return values[:, 1]
    if values.ndim == 3 and values.shape[1:] == (2, 2):
        return values[:, 1, 1]
    if values.ndim == 1:
        return values
    raise ValueError("Unsupported polarization trace shape")


def _prepare(case):
    t, arc, yaw, g, d = [np.asarray(case[key], dtype=float) for key in ("t", "arc", "yaw", "g", "d")]
    mask = np.asarray(case["mask"])
    residual, rref = _channel(case["eps"]), _channel(case["Rref"])
    arrays = (t, arc, yaw, g, d, mask, residual, rref)
    if (t.size < 2 or any(x.shape != t.shape or x.ndim != 1 for x in arrays)
            or mask.dtype != bool or not all(np.isfinite(x).all() for x in arrays)
            or (np.diff(t) <= 0).any() or (np.diff(arc) < 0).any() or (np.diff(yaw) < 0).any()
            or (g < 0).any() or (d < 0).any() or (rref <= 0).any()):
        raise ValueError("Invalid V8 trace geometry, residual, mask, or reference variance")
    eps = np.column_stack([np.zeros_like(residual), residual])
    try:
        parts = decompose(eps, t, arc, yaw, D3_CONFIG)
    except ValueError as exc:
        if str(exc) != "D3 has no locally supported residual decomposition":
            raise
        zeros = np.zeros_like(eps)
        parts = dict(support=np.zeros_like(mask), slow=zeros, fast=zeros, reconstruction_error=0.)
    bins = np.searchsorted(DISTANCE_EDGES, d, side="right") - 1
    return dict(t=t, arc=arc, yaw=yaw, g=g, d=d, mask=mask, eps=eps, rref=rref,
                parts=parts, bins=bins, eligible=mask & parts["support"])


def _indices(case, bin_index):
    return np.flatnonzero(case["eligible"] & (case["bins"] == bin_index))


def _support(case, indices):
    elapsed = case["t"] - case["t"][0]
    complete = int(np.floor((elapsed[-1] + 1e-9) / 20.))
    windows = np.floor(elapsed[indices] / 20.).astype(int)
    occupied = np.unique(windows[windows < complete]).size
    return dict(n=int(indices.size), windows=int(occupied),
                supported=bool(indices.size >= 30 and occupied >= 2))


def _donor_model(donors, indices, support):
    if not all(row["supported"] for row in support):
        return None, None, None
    design, targets = [], []
    for donor, idx in zip(donors, indices, strict=True):
        slow = donor["parts"]["slow"][idx, 1]
        scale = np.sqrt(idx.size)
        design.append(np.column_stack([np.ones(idx.size), donor["g"][idx] ** 2]) / scale)
        targets.append((slow - slow.mean()) ** 2 / scale)
    distance_only = float(np.mean([np.mean(y * np.sqrt(idx.size))
                                   for y, idx in zip(targets, indices, strict=True)]))
    matrix = np.vstack(design)
    rank = int(np.linalg.matrix_rank(matrix))
    if rank < 2:
        return None, distance_only, rank
    beta, _ = nnls(matrix, np.concatenate(targets))
    return beta.tolist(), distance_only, rank


def _sensitivity(g, donor_g, beta, observed):
    maximum = p95 = capped = None
    count = count_p95 = None
    if donor_g.size:
        maximum = float(donor_g.max())
        p95 = float(np.quantile(donor_g, .95))
        count, count_p95 = int(np.sum(g > maximum)), int(np.sum(g > p95))
        if beta is not None and g.size:
            capped = float(beta[0] + beta[1] * np.mean(np.minimum(g, maximum) ** 2))
    return dict(donor_g_max=maximum, donor_g_p95=p95, exceed_max_n=count,
                exceed_p95_n=count_p95, exceed_max_fraction=count / g.size if (count is not None and g.size) else None,
                exceed_p95_fraction=count_p95 / g.size if (count_p95 is not None and g.size) else None,
                capped_prediction=capped,
                capped_prediction_ratio=capped / observed if (capped is not None and observed > MIN_VARIANCE) else None)


def v8(cases):
    """Fit 2-coefficient distance-bin models using only the designated donor roles."""
    if set(cases) != set(ROUTES) or any(set(case) != set(ROUTES) for case in cases.values()):
        raise ValueError("V8 requires exactly three folds and all routes within each fold")
    prepared = {fold: {route: _prepare(case) for route, case in rows.items()}
                for fold, rows in cases.items()}
    rows, folds, models = [], {}, {}
    for fold in ROUTES:
        donors = [route for route in ROUTES if route != fold]
        fold_rows = []
        models[fold] = {}
        for bin_index in range(3):
            slices = {route: _indices(prepared[fold][route], bin_index) for route in ROUTES}
            support = {route: _support(prepared[fold][route], slices[route]) for route in ROUTES}
            beta, baseline, rank = _donor_model([prepared[fold][r] for r in donors],
                                                [slices[r] for r in donors],
                                                [support[r] for r in donors])
            donor_g = {r: prepared[fold][r]["g"][slices[r]] for r in donors}
            eval_case, eval_idx = prepared[fold][fold], slices[fold]
            test_g = eval_case["g"][eval_idx]
            observed = float(np.var(eval_case["parts"]["slow"][eval_idx, 1])) if eval_idx.size else 0.
            prediction = float(beta[0] + beta[1] * np.mean(test_g ** 2)) if beta is not None and test_g.size else None
            ratio = prediction / observed if (prediction is not None and observed > MIN_VARIANCE) else None
            reason = None
            if not all(row["supported"] for row in support.values()):
                reason = "INSUFFICIENT_PACKET_OR_WINDOW_SUPPORT"
            elif beta is None:
                reason = "RANK_DEFICIENT"
            elif ratio is None:
                reason = "DEGENERATE_MEASURED_VARIANCE"
            status = "INCONCLUSIVE" if reason else "PASS" if .5 <= ratio <= 2. else "FAIL"
            details = _sensitivity(test_g, np.concatenate(list(donor_g.values())), beta, observed)
            row = dict(fold=fold, donors=donors, bin_index=bin_index,
                       distance_m=DISTANCE_EDGES[bin_index:bin_index + 2].tolist(),
                       support=support, donor_g_quantiles={r: np.quantile(g, [.5, .95, 1.]).tolist() if g.size else None
                                                         for r, g in donor_g.items()},
                       status=status, inconclusive_reason=reason, beta=beta, design_rank=rank,
                       measured=observed if eval_idx.size else None, prediction=prediction, ratio=ratio,
                       slow_distance=baseline,
                       distance_prediction_ratio=baseline / observed if (baseline is not None and observed > MIN_VARIANCE) else None,
                       **details)
            fold_rows.append(row)
            models[fold][bin_index] = dict(beta=beta, slow_distance=baseline)
        rows.extend(fold_rows)
        n = sum(row["support"][fold]["n"] for row in fold_rows if row["exceed_max_n"] is not None)
        exceed = sum(row["exceed_max_n"] or 0 for row in fold_rows)
        fraction = exceed / n if n else None
        statuses = {row["status"] for row in fold_rows}
        status = ("FAIL" if "FAIL" in statuses else "INCONCLUSIVE" if "INCONCLUSIVE" in statuses
                  else "EXTRAPOLATION_PASS" if fraction is not None and fraction > .5 else "PASS")
        focus_case = prepared[fold][fold]
        outside = focus_case["eligible"]
        folds[fold] = dict(status=status, exceed_max_n=exceed, exceed_max_denominator=n,
                           exceed_max_fraction=fraction,
                           supported_outside_primary={"under_1_5_m": int(np.sum(outside & (focus_case["bins"] < 0))),
                                                      "at_or_over_10_m": int(np.sum(outside & (focus_case["bins"] >= 3)))})
    statuses = {fold["status"] for fold in folds.values()}
    status = "FAIL" if "FAIL" in statuses else "INCONCLUSIVE" if "INCONCLUSIVE" in statuses else "PASS"
    report = dict(status=status, folds=folds, rows=rows,
                  v8_cutoffs=dict(min_ratio=.5, max_ratio=2., extrapolation_fraction=.5),
                  d3_reconstruction_max=max(row["parts"]["reconstruction_error"]
                                            for fold in prepared.values() for row in fold.values()))
    return report, dict(prepared=prepared, models=models)


def _pairs(case, indices):
    i, j = np.triu_indices(indices.size, k=1)
    lag = case["arc"][indices[j]] - case["arc"][indices[i]]
    lag_bin = np.searchsorted(LAG_EDGES, lag, side="right") - 1
    lag_bin[lag == LAG_EDGES[-1]] = LAG_EDGES.size - 2
    keep = (lag_bin >= 0) & (lag_bin < LAG_EDGES.size - 1)
    i, j, lag, lag_bin = i[keep], j[keep], lag[keep], lag_bin[keep]
    count = np.bincount(lag_bin, minlength=LAG_EDGES.size - 1)
    raw = case["eps"][indices, 1]
    fast, slow = (case["parts"][component][indices, 1] for component in ("fast", "slow"))
    return dict(i=i, j=j, lag=lag, bin=lag_bin, count=count, raw=raw, fast=fast, slow=slow,
                g=case["g"][indices], rref=case["rref"][indices])


def _bin_average(pairs, values, bins):
    counts = pairs["count"]
    sums = np.bincount(pairs["bin"], weights=values, minlength=counts.size)
    return sums[bins] / counts[bins]


def _variogram_rows(pairs):
    supported = np.flatnonzero(pairs["count"])
    rows = {k: _bin_average(pairs, np.square(pairs[k][pairs["i"]] - pairs[k][pairs["j"]]) * .5, supported)
            for k in ("raw", "fast", "slow")}
    return [dict(distance_m=LAG_EDGES[b:b + 2].tolist(), pairs=int(pairs["count"][b]),
                 **({k: float(v[np.searchsorted(supported, b)]) for k, v in rows.items()} if pairs["count"][b] else {}))
            for b in range(pairs["count"].size)]


def _fit_inputs(pairs, bins, component, normalization):
    var = float(np.var(pairs["raw"])) if pairs["raw"].size else 0.
    if var <= MIN_VARIANCE or bins.size == 0:
        return None
    scale = (1. / np.sqrt(pairs["rref"]) if normalization == "Rref"
             else np.full(pairs["raw"].shape, 1. / np.sqrt(var)))
    i, j = pairs["i"], pairs["j"]
    e = (pairs[component] - pairs[component].mean()) * scale
    return (scale[i] ** 2, scale[j] ** 2, scale[i] * scale[j],
            _bin_average(pairs, .5 * (e[i] - e[j]) ** 2, bins))


def _grid_fit(pair_sets, bins, component, normalization, model=None):
    lengths = FAST_LENGTHS if component == "fast" else SLOW_LENGTHS
    inputs = [_fit_inputs(pairs, bins, component, normalization) for pairs in pair_sets]
    if any(item is None for item in inputs):
        return dict(status="UNSUPPORTED", supported=False, status_reason="NO_COMMON_LAG_SUPPORT_OR_VARIANCE")
    fast = component == "fast"
    if bins.size < (2 if fast else 1):
        return dict(status="UNSUPPORTED", supported=False, status_reason="TOO_FEW_COMMON_LAG_BINS")
    target = np.concatenate([item[3] for item in inputs])
    if fast:
        white = np.concatenate([_bin_average(p, .5 * (item[0] + item[1]), bins)
                                for p, item in zip(pair_sets, inputs, strict=True)])
    else:
        variances = [np.full(p["g"].shape, model["slow_distance"]) if model["beta"] is None
                     else model["beta"][0] + model["beta"][1] * p["g"] ** 2 for p in pair_sets]
        if all(np.max(x) <= MIN_VARIANCE for x in variances):
            return dict(status="UNSUPPORTED", supported=False, status_reason="DEGENERATE_SLOW_SILL")
    grid = []
    for length in lengths:
        correlation = [np.exp(-p["lag"] / length) for p in pair_sets]
        if fast:
            colored = np.concatenate([_bin_average(p, .5 * (s_i + s_j) - both * rho, bins)
                                      for p, (s_i, s_j, both, _), rho
                                      in zip(pair_sets, inputs, correlation, strict=True)])
            design = np.column_stack([white, colored])
            if np.linalg.matrix_rank(design) < 2:
                continue
            coefficient, _ = nnls(design, target)
            predicted = design @ coefficient
        else:
            coefficient = None
            predicted = np.concatenate([
                _bin_average(p, .5 * (s_i * var[p["i"]] + s_j * var[p["j"]])
                             - both * np.sqrt(var[p["i"]] * var[p["j"]]) * rho, bins)
                for p, (s_i, s_j, both, _), var, rho in zip(pair_sets, inputs, variances, correlation, strict=True)
            ])
        row = dict(length=float(length), loss=float(np.mean((predicted - target) ** 2)))
        if coefficient is not None:
            row.update(white=float(coefficient[0]), fast=float(coefficient[1]))
        grid.append(row)
    if not grid:
        return dict(status="UNSUPPORTED", supported=False, status_reason="RANK_DEFICIENT_VARIOGRAM")
    minimum = min(row["loss"] for row in grid)
    atol = np.finfo(float).eps * max(1., minimum)
    best = [row for row in grid if abs(row["loss"] - minimum) <= atol][-1]
    near = [row for row in grid if row["loss"] <= 1.05 * minimum + atol]
    bounds = [near[0]["length"], near[-1]["length"]]
    boundary = bounds[0] == lengths[0] or bounds[-1] == lengths[-1]
    return dict(supported=True, grid=grid, best=best, near_optimal_bounds=bounds,
                near_optimal_ratio=bounds[1] / bounds[0], boundary=bool(boundary),
                conservative=near[-1], lag_bin_indices=bins.tolist())


def _reference_fits(pairs, bins, component, model=None):
    joint = _grid_fit(pairs, bins, component, "empirical", model)
    solo = [_grid_fit([pair], bins, component, "empirical", model) for pair in pairs]
    counts = [item["best"]["length"] for item in solo if item["supported"]]
    swap_ratio = max(counts) / min(counts) if len(counts) == len(pairs) and counts else None
    endpoint = (joint.get("boundary") or (swap_ratio is not None and swap_ratio >= 2.)
                or (component == "fast" and joint.get("best", {}).get("fast", 1.) <= MIN_VARIANCE))
    status = ("UNSUPPORTED" if not joint["supported"] else "INCONCLUSIVE" if swap_ratio is None
              else "UNIDENTIFIED" if endpoint else "IDENTIFIED")
    chosen = (joint["conservative"] if endpoint else joint["best"]) if joint["supported"] else None
    return dict(status=status, chosen=chosen, donor_swap_length_ratio=swap_ratio, empirical=joint,
                per_donor=solo, Rref_sensitivity=_grid_fit(pairs, bins, component, "Rref", model))


def _expected_window_variance(case, indices, params):
    """Mean diagonal minus mean full covariance of D3 window averages."""
    arc, shape = case["arc"], case["t"].size
    use = np.zeros(shape, dtype=bool)
    amplitude_fast, amplitude_slow = np.zeros(shape), np.zeros(shape)
    inv_fast, inv_slow = np.zeros(shape), np.zeros(shape)
    white = case["rref"].copy()
    for b, param in params.items():
        if not param["supported"]:
            continue
        inside = case["bins"] == b
        use[inside] = True
        white[inside] = param["white"]
        amplitude_fast[inside] = np.sqrt(param["fast"])
        beta = param["beta"]
        variance = param["slow_distance"] if beta is None else beta[0] + beta[1] * case["g"][inside] ** 2
        amplitude_slow[inside] = np.sqrt(variance)
        inv_fast[inside], inv_slow[inside] = 1. / param["fast_length"], 1. / param["slow_length"]
    steps = np.diff(arc, prepend=arc[0])
    cov = np.diag(white)
    for amplitude, inv_length in ((amplitude_fast, inv_fast), (amplitude_slow, inv_slow)):
        scaled_arc = np.cumsum(steps * inv_length)
        cov += np.outer(amplitude, amplitude) * np.exp(-np.abs(np.subtract.outer(scaled_arc, scaled_arc)))
    left, right = (case["parts"][name][indices] for name in ("left", "right"))
    lengths = right - left
    weights = np.repeat(1. / lengths, lengths)
    cols = np.concatenate([np.arange(a, b) for a, b in zip(left, right, strict=True)])
    rows = np.repeat(np.arange(indices.size), lengths)
    averaging = csr_matrix((weights, (rows, cols)), shape=(indices.size, shape))
    cov_window = averaging @ (averaging @ cov).T
    return float(np.trace(cov_window) / indices.size - cov_window.mean()), int(np.sum(~use[cols])), int(cols.size)


def v1_v2(cases, internal):
    """Conditional component fits, matched window check, and diagnostic-only R4 oracle."""
    if set(cases) != set(internal["prepared"]):
        raise ValueError("V1/V2 fold identities diverge from V8")
    data, models = internal["prepared"], internal["models"]
    params, v1_rows, v2_rows = {}, [], []
    for fold in ROUTES:
        donors = [r for r in ROUTES if r != fold]
        params[fold] = {}
        for b in range(3):
            indices = [_indices(data[fold][r], b) for r in donors]
            pairs = [_pairs(data[fold][r], ix) for r, ix in zip(donors, indices, strict=True)]
            bins = np.flatnonzero(np.logical_and.reduce([p["count"] >= MIN_PAIRS for p in pairs]))
            fast = _reference_fits(pairs, bins, "fast")
            model = models[fold][b]
            slow = (_reference_fits(pairs, bins, "slow", model) if model["slow_distance"] is not None
                    else dict(status="UNSUPPORTED", chosen=None, status_reason="NO_SUPPORTED_DONOR_SLOW_SILL"))
            distance_slow = (_reference_fits(pairs, bins, "slow", model | {"beta": None})
                             if model["beta"] is not None else slow)
            fv = fast["chosen"]
            proxy = None
            if fv is None and bins.size:
                differences = [p["fast"][p["i"]] - p["fast"][p["j"]] for p in pairs]
                proxy = float(np.mean([.5 * np.var(diff[p["bin"] == bins[0]])
                                       for diff, p in zip(differences, pairs, strict=True)]))
            lv = slow["chosen"]
            supported = fv is not None and lv is not None
            oracle = dict(variance=None, fit=None, length=None)
            if fold == "R4":
                case = data[fold][fold]
                ix = _indices(case, b)
                if _support(case, ix)["supported"]:
                    variance = float(case["parts"]["slow"][ix, 1].var())
                    self_pairs = _pairs(case, ix)
                    local = _reference_fits([self_pairs], np.flatnonzero(self_pairs["count"] >= MIN_PAIRS),
                                            "slow", dict(beta=None, slow_distance=variance))
                    oracle = dict(variance=variance, fit=local,
                                  length=local["chosen"]["length"] if local["chosen"] else None)
            identified = all(fit["status"] == "IDENTIFIED" for fit in (fast, slow))
            params[fold][b] = dict(**model, white=fv["white"] if fv else proxy, fast=fv["fast"] if fv else None,
                                   fast_length=fv["length"] if fv else None, slow_length=lv["length"] if lv else None,
                                   distance_slow_length=distance_slow["chosen"]["length"] if distance_slow["chosen"] else None,
                                   supported=supported, identified=identified, fast_status=fast["status"],
                                   slow_status=slow["status"], oracle_slow=oracle["variance"],
                                   oracle_length=oracle["length"],
                                   oracle_status=oracle["fit"]["status"] if oracle["fit"] else "UNSUPPORTED")
            routes = {}
            for route, ix, pair in zip(donors, indices, pairs, strict=True):
                ds, dy = (np.diff(data[fold][route][key], prepend=data[fold][route][key][0])
                          for key in ("arc", "yaw"))
                use = np.zeros(ds.shape, dtype=bool)
                use[ix] = True
                components = component_summary(data[fold][route]["eps"], data[fold][route]["parts"], use)
                routes[route] = dict(variogram=_variogram_rows(pair), components=components,
                                     in_place_yaw=int(np.sum((ds[ix] <= 1e-12) & (dy[ix] > 1e-12))),
                                     rotating_intervals=int(np.sum(dy[ix] > 1e-12)),
                                     accepted_yaw_arc_rad=float(dy[ix].sum()))
            v1_rows.append(dict(fold=fold, bin_index=b, routes=routes, common_lag_bins=bins.tolist(),
                                white=params[fold][b]["white"], fast=params[fold][b]["fast"],
                                fast_length=params[fold][b]["fast_length"], slow_length=params[fold][b]["slow_length"],
                                proxy_white=proxy, chosen_slow_model="V8" if model["beta"] is not None else "DISTANCE_ONLY"))
            v2_rows.append(dict(fold=fold, bin_index=b, donor_order=donors,
                                fast=fast, slow=slow, distance_only_slow=distance_slow, own_r4_oracle=oracle))
    for row in v1_rows:
        fold, b = row["fold"], row["bin_index"]
        for route, summary in row["routes"].items():
            idx = _indices(data[fold][route], b)
            case = data[fold][route]
            observed = summary["components"].get("var_slow", [0., 0.])[1]
            if params[fold][b]["supported"] and observed > MIN_VARIANCE and idx.size:
                expected, fallback, total = _expected_window_variance(case, idx, params[fold])
                ratio = expected / observed
                summary.update(expected_window_variance=expected, expected_over_observed=ratio,
                               window_fallback_terms=fallback, window_terms=total,
                               status="PASS" if .7 <= ratio <= 1.3 else "FAIL")
            else:
                summary["status"] = "INCONCLUSIVE"
        verdicts = {summary["status"] for summary in row["routes"].values()}
        row["status"] = "FAIL" if "FAIL" in verdicts else "INCONCLUSIVE" if "INCONCLUSIVE" in verdicts else "PASS"
    verdicts = {row["status"] for row in v1_rows}
    v1_status = "FAIL" if "FAIL" in verdicts else "INCONCLUSIVE" if "INCONCLUSIVE" in verdicts else "PASS"
    v2_status = "PASS" if all(p["identified"] for fold in params.values() for p in fold.values()) else "INCONCLUSIVE"
    return (dict(status=v1_status, rows=v1_rows, lag_edges_m=LAG_EDGES.tolist(), pair_minimum=MIN_PAIRS),
            dict(status=v2_status, rows=v2_rows, fast_lengths_m=FAST_LENGTHS.tolist(), slow_lengths_m=SLOW_LENGTHS.tolist()),
            params)
