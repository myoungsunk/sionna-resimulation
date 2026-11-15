"""Pure estimators and synthetic checks for MODEL-003 v3 S2' C2, C3 and C7."""

import numpy as np
from scipy.optimize import lsq_linear, minimize_scalar
from scipy.stats import kurtosis, t


DEFAULT_PENALTIES = (0.1, 1.0, 10.0)
VALIDATION_SEED = 3003


def _samples(distance_m, residual, site):
    distance = np.asarray(distance_m, dtype=float)
    error = np.asarray(residual, dtype=float)
    keys = np.fromiter(site, dtype=object)
    if distance.ndim != 1 or distance.shape != error.shape or distance.shape != keys.shape:
        raise ValueError("distance, residual and site must have matching one-dimensional lengths")
    if not len(distance) or not np.isfinite(distance).all() or not np.isfinite(error).all():
        raise ValueError("distance and residual require nonempty finite observations")
    return distance, error, keys


def _sigma95(residual):
    return float(np.quantile(np.abs(residual), 0.95) / 1.96)


def _merge_bins(distance, site, edges, min_samples, min_sites):
    labels = np.searchsorted(edges, distance, side="right")
    groups = [np.flatnonzero(labels == group) for group in range(len(edges) + 1)]
    groups = [group for group in groups if len(group)]

    def sufficient(group):
        return len(group) >= min_samples and len(set(site[group])) >= min_sites

    while not all(sufficient(group) for group in groups):
        if len(groups) == 1:
            raise ValueError("C2 support contains fewer than the required samples or independent sites")
        first_sparse = next(i for i, group in enumerate(groups) if not sufficient(group))
        center = np.median(distance[groups[first_sparse]])
        neighbors = [i for i in (first_sparse - 1, first_sparse + 1) if 0 <= i < len(groups)]
        join = min(neighbors, key=lambda i: (abs(center - np.median(distance[groups[i]])), i))
        low, high = sorted((first_sparse, join))
        groups[low:high + 1] = [np.concatenate(groups[low:high + 1])]
    return groups


def fit_c2(distance_m, residual, site, *, knots_m, thermal_std, penalty,
           min_samples=200, min_sites=10):
    """Fit log range-dependent variance to q95 targets from a pose-thinned training pool.

    Form bins at knot midpoints, merging the first undersupported bin with the
    closest adjacent bin by distance median. Fit each merged target at its
    median distance with equal bin weight. The optional penalty acts on
    second differences of the knot log-variances.
    """
    distance, error, keys = _samples(distance_m, residual, site)
    if (not np.isfinite(thermal_std) or thermal_std < 0
            or not np.isfinite(penalty) or penalty < 0
            or min_samples < 1 or min_sites < 1):
        raise ValueError("Invalid C2 floor, penalty or minimum sample/site count")
    candidate = np.unique(np.asarray(knots_m, dtype=float))
    if not len(candidate) or not np.isfinite(candidate).all():
        raise ValueError("C2 requires finite candidate knots")
    low, high = np.min(distance), np.max(distance)
    supported = (candidate >= low) & (candidate <= high)
    knots = candidate[supported]
    if not len(knots):
        knots = np.asarray([np.median(distance)])
    groups = _merge_bins(distance, keys, (knots[:-1] + knots[1:]) / 2.0, min_samples, min_sites)

    pooled = _sigma95(error)
    floor = max(float(thermal_std), pooled / 2.0)
    if floor <= 0:
        raise ValueError("C2 requires a positive thermal or pooled scale")
    targets = np.array([_sigma95(error[group]) for group in groups])
    centers = np.array([np.median(distance[group]) for group in groups])
    design = np.column_stack([np.interp(centers, knots, col) for col in np.eye(len(knots))])
    second_diff = np.diff(np.eye(len(knots)), n=2, axis=0)
    design = np.vstack((design, np.sqrt(penalty) * second_diff))
    log_floor = 2.0 * np.log(floor)
    response = np.r_[2.0 * np.log(np.maximum(targets, floor)), np.zeros(len(second_diff))]

    # A knot with no merged-bin observation is determined by the shape penalty.
    # When necessary reduce the model to the supported observed bin centers.
    if np.linalg.matrix_rank(design) < len(knots):
        knots = np.unique(centers)
        design = np.column_stack([np.interp(centers, knots, col) for col in np.eye(len(knots))])
        second_diff = np.diff(np.eye(len(knots)), n=2, axis=0)
        design = np.vstack((design, np.sqrt(penalty) * second_diff))
        response = np.r_[response[:len(groups)], np.zeros(len(second_diff))]

    fit = lsq_linear(design, response, bounds=(log_floor, np.inf), method="bvls")
    if not fit.success or not np.isfinite(fit.x).all():
        raise RuntimeError("C2 constrained log-variance fit did not converge")
    bins = [dict(n=len(group), sites=len(set(keys[group])), center_m=float(center),
                 distance_min_m=float(np.min(distance[group])), distance_max_m=float(np.max(distance[group])),
                 sigma95=float(target))
            for group, center, target in zip(groups, centers, targets, strict=True)]
    return dict(support_m=[float(low), float(high)], knots_m=knots.tolist(),
                sigma=np.exp(fit.x / 2.0).tolist(), log_variance=fit.x.tolist(),
                white_variance=pooled**2, pooled_sigma95=pooled, floor_std=floor,
                discarded_knots_m=candidate[~supported].tolist(), bins=bins, penalty=float(penalty))


