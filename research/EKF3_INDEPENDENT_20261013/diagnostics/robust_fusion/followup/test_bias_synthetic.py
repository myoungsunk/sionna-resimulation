"""Independent differential and deterministic invariance checks."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bias_synthetic import (DiagnosticFilter, heading_model, range_h, ANCHOR,
    HEIGHT, arc, motion_cov, run_pair, update_diagnostic)


def derivative(fun, x, eps=1e-6):
    return np.column_stack([(np.asarray(fun(x+np.eye(len(x))[i]*eps))-
                             np.asarray(fun(x-np.eye(len(x))[i]*eps)))/(2*eps)
                            for i in range(len(x))])


@pytest.mark.parametrize('yaw', [0., .1, -.25])
def test_bias_motion_covariance_numerical_jacobians(yaw):
    f = DiagnosticFilter(np.array([.4, -.7, .3]), bias_state=True)
    f.x[3] = math.radians(.03)
    oldx, oldp = f.x.copy(), f.P.copy()
    ds, dt = .07, .2
    def fx(x):
        return np.r_[arc(x[:3], ds, yaw-x[3]*dt), x[3]]
    def fu(u):
        return np.r_[arc(oldx[:3], u[0], u[1]-oldx[3]*dt), oldx[3]]
    ff = derivative(fx, oldx)
    gg = derivative(fu, np.array([ds, yaw]))
    expected = ff@oldp@ff.T+gg@motion_cov(ds, dt)@gg.T
    f.predict(ds, yaw, dt)
    np.testing.assert_allclose(f.x, fx(oldx), atol=1e-12)
    np.testing.assert_allclose(f.P, expected, atol=1e-10, rtol=1e-7)


def test_observation_jacobians_independent_finite_difference():
    x = np.array([.7, -.2, .6])
    np.testing.assert_allclose(heading_model(x)[1],
        derivative(lambda z: [heading_model(z)[0]], x)[0], atol=1e-9)
    np.testing.assert_allclose(range_h(x, ANCHOR, HEIGHT)[1],
        derivative(lambda z: [range_h(z, ANCHOR, HEIGHT)[0]], x)[0], atol=1e-9)


@pytest.mark.parametrize('path', ['straight', 'turn', 'return'])
def test_exact_zero_bias_invariance(path):
    rows, _ = run_pair(path, 0., False, 0, steps=12)
    assert max(r['noiseless_invariant_max'] for r in rows) < 1e-10
    assert all(r['gate_reject_fraction'] == 0. for r in rows)
    assert all(abs(r['final_bias_error_dps']) < 1e-10 for r in rows if r['model'] == 'M1-A')


def test_noiseless_d0_known_bias_does_not_claim_convergence():
    rows, _ = run_pair('straight', .05, False, 0, steps=12)
    d0 = {r['model']: r for r in rows if r['arm'] == 'D0'}
    assert d0['M1-A']['final_bias_error_dps'] == -.05
    assert d0['M0']['heading_rmse_deg'] == d0['M1-A']['heading_rmse_deg']


def test_actual_gain_bias_correction_and_rejected_update():
    f = DiagnosticFilter(np.array([0., 0., .2]), bias_state=True)
    f.predict(.04, .01, .2)
    oldx = f.x.copy()
    zs = heading_model(f.pose)[0]+.001
    zr = range_h(f.pose, ANCHOR, HEIGHT)[0]+.001
    d = update_diagnostic(f, 'C', zs, zr)
    assert d['status'] == 'applied'
    expected_bias = oldx[3]+np.array(d['Kbias'])@np.array(d['innovation'])
    assert f.x[3] == pytest.approx(expected_bias, abs=1e-14)
    oldx, oldp = f.x.copy(), f.P.copy()
    d = update_diagnostic(f, 'C', 100., 100.)
    assert d['status'] == 'rejected_NIS'
    np.testing.assert_array_equal(f.x, oldx)
    np.testing.assert_array_equal(f.P, oldp)


def test_seeded_noisy_repetition_is_reproducible():
    first, _ = run_pair('turn', .05, True, 17, steps=5)
    second, _ = run_pair('turn', .05, True, 17, steps=5)
    assert first == second
