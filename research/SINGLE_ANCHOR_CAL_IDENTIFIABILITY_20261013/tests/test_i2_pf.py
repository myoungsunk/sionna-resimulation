import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from i2_ideal_range_calibration import pf, summarize

def fixture():
    p=dict(t_s=np.arange(6)*.2,dt_s=np.r_[0.,np.full(5,.2)],ds_odom=np.r_[0.,np.full(5,.1)],dtheta_gyro=np.zeros(6),dtheta_odom=np.zeros(6),x0=np.zeros(6),range_m=np.ones(6)*4,range_mask=np.ones(6,bool))
    c=dict(p0_std=[.03,.03,.03,.002,.01,.006],wheel_base=.287,k_s=2e-5,k_theta=1e-4,k_stheta=1e-5,gyro_N_rad_sqrt_s=.00026,anchor_xyz=[4,0,2.65],robot_z=.45,range_sigma=.05)
    return p,c

def test_truth_independence_and_determinism():
    p,c=fixture(); s,r=pf(p,c,'RANGE',500,42,[0,5])
    p['truth6']=np.full((6,6),np.nan)
    s2,r2=pf(p,c,'RANGE',500,42,[0,5])
    for k in r: np.testing.assert_array_equal(r[k],r2[k])
    assert all(np.isclose(r[k].sum(),1) for k in r if k.startswith('weights'))

def test_disabled_range_does_not_affect_dr():
    p,c=fixture(); _,r=pf(p,c,'DR',500,3,[5]); p['range_m'][:]=np.nan
    _,r2=pf(p,c,'DR',500,3,[5])
    for k in r: np.testing.assert_array_equal(r[k],r2[k])

def test_joint_empirical_mass_and_degenerate():
    x=np.random.default_rng(1).normal(size=(10000,6)); w=np.full(10000,.0001)
    s=summarize(x,w); delta=x[:,[3,5]]-s['mean']
    inside=np.einsum('ij,ji->i',delta,np.linalg.solve(s['cov'],delta.T))<=s['joint_radius']
    assert abs(w@inside-.95)<.001
    assert not summarize(np.zeros((10,6)),np.ones(10)/10)['joint_valid']

def test_matheron_conditional_moments():
    rng=np.random.default_rng(9); q=np.array([.1,.04,.02]); b=np.array([.3,-.8,1.]); y=.15
    z=rng.normal(size=(3,150000))*np.sqrt(q)[:,None]; variance=(b*b)@q
    z+=((q*b)[:,None])*(y-b@z)/variance
    np.testing.assert_allclose(z[:2].mean(axis=1),q[:2]*b[:2]*y/variance,atol=.002)
    target=np.diag(q)-np.outer(q*b,q*b)/variance
    np.testing.assert_allclose(np.cov(z)[:2,:2],target[:2,:2],atol=.002)
