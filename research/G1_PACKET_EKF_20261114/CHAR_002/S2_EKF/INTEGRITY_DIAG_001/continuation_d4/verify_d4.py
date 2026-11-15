"""Reaggregate signed-residual bin statistics from authenticated D0/D2 arrays."""

import argparse
from pathlib import Path

import numpy as np

from run_d4 import HERE, LOCK, authenticate, read, sha
from d1_shuffle import dump, verify_file


def verify(contract, out):
    lock = authenticate(contract)
    from replay_s2 import read_npz

    execution = read(out / 'EXECUTION.json')
    if execution['exit_code'] != 0 or execution['contract_sha256'] != sha(contract):
        raise ValueError('D4 execution or contract mismatch')
    for name, digest in execution['outputs'].items():
        verify_file({'path': str(out / name), 'sha256': digest})
    results = read(out / 'RESULTS.json')
    counts = {}
    for mode in ('horizontal', 'slant_sensitivity'):
        data = results[mode]
        bins = {(r['anchor'], r['bias'], r['route'], r['channel'], r['distance_min_m']): r for r in data['bins']}
        if len(bins) != 8 * lock['scope']['n_expected']:
            raise ValueError('Missing or duplicate bin rows')
        for cell in lock['cells']:
            key = tuple(cell[k] for k in ('anchor', 'bias', 'route'))
            anchor = lock['anchors'][key[0]]
            evaluator, d0, d2 = (read_npz(verify_file(cell[k])) for k in ('evaluator', 'd0_trace', 'd2_residual_check'))
            if any(not np.array_equal(evaluator[k], trace[k]) for trace in (d0, d2) for k in ('t', 'pose_id')):
                raise ValueError(f'Packet coordinate mismatch {key}')
            xy = evaluator['truth'][:, :2] - anchor[:2]
            dz = (lock['scope']['robot_z_m'] - anchor[2]) if mode == 'slant_sensitivity' else 0.
            distance = np.sqrt(xy[:, 0]**2 + xy[:, 1]**2 + dz**2)
            epsilon = d2['truth_residual_r_s']
            for low, high in lock['thresholds']['distance_bins_m']:
                in_bin = (distance >= low) & (distance < (np.inf if high is None else high))
                for c, channel in enumerate(('r', 's')):
                    row = bins[(*key, channel, low)]
                    residual = epsilon[in_bin, c]
                    if len(residual) != row['n']:
                        raise ValueError(f'Bin count mismatch: {key, channel, low}')
                    if len(residual):
                        sigma = np.sqrt(d0['Reff'][in_bin, c, c].mean())
                        expected = [residual.mean(), np.linalg.norm(residual)/np.sqrt(len(residual)),
                                    np.mean((residual-residual.mean())**2), sigma, abs(residual.mean())/sigma]
                        fields = ['signed_mean', 'rms', 'centered_variance', 'sqrt_mean_R_eff', 'abs_mean_over_sigma']
                        if not np.allclose(expected, [row[k] for k in fields], atol=1e-12, rtol=0.):
                            raise ValueError(f'Bin moment mismatch: {key, channel, low}')
        for anchor, by_bias in data['H3'].items():
            for bias, by_channel in by_bias.items():
                for name, group in by_channel.items():
                    supported = [row for row in bins.values() if (row['anchor'], row['bias'], row['channel']) ==
                                 (anchor, bias, name) and row['n'] >= 30 and row['n_eff'] >= 5]
                    excess = sum(row['abs_mean_over_sigma'] > .5 for row in supported)
                    verdict = ('H3_INCONCLUSIVE' if len(supported) < 4 else
                               'H3_SUPPORTED' if 4*excess >= len(supported) else 'H3_NOT_SUPPORTED')
                    if (group['supported_bins'], group['above_threshold_bins'], group['status']) != (len(supported), excess, verdict):
                        raise ValueError(f'H3 count mismatch: {anchor, bias, name}')
        counts[mode] = len(bins)
    dump(out.parent / 'VERIFICATION.json', {'status': 'PASS_REAGGREGATION', 'role': 'IMPLEMENTER_SELF_CHECK',
         'contract_sha256': sha(contract), 'execution_sha256': sha(out / 'EXECUTION.json'),
         'verifier_sha256': sha(Path(__file__)), 'checked_bin_rows': counts})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, default=LOCK)
    parser.add_argument('--out', type=Path, default=HERE / 'run_01')
    args = parser.parse_args()
    verify(args.contract, args.out)
