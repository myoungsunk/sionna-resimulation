"""Batched packet EKF math for G1-MODEL-003, with no RF or truth-data reads.

States begin [x, y, psi, b_g] in SI units, with k_r next for TB3. J-C and
J-CS append active [c_r, c_s]; J-CS and +K can append fixed zero-mean Schmidt
states. The caller provides all development-fitted covariances and kernels.
"""

import math

import numpy as np


GATE_RANGE = 6.6348966010212145  # Chi-squared (1 dof), 99%.
GATE_JOINT = 9.210340371976184  # Chi-squared (2 dof), 99%.
# r2_bias_replay.py, 81cdffbdedf43b318ebf8eddb4fcbac1fd30d878, lines 31–32, 118–120.
EKF4_INITIAL_STD = (0.1, 0.1, math.radians(5.0), math.radians(0.1))
RF_ARMS = {"R4", "J4", "J-V", "J-C", "J-CS", "J-CI"}


def initial_covariance(k_r_std=None):
    """Return the source EKF4 P0, optionally with an explicit TB3 scale prior."""
    std = EKF4_INITIAL_STD
    if k_r_std is not None:
        if not np.isfinite(k_r_std) or k_r_std <= 0:
            raise ValueError("Expected a positive TB3 scale prior standard deviation")
        std += (k_r_std,)
    return np.diag(np.square(std))


def sensor_v2_process_covariance(distance_m, dt_s):
    """Source EKF4 input variances for wheel distance and gyro angle only."""
    distance, dt = np.broadcast_arrays(distance_m, dt_s)
    q = np.zeros(distance.shape + (2, 2))
    q[..., 0, 0] = 2e-5 * np.abs(distance)
    q[..., 1, 1] = math.radians(0.015) ** 2 * dt
    return q


def _wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


def _transpose(matrix):
    return matrix.swapaxes(-1, -2)


def _symmetrize(matrix):
    return (matrix + _transpose(matrix)) / 2.0


def _sinc_half(angle):
    """Source EKF4 sinc and its derivative with respect to full angle."""
    small = np.abs(angle) < 1e-4
    a2 = angle**2
    h = angle / 2.0
    safe = np.where(small, 1.0, h)
    value = np.where(small, 1 - a2 / 24 + a2**2 / 1920 - a2**3 / 322560, np.sin(h) / safe)
    derivative = np.where(small, -angle / 12 + angle**3 / 480 - angle**5 / 53760,
                          (h * np.cos(h) - np.sin(h)) / (2 * safe**2))
    return value, derivative


def transition_motion(mean, distance_m, gyro_rad, dt_s, *, motion_dim=4, angular_travel_rad=None):
    """Propagate supplied odometry controls and return mean, state F, input G.

    Batched means have arbitrary leading dimensions with state as the last
    axis. The TB3 heading increment is gyro - b_g*dt - k_r*angular_travel.
    Its nonnegative rotation-travel regressor is a separate control, with
    independent gyro input perturbations defined at fixed rotation travel.
    """
    x = np.asarray(mean, dtype=float)
    if x.ndim == 0 or motion_dim not in (4, 5) or x.shape[-1] < motion_dim or not np.isfinite(x).all():
        raise ValueError("Expected finite EKF means with 4 or 5 motion coordinates")
    prefix, n = x.shape[:-1], x.shape[-1]
    ds, gyro, dt = (np.broadcast_to(a, prefix) for a in (distance_m, gyro_rad, dt_s))
    if not all(np.isfinite(a).all() for a in (ds, gyro, dt)) or np.any(dt <= 0):
        raise ValueError("Odometry controls must be finite and dt must be positive")
    angle = gyro - x[..., 3] * dt
    if motion_dim == 5:
        if angular_travel_rad is None:
            raise ValueError("TB3 prediction requires an explicit rotation-travel control")
        travel = np.broadcast_to(angular_travel_rad, prefix)
        if not np.isfinite(travel).all() or np.any(travel < 0):
            raise ValueError("Rotation travel must be finite and nonnegative")
        angle = angle - x[..., 4] * travel

    c, dc = _sinc_half(angle)
    phi = x[..., 2] + angle / 2.0
    u = np.stack((np.cos(phi), np.sin(phi)), axis=-1)
    up = np.stack((-u[..., 1], u[..., 0]), axis=-1)
    d = (ds * c)[..., None] * u
    v = ds[..., None] * (dc[..., None] * u + c[..., None] * up / 2.0)
    y = x.copy()
    y[..., :2] += d
    y[..., 2] = _wrap(x[..., 2] + angle)

    f = np.broadcast_to(np.eye(n), prefix + (n, n)).copy()
    f[..., :2, 2] = np.stack((-d[..., 1], d[..., 0]), axis=-1)
    f[..., :2, 3] = -dt[..., None] * v
    f[..., 2, 3] = -dt
    if motion_dim == 5:
        f[..., :2, 4] = -travel[..., None] * v
        f[..., 2, 4] = -travel
    g = np.zeros(prefix + (n, 2))
    g[..., :2, 0] = c[..., None] * u
    g[..., :2, 1] = v
    g[..., 2, 1] = 1.0
    return y, f, g


