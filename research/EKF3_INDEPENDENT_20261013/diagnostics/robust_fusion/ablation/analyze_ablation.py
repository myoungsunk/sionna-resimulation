"""Paired descriptive contrasts. No retuning or independent-sample claims."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

KEYS = ('case', 'channel', 'range_model', 'condition', 'level', 'seed', 'arm')
MODELS = ('M0', 'M1-A', 'M1-B', 'M1-C')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open('x', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    manifest = json.loads((a.input / 'MANIFEST.json').read_text())
    assert manifest['status'] == 'COMPLETED' and manifest['parity']['status'] == 'PASS'
    for name, digest in manifest['sha256'].items():
        assert sha(a.input / name) == digest, name
    a.out.mkdir(exist_ok=False)
    with (a.input / 'ABLATION_METRICS.csv').open() as f:
        rows = list(csv.DictReader(f))
    cells = defaultdict(dict)
    for r in rows:
        k = tuple(r[x] for x in KEYS)
        assert r['model'] not in cells[k]
        cells[k][r['model']] = r
    contrasts = []
    for k, cell in cells.items():
        assert set(cell) == set(MODELS)
        assert len({r['n'] for r in cell.values()}) == 1
        out = dict(zip(KEYS, k), n=int(cell['M0']['n']))
        for metric, power in [('heading_rmse_deg', 2), ('xy_rmse_m', 2),
                              ('mean_pose_NEES', 1), ('pose95', 1)]:
            v = {m: float(cell[m][metric]) ** power for m in MODELS}
            suffix = metric.replace('rmse', 'mse') if power == 2 else metric
            for m in MODELS:
                out[m + '_' + suffix] = v[m]
            out['bias_under_R0_' + suffix] = v['M1-A'] - v['M0']
            out['RF_without_bias_' + suffix] = v['M1-B'] - v['M0']
            out['bias_under_robust_' + suffix] = v['M1-C'] - v['M1-B']
            out['RF_with_bias_' + suffix] = v['M1-C'] - v['M1-A']
            out['interaction_' + suffix] = v['M1-C'] - v['M1-A'] - v['M1-B'] + v['M0']
        contrasts.append(out)
    write_csv(a.out / 'PAIRED_FACTORIAL_CONTRASTS.csv', contrasts)

    # Trajectory/seed summaries; sensor seeds do not create independent RF scenes.
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[x] for x in ('case', 'channel', 'range_model', 'arm', 'model'))].append(r)
    case_rows = []
    for k, members in groups.items():
        n = sum(int(r['n']) for r in members)
        out = dict(zip(('case', 'channel', 'range_model', 'arm', 'model'), k), n=n, seeds=len(members))
        for metric in ('heading_rmse_deg', 'xy_rmse_m', 'mean_pose_NEES', 'pose95', 'bias_rmse_dps'):
            if not members[0][metric]:
                out[metric] = None
                continue
            power = 2 if 'rmse' in metric else 1
            out[metric] = (sum(int(r['n']) * float(r[metric]) ** power for r in members) / n) ** (1 / power)
        case_rows.append(out)
    write_csv(a.out / 'CASE_METRICS.csv', case_rows)

    diagnostics = []
    current, samples = None, []
    def finish(k, values):
        if k is None: return
        pose = np.array([math.hypot(float(v['error_x']), float(v['error_y'])) for v in values])
        yaw = np.array([float(v['heading_error_deg']) for v in values])
        model = k[-1]; metric = cells[k[:-1]][model]
        assert len(values) == int(metric['n'])
        assert abs(math.sqrt(np.mean(pose**2)) - float(metric['xy_rmse_m'])) < 1e-10
        assert abs(math.sqrt(np.mean(yaw**2)) - float(metric['heading_rmse_deg'])) < 1e-10
        weights = [float(v['huber_weight']) for v in values if v['huber_weight']]
        bias = [math.degrees(float(v['bias_est_rad_s'])) for v in values if v['bias_est_rad_s']]
        updates = [v for v in values if v['status'] == 'applied']
        result = dict(zip(KEYS + ('model',), k), n=len(values),
            heading_error_mean_deg=float(np.mean(yaw)),
            heading_abs_error_p95_deg=float(np.quantile(abs(yaw), .95)),
            position_error_p95_m=float(np.quantile(pose, .95)),
            accepted_fraction=len(updates)/len(values),
            rejected_fraction=sum(v['status']=='rejected_NIS' for v in values)/len(values),
            mean_huber_weight=float(np.mean(weights)) if weights else None,
            downweighted_fraction=float(np.mean(np.array(weights)<1)) if weights else None,
            estimated_bias_mean_dps=float(np.mean(bias)) if bias else None,
            applied_heading_harm_fraction=float(np.mean([float(v['heading_squared_error_change'])>0 for v in updates])) if updates else None)
        diagnostics.append(result)
    with gzip.open(a.input / 'ABLATION_TRACE.csv.gz', 'rt') as f:
        for row in csv.DictReader(f):
            k = tuple(row[x] for x in KEYS + ('model',))
            if k != current:
                finish(current, samples); current, samples = k, []
            samples.append(row)
    finish(current, samples)
    assert len(diagnostics) == len(rows)
    write_csv(a.out / 'UPDATE_DIAGNOSTICS.csv', diagnostics)
    receipt = dict(status='COMPLETED', paired_cells=len(cells), trace_cells_verified=len(diagnostics),
        input_manifest_sha256=sha(a.input/'MANIFEST.json'), script_sha256=sha(Path(__file__)),
        units='heading MSE deg^2, position MSE m^2; interactions descriptive, not independent causal estimands',
        inference='Within frozen data only; no independent RF scene or time-sample p-values',
        E1='whole-route exploratory; historical state influence remains', scientific_PASS=False,
        sha256={p.name:sha(p) for p in a.out.iterdir() if p.is_file()})
    (a.out/'ANALYSIS_RECEIPT.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
