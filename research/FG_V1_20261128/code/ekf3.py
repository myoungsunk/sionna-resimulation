"""Re-implementation of the M7 H2 EKF path (own R_ref, own NIS gate, no q_table, no joint state).

nstate=4 reproduces M7 H2 ([px, py, yaw, b_g]); nstate=3 drops the gyro-bias state.
hfun(nav3) -> (h[2], H[2,3]) lets the same filter run on the FFD model or on a surrogate.
"""
import math
import numpy as np

GATE_2D = 9.210340371976184
GYRO_N = {"B0": .015, "L2_GYRO_ARW": .060}
KNOTS = np.array([0., 1.5, 3., 6., 10.])


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def transition(x, ds, gy, dt):
    """core.transition for 3- or 4-state; returns y, F, G (G columns: ds, gyro angle[, bias])."""
    n = len(x)
    b = x[3] if n == 4 else 0.
    a = gy - b * dt
    if abs(a) < 1e-4:
        a2 = a * a
        c, dc = 1 - a2 / 24 + a2 * a2 / 1920 - a2 ** 3 / 322560, -a / 12 + a ** 3 / 480 - a ** 5 / 53760
    else:
        h = a / 2
        c, dc = math.sin(h) / h, (h * math.cos(h) - math.sin(h)) / (2 * h * h)
    phi = x[2] + a / 2
    u = np.array([math.cos(phi), math.sin(phi)])
    up = np.array([-u[1], u[0]])
    d = ds * c * u
    v = ds * (dc * u + c * up / 2)
    y = np.array(x, float).copy()
    y[:2] += d
    y[2] = wrap(x[2] + a)
    F = np.eye(n)
    F[:2, 2] = [-d[1], d[0]]
    G = np.zeros((n, 3 if n == 4 else 2))
    G[:2, 0] = c * u
    G[:2, 1] = v
    G[2, 1] = 1.
    if n == 4:
        F[:2, 3] = -dt * v
        F[2, 3] = -dt
        G[3, 2] = 1.
    return y, F, G


def q_input(ds, dt, N, n):
    q = [2e-5 * abs(ds), math.radians(N) ** 2 * dt]
    return np.diag(q + [0.] if n == 4 else q)


def sym(P):
    return (P + P.T) * .5


def replay(pkt, hfun, condition="B0", nstate=3, sigma_b=0.005, fixed_mask=None, anchor=None):
    N = GYRO_N[condition]
    sig_vals = np.full(len(KNOTS), sigma_b) if np.isscalar(sigma_b) else np.asarray(sigma_b, float)
    x = np.array(pkt["x0"][:nstate], float)
    P = np.array(pkt["P0"][:nstate, :nstate], float)
    n = len(pkt["t"])
    out = {k: [] for k in ("x", "P", "prior", "Pprior", "h", "H", "Reff", "nu", "S", "nis", "mask", "rho")}
    for i in range(n):
        rho = math.hypot(x[0] - anchor[0], x[1] - anchor[1])
        R = pkt["R"][i].copy()
        R[1, 1] += float(np.interp(rho, KNOTS, sig_vals)) ** 2
        if i:
            ds, gy, dt = (float(pkt[k][i]) for k in ("ds", "gy", "dt"))
            y, F, G = transition(x, ds, gy, dt)
            Pp = sym(F @ P @ F.T + G @ q_input(ds, dt, N, nstate) @ G.T)
        else:
            y, Pp = x.copy(), P.copy()
        h, H3 = hfun(y[:3])
        H = np.zeros((2, nstate)); H[:, :3] = H3
        nu = pkt["z"][i] - h - pkt["muMB"][i]
        S = sym(H @ Pp @ H.T + R)
        nis = float(nu @ np.linalg.solve(S, nu))
        acc = bool(nis <= GATE_2D) if fixed_mask is None else bool(fixed_mask[i])
        if acc:
            K = np.linalg.solve(S, H @ Pp).T
            xn = y + K @ nu
            xn[2] = wrap(xn[2])
            A = np.eye(nstate) - K @ H
            Pn = sym(A @ Pp @ A.T + K @ R @ K.T)
        else:
            xn, Pn = y, Pp
        for k, v in (("x", xn), ("P", Pn), ("prior", y), ("Pprior", Pp), ("h", h), ("H", H), ("Reff", R),
                     ("nu", nu), ("S", S), ("nis", nis), ("mask", acc), ("rho", rho)):
            out[k].append(v)
        x, P = xn, Pn
    return {k: np.array(v) for k, v in out.items()}
