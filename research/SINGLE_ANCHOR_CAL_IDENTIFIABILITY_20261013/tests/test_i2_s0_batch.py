import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm

sys.path.insert(0,str(Path(__file__).parents[1]))
from i2_s0_batch import radial_table, S0BatchTarget, batch_s0


def inputs():
    public=dict(t_s=np.arange(4)*.2,dt_s=np.array([0.,.2,.2,.2]),
                ds_odom=np.array([0.,.04,.035,.05]),
                dtheta_gyro=np.array([0.,.01,-.02,.03]),
                dtheta_odom=np.array([0.,.012,-.015,.025]),
                range_m=np.array([1.,1.04,1.08,1.1]),
                range_mask=np.ones(4,dtype=bool))
    cfg=dict(p0_std=[.03,.03,.04,.002,.01,.006],wheel_base=.287,
             anchor_xyz=[0.,0.,1.],robot_z=.5,k_s=2e-5,k_theta=1e-4,
             k_stheta=1e-5,gyro_N_rad_sqrt_s=.0003,range_sigma=.05)
    return public,cfg


@pytest.mark.parametrize("prior",["area","radius","halfnormal10","halfnormal100"])
def test_radial_normalization_moments_and_inverse_cdf(prior):
    tab=radial_table(2.,.2,.5,prior)
    assert quad(lambda r:np.exp(tab.logpdf(r)),0,tab.hi,epsabs=1e-10)[0]==pytest.approx(1.,abs=1e-9)
    expected=quad(lambda r:r*np.exp(tab.logpdf(r)),0,tab.hi,epsabs=1e-10)[0]
    p=np.linspace(.00001,.99999,100001)
    values=np.interp(p,tab.cdf,tab.grid)
    assert values.mean()==pytest.approx(expected,abs=2e-5)
    assert tab.diagnostics["numerical_tail_mass_bound"]<=1e-12
    assert tab.diagnostics["quadrature_relative_error"]<=1e-9
    assert tab.diagnostics["quantile_resolution_error_m"]<=1e-5
    samples=tab.sample(np.random.default_rng(14),100)
    assert np.all((samples>=0)&(samples<=tab.hi))


def test_area_jacobian_and_cutoff_mass():
    area=radial_table(2.,.2,.5,"area")
    radius=radial_table(2.,.2,.5,"radius")
    points=np.array([1.2,1.8,2.1])
    ratio=np.exp(area.logpdf(points)-radius.logpdf(points))/points
    np.testing.assert_allclose(ratio,ratio[0],rtol=1e-12)
    cut=radial_table(2.,.2,.5,"area",6)
    assert 0<cut.diagnostics["excluded_mass_fraction"]<1e-7
    assert np.isneginf(cut.logpdf(cut.hi+.01))


def test_near_height_boundary_and_negative_measurement():
    for z in (.4,.5,.6,-.2):
        tab=radial_table(z,.1,.5)
        assert quad(lambda r:np.exp(tab.logpdf(r)),0,tab.hi)[0]==pytest.approx(1.,abs=1e-9)
        assert tab.diagnostics["numerical_tail_mass_bound"]<1e-12


def test_first_range_consumed_once_and_gauge():
    public,cfg=inputs()
    target=S0BatchTarget(public,cfg,"RANGE")
    param=np.array([.8,.4,0.,0.,0.]); noise=np.zeros((2,3))
    ll,path=target.evaluate(param,noise,True)
    np.testing.assert_array_equal(path[0],[.8,0.,.4])
    changed=dict(public,range_m=public["range_m"].copy())
    changed["range_m"][0]=2.
    alternative=S0BatchTarget(changed,cfg,"RANGE")
    assert alternative.evaluate(param,noise)==ll
    assert alternative.table.logpdf(.8)!=target.table.logpdf(.8)
    dr=S0BatchTarget(public,cfg,"DR")
    ll_dr=dr.evaluate(param,noise)
    r=np.sqrt(np.sum(path[1:,:2]**2,axis=1)+.5**2)
    expected=norm.logpdf(public["range_m"][1:],loc=r,scale=.05).sum()
    assert ll-target.conditional(np.zeros(6))[-1]==pytest.approx(expected)
    assert dr.evaluate(param,noise)==ll_dr
    assert target.range_count==3
    with pytest.raises(ValueError,match="x0"):
        S0BatchTarget(dict(public,x0=np.zeros(6)),cfg,"RANGE")
    with pytest.raises(ValueError,match="seven public"):
        S0BatchTarget(dict(public,true_pose=object()),cfg,"RANGE")
    zero_cfg=dict(cfg,p0_std=[0.,0.,0.,*cfg["p0_std"][3:]])
    assert S0BatchTarget(public,zero_cfg,"RANGE").evaluate(param,noise)==ll


def test_dr_range_independence_and_deterministic_mcmc():
    public,cfg=inputs()
    settings=dict(chains=4,burn=10,retained=8,thin=1,pCN_beta=.2)
    first=batch_s0(public,cfg,"DR",14,settings)
    changed=dict(public,range_m=np.full(4,np.nan))
    second=batch_s0(changed,cfg,"DR",14,settings)
    np.testing.assert_array_equal(first["samples"],second["samples"])
    assert first["samples"].shape==(4,8,5)
    assert first["diagnostic_columns"]==["bg","sf","eps"]
    assert first["reference_status"]=="REFERENCE_NOT_VALIDATED"
    ran=batch_s0(public,cfg,"RANGE",14,settings)
    assert ran["subsequent_range_count"]==3
    assert ran["initial_range_consumed"]
    assert len(set(np.asarray(ran["initial_chain_states"])[:,1]))==4
    assert np.all((ran["samples"][:,:,1]>=-np.pi)&(ran["samples"][:,:,1]<np.pi))
