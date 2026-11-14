"""Batched direct LoS/M1-R using the S1 FFD model and selected tap rule."""

import math

import numpy as np

from tb3_model003_s1_observation import RULES, channel_to_cir, range_candidates, signed_s_at_tap


_NODES, _WEIGHTS = np.polynomial.hermite.hermgauss(5)
_WEIGHTS = _WEIGHTS / math.sqrt(math.pi)


def _los_tx_plus45(model, banks, directions, yaws_deg):
    """Vectorize the first TX column of pinned hs_lut.los_h before path delay."""
    pattern = model.P
    th_t = np.arccos(np.clip(directions[:, 2], -1.0, 1.0))
    ph_t = np.arctan2(directions[:, 1], directions[:, 0])
    tx = pattern.field_world(banks[0], model.ANCHOR_ROTATION, th_t, ph_t)
    v = -directions
    th_r = np.arccos(np.clip(v[:, 2], -1.0, 1.0))
    ph_r = np.arctan2(v[:, 1], v[:, 0])
    world = pattern.direction(th_r, ph_r)
    rotation = model._rot_z_batch(np.deg2rad(yaws_deg))
    local = np.einsum("pi,pij->pj", world, rotation)
    th = np.arccos(np.clip(local[:, 2], -1.0, 1.0))
    ph = np.arctan2(local[:, 1], local[:, 0])
    t_hat, p_hat = pattern.sph_basis(th, ph)
    rx = []
    for bank in banks:
        e_th, e_ph = bank.sample(th, ph)
        field = e_th[..., None] * t_hat[None] + e_ph[..., None] * p_hat[None]
        rx.append(pattern.SCALE * np.einsum("bpi,pji->bpj", field, rotation))
    return np.einsum("rbpi,bpi->pbr", np.asarray(rx), tx)


def _marginalize(model, obs, banks, directions, yaws, distances, sigmas, rule):
    """Sample 5-point Gauss–Hermite distances or one deterministic distance."""
    fields = _los_tx_plus45(model, banks, directions, yaws)
    freq = np.asarray(banks[0].freqs_hz)
    center_only = sigmas == 0
    quadrature = ~center_only
    means, variances = np.empty(len(yaws)), np.empty(len(yaws))
    # Keep one set of antenna fields for every distance node. Only the free
    # space amplitude, phase, and chosen tap depend on the quadrature distance.
    for mask, marg in ((center_only, False), (quadrature, True)):
        if not mask.any():
            continue
        d = distances[mask, None]
        if marg:
            d = d + (math.sqrt(2.0) * sigmas[mask, None]) * _NODES
        if np.any(d <= 0):
            raise ValueError("Nonpositive M1-R quadrature distance")
        scale = model.C0 / freq / (4.0 * np.pi * d[..., None])
        phase = np.exp(-2j * np.pi * freq * d[..., None] / model.C0)
        channel = fields[mask, None, :, :] * (scale * phase)[..., None]
        channel = channel.reshape(-1, len(freq), 2, 1)
        cir = channel_to_cir(channel, obs)
        selected = range_candidates(cir, float(freq[1] - freq[0]), rules=(rule,))[rule]
        s = signed_s_at_tap(cir, selected["tap"], selected["detected"])
        if marg:
            s = s.reshape(-1, len(_NODES))
            mean = np.sum(s * _WEIGHTS, axis=-1)
            means[mask] = mean
            variances[mask] = np.sum((s - mean[:, None])**2 * _WEIGHTS, axis=-1)
        else:
            means[mask] = s
            variances[mask] = np.where(np.isfinite(s), 0.0, np.nan)
    return means, variances


