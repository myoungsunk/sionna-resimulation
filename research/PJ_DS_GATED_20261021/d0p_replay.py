#!/usr/bin/env python3
"""Recursive replay with POWER refitted on swapped labels (GT / d0), plus R0 (mu=0, R0) GT-free floor."""
from __future__ import annotations
import argparse, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
from p3_rf_adapter4 import R0

PARAMS = Path(os.environ['PJ_PARAMS'])
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case)
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    PP = pd.read_csv(next(PARAMS.rglob('D0P_PARAMS.csv.gz'))); PP = PP[PP.case == a.case]
    arms = ['R0'] + [f'{v}|{m}' for v in ['P_GT_ALL', 'P_GT_SUB', 'P_D0_BASE', 'P_D0_J4'] for m in ['POWER_DIAG', 'POWER1']]; J = len(arms)
    model = V.SourceFFD(); rows = []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']; n = len(t)
        b_true = math.radians(V.BIAS_LEVELS[bias])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        MU = np.zeros((n, J, 2)); RR = np.empty((n, J, 2, 2)); RR[:, 0] = np.asarray(R0, float)[None]
        for j, nm in enumerate(arms[1:], start=1):
            v, m = nm.split('|'); p = PP[(PP.channel == ch) & (PP.variant == v) & (PP.model == m)].set_index('pose_id').loc[ids]
            MU[:, j, 0] = p.mu_r; MU[:, j, 1] = p.mu_s; RR[:, j, 0, 0] = p.Vr; RR[:, j, 1, 1] = p.Vs; RR[:, j, 0, 1] = RR[:, j, 1, 0] = p.Crs
        mu_ref, _ = V.base_params(par, a.case, ch, ids, 'POWER_DIAG'); qa_mu = float(np.max(np.abs(mu_ref - MU[:, 1])))
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool)
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case)
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR[k], RR[k], np.ones(J)); X[k] = x; C[k] = P; acc[k] = yes
        sc = V.MC.score(X, C, t, truth, b_true); m = t >= 30
        anc = np.asarray(case['anchor'], float); dz = anc[2] - float(case['robot_z_m'])
        dtrue = np.sqrt((truth[:, 0] - anc[0]) ** 2 + (truth[:, 1] - anc[1]) ** 2 + dz ** 2)
        uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True)
        for j, nm in enumerate(arms):
            exy = X[:, j, :2] - truth[:, :2]; dhat = np.sqrt((X[:, j, 0] - anc[0]) ** 2 + (X[:, j, 1] - anc[1]) ** 2 + dz ** 2)
            rows.append({'case': a.case, 'bias': bias, 'channel': ch, 'arm': nm, **sc[j], 'accepted_fraction': float(acc[m, j].mean()), 'qa_mu_vs_oof': qa_mu,
                         'range_err_rmse_cm': float(np.sqrt(np.mean((dhat - dtrue)[m] ** 2)) * 100), 'radial_rmse_cm': float(np.sqrt(np.mean(np.sum(exy * uh, axis=1)[m] ** 2)) * 100),
                         'xy_rmse_cm': float(np.sqrt(np.mean(np.sum(exy ** 2, axis=1)[m])) * 100)})
        print('D0P_REPLAY_DONE', stem, flush=True)
    pd.DataFrame(rows).to_csv(V.OUT / f'{a.case}_D0P_SCORES.csv', index=False); print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
