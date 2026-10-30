#!/usr/bin/env python3
"""CTRL-TRAJ-03 — detectability of the far-range ceiling deviation under REAL, temporally correlated heading-prior errors
(EXPLORATORY, label-free w.r.t. POL-XCORR-001: only filter heading errors are used, no e_s/e_r labels).

Heading-prior error source: EKF traces of run 39376076166 (separate-rs final replay), FULL channel, conditions B0/L2,
all 9 filter arms. prior error at packet k = wrap(state[k-1, arm, yaw] - truth[k, yaw])  (posterior of k-1 as prior).
Only t >= 30 s (contract eval mask). Error sequences of 391 samples (= 15.6 m at 4 cm, the controlled route length;
same 0.2 s / 4 cm cadence as the timeline) are cut with stride 25.

Controlled channel: CTRL-TRAJ-02 construction (real FFD banks, slab Fresnel). Route y=0.3, z=0.45, x 4.2..19.8.
Predicted LoS state S_pred(x, psi+e) from a yaw-offset grid (-20..20 deg, 0.25 deg) with linear interpolation.
Far region: rho > 6 m. Windows: 1 m (25 samples), non-overlapping.
Statistics per window (degrees, small-angle chord):
  Dvec  = | mean_w (S_obs - S_pred) |                     (vector mean: white errors average out)
  Dperp = | mean_w P_perp (S_obs - S_pred) |  where P_perp removes the component along t = dS_pred/dpsi
Null: S_obs = true LoS state.  Alternatives: LOS+C, ALL.  Control: same errors, time order shuffled within segment.
"""
from __future__ import annotations
import argparse, glob, hashlib, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('c2', HERE.parent / 'CTRL_TRAJ_02' / 'ctrl_traj_02.py')
C2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(C2)


