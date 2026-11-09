"""Finite, purged, route-heldout calibration of B-MCG same-prior damping.

Evaluator pose is allowed in a separate offline splitter only. Error labels are
used on training/development masks for selection; selected and fixed-diagnostic
heldout losses are evaluated only after the immutable policy lock is written.
No result in this file proves closed-loop utility or unseen-seed generalization.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
import csv
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from scipy.spatial import cKDTree
from mcg import Config, covariance_update, weights, wrap

ROUTES = ('R2', 'R4', 'R5')
STRATA = ('B_FROZEN', 'B_BIAS_COV')
MODES = ('ACTIVE_R', 'ACTIVE_S', 'ACTIVE_RS')
TAUS = (1.5, 2., 3., 4.)
HISTORY_S = 5.
FUTURE_S = 10.
POSE_RADIUS_M = .25
POSE_YAW_RAD = np.radians(5.)
GOOD_GAIN_BUDGET = .05
BUDGET_COMPARISON_ATOL = 1e-12
POSITIVE_FRACTION_EPS = 1e-12


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def table(path, rows):
    if not rows:
        raise ValueError('EMPTY_TABLE')
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def candidate_id(mode, tau):
    return mode+'_tau'+format(tau, 'g').replace('.', 'p')


def candidates():
    return {candidate_id(mode, tau): (mode, replace(Config(), tau_r=tau, tau_s=tau,
             tau_joint=float(np.sqrt(2)*tau), beta_min=.25)) for mode in MODES for tau in TAUS}


def support_intervals(t):
    return np.searchsorted(t, t-HISTORY_S-1e-9), np.searchsorted(t, t+FUTURE_S+1e-9, side='right')


def support_union(mask, starts, ends, n):
    changes = np.zeros(n+1, dtype=int)
    np.add.at(changes, starts[mask], 1)
    np.add.at(changes, ends[mask], -1)
    return np.cumsum(changes[:-1]) > 0


def overlaps_other_pose_support(poses, reference):
    if not len(reference):
        return np.zeros(len(poses), bool)
    tree = cKDTree(reference[:, :2])
    hits = tree.query_ball_point(poses[:, :2], POSE_RADIUS_M+1e-12)
    return np.array([bool(ids) and bool(np.any(abs(wrap(reference[ids, 2]-p[2])) <= POSE_YAW_RAD+1e-12))
                     for p, ids in zip(poses, hits)], bool)


def any_in_support(flags, starts, ends):
    prefix = np.r_[0, np.cumsum(flags.astype(int))]
    return prefix[ends]-prefix[starts] > 0


def build_split_geometry(assets, out):
    """Splitter-only access to truth poses. Return masks and joins, never poses.

    Both train/dev purges are computed from unpurged supports simultaneously.
    This deliberately has no order-dependent relaxation after a support is lost.
    """
    geometry = {}
    receipts = {}
    for route in ROUTES:
        path = assets/f'{route}_B0_Full_10__evaluator.npz'
        with np.load(path, allow_pickle=False) as f:
            t, ids, pose = f['t'], f['pose_id'], f['truth']
        assert pose.shape == (len(t), 3) and len(np.unique(ids)) == len(t)
        assert np.isfinite(pose).all() and np.all(np.diff(t) > 0)
        lo, hi = support_intervals(t)
        cut = t[0]+.6*(t[-1]-t[0])
        eligible = (t >= t[0]+HISTORY_S-1e-9) & (t <= t[-1]-FUTURE_S+1e-9)
        train = eligible & (t <= cut-FUTURE_S-1e-9)
        dev = eligible & (t >= cut+HISTORY_S+1e-9)
        geometry[route] = dict(t=t, pose_id=ids, pose=pose, lo=lo, hi=hi, train=train, dev=dev)
        receipts[route] = {'evaluator_sha256': sha(path), 'n': len(t), 'cut_time_s': float(cut),
                           'raw_train_n': int(train.sum()), 'raw_dev_n': int(dev.sum())}
    splits = {}
    summaries = {}
    packed = {}
    for heldout in ROUTES:
        training = [r for r in ROUTES if r != heldout]
        support = {}
        for part in ('train', 'dev'):
            support[part] = np.concatenate([geometry[r]['pose'][support_union(geometry[r][part], geometry[r]['lo'], geometry[r]['hi'], len(geometry[r]['t']))] for r in training])
        splits[heldout] = {}
        summaries[heldout] = {'train_routes': training, 'routes': {}}
        for route in training:
            g = geometry[route]
            held_near = any_in_support(overlaps_other_pose_support(g['pose'], geometry[heldout]['pose']), g['lo'], g['hi'])
            route_summary = {}
            splits[heldout][route] = {}
            for part, other in (('train', 'dev'), ('dev', 'train')):
                opposite_near = any_in_support(overlaps_other_pose_support(g['pose'], support[other]), g['lo'], g['hi'])
                base = g[part]
                keep = base & ~held_near & ~opposite_near
                splits[heldout][route][part] = keep
                route_summary[part] = {'before_pose_purge': int(base.sum()),
                    'excluded_near_heldout_support': int(np.count_nonzero(base & held_near)),
                    'excluded_near_opposite_partition_support': int(np.count_nonzero(base & opposite_near)),
                    'excluded_union': int(np.count_nonzero(base & (held_near | opposite_near))),
                    'remaining': int(keep.sum()), 'status': 'ESTIMABLE_SAMPLE_AVAILABLE' if keep.any() else 'NOT_ESTIMABLE_EMPTY_SPLIT'}
                packed[f'holdout_{heldout}__{route}__{part}'] = keep
            summaries[heldout]['routes'][route] = route_summary
        summaries[heldout]['remaining_train_n'] = sum(int(splits[heldout][r]['train'].sum()) for r in training)
        summaries[heldout]['remaining_dev_n'] = sum(int(splits[heldout][r]['dev'].sum()) for r in training)
        summaries[heldout]['all_requested_route_partitions_nonempty'] = all(splits[heldout][r][p].any() for r in training for p in ('train', 'dev'))
    joins = {r: {k: geometry[r][k].copy() for k in ('t', 'pose_id')} for r in ROUTES}
    for route in ROUTES:
        packed[route+'_t'] = joins[route]['t']; packed[route+'_pose_id'] = joins[route]['pose_id']
    np.savez_compressed(out/'SPLIT_MASKS.npz', **packed)
    result = {'status': 'SPLIT_GEOMETRY_LOCKED', 'geometry_only_evaluator_access_before_policy_lock': True,
        'geometry_truth_not_runtime_feature': True, 'geometry_not_used_to_rank_candidates': True,
        'policy_selection_labels': 'Only training/dev losses; no heldout losses until POLICY_LOCK.json exists.',
        'time_split': 'early 60% duration train and late 40% dev; train ends 10 s before cut, dev starts 5 s after cut',
        'embargo_s': HISTORY_S+FUTURE_S, 'support': 'inclusive history [k-5s,k] and future diagnostic [k,k+10s]',
        'near_pose_rule': {'xy_euclidean_m': POSE_RADIUS_M, 'wrapped_yaw_deg': 5., 'combination': 'AND'},
        'purge': 'Remove any target whose full support contains any pose near any heldout pose or any opposite-partition support pose; simultaneous conservative purge; no relaxation.',
        'inputs': receipts, 'folds': summaries,
        'generalization_limit': 'Exposed one corridor and seed10; gyro noise prefixes shared across routes. These masks do not establish independent-seed validation.'}
    dump(out/'SPLIT_GEOMETRY_RECEIPT.json', result)
    return splits, joins, result


def profile_config_check(f):
    expected = asdict(Config())
    config_keys = [k for k in expected if not k.startswith('tau_') and k not in ('beta_min', 'enable_r', 'enable_s')]
    if 'config_json' in f.files:
        actual = json.loads(str(f['config_json']))
        for key in config_keys:
            assert key in actual, ('MISSING_PROFILE_CONFIG_KEY', key)
            assert np.array_equal(np.asarray(actual[key]), np.asarray(expected[key])), ('PROFILE_CONFIG_MISMATCH', key, actual[key], expected[key])
        return 'PROFILE_CONFIG_JSON_VERIFIED'
    for key in ('config_sha256', 'config_digest'):
        if key in f.files:
            assert str(f[key]) == Config().digest(), 'PROFILE_CONFIG_DIGEST_MISMATCH'
            return 'PROFILE_CONFIG_DIGEST_VERIFIED'
    raise ValueError('MISSING_PROFILE_CONFIG_PROVENANCE')


def forecasts_for_route(profiles, archives, stratum, route, join, grid):
    pp = profiles/stratum/(route+'.npz')
    tp = archives/route/f'{route}_{stratum}.npz'
    with np.load(pp, allow_pickle=False) as f:
        config_check = profile_config_check(f)
        scores, valid = f['scores'], f['valid'].astype(bool)
        state_key = next((k for k in ('states', 'statuses', 'status') if k in f.files), None)
        if state_key is None: raise ValueError('PROFILE_STATUS_MISSING')
        states = f[state_key].astype(str)
        assert np.array_equal(f['t'], join['t']) and np.array_equal(f['pose_id'], join['pose_id']), 'PROFILE_JOIN'
    with np.load(tp, allow_pickle=False) as f:
        tr = {k: f[k] for k in ('x', 'P', 'prior', 'Pprior', 'H', 'nu', 'Reff', 'mask')}
    lock = json.loads((archives/route/'SHA256.json').read_text())
    assert sha(tp) == lock[tp.name], 'ARCHIVED_TRACE_HASH'
    historical_fit_routes = None
    if stratum == 'B_BIAS_COV':
        historical_fit_routes = json.loads((archives/route/'RESULTS.json').read_text())['fit']['train_routes']
    n = len(join['t'])
    assert scores.shape == (n, 3) and valid.shape == (n, 2) and states.shape == (n,)
    assert tr['prior'].shape == (n, 4) and tr['mask'].shape == (n,)
    assert np.isfinite(scores[:, :2][valid]).all() and np.all(scores[:, :2][valid] >= 0)
    assert np.isfinite(scores[:, 2][valid.all(axis=1)]).all()
    base = np.empty((n, 4)); max_x = 0.; max_p = 0.
    for k in range(n):
        xx, cc, _, _, _ = covariance_update(tr['prior'][k], tr['Pprior'][k], tr['H'][k], tr['nu'][k], tr['Reff'][k], permitted=bool(tr['mask'][k]))
        base[k] = xx
        max_x = max(max_x, float(np.max(abs(xx-tr['x'][k]))))
        max_p = max(max_p, float(np.max(abs(cc-tr['P'][k]))))
    assert max_x <= 1e-10 and max_p <= 1e-10, ('SAME_PRIOR_BASELINE_PARITY', stratum, route, max_x, max_p)
    pred = {}; beta = {}; reasons = {}
    for name, (mode, cfg) in grid.items():
        xx = np.empty((n, 4)); bb = np.empty((n, 2)); rr = []
        for k in range(n):
            sc = {'scores': scores[k], 'valid_channels': valid[k], 'status': states[k]}
            bb[k], reason = weights(sc, cfg, mode); rr.append(reason)
            xx[k] = covariance_update(tr['prior'][k], tr['Pprior'][k], tr['H'][k], tr['nu'][k], tr['Reff'][k], bb[k], bool(tr['mask'][k]))[0]
        pred[name] = xx; beta[name] = bb; reasons[name] = np.asarray(rr)
    pred['OFF'] = base.copy(); beta['OFF'] = np.ones((n, 2)); reasons['OFF'] = np.full(n, 'OFF')
    return {'full': base, 'skip': tr['prior'], 'mask': tr['mask'].astype(bool), 'predictions': pred, 'beta': beta, 'reasons': reasons,
        'scores': scores, 'valid': valid, 'source_states': states,
        'receipt': {'profile_sha256': sha(pp), 'trace_sha256': sha(tp), 'profile_config': config_check,
                    'historical_B_calibration_training_routes': historical_fit_routes,
                    'same_prior_full_x_maxabs': max_x, 'same_prior_full_P_maxabs': max_p}}


def load_loss_truth(assets, route, join):
    with np.load(assets/f'{route}_B0_Full_10__evaluator.npz', allow_pickle=False) as f:
        assert np.array_equal(f['t'], join['t']) and np.array_equal(f['pose_id'], join['pose_id'])
        return f['truth']


def loss(x, truth):
    return np.column_stack((np.degrees(wrap(x[:, 2]-truth[:, 2]))**2, np.sum((x[:, :2]-truth[:, :2])**2, axis=1)))


def aggregate_quality(chunks):
    full = np.concatenate([c['full'] for c in chunks]); skip = np.concatenate([c['skip'] for c in chunks]); policy = np.concatenate([c['policy'] for c in chunks])
    masks = np.concatenate([c['mask'] for c in chunks]); beta = np.concatenate([c['beta'] for c in chunks])
    n = len(full)
    activity = masks & np.any(beta < 1.-1e-14, axis=1)
    result = {'n': n, 'legacy_accepted_n': int(masks.sum()), 'legacy_rejected_n': int((~masks).sum()),
              'attempted_damping_n': int(np.any(beta < 1.-1e-14, axis=1).sum()), 'actual_damping_n': int(activity.sum()), 'axes': {}}
    for j, axis in enumerate(('heading_deg2', 'xy_m2')):
        good = skip[:, j] > full[:, j]
        denominator = float(np.sum(skip[good, j]-full[good, j]))
        numerator = float(np.maximum(policy[good, j]-full[good, j], 0).sum())
        baseline = float(full[:, j].sum()); policy_sum = float(policy[:, j].sum())
        net = baseline-policy_sum
        estimable = bool(n and denominator > 0. and baseline > 0.)
        result['axes'][axis] = {'status': 'ESTIMABLE' if estimable else 'NOT_ESTIMABLE',
            'baseline_loss_sum': baseline, 'policy_loss_sum': policy_sum,
            'baseline_mse': baseline/n if n else None, 'policy_mse': policy_sum/n if n else None,
            'net_saved_loss_sum': net, 'net_saved_fraction': net/baseline if baseline > 0 else None,
            'beneficial_full_update_n': int(good.sum()), 'beneficial_gain_denominator': denominator,
            'beneficial_lost_numerator': numerator, 'beneficial_lost_gain_ratio': numerator/denominator if denominator > 0 else None,
            'net_positive': bool(estimable and net > POSITIVE_FRACTION_EPS*baseline),
            'good_gain_budget_pass': bool(estimable and numerator/denominator <= GOOD_GAIN_BUDGET+BUDGET_COMPARISON_ATOL)}
    result['eligible'] = bool(n and activity.any() and all(v['net_positive'] and v['good_gain_budget_pass'] for v in result['axes'].values()))
    result['reasons'] = []
    if not n: result['reasons'].append('NOT_ESTIMABLE_EMPTY_SPLIT')
    if not activity.any(): result['reasons'].append('NO_ACTUAL_ACCEPTED_UPDATE_ACTIVITY')
    for axis, v in result['axes'].items():
        if v['status'] != 'ESTIMABLE': result['reasons'].append(axis+':NOT_ESTIMABLE_DENOMINATOR')
        elif not v['net_positive']: result['reasons'].append(axis+':NO_POSITIVE_NET_GAIN')
        if v['status'] == 'ESTIMABLE' and not v['good_gain_budget_pass']: result['reasons'].append(axis+':BENEFICIAL_GAIN_BUDGET_FAILED')
    return result


def flat_quality(q):
    row = {k: v for k, v in q.items() if k not in ('axes', 'reasons')}
    row['reasons'] = '|'.join(q['reasons'])
    for axis, values in q['axes'].items():
        row.update({axis+'_'+k: v for k, v in values.items()})
    return row


def sliced_chunk(forecast, truth, name, selected):
    return {'full': loss(forecast['full'][selected], truth[selected]), 'skip': loss(forecast['skip'][selected], truth[selected]),
        'policy': loss(forecast['predictions'][name][selected], truth[selected]),
        'mask': forecast['mask'][selected], 'beta': forecast['beta'][name][selected]}


def run(profiles, archives, assets, out, strata=STRATA):
    strata = tuple(strata)
    if not strata or len(set(strata)) != len(strata) or not set(strata) <= set(STRATA):
        raise ValueError('INVALID_EXPLICIT_STRATA_SCOPE')
    started_code = {name: sha(Path(__file__).with_name(name)) for name in ('calibrate_policy.py', 'mcg.py')}
    if out.exists(): raise FileExistsError('NEW_OUTPUT_REQUIRED: '+str(out))
    out.mkdir(parents=True)
    started = time.time()
    grid = candidates()
    splits, joins, split_receipt = build_split_geometry(assets, out)
    all_forecasts = {}
    sources = {}
    for stratum in strata:
        all_forecasts[stratum] = {}
        sources[stratum] = {}
        for route in ROUTES:
            all_forecasts[stratum][route] = forecasts_for_route(profiles, archives, stratum, route, joins[route], grid)
            sources[stratum][route] = all_forecasts[stratum][route]['receipt']
            print('FORECASTS_NO_ERROR_LABELS', stratum, route, flush=True)
    rows = []
    policies = {}
    diagnostic = candidate_id('ACTIVE_RS', 2.)
    for stratum in strata:
        policies[stratum] = {}
        for heldout in ROUTES:
            training = [r for r in ROUTES if r != heldout]
            train_truth = {r: load_loss_truth(assets, r, joins[r]) for r in training}
            candidate_reports = {}
            for name, (mode, cfg) in grid.items():
                candidate_reports[name] = {}
                for part in ('train', 'dev'):
                    chunks = []
                    for route in training:
                        chunk = sliced_chunk(all_forecasts[stratum][route], train_truth[route], name, splits[heldout][route][part])
                        chunks.append(chunk)
                        q = aggregate_quality([chunk])
                        rows.append({'stratum': stratum, 'heldout': heldout, 'partition': part, 'source_route': route, 'candidate': name,
                                     'mode': mode, 'tau': cfg.tau_r, **flat_quality(q)})
                    q = aggregate_quality(chunks)
                    candidate_reports[name][part] = q
                    rows.append({'stratum': stratum, 'heldout': heldout, 'partition': part, 'source_route': 'POOLED_TRAIN_ROUTES', 'candidate': name,
                                 'mode': mode, 'tau': cfg.tau_r, **flat_quality(q)})
            complete_support = split_receipt['folds'][heldout]['all_requested_route_partitions_nonempty']
            eligible = [name for name, rr in candidate_reports.items() if complete_support and rr['train']['eligible'] and rr['dev']['eligible']]
            def rank(name):
                rr = candidate_reports[name]
                worst_gain = min(rr[part]['axes'][axis]['net_saved_fraction'] for part in ('train', 'dev') for axis in ('heading_deg2', 'xy_m2'))
                return (worst_gain, grid[name][1].tau_r, -sum(rr[p]['actual_damping_n'] for p in ('train', 'dev')), -list(grid).index(name))
            chosen = max(eligible, key=rank) if eligible else 'OFF'
            mode, cfg = grid[chosen] if chosen != 'OFF' else ('OFF', Config())
            policies[stratum][heldout] = {'selected_candidate': chosen, 'mode': mode, 'config': asdict(cfg),
                'status': 'ELIGIBLE_SAME_PRIOR_CANDIDATE' if eligible else 'UTILITY_NOT_DEMONSTRATED',
                'training_routes': training, 'eligible_candidates': eligible, 'candidate_train_dev': candidate_reports,
                'all_requested_route_partitions_nonempty': complete_support,
                'selection_block_reason': None if complete_support else 'NOT_ESTIMABLE_EMPTY_REQUESTED_ROUTE_PARTITION',
                'split_remaining_train_n': split_receipt['folds'][heldout]['remaining_train_n'],
                'split_remaining_dev_n': split_receipt['folds'][heldout]['remaining_dev_n'],
                'diagnostic_only_candidate': diagnostic, 'closed_loop_adoption_authorized_by_this_lock': False}
            del train_truth
            print('POLICY_SELECTED_WITHOUT_HELDOUT_LOSS', stratum, heldout, chosen, flush=True)
    table(out/'CANDIDATE_TRAIN_DEV.csv', rows)
    assert started_code == {name: sha(Path(__file__).with_name(name)) for name in started_code}, 'CALIBRATION_CODE_CHANGED_BEFORE_LOCK'
    lock = {'schema': 'B_MCG_POLICY_LOCK_V1', 'strata': list(strata), 'locked_before_heldout_error_evaluation': True,
        'splitter_only_heldout_geometry_access': True, 'runtime_truth_access': False,
        'selection': {'tau_grid': list(TAUS), 'modes': list(MODES), 'beta_min': .25,
            'joint_threshold': 'sqrt(2)*tau', 'positive_net_required': 'both axes on train and dev',
            'beneficial_lost_gain_max': GOOD_GAIN_BUDGET, 'nontrivial_accepted_activity_required': True,
            'beneficial_budget_numeric_tolerance': BUDGET_COMPARISON_ATOL,
            'each_of_two_training_routes_must_retain_both_partitions': True,
            'rank': 'largest minimum fractional saved loss across two axes and train/dev; then higher tau; then fewer actual damped rows; then fixed candidate enumeration',
            'zero_gain_denominator': 'NOT_ESTIMABLE; fail eligibility', 'no_valid_candidate': 'OFF; no split or threshold relaxation'},
        'same_prior_limit': 'Profiles and actions use each archived baseline own prior; final policy recursion must be evaluated separately.',
        'secondary_calibration_limit': 'Preserve existing historical route-heldout B_BIAS_COV parameters per archive; do not refit. Training-route archives can have calibration learned using the guard-heldout route: this is secondary sensitivity, not nested independent holdout. B_FROZEN is controlling.',
        'generalization': 'No independent scene or noise-seed claim: exposed route data, shared seed10 gyro-noise prefix.',
        'source_sha256': started_code,
        'split_geometry_receipt_sha256': sha(out/'SPLIT_GEOMETRY_RECEIPT.json'), 'input_sources': sources, 'policies': policies}
    lock_path = out/'POLICY_LOCK.json'
    dump(lock_path, lock)
    lock_sha = sha(lock_path)
    print('POLICY_LOCK_WRITTEN', lock_sha, flush=True)
    heldout_rows = []
    for stratum in strata:
        for heldout in ROUTES:
            assert sha(lock_path) == lock_sha, 'POLICY_LOCK_CHANGED'
            truth = load_loss_truth(assets, heldout, joins[heldout])
            forecast = all_forecasts[stratum][heldout]
            chosen = policies[stratum][heldout]['selected_candidate']
            for name, role in ((chosen, 'LOCKED_SELECTED'), (diagnostic, 'FIXED_DIAGNOSTIC_ONLY')):
                selected = np.ones(len(truth), bool)
                q = aggregate_quality([sliced_chunk(forecast, truth, name, selected)])
                heldout_rows.append({'stratum': stratum, 'heldout': heldout, 'role': role, 'candidate': name, **flat_quality(q)})
            np.savez_compressed(out/f'{stratum}_{heldout}_SELECTED_WEIGHTS.npz',
                t=joins[heldout]['t'], pose_id=joins[heldout]['pose_id'], selected_beta=forecast['beta'][chosen],
                selected_reason=forecast['reasons'][chosen], diagnostic_beta=forecast['beta'][diagnostic],
                diagnostic_reason=forecast['reasons'][diagnostic], scores=forecast['scores'], valid=forecast['valid'],
                selected_candidate=chosen, diagnostic_candidate=diagnostic, policy_lock_sha256=lock_sha,
                legacy_accepted=forecast['mask'])
            del truth
    table(out/'HELDOUT_SELECTED_AND_DIAGNOSTIC.csv', heldout_rows)
    ended_code = {name: sha(Path(__file__).with_name(name)) for name in started_code}
    assert started_code == ended_code, 'CALIBRATION_CODE_CHANGED_DURING_RUN'
    report = {'status': 'COMPLETED_RESEARCH_CALIBRATION', 'policy_lock_sha256': lock_sha, 'strata': list(strata),
        'calibration_code_sha256_before': started_code, 'calibration_code_sha256_after': ended_code,
        'elapsed_s': time.time()-started, 'selected': {s: {r: policies[s][r]['selected_candidate'] for r in ROUTES} for s in strata},
        'utility_demonstrated_for_all_folds': all(policies[s][r]['selected_candidate'] != 'OFF' for s in strata for r in ROUTES),
        'closed_loop_performance_claim': False, 'independent_generalization_claim': False,
        'split_counts': split_receipt['folds'], 'heldout_comparisons': heldout_rows,
        'required_next': 'Own-state closed-loop replay and wrong-reference/recovery stress; OFF remains OFF if utility was not demonstrated.'}
    dump(out/'REPORT.json', report)
    print(json.dumps({'status': report['status'], 'selected': report['selected'], 'policy_lock_sha256': lock_sha}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--profilesdir', type=Path, required=True)
    p.add_argument('--archivesdir', type=Path, required=True)
    p.add_argument('--assetsdir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--strata', nargs='+', choices=STRATA, default=list(STRATA),
                   help='Explicit stage scope; default evaluates both strata with unchanged criteria.')
    a = p.parse_args()
    run(a.profilesdir, a.archivesdir, a.assetsdir, a.out, strata=a.strata)
