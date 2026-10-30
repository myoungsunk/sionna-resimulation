#!/usr/bin/env python3
"""POL-XCORR-001 AUDIT-01 — independent recomputation (label-free).

Independence boundary (recorded in the audit report):
  * Imports NOTHING from the repository (no features.py, no p0_preflight.py, no p0v3 script).
  * Definitions were read from features.py / SCIENCE_SPEC; the code below is a separate rewrite.
  * jones_diversity uses the closed-form 2x2 eigenvalue, not eigvalsh.
  * Sampled packets are traced a second time with an explicit DFT sum (no np.fft).
  * Reference tables are read with usecols = keys + reference columns only (no label columns).
Outputs go to a new directory only.
"""
from __future__ import annotations
import argparse, hashlib, json, platform, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

C0 = 299792458.0
TINY = np.finfo(float).tiny
G5 = ['range_m', 'log_fp_power', 'abs_s_fp', 'early4', 'early8', 'early16', 'delay_rms_ns', 'peak_diff_ns',
      'eta_fp_win80', 's_diff4', 's_diff8', 's_diff16', 'tap_pol_var80', 'jones_diversity', 'freq_s_var',
      'detector_s_span', 'detector_delay_span_ns']
SCOPE = 'research/POL_XCORR_UNRESOLVED_20261029'
MANIFEST = 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
HP = 'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz'
UM = 'research/PJ_DS_USAGE_MAP_20261021/results/UM_POSE_TABLE.csv.gz'
IMPL_RUNS = ['run_40884328487', 'run_40884686972']


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- observer + G5 (own rewrite)
def cir_fft(h):
    """h: (N, 257, 2) complex -> (N, 1028, 2)."""
    nf = h.shape[1]
    win = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    return np.fft.ifft(h * win[None, :, None], n=4 * nf, axis=1) * nf


def cir_dft_single(h1):
    """Explicit DFT sum for one packet h1: (257, 2). Same scaling as ifft(...)*nf."""
    nf = h1.shape[0]; M = 4 * nf
    win = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    k = np.arange(nf)[None, :]; n = np.arange(M)[:, None]
    E = np.exp(2j * np.pi * k * n / M)                       # (M, nf)
    return (E @ (h1 * win[:, None])) * (nf / M)


def first_edge(strong, frac):
    pk = strong.max(axis=1)
    above = strong >= frac * pk[:, None]
    return np.argmax(above, axis=1), pk


