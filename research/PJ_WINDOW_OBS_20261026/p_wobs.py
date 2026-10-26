#!/usr/bin/env python3
"""Window observability of the realized BASE EKF (00_PLAN_KO.md). Offline on error budget v3 arrays.

Diagnostic only: no filter rerun, no model change, no tuning. GT is read for QA and for the
contamination-duration description only.

Per window [s, k] (end k, length L seconds) and variant:
  deterministic (plan formula):  I_{k,N} = sum_i Phi_{i,s}^T H_i^T R_i^-1 H_i Phi_{i,s}
      computed exactly with Psi_i = F_i...F_1:  Phi_{i,r} = Psi_i Psi_r^-1,
      I(ref r) = Psi_r^-T (C_k - C_{s-1}) Psi_r^-1,  C_k = sum_{i<=k} Psi_i^T M_i Psi_i.
      Optional window-constant RF nuisance beta (pol, or range+pol): measurement Jacobian [H_i Phi_{i,r}, E].
  stochastic: finite-memory covariance KF over the same window with the realized process noise
      Q_k = P^-_k - F_k P^+_{k-1} F_k^T (exact from the saved filter covariances) and a non-informative prior.
F, H (at the BASE prior state), R (POWER), accept mask: the realized BASE filter.
"""
from __future__ import annotations
import argparse, json, math, sys, traceback
from pathlib import Path
import numpy as np
import pandas as pd

DEG = 180 / math.pi
LENS = [1, 2, 3, 5, 7.5, 10, 15, 20, 30, 45, 60, 90]
END_EVERY_S = 1.0
NAMES4 = ['x', 'y', 'psi', 'bg']
# reference scales for the scaled Gramian (eigenvalue < 1: that direction is known worse than the scale)
SCALE = {'x': 0.10, 'y': 0.10, 'psi': math.radians(1.0), 'bg': math.radians(0.1), 'br': 0.05, 'bs': 0.01}
PRIOR = {'x': 100., 'y': 100., 'psi': 10., 'bg': 1., 'br': 10., 'bs': 10.}  # non-informative window prior std
COND_MAX = 1e13
OFFS = [-8, -4, -2, -1, 1, 2, 4, 8]
THR_DEG = [1., 2., 5.]


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- inputs
def load_stem(path):
    A = np.load(path, allow_pickle=False)
    g = lambda k: np.asarray(A[k])
    d = {'t': g('t'), 'truth': g('truth'), 'F': g('BASE__F'), 'H': g('BASE__H'), 'R': g('BASE__R'),
         'acc': g('BASE__acc').astype(bool), 'P': g('BASE__P'), 'Pp': g('BASE__Pp'), 'eps': g('BASE__eps'),
         'c1': g('BASE__c1'), 'dp': g('BASE__dp')}
    n = len(d['t'])
    for k in ('F', 'H', 'R', 'P', 'Pp'):
        assert len(d[k]) == n, (k, len(d[k]), n)
    return d


def derived_q(d):
    F, P, Pp = d['F'], d['P'], d['Pp']
    n = len(F)
    Q = np.zeros((n, 4, 4))
    Q[1:] = P[1:] - np.einsum('kij,kjl,kml->kim', F[1:], Pp[:-1], F[1:])
    Q = .5 * (Q + np.transpose(Q, (0, 2, 1)))
    return Q


def acf(x, maxlag):
    x = np.asarray(x, float)
    x = x - x.mean()
    n = len(x)
    v = float(np.dot(x, x) / n)
    L = min(maxlag, n - 2)
    return np.array([1.] + [float(np.dot(x[:n - l], x[l:]) / (n * v)) for l in range(1, L + 1)])


def window_factor(rho, N):
    """Variance factor of a length-N mean of an AR-like series: 1 + 2 sum_{l<N} (1 - l/N) rho_l."""
    N = int(max(1, N))
    l = np.arange(1, min(N, len(rho)))
    return float(1 + 2 * np.sum((1 - l / N) * rho[l]))


