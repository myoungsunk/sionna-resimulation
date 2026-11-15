"""Batch the frozen four-state recurrence across independent sensor paths and phases."""
import math

import numpy as np

from diag_mechanism import joint_mask


INITIAL_STD = np.r_[.1, .1, math.radians(5), math.radians(.1)]
JOINT_GATE = 9.210340371976184
RANGE_GATE = 6.6348966010212145
DISTANCE_NODES = [0., 1.5, 3., 6., 10.]
SIGMA_NODES = [.011, .020, .050, .120, .240]


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def predict_batch(x, p, ds, gyro, dt):
    """Array form of core.transition and the frozen predict_one covariance."""
    a = gyro - x[:, 3] * dt
    a2 = a*a
    half = a/2
    small = np.abs(a) < 1e-4
    safe_half = np.where(small, 1., half)
    c = np.where(small, 1-a2/24+a2*a2/1920-a2**3/322560, np.sin(half)/safe_half)
    dc = np.where(small, -a/12+a**3/480-a**5/53760,
                  (half*np.cos(half)-np.sin(half))/(2*safe_half*safe_half))
    phi = x[:, 2] + half
    u = np.column_stack([np.cos(phi), np.sin(phi)])
    up = np.column_stack([-u[:, 1], u[:, 0]])
    d = ds[:, None] * c[:, None] * u
    v = ds[:, None] * (dc[:, None]*u+c[:, None]*up/2)
    xp = x.copy()
    xp[:, :2] += d
    xp[:, 2] = wrap(x[:, 2]+a)
    f = np.broadcast_to(np.eye(4), p.shape).copy()
    f[:, 0, 2], f[:, 1, 2] = -d[:, 1], d[:, 0]
    f[:, :2, 3] = -dt*v
    f[:, 2, 3] = -dt
    g = np.zeros((len(x), 4, 2))
    g[:, :2, 0] = c[:, None]*u
    g[:, :2, 1] = v
    g[:, 2, 1] = 1.
    q = np.column_stack([2e-5*np.abs(ds), np.full(len(x), math.radians(.015)**2*dt)])
    covariance = f@p@f.swapaxes(1, 2)+(g*q[:, None, :])@g.swapaxes(1, 2)
    return xp, (covariance+covariance.swapaxes(1, 2))/2, f


def range_model(x, anchor, height, ffd):
    xy = x[:, :2] - anchor
    if ffd:
        rho = np.hypot(xy[:, 0], xy[:, 1])
        dist = np.sqrt(rho*rho+height*height)
    else:
        xyz = np.column_stack([xy, np.full(len(x), -height)])
        dist = np.sqrt(np.sum(xyz*xyz, axis=1))
    h = (dist-.5315983906250129)[:, None]
    H = np.zeros((len(x), 1, 4))
    H[:, 0, :2] = xy/dist[:, None]
    return h, H


def update_batch(x, p, z, h, H, mu, R, gate):
    """Frozen NIS and Joseph update, using scalar solve for range-only."""
    nu = z-h-mu
    hp = H@p
    S = hp@H.swapaxes(1, 2)+R
    S = (S+S.swapaxes(1, 2))/2
    if H.shape[1] == 1:
        K = (hp/S).swapaxes(1, 2)
        nis = nu[:, 0]**2/S[:, 0, 0]
    else:
        K = np.linalg.solve(S, hp).swapaxes(1, 2)
        nis = np.einsum("ni,ni->n", nu, np.linalg.solve(S, nu[..., None])[..., 0])
    accepted = nis <= gate
    new_x = x + np.einsum("nij,nj->ni", K, nu)
    new_x[:, 2] = wrap(new_x[:, 2])
    A = np.eye(4)-K@H
    new_p = A@p@A.swapaxes(1, 2)+K@R@K.swapaxes(1, 2)
    new_p = (new_p+new_p.swapaxes(1, 2))/2
    return (np.where(accepted[:, None], new_x, x),
            np.where(accepted[:, None, None], new_p, p), accepted, nis, nu, K)


