#!/usr/bin/env python3
"""S0 review diagnostics (label-free, synthetic + LoS-only). EXPLORATORY — post-S0, after H1_FAIL / R03 seen.

D-A  reproduce frozen q_ref (absolute-f delay term) and R-03 decision
D-B  q_ref with band-edge (f-f0) and band-centre (f-fc) referenced delay terms; centre = real symmetric pulse (F2 assumption)
D-C  LAW slope: frozen construction vs baseband construction; detector-following n0 vs n0 frozen at delta=0;
     fit ranges [0.05,1.0] (frozen), [0.05,0.5] and [0.05,0.25] (exploratory)
D-D  floor-equivalent reflection: |b|/|a| at delta=1 ns (wedge 0.3 and 1.0) whose mean q_W equals LoS q95
D-F  slope convergence delta->0 (centre ref, n0 fixed)
D-E  LoS floor after a direction-agnostic port equalizer c(f) estimated leave-one-route-out from LoS H
No repository module is imported; no label column is read.
"""
from __future__ import annotations
import json, sys, hashlib
from pathlib import Path
import numpy as np
import pandas as pd

P = 'research/POL_XCORR_UNRESOLVED_20261029'
MAN = 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'


def cir(Hf):  # Hf (..., 257, 2)
    nf = Hf.shape[-2]; w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    return np.fft.ifft(Hf * w[..., :, None], n=4 * nf, axis=-2) * nf


def n0_of(c):
    a = np.abs(c); br = int(np.argmax(a.max(axis=0))); s = a[:, br]
    return int(np.argmax(s >= 0.3 * s.max()))


def qW(c, n0):
    W = c[n0 - 2:n0 + 5]; j11 = np.sum(abs(W[:, 0]) ** 2); j22 = np.sum(abs(W[:, 1]) ** 2)
    j12 = np.sum(W[:, 0] * np.conj(W[:, 1])); tr = j11 + j22
    return float(4 * (j11 * j22 - abs(j12) ** 2) / tr ** 2)


def H_two(f, a, b, d_ns, psi, mode, tau0=20e-9):
    d = d_ns * 1e-9
    base = np.exp(-2j * np.pi * f * tau0)
    if mode == 'frozen':      # as implemented from TASK_HANDOFF_v1.0 / D6 text
        dl = np.exp(1j * psi - 2j * np.pi * f * d)
    elif mode == 'baseband':  # band-edge referenced: pulse is complex (carrier B/2), extra pi*B*delta phase
        dl = np.exp(1j * psi - 2j * np.pi * (f - f[0]) * d)
    else:                     # 'center': band-centre referenced -> real symmetric Hann pulse, F2 assumption
        fc = 0.5 * (f[0] + f[-1])
        dl = np.exp(1j * psi - 2j * np.pi * (f - fc) * d)
    return base[:, None] * (a[None, :] + b[None, :] * dl[:, None])


def vecs(ratio_db, wedge, a=None):
    a = np.array([1, 1], complex) / np.sqrt(2) if a is None else a / np.linalg.norm(a)
    perp = np.array([a[1].conjugate(), -a[0].conjugate()]); perp /= np.linalg.norm(perp)
    b = 10 ** (ratio_db / 20) * (np.sqrt(1 - wedge ** 2) * a + wedge * perp)
    return a, b


def qref(f, mode, ratio_db=-10, wedge=0.3, d=1.0):
    a, b = vecs(ratio_db, wedge); vals = []
    for k in range(16):
        psi = 2 * np.pi * k / 16
        if np.linalg.norm(a + b * np.exp(1j * psi)) < 0.3 * np.linalg.norm(a):
            continue
        c = cir(H_two(f, a, b, d, psi, mode)); vals.append(qW(c, n0_of(c)))
    return float(np.mean(vals))