def episodes(x, dt, smooth_s):
    """Sign-constant runs of the smoothed series whose |value| exceeds its RMS."""
    w = max(1, int(round(smooth_s / dt)))
    lp = np.convolve(x, np.ones(w) / w, mode='same')
    thr = float(np.sqrt(np.mean(lp ** 2)))
    on = np.abs(lp) > thr
    sg = np.sign(lp)
    runs = []
    i = 0
    n = len(x)
    while i < n:
        if on[i]:
            j = i
            while j + 1 < n and on[j + 1] and sg[j + 1] == sg[i]:
                j += 1
            runs.append((j - i + 1) * dt)
            i = j + 1
        else:
            i += 1
    r = np.array(runs) if runs else np.array([0.])
    return {'smooth_s': smooth_s, 'n_episodes': len(runs), 'dur_median_s': float(np.median(r)),
            'dur_p90_s': float(np.percentile(r, 90)), 'dur_max_s': float(r.max()),
            'time_frac_in_episode': float(on.mean())}


def ds_pseudo_noise(pk, case, route):
    """Held-route ridge of e_s on signed delta-s (8 offsets); returns per-pose prediction residual variance
    (constant for the case) and the held R^2. Train = the two other routes only."""
    X = np.c_[[pk[f'sF_{o:+d}'] - pk['sF_+0'] for o in OFFS]].T
    y = pk['e_s'].to_numpy(float)
    tr = (pk.route != route).to_numpy()
    te = (pk.case == case).to_numpy()
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-12
    Z = (X - mu) / sd
    Zt = np.c_[np.ones(tr.sum()), Z[tr]]
    lam = 1.0 * np.eye(Zt.shape[1])
    lam[0, 0] = 0.
    w = np.linalg.solve(Zt.T @ Zt + lam, Zt.T @ y[tr])
    yh = np.c_[np.ones(te.sum()), Z[te]] @ w
    r = y[te] - yh
    r2 = 1 - float(np.mean(r ** 2)) / float(np.var(y[te]))
    return float(np.mean(r ** 2)), r2, float(np.var(y[te]))


# ---------------------------------------------------------------- deterministic Gramian
class Gram:
    def __init__(self, d):
        F, H, R, acc = d['F'], d['H'], d['R'], d['acc']
        n = len(F)
        Psi = np.zeros((n, 4, 4))
        Psi[0] = np.eye(4)
        for i in range(1, n):
            Psi[i] = F[i] @ Psi[i - 1]
        self.Psi = Psi
        self.PsiInv = np.linalg.inv(Psi)
        Rinv = np.linalg.inv(R) * acc[:, None, None]
        self.Rinv = Rinv
        HPs = np.einsum('kij,kjl->kil', H, Psi)          # H_i Psi_i (n,2,4)
        M = np.einsum('kji,kjl,klm->kim', HPs, Rinv, HPs)  # Psi^T H^T R^-1 H Psi
        self.C = np.concatenate([np.zeros((1, 4, 4)), np.cumsum(M, 0)])
        self.E = {'bs': np.array([[0.], [1.]]), 'brs': np.eye(2)}
        self.CB, self.CBB = {}, {}
        for key, E in self.E.items():
            Bx = np.einsum('kji,kjl,lm->kim', HPs, Rinv, E)
            Bb = np.einsum('ji,kjl,lm->kim', E, Rinv, E)
            self.CB[key] = np.concatenate([np.zeros((1, 4, E.shape[1])), np.cumsum(Bx, 0)])
            self.CBB[key] = np.concatenate([np.zeros((1, E.shape[1], E.shape[1])), np.cumsum(Bb, 0)])

    def info(self, s, k, ref, aug=None):
        """Full information matrix for windows s..k (arrays), referenced to state at ref (array)."""
        T = self.PsiInv[ref]
        Ixx = np.einsum('kji,kjl,klm->kim', T, self.C[k + 1] - self.C[s], T)
        if aug is None:
            return Ixx
        Ixb = np.einsum('kji,kjl->kil', T, self.CB[aug][k + 1] - self.CB[aug][s])
        Ibb = self.CBB[aug][k + 1] - self.CBB[aug][s]
        top = np.concatenate([Ixx, Ixb], 2)
        bot = np.concatenate([np.transpose(Ixb, (0, 2, 1)), Ibb], 2)
        return np.concatenate([top, bot], 1)

    def info_direct(self, d, s, k, ref):
        """Literal plan formula (loop) for QA."""
        F, H, R, acc = d['F'], d['H'], d['R'], d['acc']
        I = np.zeros((4, 4))
        for i in range(s, k + 1):
            Phi = self.Psi[i] @ self.PsiInv[ref]
            if acc[i]:
                I += Phi.T @ H[i].T @ np.linalg.inv(R[i]) @ H[i] @ Phi
        return I


