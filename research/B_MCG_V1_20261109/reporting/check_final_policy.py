"""Independent array/formula audit. Does not import calibration or runtime code."""
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np

BASE = Path('/workspace/scratch/83f4844af087')
FINAL = BASE/'results/policy_calibration_final'
PRIMARY = BASE/'results/policy_primary_precheck'
PROFILES = BASE/'results/profiles_final'
ARCHIVES = BASE/'restored/fp-b-route-heldout-calibration-42483593407/tmp/fp-b-calibration'
ASSETS = BASE/'assets'
PACKAGE = BASE/'repo/research/B_MCG_V1_20261109'
ROUTES = ('R2', 'R4', 'R5')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def wrap(a):
    return (a+np.pi) % (2*np.pi)-np.pi


def load(p, keys):
    with np.load(p, allow_pickle=False) as f:
        return {k: f[k] for k in keys}


def stats(x, y):
    return np.column_stack((np.degrees(wrap(x[:, 2]-y[:, 2]))**2, ((x[:, :2]-y[:, :2])**2).sum(axis=1)))


def independent_betas(scores, valid, states, mode, tau):
    b = np.ones((len(scores), 2))
    bad = valid & (scores[:, :2] > tau)
    for c in range(2):
        if mode == 'ACTIVE_RS' or mode == ('ACTIVE_R' if c == 0 else 'ACTIVE_S'):
            which = bad[:, c]
            b[which, c] = np.maximum(.25, (tau/scores[which, c])**2)
    both = valid.all(axis=1) & ~bad.any(axis=1) & (scores[:, 2] > np.sqrt(2)*tau)
    if mode == 'ACTIVE_RS':
        b[both] = np.maximum(.25, (np.sqrt(2)*tau/scores[both, 2])**2)[:, None]
    b[states == 'INVALID'] = 0.
    return b


def independent_update(tr, beta):
    """Batched information application; no imported production adapter."""
    x = tr['prior'].copy()
    take = tr['mask'] & (beta > 0).all(axis=1)
    assert not np.any(tr['mask'] & ((beta > 0).sum(axis=1) == 1)), 'UNEXPECTED_ONE_CHANNEL_DROP_IN_GRID'
    h, p = tr['H'][take], tr['Pprior'][take]
    r = tr['Reff'][take].copy()
    r[:, 0, 0] /= beta[take, 0]
    r[:, 1, 1] /= beta[take, 1]
    hp = h@p
    cov = hp@h.swapaxes(1, 2)+r
    cov = (cov+cov.swapaxes(1, 2))*.5
    gain = np.linalg.solve(cov, hp).swapaxes(1, 2)
    x[take] += (gain@tr['nu'][take, :, None])[:, :, 0]
    x[take, 2] = wrap(x[take, 2])
    return x


def metric(full, skip, policy, masks, beta):
    q = {'n': len(full), 'actual_damping_n': int((masks & (beta < 1-1e-14).any(axis=1)).sum()), 'axes': {}}
    for j, name in enumerate(('heading_deg2', 'xy_m2')):
        good = skip[:, j] > full[:, j]
        den = float((skip[good, j]-full[good, j]).sum())
        lost = float(np.clip(policy[good, j]-full[good, j], 0, None).sum())
        base_sum = float(full[:, j].sum()); policy_sum = float(policy[:, j].sum())
        q['axes'][name] = {'baseline_loss_sum': base_sum, 'policy_loss_sum': policy_sum,
            'beneficial_gain_denominator': den, 'beneficial_lost_numerator': lost,
            'beneficial_full_update_n': int(good.sum()),
            'beneficial_lost_gain_ratio': lost/den if den > 0 else None,
            'net_saved_fraction': (base_sum-policy_sum)/base_sum if base_sum > 0 else None}
    q['eligible'] = bool(q['n'] and q['actual_damping_n'] and all(
        v['beneficial_gain_denominator'] > 0 and v['baseline_loss_sum'] > 0 and
        v['net_saved_fraction'] > 1e-12 and v['beneficial_lost_gain_ratio'] <= .05+1e-12 for v in q['axes'].values()))
    return q