def auc(neg, pos):
    x = np.r_[neg, pos]; y = np.r_[np.zeros(len(neg)), np.ones(len(pos))]
    o = np.argsort(x, kind='mergesort'); r = np.empty(len(x)); r[o] = np.arange(1, len(x) + 1)
    return float((r[y == 1].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def tpr_at(neg, pos, fpr=0.05):
    thr = np.quantile(neg, 1 - fpr); return float(np.mean(pos > thr))


def load_errors(art_dir, seg_len=391, stride=25):
    segs, meta = [], []
    files = sorted(glob.glob(str(Path(art_dir) / '**' / '*_full_*_TRACE.npz'), recursive=True))
    for f in files:
        z = np.load(f, allow_pickle=False); st = z['state']; tr = z['truth_scoring_only']; t = z['t_s']; arms = z['arms']
        yaw_t = tr[:, 2]; yaw_e = st[:, :, 2]
        deg = np.max(np.abs(yaw_t)) > 2 * np.pi + 0.1
        if not deg:
            yaw_t = np.degrees(yaw_t); yaw_e = np.degrees(yaw_e)
        err = (yaw_e[:-1] - yaw_t[1:, None] + 180) % 360 - 180          # prior error at k (posterior k-1)
        tt = t[1:]; ok = tt >= 30.0
        name = Path(f).name.replace('_TRACE.npz', '')
        for j, arm in enumerate(arms):
            e = err[ok, j]
            for s in range(0, len(e) - seg_len + 1, stride):
                segs.append(e[s:s + seg_len]); meta.append({'trace': name, 'arm': str(arm), 'start': s})
    return np.array(segs), pd.DataFrame(meta), files


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--repo-root', required=True); ap.add_argument('--bank-dir', required=True)
    ap.add_argument('--trace-dir', required=True); ap.add_argument('--out', required=True); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    ant = C2.Antennas(Path(a.repo_root), a.bank_dir)
    E, M, files = load_errors(a.trace_dir)
    # error statistics
    def acf_len(e):
        e = e - e.mean(); c = np.correlate(e, e, 'full')[len(e) - 1:]; c = c / c[0]
        b = np.where(c < np.exp(-1))[0]; return (b[0] if len(b) else len(e)) * 0.2
    M['abs_med'] = np.median(np.abs(E), axis=1); M['rms'] = np.sqrt(np.mean(E ** 2, axis=1))
    M['acf_1e_s'] = [acf_len(e) for e in E]
    M['cond'] = M.trace.str.extract(r'_full_(B0|L2)')[0]
    A = np.array([4.0, 0.0, 2.65]); xs = np.round(np.arange(4.2, 19.8001, 0.04), 4)
    T = np.column_stack([xs, np.full(len(xs), 0.3), np.full(len(xs), 0.45)])
    rho = np.hypot(xs - A[0], 0.3); far = np.where(rho > 6.0)[0]
    wins = [far[i:i + 25] for i in range(0, len(far) - 24, 25)]
    grid = np.round(np.arange(-20, 20.0001, 0.25), 4)
    rng = np.random.default_rng(20261030); rows = []
    for mount in (0, 45):
        for yb in (0, 180):
            base = float(yb + mount)
            G = np.stack([C2.observe(C2.channel(ant, A, T, np.full(len(xs), base + g), []))[0] for g in grid])   # (ng, n, 3)
            S_true = G[np.argmin(abs(grid))]
            S_alt = {sc: C2.observe(C2.channel(ant, A, T, np.full(len(xs), base), C2.SCEN[sc]))[0] for sc in ('LOS+C', 'ALL')}
            dG = np.gradient(G, grid, axis=0)
            ii = np.arange(len(xs))

            def pred(e):
                e = np.clip(e, grid[0], grid[-1]); k = np.clip(np.searchsorted(grid, e) - 1, 0, len(grid) - 2)
                w = (e - grid[k]) / (grid[k + 1] - grid[k])
                S = (1 - w)[:, None] * G[k, ii] + w[:, None] * G[k + 1, ii]; S /= np.linalg.norm(S, axis=1, keepdims=True)
                t = (1 - w)[:, None] * dG[k, ii] + w[:, None] * dG[k + 1, ii]; t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
                return S, t
            for si, e in enumerate(E):
                for order in ('real', 'shuffled'):
                    ee = e if order == 'real' else rng.permutation(e)
                    Sp, tv = pred(ee)
                    for hyp, Sobs in (('NULL', S_true), ('LOS+C', S_alt['LOS+C']), ('ALL', S_alt['ALL'])):
                        d = Sobs - Sp; dperp = d - np.sum(d * tv, axis=1, keepdims=True) * tv
                        for wi, w in enumerate(wins):
                            rows.append((mount, yb, si, order, hyp, wi,
                                         float(np.degrees(np.linalg.norm(d[w].mean(0)))), float(np.degrees(np.linalg.norm(dperp[w].mean(0))))))
            print('config done', mount, yb, flush=True)
    D = pd.DataFrame(rows, columns=['mount', 'yaw_body', 'seg', 'order', 'hyp', 'win', 'Dvec', 'Dperp'])
    D = D.merge(M[['arm', 'cond']].reset_index().rename(columns={'index': 'seg'}), on='seg')
    D.to_csv(out / 'CTRL_TRAJ_03_WINDOWS.csv.gz', index=False); M.to_csv(out / 'CTRL_TRAJ_03_ERROR_SEGMENTS.csv', index=False)
    res = []
    for keys, g in D.groupby(['mount', 'yaw_body', 'order', 'cond']):
        for stat in ('Dvec', 'Dperp'):
            neg = g[g.hyp == 'NULL'][stat].to_numpy()
            for alt in ('LOS+C', 'ALL'):
                pos = g[g.hyp == alt][stat].to_numpy()
                res.append(dict(zip(['mount', 'yaw_body', 'order', 'cond'], keys), stat=stat, alt=alt, auc=auc(neg, pos), tpr_at_fpr05=tpr_at(neg, pos),
                                null_med=float(np.median(neg)), alt_med=float(np.median(pos))))
    Rz = pd.DataFrame(res); Rz.to_csv(out / 'CTRL_TRAJ_03_DETECTION.csv', index=False)
    arm = []
    for keys, g in D[(D.order == 'real')].groupby(['arm', 'cond']):
        for stat in ('Dvec', 'Dperp'):
            neg = g[g.hyp == 'NULL'][stat].to_numpy(); pos = g[g.hyp == 'LOS+C'][stat].to_numpy()
            arm.append({'arm': keys[0], 'cond': keys[1], 'stat': stat, 'auc_ceiling': auc(neg, pos), 'tpr05_ceiling': tpr_at(neg, pos)})
    pd.DataFrame(arm).to_csv(out / 'CTRL_TRAJ_03_BY_ARM.csv', index=False)
    es = M.groupby(['cond', 'arm'])[['abs_med', 'rms', 'acf_1e_s']].median().reset_index(); es.to_csv(out / 'CTRL_TRAJ_03_ERROR_STATS.csv', index=False)
    meta = {'status': 'EXPLORATORY', 'trace_files': [Path(f).name for f in files], 'n_segments': int(len(E)),
            'error_overall': {'abs_median_deg': float(np.median(np.abs(E))), 'p95_abs_deg': float(np.quantile(np.abs(E), .95)),
                              'acf_1e_s_median': float(M.acf_1e_s.median())},
            'banks': ant.receipts, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    meta['outputs'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
    (out / 'CTRL_TRAJ_03_MANIFEST.json').write_text(json.dumps(meta, indent=1))
    pd.set_option('display.width', 220)
    print(json.dumps(meta['error_overall'])); print(es.round(3).to_string(index=False))
    print(Rz.round(3).to_string(index=False))


if __name__ == '__main__':
    main()
