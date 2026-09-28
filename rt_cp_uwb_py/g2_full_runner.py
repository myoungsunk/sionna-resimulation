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
FULL_BINS = list(range(257))
RUNTIME_CODE = ['scripts/g2_completion/sionna_full_runtime.py', 'scripts/g2_completion/sionna_native_runtime.py',
                'rt_cp_uwb_py/g2_full_runner.py', 'rt_cp_uwb_py/g2_full_panels.py', 'rt_cp_uwb_py/g2_full_paths.py']
FINISH_CODE = ['scripts/g2_completion/finish_sionna_full.py', 'rt_cp_uwb_py/g2_full_finish.py',
               'rt_cp_uwb_py/g2_scoped_channel.py', 'rt_cp_uwb_py/g2_native_channel.py',
               'rt_cp_uwb_py/rf_channel_closure.py', 'rt_cp_uwb_py/features.py', 'rt_cp_uwb_py/matlab_rng.py']


def run_key(config_sha256, targets_sha256, code_sha256):
    return dict(config_sha256=config_sha256, targets_sha256=targets_sha256, code_sha256=code_sha256)


def staged_sha(path, code_root, stage=None):
    """SHA of a file as deployed.

    Without a stage manifest: the local bytes. With one (03_stage/STAGE.json):
    the SHA recorded for that repository path, i.e. the Git-blob bytes that were
    shipped, so a Windows checkout whose text files differ only by line endings
    judges with the same key as the server. A path missing from the manifest is
    an error, never a fallback to local bytes.
    """
    if stage is None:
        return file_sha(path)
    rel = Path(path).resolve().relative_to(Path(code_root).resolve()).as_posix()
    shas = stage.get('_by_local') or {i['local']: i['sha256'] for i in stage['items']}
    stage['_by_local'] = shas
    if rel not in shas:
        raise ValueError('NOT_IN_STAGE_MANIFEST:' + rel)
    return shas[rel]


def expected_run_key(code_root, inputs, bins=FULL_BINS, stage=None):
    """Run key the current frozen inputs + runtime code + band would produce.

    Completion anywhere (skip, finish, verify) is judged against this key, never
    against the key stored in a COMPLETE file. TARGETS, POSES and PANELS must be
    the canonical set named by CONFIG (F5: pose_id is a content hash of the pose
    matrices, so a recomputed POSES must never be paired with the canonical TARGETS).
    """
    inputs = Path(inputs)
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    if file_sha(inputs/'TARGETS.jsonl') != config['targets_sha256']:
        raise ValueError('TARGETS_SHA_NOT_CONFIG')
    for name, field in (('POSES.json', 'poses_sha256'), ('PANELS.json', 'panels_sha256')):
        if field in config and staged_sha(inputs/name, code_root, stage) != config[field]:
            raise ValueError(f'{name}_SHA_NOT_CONFIG: not the canonical set bound to TARGETS')
    key = run_key(staged_sha(inputs/'CONFIG.json', code_root, stage), config['targets_sha256'],
                  {c: staged_sha(Path(code_root)/c, code_root, stage) for c in RUNTIME_CODE})
    key['bins'] = list(bins)
    return key


def production_key(code_root, inputs, raw_key, stage=None):
    """Key of finish outputs: the raw key plus the finish code and operating config."""
    return dict(raw_run_key=raw_key, config_sha256=staged_sha(Path(inputs)/'CONFIG.json', code_root, stage),
                finish_code_sha256={c: staged_sha(Path(code_root)/c, code_root, stage) for c in FINISH_CODE})


def production_complete(batch_dir, batch, prod_key):
    """FINISHED is valid only for the current production key and the full required output set."""
    prod = Path(batch_dir)/'production'
    fin, man = prod/'FINISHED.json', prod/'MANIFEST.json'
    if not fin.is_file() or not man.is_file():
        return False
    f = json.loads(fin.read_text(encoding='utf8'))
    if f.get('production_key') != prod_key or file_sha(man) != f.get('manifest_sha256'):
        return False
    m = json.loads(man.read_text(encoding='utf8'))
    required = {f'{t}_{s}' for t in batch['target_ids'] for s in ('CHANNEL.npz', 'RESULT.json')}
    if m.get('production_key') != prod_key or set(m.get('outputs', {})) != required \
            or f.get('targets') != len(batch['target_ids']):
        return False
    return all((prod/n).is_file() and file_sha(prod/n) == h for n, h in m['outputs'].items())


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
        if not status['complete']:
            # Every target verified but no valid COMPLETE (interrupted after the last receipt):
            # close the batch in a fresh recovery attempt; older attempts stay untouched; no RF.
            rec = new_attempt(batch_dir)
            (rec/'RECOVERY.json').write_text(json.dumps(dict(
                reason='ALL_TARGET_RECEIPTS_VERIFIED_WITHOUT_COMPLETE', rf_calls=0,
                recovered_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()), indent=1) + '\n')
            write_completion(rec, batch, done, key, recovery=True)
            status.update(attempt=rec.name, recovered=True, complete=batch_complete(batch_dir, batch, key))
        atomic_write_json(batch_dir/status['status_file'], status)
        return status
    status['status_file'] = f'{att.name}/STATUS.json'
    atomic_write_json(att/'STATUS.json', status)
    if not missing:
        write_completion(att, batch, done, key)
        status['complete'] = True
    else:
        status['complete'] = False
    return status


def write_completion(att, batch, done, key, recovery=False):
    """MANIFEST then COMPLETE (atomic, last) for a batch whose targets are all verified."""
    outputs = {}
    for tid in batch['target_ids']:
        a, r = done[tid]
        outputs[tid] = dict(attempt=a.name, npz_sha256=r['npz_sha256'],
                            receipt_sha256=file_sha(a/'raw'/f'{tid}.json'))
    atomic_write_json(att/'MANIFEST.json', dict(batch_id=batch['batch_id'], run_key=key, outputs=outputs,
                                                target_ids_sha256=batch['target_ids_sha256'],
                                                recovery=recovery))
    atomic_write_json(att/'COMPLETE.json', dict(batch_id=batch['batch_id'], count=len(outputs),
                                                manifest_sha256=file_sha(att/'MANIFEST.json'),
                                                run_key=key, recovery=recovery))


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
        # Receipt JSON must also be the one the manifest recorded (its meta feeds reports), not only the NPZ.
        if all(verified_receipt(Path(batch_dir)/o['attempt']/'raw', tid, key)
               and file_sha(Path(batch_dir)/o['attempt']/'raw'/f'{tid}.json') == o['receipt_sha256']
               for tid, o in m['outputs'].items()):
            return True
    return False