def m1r_values(model, obs, banks, directions, yaw_deg, distance_m, sigma_m, rule, *, batch_poses=40):
    """Batch counterpart of S1 m1r_s. Return signed-s mean and marginal variance.

    Directions end with a three-coordinate unit vector from anchor to robot.
    Yaw in degrees, range prior mean in m and its standard deviation in m
    broadcast over the other axes. Pattern banks are S1 [+45, -45], the first
    being the transmitted port. The same S1 CIR and selected-tap code is used.
    """
    unit = np.asarray(directions, dtype=float)
    if not (unit.ndim and unit.shape[-1] == 3) or len(banks) != 2:
        raise ValueError("Expected 3D directions and the two pinned S1 FFD banks")
    if rule not in RULES or not isinstance(batch_poses, int) or batch_poses <= 0:
        raise ValueError("Expected an S1 tap rule and a positive pose batch size")
    yaw, distance, sigma = (np.broadcast_to(values, unit.shape[:-1]).ravel()
                            for values in (yaw_deg, distance_m, sigma_m))
    if (not np.isfinite(unit).all() or not np.allclose(np.linalg.norm(unit, axis=-1), 1, atol=1e-12, rtol=0)
            or not all(np.isfinite(a).all() for a in (yaw, distance, sigma))
            or np.any(distance <= 0) or np.any(sigma < 0)):
        raise ValueError("Expected finite unit directions and a positive distance prior with nonnegative sigma")
    flat_unit = unit.reshape(-1, 3)
    mean, variance = np.empty(len(flat_unit)), np.empty(len(flat_unit))
    for low in range(0, len(flat_unit), batch_poses):
        bounds = slice(low, low + batch_poses)
        mean[bounds], variance[bounds] = _marginalize(
            model, obs, banks, flat_unit[bounds], yaw[bounds], distance[bounds], sigma[bounds], rule,
        )
    return mean.reshape(unit.shape[:-1]), variance.reshape(unit.shape[:-1])


def m1r_batch(model, obs, banks, means, covs, anchor_xyz, rx_z, rule, *,
              step_xy_m, step_yaw_rad, batch_poses=40):
    """Return predicted signed s, its [x,y,psi] gradient, and radial marginal variance.

    Means use [x,y,psi,...], psi in rad. The radial prior variance is the
    linear slant-range projection of the predicted XY covariance. The caller
    can pass covs=None for deterministic geometry. The local central difference
    holds this variance fixed while varying position and yaw; position changes
    both direction and geometric prior range center. Each perturbed evaluation
    applies the selected tap rule independently, including tap switches within
    the difference interval. No RF measurement enters.
    """
    state = np.asarray(means, dtype=float)
    anchor = np.asarray(anchor_xyz, dtype=float)
    steps = np.array([step_xy_m, step_xy_m, step_yaw_rad])
    if (state.ndim == 0 or state.shape[-1] < 3 or not np.isfinite(state[..., :3]).all()
            or anchor.shape != (3,) or not np.isfinite(anchor).all() or not np.isfinite(rx_z)
            or not np.isfinite(steps).all() or np.any(steps <= 0)):
        raise ValueError("Expected finite M1-R geometry and explicit positive difference steps")
    delta = np.empty(state.shape[:-1] + (3,))
    delta[..., :2] = state[..., :2] - anchor[:2]
    delta[..., 2] = rx_z - anchor[2]
    delta_norm = np.linalg.norm(delta, axis=-1)
    if np.any(delta_norm <= 0):
        raise ValueError("M1-R geometry requires nonzero anchor separation")
    sigma = np.zeros_like(delta_norm)
    if covs is not None:
        cov = np.asarray(covs, dtype=float)
        if cov.ndim < 2 or cov.shape[-2] != cov.shape[-1] or cov.shape[-1] < 2:
            raise ValueError("Expected a predicted covariance containing the XY block")
        p_xy = np.broadcast_to(cov[..., :2, :2], state.shape[:-1] + (2, 2))
        if not np.isfinite(p_xy).all() or not np.allclose(p_xy, p_xy.swapaxes(-1, -2), atol=1e-14, rtol=1e-12):
            raise ValueError("Predicted XY covariance must be finite and symmetric")
        jac = delta[..., :2] / delta_norm[..., None]
        radial_variance = np.einsum("...i,...ij,...j->...", jac, p_xy, jac)
        if np.any(radial_variance < 0):
            raise ValueError("Predicted covariance has negative radial variance")
        sigma = np.sqrt(radial_variance)

    shifts = np.concatenate((np.zeros((1, 3)), np.diag(steps), -np.diag(steps)))
    directed = delta[..., None, :] + np.column_stack((shifts[:, :2], np.zeros(len(shifts))))
    distance = np.linalg.norm(directed, axis=-1)
    if np.any(distance <= 0):
        raise ValueError("Perturbed M1-R geometry requires nonzero anchor separation")
    yaw_deg = np.rad2deg(state[..., None, 2] + shifts[:, 2])
    expected, variance = m1r_values(model, obs, banks, directed / distance[..., None], yaw_deg, distance,
                                    sigma[..., None], rule, batch_poses=batch_poses)
    derivatives = (expected[..., 1:4] - expected[..., 4:7]) / (2 * steps)
    return expected[..., 0], derivatives, variance[..., 0]


