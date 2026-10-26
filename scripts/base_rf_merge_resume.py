#!/usr/bin/env python3
"""Aggregate two execution-wrapper revisions without changing any source receipt.

Both wrappers call the same frozen temporal.s6 and differ only in restart validation.
Only the two audited SHA256 identities below are accepted. All source, code, configuration,
fold metric, endpoint, model, row multiplicity and output hash checks remain mandatory.
"""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from base_rf_resume_pilot import (workspace, demand, safe_member, sha, check_tables,
                                 window_keys, CODE, CONFIG, WINDOWS, TABLES, ORIGIN_RUN, ORIGIN_ARTIFACT)
RUNNERS = {
    '16588c4497e22fb566b62946a609306cceed78b27a08781bcf6cb6d7e4378a2e': 'strict derived byte hash',
    '378c82284795b890737ca3918e093d3ba51ac6c31a749bf97bfd161be1b748fc': 'exact raw bytes and observables plus native x/P/gate parity'
}


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
        demand(r['runner_sha256'] in RUNNERS, 'Unknown execution wrapper')
        demand(r['origin_run'] == ORIGIN_RUN and r['origin_artifact'] == ORIGIN_ARTIFACT, 'Unknown upstream checkpoint')
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
        runner_sha256=sha(Path(__file__)), accepted_wrappers=RUNNERS, shards=manifests))
    ws.finish('S6', rf_executed=True, operational_temporal_filter=False, partition_only=True,
        original_run=ORIGIN_RUN, window_lengths=list(WINDOWS))
    print('S6_MERGE_PASS', {n: len(f) for n, f in frames.items()}, flush=True)

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default='/tmp/brf_config.json')
    p.add_argument('--parts',type=Path,required=True)
    a=p.parse_args()
    merge(a.config,a.parts)