def sigma_at(fit, distance_m):
    """Evaluate the fitted log-linear σ and return the separate support mask."""
    distance = np.asarray(distance_m, dtype=float)
    left, right = fit["support_m"]
    sigma = np.exp(np.interp(distance, fit["knots_m"], fit["log_variance"]) / 2.0)
    return sigma, (distance >= left) & (distance <= right) & np.isfinite(distance)


def select_c2_penalty(training, *, knots_m, penalties=DEFAULT_PENALTIES, min_samples=200, min_sites=10):
    """Select λ by inner LOAO on training anchors only.

    The caller passes only the anchors allowed to fit the outer fold. Each
    value provides distance_m, residual, site, and thermal_std. Held-in anchor
    measurements outside the corresponding inner fit support are excluded
    from scoring and counted. Pool the eligible Gaussian log likelihoods.
    """
    if len(training) < 2 or not penalties or len(set(penalties)) != len(penalties):
        raise ValueError("C2 penalty selection needs at least two allowed training anchors")
    training_samples = {}
    for anchor, rows in sorted(training.items()):
        distance, error, site = _samples(rows["distance_m"], rows["residual"], rows["site"])
        thermal = float(rows["thermal_std"])
        if not np.isfinite(thermal) or thermal < 0:
            raise ValueError("C2 training thermal standard deviations must be finite and nonnegative")
        training_samples[anchor] = distance, error, site, thermal
    scores = []
    for penalty in sorted(penalties):
        folds = []
        for held_in, (valid_d, valid_e, _, _) in training_samples.items():
            donors = [(anchor, rows) for anchor, rows in training_samples.items() if anchor != held_in]
            fit = fit_c2(
                np.concatenate([rows[0] for _, rows in donors]),
                np.concatenate([rows[1] for _, rows in donors]),
                ((anchor, key) for anchor, rows in donors for key in rows[2]),
                knots_m=knots_m, thermal_std=max(rows[3] for _, rows in donors),
                penalty=penalty, min_samples=min_samples, min_sites=min_sites,
            )
            sigma, use = sigma_at(fit, valid_d)
            if not use.any():
                raise ValueError(f"No C2 evaluation support for inner held-in anchor {held_in}")
            # Include the Gaussian normalizing term so likelihood is comparable.
            ll = -0.5 * np.sum(np.log(2.0 * np.pi * sigma[use]**2) + (valid_e[use] / sigma[use])**2)
            folds.append(dict(held_in_anchor=held_in, donor_anchors=[anchor for anchor, _ in donors],
                              n_scored=int(use.sum()), out_of_support=int((~use).sum()),
                              gaussian_log_likelihood=float(ll)))
        scores.append(dict(penalty=float(penalty), gaussian_log_likelihood=sum(
            row["gaussian_log_likelihood"] for row in folds), inner_folds=folds))
    selected = max(scores, key=lambda row: (row["gaussian_log_likelihood"], -row["penalty"]))
    return dict(selected_penalty=selected["penalty"], training_anchors=sorted(training), scores=scores)


