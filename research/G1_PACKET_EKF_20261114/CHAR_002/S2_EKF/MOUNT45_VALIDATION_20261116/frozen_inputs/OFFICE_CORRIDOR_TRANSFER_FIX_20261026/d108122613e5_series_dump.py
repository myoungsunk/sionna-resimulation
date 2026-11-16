#!/usr/bin/env python3
"""Per-step series dump for position-wise regime analysis (no fitting).
Arms: BASE, INFL_R, DEFL_S, MIX_IR_DS (same tau/kappa as before). Conditions Full B0, Full L2."""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import v_replay as V
import d1_core as D

ARMS = [('BASE', 'BASE', 'BASE'), ('INFL_R', 'BASE', 'HI'), ('DEFL_S', 'LO', 'BASE'), ('MIX_IR_DS', 'LO', 'HI')]
CONDITIONS = [('B0', 'full'), ('L2', 'full')]
OFFS = [-8, -4, -2, -1, 1, 2, 4, 8]
DEG = 180 / math.pi


def taps(H):
    H = np.asarray(H, np.complex128); n, nf, _ = H.shape; nt = 4 * nf; ii = np.arange(n)
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[None, :, None], n=nt, axis=1) * nf; amp = np.abs(cir); power = amp ** 2
    branch = amp.max(axis=1).argmax(axis=1); strong = amp[ii, :, branch]; peaks = strong.max(axis=1)
    tap = (strong >= .3 * peaks[:, None]).argmax(axis=1); s = {}
    for o in [0] + OFFS:
        idx = tap + o; ok = (idx >= 0) & (idx < nt); idc = np.clip(idx, 0, nt - 1); P = power[ii, idc, :]; den = P.sum(axis=1)
        s[o] = np.where(ok & (den > 0), (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1), np.nan)
    out = {f'ds_{o:+d}': s[o] - s[0] for o in OFFS}; out['s_fp_chk'] = s[0]; out['fp_rel_power'] = peaks
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in V.MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    T = V.build_table(); tr = T[(T.channel == 'full') & (T.route != held)]
    two, five = V.calibrations(tr)
    feat = pd.read_csv(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(V.one('OOF_PARAMETERS.csv.gz'))
    Hfull = np.load(V.ROOT / case['full_path'], mmap_mode='r', allow_pickle=False)
    ids_all = pd.DataFrame(__import__('json').loads((V.ROOT / case['samples_path']).read_text())).pose_id.to_numpy(int)
    b = [taps(np.asarray(Hfull[k:k + 128, :, :, 0])) for k in range(0, len(Hfull), 128)]
    TAPS = pd.DataFrame({k: np.concatenate([x[k] for x in b]) for k in b[0]}); TAPS['pose_id'] = ids_all; TAPS = TAPS.set_index('pose_id')
    model = V.SourceFFD(); out = []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(V.one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n, J = len(t), len(ARMS); b_true = math.radians(V.BIAS_LEVELS[bias])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        tc = T[(T.case == a.case) & (T.channel == ch)].set_index('pose_id').loc[ids]; aa = tc.a.to_numpy(); gate = aa >= two['tau']
        tp = TAPS.loc[ids]; assert np.nanmax(np.abs(tp.s_fp_chk.to_numpy() - d.s_fp.to_numpy())) < 1e-9
        mu0, R0b = V.base_params(par, a.case, ch, ids, 'POWER_DIAG')
        MU = np.repeat(mu0[:, None, :], J, axis=1); RR = np.repeat(R0b[:, None], J, axis=1).copy()
        for j, (arm, ks, kr) in enumerate(ARMS):
            RR[:, j, 1, 1] *= V.factors(aa, two, five, ks, 's'); RR[:, j, 0, 0] *= V.factors(aa, two, five, kr, 'r')
        controls, x0 = V.build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[V.INITIAL_POSE_STD ** 2, V.BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool); NIS = np.empty((n, J)); Hsp = np.empty((n, J)); NU = np.empty((n, J, 2)); SS = np.empty((n, J, 2))
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = V.predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, Hk = model.batch(x, case)
            S = Hk @ P @ np.swapaxes(Hk, -1, -2) + RR[k]
            NU[k] = z[k][None] - h - MU[k]; SS[k, :, 0] = S[:, 0, 0]; SS[k, :, 1] = S[:, 1, 1]; Hsp[k] = Hk[:, 1, 2]
            x, P, nis, yes, Kk = V.MC.update(x, P, z[k], h, Hk, MU[k], RR[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P; acc[k] = yes; NIS[k] = nis
        anc = np.asarray(case['anchor'], float); dz = anc[2] - float(case['robot_z_m'])
        dtrue = np.sqrt((truth[:, 0] - anc[0]) ** 2 + (truth[:, 1] - anc[1]) ** 2 + dz ** 2)
        uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True)
        row = pd.DataFrame({'case': a.case, 'route': held, 'bias': bias, 'k': np.arange(n), 't_s': t, 'pose_id': ids, 'x': truth[:, 0], 'y': truth[:, 1], 'yaw_deg': truth[:, 2] * DEG,
                            'e_s': d.e_s.to_numpy(), 'e_r': d.e_r.to_numpy(), 'mu_s': mu0[:, 1], 'mu_r': mu0[:, 0], 'Vs': R0b[:, 1, 1], 'Vr': R0b[:, 0, 0],
                            'abs_ds1': aa, 'gate': gate, 'tau': two['tau'], 'fp_peak': tp.fp_rel_power.to_numpy(), 'log_fp_power': d.log_fp_power.to_numpy()})
        for o in OFFS: row[f'ds_{o:+d}'] = tp[f'ds_{o:+d}'].to_numpy()
        for j, (arm, *_r) in enumerate(ARMS):
            herr = D.wrap(X[:, j, 2] - truth[:, 2]) * DEG; dhat = np.sqrt((X[:, j, 0] - anc[0]) ** 2 + (X[:, j, 1] - anc[1]) ** 2 + dz ** 2)
            row[f'{arm}__est_x'] = X[:, j, 0]; row[f'{arm}__est_y'] = X[:, j, 1]; row[f'{arm}__est_yaw_deg'] = X[:, j, 2] * DEG
            row[f'{arm}__herr_deg'] = herr; row[f'{arm}__hsig_deg'] = np.sqrt(C[:, j, 2, 2]) * DEG
            row[f'{arm}__rad_err_cm'] = np.sum((X[:, j, :2] - truth[:, :2]) * uh, axis=1) * 100; row[f'{arm}__range_err_cm'] = (dhat - dtrue) * 100
            row[f'{arm}__nis'] = NIS[:, j]; row[f'{arm}__acc'] = acc[:, j]; row[f'{arm}__H_spsi'] = Hsp[:, j]
            row[f'{arm}__nu_r_w'] = NU[:, j, 0] / np.sqrt(SS[:, j, 0]); row[f'{arm}__nu_s_w'] = NU[:, j, 1] / np.sqrt(SS[:, j, 1])
            row[f'{arm}__bias_err_dps'] = (X[:, j, 3] - b_true) * DEG
        out.append(row); print('SERIES_DONE', stem, flush=True)
    pd.concat(out).to_csv(V.OUT / f'{a.case}_SERIES.csv.gz', index=False, compression='gzip')
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