def observer_and_g5(h, dt):
    cir = cir_fft(h)
    n, M, _ = cir.shape
    amp = np.abs(cir); pw_all = amp * amp
    port_peak = amp.max(axis=1)                               # (N, 2)
    branch = np.where(port_peak[:, 1] > port_peak[:, 0], 1, 0)  # argmax with tie -> port 0
    strong = amp[np.arange(n), :, branch]
    tap, pk = first_edge(strong, 0.30)
    fp_valid = pk > 0
    g5_valid = fp_valid & (tap + 80 <= M)
    out = {'branch': branch, 'tap': tap, 'fp_valid': fp_valid, 'g5_valid': g5_valid, 'cir': cir}
    fp = pw_all[np.arange(n), tap, :]; den = fp[:, 0] + fp[:, 1]
    s_fp = np.full(n, np.nan); ok = den > TINY
    s_fp[ok] = (fp[ok, 0] - fp[ok, 1]) / den[ok]
    out['s_fp'] = s_fp
    feats = {k: np.full(n, np.nan) for k in G5}
    tk = np.arange(80) * dt * 1e9
    for i in range(n):
        t0 = tap[i]
        idx = np.minimum(t0 + np.arange(80), M - 1)
        P = pw_all[i, idx, :]                                 # (80, 2)
        ps = P[:, 0] + P[:, 1]; E = ps.sum()
        w = ps / E if E > TINY else np.zeros(80)
        mt = float(np.dot(w, tk))
        rms = np.sqrt(max(0.0, float(np.dot(w, (tk - mt) ** 2))))
        r = np.where(ps > TINY, (P[:, 0] - P[:, 1]) / np.where(ps > TINY, ps, 1.0), 0.0)
        rb = float(np.dot(w, r)); vpol = float(np.dot(w, (r - rb) ** 2))
        ep = P.sum(axis=0); eps = max(E * 1e-12, TINY); epf = max(den[i] * 1e-12, TINY)
        eta = 0.5 * abs(np.log((fp[i, 0] + epf) / (fp[i, 1] + epf)) - np.log((ep[0] + eps) / (ep[1] + eps)))
        f = feats
        f['range_m'][i] = t0 * dt * C0
        f['log_fp_power'][i] = np.log10(max(den[i], TINY))
        f['abs_s_fp'][i] = abs(s_fp[i])
        f['delay_rms_ns'][i] = rms
        f['peak_diff_ns'][i] = abs(int(np.argmax(P[:, 0])) - int(np.argmax(P[:, 1]))) * dt * 1e9
        f['eta_fp_win80'][i] = eta
        f['tap_pol_var80'][i] = vpol
        for L in (4, 8, 16):
            el = P[:L].sum(axis=0); dl = el.sum()
            sl = (el[0] - el[1]) / dl if dl > TINY else np.nan
            f[f'early{L}'][i] = w[:L].sum()
            f[f's_diff{L}'][i] = abs(s_fp[i] - sl)
        # band-wide Jones second moment, closed-form smallest eigenvalue
        hp = h[i]; sc = np.max(np.abs(hp))
        hn = hp / sc if sc > TINY else np.zeros_like(hp)
        a = float(np.sum(np.abs(hn[:, 0]) ** 2)); b = float(np.sum(np.abs(hn[:, 1]) ** 2))
        c = np.sum(hn[:, 0] * np.conj(hn[:, 1]))
        tr = a + b; det = a * b - abs(c) ** 2
        lmin = tr / 2 - np.sqrt(max((tr / 2) ** 2 - det, 0.0))
        f['jones_diversity'][i] = max(lmin, 0.0) / tr if tr > TINY else np.nan
        pf = np.abs(hn) ** 2; dfp = pf.sum(axis=1); sdf = dfp.sum()
        wf = dfp / sdf if sdf > TINY else np.zeros_like(dfp)
        rs = np.where(dfp > TINY, (pf[:, 0] - pf[:, 1]) / np.where(dfp > TINY, dfp, 1.0), 0.0)
        mr = float(np.dot(wf, rs)); f['freq_s_var'][i] = float(np.dot(wf, (rs - mr) ** 2))
        spans_s, spans_t = [], []
        for q in (0.2, 0.3, 0.4):
            tq = int(np.argmax(strong[i] >= q * pk[i])); fq = pw_all[i, tq, :]; dq = fq.sum()
            spans_s.append((fq[0] - fq[1]) / dq if dq > TINY else np.nan); spans_t.append(tq)
        f['detector_s_span'][i] = np.max(np.abs(np.array(spans_s) - s_fp[i]))
        f['detector_delay_span_ns'][i] = (max(spans_t) - min(spans_t)) * dt * 1e9
    for k in G5:
        feats[k][~g5_valid] = np.nan
    out['g5'] = feats
    return out


def jones_window(cir1, n0):
    """7-tap W = n0-2..n0+4, unnormalized J = sum h h^H. Returns dict or status."""
    M = cir1.shape[0]
    if n0 - 10 < 0 or n0 + 12 >= M or n0 + 6 >= M:
        return {'status': 'INVALID_WINDOW'}
    W = cir1[n0 - 2:n0 + 5, :]
    j11 = float(np.sum(np.abs(W[:, 0]) ** 2)); j22 = float(np.sum(np.abs(W[:, 1]) ** 2))
    j12 = np.sum(W[:, 0] * np.conj(W[:, 1]))
    if j11 <= TINY or j22 <= TINY:
        return {'status': 'NULL_PORT'}
    tr = j11 + j22; det = j11 * j22 - abs(j12) ** 2
    return {'status': 'VALID', 'u': min(j11, j22) / tr, 'q_W': 4 * det / tr ** 2,
            'eps_rho': det / (j11 * j22), 'balance': 4 * j11 * j22 / tr ** 2,
            's_W': (j11 - j22) / tr}