def replay(model, case, z, mu, R, t, controls, x0, configs, *,
           oracle=None, variance=False, ffd=False, save_linearization=False):
    """List configs in phase-major order. m=0 means range-only, m=-1 means DR."""
    n = len(t)
    seed_count = len(x0)
    n_runs = len(configs)*seed_count
    anchor = np.asarray(case["anchor"][:2])
    height = case["anchor"][2]-case["robot_z_m"]
    joint = np.stack([joint_mask(n, m, p) if m > 0 else np.zeros(n, bool) for m, p in configs])
    opportunity = np.asarray([m >= 0 for m, _ in configs])
    xs = np.tile(np.column_stack([x0, np.zeros(seed_count)]), (len(configs), 1))
    ps = np.tile(np.diag(INITIAL_STD**2), (n_runs, 1, 1))
    states = np.empty((n, n_runs, 4))
    covs = np.empty((n, n_runs, 4, 4))
    accepted = np.zeros((n, n_runs), bool)
    nis = np.full((n, n_runs), np.nan)
    linear = {}
    if save_linearization:
        if configs != [(1, 0)]:
            raise ValueError("Linearization is recorded for the unmodified J4 only")
        linear = {
            "transition": np.empty((n, n_runs, 4, 4)),
            "jacobian": np.empty((n, n_runs, 2, 4)),
            "gain": np.empty((n, n_runs, 4, 2)),
            "innovation": np.empty((n, n_runs, 2)),
        }
    ds, gyro = (np.tile(controls[key].T, (1, len(configs))) for key in ("ds_odom", "dtheta_gyro"))
    proposal = np.broadcast_to(np.repeat(opportunity, seed_count), (n, n_runs))
    for k in range(n):
        if variance:
            rho = np.linalg.norm(xs[:, :2]-anchor, axis=1)
        if k:
            xs, ps, f = predict_batch(xs, ps, ds[k], gyro[k], t[k]-t[k-1])
        elif save_linearization:
            f = np.tile(np.eye(4), (n_runs, 1, 1))
        is_joint = np.repeat(joint[:, k], seed_count)
        for selected, use_joint in ((is_joint, True), (proposal[k] & ~is_joint, False)):
            if not selected.any():
                continue
            x, p = xs[selected], ps[selected]
            if use_joint:
                h, H = model(x, case)
                cov = np.broadcast_to(R[k], (len(x), 2, 2))
                obs = z[k].copy()
                if oracle is not None:
                    obs[1] -= oracle[k]
                if variance:
                    cov = cov.copy()
                    cov[:, 1, 1] += np.interp(rho[selected], DISTANCE_NODES, SIGMA_NODES)**2
                mean = mu[k]
                gate = JOINT_GATE
            else:
                h, H = range_model(x, anchor, height, ffd)
                cov, obs, mean = R[k, :1, :1], z[k, :1], mu[k, :1]
                gate = RANGE_GATE
            y, C, yes, q, nu, K = update_batch(x, p, obs, h, H, mean, cov, gate)
            xs[selected], ps[selected] = y, C
            accepted[k, selected], nis[k, selected] = yes, q
            if save_linearization:
                linear["transition"][k] = f
                linear["jacobian"][k] = H
                linear["gain"][k] = K
                linear["innovation"][k] = nu
        states[k], covs[k] = xs, ps
    if not np.isfinite(states).all() or not np.isfinite(covs).all():
        raise FloatingPointError("Nonfinite replay state or covariance")
    return {"state": states.swapaxes(0, 1), "covariance": covs.swapaxes(0, 1),
            "accepted": accepted.T, "nis": nis.T, "joint": np.repeat(joint, seed_count, axis=0),
            "proposal": proposal.T, **{k: v.swapaxes(0, 1) for k, v in linear.items()}}
