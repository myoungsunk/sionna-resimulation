"""S2 pilot report and capacity plan (no RF calls).

verify_campaign judges the whole 165,009-target contract, so after a pilot it
correctly says INCOMPLETE. This module judges only the approved pilot
batches, under the same current keys (expected_run_key/production_key):

- every listed batch is raw-complete (batch_complete) and production-complete
  (production_complete) for the current keys;
- the batches cover exactly `expected_rows` unique targets;
- the standalone LOS fixture passed for the current runtime code;
- every raw output is full band; condition-panel materials read back as
  contracted per bin (occluder sigma(f) with tan_delta 0.35; metal ITU 1 mm);
- measured seconds/row, peak RSS and bytes/row give the capacity plan.
"""
import datetime
import json
import math
import shutil
from pathlib import Path

from .g2_full_panels import occluder_conductivity
from .g2_full_runner import (FULL_BINS, RUNTIME_CODE, attempts, batch_complete, expected_run_key, file_sha,
                             production_complete, production_key)

TOTAL_TARGETS = 165009


def _complete_manifest(batch_dir, key):
    for att in reversed(attempts(batch_dir)):
        cp = att/'COMPLETE.json'
        if cp.is_file() and json.loads(cp.read_text(encoding='utf8'))['run_key'] == key:
            return json.loads((att/'MANIFEST.json').read_text(encoding='utf8'))
    return None


def _percentile(values, q):
    v = sorted(values)
    if not v:
        return None
    i = min(len(v)-1, max(0, math.ceil(q*len(v))-1))
    return v[i]


