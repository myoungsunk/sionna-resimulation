"""Whole-campaign verification against the current expected keys (no RF calls).

See scripts/g2_completion/verify_sionna_full.py for the policy.
"""
import collections
import datetime
import json
import sys
from pathlib import Path

from .g2_full_inputs import EXPECTED_SCENES, EXPECTED_TOTAL
from .g2_full_runner import (attempts, batch_complete, expected_run_key, file_sha, production_complete,
                             production_key)


def receipts_consistent(batch_dir, batch, key):
    """receipts-only: a COMPLETE for the current key whose MANIFEST lists every target with a matching receipt."""
    for att in reversed(attempts(batch_dir)):
        cp = att/'COMPLETE.json'
        if not cp.is_file():
            continue
        c = json.loads(cp.read_text(encoding='utf8'))
        if c.get('run_key') != key or file_sha(att/'MANIFEST.json') != c['manifest_sha256']:
            continue
        m = json.loads((att/'MANIFEST.json').read_text(encoding='utf8'))
        if sorted(m['outputs']) != sorted(batch['target_ids']):
            continue
        ok = True
        for tid, o in m['outputs'].items():
            rp = Path(batch_dir)/o['attempt']/'raw'/f'{tid}.json'
            if not rp.is_file() or file_sha(rp) != o['receipt_sha256']:
                ok = False; break
            r = json.loads(rp.read_text(encoding='utf8'))
            if r.get('run_key') != key or r.get('npz_sha256') != o['npz_sha256']:
                ok = False; break
        if ok:
            return True
    return False


def server_report_problems(sv, key, pkey, expected_total):
    """C: a server report is accepted only as a successful full-raw verification for these keys."""
    if not sv:
        return ['SERVER_FULL_VERIFY_MISSING_OR_OTHER_KEY']
    out = []
    if sv.get('raw_policy') != 'full' or sv.get('expected_run_key') != key or sv.get('production_key') != pkey:
        out.append('SERVER_FULL_VERIFY_MISSING_OR_OTHER_KEY')
    if sv.get('status') != 'FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED':
        out.append('SERVER_VERIFY_NOT_COMPLETE:' + str(sv.get('status')))
    counts = (sv.get('expected'), sv.get('raw_complete'), sv.get('finished'))
    if counts != (expected_total,)*3 or sv.get('pending') != 0:
        out.append(f'SERVER_VERIFY_COUNTS:{counts}/pending={sv.get("pending")}')
    if sv.get('problems') or sv.get('stale_or_other_key'):
        out.append('SERVER_VERIFY_REPORTED_PROBLEMS')
    return out


def verify_campaign(code_root, root, inputs_dir, batches_file='02_batches/BATCHES.jsonl', runs_dir='batches',
                    raw_policy='full', server_verify=None, expected_total=EXPECTED_TOTAL,
                    expected_scenes=EXPECTED_SCENES, stage=None):
    """stage: the 03_stage/STAGE.json that was deployed; keys then use the shipped bytes (B)."""
    root = Path(root)
    inputs = root/inputs_dir
    key = expected_run_key(code_root, inputs, stage=stage)
    pkey = production_key(code_root, inputs, key, stage=stage)
    census = json.loads((inputs/'TARGET_CENSUS.json').read_text(encoding='utf8'))
    fam, scene = {}, {}
    with (inputs/'TARGETS.jsonl').open(encoding='utf8') as f:
        for line in f:
            t = json.loads(line); fam[t['target_id']] = t['family']; scene[t['target_id']] = t['scene_id']
    problems = []
    if len(fam) != expected_total or census['targets'] != expected_total:
        problems.append('CAMPAIGN_TARGET_COUNT')
    if len(set(scene.values())) != expected_scenes or census['scenes'] != expected_scenes:
        problems.append('CAMPAIGN_SCENE_COUNT')
    batches = [json.loads(l) for l in (root/batches_file).read_text(encoding='utf8').splitlines()]
    in_batches = [t for b in batches for t in b['target_ids']]
    if len(in_batches) != len(set(in_batches)) or set(in_batches) != set(fam):
        problems.append('BATCH_TARGET_SET_NOT_EQUAL_TARGETS')
    if raw_policy == 'receipts-only':
        sv = json.loads(Path(server_verify).read_text(encoding='utf8')) if server_verify else None
        problems += server_report_problems(sv, key, pkey, expected_total)
    raw_done, finished, stale, failures = set(), set(), [], []
    for b in batches:
        bdir = root/runs_dir/b['batch_id']
        if not bdir.is_dir():
            continue
        raw_ok = batch_complete(bdir, b, key) if raw_policy == 'full' else receipts_consistent(bdir, b, key)
        if not raw_ok:
            if any((att/'COMPLETE.json').is_file() for att in attempts(bdir)):
                stale.append(b['batch_id'])  # complete for another key, or failing verification
            for att in attempts(bdir):
                st = att/'STATUS.json'
                if st.is_file():
                    failures += json.loads(st.read_text(encoding='utf8')).get('failed', [])
            continue
        raw_done.update(b['target_ids'])
        if production_complete(bdir, b, pkey):
            finished.update(b['target_ids'])
        elif (bdir/'production').exists():
            stale.append(b['batch_id'] + ':production')
    count = lambda ids, by: dict(collections.Counter(by[i] for i in ids))
    complete = not problems and raw_done == set(fam) and finished == set(fam)
    report = dict(
        status='FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED' if complete else 'INCOMPLETE',
        raw_policy=raw_policy, expected_run_key=key, production_key=pkey,
        key_bytes='stage manifest ' + str(stage.get('code_revision')) if stage else 'local files',
        expected=len(fam), raw_complete=len(raw_done), finished=len(finished),
        pending=len(set(fam) - finished), stale_or_other_key=stale, failures=failures, problems=problems,
        by_family=dict(expected=count(fam, fam), raw_complete=count(raw_done, fam), finished=count(finished, fam)),
        scenes=dict(expected=len(set(scene.values())), finished=len({scene[i] for i in finished})),
        claims=dict(g2_pass=False, sealed=False, search_completeness=False, hardware_accuracy=False),
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv)
    return report