def run():
    lock = json.loads((FINAL/'POLICY_LOCK.json').read_text())
    prior_lock = json.loads((PRIMARY/'POLICY_LOCK.json').read_text())
    report = json.loads((FINAL/'REPORT.json').read_text())
    sha_lock = sha(FINAL/'POLICY_LOCK.json')
    assert report['policy_lock_sha256'] == sha_lock
    assert lock['strata'] == ['B_FROZEN', 'B_BIAS_COV']
    checks = {'policy_report_lock_sha': True,
        'primary_policy_records_identical_to_primary_precheck': lock['policies']['B_FROZEN'] == prior_lock['policies']['B_FROZEN'],
        'primary_profile_receipts_identical_to_primary_precheck': lock['input_sources']['B_FROZEN'] == prior_lock['input_sources']['B_FROZEN'],
        'split_receipt_sha': sha(FINAL/'SPLIT_GEOMETRY_RECEIPT.json') == lock['split_geometry_receipt_sha256'],
        'source_start_end_equal': report['calibration_code_sha256_before'] == report['calibration_code_sha256_after'] == lock['source_sha256'],
        'current_source_matches_recorded': all(sha(PACKAGE/name) == digest for name, digest in lock['source_sha256'].items())}
    assert all(checks.values())
    geom = {}; noises = {}; near = {}; joins = {}
    release = json.loads((BASE/'repo/research/FP_NATIVE_B_CAUSAL_ABLATION_20261108/RELEASE_INPUT_LOCK.json').read_text())['files']
    input_hashes = {}
    for rec in release:
        if rec['asset_name'].endswith(('__online.npz', '__evaluator.npz')):
            p = ASSETS/rec['asset_name']; assert sha(p) == rec['sha256'] and p.stat().st_size == rec['size']
            input_hashes[rec['asset_name']] = rec['sha256']
    for route in ROUTES:
        g = load(ASSETS/f'{route}_B0_Full_10__evaluator.npz', ('truth', 't', 'pose_id'))
        on = load(ASSETS/f'{route}_B0_Full_10__online.npz', ('gy', 'dt', 't', 'pose_id'))
        assert np.array_equal(g['t'], on['t']) and np.array_equal(g['pose_id'], on['pose_id'])
        geom[route] = g
        noises[route] = (on['gy'][1:]-wrap(np.diff(g['truth'][:, 2])))/np.sqrt(on['dt'][1:])
        t = g['t']; cut = .6*(t[-1]-t[0])+t[0]
        full = (t >= t[0]+5-1e-9) & (t <= t[-1]-10+1e-9)
        joins[route] = {'train': full & (t < cut-10), 'dev': full & (t > cut+5),
            'supports': [np.flatnonzero((t >= at-5-1e-9) & (t <= at+10+1e-9)) for at in t]}
    # A separate direct pairwise implementation checks the tree-based splitter.
    for a in ROUTES:
        near[a] = {}
        for b in ROUTES:
            pa, pb = geom[a]['truth'], geom[b]['truth']
            dx = pa[:, None, 0]-pb[None, :, 0]; dy = pa[:, None, 1]-pb[None, :, 1]
            da = abs(wrap(pa[:, None, 2]-pb[None, :, 2]))
            near[a][b] = (dx*dx+dy*dy <= (.25+1e-12)**2) & (da <= np.radians(5)+1e-12)
    split_checks = {}; masks = {}
    with np.load(FINAL/'SPLIT_MASKS.npz', allow_pickle=False) as f:
        for heldout in ROUTES:
            training = [r for r in ROUTES if r != heldout]
            masks[heldout] = {}; split_checks[heldout] = {}
            unions = {}
            for part in ('train', 'dev'):
                unions[part] = {}
                for r in training:
                    used = np.zeros(len(geom[r]['t']), bool)
                    for k in np.flatnonzero(joins[r][part]): used[joins[r]['supports'][k]] = True
                    unions[part][r] = used
            for r in training:
                masks[heldout][r] = {}; split_checks[heldout][r] = {}
                for part in ('train', 'dev'):
                    opposite = 'dev' if part == 'train' else 'train'
                    bad_frame = near[r][heldout].any(axis=1)
                    for other in training:
                        bad_frame |= near[r][other][:, unions[opposite][other]].any(axis=1)
                    keep = joins[r][part].copy()
                    for k in np.flatnonzero(keep):
                        if bad_frame[joins[r]['supports'][k]].any(): keep[k] = False
                    archived = f[f'holdout_{heldout}__{r}__{part}']
                    assert np.array_equal(keep, archived), ('SPLIT_MASK_MISMATCH', heldout, r, part)
                    masks[heldout][r][part] = keep
                    split_checks[heldout][r][part] = {'n': int(keep.sum()), 'exact_mask_match': True}
    metric_max = 0.; state_max = 0.; candidate_parts = 0; decision_audit = {}; receipts = {}
    for stratum in lock['strata']:
        forecasts = {}; receipts[stratum] = {}
        for r in ROUTES:
            profile_path = PROFILES/stratum/(r+'.npz')
            tr_path = ARCHIVES/r/f'{r}_{stratum}.npz'
            recorded = lock['input_sources'][stratum][r]
            assert sha(profile_path) == recorded['profile_sha256'] and sha(tr_path) == recorded['trace_sha256']
            profile = load(profile_path, ('scores', 'valid', 'states', 't', 'pose_id', 'config_json'))
            assert np.array_equal(profile['t'], geom[r]['t']) and np.array_equal(profile['pose_id'], geom[r]['pose_id'])
            meta = json.loads((PROFILES/stratum/(r+'.json')).read_text())
            assert meta['status'] == 'OFFLINE_PROFILE_EXECUTED'
            assert meta['config_sha256'] == hashlib.sha256(json.dumps(json.loads(str(profile['config_json'])), sort_keys=True).encode()).hexdigest()
            assert all(sha(PACKAGE/n) == h for n, h in meta['runtime_code_sha256'].items())
            tr = load(tr_path, ('x', 'prior', 'Pprior', 'H', 'nu', 'Reff', 'mask'))
            full_x = independent_update(tr, np.ones((len(tr['x']), 2)))
            error = float(np.max(abs(full_x-tr['x']))); state_max = max(state_max, error); assert error < 1e-10
            forecasts[r] = {'full': stats(full_x, geom[r]['truth']), 'skip': stats(tr['prior'], geom[r]['truth']), 'mask': tr['mask'], 'candidates': {}}
            for name in lock['policies'][stratum]['R4']['candidate_train_dev']:
                mode, tau = name.split('_tau'); tau = float(tau.replace('p', '.'))
                beta = independent_betas(profile['scores'], profile['valid'], profile['states'], mode, tau)
                xx = independent_update(tr, beta)
                forecasts[r]['candidates'][name] = {'beta': beta, 'loss': stats(xx, geom[r]['truth'])}
            receipts[stratum][r] = {'profile_sha256': sha(profile_path), 'profile_metadata_sha256': sha(PROFILES/stratum/(r+'.json')), 'archive_sha256': sha(tr_path)}
        decision_audit[stratum] = {}
        for heldout in ROUTES:
            training = [r for r in ROUTES if r != heldout]
            fold = lock['policies'][stratum][heldout]
            complete = all(masks[heldout][r][p].any() for r in training for p in ('train', 'dev'))
            independently_eligible = []
            for name, metrics in fold['candidate_train_dev'].items():
                eligible = True
                for part in ('train', 'dev'):
                    cat = lambda field: np.concatenate([forecasts[r][field][masks[heldout][r][part]] for r in training])
                    pp = np.concatenate([forecasts[r]['candidates'][name]['loss'][masks[heldout][r][part]] for r in training])
                    bb = np.concatenate([forecasts[r]['candidates'][name]['beta'][masks[heldout][r][part]] for r in training])
                    calc = metric(cat('full'), cat('skip'), pp, cat('mask'), bb)
                    original = metrics[part]
                    assert calc['n'] == original['n'] and calc['actual_damping_n'] == original['actual_damping_n']
                    assert calc['eligible'] == original['eligible'], ('ELIGIBLE_DIFF', stratum, heldout, name, part)
                    for axis, values in calc['axes'].items():
                        for key, value in values.items():
                            other = original['axes'][axis][key]
                            if value is None: assert other is None
                            else:
                                error = abs(value-other)/max(1., abs(other)); metric_max = max(metric_max, error)
                                assert error < 1e-10, ('METRIC_DIFF', stratum, heldout, name, part, axis, key, value, other)
                    eligible &= calc['eligible']; candidate_parts += 1
                if complete and eligible: independently_eligible.append(name)
            assert independently_eligible == fold['eligible_candidates'] == []
            assert fold['selected_candidate'] == 'OFF' and fold['mode'] == 'OFF'
            with np.load(FINAL/f'{stratum}_{heldout}_SELECTED_WEIGHTS.npz', allow_pickle=False) as f:
                assert np.array_equal(f['selected_beta'], np.ones((len(geom[heldout]['t']), 2)))
                assert str(f['policy_lock_sha256']) == sha_lock
            decision_audit[stratum][heldout] = {'selected': 'OFF', 'independently_eligible_candidates': [],
                'complete_requested_support': bool(complete), 'recorded_block_reason': fold['selection_block_reason']}
    shared_noise = {}
    for a, b in itertools.combinations(ROUTES, 2):
        n = min(len(noises[a]), len(noises[b])); aa, bb = noises[a][:n], noises[b][:n]
        shared_noise[a+'_'+b] = {'n': n, 'maxabs_difference': float(np.max(abs(aa-bb))), 'correlation': float(np.corrcoef(aa, bb)[0, 1])}
    secondary = {}
    for heldout in ROUTES:
        secondary[heldout] = {r: {'historical_fit_routes': json.loads((ARCHIVES/r/'RESULTS.json').read_text())['fit']['train_routes'],
            'includes_guard_heldout': heldout in json.loads((ARCHIVES/r/'RESULTS.json').read_text())['fit']['train_routes']} for r in ROUTES if r != heldout}
    result = {'status': 'PASS_INDEPENDENT_FORMULA_AND_SPLIT_RECOMPUTATION',
        'review_method': 'Separate direct pairwise geometry and batched Kalman algebra; neither calibrate_policy nor mcg imported. Same collaborative implementation team, not external certification.',
        'policy_lock_sha256': sha_lock, 'checks': checks, 'split_recomputation': split_checks, 'decisions': decision_audit,
        'candidate_partition_aggregates_recomputed': candidate_parts, 'max_normalized_metric_difference': metric_max,
        'max_same_prior_state_difference': state_max, 'profile_receipts': receipts, 'input_hashes': input_hashes,
        'shared_noise_prefix': shared_noise, 'secondary_not_nested_holdout': secondary,
        'limitations': ['Heldout truth geometry was accessed by the offline splitter before policy lock; runtime never receives it. Do not claim globally zero heldout-truth access before lock.',
            'All route profiles share the seed10 gyro-noise prefix; chronological purge does not create new sensor realizations.',
            'Secondary historical B_BIAS_COV training includes the guard-heldout route through other-route fits; this remains sensitivity only.',
            'OFF preserves the baseline. It is not evidence of a successful active guard.',
            'Same-prior utility checks do not replace recursive performance or clean-recovery evaluation.']}
    (BASE/'review/FINAL_POLICY_INDEPENDENT_CHECK.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    print(json.dumps({'status': result['status'], 'candidate_partition_aggregates_recomputed': candidate_parts,
                      'max_normalized_metric_difference': metric_max, 'max_same_prior_state_difference': state_max,
                      'policy_lock_sha256': sha_lock}, indent=2))


if __name__ == '__main__': run()
