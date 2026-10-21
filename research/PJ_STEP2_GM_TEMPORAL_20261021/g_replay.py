#!/usr/bin/env python3
"""Step 2: white + Gauss-Markov measurement-bias model (consider / augment) under current state and observations."""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import chi2

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve()
ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_OUT']).resolve(); OUT.mkdir(parents=True, exist_ok=True)
D1RES = Path(os.environ['PJ_D1_RESULTS']).resolve()
for path in ['research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016', 'research/R5_N4B_20261015',
             'research/PHYSICS_RS_STAGED_20261015/code',
             'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
    sys.path.insert(0, str(ROOT / path))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_CONSISTENCY_M123_20261021'))
import p0_initial
p0_initial.OUT = OUT
from source_model import SourceFFD
import source_model
source_model.OUT = OUT
from r2_bias_replay import build_positive_bias_controls, BIAS_LEVELS, INITIAL_POSE_STD, BIAS_PRIOR_STD
from core import predict
import m_core as MC

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]
G2 = float(chi2.ppf(.99, 2)); LFW = 11


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def gm_params(route):
    a = pd.read_csv(D1RES / 'D1_ACF.csv')
    a = a[(a.channel == 'full') & (a.bias == 'B0') & (a.model == 'POWER_DIAG') & (~a.case.str.startswith(route))]
    ts = np.array([0.2, 0.5, 1, 2, 5, 10]); cols = ['lag1_noncentred', 'acf_0.5s', 'acf_1s', 'acf_2s', 'acf_5s', 'acf_10s']
    out = {}
    for ch, g in a.groupby('whitened_channel'):
        fs, taus = [], []
        for _, r in g.iterrows():
            rho = r[cols].to_numpy(float); m = rho > 0.02
            b, lnf = np.polyfit(ts[m], np.log(rho[m]), 1); fs.append(np.exp(lnf)); taus.append(-1 / b if b < 0 else np.inf)
        out[ch] = (float(np.clip(np.median(fs), 0, 0.95)), float(np.median(taus)))
    return out


def arm_specs(route):
    p = gm_params(route); fr, tr = p['r']; fs, ts = p['s']
    A = [dict(arm='BASE', base='POWER_DIAG', mode='base', fr=0., fs=0., tr=1., ts=1.),
         dict(arm='REF_POWER1', base='POWER1', mode='base', fr=0., fs=0., tr=1., ts=1.)]
    for mode, tag in [('consider', 'GMC'), ('augment', 'GMA')]:
        A.append(dict(arm=f'{tag}_S', base='POWER_DIAG', mode=mode, fr=0., fs=fs, tr=tr, ts=ts))
        A.append(dict(arm=f'{tag}_RS', base='POWER_DIAG', mode=mode, fr=fr, fs=fs, tr=tr, ts=ts))
        for k, lab in [(0.5, 'T05'), (2.0, 'T2')]:
            A.append(dict(arm=f'{tag}_RS_{lab}', base='POWER_DIAG', mode=mode, fr=fr, fs=fs, tr=tr * k, ts=ts * k))
    return A, p


def base_params(par, cm, ch, ids, model):
    p = par[(par.case == cm) & (par.channel == ch) & (par.model == model)].set_index('pose_id').loc[ids]
    R = np.zeros((len(ids), 2, 2)); R[:, 0, 0] = p.Vr; R[:, 1, 1] = p.Vs; R[:, 0, 1] = R[:, 1, 0] = p.Crs
    return p[['mu_r', 'mu_s']].to_numpy(float), R


