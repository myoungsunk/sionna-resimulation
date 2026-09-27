import json
from pathlib import Path

import numpy as np
import pytest

from rt_cp_uwb_py.g2_full_runner import (CallBudget, attempts, batch_complete, completed_targets, file_sha,
                                         plan_batches, run_batch, run_key)
from rt_cp_uwb_py.g2_scoped_channel import observe

OPERATING = Path(__file__).resolve().parents[1]/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json'
KEY = run_key('c'*64, 't'*64, {'runtime': 'r'*64})
CALLS = 3  # e.g. 1 bin x 3 arms per target in these fixtures


def targets(n, scenes=3):
    return [dict(target_id=f'{i:064x}', scene_id=f'S{i % scenes}', frame_ref=None) for i in range(n)]


def fake_compute(log):
    def compute(target, budget):
        for _ in range(CALLS):
            budget.take()
        log.append(target['target_id'])
        return dict(H=np.full(2, int(target['target_id'], 16), float)), dict(scene=target['scene_id'])
    return compute


def setup(tmp_path, n=5, size=16):
    ts = targets(n)
    batch = plan_batches(ts, size)[0]
    return ts, {t['target_id']: t for t in ts}, batch, tmp_path/batch['batch_id']


def test_batches_cover_every_target_including_short_last_batch():
    ts = targets(37)
    batches = plan_batches(ts, 16)
    assert [b['count'] for b in batches] == [16, 16, 5]
    assert sorted(t for b in batches for t in b['target_ids']) == sorted(t['target_id'] for t in ts)
    assert plan_batches(ts, 16) == batches  # deterministic


def test_complete_batch_is_reused_without_new_rf_calls(tmp_path):
    ts, by_id, batch, bdir = setup(tmp_path)
    log = []
    s1 = run_batch(batch, by_id, bdir, KEY, fake_compute(log), CallBudget(), CALLS)
    assert s1['complete'] and s1['computed'] == 5 and s1['rf_calls'] == 15
    s2 = run_batch(batch, by_id, bdir, KEY, fake_compute(log), CallBudget(), CALLS)
    assert s2['reused'] == 5 and s2['computed'] == 0 and s2['rf_calls'] == 0 and len(log) == 5
    assert len(attempts(bdir)) == 1 and batch_complete(bdir, batch, KEY)


def test_partial_and_corrupt_outputs_are_not_trusted_and_not_overwritten(tmp_path):
    ts, by_id, batch, bdir = setup(tmp_path)
    run_batch(batch, by_id, bdir, KEY, fake_compute([]), CallBudget(), CALLS)
    att = attempts(bdir)[0]
    victim, partial = batch['target_ids'][0], batch['target_ids'][1]
    (att/'raw'/f'{victim}.npz').write_bytes(b'corrupted')          # SHA no longer matches receipt
    (att/'raw'/f'{partial}.json').unlink()                           # npz without receipt = partial
    assert not batch_complete(bdir, batch, KEY)
    assert set(completed_targets(bdir, KEY)) == set(batch['target_ids'][2:])
    log = []
    s = run_batch(batch, by_id, bdir, KEY, fake_compute(log), CallBudget(), CALLS)
    assert sorted(log) == sorted([victim, partial]) and s['attempt'] == 'attempt_002' and s['complete']
    assert (att/'raw'/f'{victim}.npz').read_bytes() == b'corrupted'   # old attempt preserved as evidence
    assert batch_complete(bdir, batch, KEY)


def test_changed_run_key_forces_recompute(tmp_path):
    ts, by_id, batch, bdir = setup(tmp_path)
    run_batch(batch, by_id, bdir, KEY, fake_compute([]), CallBudget(), CALLS)
    other = dict(KEY, config_sha256='d'*64)
    assert not batch_complete(bdir, batch, other) and completed_targets(bdir, other) == {}


