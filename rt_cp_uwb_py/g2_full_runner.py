"""S1 orchestration for the full native campaign: batches, atomic outputs, resume.

Engine-free on purpose: the Sionna computation is injected as compute_fn so
batching, completion receipts, resume and the RF-call budget are testable
without RF calls.

Layout per batch (plan section 4):
    batches/<batch_id>/attempt_<nnn>/raw/<target_id>.npz + <target_id>.json
    batches/<batch_id>/attempt_<nnn>/MANIFEST.json   (written with COMPLETE)
    batches/<batch_id>/attempt_<nnn>/COMPLETE.json   (atomic, last)

Completion is decided by SHA-verified receipts that match the run key
(config/targets/code digests), never by file existence. A new attempt never
overwrites an older one; partial or corrupt outputs are left in place.
"""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path

import numpy as np

RECEIPT_SCHEMA = 'SIONNA_FULL_TARGET_RECEIPT_V1'


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_write_bytes(path, data):
    """Write to a temp file in the same directory, fsync, then os.replace."""
    path = Path(path)
    tmp = path.with_name('.' + path.name + f'.tmp{os.getpid()}')
    with tmp.open('wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    return sha_bytes(data)


def atomic_write_json(path, obj):
    return atomic_write_bytes(path, (json.dumps(obj, indent=1, sort_keys=True, allow_nan=False) + '\n').encode())


def npz_bytes(arrays):
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    return buf.getvalue()


# ------------------------------------------------------------------ batches
def plan_batches(targets, batch_size):
    """Deterministic batches: group by scene, then frame, keeping input order.

    Every target lands in exactly one batch (the last batch may be short).
    """
    if batch_size < 1:
        raise ValueError('BATCH_SIZE')
    order = sorted(range(len(targets)), key=lambda i: (targets[i]['scene_id'],
                   json.dumps(targets[i].get('frame_ref'), sort_keys=True), i))
    batches = []
    for start in range(0, len(order), batch_size):
        ids = [targets[i]['target_id'] for i in order[start:start+batch_size]]
        batches.append(dict(batch_id=f'B{len(batches):06d}', count=len(ids), target_ids=ids,
                            target_ids_sha256=sha_bytes('\n'.join(ids).encode())))
    covered = [t for b in batches for t in b['target_ids']]
    if len(covered) != len(targets) or set(covered) != {t['target_id'] for t in targets}:
        raise ValueError('BATCH_COVERAGE')
    return batches


# ------------------------------------------------------------------ receipts
def run_key(config_sha256, targets_sha256, code_sha256):
    return dict(config_sha256=config_sha256, targets_sha256=targets_sha256, code_sha256=code_sha256)


def attempts(batch_dir):
    return sorted(p for p in Path(batch_dir).glob('attempt_*') if p.is_dir())


def verified_receipt(raw_dir, target_id, key):
    """Return the receipt if the target output is complete and intact, else None."""
    rp, npz = Path(raw_dir)/f'{target_id}.json', Path(raw_dir)/f'{target_id}.npz'
    if not rp.is_file() or not npz.is_file():
        return None
    try:
        receipt = json.loads(rp.read_text(encoding='utf8'))
    except ValueError:
        return None
    if receipt.get('schema') != RECEIPT_SCHEMA or receipt.get('target_id') != target_id:
        return None
    if receipt.get('run_key') != key or receipt.get('status') != 'TARGET_COMPUTED':
        return None
    if file_sha(npz) != receipt.get('npz_sha256'):
        return None
    return receipt


def completed_targets(batch_dir, key):
    """target_id -> (attempt dir, receipt) for every verified output in any attempt."""
    done = {}
    for att in attempts(batch_dir):
        raw = att/'raw'
        if not raw.is_dir():
            continue
        for rp in raw.glob('*.json'):
            tid = rp.stem
            if tid in done:
                continue
            r = verified_receipt(raw, tid, key)
            if r:
                done[tid] = (att, r)
    return done


def new_attempt(batch_dir):
    existing = attempts(batch_dir)
    n = int(existing[-1].name.split('_')[1]) + 1 if existing else 1
    att = Path(batch_dir)/f'attempt_{n:03d}'
    (att/'raw').mkdir(parents=True, exist_ok=False)
    (att/'logs').mkdir()
    return att


class BudgetExceeded(RuntimeError):
    pass


class CallBudget:
    """Hard cap on RF (PathSolver) calls; checked before each call."""

    def __init__(self, limit=None):
        self.limit, self.used = limit, 0

    def take(self, n=1):
        if self.limit is not None and self.used + n > self.limit:
            raise BudgetExceeded(f'RF_CALL_BUDGET: used={self.used} limit={self.limit} request={n}')
        self.used += n


def run_batch(batch, targets_by_id, batch_dir, key, compute_fn, budget, calls_per_target):
    """Compute the batch's missing targets into a new attempt; reuse verified ones.

    compute_fn(target, budget) -> (arrays: dict, meta: dict). Returns a status dict.
    COMPLETE.json is written only when every target of the batch is verified.
    """
    batch_dir = Path(batch_dir); batch_dir.mkdir(parents=True, exist_ok=True)
    done = completed_targets(batch_dir, key)
    todo = [t for t in batch['target_ids'] if t not in done]
    att = new_attempt(batch_dir) if todo else attempts(batch_dir)[-1]
    status = dict(batch_id=batch['batch_id'], attempt=att.name, reused=len(batch['target_ids'])-len(todo),
                  computed=0, failed=[], rf_calls=0)
    for tid in todo:
        start = budget.used
        try:
            if budget.limit is not None and budget.used + calls_per_target > budget.limit:
                raise BudgetExceeded(f'RF_CALL_BUDGET: used={budget.used} limit={budget.limit} '
                                     f'next_target_needs={calls_per_target}')
            arrays, meta = compute_fn(targets_by_id[tid], budget)
            npz_sha = atomic_write_bytes(att/'raw'/f'{tid}.npz', npz_bytes(arrays))
            atomic_write_json(att/'raw'/f'{tid}.json', dict(
                schema=RECEIPT_SCHEMA, status='TARGET_COMPUTED', target_id=tid, batch_id=batch['batch_id'],
                attempt=att.name, run_key=key, npz_sha256=npz_sha, rf_calls=budget.used-start,
                finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), meta=meta))
            done[tid] = (att, verified_receipt(att/'raw', tid, key))
            status['computed'] += 1
        except BudgetExceeded:
            status['rf_calls'] += budget.used-start
            status['stopped'] = 'RF_CALL_BUDGET'
            break
        except Exception as exc:  # deterministic failures are recorded, never silently dropped
            status['failed'].append(dict(target_id=tid, error=f'{type(exc).__name__}: {exc}'))
        status['rf_calls'] += budget.used-start
    missing = [t for t in batch['target_ids'] if t not in done]
    status['missing'] = len(missing)
    if not todo:
        # Reuse-only run: never modify an existing attempt; leave a separate receipt.
        status['reuse_only'] = True
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (batch_dir/'reuse_checks').mkdir(exist_ok=True)
        status['status_file'] = f'reuse_checks/{stamp}.json'
        status['complete'] = batch_complete(batch_dir, batch, key)
        atomic_write_json(batch_dir/status['status_file'], status)
        return status
    status['status_file'] = f'{att.name}/STATUS.json'
    atomic_write_json(att/'STATUS.json', status)
    if not missing:
        outputs = {}
        for tid in batch['target_ids']:
            a, r = done[tid]
            outputs[tid] = dict(attempt=a.name, npz_sha256=r['npz_sha256'],
                                receipt_sha256=file_sha(a/'raw'/f'{tid}.json'))
        atomic_write_json(att/'MANIFEST.json', dict(batch_id=batch['batch_id'], run_key=key, outputs=outputs,
                                                    target_ids_sha256=batch['target_ids_sha256']))
        atomic_write_json(att/'COMPLETE.json', dict(batch_id=batch['batch_id'], count=len(outputs),
                                                    manifest_sha256=file_sha(att/'MANIFEST.json'),
                                                    run_key=key))
        status['complete'] = True
    else:
        status['complete'] = False
    return status


def batch_complete(batch_dir, batch, key):
    """True only if some attempt holds a COMPLETE receipt whose outputs all verify."""
    for att in reversed(attempts(batch_dir)):
        cp = att/'COMPLETE.json'
        if not cp.is_file():
            continue
        c = json.loads(cp.read_text(encoding='utf8'))
        if c['run_key'] != key or file_sha(att/'MANIFEST.json') != c['manifest_sha256']:
            continue
        m = json.loads((att/'MANIFEST.json').read_text(encoding='utf8'))
        if sorted(m['outputs']) != sorted(batch['target_ids']):
            continue
        if all(verified_receipt(Path(batch_dir)/o['attempt']/'raw', tid, key)
               for tid, o in m['outputs'].items()):
            return True
    return False
