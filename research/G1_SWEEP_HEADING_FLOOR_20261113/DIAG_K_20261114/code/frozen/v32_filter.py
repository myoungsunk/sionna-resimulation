"""G1-MODEL-001 v3.2 E1 calibration and station-level heading filter."""

from dataclasses import dataclass

import numpy as np


STEP = 0.25
N_YAW = 1440
GRID = np.arange(N_YAW) * STEP - 180.0
FIT_INDEX = np.arange(-8, 9)
FIT_X = STEP * FIT_INDEX
FIT_X2 = FIT_X**2 - np.mean(FIT_X**2)
H = np.array([-1.0, 0.0, 1.0])
GATE_NIS = 6.635


def wrap(angle):
    """Use (-180, 180], including the positive representative at the tie."""
    return 180.0 - np.remainder(180.0 - angle, 360.0)


@dataclass
class CandidateFeatures:
    index: np.ndarray
    yaw_deg: np.ndarray
    cost: np.ndarray
    r_raw: np.ndarray
    valid_curvature: np.ndarray
    boundary: np.ndarray
    count: np.ndarray


@dataclass
class TrainingFeatures:
    cap_sample: np.ndarray
    winner_raw: np.ndarray
    winner_error: np.ndarray


@dataclass(frozen=True)
class Calibration:
    cap_raw: float
    c_l: float
    r_bar: float
    flat_fraction: float
    n_a: int
    n_b: int
    constant_r: float | None = None

    def variance(self, features):
        if self.constant_r is not None:
            return np.full_like(features.r_raw, self.constant_r)
        return self.c_l * np.where(features.valid_curvature, features.r_raw, self.cap_raw)