def predict(mean, cov, distance_m, gyro_rad, dt_s, *, motion_dim=4, angular_travel_rad=None,
            process_cov=None, restart_pose=None, colored_phi=None, colored_target=None):
    """Batched prediction, including optional two-coordinate colored noise.

    colored_phi and colored_target contain per-packet [range, s] persistence
    and stationary variances. Their innovations are independent, with Q_i
    = (1-phi_i**2)*target_i. Remaining Schmidt states are static.

    restart_pose is a supplied SE(2) change of coordinates (translation in m,
    angle in rad), applied after a zero-distance packet. It transforms the
    existing estimate and covariance. Clock-linked heading evolution remains.
    """
    y, f, g = transition_motion(mean, distance_m, gyro_rad, dt_s, motion_dim=motion_dim,
                                angular_travel_rad=angular_travel_rad)
    p = np.broadcast_to(cov, f.shape)
    if not np.isfinite(p).all():
        raise ValueError("Expected finite state covariance")
    if process_cov is None:
        process_cov = sensor_v2_process_covariance(distance_m, dt_s)
    q = np.broadcast_to(process_cov, y.shape[:-1] + (2, 2))
    if not np.isfinite(q).all():
        raise ValueError("Expected finite wheel/gyro input covariance")
    if (colored_phi is None) != (colored_target is None):
        raise ValueError("Supply both colored persistence and stationary variance")
    if colored_phi is not None:
        if y.shape[-1] < motion_dim + 2:
            raise ValueError("Expected appended colored range and s coordinates")
        phi = np.broadcast_to(colored_phi, y.shape[:-1] + (2,))
        target = np.broadcast_to(colored_target, phi.shape)
        if (not np.isfinite(phi).all() or not np.isfinite(target).all()
                or np.any((phi < 0) | (phi > 1)) or np.any(target < 0)):
            raise ValueError("Expected persistence in [0, 1] and nonnegative variances")
        columns = np.arange(motion_dim, motion_dim + 2)
        y[..., columns] *= phi
        f[..., columns, columns] = phi
    predicted = f @ p @ _transpose(f) + g @ q @ _transpose(g)
    if colored_phi is not None:
        predicted[..., columns, columns] += (1 - phi**2) * target
    if restart_pose is not None:
        pose = np.broadcast_to(restart_pose, y.shape[:-1] + (3,))
        if (not np.isfinite(pose).all() or np.any(np.asarray(distance_m) != 0)
                or (angular_travel_rad is not None and np.any(np.asarray(angular_travel_rad) != 0))):
            raise ValueError("A frame restart requires a finite transform and zero distance/rotation travel")
        angle = pose[..., 2]
        c, s = np.cos(angle), np.sin(angle)
        rot = np.stack((c, -s, s, c), axis=-1).reshape(angle.shape + (2, 2))
        y[..., :2] = (rot @ y[..., :2, None])[..., 0] + pose[..., :2]
        y[..., 2] = _wrap(y[..., 2] + angle)
        a = np.broadcast_to(np.eye(y.shape[-1]), f.shape).copy()
        a[..., :2, :2] = rot
        predicted = a @ predicted @ _transpose(a)
    return y, _symmetrize(predicted)


