"""B0/L0/L1/L2 paired-input bias-only contract and 3/4-state prediction math."""
import math
import numpy as np
import pytest
from qclean_uwb.drivesim.sensors import DRIFT_LEVELS
from r2_bias_replay import (BIAS_LEVELS,INITIAL_POSE_STD,
    BIAS_PRIOR_STD,build_positive_bias_controls,predict_one)
from core import predict,gaussian_update
from p3_rf_adapter4 import FrozenLut,R0

def test_original_levels_exact():
    assert [x.gyro_bias_dps for x in DRIFT_LEVELS]==[.01,.05,.2]
    assert BIAS_LEVELS=={"B0":0.,"L0":.01,"L1":.05,"L2":.2}

def straight_truth():
    t=np.arange(7,dtype=float)*.2
    p=np.zeros((len(t),3))
    p[:,0]=1.+.1*np.arange(len(t))
    return t,p

def test_true_bias_only_intervention_same_white_noise_and_initial_seed():
    t,truth=straight_truth()
    data={label:build_positive_bias_controls(t,truth,label,0)
          for label in BIAS_LEVELS}
    for lab in BIAS_LEVELS:
        ctl,x=data[lab]
        np.testing.assert_array_equal(x,data["B0"][1])
        np.testing.assert_array_equal(ctl["ds_odom"],data["B0"][0]["ds_odom"])
        expected=math.radians(BIAS_LEVELS[lab])*ctl["dt_s"]
        np.testing.assert_allclose(
            ctl["dtheta_gyro"]-data["B0"][0]["dtheta_gyro"],
            expected,atol=1e-16,rtol=0)

def test_dr3_vs_dr4_pose_initial_equivalence_and_cross_cov_appears():
    x=np.array([1.0,.5,.2])
    P=np.diag([.01,.01,math.radians(5)**2])
    x4=np.r_[x,0.]
    P4=np.zeros((4,4));P4[:3,:3]=P;P4[3,3]=BIAS_PRIOR_STD**2
    ds,da,dt=.1,.002,.2
    xa,Pa=predict_one(x,P,ds,da,dt)
    xb,Pb=predict_one(x4,P4,ds,da,dt)
    np.testing.assert_allclose(xa,xb[:3],atol=1e-14,rtol=0)
    assert np.all(abs(Pb[:3,3])>0)
    assert Pb[2,3]<0
    assert Pb[2,2]>Pa[2,2]

def test_s_only_can_update_bias_after_motion_generates_pose_bias_crosscov():
    lut=FrozenLut()
    case={"anchor":[4.,0.,2.65],"mount_deg":45.,
          "robot_z_m":.45,"id":"R2_aA_m45"}
    x=np.array([5.,.8,.25,0.])
    P=np.diag([.01,.01,.02,BIAS_PRIOR_STD**2])
    x,P=predict_one(x,P,.1,.015,.2)
    h,H=lut.model(x,case)
    assert H[1,3]==0
    m=lambda xx:(lut.model(xx,case)[0][1:],lut.model(xx,case)[1][1:,:])
    state,post,info=gaussian_update(x,P,np.array([h[1]+.02]),m,R0[1:,1:])
    assert info["accepted"]
    assert abs(state[3]-x[3])>0
    assert abs(post[3,3]-P[3,3])>0

def test_no_gyrobias_state_in_3state():
    x=np.array([1.,.5,.2])
    P=np.diag([.01,.01,math.radians(5)**2])
    out,cov=predict_one(x,P,.1,.01,.2)
    assert len(out)==3 and cov.shape==(3,3)
