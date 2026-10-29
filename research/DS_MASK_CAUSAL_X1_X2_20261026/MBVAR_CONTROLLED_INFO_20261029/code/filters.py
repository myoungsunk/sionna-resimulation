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


# ============================================================================ AMENDMENT-003: batch_map_v2
# batch_map (v1) above is kept byte-identical for reproduction of the runs made under the original freeze.
# v2 fixes the audit finding: v1 applied the last proposed step without checking that it lowered the cost, and it
# never recorded why it stopped. v2 accepts a step only if the cost strictly decreases, stops on the Newton decrement
# (predicted remaining cost decrease, chi^2 units), and reports NONCONVERGED_* otherwise.
V2_DEC_TOL = 1e-10
V2_MAX_ITER = 100
V2_LAM_MAX = 1e12


def _v2_parts(h_batch, z, mu, Lm, L0, m0, qv, ds, gy, dt, x0, v, jac=True):
    n = len(z); nth = 4 + 2 * (n - 1)
    X, Fs, Gs = _rollout(x0, v, ds, gy, dt)
    h, H = h_batch(X)
    res = (z - h - mu).reshape(-1)
    d0 = np.r_[x0[:2] - m0[:2], wrap(x0[2] - m0[2]), x0[3] - m0[3]]
    sq = np.sqrt(qv[1:].reshape(-1))
    b = np.r_[np.linalg.solve(Lm, res), -np.linalg.solve(L0, d0), -(v[1:].reshape(-1)) / sq]
    if not jac:
        return float(b @ b), X
    J = np.zeros((n, 4, nth)); J[0, :, :4] = np.eye(4)
    for k in range(1, n):
        J[k] = Fs[k] @ J[k - 1]; J[k, :, 4 + 2 * (k - 1):4 + 2 * k] += Gs[k]
    Hm = np.einsum("kij,kjt->kit", H, J).reshape(2 * n, nth)
    A = np.zeros((len(b), nth))
    A[:2 * n] = np.linalg.solve(Lm, Hm); A[2 * n:2 * n + 4, :4] = np.linalg.solve(L0, np.eye(4)); A[2 * n + 4:, 4:] = np.diag(1.0 / sq)
    return float(b @ b), X, A, b, J


V2_NONSMOOTH_DEC = 0.05
V2_NONSMOOTH_SHIFT_SD = 0.1


def batch_map_v2(h_batch, z, mu, Sig_model, ds, gy, dt, m0, P0, max_iter=V2_MAX_ITER, dec_tol=V2_DEC_TOL, theta0=None,
                 lam0=1e-6, q_scale=1.0):
    """Levenberg-Marquardt MAP over theta=(x0, v_1..v_N-1) with strict-decrease acceptance.
    Returns X_hat, Pstate list (at the final accepted theta), info dict with status in
    {CONVERGED, NONCONVERGED_MAXITER, NONCONVERGED_LAMBDA} and the diagnostics the audit asked for."""
    n = len(z)
    qv = q_scale * np.array([[Q_DS * abs(ds[k]), Q_GY * dt[k]] for k in range(n)])
    if np.any(qv[1:] <= 0):
        raise ValueError("ZERO_CONTROL_VARIANCE (stationary segment not supported by batch_map)")
    Lm = np.linalg.cholesky(0.5 * (Sig_model + Sig_model.T)); L0 = np.linalg.cholesky(P0)
    x0 = np.asarray(m0 if theta0 is None else theta0[0], float).copy()
    v = np.zeros((n, 2)) if theta0 is None else np.asarray(theta0[1], float).copy()
    cost0 = None; lam = lam0; n_acc = n_rej = 0; status = "NONCONVERGED_MAXITER"; last_step = np.nan; dec = np.nan
    it = 0
    for it in range(1, max_iter + 1):
        c, X, A, b, J = _v2_parts(h_batch, z, mu, Lm, L0, m0, qv, ds, gy, dt, x0, v)
        cost0 = c if cost0 is None else cost0
        N_ = A.T @ A; g = A.T @ b
        s_gn = np.linalg.solve(N_, g); dec = float(g @ s_gn)
        if dec <= dec_tol:
            status = "CONVERGED"; break
        D = np.diag(np.diag(N_)); accepted = False
        while lam <= V2_LAM_MAX:
            s = np.linalg.solve(N_ + lam * D, g)
            x1 = x0 + s[:4]; x1[2] = wrap(x1[2]); v1 = v.copy(); v1[1:] = v[1:] + s[4:].reshape(n - 1, 2)
            c1, _ = _v2_parts(h_batch, z, mu, Lm, L0, m0, qv, ds, gy, dt, x1, v1, jac=False)
            if c1 < c:
                x0, v = x1, v1; lam = max(lam / 10.0, 1e-12); n_acc += 1; last_step = float(np.max(np.abs(s))); accepted = True
                break
            lam *= 10.0; n_rej += 1
        if not accepted:
            status = "NONCONVERGED_LAMBDA"; break
    # final quantities at the current (last accepted) theta
    c, X, A, b, J = _v2_parts(h_batch, z, mu, Lm, L0, m0, qv, ds, gy, dt, x0, v)
    N_ = A.T @ A; g = A.T @ b; s_gn = np.linalg.solve(N_, g); dec = float(g @ s_gn)
    Cth = np.linalg.inv(0.5 * (N_ + N_.T))
    Pst = [J[k] @ Cth @ J[k].T for k in range(n)]
    shift = float(np.max(np.abs(J[-1] @ s_gn) / np.sqrt(np.diag(Pst[-1]))))   # remaining GN shift at the window end, sd units
    stop = status
    if status != "CONVERGED":
        status = "CONVERGED_NONSMOOTH" if (dec <= V2_NONSMOOTH_DEC and shift <= V2_NONSMOOTH_SHIFT_SD) else "NONCONVERGED"
    info = dict(status=status, stop_reason=stop, gn_shift_end_sd=shift, iters=it, n_accept=n_acc, n_reject=n_rej, cost=c, cost_initial=cost0, newton_decrement=dec,
                grad_scaled_inf=float(np.max(np.abs(g) / np.sqrt(np.diag(N_)))), last_step_inf=last_step, lam=lam,
                theta=(x0.copy(), v.copy()))
    return X, Pst, info