def det_metrics(J, names):
    D = np.array([SCALE[n] for n in names])
    Js = J * D[None, :, None] * D[None, None, :]
    w, V = np.linalg.eigh(Js)
    wmax = np.maximum(w[:, -1], 1e-300)
    rank = (w > 1e-10 * wmax[:, None]).sum(1)
    cond = wmax / np.maximum(w[:, 0], 1e-300)
    vmin = V[:, :, 0] ** 2
    out = {'rank': rank, 'eig_min_scaled': w[:, 0], 'eig_max_scaled': w[:, -1], 'cond_scaled': cond}
    for j, n in enumerate(names):
        out[f'vmin2_{n}'] = vmin[:, j]
    ok = (cond < COND_MAX) & (w[:, 0] > 0)
    cov = np.full_like(J, np.nan)
    if ok.any():
        cov[ok] = np.linalg.inv(J[ok])
    ip = names.index('psi')
    out['sig_psi_deg'] = np.where(ok, np.sqrt(np.abs(cov[:, ip, ip])) * DEG, np.inf)
    out['sig_bg_dps'] = np.where(ok, np.sqrt(np.abs(cov[:, 3, 3])) * DEG, np.inf)
    out['sig_xy_m'] = np.where(ok, np.sqrt(np.abs(cov[:, 0, 0] + cov[:, 1, 1])), np.inf)
    if 'bs' in names:
        ib = names.index('bs')
        out['corr_psi_bs'] = np.where(ok, cov[:, ip, ib] / np.sqrt(np.abs(cov[:, ip, ip] * cov[:, ib, ib])), np.nan)
        out['cos_psi_bs'] = J[:, ip, ib] / np.sqrt(np.maximum(J[:, ip, ip] * J[:, ib, ib], 1e-300))
        out['sig_bs'] = np.where(ok, np.sqrt(np.abs(cov[:, ib, ib])), np.inf)
    return out


