"""Batch independent W0 E0 recursions over a frozen packet mask."""

import math

import numpy as np


HAND_DISTANCE = (0., 1.5, 3., 6., 10.)
HAND_SIGMA = (.011, .020, .050, .120, .240)


def _sinc_half(angle):
    """Vectorized EKF4 sinc_half, including its small-angle derivative."""
    small = np.abs(angle) < 1e-4
    c = np.empty_like(angle)
    dc = np.empty_like(angle)
    a = angle[small]
    a2 = a * a
    c[small] = 1 - a2 / 24 + a2 * a2 / 1920 - a2**3 / 322560
    dc[small] = -a / 12 + a**3 / 480 - a**5 / 53760
    half = angle[~small] / 2
    sn = np.sin(half)
    c[~small] = sn / half
    dc[~small] = (half * np.cos(half) - sn) / (2 * half * half)
    return c, dc


def _sym(matrix):
    return (matrix + matrix.swapaxes(-1, -2)) * .5


def _predict(core, x, P, ds, gyro, dt, Q):
    angle = gyro - x[:, 3] * dt
    c, dc = _sinc_half(angle)
    phi = x[:, 2] + angle / 2
    cosine, sine = np.cos(phi), np.sin(phi)
    unit = np.column_stack((cosine, sine))
    unit_perp = np.column_stack((-sine, cosine))
    d = ds * c[:, None] * unit
    v = ds * (dc[:, None] * unit + c[:, None] * unit_perp / 2)

    prior = x.copy()
    prior[:, :2] += d
    prior[:, 2] = core.wrap(x[:, 2] + angle)
    F = np.broadcast_to(np.eye(4), (len(x), 4, 4)).copy()
    F[:, 0, 2], F[:, 1, 2] = -d[:, 1], d[:, 0]
    F[:, :2, 3] = -dt * v
    F[:, 2, 3] = -dt
    G = np.zeros((len(x), 4, 3))
    G[:, :2, 0] = c[:, None] * unit
    G[:, :2, 1] = v
    G[:, 2, 1] = 1.
    G[:, 3, 2] = 1.
    return prior, _sym(F @ P @ F.swapaxes(-1, -2) + G @ Q @ G.swapaxes(-1, -2))


def replay_batch(core, online, model, spec, packet, fixed_mask, observations, *,
                 batch_size=32, return_trace=False, sigma_knots=None):
    """Run E0 over [realization, packet, channel] observations.

    Each branch has its own previous posterior for the native sigma lookup and
    every branch uses the supplied immutable acceptance mask. The full trace
    is intended for parity checks, while ordinary scoring only needs x and P.
    """
    n_packets = len(packet["t"])
    mask = np.asarray(fixed_mask)
    z = np.asarray(observations, dtype=float)
    if (n_packets == 0 or mask.shape != (n_packets,) or mask.dtype.kind != "b"
            or z.ndim != 3 or z.shape[1:] != (n_packets, 2)
            or not len(z) or not np.isfinite(z).all() or batch_size <= 0):
        raise ValueError("Invalid E0 batch observations, mask, or batch size")
    ds, gyro, dt = (np.asarray(packet[key], dtype=float) for key in ("ds", "gy", "dt"))
    if (any(value.shape != (n_packets,) or not np.isfinite(value[1:]).all()
            for value in (ds, gyro, dt)) or np.any(dt[1:] <= 0)):
        raise ValueError("Invalid E0 control increments")
    x0 = core.state_vector(np.r_[packet["x0"][:3], 0.])
    P0 = np.asarray(packet["P0"], dtype=float)
    core.covariance(P0, 4)
    base_R = np.asarray(packet["R"], dtype=float)
    means = np.asarray(packet["muMB"], dtype=float)
    if (base_R.shape != (n_packets, 2, 2) or means.shape != (n_packets, 2)
            or not np.isfinite(base_R).all() or not np.isfinite(means).all()):
        raise ValueError("Invalid E0 calibration arrays")
    distance, sigma = ((HAND_DISTANCE, HAND_SIGMA) if sigma_knots is None
                       else sigma_knots)
    distance, sigma = np.asarray(distance), np.asarray(sigma)
    if (distance.ndim != 1 or len(distance) < 2 or sigma.shape != distance.shape
            or not np.isfinite(distance).all() or not np.isfinite(sigma).all()
            or np.any(np.diff(distance) <= 0) or np.any(sigma <= 0)):
        raise ValueError("Invalid E0 sigma knots")
    if online.weight("W0", 0., 0.) != 1.:
        raise ValueError("Expected unit-weight W0")

    Q = np.zeros((n_packets, 3, 3))
    Q[1:, 0, 0] = 2e-5 * np.abs(ds[1:])
    Q[1:, 1, 1] = math.radians(.015)**2 * dt[1:]
    anchor_x, anchor_y = spec["anchor"][:2]
    fields = {"x": (4,), "P": (4, 4)}
    if return_trace:
        fields.update(prior=(4,), Pprior=(4, 4), h=(2,), H=(2, 4), mu=(2,),
                      Rvar=(2, 2), Reff=(2, 2), K=(4, 2), nu=(2,), S=(2, 2),
                      d0=(), weight=(), sigma_b=(), rho_before=(), nis=())
    traces = {key: np.empty((len(z), n_packets, *shape)) for key, shape in fields.items()}
    for start in range(0, len(z), batch_size):
        subset = slice(start, start + batch_size)
        zs = z[subset]
        count = len(zs)
        x = np.broadcast_to(x0, (count, 4)).copy()
        P = np.broadcast_to(P0, (count, 4, 4)).copy()
        for k in range(n_packets):
            xp, pp = (x, P) if k == 0 else _predict(core, x, P, ds[k], gyro[k], dt[k], Q[k])
            x_next, P_next = xp, pp
            if mask[k] or return_trace:
                # The frozen W0 lookup uses the previous posterior, before predict.
                rho = np.hypot(x[:, 0] - anchor_x, x[:, 1] - anchor_y)
                sb = np.interp(rho, distance, sigma)
                R = np.broadcast_to(base_R[k], (count, 2, 2)).copy()
                R[:, 1, 1] += sb**2
                h, H = model.batch(xp, spec)
                nu = zs[:, k] - h - means[k]
                S = _sym(H @ pp @ H.swapaxes(-1, -2) + R)
                if mask[k]:
                    gain = np.linalg.solve(S, H @ pp).swapaxes(-1, -2)
                    x_next = xp + (gain @ nu[..., None])[..., 0]
                    x_next[:, 2] = core.wrap(x_next[:, 2])
                    A = np.eye(4) - gain @ H
                    P_next = _sym(A @ pp @ A.swapaxes(-1, -2) + gain @ R @ gain.swapaxes(-1, -2))
                else:
                    gain = np.zeros((count, 4, 2))
            x, P = x_next, P_next
            traces["x"][subset, k] = x
            traces["P"][subset, k] = P
            if return_trace:
                nis = (nu[:, None, :] @ np.linalg.solve(S, nu[..., None]))[:, 0, 0]
                extras = dict(prior=xp, Pprior=pp, h=h, H=H, mu=means[k], Rvar=R,
                              Reff=R, K=gain, nu=nu, S=S, d0=zs[:, k, 1]-h[:, 1],
                              weight=1., sigma_b=sb, rho_before=rho, nis=nis)
                for key, value in extras.items():
                    traces[key][subset, k] = value
    if not all(np.isfinite(value).all() for value in traces.values()):
        raise ValueError("Nonfinite E0 batch trace")
    if return_trace:
        traces["mask"] = np.broadcast_to(mask, (len(z), n_packets)).copy()
    return traces
