"""CI execution/parity gate for one route; success never means policy adoption.

The ACTIVE_RS arm is a predeclared tau=2 diagnostic even when an optional
calibration lock selects OFF. No parameter is fitted or chosen from CI metrics.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
import numpy as np
import experiment

ROUTE_N = {'R2': 979, 'R4': 742, 'R5': 1415}
MODES = ('OFF', 'ACTIVE_RS')
TAU = 2.
SPAN_S = 5.
POLICY_ROLE = 'predeclared_diagnostic'
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_object(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.part')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def code_hashes():
    return {name: sha(HERE/name) for name in ('mcg.py', 'experiment.py', 'ci_route.py')}


def protocol_for(route):
    cfg = experiment.config_for(tau=TAU, span=SPAN_S)
    return {'schema': 'B_MCG_CI_ROUTE_PROTOCOL_V1', 'route': route, 'expected_n': ROUTE_N[route],
        'strata': list(experiment.STRATA), 'arms': list(MODES), 'config': asdict(cfg),
        'config_sha256': cfg.digest(), 'active_role': POLICY_ROLE,
        'baseline': 'Original SourceFFD W0 replay agrees with archived B_FROZEN and existing B_BIAS_COV',
        'raw_legacy_gate': 'Identical to original per-stratum B shadow for OFF and ACTIVE_RS',
        'truth': 'experiment.active reads evaluator only after completing each online recursion',
        'new_parameter_training': False, 'production_activation': False,
        'execution_success_is_performance_adoption': False}


def verify_archive_members(archives, route):
    lock_path = HERE/'ARCHIVE_LOCK.json'
    lock = json.loads(lock_path.read_text())
    required = [f'{route}/{route}_{s}.npz' for s in experiment.STRATA]+[f'{route}/RESULTS.json']
    checked = {}
    for relative in required:
        expected = lock['files_sha256'][relative]
        actual = sha(archives/relative)
        assert actual == expected, ('ARCHIVE_MEMBER_SHA_MISMATCH', relative, actual, expected)
        checked[relative] = actual
    return {'archive_lock_sha256': sha(lock_path), 'members_sha256': checked}


def verify_numeric_trace(path, expected_n, legacy_mask):
    finite_keys = ('x', 'P', 'prior', 'Pprior', 'h', 'H', 'mu', 'Reff', 'Rbase', 'K', 'nu', 'S',
                   'beta', 'trial_delta', 'actual_delta', 'shadow_x', 'shadow_P', 'latency_ms', 'guard_ms', 'gate_nis', 'nis')
    with np.load(path, allow_pickle=False) as f:
        for key in finite_keys:
            assert len(f[key]) == expected_n, ('TRACE_LENGTH', key, len(f[key]), expected_n)
            assert np.isfinite(f[key]).all(), ('NONFINITE_TRACE', key)
        mask = f['mask']; used_r = f['used_r']; used_s = f['used_s']
        assert mask.shape == (expected_n,) and mask.dtype == np.dtype(bool)
        assert np.array_equal(mask, legacy_mask), 'RAW_B_LEGACY_MASK_CHANGED'
        assert not np.any((used_r | used_s) & ~mask), 'RESCUED_LEGACY_REJECTION'
        assert np.max(abs(f['K'][~used_r, :, 0]), initial=0.) < 1e-12
        assert np.max(abs(f['K'][~used_s, :, 1]), initial=0.) < 1e-12
        assert np.all((f['beta'] >= 0.) & (f['beta'] <= 1.)), 'INVALID_BETA'
        covariance_checks = {}
        for key in ('P', 'Pprior', 'shadow_P', 'Rbase', 'Reff', 'S'):
            value = f[key]
            symmetry = float(np.max(abs(value-value.swapaxes(-1, -2))))
            smallest = float(np.linalg.eigvalsh(value).min())
            assert symmetry <= 1e-10, ('ASYMMETRIC_COVARIANCE', key, symmetry)
            assert smallest >= -1e-12, ('NON_PSD_COVARIANCE', key, smallest)
            if key in ('Rbase', 'Reff', 'S'): assert smallest > 0., ('NON_PD_OBSERVATION_COVARIANCE', key)
            covariance_checks[key] = {'max_asymmetry': symmetry, 'minimum_eigenvalue': smallest}
        assert f['t'].shape == (expected_n,) and f['pose_id'].shape == (expected_n,)
        assert np.all(np.diff(f['t']) > 0.) and len(np.unique(f['pose_id'])) == expected_n
        result = {'status': 'PASS_NUMERICAL_AND_MASK_CHECKS', 'n': expected_n,
            'legacy_accepted_n': int(mask.sum()), 'guard_used_any_n': int((used_r | used_s).sum()),
            'legacy_mask_sha256': hashlib.sha256(np.ascontiguousarray(mask).tobytes()).hexdigest(),
            'covariances': covariance_checks,
            'diagnostic_nan_policy': 'Optional unresolved profile/theta/score diagnostics may be NaN; all actual state/update/covariance fields must be finite.'}
    return result


def append_step_summary(summary, failed=False):
    destination = os.environ.get('GITHUB_STEP_SUMMARY')
    if not destination:
        return
    lines = [f"## B-MCG {summary['route']}: {'execution failed' if failed else 'execution checks passed'}", '',
        '**A green execution result does not approve performance or production activation.**', '',
        'The active arm is the fixed, predeclared `ACTIVE_RS`, τ=2, 5 s diagnostic. No parameter is trained here.', '']
    if failed:
        lines += ['Failure: `'+summary.get('error_type', 'ERROR')+'` during `'+summary.get('phase', 'UNKNOWN')+'`.', '']
    else:
        lines += ['| Stratum | Arm | Rows | Heading RMSE (deg) | XY RMSE (cm) | Damped accepted |',
                  '| --- | --- | ---: | ---: | ---: | ---: |']
        for item in summary['runs']:
            m = item['metrics']
            lines.append(f"| {item['stratum']} | {item['mode']} | {m['n']} | {m['heading_rmse_deg']:.6f} | {m['xy_rmse_cm']:.6f} | {m['guard_damped_legacy_accepted']} |")
        lines += ['', 'Both baseline strata reproduce archived traces; OFF parity, raw legacy masks, finite states and PSD covariance checks pass.',
                  '', 'Performance and useful-update retention require the separate adversarial evaluation. The diagnostic remains diagnostic even if a policy lock selects OFF.', '']
    with Path(destination).open('a', encoding='utf-8') as f:
        f.write('\n'.join(lines)+'\n')


def run(route, archives, out, policy_lock=None):
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('NEW_CI_OUTPUT_REQUIRED: '+str(out))
    out.mkdir(parents=True, exist_ok=True)
    if policy_lock is not None and not policy_lock.is_file():
        raise FileNotFoundError('POLICY_LOCK_NOT_FOUND: '+str(policy_lock))
    before = code_hashes()
    contract_path = HERE/'EXPERIMENT_CONTRACT.json'
    contract_sha = sha(contract_path)
    protocol = protocol_for(route)
    cfg_hash = protocol['config_sha256']
    assert cfg_hash == hash_object(protocol['config']), 'PROTOCOL_CONFIG_DIGEST'
    policy_sha = sha(policy_lock) if policy_lock is not None else None
    record = {'route': route, 'status': 'RUNNING', 'phase': 'VERIFY_ARCHIVES',
        'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'execution_git_sha': os.environ.get('GITHUB_SHA', 'LOCAL'),
        'protocol': protocol, 'protocol_sha256': hash_object(protocol), 'protocol_config_sha256': cfg_hash,
        'experiment_contract_sha256': contract_sha, 'runtime_code_sha256_before': before,
        'policy_lock_sha256': policy_sha, 'policy_lock_path': str(policy_lock) if policy_lock is not None else None,
        'performance_adoption': 'NOT_AUTHORIZED_BY_CI_EXECUTION', 'production_activation': False, 'runs': []}
    dump(out/'CI_ROUTE_RUNNING.json', record)
    started = time.perf_counter()
    try:
        record['archive_receipt'] = verify_archive_members(archives, route)
        record['phase'] = 'BASELINE_SOURCE_PARITY'
        experiment.baseline(route, archives, out/'baseline')
        baseline_report = json.loads((out/'baseline'/f'{route}_PARITY.json').read_text())
        assert baseline_report['status'] == 'PASS' and set(baseline_report['strata']) == set(experiment.STRATA)
        assert max(float(v) for values in baseline_report['strata'].values() for v in values.values()) <= 1e-10
        record['baseline_parity'] = baseline_report
        for stratum in experiment.STRATA:
            with np.load(archives/route/f'{route}_{stratum}.npz', allow_pickle=False) as f:
                legacy_mask = f['mask']
            assert legacy_mask.shape == (ROUTE_N[route],)
            masks = {}
            for mode in MODES:
                record['phase'] = stratum+'_'+mode
                run_out = out/'active'/stratum/mode
                experiment.active(route, stratum, archives, run_out, mode, tau=TAU, span=SPAN_S,
                                  policy_role=POLICY_ROLE, policy_lock=policy_lock)
                meta_path = run_out/f'{route}_{mode}.json'
                trace_path = run_out/f'{route}_{mode}.npz'
                meta = json.loads(meta_path.read_text())
                assert meta['status'] == 'EXECUTED_RESEARCH_REPLAY'
                assert (meta['route'], meta['stratum'], meta['mode']) == (route, stratum, mode), 'REPLAY_METADATA_IDENTITY'
                assert meta['metrics']['n'] == ROUTE_N[route]
                assert meta['config_sha256'] == cfg_hash and hash_object(meta['config']) == cfg_hash
                assert meta['execution_policy_role'] == POLICY_ROLE
                assert meta['policy_lock_sha256'] == policy_sha, 'ACTIVE_POLICY_LOCK_RECEIPT'
                assert meta['runtime_code_sha256'] == {name: before[name] for name in ('mcg.py', 'experiment.py')}, 'ACTIVE_RUNTIME_VERSION_MISMATCH'
                assert sha(trace_path) == meta['trace_sha256'], 'TRACE_HASH_MISMATCH'
                numeric = verify_numeric_trace(trace_path, ROUTE_N[route], legacy_mask)
                masks[mode] = numeric['legacy_mask_sha256']
                if mode == 'OFF':
                    assert meta['OFF_parity'] is not None and max(meta['OFF_parity'].values()) <= 1e-10
                    assert meta['metrics']['guard_damped_legacy_accepted'] == 0
                record['runs'].append({'stratum': stratum, 'mode': mode, 'execution_policy_role': POLICY_ROLE,
                    'metadata_relative_path': str(meta_path.relative_to(out)), 'trace_relative_path': str(trace_path.relative_to(out)),
                    'metadata_sha256': sha(meta_path), 'trace_sha256': sha(trace_path),
                    'config_sha256': cfg_hash, 'policy_lock_sha256': policy_sha,
                    'OFF_parity': meta['OFF_parity'], 'metrics': meta['metrics'], 'numerical_checks': numeric})
                dump(out/'CI_ROUTE_PROGRESS.json', record)
            assert len(set(masks.values())) == 1, 'OFF_ACTIVE_RAW_LEGACY_GATE_DIFFERENCE'
        after = code_hashes()
        assert before == after, 'RUNTIME_CHANGED_DURING_CI_ROUTE'
        assert sha(contract_path) == contract_sha, 'EXPERIMENT_CONTRACT_CHANGED_DURING_RUN'
        if policy_lock is not None: assert sha(policy_lock) == policy_sha, 'POLICY_LOCK_CHANGED_DURING_RUN'
        assert len(record['runs']) == 4
        record.update(status='PASS_EXECUTION_PARITY_AND_NUMERICAL_CHECKS', phase='COMPLETE',
                      runtime_code_sha256_after=after, elapsed_s=time.perf_counter()-started,
                      ended_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        dump(out/'CI_ROUTE_SUMMARY.json', record)
        append_step_summary(record)
        print(json.dumps({'status': record['status'], 'route': route, 'n': ROUTE_N[route],
                          'runs': len(record['runs']), 'protocol_sha256': record['protocol_sha256'],
                          'performance_adoption': record['performance_adoption']}, indent=2), flush=True)
    except BaseException as e:
        record.update(status='FAILED_EXECUTION_OR_VALIDATION', error_type=type(e).__name__, error=str(e),
                      traceback=traceback.format_exc(), elapsed_s=time.perf_counter()-started,
                      runtime_code_sha256_after=code_hashes(), ended_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        dump(out/'CI_ROUTE_FAILURE.json', record)
        append_step_summary(record, failed=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', choices=tuple(ROUTE_N), required=True)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--policy-lock', type=Path)
    args = parser.parse_args()
    run(args.route, args.archives, args.out, args.policy_lock)
