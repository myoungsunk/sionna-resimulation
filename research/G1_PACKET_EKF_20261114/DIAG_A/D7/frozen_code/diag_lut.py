"""Batched equivalent of the pinned 81cdffb FrozenLut observation."""

import numpy as np

from p3_rf_adapter4 import B_OLD


def interpolate(lut, theta_deg, phi_tx_deg, phi_rx_deg):
    t = np.clip(theta_deg / lut.dt, 0.0, lut.nt - 1 - 1e-9)
    a = (phi_tx_deg + 180.0) / lut.dp
    b = (phi_rx_deg + 180.0) / lut.dp
    i0 = np.floor(t).astype(int)
    j0_float, k0_float = np.floor(a), np.floor(b)
    ft, fa, fb = t - i0, a - j0_float, b - k0_float
    j0, k0 = j0_float.astype(int) % lut.np, k0_float.astype(int) % lut.np
    i1, j1, k1 = i0 + 1, (j0 + 1) % lut.np, (k0 + 1) % lut.np

    s = lut.s
    c000, c001 = s[i0, j0, k0], s[i0, j0, k1]
    c010, c011 = s[i0, j1, k0], s[i0, j1, k1]
    c100, c101 = s[i1, j0, k0], s[i1, j0, k1]
    c110, c111 = s[i1, j1, k0], s[i1, j1, k1]
    c00, c01 = c000 * (1 - fb) + c001 * fb, c010 * (1 - fb) + c011 * fb
    c10, c11 = c100 * (1 - fb) + c101 * fb, c110 * (1 - fb) + c111 * fb
    c0 = c00 * (1 - fa) + c01 * fa
    c1 = c10 * (1 - fa) + c11 * fa
    value = c0 * (1 - ft) + c1 * ft
    d_theta = (c1 - c0) / lut.dt
    d_tx = ((c01 - c00) * (1 - ft) + (c11 - c10) * ft) / lut.dp
    d_rx = (
        ((c001 - c000) * (1 - fa) + (c011 - c010) * fa) * (1 - ft)
        + ((c101 - c100) * (1 - fa) + (c111 - c110) * fa) * ft
    ) / lut.dp
    return value, d_theta, d_tx, d_rx


def lut_batch(lut, x, case):
    """Return predictions [n,2] and Jacobians [n,2,4] in [range,s] order."""
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[1] != 4 or not np.isfinite(x).all():
        raise ValueError("EKF4_BATCH_POSE_INVALID")
    anchor = np.asarray(case["anchor"], dtype=float)
    if anchor.shape != (3,) or not np.isfinite(anchor).all():
        raise ValueError("INVALID_FROZEN_ANCHOR")
    mount = float(case["mount_deg"])
    z_tag = float(case["robot_z_m"])
    u, v = x[:, 0] - anchor[0], x[:, 1] - anchor[1]
    h = anchor[2] - z_tag
    rho2 = np.maximum(u * u + v * v, 1e-12)
    rho = np.sqrt(rho2)
    psi = np.degrees(x[:, 2]) + mount
    theta_geo = np.degrees(np.arctan2(rho, h))
    phi_tx = np.degrees(np.arctan2(-v, u))
    phi_rx = (np.degrees(np.arctan2(-v, -u)) - psi + 180.0) % 360.0 - 180.0
    value, d_theta, d_tx, d_rx = interpolate(lut, theta_geo, phi_tx, phi_rx)
    k = 180.0 / np.pi
    dth_du = h / (rho2 + h * h) * u / rho * k
    dth_dv = h / (rho2 + h * h) * v / rho * k
    dtx_du = v / rho2 * k
    dtx_dv = -u / rho2 * k
    drx_du = -v / rho2 * k
    drx_dv = u / rho2 * k
    ds_dx = d_theta * dth_du + d_tx * dtx_du + d_rx * drx_du
    ds_dy = d_theta * dth_dv + d_tx * dtx_dv + d_rx * drx_dv
    ds_dpsi = -d_rx * k

    delta_xyz = np.column_stack((u, v, np.full(len(x), z_tag - anchor[2])))
    distance = np.linalg.norm(delta_xyz, axis=1)
    prediction = np.column_stack((distance + B_OLD, value))
    jacobian = np.zeros((len(x), 2, 4), dtype=float)
    jacobian[:, 0, 0], jacobian[:, 0, 1] = u / distance, v / distance
    jacobian[:, 1, 0], jacobian[:, 1, 1], jacobian[:, 1, 2] = ds_dx, ds_dy, ds_dpsi
    return prediction, jacobian
