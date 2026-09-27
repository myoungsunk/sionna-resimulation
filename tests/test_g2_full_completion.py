"""RF-free counterexamples for completion (F2) and interrupted resume (F3).

A 2-target synthetic campaign goes through the real run_batch -> finish_batch
-> verify_campaign path with 257-bin two-path raw outputs; the audit's
perturbations are then applied.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from rt_cp_uwb_py.g2_full_finish import FinishRefused, finish_batch
from rt_cp_uwb_py.g2_full_runner import CallBudget, attempts, expected_run_key, run_batch
from rt_cp_uwb_py.g2_full_verify import verify_campaign
from test_g2_full_finish import raw_two_paths

ROOT = Path(__file__).resolve().parents[1]
OPERATING = ROOT/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json'
COMPLETE = 'FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED'


def make_campaign(tmp_path):
    root = tmp_path/'campaign'; inputs = root/'IN'; inputs.mkdir(parents=True)
    targets = [dict(target_id=c*64, family='L1', scene_id='S', tx=[0., 0., 2.], rx=[3., 0., 1.2], frame_ref=None,
                    geometric_range_m=float(np.hypot(3, .8))) for c in 'ab']
    (inputs/'TARGETS.jsonl').write_text(''.join(json.dumps(t, sort_keys=True) + '\n' for t in targets))
    op = json.loads(OPERATING.read_text())
    config = dict(targets_sha256=hashlib.sha256((inputs/'TARGETS.jsonl').read_bytes()).hexdigest(),
                  noise=op['noise'], detector=op['detector'], solver=op['solver'])
    (inputs/'CONFIG.json').write_text(json.dumps(config, indent=1))
    (inputs/'TARGET_CENSUS.json').write_text(json.dumps(dict(targets=2, scenes=1)))
    batch = dict(batch_id='B000000', count=2, target_ids=[t['target_id'] for t in targets],
                 target_ids_sha256='x')
    (root/'02_batches').mkdir()
    (root/'02_batches/BATCHES.jsonl').write_text(json.dumps(batch) + '\n')
    return root, inputs, {t['target_id']: t for t in targets}, batch


def compute(target, budget):
    for _ in range(3*257):
        budget.take()
    return raw_two_paths(), dict(fixture=True)


def produce(root, inputs, targets, batch):
    key = expected_run_key(ROOT, inputs)
    return run_batch(batch, targets, root/'batches'/batch['batch_id'], key, compute, CallBudget(), 3*257)


def verify(root):
    return verify_campaign(ROOT, root, 'IN', expected_total=2, expected_scenes=1)


def test_full_path_completes_then_solver_seed_change_invalidates_everything(tmp_path):
    root, inputs, targets, batch = make_campaign(tmp_path)
    assert produce(root, inputs, targets, batch)['complete']
    assert finish_batch(ROOT, root, 'IN', batch)['status'] == 'FINISHED'
    assert verify(root)['status'] == COMPLETE
    assert finish_batch(ROOT, root, 'IN', batch)['status'] == 'ALREADY_FINISHED_FOR_CURRENT_KEY'
    # Audit counterexample B: change only the current solver seed.
    c = json.loads((inputs/'CONFIG.json').read_text()); c['solver']['seed'] += 1
    (inputs/'CONFIG.json').write_text(json.dumps(c, indent=1))
    r = verify(root)
    assert r['status'] == 'INCOMPLETE' and r['raw_complete'] == 0 and r['stale_or_other_key'] == ['B000000']
    with pytest.raises(FinishRefused, match='PRODUCTION_STALE'):
        finish_batch(ROOT, root, 'IN', batch)


def test_raw_complete_without_production_is_not_complete(tmp_path):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch)
    r = verify(root)   # audit counterexample A: zero production outputs
    assert r['status'] == 'INCOMPLETE' and r['raw_complete'] == 2 and r['finished'] == 0


def test_missing_or_tampered_production_file_is_not_complete_and_not_overwritten(tmp_path):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch); finish_batch(ROOT, root, 'IN', batch)
    prod = root/'batches/B000000/production'
    (prod/f"{'a'*64}_CHANNEL.npz").unlink()
    assert verify(root)['finished'] == 0
    with pytest.raises(FinishRefused, match='PRODUCTION_STALE_OR_INCOMPLETE'):
        finish_batch(ROOT, root, 'IN', batch)
    assert (prod/f"{'b'*64}_CHANNEL.npz").is_file()   # preserved


def test_other_runtime_code_revision_counts_as_pending(tmp_path, monkeypatch):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch); finish_batch(ROOT, root, 'IN', batch)
    import rt_cp_uwb_py.g2_full_runner as runner
    monkeypatch.setattr(runner, 'RUNTIME_CODE', runner.RUNTIME_CODE[:-1])  # expected code set differs
    assert verify(root)['status'] == 'INCOMPLETE'


@pytest.mark.parametrize('cut', ['manifest_and_complete', 'complete_only'])
def test_interrupt_after_last_receipt_is_recovered_without_rf(tmp_path, cut):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch)
    bdir = root/'batches/B000000'; att = attempts(bdir)[0]
    (att/'COMPLETE.json').unlink()
    if cut == 'manifest_and_complete':
        (att/'MANIFEST.json').unlink()
    before = {p.name: p.read_bytes() for p in att.rglob('*') if p.is_file()}
    budget = CallBudget(limit=0)                      # any RF call would raise
    s = produce_with(root, inputs, targets, batch, budget)
    assert s['recovered'] and s['complete'] and s['rf_calls'] == 0 and budget.used == 0
    assert {p.name: p.read_bytes() for p in att.rglob('*') if p.is_file()} == before
    assert [a.name for a in attempts(bdir)] == ['attempt_001', 'attempt_002']
    assert (attempts(bdir)[1]/'RECOVERY.json').is_file()
    s2 = produce_with(root, inputs, targets, batch, CallBudget(limit=0))   # terminates: no more attempts
    assert s2['complete'] and not s2.get('recovered') and len(attempts(bdir)) == 2
    assert finish_batch(ROOT, root, 'IN', batch)['status'] == 'FINISHED' and verify(root)['status'] == COMPLETE


def produce_with(root, inputs, targets, batch, budget):
    key = expected_run_key(ROOT, inputs)
    return run_batch(batch, targets, root/'batches'/batch['batch_id'], key, compute, budget, 3*257)


def test_collected_copy_without_raw_npz_needs_server_full_verify(tmp_path):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch); finish_batch(ROOT, root, 'IN', batch)
    server = verify(root)
    assert server['status'] == COMPLETE and server['raw_policy'] == 'full'
    import shutil
    shutil.copytree(root/'batches', root/'05_results/batches', ignore=shutil.ignore_patterns('*.npz'),
                    dirs_exist_ok=True)
    shutil.copytree(root/'batches/B000000/production', root/'05_results/batches/B000000/production',
                    dirs_exist_ok=True)   # production NPZ are collected; raw NPZ stay on the server
    sv = tmp_path/'SERVER_VERIFY.json'; sv.write_text(json.dumps(server))
    kw = dict(runs_dir='05_results/batches', raw_policy='receipts-only', expected_total=2, expected_scenes=1)
    assert verify_campaign(ROOT, root, 'IN', server_verify=str(sv), **kw)['status'] == COMPLETE
    r = verify_campaign(ROOT, root, 'IN', server_verify=None, **kw)
    assert r['status'] == 'INCOMPLETE' and 'SERVER_FULL_VERIFY_MISSING_OR_OTHER_KEY' in r['problems']
    other = dict(server, expected_run_key=dict(server['expected_run_key'], config_sha256='0'*64))
    sv.write_text(json.dumps(other))
    assert verify_campaign(ROOT, root, 'IN', server_verify=str(sv), **kw)['status'] == 'INCOMPLETE'
