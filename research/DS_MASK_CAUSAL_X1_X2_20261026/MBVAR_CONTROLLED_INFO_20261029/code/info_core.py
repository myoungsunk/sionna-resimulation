"""MBVAR-INFO-001 mathematical core (SCIENCE_SPEC §2-§3). Pure numpy; no repository imports.

Conventions
- state x = [p_x m, p_y m, psi rad, b_g rad/s]; observation z = [r m, s 1]; stacked observation order (r_0, s_0, r_1, s_1, ...).
- Batch posterior is computed in covariance (conditioning) form so that a singular process noise (b_g has zero Q) is exact:
    Sigma_X = joint prior of X=[x_0..x_N] from (P0, F_k, Q_k);  P_post = Sigma_X - Sigma_X H^T S^-1 H Sigma_X.
- Nuisance-marginalised information of state a = 1 / (P_post)_aa  (== Schur complement of the joint precision).
- Normalisation: I_nondim = D^T I D (never D^-1 I D^-1); for a scalar marginal this is I_a * D_a^2.
- Mis-specified (iid-claimed) estimator under the true Sigma: sandwich covariance
    K = Sigma_X H^T S_model^-1,  E_true = (I-KH) Sigma_X (I-KH)^T + K Sigma_true K^T.
"""
from __future__ import annotations

import math

import numpy as np

STATE_SCALES = np.array([0.1, 0.1, math.radians(5.0), math.radians(0.2)])   # D (contract PLAN_PARAMETERS.fixed_state_scales)


# ----------------------------------------------------------------------------- S0 analytic reference
def two_obs_ratio(rho: float, sign: int, sigma: float = 1.0) -> float:
    """I_corr / I_iid for H=[1, sign]^T, Sigma = sigma^2 [[1,rho],[rho,1]] (numerical, not the closed form)."""
    H = np.array([[1.0], [float(sign)]])
    S = sigma ** 2 * np.array([[1.0, rho], [rho, 1.0]])
    I_corr = (H.T @ np.linalg.solve(S, H)).item()
    I_iid = (H.T @ np.linalg.solve(np.diag(np.diag(S)), H)).item()
    return I_corr / I_iid


# ----------------------------------------------------------------------------- stacked dynamics
def joint_prior(P0: np.ndarray, F: list[np.ndarray], Q: list[np.ndarray]) -> np.ndarray:
    """Joint covariance of X=[x_0..x_N] with x_k = F_k x_{k-1} + w_k, w_k~N(0,Q_k); F[0], Q[0] unused (k=0 is the prior)."""
    n = len(F); d = P0.shape[0]
    Pk = [P0]
    for k in range(1, n):
        Pk.append(F[k] @ Pk[-1] @ F[k].T + Q[k])
    S = np.zeros((n * d, n * d))
    for i in range(n):
        S[i * d:(i + 1) * d, i * d:(i + 1) * d] = Pk[i]
        Phi = np.eye(d)
        for j in range(i + 1, n):
            Phi = F[j] @ Phi
            blk = Phi @ Pk[i]                      # cov(x_j, x_i)
            S[j * d:(j + 1) * d, i * d:(i + 1) * d] = blk
            S[i * d:(i + 1) * d, j * d:(j + 1) * d] = blk.T
    return 0.5 * (S + S.T)


def stack_H(Hs: list[np.ndarray], obs_states: list[int], n_states: int, d: int = 4) -> np.ndarray:
    m = Hs[0].shape[0]
    Hb = np.zeros((m * len(Hs), n_states * d))
    for i, (H, k) in enumerate(zip(Hs, obs_states)):
        Hb[i * m:(i + 1) * m, k * d:(k + 1) * d] = H
    return Hb


def condition(SX: np.ndarray, Hb: np.ndarray, Sig_model: np.ndarray, Sig_true: np.ndarray | None = None):
    """Gaussian conditioning. Returns (P_post_model, E_true) where E_true is the true error covariance of the
    estimator that assumes Sig_model when the data have covariance Sig_true (== P_post_model if Sig_true is None)."""
    S = Hb @ SX @ Hb.T + Sig_model
    S = 0.5 * (S + S.T)
    L = np.linalg.cholesky(S)
    A = np.linalg.solve(L, Hb @ SX)                 # L^-1 H SX
    P = SX - A.T @ A
    P = 0.5 * (P + P.T)
    if Sig_true is None:
        return P, P
    K = np.linalg.solve(L.T, np.linalg.solve(L, Hb @ SX)).T     # SX H^T S^-1
    IKH = np.eye(SX.shape[0]) - K @ Hb
    E = IKH @ SX @ IKH.T + K @ Sig_true @ K.T
    return P, 0.5 * (E + E.T)


