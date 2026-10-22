#!/usr/bin/env python3
"""(b) |d0|-based polarization variance inflation / polarization-only gate and (c) |d0|-based range variance inflation,
d0 = s - h_s(x^-) computed online from each arm's own prior. Bin edges / kappas / gate thresholds calibrated on the
other two routes (d0_var_calib.json). Also combined with delta-s range mean correction (MU_R_EXDS)."""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
import mu_recursive as MR

CAL = json.loads((HERE / 'd0_var_calib.json').read_text())
# arm: (range mean model, pol action, range action) ; pol action in {None,'INFL','GATE3','GATE5'} ; range action in {None,'INFL_D0','INFL_DS'}
ARMS = {'BASE': (None, None, None), 'B_INFL_S': (None, 'INFL', None), 'B_GATE3': (None, 'GATE3', None), 'B_GATE5': (None, 'GATE5', None),
        'C_INFL_R': (None, None, 'INFL_D0'), 'BC_INFL_RS': (None, 'INFL', 'INFL_D0'), 'BC_INFL_R_GATE5': (None, 'GATE5', 'INFL_D0'), 'INFL_R_DS': (None, None, 'INFL_DS'),
        'MU_R_EXDS': ('EXDS', None, None), 'MU_R+B_GATE5': ('EXDS', 'GATE5', None), 'MU_R+B_INFL_S': ('EXDS', 'INFL', None), 'MU_R+C_INFL_R': ('EXDS', None, 'INFL_D0'),
        'MU_R+BC_INFL_RS': ('EXDS', 'INFL', 'INFL_D0'), 'MU_R+BC_INFL_R_GATE5': ('EXDS', 'GATE5', 'INFL_D0')}
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]
BIG = 1e6


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); held = case['route']; cal = CAL[held]
    edges = np.asarray(cal['edges']); ks = np.asarray(cal['kappa_s']); kr = np.asarray(cal['kappa_r'])
    T = V.build_table(); two, five = V.calibrations(T[(T.channel == 'full') & (T.route != held)])
    FT = MR.feature_table(); tr = FT[(FT.channel == 'full') & (FT.route != held)]; m_r = MR.hgb(tr, MR.EXIST + MR.DS, 'e_r')
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    names = list(ARMS); J = len(names); model = V.SourceFFD(); rows = []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']; n = len(t)
        b_true = math.radians(V.BIAS_LEVELS[bias])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float); e = d[['e_r', 'e_s']].to_numpy(float)
        tc = T[(T.case == a.case) & (T.channel == ch)].set_index('pose_id').loc[ids]; hi_ds = V.factors(tc.a.to_numpy(), two, five, 'HI', 'r')
        fx = FT[(FT.case == a.case) & (FT.channel == ch)].set_index('pose_id').loc[ids]; pr = m_r.predict(fx[MR.EXIST + MR.DS])
        mu0, R0b = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        MU = np.repeat(mu0[:, None, :], J, axis=1).copy()
        for j, nm in enumerate(names):
            if ARMS[nm][0]: MU[:, j, 0] = pr
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool); AD = np.empty((n, J)); FS = np.ones((n, J)); FR = np.ones((n, J)); GT = np.zeros((n, J), bool)
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case)
            ad = np.abs(z[k, 1] - h[:, 1]); AD[k] = ad; b = np.searchsorted(edges, ad, side='right')
            RR = np.repeat(R0b[k][None], J, axis=0).copy()
            for j, nm in enumerate(names):
                _, pa, ra = ARMS[nm]
                if pa == 'INFL': FS[k, j] = ks[b[j]]
                if pa in ('GATE3', 'GATE5') and ad[j] > cal['tau_gate3' if pa == 'GATE3' else 'tau_gate5']: FS[k, j] = BIG; GT[k, j] = True
                if ra == 'INFL_D0': FR[k, j] = kr[b[j]]
                if ra == 'INFL_DS': FR[k, j] = hi_ds[k]
                RR[j, 1, 1] *= FS[k, j]; RR[j, 0, 0] *= FR[k, j]
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR, RR, np.ones(J)); X[k] = x; C[k] = P; acc[k] = yes
        sc = V.MC.score(X, C, t, truth, b_true); m = t >= 30
        anc = np.asarray(case['anchor'], float); dz = anc[2] - float(case['robot_z_m'])
        dtrue = np.sqrt((truth[:, 0] - anc[0]) ** 2 + (truth[:, 1] - anc[1]) ** 2 + dz ** 2)
        uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True)
        for j, nm in enumerate(names):
            exy = X[:, j, :2] - truth[:, :2]; dhat = np.sqrt((X[:, j, 0] - anc[0]) ** 2 + (X[:, j, 1] - anc[1]) ** 2 + dz ** 2)
            u = e - MU[:, j]; vs = R0b[:, 1, 1] * np.minimum(FS[:, j], BIG); vr = R0b[:, 0, 0] * FR[:, j]; used_s = acc[:, j] & ~GT[:, j]
            rows.append({'case': a.case, 'route': held, 'bias': bias, 'channel': ch, 'arm': nm, **sc[j], 'accepted_fraction': float(acc[m, j].mean()),
                         'range_err_rmse_cm': float(np.sqrt(np.mean((dhat - dtrue)[m] ** 2)) * 100), 'radial_rmse_cm': float(np.sqrt(np.mean(np.sum(exy * uh, axis=1)[m] ** 2)) * 100),
                         'xy_rmse_cm': float(np.sqrt(np.mean(np.sum(exy ** 2, axis=1)[m])) * 100),
                         'frac_s_inflated': float((FS[m, j] > 1).mean()), 'frac_s_gated': float(GT[m, j].mean()), 'frac_r_inflated': float((FR[m, j] > 1).mean()),
                         'meas_s95': float(np.mean((u[m, 1] ** 2 / np.where(GT[m, j], np.inf, vs[m]))[~GT[m, j]] <= 3.841)) if (~GT[m, j]).any() else np.nan,
                         'meas_r95': float(np.mean(u[m, 0] ** 2 / vr[m] <= 3.841)), 'meas_r_rms_cm': float(np.sqrt(np.mean(u[m, 0] ** 2)) * 100),
                         'pol_used_es_rms': float(np.sqrt(np.mean(u[m & used_s, 1] ** 2))), 'pol_used_es2_mass': float(np.sum(u[m & used_s, 1] ** 2)),
                         'median_abs_d0': float(np.median(AD[m, j]))})
        print('D0V_DONE', stem, flush=True)
    pd.DataFrame(rows).to_csv(V.OUT / f'{a.case}_D0V_SCORES.csv', index=False); print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
