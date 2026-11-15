"""Recompute point scores and summarize clipping and KI history from saved traces."""

from pathlib import Path
import sys

import numpy as np

from run_structure import HERE, LOCK, authenticate, read, sha
from d0_d5 import identity
from d1_shuffle import dump


def raw_metrics(trace, truth):
    from scipy.stats import chi2

    d = trace['x'][:, :3] - truth
    d[:, 2] = np.arctan2(np.sin(d[:, 2]), np.cos(d[:, 2]))
    P = trace['P'][:, :3, :3]
    n3 = np.einsum('ni,nij,nj->n', d, np.linalg.inv(P), d)
    xy = d[:, :2]
    n2 = np.einsum('ni,nij,nj->n', xy, np.linalg.inv(P[:, :2, :2]), xy)
    return np.column_stack((np.rad2deg(d[:, 2])**2, (xy**2).sum(axis=1)*1e4, n3,
                            n3 <= chi2.ppf(.95, 3), n2 <= chi2.ppf(.95, 2),
                            abs(d[:, 2]) <= 1.96 * np.sqrt(P[:, 2, 2])))


def verify(out, lock_path):
    lock, _ = authenticate(lock_path)
    from replay_s2 import read_npz

    exec_path = out / 'EXECUTION.json'
    execution = read(exec_path)
    if (execution['status'] != 'PASS_EXECUTION' or execution['exit_code'] != 0 or
            execution['contract_sha256'] != sha(lock_path)):
        raise ValueError('Execution is incomplete or used a different contract')
    for file, digest in execution['outputs'].items():
        if sha(out / file) != digest:
            raise ValueError(f'Output hash mismatch: {file}')

    result = read(out / 'RESULTS.json')
    implementation = read(out / 'IMPLEMENTATION_CHECKS.json')
    parity_max = max(error['max_normalized_error'] for group in implementation['identity'].values()
                     for route in group.values() for switch in route.values() for error in switch.values())
    evidence = {'status': 'PASS_REAGGREGATION', 'role': 'IMPLEMENTER_SELF_CHECK',
                'contract_sha256': sha(lock_path), 'execution_sha256': sha(exec_path),
                'verifier_sha256': sha(Path(__file__)), 'identity_max_normalized_error': parity_max,
                'B_B0': {}}
    score_rows = {arm: [] for arm in result['metrics']['pooled']}
    for cell in lock['cells']:
        route = cell['route']
        packet = read_npz(cell['online']['path'])
        evaluator = read_npz(cell['evaluator']['path'])
        base = read_npz(cell['fixed_gate_trace']['path'])
        route_data = evidence['B_B0'][route] = {}
        for arm in score_rows:
            if arm == 'E0':
                trace = base
            elif arm == 'LORO':
                trace = read_npz(cell['loro_trace']['path'])
            else:
                trace = read_npz(out / f'{route}_{arm}_trace.npz')
            identity(evaluator, trace, ('t', 'pose_id'))
            identity(base, trace, ('mask',))
            rows = raw_metrics(trace, evaluator['truth'])
            score_rows[arm].append(rows)
            verify_metrics(rows, result['metrics']['routes'][route][arm])
            route_data[arm] = {'heading95_hits': int(rows[:, 5].sum()),
                               'heading_sigma_rms_deg': float(np.rad2deg(np.sqrt(trace['P'][:, 2, 2].mean())))}
            if arm in ('SC', 'KI'):
                clipped = trace['q'] - trace['q_eff']
                distance_support = cell['kernel']['q_knots_m']
                route_data[arm].update(
                    clipping_count_by_channel=(clipped > 0.).sum(axis=0).tolist(),
                    clipping_max_q_difference_by_channel=clipped.max(axis=0).tolist(),
                    clipping_max_removed_variance_by_channel=(clipped * trace['R_ref'].diagonal(axis1=1, axis2=2)).max(axis=0).tolist(),
                    outside_q_knot_bounds=int(((trace['rho_prior'] < distance_support[0]) |
                                               (trace['rho_prior'] > distance_support[-1])).sum()))
            if arm == 'KI':
                stationary = np.r_[False, (packet['ds'][1:] == 0.) & (np.diff(trace['yaw_arc']) == 0.)]
                cap = trace['history_n'] == lock['KI']['max_accepted_history']
                route_data[arm]['strict_stationary'] = {'n': int(stationary.sum()),
                    'cap_fraction': float(cap[stationary].mean()) if stationary.any() else None}
    for arm, routes in score_rows.items():
        verify_metrics(np.concatenate(routes), result['metrics']['pooled'][arm])
    rms_metrics = ('heading_rmse_deg', 'xy_rmse_cm')
    evidence['rmse_ratio_vs_original_E0'] = {
        name: {arm: {metric: stats[metric] / group['E0'][metric] for metric in rms_metrics}
               for arm, stats in group.items() if arm != 'E0'}
        for name, group in (result['metrics']['routes'] | {'pooled': result['metrics']['pooled']}).items()}
    dump(out.parent / 'VERIFICATION.json', evidence)


def verify_metrics(rows, reported):
    names = ('heading_rmse_deg', 'xy_rmse_cm', 'mean_nees3', 'pose95_coverage', 'xy95_coverage', 'heading95_coverage')
    values = rows.mean(axis=0)
    values[:2] = np.sqrt(values[:2])
    if len(rows) != reported['n'] or not np.allclose(values, [reported[key] for key in names], rtol=0, atol=1e-11):
        raise ValueError('Raw evaluator score does not match the published point estimate')


if __name__ == '__main__':
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'run_01'
    verify(folder, LOCK)
