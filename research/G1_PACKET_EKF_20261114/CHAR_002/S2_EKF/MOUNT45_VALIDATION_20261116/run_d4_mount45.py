"""Run frozen D4 residual and HGB support diagnostics on the +45° B/B0 grid."""

import argparse
import csv
import os
from pathlib import Path
import sys

for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'

import numpy as np

from run_diag_mount45 import OUT as DIAGNOSTICS, DIAG, LOCK as DIAG_LOCK, PACKET_ROOT, ROOT, ROUTES, STUDY, source


OUT = ROOT / 'd4'
LOCK = OUT / 'RUN_CONTRACT.json'
ORIGINAL = DIAG / 'continuation_d4'
STRUCTURE = ROOT / 'structure'
ORIGINAL_LOCK_SHA256 = '4610582a9e858878bfbd205a544e631099125f83736c6a6dc3c8459ebc0d9e2e'
PACKET_LOCK_SHA256 = '00ae740057888859394da1795c8b6bfd45d0517046a45d274b3aa523af28c94b'
PARITY_SHA256 = '3c715e06bd0b4e5a051cb7a712974e85854418d293174802e3369c1901d147d0'
CALIBRATION_PARITY_SHA256 = '81f2ecfc69b0fa6da9d5615032d353205681115eec45c903e09b94fe996220f8'

sys.path.insert(0, str(ORIGINAL))


def bind_execution(contract, directory, contract_hash_key):
    result = directory / 'EXECUTION.json'
    report = source.load(result)
    if (report['status'] != 'PASS_EXECUTION' or report['exit_code'] != 0
            or report[contract_hash_key] != source.sha(contract)):
        raise ValueError(f'D4 prerequisite failed: {result}')
    return result, report['outputs']


