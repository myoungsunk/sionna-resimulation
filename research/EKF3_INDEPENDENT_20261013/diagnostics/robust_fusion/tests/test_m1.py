import math
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from m1_bias_robust_ekf import RobustBiasEKF, huber_block
from d6_d9_common import DiagnosticFilter, arc, wrap


def model(p):
    return float(p[2]), np.array([0., 0., 1.])


def do_update(f, z, delta=np.inf):
    return f.update('A', z, None, model, [0., 0., 0.], 1.,
                    [0.], np.array([[.01]]), delta)


def test_huber_radial_gradient_and_shared_block_weight():
    v = np.array([3., 4.])
    loss, w, grad = huber_block(v, 2.)
    assert loss == 8.
    assert w == .4
    for j in range(2):
        e = np.eye(2)[j] * 1e-6
        numeric = (huber_block(v+e, 2.)[0]-huber_block(v-e, 2.)[0])/2e-6
        assert numeric == pytest.approx(grad[j], abs=1e-8)
    assert huber_block([.1, .2], 2.)[1] == 1.


def test_gaussian_update_matches_original_bias4():
    old = DiagnosticFilter(np.array([1., 2., .2]), bias_state=True)
    new = RobustBiasEKF([1., 2., .2])
    old.predict(.1, .02, .2)
    new.predict(.1, .02, .2)
    assert old.update('A', .24, None, model, [0, 0, 0], 1., rs=.01)[0] == 'applied'
    do_update(new, .24)
    np.testing.assert_allclose(new.x, old.x, atol=1e-15)
    np.testing.assert_allclose(new.P, old.P, atol=1e-15)


def test_fixed_prior_iterations_do_not_duplicate_information():
    a, b = RobustBiasEKF([0, 0, 0], max_iterations=3), RobustBiasEKF([0, 0, 0], max_iterations=100)
    ra, rb = do_update(a, .05), do_update(b, .05)
    np.testing.assert_array_equal(a.x, b.x)
    np.testing.assert_array_equal(a.P, b.P)
    assert ra['iterations'] == rb['iterations'] >= 1
    p = math.radians(5)**2
    assert a.P[2, 2] == pytest.approx(1/(1/p+1/.01))


def test_huber_map_stationarity_and_outlier_influence():
    a, b = RobustBiasEKF([0, 0, 0]), RobustBiasEKF([0, 0, 0])
    do_update(a, 2.)
    rb = do_update(b, 2., 1.5)
    assert abs(b.pose[2]) < abs(a.pose[2])/5
    assert rb['huber_weight'] < .1
    assert rb['stationarity_norm'] < 1e-7
    assert b.P[2, 2] > a.P[2, 2]


def test_predict_bias_jacobian_against_numerical_covariance():
    f = RobustBiasEKF([1., 2., .7], bias_initial_rad_s=.03)
    x, p = f.x.copy(), f.P.copy()
    ds, gyro, dt = .6, .15, .2
    def fun(v):
        return np.r_[arc(v[:3], ds, gyro-v[3]*dt), v[3]]
    eps = 1e-6
    jac = np.column_stack([(fun(x+np.eye(4)[j]*eps)-fun(x-np.eye(4)[j]*eps))/(2*eps) for j in range(4)])
    jinput = np.column_stack([(np.r_[arc(x[:3], ds+eps, gyro-x[3]*dt), x[3]]-
                              np.r_[arc(x[:3], ds-eps, gyro-x[3]*dt), x[3]])/(2*eps),
                             (np.r_[arc(x[:3], ds, gyro+eps-x[3]*dt), x[3]]-
                              np.r_[arc(x[:3], ds, gyro-eps-x[3]*dt), x[3]])/(2*eps)])
    q = np.diag([2e-5*ds, math.radians(.015)**2*dt])
    f.predict(ds, gyro, dt)
    np.testing.assert_allclose(f.P, jac@p@jac.T+jinput@q@jinput.T, atol=1e-11, rtol=1e-8)


@pytest.mark.parametrize('bias_dps', [0., .3])
@pytest.mark.parametrize('delta', [np.inf, 1.5])
@pytest.mark.parametrize('estimated', [False, True])
def test_bias_fixed_estimated_gaussian_huber_synthetic_controls(bias_dps, delta, estimated):
    f = RobustBiasEKF([0., 0., 0.], bias_prior_std_dps=1. if estimated else 1e-8)
    for k in range(150):
        f.predict(.1, math.radians(bias_dps)*.2, .2)
        do_update(f, .4 if (delta != np.inf and k % 29 == 0) else 0., delta)
    assert np.isfinite(f.P).all()
    if estimated:
        assert abs(math.degrees(f.x[3])-bias_dps) < .05
        assert abs(f.pose[2]) < .01
    else:
        assert abs(f.x[3]) < 1e-10


def test_joint_block_covariance_and_missing_component():
    f = RobustBiasEKF([2., 0., 0.])
    r = np.array([[.01, .005], [.005, .04]])
    result = f.update('C', .8, 2.8, model, [0., 0., 0.], 0., [0., 0.], r, 1.5)
    assert result['H'].shape == (2, 4)
    np.testing.assert_allclose(result['R_effective'], r/result['huber_weight'])
    result = f.update('C', None, 2., model, [0., 0., 0.], 0., [0., 0.], r, 1.5)
    assert result['H'].shape == (1, 4)


def test_failclosed_bad_covariance_nonconvergence_and_d0():
    f = RobustBiasEKF([0., 0., 0.], max_iterations=1)
    p, x = f.P.copy(), f.x.copy()
    with pytest.raises(RuntimeError, match='converge'):
        do_update(f, 1., 1.5)
    np.testing.assert_array_equal(f.x, x)
    np.testing.assert_array_equal(f.P, p)
    with pytest.raises(ValueError):
        f.update('A', 0., None, model, [0, 0, 0], 1., [0.], [[-1.]], 1.5)
    assert f.update('D0', None, None, None, None, None, None, None, None)['status'] == 'DR_only'


def test_safeguarded_huber_weight_root_stationary_over_outliers():
    rng = np.random.default_rng(430271)
    for observation in rng.normal(0, .5, 200):
        f = RobustBiasEKF([0, 0, 0])
        result = do_update(f, float(observation), delta=1.345)
        assert result['stationarity_norm'] < 1e-7
