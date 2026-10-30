#!/usr/bin/env python3
"""CTRL-TRAJ-06 — closed-loop EKF: does detecting the far-range ceiling (Dperp + P_psipsi gating) and dropping /
down-weighting the s observation improve heading and XY? (EXPLORATORY, label-free, controlled environment)

Filter: the repository's 4-state EKF [x, y, psi, b_g] — core.transition prediction with predict_one input noise
(r2_bias_replay), joint [r, s] Gaussian update with R0 (RR, RS) and chi2(2, .99) gate, s skipped in turns.
Motion inputs: r2_bias_replay.build_positive_bias_controls (sensor-v2 wheel/gyro noise streams, B0 / L2 gyro bias),
seeded per Monte-Carlo run; initial pose error drawn by the same generator.
Channel: CTRL-TRAJ-02 construction (sha-verified FFD banks, slab Fresnel, ceiling / floor / walls, 1 bounce).
  Route: y = 0.3, z = 0.45; outbound x 4.2 -> 19.8 (yaw 0), in-place 180 deg turn (10 s), return 19.8 -> 4.2 (yaw 180).
  Observation noise: complex white noise per frequency bin and port, propagated through Hann + 4x IFFT (exact
  7-tap covariance), level calibrated so that std(s_fp) in the far LoS region equals SIGMA_S (0.09 = sqrt(RS) and 0.03).
  Range: truth + N(0, RR) (no reflection bias on range in this experiment).
Filter's s model h_s and Stokes prediction: LoS-only model LUT (x, y, psi) built with the same antenna model.
Detector (causal, uses only prior estimate, its covariance and the current/past observations):
  d_k = S_obs,k - S_pred(prior_k); d_perp = d - (d.t)t with t = dS_pred/dpsi; Dperp = |mean over last 25 samples|;
  sigma_w = rms sqrt(P_psipsi prior) over the same samples; flag = Dperp > thr_D(leg, xhat bin) and sigma_w <= thr_sigma(leg).
  Thresholds: separate NULL (LoS-only) calibration Monte-Carlo seeds with BASE policy (NULL p95, coverage 0.82).
Policies: BASE, DROP_DPERP, INFL10_DPERP, DROP_DPERP_NOGATE, DROP_D0 (power-only detector, same gating),
          ORACLE_DROP (drop s where a reflection is truly present in the far region), R_ONLY (never use s).
Uncertainty: paired seeds across policies; bootstrap 95% CI over seeds for RMSE and paired delta vs BASE; heading and
  XY NEES / 95% coverage of the filter covariance; two noise levels, two gyro-bias levels, two mounts.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / 'research/EKF4_RANGE_S_STAGED_20261014'))
import core  # noqa: E402
import r2_bias_replay as RB  # noqa: E402
from p3_rf_adapter4 import RR, RS  # noqa: E402
spec = importlib.util.spec_from_file_location('c2', HERE.parent / 'CTRL_TRAJ_02' / 'ctrl_traj_02.py')
C2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(C2)

ANCHOR = np.array([4.0, 0.0, 2.65]); ZR = 0.45; YR = 0.3
G2 = 9.210340371976184; G1 = 6.6348966010212145; CHI1_95 = 3.841458820694124; CHI2_95 = 5.991464547107979
SCEN = ['NULL', 'LOS+C', 'ALL']
POL = ['BASE', 'DROP_DPERP', 'INFL10_DPERP', 'DROP_DPERP_NOGATE', 'DROP_D0', 'ORACLE_DROP', 'R_ONLY']
WIN = 25; COVER = 0.82; FPR = 0.05
wrap = core.wrap


# ---------------------------------------------------------------- route / channel features
def route():
    xo = np.round(np.arange(4.2, 19.8001, 0.04), 4)
    P = [(x, YR, 0.0) for x in xo]
    P += [(19.8, YR, i * math.pi / 50) for i in range(1, 51)]
    P += [(x, YR, math.pi) for x in np.round(np.arange(19.76, 4.1999, -0.04), 4)]
    P = np.array(P); t = np.arange(len(P)) * 0.2
    leg = np.r_[np.zeros(len(xo), int), np.full(50, 2), np.ones(len(P) - len(xo) - 50, int)]
    leg[len(xo) + 49] = 1                                 # last turn sample is already at yaw 180 and stationary
    return t, P, leg


NF = 257
HANN = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(NF) / (NF - 1))


def taps(H):
    """H (nf, n, 2) -> FP window taps (n, 7, 2) exactly as C2.observe."""
    c = np.fft.ifft(H * HANN[:, None, None], n=4 * NF, axis=0) * NF
    a = np.abs(c); n = H.shape[1]; ii = np.arange(n)
    br = np.argmax(a.max(axis=0), axis=1); s = a[:, ii, br]
    n0 = np.argmax(s >= 0.3 * s.max(axis=0)[None, :], axis=0)
    W = c[n0[None, :] + np.arange(-2, 5)[:, None], ii[None, :], :]
    return np.moveaxis(W, 0, 1)


def feats(W):
    """W (..., 7, 2) -> unit Stokes (..., 3), s_fp (...)."""
    j11 = np.sum(abs(W[..., 0]) ** 2, -1); j22 = np.sum(abs(W[..., 1]) ** 2, -1); j12 = np.sum(W[..., 0] * np.conj(W[..., 1]), -1)
    S = np.stack([j11 - j22, 2 * j12.real, -2 * j12.imag], -1); S = S / np.linalg.norm(S, axis=-1, keepdims=True)
    p = abs(W[..., 2, :]) ** 2
    return S, (p[..., 0] - p[..., 1]) / p.sum(-1)


def noise_chol():
    k = np.arange(7); m = k[:, None] - k[None, :]
    f = np.arange(NF)
    Sig = np.einsum('f,mnf->mn', HANN ** 2, np.exp(2j * np.pi * f[None, None, :] * m[:, :, None] / (4 * NF))) / 16.0
    return np.linalg.cholesky(Sig)


def channel_feats(ant, xyz, yaw_deg, planes, chunk=1500):
    out = []
    for i in range(0, len(xyz), chunk):
        out.append(taps(C2.channel(ant, ANCHOR, xyz[i:i + chunk], yaw_deg[i:i + chunk], planes)))
    return np.concatenate(out)


# ---------------------------------------------------------------- LUT for the filter's LoS model
class Lut:
    def __init__(self, ant, mount, psi0):
        self.gx = np.round(np.arange(3.8, 20.2001, 0.08), 4); self.gy = np.round(np.arange(-0.3, 0.9001, 0.15), 4)
        self.gp = np.radians(np.arange(-20, 20.0001, 0.5)); self.psi0 = psi0
        X, Y, Pp = np.meshgrid(self.gx, self.gy, self.gp, indexing='ij')
        xyz = np.column_stack([X.ravel(), Y.ravel(), np.full(X.size, ZR)])
        S, sf = feats(channel_feats(ant, xyz, np.degrees(psi0 + Pp.ravel()) + mount, []))
        V = np.concatenate([sf[:, None], S], 1).reshape(X.shape + (4,))
        dx, dy, dp = np.gradient(V, self.gx, self.gy, self.gp, axis=(0, 1, 2))
        self.F = np.concatenate([V, dx, dy, dp], -1)            # (nx, ny, np, 16)

    def __call__(self, x, y, psi):
        dpsi = wrap(psi - self.psi0); out = 0
        q = []
        for v, g in ((x, self.gx), (y, self.gy), (dpsi, self.gp)):
            vc = np.clip(v, g[0], g[-1]); i = np.clip(np.searchsorted(g, vc) - 1, 0, len(g) - 2)
            q.append((i, (vc - g[i]) / (g[i + 1] - g[i])))
            out = out + (np.abs(v - vc) > 1e-12)
        (i, wx), (j, wy), (k, wp) = q; r = 0
        for a in (0, 1):
            for b in (0, 1):
                for c in (0, 1):
                    w = (wx if a else 1 - wx) * (wy if b else 1 - wy) * (wp if c else 1 - wp)
                    r = r + w[:, None] * self.F[i + a, j + b, k + c]
        return r, out > 0


# ---------------------------------------------------------------- vectorised EKF (validated against core)
def sinc_half_v(a):
    h = a / 2; small = abs(a) < 1e-4; a2 = a * a
    hs = np.where(small, 1.0, h)
    c = np.where(small, 1 - a2 / 24 + a2 * a2 / 1920 - a2 ** 3 / 322560, np.sin(hs) / hs)
    dc = np.where(small, -a / 12 + a ** 3 / 480 - a ** 5 / 53760, (hs * np.cos(hs) - np.sin(hs)) / (2 * hs * hs))
    return c, dc


def predict_v(X, P, ds, g, dt):
    n = len(X); a = g - X[:, 3] * dt; c, dc = sinc_half_v(a); phi = X[:, 2] + a / 2
    u = np.stack([np.cos(phi), np.sin(phi)], 1); up = np.stack([-u[:, 1], u[:, 0]], 1)
    d = (ds * c)[:, None] * u; v = ds[:, None] * (dc[:, None] * u + c[:, None] * up / 2)
    Y = X.copy(); Y[:, :2] += d; Y[:, 2] = wrap(X[:, 2] + a)
    F = np.tile(np.eye(4), (n, 1, 1)); F[:, 0, 2] = -d[:, 1]; F[:, 1, 2] = d[:, 0]
    F[:, :2, 3] = -dt[:, None] * v; F[:, 2, 3] = -dt
    G = np.zeros((n, 4, 3)); G[:, :2, 0] = c[:, None] * u; G[:, :2, 1] = v; G[:, 2, 1] = 1.; G[:, 3, 2] = 1.
    Q = np.zeros((n, 3, 3)); Q[:, 0, 0] = 2e-5 * abs(ds); Q[:, 1, 1] = math.radians(.015) ** 2 * dt
    P2 = F @ P @ np.swapaxes(F, 1, 2) + G @ Q @ np.swapaxes(G, 1, 2)
    return Y, (P2 + np.swapaxes(P2, 1, 2)) / 2


def update_v(X, P, v, H, R, thr):
    S = H @ P @ np.swapaxes(H, 1, 2) + R; S = (S + np.swapaxes(S, 1, 2)) / 2
    K = np.swapaxes(np.linalg.solve(S, H @ P), 1, 2)
    nis = np.einsum('ni,ni->n', v, np.linalg.solve(S, v[..., None])[..., 0]); ok = nis <= thr
    Xn = X + np.einsum('nij,nj->ni', K, v); Xn[:, 2] = wrap(Xn[:, 2])
    A = np.eye(4)[None] - K @ H; Pn = A @ P @ np.swapaxes(A, 1, 2) + K @ R @ np.swapaxes(K, 1, 2); Pn = (Pn + np.swapaxes(Pn, 1, 2)) / 2
    return np.where(ok[:, None], Xn, X), np.where(ok[:, None, None], Pn, P), ok


# ---------------------------------------------------------------- one closed-loop batch
def run_batch(cfg, seeds, scen_of_run, pol_of_run, thr, collect=False):
    """cfg: dict with t, P(truth), leg, luts, obsW[scen] (n,7,2), sigma_n, L, ctrl[seed], x0[seed], R_s, bias_rad."""
    t, Ptru, leg = cfg['t'], cfg['P'], cfg['leg']; n = len(t); R_ = len(seeds)
    ctrl = cfg['ctrl']; ds = np.stack([ctrl[s]['ds_odom'] for s in seeds]); gy = np.stack([ctrl[s]['dtheta_gyro'] for s in seeds])
    dtt = np.stack([ctrl[s]['dt_s'] for s in seeds])
    X = np.stack([np.r_[cfg['x0'][s], 0.] for s in seeds]); P = np.tile(np.diag(np.r_[RB.INITIAL_POSE_STD ** 2, RB.BIAS_PRIOR_STD ** 2]), (R_, 1, 1))
    # measurements (identical across policies / scenarios for the same seed)
    zr = np.stack([cfg['rnoise'][s] for s in seeds]) + np.sqrt((Ptru[:, 0] - ANCHOR[0]) ** 2 + (Ptru[:, 1] - ANCHOR[1]) ** 2 + (ANCHOR[2] - ZR) ** 2)[None]
    rho = np.hypot(Ptru[:, 0] - ANCHOR[0], Ptru[:, 1] - ANCHOR[1]); far = (rho > 6.0) & (leg != 2)
    obs_stack = np.stack([cfg['obsW'][sc] for sc in SCEN]); sidx = np.array([SCEN.index(sc) for sc in scen_of_run])
    useeds = sorted(set(seeds)); spos = np.array([useeds.index(s) for s in seeds])
    noise_stack = np.stack([cfg['tapnoise'][s] for s in useeds]); is_refl = sidx != 0
    add_stack = np.stack([cfg['addnoise'][s] for s in useeds])
    buf_d = np.zeros((R_, WIN, 3)); buf_s = np.zeros((R_, WIN)); buf_sg = np.zeros((R_, WIN)); cnt = np.zeros(R_, int); last_leg = -1
    E = np.zeros((n, R_, 3)); PS = np.zeros((n, R_)); NX = np.zeros((n, R_)); FL = np.zeros((n, R_), bool); SU = np.zeros((n, R_), bool)
    ACC = np.zeros((n, R_), bool); OOR = np.zeros((n, R_), bool); CAL = []
    for k in range(n):
        if k:
            X, P = predict_v(X, P, ds[:, k], gy[:, k], dtt[:, k])
        if leg[k] != last_leg:
            cnt[:] = 0; last_leg = leg[k]
        h_r = np.sqrt((X[:, 0] - ANCHOR[0]) ** 2 + (X[:, 1] - ANCHOR[1]) ** 2 + (ANCHOR[2] - ZR) ** 2)
        Hr = np.zeros((R_, 4)); Hr[:, 0] = (X[:, 0] - ANCHOR[0]) / h_r; Hr[:, 1] = (X[:, 1] - ANCHOR[1]) / h_r
        flag = np.zeros(R_, bool); use_s = np.zeros(R_, bool); infl = np.ones(R_)
        if leg[k] != 2:
            lut = cfg['luts'][leg[k]]; F, oor = lut(X[:, 0], X[:, 1], X[:, 2]); OOR[k] = oor
            if cfg.get('exact'):
                Se, se = feats(taps(C2.channel(cfg['ant'], ANCHOR, np.column_stack([X[:, :2], np.full(R_, ZR)]), np.degrees(X[:, 2]) + cfg['mount'], [])))
                F = F.copy(); F[:, 0] = se; F[:, 1:4] = Se
            hs = F[:, 0]; Sp = F[:, 1:4] / np.linalg.norm(F[:, 1:4], axis=1, keepdims=True); tv = F[:, 13:16]
            tv = tv / np.maximum(np.linalg.norm(tv, axis=1, keepdims=True), 1e-12)
            Hs = np.c_[F[:, 4], F[:, 8], F[:, 12], np.zeros(R_)]
            if cfg.get('noise_mode', 'taps') == 'taps':
                So, so = feats(obs_stack[sidx, k] + cfg['sigma_n'] * noise_stack[spos, k])
            else:
                Sc, sc_ = feats(obs_stack[sidx, k]); an = add_stack[spos, k]
                so = sc_ + cfg['R_s'] ** 0.5 * an[:, 0]; So = Sc + cfg['sigS'] * an[:, 1:4]; So = So / np.linalg.norm(So, axis=1, keepdims=True)
            d = So - Sp; dp = d - np.sum(d * tv, 1, keepdims=True) * tv
            buf_d = np.roll(buf_d, -1, 1); buf_s = np.roll(buf_s, -1, 1); buf_sg = np.roll(buf_sg, -1, 1)
            buf_d[:, -1] = dp; buf_s[:, -1] = so - hs; buf_sg[:, -1] = np.degrees(np.sqrt(P[:, 2, 2])); cnt += 1
            valid = cnt >= WIN
            Dp = np.degrees(np.linalg.norm(buf_d.mean(1), axis=1)); D0 = abs(buf_s.mean(1)); sw = np.sqrt(np.mean(buf_sg ** 2, 1))
            xb = np.clip(((X[:, 0] - 4.0) // 2).astype(int), 0, 7)
            if collect:
                CAL.append(pd.DataFrame({'leg': leg[k], 'xbin': xb[valid], 'Dperp': Dp[valid], 'D0': D0[valid], 'sigma_w': sw[valid]}))
            if thr is not None:
                tg = sw <= thr['sigma'][leg[k]]
                fl_p = valid & tg & (Dp > thr['Dperp'][leg[k]][xb]); fl_ng = valid & (Dp > thr['Dperp_ng'][leg[k]][xb])
                fl_0 = valid & tg & (D0 > thr['D0'][leg[k]][xb])
                orc = is_refl & far[k]
                for name, f_ in (('DROP_DPERP', fl_p), ('INFL10_DPERP', fl_p), ('DROP_DPERP_NOGATE', fl_ng), ('DROP_D0', fl_0), ('ORACLE_DROP', orc)):
                    m = pol_of_run == name; flag[m] = f_[m]
                flag[pol_of_run == 'R_ONLY'] = True
            use_s = ~flag | (pol_of_run == 'INFL10_DPERP')
            infl = np.where(flag & (pol_of_run == 'INFL10_DPERP'), 10.0, 1.0)
        else:
            so = np.zeros(R_); hs = np.zeros(R_); Hs = np.zeros((R_, 4))
        v = np.c_[zr[:, k] - h_r, np.where(use_s, so - hs, 0.)]
        H = np.stack([Hr, np.where(use_s[:, None], Hs, 0.)], 1)
        Rm = np.zeros((R_, 2, 2)); Rm[:, 0, 0] = RR; Rm[:, 1, 1] = np.where(use_s, cfg['R_s'] * infl, 1e12)
        X, P, ok = update_v(X, P, v, H, Rm, np.where(use_s, G2, G1))
        e = X[:, :3] - Ptru[k][None]; e[:, 2] = wrap(e[:, 2]); E[k] = e; PS[k] = P[:, 2, 2]
        NX[k] = np.einsum('ni,ni->n', e[:, :2], np.linalg.solve(P[:, :2, :2], e[:, :2][..., None])[..., 0])
        FL[k] = flag; SU[k] = use_s & (leg[k] != 2); ACC[k] = ok
    return dict(E=E, PS=PS, NX=NX, FL=FL, SU=SU, ACC=ACC, OOR=OOR, far=far, cal=pd.concat(CAL) if CAL else None)


def boot_ci(x, B=2000, rng=None, f=np.mean):
    rng = rng or np.random.default_rng(0); idx = rng.integers(0, len(x), (B, len(x)))
    v = f(x[idx], axis=1); return float(np.quantile(v, .025)), float(np.quantile(v, .975))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--bank-dir', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--n-eval', type=int, default=100); ap.add_argument('--n-cal', type=int, default=50)
    ap.add_argument('--mounts', default='0,45'); ap.add_argument('--sigmas', default='0.09,0.03'); ap.add_argument('--biases', default='B0,L2')
    ap.add_argument('--hs-exact', action='store_true', help='exact LoS-model value/Stokes at the estimate (LUT only for Jacobians)')
    ap.add_argument('--noise-mode', choices=['taps', 'additive'], default='taps')
    ap.add_argument('--scens', default=','.join(SCEN)); ap.add_argument('--policies', default=','.join(POL))
    ap.add_argument('--quick', action='store_true'); a = ap.parse_args()
    scens_run = a.scens.split(','); pols_run = a.policies.split(',')
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    ant = C2.Antennas(REPO, a.bank_dir); t, Ptru, leg = route(); n = len(t); QA = {}
    xyz = np.column_stack([Ptru[:, :2], np.full(n, ZR)])
    # QA: taps/feats parity with C2.observe
    Hq = C2.channel(ant, ANCHOR, xyz[::40], np.degrees(Ptru[::40, 2]), C2.SCEN['ALL']); Sq, _, _, sq = C2.observe(Hq); Sf, sf = feats(taps(Hq))
    QA['observe_parity'] = {'S_max': float(abs(Sq - Sf).max()), 's_max': float(abs(sq - sf).max())}
    # QA: vectorised prediction vs core.predict
    rng = np.random.default_rng(5); Xr = np.c_[rng.normal(10, 3, 20), rng.normal(0, 1, 20), rng.uniform(-3, 3, 20), rng.normal(0, 1e-3, 20)]
    Pr = np.stack([np.diag(rng.uniform(1e-4, 1e-2, 4)) for _ in range(20)]); dsr = rng.uniform(-0.05, 0.05, 20); gr = rng.normal(0, 0.05, 20); dtr = np.full(20, 0.2)
    Yv, Pv = predict_v(Xr, Pr, dsr, gr, dtr); md = 0
    for i in range(20):
        y, p = RB.predict_one(Xr[i], Pr[i], dsr[i], gr[i], dtr[i]); md = max(md, float(abs(wrap(y - Yv[i])).max()), float(abs(p - Pv[i]).max()))
    QA['predict_parity_max'] = md; assert md < 1e-12, md
    L = noise_chol(); mounts = tuple(int(v) for v in a.mounts.split(',')); biases = tuple(a.biases.split(',')); sig_list = tuple(float(v) for v in a.sigmas.split(','))
    if a.quick: mounts, biases, sig_list = mounts[:1], biases[:1], sig_list[:1]
    seeds_eval = list(range(a.n_eval)); seeds_cal = list(range(10000, 10000 + a.n_cal)); allseeds = seeds_eval + seeds_cal
    rows, ts_rows, thr_dump = [], [], {}
    for mount in mounts:
        luts = {0: Lut(ant, mount, 0.0), 1: Lut(ant, mount, math.pi)}
        obsW = {sc: channel_feats(ant, xyz, np.degrees(Ptru[:, 2]) + mount, C2.SCEN['LOS' if sc == 'NULL' else sc]) for sc in SCEN}
        # QA: LUT vs direct LoS model at truth (+ random offsets)
        off = np.c_[rng.normal(0, 0.15, n), rng.normal(0, 0.15, n), np.radians(rng.normal(0, 4, n))]; ok_ = leg != 2
        xyz2 = np.column_stack([Ptru[:, :2] + off[:, :2], np.full(n, ZR)]); yaw2 = Ptru[:, 2] + off[:, 2]
        Sd, sd = feats(channel_feats(ant, xyz2[ok_], np.degrees(yaw2[ok_]) + mount, []))
        Fi = np.concatenate([luts[l](xyz2[ok_][leg[ok_] == l, 0], xyz2[ok_][leg[ok_] == l, 1], yaw2[ok_][leg[ok_] == l])[0] for l in (0, 1)])
        Sd = np.concatenate([Sd[leg[ok_] == l] for l in (0, 1)]); sd = np.concatenate([sd[leg[ok_] == l] for l in (0, 1)])
        Si = Fi[:, 1:4] / np.linalg.norm(Fi[:, 1:4], axis=1, keepdims=True)
        QA[f'lut_m{mount}'] = {'s_abs_p95': float(np.quantile(abs(Fi[:, 0] - sd), .95)), 's_abs_max': float(abs(Fi[:, 0] - sd).max()),
                               'S_deg_p95': float(np.quantile(C2.ang(Si, Sd), .95)), 'S_deg_max': float(C2.ang(Si, Sd).max())}
        for sig in sig_list:
            # noise level calibration: std(s_fp) in far LoS outbound region = sig
            rr = np.random.default_rng(99); fr = np.where((leg == 0) & (np.hypot(Ptru[:, 0] - 4, 0.3) > 6))[0]
            w0 = (rr.standard_normal((400, len(fr), 2, 7)) + 1j * rr.standard_normal((400, len(fr), 2, 7))) / np.sqrt(2)
            Z = np.swapaxes(np.einsum('ij,...pj->...pi', L, w0), -1, -2)                      # (400, nfr, 7, 2)
            def sd_of(sn):
                return float(np.median(np.std(feats(obsW['NULL'][fr][None] + sn * Z)[1], axis=0)))
            lo, hi = 1e-10, 1e3
            for _ in range(60):
                mid = math.sqrt(lo * hi); lo, hi = (mid, hi) if sd_of(mid) < sig else (lo, mid)
            sigma_n = math.sqrt(lo * hi)
            Sn, sn = feats(obsW['NULL'][fr][None] + sigma_n * Z); s0 = feats(obsW['NULL'][fr])[1]
            sigS = float(np.median(np.std(Sn, axis=0)))
            QA[f'noise_m{mount}_s{sig}'] = {'sigma_n': sigma_n, 'achieved_std_s_far': sd_of(sigma_n), 'stokes_comp_std_far': sigS,
                                            'noise_bias_s_far_median': float(np.median(sn.mean(0) - s0)), 'noise_bias_s_far_absmax': float(np.max(abs(sn.mean(0) - s0))),
                                            'noise_bias_over_dsdpsi_deg_median': None}
            # per-seed measurement noise (same across scenarios / policies)
            rnoise, tapnoise, addnoise = {}, {}, {}
            for s in allseeds:
                g = np.random.default_rng([s, 77, int(sig * 1000)])
                rnoise[s] = g.normal(0, math.sqrt(RR), n)
                w = (g.standard_normal((n, 2, 7)) + 1j * g.standard_normal((n, 2, 7))) / np.sqrt(2)
                tapnoise[s] = np.einsum('ij,npj->npi', L, w).transpose(0, 2, 1)
                addnoise[s] = np.random.default_rng([s, 78, int(sig * 1000)]).standard_normal((n, 4))
            for bias in biases:
                ctrl, x0 = {}, {}
                for s in allseeds:
                    c, x = RB.build_positive_bias_controls(t, Ptru, bias, seed=s); ctrl[s] = c; x0[s] = x
                cfg = dict(t=t, P=Ptru, leg=leg, luts=luts, obsW=obsW, sigma_n=sigma_n, ctrl=ctrl, x0=x0, rnoise=rnoise, tapnoise=tapnoise,
                           addnoise=addnoise, sigS=sigS, R_s=sig ** 2, exact=a.hs_exact, noise_mode=a.noise_mode, ant=ant, mount=mount)
                # calibration (NULL, BASE)
                cr = run_batch(cfg, seeds_cal, ['NULL'] * len(seeds_cal), np.array(['BASE'] * len(seeds_cal)), None, collect=True)['cal']
                thr = {'sigma': {}, 'Dperp': {}, 'Dperp_ng': {}, 'D0': {}}
                for l in (0, 1):
                    c_ = cr[cr.leg == l]; thr['sigma'][l] = float(np.quantile(c_.sigma_w, COVER)); kept = c_[c_.sigma_w <= thr['sigma'][l]]
                    for key, src, col in (('Dperp', kept, 'Dperp'), ('Dperp_ng', c_, 'Dperp'), ('D0', kept, 'D0')):
                        q = src.groupby('xbin')[col].quantile(1 - FPR).reindex(range(8))
                        thr[key][l] = q.fillna(q.max()).to_numpy()
                thr_dump[f'm{mount}_s{sig}_{bias}'] = {k: {str(l): (v.tolist() if hasattr(v, 'tolist') else v) for l, v in d.items()} for k, d in thr.items()}
                # evaluation
                runs = [(sc, p, s) for sc in scens_run for p in pols_run for s in seeds_eval]
                res = run_batch(cfg, [r[2] for r in runs], [r[0] for r in runs], np.array([r[1] for r in runs]), thr)
                T30 = t >= 30; FAR = res['far'] & T30
                for i, (sc, p, s) in enumerate(runs):
                    e = res['E'][:, i]; ps = res['PS'][:, i]
                    row = dict(sigma_s=sig, bias=bias, mount=mount, scen=sc, policy=p, seed=s)
                    for rn, m in (('far', FAR), ('t30', T30)):
                        row[f'mse_psi_{rn}'] = float(np.mean(e[m, 2] ** 2)); row[f'mse_xy_{rn}'] = float(np.mean(np.sum(e[m, :2] ** 2, 1)))
                        row[f'bias_psi_{rn}'] = float(np.degrees(np.mean(e[m, 2])))
                        row[f'nees_psi_{rn}'] = float(np.mean(e[m, 2] ** 2 / ps[m])); row[f'cov95_psi_{rn}'] = float(np.mean(e[m, 2] ** 2 / ps[m] <= CHI1_95))
                        row[f'nees_xy_{rn}'] = float(np.mean(res['NX'][m, i])); row[f'cov95_xy_{rn}'] = float(np.mean(res['NX'][m, i] <= CHI2_95))
                        row[f'sigma_psi_{rn}'] = float(np.degrees(np.sqrt(ps[m])).mean())
                    row['flag_far'] = float(res['FL'][FAR, i].mean()); row['s_used_far'] = float(res['SU'][FAR, i].mean())
                    row['accept_t30'] = float(res['ACC'][T30, i].mean()); row['lut_oor'] = float(res['OOR'][T30, i].mean())
                    rows.append(row)
                for sc in scens_run:
                    for p in pols_run:
                        idx = [i for i, r in enumerate(runs) if r[0] == sc and r[1] == p]
                        e = res['E'][:, idx, 2]
                        ts_rows.append(pd.DataFrame({'sigma_s': sig, 'bias': bias, 'mount': mount, 'scen': sc, 'policy': p, 'k': np.arange(n), 't': t,
                                                     'x_true': Ptru[:, 0], 'leg': leg, 'mean_err_deg': np.degrees(e.mean(1)), 'rms_err_deg': np.degrees(np.sqrt((e ** 2).mean(1))),
                                                     'flag_rate': res['FL'][:, idx].mean(1)}))
                print('done', mount, sig, bias, flush=True)
    D = pd.DataFrame(rows); D.to_csv(out / 'CTRL_TRAJ_06_RUNS.csv.gz', index=False)
    pd.concat(ts_rows).to_csv(out / 'CTRL_TRAJ_06_TIMESERIES.csv.gz', index=False)
    # aggregate with bootstrap CIs (paired vs BASE)
    agg = []; rng = np.random.default_rng(2026)
    for keys, g in D.groupby(['sigma_s', 'bias', 'mount', 'scen']):
        base = g[g.policy == 'BASE'].sort_values('seed')
        for p, gp in g.groupby('policy'):
            gp = gp.sort_values('seed'); assert (gp.seed.to_numpy() == base.seed.to_numpy()).all()
            r = dict(zip(['sigma_s', 'bias', 'mount', 'scen'], keys), policy=p, n_seeds=len(gp))
            for rn in ('far', 't30'):
                for q, unit in (('psi', 'deg'), ('xy', 'm')):
                    m = gp[f'mse_{q}_{rn}'].to_numpy(); mb = base[f'mse_{q}_{rn}'].to_numpy(); sc_ = (180 / math.pi) if q == 'psi' else 1.0
                    rm = math.sqrt(m.mean()) * sc_; lo, hi = boot_ci(m, rng=rng)
                    r[f'rmse_{q}_{rn}'] = rm; r[f'rmse_{q}_{rn}_lo'] = math.sqrt(lo) * sc_; r[f'rmse_{q}_{rn}_hi'] = math.sqrt(hi) * sc_
                    idx = rng.integers(0, len(m), (2000, len(m)))
                    dl = (np.sqrt(m[idx].mean(1)) - np.sqrt(mb[idx].mean(1))) * sc_
                    r[f'd_{q}_{rn}'] = rm - math.sqrt(mb.mean()) * sc_; r[f'd_{q}_{rn}_lo'] = float(np.quantile(dl, .025)); r[f'd_{q}_{rn}_hi'] = float(np.quantile(dl, .975))
                    r[f'p_improve_{q}_{rn}'] = float(np.mean(dl < 0))
                for c in ('bias_psi', 'nees_psi', 'cov95_psi', 'nees_xy', 'cov95_xy', 'sigma_psi'):
                    r[f'{c}_{rn}'] = float(gp[f'{c}_{rn}'].mean())
            for c in ('flag_far', 's_used_far', 'accept_t30', 'lut_oor'):
                r[c] = float(gp[c].mean())
            agg.append(r)
    A = pd.DataFrame(agg); A.to_csv(out / 'CTRL_TRAJ_06_SUMMARY.csv', index=False)
    (out / 'CTRL_TRAJ_06_THRESHOLDS.json').write_text(json.dumps(thr_dump, indent=1)); (out / 'CTRL_TRAJ_06_QA.json').write_text(json.dumps(QA, indent=1))
    meta = {'status': 'EXPLORATORY', 'hs_exact': a.hs_exact, 'noise_mode': a.noise_mode, 'scens': scens_run, 'policies': pols_run, 'mounts': mounts, 'sigmas': sig_list, 'biases': biases, 'n_eval': a.n_eval, 'n_cal': a.n_cal, 'banks': ant.receipts, 'RR': RR, 'RS': RS,
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    meta['outputs'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
    (out / 'CTRL_TRAJ_06_MANIFEST.json').write_text(json.dumps(meta, indent=1))
    pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500); pd.set_option('display.max_columns', 40)
    print(json.dumps(QA, indent=1))
    cols = ['sigma_s', 'bias', 'mount', 'scen', 'policy', 'rmse_psi_far', 'd_psi_far', 'd_psi_far_lo', 'd_psi_far_hi', 'rmse_xy_far', 'd_xy_far', 'd_xy_far_lo', 'd_xy_far_hi',
            'bias_psi_far', 'nees_psi_far', 'cov95_psi_far', 'nees_xy_far', 'cov95_xy_far', 'flag_far', 's_used_far']
    print(A[cols].round(3).to_string(index=False))


if __name__ == '__main__':
    main()
