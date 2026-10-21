#!/usr/bin/env python3
"""Quick test: POWER variance re-calibrated by |delta-s+1| (mean unchanged), 4-state EKF, eta=1."""
from __future__ import annotations
import argparse, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve(); ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_OUT']).resolve(); OUT.mkdir(parents=True, exist_ok=True)
for path in ['research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016', 'research/R5_N4B_20261015',
             'research/PHYSICS_RS_STAGED_20261015/code', 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
    sys.path.insert(0, str(ROOT / path))
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent / 'PJ_CONSISTENCY_M123_20261021'))
import p0_initial
p0_initial.OUT = OUT
from source_model import SourceFFD
import source_model
source_model.OUT = OUT
from r2_bias_replay import build_positive_bias_controls, predict_one, BIAS_LEVELS, INITIAL_POSE_STD, BIAS_PRIOR_STD
import m_core as MC

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
CONDITIONS = [('B0', 'full'), ('L2', 'full'), ('B0', 'los')]


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def ds1(H):
    H = np.asarray(H, np.complex128); n, nf, _ = H.shape; nt = 4 * nf; ii = np.arange(n)
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[None, :, None], n=nt, axis=1) * nf; amp = np.abs(cir); power = amp ** 2
    branch = amp.max(axis=1).argmax(axis=1); strong = amp[ii, :, branch]; peaks = strong.max(axis=1)
    tap = (strong >= .3 * peaks[:, None]).argmax(axis=1)
    def s_at(o):
        idc = np.clip(tap + o, 0, nt - 1); P = power[ii, idc, :]; den = P.sum(axis=1); return (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1)
    return {'s0': s_at(0), 'ds1': s_at(1) - s_at(0)}


def build_table():
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(one('OOF_PARAMETERS.csv.gz')); par = par[par.model == 'POWER1']
    rows = []
    for c in MANIFEST['cases']:
        ids = pd.DataFrame(json.loads((ROOT / c['samples_path']).read_text())).pose_id.to_numpy(int)
        for ch, key in [('full', 'full_path'), ('los', 'los_path')]:
            H = np.load(ROOT / c[key], mmap_mode='r', allow_pickle=False)
            b = [ds1(np.asarray(H[k:k + 128, :, :, 0])) for k in range(0, len(H), 128)]
            d = pd.DataFrame({k: np.concatenate([x[k] for x in b]) for k in b[0]}); d['pose_id'] = ids
            f = feat[(feat.case == c['id']) & (feat.channel == ch)].set_index('pose_id').loc[ids]
            assert np.nanmax(np.abs(d.s0.to_numpy() - f.s_fp.to_numpy())) < 1e-9
            d['e_s'] = f.e_s.to_numpy(); d['e_r'] = f.e_r.to_numpy()
            p = par[(par.case == c['id']) & (par.channel == ch)].set_index('pose_id').loc[ids]
            for col in ['mu_s', 'mu_r', 'Vs', 'Vr']: d[col] = p[col].to_numpy()
            d['case'] = c['id']; d['route'] = c['route']; d['channel'] = ch; rows.append(d)
    D = pd.concat(rows, ignore_index=True); D['a'] = D.ds1.abs(); return D


def calibrations(tr):
    """Train-only: kappa = mean(r^2/V) per |ds+1| level (2-level at p80; 5-level at quintiles)."""
    rs2 = (tr.e_s - tr.mu_s) ** 2 / tr.Vs; rr2 = (tr.e_r - tr.mu_r) ** 2 / tr.Vr
    t80 = float(np.quantile(tr.a, 0.8)); hi = tr.a >= t80
    two = {'tau': t80, 's': [float(rs2[~hi].mean()), float(rs2[hi].mean())], 'r': [float(rr2[~hi].mean()), float(rr2[hi].mean())]}
    q = np.quantile(tr.a, [.2, .4, .6, .8]).tolist(); b = np.searchsorted(q, tr.a, side='right')
    five = {'cuts': q, 's': [float(rs2[b == k].mean()) for k in range(5)], 'r': [float(rr2[b == k].mean()) for k in range(5)]}
    return two, five


def factors(a, two, five, kind, chan):
    if kind == 'BASE': return np.ones_like(a)
    if kind == '2LVL':
        k = np.array(two[chan]); return k[(a >= two['tau']).astype(int)]
    if kind == 'HI':  # inflate-only: large |ds| packets x kappa_hi, others unchanged
        return np.where(a >= two['tau'], two[chan][1], 1.0)
    if kind == 'LO':  # deflate-only: small |ds| packets x kappa_lo, others unchanged
        return np.where(a >= two['tau'], 1.0, two[chan][0])
    k = np.array(five[chan]); return k[np.searchsorted(five['cuts'], a, side='right')]


