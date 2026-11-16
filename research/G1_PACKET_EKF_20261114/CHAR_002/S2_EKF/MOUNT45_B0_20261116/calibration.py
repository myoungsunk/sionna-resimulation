"""Recreate the historical donor folds and admit +45 predictions after m0 parity."""

import json
from pathlib import Path
import os
import platform
import subprocess
import sys
import argparse

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import scipy

from prepare_mount45 import (
    OUT, FULL, P2, P2_ART, P0_MANIFEST, ROWS, BLOCK, WORK, checked,
    evaluate_parity, load, release_packet, save_npz, sha, stem, utc, write,
)

MODEL_REV = 'beb845665661ad8c68d07c88f6d268da4832e493'
MODEL_BASE = 'research/MBVAR_PRR_001_20261103'
MODEL_LOCK = OUT / 'CALIBRATION_MODEL_LOCK.json'


def materialize_models():
    def blob(path):
        return subprocess.check_output(['git', '-c', 'gc.auto=0', '-C', str(WORK / 'g1_char002_s2_ekf_20261115'), 'show', f'{MODEL_REV}:{path}'])

    models = {}
    for route in ROWS:
        root = MODEL_BASE + ('/POST_S3_PROPOSER_20261104/R2_EXTENSION/native_inputs' if route == 'R2' else '/A0_R3_REFIT')
        locks = json.loads(blob(f'{root}/NATIVE_LOCK.json'))
        train = json.loads(blob(f'{root}/TRAINING_LOCK.json'))
        gate = json.loads(blob(f'{root}/FULL_GATE.json'))
        assert gate['passed'] and gate['conditions'][f'{route}_aB_m0_B0']['failed'] == 0
        name = f'{route}_aB_m0_refit.joblib'
        dest = OUT / name
        with dest.open('xb') as handle:
            handle.write(blob(f'{root}/{name}'))
        checked(dest, locks[name])
        models[route] = {'file': name, 'sha256': locks[name], 'git_path': f'{root}/{name}',
                         'historical_full_gate': gate['conditions'][f'{route}_aB_m0_B0'],
                         'training_lock': train['fit'][route], 'training_versions': train['packages']}
    write(MODEL_LOCK, {'frozen_utc': utc(), 'commit': MODEL_REV,
                      'parent_contract_sha256': sha(OUT / 'RUN_CONTRACT.json'), 'models': models,
                      'decision': 'Use authenticated previously parity-checked range HGB donors. Current-platform refit produced 0.0443 m maximum error on R2 m0 and was rejected. POWER_DIAG refit and all original parity gates are retained.'})


def historical_modules():
    os.environ.update(PJ_SOURCE_ROOT=str(P2), PJ_ART=str(P2_ART), PJ_OUT=str(OUT / 'legacy_scratch'))
    paths = ('PJ_DS_GATED_20261021', 'R5_N4B_20261015', 'PHYSICS_RS_STAGED_20261015/code')
    sys.path[:0] = [str(P2 / 'research' / name) for name in paths]
    import mu_recursive as hist
    from features import extract, GROUPS
    import n4b_rf_errors as power
    return hist, extract, GROUPS, power


def series(rows, func, chunk):
    batches = [func(rows[i:i + chunk]) for i in range(0, len(rows), chunk)]
    return {key: np.concatenate([part[key] for part in batches]) for key in batches[0]}


