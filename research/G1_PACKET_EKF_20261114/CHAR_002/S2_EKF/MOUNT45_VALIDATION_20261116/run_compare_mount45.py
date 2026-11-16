"""Freeze and run the original S2 arms plus prediction-only DR on B/B0 +45 degrees."""

import argparse
from pathlib import Path
import os
import platform
import sys

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[variable] = '1'

import numpy as np
import scipy


ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
PACKETS = WORK / 'artifacts/G1_CHAR002_S2_MOUNT45_20261116'
ORIGINAL = WORK / 'g1_char002_s2_ekf_20261115/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF'
S2_RUN = ORIGINAL / 'run_20261115_a'
TRAIN_CODE = WORK / ('artifacts/G1_CHAR002_S2_INPUTS_20261115/source_minimal/research/'
                     'G1_PACKET_EKF_20261114/CHAR_002/scripts/char2_fit_eval.py')
S2_SHA256 = 'f4870df1afe81e57cd99083229738d9f184b56dff697a02ff6a56cf0078906bf'
PACKET_PARITY_SHA256 = '3c715e06bd0b4e5a051cb7a712974e85854418d293174802e3369c1901d147d0'
HELPER_HASHES = {
    'compare_dr.py': '35a95a0d07d69e328a9da65db5d19e91168ec6e1d585bf983a66ea318b9d20e7',
    'verify_s2.py': '943ec22e5096a0edbae6933b973b700d141c2218768aba1b779e243843fccad0',
}
FAMILIES = {'E1': ('R1', 'S1'), 'E2': ('R2', 'S2'), 'E3': ('R2', 'S3'), 'E4': ('R2', 'S3')}
ARMS = ('E0', *FAMILIES, 'E5')
STATE_KEYS = ('prior', 'Pprior', 'h', 'H', 'K', 'Reff', 'mask', 'x', 'P')

sys.path.insert(0, str(PACKETS))
import prepare_mount45 as mount


def bind_inputs(args):
    original_contract = mount.checked(S2_RUN / 'RUN_CONTRACT.json', S2_SHA256)
    original = mount.load(original_contract)
    packet_contract = PACKETS / 'RUN_CONTRACT.json'
    parity_path = mount.checked(PACKETS / 'PARITY_RESULTS.json', PACKET_PARITY_SHA256)
    baseline = mount.load(parity_path)
    observer = mount.load(args.observer_results)
    fit_result = mount.load(args.fit_receipt)
    if baseline['status'] != 'PASS' or baseline['contract_sha256'] != mount.sha(packet_contract):
        raise ValueError('Missing +45 packet and E0 parity evidence')
    if observer['status'] != 'PASS' or observer['contract_sha256'] != mount.sha(args.observer_contract):
        raise ValueError('Stage 1 observer verification must pass first')
    if fit_result['status'] != 'PASS':
        raise ValueError('Stage 2 +45 training must pass first')
    fit_contract = mount.load(args.fit_contract)
    if fit_result['contract_sha256'] != mount.sha(args.fit_contract) or fit_contract['scope']['mount_deg'] != 45:
        raise ValueError('Stage 2 contract identity or mount mismatch')
    for path in (args.fit, args.yaw_fit):
        mount.checked(path, fit_result['outputs_sha256'][path.name])
    packet_snapshot = mount.load(packet_contract)
    scope = packet_snapshot['scope']
    if scope != {'anchor': 'B', 'bias': 'B0', 'mount_deg': 45, 'seed': 10, 'channel': 'Full', 'rows': mount.ROWS}:
        raise ValueError('Unexpected packet scope')
    if set(observer['routes']) != set(mount.ROWS) or set(baseline['routes']) != set(mount.ROWS):
        raise ValueError('Missing +45 packet or observer route')
    inputs = {path: mount.sha(path) for path in (Path(__file__), original_contract, packet_contract, parity_path,
              args.observer_contract, args.observer_results, args.fit_contract, args.fit_receipt, args.fit, args.yaw_fit)}
    for name, digest in original['s2_code_sha256'].items():
        inputs[S2_RUN / 'executed_source_2a_2b' / name] = digest
    for name, digest in HELPER_HASHES.items():
        inputs[ORIGINAL / name] = digest
    inputs[TRAIN_CODE] = original['s1_fit_code_sha256']
    inputs[Path(mount.__file__)] = baseline['source_sha256']['prepare_mount45.py']
    inputs.update({mount.NATIVE / name: digest for name, digest in baseline['source_sha256'].items() if '/' in name})
    inputs[mount.NATIVE / 'src/qclean_uwb/fp_sc/e0_baseline.py'] = packet_snapshot['inputs_sha256'][
        str(mount.NATIVE / 'src/qclean_uwb/fp_sc/e0_baseline.py')]
    for route, n in mount.ROWS.items():
        if baseline['routes'][route]['rows'] != n or observer['routes'][route]['status'] != 'PASS':
            raise ValueError(f'Bad route parity or observer receipt: {route}')
        for kind in ('online', 'evaluator', 'e0_trace'):
            path = PACKETS / f'{mount.stem(route)}__{kind}.npz'
            inputs[path] = baseline['routes'][route]['output_sha256'][path.name]
    for path, digest in inputs.items():
        mount.checked(path, digest)
    return scope, original, baseline, {str(path): digest for path, digest in inputs.items()}


