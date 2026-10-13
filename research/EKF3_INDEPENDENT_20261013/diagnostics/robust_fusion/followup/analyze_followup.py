"""Read-only recomputation and descriptive summaries for the frozen M1 followup."""
import argparse
import gzip
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    args = ap.parse_args()
    root = args.root
    out = root/'ANALYSIS'
    out.mkdir(exist_ok=False)
    for stage in ('BIAS_SMOKE', 'BIAS_FULL'):
        receipt = json.loads((root/stage/'RECEIPT.json').read_text())
        assert receipt['exit_code'] == 0
        for name, digest in receipt['output_sha256'].items():
            assert sha(root/stage/name) == digest
    for stage in ('RF_SMOKE', 'RF_FULL'):
        receipt = json.loads((root/stage/'MANIFEST.json').read_text())
        assert receipt['parity']['status'] == 'PASS'
        for name, digest in receipt['sha256'].items():
            assert sha(root/stage/name) == digest

    # Paired trials, never individual time steps, are the repetition units.
    bias = pd.read_csv(root/'BIAS_FULL/CASE_METRICS.csv')
    summaries = []
    bkeys = ['path', 'true_bias_dps', 'noisy', 'arm', 'model']
    for key, g in bias.groupby(bkeys):
        row = dict(zip(bkeys, key))
        row.update(trials=len(g), samples=int(g.samples.sum()))
        for col in ['position_rmse_m', 'heading_rmse_deg', 'bias_rmse_dps']:
            row[col] = float(np.sqrt(np.mean(g[col]**2)))
        for col in ['mean_pose_nees', 'pose95', 'heading95', 'bias95',
                    'mean_bias_error_dps', 'final_bias_error_dps', 'gate_reject_fraction']:
            row[col] = float(g[col].mean())
        row['final_bias_error_trial_std_dps'] = float(g.final_bias_error_dps.std(ddof=1))
        row['final_bias_error_trial_se_dps'] = row['final_bias_error_trial_std_dps']/math.sqrt(len(g))
        row['mean_paired_gate_disagreements'] = float(g.paired_gate_disagreements.mean())
        summaries.append(row)
    pd.DataFrame(summaries).to_csv(out/'BIAS_SUMMARY.csv', index=False)
    contrasts = []
    for key, g in bias[bias.noisy == 1].groupby(['path', 'true_bias_dps', 'arm']):
        a = g[g.model == 'M0'].set_index('trial')
        b = g[g.model == 'M1-A'].set_index('trial').loc[a.index]
        row = dict(zip(['path', 'true_bias_dps', 'arm'], key))
        row['independent_paired_trials'] = len(a)
        for col in ['heading_rmse_deg', 'position_rmse_m', 'pose95', 'mean_pose_nees']:
            d = b[col]-a[col]
            row[col+'_mean_paired_difference'] = float(d.mean())
            row[col+'_paired_se'] = float(d.std(ddof=1)/math.sqrt(len(d)))
        contrasts.append(row)
    pd.DataFrame(contrasts).to_csv(out/'BIAS_PAIRED_CONTRASTS.csv', index=False)

    # Check every stored representative synthetic trace, including bias correction.
    stored = defaultdict(list)
    previous_bias = defaultdict(float)
    max_bias_update_error = 0.
    with gzip.open(root/'BIAS_FULL/TRACE.jsonl.gz', 'rt') as f:
        for line in f:
            r = json.loads(line)
            key = (r['path'], r['true_bias_dps'], int(r['noisy']), r['trial'], r['arm'], r['model'])
            e = np.asarray(r['pose'])-r['truth']
            e[2] = (e[2]+np.pi)%(2*np.pi)-np.pi
            p = np.asarray(r['Ppost'])[:3, :3]
            nees = float(e@np.linalg.solve(p, e))
            stored[key].append([e[:2]@e[:2], np.degrees(e[2])**2, nees,
                                float(nees <= 7.814727903251179)])
            if r['model'] == 'M1-A':
                increment = np.degrees(np.asarray(r['Kbias'])@r['innovation']) if r['status'] == 'applied' else 0.
                error = abs(r['estimated_bias_dps']-previous_bias[key]-increment)
                max_bias_update_error = max(max_bias_update_error, error)
                previous_bias[key] = r['estimated_bias_dps']
    bindex = bias.set_index(['path', 'true_bias_dps', 'noisy', 'trial', 'arm', 'model'])
    max_bias_metric_error = 0.
    for key, vals in stored.items():
        a = np.asarray(vals)
        expected = bindex.loc[key]
        actual = [np.sqrt(a[:, 0].mean()), np.sqrt(a[:, 1].mean()), a[:, 2].mean(), a[:, 3].mean()]
        wanted = expected[['position_rmse_m', 'heading_rmse_deg', 'mean_pose_nees', 'pose95']].to_numpy(float)
        max_bias_metric_error = max(max_bias_metric_error, float(np.max(np.abs(actual-wanted))))
    assert max_bias_update_error <= 1e-10
    assert max_bias_metric_error <= 1e-8

    keys = ['case', 'channel', 'range_model', 'condition', 'level', 'seed', 'arm', 'model']
    sums = defaultdict(lambda: np.zeros(15))
    max_nees_recompute = 0.
    min_cov_eigenvalue = math.inf
    trace_rows = 0
    for chunk in pd.read_csv(root/'RF_FULL/RF_COMPONENT_TRACE.csv.gz', chunksize=50000, float_precision='round_trip'):
        n = len(chunk)
        p = np.empty((n, 3, 3))
        p[:, 0, 0] = chunk.Pxx; p[:, 1, 1] = chunk.Pyy; p[:, 2, 2] = chunk.Ppsi
        p[:, 0, 1] = p[:, 1, 0] = chunk.Pxy
        p[:, 0, 2] = p[:, 2, 0] = chunk.Pxpsi
        p[:, 1, 2] = p[:, 2, 1] = chunk.Pypsi
        e = np.column_stack([chunk.error_x, chunk.error_y, np.radians(chunk.heading_error_deg)])
        recomputed = np.einsum('ij,ij->i', e, np.linalg.solve(p, e[..., None])[..., 0])
        max_nees_recompute = max(max_nees_recompute, float(np.max(np.abs(recomputed-chunk.pose_NEES))))
        min_cov_eigenvalue = min(min_cov_eigenvalue, float(np.linalg.eigvalsh(p).min()))
        chunk['heading_sq'] = chunk.heading_error_deg**2
        chunk['position_sq'] = chunk.error_x**2+chunk.error_y**2
        chunk['count'] = 1
        chunk['accepted'] = (chunk.status == 'applied').astype(int)
        chunk['rejected'] = (chunk.status == 'rejected_NIS').astype(int)
        chunk['heading_cov_ratio'] = chunk.Ppsi/chunk.prior_Ppsi
        chunk['xy_cov_ratio'] = (chunk.Pxx+chunk.Pyy)/(chunk.prior_Pxx+chunk.prior_Pyy)
        chunk['weight_count'] = chunk.huber_weight.notna().astype(int)
        chunk['weight_sum'] = chunk.huber_weight.fillna(0)
        cols = ['count', 'heading_sq', 'position_sq', 'pose_NEES', 'heading_NEES', 'pose95', 'heading95',
                'accepted', 'rejected', 'heading_cov_ratio', 'xy_cov_ratio', 'weight_count', 'weight_sum', 'R_s', 'R_r']
        for key, row in chunk.groupby(keys)[cols].sum().iterrows():
            sums[key] += row.to_numpy(float)
        trace_rows += n
    original = pd.read_csv(root/'RF_FULL/RF_COMPONENT_METRICS.csv').set_index(keys)
    assert len(original) == len(sums) == 1512
    metric_max = 0.
    rows = []
    for key, a in sums.items():
        n = a[0]
        vals = [np.sqrt(a[1]/n), np.sqrt(a[2]/n), a[3]/n, a[4]/n, a[5]/n, a[6]/n]
        fields = ['heading_rmse_deg', 'xy_rmse_m', 'mean_pose_NEES', 'mean_heading_NEES', 'pose95', 'heading95']
        ref = original.loc[key]
        metric_max = max(metric_max, float(np.max(np.abs(np.asarray(vals)-ref[fields].to_numpy(float)))))
        assert n == ref['n'] and a[7] == ref.accepted_updates and a[8] == ref.rejected_updates
        row = dict(zip(keys, key)); row.update(zip(fields, vals))
        row.update(n=int(n), accept_fraction=a[7]/n, reject_fraction=a[8]/n,
                   mean_heading_cov_ratio=a[9]/n, mean_xy_cov_ratio=a[10]/n,
                   mean_huber_weight=a[12]/a[11] if a[11] else None,
                   R_s=a[13]/n, R_r=a[14]/n)
        rows.append(row)
    assert min_cov_eigenvalue > 0
    assert metric_max <= 1e-8
    assert max_nees_recompute <= 1e-8
    frame = pd.DataFrame(rows)
    d0_max_difference = 0.
    for _, g in frame[frame.arm == 'D0'].groupby(keys[:6]):
        cols = ['heading_rmse_deg', 'xy_rmse_m', 'mean_pose_NEES', 'pose95']
        base = g[g.model == 'M0'][cols].to_numpy(float)[0]
        d0_max_difference = max(d0_max_difference, float(np.max(np.abs(g[cols].to_numpy(float)-base))))
    assert d0_max_difference <= 1e-8
    frame.to_csv(out/'RF_TRACE_VERIFIED_METRICS.csv', index=False)
    case_rows = []
    for key, g in frame.groupby(['case', 'channel', 'range_model', 'arm', 'model']):
        row = dict(zip(['case', 'channel', 'range_model', 'arm', 'model'], key))
        row.update(seeds=len(g), n=int(g.n.sum()))
        for col in ['heading_rmse_deg', 'xy_rmse_m']:
            row[col] = float(np.sqrt(np.average(g[col]**2, weights=g.n)))
        for col in ['mean_pose_NEES', 'pose95', 'accept_fraction', 'reject_fraction',
                    'mean_heading_cov_ratio', 'mean_xy_cov_ratio']:
            row[col] = float(np.average(g[col], weights=g.n))
        case_rows.append(row)
    pd.DataFrame(case_rows).to_csv(out/'RF_CASE_SUMMARY.csv', index=False)
    receipt = dict(status='PASS', created_utc=datetime.now(timezone.utc).isoformat(),
                   synthetic_cells=len(bias), synthetic_representative_trace_cells=len(stored),
                   synthetic_trace_metric_max_abs_error=max_bias_metric_error,
                   synthetic_bias_update_max_abs_error_dps=max_bias_update_error,
                   RF_trace_rows=trace_rows, RF_trace_cells_verified=len(sums),
                   RF_metric_max_abs_error=metric_max, RF_NEES_recompute_max_abs_error=max_nees_recompute,
                   RF_min_pose_cov_eigenvalue=min_cov_eigenvalue,
                   RF_D0_all_model_max_abs_difference=d0_max_difference,
                   time_samples_independent=False, scientific_PASS=False,
                   source_sha256=sha(Path(__file__)),
                   output_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    (out/'ANALYSIS_RECEIPT.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