def freeze():
    inputs = {}

    def bind(path, expected=None):
        path = Path(path)
        digest = source.sha(path)
        if expected is not None and digest != expected:
            raise ValueError(f'D4 input identity mismatch: {path}')
        inputs[str(path)] = digest
        return path

    template_path = bind(ORIGINAL / 'RUN_CONTRACT_RETRY_02.json', ORIGINAL_LOCK_SHA256)
    template = source.load(template_path)
    for name in ('run_d4.py', 'feature_d4.py', 'residual_d4.py', 'replay_s2.py'):
        [item] = [row for row in template['sources'] if Path(row['path']).name == name]
        bind(item['path'], item['sha256'])
    from feature_d4 import FEATURES
    from residual_d4 import D4_THRESHOLDS

    if template['thresholds'] != D4_THRESHOLDS or template['feature_assessment']['columns'] != list(FEATURES):
        raise ValueError('Original D4 thresholds or HGB feature list changed')
    feature = template['feature_assessment']
    for item in (feature['x1_input_lock'], *(feature['sources'][key] for key in ('feature_csv', 'series_dump', 'mu_recursive'))):
        bind(item['path'], item['sha256'])
    for row in feature['source_cases'].values():
        for key in ('samples', 'full_rf'):
            bind(row[key]['path'], row[key]['sha256'])

    packet_lock = bind(PACKET_ROOT / 'RUN_CONTRACT.json', PACKET_LOCK_SHA256)
    packet_contract = source.load(packet_lock)
    parity_path = bind(PACKET_ROOT / 'PARITY_RESULTS.json', PARITY_SHA256)
    parity = source.load(parity_path)
    cal_parity_path = bind(PACKET_ROOT / 'CALIBRATION_PARITY.json', CALIBRATION_PARITY_SHA256)
    cal_parity = source.load(cal_parity_path)
    if (parity['status'] != 'PASS' or cal_parity['status'] != 'PASS' or cal_parity['contract_sha256'] != source.sha(packet_lock)
            or parity['calibration_receipt_sha256'] != source.sha(cal_parity_path)):
        raise ValueError('Frozen +45 packet or calibration receipt is inconsistent')
    model_path = bind(PACKET_ROOT / 'CALIBRATION_MODEL_LOCK.json', cal_parity['model_lock_sha256'])
    model_lock = source.load(model_path)
    if model_lock['parent_contract_sha256'] != source.sha(packet_lock) or cal_parity['hgb']['feature_columns'] != list(FEATURES):
        raise ValueError('Frozen +45 calibration model or feature schema mismatch')
    bind(PACKET_ROOT / 'calibration.py', cal_parity['source_sha256'])
    bind(PACKET_ROOT / 'prepare_mount45.py', parity['source_sha256']['prepare_mount45.py'])
    for name, digest in parity['source_sha256'].items():
        if '/' in name:
            bind(source.NATIVE / name, digest)
    locked = packet_contract['inputs_sha256']
    for name in ('freqs_hz.npy', 'features.py', 'experiment.py', 'n4b_rf_errors.py', 'e0_baseline.py'):
        [path] = [path for path in locked if Path(path).name == name]
        bind(path, locked[path])

    diag = source.load(bind(DIAG_LOCK))
    if diag['scope'] != {'anchor': 'B', 'bias': 'B0', 'mount_deg': 45, 'seed': 10, 'n_expected': len(ROUTES)}:
        raise ValueError('Unexpected diagnostic scope')
    bind(STRUCTURE / 'RUN_CONTRACT.json')
    struct, sc_files = bind_execution(STRUCTURE / 'RUN_CONTRACT.json', STRUCTURE / 'execution', 'contract_sha256')
    d0, d0_files = bind_execution(DIAG_LOCK, DIAGNOSTICS / 'd0', 'run_contract_sha256')
    d2, d2_files = bind_execution(DIAG_LOCK, DIAGNOSTICS / 'd2', 'run_contract_sha256')
    for path in (struct, d0, d2, Path(__file__), ROOT / 'run_diag_mount45.py', ROOT / 'check_observer.py'):
        bind(path)
    bind(STRUCTURE / 'execution/RESULTS.json', sc_files['RESULTS.json'])
    d0_scores = bind(DIAGNOSTICS / 'd0/RESULTS.json', d0_files['RESULTS.json'])
    cells = {}
    for route in ROUTES:
        key = f'B_B0_{route}'
        cell = {}
        for kind in ('online', 'evaluator'):
            path = PACKET_ROOT / f'{source.stem(route)}__{kind}.npz'
            cell[kind] = str(bind(path, parity['routes'][route]['output_sha256'][path.name]))
        for kind, assets in (('d0', d0_files), ('d2', d2_files)):
            name = f'{key}.npz'
            cell[kind] = str(bind(DIAGNOSTICS / kind / name, assets[name]))
        frozen = model_lock['models'][route]
        cell['model'] = str(bind(PACKET_ROOT / frozen['file'], frozen['sha256']))
        cell['training_n'] = frozen['training_lock']['n']
        cell['calibration_training_counts'] = cal_parity['routes'][route]['donor_cases_hgb']
        cells[route] = cell
    OUT.mkdir()
    source.write(LOCK, {
        'question': 'G1-INT-DIAG-001/M45/D4', 'classification': 'DIAGNOSTIC_ONLY', 'role': 'IMPLEMENTER',
        'frozen_utc': source.utc(), 'scope': diag['scope'], 'geometry': source.SPEC, 'thresholds': D4_THRESHOLDS,
        'range_primary': template['range_primary'], 'range_sensitivity': template['range_sensitivity'],
        'residual': template['residual'], 'R_eff': template['R_eff'], 'autocorrelation': template['autocorrelation'],
        'boundary': 'H3 mean residual and historical HGB marginal feature support on +45 B/B0 seed 10.',
        'feature_config': {key: feature[key] for key in ('source_commit', 'sources', 'source_cases', 'columns', 'target',
                           'training_rule', 'quantile_probabilities', 'quantile_method')},
        'feature_model_commit': model_lock['commit'], 'feature_runtime': cal_parity['runtime']['sklearn'],
        'd0_scores': str(d0_scores), 'cells': cells, 'inputs_sha256': inputs,
    })


