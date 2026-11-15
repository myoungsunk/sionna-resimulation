"""Frozen M1 donor covariance fit and offline M3 revisit diagnostics."""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize


KNOTS = np.array([0., 1.5, 3., 6., 10.])
DISTANCE_EDGES = np.array([0., .02, .05, .1, .25, .5, 1., 2., np.inf])
YAW_EDGES = np.deg2rad([0., 2., 5., 10., 20., 45., 90., np.inf])
LENGTH_M = (.1, .25, .5, 1., 2., 4.)
LENGTH_DEG = (5., 10., 20., 45., 90., 180.)
Q_STARTS = (.05, .30, .70, .95)
CHANNELS = ('r', 's')
MIN_PAIRS = 20
SHORT_LAG_S = 10.
TIE_TOLERANCE = 1e-12
WHITE_FLOOR = .05


@dataclass(frozen=True)
class Donor:
    time: np.ndarray
    prior: np.ndarray
    distance: np.ndarray
    residual: np.ndarray
    r_ref: np.ndarray
    standardized: np.ndarray
    arc: np.ndarray
    yaw_arc: np.ndarray


def prepare_donor(packet, residual, reference_trace, anchor, arc, yaw_arc):
    """Bind full donor packets to the target fold's LORO reference replay.

    Arc is cumulative absolute encoder distance in m. Yaw arc is cumulative
    absolute wrapped LORO prior minus previous posterior yaw in rad.
    """
    time = np.asarray(packet['t'], dtype=float)
    prior = np.asarray(reference_trace['prior'], dtype=float)
    r_ref = np.diagonal(reference_trace['Reff'], axis1=-2, axis2=-1)
    residual, arc, yaw_arc = (np.asarray(value, dtype=float) for value in (residual, arc, yaw_arc))
    n = len(time)
    if (time.shape != (n,) or prior.shape != (n, 4) or residual.shape != (n, 2) or
            r_ref.shape != (n, 2) or arc.shape != (n,) or yaw_arc.shape != (n,) or n < 2):
        raise ValueError('Invalid donor packet/trace dimensions')
    if (not all(np.isfinite(value).all() for value in (time, prior, residual, r_ref, arc, yaw_arc)) or
            np.any(r_ref <= 0.) or np.any(np.diff(time) <= 0.) or
            np.any(np.diff(arc) < 0.) or np.any(np.diff(yaw_arc) < 0.)):
        raise ValueError('Invalid donor values, ordering, or R_ref')
    distance = np.linalg.norm(prior[:, :2] - np.asarray(anchor)[:2], axis=1)
    u = (residual - residual.mean(axis=0)) / np.sqrt(r_ref)
    standardized = u - u.mean(axis=0)
    return Donor(time, prior, distance, residual, r_ref, standardized, arc, yaw_arc)


def _interp_design(x, knots):
    eye = np.eye(len(knots))
    return np.column_stack([np.interp(x, knots, basis) for basis in eye])


def _pair_groups(distance, yaw):
    return ((np.searchsorted(DISTANCE_EDGES[1:], distance, side='right') * (len(YAW_EDGES) - 1))
            + np.searchsorted(YAW_EDGES[1:], yaw, side='right'))


@dataclass(frozen=True)
class Pairs:
    i: np.ndarray
    j: np.ndarray
    dt: np.ndarray
    arc: np.ndarray
    yaw_arc: np.ndarray
    xy: np.ndarray
    yaw: np.ndarray


def _pairs(donor, *, short_only=False):
    i, j = np.triu_indices(len(donor.time), k=1)
    dt = donor.time[j] - donor.time[i]
    if short_only:
        keep = dt <= SHORT_LAG_S
        i, j, dt = i[keep], j[keep], dt[keep]
    arc = donor.arc[j] - donor.arc[i]
    yaw_arc = donor.yaw_arc[j] - donor.yaw_arc[i]
    xy = np.linalg.norm(donor.prior[j, :2] - donor.prior[i, :2], axis=1)
    ydiff = donor.prior[j, 2] - donor.prior[i, 2]
    yaw = np.abs((ydiff + np.pi) % (2 * np.pi) - np.pi)
    return Pairs(i, j, dt, arc, yaw_arc, xy, yaw)


@dataclass(frozen=True)
class Regression:
    design: np.ndarray
    left: np.ndarray
    right: np.ndarray
    group: np.ndarray
    counts: np.ndarray
    arc: np.ndarray
    yaw_arc: np.ndarray
    targets: np.ndarray
    weights: np.ndarray
    support: np.ndarray
    expand: np.ndarray
    grouped_labels: list


