"""Offline antenna-pattern application for the trace/pattern split (method B).

A trace with unit isotropic V/H ports at identity orientation gives, per path, ``a_iso[r, t] = b_r^T J b_t`` with
``b`` the world-frame spherical basis (theta_hat, phi_hat) at the arrival / departure direction.  Hence the transverse
3x3 path Jones matrix is ``J = B_r a_iso B_t^T`` and any FFD pattern pair gives ``a[r, t] = F_rx[r]^T J F_tx[t]``
(``F`` = world-frame field vectors; same Cartesian contraction as ``corridor_sionna_run.los_check``).
Pure numpy, no Sionna import.  Bilinear interpolation replicates ``sionna_native_runtime.BankPort.evaluate``.
"""
from __future__ import annotations

import numpy as np

SCALE = float(np.sqrt(2.0 * np.pi / 376.730313668))   # rE at 1 W incident -> Sionna dimensionless pattern (BankPort.update)
TWO_PI = 2.0 * np.pi


def sph_basis(theta, phi):
    """World-frame (theta_hat, phi_hat) unit vectors, each (n, 3)."""
    ct, st, cp, sp = np.cos(theta), np.sin(theta), np.cos(phi), np.sin(phi)
    return np.stack((ct * cp, ct * sp, -st), -1), np.stack((-sp, cp, np.zeros_like(cp)), -1)


def direction(theta, phi):
    return np.stack((np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)), -1)


def jones_from_iso(a_iso, theta_t, phi_t, theta_r, phi_r):
    """a_iso (..., 2, 2, n) [rx V/H, tx V/H, path] -> J (..., n, 3, 3)."""
    bt = np.stack(sph_basis(theta_t, phi_t), -1)    # (n, 3, 2)
    br = np.stack(sph_basis(theta_r, phi_r), -1)
    a = np.moveaxis(np.asarray(a_iso), -1, -3)       # (..., n, 2, 2)
    return np.einsum("nik,...nkl,njl->...nij", br, a, bt)


class Bank:
    """FFD bank on a regular (theta, phi) grid; fields have shape (n_bin, n_theta, n_phi)."""

    def __init__(self, data: dict):
        self.theta = np.deg2rad(np.asarray(data["theta_deg"], float))
        self.phi = np.deg2rad(np.asarray(data["phi_deg"], float))
        self.t0, self.p0 = float(self.theta[0]), float(self.phi[0])
        self.dt, self.dp = float(self.theta[1] - self.theta[0]), float(self.phi[1] - self.phi[0])
        self.nt, self.np = len(self.theta), len(self.phi)
        self.e_theta = np.asarray(data["e_theta"])
        self.e_phi = np.asarray(data["e_phi"])
        self.freqs_hz = np.asarray(data["freqs_hz"], float)

    def sample(self, theta, phi, bins=None):
        tw = np.clip((theta - self.t0) / self.dt, 0.0, self.nt - 1.0)
        wrapped = phi - self.p0
        wrapped = wrapped - np.floor(wrapped / TWO_PI) * TWO_PI
        pw = np.clip(wrapped / self.dp, 0.0, self.np - 1.0)
        it = np.minimum(np.floor(tw), self.nt - 2).astype(int)
        ip = np.minimum(np.floor(pw), self.np - 2).astype(int)
        wt, wp = tw - it, pw - ip
        out = []
        for e in (self.e_theta, self.e_phi):
            e = e if bins is None else e[bins]
            a, b, c, d = e[:, it, ip], e[:, it, ip + 1], e[:, it + 1, ip], e[:, it + 1, ip + 1]
            out.append((1 - wt) * ((1 - wp) * a + wp * b) + wt * ((1 - wp) * c + wp * d))
        return out   # [E_theta, E_phi], each (n_bin, n)


def field_world(bank: Bank, rotation, theta_w, phi_w, bins=None):
    """World-frame field vectors (n_bin, n, 3) of one port for directions (theta_w, phi_w) given in the world frame.

    ``rotation`` maps antenna-local axes to world axes (columns = local x, y, z in world).
    """
    rot = np.asarray(rotation, float)
    local = direction(theta_w, phi_w) @ rot            # R^T d
    th = np.arccos(np.clip(local[:, 2], -1.0, 1.0))
    ph = np.arctan2(local[:, 1], local[:, 0])
    e_th, e_ph = bank.sample(th, ph, bins)
    t_hat, p_hat = sph_basis(th, ph)
    vec = e_th[..., None] * t_hat[None] + e_ph[..., None] * p_hat[None]
    return SCALE * (vec @ rot.T)


def channel_from_jones(jones, tau, freqs_hz, rx_fields, tx_fields):
    """H (n_bin, n_rx, n_tx) = sum_paths F_rx^T J F_tx exp(-j 2 pi f tau).

    jones: (n_bin or 1, n, 3, 3);  rx_fields / tx_fields: (n_port, n_bin, n, 3).
    """
    a = np.einsum("rbni,bnij,tbnj->brtn", rx_fields, jones, tx_fields)
    phase = np.exp(-2j * np.pi * np.asarray(freqs_hz, float)[:, None] * np.asarray(tau, float)[None, :])
    return np.einsum("brtn,bn->brt", a, phase)


