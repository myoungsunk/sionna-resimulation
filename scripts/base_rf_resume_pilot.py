#!/usr/bin/env python3
"""Execution-only checkpoint recovery and S6 partition/merge.

Calls the unchanged temporal.s6 function with its existing window_lengths parameter.
No sampling, optimization, sensor, model, gate, training, or scoring changes.
S6_SHARD success is never a whole-stage S6 PASS. Merge requires every window.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ORIGIN_RUN = 40063600117
ORIGIN_ARTIFACT = 12557265307
CODE = 'ad1c90c8febd6a27740172b4e362258d1038e084ea764b4b00babc9b5771e74b'
CONFIG = 'f42e1b6cad3e1b179ce88b3d3a54179ff09ff44d0d815ee25896f2b23e8569e1'
WINDOWS = (2, 5, 10, 30, 60)
TABLES = ('S6_INFORMATION.csv', 'S6_NONLINEAR_PROFILE.csv.gz', 'S6_BIAS_FORECAST_DIAGNOSTIC.csv')


def demand(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def safe_member(root, relative):
    root = Path(root).resolve()
    demand(not Path(relative).is_absolute(), 'Absolute checkpoint member')
    p = (root / relative).resolve()
    demand(p.is_relative_to(root), 'Checkpoint member outside root')
    demand(p.is_file() and not (root / relative).is_symlink(), f'Missing/symlink member {relative}')
    return p


def verify_saved(root):
    root = Path(root)
    counts = {}
    for stage in ('AUDIT', *(f'S{i}' for i in range(6))):
        rec = json.loads((root / (stage + '_STATUS.json')).read_text())
        demand(rec['status'] == 'PASS', f'{stage} not PASS')
        demand(rec['code_sha256'] == CODE and rec['config_sha256'] == CONFIG, f'{stage} identity mismatch')
        demand(rec.get('outputs'), f'{stage} empty output manifest')
        for name, want in rec['outputs'].items():
            demand(sha(safe_member(root, name)) == want, f'Corrupt checkpoint {name}')
        counts[stage] = len(rec['outputs'])
    return counts


def workspace(config):
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.common import Workspace, read_json, code_hash
    cfg = read_json(Path(config))
    ws = Workspace(Path(cfg['work_dir']), cfg)
    demand(code_hash() == CODE and ws.config_hash == CONFIG, 'Original code/config changed; receipts cannot be reused')
    for stage in ('AUDIT', *(f'S{i}' for i in range(6))):
        ws.require_stage(stage)
    return ws


def verify(config):
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.common import read_json, digest, write_json
    ws = workspace(config)
    counts = verify_saved(ws.root)
    old = read_json(ws.root / 'S0/S0_MANIFEST.json')['asset_lock']
    new = read_json(Path(ws.config['asset_lock']))
    demand(old == new['files'], 'Restaged source file inventory differs from original S0')
    source_hash = digest(new)
    import csv
    with (ws.root / 'S0/S0_INPUT_QA.csv').open() as f:
        rows = list(csv.DictReader(f))
    demand(rows and all(r['source_hash'] == source_hash for r in rows), 'Restaged source provenance mismatch')
    for name, want in new['files'].items():
        demand(sha(Path(name)) == want, f'Restaged input mismatch {name}')
    out = Path('/tmp/brf_resume_meta'); out.mkdir(exist_ok=True)
    write_json(out / 'CHECKPOINT_VERIFIED.json', dict(origin_run=ORIGIN_RUN, origin_artifact=ORIGIN_ARTIFACT,
        code_sha256=CODE, config_sha256=CONFIG, source_hash=source_hash, receipt_file_counts=counts,
        runner_sha256=sha(Path(__file__)), scientific_changes=False, completed_stages_recomputed=False))
    print('CHECKPOINT_VERIFIED', counts, flush=True)


def window_keys(inputs, seconds):
    import numpy as np
    t = inputs.t
    ends = np.unique(np.searchsorted(t, np.arange(t[0], t[-1] + 1e-9, 10.)))
    for end in ends[ends < len(t)]:
        if t[end] - seconds < t[0]:
            continue
        start = int(np.searchsorted(t, t[end] - seconds))
        if end - start + 1 >= 5:
            yield (inputs.case, inputs.bias, int(inputs.seed_idx), inputs.channel, float(t[end]), int(seconds))


def check_tables(frames, expected):
    expected = set(expected)
    demand(expected, 'Empty S6 window scope')
    for filename, df in frames.items():
        basic = ['case', 'bias', 'seed_idx', 'channel', 'now_t', 'window_s']
        keys = basic + ['bias_model']
        repetitions = 3
        if filename == 'S6_NONLINEAR_PROFILE.csv.gz':
            keys += ['delta_heading_deg']; repetitions = 82
        elif filename == 'S6_BIAS_FORECAST_DIAGNOSTIC.csv':
            keys += ['forecast_horizon_s']; repetitions = 4
        demand(not df.duplicated(keys).any(), f'Duplicate {filename} keys')
        actual = set(df[basic].itertuples(index=False, name=None))
        demand(actual == expected, f'Missing/extra S6 windows in {filename}')
        sizes = df.groupby(basic, dropna=False).size()
        demand((sizes == repetitions).all(), f'Incomplete per-window computations in {filename}')
        models = set(df.bias_model)
        want = {'constant', 'linear', 'free_packet'} if repetitions == 3 else {'constant', 'linear'}
        demand(models == want, f'Wrong nuisance models in {filename}')
        if repetitions == 82:
            want_grid = set(range(-20, 21))
            for _, g in df.groupby(basic + ['bias_model'], dropna=False):
                demand(set(g.delta_heading_deg) == want_grid, 'Altered nonlinear heading grid')


def shard(config, seconds):
    import pandas as pd
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.common import Trace, write_json, digest
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.native import NativeAssets
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.stages import units, trace_path
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.temporal import fit_spectral_metric, s6
    demand(seconds in WINDOWS, 'Unknown window shard')
    ws = workspace(config); assets = NativeAssets(ws.config)
    cal = pd.read_csv(ws.root / 'S3/S3_TEMPORAL_CALIBRATION.csv')
    metrics = {held: fit_spectral_metric(d, held) for held, d in cal.groupby('held')}
    stage = f'S6_SHARDS/w{seconds}'
    rows = {name: [] for name in TABLES}; expected = []
    for spec in units(ws.config):
        inp, model, truth = assets.load(*spec)
        base = Trace.load(trace_path(ws, 'S0', inp, 'BASE'))
        demand(base.metadata['raw_input_sha256'] == inp.checksum(), 'Restored raw inputs changed')
        demand(base.metadata['source_hash'] == inp.source_hash, 'Restored source hash changed')
        expected.extend(window_keys(inp, seconds))
        print('S6_SHARD_START', seconds, inp.tag, flush=True)
        tables = s6(inp, truth, model, base, metrics[inp.route], window_lengths=(seconds,))
        for name in TABLES:
            rows[name].extend(tables[name])
    frames = {name: pd.DataFrame(data) for name, data in rows.items()}
    check_tables(frames, expected)
    for name, frame in frames.items():
        ws.table(stage, name, frame, partition_only=True, original_function='temporal.s6', window_lengths=[seconds])
    out = ws.root / stage
    outputs = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write_json(out / 'SHARD_STATUS.json', dict(status='PARTIAL_COMPLETE', stage='S6', window_s=seconds,
        origin_run=ORIGIN_RUN, origin_artifact=ORIGIN_ARTIFACT, code_sha256=CODE, config_sha256=CONFIG,
        runner_sha256=sha(Path(__file__)), source_hash=assets.source_hash, expected_window_keys=expected,
        metric_hashes={h: digest(m) for h, m in metrics.items()}, outputs=outputs,
        row_counts={n: len(f) for n, f in frames.items()}, whole_stage_pass=False))
    print('S6_SHARD_COMPLETE', seconds, {n: len(f) for n, f in frames.items()}, flush=True)


def merge(config, parts):
    import numpy as np
    import pandas as pd
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.common import write_json, digest
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.temporal import fit_spectral_metric, bias_forecast_diagnostic
    ws = workspace(config)
    records = list(Path(parts).rglob('SHARD_STATUS.json'))
    demand(len(records) == len(WINDOWS), 'All five independent S6 shards required')
    merged = {n: [] for n in TABLES}; expected = []; found = set(); metric_hashes = None; source_hash = None
    manifests = []
    for file in sorted(records):
        r = json.loads(file.read_text()); w = r['window_s']
        demand(w in WINDOWS and w not in found, 'Duplicate/unrecognized window shard'); found.add(w)
        demand(r['status'] == 'PARTIAL_COMPLETE' and r['code_sha256'] == CODE and r['config_sha256'] == CONFIG, 'Wrong shard receipt')
        demand(r['runner_sha256'] == sha(Path(__file__)), 'Sharding runner changed')
        if metric_hashes is None:
            metric_hashes, source_hash = r['metric_hashes'], r['source_hash']
        demand(metric_hashes == r['metric_hashes'] and source_hash == r['source_hash'], 'Fold metric/source differs between shards')
        for name, want in r['outputs'].items():
            demand(sha(safe_member(file.parent, name)) == want, f'Changed shard output {name}')
        frames = {n: pd.read_csv(file.parent / n) for n in TABLES}
        keys = [tuple(k) for k in r['expected_window_keys']]; check_tables(frames, keys)
        for n, frame in frames.items(): merged[n].append(frame)
        expected.extend(keys); manifests.append(r)
    demand(found == set(WINDOWS), 'Incomplete S6 window coverage')
    frames = {n: pd.concat(fs, ignore_index=True) for n, fs in merged.items()}
    check_tables(frames, expected)
    # Derive expected endpoint coverage independently from the unchanged S0 timestamps.
    from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.common import Trace
    import types
    independently_expected = []
    for case in ws.config['cases']:
        for bias in ws.config['biases']:
            for seed in ws.config['seeds']:
                path = ws.root / 'S0/traces' / f'{case}__full__{bias}__seed{seed}__BASE.npz'
                tr = Trace.load(path)
                inp = types.SimpleNamespace(t=tr.arrays['t'], case=case, bias=bias, seed_idx=seed, channel='full')
                for w in WINDOWS: independently_expected.extend(window_keys(inp, w))
    demand(set(expected) == set(independently_expected), 'Shards omitted expected original endpoints')
    cal = pd.read_csv(ws.root / 'S3/S3_TEMPORAL_CALIBRATION.csv')
    for held, d in cal.groupby('held'):
        metric = fit_spectral_metric(d, held)
        demand(digest(metric) == metric_hashes[held], 'Train-only spectral metric not identical')
        write_json(ws.root / 'S6' / f'{held}_TEMPORAL_METRIC.json', metric)
    forecasts = []
    for (held, case), sub in cal.groupby(['held', 'case']):
        sub = sub[np.isfinite(sub.t_s)].sort_values('t_s'); tt = sub.t_s.to_numpy(); bb = sub.target.to_numpy()
        if len(tt) < 5: continue
        for now in np.unique(np.searchsorted(tt, np.arange(tt[0], tt[-1] + 1e-10, 10.))):
            if now >= len(tt): continue
            for window in WINDOWS:
                for kind in ('constant', 'linear'):
                    for horizon in (2., 10.):
                        forecasts.append(dict(held=held, case=case, now_t=tt[now], window_s=window, bias_model=kind,
                            forecast_horizon_s=horizon, **bias_forecast_diagnostic(tt, bb, now, window, horizon, kind)))
    ws.table('S6', 'S6_TRAIN_BIAS_MODEL_FORECAST.csv', forecasts)
    for n, frame in frames.items():
        ws.table('S6', n, frame.sort_values(['case', 'bias', 'seed_idx', 'now_t', 'window_s', 'bias_model']).reset_index(drop=True))
    write_json(ws.root / 'S6/S6_TEMPORAL_ADOPTION.json', dict(status='INCONCLUSIVE', operational_temporal_filter_installed=False,
        reason='Bias-model adequacy, nuisance-marginal RF information, nonlinear ambiguity and recovery require joint review.'))
    write_json(ws.root / 'S6/SHARD_MERGE_QA.json', dict(status='PASS', origin_run=ORIGIN_RUN, windows=list(WINDOWS),
        expected_endpoints=len(expected), original_function_unchanged=True, all_rows_unique=True, source_hash=source_hash,
        runner_sha256=sha(Path(__file__)), shards=manifests))
    ws.finish('S6', rf_executed=True, operational_temporal_filter=False, partition_only=True,
        original_run=ORIGIN_RUN, window_lengths=list(WINDOWS))
    print('S6_MERGE_PASS', {n: len(f) for n, f in frames.items()}, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['verify', 'shard', 'merge'])
    p.add_argument('--config', default='/tmp/brf_config.json')
    p.add_argument('--window', type=int, choices=WINDOWS)
    p.add_argument('--parts', type=Path)
    a = p.parse_args()
    if a.command == 'verify': verify(a.config)
    elif a.command == 'shard':
        demand(a.window is not None, '--window required'); shard(a.config, a.window)
    else:
        demand(a.parts is not None, '--parts required'); merge(a.config, a.parts)


if __name__ == '__main__':
    main()
