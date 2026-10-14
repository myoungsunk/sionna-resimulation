"""R3 numerical safeguard: same scalar objective, branch-neutral assertions."""
import numpy as np
import pytest
from stable_descent import integrated_descent
from core import SyntheticRF,map_update
@pytest.mark.r3
def test_numerically_unresolved_valid_descent():
 y=np.array([1e-7]);g=.8*y;d=-g
 def e(v):return 1.+.4*float(v@v),.8*v,np.eye(1)
 proof=integrated_descent(e,y,d,1.,g,1.+5e-15,.8*(y+d),np.eye(1))
 assert proof is not None
 assert proof['gradient_integral_difference']<0
 assert proof['quadrature_error_indicator']>=0
@pytest.mark.r3
@pytest.mark.parametrize('branch',['uphill','large','nonfinite','big_cost_increase'])
def test_invalid_terminal_step_never_claimed(branch):
 y=np.array([1e-7]);g=.8*y;d=-g;g1=.8*(y+d);c1=1.+5e-15
 def e(v):return 1.+.4*float(v@v),.8*v,np.eye(1)
 if branch=='uphill':d=-d;g1=.8*(y+d)
 if branch=='large':d=np.array([-1.]);g1=np.array([0.])
 if branch=='nonfinite':g1=np.array([np.nan])
 if branch=='big_cost_increase':c1=1.1
 assert integrated_descent(e,y,d,1.,g,c1,g1,np.eye(1)) is None
@pytest.mark.r3
def test_high_precision_not_automatically_treated_as_coverage():
 x=np.array([1.,1.,.2,0.]);P=np.diag([.01,.01,.02,1e-6])
 z=SyntheticRF()(x)[0]
 a=map_update(x,P,z,SyntheticRF(),np.diag([.0025,.0009]),max_iter=20)
 assert a.status=='CONVERGED'
 assert a.gradient_inf<=1e-8
 assert a.P.shape==(4,4)
