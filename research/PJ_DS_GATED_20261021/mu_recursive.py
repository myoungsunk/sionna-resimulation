#!/usr/bin/env python3
"""Recursive check of measurement-level delta-s mean corrections (range / polarization, all / gated)."""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
import d1_core as D
from series_dump import taps, OFFS

DS = [f'ds_{o:+d}' for o in OFFS]
EXIST = ['log_fp_power', 'abs_s_fp', 'early4', 'early8', 'early16', 'delay_rms_ns', 'peak_diff_ns', 'eta_fp_win80', 's_diff4', 's_diff8', 's_diff16',
         'tap_pol_var80', 'jones_diversity', 'freq_s_var', 'detector_s_span', 'detector_delay_span_ns']
# arm: (range-mean model, polarization-mean model, gated, inflate range)
ARMS = {'BASE': (None, None, False, False), 'INFL_R': (None, None, False, True),
        'MU_R_EX': ('EX', None, False, False), 'MU_R_EXDS': ('EXDS', None, False, False),
        'MU_S_EX': (None, 'EX', False, False), 'MU_S_EXDS': (None, 'EXDS', False, False), 'MU_RS_EXDS': ('EXDS', 'EXDS', False, False),
        'G_MU_R': ('EXDS', None, True, False), 'G_MU_S': (None, 'EXDS', True, False), 'G_MU_RS': ('EXDS', 'EXDS', True, False),
        'INFL_R+MU_R_EXDS': ('EXDS', None, False, True), 'INFL_R+G_MU_RS': ('EXDS', 'EXDS', True, True)}
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]
DEG = 180 / math.pi


def feature_table():
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); rows = []
    for c in V.MANIFEST['cases']:
        ids = pd.DataFrame(json.loads((V.ROOT / c['samples_path']).read_text())).pose_id.to_numpy(int)
        for ch, key in [('full', 'full_path'), ('los', 'los_path')]:
            H = np.load(V.ROOT / c[key], mmap_mode='r', allow_pickle=False)
            b = [taps(np.asarray(H[k:k + 128, :, :, 0])) for k in range(0, len(H), 128)]
            d = pd.DataFrame({k: np.concatenate([x[k] for x in b]) for k in b[0]}); d['pose_id'] = ids
            f = feat[(feat.case == c['id']) & (feat.channel == ch)].set_index('pose_id').loc[ids]
            assert np.nanmax(np.abs(d.s_fp_chk.to_numpy() - f.s_fp.to_numpy())) < 1e-9
            for col in EXIST + ['e_s', 'e_r']: d[col] = f[col].to_numpy()
            d['case'] = c['id']; d['route'] = c['route']; d['channel'] = ch; rows.append(d)
    return pd.concat(rows, ignore_index=True)


