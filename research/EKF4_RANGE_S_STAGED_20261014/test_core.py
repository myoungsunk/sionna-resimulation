"""Tests run on GitHub Actions; synthetic tests are not RF validation."""
import json
import math
import numpy as np
import pytest
from scipy.optimize import least_squares
from core import (wrap, covariance, transition, predict, gaussian_update,
                  sequential_affine, conditional_rf, recover_bias,
                  map_update, SyntheticRF)


def difference(a, b):
    d = np.asarray(a)-np.asarray(b)
    d[2] = wrap(d[2])
    return d


def pd(rng, n):
    A = rng.normal(size=(n, n))
    return A@A.T+.2*np.eye(n)


@pytest.mark.p0
@pytest.mark.parametrize('n', [3, 4])
def test_transition_independent_complex_integral(n):
    rng = np.random.default_rng(403)
    worst = 0.
    for angle in [0., 1e-10, -1e-5, .2, -1.7, 2.8]:
        for ds in [0., .5, -.3]:
            x = np.r_[rng.normal(size=2), .8, .01][:n]
            dt = .3
            measured = angle+(x[3]*dt if n == 4 else 0.)
            y, _, _ = transition(x, ds, measured, dt)
            # Independent integral of exp(i*(psi+t*angle)), t in [0,1].
            integral = 1. if angle == 0 else np.expm1(1j*angle)/(1j*angle)
            d = ds*np.exp(1j*x[2])*integral
            truth = x.copy()
            truth[:2] += [d.real, d.imag]
            truth[2] = wrap(x[2]+angle)
            worst = max(worst, float(np.max(np.abs(difference(y, truth)))))
    print('METRIC independent_motion_max', worst)
    assert worst < 1e-12


@pytest.mark.p0
@pytest.mark.parametrize('n', [3, 4])
def test_F_G_central_difference(n):
    rng = np.random.default_rng(515)
    worst_f = worst_g = 0.
    eps = 1e-6
    for i in range(200):
        x = np.r_[rng.normal(size=2), rng.uniform(-np.pi, np.pi), rng.normal(scale=.01)][:n]
        ds = rng.uniform(-1., 1.)
        dt = rng.uniform(.02, 1.)
        a = [0., 1e-10, -1e-5, rng.uniform(-2., 2.)][i % 4]
        y, F, G = transition(x, ds, a, dt)
        numeric = np.zeros((n, n))
        for j in range(n):
            v = np.zeros(n); v[j] = eps
            numeric[:, j] = difference(transition(x+v, ds, a, dt)[0],
                                       transition(x-v, ds, a, dt)[0])/(2*eps)
        ng = np.zeros_like(G)
        ng[:, 0] = difference(transition(x, ds+eps, a, dt)[0],
                               transition(x, ds-eps, a, dt)[0])/(2*eps)
        ng[:, 1] = difference(transition(x, ds, a+eps, dt)[0],
                               transition(x, ds, a-eps, dt)[0])/(2*eps)
        if n == 4:
            plus, minus = y.copy(), y.copy()
            plus[3] += eps; minus[3] -= eps
            ng[:, 2] = difference(plus, minus)/(2*eps)
        worst_f = max(worst_f, float(np.max(np.abs(F-numeric))))
        worst_g = max(worst_g, float(np.max(np.abs(G-ng))))
    print('METRIC jacobian_max', json.dumps({'n': n, 'F': worst_f, 'G': worst_g}))
    assert worst_f < 1e-6 and worst_g < 1e-6


@pytest.mark.p0
def test_frozen_three_state_limit_and_no_mutation():
    rng = np.random.default_rng(401)
    P3 = pd(rng, 3)
    P4 = np.zeros((4, 4)); P4[:3, :3] = P3
    x3 = np.array([2., 1., .1]); x4 = np.r_[x3, 0.]
    q3 = np.diag([1e-4, 2e-6]); q4 = np.diag([1e-4, 2e-6, 0.])
    saved_x, saved_p = x4.copy(), P4.copy()
    y3, p3, _, _ = predict(x3, P3, .3, .03, .2, q3)
    y4, p4, _, _ = predict(x4, P4, .3, .03, .2, q4)
    np.testing.assert_allclose(y3, y4[:3], atol=1e-14)
    np.testing.assert_allclose(p3, p4[:3, :3], atol=1e-14)
    np.testing.assert_array_equal(x4, saved_x)
    np.testing.assert_array_equal(P4, saved_p)


