#!/usr/bin/env python3
"""d0-based polarization rejection that tries to separate multipath from state error, under the same initial-error
conditions and windows as d0early.py. Rejection = explicit range-only update (chi2_1 gate); otherwise standard 2-D update.
Rules (thresholds from training routes only, or theory):
  RJ_D0    : |d0| > tau5
  RJ_STATE : d0^2 > tau5^2 + 4 * H_s P^- H_s^T          (allow the state-error part implied by the prior)
  RJ_SHAPE : |d0| > tau5 AND shape > tau_shape            (shape = max_o |dS_meas(o) - dS_LUT(o; x^-)|, o=+1,+2,+4; heading-insensitive)
  RJ_ORACLE: |e_s| > q95_T                                (diagnostic upper reference: true multipath only, not online)
Each rule with eta=1 and eta=3 (COMMON: gate with R, update with eta R)."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import strict_common as S
from strict_common import V
from series_dump import taps

HERE = Path(__file__).resolve().parent
CAL = {c['held']: c for c in json.loads((HERE / 'results_strict/SB_CALIB.json').read_text())}
INITS = [('NOM', None, None)] + [(f'E{o:+d}_P{p}', o, p) for o in (10, -10, 20, -20) for p in ('5', 'M')]
RULES = ['NONE', 'RJ_D0', 'RJ_STATE', 'RJ_SHAPE', 'RJ_ORACLE']
ARMS = [(r, e) for e in (1.0, 3.0) for r in RULES]
OF = [1, 2, 4]


def lut_profile(model, states, case):
    h = model.spectrum(states, case, gradient=False)[0]; nf = h.shape[1]
    w = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1)); c = np.fft.ifft(h * w[None, :, None], n=4 * nf, axis=1) * nf
    amp = np.abs(c); pw = amp ** 2; ii = np.arange(len(states)); br = amp.max(axis=1).argmax(axis=1); st = amp[ii, :, br]
    fp = (st >= .3 * st.max(axis=1)[:, None]).argmax(axis=1); nt = c.shape[1]
    def s_at(o):
        P = pw[ii, np.clip(fp + o, 0, nt - 1), :]; den = P.sum(1); return (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1)
    s0 = s_at(0); return np.column_stack([s_at(o) - s0 for o in OF])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); ap.add_argument('--cond', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); H = case['route']; T = [r for r in S.ROUTES if r != H]; tau5 = CAL[H]['tau5_d0']
    data = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    q95 = float(data[(data.channel == 'full') & data.route.isin(T)].e_s.abs().quantile(.95))
    PK = pd.read_csv(HERE / 'results_hpath/HP_PACKETS.csv.gz'); PK = PK[PK.route.isin(T)]
    sh_t = np.max(np.column_stack([np.abs((PK[f'sF_{o:+d}'] - PK['sF_+0']) - (PK[f'sMGT_{o:+d}'] - PK['sMGT_+0'])) for o in OF]), axis=1)
    tau_shape = float(np.nanquantile(sh_t, 0.8))
    bias, ch = a.cond.split('_'); stem = f'{a.case}_{ch}_{bias}'
    old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']; n = len(t)
    d = data[(data.case == a.case) & (data.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float); es = d.e_s.to_numpy()
    Hm = np.load(V.ROOT / case['full_path' if ch == 'full' else 'los_path'], mmap_mode='r', allow_pickle=False)
    allids = pd.DataFrame(json.loads((V.ROOT / case['samples_path']).read_text())).pose_id.to_numpy(int)
    tb = [taps(np.asarray(Hm[k:k + 128, :, :, 0])) for k in range(0, len(Hm), 128)]
    TP = pd.DataFrame({k: np.concatenate([x[k] for x in tb]) for k in tb[0]}); TP['pose_id'] = allids; TP = TP.set_index('pose_id').loc[ids]
    assert np.nanmax(np.abs(TP.s_fp_chk.to_numpy() - d.s_fp.to_numpy())) < 1e-9
    dsm = TP[[f'ds_{o:+d}' for o in OF]].to_numpy()
    mu0, R0 = V.base_params(par, a.case, ch, ids, 'POWER_DIAG'); J = len(ARMS); MU = np.repeat(mu0[:, None, :], J, axis=1)
    eta = np.array([e for _, e in ARMS]); rule = [r for r, _ in ARMS]
    model = V.SourceFFD(); controls, x0r = V.build_positive_bias_controls(t, truth, bias); out = []
    for iname, off, pk in INITS:
        x0 = x0r.copy(); P0 = np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2])
        if off is not None:
            x0[2] = V.MC.wrap(truth[0, 2] + math.radians(off))
            if pk == 'M': P0[2, 2] = math.radians(abs(off)) ** 2
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(P0, (J, 1, 1))
        rec = {k: np.empty((n, J)) for k in ['herr', 'hsig', 'flag']}; det = {k: np.empty(n) for k in ['d0', 'hph', 'shape']}
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case); d0 = z[k, 1] - h[:, 1]; hph = np.einsum('ji,jik,jk->j', Hk[:, 1, :], P, Hk[:, 1, :])
            shape = np.max(np.abs(dsm[k][None] - lut_profile(model, x, case)), axis=1)
            fl = np.zeros(J, bool)
            for j in range(J):
                r = rule[j]
                fl[j] = (r == 'RJ_D0' and abs(d0[j]) > tau5) or (r == 'RJ_STATE' and d0[j] ** 2 > tau5 ** 2 + 4 * hph[j]) or \
                        (r == 'RJ_SHAPE' and abs(d0[j]) > tau5 and shape[j] > tau_shape) or (r == 'RJ_ORACLE' and abs(es[k]) > q95)
            Rp = np.repeat(R0[k][None], J, axis=0); Re = Rp * eta[:, None, None]
            x, P, nis, yes = S.update(x, P, z[k], h, Hk, MU[k], MU[k], Rp, Re, fl)
            rec['flag'][k] = fl; rec['herr'][k] = V.MC.wrap(x[:, 2] - truth[k, 2]) * S.DEG; rec['hsig'][k] = np.sqrt(P[:, 2, 2]) * S.DEG
            det['d0'][k] = d0[0]; det['hph'][k] = hph[0]; det['shape'][k] = shape[0]
        df = pd.DataFrame({'case': a.case, 'route': H, 'bias': bias, 'channel': ch, 'init': iname, 'k': np.arange(n), 't_s': t, 'e_s': es, 'Vs': R0[:, 1, 1],
                           'BASE__d0': det['d0'], 'BASE__hph': det['hph'], 'BASE__shape': det['shape']})
        for j, (r, e) in enumerate(ARMS):
            for kk, v in rec.items(): df[f'{r}_e{e:g}__{kk}'] = v[:, j]
        out.append(df); print('REJ_DONE', stem, iname, flush=True)
    pd.concat(out).to_csv(V.OUT / f'{a.case}_{a.cond}_REJ.csv.gz', index=False, compression='gzip')
    (V.OUT / f'{a.case}_{a.cond}_REJ_META.json').write_text(json.dumps({'case': a.case, 'held': H, 'tau5_d0': tau5, 'tau_shape': tau_shape, 'q95_es_train': q95}, indent=2)); print('CASE_DONE', flush=True)


if __name__ == '__main__':
    main()