def _regression(donors):
    hats = [_interp_design(donor.distance, KNOTS) for donor in donors.values()]
    support_count = np.sum([(hat > 0.).sum(axis=0) for hat in hats], axis=0)
    support = support_count >= 20
    if not support.any():
        raise ValueError('M1 fit unsupported: no q knot with 20 donor packets')
    expand = _interp_design(KNOTS, KNOTS[support])
    joined_design = np.concatenate(hats) @ expand
    left, right, groups, arc, yaw_arc, counts, targets, weights, labels = ([] for _ in range(9))
    group_offset = 0
    packet_offset = 0
    n_bins = (len(DISTANCE_EDGES) - 1) * (len(YAW_EDGES) - 1)
    for name, donor in donors.items():
        pairs = _pairs(donor, short_only=True)
        bins = _pair_groups(pairs.arc, pairs.yaw_arc)
        count = np.bincount(bins, minlength=n_bins)
        used = np.flatnonzero(count >= MIN_PAIRS)
        if not len(used):
            raise ValueError(f'M1 fit unsupported in donor {name}: no motion bin with 20 pairs')
        select = count[bins] >= MIN_PAIRS
        selected_bins = bins[select]
        new_ids = np.searchsorted(used, selected_bins)
        left.append(pairs.i[select] + packet_offset)
        right.append(pairs.j[select] + packet_offset)
        groups.append(new_ids + group_offset)
        arc.append(pairs.arc[select])
        yaw_arc.append(pairs.yaw_arc[select])
        counts.append(count[used])
        product = donor.standardized[pairs.i[select]] * donor.standardized[pairs.j[select]]
        target = np.column_stack([np.bincount(new_ids, weights=product[:, c], minlength=len(used))
                                  / count[used] for c in range(2)])
        targets.append(target)
        weights.append(np.full(len(used), 1. / (len(used) * len(donors))))
        labels.extend((name, int(bin_id)) for bin_id in used)
        group_offset += len(used)
        packet_offset += len(donor.time)
    joined = [np.concatenate(value) for value in (left, right, groups, counts, arc, yaw_arc, targets, weights)]
    return Regression(joined_design, *joined, support_count, expand, labels)


def _factor(reg, ell_m, ell_deg):
    return np.exp(-reg.arc / ell_m - reg.yaw_arc / np.deg2rad(ell_deg)) / reg.counts[reg.group]


def _prediction(theta, reg, factor):
    # Optimize sqrt(q knots); interpolation is always performed on q, not sqrt(q).
    amplitude = np.sqrt(reg.design @ (theta * theta))
    left, right = amplitude[reg.left], amplitude[reg.right]
    predicted = np.bincount(reg.group, weights=factor * left * right, minlength=len(reg.counts))
    return predicted, amplitude, left, right


def _objective(theta, reg, factor, channel):
    predicted, amplitude, left, right = _prediction(theta, reg, factor)
    err = predicted - reg.targets[:, channel]
    score = float(np.dot(reg.weights, err * err))
    chain = factor * (2 * reg.weights * err)[reg.group]
    n = len(amplitude)
    d_amplitude = (np.bincount(reg.left, weights=chain * right, minlength=n) +
                   np.bincount(reg.right, weights=chain * left, minlength=n))
    ratio = np.divide(d_amplitude, amplitude, out=np.zeros_like(amplitude), where=amplitude > 0.)
    gradient = theta * (reg.design.T @ ratio)
    return score, gradient


