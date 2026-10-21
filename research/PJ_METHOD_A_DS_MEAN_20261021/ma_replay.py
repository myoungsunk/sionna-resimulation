#!/usr/bin/env python3
"""Method A: delta-s conditioned polarization mean in the unchanged 4-state EKF (eta=1)."""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve(); ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_OUT']).resolve(); OUT.mkdir(parents=True, exist_ok=True)
for path in ['research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016', 'research/R5_N4B_20261015',
             'research/PHYSICS_RS_STAGED_20261015/code', 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
    sys.path.insert(0, str(ROOT / path))
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent / 'PJ_CONSISTENCY_M123_20261021'))
import p0_initial
p0_initial.OUT = OUT
from source_model import SourceFFD
import source_model
source_model.OUT = OUT
from r2_bias_replay import build_positive_bias_controls, predict_one, BIAS_LEVELS, INITIAL_POSE_STD, BIAS_PRIOR_STD
from p3_rf_adapter4 import R0
import m_core as MC

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]
OFFS = [-8, -4, -2, -1, 1, 2, 4, 8]; DS = [f'ds_{o:+d}' for o in OFFS]
EXIST = ['log_fp_power', 'abs_s_fp', 'early4', 'early8', 'early16', 'delay_rms_ns', 'peak_diff_ns', 'eta_fp_win80', 's_diff4', 's_diff8', 's_diff16',
         'tap_pol_var80', 'jones_diversity', 'freq_s_var', 'detector_s_span', 'detector_delay_span_ns']
MODELS = {'LIN': ('ridge', DS + ['log_fp_power']), 'DS_LIN': ('ridge', DS), 'HGB': ('hgb', EXIST + DS)}
LFW = 11; FLOOR = 0.1 * float(R0[1, 1])


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def taps(H):
    H = np.asarray(H, np.complex128); n, nf, _ = H.shape; nt = 4 * nf; ii = np.arange(n)
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[None, :, None], n=nt, axis=1) * nf
    amp = np.abs(cir); power = amp ** 2
    branch = amp.max(axis=1).argmax(axis=1); strong = amp[ii, :, branch]; peaks = strong.max(axis=1)
    tap = (strong >= .3 * peaks[:, None]).argmax(axis=1); s = {}
    for o in [0] + OFFS:
        idx = tap + o; ok = (idx >= 0) & (idx < nt); idc = np.clip(idx, 0, nt - 1); P = power[ii, idc, :]; den = P.sum(axis=1)
        s[o] = np.where(ok & (den > 0), (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1), np.nan)
    return {f'ds_{o:+d}': s[o] - s[0] for o in OFFS} | {'s0': s[0]}


def build_table():
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); rows = []
    for c in MANIFEST['cases']:
        ids = pd.DataFrame(json.loads((ROOT / c['samples_path']).read_text())).pose_id.to_numpy(int)
        for ch, key in [('full', 'full_path'), ('los', 'los_path')]:
            H = np.load(ROOT / c[key], mmap_mode='r', allow_pickle=False)
            b = [taps(np.asarray(H[k:k + 128, :, :, 0])) for k in range(0, len(H), 128)]
            d = pd.DataFrame({k: np.concatenate([x[k] for x in b]) for k in b[0]}); d['pose_id'] = ids
            f = feat[(feat.case == c['id']) & (feat.channel == ch)].set_index('pose_id').loc[ids]
            assert np.nanmax(np.abs(d.s0.to_numpy() - f.s_fp.to_numpy())) < 1e-9
            for col in EXIST + ['e_s']: d[col] = f[col].to_numpy()
            d['case'] = c['id']; d['route'] = c['route']; d['channel'] = ch; rows.append(d)
    return pd.concat(rows, ignore_index=True)


def fit(tr, kind, cols):
    trm = tr[cols + ['e_s']].dropna()
    if kind == 'hgb':
        m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(trm[cols], trm.e_s)
        return lambda X: m.predict(X[cols])
    sc = StandardScaler().fit(trm[cols]); m = Ridge(alpha=1.0).fit(sc.transform(trm[cols]), trm.e_s)
    return lambda X: m.predict(sc.transform(X[cols].fillna(0.0)))


def variance_model(tr, kind, cols):
    """OOF residuals across the two train routes, power-tertile bins with shrinkage."""
    res = []
    routes = sorted(tr.route.unique()); assert len(routes) == 2
    for a, b in [(routes[0], routes[1]), (routes[1], routes[0])]:
        f = fit(tr[tr.route == a], kind, cols); t = tr[tr.route == b]
        res.append(pd.DataFrame({'lp': t.log_fp_power.to_numpy(), 'r': t.e_s.to_numpy() - f(t)}))
    R = pd.concat(res).dropna(); cuts = np.quantile(R.lp, [1 / 3, 2 / 3]); gv = max(float(np.var(R.r)), FLOOR)
    vb = []
    for k in range(3):
        sel = np.searchsorted(cuts, R.lp, side='right') == k; n = int(sel.sum()); v = float(np.var(R.r[sel])) if n > 1 else gv
        a = n / (n + 100.); vb.append(max(a * v + (1 - a) * gv, FLOOR))
    return lambda X: np.array(vb)[np.searchsorted(cuts, X.log_fp_power.to_numpy(), side='right')], {'cuts': cuts.tolist(), 'bins': vb, 'global': gv}