# ---------------------------------------------------------------- stochastic window KF
def kf_windows(d, Q, starts, nsteps, aug=None, rfac=(1., 1.), ds_var=None, zeroQ=False):
    F, H, R, acc = d['F'], d['H'], d['R'], d['acc']
    names = NAMES4 + ([] if aug is None else (['bs'] if aug == 'bs' else ['br', 'bs']))
    nb = len(names) - 4
    dim = len(names)
    J = len(starts)
    P = np.zeros((J, dim, dim))
    for j, n in enumerate(names):
        P[:, j, j] = PRIOR[n] ** 2
    E = np.zeros((2, nb))
    if aug == 'bs':
        E[1, 0] = 1.
    elif aug == 'brs':
        E[:, :] = np.eye(2)
    rs = np.sqrt(np.array(rfac))
    I = np.eye(dim)
    for m in range(nsteps + 1):
        i = starts + m
        if m > 0:
            Fi = np.repeat(I[None], J, 0)
            Fi[:, :4, :4] = F[i]
            P = np.einsum('kij,kjl,kml->kim', Fi, P, Fi)
            if not zeroQ:
                P[:, :4, :4] += Q[i]
        Hi = np.zeros((J, 2, dim))
        Hi[:, :, :4] = H[i]
        Hi[:, :, 4:] = E
        Ri = R[i] * rs[None, :, None] * rs[None, None, :]
        HP = np.einsum('kij,kjl->kil', Hi, P)
        S = np.einsum('kij,klj->kil', HP, Hi) + Ri
        K = np.transpose(np.linalg.solve(S, HP), (0, 2, 1))
        K[~acc[i]] = 0.
        A = I[None] - np.einsum('kij,kjl->kil', K, Hi)
        P = np.einsum('kij,kjl,kml->kim', A, P, A) + np.einsum('kij,kjl,kml->kim', K, Ri, K)
        if ds_var is not None and aug is not None:
            ib = names.index('bs')
            v = ds_var[i] * rfac[1]
            ph = P[:, :, ib]
            s = P[:, ib, ib] + v
            Kd = ph / s[:, None]
            P = P - np.einsum('ki,kj->kij', Kd, ph)
        P = .5 * (P + np.transpose(P, (0, 2, 1)))
    return P, names


def stoch_metrics(P, names):
    ip = names.index('psi')
    out = {'sig_psi_deg': np.sqrt(P[:, ip, ip]) * DEG, 'sig_bg_dps': np.sqrt(P[:, 3, 3]) * DEG,
           'sig_xy_m': np.sqrt(P[:, 0, 0] + P[:, 1, 1])}
    out['psi_prior_frac'] = np.sqrt(P[:, ip, ip]) / PRIOR['psi']
    if 'bs' in names:
        ib = names.index('bs')
        out['corr_psi_bs'] = P[:, ip, ib] / np.sqrt(P[:, ip, ip] * P[:, ib, ib])
        out['sig_bs'] = np.sqrt(P[:, ib, ib])
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='directory tree containing *_EB3_ARRAYS.npz')
    ap.add_argument('--packets', required=True, help='HP_PACKETS.csv.gz')
    ap.add_argument('--series', required=True, help='HP_SERIES.csv.gz (k -> pose_id map)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--cases', default='')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(a.input).rglob('*_EB3_ARRAYS.npz'))
    if a.cases:
        keep = set(a.cases.split(','))
        files = [f for f in files if f.name.split('_full_')[0] in keep]
    assert files, 'NO_EB3_ARRAYS'
    pk = pd.read_csv(a.packets)
    se = pd.read_csv(a.series, usecols=['case', 'bias', 'k', 't_s', 'pose_id'])
    frames, cont, cfac = [], [], []
    qa = {}
    rng = np.random.default_rng(20261026)
    for f in files:
        stem = f.name.replace('_EB3_ARRAYS.npz', '')
        case, bias = stem.split('_full_')
        route = case.split('_')[0]
        try:
            process_stem(f, stem, case, bias, route, pk, se, frames, cont, cfac, qa, rng)
        except Exception:
            tb = traceback.format_exc()
            log('WOBS_STEM_FAIL ' + stem + '\n' + tb)
            qa[stem] = {'error': tb}
    finish(out, frames, cont, cfac, qa)


