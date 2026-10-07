"""S4: LoS-only measurement model h_s(theta, phi_tx, phi_rx) as a look-up table (single-port anchor, TX +45 column).

For a ceiling anchor (boresight down) and an up-facing robot antenna the off-boresight angle theta is the same at both ends.
phi_tx is the azimuth of the line of sight in the anchor frame, phi_rx the azimuth of the direction towards the anchor in the antenna
frame (it contains the antenna yaw).  s is computed from the FFD banks with the validated Cartesian contraction and passed through the
same first-path chain as the simulation (new single-port rule), so the LUT is the exact LoS-only curve of that chain.
"""
from __future__ import annotations

import numpy as np

from qclean_uwb.drivesim import observation as O
from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, rot_z

C0 = 299792458.0
D_REF_M = 10.0          # s is a ratio at one tap: independent of the link length up to the sub-tap position; fixed here


def los_h(banks, d_world, yaw_deg, dist_m: float = D_REF_M):
    """Clean LoS channel (n_bin, 2 rx, 2 tx) for a unit direction ``d_world`` anchor->robot and antenna yaw (deg)."""
    d = np.asarray(d_world, float).reshape(1, 3)
    th_t, ph_t = np.arccos(d[:, 2]), np.arctan2(d[:, 1], d[:, 0])
    v = -d
    th_r, ph_r = np.arccos(v[:, 2]), np.arctan2(v[:, 1], v[:, 0])
    freqs = banks[0].freqs_hz
    tx_f = np.stack([P.field_world(b, ANCHOR_ROTATION, th_t, ph_t) for b in banks])[:, :, 0, :]      # (tx, bin, 3)
    rx_f = np.stack([P.field_world(b, rot_z(yaw_deg), th_r, ph_r) for b in banks])[:, :, 0, :]       # (rx, bin, 3)
    scale = C0 / freqs / (4.0 * np.pi * dist_m)
    phase = np.exp(-2j * np.pi * freqs * dist_m / C0)
    return np.einsum("rbi,tbi->brt", rx_f, tx_f) * (scale * phase)[:, None, None]


def los_s_direct(banks, theta_deg, phi_tx_deg, phi_rx_deg) -> float:
    """Reference value (no table): s for one (theta, phi_tx, phi_rx)."""
    th, pt = np.radians(theta_deg), np.radians(phi_tx_deg)
    d_local = np.array([np.sin(th) * np.cos(pt), np.sin(th) * np.sin(pt), np.cos(th)])
    d_world = ANCHOR_ROTATION @ d_local
    v = -d_world
    yaw = np.degrees(np.arctan2(v[1], v[0])) - phi_rx_deg
    h = los_h(banks, d_world, yaw)
    return float(O.observe(h[None], banks[0].freqs_hz, None, None, tx=0)["s"][0])


def _rot_z_batch(psi_rad):
    c, s_ = np.cos(psi_rad), np.sin(psi_rad)
    r = np.zeros((len(psi_rad), 3, 3))
    r[:, 0, 0], r[:, 0, 1], r[:, 1, 0], r[:, 1, 1], r[:, 2, 2] = c, -s_, s_, c, 1.0
    return r


def build_lut(banks, theta_step_deg: float = 2.0, phi_step_deg: float = 2.0, theta_max_deg: float = 90.0, progress=None) -> dict:
    """Vectorised over phi_rx: for a fixed line of sight the antenna yaw only rotates the local frame about z, so the RX field is the bank
    sampled at (theta, phi_rx) and rotated to the world frame by the yaw."""
    thetas = np.arange(0.0, theta_max_deg + 1e-9, theta_step_deg)
    phis = np.arange(-180.0, 180.0, phi_step_deg)
    phis_rad = np.radians(phis)
    freqs = banks[0].freqs_hz
    scale = C0 / freqs / (4.0 * np.pi * D_REF_M)
    phase = np.exp(-2j * np.pi * freqs * D_REF_M / C0)
    s = np.empty((len(thetas), len(phis), len(phis)))
    for i, t in enumerate(np.radians(thetas)):
        for j, pt in enumerate(np.radians(phis)):
            d_local = np.array([np.sin(t) * np.cos(pt), np.sin(t) * np.sin(pt), np.cos(t)])
            d_world = ANCHOR_ROTATION @ d_local
            v = -d_world
            th_t, ph_t = np.arccos(d_world[2]), np.arctan2(d_world[1], d_world[0])
            az_v = np.arctan2(v[1], v[0])
            tx_f = np.stack([P.field_world(b, ANCHOR_ROTATION, np.array([th_t]), np.array([ph_t]))[:, 0, :] for b in banks])      # (tx, bin, 3)
            th_loc = np.full_like(phis_rad, np.arccos(np.clip(v[2], -1, 1)))
            t_hat, p_hat = P.sph_basis(th_loc, phis_rad)
            rot = _rot_z_batch(az_v - phis_rad)                                                    # yaw = az(v) - phi_rx
            rx = []
            for b in banks[:2]:
                e_th, e_ph = b.sample(th_loc, phis_rad)                                            # (bin, phi)
                local = e_th[..., None] * t_hat[None] + e_ph[..., None] * p_hat[None]              # (bin, phi, 3)
                rx.append(P.SCALE * np.einsum("pij,bpj->bpi", rot, local))
            rx = np.stack(rx)                                                                      # (rx, bin, phi, 3)
            h = np.einsum("rbpi,bi->pbr", rx, tx_f[0]) * (scale * phase)[None, :, None]
            h4 = np.zeros((len(phis), len(freqs), 2, 2), complex)
            h4[..., 0] = h
            s[i, j] = O.observe(h4, freqs, None, None, tx=0)["s"]
        if progress:
            progress(i + 1, len(thetas))
    return dict(theta_deg=thetas, phi_deg=phis, s=s, d_ref_m=D_REF_M)