def pilot_report(code_root, root, inputs_dir, batch_ids, expected_rows, batches_file='02_batches/BATCHES.jsonl',
                 runs_dir='batches', lanes=2, threads=4, require_fixture=True):
    root = Path(root); inputs = root/inputs_dir
    key = expected_run_key(code_root, inputs)
    pkey = production_key(code_root, inputs, key)
    code = {c: file_sha(Path(code_root)/c) for c in RUNTIME_CODE}
    known = {json.loads(l)['batch_id']: json.loads(l) for l in (root/batches_file).read_text(encoding='utf8')
             .splitlines()}
    problems, rows, per_target = [], [], []
    for bid in batch_ids:
        if bid not in known:
            problems.append(f'UNKNOWN_BATCH:{bid}'); continue
        b, bdir = known[bid], root/runs_dir/bid
        raw_ok = bdir.is_dir() and batch_complete(bdir, b, key)
        prod_ok = raw_ok and production_complete(bdir, b, pkey)
        if not raw_ok:
            problems.append(f'RAW_NOT_COMPLETE_FOR_CURRENT_KEY:{bid}')
        elif not prod_ok:
            problems.append(f'PRODUCTION_NOT_COMPLETE_FOR_CURRENT_KEY:{bid}')
        rows += b['target_ids']
        if not raw_ok:
            continue
        man = _complete_manifest(bdir, key)
        n_attempts = len(attempts(bdir))
        for tid in b['target_ids']:
            o = man['outputs'][tid]
            raw_dir = bdir/o['attempt']/'raw'
            receipt = json.loads((raw_dir/f'{tid}.json').read_text(encoding='utf8'))
            meta = receipt.get('meta', {})
            rec = dict(target_id=tid, batch_id=bid, family=meta.get('family'), scene_id=meta.get('scene_id'),
                       rf_calls=receipt.get('rf_calls'), elapsed_s=meta.get('elapsed_s'),
                       peak_rss_kib=meta.get('peak_rss_kib'), raw_bytes=(raw_dir/f'{tid}.npz').stat().st_size,
                       bins=len(meta.get('bins', [])), attempt=o['attempt'], batch_attempts=n_attempts)
            if meta.get('bins') != FULL_BINS:
                problems.append(f'NOT_FULL_BAND:{tid}')
            if rec['rf_calls'] != 3*len(FULL_BINS):
                problems.append(f'RF_CALLS_NOT_{3*len(FULL_BINS)}:{tid}')
            kind = next((x.get('kind') for x in meta.get('bindings', []) if x.get('object') == 'dynamic_panel'),
                        None)
            rb = meta.get('panel_material_readback', [])
            if kind == 'dielectric':
                ok = len(rb) == len(FULL_BINS) and all(
                    math.isclose(r['relative_permittivity'], 12., rel_tol=1e-6)
                    and math.isclose(r['thickness_m'], .02, rel_tol=1e-6)
                    and math.isclose(r['conductivity_s_m'], occluder_conductivity(r['frequency_hz']), rel_tol=1e-6)
                    for r in rb)
            elif kind == 'PEC':
                ok = len(rb) == len(FULL_BINS) and all(
                    r['type'] == 'ITURadioMaterial' and math.isclose(r['thickness_m'], .001, rel_tol=1e-6)
                    for r in rb)
            else:
                ok = not rb
            rec['panel_kind'] = kind
            if not ok:
                problems.append(f'PANEL_MATERIAL_READBACK:{tid}')
            if prod_ok:
                prod = bdir/'production'
                rec['production_bytes'] = sum((prod/f'{tid}_{s}').stat().st_size
                                              for s in ('CHANNEL.npz', 'RESULT.json'))
                res = json.loads((prod/f'{tid}_RESULT.json').read_text(encoding='utf8'))
                rec['detection_states'] = sorted({d['state'] for d in res['detections']})
                rec['nolos'] = res['labels']['NoLoS']
                rec['resum_max_abs_diff'] = res['resum_max_abs_diff']
            per_target.append(rec)
    if len(rows) != len(set(rows)) or len(set(rows)) != expected_rows:
        problems.append(f'PILOT_ROWS:{len(set(rows))}!={expected_rows}')
    fixtures = sorted((root/'02_fixtures').glob('LOS_FIXTURE.*.json')) if (root/'02_fixtures').is_dir() else []
    fixture = next((json.loads(p.read_text(encoding='utf8')) for p in fixtures
                    if json.loads(p.read_text(encoding='utf8')).get('code_sha256') == code), None)
    fixture_ok = bool(fixture and fixture.get('passed') and fixture.get('rf_calls') == 9)
    if require_fixture and not fixture_ok:
        problems.append('LOS_FIXTURE_MISSING_OR_FAILED_FOR_CURRENT_CODE')
    sec = [r['elapsed_s'] for r in per_target if r.get('elapsed_s') is not None]
    rss = [r['peak_rss_kib'] for r in per_target if r.get('peak_rss_kib') is not None]
    raw_b = [r['raw_bytes'] for r in per_target]
    prod_b = [r['production_bytes'] for r in per_target if 'production_bytes' in r]
    mean = lambda v: sum(v)/len(v) if v else None
    remaining = TOTAL_TARGETS - len(per_target)
    capacity = dict(
        measured_rows=len(per_target), lanes=lanes, threads_per_lane=threads,
        seconds_per_row=dict(mean=mean(sec), p50=_percentile(sec, .5), p95=_percentile(sec, .95),
                             max=max(sec) if sec else None),
        peak_rss_gib_max=(max(rss)/2**20) if rss else None,
        bytes_per_row=dict(raw_mean=mean(raw_b), production_mean=mean(prod_b)),
        projection_for_remaining=dict(
            rows=remaining,
            cpu_lane_hours=(remaining*mean(sec)/3600) if sec else None,
            wall_hours_at_measured_lanes=(remaining*mean(sec)/3600/lanes) if sec else None,
            raw_tib=(remaining*mean(raw_b)/2**40) if raw_b else None,
            production_tib=(remaining*mean(prod_b)/2**40) if prod_b else None),
        disk_free_gib_at_runs=(shutil.disk_usage(root).free/2**30),
        basis='pilot receipts (elapsed_s per target within one lane incl. scene load; peak RSS is the lane '
              'process maximum); projection is linear and assumes the pilot mix represents the campaign - '
              'review before any S3 decision')
    report = dict(
        status='S2_PILOT_PASS' if not problems else 'S2_PILOT_INCOMPLETE_OR_FAILED',
        batches=batch_ids, expected_rows=expected_rows, rows_verified=len(per_target),
        expected_run_key=key, production_key=pkey, los_fixture=dict(ok=fixture_ok, record=fixture),
        rf_calls_targets=sum(r['rf_calls'] or 0 for r in per_target),
        rf_calls_fixture=9 if fixture_ok else 0, problems=problems,
        families={f: sum(r['family'] == f for r in per_target) for f in sorted({r['family'] for r in per_target})},
        retried_batches=sorted({r['batch_id'] for r in per_target if r['batch_attempts'] > 1}),
        targets=per_target, capacity=capacity,
        scope='bounded S2 pilot only; not S3, not a G2 PASS, not a seal',
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    return report
