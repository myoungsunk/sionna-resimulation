#!/usr/bin/env python3
"""Pass-1 label filters on Full B0: record prior innovations d = z - h(x^-) for
J4 (mu=0, R=R0 constant: GT-free) and BASE (POWER_DIAG, GT-trained). d_s = d0 (polarization), d_r = range analogue."""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
import d1_core as D
from p3_rf_adapter4 import R0

DEG = 180 / math.pi


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case)
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    model = V.SourceFFD(); arms = ['J4', 'BASE']; J = 2; out = []
    stem = f'{a.case}_full_B0'
    old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']; n = len(t)
    d = feat[(feat.case == a.case) & (feat.channel == 'full')].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
    mu0, R0b = V.base_params(par, a.case, 'full', ids, 'POWER_DIAG')
    MU = np.zeros((n, J, 2)); MU[:, 1] = mu0; RR = np.empty((n, J, 2, 2)); RR[:, 0] = np.asarray(R0, float)[None]; RR[:, 1] = R0b
    controls, x0 = V.build_positive_bias_controls(t, truth, 'B0')
    x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
    DD = np.empty((n, J, 2)); PE = np.empty((n, J)); ACC = np.empty((n, J), bool); X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4))
    for k in range(n):
        if k:
            for j in range(J):
                x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
        h, Hk = model.batch(x, case); DD[k] = z[k][None] - h; PE[k] = D.wrap(x[:, 2] - truth[k, 2]) * DEG
        x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR[k], RR[k], np.ones(J)); ACC[k] = yes; X[k] = x; C[k] = P
    sc = V.MC.score(X, C, t, truth, 0.)
    for j, nm in enumerate(arms):
        out.append(pd.DataFrame({'case': a.case, 'label_filter': nm, 'k': np.arange(n), 't_s': t, 'pose_id': ids, 'd_r': DD[:, j, 0], 'd_s': DD[:, j, 1],
                                 'e_r': d.e_r.to_numpy(), 'e_s': d.e_s.to_numpy(), 'prior_psi_err_deg': PE[:, j], 'acc': ACC[:, j],
                                 'label_filter_heading_rmse_deg': sc[j]['heading_rmse_deg']}))
    pd.concat(out).to_csv(V.OUT / f'{a.case}_D0P_LABELS.csv.gz', index=False, compression='gzip'); print('LABELS_DONE', a.case, [s['heading_rmse_deg'] for s in sc], flush=True)


if __name__ == '__main__':
    main()
