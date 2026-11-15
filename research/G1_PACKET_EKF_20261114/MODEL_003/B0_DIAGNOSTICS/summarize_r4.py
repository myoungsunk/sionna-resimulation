"""Summarize the exact R4 replay and diagnostic controls in G-T1 B0."""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def rms(a):
    return float(np.sqrt(np.nanmean(np.asarray(a)**2)))


def angle(a):
    return np.rad2deg(np.arctan2(np.sin(a), np.cos(a)))


def moments(a):
    return dict(mean=float(np.nanmean(a)), std=float(np.nanstd(a)), rms=rms(a))


def corr(a, b):
    finite = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[finite], b[finite])[0, 1])


def push(bins, group, **arrays):
    for label, array in arrays.items():
        bins[group][label].append(np.ravel(array))


def join(group):
    return {k: np.concatenate(v) for k, v in group.items()}


def main():
    base = Path(__file__).parent
    folds = sorted((base/'r4_trace').glob('*.npz'))
    assert len(folds) == 18, [p.name for p in folds]
    bins = defaultdict(lambda: defaultdict(list))
    residuals = defaultdict(lambda: defaultdict(list))
    range_sigmas = {}
    max_error = 0.
    for f in folds:
        prefix, anchor, path = f.stem.removesuffix('_B0').split('_', maxsplit=2)
        case = f'{prefix}_{anchor}'
        with np.load(f, allow_pickle=False) as obj:
            d = {k: obj[k] for k in obj.files}
        cp = d['cp']
        trace = d['observed']
        dr = angle(d['dr'])
        r4 = angle(trace[cp, :, 8])
        los = angle(d['los'][cp, :, 8])
        ideal = angle(d['ideal'][cp, :, 8])
        direct = np.rad2deg(trace[cp, :, 9])
        drift = np.rad2deg(trace[cp, :, 10])
        psi_sigma = np.rad2deg(trace[cp, :, 6])
        bias = np.rad2deg(trace[cp, :, 5])
        assert np.max(np.abs(angle(np.deg2rad(r4-dr-direct-drift)))) < 3e-9
        max_error = max(max_error, float(d['decomposition_max_rad']))
        series = dict(dr=dr, r4=r4, los=los, ideal=ideal, direct=direct, drift=drift, psi_sigma=psi_sigma, bias=bias)
        for group in ('all', case, path, f'{case}/{path}'):
            push(bins, group, **series)
        for phase in np.unique(d['streams'][cp]):
            take = d['streams'][cp] == phase
            push(bins, f'{case}/{path}/{phase}', **{k: v[take] for k,v in series.items()})
            push(bins, f'{path}/{phase}', **{k: v[take] for k,v in series.items()})

        q = d['observations']
        ion = d['pose_range']-d['true_range']
        tap = d['clean_los']-(d['pose_range']+d['offset'])
        mp = d['clean_full']-d['clean_los']
        noise = q-d['clean_full'][:, None]
        rho = d['true_range']
        z = q-(rho[:, None]+d['offset'])
        z_los = d['obs_los']-(rho[:, None]+d['offset'])
        assert np.nanmax(np.abs(z-ion[:, None]-tap[:, None]-mp[:, None]-noise)) < 2e-13
        biased = dict(res=z, res_los=z_los, pose=ion, los_tap=tap, multipath=mp, thermal=noise,
                      accepted=trace[...,1], detected=np.isfinite(q),
                      los_accepted=d['los'][...,1], los_detected=np.isfinite(d['obs_los']),
                      ideal_accepted=d['ideal'][...,1])
        same_pose = d['ids'][1:] == d['ids'][:-1]
        for group in ('all', case, path):
            push(residuals, group, **biased)
            for label, select in (('same_pose',same_pose), ('different_pose', ~same_pose)):
                push(residuals, group, **{f'{label}_lag1_a':z[:-1][select], f'{label}_lag1_b':z[1:][select]})
            push(residuals, group, lag1_a=z[:-1], lag1_b=z[1:],
                 los_lag1_a=z_los[:-1], los_lag1_b=z_los[1:])
        for lo, hi in ((0, 3), (3, 6), (6, 10), (10, np.inf)):
            take = (rho >= lo) & (rho < hi)
            if take.any():
                for group in (f'all/{lo}–{hi}m',f'{case}/{lo}–{hi}m'):
                    push(residuals, group, **{k:v[take] for k,v in biased.items()})
        range_sigmas[f'{case}/{path}'] = float(d['range_sigma'])

    summary = {}
    for key, values in bins.items():
        g = join(values)
        paired = angle(np.deg2rad(g['r4']-g['dr']))
        summary[key] = dict(n_unique=len(paired), **{f'{m}_rmse_deg':rms(g[m]) for m in ('dr','r4','los','ideal')},
                            paired_change_deg=moments(paired), direct_deg=moments(g['direct']), drift_deg=moments(g['drift']),
                            direct_drift_corr=corr(g['direct'], g['drift']), bias_degps=moments(g['bias']),
                            posterior_heading_sigma_deg=moments(g['psi_sigma']),
                            excess_squares_deg2=float(np.sum(g['r4']**2-g['dr']**2)))
    assert summary['all']['n_unique'] == 8820
    by_range = {}
    for key, values in residuals.items():
        g = join(values)
        out = {k:moments(g[k]) for k in ('res','res_los','pose','los_tap','multipath','thermal')}
        out.update(n_packets=len(g['pose']), det_rate=float(np.mean(g['detected'])),
                   accepted_given_detection=float(np.mean(g['accepted'][g['detected']])),
                   los_det_rate=float(np.mean(g['los_detected'])),
                   los_accepted_given_detection=float(np.mean(g['los_accepted'][g['los_detected']])),
                   ideal_accepted_given_detection=float(np.mean(g['ideal_accepted'][g['detected']])),
                   detectable_multipath_tap_change_rate=float(np.mean(np.abs(g['multipath']) > 1e-10)))
        for label in ('lag1', 'los_lag1', 'same_pose_lag1', 'different_pose_lag1'):
            if f'{label}_a' in g and len(g[f'{label}_a']) > 1:
                out[label] = dict(n=int(np.sum(np.isfinite(g[f'{label}_a']) & np.isfinite(g[f'{label}_b']))),
                                  corr=corr(g[f'{label}_a'], g[f'{label}_b']))
        by_range[key] = out

    report = dict(n_folds=len(folds), exact_checkpoint_rows=2*summary['all']['n_unique'], max_decomposition_rad=max_error,
                  range_sigmas_m=range_sigmas, heading=summary, range=by_range)
    (base/'R4_DIAGNOSTIC_SUMMARY.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+'\n',
                                                   encoding='utf-8')
    print(json.dumps(summary['all'], indent=2))
    print(json.dumps(by_range['all'], indent=2))


if __name__ == '__main__':
    main()
