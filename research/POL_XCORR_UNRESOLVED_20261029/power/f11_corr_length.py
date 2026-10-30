#!/usr/bin/env python3
"""F-11 support: label-free spatial correlation length of baseline (M0/G5) features along timeline drive.

Reads ONLY keys + G5 columns of the committed UM_POSE_TABLE (Full channel) and the P0 POSE_ALIGNMENT table.
For each case and feature: ACF over travelled distance within drive segments (lag bins of 0.04 m),
correlation length ell_e = first lag where ACF < 1/e. No label column is read.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

UM = 'research/PJ_DS_USAGE_MAP_20261021/results/UM_POSE_TABLE.csv.gz'
POSE = 'research/POL_XCORR_UNRESOLVED_20261029/results_p0/run_40867521966/POSE_ALIGNMENT.csv'
FEATS = ['abs_s_fp', 'jones_diversity', 'freq_s_var', 'delay_rms_ns', 'tap_pol_var80', 'early4', 's_diff4', 'log_fp_power']


def ell_e(x, d, seg, step=0.04, maxlag_m=6.0):
    lags = np.arange(1, int(maxlag_m / step) + 1)
    out = []
    for L in lags:
        num = 0.0; den = 0.0; n = 0
        for s in np.unique(seg):
            m = seg == s; xs = x[m]
            if len(xs) <= L:
                continue
            a = xs[:-L]; b = xs[L:]
            num += np.sum((a - a.mean()) * (b - b.mean())); den += np.sqrt(np.sum((a - a.mean()) ** 2) * np.sum((b - b.mean()) ** 2)); n += 1
        out.append(num / den if den > 0 else np.nan)
    acf = np.array(out)
    below = np.where(acf < np.exp(-1))[0]
    return (float(lags[below[0]] * step) if len(below) else float('nan')), acf


def main(root, out):
    root = Path(root); out = Path(out); out.mkdir(parents=True, exist_ok=False)
    U = pd.read_csv(root / UM, usecols=['case', 'pose_id'] + FEATS)
    P = pd.read_csv(root / POSE, usecols=['case', 'pose_id', 'stratum', 'phase', 'travelled_m', 'block_id'])
    D = P[(P.stratum == 'TIMELINE') & (P.phase == 'drive')].merge(U, on=['case', 'pose_id'], validate='one_to_one')
    rows = []
    for case, g in D.groupby('case'):
        g = g.sort_values('pose_id'); seg = g.block_id.str.split('/').str[2].astype(int).to_numpy()
        step = float(np.median(np.diff(g.travelled_m.to_numpy())[np.diff(seg) == 0]))
        for f in FEATS:
            x = g[f].to_numpy(float)
            if f in ('jones_diversity', 'freq_s_var', 'tap_pol_var80', 's_diff4'):
                x = np.log(np.maximum(x, 1e-12))
            le, _ = ell_e(x, g.travelled_m.to_numpy(), seg, step=step)
            rows.append({'case': case, 'feature': f, 'ell_1e_m': le, 'step_m': step, 'n': len(g)})
    T = pd.DataFrame(rows); T.to_csv(out / 'F11_CORR_LENGTH.csv', index=False)
    S = T.groupby('feature').ell_1e_m.describe(percentiles=[.5])[['min', '50%', 'max']]
    S.to_csv(out / 'F11_CORR_LENGTH_SUMMARY.csv')
    meta = {'label_free': True, 'inputs': {UM: hashlib.sha256((root / UM).read_bytes()).hexdigest(),
                                           POSE: hashlib.sha256((root / POSE).read_bytes()).hexdigest()},
            'columns_read': ['case', 'pose_id'] + FEATS, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'overall_median_ell_m': float(T.ell_1e_m.median())}
    (out / 'F11_CORR_LENGTH_MANIFEST.json').write_text(json.dumps(meta, indent=1))
    print(S.round(3).to_string()); print('overall median', meta['overall_median_ell_m'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
