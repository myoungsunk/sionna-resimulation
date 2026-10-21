#!/usr/bin/env python3
"""Exploratory usage map for signed delta-s (fixed plan in 00_PLAN.md). No filter replay."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve(); ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_RESULTS']).resolve(); OUT.mkdir(parents=True, exist_ok=True)
for path in ['research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016', 'research/R5_N4B_20261015', 'research/PHYSICS_RS_STAGED_20261015/code']:
    sys.path.insert(0, str(ROOT / path))
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent / 'PJ_D1_TEMPORAL_20261021'))
import p0_initial
p0_initial.OUT = OUT
from source_model import SourceFFD
import source_model
source_model.OUT = OUT
import d1_core as D1

MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
OFFS = [-8, -4, -2, -1, 1, 2, 4, 8]
DS = [f'ds_{o:+d}' for o in OFFS]; DSA = [f'absds_{o:+d}' for o in OFFS]
EXIST = ['log_fp_power', 'abs_s_fp', 'early4', 'early8', 'early16', 'delay_rms_ns', 'peak_diff_ns', 'eta_fp_win80', 's_diff4', 's_diff8', 's_diff16',
         'tap_pol_var80', 'jones_diversity', 'freq_s_var', 'detector_s_span', 'detector_delay_span_ns']
LFW = 11


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def taps(H):
    H = np.asarray(H, np.complex128); n, nf, _ = H.shape; nt = 4 * nf; ii = np.arange(n)
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[None, :, None], n=nt, axis=1) * nf
    amp = np.abs(cir); power = amp ** 2
    branch = amp.max(axis=1).argmax(axis=1); strong = amp[ii, :, branch]; peaks = strong.max(axis=1)
    tap = (strong >= .3 * peaks[:, None]).argmax(axis=1); out = {}
    for o in [0] + OFFS:
        idx = tap + o; ok = (idx >= 0) & (idx < nt); idc = np.clip(idx, 0, nt - 1)
        P = power[ii, idc, :]; den = P.sum(axis=1)
        out[f's_{o:+d}'] = np.where(ok & (den > 0), (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1), np.nan)
    return out


def build(model):
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    par = pd.read_csv(one('OOF_PARAMETERS.csv.gz')); par = par[par.model == 'POWER1']
    rows, los_rows = [], []
    for c in MANIFEST['cases']:
        ids = pd.DataFrame(json.loads((ROOT / c['samples_path']).read_text())).pose_id.to_numpy(int)
        per = {}
        for ch, key in [('full', 'full_path'), ('los', 'los_path')]:
            H = np.load(ROOT / c[key], mmap_mode='r', allow_pickle=False)
            b = [taps(np.asarray(H[k:k + 128, :, :, 0])) for k in range(0, len(H), 128)]
            d = pd.DataFrame({k: np.concatenate([x[k] for x in b]) for k in b[0]}); d['pose_id'] = ids
            for o in OFFS:
                d[f'ds_{o:+d}'] = d[f's_{o:+d}'] - d['s_+0']; d[f'absds_{o:+d}'] = d[f'ds_{o:+d}'].abs()
            per[ch] = d
        ff = feat[(feat.case == c['id']) & (feat.channel == 'full')].set_index('pose_id').loc[ids]
        fl = feat[(feat.case == c['id']) & (feat.channel == 'los')].set_index('pose_id').loc[ids]
        d = per['full'].copy()
        for col in EXIST + ['e_s', 'e_r', 's_fp', 'range_m', 'x_eval', 'y_eval', 'yaw_eval_rad']:
            d[col] = ff[col].to_numpy()
        d['d_mp_s'] = d['s_fp'] - fl['s_fp'].to_numpy(); d['d_mp_r'] = d['range_m'] - fl['range_m'].to_numpy()
        p = par[(par.case == c['id']) & (par.channel == 'full')].set_index('pose_id').loc[ids]
        d['mu_s'] = p.mu_s.to_numpy(); d['mu_r'] = p.mu_r.to_numpy(); d['Vs'] = p.Vs.to_numpy(); d['Vr'] = p.Vr.to_numpy()
        st = np.column_stack([d.x_eval, d.y_eval, d.yaw_eval_rad, np.zeros(len(d))])
        hs, gs = [], []
        for k in range(0, len(st), 64):
            h, J = model.batch(st[k:k + 64], c, gradient=True); hs.append(h[:, 1]); gs.append(J[:, 1, 2])
        d['h_s'] = np.concatenate(hs); d['g_psi'] = np.concatenate(gs)
        d['case'] = c['id']; d['route'] = c['route']; rows.append(d)
        l = per['los'][['pose_id', 'ds_+1', 'ds_+4']].copy(); l['case'] = c['id']; los_rows.append(l)
    return pd.concat(rows, ignore_index=True), pd.concat(los_rows, ignore_index=True)


def r2nc(y, p):
    m = np.isfinite(y) & np.isfinite(p); return float(1 - np.mean((y[m] - p[m]) ** 2) / np.mean(y[m] ** 2)) if m.sum() > 10 else np.nan


def lf(case, s):
    c = next(x for x in MANIFEST['cases'] if x['id'] == case); r = next(x for x in MANIFEST['routes'] if x['id'] == c['route'])
    tl = pd.read_csv(ROOT / r['path'])
    return pd.Series(s.reindex(tl.pose_id.to_numpy()).to_numpy(float)).rolling(LFW, center=True, min_periods=1).mean().to_numpy()


def fit_predict(tr, te, cols, y, kind='ridge'):
    trm = tr[cols + [y]].replace([np.inf, -np.inf], np.nan).dropna(); X = te[cols]; ok = X.notna().all(axis=1).to_numpy(); out = np.full(len(te), np.nan)
    if kind == 'hgb':
        m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(trm[cols], trm[y])
        out[ok] = m.predict(X[ok]); return out
    sc = StandardScaler().fit(trm[cols]); m = Ridge(alpha=1.0).fit(sc.transform(trm[cols]), trm[y]); out[ok] = m.predict(sc.transform(X[ok])); return out


def auc_logit(tr, te, cols, ylab):
    trm = tr[cols + [ylab]].dropna(); X = te[cols]; ok = X.notna().all(axis=1).to_numpy()
    sc = StandardScaler().fit(trm[cols]); m = LogisticRegression(C=1.0, max_iter=2000).fit(sc.transform(trm[cols]), trm[ylab].astype(int))
    p = np.full(len(te), np.nan); p[ok] = m.predict_proba(sc.transform(X[ok]))[:, 1]; return p


def safe_auc(y, s):
    m = np.isfinite(s); y = np.asarray(y)[m]; s = np.asarray(s)[m]
    return float(roc_auc_score(y, s)) if len(np.unique(y)) == 2 else np.nan


def main():
    model = SourceFFD(); Dt, L = build(model)
    Dt.to_csv(OUT / 'UM_POSE_TABLE.csv.gz', index=False, compression='gzip')
    Dt['logabs_e_s'] = np.log(np.abs(Dt.e_s) + 1e-4); Dt['logabs_e_r'] = np.log(np.abs(Dt.e_r) + 1e-4)
    Dt['contam'] = (Dt.d_mp_s.abs() > 0.05).astype(int); Dt['outlier_s'] = (Dt.e_s.abs() > 2 * np.sqrt(Dt.Vs)).astype(int)
    Dt['rs_same_sign'] = (Dt.e_r * Dt.e_s > 0).astype(int)
    A, B, C = [], [], []
    for held in ['R2', 'R4', 'R5']:
        tr = Dt[Dt.route != held]; te = Dt[Dt.route == held].copy()
        for y in ['e_s', 'd_mp_s', 'e_r', 'd_mp_r']:
            preds = {nm: fit_predict(tr, te, cols, y) for nm, cols in [('EXIST', EXIST), ('DS', DS), ('EXIST_DS', EXIST + DS)]}
            preds['HGB_EXIST_DS'] = fit_predict(tr, te, EXIST + DS, y, 'hgb')
            if y in ('e_s', 'e_r'): preds['POWER1_MU'] = te['mu_s' if y == 'e_s' else 'mu_r'].to_numpy()
            for nm, p in preds.items():
                te['_p'] = p
                for case, g in te.groupby('case'):
                    row = {'case': case, 'target': y, 'model': nm, 'R2_nc_pose': r2nc(g[y].to_numpy(), g._p.to_numpy())}
                    if y in ('e_s', 'e_r'):
                        row['R2_nc_LF'] = r2nc(lf(case, g.set_index('pose_id')[y]), lf(case, g.set_index('pose_id')._p))
                    A.append(row)
        for y, base in [('logabs_e_s', 'Vs'), ('logabs_e_r', 'Vr')]:
            preds = {nm: fit_predict(tr, te, cols, y) for nm, cols in [('EXIST', EXIST), ('DSA', DSA), ('EXIST_DSA', EXIST + DSA)]}
            preds['POWER1_V'] = te[base].to_numpy()
            for nm, p in preds.items():
                te['_p'] = p
                for case, g in te.groupby('case'):
                    m = np.isfinite(g._p)
                    B.append({'case': case, 'target': y.replace('logabs_', '|') + '|', 'model': nm, 'spearman': float(spearmanr(g._p[m], np.exp(g[y][m])).statistic)})
        for lab, sets in [('contam', [('EXIST', EXIST), ('DSA', DSA), ('EXIST_DSA', EXIST + DSA)]), ('outlier_s', [('EXIST', EXIST), ('DSA', DSA), ('EXIST_DSA', EXIST + DSA)]),
                          ('rs_same_sign', [('EXIST', EXIST), ('DS', DS), ('EXIST_DS', EXIST + DS)])]:
            for nm, cols in sets:
                te['_p'] = auc_logit(tr, te, cols, lab)
                for case, g in te.groupby('case'):
                    C.append({'case': case, 'label': lab, 'model': nm, 'auc': safe_auc(g[lab], g._p.to_numpy()), 'prevalence': float(g[lab].mean())})
            if lab != 'rs_same_sign':
                for case, g in te.groupby('case'):
                    C.append({'case': case, 'label': lab, 'model': 'RAW_|ds+1|_no_training', 'auc': safe_auc(g[lab], g['absds_+1'].to_numpy()), 'prevalence': float(g[lab].mean())})
    A, B, C = pd.DataFrame(A), pd.DataFrame(B), pd.DataFrame(C)
    Dd, E, F = [], [], []
    for case, g in Dt.groupby('case'):
        X = np.column_stack([np.ones(len(g)), g.h_s, g.g_psi, g.g_psi ** 2]); y = g['ds_+1'].to_numpy(); m = np.isfinite(y)
        beta, *_ = np.linalg.lstsq(X[m], y[m], rcond=None); res = y[m] - X[m] @ beta
        Dd.append({'case': case, 'R2_ds1_on_hs_g': float(1 - res.var() / y[m].var()), 'corr_ds1_g': float(np.corrcoef(y[m], g.g_psi[m])[0, 1]),
                   'corr_ds1_hs': float(np.corrcoef(y[m], g.h_s[m])[0, 1]), 'corr_e_s_g': float(np.corrcoef(g.e_s, g.g_psi)[0, 1])})
        c = next(x for x in MANIFEST['cases'] if x['id'] == case); r = next(x for x in MANIFEST['routes'] if x['id'] == c['route'])
        tl = pd.read_csv(ROOT / r['path']); dt = float(np.median(np.diff(tl.t_s)))
        gi = g.set_index('pose_id')
        for col in ['ds_+1', 'ds_+4', 'e_s', 'e_r']:
            v = gi[col].reindex(tl.pose_id.to_numpy()).to_numpy(float); v = v - np.nanmean(v) if col.startswith('ds') else v
            st = D1.acf_stats(np.nan_to_num(v), dt, max_s=30.0); E.append({'case': case, 'series': col, 'tau_int_s': st['tau_int_s'], 'lag1': st['lag1_noncentred'], 'acf_2s': st['acf_2s']})
        lc = L[L.case == case]
        F.append({'case': case, 'median_abs_ds1_full': float(g['ds_+1'].abs().median()), 'median_abs_ds1_los': float(lc['ds_+1'].abs().median()),
                  'frac_abs_ds1_gt_0.01_full': float((g['ds_+1'].abs() > 0.01).mean()), 'frac_abs_ds1_gt_0.01_los': float((lc['ds_+1'].abs() > 0.01).mean())})
    Dd, E, F = pd.DataFrame(Dd), pd.DataFrame(E), pd.DataFrame(F)
    for nm, df in [('A_SIGNED_TARGETS', A), ('B_MAGNITUDE', B), ('C_CLASSIFY', C), ('D_PSI_INDEPENDENCE', Dd), ('E_TEMPORAL', E), ('F_LOS_SANITY', F)]:
        df.to_csv(OUT / f'UM_{nm}.csv', index=False)
    summ = {'A_R2_pose_median': A.pivot_table(index='target', columns='model', values='R2_nc_pose', aggfunc='median').round(3).to_dict('index'),
            'A_R2_LF_median': A.dropna(subset=['R2_nc_LF']).pivot_table(index='target', columns='model', values='R2_nc_LF', aggfunc='median').round(3).to_dict('index'),
            'B_spearman_median': B.pivot_table(index='target', columns='model', values='spearman', aggfunc='median').round(3).to_dict('index'),
            'C_auc_median': C.pivot_table(index='label', columns='model', values='auc', aggfunc='median').round(3).to_dict('index'),
            'D_median': Dd.drop(columns='case').median().round(3).to_dict(), 'E_tau_median': E.pivot_table(index='series', values='tau_int_s', aggfunc='median').round(2).tau_int_s.to_dict(),
            'F': F.round(4).to_dict('records')}
    (OUT / 'UM_SUMMARY.json').write_text(json.dumps(summ, indent=2, default=str))
    md = ['# Delta-s usage map (machine summary)', '', '```json', json.dumps(summ, indent=2, default=str), '```', '', '## A', A.round(3).to_markdown(index=False), '', '## B', B.round(3).to_markdown(index=False),
          '', '## C', C.round(3).to_markdown(index=False), '', '## D', Dd.round(3).to_markdown(index=False), '', '## E', E.round(3).to_markdown(index=False), '', '## F', F.round(4).to_markdown(index=False)]
    (OUT / 'UM_RESULTS.md').write_text('\n'.join(md) + '\n')
    print('UM_DONE', flush=True)


if __name__ == '__main__':
    main()