class HsLut:
    """Trilinear interpolation (periodic in both azimuths) with the analytic gradient of the interpolant."""

    def __init__(self, lut: dict):
        self.theta = np.asarray(lut["theta_deg"], float)
        self.phi = np.asarray(lut["phi_deg"], float)
        self.s = np.asarray(lut["s"], float)
        self.dt = float(self.theta[1] - self.theta[0])
        self.dp = float(self.phi[1] - self.phi[0])
        self.np = len(self.phi)
        self.nt = len(self.theta)

    def __call__(self, theta_deg, phi_tx_deg, phi_rx_deg, with_grad: bool = False):
        t = np.clip(np.asarray(theta_deg, float) / self.dt, 0.0, self.nt - 1 - 1e-9)
        a = (np.asarray(phi_tx_deg, float) + 180.0) / self.dp
        b = (np.asarray(phi_rx_deg, float) + 180.0) / self.dp
        i0 = np.floor(t).astype(int)
        j0f, k0f = np.floor(a), np.floor(b)
        ft, fa, fb = t - i0, a - j0f, b - k0f
        j0, k0 = j0f.astype(int) % self.np, k0f.astype(int) % self.np
        j1, k1, i1 = (j0 + 1) % self.np, (k0 + 1) % self.np, i0 + 1
        S = self.s
        c000, c001, c010, c011 = S[i0, j0, k0], S[i0, j0, k1], S[i0, j1, k0], S[i0, j1, k1]
        c100, c101, c110, c111 = S[i1, j0, k0], S[i1, j0, k1], S[i1, j1, k0], S[i1, j1, k1]
        c00, c01, c10, c11 = c000 * (1 - fb) + c001 * fb, c010 * (1 - fb) + c011 * fb, c100 * (1 - fb) + c101 * fb, c110 * (1 - fb) + c111 * fb
        c0, c1 = c00 * (1 - fa) + c01 * fa, c10 * (1 - fa) + c11 * fa
        val = c0 * (1 - ft) + c1 * ft
        if not with_grad:
            return val
        d_t = (c1 - c0) / self.dt
        d_a = ((c01 - c00) * (1 - ft) + (c11 - c10) * ft) / self.dp
        d_b = (((c001 - c000) * (1 - fa) + (c011 - c010) * fa) * (1 - ft) + ((c101 - c100) * (1 - fa) + (c111 - c110) * fa) * ft) / self.dp
        return val, np.stack((d_t, d_a, d_b), -1)


def geometry_angles(anchor_xyz, robot_xyz, antenna_yaw_deg):
    """(theta, phi_tx, phi_rx) in degrees for the LoS between the anchor and the robot antenna (vectorised over the robot)."""
    robot = np.asarray(robot_xyz, float)
    d = robot - np.asarray(anchor_xyz, float)
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    local = d @ ANCHOR_ROTATION                           # R^T d  (R is symmetric here)
    theta = np.degrees(np.arccos(np.clip(local[..., 2], -1, 1)))
    phi_tx = np.degrees(np.arctan2(local[..., 1], local[..., 0]))
    v_az = np.degrees(np.arctan2(-d[..., 1], -d[..., 0]))
    phi_rx = (v_az - np.asarray(antenna_yaw_deg, float) + 180.0) % 360.0 - 180.0
    return theta, phi_tx, phi_rx


def s_model(lut: HsLut, anchor_xyz, robot_z: float, x, y, theta_rad, mount_deg: float = 0.0, with_jac: bool = False):
    """Predicted LoS-only s for robot body positions (x, y) and body yaw ``theta_rad`` (antenna yaw = body yaw + mount).

    Vectorised.  ``with_jac`` additionally returns ds/d(x, y, theta) (theta in radians) from the geometric chain rule and the LUT gradient.
    """
    ax, ay, az = (float(v) for v in anchor_xyz)
    u, v = np.asarray(x, float) - ax, np.asarray(y, float) - ay
    h = az - robot_z
    rho2 = np.maximum(u * u + v * v, 1e-12)
    rho = np.sqrt(rho2)
    psi = np.degrees(np.asarray(theta_rad, float)) + mount_deg
    theta_geo = np.degrees(np.arctan2(rho, h))
    phi_tx = np.degrees(np.arctan2(-v, u))
    phi_rx = (np.degrees(np.arctan2(-v, -u)) - psi + 180.0) % 360.0 - 180.0
    if not with_jac:
        return lut(theta_geo, phi_tx, phi_rx)
    val, g = lut(theta_geo, phi_tx, phi_rx, with_grad=True)
    k = 180.0 / np.pi
    dth_du, dth_dv = h / (rho2 + h * h) * u / rho * k, h / (rho2 + h * h) * v / rho * k
    dtx_du, dtx_dv = v / rho2 * k, -u / rho2 * k
    drx_du, drx_dv = -v / rho2 * k, u / rho2 * k
    jac = np.stack((g[..., 0] * dth_du + g[..., 1] * dtx_du + g[..., 2] * drx_du,
                    g[..., 0] * dth_dv + g[..., 1] * dtx_dv + g[..., 2] * drx_dv,
                    -g[..., 2] * k), -1)
    return val, jac
