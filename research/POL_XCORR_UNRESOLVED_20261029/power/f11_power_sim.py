#!/usr/bin/env python3
"""POL-XCORR-001 F-11 — label-free power simulation for the primary E1 go rule.

Uses ONLY the real timeline drive structure (travelled distance, 1 m block ids, route sizes) from the P0
POSE_ALIGNMENT table. Labels and features are SYNTHETIC. No real label, no real Full-channel metric is read.

Model (assumption, declared before freeze):
  z0, z1, e ~ independent OU (exponential-covariance Gaussian) processes along travelled distance,
  correlation length ell [m], uncorrelated across drive segments. Baseline score x0 = z0 (M0 proxy), candidate adds x1 = z1 (q_W proxy).
  latent y* = z0 + beta*z1 + kappa*e ; label = 1{y* >= q0.80 of pooled training routes}.
  (kappa, beta) are calibrated on 200k iid draws so that population AUC(M0) = auc0 and
  AUC(oracle M0+q) - AUC(M0) = delta.
Procedure = contract: leave-one-route-out, logistic (C fixed, here unpenalised IRLS on 1-2 standardised
features), held-out ΔAUC, 1 m block bootstrap 95% percentile CI (B as contract), go rule
  CI_lo > 0 in >= 2/3 routes AND ΔAUC > 0 in 3/3 routes.
Conservative: one case per route (aA_m0); pooling aA/aB/m45 with joint blocks is not credited.
"""
from __future__ import annotations
import argparse, hashlib, json, platform
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

POSE = 'research/POL_XCORR_UNRESOLVED_20261029/results_p0/run_40867521966/POSE_ALIGNMENT.csv'
CASE_PER_ROUTE = {'R2': 'R2_aA_m0', 'R4': 'R4_aA_m0', 'R5': 'R5_aA_m0'}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def auc(score, y):
    o = np.argsort(score, kind='mergesort'); yy = y[o]
    npos = yy.sum(); nneg = len(yy) - npos
    cneg = np.cumsum(1 - yy)
    return float((cneg[yy == 1]).sum() / (npos * nneg))


def auc_weighted(score, y, W):
    """W: (B, n) nonnegative weights. Returns (B,) AUCs (ties ignored; continuous scores)."""
    o = np.argsort(score, kind='mergesort'); Wy = W[:, o]; yy = y[o].astype(bool)
    wneg = np.where(yy[None, :], 0.0, Wy); wpos = np.where(yy[None, :], Wy, 0.0)
    cneg = np.cumsum(wneg, axis=1)
    num = (wpos * cneg).sum(axis=1); den = wpos.sum(axis=1) * wneg.sum(axis=1)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def logistic_fit(X, y, iters=50):
    X1 = np.column_stack([np.ones(len(X)), X]); b = np.zeros(X1.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X1 @ b)); W = p * (1 - p) + 1e-12
        H = X1.T @ (X1 * W[:, None]) + 1e-8 * np.eye(X1.shape[1]); g = X1.T @ (y - p)
        step = np.linalg.solve(H, g); b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return b