def load_cases(lock, model):
    from replay_s2 import parity, validate_trace

    score = source.load(Path(lock['d0_scores']))['by_cell']
    spec = lock['geometry']
    cases, checks, packets = [], {}, {}
    for route, payload in lock['cells'].items():
        packet, evaluator, d0, d2 = (source.npz(Path(payload[name])) for name in ('online', 'evaluator', 'd0', 'd2'))
        for row in (evaluator, d0, d2):
            if any(not np.array_equal(row[key], packet[key]) for key in ('pose_id', 't')):
                raise ValueError(f'D4 packet grid mismatch: {route}')
        validate_trace(d0)
        truth = evaluator['truth']
        nominal, _ = model.batch(np.column_stack((truth, np.zeros(len(truth)))), spec, gradient=False)
        epsilon = packet['z'] - nominal - packet['muMB']
        checks[route] = parity({'epsilon': epsilon, 'mask': d0['mask']},
                               {'epsilon': d2['truth_residual_r_s'], 'mask': d2['mask']})
        rho = np.linalg.norm(truth[:, :2] - np.array(spec['anchor'][:2]), axis=1)
        slant = np.hypot(rho, spec['anchor'][2] - spec['robot_z_m'])
        cases.append({'anchor': 'B', 'bias': 'B0', 'route': route, 't': packet['t'], 'pose_id': packet['pose_id'],
                      'rho': rho, 'slant': slant, 'epsilon': epsilon, 'mask': d0['mask'],
                      'R_eff_diagonal': d0['Reff'].diagonal(axis1=1, axis2=2),
                      'reference_metrics': score[f'B_B0_{route}']['e0']})
        packets[route] = packet
    return cases, checks, packets


def analyze_features(lock, packets):
    import pandas as pd
    sys.path.insert(0, str(PACKET_ROOT / 'runtime_sk172'))
    import joblib
    import sklearn
    from calibration import historical_modules, series
    from feature_d4 import CASES, FEATURES, FEATURES_EXIST, _feature_source, _taps_function, feature_support

    if sklearn.__version__ != lock['feature_runtime']:
        raise ValueError(f'Expected scikit-learn {lock["feature_runtime"]}, found {sklearn.__version__}')
    config = lock['feature_config']
    if config['columns'] != list(FEATURES) or config['quantile_probabilities'] != [0.05, 0.95] or config['quantile_method'] != 'linear':
        raise ValueError('D4 feature contract drift')
    cols = ['case', 'channel', 'pose_id', 's_fp', 'range_m', 'e_r', *FEATURES_EXIST]
    frame = pd.read_csv(config['sources']['feature_csv']['path'], usecols=cols)
    taps = _taps_function(config)
    history = {case: _feature_source(config, case, frame, taps) for case in CASES}
    training = {route: np.concatenate([history[c]['x'] for c in CASES if config['source_cases'][c]['route'] == route])
                for route in ROUTES}
    hist, extract, _, _ = historical_modules()
    freq = np.load(source.BLOCK / 'freqs_hz.npy', allow_pickle=False)
    if list(FEATURES) != hist.EXIST + hist.DS:
        raise ValueError('Historical calibration and D4 feature order mismatch')
    evaluation = []
    for route, packet in packets.items():
        payload = lock['cells'][route]
        counts = {case: len(raw['x']) for case, raw in history.items() if config['source_cases'][case]['route'] != route}
        if payload['calibration_training_counts'] != counts or payload['training_n'] != sum(counts.values()):
            raise ValueError(f'D4 historical HGB donor membership mismatch: {route}')
        feature = series(packet['Hrf'], lambda h: extract(h, freq), 64)
        late = series(packet['Hrf'], hist.taps, 128)
        if not feature['valid'].all() or np.max(np.abs(late['s_fp_chk'] - feature['s_fp'])) >= 1e-9:
            raise ValueError(f'D4 historical feature reconstruction mismatch: {route}')
        matrix = pd.DataFrame({col: feature[col] if col in FEATURES_EXIST else late[col] for col in FEATURES})
        model = joblib.load(payload['model'])
        if list(model.feature_names_in_) != list(FEATURES):
            raise ValueError(f'D4 model feature schema mismatch: {route}')
        reconstructed = {'z': np.column_stack((feature['range_m'], feature['s_fp'])), 'mu_r': model.predict(matrix)}
        parity = source.evaluate_parity({'z': packet['z'], 'mu_r': packet['muMB'][:, 0]}, reconstructed)
        evaluation.append({'anchor': 'B', 'bias': 'B0', 'route': route, 'case': f'{route}_aB_m45',
                           'features': matrix.to_numpy(float), 'parity': parity})
    return {'status': 'FEATURE_SUPPORT_VERIFIED', 'runtime': sklearn.__version__, 'tolerance': source.TOL,
            'columns': list(FEATURES), 'historical_arm': 'MU_R_EXDS distance correction (X1 MB)',
            'quantile_probabilities': config['quantile_probabilities'], 'quantile_method': config['quantile_method'],
            'training_rule': config['training_rule'],
            'source_full_cases': {case: {'n': len(row['ids']), 's_fp_max_error': row['s_fp_max_error']}
                                  for case, row in history.items()}, **feature_support(training, evaluation)}


