"""New nonsmooth local candidate independent fixture smoke tests.

No original MAP 'CONVERGED' is backfilled by derivative-free candidate.
"""
import math
import numpy as np
from p4_nonsmooth_local import local_nonsmooth_minimize,fixed_objective,probe_directions,frozen_lut_angles
from p3_rf_adapter4 import R0

def test_original_quadratic_gaussian_objective_and_probe_directions():
    mu=np.array([.2,-.1,.05,0.])
    P=np.diag([.3,.2,.1,1e-5])
    z=np.array([.5,.1])
    def model(x):
        H=np.array([[1.,0.,0.,0.],[0.,0.,.5,0.]])
        return np.array([x[0],.5*x[2]]),H
    c,g,L=fixed_objective(mu,P,z,model)
    yy=np.array([.2,-.3,.15,0.])
    eps=1e-6
    for i in range(4):
        v=np.zeros(4);v[i]=eps
        approx=(c(yy+v)-c(yy-v))/(2*eps)
        assert abs(approx-g(yy)[i])<1e-7
    assert len(probe_directions(4))>=104

def test_powell_smooth_model_converges_without_changing_objective():
    mu=np.array([.2,-.1,.05,0.])
    P=np.diag([.03,.02,.01,1e-6])
    z=np.array([.23,.1])
    def model(x):
        H=np.array([[1.,0.,0.,0.],[0.,0.,.5,0.]])
        return np.array([x[0],.5*x[2]]),H
    result=local_nonsmooth_minimize(mu,P,z,model,maxfev=3000)
    assert result["powell_success"],result
    assert result["J_delta"]<=1e-12
    assert result["original_smooth_gradient_inf"]<1e-5
    assert result["probe"]["negative_beyond_1e_minus_5"]==0

def test_kink_model_reports_separate_stationary_contract_not_old_smooth_pass():
    mu=np.array([0.,0.,0.,0.])
    P=np.diag([.05,.02,.1,1e-5])
    z=np.array([0.,-1.])
    def nonsmooth(x):
        H=np.zeros((2,4))
        H[0,0]=1.
        H[1,0]=1. if x[0]>=0 else -1.
        return np.array([x[0],abs(x[0])]),H
    res=local_nonsmooth_minimize(mu,P,z,nonsmooth,maxfev=4500)
    assert res["powell_success"],res
    assert abs(res["candidate_x"][0])<2e-4
    assert res["J_delta"]<=1e-9
    assert "NONSMMOOTH" in res["terminal_status"]
    assert "original_smooth_gradient_satisfied" in res

def test_actual_theta_tx_rx_grid_angle_coordinates_preserved():
    case={"id":"R2_aA_m0","anchor":[4.,0.,2.65],
          "robot_z_m":.45,"mount_deg":0.}
    x=np.array([2.755877,.553919,.106701,0.])
    a=frozen_lut_angles(x,case)
    assert a.shape==(3,)
    assert abs(a[1]+156.)<.005
