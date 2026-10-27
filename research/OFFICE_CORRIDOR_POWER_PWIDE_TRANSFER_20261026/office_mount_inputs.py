"""Additive Mount 0/45 input preparation; no RF, estimator fit or replay.

The original 45-only lock and CLI remain unchanged. Freeze before prepare.
Features are observable Full-channel quantities; source-GT labels are separate.
"""
from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

from office_transfer_core import (P_FEATURES, load_source_ffd, observe_port, sha256)
from runtime_contract import verify_checkout, verify_loaded_modules

SOURCE_COMMIT = '034e57a7209a3bd1bb8857b24fd85c64942e1258'
PARITY_LIMIT = .05
COUNTS = {'O01': (192, 461), 'O02': (207, 521), 'O03': (412, 1175)}
CHANNELS = ('H_FULL', 'H_DIRECT_LOS', 'H_DIRECT_FROM_FULL', 'H_ANALYTIC_DIRECT')
KEY = ['case', 'route', 'mount_deg', 'pose_id', 't_s']
BANKS = {'LP_plus45_bank.npz': 'b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b',
         'LP_minus45_bank.npz': '39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9'}


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def need(value, reason):
    if not value:
        raise ValueError(reason)


def sealed_files(folder):
    folder = Path(folder).resolve()
    out = {}
    for line in (folder / 'SHA256SUMS.txt').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (folder / name).resolve()
        need(path.is_relative_to(folder) and name not in out, 'CASE_SEAL_UNSAFE_OR_DUPLICATE')
        need(sha256(path) == expected, 'CASE_SEAL_HASH:' + name)
        out[name] = expected
    required = {name + '.npy' for name in CHANNELS} | {
        'RADIO_POSE.csv', 'FREQUENCIES_HZ.npy', 'LOS_EXISTS.npy', 'LOS_EXISTS_BY_BIN.npy',
        'QA_RECEIPT.json', 'SCENE_METADATA.json', 'FIRST_PATH.csv'}
    need(required.issubset(out), 'CASE_SEAL_INCOMPLETE')
    out['SHA256SUMS.txt'] = sha256(folder / 'SHA256SUMS.txt')
    return out


def freeze(root0, root45, original_lock, audit_checkout, output):
    need(not output.exists(), 'MANIFEST_EXISTS_NO_OVERWRITE')
    verify_checkout(audit_checkout, SOURCE_COMMIT, 'SOURCE_AUDIT')
    old = read(original_lock)
    need(old['source_audit_commit'] == SOURCE_COMMIT and old['antenna_mount_deg'] == 45,
         'ORIGINAL_LOCK_IDENTITY')
    bankroot = Path(audit_checkout).resolve().parent
    for name, expected in BANKS.items():
        need(sha256(bankroot / name) == expected, 'SOURCE_BANK_HASH:' + name)
    manifest = {'schema': 'OFFICE_MOUNT_INPUT_V1', 'source_audit_commit': SOURCE_COMMIT,
        'source_los_model_max_abs_tol': PARITY_LIMIT,
        'original_45_lock_sha256': sha256(original_lock),
        'created_epoch': time.time(), 'bank_sha256': BANKS,
        'bank_manifest_sha256': sha256(bankroot / 'BANK_MANIFEST.json'), 'cases': []}
    for mount, root in [(0, root0), (45, root45)]:
        for route, (n, motion_n) in COUNTS.items():
            folder = root / 'CASES' / f'{route}_O0_M{mount}_FULL'
            files = sealed_files(folder)
            if mount == 45:
                need(all(files[k] == v for k, v in old['paths'][route]['files'].items()),
                     'ORIGINAL_M45_LOCK_HASH_CHANGED')
            motion = root / 'POSES' / f'{route}_ROUTE_POSE.csv'
            manifest['cases'].append({'route': route, 'mount_deg': mount,
                'case': folder.name, 'folder': str(folder.resolve()), 'rf_n': n,
                'motion_n': motion_n, 'motion_path': str(motion.resolve()),
                'motion_sha256': sha256(motion), 'files': files})
    validate_manifest(manifest)
    # A cross-mount identity check precedes feature extraction and label creation.
    motions = {}
    for case in manifest['cases']:
        _, motion, _ = validate_case(case)
        motions[(case['route'], case['mount_deg'])] = motion
    for route in COUNTS:
        a, b = [motions[(route, m)].drop(columns='yaw_antenna_deg') for m in (0, 45)]
        need(a.equals(b), 'CROSS_MOUNT_MOTION_CHANGED:' + route)
    write(output, manifest)
    return manifest


