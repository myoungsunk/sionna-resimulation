#!/usr/bin/env python3
"""Stage B: evaluate held route H = route(case). All hyper-parameters from training routes only (stage A outputs + inner POWER)."""
from __future__ import annotations
import argparse, json, math, os
from pathlib import Path
import numpy as np
import pandas as pd
import strict_common as S
from strict_common import V
import mu_recursive as MR

SA = Path(os.environ['PJ_SA'])
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]


def select_eta(sa, fam):
    g = sa[sa.family == fam].copy(); g['dev'] = np.abs(np.log(g.heading_nees_1d))
    med = g.groupby('eta').dev.median(); return float(med.idxmin()), med.round(4).to_dict()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); H = case['route']; T = [r for r in S.ROUTES if r != H]
    data = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    # ---- calibration strictly inside T
    sa = pd.concat([pd.read_csv(p) for p in SA.rglob(f'{H}_*_SA_SCORES.csv')], ignore_index=True)
    sd = pd.concat([pd.read_csv(p) for p in SA.rglob(f'{H}_*_SA_D0.csv.gz')], ignore_index=True)
    assert set(sa.route) == set(T) and H not in set(sa.route) and H not in set(sd.route)
    eta_b, dev_b = select_eta(sa, 'BASE'); eta_m, dev_m = select_eta(sa, 'MUGRAW')
    tau5 = float(sd[sd.t_s >= 30].d0.abs().quantile(0.95))
    PIN = pd.concat([S.power_fit(data, [o for o in T if o != r], r) for r in T], ignore_index=True)   # inner POWER for T routes
    TBALL = V.build_table(); TB = TBALL[(TBALL.channel == 'full') & TBALL.route.isin(T)].drop(columns=['mu_s', 'mu_r', 'Vs', 'Vr'])
    TB = TB.merge(PIN[PIN.channel == 'full'][['case', 'pose_id', 'mu_r', 'mu_s', 'Vr', 'Vs']], on=['case', 'pose_id'])
    two, five = V.calibrations(TB)
    PH = S.power_fit(data, T, H); mu_chk = PH.merge(par[par.model == 'POWER_DIAG'], on=['case', 'channel', 'pose_id'], suffixes=('', '_o'))
    calib = {'held': H, 'train_routes': T, 'eta_star_BASE': eta_b, 'eta_dev_BASE': dev_b, 'eta_star_MU': eta_m, 'eta_dev_MU': dev_m, 'tau5_d0': tau5,
             'ds_tau': two['tau'], 'kappa_r_hi': two['r'][1], 'kappa_s_hi': two['s'][1], 'qa_powerH_vs_oof_mu': float((mu_chk.mu_s - mu_chk.mu_s_o).abs().max()),
             'n_stageA_rows': len(sa)}
    print('CALIB', json.dumps(calib), flush=True)
    FT = MR.feature_table(); tr = FT[(FT.channel == 'full') & FT.route.isin(T)]
    m_ex = MR.hgb(tr, MR.EXIST, 'e_r'); m_ds = MR.hgb(tr, MR.EXIST + MR.DS, 'e_r')
    # arm: (mu model, gate-raw, range-only flag, eta, infl_r)
    E = {'B': eta_b, 'M': eta_m}
    ARMS = {'BASE': (None, False, False, 1., False), 'INFL_R_S': (None, False, False, 1., True), 'MU_R_EX': ('EX', False, False, 1., False),
            'MU_R': ('EXDS', False, False, 1., False), 'MU_R+GRAW': ('EXDS', True, False, 1., False), 'MU_R+RONLY': ('EXDS', False, True, 1., False),
            'MU_R+GRAW+RONLY': ('EXDS', True, True, 1., False), 'BASE_eta*': (None, False, False, E['B'], False), 'MU_R_eta*': ('EXDS', False, False, E['M'], False),
            'MU_R+GRAW_eta*': ('EXDS', True, False, E['M'], False), 'MU_R+GRAW+RONLY_eta*': ('EXDS', True, True, E['M'], False),
            'BASE_eta2': (None, False, False, 2., False), 'BASE_eta3': (None, False, False, 3., False), 'MU_R+GRAW_eta2': ('EXDS', True, False, 2., False),
            'MU_R+GRAW_eta3': ('EXDS', True, False, 3., False), 'INFL_R_S_eta*': (None, False, False, E['B'], True)}
    names = list(ARMS); J = len(names); eta = np.array([ARMS[n][3] for n in names]); model = V.SourceFFD()
    rows, series, det = [], [], []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']; n = len(t)
        b_true = math.radians(V.BIAS_LEVELS[bias])
        d = data[(data.case == a.case) & (data.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        mu0, R0 = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        fx = FT[(FT.case == a.case) & (FT.channel == ch)].set_index('pose_id').loc[ids]
        pred = {'EX': m_ex.predict(fx[MR.EXIST]), 'EXDS': m_ds.predict(fx[MR.EXIST + MR.DS])}
        tab = TBALL[(TBALL.case == a.case) & (TBALL.channel == ch)].set_index('pose_id').loc[ids]
        hi_r = V.factors(tab.a.to_numpy(), two, five, 'HI', 'r')
        MUU = np.repeat(mu0[:, None, :], J, axis=1).copy(); MUG = MUU.copy(); FR = np.ones((n, J))
        for j, nm in enumerate(names):
            mm, graw, _, _, infl = ARMS[nm]
            if mm: MUU[:, j, 0] = pred[mm]
            if mm and not graw: MUG[:, j, 0] = pred[mm]
            if infl: FR[:, j] = hi_r
        ron = np.array([ARMS[n_][2] for n_ in names])
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool); flag = np.zeros((n, J), bool)
        D0 = np.empty((n, J)); HPH = np.empty((n, J)); PE = np.empty((n, J))
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case); D0[k] = z[k, 1] - h[:, 1]; PE[k] = V.MC.wrap(x[:, 2] - truth[k, 2]) * S.DEG
            HPH[k] = np.einsum('ji,jik,jk->j', Hk[:, 1, :], P, Hk[:, 1, :])
            fl = ron & (np.abs(D0[k]) > tau5); flag[k] = fl
            Rp = np.repeat(R0[k][None], J, axis=0).copy(); Rp[:, 0, 0] *= FR[k]; Re = Rp * eta[:, None, None]
            x, P, nis, yes = S.update(x, P, z[k], h, Hk, MUU[k], MUG[k], Rp, Re, fl); X[k] = x; C[k] = P; acc[k] = yes
        sc = V.MC.score(X, C, t, truth, b_true); ex, ser = S.score_extra(X, C, t, truth, case); m = t >= 30
        for j, nm in enumerate(names):
            rows.append({'case': a.case, 'route': H, 'bias': bias, 'channel': ch, 'arm': nm, 'eta': eta[j], **ex[j], 'heading_rmse_deg_mc': sc[j]['heading_rmse_deg'],
                         'acc': float(acc[m, j].mean()), 'frac_ronly': float(flag[m, j].mean())})
        if ch == 'full':
            sr = pd.DataFrame({'case': a.case, 'bias': bias, 'k': np.arange(n), 't_s': t, 'pose_id': ids})
            for j, nm in enumerate(names):
                for key_, v in ser[j].items(): sr[f'{nm}__{key_}'] = v
            series.append(sr)
            for nm in ['BASE', 'MU_R']:
                j = names.index(nm); nu = D0[:, j] - MUU[:, j, 1]
                det.append(pd.DataFrame({'case': a.case, 'bias': bias, 'prior_arm': nm, 't_s': t, 'd0': D0[:, j], 'nu_s': nu, 'hph_ss': HPH[:, j], 'Vs': R0[:, 1, 1], 'e_s': d.e_s.to_numpy(),
                                         'prior_psi_err_deg': PE[:, j]}))
        print('SB_DONE', stem, flush=True)
    out = V.OUT
    pd.DataFrame(rows).to_csv(out / f'{a.case}_SB_SCORES.csv', index=False); pd.concat(series).to_csv(out / f'{a.case}_SB_SERIES.csv.gz', index=False, compression='gzip')
    pd.concat(det).to_csv(out / f'{a.case}_SB_DET.csv.gz', index=False, compression='gzip'); (out / f'{a.case}_SB_CALIB.json').write_text(json.dumps(calib, indent=2))
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