def self_check(model, obs, banks, scalar_m1r):
    """Compare scalar S1 and batch math on synthetic poses, across frozen rules."""
    anchor, rx_z = np.array([0., 0., 2.7]), 0.8
    points = np.array([[0., 0., 0.], [0.8, -4.5, 2.1], [-2.3, 0., 0.12], [-4., 0.001, -np.pi],
                       [-4., -0.001, np.pi], [8.4, 8.2, 0.005], [0.0001, 0., 0.8], [0., 5.1, -2.2]])
    delta = np.column_stack((points[:, :2], np.full(len(points), rx_z - anchor[2])))
    distance = np.linalg.norm(delta, axis=-1)
    direction = delta / distance[:, None]
    yaw = np.rad2deg(points[:, 2])
    sigma = np.array([0., 0., 0.5, 0., 0.25, 0.1, 0.05, 0.21])
    result = {}
    inputs = tuple(zip(direction, yaw, distance, sigma, strict=True))
    for rule in RULES:
        expected = np.array([scalar_m1r(model, obs, banks, *row, rule) for row in inputs])
        actual = np.column_stack(m1r_values(model, obs, banks, direction, yaw, distance, sigma, rule,
                                            batch_poses=3))
        np.testing.assert_allclose(actual, expected, atol=2e-12, rtol=0)
        result[rule] = np.max(np.abs(actual - expected), axis=0).tolist()

    xy_step, yaw_step = 0.002, math.radians(0.05)
    cov = np.array([[0.04, 0.008], [0.008, 0.05]])
    actual_s, actual_gradient, actual_var = m1r_batch(model, obs, banks, points, cov, anchor, rx_z, "O30",
                                                      step_xy_m=xy_step, step_yaw_rad=yaw_step, batch_poses=5)
    radial_sigma = np.sqrt(np.einsum("bi,ij,bj->b", direction[:, :2], cov, direction[:, :2]))

    def scalar_pose(pos, std):
        delta = np.array([pos[0], pos[1], rx_z]) - anchor
        radius = np.linalg.norm(delta)
        return scalar_m1r(model, obs, banks, delta / radius, math.degrees(pos[2]), radius, std, "O30")

    deriv = np.diag([xy_step, xy_step, yaw_step])
    expected = np.array([scalar_pose(p, std) for p, std in zip(points, radial_sigma, strict=True)])
    jac = np.array([[(scalar_pose(p + d, std)[0] - scalar_pose(p - d, std)[0]) / (2 * step)
                     for d, step in zip(deriv, deriv.diagonal(), strict=True)]
                    for p, std in zip(points, radial_sigma, strict=True)])
    np.testing.assert_allclose(np.column_stack((actual_s, actual_var)), expected, atol=2e-12, rtol=0)
    np.testing.assert_allclose(actual_gradient, jac, atol=2e-9, rtol=0)
    return dict(status="PASS", max_delta_mean_and_var=result,
                max_delta_gradient=float(np.max(np.abs(actual_gradient - jac))))
