"""Recover and assess the actual leave-one-route-out MU_R_EXDS feature support."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np


WORKSPACE = Path(__file__).resolve().parents[3]
X1_REPO = WORKSPACE / 'DS_X1_X2_RESULTS_COMMIT_20261026'
X1_COMMIT = '37c9b555e8d86a749bd3ce92e1c45e7da74a4a35'
X1_DIR = X1_REPO / 'research/DS_MASK_CAUSAL_X1_X2_20261026/x1'
X1_LOCK_SHA = '9ed7161e0c68ce11ee50a6287db40ad5800a1bf7a8006ac503a968e4551390e9'
SOURCE_COMMIT = '902ddcaf0f8e59734bb8026d3bcdc36eab506a27'
CASES = ('R2_aA_m0', 'R2_aB_m0', 'R2_aA_m45', 'R4_aA_m0', 'R4_aB_m0', 'R5_aA_m0', 'R5_aB_m0')
ROUTES = ('R2', 'R4', 'R5')
FEATURES_EXIST = ('log_fp_power', 'abs_s_fp', 'early4', 'early8', 'early16', 'delay_rms_ns', 'peak_diff_ns',
                  'eta_fp_win80', 's_diff4', 's_diff8', 's_diff16', 'tap_pol_var80', 'jones_diversity',
                  'freq_s_var', 'detector_s_span', 'detector_delay_span_ns')
OFFSETS = (-8, -4, -2, -1, 1, 2, 4, 8)
FEATURES = FEATURES_EXIST + tuple(f'ds_{offset:+d}' for offset in OFFSETS)
TOL = 1e-10


def _verify(entry):
    path = Path(entry['path'])
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != entry['sha256'] or ('bytes' in entry and path.stat().st_size != entry['bytes']):
        raise ValueError(f'D4 feature input hash or size mismatch: {path}')
    return path


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def feature_inputs():
    """Find the exact source inventory, without computing any diagnostic statistics."""
    input_lock = {'path': str(X1_DIR / 'INPUT_LOCK.json'), 'sha256': X1_LOCK_SHA}
    upstream = _json(_verify(input_lock))
    if upstream['source_commit'] != SOURCE_COMMIT:
        raise ValueError('D4 unexpected MU_R_EXDS source commit')
    upstream_files = {Path(row['path']): row for row in upstream['files']}

    def unique(name):
        rows = [row for path, row in upstream_files.items() if path.name == name]
        if len(rows) != 1:
            raise ValueError(f'D4 expected one locked source entry for {name}')
        return rows[0]

    manifest = unique('P0_INPUT_MANIFEST.json')
    manifest_path = _verify(manifest)
    source_root = manifest_path.parents[2]
    sources = {'manifest': manifest, 'feature_csv': unique('OBSERVATION_FEATURES_LABELS.csv.gz'),
               'mu_recursive': unique('mu_recursive.py'), 'series_dump': unique('series_dump.py'),
               'mr_series': unique('MR_SERIES.csv.gz'),
               'x1_stage': {'path': str(X1_DIR / 'run_stage.py'), 'sha256': upstream['script_sha256']}}
    definitions = _json(manifest_path)['cases']
    if tuple(case['id'] for case in definitions) != CASES:
        raise ValueError('D4 training manifest differs from the original seven Full conditions')
    source_cases = {case['id']: {'route': case['route'],
                                'samples': upstream_files[source_root / case['samples_path']],
                                'full_rf': upstream_files[source_root / case['full_path']]} for case in definitions}
    traces = {}
    for case in CASES:
        if not case.endswith('m0'):
            continue
        for bias in ('B0', 'L2'):
            key = f'{case}_{bias}'
            path = X1_DIR / 'x1' / f'{key}.npz'
            spec = f'{X1_COMMIT}:{path.relative_to(X1_REPO).as_posix()}'
            pointer = subprocess.check_output(['git', '-C', str(X1_REPO), 'show', spec], text=True).splitlines()
            header, oid, size = pointer
            if header != 'version https://git-lfs.github.com/spec/v1' or not oid.startswith('oid sha256:'):
                raise ValueError(f'D4 X1 MB trace lacks a locked Git LFS digest: {path}')
            traces[key] = {'path': str(path), 'sha256': oid.removeprefix('oid sha256:'),
                           'bytes': int(size.removeprefix('size '))}
    authenticated = [input_lock, *sources.values(), *traces.values()]
    authenticated.extend(entry for case in source_cases.values() for entry in (case['samples'], case['full_rf']))
    for entry in authenticated:
        _verify(entry)
    return {'status': 'FEATURE_INPUTS_AVAILABLE', 'source_commit': SOURCE_COMMIT, 'x1_evidence_commit': X1_COMMIT,
            'x1_input_lock': input_lock, 'sources': sources, 'source_cases': source_cases,
            'x1_traces': traces, 'frozen_files': authenticated, 'columns': list(FEATURES),
            'target': 'e_r', 'arm': 'MU_R_EXDS', 'training_rule': 'all Full rows with route != held-out route',
            'quantile_probabilities': [0.05, 0.95], 'quantile_method': 'linear',
            'evaluation_scope': 'mount 0, A/B, B0/L2 with exact pose/time and numerical observation/MB mean parity'}


def _named_value(tree, name):
    [node] = [node for node in tree.body if isinstance(node, ast.Assign) and
              any(isinstance(key, ast.Name) and key.id == name for key in node.targets)]
    return ast.literal_eval(node.value)


def _taps_function(config):
    paths = config['sources']
    mean_code = ast.parse(Path(paths['mu_recursive']['path']).read_text(encoding='utf-8-sig'))
    taps_code = ast.parse(Path(paths['series_dump']['path']).read_text(encoding='utf-8-sig'))
    if tuple(_named_value(mean_code, 'EXIST')) != FEATURES_EXIST or tuple(_named_value(taps_code, 'OFFS')) != OFFSETS:
        raise ValueError('D4 HGB actual feature schema differs from frozen inputs')
    [body] = [node for node in taps_code.body if isinstance(node, ast.FunctionDef) and node.name == 'taps']
    namespace = {'np': np, 'OFFS': list(OFFSETS)}
    # Load only the verified pure function. Source-module imports set global runtime paths.
    exec(compile(ast.Module(body=[body], type_ignores=[]), paths['series_dump']['path'], 'exec'), namespace)
    return namespace['taps']


def _feature_source(config, case, frame, taps):
    row = config['source_cases'][case]
    ids = np.asarray([sample['pose_id'] for sample in _json(row['samples']['path'])], dtype=int)
    H = np.load(row['full_rf']['path'], allow_pickle=False, mmap_mode='r')
    if len(H) != len(ids) or len(np.unique(ids)) != len(ids):
        raise ValueError(f'D4 raw H does not align with unique source pose IDs: {case}')
    d = frame[(frame.case == case) & (frame.channel == 'full')].set_index('pose_id', verify_integrity=True).loc[ids]
    reconstructed = [taps(np.asarray(H[start:start + 128, :, :, 0])) for start in range(0, len(H), 128)]
    fp = np.concatenate([batch['s_fp_chk'] for batch in reconstructed])
    fp_error = float(np.max(np.abs(fp - d['s_fp'].to_numpy(float))))
    if not np.isfinite(fp_error) or fp_error >= 1e-9:
        raise ValueError(f'D4 first tap mismatch with historical feature table: {case}: {fp_error}')
    late = np.column_stack([np.concatenate([batch[col] for batch in reconstructed]) for col in FEATURES[len(FEATURES_EXIST):]])
    return {'ids': ids, 'x': np.column_stack((d[list(FEATURES_EXIST)].to_numpy(float), late)),
            'z': d[['range_m', 's_fp']].to_numpy(float), 'target': d['e_r'].to_numpy(float), 's_fp_max_error': fp_error}


def _maximum_absolute_difference(a, b):
    if a.shape != b.shape or not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError('D4 source parity arrays differ in shape or have nonfinite values')
    return float(np.max(np.abs(a - b)))


def _evaluation_record(cell, config, raw, mr_series):
    anchor, bias, route = (cell[key] for key in ('anchor', 'bias', 'route'))
    case = f'{route}_a{anchor}_m0'
    label = f'{case}_{bias}'
    source = raw[case]
    with np.load(_verify(cell['online']), allow_pickle=False) as stage, np.load(config['x1_traces'][label]['path'], allow_pickle=False) as x1:
        ids = stage['pose_id']
        if not np.array_equal(ids, x1['pose_id']) or not np.array_equal(stage['t'], x1['t_s']):
            raise ValueError(f'D4 Stage 2 and archived X1 grid mismatch: {label}')
        index = {int(pid): i for i, pid in enumerate(source['ids'])}
        order = [index[int(pid)] for pid in ids]
        [arm] = np.flatnonzero(x1['names'] == 'MB')
        original = mr_series[(mr_series.case == case) & (mr_series.bias == bias) & (mr_series.channel == 'full')]
        original = original.set_index('pose_id', verify_integrity=True).loc[ids]
        if not np.array_equal(original['t_s'].to_numpy(float), x1['t_s']):
            raise ValueError(f'D4 MR (mean predictor archive) and X1 time mismatch: {label}')
        historical_prediction = source['target'][order] - original['MU_R_EXDS__meas_r_cm'].to_numpy(float) / 100.0
        errors = {'stage2_z_vs_x1': _maximum_absolute_difference(stage['z'], x1['z']),
                  'stage2_muMB_vs_x1_MB': _maximum_absolute_difference(stage['muMB'], x1['mu'][:, arm]),
                  'x1_z_vs_training_table_observation': _maximum_absolute_difference(x1['z'], source['z'][order]),
                  'x1_mu_range_vs_archived_MU_R_EXDS': _maximum_absolute_difference(x1['mu'][:, arm, 0], historical_prediction)}
        if max(errors.values()) > TOL:
            raise ValueError(f'D4 feature evidence does not bind to Stage 2: {label}: {errors}')
    return {'anchor': anchor, 'bias': bias, 'route': route, 'case': case, 'features': source['x'][order],
            'parity_max_absolute_error': errors}


def _per_feature(lo, hi, column):
    valid = np.isfinite(column)
    lower, upper = valid & (column < lo), valid & (column > hi)
    count = int((lower | upper).sum())
    return {'finite_n': int(valid.sum()), 'nan_n': int((~valid).sum()), 'outside_n': count,
            'below_n': int(lower.sum()), 'above_n': int(upper.sum()), 'outside_fraction_all': count / len(column),
            'outside_fraction_finite': count / int(valid.sum()) if valid.any() else None}


def feature_support(training, evaluation):
    """Compute holdout fold envelopes and annotate each supplied evaluation feature matrix."""
    if set(training) != set(ROUTES):
        raise ValueError('D4 training groups must contain the three historical routes')
    for values in training.values():
        if values.ndim != 2 or values.shape[1] != len(FEATURES) or not len(values) or np.isinf(values).any():
            raise ValueError('D4 unexpected original training feature matrix')
    folds, fold_arrays = {}, {}
    for held in ROUTES:
        donors = [route for route in ROUTES if route != held]
        fit = np.concatenate([training[route] for route in donors])
        finite_per_column = np.isfinite(fit).sum(axis=0)
        if (finite_per_column == 0).any():
            raise ValueError(f'D4 no training support for one or more HGB columns: {held}')
        lo, hi = np.nanquantile(fit, (0.05, 0.95), axis=0, method='linear')
        fold_arrays[held] = lo, hi
        folds[held] = {'held_out_route': held, 'training_routes': donors, 'train_n': len(fit),
                       'donor_n_by_route': {route: len(training[route]) for route in donors},
                       'columns': {col: {'p05': float(a), 'p95': float(b), 'finite_n': int(n), 'nan_n': int(len(fit) - n)}
                                   for col, a, b, n in zip(FEATURES, lo, hi, finite_per_column, strict=True)}}
    rows = []
    for record in evaluation:
        features = record['features']
        if features.ndim != 2 or features.shape[1] != len(FEATURES) or not len(features) or np.isinf(features).any():
            raise ValueError(f"D4 unexpected evaluation feature matrix: {record['case']}")
        lo, hi = fold_arrays[record['route']]
        outside = ((features < lo) | (features > hi)).any(axis=1)
        missing = np.isnan(features).any(axis=1)
        outside_n, missing_n = int(outside.sum()), int(missing.sum())
        outside_complete_n = int((outside & ~missing).sum())
        missing_only_n = int((missing & ~outside).sum())
        complete_n = int((~missing).sum())
        n = len(features)
        rows.append({key: record[key] for key in record if key != 'features'} | {
            'n': n, 'any_feature_outside_n': outside_n, 'any_feature_outside_fraction_all': outside_n / n,
            'any_feature_missing_n': missing_n, 'any_feature_missing_fraction_all': missing_n / n,
            'missing_only_n': missing_only_n, 'missing_only_fraction_all': missing_only_n / n,
            'outside_and_missing_n': int((outside & missing).sum()), 'complete_n': complete_n,
            'complete_any_outside_n': outside_complete_n,
            'complete_any_outside_fraction': outside_complete_n / complete_n if complete_n else None,
            'columns': {col: _per_feature(a, b, features[:, j])
                        for j, (col, a, b) in enumerate(zip(FEATURES, lo, hi, strict=True))}})
    return {'folds': folds, 'cells': rows}


def analyze_support(config, cells):
    """Authenticate inputs, recover original features from frozen arrays, and score support."""
    import pandas as pd

    if config['columns'] != list(FEATURES) or config['quantile_probabilities'] != [0.05, 0.95] or config['quantile_method'] != 'linear':
        raise ValueError('D4 feature assessment settings differ from the frozen schema')
    for row in config['frozen_files']:
        _verify(row)
    taps = _taps_function(config)
    path = config['sources']['feature_csv']['path']
    columns = ['case', 'channel', 'pose_id', 's_fp', 'range_m', 'e_r', *FEATURES_EXIST]
    frame = pd.read_csv(path, usecols=columns)
    rr = config['sources']['mr_series']['path']
    mr = pd.read_csv(rr, usecols=['case', 'bias', 'channel', 'pose_id', 't_s', 'MU_R_EXDS__meas_r_cm'])
    raw = {case: _feature_source(config, case, frame, taps) for case in CASES}
    training = {route: np.concatenate([raw[case]['x'] for case in CASES if config['source_cases'][case]['route'] == route])
                for route in ROUTES}
    evaluation = [_evaluation_record(cell, config, raw, mr) for cell in cells]
    return {'status': 'FEATURE_SUPPORT_VERIFIED', 'columns': list(FEATURES), 'quantile_probabilities': [0.05, 0.95],
            'quantile_method': 'linear', 'target': config['target'], 'training_rule': config['training_rule'],
            'historical_arm': 'MU_R_EXDS distance correction (X1 MB)', 'stage2_binding_tolerance': TOL,
            'numpy_version': np.__version__, 'pandas_version': pd.__version__,
            'source_full_cases': {case: {'n': len(v['ids']), 's_fp_max_error': v['s_fp_max_error']} for case, v in raw.items()},
            **feature_support(training, evaluation)}