def replay(model, case, bias, ch, feat, par, arms):
    cm = case['id']; stem = f'{cm}_{ch}_{bias}'
    old = np.load(one(stem + '_TRACE.npz'), allow_pickle=False)
    t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
    n, J = len(t), len(arms); b_true = math.radians(BIAS_LEVELS[bias])
    d = feat[(feat.case == cm) & (feat.channel == ch)].set_index('pose_id').loc[ids]
    z = d[['range_m', 's_fp']].to_numpy(float); e_s = d['e_s'].to_numpy(float); e_r = d['e_r'].to_numpy(float)
    bases = {b: base_params(par, cm, ch, ids, b) for b in {a['base'] for a in arms}}
    MU = np.stack([bases[a['base']][0] for a in arms], 1); R = np.stack([bases[a['base']][1] for a in arms], 1)
    f = np.array([[a['fr'], a['fs']] for a in arms]); tau = np.array([[a['tr'], a['ts']] for a in arms])
    mask = (f > 0).astype(float); aug = np.array([a['mode'] == 'augment' for a in arms])
    Dw = np.sqrt(1 - f)
    controls, x0 = build_positive_bias_controls(t, truth, bias)
    x = np.zeros((J, 6)); x[:, :3] = x0
    P = np.zeros((J, 6, 6)); P[:, :4, :4] = np.diag(np.r_[INITIAL_POSE_STD ** 2, BIAS_PRIOR_STD ** 2]); P[:, 4, 4] = f[:, 0]; P[:, 5, 5] = f[:, 1]
    X = np.empty((n, J, 6)); C = np.empty((n, J, 6, 6)); acc = np.empty((n, J), bool)
    for k in range(n):
        if k:
            ds, gy, dt = float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k])
            q = np.diag([2e-5 * abs(ds), math.radians(.015) ** 2 * dt, 0.])
            phi = np.exp(-dt / tau)
            for j in range(J):
                y, Pxx, F, G = predict(x[j, :4], P[j, :4, :4], ds, gy, dt, q)
                Ph = np.diag(phi[j])
                Pn = np.zeros((6, 6)); Pn[:4, :4] = Pxx; Pn[:4, 4:] = F @ P[j, :4, 4:] @ Ph; Pn[4:, :4] = Pn[:4, 4:].T
                Pn[4:, 4:] = Ph @ P[j, 4:, 4:] @ Ph + np.diag(f[j] * (1 - phi[j] ** 2))
                x[j, :4] = y; x[j, 4:] = phi[j] * x[j, 4:]; P[j] = .5 * (Pn + Pn.T)
        h, H = model.batch(x[:, :4], case)
        sv = np.sqrt(np.stack([R[k, :, 0, 0], R[k, :, 1, 1]], 1))
        Ha = np.zeros((J, 2, 6)); Ha[:, :, :4] = H; Ha[:, 0, 4] = sv[:, 0] * mask[:, 0]; Ha[:, 1, 5] = sv[:, 1] * mask[:, 1]
        Ra = Dw[:, :, None] * R[k] * Dw[:, None, :]
        v = z[k][None] - h - MU[k] - sv * x[:, 4:] * mask
        S = Ha @ P @ np.swapaxes(Ha, -1, -2) + Ra; S = .5 * (S + np.swapaxes(S, -1, -2))
        nis = np.einsum('ni,ni->n', v, np.linalg.solve(S, v[..., None])[..., 0]); yes = nis <= G2
        K = np.swapaxes(np.linalg.solve(S, Ha @ P), -1, -2)
        K[~aug, 4:, :] = 0.
        cand = x + np.einsum('nij,nj->ni', K, v); cand[:, 2] = MC.wrap(cand[:, 2])
        A_ = np.eye(6)[None] - K @ Ha
        Cn = A_ @ P @ np.swapaxes(A_, -1, -2) + K @ Ra @ np.swapaxes(K, -1, -2); Cn = .5 * (Cn + np.swapaxes(Cn, -1, -2))
        x = np.where(yes[:, None], cand, x); P = np.where(yes[:, None, None], Cn, P)
        X[k] = x; C[k] = P; acc[k] = yes
    assert np.isfinite(X).all() and np.linalg.eigvalsh(C[:, :, :4, :4]).min() > 0
    sc = MC.score(X[:, :, :4], C[:, :, :4, :4], t, truth, b_true); m = t >= 30
    u_s_lf = {}; rows = []
    for j, a in enumerate(arms):
        r = {'case': cm, 'route': case['route'], 'bias': bias, 'channel': ch, **a, **sc[j], 'accepted_fraction': float(acc[m, j].mean())}
        if a['mode'] == 'augment':
            us = pd.Series(e_s - MU[:, j, 1]).rolling(LFW, center=True, min_periods=1).mean().to_numpy()
            ur = pd.Series(e_r - MU[:, j, 0]).rolling(LFW, center=True, min_periods=1).mean().to_numpy()
            bs = np.sqrt(R[:, j, 1, 1]) * X[:, j, 5]; br = np.sqrt(R[:, j, 0, 0]) * X[:, j, 4]
            r['beta_s_corr_with_us_LF'] = float(np.corrcoef(bs[m], us[m])[0, 1]); r['beta_s_post_prior_var'] = float(np.mean(C[m, j, 5, 5]) / a['fs'])
            r['us_LF_rms'] = float(np.sqrt(np.mean(us[m] ** 2))); r['us_LF_minus_beta_rms'] = float(np.sqrt(np.mean((us[m] - bs[m]) ** 2)))
            if a['fr'] > 0:
                r['beta_r_corr_with_ur_LF'] = float(np.corrcoef(br[m], ur[m])[0, 1]); r['beta_r_post_prior_var'] = float(np.mean(C[m, j, 4, 4]) / a['fr'])
        rows.append(r)
    old_sc = pd.read_csv(one(stem + '_SCORES.csv')); old_sc = old_sc[old_sc['mode'] == 'NATURAL_RECURSIVE'].set_index('model')
    qa = [{'case': cm, 'bias': bias, 'channel': ch, 'arm': arm, 'ref': ref,
           'd_rmse': abs(next(x for x in rows if x['arm'] == arm)['heading_rmse_deg'] - old_sc.loc[ref, 'heading_rmse_deg'])}
          for arm, ref in [('BASE', 'POWER_DIAG'), ('REF_POWER1', 'POWER1')]]
    tr = []
    for j, a in enumerate(arms):
        if a['arm'] in ('BASE', 'GMC_RS', 'GMA_RS', 'GMA_S'):
            tr.append(pd.DataFrame({'case': cm, 'bias': bias, 'channel': ch, 'arm': a['arm'], 't_s': np.round(t, 3),
                                    'heading_err_deg': np.degrees(MC.wrap(X[:, j, 2] - truth[:, 2])), 'heading_sigma_deg': np.degrees(np.sqrt(C[:, j, 2, 2])),
                                    'beta_s_phys': np.sqrt(R[:, j, 1, 1]) * X[:, j, 5], 'u_s': e_s - MU[:, j, 1]}))
    print('G_REPLAY_DONE', stem, json.dumps(qa), flush=True)
    return rows, qa, pd.concat(tr)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in MANIFEST['cases'] if c['id'] == a.case)
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(one('OOF_PARAMETERS.csv.gz'))
    arms, p = arm_specs(case['route']); print('GM_PARAMS', a.case, json.dumps(p), flush=True)
    model = SourceFFD(); rows = []; qas = []; trs = []
    for bias, ch in CONDITIONS:
        r, q, t_ = replay(model, case, bias, ch, feat, par, arms); rows += r; qas += q; trs.append(t_)
    pd.DataFrame(rows).to_csv(OUT / f'{a.case}_G_SCORES.csv', index=False)
    pd.DataFrame(qas).to_csv(OUT / f'{a.case}_G_QA.csv', index=False)
    pd.concat(trs).to_csv(OUT / f'{a.case}_G_TRAJ.csv.gz', index=False, compression='gzip')
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
