#!/usr/bin/env python3
"""Adaptive COMMON inflation replay for one case (gate with packet R, update with eta_k R)."""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

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
from r2_bias_replay import build_positive_bias_controls, predict_one, BIAS_LEVELS, INITIAL_POSE_STD, BIAS_PRIOR_STD
import m_core as MC
import a_core as A

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def eta_bounds(route):
    s = pd.read_csv(D1RES / 'D1_SURROGATE.csv')
    s = s[(s.channel == 'full') & (s.bias == 'B0') & (s.model == 'POWER_DIAG')].pivot_table(index='case', columns='kind', values='nees_u_mean')
    r = (s.ACTUAL / s.SHUFFLE); r = r[[c[:2] != route for c in r.index]]
    return float(r.median()), float(r.max())


def arm_specs(route):
    med, mx = eta_bounds(route)
    arms = [dict(arm=f'FIX_{e:g}', base='POWER_DIAG', mode='fixed', eta0=float(e), eta_max=float(e), ch=None) for e in [1, 2, 3, 4, 6, 8]]
    arms += [dict(arm='FIX_MED', base='POWER_DIAG', mode='fixed', eta0=med, eta_max=med, ch=None),
             dict(arm='ADAPT_RS_MAX', base='POWER_DIAG', mode='adapt', eta0=1., eta_max=mx, ch='rs'),
             dict(arm='ADAPT_S_MAX', base='POWER_DIAG', mode='adapt', eta0=1., eta_max=mx, ch='s'),
             dict(arm='ADAPT_RS_MED', base='POWER_DIAG', mode='adapt', eta0=1., eta_max=med, ch='rs'),
             dict(arm='ADAPT_RS_NOCAP', base='POWER_DIAG', mode='adapt', eta0=1., eta_max=24., ch='rs'),
             dict(arm='REF_POWER1', base='POWER1', mode='fixed', eta0=1., eta_max=1., ch=None)]
    return arms, med, mx


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
    z = d[['range_m', 's_fp']].to_numpy(float)
    bases = {b: base_params(par, cm, ch, ids, b) for b in {a['base'] for a in arms}}
    MU = np.stack([bases[a['base']][0] for a in arms], axis=1); RP = np.stack([bases[a['base']][1] for a in arms], axis=1)
    eta = np.array([a['eta0'] for a in arms], float)
    acf_rs = [A.InnovACF() for _ in arms]; acf_s = [A.InnovACF() for _ in arms]
    controls, x0 = build_positive_bias_controls(t, truth, bias)
    x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[INITIAL_POSE_STD ** 2, BIAS_PRIOR_STD ** 2]), (J, 1, 1))
    X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool)
    ETA = np.empty((n, J)); RAW_RS = np.full((n, J), np.nan); RAW_S = np.full((n, J), np.nan)
    for k in range(n):
        if k:
            for j in range(J):
                x[j], P[j] = predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
        h, H = model.batch(x, case)
        RE = RP[k] * eta[:, None, None]
        v = z[k][None] - h - MU[k]
        Se = H @ P @ np.swapaxes(H, -1, -2) + RE; Se = .5 * (Se + np.swapaxes(Se, -1, -2))
        vrs, vs = A.whiten(v, Se)
        ETA[k] = eta
        x, P, nis, yes, K = MC.update(x, P, z[k], h, H, MU[k], RP[k], RE, np.ones(J))
        X[k] = x; C[k] = P; acc[k] = yes
        for j, a in enumerate(arms):
            if yes[j]:
                acf_rs[j].push(vrs[j]); acf_s[j].push(vs[j])
            RAW_RS[k, j] = acf_rs[j].eta_raw(); RAW_S[k, j] = acf_s[j].eta_raw()
            if a['mode'] == 'adapt':
                eta[j] = A.step_eta(eta[j], RAW_RS[k, j] if a['ch'] == 'rs' else RAW_S[k, j], a['eta_max'])
    assert np.isfinite(X).all() and np.linalg.eigvalsh(C).min() > 0
    sc = MC.score(X, C, t, truth, b_true); m = t >= 30
    rows = []
    for j, a in enumerate(arms):
        rows.append({'case': cm, 'route': case['route'], 'bias': bias, 'channel': ch, **{k: a[k] for k in ['arm', 'mode', 'eta_max', 'ch']}, **sc[j],
                     'accepted_fraction': float(acc[m, j].mean()), 'eta_mean': float(ETA[m, j].mean()), 'eta_min': float(ETA[m, j].min()),
                     'eta_max_reached': float(ETA[m, j].max()), 'eta_final': float(ETA[-1, j]),
                     'frac_at_cap': float(np.mean(ETA[m, j] >= a['eta_max'] - 1e-9)) if a['mode'] == 'adapt' else np.nan,
                     'openloop_eta_raw_rs_mean': float(np.nanmean(RAW_RS[m, j])), 'openloop_eta_raw_s_mean': float(np.nanmean(RAW_S[m, j]))})
    old_sc = pd.read_csv(one(stem + '_SCORES.csv')); old_sc = old_sc[old_sc['mode'] == 'NATURAL_RECURSIVE'].set_index('model')
    qa = []
    for arm, ref in [('FIX_1', 'POWER_DIAG'), ('REF_POWER1', 'POWER1')]:
        r = next(x for x in rows if x['arm'] == arm)
        qa.append({'case': cm, 'bias': bias, 'channel': ch, 'arm': arm, 'ref': ref,
                   'd_rmse': abs(r['heading_rmse_deg'] - old_sc.loc[ref, 'heading_rmse_deg']), 'd_h95': abs(r['heading95'] - old_sc.loc[ref, 'heading95'])})
    traj = []
    sel = [j for j, a in enumerate(arms) if a['mode'] == 'adapt' or a['arm'] in ('FIX_1', 'FIX_MED')]
    for j in sel:
        e = MC.wrap(X[:, j, 2] - truth[:, 2])
        traj.append(pd.DataFrame({'case': cm, 'bias': bias, 'channel': ch, 'arm': arms[j]['arm'], 't_s': np.round(t, 3), 'eta': ETA[:, j],
                                  'eta_raw_rs': RAW_RS[:, j], 'eta_raw_s': RAW_S[:, j], 'heading_err_deg': np.degrees(e),
                                  'heading_sigma_deg': np.degrees(np.sqrt(C[:, j, 2, 2])), 'accepted': acc[:, j]}))
    print('A_REPLAY_DONE', stem, json.dumps(qa), flush=True)
    return rows, qa, pd.concat(traj)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in MANIFEST['cases'] if c['id'] == a.case)
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(one('OOF_PARAMETERS.csv.gz'))
    arms, med, mx = arm_specs(case['route'])
    print('ETA_BOUNDS', a.case, case['route'], 'MED', med, 'MAX', mx, flush=True)
    model = SourceFFD(); rows = []; qas = []; trajs = []
    for bias, ch in CONDITIONS:
        r, q, tr = replay(model, case, bias, ch, feat, par, arms); rows += r; qas += q; trajs.append(tr)
    pd.DataFrame(rows).to_csv(OUT / f'{a.case}_A_SCORES.csv', index=False)
    pd.DataFrame(qas).to_csv(OUT / f'{a.case}_A_QA.csv', index=False)
    pd.concat(trajs).to_csv(OUT / f'{a.case}_A_TRAJ.csv.gz', index=False, compression='gzip')
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
