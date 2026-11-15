"""Augmented EKF for SPEC_A D7. Covariances and angles use SI units."""
from dataclasses import dataclass

import numpy as np

from diag_replay import DISTANCE_NODES, INITIAL_STD, JOINT_GATE, predict_batch, wrap


@dataclass(frozen=True)
class Term:
    channel: int
    mode: str
    variance: float | tuple[float, ...]
    distance_length: float = np.inf
    yaw_length: float = np.inf

    def at_range(self, rho):
        if isinstance(self.variance, tuple):
            return np.interp(rho, DISTANCE_NODES, self.variance) ** 2
        return np.full_like(rho, self.variance)


def update(x, p, z, h, jacobian, mu, r, consider):
    innovation = z - h - mu
    hp = jacobian @ p
    s = hp @ jacobian.swapaxes(-1, -2) + r
    s = (s + s.swapaxes(-1, -2)) / 2
    gain = np.linalg.solve(s, hp).swapaxes(-1, -2)
    gain[:, consider] = 0.0
    nis = np.einsum("ni,ni->n", innovation, np.linalg.solve(s, innovation[..., None])[..., 0])
    accepted = nis <= JOINT_GATE
    y = x + np.einsum("nij,nj->ni", gain, innovation)
    y[:, 2] = wrap(y[:, 2])
    a = np.eye(x.shape[-1]) - gain @ jacobian
    c = a @ p @ a.swapaxes(-1, -2) + gain @ r @ gain.swapaxes(-1, -2)
    return (np.where(accepted[:, None], y, x),
            np.where(accepted[:, None, None], (c+c.swapaxes(-1, -2))/2, p),
            accepted, nis, innovation, gain)


def replay(data, controls, initial, terms, *, save_linearization=False):
    n_seeds = len(initial)
    t = data["t"]
    n_steps = len(t)
    white_terms = tuple(term for term in terms if term.mode == "white")
    terms = tuple(term for term in terms if term.mode != "white")
    n_states = 4 + len(terms)
    x = np.zeros((n_seeds, n_states))
    x[:, :3] = initial
    p = np.zeros((n_seeds, n_states, n_states))
    p[:, :4, :4] = np.diag(INITIAL_STD ** 2)
    anchor = np.asarray(data["case"]["anchor"][:2])
    ds, gyro = [controls[k].T for k in ("ds_odom", "dtheta_gyro")]
    consider = [index for index, term in enumerate(terms, 4) if term.mode == "consider"]
    out = {
        "state": np.empty((n_seeds, n_steps, 4)),
        "covariance": np.empty((n_seeds, n_steps, 4, 4)),
        "accepted": np.empty((n_seeds, n_steps), dtype=bool),
        "nis": np.empty((n_seeds, n_steps)),
        "heading_update_rad": np.empty((n_seeds, n_steps)),
    }
    if save_linearization:
        out.update({
            "transition": np.empty((n_seeds, n_steps, n_states, n_states)),
            "jacobian": np.empty((n_seeds, n_steps, 2, n_states)),
            "gain": np.empty((n_seeds, n_steps, n_states, 2)),
            "innovation": np.empty((n_seeds, n_steps, 2)),
        })
    for k in range(n_steps):
        rho = np.linalg.norm(x[:, :2] - anchor, axis=1)
        f = np.broadcast_to(np.eye(n_states), p.shape).copy()
        if k:
            dt = t[k] - t[k-1]
            yaw_step = np.abs(wrap(gyro[k] - dt*x[:, 3]))
            prior, cov, f[:, :4, :4] = predict_batch(
                x[:, :4], p[:, :4, :4], ds[k], gyro[k], dt)
            scales = np.ones((n_seeds, n_states))
            process = np.zeros_like(scales)
            for i, term in enumerate(terms, 4):
                if term.mode == "ar":
                    exponent = np.abs(ds[k])/term.distance_length + yaw_step/term.yaw_length
                    scales[:, i] = np.exp(-exponent)
                    process[:, i] = term.at_range(rho) * -np.expm1(-2*exponent)
                f[:, i, i] = scales[:, i]
            p = (f @ p @ f.swapaxes(-1, -2))
            p[:, :4, :4] = cov
            diag = np.arange(n_states)
            p[:, diag, diag] += process
            x[:, 4:] *= scales[:, 4:]
            x[:, :4] = prior
        else:
            for i, term in enumerate(terms, 4):
                p[:, i, i] = term.at_range(rho)
        h, base_jacobian = data["model"](x[:, :4], data["case"])
        h = h.copy()
        jacobian = np.zeros((n_seeds, 2, n_states))
        jacobian[:, :, :4] = base_jacobian
        for i, term in enumerate(terms, 4):
            h[:, term.channel] += x[:, i]
            jacobian[:, term.channel, i] = 1.0
        r = data["R"][k]
        if white_terms:
            r = np.broadcast_to(r, (n_seeds, 2, 2)).copy()
            for term in white_terms:
                r[:, term.channel, term.channel] += term.at_range(rho)
        x, p, accepted, nis, innovation, gain = update(
            x, p, data["z"][k], h, jacobian, data["mu"][k], r, consider)
        if not np.isfinite(x).all() or not np.isfinite(p).all():
            raise FloatingPointError(f"Non-finite augmented posterior at frame {k}")
        out["state"][:, k] = x[:, :4]
        out["covariance"][:, k] = p[:, :4, :4]
        out["accepted"][:, k] = accepted
        out["nis"][:, k] = nis
        update_yaw = np.einsum("ni,ni->n", gain[:, 2], innovation)
        out["heading_update_rad"][:, k] = np.where(accepted, np.abs(update_yaw), 0.0)
        if save_linearization:
            out["transition"][:, k] = f
            out["jacobian"][:, k] = jacobian
            out["gain"][:, k] = gain
            out["innovation"][:, k] = innovation
    joint = np.ones_like(out["accepted"])
    return {**out, "joint": joint, "proposal": joint}
