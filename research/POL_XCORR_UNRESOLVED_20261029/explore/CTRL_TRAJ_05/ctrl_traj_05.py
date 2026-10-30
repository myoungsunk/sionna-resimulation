#!/usr/bin/env python3
"""CTRL-TRAJ-05 — deployable gating with the EKF heading covariance P_psipsi (EXPLORATORY, label-free).

Post-processes CTRL-TRAJ-04 window statistics (run 41003294951). For every error segment/window the filter's own
heading std sigma_w = sqrt(mean_w cov[k-1, arm, psi, psi]) is attached (posterior of k-1 = the prior used at k, same
indexing as the error). No truth is used for gating or thresholds; truth rms is reported only as the oracle reference.

Thresholds are cross-fitted by trace file (2 folds, alternating sorted trace order): calibrated on NULL windows of one
fold, evaluated (FPR on NULL, TPR on LOS+C / ALL) on the other fold. Per (mount, yaw_body) config, since the heading
prior itself gives the body yaw and mount is known.

Schemes
  G_cov(c)   : keep windows with sigma_w <= fold-calibrated quantile c of sigma; single threshold = NULL p95 among kept
  S_cov(B)   : keep all windows; threshold per sigma bin (B quantile bins from the calibration fold) = NULL p95 in bin
  Z          : statistic / sigma_w and / sigma_w^2, single threshold
  O(c)       : oracle reference, same as G_cov but ranked by true window rms
"""
from __future__ import annotations
import argparse, glob, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

STATS = ['d0_fp', 'd0_W', 'Dvec', 'Dperp', 'Dvec_fit']


def load_sigma(art_dir, seg_len=391, stride=25):
    """Same segmentation as CTRL_TRAJ_03.load_errors; returns errors, prior sigma (deg) and meta."""
    E, SG, meta = [], [], []
    files = sorted(glob.glob(str(Path(art_dir) / '**' / '*_full_*_TRACE.npz'), recursive=True))
    for f in files:
        z = np.load(f, allow_pickle=False); st = z['state']; tr = z['truth_scoring_only']; t = z['t_s']; arms = z['arms']; cv = z['cov']
        yaw_t = tr[:, 2]; yaw_e = st[:, :, 2]; pvar = cv[:, :, 2, 2]
        deg = np.max(np.abs(yaw_t)) > 2 * np.pi + 0.1
        if not deg:
            yaw_t = np.degrees(yaw_t); yaw_e = np.degrees(yaw_e); pvar = pvar * (180 / np.pi) ** 2
        err = (yaw_e[:-1] - yaw_t[1:, None] + 180) % 360 - 180; sg = np.sqrt(np.maximum(pvar[:-1], 0))
        ok = t[1:] >= 30.0; name = Path(f).name.replace('_TRACE.npz', '')
        for j, arm in enumerate(arms):
            e = err[ok, j]; s = sg[ok, j]
            for k in range(0, len(e) - seg_len + 1, stride):
                E.append(e[k:k + seg_len]); SG.append(s[k:k + seg_len]); meta.append({'trace': name, 'arm': str(arm)})
    return np.array(E), np.array(SG), pd.DataFrame(meta), files, deg