def rotation_rt(p_ref: np.ndarray, anchor_xy: np.ndarray) -> np.ndarray:
    """4x4 rotation taking [p_x,p_y,psi,b_g] errors to [radial, tangential, psi, b_g] at p_ref."""
    u = np.asarray(p_ref[:2], float) - np.asarray(anchor_xy[:2], float)
    u = u / np.linalg.norm(u)
    T = np.eye(4)
    T[0, :2] = u
    T[1, :2] = [-u[1], u[0]]
    return T


def marginal_block(P: np.ndarray, k: int, T: np.ndarray, d: int = 4) -> np.ndarray:
    B = P[k * d:(k + 1) * d, k * d:(k + 1) * d]
    return T @ B @ T.T


def nondim_info(Pblock: np.ndarray, scales: np.ndarray = STATE_SCALES) -> np.ndarray:
    """Marginal (nuisance-marginalised) normalised information per state: D_a^2 / P_aa."""
    return scales ** 2 / np.diag(Pblock)


def nondim_matrix(I: np.ndarray, scales: np.ndarray = STATE_SCALES) -> np.ndarray:
    D = np.diag(scales)
    return D.T @ I @ D


# ----------------------------------------------------------------------------- S1 covariance (SCIENCE_SPEC §3)
def k_pose(P: np.ndarray, yaw: np.ndarray, ell_p: float, ell_psi: float | None) -> np.ndarray:
    d2 = np.sum((P[:, None, :] - P[None, :, :]) ** 2, axis=-1)
    K = np.exp(-d2 / (2.0 * ell_p ** 2)) if ell_p > 0 else (d2 == 0).astype(float)
    if ell_psi is not None:
        dy = yaw[:, None] - yaw[None, :]
        K = K * np.exp(-2.0 * np.sin(dy / 2.0) ** 2 / ell_psi ** 2)
    return K


def k_time(t: np.ndarray, tau: float) -> np.ndarray:
    return np.exp(-np.abs(t[:, None] - t[None, :]) / tau) if tau > 0 else np.eye(len(t))


def obs_covariance(Kp: np.ndarray | None, Kt: np.ndarray | None, alphas: tuple, sig: np.ndarray, c: float) -> np.ndarray:
    """Sigma_ij = D_i C D_j [a_p Kp_ij + a_t Kt_ij + a_w delta_ij]; sig = (n,2) per-observation (sigma_r, sigma_s)."""
    a_p, a_t, a_w = alphas
    n = sig.shape[0]
    K = a_w * np.eye(n)
    if a_p:
        K = K + a_p * Kp
    if a_t:
        K = K + a_t * Kt
    C = np.array([[1.0, c], [c, 1.0]])
    S = np.kron(K, C)
    dv = sig.reshape(-1)
    S = dv[:, None] * S * dv[None, :]
    return 0.5 * (S + S.T)


def psd_sqrt(K: np.ndarray, rel_tol: float = 1e-10):
    """Symmetric square-root via eigen-decomposition. Returns (Lhalf, min_eig, max_eig). Raises on |neg| > rel_tol*max."""
    asym = float(np.max(np.abs(K - K.T)) / max(np.max(np.abs(K)), 1e-300))
    if asym > 1e-12:
        raise ValueError(f"ERR_S1_COV asymmetric {asym}")
    w, V = np.linalg.eigh(0.5 * (K + K.T))
    if w[0] < -rel_tol * w[-1]:
        raise ValueError(f"ERR_S1_COV non-PSD min_eig={w[0]} max={w[-1]}")
    return V * np.sqrt(np.clip(w, 0.0, None))[None, :], float(w[0]), float(w[-1])


def sample_unit_field(Lhalf: np.ndarray, rng: np.random.Generator, channels: int = 2, c: float = 0.0) -> np.ndarray:
    """One zero-mean unit-marginal vector field over the K index set: returns (n, channels) with channel covariance C."""
    n = Lhalf.shape[0]
    Z = rng.standard_normal((Lhalf.shape[1], channels))
    U = Lhalf @ Z
    if channels == 2 and c != 0.0:
        Lc = np.linalg.cholesky(np.array([[1.0, c], [c, 1.0]]))
        U = U @ Lc.T
    return U
