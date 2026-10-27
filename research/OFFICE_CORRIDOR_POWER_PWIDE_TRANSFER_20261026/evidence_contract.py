"""Stage evidence, frozen input checks and upstream baseline acceptance gate."""
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from office_transfer_core import sha256, load_lock

METRICS = ('heading_rmse_deg', 'heading_nees_1d', 'heading_cov95',
           'xy_rmse_cm', 'anchor_range_rmse_cm')
BASELINE_TOL = 1e-7  # Same strict bound as frozen P2; never fitted to results.


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def execution_record(lock_path):
    root = Path(__file__).parent
    return {'utc': datetime.now(timezone.utc).isoformat(), 'argv': sys.argv,
            'python': sys.version, 'platform': platform.platform(),
            'versions': {n: importlib.metadata.version(n) for n in
                         ('numpy', 'pandas', 'scipy', 'scikit-learn', 'joblib')},
            'lock_sha256': sha256(lock_path),
            'implementation_sha256': {p.name: sha256(p) for p in sorted(root.glob('*.py'))}}


def fresh_output(path):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('OUTPUT_EXISTS_NO_OVERWRITE:'+str(path))
    path.mkdir(parents=True)
    return path


def validate_source_qa(path, lock_path, table=None):
    qa = read_json(path);lock = load_lock(lock_path)
    if qa.get('technical') == 'SOURCE_DATASET_PREPARED_MOUNT_0_45':
        from office_mount_inputs import validate_outputs
        folder = Path(path).resolve().parent
        manifest_path = folder.parent / 'INPUT_MANIFEST.json'
        manifest = read_json(manifest_path)
        if (manifest.get('original_45_lock_sha256') != sha256(lock_path) or
                qa.get('source_commit') != lock['source_audit_commit']):
            raise ValueError('SOURCE_QA_IDENTITY_MISMATCH')
        validate_outputs(folder, manifest_path, qa['input_manifest_sha256'])
        label_sha = qa['outputs_sha256']['OFFICE_SOURCE_LABELS.csv.gz']
        if table is not None and sha256(table) != label_sha:
            raise ValueError('SOURCE_TABLE_SHA_MISMATCH')
        # Normalize the two input schemas for the existing model provenance chain.
        return dict(qa, label_file_sha256=label_sha, lock_sha256=sha256(lock_path))
    if (qa.get('technical') != 'SOURCE_DATASET_PREPARED' or
            qa.get('source_commit') != lock['source_audit_commit'] or
            qa.get('lock_sha256') != sha256(lock_path)):
        raise ValueError('SOURCE_QA_IDENTITY_MISMATCH')
    rows = qa.get('routes', [])
    if len(rows) != 3 or {r['route'] for r in rows} != {'O01','O02','O03'}:
        raise ValueError('SOURCE_QA_ROUTE_SET')
    for row in rows:
        meta = lock['paths'][row['route']]
        value = row.get('model_vs_direct_los_max_abs')
        if (value is None or not np.isfinite(value) or value < 0 or
                value > lock['source_los_model_max_abs_tol'] or row['n_los_visible'] <= 0):
            raise ValueError('SOURCE_QA_PARITY_NOT_PASS')
        if any(row[k] != v for k,v in [('n_rf',meta['rf_n']),('n_motion',meta['motion_n']),
                ('radio_sha256',meta['files']['RADIO_POSE.csv']),('release_sha256',meta['archive_sha256'])]):
            raise ValueError('SOURCE_QA_INPUT_MISMATCH')
    if table is not None and sha256(table) != qa.get('label_file_sha256'):
        raise ValueError('SOURCE_TABLE_SHA_MISMATCH')
    return qa


def training_provenance(source_qa, lock_path):
    qa = validate_source_qa(source_qa, lock_path)
    return {'source_qa_sha256': sha256(source_qa),
            'training_file_sha256': qa['label_file_sha256'],
            'source_commit': qa['source_commit'], 'lock_sha256': sha256(lock_path)}


def validate_training(models, train_qa, source_qa, lock_path):
    qa = read_json(train_qa)
    provenance = training_provenance(source_qa, lock_path)
    if (qa.get('status') != 'SOURCE_TRAINING_COMPLETE' or
            qa.get('model_sha256') != sha256(models) or qa.get('provenance') != provenance):
        raise ValueError('TRAIN_QA_CHAIN_MISMATCH')
    return provenance


def verify_input_manifest(path, expected_sha, inputs, case, channel, bias, commit):
    # The expected manifest digest must come from the pre-run frozen input inventory.
    # This function never creates/approves a manifest from the current inputs.
    if sha256(path) != expected_sha:
        raise ValueError('TARGET_MANIFEST_SHA_MISMATCH')
    doc = read_json(path)
    if (doc.get('schema') != 'TRANSFER_TARGET_INPUTS_V1' or
            doc.get('target_commit') != commit or
            doc.get('condition') != {'case':case, 'channel':channel, 'bias':bias}):
        raise ValueError('TARGET_MANIFEST_IDENTITY_MISMATCH')
    if set(doc.get('files', {})) != set(inputs):
        raise ValueError('TARGET_MANIFEST_FILE_SET_MISMATCH')
    records = {}
    for name, item in inputs.items():
        file = Path(item).resolve();digest = sha256(file)
        if doc['files'][name] != digest:
            raise ValueError('TARGET_INPUT_SHA_MISMATCH:'+name)
        records[name] = {'path':str(file), 'sha256':digest}
    return records


def check_baseline(scores, reference, case, channel, bias):
    rows = reference[(reference.case==case)&(reference.channel==channel)&
                     (reference.bias==bias)&(reference.arm=='BASE')]
    if len(rows) != 1:
        raise ValueError('STRICT_BASE_MISSING_OR_DUPLICATE')
    errors = {}
    for key in METRICS:
        actual, expected = float(scores[key]), float(rows.iloc[0][key])
        if not np.isfinite([actual,expected]).all():
            raise ValueError('STRICT_BASE_NONFINITE:'+key)
        errors[key] = abs(actual-expected)
    if max(errors.values()) >= BASELINE_TOL:
        raise ValueError('STRICT_BASE_PARITY_FAIL:'+json.dumps(errors))
    return {'status':'PASS', 'tolerance_strict_lt':BASELINE_TOL, 'absolute_errors':errors}


def validate_alignment(t, ids, truth, observations, packets):
    if (len(t) < 2 or np.asarray(t).ndim != 1 or np.asarray(ids).shape != np.asarray(t).shape or
            len(np.unique(ids)) != len(ids) or not np.equal(ids,np.asarray(ids,dtype=int)).all() or
            not np.isfinite(t).all() or not np.all(np.diff(t)>0) or
            np.asarray(truth).shape != (len(t),3) or not np.isfinite(truth).all()):
        raise ValueError('TARGET_TRACE_ALIGNMENT_INVALID')
    for name, frame in [('OBSERVATION',observations), ('PACKET',packets)]:
        if not frame.pose_id.is_unique or not set(ids).issubset(set(frame.pose_id)):
            raise ValueError('TARGET_'+name+'_POSE_ALIGNMENT_INVALID')
