"""Offline provenance audit; this module must never be a runtime monitor input."""
from __future__ import annotations
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources'
sys.path.insert(0, str(SRC / 'src'))
sys.path.insert(0, str(SRC / 'research/EKF4_RANGE_S_STAGED_20261014'))
from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments, rng, wrap
import core


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(assets, archives, p2, out):
    reports = {}
    noise = {}
    for route in ('R2', 'R4', 'R5'):
        op = assets / f'{route}_B0_Full_10__online.npz'
        ep = assets / f'{route}_B0_Full_10__evaluator.npz'
        tp = archives / route / f'{route}_B_FROZEN.npz'
        with np.load(op, allow_pickle=False) as f:
            keys = list(f.files)
            on = {k: f[k] for k in ('t', 'pose_id', 'ds', 'gy', 'dt', 'x0', 'P0')}
        with np.load(ep, allow_pickle=False) as f:
            truth = f['truth']
            assert np.array_equal(f['t'], on['t']) and np.array_equal(f['pose_id'], on['pose_id'])
        with np.load(tp, allow_pickle=False) as f:
            tr = {k: f[k] for k in ('prior', 'x', 'K', 'nu')}
        oldp = ROOT / f'research/FP_SC_RECOVERY_R0_R5_20261107/R45_RUN_001/{route}_TRACE.npz'
        with np.load(oldp, allow_pickle=False) as f:
            assert np.array_equal(f['t'], on['t']) and np.array_equal(f['pose_id'], on['pose_id'])
            prior_err = float(np.max(abs(f['prior'][:, 0] - tr['prior'])))
            assert prior_err < 1e-10
        archive_lock = json.loads((archives / route / 'SHA256.json').read_text())
        assert digest(tp) == archive_lock[tp.name]
        ds, angle = motion_increments(on['t'], truth, convention='legacy-euler')
        inp, ev = generate(on['t'], ds, angle, SensorV2Config(level=1, condition='noise_pair', common_scale=0., bias_rw_rad_s_sqrt_s=0.), 10)
        source_noise = rng(10, 'gyro').standard_normal(len(on['t'])) * np.sqrt(on['dt']) * np.radians(.015)
        raw = on['gy'][1:] - wrap(np.diff(truth[:, 2]))
        noise[route] = raw / np.sqrt(on['dt'][1:])
        assert np.max(abs(on['gy'] - inp['dtheta_gyro'])) == 0.
        assert np.max(abs(on['ds'] - inp['ds_odom'])) < 1e-15
        assert np.max(abs(ev['true_bias_rad_s'])) == 0.
        assert np.array_equal(on['dt'], np.r_[0., np.diff(on['t'])])
        assert np.max(abs(on['dt'][1:] - .2)) < 1e-12
        assert all(on[k][0] == 0 for k in ('ds', 'gy', 'dt'))
        se2_error = None
        try:
            motion_increments(on['t'], truth, convention='se2')
        except ValueError as e:
            se2_error = str(e)
        convention_only = {}
        for span in (2., 5., 10.):
            length = round(span/.2)
            errors = []
            for k in range(length, len(truth)):
                x = np.r_[truth[k-length], 0.]
                for j in range(k-length+1, k+1):
                    x = core.transition(x, ds[j], angle[j], on['dt'][j])[0]
                errors.append(np.linalg.norm(x[:2]-truth[k, :2]))
            convention_only[str(span)] = {'xy_p50_p95_p99_max_m': np.quantile(errors, [.5, .95, .99, 1]).tolist()}
        reports[route] = {
            'n': len(on['t']), 'online_sha256': digest(op), 'evaluator_sha256': digest(ep),
            'B_archive_sha256': digest(tp), 'archive_prior_parity_maxabs': prior_err,
            'online_keys': keys, 'independent_wheel_yaw_in_current_archive': False,
            'initial_error_xy_yaw': (on['x0'][:3] - truth[0]).tolist(),
            'P0_diagonal': np.diag(on['P0']).tolist(),
            'legacy_euler_B0_recipe_maxabs_ds_m': float(np.max(abs(on['ds'] - inp['ds_odom']))),
            'B0_recipe_maxabs_gyro_rad': float(np.max(abs(on['gy'] - inp['dtheta_gyro']))),
            'B0_true_bias_maxabs_rad_s': float(np.max(abs(ev['true_bias_rad_s']))),
            'raw_gyro_noise_recipe_maxabs_rad': float(np.max(abs(raw - source_noise[1:]))),
            'SE2_truth_increment_validation_error': se2_error,
            'truth_increments_SE2_propagation_convention_only': convention_only,
            'bias_prediction_persistence_maxabs': float(np.max(abs(tr['prior'][1:, 3] - tr['x'][:-1, 3]))),
            'bias_RF_update_identity_maxabs': float(np.max(abs(tr['x'][:, 3] - tr['prior'][:, 3] - np.einsum('ni,ni->n', tr['K'][:, 3, :], tr['nu'])))),
            'prior_bias_min_median_p95_max_deg_s': np.degrees(np.quantile(tr['prior'][:, 3], [0, .5, .95, 1])).tolist(),
        }
    pairs = {}
    for a, b in itertools.combinations(noise, 2):
        n = min(len(noise[a]), len(noise[b]))
        aa, bb = noise[a][:n], noise[b][:n]
        pairs[f'{a}_{b}'] = {'common_increments': n, 'noise_over_sqrt_dt_maxabs': float(np.max(abs(aa-bb))), 'correlation': float(np.corrcoef(aa, bb)[0, 1])}
    motion = list(csv.DictReader((p2 / 'MOTION_WINDOWS.csv').open()))
    keyed = {(r['route'], int(r['k']), float(r['span_s']), r['mode']): r for r in motion}
    identity = {}
    for route in reports:
        errors = []
        for (rr, k, span, mode), row in keyed.items():
            if rr != route or mode != 'frozen_anchor_bg':
                continue
            other = keyed[(route, k, span, 'zero_bg')]
            errors.append(abs(wrap(float(row['relative_yaw_error_rad']) - float(other['relative_yaw_error_rad']) + span*float(row['anchor_bg_rad_s']))))
        identity[route] = float(max(errors))
        assert identity[route] < 1e-12
    result = {'status': 'PASS_CONTROL_PROVENANCE_AND_P2_ALGEBRA', 'source_commit': 'c141839093d1a2e4a76f91eea632cb6467163e28',
        'routes': reports, 'shared_gyro_noise_prefix': pairs, 'P2_error_bg_decomposition_maxabs_rad': identity,
        'interpretation_limits': ['B0 has exactly zero true gyro bias and scale error in the matched recipe.',
            'All routes share the seed10 gyro-noise prefix; route holdout is not noise-seed holdout.',
            'P2 true-anchor results isolate relative propagation; they do not validate actual wrong-pose anchors.',
            'P2 XY error includes legacy-Euler truth vs SE2 filter integration mismatch.',
            'RF innovation changes estimated gyro bias, but multipath-only causality requires further counterfactuals.']}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status': result['status'], 'P2_error_bg_decomposition_maxabs_rad': identity, 'shared_gyro_noise_prefix': pairs}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('assets', 'archives', 'p2', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    run(a.assets, a.archives, a.p2, a.out)