def range_model(mean, anchor_xy, anchor_dz, range_offset_m=0.0):
    """Slant range with a supplied additive S1 offset and analytic Jacobian."""
    x = np.asarray(mean, dtype=float)
    delta = x[..., :2] - anchor_xy
    rho = np.sqrt(np.sum(delta**2, axis=-1) + np.square(anchor_dz))
    if not np.isfinite(rho).all() or np.any(rho <= 0):
        raise ValueError("Slant range derivative requires a finite nonzero separation")
    h = rho + range_offset_m
    jacobian = np.zeros_like(x)
    jacobian[..., :2] = delta / rho[..., None]
    return h, jacobian


def update_rf(mean, cov, z, anchor_xy, anchor_dz, range_offset_m, R, *, arm, motion_dim=4,
              s_expected=None, s_jacobian=None, colored_columns=None, consider_s=None, ci_weight=None):
    """One frozen-linearization batched RF update and per-run diagnostics.

    z and R use [range, s] order. R4 consumes only the range component.
    The caller is responsible for selecting/assembling R: in J-V it includes
    radial colored variance; in J-C/J-CS it excludes variance already in the
    state. Signed s and its [x, y, psi] derivatives are evaluated by the caller
    at this predicted mean. Joint arms require both measurements and finite
    model evaluations. Missing observations are flagged separately from NIS
    rejection. All gates use the nominal innovation covariance.

    J-C/J-CS use explicit colored_columns=(motion_dim, motion_dim+1). Trailing
    Schmidt states have zero fixed mean and consider_s gives their loadings on
    signed s in full-state order. J-CS and +K requests must provide these.
    J-CI uses explicit prior CI weight w: inflate P by 1/w and R by 1/(1-w).
    For J-CI+K only the active covariance block is inflated, holding the fixed
    Schmidt block and prior cross covariance on their supplied scales. This
    is a positive semidefinite inflation of the supplied covariance.
    """
    base_arm = arm.removesuffix("+K")
    use_k = arm.endswith("+K")
    if base_arm not in RF_ARMS or (use_k and base_arm == "R4"):
        raise ValueError(f"Unsupported MODEL-003 RF arm {arm}")
    x = np.asarray(mean, dtype=float)
    if x.ndim == 0 or motion_dim not in (4, 5) or x.shape[-1] < motion_dim or not np.isfinite(x).all():
        raise ValueError("Expected finite EKF means with 4 or 5 motion coordinates")
    prefix, n = x.shape[:-1], x.shape[-1]
    p = np.broadcast_to(cov, prefix + (n, n))
    if not np.isfinite(p).all():
        raise ValueError("Expected finite filter covariances")
    joint = base_arm != "R4"
    count = 2 if joint else 1
    z = np.broadcast_to(z, prefix + (2,))[..., :count]
    noise = np.broadcast_to(R, prefix + (2, 2))[..., :count, :count]
    h = np.zeros(prefix + (count,))
    H = np.zeros(prefix + (count, n))
    h[..., 0], H[..., 0, :] = range_model(x, anchor_xy, anchor_dz, range_offset_m)
    if joint:
        if s_expected is None or s_jacobian is None:
            raise ValueError("A joint RF update requires signed s and its analytic or LUT Jacobian")
        h[..., 1] = s_expected
        H[..., 1, :3] = s_jacobian

    colored = base_arm in {"J-C", "J-CS"}
    n_active = motion_dim + (2 if colored else 0)
    if colored:
        if colored_columns is None or tuple(colored_columns) != (motion_dim, motion_dim + 1) or n < n_active:
            raise ValueError("Expected active colored columns immediately after the motion state")
        h += x[..., list(colored_columns)]
        H[..., 0, colored_columns[0]] = H[..., 1, colored_columns[1]] = 1.0
    elif colored_columns is not None:
        raise ValueError("Colored coordinates are restricted to J-C and J-CS")
    schmidt = base_arm == "J-CS" or use_k
    if schmidt:
        if n == n_active or consider_s is None or np.any(x[..., n_active:] != 0):
            raise ValueError("Expected appended, zero-mean Schmidt coordinates and their s loadings")
        loadings = np.broadcast_to(consider_s, prefix + (n,))
        if np.any(loadings[..., :n_active] != 0) or not np.isfinite(loadings).all():
            raise ValueError("Schmidt loadings must be finite and zero on active coordinates")
        H[..., 1, n_active:] = loadings[..., n_active:]
    elif n != n_active or consider_s is not None:
        raise ValueError("Unexpected extra filter coordinates or Schmidt loadings")
    if base_arm == "J-CI":
        if ci_weight is None or not np.isfinite(ci_weight) or not 0 < ci_weight < 1:
            raise ValueError("J-CI requires a prefrozen prior weight in (0, 1)")
    elif ci_weight is not None:
        raise ValueError("CI weight is restricted to J-CI")

    residual = z - h
    available = np.isfinite(residual).all(axis=-1) & np.isfinite(H).all(axis=(-2, -1))
    nis = np.full(prefix, np.nan)
    accepted = np.zeros(prefix, dtype=bool)
    x_out, p_out = x.copy(), p.copy()
    if available.any():
        pp, jac, rr, nu = p[available], H[available], noise[available], residual[available]
        if not np.isfinite(rr).all() or not np.allclose(rr, _transpose(rr), atol=1e-14, rtol=1e-12):
            raise ValueError("Expected finite symmetric RF measurement covariance")
        np.linalg.cholesky(rr)
        innovation_cov = jac @ pp @ _transpose(jac) + rr
        np.linalg.cholesky(innovation_cov)
        nis[available] = np.sum(nu * np.linalg.solve(innovation_cov, nu[..., None])[..., 0], axis=-1)
        accepted = available & (nis <= (GATE_JOINT if joint else GATE_RANGE))
    if accepted.any():
        pp, jac, rr, nu = p[accepted].copy(), H[accepted], noise[accepted], residual[accepted]
        if base_arm == "J-CI":
            pp[..., :n_active, :n_active] /= ci_weight
            rr = rr / (1 - ci_weight)
        ph = pp @ _transpose(jac)
        gain = _transpose(np.linalg.solve(jac @ ph + rr, _transpose(ph)))
        gain[..., n_active:, :] = 0.0
        posterior = x[accepted] + (gain @ nu[..., None])[..., 0]
        posterior[..., 2] = _wrap(posterior[..., 2])
        a = np.eye(n) - gain @ jac
        x_out[accepted] = posterior
        p_out[accepted] = _symmetrize(a @ pp @ _transpose(a) + gain @ rr @ _transpose(gain))
    return x_out, p_out, dict(nis=nis, available=available, accepted=accepted, rejected=available & ~accepted,
                              innovation=residual)