def process_stem(f, stem, case, bias, route, pk, se, frames, cont, cfac, qa, rng):
    if True:
        d = load_stem(f)
        log('WOBS_KEYS ' + stem + ' ' + json.dumps({k: list(v.shape) for k, v in d.items()}))
        t = d['t']
        n = len(t)
        dt = float(np.median(np.diff(t)))
        q = {}
        log(f'WOBS_START {stem} n={n} dt={dt}')
        # --- QA: process noise, Psi inverse, series alignment, g at GT
        Q = derived_q(d)
        qe = np.linalg.eigvalsh(Q[1:])
        q['Q_min_eig'] = float(qe.min())
        q['Q_max_eig'] = float(qe.max())
        G = Gram(d)
        q['psi_inv_resid'] = float(np.max(np.abs(np.einsum('kij,kjl->kil', G.Psi, G.PsiInv) - np.eye(4))))
        ss = se[(se.case == case) & (se.bias == bias)].sort_values('k')
        assert len(ss) == n, ('SERIES_LEN', stem, len(ss), n)
        q['series_t_maxdiff'] = float(np.max(np.abs(ss.t_s.to_numpy() - t)))
        assert q['series_t_maxdiff'] < 1e-6
        pc = pk[pk.case == case].set_index('pose_id').loc[ss.pose_id.to_numpy()]
        g_gt = (pc['sMGTp1_+0'].to_numpy() - pc['sMGTm1_+0'].to_numpy()) / (2 * math.radians(1.))
        g_re = d['H'][:, 1, 2]
        q['g_corr_realized_vs_gt'] = float(np.corrcoef(g_re, g_gt)[0, 1])
        big = np.abs(g_gt) > np.percentile(np.abs(g_gt), 50)
        q['g_ratio_median'] = float(np.median(g_re[big] / g_gt[big]))
        q['heading_rmse_t30_deg'] = float(np.sqrt(np.mean(d['dp'][t >= 30, 2] ** 2)) * DEG)
        q['accept_frac'] = float(d['acc'].mean())
        # Delta-s pseudo-measurement noise (held route), per pose -> per step
        ds_mse, ds_r2, es_var = ds_pseudo_noise(pk, case, route)
        q['ds_heldout_r2'] = ds_r2
        q['ds_pseudo_sd'] = math.sqrt(ds_mse)
        q['es_sd'] = math.sqrt(es_var)
        ds_var = np.full(n, ds_mse)
        # correlation factors per window length (pol, range) from the realized residuals
        rho_s = acf(d['eps'][:, 1], int(max(LENS) / dt) + 2)
        rho_r = acf(d['eps'][:, 0], int(max(LENS) / dt) + 2)
        fac = {L: (max(window_factor(rho_r, L / dt), .2), max(window_factor(rho_s, L / dt), .2)) for L in LENS}
        # contamination durations and per-length correlation factors
        for chn, r in (('pol', rho_s), ('range', rho_r)):
            x = d['eps'][:, 1 if chn == 'pol' else 0]
            neg = np.where(r[1:] <= 0)[0]
            l0 = int(neg[0]) + 1 if len(neg) else len(r)
            tau_int = dt * (1 + 2 * float(r[1:l0].sum())) / 2
            for sm in (1., 5.):
                cont.append({'case': case, 'bias': bias, 'channel': chn, 'tau_int_s': tau_int, **episodes(x, dt, sm)})
            for L in LENS:
                cfac.append({'case': case, 'bias': bias, 'channel': chn, 'window_s': L, 'window_info_factor': window_factor(r, L / dt)})
        # --- QA: cumsum Gramian equals literal formula
        errs = []
        for _ in range(15):
            Ls = int(rng.choice([5, 25, 75, 150]))
            k = int(rng.integers(Ls, n))
            s = k - Ls
            Jd = G.info_direct(d, s, k, s)
            Jc = G.info(np.array([s]), np.array([k]), np.array([s]))[0]
            errs.append(float(np.max(np.abs(Jd - Jc)) / max(np.max(np.abs(Jd)), 1e-30)))
        q['gram_cumsum_vs_loop_relerr'] = max(errs)
        assert q['gram_cumsum_vs_loop_relerr'] < 1e-8
        # --- windows
        every = int(round(END_EVERY_S / dt))
        ends_all = np.arange(0, n, every)
        qa_kf = None
        for L in LENS:
            N = int(round(L / dt))
            ends = ends_all[ends_all >= N]
            if len(ends) == 0:
                continue
            starts = ends - N
            base = {'case': case, 'route': route, 'bias': bias, 'window_s': L}
            gw = np.array([d['H'][s0:e0 + 1, 1, 2][d['acc'][s0:e0 + 1]] for s0, e0 in zip(starts, ends)], dtype=object)
            g_mean = np.array([np.mean(x) if len(x) else np.nan for x in gw])
            g_sd = np.array([np.std(x) if len(x) else np.nan for x in gw])
            g_rms = np.array([np.sqrt(np.mean(x ** 2)) if len(x) else np.nan for x in gw])
            g_sign = np.array([float(np.any(x > 0) and np.any(x < 0)) if len(x) else np.nan for x in gw])
            n_acc = np.array([len(x) for x in gw])
            dpsi = np.abs(np.array([np.unwrap(d['truth'][s0:e0 + 1, 2])[-1] - d['truth'][s0, 2] for s0, e0 in zip(starts, ends)])) * DEG
            common = {'t_end': t[ends], 'k_end': ends, 'n_acc': n_acc, 'g_mean': g_mean, 'g_sd': g_sd, 'g_cv': g_sd / g_rms,
                      'g_sign_change': g_sign, 'turn_deg': dpsi}
            res = {}
            # deterministic, plan formula: rank / eigen at the window start, sigma at the window end
            for vn, aug in (('D4', None), ('D5s', 'bs'), ('D6', 'brs')):
                names = NAMES4 + ([] if aug is None else (['bs'] if aug == 'bs' else ['br', 'bs']))
                Js = G.info(starts, ends, starts, aug)
                Je = G.info(starts, ends, ends, aug)
                ms = det_metrics(Js, names)
                me = det_metrics(Je, names)
                res[vn] = {'rank': ms['rank'], 'eig_min_scaled': ms['eig_min_scaled'], 'cond_scaled': ms['cond_scaled'],
                           **{k: v for k, v in ms.items() if k.startswith('vmin2_')},
                           'sig_psi_deg': me['sig_psi_deg'], 'sig_bg_dps': me['sig_bg_dps'], 'sig_xy_m': me['sig_xy_m']}
                if aug is not None:
                    res[vn].update({'corr_psi_bs': me['corr_psi_bs'], 'cos_psi_bs': me['cos_psi_bs'], 'sig_bs': me['sig_bs']})
            # stochastic finite-memory KF
            for vn, aug, use_ds, corr in (('S4', None, False, False), ('S5s', 'bs', False, False), ('S5s_ds', 'bs', True, False),
                                          ('S6', 'brs', False, False), ('S4c', None, False, True), ('S5s_c', 'bs', False, True),
                                          ('S5s_ds_c', 'bs', True, True)):
                P, names = kf_windows(d, Q, starts, N, aug, fac[L] if corr else (1., 1.), ds_var if use_ds else None)
                res[vn] = stoch_metrics(P, names)
            if qa_kf is None and N >= 25:
                P0, nm0 = kf_windows(d, Q, starts, N, None, zeroQ=True)
                sk = np.sqrt(P0[:, 2, 2]) * DEG
                sd_ = res['D4']['sig_psi_deg']
                okm = np.isfinite(sd_) & (sd_ < 50)
                qa_kf = float(np.max(np.abs(sk[okm] / sd_[okm] - 1))) if okm.any() else np.nan
                q['kf_zeroQ_vs_gram_sigpsi_maxrel'] = qa_kf
                q['kf_zeroQ_check_window_s'] = L
            for vn, mm in res.items():
                fr = pd.DataFrame({**{kk: np.asarray(vv) for kk, vv in common.items()}, **{kk: np.asarray(vv) for kk, vv in mm.items()}})
                for kk, vv in base.items():
                    fr.insert(0, kk, vv)
                fr.insert(4, 'variant', vn)
                frames.append(fr)
            log(f'WOBS_LEN {stem} L={L} windows={len(ends)}')
        qa[stem] = q
        log('WOBS_QA ' + json.dumps({stem: q}))


