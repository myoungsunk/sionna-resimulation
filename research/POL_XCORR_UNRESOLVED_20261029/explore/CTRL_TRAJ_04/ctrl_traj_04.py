#!/usr/bin/env python3
"""CTRL-TRAJ-04 — head-to-head: d0-type power-only statistics vs signal-correlation (Stokes) statistics
under the SAME real EKF heading-prior errors, channel and windows as CTRL-TRAJ-03 (EXPLORATORY, label-free).

Statistics per 1 m window in the far region (rho > 6 m), all as |window mean of signed deviation|:
  d0_fp  : s_fp(obs) - s_fp(pred at psi+e)            FP-tap power ratio = the EKF observation (previous d0)
  d0_W   : S1(obs) - S1(pred)                         same 7-tap window, power-difference component only
  Dvec   : |S(obs) - S(pred)|  (3 Stokes components)  includes S2/S3 = two-port complex correlation
  Dperp  : component of S(obs)-S(pred) orthogonal to dS_pred/dpsi   (needs S2/S3)
  *_fit  : window-level nuisance fit: one heading-error amplitude a per 1 m window is fitted by least squares along the
           heading sensitivity (ds/dpsi for scalars, dS/dpsi for Stokes) and the rms residual is reported. This is the
           strongest fair power-only competitor: a scalar has no per-sample direction orthogonal to heading, so the only
           way a power-only statistic can discount heading error is a fit across samples.
  d0_W uses the power-only window ratio (J11-J22)/(J11+J22) (no cross term), not the normalised Stokes S1.
Units: d0_* in s-units (dimensionless, -1..1); D* in degrees of Stokes chord. Detection is rank-based (AUC, TPR@FPR),
so unit differences do not matter.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
C2 = _load('c2', HERE.parent / 'CTRL_TRAJ_02' / 'ctrl_traj_02.py')
C3 = _load('c3', HERE.parent / 'CTRL_TRAJ_03' / 'ctrl_traj_03.py')
STATS = ['d0_fp', 'd0_W', 'd0_fp_fit', 'd0_W_fit', 'Dvec', 'Dperp', 'Dvec_fit']


def observe_ext(H):
    """C2.observe plus the power-only 7-tap window ratio sW = (J11-J22)/(J11+J22) on the same window."""
    S, n0, q, sfp = C2.observe(H)
    nf = H.shape[0]; w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    c = np.fft.ifft(H * w[:, None, None], n=4 * nf, axis=0) * nf; ii = np.arange(H.shape[1])
    W = c[n0[None, :] + np.arange(-2, 5)[:, None], ii[None, :], :]
    j11 = np.sum(abs(W[..., 0]) ** 2, 0); j22 = np.sum(abs(W[..., 1]) ** 2, 0)
    return S, sfp, (j11 - j22) / (j11 + j22)


def fit_resid(d, g):
    """rms residual of d after LS fit of one amplitude along g (d, g: (m,) or (m,k))."""
    d = d.reshape(len(d), -1); g = g.reshape(len(g), -1); a = np.sum(d * g) / max(np.sum(g * g), 1e-30)
    return float(np.sqrt(np.mean(np.sum((d - a * g) ** 2, axis=1))))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--repo-root', required=True); ap.add_argument('--bank-dir', required=True)
    ap.add_argument('--trace-dir', required=True); ap.add_argument('--out', required=True); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    ant = C2.Antennas(Path(a.repo_root), a.bank_dir)
    E, M, files = C3.load_errors(a.trace_dir)
    M['rms'] = np.sqrt(np.mean(E ** 2, axis=1)); M['cond'] = M.trace.str.extract(r'_full_(B0|L2)')[0]
    A = np.array([4.0, 0.0, 2.65]); xs = np.round(np.arange(4.2, 19.8001, 0.04), 4)
    T = np.column_stack([xs, np.full(len(xs), 0.3), np.full(len(xs), 0.45)])
    rho = np.hypot(xs - A[0], 0.3); far = np.where(rho > 6.0)[0]
    wins = [far[i:i + 25] for i in range(0, len(far) - 24, 25)]
    grid = np.round(np.arange(-20, 20.0001, 0.25), 4); ii = np.arange(len(xs)); rows = []
    for mount in (0, 45):
        for yb in (0, 180):
            base = float(yb + mount)
            obsg = [observe_ext(C2.channel(ant, A, T, np.full(len(xs), base + g), [])) for g in grid]
            G = np.stack([o[0] for o in obsg]); SF = np.stack([o[1] for o in obsg]); SW = np.stack([o[2] for o in obsg])
            k0 = int(np.argmin(abs(grid))); dG = np.gradient(G, grid, axis=0)
            dSF = np.gradient(SF, grid, axis=0); dSW = np.gradient(SW, grid, axis=0)
            obs = {'NULL': (G[k0], SF[k0], SW[k0])}
            for sc in ('LOS+C', 'ALL'):
                obs[sc] = observe_ext(C2.channel(ant, A, T, np.full(len(xs), base), C2.SCEN[sc]))
            if mount == 0 and yb == 0:
                print('sens |dS/dpsi| deg/deg median', float(np.degrees(np.median(np.linalg.norm(dG[k0][far], axis=1)))),
                      '|ds_fp/dpsi| /deg', float(np.median(abs(dSF[k0][far]))), '|ds_W/dpsi| /deg', float(np.median(abs(dSW[k0][far]))), flush=True)

            def lin(X, k, w):
                return ((1 - w)[:, None] * X[k, ii] + w[:, None] * X[k + 1, ii]) if X.ndim == 3 else (1 - w) * X[k, ii] + w * X[k + 1, ii]

            def pred(e):
                e = np.clip(e, grid[0], grid[-1]); k = np.clip(np.searchsorted(grid, e) - 1, 0, len(grid) - 2)
                w = (e - grid[k]) / (grid[k + 1] - grid[k])
                S = lin(G, k, w); S /= np.linalg.norm(S, axis=1, keepdims=True)
                traw = lin(dG, k, w); t = traw / np.maximum(np.linalg.norm(traw, axis=1, keepdims=True), 1e-12)
                return S, t, traw, lin(SF, k, w), lin(dSF, k, w), lin(SW, k, w), lin(dSW, k, w)
            for si, e in enumerate(E):
                Sp, tv, traw, sfp, gfp, swp, gw = pred(e)
                for hyp, (So, sfo, swo) in obs.items():
                    d = So - Sp; dp = d - np.sum(d * tv, axis=1, keepdims=True) * tv; ds = sfo - sfp; dw = swo - swp
                    for wi, w in enumerate(wins):
                        rows.append((mount, yb, si, hyp, wi, abs(ds[w].mean()), abs(dw[w].mean()),
                                     fit_resid(ds[w], gfp[w]), fit_resid(dw[w], gw[w]),
                                     float(np.degrees(np.linalg.norm(d[w].mean(0)))), float(np.degrees(np.linalg.norm(dp[w].mean(0)))),
                                     float(np.degrees(fit_resid(d[w], traw[w])))))
            print('config done', mount, yb, flush=True)
    D = pd.DataFrame(rows, columns=['mount', 'yaw_body', 'seg', 'hyp', 'win'] + STATS)
    D = D.merge(M[['arm', 'cond', 'rms']].reset_index().rename(columns={'index': 'seg'}), on='seg')
    D.to_csv(out / 'CTRL_TRAJ_04_WINDOWS.csv.gz', index=False)
    res = []
    for keys, g in D.groupby(['mount', 'yaw_body']):
        for alt in ('LOS+C', 'ALL'):
            for st in STATS:
                n = g[g.hyp == 'NULL'][st].to_numpy(); p = g[g.hyp == alt][st].to_numpy()
                res.append({'mount': keys[0], 'yaw_body': keys[1], 'alt': alt, 'stat': st, 'auc': C3.auc(n, p),
                            'tpr_fpr05': C3.tpr_at(n, p, .05), 'tpr_fpr10': C3.tpr_at(n, p, .10)})
    R = pd.DataFrame(res); R.to_csv(out / 'CTRL_TRAJ_04_DETECTION.csv', index=False)
    gate = []
    for lim in (2, 4, 8, 1e9):
        g = D[D.rms <= lim]
        for st in STATS:
            n = g[g.hyp == 'NULL'][st].to_numpy(); p = g[g.hyp == 'LOS+C'][st].to_numpy()
            gate.append({'rms_le': lim, 'stat': st, 'frac_seg': g.seg.nunique() / D.seg.nunique(), 'auc': C3.auc(n, p), 'tpr_fpr05': C3.tpr_at(n, p, .05)})
    pd.DataFrame(gate).to_csv(out / 'CTRL_TRAJ_04_ORACLE_GATE.csv', index=False)
    arm = []
    for keys, g in D.groupby(['arm', 'cond']):
        for st in STATS:
            n = g[g.hyp == 'NULL'][st].to_numpy(); p = g[g.hyp == 'LOS+C'][st].to_numpy()
            arm.append({'arm': keys[0], 'cond': keys[1], 'stat': st, 'auc': C3.auc(n, p), 'tpr_fpr05': C3.tpr_at(n, p, .05)})
    pd.DataFrame(arm).to_csv(out / 'CTRL_TRAJ_04_BY_ARM.csv', index=False)
    pool = []
    for alt in ('LOS+C', 'ALL'):
        for st in STATS:
            n = D[D.hyp == 'NULL'][st].to_numpy(); p = D[D.hyp == alt][st].to_numpy()
            pool.append({'alt': alt, 'stat': st, 'auc': C3.auc(n, p), 'tpr_fpr05': C3.tpr_at(n, p, .05), 'tpr_fpr10': C3.tpr_at(n, p, .10),
                         'null_med': float(np.median(n)), 'null_p95': float(np.quantile(n, .95)), 'alt_med': float(np.median(p))})
    P = pd.DataFrame(pool); P.to_csv(out / 'CTRL_TRAJ_04_POOLED.csv', index=False)
    meta = {'status': 'EXPLORATORY', 'n_segments': int(len(E)), 'banks': ant.receipts,
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    meta['outputs'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
    (out / 'CTRL_TRAJ_04_MANIFEST.json').write_text(json.dumps(meta, indent=1))
    pd.set_option('display.width', 220)
    print(R.pivot_table(index=['alt', 'stat'], columns=['mount', 'yaw_body'], values='auc').round(3).to_string())
    print(R.pivot_table(index=['alt', 'stat'], columns=['mount', 'yaw_body'], values='tpr_fpr05').round(3).to_string())
    print(pd.DataFrame(gate).round(3).to_string(index=False)); print(P.round(4).to_string(index=False))
    print(pd.DataFrame(arm).pivot_table(index='stat', columns=['cond', 'arm'], values='auc').round(3).to_string())


if __name__ == '__main__':
    main()
