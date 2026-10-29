"""AMENDMENT-008 KINK_FIXTURES: one-/two-sided FD recover left/right/mean slopes at a kink; a smooth control agrees."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import a8_jac as AJ  # noqa: E402


def test_left_right_central_at_kink():
    hv, Xk, _ = AJ.fixture_piecewise()
    L = AJ.fd_H(hv, Xk, "backward", 1e-7); R = AJ.fd_H(hv, Xk, "forward", 1e-7); C = AJ.fd_H(hv, Xk, "central", 1e-2)
    assert np.allclose(L[:, 0, 0], 2.0, atol=1e-6) and np.allclose(R[:, 0, 0], 5.0, atol=1e-6)
    assert np.allclose(C[:, 0, 0], 3.5, atol=1e-9)                     # mean of the one-sided slopes


def test_smooth_control_all_methods_agree():
    hv, _, Xs = AJ.fixture_piecewise()
    Hs = [AJ.fd_H(hv, Xs, *AJ.METHODS[m]) for m in AJ.METHODS if AJ.METHODS[m] is not None]
    an = np.zeros_like(Hs[0]); an[:, 0, 0] = 5.0; an[:, 0, 1] = 0.1; an[:, 1, 1] = Xs[:, 1]; an[:, 1, 2] = 0.3
    for H in Hs:
        assert np.max(np.abs(H - an)) <= 1e-6                             # AMENDMENT-008 KINK_FIXTURES smooth control


def test_linear_exact_all_methods_equal_analytic():
    hb = AJ.linear_h(); X = np.random.default_rng(0).normal(size=(5, 4))
    h, H = hb(X)
    for m in AJ.METHODS:
        Hm = AJ.h_batch_for(m, hb)(X)[1]
        assert np.max(np.abs(Hm - H)) <= 1e-6 * np.max(np.abs(H))


def test_negative_fixture_one_sided_disagree_at_kink():
    hv, Xk, _ = AJ.fixture_piecewise()
    L = AJ.fd_H(hv, Xk, "backward", 1e-7); R = AJ.fd_H(hv, Xk, "forward", 1e-7)
    assert np.max(np.abs(L - R)) > 1.0                                   # a kink must be detectable


def test_unknown_mode_rejected():
    hv, Xk, _ = AJ.fixture_piecewise()
    with pytest.raises(ValueError):
        AJ.fd_H(hv, Xk, "sideways", 1e-3)