def finish(out, frames, cont, cfac, qa):
    (out / 'WOBS_QA.json').write_text(json.dumps(qa, indent=2))
    assert frames, 'NO_WINDOWS'
    W = pd.concat(frames, ignore_index=True)
    W.to_csv(out / 'WOBS_WINDOWS.csv.gz', index=False, float_format='%.5g')
    # summaries
    def q10(x): return float(np.nanpercentile(x, 10))
    def q90(x): return float(np.nanpercentile(x, 90))
    agg = {'n': ('t_end', 'size'), 'sig_psi_med': ('sig_psi_deg', 'median'), 'sig_psi_p10': ('sig_psi_deg', q10),
           'sig_psi_p90': ('sig_psi_deg', q90), 'sig_xy_med': ('sig_xy_m', 'median'), 'sig_bg_med': ('sig_bg_dps', 'median'),
           'g_cv_med': ('g_cv', 'median'), 'turn_med': ('turn_deg', 'median')}
    S = W.groupby(['case', 'route', 'bias', 'variant', 'window_s']).agg(**agg).reset_index()
    for thr in THR_DEG:
        S[f'frac_sig_psi_le_{int(thr)}deg'] = W.assign(z=W.sig_psi_deg <= thr).groupby(['case', 'route', 'bias', 'variant', 'window_s']).z.mean().to_numpy()
    if 'corr_psi_bs' in W:
        S['abs_corr_psi_bs_med'] = W.assign(z=W.corr_psi_bs.abs()).groupby(['case', 'route', 'bias', 'variant', 'window_s']).z.median().to_numpy()
    if 'rank' in W:
        S['rank_deficient_frac'] = W.assign(z=W['rank'] < W.variant.map({'D4': 4, 'D5s': 5, 'D6': 6})).groupby(['case', 'route', 'bias', 'variant', 'window_s']).z.mean().to_numpy()
        S['eig_min_scaled_med'] = W.groupby(['case', 'route', 'bias', 'variant', 'window_s']).eig_min_scaled.median().to_numpy()
    S.to_csv(out / 'WOBS_SUMMARY.csv', index=False)
    # minimal window length per end time (same end time across lengths)
    LS = []
    for (case, bias, vn), g in W.groupby(['case', 'bias', 'variant']):
        piv = g.pivot_table(index='t_end', columns='window_s', values='sig_psi_deg', aggfunc='first')
        for thr in THR_DEG:
            ok = piv.le(thr)
            Lstar = ok.apply(lambda r: next((c for c in piv.columns if r.get(c, False)), np.inf), axis=1)
            Lstar = Lstar[piv.index >= 30]
            Lf = np.where(np.isfinite(Lstar), Lstar, 1e9)
            pct = lambda p: (lambda v: float(v) if v < 1e8 else np.inf)(np.percentile(Lf, p, method='higher'))
            LS.append({'case': case, 'bias': bias, 'variant': vn, 'thr_deg': thr, 'n_end': len(Lstar),
                       'Lstar_med_s': pct(50), 'Lstar_p90_s': pct(90),
                       'frac_never': float(np.mean(~np.isfinite(Lstar))),
                       **{f'frac_Lstar_le_{int(c) if float(c).is_integer() else c}s': float(np.mean(Lstar <= c)) for c in (3, 10, 30, 90)}})
    pd.DataFrame(LS).to_csv(out / 'WOBS_LSTAR.csv', index=False)
    pd.DataFrame(cont).to_csv(out / 'WOBS_CONTAM.csv', index=False)
    pd.DataFrame(cfac).to_csv(out / 'WOBS_CORR_FACTOR.csv', index=False)
    (out / 'WOBS_QA.json').write_text(json.dumps(qa, indent=2))
    nfail = sum('error' in v for v in qa.values())
    log(f'WOBS_DONE stems={len(qa)} failed={nfail}')
    if nfail:
        sys.exit(2)
    log('WOBS_ALL_PASS')


if __name__ == '__main__':
    main()
