"""Independent normalization and fixed contract checks for loss-shape calibration."""
import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.stats import multivariate_t

sys.path.insert(0,str(Path(__file__).resolve().parent))
from calibrate_loss_family import fit_shapes,DFS,CONTRACT

@pytest.mark.parametrize('d',[1,2])
def test_student_training_nll_matches_scipy(d):
    z=np.random.default_rng(42).normal(size=(1000,d))
    r=fit_shapes(z)
    for item in r['student_candidates']:
        df=item['df'];scale=(df-2)/df*np.eye(d)
        expected=-np.mean(multivariate_t.logpdf(z,loc=np.zeros(d),shape=scale,df=df))
        assert abs(item['mean_nll_standardized']-expected)<1e-12
    assert r['student_df']==min(r['student_candidates'],key=lambda x:x['mean_nll_standardized'])['df']
    assert abs(r['cauchy_score_equation'])<1e-10

def test_cauchy_training_scale_equivariance():
    z=np.random.default_rng(53).normal(size=(1000,2))
    assert fit_shapes(4*z)['cauchy_scale']==pytest.approx(4*fit_shapes(z)['cauchy_scale'],rel=1e-10)

@pytest.mark.parametrize('z',[np.zeros((100,2)),np.ones((99,2)),np.full((100,2),np.nan)])
def test_invalid_or_degenerate_training_fails(z):
    with pytest.raises(ValueError):fit_shapes(z)

def test_training_contract_unchanged():
    assert DFS==(3.,4.,6.,10.,20.,50.,100.)
    assert CONTRACT['spatial_buffer_m']==.25 and CONTRACT['mean']=='ZERO_NO_FIT'
    assert CONTRACT['evaluation_labels_used'] is False

def test_four_models_keep_baseline_kernels():
    import run_loss_family as r
    import rf_components as f
    assert r.base_make_filter is f.make_filter and r.base_update_filter is f.update_filter
    assert r.MODELS==('M0','RF_HUBER_ONLY','RF_CAUCHY','RF_STUDENT_T')
    assert r.extension_contract('gyro_bias',2)['gyro_bias_magnitude_dps']==.2
    assert r.make_filter('RF_CAUCHY',np.zeros(3),r.extension_contract('noise_pair',1)).map_solver is r.scalar_map