def freeze(args):
    scope, original, baseline, inputs = bind_inputs(args)
    args.out.mkdir(parents=True)
    mount.write(args.out / 'RUN_CONTRACT.json', {
        'question': 'G1-CHAR002-S2-MOUNT45/CHECKLIST-03', 'role': 'IMPLEMENTER', 'frozen_utc': mount.utc(),
        'scope': scope, 'geometry': mount.SPEC, 's2_spec_commit': original['spec_commit'],
        'thresholds': original['thresholds'], 'gate': original['gate'], 'arms': original['arms'],
        'arm_eligibility': {'E3': 'S2 primary; fixed original S2 integrity criteria', 'E5': 'DIAGNOSTIC_ONLY'},
        'historical_m45_reference': baseline['historical_m45_reference'],
        'dr': 'Original prediction-only DR with identical ds, gy, dt, x0, bias=0, P0 and Q; no RF update',
        'input_files': {key: str(getattr(args, key)) for key in ('fit', 'yaw_fit', 'fit_contract', 'fit_receipt',
                         'observer_contract', 'observer_results')},
        'frozen_predictors': original['frozen_predictors'], 'student_t': original['student_t'],
        'yaw_state': original['yaw_state'], 'motion_labels': original['motion_labels'], 'bootstrap': original['bootstrap'],
        'distance_extrapolation_m': original['distance_extrapolation_m'], 'distance_mean': original['distance_mean'],
        'metric_pooling': 'Concatenate packet metrics. Pool end errors by RMS of the three route-end errors.',
        'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__},
        'governance': mount.load(args.observer_contract)['governance'], 'inputs_sha256': inputs,
    })


def end_metrics(rows):
    return {'heading_end_abs_deg': float(np.sqrt(rows[-1, 0])), 'xy_end_error_cm': float(np.sqrt(rows[-1, 1]))}


