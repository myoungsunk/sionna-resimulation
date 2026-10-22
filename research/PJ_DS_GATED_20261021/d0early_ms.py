#!/usr/bin/env python3
"""MULTI-START variant: the filter is (re)initialised at many points along the route (every 20 s from t=30 s), each run 30 s,
so that early windows contain many multipath packets. Otherwise identical to d0early.py.
d0 early-phase detection: initial heading error 0 (original random draw, sigma 5 deg), +-10, +-20 deg;
P0 heading sigma 5 deg (overconfident) or = |offset| (matched). Passive BASE prior detectors + two active range-only rejection arms.
Thresholds strictly from training routes: tau5 (|d0| 95th pct of inner BASE prior, results_strict/SB_CALIB.json).
Normalised detector uses a theory threshold chi2_1(0.95) on d0^2/(H P H^T + V_s) (no data)."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import strict_common as S
from strict_common import V

HERE = Path(__file__).resolve().parent
CAL = {c['held']: c for c in json.loads((HERE / 'results_strict/SB_CALIB.json').read_text())}
INITS = [('NOM', None, None)] + [(f'E{o:+d}_P{p}', o, p) for o in (10, -10, 20, -20) for p in ('5', 'M')]
ARMS = ['BASE', 'RONLY_D0', 'RONLY_NORM']


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); ap.add_argument('--cond', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); H = case['route']; tau5 = CAL[H]['tau5_d0']
    data = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    T = [r for r in S.ROUTES if r != H]; es_t = data[(data.channel == 'full') & data.route.isin(T)].e_s.abs()
    thr = {'q50': float(es_t.quantile(.5)), 'q90': float(es_t.quantile(.9)), 'q95': float(es_t.quantile(.95))}
    model = V.SourceFFD(); J = len(ARMS); out = []
    for bias, ch in [tuple(a.cond.split('_'))]:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']; n = len(t)
        d = data[(data.case == a.case) & (data.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        mu0, R0 = V.base_params(par, a.case, ch, ids, 'POWER_DIAG'); MU = np.repeat(mu0[:, None, :], J, axis=1)
        controls, _x0 = V.build_positive_bias_controls(t, truth, bias); rng = np.random.default_rng(7)
        starts = [k0 for k0 in range(int(np.searchsorted(t, 30.0)), n - 10, int(round(20.0 / np.median(np.diff(t)))))]
        L = int(round(30.0 / np.median(np.diff(t)))) + 1
        for k0 in starts:
          kk_end = min(n, k0 + L); x0r = truth[k0].copy(); x0r += rng.standard_normal(3) * V.INITIAL_POSE_STD; x0r[2] = V.MC.wrap(x0r[2])
          for iname, off, pk in INITS:
              x0 = x0r.copy(); P0 = np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2])
              if off is not None:
                  x0[2] = V.MC.wrap(truth[k0, 2] + math.radians(off))
                  if pk == 'M': P0[2, 2] = math.radians(abs(off)) ** 2
              x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(P0, (J, 1, 1))
              rec = {k: np.full((n, J), np.nan) for k in ['d0', 'hph', 'herr', 'hsig', 'flag', 'acc']}
              for k in range(k0, kk_end):
                  if k > k0:
                      for j in range(J):
                          x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
                  h, Hk = model.batch(x, case); d0 = z[k, 1] - h[:, 1]; hph = np.einsum('ji,jik,jk->j', Hk[:, 1, :], P, Hk[:, 1, :])
                  fl = np.array([False, abs(d0[1]) > tau5, d0[2] ** 2 / (hph[2] + R0[k, 1, 1]) > S.C1])
                  Rp = np.repeat(R0[k][None], J, axis=0)
                  x, P, nis, yes = S.update(x, P, z[k], h, Hk, MU[k], MU[k], Rp, Rp, fl)
                  rec['d0'][k] = d0; rec['hph'][k] = hph; rec['flag'][k] = fl; rec['acc'][k] = yes
                  rec['herr'][k] = V.MC.wrap(x[:, 2] - truth[k, 2]) * S.DEG; rec['hsig'][k] = np.sqrt(P[:, 2, 2]) * S.DEG
              df = pd.DataFrame({'case': a.case, 'route': H, 'bias': bias, 'channel': ch, 'init': iname, 'start_k': k0, 'k': np.arange(n), 't_s': t - t[k0], 'e_s': d.e_s.to_numpy(), 'Vs': R0[:, 1, 1]})
              for j, nm in enumerate(ARMS):
                  for kk, v in rec.items(): df[f'{nm}__{kk}'] = v[:, j]
              df = df.iloc[k0:kk_end]; out.append(df)
          print('MS_DONE', stem, k0, flush=True)
    R = pd.concat(out); R.to_csv(V.OUT / f'{a.case}_{a.cond}_EARLYMS.csv.gz', index=False, compression='gzip')
    (V.OUT / f'{a.case}_{a.cond}_EARLYMS_META.json').write_text(json.dumps({'case': a.case, 'held': H, 'tau5_d0': tau5, 'es_thresholds_from_train_routes': thr}, indent=2)); print('CASE_DONE', flush=True)


if __name__ == '__main__':
    main()