def hgb(tr, cols, y):
    return HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(tr[cols], tr[y])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    T = V.build_table(); two, five = V.calibrations(T[(T.channel == 'full') & (T.route != held)])
    FT = feature_table(); tr = FT[(FT.channel == 'full') & (FT.route != held)]
    models = {(y, k): hgb(tr, EXIST if k == 'EX' else EXIST + DS, y) for y in ['e_r', 'e_s'] for k in ['EX', 'EXDS']}
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    names = list(ARMS); model = V.SourceFFD(); rows, series, meas = [], [], []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n, J = len(t), len(names); b_true = math.radians(V.BIAS_LEVELS[bias])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        tc = T[(T.case == a.case) & (T.channel == ch)].set_index('pose_id').loc[ids]; aa = tc.a.to_numpy(); gate = aa >= two['tau']
        fx = FT[(FT.case == a.case) & (FT.channel == ch)].set_index('pose_id').loc[ids]
        pred = {(y, k): m.predict(fx[EXIST if k == 'EX' else EXIST + DS]) for (y, k), m in models.items()}
        mu0, R0b = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        MU = np.repeat(mu0[:, None, :], J, axis=1).copy(); RR = np.repeat(R0b[:, None], J, axis=1).copy()
        hi_r = V.factors(aa, two, five, 'HI', 'r')
        for j, nm in enumerate(names):
            mr, ms, gated, infl = ARMS[nm]; sel = gate if gated else np.ones(n, bool)
            if mr: MU[:, j, 0] = np.where(sel, pred[('e_r', mr)], mu0[:, 0])
            if ms: MU[:, j, 1] = np.where(sel, pred[('e_s', ms)], mu0[:, 1])
            if infl: RR[:, j, 0, 0] *= hi_r
            er = d.e_r.to_numpy() - MU[:, j, 0]; es = d.e_s.to_numpy() - MU[:, j, 1]; mm = t >= 30
            meas.append({'case': a.case, 'bias': bias, 'channel': ch, 'arm': nm, 'meas_r_rms_cm': float(np.sqrt(np.mean(er[mm] ** 2)) * 100), 'meas_s_rms': float(np.sqrt(np.mean(es[mm] ** 2))),
                         'meas_r_rms_cm_gated': float(np.sqrt(np.mean(er[mm & gate] ** 2)) * 100), 'meas_s_rms_gated': float(np.sqrt(np.mean(es[mm & gate] ** 2)))})
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool)
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case)
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P; acc[k] = yes
        sc = V.MC.score(X, C, t, truth, b_true); m = t >= 30
        anc = np.asarray(case['anchor'], float); dz = anc[2] - float(case['robot_z_m'])
        dtrue = np.sqrt((truth[:, 0] - anc[0]) ** 2 + (truth[:, 1] - anc[1]) ** 2 + dz ** 2)
        uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True); ut = np.column_stack([-uh[:, 1], uh[:, 0]])
        sr = {'case': a.case, 'bias': bias, 'channel': ch, 'k': np.arange(n), 't_s': t, 'pose_id': ids, 'x': truth[:, 0], 'abs_ds1': aa, 'gate': gate}
        for j, nm in enumerate(names):
            exy = X[:, j, :2] - truth[:, :2]; dhat = np.sqrt((X[:, j, 0] - anc[0]) ** 2 + (X[:, j, 1] - anc[1]) ** 2 + dz ** 2); rerr = dhat - dtrue
            rows.append({'case': a.case, 'route': held, 'bias': bias, 'channel': ch, 'arm': nm, **sc[j], 'accepted_fraction': float(acc[m, j].mean()),
                         'range_err_rmse_cm': float(np.sqrt(np.mean(rerr[m] ** 2)) * 100), 'radial_rmse_cm': float(np.sqrt(np.mean(np.sum(exy * uh, axis=1)[m] ** 2)) * 100),
                         'tangential_rmse_cm': float(np.sqrt(np.mean(np.sum(exy * ut, axis=1)[m] ** 2)) * 100)})
            if ch == 'full':
                sr[f'{nm}__herr_deg'] = D.wrap(X[:, j, 2] - truth[:, 2]) * DEG; sr[f'{nm}__range_err_cm'] = rerr * 100
                sr[f'{nm}__hsig_deg'] = np.sqrt(C[:, j, 2, 2]) * DEG; sr[f'{nm}__meas_r_cm'] = (d.e_r.to_numpy() - MU[:, j, 0]) * 100; sr[f'{nm}__meas_s'] = d.e_s.to_numpy() - MU[:, j, 1]
        if ch == 'full': series.append(pd.DataFrame(sr))
        print('MR_DONE', stem, flush=True)
    pd.DataFrame(rows).to_csv(V.OUT / f'{a.case}_MR_SCORES.csv', index=False); pd.DataFrame(meas).to_csv(V.OUT / f'{a.case}_MR_MEAS.csv', index=False)
    pd.concat(series).to_csv(V.OUT / f'{a.case}_MR_SERIES.csv.gz', index=False, compression='gzip'); print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
