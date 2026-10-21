#!/usr/bin/env python3
"""D1: temporal structure of measurement residuals vs recursive Heading overconfidence.
Reads immutable traces of run 39376076166. No fitting, no gate/covariance retuning."""
from __future__ import annotations
import argparse, json, math, os, sys, zlib
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve()
ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_OUT']).resolve()
OUT.mkdir(parents=True, exist_ok=True)
for path in ['research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016', 'research/R5_N4B_20261015',
             'research/PHYSICS_RS_STAGED_20261015/code',
             'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
    sys.path.insert(0, str(ROOT / path))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p0_initial
p0_initial.OUT = OUT
from source_model import SourceFFD
import source_model
source_model.OUT = OUT
from r2_bias_replay import build_positive_bias_controls, predict_one, BIAS_LEVELS, INITIAL_POSE_STD, BIAS_PRIOR_STD
from core import transition
import d1_core as D

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]
M = 200
LF_WINDOW_S = 2.0
SEED = 20261021


def one(path_glob):
    m = sorted(ART.rglob(path_glob))
    assert len(m) == 1, (path_glob, m)
    return m[0]


def analyze(model, case, bias, ch, feat):
    cm = case['id']
    stem = f'{cm}_{ch}_{bias}'
    tr = np.load(one(stem + '_TRACE.npz'), allow_pickle=False)
    X, C, acc = tr['state'], tr['cov'], tr['accepted'].astype(bool)
    arms = [str(a) for a in tr['arms']]
    t, ids, mu, R = tr['t_s'], tr['pose_id'], tr['mu'], tr['R']
    truth = tr['truth_scoring_only']
    n, J = acc.shape
    b_true = math.radians(BIAS_LEVELS[bias])
    truth4 = np.column_stack([truth, np.full(n, b_true)])
    controls, x0 = build_positive_bias_controls(t, truth, bias)
    d = feat[(feat.case == cm) & (feat.channel == ch)].set_index('pose_id').loc[ids]
    z = d[['range_m', 's_fp']].to_numpy(float)
    e = d[['e_r', 'e_s']].to_numpy(float)
    u = e[:, None, :] - mu
    dt = float(np.median(np.diff(t)))

    F = np.zeros((n, J, 4, 4)); K = np.zeros((n, J, 4, 2)); H = np.zeros((n, J, 2, 4))
    w = np.zeros((n, 4)); em = np.zeros((n, J, 4))
    qa_dx = qa_dP = 0.0
    xm = np.tile(np.r_[x0, 0.], (J, 1))
    Pm = np.tile(np.diag(np.r_[INITIAL_POSE_STD ** 2, BIAS_PRIOR_STD ** 2]), (J, 1, 1))
    for k in range(n):
        if k:
            ds, gy, dtk = float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k])
            for j in range(J):
                xm[j], Pm[j] = predict_one(X[k - 1, j], C[k - 1, j], ds, gy, dtk)
                F[k, j] = transition(X[k - 1, j], ds, gy, dtk)[1]
            wk = truth4[k] - transition(truth4[k - 1], ds, gy, dtk)[0]
            wk[2] = D.wrap(wk[2]); w[k] = wk
        h, Hk = model.batch(xm, case)
        S = Hk @ Pm @ np.swapaxes(Hk, -1, -2) + R[k]; S = 0.5 * (S + np.swapaxes(S, -1, -2))
        Kk = np.swapaxes(np.linalg.solve(S, Hk @ Pm), -1, -2)
        nu = z[k] - h - mu[k]
        xr = xm + np.einsum('jab,jb->ja', Kk, nu); xr[:, 2] = D.wrap(xr[:, 2])
        A = np.eye(4)[None] - Kk @ Hk
        Pr = A @ Pm @ np.swapaxes(A, -1, -2) + Kk @ R[k] @ np.swapaxes(Kk, -1, -2); Pr = 0.5 * (Pr + np.swapaxes(Pr, -1, -2))
        xr = np.where(acc[k][:, None], xr, xm); Pr = np.where(acc[k][:, None, None], Pr, Pm)
        dx = np.abs(xr - X[k]); dx[:, 2] = np.abs(D.wrap(xr[:, 2] - X[k][:, 2]))
        qa_dx = max(qa_dx, float(dx.max())); qa_dP = max(qa_dP, float(np.abs(Pr - C[k]).max()))
        K[k], H[k] = Kk, Hk
        em[k] = D.err(xm, truth4[k])
    ep = D.err(X, truth4[:, None, :])
    uf = np.stack([pd.DataFrame(u[:, j, :]).rolling(max(1, int(round(LF_WINDOW_S / dt))) | 1, center=True, min_periods=1).mean().to_numpy()
                   for j in range(J)], axis=1)
    comps, Aup, Ka = D.decompose(F, K, H, acc, w, u, em, ep, uf)
    total = sum(comps.values())
    closure = float(np.max(np.abs(D.wrap(total[..., 2] - ep[..., 2]))))
    closure_all = float(np.max(np.abs(total[..., [0, 1, 3]] - ep[..., [0, 1, 3]])))
    Pu = D.meas_cov(F, Aup, Ka, R)
    mask = t >= 30
    sig2 = C[:, :, 2, 2]
    deg = 180 / math.pi

    scores = pd.read_csv(one(stem + '_SCORES.csv'))
    scores = scores[scores['mode'] == 'NATURAL_RECURSIVE'].set_index('model')
    rows_comp, rows_sur, rows_acf, rows_scalar, rows_cov = [], [], [], [], []
    ufull = comps['U_R_LF'] + comps['U_R_HF'] + comps['U_S_LF'] + comps['U_S_HF']
    other = comps['INIT'] + comps['PROCESS'] + comps['LIN']
    L = np.linalg.cholesky(R)
    ut = np.linalg.solve(L, u[..., None])[..., 0]
    rng = np.random.default_rng(SEED + zlib.crc32(stem.encode()) % 100000)
    SH, PH = D.surrogates(ut, L, M, rng)
    eps_sh = D.propagate_meas(F, Aup, Ka, SH)
    eps_ph = D.propagate_meas(F, Aup, Ka, PH)
    head_rms_total = np.sqrt(np.mean(ep[mask, :, 2] ** 2, axis=0))
    for j, arm in enumerate(arms):
        base = dict(case=cm, bias=bias, channel=ch, model=arm)
        cov_check = D.coverage(ep[mask, j, 2], sig2[mask, j])
        for name, c in list(comps.items()) + [('U_ALL', ufull), ('OTHER', other)]:
            rows_comp.append({**base, 'component': name,
                              'heading_rms_deg': float(np.sqrt(np.mean(c[mask, j, 2] ** 2)) * deg),
                              'heading_mean_deg': float(np.mean(c[mask, j, 2]) * deg),
                              'heading_mse_deg2': float(np.mean(c[mask, j, 2] ** 2) * deg ** 2),
                              'bias_rms_dps': float(np.sqrt(np.mean(c[mask, j, 3] ** 2)) * deg),
                              'xy_rms_m': float(np.sqrt(np.mean(np.sum(c[mask, j, :2] ** 2, axis=1)))),
                              'share_of_total_heading_rms': float(np.sqrt(np.mean(c[mask, j, 2] ** 2)) / head_rms_total[j])})
        pu = Pu[mask, j, 2, 2]
        for kind, eps in [('ACTUAL', ufull[None, :, j, 2]), ('SHUFFLE', eps_sh[:, :, j, 2]), ('PHASE', eps_ph[:, :, j, 2])]:
            ne_u = np.array([D.nees(x[mask], pu) for x in eps]); cv_u = np.array([D.coverage(x[mask], pu) for x in eps])
            tot = other[None, mask, j, 2] + eps[:, mask]
            ne_t = np.array([D.nees(x, sig2[mask, j]) for x in tot]); cv_t = np.array([D.coverage(x, sig2[mask, j]) for x in tot])
            rmse_t = np.sqrt(np.mean(tot ** 2, axis=1)) * deg
            rows_sur.append({**base, 'kind': kind, 'M': len(eps), 'nees_u_mean': float(ne_u.mean()), 'nees_u_median': float(np.median(ne_u)),
                             'cov95_u_mean': float(cv_u.mean()), 'nees_total_mean': float(ne_t.mean()), 'cov95_total_mean': float(cv_t.mean()),
                             'heading_rmse_total_mean_deg': float(rmse_t.mean())})
        for ci, cname in enumerate(['r', 's']):
            rows_acf.append({**base, 'whitened_channel': cname, 'dt_s': dt, **D.acf_stats(ut[:, j, ci], dt)})
        a1 = D.acf_stats(ut[:, j, 1], dt)['lag1_noncentred']
        gain = (Ka[:, j, 2, 1] * H[:, j, 1, 2])[mask & acc[:, j]]
        lam = 1 - float(np.median(gain)) if gain.size else float('nan')
        rows_scalar.append({**base, 'a_lag1_s': a1, 'lambda': lam, 'gamma_scalar': (1 + lam * a1) / (1 - lam * a1),
                            'rho_rs_whitened_lag0': float(np.mean(ut[:, j, 0] * ut[:, j, 1]) / np.sqrt(np.mean(ut[:, j, 0] ** 2) * np.mean(ut[:, j, 1] ** 2))),
                            'packet_joint95_whitened': float(np.mean(np.sum(ut[:, j] ** 2, axis=1) <= 5.991464547107979)),
                            'heading95_trace_check_absdiff': abs(cov_check - float(scores.loc[arm, 'heading95'])),
                            'heading_rmse_trace_deg': float(head_rms_total[j] * deg),
                            'heading95_trace': cov_check, 'heading_sigma_mean_deg': float(np.mean(np.sqrt(sig2[mask, j])) * deg)})
    jp = arms.index('POWER1')
    dP, sP = ep[mask, jp, 2], sig2[mask, jp]
    for j, arm in enumerate(arms):
        dA, sA = ep[mask, j, 2], sig2[mask, j]
        cPP, cPA, cAA = D.coverage(dP, sP), D.coverage(dP, sA), D.coverage(dA, sA)
        rows_cov.append({'case': cm, 'bias': bias, 'channel': ch, 'model': arm, 'cov_power': cPP, 'cov_arm': cAA,
                         'sigma_effect': cPA - cPP, 'delta_effect': cAA - cPA, 'total_change': cAA - cPP,
                         'rms_heading_diff_vs_power_deg': float(np.sqrt(np.mean((dA - dP) ** 2)) * deg),
                         'sigma_ratio_mean': float(np.mean(np.sqrt(sA / sP)))})
    qa = {'case': cm, 'bias': bias, 'channel': ch, 'n': n, 'J': J, 'dt_s': dt, 'reconstruct_max_dx': qa_dx, 'reconstruct_max_dP': qa_dP,
          'decomp_closure_heading_rad': closure, 'decomp_closure_other': closure_all, 'M': M, 'lf_window_s': LF_WINDOW_S,
          'QA0_pass': bool(qa_dx < 1e-8 and qa_dP < 1e-8)}
    if ch == 'full' and bias == 'B0':
        np.savez_compressed(OUT / f'{stem}_HEADING_COMPONENTS.npz', t_s=t.astype(np.float32), arms=np.array(arms),
                            heading_error=ep[:, :, 2].astype(np.float32), heading_sigma=np.sqrt(sig2).astype(np.float32),
                            accepted=acc, **{f'c_{k}': v[:, :, 2].astype(np.float32) for k, v in comps.items()},
                            ut_r=ut[:, :, 0].astype(np.float32), ut_s=ut[:, :, 1].astype(np.float32),
                            P_u_heading=Pu[:, :, 2, 2].astype(np.float32))
    print('D1_DONE', stem, json.dumps(qa), flush=True)
    return rows_comp, rows_sur, rows_acf, rows_scalar, rows_cov, qa


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); args = ap.parse_args()
    case = next(c for c in MANIFEST['cases'] if c['id'] == args.case)
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    model = SourceFFD()
    acc = [[] for _ in range(5)]; qas = []
    for bias, ch in CONDITIONS:
        res = analyze(model, case, bias, ch, feat)
        for i in range(5): acc[i] += res[i]
        qas.append(res[5])
    for name, rows in zip(['COMPONENTS', 'SURROGATE', 'ACF', 'SCALAR', 'COVATTR'], acc):
        pd.DataFrame(rows).to_csv(OUT / f'{args.case}_D1_{name}.csv', index=False)
    (OUT / f'{args.case}_D1_QA.json').write_text(json.dumps(qas, indent=2))


if __name__ == '__main__':
    main()