def validate_manifest(manifest):
    need(manifest.get('schema') == 'OFFICE_MOUNT_INPUT_V1', 'MANIFEST_SCHEMA')
    need(manifest.get('source_audit_commit') == SOURCE_COMMIT, 'SOURCE_COMMIT_CHANGED')
    need(manifest.get('source_los_model_max_abs_tol') == PARITY_LIMIT, 'PARITY_THRESHOLD_CHANGED')
    need(manifest.get('bank_sha256') == BANKS, 'BANK_CONTRACT_CHANGED')
    cases = manifest.get('cases', [])
    need(len(cases) == 6 and {(c['route'], c['mount_deg']) for c in cases} ==
         {(r, m) for r in COUNTS for m in (0, 45)}, 'SIX_CASE_IDENTITY')
    for case in cases:
        need(case['case'] == f"{case['route']}_O0_M{case['mount_deg']}_FULL", 'MOUNT_CASE_MISMATCH')
        need((case['rf_n'], case['motion_n']) == COUNTS[case['route']], 'CASE_COUNTS_CHANGED')
        folder = Path(case['folder'])
        need(sealed_files(folder) == case['files'], 'INPUT_FILE_OR_SEAL_CHANGED')
        need(sha256(case['motion_path']) == case['motion_sha256'], 'MOTION_CHANGED')


def validate_case(case):
    folder = Path(case['folder'])
    pose = pd.read_csv(folder / 'RADIO_POSE.csv')
    motion = pd.read_csv(case['motion_path'])
    n, mn, mount = case['rf_n'], case['motion_n'], case['mount_deg']
    need(len(pose) == n and len(motion) == mn, 'POSE_COUNTS')
    for frame in [pose, motion]:
        vals = frame[['pose_id', 't_s', 'x_m', 'y_m', 'z_m', 'yaw_body_deg', 'yaw_antenna_deg']].to_numpy(float)
        need(np.isfinite(vals).all() and not frame.pose_id.duplicated().any(), 'POSE_NONFINITE_OR_DUPLICATE')
        need(np.all(np.diff(frame.t_s) > 0), 'TIME_NOT_STRICT')
        need(np.all(np.equal(frame.pose_id, np.floor(frame.pose_id))), 'POSE_ID_NOT_INTEGER')
        delta = (frame.yaw_antenna_deg - frame.yaw_body_deg - mount + 180) % 360 - 180
        need(np.max(np.abs(delta)) < 1e-8, 'BODY_ANTENNA_MOUNT_CHANGED')
        need(np.allclose(frame.z_m, .45, atol=1e-12, rtol=0), 'TAG_HEIGHT_CHANGED')
    need(np.array_equal(motion.pose_id, np.arange(mn)) and np.allclose(np.diff(motion.t_s), .25), 'MOTION_CLOCK')
    need(pose.equals(motion.loc[motion.rf_sample == 1].reset_index(drop=True)), 'RF_MOTION_EXACT_JOIN')
    qa = read(folder / 'QA_RECEIPT.json')
    need(qa['status'] == 'FULL_CASE_QA_PASS' and qa['case']['case_id'] == case['case'], 'RF_QA_CASE')
    # Original M45 receipts predate the explicit mount field; case ID and both
    # pose streams above still independently bind their actual antenna rotation.
    receipt_mount = qa['case'].get('mount_deg', 45 if mount == 45 else None)
    need(receipt_mount == mount and qa['case']['anchor_m'] == [5, 2.2, 2.65], 'RF_GEOMETRY')
    frequency = np.load(folder / 'FREQUENCIES_HZ.npy', allow_pickle=False)
    need(np.array_equal(frequency, 6250400000 + 1950000 * np.arange(257)), 'FREQUENCY_GRID')
    flags = np.load(folder / 'LOS_EXISTS.npy', allow_pickle=False)
    bybin = np.load(folder / 'LOS_EXISTS_BY_BIN.npy', allow_pickle=False)
    need(flags.dtype == np.bool_ and flags.shape == (n,) and bybin.shape == (n, 257), 'LOS_SHAPE_OR_TYPE')
    need(np.array_equal(bybin, np.broadcast_to(flags[:, None], bybin.shape)), 'LOS_MASK_DRIFT')
    return pose, motion, flags


