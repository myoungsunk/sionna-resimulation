"""Independent analytic contracts for the separated components."""
from pathlib import Path
import sys
import math
import json
import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from run_ablation import make_filter, update_filter, check_parity, pooled_metrics
from robust_pose_ekf import RobustPoseEKF
from m1_bias_robust_ekf import RobustBiasEKF
from d6_d9_common import EKF3, P0_COV, RS, RR, GATE_1D_99, range_h

CONTRACT = dict(bias_prior_std_dps=.1,bias_rw_dps_sqrt_s=0.)
CASE = dict(anchor=[0.,0.,0.],robot_z_m=1.)

def heading(p): return float(p[2]),np.array([0.,0.,1.])

def test_bias_only_update_with_zero_cross_cov_matches_original():
    x=np.array([1.,2.,.2]); original=EKF3(x,P0_COV.copy())
    bias=make_filter('M1-A',x,CONTRACT)
    a=original.update_heading(.21,RS,s_model=heading)
    b=update_filter('M1-A',bias,'A',.21,2.,heading,CASE,np.zeros(2),np.eye(2),1.345)
    assert a.status==b['status']=='applied'
    np.testing.assert_allclose(bias.pose,original.x,atol=1e-15,rtol=0)
    np.testing.assert_allclose(bias.Ppose,original.P,atol=1e-15,rtol=0)
    assert bias.x[3]==0 and np.all(bias.P[:3,3]==0)

def test_bias_only_preserves_nis_rejection_and_boundary():
    f=make_filter('M1-A',np.array([1.,2.,.2]),CONTRACT)
    p=f.P.copy();x=f.x.copy()
    z=.2+math.sqrt((p[2,2]+RS)*GATE_1D_99)*1.0001
    r=update_filter('M1-A',f,'A',z,2.,heading,CASE,np.zeros(2),np.eye(2),1.345)
    assert r['status']=='rejected_NIS'
    np.testing.assert_array_equal(f.x,x);np.testing.assert_array_equal(f.P,p)

def test_three_state_prediction_is_original_exact_and_no_bias():
    f=RobustPoseEKF([1.,2.,.2]);o=EKF3([1.,2.,.2],P0_COV.copy())
    for ds,yaw,dt in [(.1,.02,.2),(.3,-.05,.2),(.01,0.,.2)]:
        f.predict(ds,yaw,dt);o.predict(ds,yaw,dt)
        np.testing.assert_array_equal(f.x,o.x);np.testing.assert_array_equal(f.P,o.P)
    assert f.x.shape==(3,) and f.P.shape==(3,3)

def test_three_state_gaussian_joint_matches_independent_matrix_solution():
    f=RobustPoseEKF([1.,2.,.2]);x=f.x.copy();p=f.P.copy()
    hr,jr=range_h(x,CASE['anchor'],1.)
    h=np.array([[0.,0.,1.],jr]);r=np.diag([.01,.02]);mu=np.array([.03,-.01])
    z=np.array([.25,hr+.1]);y=z-np.array([.2,hr])-mu
    gain=np.linalg.solve(h@p@h.T+r,h@p).T
    expected_x=x+gain@y;a=np.eye(3)-gain@h
    expected_p=a@p@a.T+gain@r@gain.T
    result=f.update('C',*z,heading,CASE['anchor'],1.,mu,r,np.inf)
    np.testing.assert_allclose(f.x,expected_x,atol=1e-15)
    np.testing.assert_allclose(f.P,expected_p,atol=1e-15)
    assert result['huber_weight']==1.

def test_three_state_robust_stationarity_block_and_missing():
    f=RobustPoseEKF([1.,2.,.2])
    result=f.update('C',3.,9.,heading,CASE['anchor'],1.,np.zeros(2),np.diag([.01,.02]),1.345)
    assert result['huber_weight']<1 and result['H'].shape==(2,3)
    assert result['stationarity_norm']<1e-8
    assert np.linalg.eigvalsh(f.P).min()>0
    x=f.x.copy();p=f.P.copy()
    assert f.update('C',np.nan,np.nan,heading,CASE['anchor'],1.,np.zeros(2),np.eye(2),1.345)['status']=='missing'
    np.testing.assert_array_equal(x,f.x);np.testing.assert_array_equal(p,f.P)

def test_three_state_zero_motion_matches_existing_robust_pose_block():
    a=RobustPoseEKF([1.,2.,.2]);b=RobustBiasEKF([1.,2.,.2])
    for z in [.3,2.,-.4]:
        args=('A',z,None,heading,CASE['anchor'],1.,np.zeros(2),np.diag([.01,.02]),1.345)
        ra=a.update(*args);rb=b.update(*args)
        np.testing.assert_allclose(a.x,b.pose,atol=1e-14,rtol=0)
        np.testing.assert_allclose(a.P,b.Ppose,atol=1e-14,rtol=0)
        assert ra['huber_weight']==pytest.approx(rb['huber_weight'],abs=1e-14)

def test_current_combo_factory_uses_existing_class_exactly():
    f=make_filter('M1-C',np.array([1.,2.,.2]),CONTRACT)
    assert type(f) is RobustBiasEKF

def test_parity_fails_closed_without_tolerance_relaxation():
    base=dict(case='x',channel='full',range_model='B_OLD',condition='noise_pair',level=1,seed=0,arm='C',n=3,
        heading_rmse_deg=1.,xy_rmse_m=1.,mean_pose_NEES=1.,mean_heading_NEES=1.,pose95=1.,accepted_updates=3,rejected_updates=0)
    from run_ablation import key
    rows=[dict(base,model='M0'),dict(base,model='M1-C')]
    refs={m:{key(base):base} for m in ('M0','M1-C')}
    assert check_parity(rows,refs)['status']=='PASS'
    rows[1]['mean_pose_NEES']+=1.01e-8
    with pytest.raises(RuntimeError,match='Parity failure'):check_parity(rows,refs)

def test_contract_numeric_parameters_must_match_initial_experiment():
    from run_ablation import validate_contract
    contract=json.loads((HERE/'contract.json').read_text())
    parent=json.loads((HERE.parent/'experiment_contract.json').read_text())
    validate_contract(contract,parent)
    contract['huber_delta']*=2
    with pytest.raises(RuntimeError,match='Parent contract mismatch'):validate_contract(contract,parent)