def self_check():
    """Synthetic Jacobian, gating, Schmidt and frame tests without RF data."""
    x = np.array([1.0, -2.0, 0.4, 0.012, 0.003])
    y, f, g = transition_motion(x, 0.4, -0.15, 0.2, motion_dim=5, angular_travel_rad=0.17)
    eps = 1e-6
    fd = np.column_stack([(transition_motion(x + d, 0.4, -0.15, 0.2, motion_dim=5, angular_travel_rad=0.17)[0]
                           - transition_motion(x - d, 0.4, -0.15, 0.2, motion_dim=5, angular_travel_rad=0.17)[0])
                          / (2 * eps) for d in eps * np.eye(len(x))])
    np.testing.assert_allclose(f, fd, atol=1e-9, rtol=0)
    controls = np.array([0.4, -0.15])
    fd = np.column_stack([(transition_motion(x, *(controls + d), 0.2, motion_dim=5, angular_travel_rad=0.17)[0]
                           - transition_motion(x, *(controls - d), 0.2, motion_dim=5, angular_travel_rad=0.17)[0])
                          / (2 * eps) for d in eps * np.eye(2)])
    np.testing.assert_allclose(g, fd, atol=1e-9, rtol=0)
    np.testing.assert_allclose(y[2], x[2] - 0.15 - x[3] * 0.2 - x[4] * 0.17, atol=1e-14)

    p0 = initial_covariance()
    p5 = initial_covariance(0.01)
    np.testing.assert_array_equal(p5[:4, :4], p0)
    x4 = np.array([3., 4., 0.1, 0.0])
    asymmetric = p0 + np.diag([0.04, 0., 0., 0.])
    x_restart, p_restart = predict(x4, asymmetric, 0.0, 0.2, 0.2, restart_pose=[7.0, 2.0, np.pi / 2])
    np.testing.assert_allclose(x_restart, [3.0, 5.0, 0.3 + np.pi / 2, 0.0], atol=1e-14)
    rotated_indices = [1, 0, 2, 3]
    p_continuous = predict(x4, asymmetric, 0.0, 0.2, 0.2)[1]
    np.testing.assert_allclose(p_restart, p_continuous[np.ix_(rotated_indices, rotated_indices)], atol=1e-14)
    h, H = range_model(x4, [0., 0.], 12.0, 0.1)
    np.testing.assert_allclose([h, *H], [13.1, 3. / 13, 4. / 13, 0., 0.], atol=1e-14)

    joint = dict(anchor_xy=[0., 0.], anchor_dz=12.0, range_offset_m=0.1, R=np.diag([0.09, 0.01]),
                 s_expected=0.2, s_jacobian=[0., 0., -0.5])
    samples = [[h + 0.1, 0.3], [h + 10.0, 0.3], [h + 0.1, np.nan]]
    states = np.broadcast_to(x4, (3, 4))
    xx, pp, gate = update_rf(states, p0, samples, **joint, arm="J4")
    np.testing.assert_array_equal(gate["accepted"], [True, False, False])
    np.testing.assert_array_equal(gate["rejected"], [False, True, False])
    np.testing.assert_array_equal(gate["available"], [True, True, False])
    np.testing.assert_array_equal(xx[1:], states[1:])
    np.testing.assert_array_equal(pp[1:], np.broadcast_to(p0, (2, 4, 4)))
    np.testing.assert_array_equal(update_rf(states, p0, samples, **joint, arm="R4")[2]["accepted"],
                                  [True, False, True])
    if not xx[0, 2] < x4[2]:
        raise AssertionError("Signed s derivative should produce a negative yaw correction")

    xc = np.r_[x4, 0., 0., 0.]
    pc = np.diag(np.r_[p0.diagonal(), 0.02, 0.03, 0.04])
    xc1, pc1 = predict(xc, pc, 0.0, 0.0, 0.2, colored_phi=[0.5, 0.75], colored_target=[0.04, 0.06])
    np.testing.assert_allclose(pc1.diagonal()[-3:], [0.035, 0.043125, 0.04])
    xc2, pc2, status = update_rf(xc1, pc1, samples[0], **joint, arm="J-CS", colored_columns=[4, 5],
                                 consider_s=[0, 0, 0, 0, 0, 0, 1])
    np.testing.assert_array_equal([xc2[-1], pc2[-1, -1]], [0.0, pc[-1, -1]])
    if not status["accepted"] or np.linalg.eigvalsh(pc2).min() <= 0 or pc2[2, -1] == 0:
        raise AssertionError("Schmidt update must preserve its variance and carry cross-covariance")
    xi, pi, gate_i = update_rf(x4, p0, samples[0], **joint, arm="J-CI", ci_weight=0.5)
    np.testing.assert_allclose(xi, xx[0], atol=1e-14)
    np.testing.assert_allclose(pi, 2 * pp[0], atol=1e-14)
    np.testing.assert_allclose(gate_i["nis"], gate["nis"][0], atol=1e-14)
    xk = np.r_[x4, 0.]
    pk = np.diag(np.r_[p0.diagonal(), 0.04])
    pk[2, -1] = pk[-1, 2] = 0.002
    for arm in ("J4+K", "J-V+K", "J-CI+K"):
        options = {"ci_weight": 0.5} if arm == "J-CI+K" else {}
        xk_out, pk_out, status = update_rf(xk, pk, samples[0], **joint, arm=arm,
                                          consider_s=[0, 0, 0, 0, 1], **options)
        if not status["accepted"] or np.linalg.eigvalsh(pk_out).min() <= 0:
            raise AssertionError("Expected accepted positive-definite +K update")
        np.testing.assert_array_equal([xk_out[-1], pk_out[-1, -1]], [0.0, pk[-1, -1]])
    return "PASS"


if __name__ == "__main__":
    print(f"MODEL-003 synthetic EKF math: {self_check()}")