def build_case(case, model):
    pose, _, flags = validate_case(case)
    folder, n, mount = Path(case['folder']), case['rf_n'], case['mount_deg']
    arrays = {}
    for name in CHANNELS:
        value = np.load(folder / (name + '.npy'), allow_pickle=False)
        need(value.shape == (n, 257, 2, 2) and value.dtype == np.complex128 and np.isfinite(value).all(),
             'CHANNEL_SHAPE_TYPE_FINITE:' + name)
        arrays[name] = value
    need(np.all(arrays['H_DIRECT_LOS'][~flags] == 0), 'BLOCKED_DIRECT_NOT_ZERO')
    need(np.array_equal(arrays['H_DIRECT_LOS'], arrays['H_DIRECT_FROM_FULL']), 'NATIVE_DIRECT_PARITY')
    freq = np.load(folder / 'FREQUENCIES_HZ.npy', allow_pickle=False)
    # Both TX selection and two-RX same-first-path convention are unchanged.
    q = observe_port(arrays['H_FULL'][:, :, :, 0], freq)
    for key, val in [('case', case['case']), ('route', case['route']), ('mount_deg', mount)]:
        q[key] = val
    q['pose_id'] = pose.pose_id.to_numpy(int)
    q['t_s'] = pose.t_s.to_numpy(float)
    q['scene'] = 'OFFICE_E'
    q['los_exists'] = flags
    q['x_eval'], q['y_eval'] = pose.x_m.to_numpy(), pose.y_m.to_numpy()
    q['yaw_body_deg'] = pose.yaw_body_deg.to_numpy()
    q['anchor_id'] = 'O0'
    q['anchor_x_m'], q['anchor_y_m'] = 5., 2.2
    q['channel'] = 'full'
    q['sample_hash'] = case['files']['H_FULL.npy']
    conf = {'id': case['case'], 'anchor': [5., 2.2, 2.65], 'robot_z_m': .45, 'mount_deg': float(mount)}
    states = np.c_[pose.x_m, pose.y_m, np.deg2rad(pose.yaw_body_deg), np.zeros(n)]
    predicted = np.concatenate([model.batch(states[k:k+32], conf, gradient=False)[0] for k in range(0, n, 32)])
    need(predicted.shape == (n, 2) and np.isfinite(predicted).all(), 'MODEL_PREDICTION_INVALID')
    q['h_s_gt_source'] = predicted[:, 1]
    q['e_r'], q['e_s'] = q.range_m - predicted[:, 0], q.s_fp - predicted[:, 1]
    q['d0_gt_source'] = q.e_s
    q.loc[~flags, ['e_r', 'e_s', 'd0_gt_source', 'h_s_gt_source']] = np.nan
    q['valid_for_training'] = flags & np.isfinite(q[['log_fp_power', 's_fp', 'e_r', 'e_s']].to_numpy(float)).all(axis=1)
    q['pwide_feature_imputations'] = q[P_FEATURES].isna().sum(axis=1).to_numpy(int)
    direct = np.full(n, np.nan)
    if flags.any():
        direct[flags] = observe_port(arrays['H_DIRECT_LOS'][flags, :, :, 0], freq).s_fp.to_numpy(float)
    q['s_direct_los_audit_only'] = direct
    errors = np.abs(predicted[flags, 1] - direct[flags])
    # Independent native first-path records also bind extraction to the RF detector.
    first = pd.read_csv(folder / 'FIRST_PATH.csv')
    full_fp = first[first.channel == 'FULL'].reset_index(drop=True)
    need(np.array_equal(full_fp.pose_id, pose.pose_id) and np.array_equal(full_fp.t_s, pose.t_s), 'RF_OBSERVER_JOIN')
    need(np.array_equal(full_fp.fp_tap.to_numpy(int), q.fp_full), 'RF_OBSERVER_TAP_CHANGED')
    need(np.max(np.abs(full_fp.s - q.s_fp)) < 1e-10 and np.max(np.abs(full_fp.range_raw_m - q.range_m)) < 1e-10,
         'RF_OBSERVER_VALUES_CHANGED')
    info = {'case': case['case'], 'route': case['route'], 'mount_deg': mount, 'n_rf': n,
        'n_motion': case['motion_n'], 'n_los_visible': int(flags.sum()), 'n_los_blocked': int((~flags).sum()),
        'n_train_valid': int(q.valid_for_training.sum()), 'model_vs_direct_los_max_abs': float(errors.max()) if len(errors) else None,
        'model_vs_direct_los_rmse': float(np.sqrt(np.mean(errors ** 2))) if len(errors) else None,
        'radio_sha256': case['files']['RADIO_POSE.csv'], 'full_sha256': case['files']['H_FULL.npy'],
        'pwide_rows_needing_imputation': int(((q.pwide_feature_imputations > 0) & q.valid_for_training).sum())}
    return q, info


