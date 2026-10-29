"""AMENDMENT-008 §2: Jacobian conventions for post-fit covariance at a fixed MAP estimate (pure numpy; no FFD import).

hval(X) -> h (n,2). The analytic Jacobian is supplied by the caller; the FD conventions below are defined here.
"""
from __future__ import annotations

import numpy as np

PSI_PER_M = 0.17453292519943295          # 10 deg per metre-equivalent step
BG_STEP = 1e-6
METHODS = {"A": None, "C03": ("central", 3e-3), "C10": ("central", 1e-2), "C30": ("central", 3e-2),
           "L": ("backward", 1e-7), "R": ("forward", 1e-7)}
PRIMARY = "C10"


def steps(s):
    return np.array([s, s, PSI_PER_M * s, BG_STEP])


def fd_H(hval, X, mode, s, h0=None):
    X = np.asarray(X, float); st = steps(s); n = len(X)
    h0 = hval(X) if (h0 is None and mode != "central") else h0
    H = np.zeros((n, 2, 4))
    for j in range(4):
        d = np.zeros(4); d[j] = st[j]
        if mode == "central":
            H[:, :, j] = (hval(X + d) - hval(X - d)) / (2 * st[j])
        elif mode == "forward":
            H[:, :, j] = (hval(X + d) - h0) / st[j]
        elif mode == "backward":
            H[:, :, j] = (h0 - hval(X - d)) / st[j]
        else:
            raise ValueError(mode)
    return H


def h_batch_for(method, h_batch):
    """Wrap an analytic h_batch(X)->(h,H) into the requested Jacobian convention."""
    if METHODS[method] is None:
        return h_batch
    mode, s = METHODS[method]

    def hb(X):
        h, _ = h_batch(X)
        return h, fd_H(lambda Y: h_batch(Y)[0], X, mode, s, h0=h)
    return hb


def fixture_piecewise():
    """Kink fixture: h(x) = 2x for x<0, 5x for x>=0 on the x state; quadratic (central-FD exact) elsewhere.
    Returns (hval, X_at_kink, X_smooth). Analytic H at X_smooth: [[5, 0.1, 0, 0], [0, y, 0.3, 0]]."""
    def hval(X):
        x = X[:, 0]; y = X[:, 1]
        return np.c_[np.where(x < 0, 2 * x, 5 * x) + 0.1 * y, 0.5 * y ** 2 + 0.3 * X[:, 2]]
    Xk = np.zeros((3, 4)); Xs = np.array([[0.4, 0.2, 0.1, 0.0]] * 3)
    return hval, Xk, Xs


def linear_h(anchor=(1.0, 2.0)):
    """LINEAR_EXACT fixture: h affine in the state (constant H), so every FD convention must equal the analytic H and the
    Gauss-Newton P of every method must coincide. Returns h_batch(X) -> (h, H)."""
    G = np.array([[0.8, -0.3, 0.0, 0.0], [0.2, 0.5, 0.7, 0.0]]); c = np.array([anchor[0], anchor[1]])

    def hb(X):
        X = np.asarray(X, float)
        return X @ G.T + c, np.broadcast_to(G, (len(X), 2, 4)).copy()
    return hb