def run(args):
    frozen = args.out / 'RUN_CONTRACT.json'
    contract = mount.load(frozen)
    for path, digest in contract['inputs_sha256'].items():
        mount.checked(Path(path), digest)
    sys.path[:0] = [str(S2_RUN / 'executed_source_2a_2b'), str(ORIGINAL), str(mount.NATIVE / 'src')]
    from compare_dr import compare, replay_dr, verify_grid
    from metrics_s2 import Trace, _summarize, classify_motion, evaluate_stage
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from replay_s2 import D_MAX, b0_reference, geometry, learned_replay, parity, validate_trace
    from run_s2 import models, oracle_models
    from verify_s2 import check_dynamics, check_metric_rows, from_trace

    paths = {key: Path(path) for key, path in contract['input_files'].items()}
    learned = models(mount.load(paths['fit']))
    if set(learned) != {'R1', 'R2', 'S1', 'S2', 'S3'}:
        raise ValueError('Stage 2 did not produce all five frozen fit models')
    yawfit = mount.load(paths['yaw_fit'])
    if not 0 <= yawfit['correlated_share'] < 1 or not yawfit['ell_yaw_rad'] > 0:
        raise ValueError('E4 needs finite positive length and nonzero white scale')
    core, online, model, native_hashes = load_original_model(mount.NATIVE)
    for name, digest in native_hashes.items():
        if contract['inputs_sha256'][str(mount.NATIVE / name)] != digest:
            raise ValueError(f'Pinned native source mismatch: {name}')
    dest = args.out / 'execution'
    dest.mkdir()
    execution = {'command': [sys.executable, *sys.argv], 'contract_sha256': mount.sha(frozen),
                 'started_utc': mount.utc()}
    try:
        baselines = {}
        for route, expected in mount.ROWS.items():
            stem = PACKETS / mount.stem(route)
            packet = mount.npz(stem.with_name(f'{stem.name}__online.npz'))
            reference = mount.npz(stem.with_name(f'{stem.name}__e0_trace.npz'))
            verify_grid(packet, reference)
            if packet['z'].shape != (expected, 2) or np.any(np.diff(packet['t']) <= 0):
                raise ValueError(f'Unexpected packet shape or order: {route}')
            controls = mount.controls(packet)
            base = online.replay(packet, controls, 'W0', core, model, mount.SPEC)
            validate_trace(base)
            checks = parity(base, {field: reference[field] for field in STATE_KEYS})
            packed = parity(base, b0_reference(packet))
            baselines[route] = (packet, reference, controls, base, checks, packed)
        mount.write(dest / 'E0_PARITY.json', {
            'status': 'PASS', 'tolerance': contract['thresholds']['parity_normalized_tolerance'],
            'historical_m45_reference': contract['historical_m45_reference'], 'routes': {
                route: {'archived_e0_trace': checks, 'online_embedded_trace': packed,
                        'accepted': int(reference['mask'].sum()), 'rows': len(reference['mask'])}
                for route, (_, reference, _, _, checks, packed) in baselines.items()},
        })

        traces, row_sets, comparison, oracle = {}, {}, {}, {}
        s2_settings = contract['bootstrap']
        for route, (packet, reference, controls, base, _, _) in baselines.items():
            base['prior_range'], base['prior_bearing_deg'] = geometry(base['prior'], mount.SPEC)
            replay = {'E0': base}
            for arm, (r, s) in FAMILIES.items():
                replay[arm] = learned_replay(packet, controls, reference['mask'], core, online, model,
                                             mount.SPEC, arm, learned[r], learned[s], yawfit)
            dr, prior_delta = replay_dr(packet, base, core, online, mount.TOL)
            stem = PACKETS / mount.stem(route)
            evaluator = mount.npz(stem.with_name(f'{stem.name}__evaluator.npz'))
            verify_grid(packet, evaluator)
            truth = evaluator['truth']
            rfit, sfit, oracle[route] = oracle_models(truth, packet['z'], model, mount.SPEC, TRAIN_CODE)
            replay['E5'] = learned_replay(packet, controls, reference['mask'], core, online, model,
                                          mount.SPEC, 'E5', rfit, sfit, yawfit)
            motion = classify_motion(truth)
            grid = {key: packet[key] for key in ('pose_id', 't')}
            traces[route], rows = {}, {}
            for arm, result in replay.items():
                if not np.array_equal(result['mask'], reference['mask']):
                    raise ValueError(f'Fixed E0 gate mismatch: {route}/{arm}')
                result.update(**grid, motion=motion, extrapolated=result['prior_range'] > D_MAX)
                check_dynamics(result, route, arm, np.asarray(mount.SPEC['anchor']), yawfit)
                archive = dest / f'{route}_{arm}_trace.npz'
                mount.save_npz(archive, result)
                stored = mount.npz(archive)
                verify_grid(stored, evaluator)
                rows[arm] = from_trace(stored, truth)
                traces[route][arm] = Trace(stored['t'], stored['x'], stored['P'], truth, stored['extrapolated'],
                                          stored['prior_bearing_deg'], stored['motion'], stored['mask'])
            archive = dest / f'{route}_DR_trace.npz'
            mount.save_npz(archive, dr)
            dr = mount.npz(archive)
            verify_grid(dr, evaluator)
            rows['DR'] = from_trace(dr, truth)
            row_sets[route] = rows
            segment_metrics, changes = compare(rows, evaluator['t'], s2_settings)
            comparison[route] = {'metrics': segment_metrics, 'end_error': {arm: end_metrics(values) for arm, values in rows.items()},
                                 'rmse_vs_dr': changes, 'e0_prior_max_abs_delta': prior_delta}
            print(f'{route}: E0–E5 and DR replay/trace checks complete', flush=True)
        s2 = evaluate_stage(traces, expected_cases=tuple(mount.ROWS), bootstrap_seed=s2_settings['seed'])
        pooled_rows = {arm: np.concatenate([rows[arm] for rows in row_sets.values()]) for arm in (*ARMS, 'DR')}
        for arm in ARMS:
            check_metric_rows(pooled_rows[arm], s2['pooled'][arm])
            for route, rows in row_sets.items():
                check_metric_rows(rows[arm], s2['by_case'][route][arm])
        pooled_end = {arm: {key: float(np.sqrt(np.mean([row['end_error'][arm][key] ** 2 for row in comparison.values()])))
                            for key in ('heading_end_abs_deg', 'xy_end_error_cm')} for arm in pooled_rows}
        mount.write(dest / 'ORACLE_FIT_DIAGNOSTIC.json', {'status': 'DIAGNOSTIC_ONLY', 'routes': oracle})
        mount.write(dest / 'RESULTS.json', {**s2, 'by_route_dr_comparison': comparison,
                    'pooled_dr': _summarize(pooled_rows['DR']), 'pooled_end_error': pooled_end,
                    'e5_status': 'DIAGNOSTIC_ONLY'})
        execution.update(status='PASS_EXECUTION_AND_IMPLEMENTER_CHECK', exit_code=0)
    except Exception as error:
        execution.update(status='FAIL_EXECUTION', exit_code=1, error=str(error))
        raise
    finally:
        execution.update(finished_utc=mount.utc(), outputs_sha256={path.name: mount.sha(path) for path in dest.iterdir()})
        mount.write(dest / 'EXECUTION.json', execution)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_subparsers(dest='stage', required=True)
    prepare = stages.add_parser('freeze')
    for field in ('fit', 'yaw-fit', 'fit-contract', 'fit-receipt'):
        prepare.add_argument('--' + field, type=Path, required=True)
    prepare.add_argument('--observer-contract', type=Path, default=ROOT / 'OBSERVER_CONTRACT.json')
    prepare.add_argument('--observer-results', type=Path, default=ROOT / 'OBSERVER_RESULTS.json')
    for stage in (prepare, stages.add_parser('run')):
        stage.add_argument('--out', type=Path, default=ROOT / 'comparison')
    arguments = parser.parse_args()
    for name, value in vars(arguments).items():
        if isinstance(value, Path):
            setattr(arguments, name, value.resolve())
    {'freeze': freeze, 'run': run}[arguments.stage](arguments)