def main():
    sys.path.insert(0, str(OUT / 'runtime_sk172'))
    import joblib
    import sklearn
    contract_path = OUT / 'RUN_CONTRACT.json'
    contract = load(contract_path)
    for path, expected in contract['inputs_sha256'].items():
        checked(Path(path), expected)
    fold_models = load(MODEL_LOCK)
    assert fold_models['parent_contract_sha256'] == sha(contract_path)
    assert sklearn.__version__ == '1.7.2'
    hist, extract, groups, power = historical_modules()
    features = pd.read_csv(P2_ART / 'prepared/OBSERVATION_FEATURES_LABELS.csv.gz')
    features = features[features.channel == 'full']
    mr = pd.read_csv(P2 / 'research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz')
    cols = hist.EXIST + hist.DS
    donors = []
    for case in load(P0_MANIFEST)['cases']:
        raw = np.load(P2 / case['full_path'], allow_pickle=False, mmap_mode='r')
        ids = [row['pose_id'] for row in load(P2 / case['samples_path'])]
        full_rows = features[features.case == case['id']].set_index('pose_id').loc[ids].copy()
        taps = series(raw[:, :, :, 0], hist.taps, 128)
        assert np.max(np.abs(taps['s_fp_chk'] - full_rows.s_fp)) < 1e-9
        for col in hist.DS:
            full_rows[col] = taps[col]
        donors.append(full_rows.reset_index())
    donors = pd.concat(donors, ignore_index=True)
    freq = np.load(BLOCK / 'freqs_hz.npy', allow_pickle=False)
    results, predictions = {}, {}
    for route in ROWS:
        old = release_packet(route, 'online')
        ids = old['pose_id']
        target_id = f'{route}_aB_m0'
        old_rows = donors[donors.case == target_id].set_index('pose_id').loc[ids]
        train_hgb = donors[donors.route != route]
        # Preserve the original POWER_DIAG training membership. Its near-site
        # exclusion was computed from historical rows, independent of mount45 inputs.
        old_holdout_xy = donors[donors.route == route][['x_eval', 'y_eval']].to_numpy()
        near = cKDTree(old_holdout_xy).query(donors[['x_eval', 'y_eval']].to_numpy())[0]
        train_power = donors[(donors.route != route) & (near > 1e-4)]
        sample_weights = power.site_weights(np, pd, train_power)
        raw45 = np.load(FULL / f'H_{route}_aB_m45.npy', mmap_mode='r', allow_pickle=False)[ids, :, :, 0]
        f45 = series(raw45, lambda h: extract(h, freq), 64)
        tap45 = series(raw45, hist.taps, 128)
        assert f45['valid'].all() and np.max(np.abs(tap45['s_fp_chk'] - f45['s_fp'])) < 1e-9
        f45 = pd.DataFrame({**f45, **{col: tap45[col] for col in hist.DS}})
        assert set(cols).issubset(f45.columns)
        assert not set(('e_r', 'e_s', 'x_eval', 'y_eval', 'yaw_eval_rad')) & set(f45.columns)
        tests = pd.concat([old_rows, f45], ignore_index=True)
        base, covariance, fold = power.fit_model(np, train_power, tests, sample_weights, 'POWER_BIN_JOINT', groups)
        covariance[:, 1, 0] = covariance[:, 0, 1] = 0
        corrected = base.copy()
        frozen = fold_models['models'][route]
        model = joblib.load(checked(OUT / frozen['file'], frozen['sha256']))
        assert list(model.feature_names_in_) == cols and frozen['training_lock']['n'] == len(train_hgb)
        corrected[:len(ids), 0] = model.predict(old_rows[cols])
        old_mr = mr[(mr['case'] == target_id) & (mr['channel'] == 'full') & (mr['bias'] == 'B0')].set_index('pose_id').loc[ids]
        archive_mu_r = old_rows['e_r'].to_numpy() - old_mr['MU_R_EXDS__meas_r_cm'].to_numpy() / 100.
        n = len(ids)
        columns = ('muBASE', 'R', 'muMB', 'D', 'z')
        m0 = dict(zip(columns, (base[:n], covariance[:n], corrected[:n], old_rows['ds_+1'].abs().to_numpy(), old_rows[['range_m', 's_fp']].to_numpy())))
        for name in columns:
            print(route, name, 'm0 maxabs', np.max(np.abs(old[name] - m0[name])), flush=True)
        result = evaluate_parity({key: old[key] for key in columns}, m0)
        result.update(evaluate_parity({'MR_range_mu': archive_mu_r}, {'MR_range_mu': corrected[:n, 0]}))
        corrected[n:, 0] = model.predict(f45[cols])
        m45 = dict(zip(columns, (base[n:], covariance[n:], corrected[n:], f45['ds_+1'].abs().to_numpy(), f45[['range_m', 's_fp']].to_numpy())))
        assert np.linalg.eigvalsh(m45['R']).min() > 0 and all(np.isfinite(val).all() for val in m45.values())
        results[route] = {'m0': result, 'donor_cases_hgb': train_hgb.groupby('case').size().to_dict(),
                          'donor_cases_power': train_power.groupby('case').size().to_dict(), 'power_model': fold}
        predictions[route] = {'pose_id': ids, **m45}
    hashes = {}
    for route, payload in predictions.items():
        path = OUT / f'{stem(route)}__calibration.npz'
        save_npz(path, payload)
        hashes[path.name] = sha(path)
    write(OUT / 'CALIBRATION_PARITY.json', {
        'status': 'PASS', 'utc': utc(), 'contract_sha256': sha(contract_path), 'model_lock_sha256': sha(MODEL_LOCK),
        'source_sha256': sha(OUT / 'calibration.py'),
        'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__,
                    'scipy': scipy.__version__, 'sklearn': sklearn.__version__},
        'hgb': {'feature_columns': cols, **{key: model.get_params()[key] for key in ('max_iter', 'learning_rate', 'max_leaf_nodes', 'l2_regularization', 'random_state')}},
        'routes': results, 'output_sha256': hashes,
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('models', 'predict'))
    args = parser.parse_args()
    {'models': materialize_models, 'predict': main}[args.stage]()