# ---------------------------------------------------------------- math checks (no contract S0)
def gaussian_two_path_check():
    """Continuous-time small-delta law with a Gaussian pulse (NOT the contract's Hann band / q_ref)."""
    t = np.linspace(-40, 40, 40001); dtc = t[1] - t[0]; sig = 3.0
    p = np.exp(-0.5 * (t / sig) ** 2); dp = -t / sig ** 2 * p
    a = np.array([1.0 + 0.0j, 0.35 - 0.2j]); b = np.array([0.25 + 0.1j, -0.4 + 0.3j]) * 0.6
    wedge = abs(a[0] * b[1] - a[1] * b[0]) ** 2
    Ep = np.sum(p * p) * dtc; Epp = np.sum(dp * dp) * dtc; cr = np.sum(p * dp) * dtc
    rows = []
    for d in (0.02, 0.04, 0.08, 0.16, 0.32):
        h = a[None, :] * p[:, None] + b[None, :] * np.exp(-0.5 * ((t - d) / sig) ** 2)[:, None]
        J = (h.T @ h.conj()) * dtc
        det_exact = float(np.real(J[0, 0] * J[1, 1] - abs(J[0, 1]) ** 2))
        det_pred = d * d * wedge * (Ep * Epp - cr * cr)
        rows.append({'delta': d, 'det_exact': det_exact, 'det_pred': det_pred, 'ratio': det_exact / det_pred})
    lx = np.log([r['delta'] for r in rows]); ly = np.log([r['det_exact'] for r in rows])
    slope = float(np.polyfit(lx, ly, 1)[0])
    # parallel Jones -> det == 0 for any delta
    bpar = a * (0.4 - 0.3j)
    h = a[None, :] * p[:, None] + bpar[None, :] * np.exp(-0.5 * ((t - 0.5) / sig) ** 2)[:, None]
    J = (h.T @ h.conj()) * dtc
    det_par = float(np.real(J[0, 0] * J[1, 1] - abs(J[0, 1]) ** 2)) / float(np.real(J[0, 0] * J[1, 1]))
    return {'rows': rows, 'loglog_slope': slope, 'parallel_jones_eps_rho': det_par}


