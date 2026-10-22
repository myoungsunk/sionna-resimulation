#!/usr/bin/env python3
"""Stage A (inside the training routes only): for held route H and a training case C (route(C) != H),
run inner filters (inner POWER fit on the other training route only, inner range HGB on the other training route only)
on Full B0/L2 for the eta grid: BASE_eta and MU_R+GRAW_eta. Records scores (for eta selection) and BASE(eta=1) prior d0."""
from __future__ import annotations
import argparse, math
import numpy as np
import pandas as pd
import strict_common as S
from strict_common import V
import mu_recursive as MR


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--held', required=True); ap.add_argument('--case', required=True); a = ap.parse_args()
    H = a.held; case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); rc = case['route']; assert rc != H
    other = [r for r in S.ROUTES if r not in (H, rc)]; assert len(other) == 1
    data = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    PIN = S.power_fit(data, other, rc)                                   # inner POWER for route(C): trained on the other training route only
    FT = MR.feature_table(); tr = FT[(FT.channel == 'full') & (FT.route == other[0])]; m_r = MR.hgb(tr, MR.EXIST + MR.DS, 'e_r')
    arms = [(f'BASE_e{e:g}', False, e) for e in S.ETA_GRID] + [(f'MUGRAW_e{e:g}', True, e) for e in S.ETA_GRID]; J = len(arms)
    model = V.SourceFFD(); rows, d0rows = [], []
    for bias in ['B0', 'L2']:
        stem = f'{a.case}_full_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']; n = len(t)
        b_true = math.radians(V.BIAS_LEVELS[bias])
        d = data[(data.case == a.case) & (data.channel == 'full')].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        mu0, R0 = S.params_for(PIN, a.case, 'full', ids)
        fx = FT[(FT.case == a.case) & (FT.channel == 'full')].set_index('pose_id').loc[ids]; pr = m_r.predict(fx[MR.EXIST + MR.DS])
        MUU = np.repeat(mu0[:, None, :], J, axis=1).copy(); MUG = np.repeat(mu0[:, None, :], J, axis=1).copy()
        eta = np.array([e for _, _, e in arms])
        for j, (_, mu, _) in enumerate(arms):
            if mu: MUU[:, j, 0] = pr
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool); d0 = np.empty(n)
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case); d0[k] = z[k, 1] - h[0, 1]
            Rp = np.repeat(R0[k][None], J, axis=0); Re = Rp * eta[:, None, None]
            x, P, nis, yes = S.update(x, P, z[k], h, Hk, MUU[k], MUG[k], Rp, Re, np.zeros(J, bool)); X[k] = x; C[k] = P; acc[k] = yes
        sc, _ = S.score_extra(X, C, t, truth, case)
        for j, (nm, mu, e) in enumerate(arms):
            rows.append({'held': H, 'case': a.case, 'route': rc, 'bias': bias, 'arm': nm, 'family': 'MUGRAW' if mu else 'BASE', 'eta': e, **sc[j], 'acc': float(acc[t >= 30, j].mean())})
        d0rows.append(pd.DataFrame({'held': H, 'case': a.case, 'route': rc, 'bias': bias, 't_s': t, 'pose_id': ids, 'd0': d0, 'e_s': d.e_s.to_numpy(), 'mu_s_inner': mu0[:, 1]}))
        print('SA_DONE', H, stem, flush=True)
    pd.DataFrame(rows).to_csv(V.OUT / f'{H}_{a.case}_SA_SCORES.csv', index=False)
    pd.concat(d0rows).to_csv(V.OUT / f'{H}_{a.case}_SA_D0.csv.gz', index=False, compression='gzip'); print('CASE_DONE', flush=True)


if __name__ == '__main__':
    main()