# ============================================================================ AMENDMENT-004: misfit-triggered heading multi-start
# C1-d (AMENDMENT-003) showed that from the prior mean a single LM run can converge to a spurious basin (cost ~3000 for
# 2N = 120 residuals, ~1 m error) when the initial heading is ~1.7 prior sd off. Deployable rule (no truth): if the final
# cost exceeds the chi^2_{0.999}(2N) quantile, re-run from heading offsets k*sd_psi(P0), k in MS_K, and keep the minimum.
MS_K = (0, -1, 1, -2, 2, -3, 3)


def chi2_quantile_wh(k, z=3.090232306167813):
    """Wilson-Hilferty chi^2 quantile (default p = 0.999)."""
    a = 2.0 / (9.0 * k)
    return k * (1.0 - a + z * math.sqrt(a)) ** 3


def batch_map_v2_ms(h_batch, z, mu, Sig_model, ds, gy, dt, m0, P0, **kw):
    n = len(z); thr = chi2_quantile_wh(2 * n); sd_psi = math.sqrt(P0[2, 2])
    X, Pst, info = batch_map_v2(h_batch, z, mu, Sig_model, ds, gy, dt, m0, P0, **kw)
    best = (info["cost"], 0, X, Pst, info); costs = {0: info["cost"]}; trig = info["cost"] > thr
    if trig:
        for k in MS_K[1:]:
            x0 = np.asarray(m0, float).copy(); x0[2] = wrap(x0[2] + k * sd_psi)
            Xk, Pk, Ik = batch_map_v2(h_batch, z, mu, Sig_model, ds, gy, dt, m0, P0, theta0=(x0, np.zeros((n, 2))), **kw)
            costs[k] = Ik["cost"]
            if Ik["cost"] < best[0]:
                best = (Ik["cost"], k, Xk, Pk, Ik)
    c, kb, Xb, Pb, Ib = best
    rescued = False
    if Ib["status"] == "NONCONVERGED":                 # AMENDMENT-006 rescue: re-linearise with a smoothed (central-FD) Jacobian
        hs = _fd_smoothed(h_batch)
        Xr, Pr, Ir = batch_map_v2(hs, z, mu, Sig_model, ds, gy, dt, m0, P0, theta0=Ib["theta"], **kw)
        Xa, Pa, Ia = batch_map_v2(h_batch, z, mu, Sig_model, ds, gy, dt, m0, P0, theta0=Ir["theta"], **kw)
        if Ia["cost"] <= c + 1e-9 and Ia["status"] != "NONCONVERGED" or Ia["cost"] < c - 1e-9:
            c, Xb, Pb, Ib, rescued = Ia["cost"], Xa, Pa, Ia, True
    cv = sorted(costs.values()); distinct = 1 + sum(1 for a, b in zip(cv, cv[1:]) if b - a > 1.0)
    Ib = dict(Ib, ms_triggered=bool(trig), ms_threshold=thr, ms_best_k=int(kb), ms_n_starts=len(costs), ms_n_distinct_minima=distinct,
              ms_cost_start0=costs[0], ms_final_misfit=bool(c > thr), rescued=rescued)
    return Xb, Pb, Ib


FD_SMOOTH_STEP = (1e-2, 1e-2, math.radians(0.1), 1e-6)


def _fd_smoothed(h_batch):
    """h with a central finite-difference Jacobian (steps FD_SMOOTH_STEP): averages one-sided derivatives across the 1-degree
    pattern-cell kinks. Used only by the AMENDMENT-006 rescue of NONCONVERGED runs."""
    def hb(X):
        h, _ = h_batch(X); H = np.zeros((len(X), 2, 4))
        for j, e in enumerate(FD_SMOOTH_STEP):
            d = np.zeros(4); d[j] = e
            H[:, :, j] = (h_batch(X + d)[0] - h_batch(X - d)[0]) / (2 * e)
        return h, H
    return hb
