"""Exact baseline, independent Joseph, unchanged gate and constant-weight checks."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixed_weight_control as k

X=np.array([.2,.1,.03]); ANCHOR=[3.,2.,1.]
def model(x): return float(x[2]),np.array([0.,0.,1.])
def update(f,arm='C',zs=.08,zr=3.5):
    return f.update(arm,zs,zr,model,ANCHOR,.5)

@pytest.mark.parametrize('arm,zs,zr',[('A',.08,None),('B',None,3.5),('C',.08,3.5),
    ('C',None,3.5),('C',.08,None)])
def test_unit_weight_exact_m0(arm,zs,zr):
    f=k.FixedWeightPoseEKF(X,weight=1.); ref=k.DiagnosticFilter(X)
    expected_status,expected_nis=ref.update(arm,zs,zr,model,ANCHOR,.5)
    result=update(f,arm,zs,zr)
    assert result['status']==expected_status and result['NIS']==expected_nis
    np.testing.assert_array_equal(f.pose,ref.pose)
    np.testing.assert_array_equal(f.Ppose,ref.Ppose)

def test_one_third_independent_gain_joseph():
    f=k.FixedWeightPoseEKF(X); x=f.pose.copy(); p=f.P.copy()
    hr,jr=k.range_h(x,ANCHOR,.5)
    h=np.array([[0.,0.,1.],jr]); r0=np.diag([k.RS,k.RR])
    y=np.array([.08-x[2],(3.5+k.B_OLD)-(hr+k.B_OLD)])
    effective=3*r0
    gain=np.linalg.solve(h@p@h.T+effective,h@p).T
    a=np.eye(3)-gain@h
    result=update(f)
    np.testing.assert_allclose(result['R_effective'],effective,atol=1e-16)
    np.testing.assert_allclose(f.pose,x+gain@y,atol=1e-15)
    np.testing.assert_allclose(f.P,a@p@a.T+gain@effective@gain.T,atol=1e-15)
    assert result['robust_weight']==1/3
    assert np.linalg.eigvalsh(f.P).min()>0

def test_gate_original_r0_rejects_even_when_inflated_would_accept():
    f=k.FixedWeightPoseEKF(X); x=f.pose.copy(); p=f.P.copy()
    # 1D NIS=8 under R0, but <99% threshold under 3R0.
    zs=x[2]+np.sqrt(8*(p[2,2]+k.RS))
    assert (zs-x[2])**2/(p[2,2]+3*k.RS)<k.GATE_1D_99
    result=update(f,'A',zs,None)
    assert result['status']=='rejected_NIS' and result['NIS']>k.GATE_1D_99
    np.testing.assert_array_equal(f.pose,x); np.testing.assert_array_equal(f.P,p)

def test_common_weight_independent_of_residual():
    results=[]
    for zs in (.03,.05,.10):
        f=k.FixedWeightPoseEKF(X)
        hr,_=k.range_h(f.pose,ANCHOR,.5)
        results.append(update(f,'C',zs,hr+.04))
    assert all(r['robust_weight']==1/3 for r in results)
    assert all(r['observation_dimension']==2 for r in results)
    for result in results[1:]:
        np.testing.assert_array_equal(result['R_effective'],results[0]['R_effective'])

def test_reset_identical_prior_and_no_alias():
    f=k.FixedWeightPoseEKF(X); x=np.array([1.,2.,.4]); p=np.diag([.1,.2,.3])
    f.reset(x,p); x[:]=0; p[:]=0
    np.testing.assert_array_equal(f.pose,[1.,2.,.4])
    np.testing.assert_array_equal(f.P,np.diag([.1,.2,.3]))
    prior_x=f.pose.copy(); prior_p=f.P.copy()
    with pytest.raises(ValueError): f.reset(np.zeros(3),np.zeros((3,3)))
    np.testing.assert_array_equal(f.pose,prior_x); np.testing.assert_array_equal(f.P,prior_p)

def test_missing_and_prediction_parity():
    f=k.FixedWeightPoseEKF(X); ref=k.DiagnosticFilter(X)
    assert update(f,'C',None,None)['status']=='missing'
    f.predict(.1,.03,.2); ref.predict(.1,.03,.2)
    np.testing.assert_array_equal(f.pose,ref.pose); np.testing.assert_array_equal(f.Ppose,ref.Ppose)

@pytest.mark.parametrize('weight',[0.,-1.,float('nan'),float('inf'),1.01])
def test_invalid_weight(weight):
    with pytest.raises(ValueError): k.FixedWeightPoseEKF(X,weight=weight)
