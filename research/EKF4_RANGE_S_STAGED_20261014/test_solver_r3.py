"""R3 independent numerical regression: NEVER accept unresolved uphill cost."""
import json
from pathlib import Path
import math
import numpy as np
import pytest
from core import SyntheticRF, map_update
from solver_r3 import resolved_armijo, exact_newton_direction

HERE = Path(__file__).resolve().parent


def test_old_positive_roundoff_armijo_would_accept_uphill_but_r3_refuses():
    eps = np.finfo(float).eps
    c0, c1, slope = 1.0, 1.0+2*eps, -1e-15
    old = c1 <= c0+1e-4*slope+4*eps*max(1., abs(c0))
    assert old, 'This fixture targets the actual permissive R2 branch'
    assert not resolved_armijo(c0,c1,slope)


@pytest.mark.parametrize('c0,c1,slope,accepted',[
    (1.0, 0.9, -0.2, True),
    (1.0, 1.0, -1e-15, False),
    (1.0, 1.0+1e-15, -1e-15, False),
    (1.0, 1.0-1e-15, -1e-15, False),
    (1.0, 0.9, 0.1, False),
    (1.0, math.inf, -1., False)])
def test_resolved_direct_sufficient_decrease(c0,c1,slope,accepted):
    assert resolved_armijo(c0,c1,slope) == accepted


def test_guarded_exact_hessian_recovers_true_curvature():
    def evaluate(y):
        x = float(y[0])
        return .5*(2*x*x + .25*x**4), np.array([2*x+.5*x**3]), np.array([[2.]])
    y = np.array([.04])
    g = evaluate(y)[1]
    step = exact_newton_direction(evaluate,y,g)
    assert step is not None
    np.testing.assert_allclose(step, -g/(2+1.5*y*y), atol=2e-9, rtol=0)


def test_indefinite_exact_hessian_is_rejected():
    def evaluate(y):
        return -0.5*float(y@y), -y, -np.eye(len(y))
    y = np.array([.01])
    assert exact_newton_direction(evaluate,y,-y) is None


@pytest.mark.parametrize('fixture',['FAILURE_SNAPSHOT.json','RESUME_FAILURE_SNAPSHOT.json'])
@pytest.mark.parametrize('saved',[False,True])
def test_r3_original_frozen_regressions_and_acceptance_signs(fixture,saved):
    s = json.loads((HERE/fixture).read_text())
    mu,P,z,R = (np.asarray(s[k]) for k in ('prior_x','prior_P','z','R'))
    kw = {'range_first':not saved}
    if saved:
        kw['initial_delta'] = np.asarray(s['prior_delta'])
    result = map_update(mu,P,z,SyntheticRF(),R,max_iter=80,gradient_tol=1e-8,**kw)
    assert result.status=='CONVERGED', (fixture,saved,result.status,result.gradient_inf)
    assert result.gradient_inf <= 1e-8
    for row in result.history:
        if row.get('step_acceptance') == 'ARMIJO_DIRECT':
            assert row['direct_cost_difference'] < 0
        if row.get('step_acceptance','').startswith('GRADIENT_INTEGRAL'):
            assert row['gradient_integral_difference'] < 0
    Lp,Lr=np.linalg.cholesky(P),np.linalg.cholesky(R)
    y=np.linalg.solve(Lp,result.prior_delta)
    h,H=SyntheticRF()(mu+result.prior_delta)
    v=np.linalg.solve(Lr,z-h)
    B=np.linalg.solve(Lr,H@Lp)
    assert np.max(np.abs(y-B.T@v))<=1e-8
    assert abs(result.cost-.5*(y@y+v@v))<1e-12
    np.testing.assert_allclose(result.P,Lp@np.linalg.solve(np.eye(len(y))+B.T@B,Lp.T),atol=1e-12,rtol=1e-9)
    print('R3_SNAPSHOT '+json.dumps({
        'fixture':fixture,'saved':saved,'gradient_inf':result.gradient_inf,
        'iterations':result.iterations,
        'accepts':[a.get('step_acceptance') for a in result.history if 'step_acceptance' in a]}))