def base_params(par, cm, ch, ids, model):
    p = par[(par.case == cm) & (par.channel == ch) & (par.model == model)].set_index('pose_id').loc[ids]
    R = np.zeros((len(ids), 2, 2)); R[:, 0, 0] = p.Vr; R[:, 1, 1] = p.Vs; R[:, 0, 1] = R[:, 1, 0] = p.Crs
    return p[['mu_r', 'mu_s']].to_numpy(float), R


def lf(case, pose_ids, v):
    c = next(x for x in MANIFEST['cases'] if x['id'] == case); r = next(x for x in MANIFEST['routes'] if x['id'] == c['route'])
    tl = pd.read_csv(ROOT / r['path'])
    return pd.Series(pd.Series(v, index=pose_ids).reindex(tl.pose_id.to_numpy()).to_numpy(float)).rolling(LFW, center=True, min_periods=1).mean().to_numpy()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    T = build_table(); tr = T[(T.channel == 'full') & (T.route != held)]
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(one('OOF_PARAMETERS.csv.gz'))
    mu_f, var_f, vinfo = {}, {}, {}
    for nm, (kind, cols) in MODELS.items():
        mu_f[nm] = fit(tr, kind, cols); var_f[nm], vinfo[nm] = variance_model(tr, kind, cols)
    print('VAR_MODELS', a.case, json.dumps(vinfo), flush=True)
    arms = [('BASE', 'POWER_DIAG', None, False), ('REF_POWER1', 'POWER1', None, False), ('A_LIN_PV', 'POWER_DIAG', 'LIN', False), ('A_LIN', 'POWER_DIAG', 'LIN', True),
            ('A_HGB_PV', 'POWER_DIAG', 'HGB', False), ('A_HGB', 'POWER_DIAG', 'HGB', True), ('A_DS_LIN', 'POWER_DIAG', 'DS_LIN', True)]
    model = SourceFFD(); rows, qa, meas = [], [], []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n, J = len(t), len(arms); b_true = math.radians(BIAS_LEVELS[bias])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        tc = T[(T.case == a.case) & (T.channel == ch)].set_index('pose_id').loc[ids]
        MU = np.empty((n, J, 2)); RR = np.empty((n, J, 2, 2))
        for j, (arm, base, mname, newvar) in enumerate(arms):
            mu, R = base_params(par, a.case, ch, ids, base); mu = mu.copy(); R = R.copy()
            if mname:
                mu[:, 1] = mu_f[mname](tc)
                if newvar: R[:, 1, 1] = var_f[mname](tc)
            MU[:, j] = mu; RR[:, j] = R
            if bias == 'B0':
                es = tc.e_s.to_numpy(); r = es - mu[:, 1]
                meas.append({'case': a.case, 'channel': ch, 'arm': arm, 'R2_nc_pose': float(1 - np.mean(r ** 2) / np.mean(es ** 2)),
                             'R2_nc_LF': float(1 - np.mean((lf(a.case, ids, es) - lf(a.case, ids, mu[:, 1])) ** 2) / np.mean(lf(a.case, ids, es) ** 2)),
                             's95_packet': float(np.mean(r ** 2 / R[:, 1, 1] <= 3.841458820694124)), 'mean_Vs': float(R[:, 1, 1].mean()), 'rms_resid': float(np.sqrt(np.mean(r ** 2)))})
        controls, x0 = build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[INITIAL_POSE_STD ** 2, BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool)
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, H = model.batch(x, case)
            x, P, nis, yes, K = MC.update(x, P, z[k], h, H, MU[k], RR[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P; acc[k] = yes
        sc = MC.score(X, C, t, truth, b_true); m = t >= 30
        for j, (arm, base, mname, newvar) in enumerate(arms):
            rows.append({'case': a.case, 'route': held, 'bias': bias, 'channel': ch, 'arm': arm, 'mu_model': mname or 'POWER1', 'new_var': newvar, **sc[j], 'accepted_fraction': float(acc[m, j].mean())})
        old_sc = pd.read_csv(one(stem + '_SCORES.csv')); old_sc = old_sc[old_sc['mode'] == 'NATURAL_RECURSIVE'].set_index('model')
        for arm, ref in [('BASE', 'POWER_DIAG'), ('REF_POWER1', 'POWER1')]:
            r = next(x for x in rows if x['arm'] == arm and x['bias'] == bias and x['channel'] == ch)
            qa.append({'case': a.case, 'bias': bias, 'channel': ch, 'arm': arm, 'd_rmse': abs(r['heading_rmse_deg'] - old_sc.loc[ref, 'heading_rmse_deg'])})
        print('MA_DONE', stem, json.dumps(qa[-2:]), flush=True)
    pd.DataFrame(rows).to_csv(OUT / f'{a.case}_MA_SCORES.csv', index=False); pd.DataFrame(qa).to_csv(OUT / f'{a.case}_MA_QA.csv', index=False)
    pd.DataFrame(meas).to_csv(OUT / f'{a.case}_MA_MEAS.csv', index=False)
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
