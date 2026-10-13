"""Pure consistency-diagnostic functions for the DR (RF-off) EKF diagnosis.

No filter or generator imports: every function maps arrays to arrays so it can be unit-tested
(tests/test_dr_consistency_diagnostics.py). Conventions: error e = truth - estimate, heading
component index 2 already wrapped; covariances are the filter's own (no projection/repair).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import chi2

POSE = slice(0, 3)
DRIVE_STRAIGHT_YAW_RATE_RAD_S = math.radians(0.5)  # drive samples below this |yaw rate| are "straightish"


def wrap(a):
    return (np.asarray(a, float) + np.pi) % (2 * np.pi) - np.pi


# ----------------------------------------------------------------------------- per-run, per-time NEES family
def nees(e, P):
    """e (..., d), P (..., d, d) -> e^T P^-1 e (...). NaN where P is not positive definite."""
    e = np.asarray(e, float)
    P = np.asarray(P, float)
    out = np.full(e.shape[:-1], np.nan)
    ok = np.linalg.eigvalsh(P).min(axis=-1) > 0
    if np.any(ok):
        sol = np.linalg.solve(P[ok], e[ok][..., None])[..., 0]
        out[ok] = np.einsum('...i,...i->...', e[ok], sol)
    return out


def heading_conditional_split(e3, P3):
    """Split pose NEES into heading and heading-conditional XY parts (Schur complement).

    NEES_pose = e_psi^2/P_psipsi + e~^T P_xy|psi^-1 e~,  e~ = e_xy - P_xy,psi/P_psipsi * e_psi.
    Returns dict(heading, cond_xy, e_tilde (...,2), P_cond (...,2,2)). Expectations 1 and 2 when consistent.
    """
    e3 = np.asarray(e3, float)
    P3 = np.asarray(P3, float)
    ppsi = P3[..., 2, 2]
    cross = P3[..., :2, 2]
    gain = cross / ppsi[..., None]
    e_tilde = e3[..., :2] - gain * e3[..., 2:3]
    P_cond = P3[..., :2, :2] - cross[..., :, None] * cross[..., None, :] / ppsi[..., None, None]
    return dict(heading=e3[..., 2] ** 2 / ppsi, cond_xy=nees(e_tilde, P_cond), e_tilde=e_tilde, P_cond=P_cond)


def rotation_to_path(psi):
    """2x2 rotations mapping world XY to (longitudinal, lateral) of a path heading psi (...)."""
    c, s = np.cos(psi), np.sin(psi)
    R = np.empty(np.shape(psi) + (2, 2))
    R[..., 0, 0], R[..., 0, 1], R[..., 1, 0], R[..., 1, 1] = c, s, -s, c
    return R


def long_lat_z2(e_xy, P_xy, psi):
    """Squared marginal z of longitudinal/lateral error in the path frame of heading psi. Returns (..., 2)."""
    R = rotation_to_path(psi)
    e_ll = np.einsum('...ij,...j->...i', R, e_xy)
    P_ll = np.einsum('...ij,...jk,...lk->...il', R, P_xy, R)
    return e_ll ** 2 / np.stack([P_ll[..., 0, 0], P_ll[..., 1, 1]], axis=-1)


def per_run_diagnostics(E6, P6, psi_path):
    """All per-time scalar diagnostics of one run. E6 (n,6), P6 (n,6,6), psi_path (n,) true heading."""
    e3, P3 = E6[:, POSE], P6[:, POSE, POSE]
    split = heading_conditional_split(e3, P3)
    zll = long_lat_z2(e3[:, :2], P3[:, :2, :2], psi_path)
    zll_c = long_lat_z2(split['e_tilde'], split['P_cond'], psi_path)
    return dict(
        nees_pose=nees(e3, P3),
        nees_heading=split['heading'],
        nees_cond_xy=split['cond_xy'],
        nees_xy=nees(e3[:, :2], P3[:, :2, :2]),
        nees_cal=nees(E6[:, 3:], P6[:, 3:, 3:]),
        nees_full=nees(E6, P6),
        z2_long=zll[:, 0], z2_lat=zll[:, 1], z2_long_cond=zll_c[:, 0], z2_lat_cond=zll_c[:, 1],
        sigma_psi=np.sqrt(P3[:, 2, 2]),
        cond_xy_min_sigma=np.sqrt(np.linalg.eigvalsh(split['P_cond'])[:, 0].clip(min=0)),
    )


# ----------------------------------------------------------------------------- ensemble statistics
def anees_band(n_runs, dof=3, level=0.95):
    """Per-time ensemble ANEES two-sided band, chi2(dof*N)/N (independent runs, exact Gaussian assumption)."""
    lo, hi = chi2.ppf([(1 - level) / 2, 1 - (1 - level) / 2], dof * n_runs) / n_runs
    return float(lo), float(hi)


def sym_inv_sqrt(P):
    w, V = np.linalg.eigh(P)
    return (V / np.sqrt(w)[..., None, :]) @ np.swapaxes(V, -1, -2)


def sym_sqrt(P):
    w, V = np.linalg.eigh(P)
    return (V * np.sqrt(w.clip(min=0))[..., None, :]) @ np.swapaxes(V, -1, -2)


def mse_vs_predicted(sum_e, sum_ee, sum_P, n_runs):
    """From ensemble sums at each time: ebar, M=mean e e^T, Pbar=mean P, Cov=M-ebar ebar^T and
    whitened ratios W = Pbar^-1/2 M Pbar^-1/2 (unit-free; eigenvalue 1 = matched along that direction).

    bias_term = ebar^T Pbar^-1 ebar, var_term = tr(Pbar^-1 Cov); bias_term+var_term = tr(Pbar^-1 M).
    """
    ebar = sum_e / n_runs
    M = sum_ee / n_runs
    Pbar = sum_P / n_runs
    Cov = M - ebar[..., :, None] * ebar[..., None, :]
    Wi = sym_inv_sqrt(Pbar)
    W = Wi @ M @ Wi
    lam, V = np.linalg.eigh(W)
    lam, V = lam[..., ::-1], V[..., ::-1]
    bias = np.einsum('...i,...i->...', ebar, np.linalg.solve(Pbar, ebar[..., None])[..., 0])
    var = np.trace(np.linalg.solve(Pbar, Cov), axis1=-2, axis2=-1)
    # physical direction of the most over-confident whitened axis: d = Pbar^1/2 v, scaled by sqrt(diag Pbar)
    d = (sym_sqrt(Pbar) @ V[..., :, :1])[..., 0]
    d_scaled = d / np.sqrt(np.diagonal(Pbar, axis1=-2, axis2=-1))
    d_scaled /= np.linalg.norm(d_scaled, axis=-1, keepdims=True)
    return dict(ebar=ebar, M=M, Pbar=Pbar, Cov=Cov, whitened_eig=lam, top_dir_scaled=d_scaled,
                bias_term=bias, var_term=var)


def first_persistent_exceedance(series, t, upper, min_duration_s=5.0):
    """First time the series stays above `upper` for at least min_duration_s (inclusive samples). NaN if never."""
    above = np.asarray(series) > upper
    t = np.asarray(t, float)
    start = None
    for k, a in enumerate(above):
        if a and start is None:
            start = k
        if not a:
            start = None
        if start is not None and t[k] - t[start] >= min_duration_s:
            return float(t[start]), int(start)
    return float('nan'), -1


# ----------------------------------------------------------------------------- motion phase labels
def motion_phase(ds, dtheta, dt):
    """'stop' (no motion), 'spin' (in-place rotation), 'drive_straight' / 'drive_curve' by |yaw rate|."""
    ds, dtheta, dt = (np.asarray(x, float) for x in (ds, dtheta, dt))
    rate = np.divide(np.abs(dtheta), dt, out=np.zeros_like(dtheta), where=dt > 0)
    out = np.full(ds.shape, 'drive_curve', dtype='U14')
    out[np.abs(ds) < 1e-9] = 'spin'
    out[(np.abs(ds) < 1e-9) & (np.abs(dtheta) < 1e-9)] = 'stop'
    out[(np.abs(ds) >= 1e-9) & (rate < DRIVE_STRAIGHT_YAW_RATE_RAD_S)] = 'drive_straight'
    return out


def time_since_last_spin(phase, t):
    """Seconds since the last 'spin' sample ended (inf before the first spin)."""
    out = np.full(len(phase), np.inf)
    last = None
    for k, p in enumerate(phase):
        if p == 'spin':
            last = t[k]
            out[k] = 0.0
        elif last is not None:
            out[k] = t[k] - last
    return out


# ----------------------------------------------------------------------------- distribution shape
def skew_kurt(x, axis=0):
    x = np.asarray(x, float)
    m = x.mean(axis=axis, keepdims=True)
    d = x - m
    v = (d ** 2).mean(axis=axis)
    return (d ** 3).mean(axis=axis) / v ** 1.5, (d ** 4).mean(axis=axis) / v ** 2


def bimodality_coefficient(x):
    """Sarle's sample bimodality coefficient; > 5/9 (~0.555) suggests bi/multimodality."""
    x = np.asarray(x, float)
    n = len(x)
    g, k = skew_kurt(x)
    excess = k - 3.0
    return float((g ** 2 + 1) / (excess + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))))
