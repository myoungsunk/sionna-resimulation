#!/usr/bin/env python3
"""Trade-off path analysis: exact error-path decomposition for delta-s variance arms (no new fitting)."""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V          # sets paths, loads SourceFFD etc.
import d1_core as D
from core import transition

ARMS = [('BASE', 'BASE', 'BASE'), ('INFL_S', 'HI', 'BASE'), ('DEFL_S', 'LO', 'BASE'), ('INFL_R', 'BASE', 'HI'), ('DEFL_R', 'BASE', 'LO'), ('MIX_IR_DS', 'LO', 'HI')]
CONDITIONS = [('B0', 'full'), ('L2', 'full')]
DEG = 180 / math.pi


def lf(u, w):
    return np.stack([pd.DataFrame(u[:, j, :]).rolling(w, center=True, min_periods=1).mean().to_numpy() for j in range(u.shape[1])], axis=1)


def attribution(comps, uh, ut, m):
    """Exact additive attribution: contrib_c = mean(q_c * q_total); sum equals mean(q_total^2)."""
    q = {'heading_deg': lambda c: c[..., 2] * DEG,
         'radial_cm': lambda c: (c[..., 0] * uh[:, None, 0] + c[..., 1] * uh[:, None, 1]) * 100,
         'tangential_cm': lambda c: (c[..., 0] * ut[:, None, 0] + c[..., 1] * ut[:, None, 1]) * 100}
    tot = sum(comps.values()); out = {}
    for qn, f in q.items():
        T = f(tot)[m]
        for cn, c in comps.items():
            C = f(c)[m]
            out[(qn, cn)] = (np.mean(C * T, axis=0), np.mean(C ** 2, axis=0))
        out[(qn, 'TOTAL')] = (np.mean(T ** 2, axis=0), np.mean(T ** 2, axis=0))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    T = V.build_table(); tr = T[(T.channel == 'full') & (T.route != held)]
    two, five = V.calibrations(tr)
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    model = V.SourceFFD(); rows_attr, rows_gain, rows_score, qa = [], [], [], []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n, J = len(t), len(ARMS); b_true = math.radians(V.BIAS_LEVELS[bias]); truth4 = np.column_stack([truth, np.full(n, b_true)])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        e = d[['e_r', 'e_s']].to_numpy(float)
        tc = T[(T.case == a.case) & (T.channel == ch)].set_index('pose_id').loc[ids]; aa = tc.a.to_numpy(); gate = aa >= two['tau']
        mu0, R0b = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        MU = np.repeat(mu0[:, None, :], J, axis=1); RR = np.repeat(R0b[:, None], J, axis=1).copy()
        for j, (arm, ks, kr) in enumerate(ARMS):
            RR[:, j, 1, 1] *= V.factors(aa, two, five, ks, 's'); RR[:, j, 0, 0] *= V.factors(aa, two, five, kr, 'r')
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool)
        F = np.zeros((n, J, 4, 4)); K = np.zeros((n, J, 4, 2)); H = np.zeros((n, J, 2, 4)); w = np.zeros((n, 4)); em = np.zeros((n, J, 4)); Pm = np.zeros((n, J, 4, 4))
        for k in range(n):
            if k:
                ds, gy, dt = float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k])
                for j in range(J):
                    F[k, j] = transition(x[j], ds, gy, dt)[1]
                    x[j], P[j] = V.predict_one(x[j], P[j], ds, gy, dt)
                wk = truth4[k] - transition(truth4[k - 1], ds, gy, dt)[0]; wk[2] = D.wrap(wk[2]); w[k] = wk
            h, Hk = model.batch(x, case)
            em[k] = D.err(x, truth4[k]); Pm[k] = P
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P; acc[k] = yes; K[k] = Kk; H[k] = Hk
        ep = D.err(X, truth4[:, None, :]); u = e[:, None, :] - MU; m = t >= 30
        anc = np.asarray(case['anchor'], float)
        uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True); ut = np.column_stack([-uh[:, 1], uh[:, 0]])
        dt_med = float(np.median(np.diff(t))); wl = max(1, int(round(2.0 / dt_med))) | 1
        splits = {'time': lf(u, wl), 'gate': u * gate[:, None, None]}
        closure = 0.
        for sname, uf in splits.items():
            comps, Aup, Ka = D.decompose(F, K, H, acc, w, u, em, ep, uf)
            tot = sum(comps.values())
            closure = max(closure, float(np.max(np.abs(D.wrap(tot[..., 2] - ep[..., 2])))), float(np.max(np.abs(tot[..., :2] - ep[..., :2]))))
            ren = {'U_R_LF': 'U_R_LF' if sname == 'time' else 'U_R_GATED', 'U_R_HF': 'U_R_HF' if sname == 'time' else 'U_R_UNGATED',
                   'U_S_LF': 'U_S_LF' if sname == 'time' else 'U_S_GATED', 'U_S_HF': 'U_S_HF' if sname == 'time' else 'U_S_UNGATED'}
            comps = {ren.get(k_, k_): v for k_, v in comps.items()}
            att = attribution(comps, uh, ut, m)
            for (qn, cn), (contrib, ms) in att.items():
                for j, (arm, *_r) in enumerate(ARMS):
                    rows_attr.append({'case': a.case, 'bias': bias, 'arm': arm, 'split': sname, 'quantity': qn, 'component': cn, 'contrib': float(contrib[j]), 'ms': float(ms[j])})
        # gain routing at prior, accepted packets, t>=30
        for j, (arm, *_r) in enumerate(ARMS):
            sel = m & acc[:, j]
            sr = np.sqrt(RR[:, j, 0, 0]); ss = np.sqrt(RR[:, j, 1, 1])
            Kpr = K[:, j, 2, 0] * sr * DEG; Kps = K[:, j, 2, 1] * ss * DEG
            Krr = (K[:, j, 0, 0] * uh[:, 0] + K[:, j, 1, 0] * uh[:, 1]) * sr * 100; Krs = (K[:, j, 0, 1] * uh[:, 0] + K[:, j, 1, 1] * uh[:, 1]) * ss * 100
            Pxy = Pm[:, j, :2, :2]; Prad = np.einsum('ni,nij,nj->n', uh, Pxy, uh); Prp = np.einsum('ni,ni->n', uh, Pm[:, j, :2, 2])
            row = {'case': a.case, 'bias': bias, 'arm': arm}
            for sub, msk in [('all', sel), ('gated', sel & gate), ('ungated', sel & ~gate)]:
                if msk.sum() == 0: continue
                row.update({f'{sub}_Kpsi_r_deg': float(np.median(np.abs(Kpr[msk]))), f'{sub}_Kpsi_s_deg': float(np.median(np.abs(Kps[msk]))),
                            f'{sub}_Krad_r_cm': float(np.median(np.abs(Krr[msk]))), f'{sub}_Krad_s_cm': float(np.median(np.abs(Krs[msk])))})
            row.update({'prior_sig_psi_deg': float(np.median(np.sqrt(Pm[sel, j, 2, 2])) * DEG), 'prior_sig_rad_cm': float(np.median(np.sqrt(Prad[sel])) * 100),
                        'prior_rho_rad_psi': float(np.median(Prp[sel] / np.sqrt(Prad[sel] * Pm[sel, j, 2, 2])))})
            rows_gain.append(row)
        sc = V.MC.score(X, C, t, truth, b_true)
        dz = anc[2] - float(case['robot_z_m']); dtrue = np.sqrt((truth[:, 0] - anc[0]) ** 2 + (truth[:, 1] - anc[1]) ** 2 + dz ** 2)
        for j, (arm, *_r) in enumerate(ARMS):
            exy = X[:, j, :2] - truth[:, :2]; rad = np.sum(exy * uh, axis=1)[m]; tan = np.sum(exy * ut, axis=1)[m]
            dhat = np.sqrt((X[:, j, 0] - anc[0]) ** 2 + (X[:, j, 1] - anc[1]) ** 2 + dz ** 2); rerr = (dhat - dtrue)[m]
            rows_score.append({'case': a.case, 'bias': bias, 'arm': arm, **sc[j], 'radial_rmse_cm': float(np.sqrt(np.mean(rad ** 2)) * 100), 'tangential_rmse_cm': float(np.sqrt(np.mean(tan ** 2)) * 100),
                               'range_err_rmse_cm': float(np.sqrt(np.mean(rerr ** 2)) * 100), 'accepted_fraction': float(acc[m, j].mean())})
        qa.append({'case': a.case, 'bias': bias, 'decomp_closure': closure})
        print('TP_DONE', stem, 'closure', closure, flush=True)
    for nm, rows in [('TP_ATTR', rows_attr), ('TP_GAIN', rows_gain), ('TP_SCORES', rows_score), ('TP_QA', qa)]:
        pd.DataFrame(rows).to_csv(V.OUT / f'{a.case}_{nm}.csv', index=False)
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
