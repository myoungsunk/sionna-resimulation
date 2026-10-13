"""Independent RF isolation contracts and Gaussian/Joseph reference checks."""
import math
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import rf_components as r

CASE=dict(anchor=[3.,2.,1.],robot_z_m=.5)
X=np.array([.2,.1,.03])
MU=np.array([.02,.05])
COV=np.diag([.004,.08])
def model(x): return float(x[2]), np.array([0.,0.,1.])
def make(name): return r.make_filter(name,X,r.component_contract())
def update(name,f,z=.1,arm='C'):
    return r.update_filter(name,f,arm,z,3.5,model,CASE,MU,COV,1.345)

@pytest.mark.parametrize('name',r.MODELS)
def test_real_three_states(name):
    f=make(name); assert f.pose.shape==(3,) and f.Ppose.shape==(3,3)

@pytest.mark.parametrize('name',['M0','RF_MEAN_ONLY','RF_VAR_ONLY'])
def test_frozen_gaussian_original_update(name):
    f=make(name); reference=r.DiagnosticFilter(X)
    mu=MU if name=='RF_MEAN_ONLY' else np.zeros(2)
    cov=COV if name=='RF_VAR_ONLY' else np.diag([r.RS,r.RR])
    status,nis=reference.update('C',.1-mu[0],3.5-mu[1],model,CASE['anchor'],CASE['robot_z_m'],rs=cov[0,0],rr=cov[1,1])
    result=update(name,f)
    assert result['status']==status and result['NIS']==nis
    np.testing.assert_array_equal(f.pose,reference.pose)
    np.testing.assert_array_equal(f.Ppose,reference.Ppose)

def test_gate_off_gaussian_against_independent_gain_joseph():
    f=make('RF_GATE_OFF'); x,p=f.pose.copy(),f.Ppose.copy()
    hr,jr=r.range_h(x,CASE['anchor'],CASE['robot_z_m'])
    H=np.array([[0.,0.,1.],jr]); R=np.diag([r.RS,r.RR])
    y=np.array([.1-x[2],3.5-hr]); S=H@p@H.T+R
    K=p@H.T@np.linalg.inv(S); A=np.eye(3)-K@H
    result=update('RF_GATE_OFF',f)
    assert result['status']=='applied' and result['huber_weight']==1.
    np.testing.assert_allclose(f.pose,x+K@y,rtol=1e-12,atol=1e-12)
    np.testing.assert_allclose(f.Ppose,A@p@A.T+K@R@K.T,rtol=1e-12,atol=1e-12)

@pytest.mark.parametrize('arm',['A','C'])
def test_huber_rejection_on_original_prior_nis(arm):
    f=make('RF_HUBER_ONLY'); x,p=f.pose.copy(),f.Ppose.copy()
    prior=r.observation_prior(f,arm,100.,3.5,model,CASE,np.zeros(2),np.diag([r.RS,r.RR]))
    result=update('RF_HUBER_ONLY',f,z=100.,arm=arm)
    assert prior['NIS']>prior['gate_threshold']
    assert result['status']=='rejected_NIS' and result['NIS']==prior['NIS']
    assert result['huber_weight'] is None
    np.testing.assert_array_equal(f.pose,x); np.testing.assert_array_equal(f.Ppose,p)

def test_huber_gate_once_prior_not_posterior():
    f=make('RF_HUBER_ONLY')
    # Acceptable prior NIS, yet residual can invoke Huber downweighting.
    z=f.pose[2]+math.sqrt(r.GATE_1D_99*.8*(f.Ppose[2,2]+r.RS))
    prior=r.observation_prior(f,'A',z,3.5,model,CASE,np.zeros(2),np.diag([r.RS,r.RR]))
    result=update('RF_HUBER_ONLY',f,z=z,arm='A')
    assert result['status']=='applied'
    assert result['NIS']==pytest.approx(prior['NIS'])
    assert 0<result['huber_weight']<=1

def test_full_model_exact_existing_robust_pose():
    f=make('M1B_REPRO'); reference=r.RobustPoseEKF(X)
    expected=reference.update('C',.1,3.5,model,CASE['anchor'],CASE['robot_z_m'],MU,COV,1.345)
    actual=update('M1B_REPRO',f)
    assert actual['NIS']==expected['NIS']
    np.testing.assert_array_equal(f.pose,reference.pose)
    np.testing.assert_array_equal(f.Ppose,reference.Ppose)

def test_no_tuning_contract():
    c=r.component_contract()
    assert c['huber_delta']==1.345 and c['parity_abs_tolerance']==1e-8
    assert c['bias_state'] is False and c['parameter_retuning'] is False
    assert c['cells_per_model']==252 and c['smoke_cells_per_model']==12
