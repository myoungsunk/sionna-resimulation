#!/usr/bin/env python3
"""CTRL-TRAJ-02 — controlled trajectory experiment with the REAL SourceFFD antenna banks (EXPLORATORY, label-free).

Same controlled corridor as CTRL-TRAJ-01, but antenna fields come from the sha-verified FFD banks
(LP_plus45 / LP_minus45), anchor rotation and robot rotation exactly as in qclean_uwb.scenarios.corridor and
FFD_P0P3_20261016/p0_initial.direct():  H_path[f, r] = F_rx[r](f, -k_arr)^T  J_path  F_tx[0](f, k_dep) * c/(4 pi f L) e^{-j2pi f L/c}.
J_LOS = I;  J_refl = G_TE s s^T + G_TM p_r p_in^T (single-layer slab Fresnel, ITU-R P.2040 materials, scene thicknesses).
Checks:
  V0  LoS parity of this construction against the stored corpus H_LoS (Sionna) at 64 timeline poses per case
Experiment (no corpus RF, no labels):
  straight route y=0.3, z=0.45, x 4.2..19.8 m (4 cm), yaw_body 0 / 180 deg, mount 0 / 45 deg
  scenarios LOS, LOS+C, LOS+F, LOS+W, ALL
  metrics on the FP 7-tap window Stokes state (Hann, 4N IFFT, 30 % stronger-port edge, W = n0+[-2,4]):
    dev_true   angle to the true LoS-only state at the same pose           (prior/model-based detectability)
    osc_rms    2 m sliding-window rms after local quadratic detrend         (prior-free trajectory)
    prior_err  angle between LoS states at yaw and yaw+e, e in {1,2,5} deg  (model error from heading prior)
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

C0 = 299792458.0; EPS0 = 8.854187817e-12
SRC = 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
BANK_SHA = {'LP_plus45_bank.npz': 'b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b',
            'LP_minus45_bank.npz': '39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9'}
MAT = {'concrete': (5.24, 0.0462, 0.7822, 0.20), 'plasterboard': (2.73, 0.0085, 0.9395, 0.0125)}  # eps', a, b, thickness
PLANES = {'C': (np.array([0, 0, 1.0]), 2.70, 'concrete'), 'F': (np.array([0, 0, 1.0]), 0.0, 'concrete'),
          'Wp': (np.array([0, 1.0, 0]), 1.2, 'plasterboard'), 'Wn': (np.array([0, 1.0, 0]), -1.2, 'plasterboard')}
SCEN = {'LOS': [], 'LOS+C': ['C'], 'LOS+F': ['F'], 'LOS+W': ['Wp', 'Wn'], 'ALL': ['C', 'F', 'Wp', 'Wn']}


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def rot_z(deg):
    a = np.radians(deg); return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])


class Antennas:
    def __init__(self, root, bankdir):
        sys.path.insert(0, str(Path(root) / SRC))
        from qclean_uwb.drivesim import pattern_apply as P
        from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION
        self.P = P; self.AR = np.asarray(ANCHOR_ROTATION, float); self.banks = []; self.receipts = {}
        for name in ('LP_plus45_bank.npz', 'LP_minus45_bank.npz'):
            m = list(Path(bankdir).rglob(name)); assert len(m) == 1, (name, m)
            h = sha(m[0]); assert h == BANK_SHA[name], (name, h); self.receipts[name] = h
            with np.load(m[0], allow_pickle=False) as z:
                self.banks.append(P.Bank(dict(z)))
        self.f = self.banks[0].freqs_hz

    def field(self, bank_i, rotation, dirs):
        d = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
        th = np.arccos(np.clip(d[:, 2], -1, 1)); ph = np.arctan2(d[:, 1], d[:, 0])
        return self.P.field_world(self.banks[bank_i], rotation, th, ph)      # (nf, n, 3)


def eps_c(mat, f):
    e, a, b, _ = MAT[mat]; return e - 1j * a * (f / 1e9) ** b / (2 * np.pi * f * EPS0)


def slab_gamma(mat, f, cos_i):
    """Single-layer slab reflection (TE, TM) for arrays f (nf,) and cos_i (n,) -> (nf, n)."""
    er = eps_c(mat, f)[:, None]; d = MAT[mat][3]; sin2 = 1 - cos_i[None, :] ** 2
    root = np.sqrt(er - sin2); ci = cos_i[None, :]
    r_te = (ci - root) / (ci + root); r_tm = (er * ci - root) / (er * ci + root)
    beta = 2 * np.pi * f[:, None] / C0 * d * root; ph = np.exp(-2j * beta)
    g = lambda r: r * (1 - ph) / (1 - r * r * ph)
    return g(r_te), g(r_tm)


def channel(ant, A, T, yaw_tot, planes, rx_rot=None):
    """A (3,), T (n,3), yaw_tot (n,) deg -> H (nf, n, 2rx) for TX port 0 (+45)."""
    f = ant.f; n = len(T); H = np.zeros((len(f), n, 2), complex)
    rrot = [rot_z(y) for y in yaw_tot]

    def rx_fields(dirs):
        out = np.zeros((2, len(f), n, 3), complex)
        for i in range(n):  # per-pose rotation
            for r in range(2):
                out[r, :, i, :] = ant.field(r, rrot[i], dirs[i:i + 1])[:, 0, :]
        return out
    paths = [('LOS', None)] + [(p, PLANES[p]) for p in planes]
    for name, pl in paths:
        if pl is None:
            src = np.broadcast_to(A, T.shape); kdep = T - A; L = np.linalg.norm(kdep, axis=1); kdep = kdep / L[:, None]
            karr = kdep
            J = None
        else:
            nrm, c, mat = pl
            Ai = A - 2 * (A @ nrm - c) * nrm
            v = T - Ai; L = np.linalg.norm(v, axis=1); karr = v / L[:, None]
            tpar = (c - Ai @ nrm) / (karr @ nrm); P_ = Ai[None, :] + tpar[:, None] * karr
            kdep = P_ - A; kdep = kdep / np.linalg.norm(kdep, axis=1, keepdims=True)
            s = np.cross(kdep, nrm); s = s / np.linalg.norm(s, axis=1, keepdims=True)
            pin = np.cross(s, kdep); pr = np.cross(s, karr)
            cos_i = np.abs(kdep @ nrm); gte, gtm = slab_gamma(mat, f, cos_i)
            J = (gte[:, :, None, None] * (s[None, :, :, None] * s[None, :, None, :]) +
                 gtm[:, :, None, None] * (pr[None, :, :, None] * pin[None, :, None, :]))     # (nf, n, 3, 3)
        Ft = ant.field(0, ant.AR, kdep)                      # (nf, n, 3)
        Fr = rx_fields(-karr)                                 # (2, nf, n, 3)
        Et = Ft if J is None else np.einsum('fnij,fnj->fni', J, Ft)
        fac = C0 / f[:, None] / (4 * np.pi * L[None, :]) * np.exp(-2j * np.pi * f[:, None] * L[None, :] / C0)
        for r in range(2):
            H[:, :, r] += np.einsum('fni,fni->fn', Fr[r], Et) * fac
    return H


def observe(H):
    """H (nf, n, 2) -> per pose Stokes unit (n,3), n0, q_W, s_fp."""
    nf = H.shape[0]; w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nf) / (nf - 1))
    c = np.fft.ifft(H * w[:, None, None], n=4 * nf, axis=0) * nf
    a = np.abs(c); n = H.shape[1]; ii = np.arange(n)
    br = np.argmax(a.max(axis=0), axis=1); s = a[:, ii, br]
    n0 = np.argmax(s >= 0.3 * s.max(axis=0)[None, :], axis=0)
    idx = n0[None, :] + np.arange(-2, 5)[:, None]; W = c[idx, ii[None, :], :]          # (7, n, 2)
    j11 = np.sum(abs(W[..., 0]) ** 2, 0); j22 = np.sum(abs(W[..., 1]) ** 2, 0); j12 = np.sum(W[..., 0] * np.conj(W[..., 1]), 0)
    S = np.stack([j11 - j22, 2 * j12.real, -2 * j12.imag], 1); S /= np.linalg.norm(S, axis=1, keepdims=True)
    q = 4 * (j11 * j22 - abs(j12) ** 2) / (j11 + j22) ** 2
    p = abs(c[n0, ii, :]) ** 2; sfp = (p[:, 0] - p[:, 1]) / p.sum(1)
    return S, n0, q, sfp


def ang(U, V):
    return np.degrees(np.arccos(np.clip(np.sum(U * V, axis=1), -1, 1)))


def osc_rms(x, S, half=25):
    o = np.full(len(x), np.nan)
    for i in range(half, len(x) - half):
        sl = slice(i - half, i + half + 1); xx = x[sl] - x[i]
        res = np.array([S[sl, k] - np.polyval(np.polyfit(xx, S[sl, k], 2), xx) for k in range(3)])
        o[i] = np.degrees(np.sqrt(np.mean(np.sum(res ** 2, 0))))
    return o


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--repo-root', required=True); ap.add_argument('--bank-dir', required=True)
    ap.add_argument('--out', required=True); a = ap.parse_args()
    root = Path(a.repo_root); out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    ant = Antennas(root, a.bank_dir); R = {'banks': ant.receipts}
    man = json.loads((root / 'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
    # V0 LoS parity vs stored corpus H_LoS
    par = []
    rng = np.random.default_rng(20261030)
    for case in man['cases']:
        S_ = pd.DataFrame(json.loads((root / case['samples_path']).read_text()))
        pick = np.sort(rng.choice(len(S_), 64, replace=False))
        T = np.column_stack([S_.x.to_numpy()[pick], S_.y.to_numpy()[pick], np.full(64, case['robot_z_m'])])
        yaw = S_.yaw_body_deg.to_numpy()[pick] + case['mount_deg']
        Hm = channel(ant, np.asarray(case['anchor'], float), T, yaw, [])
        Hs = np.asarray(np.load(root / case['los_path'], mmap_mode='r')[pick, :, :, 0])     # (64, nf, 2)
        Hs = np.moveaxis(Hs, 0, 1)
        rel = np.linalg.norm(Hm - Hs, axis=(0, 2)) / np.linalg.norm(Hs, axis=(0, 2))
        Sm, _, _, sm = observe(Hm); Ss, _, _, ss = observe(Hs)
        par.append({'case': case['id'], 'rel_err_median': float(np.median(rel)), 'rel_err_max': float(rel.max()),
                    'state_angle_max_deg': float(ang(Sm, Ss).max()), 's_fp_absdiff_max': float(np.max(abs(sm - ss)))})
    pd.DataFrame(par).to_csv(out / 'V0_LOS_PARITY.csv', index=False); R['V0'] = par
    print(pd.DataFrame(par).round(6).to_string(index=False), flush=True)
    # experiment
    A = np.array([4.0, 0.0, 2.65]); xs = np.round(np.arange(4.2, 19.8001, 0.04), 4)
    T = np.column_stack([xs, np.full(len(xs), 0.3), np.full(len(xs), 0.45)]); rho = np.hypot(xs - A[0], 0.3)
    rows = []
    for mount in (0, 45):
        for yb in (0, 180):
            yaw = np.full(len(xs), float(yb + mount))
            S_los, n0_los, q_los, _ = observe(channel(ant, A, T, yaw, []))
            perr = {e: ang(observe(channel(ant, A, T, yaw + e, []))[0], S_los) for e in (1, 2, 5)}
            for sc, planes in SCEN.items():
                S, n0, q, sfp = (S_los, n0_los, q_los, None) if sc == 'LOS' else observe(channel(ant, A, T, yaw, planes))
                dev = ang(S, S_los); osc = osc_rms(xs, S)
                for i in range(len(xs)):
                    rows.append({'mount': mount, 'yaw_body': yb, 'scenario': sc, 'x': xs[i], 'rho': rho[i], 'n0': int(n0[i]),
                                 'q_W': float(q[i]), 'dev_true_deg': float(dev[i]), 'osc_rms_deg': float(osc[i]),
                                 'prior_err1_deg': float(perr[1][i]), 'prior_err2_deg': float(perr[2][i]), 'prior_err5_deg': float(perr[5][i])})
            print('done', mount, yb, flush=True)
    D = pd.DataFrame(rows); D.to_csv(out / 'CTRL_TRAJ_02_ROWS.csv.gz', index=False)
    D['rho_bin'] = pd.cut(D.rho, [0, 2, 4, 6, 9, 12, 16.1])
    S = D.groupby(['mount', 'yaw_body', 'scenario', 'rho_bin'], observed=True).agg(
        dev_true=('dev_true_deg', 'median'), osc=('osc_rms_deg', 'median'), q_W=('q_W', 'median'),
        prior_err1=('prior_err1_deg', 'median'), prior_err2=('prior_err2_deg', 'median'), prior_err5=('prior_err5_deg', 'median')).reset_index()
    S.to_csv(out / 'CTRL_TRAJ_02_SUMMARY.csv', index=False)
    R['script_sha256'] = sha(__file__); R['outputs'] = {p.name: sha(p) for p in out.iterdir()}
    (out / 'CTRL_TRAJ_02_MANIFEST.json').write_text(json.dumps(R, indent=1, default=str))
    pd.set_option('display.width', 220); print(S.round(3).to_string(index=False))


if __name__ == '__main__':
    main()
