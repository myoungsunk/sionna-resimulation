import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.special import ndtr
from scipy.stats import norm
sys.path.insert(0, str(Path(__file__).parents[1]))
from repair_r1_cdf_v2 import AdaptiveCDF, run_case
from test_repair_r1_dr import inputs
from repair_r1_dr import run_case as tensor_case


class GaussianTarget:
    std = np.ones(3)*.01
    def integrated(self, sf, eps):
        return 0., .4*sf+.3*eps, .75


def test_adaptive_gaussian_masses_and_correlated_bias_cdf():
    engine=AdaptiveCDF(GaussianTarget(),8.,1e-8,1e-8,0.)
    mass,error=engine.mass()
    assert mass==pytest.approx(1.,abs=1e-9)
    # Marginal bias variance .75+.4²+.3²=1.
    for axis in range(3):
        value,err=engine.mass(axis,.7)
        assert value/mass==pytest.approx(ndtr(.7),abs=1e-8)
        assert err>=0
    assert error>=0


def test_narrow_conditional_bias_transition():
    class Narrow(GaussianTarget):
        def integrated(self,sf,eps):
            return 0.,eps,1e-12
    engine=AdaptiveCDF(Narrow(),8.,1e-8,1e-8,0.)
    mass,_=engine.mass()
    value,_=engine.mass(0,.713)
    assert value/mass==pytest.approx(ndtr(.713/np.sqrt(1+1e-12)),abs=1e-8)


def test_direct_cdf_matches_independently_refined_tensor_toy():
    public,cfg=inputs()
    old=tensor_case(public,cfg,96,8.)
    result=run_case(public,cfg,8.,1e-7,1e-7,old["log_normalization"])
    assert result["log_normalization"]==pytest.approx(old["log_normalization"],abs=1e-7)
    # Old interpolation is independently approximate; use a stricter integration
    # mass check and a modest quantile comparison for its finite-grid error.
    q=np.array(result["marginal_quantiles"])
    assert np.max(abs(q-np.array(old["marginal_quantiles"]))/np.array(old["sd"])[:,None])<.01
    assert result["evaluation_count"]>0
    assert result["reference_status"]=="REFERENCE_NOT_VALIDATED"


def test_invalid_numeric_settings_and_support():
    target=GaussianTarget()
    with pytest.raises(ValueError): AdaptiveCDF(target,0.,1e-8,1e-8,0.)
    with pytest.raises(ValueError): AdaptiveCDF(target,101.,1e-8,1e-8,0.)


def test_expired_deadline_raises_without_returning_reference():
    engine=AdaptiveCDF(GaussianTarget(),8.,1e-8,1e-8,0.)
    engine.deadline=0.
    with pytest.raises(TimeoutError,match="exceeded"):
        engine.mass()