def fit_c3(lag, correlation, pairs, *, lower, upper):
    """Bounded pair-count-weighted nugget–exponential fit to positive-lag data."""
    x, y, count = (np.asarray(a, dtype=float) for a in (lag, correlation, pairs))
    if (x.ndim != 1 or x.shape != y.shape or x.shape != count.shape
            or not all(np.isfinite(a).all() for a in (x, y, count)) or np.any(count < 0)
            or not np.isfinite(lower) or not np.isfinite(upper) or not 0 < lower < upper):
        raise ValueError("Invalid C3 lag, correlation, pair-count or length bounds")
    use = (x > 0) & (count > 0)
    if len(np.unique(x[use])) < 2 or np.any(np.abs(y[use]) > 1 + 1e-12):
        raise ValueError("C3 needs at least two distinct supported positive lags and valid correlations")
    x, y, count = x[use], y[use], count[use]
    weights = count / count.sum()

    def profile(length):
        exp = np.exp(-x / length)
        # Profile out the linear scale 1 - nugget at each candidate length.
        cross = np.dot(weights * exp, y)
        norm = np.dot(weights * exp, exp)
        scale = np.clip(cross / norm, np.finfo(float).eps, 1.0) if norm > 0 else np.finfo(float).eps
        return float(np.dot(weights, (y - scale * exp)**2)), float(scale)

    result = minimize_scalar(lambda log_length: profile(np.exp(log_length))[0],
                             bounds=(np.log(lower), np.log(upper)), method="bounded",
                             options={"xatol": 1e-12})
    if not result.success:
        raise RuntimeError("C3 bounded length fit did not converge")
    # Explicit endpoint evaluation makes the boundary decision reproducible.
    candidates = [(lower, "LOWER"), (upper, "UPPER"), (float(np.exp(result.x)), "INTERIOR")]
    length, boundary = min(candidates, key=lambda candidate: profile(candidate[0])[0])
    loss, scale = profile(length)
    return dict(length=float(length), nugget=1.0 - scale, boundary=boundary,
                mode="WHITE" if boundary == "LOWER" else "COLORED",
                requires_consider=boundary == "UPPER", weighted_sse=loss,
                pair_count=int(count.sum()), lag_count=len(x), bounds=[float(lower), float(upper)])


def fit_c7(distance_m, residual, site, c2):
    """Fit fixed-location Student-t after C2 scale normalization and site thinning."""
    distance, error, keys = _samples(distance_m, residual, site)
    sigma, support = sigma_at(c2, distance)
    # Deterministically keep the first supported row per site in the caller's
    # predeclared order of the pose-thinned samples.
    first = {}
    for index in np.flatnonzero(support):
        first.setdefault(keys[index], index)
    indices = np.asarray(list(first.values()), dtype=int)
    z = error[indices] / sigma[indices]
    if len(z) < 4 or not np.isfinite(z).all() or np.all(z == z[0]):
        raise ValueError("C7 needs at least four supported sites with finite nonconstant residuals")
    estimate, loc, scale = t.fit(z, floc=0.0)
    if loc != 0 or not np.isfinite(estimate) or not np.isfinite(scale) or scale <= 0:
        raise RuntimeError("C7 fixed-location fit did not yield valid degrees of freedom and scale")
    return dict(nu_hat=float(estimate), nu_use=max(float(estimate), 3.0), loc=float(loc),
                scale=float(scale), status="TAIL_BELOW_FLOOR" if estimate < 3.0 else "OK",
                n_sites=len(indices), out_of_support=int((~support).sum()),
                excess_kurtosis_before=float(kurtosis(error[indices], bias=False)),
                excess_kurtosis_after=float(kurtosis(z, bias=False)))


