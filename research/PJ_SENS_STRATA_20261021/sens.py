#!/usr/bin/env python3
"""Sensitivity-stratified analysis of polarization mean models (plan in 00_PLAN.md)."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve(); ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_RESULTS']).resolve(); OUT.mkdir(parents=True, exist_ok=True)
for path in ['research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016', 'research/R5_N4B_20261015', 'research/PHYSICS_RS_STAGED_20261015/code']:
    sys.path.insert(0, str(ROOT / path))
import p0_initial
p0_initial.OUT = OUT
from source_model import SourceFFD
import source_model
source_model.OUT = OUT

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
OFFS = [-8, -4, -2, -1, 1, 2, 4, 8]; DS = [f'ds_{o:+d}' for o in OFFS]
EXIST = ['log_fp_power', 'abs_s_fp', 'early4', 'early8', 'early16', 'delay_rms_ns', 'peak_diff_ns', 'eta_fp_win80', 's_diff4', 's_diff8', 's_diff16',
         'tap_pol_var80', 'jones_diversity', 'freq_s_var', 'detector_s_span', 'detector_delay_span_ns']
DEG = 180 / np.pi


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def ds_table(H):
    H = np.asarray(H, np.complex128); n, nf, _ = H.shape; nt = 4 * nf; ii = np.arange(n)
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[None, :, None], n=nt, axis=1) * nf; amp = np.abs(cir); power = amp ** 2
    branch = amp.max(axis=1).argmax(axis=1); strong = amp[ii, :, branch]; peaks = strong.max(axis=1)
    tap = (strong >= .3 * peaks[:, None]).argmax(axis=1); s = {}
    for o in [0] + OFFS:
        idx = tap + o; ok = (idx >= 0) & (idx < nt); idc = np.clip(idx, 0, nt - 1); P = power[ii, idc, :]; den = P.sum(axis=1)
        s[o] = np.where(ok & (den > 0), (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1), np.nan)
    return {f'ds_{o:+d}': s[o] - s[0] for o in OFFS}


def build(model):
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz')); par = pd.read_csv(one('OOF_PARAMETERS.csv.gz')); par = par[par.model == 'POWER1']
    rows = []
    for c in MANIFEST['cases']:
        ids = pd.DataFrame(json.loads((ROOT / c['samples_path']).read_text())).pose_id.to_numpy(int)
        H = np.load(ROOT / c['full_path'], mmap_mode='r', allow_pickle=False)
        b = [ds_table(np.asarray(H[k:k + 128, :, :, 0])) for k in range(0, len(H), 128)]
        d = pd.DataFrame({k: np.concatenate([x[k] for x in b]) for k in b[0]}); d['pose_id'] = ids
        f = feat[(feat.case == c['id']) & (feat.channel == 'full')].set_index('pose_id').loc[ids]
        for col in EXIST + ['e_s', 'e_r', 'x_eval', 'y_eval', 'yaw_eval_rad']: d[col] = f[col].to_numpy()
        p = par[(par.case == c['id']) & (par.channel == 'full')].set_index('pose_id').loc[ids]
        for col in ['mu_s', 'mu_r', 'Vs', 'Vr']: d[col] = p[col].to_numpy()
        st = np.column_stack([d.x_eval, d.y_eval, d.yaw_eval_rad, np.zeros(len(d))]); Js = []
        for k in range(0, len(st), 64):
            _, J = model.batch(st[k:k + 64], c, gradient=True); Js.append(J)
        J = np.concatenate(Js)
        d['rx'], d['ry'] = J[:, 0, 0], J[:, 0, 1]; d['sx'], d['sy'], d['g'] = J[:, 1, 0], J[:, 1, 1], J[:, 1, 2]
        d['case'] = c['id']; d['route'] = c['route']; rows.append(d)
    D = pd.concat(rows, ignore_index=True)
    parts = []
    for held in ['R2', 'R4', 'R5']:
        tr = D[D.route != held]; te = D[D.route == held].copy()
        t1 = tr.dropna(subset=DS + ['log_fp_power']); sc = StandardScaler().fit(t1[DS + ['log_fp_power']])
        m = Ridge(alpha=1.0).fit(sc.transform(t1[DS + ['log_fp_power']]), t1.e_s); te['mu_LIN'] = m.predict(sc.transform(te[DS + ['log_fp_power']].fillna(0)))
        te['mu_HGB'] = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(tr[EXIST + DS], tr.e_s).predict(te[EXIST + DS])
        parts.append(te)
    D = pd.concat(parts, ignore_index=True); D['mu_POWER1'] = D.mu_s
    D['gxy'] = np.hypot(D.sx, D.sy)
    return D


def wls_windows(g, mu_col, only_delta=None):
    """Window joint WLS: unknowns dx, dy, dpsi; rows: range and polarization."""
    w = np.floor(g.x_eval / 1.0).astype(int); out = []
    prior = np.diag([1 / 0.5 ** 2, 1 / 0.5 ** 2, 1 / np.radians(10) ** 2])
    for k, gg in g.groupby(w):
        Jr = np.column_stack([gg.rx, gg.ry, np.zeros(len(gg))]); Js = np.column_stack([gg.sx, gg.sy, gg.g])
        if only_delta is None:
            rr = (gg.e_r - gg.mu_r).to_numpy(); rs = (gg.e_s - gg[mu_col]).to_numpy()
        else:  # induced shift: only the change of polarization mean, range residual zero
            rr = np.zeros(len(gg)); rs = -(gg[mu_col] - gg[only_delta]).to_numpy()
        A = prior + Jr.T @ (Jr / gg.Vr.to_numpy()[:, None]) + Js.T @ (Js / gg.Vs.to_numpy()[:, None])
        bvec = Jr.T @ (rr / gg.Vr.to_numpy()) + Js.T @ (rs / gg.Vs.to_numpy())
        dx = np.linalg.solve(A, bvec)
        out.append({'win': int(k), 'n': len(gg), 'dpsi_deg': dx[2] * DEG, 'dxy_m': float(np.hypot(dx[0], dx[1])), 'median_abs_g': float(gg.g.abs().median())})
    return pd.DataFrame(out)


def main():
    model = SourceFFD(); D = build(model); D.to_csv(OUT / 'SENS_POSE_TABLE.csv.gz', index=False, compression='gzip')
    M = ['POWER1', 'LIN', 'HGB']
    # A: |g| strata (pooled quartiles)
    q = np.quantile(D.g.abs(), [.25, .5, .75]); D['gq'] = np.searchsorted(q, D.g.abs(), side='right')
    A = []
    for k, gg in D.groupby('gq'):
        row = {'g_quartile': int(k), 'g_range': f'{gg.g.abs().min():.2f}-{gg.g.abs().max():.2f}', 'n': len(gg), 'median_gxy_per_m': gg.gxy.median()}
        for m in M:
            r = gg.e_s - gg['mu_' + m]
            row[f'rs_rms_{m}'] = float(np.sqrt(np.mean(r ** 2))); row[f'head_equiv_med_deg_{m}'] = float(np.median(np.abs(r / gg.g)) * DEG)
            row[f'pos_equiv_med_m_{m}'] = float(np.median(np.abs(r) / gg.gxy))
        A.append(row)
    A = pd.DataFrame(A)
    # B: information geometry per case
    B = []
    for case, gg in D.groupby('case'):
        Ipsi = np.sum(gg.g ** 2 / gg.Vs); Ixy_s = np.sum(gg.gxy ** 2 / gg.Vs); Ixy_r = np.sum((gg.rx ** 2 + gg.ry ** 2) / gg.Vr)
        B.append({'case': case, 'median_abs_g_per_rad': gg.g.abs().median(), 'median_gxy_per_m': gg.gxy.median(), 'heading_share_of_s_info': Ipsi / (Ipsi + Ixy_s),
                  's_xy_info_over_range_xy_info': Ixy_s / Ixy_r})
    B = pd.DataFrame(B)
    # C & D: window WLS
    C, Dd = [], []
    for case, gg in D.groupby('case'):
        for m in M:
            w = wls_windows(gg, 'mu_' + m)
            C.append({'case': case, 'model': m, 'wls_dpsi_rms_deg': float(np.sqrt(np.mean(w.dpsi_deg ** 2))), 'wls_dxy_rms_m': float(np.sqrt(np.mean(w.dxy_m ** 2))), 'n_windows': len(w)})
        for m in ['LIN', 'HGB']:
            w = wls_windows(gg, 'mu_' + m, only_delta='mu_POWER1'); dmu = gg['mu_' + m] - gg.mu_POWER1
            Dd.append({'case': case, 'model': m, 'induced_dpsi_rms_deg': float(np.sqrt(np.mean(w.dpsi_deg ** 2))), 'induced_dxy_rms_m': float(np.sqrt(np.mean(w.dxy_m ** 2))),
                       'dmu_rms': float(np.sqrt(np.mean(dmu ** 2))), 'corr_dmu_g': float(np.corrcoef(dmu, gg.g)[0, 1]), 'corr_dmu_gxy': float(np.corrcoef(dmu, gg.gxy)[0, 1])})
    C, Dd = pd.DataFrame(C), pd.DataFrame(Dd)
    for nm, df in [('A_G_STRATA', A), ('B_INFO_GEOMETRY', B), ('C_WINDOW_WLS', C), ('D_INDUCED_SHIFT', Dd)]:
        df.to_csv(OUT / f'SENS_{nm}.csv', index=False)
    md = ['# Sensitivity analysis (machine summary)', '## A', A.round(3).to_markdown(index=False), '## B', B.round(3).to_markdown(index=False),
          '## C', C.pivot_table(index='case', columns='model', values=['wls_dpsi_rms_deg', 'wls_dxy_rms_m']).round(3).to_markdown(), '## D', Dd.round(3).to_markdown(index=False)]
    (OUT / 'SENS_RESULTS.md').write_text('\n\n'.join(md) + '\n'); print('SENS_DONE', flush=True)


if __name__ == '__main__':
    main()
