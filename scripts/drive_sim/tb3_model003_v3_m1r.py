"""Positive-distance M1-R with a local linear variance remainder."""

import numpy as np

from tb3_model003_m1r_batch import m1r_values


DISTANCE_FLOOR_M = 0.5
MAX_NORMAL_NODE = float(np.sqrt(2.0)*np.polynomial.hermite.hermgauss(5)[0][-1])


def clip_distance(distance, sigma, *, floor=DISTANCE_FLOOR_M):
    distance, sigma = np.broadcast_arrays(np.asarray(distance, dtype=float), np.asarray(sigma, dtype=float))
    if not np.isfinite(distance).all() or not np.isfinite(sigma).all() or np.any(sigma < 0.0):
        raise ValueError("Invalid Gaussian distance prior")
    available = distance > floor
    allowed = np.maximum((distance - floor)/MAX_NORMAL_NODE, 0.0)
    use = np.minimum(sigma, allowed)
    return use, available, available & (sigma > use)


def _values(model, obs, banks, directions, yaw, distance, sigma, rule, radial_step, batch_poses):
    use, available, clipped = clip_distance(distance, sigma)
    pred = np.full(distance.shape, np.nan)
    variance = np.full(distance.shape, np.nan)
    if available.any():
        pred[available], variance[available] = m1r_values(
            model, obs, banks, directions[available], yaw[available],
            distance[available], use[available], rule, batch_poses=batch_poses)
    if clipped.any():
        center = distance[clipped]
        plus = center + radial_step
        minus = np.maximum(center - radial_step, DISTANCE_FLOOR_M)
        args = model, obs, banks, directions[clipped], yaw[clipped]
        upper = m1r_values(*args, plus, 0., rule, batch_poses=batch_poses)[0]
        lower = m1r_values(*args, minus, 0., rule, batch_poses=batch_poses)[0]
        gradient = (upper - lower)/(plus - minus)
        variance[clipped] += gradient**2*(sigma[clipped]**2 - use[clipped]**2)
    return pred, variance, clipped


def m1r_clipped(model, obs, banks, state, cov, anchor, rx_height, rule, *,
                 xy_step=0.001, yaw_step=np.deg2rad(0.1), radial_step=0.001, batch_poses=40):
    """Evaluate s and its finite differences at the predicted packet state."""
    delta = np.column_stack((state[:, :2] - anchor[:2], np.full(len(state), rx_height - anchor[2])))
    nominal = np.linalg.norm(delta, axis=-1)
    jac_range = np.divide(delta[:, :2], nominal[:, None], out=np.zeros_like(delta[:, :2]),
                          where=nominal[:, None] > 0.0)
    radial_variance = np.einsum("ni,nij,nj->n", jac_range, cov[:, :2, :2], jac_range)
    if np.any(radial_variance < 0.0):
        raise ValueError("Negative predicted radial variance")
    sigma = np.sqrt(radial_variance)
    steps = np.diag([xy_step, xy_step, yaw_step])
    shifts = np.concatenate((np.zeros((1, 3)), steps, -steps))
    shifted = delta[:, None, :] + np.column_stack((shifts[:, :2], np.zeros(len(shifts))))
    distance = np.linalg.norm(shifted, axis=-1)
    direction = np.divide(shifted, distance[..., None], out=np.zeros_like(shifted), where=distance[..., None] > 0.0)
    yaw = np.rad2deg(state[:, 2, None] + shifts[:, 2])
    pred, var, clipped = _values(model, obs, banks, direction, yaw, distance,
                                  np.broadcast_to(sigma[:, None], distance.shape), rule, radial_step, batch_poses)
    jac = (pred[:, 1:4] - pred[:, 4:7]) / (2.0*np.array([xy_step, xy_step, yaw_step]))
    return pred[:, 0], jac, var[:, 0], clipped.any(axis=1)


def synthetic_check():
    center = np.array([0.45, 0.5, 0.51, 2.7, 10.0])
    sigma = np.array([0.03, 0.03, 0.01, 1.68, 0.01])
    clipped_sigma, available, clipped = clip_distance(center, sigma)
    np.testing.assert_array_equal(available, [False, False, True, True, True])
    np.testing.assert_array_equal(clipped, [False, False, True, True, False])
    np.testing.assert_allclose((center - MAX_NORMAL_NODE*clipped_sigma)[clipped], DISTANCE_FLOOR_M,
                               rtol=0.0, atol=2e-15)
    assert clipped_sigma[-1] == sigma[-1]
    return {"status": "PASS", "floor_m": DISTANCE_FLOOR_M, "max_node": MAX_NORMAL_NODE}
