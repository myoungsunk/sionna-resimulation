#!/usr/bin/env python3
"""Position/update-wise switching replay: range variance inflated (large |ds|) always; polarization
variance deflated (small |ds|) only on packets where a precomputed selector is on. No fitting here."""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
import d1_core as D

SELECTORS = ['SW_ORACLE_SEG', 'SW_EOS3', 'SW_POSMAP', 'SW_I_ABSDS_40', 'SW_I_PUSH_40']
ARMS = ['BASE', 'INFL_R', 'MIX_IR_DS'] + SELECTORS
CONDITIONS = [('B0', 'full'), ('L2', 'full')]
DEG = 180 / math.pi


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    T = V.build_table(); tr = T[(T.channel == 'full') & (T.route != held)]
    two, five = V.calibrations(tr)
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    DEC = pd.read_csv(HERE / 'results_series' / 'SWITCH_DECISIONS.csv.gz'); DEC = DEC[DEC.case == a.case]
    model = V.SourceFFD(); rows = []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n, J = len(t), len(ARMS); b_true = math.radians(V.BIAS_LEVELS[bias])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        tc = T[(T.case == a.case) & (T.channel == ch)].set_index('pose_id').loc[ids]; aa = tc.a.to_numpy()
        dec = DEC[DEC.bias == bias].sort_values('k'); assert len(dec) == n and np.array_equal(dec.pose_id.to_numpy(), ids)
        mu0, R0b = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        MU = np.repeat(mu0[:, None, :], J, axis=1); RR = np.repeat(R0b[:, None], J, axis=1).copy()
        hi_r = V.factors(aa, two, five, 'HI', 'r'); lo_s = V.factors(aa, two, five, 'LO', 's'); sw = {}
        for j, arm in enumerate(ARMS):
            if arm == 'BASE': continue
            RR[:, j, 0, 0] *= hi_r
            on = np.ones(n, bool) if arm == 'MIX_IR_DS' else (np.zeros(n, bool) if arm == 'INFL_R' else dec[arm].to_numpy(bool))
            RR[:, j, 1, 1] *= np.where(on, lo_s, 1.0); sw[arm] = on
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4))
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case)
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P
        sc = V.MC.score(X, C, t, truth, b_true); m = t >= 30
        anc = np.asarray(case['anchor'], float); dz = anc[2] - float(case['robot_z_m'])
        dtrue = np.sqrt((truth[:, 0] - anc[0]) ** 2 + (truth[:, 1] - anc[1]) ** 2 + dz ** 2)
        uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True); ut = np.column_stack([-uh[:, 1], uh[:, 0]])
        for j, arm in enumerate(ARMS):
            exy = X[:, j, :2] - truth[:, :2]; dhat = np.sqrt((X[:, j, 0] - anc[0]) ** 2 + (X[:, j, 1] - anc[1]) ** 2 + dz ** 2)
            rows.append({'case': a.case, 'route': held, 'bias': bias, 'arm': arm, **sc[j], 'switch_on_frac': float(sw[arm][m].mean()) if arm in sw else 0.0,
                         'range_err_rmse_cm': float(np.sqrt(np.mean(((dhat - dtrue)[m]) ** 2)) * 100),
                         'radial_rmse_cm': float(np.sqrt(np.mean(np.sum(exy * uh, axis=1)[m] ** 2)) * 100), 'tangential_rmse_cm': float(np.sqrt(np.mean(np.sum(exy * ut, axis=1)[m] ** 2)) * 100)})
        print('SW_DONE', stem, flush=True)
    pd.DataFrame(rows).to_csv(V.OUT / f'{a.case}_SW_SCORES.csv', index=False); print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