def main(root, out):
    root = Path(root); out = Path(out); out.mkdir(parents=True, exist_ok=False)
    man = json.loads((root / MAN).read_text())
    f = np.load(root / 'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
    L = pd.read_csv(root / P / 'results_p0/run_40867521966/LOS_FLOOR.csv')
    q95 = float(np.quantile(L[L.stratum == 'TIMELINE'].q_W, 0.95))
    R = {'los_q95_timeline': q95}
    # D-A / D-B
    for mode in ('frozen', 'baseband', 'center'):
        R[f'qref_{mode}'] = qref(f, mode)
        R[f'ratio_{mode}'] = q95 / R[f'qref_{mode}']
        R[f'R03_{mode}'] = 'NEGLIGIBLE' if q95 <= 0.1 * R[f'qref_{mode}'] else ('NUISANCE' if q95 <= R[f'qref_{mode}'] else 'REDESIGN_REQUIRED')
    # D-C
    rows = []
    grid = np.round(np.arange(0.05, 1.0001, 0.05), 4)
    for mode in ('frozen', 'baseband', 'center'):
        for ratio in (-20, -10, -6, -3):
            for wedge in (0.1, 0.3, 0.6, 1.0):
                a, b = vecs(ratio, wedge)
                for k in range(16):
                    psi = 2 * np.pi * k / 16
                    if np.linalg.norm(a + b * np.exp(1j * psi)) < 0.3 * np.linalg.norm(a):
                        continue
                    c0 = cir(H_two(f, a, b, 0.0, psi, mode)); n_fix = n0_of(c0)
                    qf, qd, sw = [], [], 0; prev = None
                    for d in grid:
                        c = cir(H_two(f, a, b, d, psi, mode)); n = n0_of(c)
                        sw += int(prev is not None and n != prev); prev = n
                        qd.append(qW(c, n)); qf.append(qW(c, n_fix))
                    for lab, q in (('detector', qd), ('n0_fixed', qf)):
                        q = np.array(q)
                        for lo, hi in ((0.05, 1.0), (0.05, 0.5), (0.05, 0.25)):
                            m = (grid >= lo - 1e-9) & (grid <= hi + 1e-9) & (q > 0)
                            s = float(np.polyfit(np.log(grid[m]), np.log(q[m]), 1)[0])
                            rows.append({'mode': mode, 'window': lab, 'fit': f'{lo}-{hi}', 'ratio_db': ratio, 'wedge': wedge,
                                         'psi_k': k, 'slope': s, 'pass': 1.9 <= s <= 2.1, 'n0_switches': sw})
    T = pd.DataFrame(rows); T.to_csv(out / 'S0R_LAW_SLOPES.csv', index=False)
    S = T.groupby(['mode', 'window', 'fit']).agg(n=('slope', 'size'), pass_rate=('pass', 'mean'),
                                                  slope_med=('slope', 'median'), slope_p05=('slope', lambda x: x.quantile(.05)),
                                                  slope_p95=('slope', lambda x: x.quantile(.95)), switches_mean=('n0_switches', 'mean')).reset_index()
    S.to_csv(out / 'S0R_LAW_SUMMARY.csv', index=False)
    # D-D floor-equivalent amplitude
    feq = {}
    for wedge in (0.3, 1.0):
        lo, hi = -40.0, 0.0
        for _ in range(40):
            mid = 0.5 * (lo + hi); qv = qref(f, 'baseband', ratio_db=mid, wedge=wedge)
            lo, hi = (mid, hi) if qv < q95 else (lo, mid)
        feq[f'wedge_{wedge}'] = round(0.5 * (lo + hi), 2)
    R['floor_equivalent_ratio_db_at_delta1ns'] = feq
    # D-E equalizer (LORO over routes), LoS only
    rec = []
    per_route = {}
    for case in man['cases']:
        H = np.asarray(np.load(root / case['los_path'], mmap_mode='r')[:, :, :, 0], complex)
        ratio = H[:, :, 0] / H[:, :, 1]                     # per pose, per f
        ratio_n = ratio / np.mean(ratio, axis=1, keepdims=True)  # remove pose-dependent complex constant
        per_route.setdefault(case['route'], []).append((case['id'], H, ratio_n))
    for held in per_route:
        train = np.concatenate([r for k, v in per_route.items() if k != held for (_, _, r) in v], axis=0)
        cbar = np.median(train.real, axis=0) + 1j * np.median(train.imag, axis=0)   # direction-agnostic c(f)
        for cid, H, _ in per_route[held]:
            He = H.copy(); He[:, :, 1] = He[:, :, 1] * cbar[None, :]
            C0 = cir(H); C1 = cir(He)
            for i in range(len(H)):
                n = n0_of(C0[i]); n1 = n0_of(C1[i])
                rec.append({'case': cid, 'route': held, 'q_raw': qW(C0[i], n), 'q_eq': qW(C1[i], n1)})
    E = pd.DataFrame(rec); E.to_csv(out / 'S0R_EQUALIZER_LOS.csv.gz', index=False)
    R['equalizer'] = {'q95_raw_all': float(E.q_raw.quantile(.95)), 'q95_eq_all': float(E.q_eq.quantile(.95)),
                      'median_raw': float(E.q_raw.median()), 'median_eq': float(E.q_eq.median()),
                      'q95_eq_over_qref_baseband': float(E.q_eq.quantile(.95) / R['qref_baseband'])}
    # D-F asymptotic convergence (centre reference, n0 fixed at delta=0)
    conv = []
    for ratio in (-20, -10, -6, -3):
        for wedge in (0.1, 0.3, 0.6, 1.0):
            a, b = vecs(ratio, wedge)
            for k in range(16):
                psi = 2 * np.pi * k / 16
                if np.linalg.norm(a + b * np.exp(1j * psi)) < 0.3 * np.linalg.norm(a):
                    continue
                n = n0_of(cir(H_two(f, a, b, 0.0, psi, 'center')))
                for lo, hi in ((0.002, 0.01), (0.01, 0.05), (0.05, 0.25), (0.25, 0.5), (0.5, 1.0)):
                    g = np.linspace(lo, hi, 6); q = np.array([qW(cir(H_two(f, a, b, d, psi, 'center')), n) for d in g])
                    conv.append({'range_ns': f'{lo}-{hi}', 'ratio_db': ratio, 'wedge': wedge, 'psi_k': k,
                                 'slope': float(np.polyfit(np.log(g), np.log(q), 1)[0])})
    C = pd.DataFrame(conv); C.to_csv(out / 'S0R_CONVERGENCE.csv', index=False)
    R['convergence_centre_n0fixed'] = {r: {'p05': float(g.slope.quantile(.05)), 'median': float(g.slope.median()), 'p95': float(g.slope.quantile(.95))}
                                       for r, g in C.groupby('range_ns', sort=False)}
    nf = len(f); w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1)); fk = f - 0.5 * (f[0] + f[-1])
    brms = float(np.sqrt(np.sum(fk ** 2 * w ** 2) / np.sum(w ** 2)))
    R['pulse_B_rms_MHz'] = brms / 1e6; R['pulse_sigma_t_ns'] = 1e9 / (2 * np.pi * brms)
    R['law_summary'] = S.round(4).to_dict('records')
    R['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out / 'S0R_DIAG.json').write_text(json.dumps(R, indent=1))
    print(json.dumps({k: v for k, v in R.items() if k != 'law_summary'}, indent=1)); print(S.round(3).to_string(index=False))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
