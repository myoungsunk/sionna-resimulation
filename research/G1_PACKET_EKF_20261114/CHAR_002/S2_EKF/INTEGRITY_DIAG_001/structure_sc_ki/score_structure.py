"""Check candidate traces and score them against the frozen D5 reference."""

from pathlib import Path

import numpy as np

from d0_d5 import KNOTS, compare, identity
from d1_shuffle import dump
from metrics_s2 import _summarize
from replay_s2 import parity, read_npz, validate_trace, wrap
from verify_s2 import from_trace


ARMS = ('E0', 'LORO', 'SC', 'KI')
RMS = ('heading_rmse_deg', 'xy_rmse_cm')
COVERAGES = ('pose95_coverage', 'heading95_coverage', 'xy95_coverage')


def recheck_trace(trace, case, arm):
    validate_trace(trace)
    mask = case['mask']
    packet = case['packet']
    identity(trace, case, ('mask',))
    for posterior, prior in [('x', 'prior'), ('P', 'Pprior')]:
        if not np.array_equal(trace[posterior][~mask], trace[prior][~mask]):
            raise ValueError(f'{arm} rejected packet changed {posterior}')
    if np.any(trace['K'][~mask]):
        raise ValueError(f'{arm} rejected packet has nonzero gain')

    anchor = np.array(case['spec']['anchor'][:2])
    previous = np.vstack((packet['x0'], trace['x'][:-1]))
    rho_before = np.linalg.norm(previous[:, :2] - anchor, axis=1)
    rho_prior = np.linalg.norm(trace['prior'][:, :2] - anchor, axis=1)
    sigma = np.interp(rho_before, KNOTS, case['table'])
    ref_noise = packet['R'].copy()
    ref_noise[:, 1, 1] += sigma**2
    kernel = [case['fit']['fits'][channel] for channel in ('r', 's')]
    knots = case['fit']['q_knots_m']
    q = np.column_stack([np.interp(rho_prior, knots, model['q_knots']) for model in kernel])
    effective_q = np.minimum(q, .95)
    d = np.r_[0., abs(case['controls']['ds'][1:])]
    yaw = np.r_[0., abs(wrap(trace['prior'][1:, 2] - previous[1:, 2]))]
    ell_d = [model['ell_m'] for model in kernel]
    ell_yaw = np.deg2rad([model['ell_deg'] for model in kernel])
    arc, yaw_arc = np.cumsum(d), np.cumsum(yaw)
    loading = np.sqrt(effective_q * ref_noise.diagonal(axis1=1, axis2=2))[:, None, :] * np.eye(2)
    white = ref_noise - loading @ loading.swapaxes(1, 2)
    np.linalg.cholesky(white)
    expected = dict(rho_before=rho_before, rho_prior=rho_prior, sigma_b=sigma, R_ref=ref_noise, q=q,
                    q_eff=effective_q, alpha=np.exp(-d[:, None] / ell_d - yaw[:, None] / ell_yaw),
                    arc=arc, yaw_arc=yaw_arc, D=loading, R_white=white,
                    nu=packet['z'] - trace['h'] - packet['muMB'])
    if arm == 'SC':
        G = np.concatenate((trace['H'], loading), axis=2)
        pred, post, K = (trace[key] for key in ('Pprior_aug', 'P_aug', 'K_aug'))
        expected['Reff'] = white
        for cov, native in ((pred, trace['Pprior']), (post, trace['P'])):
            if (not np.array_equal(cov[:, :4, :4], native) or
                    not np.array_equal(cov[:, 4:, 4:], np.broadcast_to(np.eye(2), cov[:, 4:, 4:].shape)) or
                    np.max(abs(cov - cov.swapaxes(1, 2))) > 1e-12 or np.linalg.eigvalsh(cov).min() < -1e-12):
                raise ValueError('Invalid SC augmented covariance')
        if (np.any(K[:, 4:]) or np.any(trace['u_mean']) or
                not np.array_equal(post[~mask], pred[~mask])):
            raise ValueError('SC changed a fixed nuisance mean/gain or updated on a reject')
        R = white
    else:
        t = packet['t']
        past = np.flatnonzero(mask)
        multiplier = np.ones_like(q)
        count = np.zeros(len(t), dtype=int)
        for i, end in enumerate(np.searchsorted(past, np.arange(len(t)))):
            indices = past[max(0, end - 100):end]
            indices = indices[t[i] - t[indices] <= 10.]
            decay = np.exp(-(arc[i] - arc[indices, None]) / ell_d -
                           (yaw_arc[i] - yaw_arc[indices, None]) / ell_yaw)
            multiplier[i] += 2. * (np.sqrt(effective_q[i] * effective_q[indices]) * decay).sum(axis=0)
            count[i] = len(indices)
        R = ref_noise * multiplier[:, None, :]
        expected.update(Reff=R, k=multiplier, history_n=count)
        G, pred, post, K = (trace[key] for key in ('H', 'Pprior', 'P', 'K'))
    S = G @ pred @ G.swapaxes(1, 2) + R
    expected['S'] = S
    np.linalg.cholesky(S)
    gain_product = K @ S
    gain_target = pred @ G.swapaxes(1, 2)
    gain_shape = gain_product[mask, :4].shape
    K_check = parity({'gain_product': gain_product[mask, :4]},
                     {'gain_product': gain_target[mask, :4].reshape(gain_shape)})
    A = np.eye(pred.shape[1]) - K @ G
    joseph = A @ pred @ A.swapaxes(1, 2) + K @ R @ K.swapaxes(1, 2)
    post_check = parity({'joseph': post}, {'joseph': joseph})
    x_check = trace['prior'] + (trace['K'] @ trace['nu'][..., None])[..., 0]
    x_check[mask, 2] = wrap(x_check[mask, 2])
    expected['x'] = x_check
    return {'n': len(mask), 'accepted': int(mask.sum()), 'rejected': int((~mask).sum()),
            'reconstruction': parity(trace, expected) | K_check | post_check,
            'white_floor_fraction_by_channel': dict(zip(('r', 's'), (q >= .95).mean(axis=0).tolist()))}