@pytest.mark.p0
def test_constant_unknown_bias_grows_as_time_squared():
    x = np.array([0., 0., 0., 0.])
    p = np.diag([.01, .01, .001, .0002])
    for _ in range(20):
        x, p, _, _ = predict(x, p, 0., 0., .5, np.zeros((3, 3)))
    assert abs(p[2, 2]-(.001+100*.0002)) < 1e-13
    assert abs(p[2, 3]-(-10*.0002)) < 1e-13
    assert p[3, 3] == .0002


@pytest.mark.p0
@pytest.mark.parametrize('corr', [-.8, 0., .8])
def test_correlated_likelihood_and_sequential_parity(corr):
    rng = np.random.default_rng(99)
    worst = 0.
    for _ in range(100):
        mu = rng.normal(scale=.05, size=4)
        P = pd(rng, 4)*.01
        H = rng.normal(size=(2, 4)); H[:, 3] = 0.
        z = rng.normal(scale=.05, size=2)
        R = np.array([[.3, corr*np.sqrt(.3*.7)], [corr*np.sqrt(.3*.7), .7]])
        model = lambda x: (H@x, H)
        a, A, _ = gaussian_update(mu, P, z, model, R)
        b, B, _ = sequential_affine(mu, P, z, H@mu, H, R)
        worst = max(worst, float(np.max(np.abs(difference(a,b)))), float(np.max(np.abs(A-B))))
        residual = z-H@mu
        er, es, vr, vs, hs = conditional_rf(residual, H, R)
        lhs = residual@np.linalg.solve(R, residual)+np.linalg.slogdet(R)[1]
        rhs = er**2/vr+es**2/vs+np.log(vr*vs)
        assert abs(lhs-rhs) < 1e-9
        m, C = recover_bias(mu, P, a[:3], A[:3, :3])
        np.testing.assert_allclose(m, a, atol=1e-9)
        np.testing.assert_allclose(C, A, atol=1e-9)
    print('METRIC correlated_parity', corr, worst)
    assert worst < 1e-9


@pytest.mark.p0
@pytest.mark.parametrize('bad', [np.diag([1., -1.]), np.array([[1.,2.],[0.,1.]]), np.eye(2)*np.nan])
def test_invalid_covariance_rejected(bad):
    with pytest.raises(ValueError): covariance(bad, 2, positive=True)


@pytest.mark.p0
@pytest.mark.parametrize('dt', [0., -1., float('nan')])
def test_invalid_time_rejected(dt):
    with pytest.raises(ValueError): transition(np.zeros(4), 0., 0., dt)


@pytest.mark.p0
def test_gate_rejection_does_not_shrink_covariance():
    x = np.array([1., 1., .2, 0.]); p = np.eye(4)*.01
    model = SyntheticRF(); z = model(x)[0]+100.
    y, C, d = gaussian_update(x,p,z,model,np.eye(2),gate_threshold=9.21)
    assert not d['accepted']
    np.testing.assert_array_equal(y,x)
    np.testing.assert_array_equal(C,p)


@pytest.mark.p1
@pytest.mark.parametrize('n', [3, 4])
def test_linear_iterated_MAP_is_single_update(n):
    rng = np.random.default_rng(700)
    worst = 0.
    for _ in range(50):
        mu = rng.normal(scale=.02, size=n)
        P = pd(rng,n)*.01
        H = rng.normal(size=(2,n)); H[:,2] *= .1
        if n == 4: H[:,3] = 0.
        R = pd(rng,2)*.05
        z = rng.normal(scale=.05, size=2)
        model = lambda x: (H@x,H)
        expected, C, _ = gaussian_update(mu,P,z,model,R)
        result = map_update(mu,P,z,model,R,max_iter=20)
        assert result.status == 'CONVERGED'
        worst = max(worst, float(np.max(np.abs(difference(result.x,expected)))), float(np.max(np.abs(result.P-C))))
        assert len(result.history) <= 3
    print('METRIC linear_MAP_max', n, worst)
    assert worst < 1e-9


