#!/usr/bin/env python3
"""CTRL-TRAJ-01 — controlled synthetic experiment (EXPLORATORY, outside POL-XCORR-001 estimands).

Question: along a straight constant-yaw drive, how does the FP two-port polarization state (2-port signal correlation)
evolve with position, per reflection mechanism — in particular in the far, ceiling-dominant region?

Controlled environment (no RT corpus, no labels):
  corridor: ceiling z=2.70 (concrete), floor z=0 (concrete), walls y=+-1.2 (plasterboard), half-space Fresnel, 1 bounce
  anchor (4,0,2.65), TX +45 slant LP in horizontal plane, ideal frequency-flat pattern (transverse projection)
  tag z=0.45, y=0.3, x from 4.2 to 20.0 m, 4 cm steps, ports +-45 slant in horizontal plane rotated by yaw
  band = repository freqs_hz.npy (257 bins), observer = Hann, 4N IFFT, stronger-port 30% first edge, W=n0+[-2,4]
Scenarios: LOS, LOS+C, LOS+F, LOS+W(both walls), ALL; yaw = constant 0 deg, or weave +-4 deg (period 4 m)
Ideal antenna => no antenna-dispersion floor (that effect is studied separately).
Orientation: 'hslant' = TX/RX slant +-45 in the horizontal plane (boresight vertical);
             'vslant' = slant +-45 in the y-z plane (boresight along corridor x).
"""
from __future__ import annotations
import json, sys, hashlib
from pathlib import Path
import numpy as np
import pandas as pd

C0 = 299792458.0
EPS0 = 8.854187817e-12
MAT = {'concrete': (5.24, 0.0462, 0.7822), 'plasterboard': (2.73, 0.0085, 0.9395)}  # ITU-R P.2040: eps', a, b (sigma=a f^b)
PLANES = {'C': (np.array([0, 0, 1.0]), 2.70, 'concrete'), 'F': (np.array([0, 0, 1.0]), 0.0, 'concrete'),
          'Wp': (np.array([0, 1.0, 0]), 1.2, 'plasterboard'), 'Wn': (np.array([0, 1.0, 0]), -1.2, 'plasterboard')}
SCEN = {'LOS': [], 'LOS+C': ['C'], 'LOS+F': ['F'], 'LOS+W': ['Wp', 'Wn'], 'ALL': ['C', 'F', 'Wp', 'Wn']}
A = np.array([4.0, 0.0, 2.65])
ORIENT = {'hslant': (np.array([1.0, 1.0, 0.0]) / np.sqrt(2), [np.array([1, 1, 0]) / np.sqrt(2), np.array([1, -1, 0]) / np.sqrt(2)]),
          'vslant': (np.array([0.0, 1.0, 1.0]) / np.sqrt(2), [np.array([0, 1, 1]) / np.sqrt(2), np.array([0, 1, -1]) / np.sqrt(2)])}
PTX, PRX0 = ORIENT['hslant']


def eps_c(mat, f):
    e, a, b = MAT[mat]; sig = a * (f / 1e9) ** b
    return e - 1j * sig / (2 * np.pi * f * EPS0)


def transverse(p, k):
    return p - np.dot(p, k) * k


def rays(T, planes):
    """Return list of (path_length, E_arrival_unit_vector_factor(complex 3-vector per f), arrival dir) for LoS + 1-bounce."""
    out = []
    d = T - A; L = np.linalg.norm(d); k = d / L
    out.append(('LOS', L, None, k, None))
    for name in planes:
        n, c, mat = PLANES[name]
        Ai = A - 2 * (np.dot(A, n) - c) * n                       # image of anchor
        v = T - Ai; Lr = np.linalg.norm(v); kr = v / Lr          # reflected direction (toward tag)
        t = (c - np.dot(A, n)) / np.dot(T - Ai, n) if np.dot(T - Ai, n) != 0 else None
        P = Ai + (np.dot(Ai, n) * 0 + (c - np.dot(Ai, n)) / np.dot(kr, n)) * kr   # reflection point on plane
        kin = (P - A) / np.linalg.norm(P - A)
        out.append((name, Lr, (n, mat), kin, kr))
    return out


