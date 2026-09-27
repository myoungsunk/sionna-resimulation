"""Post-process one COMPLETE batch into production channels (no RF calls).

    python scripts/g2_completion/finish_sionna_full.py --campaign-root <root> --inputs-dir 00_inputs_R3 \
        --batch-id B000000 [--runs-dir batches]

Reads the batch's COMPLETE attempt, verifies every raw output against its
receipt, re-sums H, applies the fixed operating point (noise/CIR/detector),
and writes batches/<id>/production/ atomically with a manifest and a
FINISHED receipt. Raw outputs are never modified. Only full-band raw outputs
are accepted (3-bin smoke outputs are rejected with FULL_BAND_REQUIRED).
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_finish import finish_target  # noqa: E402
from rt_cp_uwb_py.g2_full_runner import (atomic_write_bytes, atomic_write_json, attempts, file_sha,  # noqa: E402
                                         npz_bytes, verified_receipt)

CODE = ['scripts/g2_completion/finish_sionna_full.py', 'rt_cp_uwb_py/g2_full_finish.py',
        'rt_cp_uwb_py/g2_scoped_channel.py', 'rt_cp_uwb_py/g2_native_channel.py', 'rt_cp_uwb_py/rf_channel_closure.py',
        'rt_cp_uwb_py/features.py', 'rt_cp_uwb_py/matlab_rng.py']


def complete_attempt(batch_dir):
    for att in reversed(attempts(batch_dir)):
        if (att/'COMPLETE.json').is_file():
            return att, json.loads((att/'COMPLETE.json').read_text(encoding='utf8'))
    raise SystemExit('BATCH_NOT_COMPLETE')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', required=True)
    ap.add_argument('--batch-id', required=True)
    ap.add_argument('--runs-dir', default='batches')
    a = ap.parse_args()
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    inputs = root/a.inputs_dir
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    batch_dir = root/a.runs_dir/a.batch_id
    att, complete = complete_attempt(batch_dir)
    if file_sha(att/'MANIFEST.json') != complete['manifest_sha256']:
        raise SystemExit('MANIFEST_SHA_MISMATCH')
    manifest = json.loads((att/'MANIFEST.json').read_text(encoding='utf8'))
    key = manifest['run_key']
    wanted = set(manifest['outputs'])
    targets = {}
    with (inputs/'TARGETS.jsonl').open(encoding='utf8') as f:
        for line in f:
            t = json.loads(line)
            if t['target_id'] in wanted:
                targets[t['target_id']] = t
    prod = batch_dir/'production'
    if (prod/'FINISHED.json').is_file():
        print('already finished'); return
    prod.mkdir(exist_ok=True)
    outputs, records = {}, []
    for tid, o in sorted(manifest['outputs'].items()):
        raw_dir = batch_dir/o['attempt']/'raw'
        if not verified_receipt(raw_dir, tid, key):
            raise SystemExit(f'RAW_NOT_VERIFIED:{tid}')
        with np.load(raw_dir/f'{tid}.npz') as z:
            raw = {k: z[k] for k in z.files}
        arrays, record = finish_target(raw, targets[tid], config['noise'], config['detector'])
        record.update(raw_npz=f"{o['attempt']}/raw/{tid}.npz", raw_npz_sha256=o['npz_sha256'])
        outputs[f'{tid}_CHANNEL.npz'] = atomic_write_bytes(prod/f'{tid}_CHANNEL.npz', npz_bytes(arrays))
        outputs[f'{tid}_RESULT.json'] = atomic_write_json(prod/f'{tid}_RESULT.json', record)
        records.append(record)
    atomic_write_json(prod/'MANIFEST.json', dict(
        batch_id=a.batch_id, run_key=key, config_sha256=file_sha(inputs/'CONFIG.json'),
        code_sha256={c: file_sha(ROOT/c) for c in CODE}, outputs=outputs,
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv))
    states = {}
    for r in records:
        for d in r['detections']:
            states[d['state']] = states.get(d['state'], 0) + 1
    atomic_write_json(prod/'FINISHED.json', dict(batch_id=a.batch_id, targets=len(records), detection_states=states,
                                                 manifest_sha256=file_sha(prod/'MANIFEST.json'), rf_calls=0))
    print(json.dumps(dict(batch_id=a.batch_id, targets=len(records), detection_states=states)))


if __name__ == '__main__':
    main()
