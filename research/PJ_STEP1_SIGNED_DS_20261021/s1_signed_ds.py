#!/usr/bin/env python3
"""Step 1: signed s around first path vs polarization bias. No filter, no new RF."""
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(os.environ['PJ_SOURCE_ROOT']).resolve()
ART = Path(os.environ['PJ_ART']).resolve()
OUT = Path(os.environ['PJ_RESULTS']).resolve(); OUT.mkdir(parents=True, exist_ok=True)
MANIFEST = json.loads((ROOT / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
OFFS = [-8, -4, -2, -1, 0, 1, 2, 4, 8]
SIGNED = [f'ds_{o:+d}' for o in OFFS if o != 0]
ABSF = [f'abs_ds_{o:+d}' for o in OFFS if o != 0] + ['s_diff4', 's_diff8', 's_diff16', 'detector_s_span']
LFW = 11  # 2 s at 0.2 s


def one(g):
    m = sorted(ART.rglob(g)); assert len(m) == 1, (g, m); return m[0]


def taps(H):
    """Same steps as features.extract; returns fp tap, s and relative amplitude at offsets."""
    H = np.asarray(H, np.complex128); n, nf, _ = H.shape; nt = 4 * nf; ii = np.arange(n)
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    cir = np.fft.ifft(H * window[None, :, None], n=nt, axis=1) * nf
    amp = np.abs(cir); power = amp ** 2
    branch = amp.max(axis=1).argmax(axis=1)
    strong = amp[ii, :, branch]; peaks = strong.max(axis=1)
    tap = (strong >= .3 * peaks[:, None]).argmax(axis=1)
    out = {'tap': tap}
    for o in OFFS:
        idx = tap + o; ok = (idx >= 0) & (idx < nt); idc = np.clip(idx, 0, nt - 1)
        P = power[ii, idc, :]; den = P.sum(axis=1)
        s = np.where(ok & (den > 0), (P[:, 0] - P[:, 1]) / np.where(den > 0, den, 1), np.nan)
        out[f's_{o:+d}'] = s; out[f'rel_{o:+d}'] = np.where(ok, amp[ii, idc, branch] / peaks, np.nan)
    return out


def build():
    feat = pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz'))
    par = pd.read_csv(one('OOF_PARAMETERS.csv.gz')); par = par[par.model == 'POWER1']
    rows = []; qa = []
    for c in MANIFEST['cases']:
        ids = pd.DataFrame(json.loads((ROOT / c['samples_path']).read_text())).pose_id.to_numpy(int)
        per = {}
        for ch, key in [('full', 'full_path'), ('los', 'los_path')]:
            H = np.load(ROOT / c[key], mmap_mode='r', allow_pickle=False)
            blocks = [taps(np.asarray(H[k:k + 128, :, :, 0])) for k in range(0, len(H), 128)]
            d = pd.DataFrame({k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}); d['pose_id'] = ids
            f = feat[(feat.case == c['id']) & (feat.channel == ch)].set_index('pose_id').loc[ids]
            qa.append({'case': c['id'], 'channel': ch, 'max_abs_s_fp_diff': float(np.nanmax(np.abs(d['s_+0'].to_numpy() - f.s_fp.to_numpy())))})
            for col in ['e_s', 's_fp', 's_diff4', 's_diff8', 's_diff16', 'detector_s_span']:
                d[col] = f[col].to_numpy()
            per[ch] = d
        full = per['full'].copy(); full['s_los_fp'] = per['los']['s_+0'].to_numpy(); full['d_mp'] = full['s_+0'] - full['s_los_fp']
        p = par[(par.case == c['id']) & (par.channel == 'full')].set_index('pose_id').loc[ids]; full['mu_s_power1'] = p.mu_s.to_numpy()
        full['case'] = c['id']; full['route'] = c['route']; rows.append(full)
    D = pd.concat(rows, ignore_index=True)
    for o in OFFS:
        if o:
            D[f'ds_{o:+d}'] = D[f's_{o:+d}'] - D['s_+0']; D[f'abs_ds_{o:+d}'] = D[f'ds_{o:+d}'].abs()
    return D, pd.DataFrame(qa)


def r2nc(y, yhat):
    m = np.isfinite(y) & np.isfinite(yhat); return float(1 - np.mean((y[m] - yhat[m]) ** 2) / np.mean(y[m] ** 2))


def lf_series(case, values_by_pose):
    c = next(x for x in MANIFEST['cases'] if x['id'] == case); r = next(x for x in MANIFEST['routes'] if x['id'] == c['route'])
    tl = pd.read_csv(ROOT / r['path']); v = values_by_pose.reindex(tl.pose_id.to_numpy()).to_numpy(float)
    return pd.Series(v).rolling(LFW, center=True, min_periods=1).mean().to_numpy()


def main():
    D, QA = build()
    D.to_csv(OUT / 'S1_POSE_TABLE.csv.gz', index=False, compression='gzip'); QA.to_csv(OUT / 'S1_QA.csv', index=False)
    res = []
    for c in MANIFEST['cases']:
        g = D[D.case == c['id']]; r = {'case': c['id'], 'n': len(g)}
        for lab in ['d_mp', 'e_s']:
            for o in [4, 1, 2, 8]:
                sel = (g[lab].abs() > 0.02) & (g[f'ds_{o:+d}'].abs() > 0.01)
                r[f'M1_sign_agree_{lab}_+{o}'] = float((np.sign(g.loc[sel, f'ds_{o:+d}']) == np.sign(g.loc[sel, lab])).mean()) if sel.any() else np.nan
                r[f'M1_n_{lab}_+{o}'] = int(sel.sum())
            sel = (g[lab].abs() > 0.02) & (g['ds_-4'].abs() > 0.01)
            r[f'M1b_sign_agree_{lab}_minus4_negated'] = float((np.sign(-g.loc[sel, 'ds_-4']) == np.sign(g.loc[sel, lab])).mean()) if sel.any() else np.nan
        for o in [4, 2, 1]:
            a = (g[f's_{-o:+d}'] - g.s_los_fp).abs(); b = (g['s_+0'] - g.s_los_fp).abs(); m = a.notna()
            r[f'M2_lead{o}_closer_frac'] = float((a[m] < b[m]).mean()); r[f'M2_lead{o}_rms'] = float(np.sqrt(np.mean(a[m] ** 2))); r['M2_fp_rms'] = float(np.sqrt(np.mean(b[m] ** 2)))
            r[f'M2_lead{o}_relamp_median'] = float(g[f'rel_{-o:+d}'].median())
        m = (g['ds_+4'].abs() > 0.01) & g.d_mp.notna()
        r['M4_lambda_d_mp'] = float((g.loc[m, 'd_mp'] * g.loc[m, 'ds_+4']).sum() / (g.loc[m, 'ds_+4'] ** 2).sum()) if m.any() else np.nan
        r['corr_d_mp_e_s'] = float(np.corrcoef(g.d_mp, g.e_s)[0, 1]); r['rms_d_mp'] = float(np.sqrt(np.mean(g.d_mp ** 2))); r['rms_e_s'] = float(np.sqrt(np.mean(g.e_s ** 2)))
        res.append(r)
    M = pd.DataFrame(res).set_index('case')
    # M3 held-route regression
    fits = []
    for held in ['R2', 'R4', 'R5']:
        tr = D[D.route != held]; te = D[D.route == held]
        for name, cols in [('SIGNED', SIGNED), ('ABS', ABSF), ('SIGNED_ABS', SIGNED + ABSF)]:
            for lab in ['d_mp', 'e_s']:
                trm = tr[cols + [lab]].dropna(); sc = StandardScaler().fit(trm[cols]); reg = Ridge(alpha=1.0).fit(sc.transform(trm[cols]), trm[lab])
                X = te[cols].copy(); ok = X.notna().all(axis=1); pred = np.full(len(te), np.nan); pred[ok.to_numpy()] = reg.predict(sc.transform(X[ok]))
                te2 = te.assign(pred=pred)
                for case, gg in te2.groupby('case'):
                    row = {'case': case, 'model': name, 'label': lab, 'R2_nc_pose': r2nc(gg[lab].to_numpy(), gg.pred.to_numpy()),
                           'coefs_std': json.dumps(dict(zip(cols, np.round(reg.coef_, 5).tolist())))}
                    if lab == 'e_s':
                        e_lf = lf_series(case, gg.set_index('pose_id').e_s); p_lf = lf_series(case, gg.set_index('pose_id').pred)
                        row['R2_nc_LF'] = r2nc(e_lf, p_lf)
                    fits.append(row)
    for case, gg in D.groupby('case'):
        e_lf = lf_series(case, gg.set_index('pose_id').e_s); p_lf = lf_series(case, gg.set_index('pose_id').mu_s_power1)
        fits.append({'case': case, 'model': 'POWER1_MU', 'label': 'e_s', 'R2_nc_pose': r2nc(gg.e_s.to_numpy(), gg.mu_s_power1.to_numpy()), 'R2_nc_LF': r2nc(e_lf, p_lf)})
        fits.append({'case': case, 'model': 'POWER1_MU', 'label': 'd_mp', 'R2_nc_pose': r2nc(gg.d_mp.to_numpy(), gg.mu_s_power1.to_numpy())})
    F = pd.DataFrame(fits); F.to_csv(OUT / 'S1_M3_FITS.csv', index=False); M.to_csv(OUT / 'S1_CASE_METRICS.csv')
    lf = F[(F.label == 'e_s')].pivot_table(index='case', columns='model', values='R2_nc_LF')
    pz = F.pivot_table(index=['case', 'label'], columns='model', values='R2_nc_pose')
    J = {'QA_max_s_fp_diff': float(QA.max_abs_s_fp_diff.max()),
         'M1_sign_agree_d_mp_+4_by_case': M['M1_sign_agree_d_mp_+4'].round(3).to_dict(),
         'M1_cases_ge_0.65_d_mp_+4': int((M['M1_sign_agree_d_mp_+4'] >= 0.65).sum()),
         'M1_sign_agree_e_s_+4_by_case': M['M1_sign_agree_e_s_+4'].round(3).to_dict(),
         'M2_lead4_closer_frac_by_case': M['M2_lead4_closer_frac'].round(3).to_dict(),
         'M2_rms_fp_vs_lead4': {k: [round(a, 4), round(b, 4)] for k, a, b in zip(M.index, M.M2_fp_rms, M.M2_lead4_rms)},
         'M3_R2_LF_e_s': lf.round(3).to_dict('index'),
         'M3_cases_signed_beats_power1_by_0.10_LF': int(((lf.SIGNED - lf.POWER1_MU) >= 0.10).sum()),
         'M3_R2_pose': pz.round(3).reset_index().to_dict('records'),
         'M4_lambda_by_case': M.M4_lambda_d_mp.round(3).to_dict()}
    (OUT / 'S1_JUDGEMENT.json').write_text(json.dumps(J, indent=2, default=str))
    md = ['# Step 1 machine summary', '', '```json', json.dumps(J, indent=2, default=str), '```', '', '## Case metrics', M.round(4).T.to_markdown()]
    (OUT / 'S1_RESULTS.md').write_text('\n'.join(md) + '\n')
    print('::notice title=S1::' + json.dumps({k: J[k] for k in ['QA_max_s_fp_diff', 'M1_cases_ge_0.65_d_mp_+4', 'M3_cases_signed_beats_power1_by_0.10_LF']}))
    print('S1_DONE', flush=True)


if __name__ == '__main__':
    main()