def tables(frame):
    need(not frame.duplicated(['case', 'pose_id']).any(), 'COMPOSITE_KEY_DUPLICATE')
    features = frame[KEY + ['scene', 'range_m', 's_fp'] + P_FEATURES].copy()
    label_names = ['los_exists', 'valid_for_training', 'e_r', 'e_s', 'd0_gt_source',
                   'h_s_gt_source', 's_direct_los_audit_only', 'x_eval', 'y_eval', 'yaw_body_deg']
    labels = frame[KEY + label_names].copy()
    need(not labels.loc[~labels.los_exists, ['e_r', 'e_s', 'd0_gt_source', 'h_s_gt_source']].notna().any().any(),
         'BLOCKED_LABEL_LEAK')
    need(np.isfinite(labels.loc[labels.valid_for_training, ['e_r', 'e_s', 'd0_gt_source']].to_numpy(float)).all(),
         'VALID_LABEL_NOT_FINITE')
    # Group identity is deliberately independent of mount and revisit time.
    split = frame[KEY].copy()
    split['scene_group'] = 'OFFICE_E'
    split['route_group'] = frame.route
    split['spatial_group'] = [f'OFFICE_E:{x:.4f}:{y:.4f}' for x, y in zip(frame.x_eval, frame.y_eval)]
    split['partition'] = 'UNASSIGNED_NO_TRAINING'
    return features, labels, split


def motion_timeline(manifest):
    frames = []
    for case in manifest['cases']:
        motion = pd.read_csv(case['motion_path'])
        motion.insert(0, 'mount_deg', case['mount_deg'])
        motion.insert(0, 'case', case['case'])
        frames.append(motion)
    return pd.concat(frames, ignore_index=True)