def evaluate_gates(scores, thresholds, ratios):
    route_integrity, route_accuracy = {}, {}
    for route, metrics in scores['routes'].items():
        route_integrity[route] = {
            metric: metrics[metric] >= thresholds[f'per_route_{metric.removesuffix("_coverage")}_min']
            for metric in COVERAGES}
        route_accuracy[route] = {metric: ratios['routes'][route][metric] <= thresholds['per_route_rmse_ratio_max']
                                 for metric in RMS}
    pooled = scores['pooled']
    low, high = thresholds['pooled_mean_nees3_interval']
    pooled_integrity = {'pose95_coverage': pooled['pose95_coverage'] >= thresholds['pooled_pose95_min'],
                        'heading95_coverage': pooled['heading95_coverage'] >= thresholds['pooled_heading95_min'],
                        'mean_nees3': low <= pooled['mean_nees3'] <= high}
    pooled_accuracy = {metric: ratios['pooled'][metric] <= thresholds['pooled_rmse_ratio_max'] for metric in RMS}
    return {'routes': {route: {'integrity': route_integrity[route], 'accuracy': route_accuracy[route]}
                       for route in route_integrity},
            'pooled': {'integrity': pooled_integrity, 'accuracy': pooled_accuracy},
            'integrity_pass': all(pooled_integrity.values()) and all(all(gate.values()) for gate in route_integrity.values()),
            'accuracy_pass': all(pooled_accuracy.values()) and all(all(gate.values()) for gate in route_accuracy.values())}


