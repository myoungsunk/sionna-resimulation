"""MBVAR-INFO-001 estimators.

ekf(): recursive single-anchor EKF with the exact arithmetic of pol_bias_model/exp_pb.run (sigma_b from the posterior
before prediction, same Q, Joseph update); hooks: per-packet R, optional own NIS gate, optional fixed acceptance mask.
batch_map(): Gauss-Newton MAP over theta=(x0, v_1..v_N) with x_k = f(x_{k-1}, u_k + v_k), v_k ~ N(0, q_k[:2,:2]);
b_g has zero process noise and is therefore a constant inside x0 (exact, no pseudo-inverse). Measurement weighting with
an arbitrary (full or block-diagonal) observation covariance. Posterior state covariance from the final linearisation.
"""
from __future__ import annotations

import math

import numpy as np

from world import predict, wrap

Q_DS = 2e-5
Q_GY = math.radians(0.015) ** 2


def qmat(ds, dt):
    return np.diag([Q_DS * abs(ds), Q_GY * dt, 0.0])


def ekf(h_fn, z, mu, R_fn, ds, gy, dt, x0, P0, use=None, gate_thr=None, anchor_xy=None, sig_fn=None):
    """h_fn(x)->(h(2), H(2x4)); R_fn(k, sg)->R(2x2) where sg = sig_fn(rho_post_before_predict) (0 if sig_fn None).
    use: bool mask of packets to update (fixed gate); gate_thr: own joint NIS gate (overrides use)."""
    n = len(z); x = np.asarray(x0, float).copy(); P = np.asarray(P0, float).copy()
    X = np.zeros((n, 4)); PX = np.zeros((n, 4, 4)); NIS = np.full(n, np.nan); used = np.zeros(n, bool)
    for k in range(n):
        rh = math.hypot(x[0] - anchor_xy[0], x[1] - anchor_xy[1]) if anchor_xy is not None else 0.0
        sg = sig_fn(rh) if sig_fn is not None else 0.0
        if k:
            dsk, gyk, dtk = float(ds[k]), float(gy[k]), float(dt[k])
            x, P, _, _ = predict(x, P, dsk, gyk, dtk, qmat(dsk, dtk))
        if np.isfinite(z[k]).all():
            h, H = h_fn(x)
            Rk = R_fn(k, sg)
            v = z[k] - h - mu[k]
            S_ = H @ P @ H.T + Rk; S_ = 0.5 * (S_ + S_.T)
            nis = float(v @ np.linalg.solve(S_, v)); NIS[k] = nis
            ok = (nis <= gate_thr) if gate_thr is not None else (True if use is None else bool(use[k]))
            if ok:
                K = np.linalg.solve(S_, H @ P).T
                y = x + K @ v; y[2] = wrap(y[2])
                A_ = np.eye(4) - K @ H; Pn = A_ @ P @ A_.T + K @ Rk @ K.T
                x = y; P = 0.5 * (Pn + Pn.T); used[k] = True
        X[k] = x; PX[k] = P
    return X, PX, NIS, used


def _rollout(x0, v, ds, gy, dt):
    n = len(ds); X = np.zeros((n, 4)); Fs = [np.eye(4)]; Gs = [np.zeros((4, 2))]
    X[0] = x0
    for k in range(1, n):
        q = qmat(ds[k] + v[k, 0], dt[k])
        y, _, F, G = predict(X[k - 1], np.zeros((4, 4)), float(ds[k] + v[k, 0]), float(gy[k] + v[k, 1]), float(dt[k]), q)
        X[k] = y; Fs.append(np.asarray(F)); Gs.append(np.asarray(G)[:, :2])
    return X, Fs, Gs


def batch_map(h_batch, z, mu, Sig_model, ds, gy, dt, m0, P0, iters=20, tol=1e-10):
    """Returns X_hat (n,4), Pstate list of 4x4 marginal covariances, info dict. h_batch(X)->(h(n,2), H(n,2,4))."""
    n = len(z)
    qv = np.array([[Q_DS * abs(ds[k]), Q_GY * dt[k]] for k in range(n)])
    if np.any(qv[1:] <= 0):
        raise ValueError("ZERO_CONTROL_VARIANCE (stationary segment not supported by batch_map)")
    Lm = np.linalg.cholesky(0.5 * (Sig_model + Sig_model.T))
    L0 = np.linalg.cholesky(P0)
    x0 = np.asarray(m0, float).copy(); v = np.zeros((n, 2))
    nth = 4 + 2 * (n - 1)
    lam = 1e-6; prev = None
    for it in range(iters):
        X, Fs, Gs = _rollout(x0, v, ds, gy, dt)
        h, H = h_batch(X)
        # dX_k/dtheta
        J = np.zeros((n, 4, nth)); J[0, :, :4] = np.eye(4)
        for k in range(1, n):
            J[k] = Fs[k] @ J[k - 1]
            J[k, :, 4 + 2 * (k - 1):4 + 2 * k] += Gs[k]
        Hm = np.einsum("kij,kjt->kit", H, J).reshape(2 * n, nth)
        res = (z - h - mu).reshape(-1)                          # (r_0, s_0, r_1, s_1, ...)
        A_meas = np.linalg.solve(Lm, Hm); b_meas = np.linalg.solve(Lm, res)
        d0 = np.r_[x0[:2] - m0[:2], wrap(x0[2] - m0[2]), x0[3] - m0[3]]
        A_pri = np.zeros((4, nth)); A_pri[:, :4] = np.linalg.solve(L0, np.eye(4)); b_pri = -np.linalg.solve(L0, d0)
        A_v = np.zeros((2 * (n - 1), nth)); b_v = np.zeros(2 * (n - 1))
        sq = np.sqrt(qv[1:].reshape(-1))
        A_v[:, 4:] = np.diag(1.0 / sq); b_v[:] = -(v[1:].reshape(-1)) / sq
        A = np.vstack([A_meas, A_pri, A_v]); b = np.r_[b_meas, b_pri, b_v]
        cost = float(b @ b)
        if prev is not None and cost > prev[0]:
            x0, v = prev[1], prev[2]; lam *= 10; continue
        N_ = A.T @ A; g = A.T @ b
        step = np.linalg.solve(N_ + lam * np.diag(np.diag(N_)), g)
        prev = (cost, x0.copy(), v.copy())
        x0 = x0 + step[:4]; x0[2] = wrap(x0[2]); v[1:] = v[1:] + step[4:].reshape(n - 1, 2)
        lam = max(lam / 10, 1e-12)
        if np.max(np.abs(step)) < tol:
            break
    X, Fs, Gs = _rollout(x0, v, ds, gy, dt)
    h, H = h_batch(X)
    J = np.zeros((n, 4, nth)); J[0, :, :4] = np.eye(4)
    for k in range(1, n):
        J[k] = Fs[k] @ J[k - 1]; J[k, :, 4 + 2 * (k - 1):4 + 2 * k] += Gs[k]
    Hm = np.einsum("kij,kjt->kit", H, J).reshape(2 * n, nth)
    A_meas = np.linalg.solve(Lm, Hm)
    Prec = A_meas.T @ A_meas
    Prec[:4, :4] += np.linalg.inv(P0)
    Prec[4:, 4:] += np.diag(1.0 / qv[1:].reshape(-1))
    Cth = np.linalg.inv(0.5 * (Prec + Prec.T))
    Pst = [J[k] @ Cth @ J[k].T for k in range(n)]
    return X, Pst, dict(iters=it + 1, cost=float(prev[0]) if prev else np.nan)