def validate_outputs(output, manifest_path, expected_sha):
    manifest = read(manifest_path)
    need(sha256(manifest_path) == expected_sha, 'MANIFEST_HASH_CHANGED')
    validate_manifest(manifest)
    qa = read(output / 'OFFICE_SOURCE_QA.json')
    need(qa['technical'] == 'SOURCE_DATASET_PREPARED_MOUNT_0_45' and qa['input_manifest_sha256'] == expected_sha,
         'SOURCE_QA_IDENTITY')
    need(qa['model_fitting'] == 'NOT_RUN' and qa['recursive_eval'] == 'NOT_RUN', 'STAGE_BOUNDARY')
    for name, checksum in qa['outputs_sha256'].items():
        need(sha256(output / name) == checksum, 'OUTPUT_HASH_CHANGED:' + name)
    frame = pd.read_csv(output / 'OFFICE_SOURCE_LABELS.csv.gz')
    features, labels, split = tables(frame)
    for name, expected in [('FEATURES.csv.gz', features), ('LABELS_GT_SOURCE_ONLY.csv.gz', labels),
                           ('SPLIT_GROUPS.csv.gz', split),
                           ('MOTION_TIMELINE.csv.gz', motion_timeline(manifest))]:
        actual = pd.read_csv(output / name)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-12, atol=1e-14)
    for c in manifest['cases']:
        subset = frame[frame.case == c['case']]
        need(len(subset) == c['rf_n'] and subset.mount_deg.eq(c['mount_deg']).all(), 'TABLE_CASE_COVERAGE')
        need(np.array_equal(subset.pose_id, pd.read_csv(Path(c['folder']) / 'RADIO_POSE.csv').pose_id), 'TABLE_POSE_ORDER')
        row = next(r for r in qa['routes'] if r['case'] == c['case'])
        need(row['model_vs_direct_los_max_abs'] is not None and row['model_vs_direct_los_max_abs'] <= PARITY_LIMIT,
             'MODEL_DIRECT_PARITY_NOT_PASS')
        need(int(subset.valid_for_training.sum()) == row['n_train_valid'], 'TRAIN_MASK_COUNT')
    need(len(frame) == 1622, 'ALL_ROWS_COVERAGE')
    need(not any(output.glob('*.joblib')) and not any(output.glob('*.pkl')), 'UNEXPECTED_TRAINED_MODEL')
    return {'status': 'PREPARED_DATA_VALIDATION_PASS', 'rows': len(frame),
            'motion_rows': len(motion_timeline(manifest)),
            'valid_training_candidates': int(frame.valid_for_training.sum()),
            'blocked_los_rows_retained': int((~frame.los_exists).sum()),
            'model_fitting': 'NOT_RUN', 'recursive_eval': 'NOT_RUN'}