def feature_csv(path, scores):
    rows = []
    for case in scores['cells']:
        train = scores['folds'][case['route']]['columns']
        for name, column in case['columns'].items():
            limits = train[name]
            rows.append({'anchor': case['anchor'], 'bias': case['bias'], 'held_out_route': case['route'], 'feature': name,
                         'train_p05': limits['p05'], 'train_p95': limits['p95'], 'train_finite_n': limits['finite_n'],
                         'train_missing_n': limits['nan_n'], 'evaluated_n': case['n'], 'evaluated_finite_n': column['finite_n'],
                         'evaluated_missing_n': column['nan_n'], 'below_p05_n': column['below_n'], 'above_p95_n': column['above_n'],
                         'outside_n': column['outside_n'], 'outside_fraction_all': column['outside_fraction_all'],
                         'outside_fraction_finite': column['outside_fraction_finite']})
    if len(rows) != len(ROUTES) * len(scores['columns']):
        raise ValueError('Incomplete D4 feature table')
    with path.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run():
    lock = source.load(LOCK)
    for path, digest in lock['inputs_sha256'].items():
        source.checked(Path(path), digest)
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from residual_d4 import D4_THRESHOLDS, analyze, synthetic_checks
    from run_d4 import save_table

    if lock['thresholds'] != D4_THRESHOLDS:
        raise ValueError('D4 threshold drift')
    destination = OUT / 'execution'
    destination.mkdir()
    receipt = {'started_utc': source.utc(), 'contract_sha256': source.sha(LOCK), 'command': [sys.executable, *sys.argv]}
    try:
        _, _, model, native = load_original_model(source.NATIVE)
        receipt['native_hashes'] = native
        cases, checks, packets = load_cases(lock, model)
        primary = analyze(cases)
        slant = analyze([case | {'rho': case['slant']} for case in cases])
        feature = analyze_features(lock, packets)
        save_table(destination / 'RESIDUAL_BINS.csv', primary, slant)
        feature_csv(destination / 'HGB_FEATURE_RATES.csv', feature)
        source.write(destination / 'HGB_FEATURE_SUPPORT.json', feature)
        source.write(destination / 'CHECKS.json', {'synthetic': synthetic_checks(), 'D2_reconstruction_and_mask_parity': checks})
        source.write(destination / 'RESULTS.json', {'question': lock['question'], 'classification': lock['classification'],
                     'horizontal': primary, 'slant_sensitivity': slant, 'HGB_feature_support': 'HGB_FEATURE_SUPPORT.json',
                     'HGB_feature_table': 'HGB_FEATURE_RATES.csv', 'claim_boundary': lock['boundary']})
        receipt.update(status='PASS_EXECUTION', exit_code=0)
    except Exception as error:
        receipt.update(status='FAIL_EXECUTION', exit_code=1, error=str(error))
        raise
    finally:
        receipt.update(finished_utc=source.utc(), outputs={p.name: source.sha(p) for p in destination.iterdir() if p.is_file()})
        source.write(destination / 'EXECUTION.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