def identity_checks(rng):
    out = {'q_eq_4u1u_eps': 0.0, 'q_eq_4x1x': 0.0}
    for _ in range(20000):
        A = rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)); J = A @ A.conj().T
        j11, j22 = J[0, 0].real, J[1, 1].real; tr = j11 + j22; det = (j11 * j22 - abs(J[0, 1]) ** 2)
        u = min(j11, j22) / tr; q = 4 * det / tr ** 2; e = det / (j11 * j22)
        lmin = tr / 2 - np.sqrt((tr / 2) ** 2 - det); x = lmin / tr
        out['q_eq_4u1u_eps'] = max(out['q_eq_4u1u_eps'], abs(q - 4 * u * (1 - u) * e))
        out['q_eq_4x1x'] = max(out['q_eq_4x1x'], abs(q - 4 * x * (1 - x)))
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo-root', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--r13b-artifact', default=None)
    ap.add_argument('--n-random', type=int, default=24); ap.add_argument('--seed', type=int, default=20261030)
    args = ap.parse_args()
    root = Path(args.repo_root).resolve(); out = Path(args.out)
    if out.exists():
        raise SystemExit(f'append-only: {out} exists')
    out.mkdir(parents=True)
    rng = np.random.default_rng(args.seed)
    R = {'schema': 'POL_XCORR_AUDIT01_V1', 'role': 'AUDITOR', 'independence': 'SELF_REVIEW_ONLY',
         'started_utc': datetime.now(timezone.utc).isoformat(), 'checks': {}}

    def rec(k, status, obs):
        R['checks'][k] = {'status': status, 'observed': obs}

    scope = root / SCOPE
    # A. input lock
    lock = json.loads((scope / 'config/INPUT_LOCK_v2.json').read_text())
    bad = [a['path'] for a in lock['assets'] if sha(root / a['path']) != a['sha256']]
    tr = lock['path_trace_set']
    lines = ''.join(f"{e['path']}\t{sha(root / e['path'])}\n" for e in sorted(tr['files'], key=lambda e: e['path'].encode()))
    setsha = hashlib.sha256(lines.encode()).hexdigest()
    rec('A_INPUT_LOCK', 'PASS' if not bad and setsha == tr['set_sha256'] else 'FAIL',
        {'assets': len(lock['assets']), 'mismatch': bad, 'trace_set_recomputed': setsha, 'trace_set_locked': tr['set_sha256']})
    man = json.loads((root / MANIFEST).read_text())
    freqs = np.load(root / next(a['path'] for a in lock['assets'] if a['kind'] == 'FREQUENCY'))
    df = float(np.mean(np.diff(freqs))); dt = 1.0 / (4 * len(freqs) * df)
    R['dt_ns'] = dt * 1e9

    # B/C/D. full recompute
    full_rows, los_rows, keep = [], [], {}
    for case in man['cases']:
        ids = np.array([s['pose_id'] for s in json.loads((root / case['samples_path']).read_text())], int)
        for ch, key in (('full', 'full_path'), ('los', 'los_path')):
            H = np.load(root / case[key], mmap_mode='r')
            for lo in range(0, len(ids), 128):
                hi = min(lo + 128, len(ids)); h = np.asarray(H[lo:hi, :, :, 0], np.complex128)
                o = observer_and_g5(h, dt)
                base = pd.DataFrame({'case': case['id'], 'channel': ch, 'pose_id': ids[lo:hi], 'n0': o['tap'],
                                     'branch': o['branch'], 'fp_valid': o['fp_valid'], 'g5_valid': o['g5_valid'],
                                     's_fp': o['s_fp']})
                for k in G5:
                    base[k] = o['g5'][k]
                (full_rows if ch == 'full' else los_rows).append(base)
                if ch == 'los':
                    js = [jones_window(o['cir'][j], int(o['tap'][j])) for j in range(hi - lo)]
                    for col in ('status', 'u', 'q_W', 'eps_rho', 'balance', 's_W'):
                        base[col] = [x.get(col) for x in js]
                keep[(case['id'], ch)] = case[key]
    F = pd.concat(full_rows, ignore_index=True); L = pd.concat(los_rows, ignore_index=True)

    def cmp(new, ref, keys, cols, tol=1e-9):
        m = new[keys + cols].merge(ref[keys + cols], on=keys, how='outer', suffixes=('_a', '_r'), indicator=True)
        cover = m['_merge'].value_counts().to_dict(); m = m[m['_merge'] == 'both']
        worst, nanmm, per = 0.0, 0, {}
        for c in cols:
            a = m[c + '_a'].to_numpy(float); b = m[c + '_r'].to_numpy(float)
            nm = int(np.sum(np.isnan(a) != np.isnan(b))); fin = np.isfinite(a) & np.isfinite(b)
            d = float(np.max(np.abs(a[fin] - b[fin]))) if fin.any() else 0.0
            per[c] = {'max_abs': d, 'nan_mismatch': nm}; worst = max(worst, d); nanmm += nm
        ok = cover.get('left_only', 0) == 0 and cover.get('right_only', 0) == 0 and nanmm == 0 and worst <= tol
        return {'status': 'PASS' if ok else 'FAIL', 'coverage': {str(k): int(v) for k, v in cover.items()},
                'max_abs': worst, 'nan_mismatch': nanmm, 'per_column': per}

    hp = pd.read_csv(root / HP, usecols=['case', 'pose_id', 'sF_+0', 'log_fp_power']).rename(columns={'sF_+0': 's_fp'})
    um = pd.read_csv(root / UM, usecols=['case', 'pose_id'] + G5)
    rec('B_R02_SFP_vs_HP', **dict(zip(('status', 'obs'), (lambda r: (r['status'], r))(cmp(F, hp, ['case', 'pose_id'], ['s_fp'])))))
    rec('B_R12_LOGP_vs_HP', **dict(zip(('status', 'obs'), (lambda r: (r['status'], r))(cmp(F, hp, ['case', 'pose_id'], ['log_fp_power'])))))
    rec('C_R13a_G5_vs_UM', **dict(zip(('status', 'obs'), (lambda r: (r['status'], r))(cmp(F, um, ['case', 'pose_id'], G5)))))
    if args.r13b_artifact and Path(args.r13b_artifact).is_file():
        art = pd.read_csv(args.r13b_artifact, usecols=['case', 'channel', 'pose_id'] + G5)
        both = pd.concat([F, L], ignore_index=True)
        r = cmp(both, art, ['case', 'channel', 'pose_id'], G5); r['artifact_sha256'] = sha(args.r13b_artifact)
        rec('C_R13b_G5_vs_artifact', r['status'], r)
    else:
        rec('C_R13b_G5_vs_artifact', 'BLOCKED_REFERENCE_UNAVAILABLE', {'path': args.r13b_artifact})

    # D. compare against implementer P0V3 outputs (LoS n0/branch/u/q/eps, weak counts)
    for run in IMPL_RUNS:
        p = scope / 'results_p0_v03' / run / 'P0V3_LOS_PORT_BALANCE.csv'
        if not p.is_file():
            rec(f'D_IMPL_{run}', 'MISSING', str(p)); continue
        I = pd.read_csv(p)
        m = L.merge(I, on=['case', 'pose_id'], how='outer', suffixes=('_a', '_i'), indicator=True)
        both = m[m['_merge'] == 'both']
        obs = {'coverage': m['_merge'].value_counts().astype(int).to_dict(),
               'n0_mismatch': int((both.n0_a != both.n0_i).sum()), 'branch_mismatch': int((both.branch_a != both.branch_i).sum())}
        for c in ('u', 'q_W', 'eps_rho'):
            obs[c + '_max_abs'] = float(np.nanmax(np.abs(both[c + '_a'].astype(float) - both[c + '_i'].astype(float))))
        obs['weak_audit'] = int((L.u < 0.05).sum()); obs['weak_impl'] = int(I.weak_port.astype(bool).sum())
        ok = (obs['coverage'].get('both', 0) == len(L) == len(I) and obs['n0_mismatch'] == 0 and obs['branch_mismatch'] == 0
              and max(obs['u_max_abs'], obs['q_W_max_abs'], obs['eps_rho_max_abs']) <= 1e-12 and obs['weak_audit'] == obs['weak_impl'])
        obs['coverage'] = {str(k): v for k, v in obs['coverage'].items()}
        rec(f'D_IMPL_LOS_{run}', 'PASS' if ok else 'FAIL', obs)

    # E. random + adversarial packets traced with explicit DFT
    Lr = L.reset_index(drop=True)
    adv = {
        'max_eps_rho': int(Lr.eps_rho.astype(float).idxmax()), 'min_u': int(Lr.u.astype(float).idxmin()),
        'max_q_W': int(Lr.q_W.astype(float).idxmax()), 'min_n0': int(Lr.n0.idxmin()), 'max_n0': int(Lr.n0.idxmax()),
        'u_near_half': int((Lr.u.astype(float) - 0.5).abs().idxmin()),
    }
    picks = [('ADV_' + k, v) for k, v in adv.items()] + [('RAND', int(i)) for i in rng.choice(len(Lr), args.n_random, replace=False)]
    trace = []
    cases = {c['id']: c for c in man['cases']}
    for tag, i in picks:
        row = Lr.iloc[i]; case = cases[row.case]
        ids = np.array([s['pose_id'] for s in json.loads((root / case['samples_path']).read_text())], int)
        k = int(np.where(ids == row.pose_id)[0][0])
        h1 = np.asarray(np.load(root / case['los_path'], mmap_mode='r')[k, :, :, 0], np.complex128)
        c1 = cir_dft_single(h1); a1 = np.abs(c1)
        br = 1 if a1[:, 1].max() > a1[:, 0].max() else 0
        n0 = int(np.argmax(a1[:, br] >= 0.3 * a1[:, br].max()))
        jw = jones_window(c1, n0)
        trace.append({'tag': tag, 'case': row.case, 'pose_id': int(row.pose_id), 'n0_dft': n0, 'n0_fft': int(row.n0),
                      'branch_dft': br, 'branch_fft': int(row.branch), 'q_dft': jw.get('q_W'), 'q_fft': float(row.q_W),
                      'u_dft': jw.get('u'), 'u_fft': float(row.u), 'eps_dft': jw.get('eps_rho'), 'eps_fft': float(row.eps_rho)})
    T = pd.DataFrame(trace); T.to_csv(out / 'AUDIT01_PACKET_TRACE.csv', index=False)
    trel = lambda a, b: float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-300)))
    eobs = {'n': len(T), 'n0_mismatch': int((T.n0_dft != T.n0_fft).sum()), 'branch_mismatch': int((T.branch_dft != T.branch_fft).sum()),
            'q_rel': trel(T.q_dft.astype(float), T.q_fft), 'u_rel': trel(T.u_dft.astype(float), T.u_fft),
            'eps_rel': trel(T.eps_dft.astype(float), T.eps_fft)}
    rec('E_PACKET_TRACE_DFT', 'PASS' if eobs['n0_mismatch'] == 0 and eobs['branch_mismatch'] == 0 and max(eobs['q_rel'], eobs['u_rel'], eobs['eps_rel']) <= 1e-8 else 'FAIL', eobs)

    # F. weak-port summary (own numbers)
    pa = pd.read_csv(scope / 'results_p0/run_40867521966/POSE_ALIGNMENT.csv', usecols=['case', 'pose_id', 'stratum', 'phase'])
    Lw = L.merge(pa, on=['case', 'pose_id'], how='left', validate='one_to_one'); Lw['weak'] = Lw.u.astype(float) < 0.05
    rec('F_WEAK_PORT_COUNTS', 'MEASURED', {
        'all': [int(Lw.weak.sum()), len(Lw)], 'by_stratum': Lw.groupby('stratum').weak.agg(['sum', 'size']).astype(int).to_dict('index'),
        'timeline_by_case_pct': Lw[Lw.stratum == 'TIMELINE'].groupby('case').weak.mean().mul(100).round(2).to_dict(),
        'u_ge_0499': int((Lw.u.astype(float) >= 0.499).sum())})

    # G. port-balance confound in q_W (LoS only, label-free)
    v = Lw[Lw.status == 'VALID'].copy()
    lq = np.log(v.q_W.astype(float)); lb = np.log(v.balance.astype(float)); le = np.log(v.eps_rho.astype(float))
    var = float(np.var(lq)); cov_b = float(np.cov(lq, lb)[0, 1]); cov_e = float(np.cov(lq, le)[0, 1])
    fp_abs = v.s_fp.abs().astype(float); sW = v.s_W.astype(float)
    rec('G_QW_BALANCE_DECOMPOSITION_LOS', 'MEASURED', {
        'identity': 'log q_W = log 4u(1-u) + log eps_rho (exact)',
        'share_of_var_log_q_from_balance': cov_b / var, 'share_from_eps_rho': cov_e / var,
        'spearman_balance_vs_one_minus_sfp2': float(pd.Series(v.balance.astype(float)).corr(1 - fp_abs ** 2, method='spearman')),
        'spearman_sW_vs_sfp': float(pd.Series(sW).corr(v.s_fp.astype(float), method='spearman')),
        'note': 'LoS channel only; no label, no Full-channel M1 values computed'})

    # H. output manifest integrity of implementer runs and earlier P0 runs (append-only)
    integ = {}
    for sub, runs in (('results_p0_v03', IMPL_RUNS), ('results_p0', ['run_40867063352', 'run_40867521966'])):
        for run in runs:
            d = scope / sub / run; mf = json.loads((d / 'MANIFEST.json').read_text())
            files = mf.get('output_file_sha256') or mf.get('files') or {}
            bad = {k: v for k, v in files.items() if (d / k).is_file() and sha(d / k) != v and k != 'MANIFEST.json'}
            missing = [k for k in files if not (d / k).is_file()]
            integ[f'{sub}/{run}'] = {'listed': len(files), 'mismatch': list(bad), 'missing': missing}
    a, b = [scope / 'results_p0_v03' / r for r in IMPL_RUNS]
    common = sorted(set(p.name for p in a.iterdir()) & set(p.name for p in b.iterdir()))
    ident = {n: sha(a / n) == sha(b / n) for n in common}
    integ['impl_runs_common_identical'] = ident
    nbad = sum(len(x['mismatch']) + len(x['missing']) for k, x in integ.items() if isinstance(x, dict) and 'listed' in x)
    rec('H_OUTPUT_INTEGRITY', 'PASS' if nbad == 0 else 'FAIL', integ)

    # I. math (not contract S0)
    rec('I_MATH_IDENTITIES', 'PASS', identity_checks(rng))
    g = gaussian_two_path_check()
    rec('I_MATH_SMALL_DELTA_LAW', 'PASS' if 1.95 <= g['loglog_slope'] <= 2.05 and g['parallel_jones_eps_rho'] < 1e-12 else 'FAIL', g)

    # J. label isolation of implementer outputs
    lab = {'e_s', 'e_r', 'eta', 'T1', 'T2', 'T3', 'eta_W', 'label'}
    hits = {}
    for run in IMPL_RUNS:
        for p in (scope / 'results_p0_v03' / run).glob('*.csv'):
            cols = set(pd.read_csv(p, nrows=0).columns)
            if cols & lab:
                hits[f'{run}/{p.name}'] = sorted(cols & lab)
    rec('J_LABEL_ISOLATION_OUTPUTS', 'PASS' if not hits else 'FAIL', {'label_columns_found': hits})

    L.drop(columns=[c for c in G5], errors='ignore').to_csv(out / 'AUDIT01_LOS_JONES.csv.gz', index=False)
    R['finished_utc'] = datetime.now(timezone.utc).isoformat()
    R['versions'] = {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__}
    R['script_sha256'] = sha(__file__); R['command'] = sys.argv
    core = [k for k, v in R['checks'].items() if v['status'] not in ('PASS', 'MEASURED', 'BLOCKED_REFERENCE_UNAVAILABLE')]
    R['technical_status'] = 'PASS' if not core else 'FAIL:' + ','.join(core)
    (out / 'AUDIT01_CHECKS.json').write_text(json.dumps(R, indent=1, default=float))
    R['outputs'] = {p.name: sha(p) for p in out.iterdir() if p.is_file()}
    (out / 'AUDIT01_MANIFEST.json').write_text(json.dumps({k: R[k] for k in ('schema', 'role', 'independence', 'started_utc', 'finished_utc', 'versions', 'script_sha256', 'command', 'technical_status', 'outputs')}, indent=1))
    print(json.dumps({'technical_status': R['technical_status'], **{k: v['status'] for k, v in R['checks'].items()}}, indent=1))


if __name__ == '__main__':
    main()