def tpr_fpr(neg, pos, thr):
    return float(np.mean(pos > thr)), float(np.mean(neg > thr))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--windows', required=True); ap.add_argument('--trace-dir', required=True)
    ap.add_argument('--out', required=True); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    E, SG, M, files, deg = load_sigma(a.trace_dir)
    D = pd.read_csv(a.windows, keep_default_na=False)
    # alignment check against CTRL-TRAJ-04 segment rms
    rms = np.sqrt(np.mean(E ** 2, axis=1)); chk = D.groupby('seg').rms.first()
    align = float(np.max(np.abs(chk.to_numpy() - rms[chk.index.to_numpy()])))
    assert align < 1e-9 and len(E) == D.seg.nunique(), align
    xs = np.round(np.arange(4.2, 19.8001, 0.04), 4); rho = np.hypot(xs - 4.0, 0.3); far = np.where(rho > 6.0)[0]
    wins = [far[i:i + 25] for i in range(0, len(far) - 24, 25)]
    sw = np.stack([np.sqrt(np.mean(SG[:, w] ** 2, axis=1)) for w in wins], 1)          # (nseg, nwin)
    tw = np.stack([np.sqrt(np.mean(E[:, w] ** 2, axis=1)) for w in wins], 1)
    D['sigma_w'] = sw[D.seg.to_numpy(), D.win.to_numpy()]; D['true_w'] = tw[D.seg.to_numpy(), D.win.to_numpy()]
    tr_order = sorted(M.trace.unique()); fold_of = {t: i % 2 for i, t in enumerate(tr_order)}
    D['fold'] = M.trace.map(fold_of).to_numpy()[D.seg.to_numpy()]
    for st in STATS:
        D[st + '/s'] = D[st] / D.sigma_w; D[st + '/s2'] = D[st] / D.sigma_w ** 2

    # --- sigma calibration (filter consistency), NULL rows only (one per seg/win/config) ---
    U = D[(D.hyp == 'NULL') & (D.mount == 0) & (D.yaw_body == 0)]
    cal = {'pearson_rank_sigma_vs_true': float(np.corrcoef(U.sigma_w.rank(), U.true_w.rank())[0, 1]),
           'ratio_true_over_sigma_median': float(np.median(U.true_w / U.sigma_w)),
           'sigma_w_median_deg': float(U.sigma_w.median()), 'true_w_median_deg': float(U.true_w.median())}
    dec = U.assign(dec=pd.qcut(U.sigma_w, 10, labels=False)).groupby('dec').agg(sigma_med=('sigma_w', 'median'), true_med=('true_w', 'median'),
                                                                                  true_p90=('true_w', lambda x: np.quantile(x, .9)), n=('true_w', 'size')).reset_index()
    dec.to_csv(out / 'CTRL_TRAJ_05_SIGMA_DECILES.csv', index=False)
    byarm = U.groupby('arm').apply(lambda g: pd.Series({'rank_corr': np.corrcoef(g.sigma_w.rank(), g.true_w.rank())[0, 1],
                                                        'sigma_med': g.sigma_w.median(), 'true_med': g.true_w.median(),
                                                        'true_over_sigma_med': np.median(g.true_w / g.sigma_w)}), include_groups=False).reset_index()
    byarm.to_csv(out / 'CTRL_TRAJ_05_SIGMA_BY_ARM.csv', index=False)

    rows = []
    for (mo, yb), g in D.groupby(['mount', 'yaw_body']):
        for f in (0, 1):
            C = g[g.fold != f]; V = g[g.fold == f]; Cn = C[C.hyp == 'NULL']; Vn = V[V.hyp == 'NULL']
            for alt in ('LOS+C', 'ALL'):
                Vp = V[V.hyp == alt]
                for st in STATS:
                    base = dict(mount=mo, yaw_body=yb, fold=f, alt=alt, stat=st)
                    thr = np.quantile(Cn[st], .95); t_, f_ = tpr_fpr(Vn[st], Vp[st], thr)
                    rows.append({**base, 'scheme': 'none', 'param': 1.0, 'coverage': 1.0, 'tpr': t_, 'fpr': f_})
                    for c in (0.34, 0.5, 0.82):
                        for key, sch in (('sigma_w', 'G_cov'), ('true_w', 'O_oracle')):
                            lim = np.quantile(Cn[key], c); kc = Cn[Cn[key] <= lim]; thr = np.quantile(kc[st], .95)
                            vn = Vn[Vn[key] <= lim]; vp = Vp[Vp[key] <= lim]; t_, f_ = tpr_fpr(vn[st], vp[st], thr)
                            rows.append({**base, 'scheme': sch, 'param': c, 'coverage': len(vn) / len(Vn), 'tpr': t_, 'fpr': f_})
                    for B in (3, 5, 10):
                        edges = np.quantile(Cn.sigma_w, np.linspace(0, 1, B + 1)); edges[0], edges[-1] = -np.inf, np.inf
                        bc = np.digitize(Cn.sigma_w, edges[1:-1]); thr_b = np.array([np.quantile(Cn[st].to_numpy()[bc == b], .95) for b in range(B)])
                        tn = thr_b[np.digitize(Vn.sigma_w, edges[1:-1])]; tp = thr_b[np.digitize(Vp.sigma_w, edges[1:-1])]
                        rows.append({**base, 'scheme': 'S_cov', 'param': B, 'coverage': 1.0,
                                     'tpr': float(np.mean(Vp[st].to_numpy() > tp)), 'fpr': float(np.mean(Vn[st].to_numpy() > tn))})
                    for sfx in ('/s', '/s2'):
                        thr = np.quantile(Cn[st + sfx], .95); t_, f_ = tpr_fpr(Vn[st + sfx], Vp[st + sfx], thr)
                        rows.append({**base, 'scheme': 'Z' + sfx, 'param': 1.0, 'coverage': 1.0, 'tpr': t_, 'fpr': f_})
    R = pd.DataFrame(rows); R.to_csv(out / 'CTRL_TRAJ_05_GATING.csv', index=False)
    S = R.groupby(['alt', 'scheme', 'param', 'stat'])[['coverage', 'tpr', 'fpr']].mean().reset_index()
    S.to_csv(out / 'CTRL_TRAJ_05_SUMMARY.csv', index=False)
    Sc = R.groupby(['alt', 'scheme', 'param', 'stat', 'mount', 'yaw_body'])[['coverage', 'tpr', 'fpr']].mean().reset_index()
    Sc.to_csv(out / 'CTRL_TRAJ_05_SUMMARY_BY_CONFIG.csv', index=False)
    # per-arm, G_cov 0.82 and S_cov 5 for Dperp vs d0_W (LOS+C)
    arm_rows = []
    for (mo, yb), g in D.groupby(['mount', 'yaw_body']):
        for f in (0, 1):
            C = g[g.fold != f]; V = g[g.fold == f]; Cn = C[C.hyp == 'NULL']
            edges = np.quantile(Cn.sigma_w, np.linspace(0, 1, 6)); edges[0], edges[-1] = -np.inf, np.inf
            for st in ('d0_W', 'Dperp'):
                bc = np.digitize(Cn.sigma_w, edges[1:-1]); thr_b = np.array([np.quantile(Cn[st].to_numpy()[bc == b], .95) for b in range(5)])
                for arm, va in V.groupby('arm'):
                    vn = va[va.hyp == 'NULL']; vp = va[va.hyp == 'LOS+C']
                    arm_rows.append({'mount': mo, 'yaw_body': yb, 'fold': f, 'arm': arm, 'stat': st,
                                     'tpr': float(np.mean(vp[st].to_numpy() > thr_b[np.digitize(vp.sigma_w, edges[1:-1])])),
                                     'fpr': float(np.mean(vn[st].to_numpy() > thr_b[np.digitize(vn.sigma_w, edges[1:-1])]))})
    A = pd.DataFrame(arm_rows).groupby(['arm', 'stat'])[['tpr', 'fpr']].mean().reset_index(); A.to_csv(out / 'CTRL_TRAJ_05_SCOV5_BY_ARM.csv', index=False)
    meta = {'status': 'EXPLORATORY', 'yaw_units_in_trace': 'deg' if deg else 'rad', 'alignment_max_abs_diff': align,
            'n_segments': int(len(E)), 'folds': fold_of, 'sigma_calibration': cal,
            'windows_input_sha256': hashlib.sha256(Path(a.windows).read_bytes()).hexdigest(),
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    meta['outputs'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
    (out / 'CTRL_TRAJ_05_MANIFEST.json').write_text(json.dumps(meta, indent=1))
    pd.set_option('display.width', 220); pd.set_option('display.max_rows', 500)
    print(json.dumps(cal)); print(dec.round(3).to_string(index=False)); print(byarm.round(3).to_string(index=False))
    print(S[S.alt == 'LOS+C'].pivot_table(index=['scheme', 'param'], columns='stat', values='tpr').round(3).to_string())
    print(S[S.alt == 'LOS+C'].pivot_table(index=['scheme', 'param'], columns='stat', values='fpr').round(3).to_string())
    print(S[S.alt == 'LOS+C'].pivot_table(index=['scheme', 'param'], columns='stat', values='coverage').round(3).to_string())
    print(Sc[(Sc.alt == 'LOS+C') & (Sc.stat == 'Dperp')].pivot_table(index=['scheme', 'param'], columns=['mount', 'yaw_body'], values='tpr').round(3).to_string())
    print(A.pivot_table(index='arm', columns='stat', values=['tpr', 'fpr']).round(3).to_string())


if __name__ == '__main__':
    main()