def test_rf_budget_stops_before_exceeding_and_resume_finishes(tmp_path):
    ts, by_id, batch, bdir = setup(tmp_path)
    budget = CallBudget(limit=7)  # room for 2 targets x 3 calls, not a third
    s = run_batch(batch, by_id, bdir, KEY, fake_compute([]), budget, CALLS)
    assert s['stopped'] == 'RF_CALL_BUDGET' and budget.used == 6 and s['computed'] == 2 and not s['complete']
    assert not (attempts(bdir)[0]/'COMPLETE.json').exists()
    s2 = run_batch(batch, by_id, bdir, KEY, fake_compute([]), CallBudget(), CALLS)
    assert s2['reused'] == 2 and s2['computed'] == 3 and s2['complete']


def test_failed_target_is_recorded_and_blocks_completion(tmp_path):
    ts, by_id, batch, bdir = setup(tmp_path)
    bad = batch['target_ids'][3]

    def compute(target, budget):
        if target['target_id'] == bad:
            raise FloatingPointError('NaN in H')
        return fake_compute([])(target, budget)
    s = run_batch(batch, by_id, bdir, KEY, compute, CallBudget(), CALLS)
    assert s['failed'][0]['target_id'] == bad and 'NaN' in s['failed'][0]['error'] and not s['complete']
    status = json.loads((attempts(bdir)[0]/'STATUS.json').read_text())
    assert status['missing'] == 1


def test_manifest_hashes_match_outputs(tmp_path):
    ts, by_id, batch, bdir = setup(tmp_path)
    run_batch(batch, by_id, bdir, KEY, fake_compute([]), CallBudget(), CALLS)
    att = attempts(bdir)[0]
    m = json.loads((att/'MANIFEST.json').read_text())
    for tid, o in m['outputs'].items():
        assert file_sha(bdir/o['attempt']/'raw'/f'{tid}.npz') == o['npz_sha256']


def test_empty_path_channel_is_a_valid_noise_only_observation():
    c = json.loads(OPERATING.read_text())
    f = 6250400000.+1950000.*np.arange(257)
    row = dict(scene_id='S', link_id='T', frame=None, tx=[0, 0, 0], rx=[1, 0, 0])
    a, records = observe(np.zeros((257, 6, 6)), f, row, c['noise'], c['detector'])
    assert np.isfinite(a['CP_CIR']).all() and np.any(a['noise_H'] != 0)
    assert {r['state'] for r in records} <= {'MISSED_OR_NO_SIGNAL', 'DETECTED_CANDIDATE'}


def test_noise_seed_depends_on_target_identity_only():
    c = json.loads(OPERATING.read_text())
    f = 6250400000.+1950000.*np.arange(257)
    row = dict(scene_id='S', link_id='T', frame=3, tx=[0, 0, 0], rx=[1, 0, 0])
    a, r1 = observe(np.zeros((257, 6, 6)), f, row, c['noise'], c['detector'])
    b, r2 = observe(np.ones((257, 6, 6))*1e-6, f, dict(row), c['noise'], c['detector'])
    np.testing.assert_array_equal(a['noise_H'], b['noise_H'])      # same link/frame -> same noise
    assert len({r['seed'] for r in r1 + r2}) == 1                   # one seed shared by all arms
    c2, _ = observe(np.zeros((257, 6, 6)), f, dict(row, frame=4), c['noise'], c['detector'])
    assert not np.array_equal(a['noise_H'], c2['noise_H'])


def test_reuse_only_run_never_modifies_existing_attempt(tmp_path):
    ts, by_id, batch, bdir = setup(tmp_path)
    run_batch(batch, by_id, bdir, KEY, fake_compute([]), CallBudget(), CALLS)
    att = attempts(bdir)[0]
    before = {p.name: p.read_bytes() for p in att.iterdir() if p.is_file()}
    s = run_batch(batch, by_id, bdir, KEY, fake_compute([]), CallBudget(), CALLS)
    assert s['reuse_only'] and s['complete'] and s['status_file'].startswith('reuse_checks/')
    assert {p.name: p.read_bytes() for p in att.iterdir() if p.is_file()} == before
    assert json.loads((att/'STATUS.json').read_text())['rf_calls'] == 15
