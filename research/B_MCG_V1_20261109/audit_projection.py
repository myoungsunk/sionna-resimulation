"""P3 diagnostic: local nuisance projection using the exact SourceFFD model.

No evaluator or clean channel is read. A small projected residual is not proof
of a correct heading or recoverable signal: the nuisance fit is unbounded and
local, and observation errors need not be white or independent.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from mcg import Config, motion_path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'research/FP_NATIVE_B_CAUSAL_ABLATION_20261108'))
from fp_ns_ablation import load_original_replay, identical_input_condition

RCOND = 1e-3
WINDOW_STEPS = 25
EXACT_STRIDE = 50


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def motion_group(distance, rotation_deg):
    if distance < .02:
        return 'LOW_DISTANCE_LOW_ROTATION' if rotation_deg <= 2. else 'LOW_DISTANCE_ROTATING'
    return 'TRANSLATING_LOW_ROTATION' if rotation_deg <= 2. else 'TRANSLATING_ROTATING'


def summarize(rows):
    fraction = np.array([r['perpendicular_energy_fraction'] for r in rows if r['perpendicular_energy_fraction'] is not None])
    exact = [r for r in rows if r['exact_status'] == 'EVALUATED']
    def quantiles(values):
        return np.quantile(values, [.05, .5, .95, 1.]).tolist() if len(values) else None
    return {'n_windows': len(rows),
        'rank_counts': {str(rank): sum(r['operational_rank'] == rank for r in rows) for rank in range(5)},
        'unbounded_fit_exceeds_nuisance_bounds_n': sum(r['unbounded_fit_outside_bounds'] for r in rows),
        'unbounded_fit_exceeds_nuisance_bounds_fraction': sum(r['unbounded_fit_outside_bounds'] for r in rows)/len(rows) if rows else None,
        'perpendicular_energy_fraction_p05_p50_p95_max': quantiles(fraction),
        'sum_residual_energy': sum(r['residual_energy'] for r in rows),
        'sum_perpendicular_energy': sum(r['perpendicular_energy'] for r in rows),
        'exact_stride_selected_n': sum(r['exact_status'] != 'NOT_SELECTED' for r in rows),
        'exact_success_n': len(exact),
        'exact_nonlinearity_rms_sigma_p05_p50_p95_max': quantiles([r['exact_minus_local_rms_sigma'] for r in exact]),
        'exact_residual_energy_fraction_p05_p50_p95_max': quantiles([r['exact_energy_fraction'] for r in exact if r['exact_energy_fraction'] is not None]),
        'exact_cost_worse_than_unmodified_reference_n': sum(r['exact_energy'] > r['residual_energy'] for r in exact),
        'exact_failed_or_nonfinite_n': sum(r['exact_status'] not in ('EVALUATED', 'NOT_SELECTED') for r in rows)}


def detailed_diagnostics(rows):
    exact_groups = {}; components = {}
    columns = ('normalized_dx', 'normalized_dy', 'normalized_dyaw', 'normalized_dbg')
    for route in ('R2', 'R4', 'R5'):
        rr = [r for r in rows if r['route'] == route]
        u = np.asarray([[float(r[key]) for key in columns] for r in rr])
        components[route] = {name: {
            'outside_n': int((abs(u[:, j]) > 1.+1e-9).sum()),
            'outside_fraction': float((abs(u[:, j]) > 1.+1e-9).mean()),
            'abs_normalized_p50_p95_max': np.quantile(abs(u[:, j]), [.5, .95, 1.]).tolist()}
            for j, name in enumerate(('dx', 'dy', 'yaw', 'bg'))}
        exact_groups[route] = {}
        for label in ('inside_bounds', 'outside_bounds'):
            subset = [r for r in rr if r['exact_status'] == 'EVALUATED' and
                      (str(r['unbounded_fit_outside_bounds']) == 'True') == (label == 'outside_bounds')]
            exact_groups[route][label] = {'n': len(subset),
                'cost_worse_than_reference_n': sum(float(r['exact_energy']) > float(r['residual_energy']) for r in subset),
                'median_exact_vs_reference_energy': float(np.median([float(r['exact_energy_fraction']) for r in subset])) if subset else None,
                'median_local_vs_reference_energy': float(np.median([float(r['perpendicular_energy_fraction']) for r in subset])) if subset else None}
    return exact_groups, components


def run(repo, assets, archives, out):
    if out.exists():
        raise FileExistsError('NEW_OUTPUT_REQUIRED: '+str(out))
    out.mkdir(parents=True)
    started = time.time()
    r45, core, online, model, source_hashes = load_original_replay(repo)
    cfg = Config(); bounds = np.asarray(cfg.bounds)
    rows = []; receipts = {}; checks = {}
    for route in ('R2', 'R4', 'R5'):
        op = assets/f'{route}_B0_Full_10__online.npz'
        tp = archives/route/f'{route}_B_FROZEN.npz'
        with np.load(op, allow_pickle=False) as f:
            on = {key: f[key] for key in ('Hrf', 'z', 'muMB', 't', 'pose_id', 'ds', 'gy', 'dt')}
        with np.load(tp, allow_pickle=False) as f:
            prior, Rbase = f['prior'], f['Reff']
        expected = json.loads((archives/route/'SHA256.json').read_text())[tp.name]
        assert sha(tp) == expected
        with np.load(r45.ROOT/'R45_RUN_001'/f'{route}_TRACE.npz', allow_pickle=False) as f:
            assert np.array_equal(f['t'], on['t']) and np.array_equal(f['pose_id'], on['pose_id'])
            assert np.max(abs(f['prior'][:, 0]-prior)) <= 1e-10
        assert np.max(abs(np.diff(on['t'])-.2)) < 1e-12
        _, _, _, zB = identical_input_condition(on, r45, route+'_B0_Full_10')
        controls = np.column_stack([on[key] for key in ('ds', 'gy', 'dt')])
        max_orthogonality = 0.; max_identity = 0.
        for k in range(WINDOW_STEPS, len(on['t'])):
            a = k-WINDOW_STEPS
            ctrl = controls[a:k+1]
            anchor = prior[a].copy()
            q, T = motion_path(core, anchor, ctrl)
            h, H = model.batch(q, r45.SPEC)
            J = np.einsum('nci,nij->ncj', H, T)*bounds[None, None, :]
            L = np.linalg.cholesky(Rbase[a:k])
            A = np.linalg.solve(L, J[:-1]).reshape(-1, 4)
            residual = np.linalg.solve(L, (zB[a:k]-h[:-1]-on['muMB'][a:k])[..., None])[..., 0].ravel()
            u, _, rank, sv = np.linalg.lstsq(A, residual, rcond=RCOND)
            fitted = A@u; perpendicular = residual-fitted
            # Exact orthogonality applies to the retained SVD subspace only.
            U, ss, _ = np.linalg.svd(A, full_matrices=False)
            retained = ss > ss[0]*RCOND if len(ss) and ss[0] else np.zeros(len(ss), bool)
            orthogonality = float(np.max(abs(U[:, retained].T@perpendicular))) if retained.any() else 0.
            identity = float(abs(residual@residual-fitted@fitted-perpendicular@perpendicular))
            max_orthogonality = max(max_orthogonality, orthogonality)
            max_identity = max(max_identity, identity/max(1., float(residual@residual)))
            energy = float(residual@residual); pe = float(perpendicular@perpendicular)
            distance = float(np.sum(abs(ctrl[1:, 0])))
            rotation = float(np.degrees(np.sum(abs(ctrl[1:, 1]-anchor[3]*ctrl[1:, 2]))))
            row = {'route': route, 'k': k, 'anchor_index': a, 'history_end': k-1, 't_s': float(on['t'][k]),
                'span_s': float(on['t'][k]-on['t'][a]), 'history_rows': k-a,
                'motion_stratum': motion_group(distance, rotation), 'distance_m': distance, 'cumulative_abs_rotation_deg': rotation,
                'operational_rank': int(rank), 'numeric_rank': int(np.linalg.matrix_rank(A)),
                'sv1': float(sv[0]), 'sv2': float(sv[1]), 'sv3': float(sv[2]), 'sv4': float(sv[3]),
                'normalized_dx': float(u[0]), 'normalized_dy': float(u[1]), 'normalized_dyaw': float(u[2]), 'normalized_dbg': float(u[3]),
                'unbounded_fit_outside_bounds': bool(np.max(abs(u)) > 1.+1e-9),
                'residual_energy': energy, 'perpendicular_energy': pe,
                'perpendicular_energy_fraction': pe/energy if energy > 0 else None,
                'orthogonality_retained_subspace_maxabs': orthogonality,
                'exact_status': 'NOT_SELECTED', 'exact_energy': None, 'exact_energy_fraction': None,
                'exact_minus_local_rms_sigma': None, 'exact_error': None}
            if (k-WINDOW_STEPS) % EXACT_STRIDE == 0:
                try:
                    qe, _ = motion_path(core, anchor+bounds*u, ctrl)
                    he, _ = model.batch(qe, r45.SPEC, gradient=False)
                    re = np.linalg.solve(L, (zB[a:k]-he[:-1]-on['muMB'][a:k])[..., None])[..., 0].ravel()
                    assert np.isfinite(re).all()
                    ee = float(re@re)
                    linearity = float(np.sqrt(np.mean((re-perpendicular)**2)))
                    row.update(exact_status='EVALUATED', exact_energy=ee,
                               exact_energy_fraction=ee/energy if energy > 0 else None,
                               exact_minus_local_rms_sigma=linearity)
                except Exception as e:
                    row.update(exact_status='FAILED_OR_NONFINITE', exact_error=type(e).__name__+': '+str(e))
            rows.append(row)
            if (k-WINDOW_STEPS) % 200 == 0:
                print('PROJECTION_PROGRESS', route, k, '/', len(on['t']), flush=True)
        checks[route] = {'retained_subspace_orthogonality_maxabs': max_orthogonality,
                         'relative_energy_decomposition_maxabs': max_identity}
        assert max_orthogonality < 1e-7 and max_identity < 1e-10
        receipts[route] = {'online_sha256': sha(op), 'B_archive_sha256': sha(tp), 'n_windows': len(on['t'])-WINDOW_STEPS}
        dump(out/'PROGRESS.json', {'completed_routes': list(receipts), 'n_windows': len(rows)})
    with (out/'PROJECTION_WINDOWS.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    exact_groups, components = detailed_diagnostics(rows)
    dump(out/'EXACT_BOUND_STRATA.json', exact_groups)
    dump(out/'NUISANCE_BOUND_COMPONENTS.json', components)
    summaries = {'pooled': summarize(rows), 'by_route': {}, 'by_route_motion': {}}
    for route in ('R2', 'R4', 'R5'):
        group = [r for r in rows if r['route'] == route]
        summaries['by_route'][route] = summarize(group)
        summaries['by_route_motion'][route] = {m: summarize([r for r in group if r['motion_stratum'] == m]) for m in sorted({r['motion_stratum'] for r in group})}
    result = {'status': 'EXECUTED_LOCAL_IDENTIFIABILITY_DIAGNOSTIC', 'n_windows': len(rows), 'elapsed_s': time.time()-started,
        'scope': 'B_FROZEN R2/R4/R5 B0 Full seed10; 5 s immutable pre-RF anchor windows, no evaluator/clean RF input',
        'fit': {'history_only': True, 'current_target_excluded': True, 'nuisance': ['anchor_px', 'anchor_py', 'absolute_yaw', 'constant_gyro_bias'],
                'normalization_bounds': bounds.tolist(), 'whitening': 'Archived B Reff per history row, fixed during local projection',
                'rank_rcond': RCOND, 'unbounded': True, 'new_Q_or_calibration': False},
        'exact_check': {'schedule': 'every 50th eligible window per route, starting at k=25', 'u_clipped': False,
                        'same_unbounded_solution': True, 'sample_not_full_nonlinear_coverage': True},
        'motion_strata': {'distance_threshold_m': .02, 'cumulative_rotation_threshold_deg': 2., 'uses_evaluator_truth': False},
        'interpretation': ['Energy removed by a local nuisance projection is confounded with allowed pose/bias changes; it is not recovered s or correct pose.',
            'Unbounded normalized nuisance outside +/-1 is infeasible for B-MCG bounds.',
            'Exact same-u residual can be worse than the local projection because SourceFFD is nonlinear/nonsmooth.',
            'Residual energy is descriptive, not chi-square or a calibrated independent-noise likelihood.',
            'Overlapping windows and shared route noise prefix prevent independent-sample confidence claims.'],
        'input_receipts': receipts, 'original_source_hashes': source_hashes, 'checks': checks, 'summary': summaries}
    assert len(rows) == 3061
    dump(out/'PROJECTION_SUMMARY.json', result)
    print(json.dumps({'status': result['status'], 'n_windows': len(rows), 'summary': summaries['by_route']}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('repo', 'assets', 'archives', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    run(a.repo, a.assets, a.archives, a.out)
