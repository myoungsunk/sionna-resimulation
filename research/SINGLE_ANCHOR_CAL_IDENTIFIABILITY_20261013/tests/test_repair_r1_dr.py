import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm
sys.path.insert(0,str(Path(__file__).parents[1]))
from repair_r1_dr import DRReference, run_case, compare_cases
from i2_s0_batch import S0BatchTarget


def inputs():
    public=dict(t_s=np.arange(4)*.2,dt_s=np.array([0.,.2,.2,.2]),
                ds_odom=np.array([0.,.04,.035,.05]),
                dtheta_gyro=np.array([0.,.01,-.02,.03]),
                dtheta_odom=np.array([0.,.012,-.015,.025]),
                range_m=np.array([1.,1.04,1.08,1.1]),range_mask=np.ones(4,bool))
    cfg=dict(p0_std=[0.,0.,0.,.002,.01,.006],wheel_base=.287,
             anchor_xyz=[0.,0.,1.],robot_z=.5,k_s=2e-5,k_theta=1e-4,
             k_stheta=1e-5,gyro_N_rad_sqrt_s=.0003,range_sigma=.05)
    return public,cfg


def test_direct_target_matches_existing_and_ignores_latent_noise():
    public,cfg=inputs(); ref=DRReference(public,cfg); existing=S0BatchTarget(public,cfg,"DR")
    for z in (np.zeros(3),np.array([1.,-.4,.8]),np.array([-2.,.3,-.2])):
        param=np.r_[0.,0.,z]
        expected=existing.evaluate(param,np.ones((2,3)))+norm.logpdf(z).sum()
        assert ref.direct_logdensity(z)==pytest.approx(expected,abs=1e-11)
        assert existing.evaluate(param,np.zeros((2,3)))==pytest.approx(existing.evaluate(param,np.ones((2,3))),abs=1e-11)


def test_analytic_bias_integral_and_conditional_moments():
    public,cfg=inputs(); ref=DRReference(public,cfg)
    for sf,eps in ((0.,0.),(.7,-.4),(-1.1,1.5)):
        ll,mu,var=ref.integrated(sf,eps)
        # Full direct density includes the two remaining Gaussian prior densities.
        shift=ref.direct_logdensity([mu,sf,eps])
        kernel=lambda bg:np.exp(ref.direct_logdensity([bg,sf,eps])-shift)
        mass=quad(kernel,-np.inf,np.inf,epsabs=1e-10)[0]
        expected=ll+norm.logpdf(sf)+norm.logpdf(eps)
        assert np.log(mass)+shift==pytest.approx(expected,abs=1e-10)
        mean=quad(lambda bg:bg*kernel(bg),-np.inf,np.inf,epsabs=1e-10)[0]/mass
        variance=quad(lambda bg:(bg-mean)**2*kernel(bg),-np.inf,np.inf,epsabs=1e-10)[0]/mass
        assert mu==pytest.approx(mean,abs=1e-10)
        assert var==pytest.approx(variance,abs=1e-10)


def test_quadrature_refinement_and_covariance():
    public,cfg=inputs()
    a=run_case(public,cfg,48,8); b=run_case(public,cfg,96,8)
    c=compare_cases(a,b)
    assert c["normalization_relative_difference"]<1e-6
    assert max(c["quantile_difference_sd"])<.01
    assert c["covariance_relative_frobenius_difference"]<1e-6
    assert np.linalg.eigvalsh(b["covariance"]).min()>0
    assert 0<=b["posterior_omitted_tail_upper_bound"]<=1
    # Bounds10 tail must not round to zero through subtraction from one.
    d=run_case(public,cfg,48,10)
    assert d["box_omitted_prior_mass"]>0
    assert b["reference_status"]=="REFERENCE_NOT_VALIDATED"


def test_public_input_protection_and_parameter_support():
    public,cfg=inputs()
    with pytest.raises(ValueError,match="seven"):
        DRReference(dict(public,true_calibration=[1,2,3]),cfg)
    ref=DRReference(public,cfg)
    assert ref.direct_logdensity([0.,-101.,0.])==-np.inf
    assert ref.direct_logdensity([0.,0.,400.])==-np.inf
    with pytest.raises(ValueError,match="positive"):
        DRReference(public,dict(cfg,p0_std=[0.,0.,0.,0.,.01,.006]))


def test_no_false_tail_bound_when_odom_noise_floor_vanishes():
    public,cfg=inputs(); cfg=dict(cfg,k_theta=0.,k_stheta=0.)
    a=run_case(public,cfg,24,6)
    assert a["posterior_omitted_tail_upper_bound"] is None
