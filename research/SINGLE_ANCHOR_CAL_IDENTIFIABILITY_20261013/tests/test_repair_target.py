import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from i2_s0_batch import S0BatchTarget
from repair_target import full_log_density, log_rho_density, mh_log_ratio
from test_i2_s0_batch import inputs


def setup_target():
    public, cfg = inputs()
    return S0BatchTarget(public, cfg, 'RANGE')


def test_complete_density_includes_radial_and_both_gaussian_priors():
    t=setup_target(); p=np.array([.86,.4,.1,-.2,.3]); z=np.full((2,3),.2)
    expected=t.evaluate(p,z)+t.table.logpdf(p[0])-np.log(2*np.pi)
    expected-=.5*(p[2:]@p[2:]+3*np.log(2*np.pi))
    expected-=.5*(np.sum(z*z)+z.size*np.log(2*np.pi))
    assert full_log_density(t,p,z)==pytest.approx(expected,abs=1e-12)
    q=p.copy(); q[0]=.93
    full_delta=full_log_density(t,q,z)-full_log_density(t,p,z)
    ll_delta=t.evaluate(q,z)-t.evaluate(p,z)
    assert abs(full_delta-ll_delta)>1e-3
    assert full_delta-ll_delta==pytest.approx(t.table.logpdf(q[0])-t.table.logpdf(p[0]))


def test_independent_radial_cancels_only_with_proposal_ratio():
    t=setup_target(); p=np.array([.86,.4,.1,-.2,.3]); q=p.copy();q[0]=.93;z=np.zeros((2,3))
    alpha=mh_log_ratio(full_log_density(t,q,z),full_log_density(t,p,z),
                      t.table.logpdf(p[0]),t.table.logpdf(q[0]))
    assert alpha==pytest.approx(t.evaluate(q,z)-t.evaluate(p,z))


def test_log_radius_jacobian_and_detailed_balance():
    t=setup_target(); p=np.array([.86,.4,.1,-.2,.3]);q=p+np.array([.01,.03,.02,0.,-.01]);z=np.zeros((2,3))
    eta=p.copy(); eta[0]=np.log(p[0])
    assert log_rho_density(t,eta,z)==pytest.approx(full_log_density(t,p,z)+np.log(p[0]))
    a,b=full_log_density(t,p,z),full_log_density(t,q,z)
    forward,reverse=-1.3,-.8
    ratio=mh_log_ratio(b,a,reverse,forward)
    assert a+forward+min(0.,ratio)==pytest.approx(b+reverse+min(0.,-ratio))


def test_support_is_rejected_not_repaired():
    t=setup_target();p=np.array([-.1,0.,0.,0.,0.]);z=np.zeros((2,3))
    assert np.isneginf(full_log_density(t,p,z))
    p[0]=.9;p[1]=4.
    assert np.isneginf(full_log_density(t,p,z))
