"""Synthetic receipts only; never evidence of a real Office run."""
import json
from pathlib import Path
from office_transfer_core import load_lock, sha256


def source_receipt(path, lock_path, table=None):
    lock=load_lock(lock_path)
    rows=[]
    for route,meta in lock['paths'].items():
        rows.append({'route':route,'n_rf':meta['rf_n'],'n_motion':meta['motion_n'],
            'n_los_visible':meta['rf_n'],'n_train_valid':meta['rf_n'],
            'radio_sha256':meta['files']['RADIO_POSE.csv'],
            'release_sha256':meta['archive_sha256'],'model_vs_direct_los_max_abs':0.01})
    qa={'technical':'SOURCE_DATASET_PREPARED','source_commit':lock['source_audit_commit'],
        'lock_sha256':sha256(lock_path),'label_file_sha256':sha256(table) if table else '0'*64,
        'valid_training_rows':sum(r['n_train_valid'] for r in rows),'routes':rows}
    Path(path).write_text(json.dumps(qa),encoding='utf-8')
    return qa


def input_manifest(path, lock_path, inputs, case, channel, bias):
    doc={'schema':'TRANSFER_TARGET_INPUTS_V1','target_commit':load_lock(lock_path)['corridor_p2_commit'],
         'condition':{'case':case,'channel':channel,'bias':bias},
         'files':{name:sha256(file) for name,file in inputs.items()}}
    Path(path).write_text(json.dumps(doc),encoding='utf-8')
    return sha256(path)