def channel(T, yaw_deg, planes, f):
    y = np.radians(yaw_deg)
    R = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])
    prx = [R @ p for p in PRX0]
    H = np.zeros((len(f), 2), complex); info = []
    for name, L, refl, kin, kr in rays(T, planes):
        E = transverse(PTX, kin).astype(complex)
        if refl is None:
            Ef = np.tile(E, (len(f), 1)); karr = kin
        else:
            n, mat = refl
            s = np.cross(kin, n); s /= np.linalg.norm(s)
            pin = np.cross(s, kin); pr = np.cross(s, kr)
            cos_i = abs(np.dot(kin, n)); sin2 = 1 - cos_i ** 2
            er = eps_c(mat, f); root = np.sqrt(er - sin2)
            gte = (cos_i - root) / (cos_i + root); gtm = (er * cos_i - root) / (er * cos_i + root)
            Ef = (gte[:, None] * np.dot(E, s) * s[None, :] + gtm[:, None] * np.dot(E, pin) * pr[None, :])
            karr = kr
            info.append({'path': name, 'cos_inc': cos_i, '|gte|': float(abs(gte[128])), '|gtm|': float(abs(gtm[128])),
                         'delta_ns': (L - np.linalg.norm(T - A)) / C0 * 1e9})
        amp = (C0 / f) / (4 * np.pi * L) * np.exp(-2j * np.pi * f * L / C0)
        for p_i, p in enumerate(prx):
            H[:, p_i] += amp * (Ef @ transverse(p, karr))
    return H, info


def observe(H):
    nf = H.shape[0]; w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    c = np.fft.ifft(H * w[:, None], n=4 * nf, axis=0) * nf
    a = np.abs(c); br = int(np.argmax(a.max(axis=0))); s = a[:, br]; n0 = int(np.argmax(s >= 0.3 * s.max()))
    W = c[n0 - 2:n0 + 5]
    j11 = np.sum(abs(W[:, 0]) ** 2); j22 = np.sum(abs(W[:, 1]) ** 2); j12 = np.sum(W[:, 0] * np.conj(W[:, 1]))
    S = np.array([j11 - j22, 2 * j12.real, -2 * j12.imag]); S /= np.linalg.norm(S)
    hf = H; f11 = np.sum(abs(hf[:, 0]) ** 2); f22 = np.sum(abs(hf[:, 1]) ** 2); f12 = np.sum(hf[:, 0] * np.conj(hf[:, 1]))
    SF = np.array([f11 - f22, 2 * f12.real, -2 * f12.imag]); SF /= np.linalg.norm(SF)
    q = 4 * (j11 * j22 - abs(j12) ** 2) / (j11 + j22) ** 2
    s_fp = (abs(c[n0, 0]) ** 2 - abs(c[n0, 1]) ** 2) / (abs(c[n0, 0]) ** 2 + abs(c[n0, 1]) ** 2)
    return {'n0': n0, 'S': S, 'SF': SF, 'q_W': float(q), 's_fp': float(s_fp), 'p_fp': float(abs(c[n0, 0]) ** 2 + abs(c[n0, 1]) ** 2)}


def ang(u, v):
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v), -1, 1))))


