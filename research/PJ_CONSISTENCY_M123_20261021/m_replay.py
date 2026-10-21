#!/usr/bin/env python3
"""M1-M3 grid replay + H-A/H-D/H-E metrics for one case. No RF refit."""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve()
ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_OUT']).resolve(); OUT.mkdir(parents=True, exist_ok=True)
for path in ['research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016', 'research/R5_N4B_20261015',
             'research/PHYSICS_RS_STAGED_20261015/code',
             'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
    sys.path.insert(0, str(ROOT / path))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import p0_initial
p0_initial.OUT = OUT
from source_model import SourceFFD
import source_model
source_model.OUT = OUT
from r2_bias_replay import build_positive_bias_controls, predict_one, BIAS_LEVELS, INITIAL_POSE_STD, BIAS_PRIOR_STD
import m_core as MC
import d1_core as D

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
ETAS = [1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24]
KAPPAS = [1.0, 0.5, 0.0]
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def arm_specs():
    arms = [dict(arm='REF_POWER1', family='REF', base='POWER1', eta_r=1., eta_s=1., kappa=1., mu_s0=False),
            dict(arm='REF_JOINT4', family='REF', base='JOINT4', eta_r=1., eta_s=1., kappa=1., mu_s0=False)]
    for fam in ['S_ONLY', 'COMMON', 'MU_S0']:
        for e in ETAS:
            for k in KAPPAS:
                arms.append(dict(arm=f'{fam}_e{e:g}_k{k:g}', family=fam, base='POWER_DIAG', eta_r=float(e) if fam == 'COMMON' else 1.,
                                 eta_s=float(e), kappa=k, mu_s0=fam == 'MU_S0'))
    return arms


def base_params(par, cm, ch, ids, model):
    p = par[(par.case == cm) & (par.channel == ch) & (par.model == model)].set_index('pose_id').loc[ids]
    mu = p[['mu_r', 'mu_s']].to_numpy(float)
    R = np.zeros((len(ids), 2, 2)); R[:, 0, 0] = p.Vr; R[:, 1, 1] = p.Vs; R[:, 0, 1] = R[:, 1, 0] = p.Crs
    return mu, R


def replay(model, case, bias, ch, feat, par, arms):
    cm = case['id']; stem = f'{cm}_{ch}_{bias}'
    old = np.load(one(stem + '_TRACE.npz'), allow_pickle=False)
    t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
    n, J = len(t), len(arms)
    b_true = math.radians(BIAS_LEVELS[bias])
    d = feat[(feat.case == cm) & (feat.channel == ch)].set_index('pose_id').loc[ids]
    z = d[['range_m', 's_fp']].to_numpy(float)
    bases = {b: base_params(par, cm, ch, ids, b) for b in {a['base'] for a in arms}}
    MU = np.empty((n, J, 2)); RP = np.empty((n, J, 2, 2)); RE = np.empty((n, J, 2, 2))
    kap = np.array([a['kappa'] for a in arms])
    for j, a in enumerate(arms):
        mu, R = bases[a['base']]
        MU[:, j] = mu
        if a['mu_s0']: MU[:, j, 1] = 0.
        RP[:, j] = R
        sc = np.array([math.sqrt(a['eta_r']), math.sqrt(a['eta_s'])])
        RE[:, j] = R * sc[None, :, None] * sc[None, None, :]
    controls, x0 = build_positive_bias_controls(t, truth, bias)
    x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[INITIAL_POSE_STD ** 2, BIAS_PRIOR_STD ** 2]), (J, 1, 1))
    X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool); NIS = np.empty((n, J))
    Kps = np.empty((n, J))
    for k in range(n):
        if k:
            for j in range(J):
                x[j], P[j] = predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
        h, H = model.batch(x, case)
        x, P, nis, yes, K = MC.update(x, P, z[k], h, H, MU[k], RP[k], RE[k], kap)
        X[k] = x; C[k] = P; acc[k] = yes; NIS[k] = nis; Kps[k] = np.where(yes, K[:, 2, 1], 0.)
    assert np.isfinite(X).all() and np.linalg.eigvalsh(C).min() > 0
    sc = MC.score(X, C, t, truth, b_true)
    rows = []
    m = t >= 30
    for j, a in enumerate(arms):
        rows.append({'case': cm, 'route': case['route'], 'bias': bias, 'channel': ch, **a, **sc[j],
                     'accepted_fraction': float(acc[m, j].mean()), 'nis_mean': float(NIS[m, j].mean())})
    old_sc = pd.read_csv(one(stem + '_SCORES.csv')); old_sc = old_sc[old_sc['mode'] == 'NATURAL_RECURSIVE'].set_index('model')
    qa = []
    for arm, ref in [('S_ONLY_e1_k1', 'POWER_DIAG'), ('REF_POWER1', 'POWER1'), ('REF_JOINT4', 'JOINT4')]:
        r = next(x for x in rows if x['arm'] == arm)
        qa.append({'case': cm, 'bias': bias, 'channel': ch, 'arm': arm, 'ref': ref,
                   'd_rmse': abs(r['heading_rmse_deg'] - old_sc.loc[ref, 'heading_rmse_deg']),
                   'd_h95': abs(r['heading95'] - old_sc.loc[ref, 'heading95']),
                   'd_bias': abs(r['bias_rmse_dps'] - old_sc.loc[ref, 'bias_rmse_dps'])})
    np.savez_compressed(OUT / f'{stem}_M_TRACE.npz', t_s=t.astype(np.float32), arms=np.array([a['arm'] for a in arms]),
                        heading_error=MC.wrap(X[:, :, 2] - truth[:, None, 2]).astype(np.float32),
                        heading_sigma=np.sqrt(C[:, :, 2, 2]).astype(np.float32), accepted=acc, K_psi_s=Kps.astype(np.float32))
    print('M_REPLAY_DONE', stem, json.dumps(qa), flush=True)
    return rows, qa


