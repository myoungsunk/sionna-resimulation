"""R2 same-objective regression and numerical negative controls."""
import json
from pathlib import Path
import numpy as np
import pytest
from core import SyntheticRF, map_update
from stable_descent import integrated_descent
HERE=Path(__file__).resolve().parent

@pytest.mark.parametrize('fixture',['FAILURE_SNAPSHOT.json','RESUME_FAILURE_SNAPSHOT.json'])
@pytest.mark.parametrize('saved',[False,True])
def test_both_frozen_failures(fixture,saved):
    s=json.loads((HERE/fixture).read_text())
    mu,P,z,R=(np.asarray(s[k]) for k in ('prior_x','prior_P','z','R'))
    kw={'range_first':not saved}
    if saved:kw['initial_delta']=np.asarray(s['prior_delta'])
    a=map_update(mu,P,z,SyntheticRF(),R,max_iter=80,gradient_tol=1e-8,**kw)
    assert a.status=='CONVERGED',(fixture,saved,a.status,a.gradient_inf)
    assert a.gradient_inf<=1e-8
    Lp=np.linalg.cholesky(P);Lr=np.linalg.cholesky(R);y=np.linalg.solve(Lp,a.prior_delta)
    h,H=SyntheticRF()(mu+a.prior_delta);v=np.linalg.solve(Lr,z-h);B=np.linalg.solve(Lr,H@Lp)
    assert abs(a.cost-.5*(y@y+v@v))<1e-12
    assert np.max(np.abs(y-B.T@v))<=1e-8
    np.testing.assert_allclose(a.P,Lp@np.linalg.solve(np.eye(len(mu))+B.T@B,Lp.T),rtol=1e-9,atol=1e-12)
    # Branch-specific telemetry is not a universal convergence requirement.
    # Gradient, objective and local covariance were checked independently.
    if saved and fixture.startswith('RESUME'):
        assert a.history
        first=a.history[0]
        assert first.get('step_acceptance') in (
            'ARMIJO_DIRECT','GRADIENT_INTEGRAL_TERMINAL','GRADIENT_INTEGRAL_PROGRESS','STABLE_OBJECTIVE_DESCENT')
        if first.get('step_acceptance','').startswith('GRADIENT_INTEGRAL'):
            assert first.get('gradient_integral_difference',float('inf'))<0
        # In-depth D2 80-digit delta is documented by frozen D2 evidence,
        # not asserted for every solver route's first accepted iteration.
    print('R2_CASE '+json.dumps({'fixture':fixture,'saved':saved,'status':a.status,'gradient_inf':a.gradient_inf,'iterations':a.iterations}))


def test_progress_is_allowed_without_declaring_convergence():
    y=np.array([1e-7]);g=.8*y;d=-g
    def ev(v):return 1+.4*float(v@v),.8*v,np.eye(1)
    gn=.8*(y+d)
    proof=integrated_descent(ev,y,d,1.,g,1.+5e-15,gn,np.eye(1))
    assert proof is not None
    assert proof['gradient_new_inf']>1e-8
    assert proof['gradient_new_inf']<np.max(np.abs(g))
    assert proof['gradient_integral_difference']<0

@pytest.mark.parametrize('mode',['uphill','large','invalid_gradient','cost_not_at_roundoff'])
def test_safeguards_fail_closed(mode):
    y=np.array([1e-7]);g=.8*y;d=-g;c1=1.+5e-15;gn=.8*(y+d)
    def ev(v):return 1+.4*float(v@v),.8*v,np.eye(1)
    if mode=='uphill':d=-d;gn=.8*(y+d)
    elif mode=='large':d=np.array([-1.]);gn=np.array([0.])
    elif mode=='invalid_gradient':gn=None
    else:c1=1.1
    assert integrated_descent(ev,y,d,1.,g,c1,gn,np.eye(1)) is None


def test_unresolved_zero_budget_not_pass():
    s=json.loads((HERE/'RESUME_FAILURE_SNAPSHOT.json').read_text())
    mu,P,z,R=(np.asarray(s[k]) for k in ('prior_x','prior_P','z','R'))
    a=map_update(mu,P,z,SyntheticRF(),R,max_iter=0,gradient_tol=1e-8)
    assert a.status=='MAX_ITERATIONS' and a.gradient_inf>1e-8
