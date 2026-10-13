import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from i2_s0 import pf_s0,summary

def fixture(n=6):
    p=dict(t_s=np.arange(n)*.2,dt_s=np.r_[0.,np.full(n-1,.2)],ds_odom=np.r_[0.,np.full(n-1,.1)],dtheta_gyro=np.zeros(n),dtheta_odom=np.zeros(n),range_m=np.full(n,4.),range_mask=np.ones(n,bool))
    cfg=dict(p0_std=[0,0,0,.002,.01,.006],wheel_base=.287,k_s=2e-5,k_theta=1e-4,k_stheta=1e-5,gyro_N_rad_sqrt_s=.00026,anchor_xyz=[0,0,2.65],robot_z=.45,range_sigma=.05)
    return p,cfg

def test_first_range_is_not_reweighted_and_heading_is_uniform():
    p,c=fixture(1);s,raw,_=pf_s0(p,c,'RANGE',20000,42,[0])
    np.testing.assert_array_equal(raw['weights_0'],np.full(20000,1/20000))
    assert s[0]['range_updates_after_initialization']==0
    assert s[0]['initial_delta_resultant']<.025
    assert s[0]['initial_rho_quantiles'][2]>s[0]['initial_rho_quantiles'][0]

def test_dr_gauge_and_truth_rejection():
    p,c=fixture();s,raw,_=pf_s0(p,c,'DR',1000,9,[0,5])
    np.testing.assert_array_equal(raw['initial_rho_delta_0'],np.zeros((1000,2)))
    p['range_m'][:]=np.nan
    _,r2,_=pf_s0(p,c,'DR',1000,9,[0,5])
    for k in raw:np.testing.assert_array_equal(raw[k],r2[k])
    p['x0']=np.zeros(6)
    with pytest.raises(ValueError):pf_s0(p,c,'DR',1000,9,[0,5])

def test_count_range_and_reproducibility():
    p,c=fixture();s,r,_=pf_s0(p,c,'RANGE',1000,5,[5])
    assert s[0]['range_updates_after_initialization']==5
    _,r2,_=pf_s0(p,c,'RANGE',1000,5,[5])
    for k in r:np.testing.assert_array_equal(r[k],r2[k])

def test_collapsed_or_collinear_joint_region_is_invalid():
    c=np.full((100,3),[.003,.002,.004]);w=np.ones(100)/100
    assert not summary(c,w)['joint_valid']
    c[:,0]=np.linspace(-1,1,100);c[:,2]=2*c[:,0]
    assert not summary(c,w)['joint_valid']

def test_scaled_joint_region_contains_empirical_mass():
    c=np.random.default_rng(3).normal(size=(10000,3))*[.002,.01,.006]
    w=np.ones(10000)/10000;s=summary(c,w)
    d=c[:,[0,2]]-s['mean'];q=np.einsum('ij,ji->i',d,np.linalg.solve(s['cov'],d.T))
    assert abs(np.mean(q<=s['joint_radius'])-.95)<.001
