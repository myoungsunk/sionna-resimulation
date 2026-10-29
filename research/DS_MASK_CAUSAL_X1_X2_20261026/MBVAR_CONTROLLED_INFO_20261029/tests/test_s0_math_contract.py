"""MATH-01/03 and CHECK_S0_DYNAMIC. Independent pathways are written inline here (not via info_core helpers)."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import info_core as IC  # noqa: E402


# ---------------------------------------------------------------- MATH-01 analytic two-observation ratios
@pytest.mark.parametrize("rho", [0.0, 0.5, 0.9])
def test_two_obs_closed_form(rho):
    assert abs(IC.two_obs_ratio(rho, +1) - 1.0 / (1.0 + rho)) <= 1e-10
    assert abs(IC.two_obs_ratio(rho, -1) - 1.0 / (1.0 - rho)) <= 1e-10


def test_rho09_contract_constants():
    assert abs(IC.two_obs_ratio(0.9, +1) - 0.5263157894736842) <= 1e-10
    assert abs(IC.two_obs_ratio(0.9, -1) - 10.0) <= 1e-10


# ---------------------------------------------------------------- MATH-03 unit invariance of D^T I D (and negative fixture)
def _rand_info(seed=0):
    r = np.random.default_rng(seed); A = r.standard_normal((6, 4)); return A.T @ A + 0.1 * np.eye(4)


def test_nondim_unit_invariance():
    I = _rand_info(); S = np.diag([100.0, 100.0, 180 / math.pi, 180 / math.pi])        # m->cm, rad->deg
    Ip = np.linalg.inv(S).T @ I @ np.linalg.inv(S); Dp = IC.STATE_SCALES * np.diag(S)
    a = IC.nondim_matrix(I); b = IC.nondim_matrix(Ip, Dp)
    assert np.max(np.abs(a - b)) / np.max(np.abs(a)) <= 1e-10


def test_negative_fixture_wrong_normalisation_not_invariant():
    I = _rand_info(); S = np.diag([100.0, 100.0, 180 / math.pi, 180 / math.pi])
    Ip = np.linalg.inv(S).T @ I @ np.linalg.inv(S); Dp = IC.STATE_SCALES * np.diag(S)
    wrong = lambda M, d: np.diag(1 / d) @ M @ np.diag(1 / d)  # noqa: E731  D^-1 I D^-1
    a = wrong(I, IC.STATE_SCALES); b = wrong(Ip, Dp)
    assert np.max(np.abs(a - b)) / np.max(np.abs(a)) > 1e-3        # the forbidden form must NOT pass the invariance test


# ---------------------------------------------------------------- CHECK_S0_DYNAMIC: Q-aware batch vs independent pathways
def _small_system(n=6, seed=1):
    r = np.random.default_rng(seed)
    F = [np.eye(4)] + [np.eye(4) + 0.05 * r.standard_normal((4, 4)) for _ in range(n - 1)]
    G = [None] + [r.standard_normal((4, 2)) * 0.1 for _ in range(n - 1)]
    Q = [np.zeros((4, 4))] + [g @ np.diag([1e-3, 2e-3]) @ g.T + 1e-6 * np.eye(4) for g in G[1:]]
    H = [r.standard_normal((2, 4)) for _ in range(n)]
    P0 = np.diag([0.01, 0.01, 0.003, 1e-5])
    A = r.standard_normal((2 * n, 2 * n)); Sig = 0.01 * (A @ A.T / (2 * n) + np.eye(2 * n))
    return F, Q, H, P0, Sig


def test_joint_prior_by_simulation_identity():
    F, Q, H, P0, Sig = _small_system()
    SX = IC.joint_prior(P0, F, Q)
    # independent: build via block lower-triangular transfer T with x = T w, w=[x0,w1..]
    n = len(F); d = 4; T = np.zeros((n * d, n * d)); Wc = np.zeros((n * d, n * d))
    for k in range(n):
        Phi = np.eye(d)
        for j in range(k, -1, -1):
            T[k * d:(k + 1) * d, j * d:(j + 1) * d] = Phi
            Phi = Phi @ F[j] if j > 0 else Phi
        Wc[k * d:(k + 1) * d, k * d:(k + 1) * d] = P0 if k == 0 else Q[k]
    assert np.max(np.abs(SX - T @ Wc @ T.T)) <= 1e-12


def test_conditioning_equals_information_form():
    F, Q, H, P0, Sig = _small_system()
    n = len(F); SX = IC.joint_prior(P0, F, Q); Hb = IC.stack_H(H, list(range(n)), n)
    P_cov, _ = IC.condition(SX, Hb, Sig)
    P_inf = np.linalg.inv(np.linalg.inv(SX) + Hb.T @ np.linalg.inv(Sig) @ Hb)
    assert np.max(np.abs(P_cov - P_inf)) / np.max(np.abs(P_inf)) <= 1e-9


def test_iid_batch_final_equals_kalman_filter():
    F, Q, H, P0, _ = _small_system()
    n = len(F); R = np.diag([0.02, 0.01]); Sig = np.kron(np.eye(n), R)
    SX = IC.joint_prior(P0, F, Q); Hb = IC.stack_H(H, list(range(n)), n)
    P_cov, _ = IC.condition(SX, Hb, Sig)
    P = P0.copy()
    for k in range(n):
        if k:
            P = F[k] @ P @ F[k].T + Q[k]
        S = H[k] @ P @ H[k].T + R; K = P @ H[k].T @ np.linalg.inv(S); P = (np.eye(4) - K @ H[k]) @ P
    assert np.max(np.abs(P_cov[-4:, -4:] - P)) / np.max(np.abs(P)) <= 1e-9


def test_sandwich_equals_monte_carlo_linear():
    F, Q, H, P0, Sig = _small_system(n=4, seed=3)
    n = len(F); SX = IC.joint_prior(P0, F, Q); Hb = IC.stack_H(H, list(range(n)), n)
    Sbd = np.zeros_like(Sig)
    for k in range(n):
        Sbd[2 * k:2 * k + 2, 2 * k:2 * k + 2] = Sig[2 * k:2 * k + 2, 2 * k:2 * k + 2]
    P_claim, E = IC.condition(SX, Hb, Sbd, Sig)
    r = np.random.default_rng(7); M = 200000
    LX = np.linalg.cholesky(SX + 1e-15 * np.eye(len(SX))); LS = np.linalg.cholesky(Sig)
    X = LX @ r.standard_normal((len(SX), M)); Z = Hb @ X + LS @ r.standard_normal((len(Sig), M))
    K = SX @ Hb.T @ np.linalg.inv(Hb @ SX @ Hb.T + Sbd); Xh = K @ Z
    Emc = np.cov(X - Xh)
    assert np.max(np.abs(Emc - E)) / np.max(np.abs(E)) < 0.02
