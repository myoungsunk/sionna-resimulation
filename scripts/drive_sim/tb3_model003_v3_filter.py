"""MODEL-003 v3 RF update math and the S0 legacy comparison path."""

import numpy as np

from tb3_model003_filter import GATE_JOINT, GATE_RANGE, range_model


def colored_transition(distance_m, yaw_rad, length_m, length_rad, variance):
    """Use measured odometry; a hold preserves the colored state."""
    phi = np.exp(-np.abs(distance_m) / length_m - np.abs(yaw_rad) / length_rad)
    return phi, variance * (1.0 - phi**2)


def white_boundary_variance(thermal, colored_variance):
    """The C3 flagged lower-bound channel is represented as white."""
    return thermal + colored_variance


def corrected_range(observed, offset, knots, bias):
    """C6 lookup uses the measured range minus the S1' offset."""
    lookup = observed - offset
    applied = np.interp(lookup, knots, bias)
    outside = np.isfinite(lookup) & ((lookup < knots[0]) | (lookup > knots[-1]))
    return observed - applied, outside


def _transpose(matrix):
    return matrix.swapaxes(-1, -2)


def _nis(prior, jac, noise, residual):
    innovation = jac @ prior @ _transpose(jac) + noise
    np.linalg.cholesky(innovation)
    return np.sum(residual * np.linalg.solve(innovation, residual[..., None])[..., 0], axis=-1)


def student_noise(prior, jac, noise, residual, df):
    """Three frozen Student-t reweighting steps for the signed-s row."""
    if np.isnan(df) or df < 3:
        raise ValueError("MODEL-003 v3 requires Student-t degrees of freedom >= 3")
    current = noise.copy()
    for _ in range(3):
        innovation_s = (jac @ prior @ _transpose(jac) + current)[..., 1, 1]
        standardized = residual[..., 1]**2 / innovation_s
        weight = np.minimum(1.0, 1.0 + (1.0-standardized)/(df+standardized))
        current[..., 1, 1] = noise[..., 1, 1] / weight
    return current, weight


def joseph_update(mean, prior, jac, noise, residual, active_dim, *, ci_weight=None):
    """Update accepted batches; retain Schmidt mean and propagate cross covariance."""
    if ci_weight is not None:
        prior = prior.copy()
        prior[..., :active_dim, :active_dim] /= ci_weight
        noise = noise / (1.0 - ci_weight)
    ph = prior @ _transpose(jac)
    gain = _transpose(np.linalg.solve(jac @ ph + noise, _transpose(ph)))
    gain[..., active_dim:, :] = 0.0
    posterior = mean + (gain @ residual[..., None])[..., 0]
    posterior[..., 2] = (posterior[..., 2] + np.pi) % (2.0*np.pi) - np.pi
    a = np.eye(mean.shape[-1]) - gain @ jac
    covariance = a @ prior @ _transpose(a) + gain @ noise @ _transpose(gain)
    return posterior, (covariance + _transpose(covariance)) / 2.0


def regression_rf_update(mean, cov, z, anchor_xy, anchor_dz, offset, noise, *,
                         arm, motion_dim=4, colored_columns=None, ci_weight=None,
                         s_expected=None, s_jacobian=None):
    """R4/J4 with v2 gates and with all v3 observation changes disabled."""
    if arm not in ("R4", "J4") or colored_columns is not None or ci_weight is not None:
        raise ValueError("The S0 comparison covers frozen R4 and J4 only")
    count = 1 if arm == "R4" else 2
    if mean.shape[-1] != motion_dim:
        raise ValueError("The S0 comparison has no appended coordinates")
    h_r, H_r = range_model(mean, anchor_xy, anchor_dz, offset)
    h = h_r[..., None]
    H = H_r[..., None, :]
    if count == 2:
        h = np.concatenate((h, s_expected[..., None]), axis=-1)
        H_s = np.zeros_like(H_r)
        H_s[..., :3] = s_jacobian
        H = np.stack((H_r, H_s), axis=-2)
    residual = z[..., :count] - h
    R = noise[..., :count, :count]
    available = np.isfinite(residual).all(axis=-1) & np.isfinite(H).all(axis=(-2, -1))
    nis = np.full(available.shape, np.nan)
    nis[available] = _nis(cov[available], H[available], R[available], residual[available])
    accepted = available & (nis <= (GATE_RANGE if count == 1 else GATE_JOINT))
    new_mean, new_cov = mean.copy(), cov.copy()
    if accepted.any():
        new_mean[accepted], new_cov[accepted] = joseph_update(
            mean[accepted], cov[accepted], H[accepted], R[accepted], residual[accepted], motion_dim)
    return new_mean, new_cov, dict(nis=nis, available=available, accepted=accepted,
                                   rejected=available & ~accepted, innovation=residual)