def main(root, out, orient='hslant'):
    global PTX, PRX0
    PTX, PRX0 = ORIENT[orient]
    root = Path(root); out = Path(out); out.mkdir(parents=True, exist_ok=False)
    f = np.load(root / 'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
    xs = np.round(np.arange(4.2, 20.0001, 0.04), 4)
    lam = C0 / (0.5 * (f[0] + f[-1]))
    rows = []
    for yawmode in ('const', 'weave'):
        for x in xs:
            T = np.array([x, 0.3, 0.45]); yaw = 0.0 if yawmode == 'const' else 4.0 * np.sin(2 * np.pi * x / 4.0)
            ref = None
            for sc, planes in SCEN.items():
                H, info = channel(T, yaw, planes, f); o = observe(H)
                if sc == 'LOS':
                    ref = o
                r = {'yaw_mode': yawmode, 'x': x, 'rho_m': float(np.hypot(x - A[0], 0.3)), 'yaw_deg': yaw, 'scenario': sc,
                     'n0': o['n0'], 'q_W': o['q_W'], 's_fp': o['s_fp'], 'p_fp_db': 10 * np.log10(o['p_fp']),
                     'S1': o['S'][0], 'S2': o['S'][1], 'S3': o['S'][2],
                     'dev_from_LOS_W_deg': ang(o['S'], ref['S']), 'dev_from_LOS_band_deg': ang(o['SF'], ref['SF'])}
                if sc == 'ALL':
                    for it in info:
                        r[f"delta_ns_{it['path']}"] = it['delta_ns']; r[f"gte_{it['path']}"] = it['|gte|']; r[f"gtm_{it['path']}"] = it['|gtm|']
                rows.append(r)
    D = pd.DataFrame(rows)
    # trajectory (prior-free) metrics per scenario: geodesic step and band-limited oscillation (periods 0.6-3 m)
    agg = []
    for (ym, sc), g in D.groupby(['yaw_mode', 'scenario']):
        g = g.sort_values('x'); S = g[['S1', 'S2', 'S3']].to_numpy()
        step = np.r_[np.nan, np.degrees(np.arccos(np.clip(np.sum(S[1:] * S[:-1], axis=1), -1, 1)))]
        D.loc[g.index, 'step_deg'] = step
        # sliding 2 m windows: rms of Stokes after removing local quadratic trend, converted to deg on sphere
        osc = np.full(len(g), np.nan); xv = g.x.to_numpy(); half = 25
        for i in range(half, len(g) - half):
            sl = slice(i - half, i + half + 1); xx = xv[sl] - xv[i]
            res = [S[sl, k] - np.polyval(np.polyfit(xx, S[sl, k], 2), xx) for k in range(3)]
            osc[i] = np.degrees(np.sqrt(np.mean(np.sum(np.array(res) ** 2, axis=0))))
        D.loc[g.index, 'osc_rms_deg_2m'] = osc
    D.to_csv(out / 'CTRL_TRAJ_01_ROWS.csv.gz', index=False)
    bins = [4.2, 6, 8, 10, 13, 16, 20.01]
    D['rho_bin'] = pd.cut(D.rho_m, [0, 2, 4, 6, 9, 12, 16.1])
    S = D.groupby(['yaw_mode', 'scenario', 'rho_bin'], observed=True).agg(
        dev_W_med=('dev_from_LOS_W_deg', 'median'), dev_band_med=('dev_from_LOS_band_deg', 'median'),
        osc_rms_med=('osc_rms_deg_2m', 'median'), step_med=('step_deg', 'median'), q_W_med=('q_W', 'median'),
        n0_switch_rate=('n0', lambda v: float(np.mean(np.diff(v.to_numpy()) != 0)))).reset_index()
    S.to_csv(out / 'CTRL_TRAJ_01_SUMMARY.csv', index=False)
    G = D[(D.yaw_mode == 'const') & (D.scenario == 'ALL')][['rho_m'] + [c for c in D.columns if c.startswith(('delta_ns_', 'gte_', 'gtm_'))]]
    geo = G.groupby(pd.cut(G.rho_m, [0, 2, 4, 6, 9, 12, 16.1]), observed=True).median().reset_index(drop=True)
    geo.insert(0, 'rho_bin', ['0-2', '2-4', '4-6', '6-9', '9-12', '12-16'][:len(geo)])
    geo.to_csv(out / 'CTRL_TRAJ_01_GEOMETRY.csv', index=False)
    meta = {'orientation': orient, 'status': 'EXPLORATORY', 'label_free': True, 'outside_contract': 'POL-XCORR-001 estimands not affected',
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'lambda_c_m': lam,
            'outputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}}
    (out / 'CTRL_TRAJ_01_MANIFEST.json').write_text(json.dumps(meta, indent=1))
    pd.set_option('display.width', 220)
    print(geo.round(3).to_string(index=False))
    print(S[S.yaw_mode == 'const'].drop(columns='yaw_mode').round(2).to_string(index=False))
    print(S[(S.yaw_mode == 'weave') & S.scenario.isin(['LOS', 'ALL'])].drop(columns='yaw_mode').round(2).to_string(index=False))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'hslant')
