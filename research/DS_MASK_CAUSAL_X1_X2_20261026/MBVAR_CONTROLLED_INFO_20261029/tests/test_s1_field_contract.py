"""CHECK_S1_KERNEL: PSD, unit marginals, exact same-pose spatial draw, time-only OU independent of pose; negative fixtures."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import info_core as IC  # noqa: E402


def _poses():
    x = np.linspace(2, 4, 21); P = np.c_[x, np.full(21, 6.0)]; yaw = np.zeros(21)
    P = np.r_[P, [[6.0, 6.0], [6.0, 6.0]]]; yaw = np.r_[yaw, 0.0, 2 * math.pi]          # spin 0 and 360 deg: same pose
    return P, yaw


def test_pose_kernel_psd_unit_diag_and_revisit_equal():
    P, yaw = _poses(); K = IC.k_pose(P, yaw, 0.5, math.radians(20))
    assert np.allclose(np.diag(K), 1.0, atol=0, rtol=0)
    assert abs(K[-1, -2] - 1.0) <= 1e-12                                                 # 0 deg == 360 deg
    L, wmin, wmax = IC.psd_sqrt(K)
    U = IC.sample_unit_field(L, np.random.default_rng(0))
    assert np.max(np.abs(U[-1] - U[-2])) <= 1e-12 * max(1.0, np.max(np.abs(U)))           # DATA-01 same spatial draw


def test_marginal_variance_identical_across_arms():
    P, yaw = _poses(); n = len(P); sig = np.tile([0.05, 0.02], (n, 1))
    Kp = IC.k_pose(P, yaw, 0.5, math.radians(20)); Kt = IC.k_time(np.arange(n) * 0.5, 5.0)
    arms = [(0, 0, 1), (0.7, 0, 0.3), (0, 0.7, 0.3)]
    diags = [np.diag(IC.obs_covariance(Kp, Kt, a, sig, 0.0)) for a in arms]
    for d in diags[1:]:
        assert np.max(np.abs(d - diags[0]) / diags[0]) <= 1e-12                         # DATA-02


def test_time_component_ignores_pose():
    t = np.array([0.0, 0.5, 100.0]); K = IC.k_time(t, 1.0)
    assert K[0, 2] < 1e-40 and abs(K[0, 1] - math.exp(-0.5)) <= 1e-15


def test_obs_covariance_psd_with_rs_corr():
    P, yaw = _poses(); n = len(P); sig = np.tile([0.05, 0.02], (n, 1))
    S = IC.obs_covariance(IC.k_pose(P, yaw, 0.5, math.radians(20)), None, (0.7, 0, 0.3), sig, 0.3)
    w = np.linalg.eigvalsh(S); assert w[0] >= -1e-10 * w[-1]
    assert abs(S[0, 1] / math.sqrt(S[0, 0] * S[1, 1]) - 0.3) <= 1e-12


def test_negative_fixture_non_psd_rejected():
    K = np.array([[1.0, 0.99, -0.99], [0.99, 1.0, 0.99], [-0.99, 0.99, 1.0]])
    with pytest.raises(ValueError):
        IC.psd_sqrt(K)


def test_negative_fixture_resampled_draw_detected():
    P, yaw = _poses(); K = IC.k_pose(P, yaw, 0.5, math.radians(20)); L, _, _ = IC.psd_sqrt(K)
    U1 = IC.sample_unit_field(L, np.random.default_rng(0)); U2 = IC.sample_unit_field(L, np.random.default_rng(1))
    assert np.max(np.abs(U1[-1] - U2[-2])) > 1e-6          # independent resampling at the same pose is distinguishable