def prepare(manifest_path, expected_sha, audit_checkout, output):
    need(sha256(manifest_path) == expected_sha, 'MANIFEST_HASH_CHANGED')
    manifest = read(manifest_path)
    validate_manifest(manifest)
    verify_checkout(audit_checkout, SOURCE_COMMIT, 'SOURCE_AUDIT')
    bankroot = Path(audit_checkout).resolve().parent
    for name, expected in BANKS.items():
        need(sha256(bankroot / name) == expected, 'SOURCE_BANK_HASH:' + name)
    need(sha256(bankroot / 'BANK_MANIFEST.json') == manifest['bank_manifest_sha256'], 'BANK_MANIFEST_CHANGED')
    need(not output.exists(), 'OUTPUT_EXISTS_NO_OVERWRITE')
    output.mkdir(parents=True)
    try:
        model = load_source_ffd(audit_checkout)
        frames, routes = [], []
        for case in manifest['cases']:
            frame, info = build_case(case, model)
            frames.append(frame)
            routes.append(info)
            print(json.dumps(info), flush=True)
        frame = pd.concat(frames, ignore_index=True)
        features, labels, split = tables(frame)
        # Keep diagnostic evidence on gate failure; never issue training-ready QA.
        failed = [r for r in routes if r['model_vs_direct_los_max_abs'] is None or
                  r['model_vs_direct_los_max_abs'] > PARITY_LIMIT or not r['n_train_valid']]
        for name, data in [('FEATURES.csv.gz', features), ('LABELS_GT_SOURCE_ONLY.csv.gz', labels),
                           ('OFFICE_SOURCE_LABELS.csv.gz', frame), ('SPLIT_GROUPS.csv.gz', split),
                           ('MOTION_TIMELINE.csv.gz', motion_timeline(manifest))]:
            data.to_csv(output / name, index=False, compression={'method': 'gzip', 'mtime': 0})
        write(output / 'FEATURE_CONTRACT.json', {'schema': 'OFFICE_MOUNT_FEATURES_V1',
            'keys': KEY, 'model_feature_columns': P_FEATURES, 'range_column': 'range_m',
            'gt_columns_allowed_in_features': [], 'label_policy': 'Full minus SourceFFD model at source GT; visible LoS only',
            'first_path': 'TX index 0, two RX same strongest-port 30% Hann 4N IFFT tap',
            'missing_offset_policy': 'Retain NaN; fit imputation on training fold only',
            'split_policy': 'Unassigned; spatial groups shared across mount/revisits; route/scene embargo required'})
        if failed:
            write(output / 'OFFICE_SOURCE_QA_BLOCKED.json', {'technical': 'BLOCKED_SOURCE_LoS_MODEL_PARITY',
                'limit_abs': PARITY_LIMIT, 'routes': routes, 'failed_cases': [r['case'] for r in failed],
                'input_manifest_sha256': expected_sha, 'model_fitting': 'NOT_RUN', 'recursive_eval': 'NOT_RUN'})
            raise ValueError('SOURCE_LoS_MODEL_PARITY_FAIL')
        validate_manifest(manifest)
        qa = {'technical': 'SOURCE_DATASET_PREPARED_MOUNT_0_45', 'source_commit': SOURCE_COMMIT,
            'input_manifest_sha256': expected_sha, 'source_los_model_max_abs_tol': PARITY_LIMIT,
            'routes': routes, 'valid_training_rows': int(frame.valid_for_training.sum()),
            'source_modules': verify_loaded_modules(audit_checkout), 'model_fitting': 'NOT_RUN',
            'recursive_eval': 'NOT_RUN', 'timestamp_epoch': time.time(),
            'versions': {n: importlib.metadata.version(n) for n in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'joblib']},
            'implementation_sha256': {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')},
            'outputs_sha256': {p.name: sha256(p) for p in output.iterdir() if p.is_file()},
            'argv': sys.argv}
        write(output / 'OFFICE_SOURCE_QA.json', qa)
        result = validate_outputs(output, manifest_path, expected_sha)
        write(output / 'VALIDATION_RECEIPT.json', result)
        print(json.dumps(result), flush=True)
    except Exception as exc:
        write(output / 'FAILURE_RECEIPT.json', {'status': 'FAILED_STOP', 'error': repr(exc),
            'model_fitting': 'NOT_RUN', 'recursive_eval': 'NOT_RUN', 'timestamp_epoch': time.time()})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    f = sub.add_parser('freeze')
    f.add_argument('--root0', type=Path, required=True)
    f.add_argument('--root45', type=Path, required=True)
    f.add_argument('--original-lock', type=Path, required=True)
    f.add_argument('--audit-checkout', type=Path, required=True)
    f.add_argument('--out', type=Path, required=True)
    for stage in ['prepare', 'validate']:
        a = sub.add_parser(stage)
        a.add_argument('--manifest', type=Path, required=True)
        a.add_argument('--manifest-sha256', required=True)
        a.add_argument('--out', type=Path, required=True)
        if stage == 'prepare':
            a.add_argument('--audit-checkout', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        freeze(args.root0, args.root45, args.original_lock, args.audit_checkout, args.out)
        print('FROZEN', sha256(args.out))
    elif args.command == 'prepare':
        prepare(args.manifest, args.manifest_sha256, args.audit_checkout, args.out)
    else:
        print(json.dumps(validate_outputs(args.out, args.manifest, args.manifest_sha256)))


if __name__ == '__main__':
    main()
