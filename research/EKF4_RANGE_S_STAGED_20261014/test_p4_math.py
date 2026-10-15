"""P4 algebraic invariants and destructive negative tests before RF experiments."""
from __future__ import annotations
import math,os
import numpy as np
import pytest
from core import gaussian_update,sequential_affine,conditional_rf,map_update
from p4_pre_run_audit import require_p4_audit
from p4_one_step_models import prior_pair,fixed_methods,map_methods,BIAS_PRIOR_STD_RAD_S
from p3_rf_adapter4 import FrozenLut,R0,B_OLD,GATE_JOINT

@pytest.fixture(scope="session",autouse=True)
def preaudit():
    require_p4_audit(os.environ["EKF4_P4_AUDIT_RECEIPT"])

def positive(n):
    rng=np.random.default_rng(31415+n)
    A=rng.normal(size=(n,n))
    return A@A.T+np.eye(n)

@pytest.mark.parametrize("corr",[-.85,0.,.7])
@pytest.mark.parametrize("n",[3,4])
def test_independent_linear_joint_equals_both_frozen_orders_even_correlated_R(corr,n):
    rng=np.random.default_rng(600+n)
    mu=rng.normal(size=n)*.1
    mu[2]=.2
    P=positive(n)*.01
    H=rng.normal(size=(2,n))
    if n==4:H[:,3]=0
    h=H@mu
    z=h+np.array([.08,-.12])
    R=np.array([[.6,corr*math.sqrt(.42)],[corr*math.sqrt(.42),.7]])
    model=lambda x:(h,H)
    x,C,_=gaussian_update(mu,P,z,model,R)
    xr,Cr,_=sequential_affine(mu,P,z,h,H,R)
    xs,Cs,_=sequential_affine(mu,P,z[::-1],h[::-1],H[::-1],R[::-1,::-1])
    np.testing.assert_allclose(x,xr,atol=1e-12,rtol=0)
    np.testing.assert_allclose(C,Cr,atol=1e-12,rtol=0)
    np.testing.assert_allclose(x,xs,atol=1e-12,rtol=0)
    np.testing.assert_allclose(C,Cs,atol=1e-12,rtol=0)
    er,es,vr,vs,hs=conditional_rf(z-h,H,R)
    v=z-h
    assert abs(float(v@np.linalg.solve(R,v))-(er*er/vr+es*es/vs))<1e-10

def test_zero_pose_bias_cross_gives_zero_one_step_bias_information():
    mu=np.array([3.,1.,.3,0.])
    P=np.zeros((4,4));P[:3,:3]=positive(3)*.01
    P[3,3]=BIAS_PRIOR_STD_RAD_S**2
    H=np.array([[.7,.2,0.,0.],[.08,.05,.41,0.]])
    h=np.array([2.1,.1]);z=np.array([2.4,.2])
    x,C,_=gaussian_update(mu,P,z,lambda v:(h,H),R0)
    assert x[3]==0.
    assert abs(C[3,3]-P[3,3])<1e-16
    np.testing.assert_array_equal(C[:3,3],np.zeros(3))
    x3,C3,_=gaussian_update(mu[:3],P[:3,:3],z,
                             lambda v:(h,H[:,:3]),R0)
    np.testing.assert_allclose(x[:3],x3,atol=1e-12,rtol=0)
    np.testing.assert_allclose(C[:3,:3],C3,atol=1e-12,rtol=0)

def test_nonzero_cross_can_update_bias_in_mathematical_negative_control():
    mu=np.array([1.,2.,.2,0.])
    P=np.diag([.04,.03,.05,1e-5])
    P[3,2]=P[2,3]=.0002
    assert np.linalg.eigvalsh(P).min()>0
    h=np.array([2.,.3])
    H=np.array([[1.,0.,0.,0.],[0.,0.,.4,0.]])
    x,C,_=gaussian_update(mu,P,h+np.array([0.,.25]),
                           lambda v:(h,H),R0)
    assert abs(x[3])>1e-7
    assert C[3,3]<P[3,3]

def test_common_gate_reject_keeps_prior_unchanged():
    mu=np.array([1.,1.,.3,0.])
    P=np.diag([.01,.01,.02,BIAS_PRIOR_STD_RAD_S**2])
    H=np.array([[1.,0.,0.,0.],[0.,0.,.5,0.]])
    h=np.array([1.,0.])
    z=h+np.array([10.,0.])
    x,C,info=gaussian_update(mu,P,z,lambda v:(h,H),R0,
                              gate_threshold=GATE_JOINT)
    assert not info["accepted"]
    np.testing.assert_array_equal(x,mu)
    np.testing.assert_array_equal(C,P)

def test_los_physical_range_order_and_bad_double_offset_negative_control():
    lut=FrozenLut()
    case={"id":"R2_aA_m0","anchor":[4.,0.,2.65],"robot_z_m":.45,"mount_deg":0}
    x=np.array([5.43,.96,.31,0.])
    h,H=lut.model(x,case)
    rho=float(np.linalg.norm([x[0]-4.,x[1],.45-2.65]))
    assert abs(h[0]-rho-B_OLD)<1e-12
    assert np.max(abs(H[:,3]))==0
    assert abs((h[0]+B_OLD)-h[0])>.5
    assert abs(h[0]-h[1])>.1
    assert R0[0,0]==.0068578637 and R0[1,1]==.0081

def test_range_first_is_only_warm_start_for_same_fixed_posterior():
    P=np.diag([.1,.1,.02,1e-5])
    mu=np.array([5.2,1.,.3,0.])
    def model(x):
        H=np.array([[1.,0.,0.,0.],[0.,0.,.6,0.]])
        return np.array([x[0],.6*x[2]]),H
    z=np.array([5.23,.23])
    rp=map_update(mu,P,z,model,R0,range_first=False,max_iter=80,gradient_tol=1e-8)
    rr=map_update(mu,P,z,model,R0,range_first=True,max_iter=80,gradient_tol=1e-8)
    assert rp.status==rr.status=="CONVERGED"
    np.testing.assert_allclose(rr.x,rp.x,rtol=0,atol=1e-11)
    np.testing.assert_allclose(rr.P,rp.P,rtol=0,atol=1e-12)

def test_no_invalid_posterior_covariance_is_faked():
    P=np.diag([.1,.1,.02,BIAS_PRIOR_STD_RAD_S**2])
    mu=np.array([1.,2.,.3,0.])
    bad_R=np.array([[-.5,0.],[0.,1.]])
    with pytest.raises(ValueError):
        gaussian_update(mu,P,np.zeros(2),
                        lambda v:(np.zeros(2),np.zeros((2,4))),bad_R)

def test_r0_independence_does_not_imply_diagonal_innovation_covariance():
    H=np.array([[.2,.5,0.,0.],[.1,.3,.5,0.]])
    P=np.zeros((4,4));P[:3,:3]=positive(3)*.01
    P[3,3]=BIAS_PRIOR_STD_RAD_S**2
    S=H@P@H.T+R0
    assert abs(S[0,1])>1e-6
    assert np.linalg.eigvalsh(S).min()>0