def _fit_channel(reg, channel):
    n_variables = reg.design.shape[1]
    best, grid = None, []
    for ell_m in LENGTH_M:
        for ell_deg in LENGTH_DEG:
            factor = _factor(reg, ell_m, ell_deg)
            starts = []
            for initial in Q_STARTS:
                fit = minimize(_objective, np.full(n_variables, np.sqrt(initial)), args=(reg, factor, channel),
                               jac=True, method='L-BFGS-B', bounds=[(0., 1.)] * n_variables,
                               options={'ftol': 1e-12, 'gtol': 1e-7, 'maxiter': 200})
                cost = float(fit.fun) if np.isfinite(fit.fun) else None
                starts.append({'q_initial': initial, 'loss': cost, 'success': bool(fit.success),
                               'iterations': int(fit.nit), 'function_evaluations': int(fit.nfev),
                               'solver_status': int(fit.status), 'solver_message': str(fit.message)})
                if (fit.success and cost is not None and np.isfinite(fit.x).all() and
                        (best is None or cost < best[0] - TIE_TOLERANCE)):
                    best = cost, ell_m, ell_deg, fit.x.copy()
            if not any(start['success'] and start['loss'] is not None for start in starts):
                raise RuntimeError(f'All M1 q fits failed at {ell_m:g} m, {ell_deg:g} deg, {CHANNELS[channel]}')
            grid.append({'ell_m': ell_m, 'ell_deg': ell_deg, 'starts': starts})
    if best is None:
        raise RuntimeError(f'No converged M1 q fit for {CHANNELS[channel]}')
    score, ell_m, ell_deg, theta = best
    predicted, *_ = _prediction(theta, reg, _factor(reg, ell_m, ell_deg))
    fit_bins = []
    for index, (donor, bin_id) in enumerate(reg.grouped_labels):
        row = _bin_label(bin_id)
        row.update(donor=donor, n_pairs=int(reg.counts[index]),
                   weight=float(reg.weights[index]), observed=float(reg.targets[index, channel]),
                   predicted=float(predicted[index]),
                   observed_minus_predicted=float(reg.targets[index, channel] - predicted[index]))
        fit_bins.append(row)
    return {'q_knots': (reg.expand @ (theta * theta)).tolist(), 'ell_m': ell_m, 'ell_deg': ell_deg,
            'loss': score, 'distance_boundary': ell_m in (LENGTH_M[0], LENGTH_M[-1]),
            'yaw_boundary': ell_deg in (LENGTH_DEG[0], LENGTH_DEG[-1]), 'grid_fits': grid, 'fit_bins': fit_bins}


def _bin_label(bin_id):
    d, a = divmod(bin_id, len(YAW_EDGES) - 1)
    return {'distance_bin_m': [float(DISTANCE_EDGES[d]), _json_edge(DISTANCE_EDGES[d + 1])],
            'yaw_bin_deg': [float(np.rint(np.rad2deg(YAW_EDGES[a]))),
                            _json_edge(np.rint(np.rad2deg(YAW_EDGES[a + 1])))]}


def _json_edge(value):
    return float(value) if np.isfinite(value) else None


def _packet_q(donor, fit):
    q = np.interp(donor.distance, KNOTS, fit['q_knots'])
    return q, np.minimum(q, 1. - WHITE_FLOOR)


def _means(observed, predicted, white_predicted, index):
    if not len(index):
        return {'n_pairs': 0, 'observed': None, 'predicted': None, 'observed_minus_predicted': None,
                'white_clipped_predicted': None, 'observed_minus_white_clipped': None}
    obs = float(observed[index].mean())
    pred = float(predicted[index].mean())
    white_pred = float(white_predicted[index].mean())
    return {'n_pairs': int(len(index)), 'observed': obs, 'predicted': pred,
            'observed_minus_predicted': obs - pred, 'white_clipped_predicted': white_pred,
            'observed_minus_white_clipped': obs - white_pred}


def _motion_bins(donor, pairs, fits):
    bins = _pair_groups(pairs.xy, pairs.yaw)
    n_bins = (len(DISTANCE_EDGES) - 1) * (len(YAW_EDGES) - 1)
    obs = donor.standardized[pairs.i] * donor.standardized[pairs.j]
    near = (pairs.xy <= .05) & (pairs.yaw <= np.deg2rad(10.))
    rows = {}
    for channel, name in enumerate(CHANNELS):
        fit = fits[name]
        q, q_eff = _packet_q(donor, fit)
        decay = np.exp(-pairs.arc / fit['ell_m'] - pairs.yaw_arc / np.deg2rad(fit['ell_deg']))
        predicted = np.sqrt(q[pairs.i] * q[pairs.j]) * decay
        white_predicted = np.sqrt(q_eff[pairs.i] * q_eff[pairs.j]) * decay
        sums = {}
        for time_name, time_select in (('le_10_s', pairs.dt <= SHORT_LAG_S), ('gt_10_s', pairs.dt > SHORT_LAG_S)):
            sort = np.argsort(bins[time_select], kind='stable')
            selected = np.flatnonzero(time_select)[sort]
            counts = np.bincount(bins[selected], minlength=n_bins)
            end = np.cumsum(counts)
            position_bins = []
            for index, stop in enumerate(end):
                take = selected[stop - counts[index]:stop]
                position_bins.append({**_bin_label(index), **_means(obs[:, channel], predicted, white_predicted, take)})
            proximity = {}
            for proximity_name, proximity_select in (('adjacent', pairs.arc < .5), ('revisit', pairs.arc >= .5)):
                take = np.flatnonzero(near & time_select & proximity_select)
                result = _means(obs[:, channel], predicted, white_predicted, take)
                result['position_kernel_candidate'] = bool(proximity_name == 'revisit' and len(take) >= MIN_PAIRS and
                                                           result['observed'] > 0. and
                                                           result['observed_minus_predicted'] >= .20)
                proximity[proximity_name] = result
            sums[time_name] = {'n_pairs': int(len(selected)), 'position_bins': position_bins, 'proximity': proximity}
        sums['white_floor'] = {'source': '5 percent R_ref; independent thermal component unavailable',
                               'at_or_above_0_95_fraction': float(np.mean(q >= .95)),
                               'active_fraction': float(np.mean(q > q_eff)),
                               'mean_cut_q': float(np.mean(q - q_eff)),
                               'mean_cut_variance': float(np.mean((q - q_eff) * donor.r_ref[:, channel]))}
        rows[name] = sums
    return rows