def hypotheses(model, case, feat):
    """H-A, H-D, H-E on Full B0 existing traces."""
    cm = case['id']; stem = f'{cm}_full_B0'
    tr = np.load(one(stem + '_TRACE.npz'), allow_pickle=False)
    arms_old = [str(a) for a in tr['arms']]
    X, C, acc, mu, R, t, ids, truth = tr['state'], tr['cov'], tr['accepted'].astype(bool), tr['mu'], tr['R'], tr['t_s'], tr['pose_id'], tr['truth_scoring_only']
    n = len(t); dt = float(np.median(np.diff(t))); w = max(1, int(round(2.0 / dt))) | 1; m = t >= 30
    d = feat[(feat.case == cm) & (feat.channel == 'full')].set_index('pose_id').loc[ids]
    e_s = d['e_s'].to_numpy(float)
    controls, x0 = build_positive_bias_controls(t, truth, 'B0')
    use = ['POWER_DIAG', 'SEP_BIN', 'POWER1']; jj = [arms_old.index(a) for a in use]
    ha_rows = []
    kps = np.zeros((n, len(use)))
    xm = np.tile(np.r_[x0, 0.], (len(use), 1)); Pm = np.tile(np.diag(np.r_[INITIAL_POSE_STD ** 2, BIAS_PRIOR_STD ** 2]), (len(use), 1, 1))
    for k in range(n):
        if k:
            for i, j in enumerate(jj):
                xm[i], Pm[i] = predict_one(X[k - 1, j], C[k - 1, j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
        h, H = model.batch(xm, case)
        Rk = R[k, jj]
        S = H @ Pm @ np.swapaxes(H, -1, -2) + Rk; S = .5 * (S + np.swapaxes(S, -1, -2))
        K = np.swapaxes(np.linalg.solve(S, H @ Pm), -1, -2)
        kps[k] = np.where(acc[k, jj], K[:, 2, 1], 0.)
    for i, (a, j) in enumerate(zip(use, jj)):
        dlf = MC.lf(e_s - mu[:, j, 1], w)
        rho = float(spearmanr(kps[m, i], np.abs(dlf[m])).statistic)
        Vs = R[m, j, 1, 1]; q = np.quantile(Vs, [1 / 3, 2 / 3]); b = np.searchsorted(q, Vs, side='right')
        means = [float(np.abs(dlf[m])[b == t_].mean()) if np.any(b == t_) else float('nan') for t_ in range(3)]
        ha_rows.append({'case': cm, 'model': a, 'rho_A': rho, 'absd_mean_lowV': means[0], 'absd_mean_midV': means[1], 'absd_mean_highV': means[2],
                        'lowV_has_max_absd': bool(np.nanargmax(means) == 0), 'n_unique_Vs': int(len(np.unique(np.round(Vs, 12)))),
                        'mean_abs_kpsi_s': float(np.abs(kps[m, i]).mean())})
    # H-E
    he_rows = []
    elf = MC.lf(e_s, w)
    for a in ['POWER1', 'SEP_BIN', 'POWER_DIAG']:
        j = arms_old.index(a); mlf = MC.lf(mu[:, j, 1], w)
        he_rows.append({'case': cm, 'model': a, 'R2_nc': float(1 - np.mean((elf[m] - mlf[m]) ** 2) / np.mean(elf[m] ** 2)),
                        'R2_centred': float(1 - np.var(elf[m] - mlf[m]) / np.var(elf[m])),
                        'rms_elf': float(np.sqrt(np.mean(elf[m] ** 2))), 'rms_resid_lf': float(np.sqrt(np.mean((elf[m] - mlf[m]) ** 2)))})
    skip = {'case', 'route', 'channel', 'pose_id', 'x_eval', 'y_eval', 'yaw_eval_rad', 'e_r', 'e_s', 's_fp', 'range_m'}
    expl = []
    for col in d.columns:
        if col in skip or not np.issubdtype(d[col].dtype, np.number): continue
        v = d[col].to_numpy(float)
        if np.nanstd(v[m]) == 0: continue
        expl.append({'case': cm, 'feature': col, 'spearman_with_elf': float(spearmanr(v[m], elf[m]).statistic),
                     'spearman_with_abs_elf': float(spearmanr(v[m], np.abs(elf[m])).statistic)})
    # H-D
    j = arms_old.index('POWER_DIAG')
    ut = (e_s - mu[:, j, 1]) / np.sqrt(R[:, j, 1, 1])
    sp = np.r_[np.nan, np.hypot(np.diff(truth[:, 0]), np.diff(truth[:, 1])) / np.diff(t)]
    om = np.r_[np.nan, np.abs(MC.wrap(np.diff(truth[:, 2]))) / np.diff(t)]
    hd_rows = []
    edges = np.arange(t[0], t[-1] + 1e-9, 30.0)
    for a0, a1 in zip(edges[:-1], edges[1:]):
        s_ = (t >= a0) & (t < a1)
        if s_.sum() < 100: continue
        st = D.acf_stats(ut[s_], dt, max_s=10.0)
        hd_rows.append({'case': cm, 't0': float(a0), 'v_mean': float(np.nanmean(sp[s_])), 'omega_mean': float(np.nanmean(om[s_])),
                        'tau_int_s': st['tau_int_s'], 'lag1': st['lag1_noncentred'], 'n': int(s_.sum())})
    full = D.acf_stats(ut, dt, max_s=30.0); vbar = float(np.nanmean(sp[sp > 0.02])) if np.any(sp > 0.02) else float('nan')
    hd_case = {'case': cm, 'tau_int_s': full['tau_int_s'], 'v_moving_mean': vbar, 'ell_c_m': full['tau_int_s'] * vbar,
               'frac_moving': float(np.nanmean(sp > 0.02))}
    return ha_rows, he_rows, expl, hd_rows, hd_case


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in MANIFEST['cases'] if c['id'] == a.case)
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(one('OOF_PARAMETERS.csv.gz'))
    model = SourceFFD(); arms = arm_specs(); rows = []; qas = []
    for bias, ch in CONDITIONS:
        r, q = replay(model, case, bias, ch, feat, par, arms); rows += r; qas += q
    pd.DataFrame(rows).to_csv(OUT / f'{a.case}_M_SCORES.csv', index=False)
    pd.DataFrame(qas).to_csv(OUT / f'{a.case}_M_QA.csv', index=False)
    ha, he, ex, hd, hdc = hypotheses(model, case, feat)
    pd.DataFrame(ha).to_csv(OUT / f'{a.case}_HA.csv', index=False)
    pd.DataFrame(he).to_csv(OUT / f'{a.case}_HE.csv', index=False)
    pd.DataFrame(ex).to_csv(OUT / f'{a.case}_HE_FEATURES.csv', index=False)
    pd.DataFrame(hd).to_csv(OUT / f'{a.case}_HD_BLOCKS.csv', index=False)
    pd.DataFrame([hdc]).to_csv(OUT / f'{a.case}_HD_CASE.csv', index=False)
    print('CASE_DONE', a.case, len(rows), flush=True)


if __name__ == '__main__':
    main()