@pytest.mark.p1
@pytest.mark.parametrize('yaw', [0.2, np.pi-.001, -np.pi+.001])
def test_noiseless_invariance_and_periodic_seam(yaw):
    x = np.array([1.,1.,yaw,0.001]); p = np.diag([.01,.01,.02,1e-5])
    model = SyntheticRF(); z = model(x)[0]
    result = map_update(x,p,z,model,np.diag([.01,.002]))
    assert result.status == 'CONVERGED'
    np.testing.assert_allclose(difference(result.x,x),0.,atol=1e-12)
    assert result.cost < 1e-20
    # Periodic model continuity, without pretending +/-pi are far apart.
    xp = x.copy(); xp[2] += 2*np.pi
    np.testing.assert_allclose(model(xp)[0],z,atol=1e-14)


@pytest.mark.p1
def test_synthetic_RF_jacobian():
    rng = np.random.default_rng(204)
    model = SyntheticRF(); eps=1e-6; worst=0.
    for _ in range(100):
        x = np.r_[rng.normal(size=2), rng.uniform(-np.pi,np.pi),0.]
        h,H = model(x)
        numeric=np.zeros((2,4))
        for j in range(4):
            v=np.zeros(4);v[j]=eps
            numeric[:,j]=(model(x+v)[0]-model(x-v)[0])/(2*eps)
        worst=max(worst,float(np.max(np.abs(H-numeric))))
    print('METRIC synthetic_RF_Jacobian',worst)
    assert worst<1e-6


@pytest.mark.p1
def test_local_MAP_against_independent_scipy_solver():
    rng=np.random.default_rng(909)
    model=SyntheticRF()
    R=np.array([[.05**2, .00015],[.00015,.03**2]])
    Lr=np.linalg.cholesky(R)
    max_cost=max_state=0.
    for _ in range(40):
        mu=np.array([1.,1.,rng.uniform(-.6,.6),0.])
        A=rng.normal(size=(4,4))
        D=np.diag([.05,.05,.05,.001])
        P=D@(A@A.T+np.eye(4))@D
        Lp=np.linalg.cholesky(P)
        z=model(mu)[0]+Lr@rng.normal(size=2)
        def residual(y):
            return np.r_[y,np.linalg.solve(Lr,z-model(mu+Lp@y)[0])]
        ref=least_squares(residual,np.zeros(4),jac='3-point',
                          ftol=1e-13,xtol=1e-13,gtol=1e-12,max_nfev=500)
        assert ref.success
        result=map_update(mu,P,z,model,R,max_iter=80)
        assert result.status=='CONVERGED', (result.status,result.gradient_inf)
        expected=mu+Lp@ref.x
        cost_error=abs(result.cost-ref.cost)
        state_error=float(np.max(np.abs(difference(result.x,expected))))
        max_cost=max(max_cost,cost_error);max_state=max(max_state,state_error)
        assert cost_error<1e-8 and state_error<1e-6
        costs=np.array([h['cost'] for h in result.history])
        assert np.all(np.diff(costs)<=1e-12)
        # Iteration is not repeated information: compute local covariance once.
        H=model(mu+result.prior_delta)[1]
        expected_P=np.linalg.inv(np.linalg.inv(P)+H.T@np.linalg.solve(R,H))
        np.testing.assert_allclose(result.P,expected_P,rtol=1e-9,atol=1e-12)
    print('METRIC scipy_MAP_parity',json.dumps({'cost':max_cost,'state':max_state}))


@pytest.mark.p1
def test_nonconvergence_is_explicit():
    mu=np.array([1.,1.,.2,0.]);P=np.diag([.01,.01,.01,1e-5])
    model=SyntheticRF();z=model(mu)[0]+[.1,.2]
    result=map_update(mu,P,z,model,np.diag([.01,.001]),max_iter=0)
    assert result.status=='MAX_ITERATIONS'
    assert result.gradient_inf>1e-8