def logistic_score(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


_CHOL = {}


def ou3(R, ell, rng):
    """Three independent OU processes along travelled distance (exact Gaussian, cov exp(-|dd|/ell), 0 across segments)."""
    key = (id(R), ell)
    if key not in _CHOL:
        d = R['dist']; same = R['seg'][:, None] == R['seg'][None, :]
        C = np.exp(-np.abs(d[:, None] - d[None, :]) / ell) * same + 1e-10 * np.eye(len(d))
        _CHOL[key] = np.linalg.cholesky(C)
    return _CHOL[key] @ rng.normal(size=(len(R['dist']), 3))


def calibrate(auc0, delta, rng, n=200_000):
    z0, z1, e = rng.normal(size=(3, n))

    def aucs(beta, kappa):
        ys = z0 + beta * z1 + kappa * e; y = (ys >= np.quantile(ys, 0.8)).astype(int)
        return auc(z0, y), auc(z0 + beta * z1, y)
    beta = 0.0
    # outer: beta for delta, inner: kappa for auc0 (both monotone)
    def kappa_for(beta):
        lo, hi = 1e-3, 20.0
        for _ in range(24):
            mid = 0.5 * (lo + hi); a0, _ = aucs(beta, mid)
            lo, hi = (mid, hi) if a0 > auc0 else (lo, mid)
        return 0.5 * (lo + hi)
    if delta > 0:
        lo, hi = 0.0, 3.0
        for _ in range(22):
            mid = 0.5 * (lo + hi); k = kappa_for(mid); a0, a1 = aucs(mid, k)
            lo, hi = (mid, hi) if (a1 - a0) < delta else (lo, mid)
        beta = 0.5 * (lo + hi)
    kappa = kappa_for(beta); a0, a1 = aucs(beta, kappa)
    return beta, kappa, a0, a1 - a0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo-root', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--reps', type=int, default=300); ap.add_argument('--boot', type=int, default=2000)
    ap.add_argument('--seed', type=int, default=20261030)
    ap.add_argument('--auc0', type=float, nargs='+', default=[0.70, 0.80])
    ap.add_argument('--delta', type=float, nargs='+', default=[0.0, 0.02, 0.05])
    ap.add_argument('--ell', type=float, nargs='+', default=[0.5, 2.0])
    a = ap.parse_args()
    root = Path(a.repo_root); out = Path(a.out)
    if out.exists():
        raise SystemExit('append-only output exists')
    out.mkdir(parents=True)
    P = pd.read_csv(root / POSE, usecols=['case', 'route', 'pose_id', 'stratum', 'phase', 'travelled_m', 'block_id'])
    routes = {}
    for r, c in CASE_PER_ROUTE.items():
        d = P[(P.case == c) & (P.stratum == 'TIMELINE') & (P.phase == 'drive')].sort_values('pose_id')
        seg = d.block_id.str.split('/').str[2].astype(int).to_numpy()
        blk = pd.factorize(d.block_id)[0]
        routes[r] = {'dist': d.travelled_m.to_numpy(float), 'seg': seg, 'blk': blk, 'n': len(d), 'nb': int(blk.max() + 1)}
    turn_blocks = {r: int(P[(P.case == c) & (P.phase == 'turn')].block_id.nunique()) for r, c in CASE_PER_ROUTE.items()}
    master = np.random.default_rng(a.seed); rows = []; calib = []
    for auc0 in a.auc0:
        for delta in a.delta:
            beta, kappa, a0p, dp = calibrate(auc0, delta, np.random.default_rng(master.integers(2**63)))
            calib.append({'auc0_target': auc0, 'delta_target': delta, 'beta': beta, 'kappa': kappa,
                          'auc0_pop': a0p, 'delta_pop': dp})
            for ell in a.ell:
                rng = np.random.default_rng(master.integers(2**63))
                go = 0; deltas = []; halfw = []; lo_pos = []
                for rep in range(a.reps):
                    sim = {}
                    for r, R in routes.items():
                        Z = ou3(R, ell, rng); z0, z1, e = Z[:, 0], Z[:, 1], Z[:, 2]
                        sim[r] = (z0, z1, z0 + beta * z1 + kappa * e)
                    d_r, lo_r = [], []
                    for held in routes:
                        tr = [r for r in routes if r != held]
                        ys_tr = np.concatenate([sim[r][2] for r in tr]); thr = np.quantile(ys_tr, 0.8)
                        X0 = np.concatenate([sim[r][0] for r in tr]); X1 = np.concatenate([sim[r][1] for r in tr])
                        ytr = (ys_tr >= thr).astype(float)
                        mu = np.array([X0.mean(), X1.mean()]); sd = np.array([X0.std(), X1.std()])
                        b0 = logistic_fit(((X0 - mu[0]) / sd[0])[:, None], ytr)
                        b1 = logistic_fit(np.column_stack([(X0 - mu[0]) / sd[0], (X1 - mu[1]) / sd[1]]), ytr)
                        z0h, z1h, ysh = sim[held]; yh = (ysh >= thr).astype(int)
                        if yh.sum() in (0, len(yh)):
                            d_r.append(np.nan); lo_r.append(np.nan); continue
                        s0 = logistic_score(b0, ((z0h - mu[0]) / sd[0])[:, None])
                        s1 = logistic_score(b1, np.column_stack([(z0h - mu[0]) / sd[0], (z1h - mu[1]) / sd[1]]))
                        dhat = auc(s1, yh) - auc(s0, yh)
                        blk = routes[held]['blk']; nb = routes[held]['nb']
                        cnt = np.zeros((a.boot, nb))
                        draw = rng.integers(0, nb, size=(a.boot, nb))
                        np.add.at(cnt, (np.repeat(np.arange(a.boot), nb), draw.ravel()), 1)
                        Wt = cnt[:, blk]
                        db = auc_weighted(s1, yh, Wt) - auc_weighted(s0, yh, Wt)
                        lo, hi = np.nanpercentile(db, [2.5, 97.5])
                        d_r.append(dhat); lo_r.append(lo); halfw.append((hi - lo) / 2)
                    d_r = np.array(d_r); lo_r = np.array(lo_r)
                    ok = np.nansum(lo_r > 0) >= 2 and np.all(d_r > 0)
                    go += int(ok); deltas.append(np.nanmean(d_r)); lo_pos.append(np.nanmean(lo_r > 0))
                rows.append({'auc0_target': auc0, 'delta_target': delta, 'ell_m': ell, 'reps': a.reps, 'boot': a.boot,
                             'go_rate': go / a.reps, 'mean_heldout_delta': float(np.mean(deltas)),
                             'median_ci_halfwidth': float(np.median(halfw)), 'mean_frac_routes_ci_lo_pos': float(np.mean(lo_pos))})
                print(json.dumps(rows[-1]), flush=True)
    T = pd.DataFrame(rows); T.to_csv(out / 'F11_POWER.csv', index=False)
    pd.DataFrame(calib).to_csv(out / 'F11_CALIBRATION.csv', index=False)
    meta = {'schema': 'POL_XCORR_F11_POWER_V1', 'label_free': True, 'real_inputs': [POSE], 'pose_alignment_sha256': sha(root / POSE),
            'routes': {r: {'case': CASE_PER_ROUTE[r], 'n_drive': R['n'], 'n_drive_blocks': R['nb']} for r, R in routes.items()},
            'turn_blocks_per_route': turn_blocks, 'args': vars(a), 'script_sha256': sha(__file__),
            'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__},
            'utc': datetime.now(timezone.utc).isoformat(),
            'outputs': {p.name: sha(p) for p in out.iterdir() if p.is_file()}}
    (out / 'F11_MANIFEST.json').write_text(json.dumps(meta, indent=1))


if __name__ == '__main__':
    main()