def synthetic_check(seed=VALIDATION_SEED):
    """Run the six pre-S2' checks and complementary lower-bound and floor checks."""
    rng = np.random.default_rng(seed)
    knots = np.array([2.0, 5.0, 11.0])
    truth = np.array([0.04, np.sqrt(0.04 * 0.4), 0.4])
    # Sparse high-variance bands keep the mandatory pooled σ floor below the
    # lowest true σ, making the knot-recovery and floor properties separable.
    sizes = [20_000, 1_200, 1_200]
    distance = np.repeat(knots, sizes)
    residual = rng.normal(scale=np.repeat(truth, sizes))
    sites = np.arange(len(distance))
    c2 = fit_c2(distance, residual, sites, knots_m=[0.0, *knots, 12.0], thermal_std=0.003, penalty=0.1)
    relative = np.abs(np.asarray(c2["sigma"]) / truth - 1.0)
    floor_active = fit_c2(distance, residual, sites, knots_m=knots, thermal_std=0.06, penalty=0.1)
    lag = np.linspace(0.018, 0.50, 60)
    weights = np.arange(50, 110)
    c3 = fit_c3(lag, 0.7 * np.exp(-lag / 0.1), weights, lower=0.016, upper=0.333)
    upper = fit_c3(lag, 0.7 * np.exp(-lag / 2.0), weights, lower=0.016, upper=0.333)
    lower = fit_c3(lag, 0.7 * np.exp(-lag / 0.006), weights, lower=0.016, upper=0.333)
    tail_n = 20_000
    c7 = fit_c7(np.full(tail_n, knots[0]), truth[0] * rng.standard_t(4, size=tail_n),
                np.arange(tail_n), c2)
    # A 50:50 mixture of zero-mean Gaussians has excess kurtosis below 3
    # for any finite scale ratio. A rare high-variance stratum exercises the
    # preregistered >3 check at the prescribed 10× scale ratio.
    mixture_counts = [32_000, 8_000]
    mixture_distances = np.repeat(knots[[0, -1]], mixture_counts)
    known_sigma = np.repeat(truth[[0, -1]], mixture_counts)
    err = rng.normal(scale=known_sigma)
    estimated, _ = sigma_at(c2, mixture_distances)
    raw_kurtosis = float(kurtosis(err, bias=False))
    normalized_kurtosis = float(kurtosis(err / estimated, bias=False))

    checks = dict(
        c2_knot_accuracy=bool(np.max(relative) <= 0.15 and min(c2["sigma"]) > 0),
        c2_support=c2["discarded_knots_m"] == [0.0, 12.0] and c2["knots_m"] == knots.tolist(),
        c3_parameter_recovery=abs(c3["length"] - 0.1) <= 0.02 and abs(c3["nugget"] - 0.3) <= 0.1,
        c3_upper=upper["boundary"] == "UPPER" and upper["requires_consider"],
        c7_student_t=3.0 <= c7["nu_hat"] <= 5.5,
        c7_heteroscedastic_kurtosis=raw_kurtosis > 3.0 and abs(normalized_kurtosis) < 0.5,
        c3_lower=lower["boundary"] == "LOWER" and lower["mode"] == "WHITE",
        c2_active_floor=min(floor_active["sigma"]) >= 0.06 - 1e-14,
    )
    return dict(status="PASS" if all(checks.values()) else "FAIL", seed=seed, checks=checks,
                c2=dict(truth_sigma=truth.tolist(), fitted_sigma=c2["sigma"], floor_sigma=c2["floor_std"],
                        relative_error=relative.tolist(), discarded_knots_m=c2["discarded_knots_m"]),
                c3=c3, c3_upper=upper, c3_lower=lower, c7=c7,
                gaussian_mixture_excess_kurtosis=dict(raw=raw_kurtosis, normalized=normalized_kurtosis,
                                                       counts=mixture_counts))