def fit_fold(donors, *, fold):
    """Fit both channels on two B/B0 donor trajectories, with the fold held out."""
    if len(donors) != 2 or fold in donors:
        raise ValueError('Expected two donor routes and an absent held-out route')
    reg = _regression(donors)
    fits = {name: _fit_channel(reg, index) for index, name in enumerate(CHANNELS)}
    diagnostics, candidates = {}, []
    for route, donor in donors.items():
        diag = _motion_bins(donor, _pairs(donor), fits)
        std = donor.standardized.std(axis=0)
        cross = None if np.any(std == 0.) else float(np.mean(np.prod(donor.standardized, axis=1)) / np.prod(std))
        diagnostics[route] = {'route_mean_residual': donor.residual.mean(axis=0).tolist(),
                              'centered_standardized_residual_variance': (std**2).tolist(),
                              'contemporaneous_r_s_correlation': cross, 'by_channel': diag}
        for channel, record in diag.items():
            for window in ('le_10_s', 'gt_10_s'):
                revisit = record[window]['proximity']['revisit']
                if revisit['position_kernel_candidate']:
                    candidates.append({'donor': route, 'channel': channel, 'lag': window, **revisit})
    return {'held_out_route': fold, 'donor_routes': list(donors), 'q_knots_m': KNOTS.tolist(),
            'q_knot_support_counts': reg.support.tolist(), 'q_knots_fitted': (reg.support >= 20).tolist(),
            'fit_pair_total': int(len(reg.left)), 'fit_max_lag_s': SHORT_LAG_S,
            'model': 'sqrt(q_i*q_j)*exp(-arc/ell_m-abs_yaw_arc/ell_rad)',
            'residual': 'donor-centered raw epsilon / sqrt(R_ref), then donor-centered again',
            'grid_tie_absolute_loss_tolerance': TIE_TOLERANCE, 'fits': fits, 'donor_diagnostics': diagnostics,
            'position_kernel_candidates': candidates}


def compare_slow(donors, fit, slow_by_route):
    """Compare D3 smooth-sample variance and fitted q on the identical support."""
    if list(donors) != fit['donor_routes'] or set(slow_by_route) != set(donors):
        raise ValueError('D3 and D2 donor routes differ')
    edges = np.r_[KNOTS, np.inf]
    out = {}
    for route, donor in donors.items():
        slow, support = slow_by_route[route]
        slow, support = np.asarray(slow), np.asarray(support)
        if slow.shape != donor.residual.shape or support.dtype.kind != 'b' or support.shape != donor.time.shape:
            raise ValueError(f'Invalid slow decomposition support for {route}')
        if not np.isfinite(slow[support]).all():
            raise ValueError(f'Nonfinite slow component on supported packets for {route}')
        result = {}
        for c, name in enumerate(CHANNELS):
            q, q_eff = _packet_q(donor, fit['fits'][name])
            bins = []
            for lo, hi in zip(edges[:-1], edges[1:]):
                selected = support & (donor.distance >= lo) & (donor.distance < hi)
                n = int(selected.sum())
                row = {'distance_bin_m': [float(lo), _json_edge(hi)], 'n_support': n}
                if n:
                    slow_fraction = float(slow[selected, c].var() / donor.r_ref[selected, c].mean())
                    mean_q = float(q[selected].mean())
                    mean_q_eff = float(q_eff[selected].mean())
                    row.update(slow_variance_over_mean_r_ref=slow_fraction, mean_q=mean_q, mean_q_eff=mean_q_eff,
                               q_minus_slow_fraction=mean_q - slow_fraction,
                               q_eff_minus_slow_fraction=mean_q_eff - slow_fraction,
                               white_floor_active_fraction=float(np.mean(q[selected] > q_eff[selected])))
                bins.append(row)
            result[name] = bins
        out[route] = result
    return out