def _plateau_representatives(values, local, active, full):
    """Collapse tied interior valleys, preserving strict constrained endpoints."""
    for row in np.flatnonzero(active):
        n = len(values[row]) if full[row] else np.count_nonzero(np.isfinite(values[row]))
        y = values[row, :n]
        if n < 3:
            continue
        # Rotate a periodic row so an exact plateau never straddles the slice.
        if full[row] and y[0] == y[-1]:
            transitions = np.flatnonzero(y[1:] != y[:-1])
            if not transitions.size:
                continue
            order = (np.arange(n) + transitions[0] + 1) % n
        else:
            order = np.arange(n)
        y = y[order]
        boundaries = np.r_[0, np.flatnonzero(y[1:] != y[:-1]) + 1, n]
        for lo, hi in zip(boundaries[:-1], boundaries[1:]):
            if hi - lo < 2:
                continue
            local[row, order[lo:hi]] = False
            if not full[row] and (lo == 0 or hi == n):
                continue
            if y[lo] < y[(lo - 1) % n] and y[lo] < y[hi % n]:
                local[row, order[(lo + hi - 1) // 2]] = True


def _window_candidates(j, center, half, valid_sweep, limit):
    center = wrap(center)
    full = half >= 180.0
    first = np.ceil((center - half + 180.0) / STEP - 1e-10).astype(int)
    last = np.floor((center + half + 180.0) / STEP + 1e-10).astype(int)
    length = np.where(full, N_YAW, last - first + 1)
    first = np.where(full, 0, first)
    offsets = np.arange(int(np.max(length, initial=1)))
    index = (first[:, None] + offsets) % N_YAW
    in_window = offsets < length[:, None]
    values = np.take_along_axis(j, index, axis=1)
    finite = np.all(np.isfinite(values) | ~in_window, axis=1) & valid_sweep
    values = np.where(in_window & finite[:, None], values, np.inf)
    prev = np.empty_like(values)
    nex = np.empty_like(values)
    prev[:, 1:] = values[:, :-1]
    prev[:, 0] = np.where(full, values[:, -1], np.inf)
    nex[:, :-1] = values[:, 1:]
    nex[:, -1] = np.where(full, values[:, 0], np.inf)
    local = (values <= prev) & (values <= nex) & ((values < prev) | (values < nex))
    tied = (values == prev) | (values == nex)
    _plateau_representatives(values, local, np.any(tied & local, axis=1), full)

    width = int(np.max(np.sum(local, axis=1), initial=0)) if limit is None else limit
    selected = np.full((len(j), width), -1, dtype=np.int32)
    edge = np.zeros((len(j), width), dtype=bool)
    active = local
    rows = np.arange(len(j))
    for slot in range(width):
        possible = np.any(active, axis=1)
        if not np.any(possible):
            break
        ranked = np.where(active, values, np.inf)
        best = np.min(ranked, axis=1, keepdims=True)
        # An equal minimum uses the smaller absolute circular grid index.
        tied_index = np.where(active & (ranked == best), index, N_YAW)
        pos = np.argmin(tied_index, axis=1)
        candidate = index[rows, pos]
        selected[possible, slot] = candidate[possible]
        edge[possible, slot] = (~full & ((pos == 0) | (pos == length - 1)))[possible]
        separation = np.abs(index - candidate[:, None])
        active = active & (np.minimum(separation, N_YAW - separation) >= 8)
    return selected, edge, center


def candidate_features(j, chi2_min, n_valid, center_deg, half_deg, max_candidates=3):
    """Return the selected minima, ordered by J, and their §3.2 fit features.

    Rows use the absolute 0.25-degree grid. chi2_min holds unnormalized
    minimum-node squared residuals in chi-squared units before dividing by
    n_valid-1. Pass max_candidates=None for all separated calibration minima.
    Missing slots have index -1 and nonfinite yaw/cost/raw variance.
    """
    j = np.asarray(j)
    chi2_min = np.asarray(chi2_min)
    n_valid = np.broadcast_to(n_valid, (len(j),))
    center = np.broadcast_to(center_deg, (len(j),))
    half = np.broadcast_to(half_deg, (len(j),))
    indices, edge, center = _window_candidates(j, center, half, n_valid >= 3, max_candidates)
    rows, slots = np.nonzero(indices >= 0)
    chosen = indices[rows, slots]
    yaw = np.full(indices.shape, np.nan)
    yaw[rows, slots] = GRID[chosen]
    cost = np.full(indices.shape, np.inf)
    cost[rows, slots] = j[rows, chosen]
    raw = np.full(indices.shape, np.nan)
    valid = np.zeros(indices.shape, dtype=bool)

    fit = j[rows[:, None], (chosen[:, None] + FIT_INDEX) % N_YAW].astype(np.float64)
    fit -= np.mean(fit, axis=1, keepdims=True)
    a = np.sum(fit * FIT_X2, axis=1) / (FIT_X2 @ FIT_X2)
    b = np.sum(fit * FIT_X, axis=1) / (FIT_X @ FIT_X)
    residual = fit - a[:, None] * FIT_X2 - b[:, None] * FIT_X
    sst = np.sum(fit**2, axis=1)
    sse = np.sum(residual**2, axis=1)
    red = chi2_min[rows, chosen] / (n_valid[rows] - 1)
    clearance = half[rows] - np.abs(wrap(yaw[rows, slots] - center[rows]))
    inside = (half[rows] >= 180.0) | ((clearance > 0.5) & ~edge[rows, slots])
    good = (a > 0.0) & (sst > 0.0) & (sse <= 0.5 * sst) & inside & np.isfinite(red)
    raw[rows[good], slots[good]] = np.maximum(1.0, red[good]) / a[good]
    valid[rows[good], slots[good]] = True
    return CandidateFeatures(indices, yaw, cost, raw, valid, edge, np.sum(indices >= 0, axis=1))


def training_features(j, chi2_min, n_valid, truth_deg):
    """Extract independent sample A values and sample B error/variance pairs."""
    truth = np.broadcast_to(truth_deg, (len(j),))
    result = candidate_features(j, chi2_min, n_valid, truth, 10.0, max_candidates=None)
    winners = np.flatnonzero(result.count)
    if not winners.size:
        empty = np.empty(0)
        return TrainingFeatures(empty, empty, empty)
    return TrainingFeatures(
        result.r_raw[result.valid_curvature],
        result.r_raw[winners, 0],
        wrap(result.yaw_deg[winners, 0] - truth[winners]),
    )


def _training_pool(features):
    if isinstance(features, TrainingFeatures):
        return features
    return TrainingFeatures(*(
        np.concatenate([getattr(item, name) for item in features])
        for name in ('cap_sample', 'winner_raw', 'winner_error')
    ))


def fit_e1(features):
    """Fit L1-L5 after the caller has excluded the evaluation route."""
    pool = _training_pool(features)
    if not pool.cap_sample.size or not pool.winner_error.size:
        raise ValueError('E1 calibration requires both valid curvature A and aligned sweep B')
    cap = float(np.quantile(pool.cap_sample, 0.99))
    fallback = ~np.isfinite(pool.winner_raw)
    raw = np.where(fallback, cap, pool.winner_raw)
    q95 = np.quantile(np.abs(pool.winner_error) / np.sqrt(raw), 0.95)
    scale = float((q95 / 1.96)**2)
    return Calibration(cap, scale, float(np.mean(scale * raw)), float(np.mean(fallback)),
                       int(pool.cap_sample.size), int(raw.size))


def fit_e0(features, e1=None):
    """E0 fixed second moment with the §4.4 AR scale from E1."""
    pool = _training_pool(features)
    e1 = fit_e1(pool) if e1 is None else e1
    fixed = float(np.mean(pool.winner_error**2))
    return Calibration(e1.cap_raw, e1.c_l, e1.r_bar, e1.flat_fraction, e1.n_a, e1.n_b, fixed)


def _branch_update(x, p, features, variance, sigma_a2, dr_absolute, gate):
    available = features.index >= 0
    # Subtracting the best J protects both the exponential and its normalizer.
    best = np.min(np.where(available, features.cost, np.inf), axis=1, keepdims=True)
    relative = np.where(available, features.cost, 0.0) - np.where(available, best, 0.0)
    weight = np.where(available, np.exp(-0.5 * relative), 0.0)
    weight /= np.maximum(weight.sum(axis=1, keepdims=True), 1.0)
    available &= weight >= 0.05
    measurement = wrap(np.where(available, features.yaw_deg, dr_absolute[:, None]) - dr_absolute[:, None])
    nu = wrap(measurement - (x @ H)[:, None])
    white = np.maximum(variance - sigma_a2[:, None], 0.25 * variance)
    cross = p @ H
    s = np.maximum((cross @ H)[:, None] + white, 1e-12)
    nis = nu**2 / s
    accepted = available & ((nis <= GATE_NIS) if gate else True)
    used = np.any(accepted, axis=1)
    rejected = np.any(available, axis=1) & ~used
    invalid = ~np.any(available, axis=1)
    if not np.any(used):
        return x, p, used, rejected, invalid

    r, c = np.nonzero(accepted)
    logp = np.log(weight[r, c]) - 0.5 * (nis[r, c] + np.log(s[r, c]))
    maxlog = np.full(len(x), -np.inf)
    np.maximum.at(maxlog, r, logp)
    mixture = np.exp(logp - maxlog[r])
    mixture /= np.bincount(r, weights=mixture, minlength=len(x))[r]

    gain = cross[r] / s[r, c, None]
    # All branch states are in the same local chart of the predicted state.
    dx = gain * nu[r, c, None]
    correction = np.zeros_like(x)
    np.add.at(correction, r, mixture[:, None] * dx)
    identity_minus_kh = np.eye(3) - gain[:, :, None] * H
    covariance = (identity_minus_kh @ p[r] @ identity_minus_kh.transpose(0, 2, 1)
                  + white[r, c, None, None] * gain[:, :, None] * gain[:, None, :])
    between = dx - correction[r]
    covariance += between[:, :, None] * between[:, None, :]
    total = np.zeros_like(p)
    np.add.at(total, r, mixture[:, None, None] * covariance)
    p[used] = total[used]
    return x + correction, p, used, rejected, invalid


def simulate(curve_at, dr, case_index, rho_by_case, calibration_by_case, *, e0_sd=0.0,
             w_sd=0.486, beta_sd=0.45, max_candidates=3, beta_rw_sd=0.0, gate=True):
    """Run §4.4 for paired DR trajectories, with a per-visit curve accessor.

    curve_at(visit_index) returns J, minimum-node chi2, valid pose counts,
    and optionally absolute truth headings (defaults to zero). dr holds
    unwrapped DR error relative to that truth. Both lookup models and LORO
    parameters are supplied by the caller, outside this filter.
    """
    dr = np.asarray(dr, dtype=np.float64)
    case_index = np.asarray(case_index)
    cases = np.unique(case_index)
    rho = np.array([rho_by_case[c] for c in case_index])
    sigma_a2 = rho * np.array([calibration_by_case[c].r_bar for c in case_index])
    x = np.zeros((len(dr), 3))
    f = np.broadcast_to(np.eye(3), (len(dr), 3, 3)).copy()
    f[:, 0, 1] = 1.0
    f[:, 2, 2] = rho
    q = np.zeros_like(f)
    q[:, 0, 0] = w_sd**2
    q[:, 1, 1] = beta_rw_sd**2
    q[:, 2, 2] = (1.0 - rho**2) * sigma_a2
    p = np.zeros_like(f)
    p[:, 0, 0] = e0_sd**2
    p[:, 1, 1] = beta_sd**2
    p[:, 2, 2] = sigma_a2
    err, nees, p_ee = (np.empty_like(dr) for _ in range(3))
    covered, miss, used, reject, invalid = (np.empty_like(dr, dtype=bool) for _ in range(5))
    masks = {c: case_index == c for c in cases}

    for k in range(dr.shape[1]):
        x = (f @ x[:, :, None])[:, :, 0]
        p = f @ p @ f.transpose(0, 2, 1) + q
        inputs = curve_at(k)
        j, chi2, n_valid = inputs[:3]
        truth = np.broadcast_to(inputs[3] if len(inputs) == 4 else 0.0, (len(dr),))
        dr_absolute = truth + dr[:, k]
        center = dr_absolute - x[:, 0]
        half = np.minimum(180.0, np.maximum(3.0 * np.sqrt(np.maximum(p[:, 0, 0], 0.0)), 10.0))
        miss[:, k] = np.abs(wrap(center - truth)) > half
        features = candidate_features(j, chi2, n_valid, center, half, max_candidates)
        variance = np.full_like(features.r_raw, np.nan)
        for c, mask in masks.items():
            candidate = calibration_by_case[c]
            variance[mask] = (candidate.constant_r if candidate.constant_r is not None else
                              candidate.c_l * np.where(features.valid_curvature[mask],
                                                       features.r_raw[mask], candidate.cap_raw))
        x, p, used[:, k], reject[:, k], invalid[:, k] = _branch_update(
            x, p, features, variance, sigma_a2, dr_absolute, gate)
        p_ee[:, k] = np.maximum(p[:, 0, 0], 1e-12)
        err[:, k] = wrap(dr[:, k] - x[:, 0])
        nees[:, k] = err[:, k]**2 / p_ee[:, k]
        covered[:, k] = np.abs(err[:, k]) <= 1.96 * np.sqrt(p_ee[:, k])
    return dict(err=err, nees=nees, covered=covered, miss=miss, used=used, reject=reject,
                invalid=invalid, p_ee=p_ee)