def canonical_order(tau, theta_t, phi_t, theta_r, phi_r, decimals: int = 3):
    """Index order that is stable across traces at different frequencies / orientations.

    Delays are bit-identical across traces; angles only jitter at float32 level (~5e-6 rad, and phi may flip between
    +pi and -pi), so ties in delay are broken with rounded *unit direction vectors* instead of raw angles.
    """
    keys = np.round(np.concatenate((direction(np.asarray(theta_r), np.asarray(phi_r)), direction(np.asarray(theta_t), np.asarray(phi_t))), axis=-1), decimals)
    return np.lexsort(tuple(keys[:, i] for i in reversed(range(6))) + (np.asarray(tau),))


def interp_jones(jones_nodes, node_freq_hz, freqs_hz, present=None):
    """Interpolate path Jones matrices over frequency: cubic spline of ``J * f`` (removes the 1/f spreading factor).

    Measured on x7.0_y0.0 (257 bins, 6.25-6.75 GHz): K=9 nodes 1.0e-5, K=17 nodes 5.4e-7 relative H error (linear: 1.1e-4 / 2.4e-5).
    With ``node_freq_hz == freqs_hz`` the input is returned unchanged (bin-by-bin trace).

    ``present`` (K, n) marks the nodes at which a path exists (the solver drops some paths inside the band).  Such a path is interpolated by a spline
    through the nodes where it exists and is exactly zero outside the first/last of them (the bisection node puts that boundary on a bin).
    """
    from scipy.interpolate import CubicSpline

    nodes = np.asarray(node_freq_hz, float)
    freqs = np.asarray(freqs_hz, float)
    jones_nodes = np.asarray(jones_nodes)
    if nodes.shape == freqs.shape and np.array_equal(nodes, freqs):
        return jones_nodes
    if len(nodes) == 1:
        return np.repeat(jones_nodes * nodes[0], len(freqs), axis=0) / freqs[:, None, None, None]
    scaled = jones_nodes * nodes[:, None, None, None]
    out = CubicSpline(nodes, scaled, axis=0)(freqs) / freqs[:, None, None, None]
    if present is not None:
        present = np.asarray(present, bool)
        for i in np.flatnonzero(~present.all(axis=0)):
            keep = np.flatnonzero(present[:, i])
            if len(keep) == 0:
                out[:, i] = 0.0
                continue
            lo, hi = nodes[keep[0]], nodes[keep[-1]]
            inside = (freqs >= lo - 1e-3) & (freqs <= hi + 1e-3)
            seg = np.zeros((len(freqs),) + jones_nodes.shape[2:], complex)
            if len(keep) >= 2:
                seg[inside] = CubicSpline(nodes[keep], scaled[keep, i], axis=0)(freqs[inside]) / freqs[inside][:, None, None]
            else:
                seg[inside] = scaled[keep[0], i] / freqs[inside][:, None, None]
            out[:, i] = seg
    return out


def path_directions(theta_t, phi_t, theta_r, phi_r):
    """(n, 6) departure+arrival unit vectors; continuous, so immune to the +pi/-pi flip of phi."""
    return np.concatenate((direction(np.asarray(theta_r), np.asarray(phi_r)), direction(np.asarray(theta_t), np.asarray(phi_t))), axis=-1)


def align_paths(ref_tau, ref_dirs, tau, dirs, tol: float = 1e-4, tau_tol: float = 2e-13):
    """Permutation ``perm`` that aligns a new trace with the reference trace, or ``None`` if the path sets differ.

    The same path can differ by one float32 ulp in delay (~1e-15 s, depends on thread/kernel state) and by ~5e-6 rad in
    angle between calls, so delays are NOT compared bit-exactly.  The full assignment minimises
    ``|d_dir| + |d_tau| / 1 ns`` which also separates paths with degenerate (equal) delays by direction.
    ``tol`` bounds the matched direction distance (unit vectors), ``tau_tol`` the matched delay difference [s].
    """
    from scipy.optimize import linear_sum_assignment

    ref_tau, tau = np.asarray(ref_tau, float), np.asarray(tau, float)
    if ref_tau.shape != tau.shape:
        return None
    dist = np.linalg.norm(ref_dirs[:, None, :] - dirs[None, :, :], axis=-1)
    dtau = np.abs(ref_tau[:, None] - tau[None, :])
    rows, cols = linear_sum_assignment(dist + dtau * 1e9)
    if dist[rows, cols].max() > tol or dtau[rows, cols].max() > tau_tol:
        return None
    perm = np.empty(len(ref_tau), int)
    perm[rows] = cols
    return perm, float(dist[rows, cols].max())


def match_partial(ref_tau, ref_dirs, tau, dirs, tol: float = 1e-4, tau_tol: float = 2e-13):
    """Rectangular version of ``align_paths``: ``(match, extra)`` with ``match[i]`` = index into the new trace for reference path ``i`` (-1 if the
    path is absent in the new trace) and ``extra`` = indices of new paths that match no reference path."""
    from scipy.optimize import linear_sum_assignment

    ref_tau, tau = np.asarray(ref_tau, float), np.asarray(tau, float)
    match = np.full(len(ref_tau), -1, int)
    if len(ref_tau) and len(tau):
        dist = np.linalg.norm(ref_dirs[:, None, :] - dirs[None, :, :], axis=-1)
        dtau = np.abs(ref_tau[:, None] - tau[None, :])
        rows, cols = linear_sum_assignment(dist + dtau * 1e9)
        for r, c in zip(rows, cols):
            if dist[r, c] <= tol and dtau[r, c] <= tau_tol:
                match[r] = c
    extra = np.array(sorted(set(range(len(tau))) - set(match[match >= 0].tolist())), int)
    return match, extra
