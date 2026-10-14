"""R1 numerical-only regression against the immutable first P2 failure."""
import json
import math
from pathlib import Path
import numpy as np
import pytest
from core import SyntheticRF, map_update

HERE = Path(__file__).resolve().parent

def frozen():
    s = json.loads((HERE/'FAILURE_SNAPSHOT.json').read_text())
    d = json.loads((HERE/'D1_RESULT_SUMMARY.json').read_text())
    return s,d,np.asarray(s['prior_x']),np.asarray(s['prior_P']),np.asarray(s['z']),np.asarray(s['R'])

def independent_grad(mu,P,z,R,delta):
    model = SyntheticRF()
    Lp,Lr = np.linalg.cholesky(P),np.linalg.cholesky(R)
    y = np.linalg.solve(Lp,delta)
    h,H = model(mu+Lp@y)
    v = np.linalg.solve(Lr,z-h)
    B = np.linalg.solve(Lr,H@Lp)
    return y, y-B.T@v, np.eye(len(y))+B.T@B, .5*float(y@y+v@v)

@pytest.mark.regression
def test_saved_failed_terminal_iterate_repaired_at_original_threshold():
    s,d,mu,P,z,R=frozen()
    assert s['recorded_status']=='LINE_SEARCH_FAILED'
    assert s['source_run_id']==38514443823
    assert d['original_failure_reproduced']
    assert d['unchanged_required_gradient_inf']==1e-8
    a=map_update(mu,P,z,SyntheticRF(),R,range_first=False,
                 initial_delta=np.asarray(s['prior_delta']),max_iter=40,gradient_tol=1e-8)
    assert a.status=='CONVERGED', (a.status,a.gradient_inf)
    assert a.gradient_inf<=1e-8
    # Any valid accepted branch is permissible. The optional line-integral
    # metadata is tested separately by its independent fixed-input check.
    first=a.history[0]
    assert first.get('step_acceptance') in (
        'ARMIJO_DIRECT','GRADIENT_INTEGRAL_TERMINAL','GRADIENT_INTEGRAL_PROGRESS')
    if first.get('step_acceptance','').startswith('GRADIENT_INTEGRAL'):
        assert first.get('gradient_integral_difference',float('inf'))<0
        assert first.get('gradient_new_inf',float('inf'))<=1e-8
    assert np.linalg.eigvalsh(a.P)[0]>0
    assert np.max(np.abs(a.prior_delta-np.asarray(s['prior_delta'])))<1e-6
    print('R1_TERMINAL',json.dumps({'status':a.status,'old_gradient':s['recorded_gradient_inf'],
           'new_gradient':a.gradient_inf,'float_delta':first['direct_cost_difference'],
           'integral_delta':first['gradient_integral_difference']}))

@pytest.mark.regression
def test_integral_difference_matches_previously_frozen_80_digit_reference():
    s,d,mu,P,z,R=frozen()
    y,g,A,c=independent_grad(mu,P,z,R,np.asarray(s['prior_delta']))
    step=np.linalg.solve(A,-g)
    Lp=np.linalg.cholesky(P)
    _,gm,_,_=independent_grad(mu,P,z,R,Lp@(y+.5*step))
    _,gn,_,cnew=independent_grad(mu,P,z,R,Lp@(y+step))
    area=math.fsum(float(a)*float(b) for a,b in zip((g+4*gm+gn)/6,step))
    ref=float(d['diagnostic_full_GN_step']['mpmath_80_digit_cost_change'])
    assert cnew-c>0 and area<0 and ref<0
    assert abs(area-ref)<1e-19
    assert np.max(np.abs(gn))<1e-8
    print('R1_INTEGRAL',json.dumps({'double_delta':cnew-c,'integral_delta':area,'reference_80_digit':ref}))

@pytest.mark.regression
def test_original_range_first_initialization_and_same_objective():
    s,d,mu,P,z,R=frozen()
    a=map_update(mu,P,z,SyntheticRF(),R,range_first=True,max_iter=40,gradient_tol=1e-8)
    assert a.status=='CONVERGED', (a.status,a.gradient_inf)
    assert a.gradient_inf<=1e-8
    y,g,A,c=independent_grad(mu,P,z,R,a.prior_delta)
    assert abs(c-a.cost)<2e-14
    assert np.max(np.abs(g))<=1e-8
    Lp=np.linalg.cholesky(P)
    np.testing.assert_allclose(a.P,Lp@np.linalg.solve(A,Lp.T),atol=1e-10,rtol=1e-10)
    assert abs(a.prior_delta[2])<np.pi
    assert np.max(np.abs(a.prior_delta-np.asarray(s['prior_delta'])))<1e-5
    print('R1_RANGE_FIRST',json.dumps({'status':a.status,'gradient':a.gradient_inf,'iterations':a.iterations}))

@pytest.mark.regression
def test_stricter_unsupported_precision_does_not_falsely_pass():
    s,d,mu,P,z,R=frozen()
    a=map_update(mu,P,z,SyntheticRF(),R,range_first=False,
                 initial_delta=np.asarray(s['prior_delta']),max_iter=4,gradient_tol=1e-16)
    assert a.status!='CONVERGED'
    assert a.gradient_inf>1e-16

@pytest.mark.regression
def test_chart_and_initialization_contract_failure():
    s,d,mu,P,z,R=frozen()
    with pytest.raises(ValueError,match='mutually exclusive'):
        map_update(mu,P,z,SyntheticRF(),R,range_first=True,initial_delta=np.asarray(s['prior_delta']))
    invalid=np.asarray(s['prior_delta']).copy();invalid[2]=np.pi
    with pytest.raises(ValueError,match='outside'):
        map_update(mu,P,z,SyntheticRF(),R,range_first=False,initial_delta=invalid)
    with pytest.raises(ValueError,match='finite'):
        map_update(mu,P,z,SyntheticRF(),R,range_first=False,initial_delta=np.array([np.nan,0,0]))