def score(out: Path, lock, *, save=True):
    rows, times, gates, ki_details = {}, {}, {}, {}
    for cell in lock['cells']:
        route = cell['route']
        evaluator = read_npz(cell['evaluator']['path'])
        times[route] = evaluator['t']
        traces = {'E0': read_npz(cell['fixed_gate_trace']['path']), 'LORO': read_npz(cell['loro_trace']['path']),
                  **{arm: read_npz(out / f'{route}_{arm}_trace.npz') for arm in lock['arms_in_order']}}
        rows[route] = {}
        fixed_mask = traces['E0']['mask']
        for arm, trace in traces.items():
            identity(evaluator, trace, ('t', 'pose_id'))
            if trace['mask'].dtype.kind != 'b' or not np.array_equal(fixed_mask, trace['mask']):
                raise ValueError(f'Frozen gate mismatch in scoring {route}/{arm}')
            rows[route][arm] = from_trace(trace, evaluator['truth'])
        gates[route] = {'n': len(fixed_mask), 'accepted': int(fixed_mask.sum()), 'rejected': int((~fixed_mask).sum())}
        elapsed = times[route] - times[route][0]
        ki_details[route] = {}
        cutoff = lock['KI']['max_age_s_inclusive']
        for segment, select in [('first_10_s', elapsed < cutoff), ('after_first_10_s', elapsed >= cutoff)]:
            k = traces['KI']['k'][select]
            n = traces['KI']['history_n'][select]
            ki_details[route][segment] = {
                'metrics': {arm: _summarize(rows[route][arm][select]) for arm in ('LORO', 'KI')},
                'k_by_channel': dict(zip(('r', 's'), np.quantile(k, [0., .5, .95, 1.], axis=0).T.tolist())),
                'k_quantiles': [0., .5, .95, 1.], 'history_cap_fraction': float((n == lock['KI']['max_accepted_history']).mean())}

    groups = {'routes': {route: {arm: _summarize(data[arm]) for arm in ARMS} for route, data in rows.items()},
              'pooled': {arm: _summarize(np.concatenate([data[arm] for data in rows.values()])) for arm in ARMS}}
    output = {'fixed_gate_packets': gates, 'metrics': groups, 'KI_segments': ki_details, 'assessment': {}, 'paired_vs_LORO': {}}
    for arm in ARMS:
        scores = {'routes': {route: data[arm] for route, data in groups['routes'].items()}, 'pooled': groups['pooled'][arm]}
        ratios = {'routes': {route: {key: data[arm][key] / data['LORO'][key] for key in RMS}
                             for route, data in groups['routes'].items()},
                  'pooled': {key: scores['pooled'][key] / groups['pooled']['LORO'][key] for key in RMS}}
        output['assessment'][arm] = evaluate_gates(scores, lock['M2_thresholds'], ratios) | {'ratios_to_LORO': ratios}
        if arm != 'LORO':
            cases = {route: {'time': times[route], 'e0': data['LORO'], 'loro': data[arm]} for route, data in rows.items()}
            output['paired_vs_LORO'][arm] = {route: paired([case]) for route, case in cases.items()} | {
                'pooled': paired(list(cases.values()))}

    eligible = [arm for arm in lock['arms_in_order'] if output['assessment'][arm]['integrity_pass'] and
                output['assessment'][arm]['accuracy_pass']]
    cost = {arm: max(output['assessment'][arm]['ratios_to_LORO']['pooled'].values()) for arm in eligible}
    tie = lock['score']['candidate_tie_within_absolute_rmse_ratio']
    chosen = next((arm for arm in lock['score']['candidate_tie_order'] if arm in cost and
                   cost[arm] <= min(cost.values()) + tie), None)
    output['decision'] = {'eligible': eligible, 'selected': chosen, 'max_pooled_rmse_ratio': cost}
    if save:
        dump(out / 'RESULTS.json', output)
    return output


def paired(cases):
    result = compare(cases)
    return {'delta': result['loro_minus_e0'], 'bootstrap_95_interval': result['moving_block_bootstrap_paired']}