def base_params(par, cm, ch, ids, model):
    p = par[(par.case == cm) & (par.channel == ch) & (par.model == model)].set_index('pose_id').loc[ids]
    R = np.zeros((len(ids), 2, 2)); R[:, 0, 0] = p.Vr; R[:, 1, 1] = p.Vs; R[:, 0, 1] = R[:, 1, 0] = p.Crs
    return p[['mu_r', 'mu_s']].to_numpy(float), R


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--case', required=True); a = ap.parse_args()
    case = next(c for c in MANIFEST['cases'] if c['id'] == a.case); held = case['route']
    T = build_table(); tr = T[(T.channel == 'full') & (T.route != held)]
    two, five = calibrations(tr); print('CALIB', a.case, json.dumps({'two': two, 'five': five}), flush=True)
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(one('OOF_PARAMETERS.csv.gz'))
    arms = [('BASE', 'POWER_DIAG', 'BASE', False, False), ('REF_POWER1', 'POWER1', 'BASE', False, False)]
    if os.environ.get('PJ_ARMSET', 'quick1') == 'oneside':
        for kind, tag in [('HI', 'INFL'), ('LO', 'DEFL')]:
            arms += [(f'{tag}_S', 'POWER_DIAG', kind, True, False), (f'{tag}_R', 'POWER_DIAG', kind, False, True), (f'{tag}_SR', 'POWER_DIAG', kind, True, True)]
    else:
        arms += [('V2LVL_S', 'POWER_DIAG', '2LVL', True, False), ('V2LVL_R', 'POWER_DIAG', '2LVL', False, True),
                 ('V2LVL_SR', 'POWER_DIAG', '2LVL', True, True), ('V5BIN_SR', 'POWER_DIAG', '5BIN', True, True)]
    model = SourceFFD(); rows, qa, meas = [], [], []
    for bias, ch in CONDITIONS:
        stem = f'{a.case}_{ch}_{bias}'
        old = np.load(one(stem + '_TRACE.npz'), allow_pickle=False); t, ids, truth = old['t_s'], old['pose_id'], old['truth_scoring_only']
        n, J = len(t), len(arms); b_true = math.radians(BIAS_LEVELS[bias])
        d = feat[(feat.case == a.case) & (feat.channel == ch)].set_index('pose_id').loc[ids]; z = d[['range_m', 's_fp']].to_numpy(float)
        tc = T[(T.case == a.case) & (T.channel == ch)].set_index('pose_id').loc[ids]; aa = tc.a.to_numpy()
        MU = np.empty((n, J, 2)); RR = np.empty((n, J, 2, 2))
        for j, (arm, base, kind, ds_s, ds_r) in enumerate(arms):
            mu, R = base_params(par, a.case, ch, ids, base); R = R.copy()
            if ds_s: R[:, 1, 1] *= factors(aa, two, five, kind, 's')
            if ds_r: R[:, 0, 0] *= factors(aa, two, five, kind, 'r')
            MU[:, j] = mu; RR[:, j] = R
            if bias == 'B0':
                rs = tc.e_s.to_numpy() - mu[:, 1]; rr = tc.e_r.to_numpy() - mu[:, 0]; hi = aa >= two['tau']
                for sub, msk in [('all', np.ones(n, bool)), ('gated', hi), ('ungated', ~hi)]:
                    meas.append({'case': a.case, 'channel': ch, 'arm': arm, 'subset': sub, 'n': int(msk.sum()),
                                 's95': float(np.mean(rs[msk] ** 2 / R[msk, 1, 1] <= 3.841458820694124)), 'r95': float(np.mean(rr[msk] ** 2 / R[msk, 0, 0] <= 3.841458820694124)),
                                 's_nees_pkt': float(np.mean(rs[msk] ** 2 / R[msk, 1, 1])), 'r_nees_pkt': float(np.mean(rr[msk] ** 2 / R[msk, 0, 0]))})
        controls, x0 = build_positive_bias_controls(t, truth, bias)
        x = np.tile(np.r_[x0, 0.], (J, 1)); P = np.tile(np.diag(np.r_[INITIAL_POSE_STD ** 2, BIAS_PRIOR_STD ** 2]), (J, 1, 1))
        X = np.empty((n, J, 4)); C = np.empty((n, J, 4, 4)); acc = np.empty((n, J), bool)
        for k in range(n):
            if k:
                for j in range(J):
                    x[j], P[j] = predict_one(x[j], P[j], float(controls['ds_odom'][k]), float(controls['dtheta_gyro'][k]), float(controls['dt_s'][k]))
            h, H = model.batch(x, case)
            x, P, nis, yes, K = MC.update(x, P, z[k], h, H, MU[k], RR[k], RR[k], np.ones(J))
            X[k] = x; C[k] = P; acc[k] = yes
        sc = MC.score(X, C, t, truth, b_true); m = t >= 30
        for j, (arm, *_r) in enumerate(arms):
            rows.append({'case': a.case, 'route': held, 'bias': bias, 'channel': ch, 'arm': arm, **sc[j], 'accepted_fraction': float(acc[m, j].mean()),
                         'gated_fraction': float(np.mean(aa >= two['tau']))})
        old_sc = pd.read_csv(one(stem + '_SCORES.csv')); old_sc = old_sc[old_sc['mode'] == 'NATURAL_RECURSIVE'].set_index('model')
        for arm, ref in [('BASE', 'POWER_DIAG'), ('REF_POWER1', 'POWER1')]:
            r = next(x for x in rows if x['arm'] == arm and x['bias'] == bias and x['channel'] == ch)
            qa.append({'case': a.case, 'bias': bias, 'channel': ch, 'arm': arm, 'd_rmse': abs(r['heading_rmse_deg'] - old_sc.loc[ref, 'heading_rmse_deg'])})
        print('V_DONE', stem, flush=True)
    pd.DataFrame(rows).to_csv(OUT / f'{a.case}_V_SCORES.csv', index=False); pd.DataFrame(qa).to_csv(OUT / f'{a.case}_V_QA.csv', index=False)
    pd.DataFrame(meas).to_csv(OUT / f'{a.case}_V_MEAS.csv', index=False)
    (OUT / f'{a.case}_V_CALIB.json').write_text(json.dumps({'two': two, 'five': five}, indent=2))
    print('CASE_DONE', a.case, flush=True)


if __name__ == '__main__':
    main()
