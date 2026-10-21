#!/usr/bin/env python3
"""Why does range mean correction enlarge the polarization (U_S) heading path? Gate on/off arms and
counterfactual U_S propagation that swaps the acceptance mask / gain sequence between BASE and range-corrected arms."""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
import d1_core as D
from core import transition
import mu_recursive as MR

ARMS = [('BASE', None, True), ('MU_R_EXDS', 'EXDS', True), ('MU_R_ORACLE', 'ORACLE', True),
        ('BASE_NOGATE', None, False), ('MU_R_EXDS_NOGATE', 'EXDS', False), ('MU_R_ORACLE_NOGATE', 'ORACLE', False)]
CONDITIONS = [('B0', 'full'), ('L2', 'full')]
DEG = 180 / math.pi


def us_path(F, K, H, a, u_s):
    """Heading part of the U_S component for one arm's matrices (n,4,4),(n,4,2),(n,2,4), mask a (n,), u_s (n,)."""
    n = len(a); Ka = np.where(a[:, None, None], K, 0.); Aup = D.I4[None] - Ka @ H; c = np.zeros((n, 4)); prev = np.zeros(4)
    for k in range(n):
        cm = prev if k == 0 else F[k] @ prev
        c[k] = Aup[k] @ cm + Ka[k][:, 1] * u_s[k]; prev = c[k]
    return c[:, 2] * DEG


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    FT = MR.feature_table(); tr = FT[(FT.channel == 'full') & (FT.route != held)]
    m_r = MR.hgb(tr, MR.EXIST + MR.DS, 'e_r')
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    model = V.SourceFFD(); J = len(ARMS); rows, cf_rows, series = [], [], []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n = len(t); b_true = math.radians(V.BIAS_LEVELS[bias]); truth4 = np.column_stack([truth, np.full(n, b_true)])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float); e = d[['e_r', 'e_s']].to_numpy(float)
        fx = FT[(FT.case == a.case) & (FT.channel == ch)].set_index('pose_id').loc[ids]; pr = m_r.predict(fx[MR.EXIST + MR.DS])
        mu0, R0b = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        MU = np.repeat(mu0[:, None, :], J, axis=1).copy(); RR = np.repeat(R0b[:, None], J, axis=1).copy(); RG = RR.copy()
        for j, (nm, mr, g) in enumerate(ARMS):
            if mr: MU[:, j, 0] = e[:, 0] if mr == 'ORACLE' else pr
            if not g: RG[:, j] *= 1e12
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool); NIS = np.empty((n, J))
        F = np.zeros((n, J, 4, 4)); K = np.zeros((n, J, 4, 2)); H = np.zeros((n, J, 2, 4)); NU = np.empty((n, J, 2))
        for k in range(n):
            if k:
                ds_, gy, dt = float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k])
                for j in range(J):
                    F[k, j] = transition(x[j], ds_, gy, dt)[1]; x[j], P[j] = V.predict_one(x[j], P[j], ds_, gy, dt)
            h, Hk = model.batch(x, case); NU[k] = z[k][None] - h - MU[k]
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RG[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P; acc[k] = yes; K[k] = Kk; H[k] = Hk; NIS[k] = nis
        sc = V.MC.score(X, C, t, truth, b_true); m = t >= 30; u_s = e[:, 1] - mu0[:, 1]
        herr = D.wrap(X[..., 2] - truth[:, None, 2]) * DEG
        for j, (nm, mr, g) in enumerate(ARMS):
            na = ~acc[:, 0] & acc[:, j]; nr = acc[:, 0] & ~acc[:, j]
            rows.append({'case': a.case, 'bias': bias, 'arm': nm, **sc[j], 'acc': float(acc[m, j].mean()), 'n_new_accept': int((na & m).sum()), 'n_new_reject': int((nr & m).sum()),
                         'abs_es_new_accept': float(np.abs(e[na & m, 1]).mean()) if (na & m).any() else np.nan, 'abs_es_all': float(np.abs(e[m, 1]).mean()),
                         'abs_es_rejected_base': float(np.abs(e[m & ~acc[:, 0], 1]).mean()) if (m & ~acc[:, 0]).any() else np.nan})
        # counterfactual U_S heading path: matrices from arm j, mask from arm i
        pairs = [(0, 0), (1, 1), (2, 2), (1, 0), (2, 0), (0, 1), (0, 2), (3, 3), (4, 4), (5, 5)]
        for jm, ja in pairs:
            q = us_path(F[:, jm], K[:, jm], H[:, jm], acc[:, ja], u_s)
            cf_rows.append({'case': a.case, 'bias': bias, 'matrices_from': ARMS[jm][0], 'mask_from': ARMS[ja][0], 'us_heading_ms': float(np.mean(q[m] ** 2)), 'us_heading_mean': float(np.mean(q[m]))})
        sr = pd.DataFrame({'case': a.case, 'bias': bias, 'k': np.arange(n), 't_s': t, 'pose_id': ids, 'e_s': e[:, 1], 'e_r': e[:, 0]})
        for j, (nm, *_r) in enumerate(ARMS):
            sr[f'{nm}__acc'] = acc[:, j]; sr[f'{nm}__nis'] = NIS[:, j]; sr[f'{nm}__nu_r'] = NU[:, j, 0]; sr[f'{nm}__nu_s'] = NU[:, j, 1]; sr[f'{nm}__herr'] = herr[:, j]
        series.append(sr); print('HG_DONE', stem, flush=True)
    pd.DataFrame(rows).to_csv(V.OUT / f'{a.case}_HG_SCORES.csv', index=False); pd.DataFrame(cf_rows).to_csv(V.OUT / f'{a.case}_HG_CF.csv', index=False)
    pd.concat(series).to_csv(V.OUT / f'{a.case}_HG_SERIES.csv.gz', index=False, compression='gzip'); print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
