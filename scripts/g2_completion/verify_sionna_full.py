"""Whole-campaign coverage and integrity check (no RF calls).

    python scripts/g2_completion/verify_sionna_full.py --campaign-root <root> --inputs-dir 00_inputs_R3 \
        [--batches-file 02_batches/BATCHES.jsonl] [--runs-dir batches] [--out 06_validation/VERIFY.json]

Checks target-set equality between TARGETS, BATCHES and COMPLETE batches,
re-verifies every raw receipt SHA, requires a FINISHED production manifest
per batch with matching output SHAs, and reports per-family / per-scene
coverage. Status FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED only when all
165,009 targets are raw-complete and finished; never a G2 PASS or seal.
"""
import argparse
import collections
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_runner import atomic_write_json, attempts, batch_complete, file_sha  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', required=True)
    ap.add_argument('--batches-file', default='02_batches/BATCHES.jsonl')
    ap.add_argument('--runs-dir', default='batches')
    ap.add_argument('--out', default='06_validation/VERIFY.json')
    a = ap.parse_args()
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    inputs = root/a.inputs_dir
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    if file_sha(inputs/'TARGETS.jsonl') != config['targets_sha256']:
        raise SystemExit('TARGETS_SHA_NOT_CONFIG')
    fam, scene = {}, {}
    with (inputs/'TARGETS.jsonl').open(encoding='utf8') as f:
        for line in f:
            t = json.loads(line); fam[t['target_id']] = t['family']; scene[t['target_id']] = t['scene_id']
    batches = [json.loads(l) for l in (root/a.batches_file).read_text(encoding='utf8').splitlines()]
    in_batches = [t for b in batches for t in b['target_ids']]
    problems = []
    if len(in_batches) != len(set(in_batches)) or set(in_batches) != set(fam):
        problems.append('BATCH_TARGET_SET_NOT_EQUAL_TARGETS')
    raw_done, finished, failures = set(), set(), []
    for b in batches:
        bdir = root/a.runs_dir/b['batch_id']
        if not bdir.is_dir():
            continue
        complete = [att for att in attempts(bdir) if (att/'COMPLETE.json').is_file()]
        if not complete:
            for att in attempts(bdir):
                st = att/'STATUS.json'
                if st.is_file():
                    failures += json.loads(st.read_text(encoding='utf8')).get('failed', [])
            continue
        key = json.loads((complete[-1]/'COMPLETE.json').read_text(encoding='utf8'))['run_key']
        if not batch_complete(bdir, b, key):
            problems.append(f"RAW_VERIFY_FAILED:{b['batch_id']}"); continue
        raw_done.update(b['target_ids'])
        fin = bdir/'production'/'FINISHED.json'
        if fin.is_file():
            f = json.loads(fin.read_text(encoding='utf8'))
            m = json.loads((bdir/'production'/'MANIFEST.json').read_text(encoding='utf8'))
            if file_sha(bdir/'production'/'MANIFEST.json') != f['manifest_sha256'] or any(
                    file_sha(bdir/'production'/n) != h for n, h in m['outputs'].items()):
                problems.append(f"PRODUCTION_SHA_MISMATCH:{b['batch_id']}")
            else:
                finished.update(b['target_ids'])
    count = lambda ids, by: dict(collections.Counter(by[i] for i in ids))
    complete = not problems and raw_done == set(fam) and finished == set(fam)
    report = dict(
        status='FULL_NATIVE_SIMULATION_COMPLETE_UNSEALED' if complete else 'INCOMPLETE',
        expected=len(fam), raw_complete=len(raw_done), finished=len(finished),
        pending=len(set(fam) - raw_done), failures=failures, problems=problems,
        by_family=dict(expected=count(fam, fam), raw_complete=count(raw_done, fam), finished=count(finished, fam)),
        scenes=dict(expected=len(set(scene.values())), raw_complete=len({scene[i] for i in raw_done})),
        claims=dict(g2_pass=False, sealed=False, search_completeness=False, hardware_accuracy=False),
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv)
    out = root/a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out, report)
    print(json.dumps({k: report[k] for k in ('status', 'expected', 'raw_complete', 'finished', 'pending')}))


if __name__ == '__main__':
    main()
