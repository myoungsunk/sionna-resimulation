"""Fixed contract, frozen-kernel reuse and fail-closed parity checks."""
import copy
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import huber_gyro as h


@pytest.mark.parametrize('level,magnitude',[(0,.01),(1,.05),(2,.20)])
def test_fixed_gyro_contract(level,magnitude):
    c=h.extension_contract('gyro_bias',level)
    assert tuple(c['models'])==h.MODELS
    assert c['level']==level and c['gyro_bias_magnitude_dps']==magnitude
    assert c['huber_delta']==1.345 and c['parity_abs_tolerance']==1e-8
    assert c['bias_state'] is False and c['mean_correction'] is False
    assert c['covariance']=='FROZEN_R0' and c['parameter_retuning'] is False
    assert c['receiver']=='ORIGINAL_FP' and c['eval_start_s']==30
    assert c['cells_per_model']==252 and c['smoke_cells_per_model']==12
    assert c['seeds']==[0,1,2]


@pytest.mark.parametrize('condition,level',[('noise_pair',0),('noise_pair',2),('gyro_bias',3),('all',1)])
def test_unsupported_grid_rejected(condition,level):
    with pytest.raises(ValueError): h.extension_contract(condition,level)


def rows():
    base=dict(case='R2_aA_m0',channel='full',range_model='B_OLD',condition='noise_pair',level=1,seed=0,arm='D0',
        n=100,accepted_updates=0,rejected_updates=0,heading95=.95)
    base.update({field:.2 for field in h.PARITY})
    return [dict(base,model=m) for m in h.MODELS]


def references(data):
    return {m:{h.key(r):r for r in data if r['model']==m} for m in h.MODELS}


def test_reproduction_counts_and_finite_parity():
    data=rows(); refs=references(data)
    assert h.check_parity(data,refs,expected=1)['max_abs_difference']==0.
    altered=copy.deepcopy(data); altered[1]['heading_rmse_deg']+=1e-7
    with pytest.raises(RuntimeError,match='Parity failure'): h.check_parity(altered,refs)
    altered[1]['heading_rmse_deg']=float('nan')
    with pytest.raises(RuntimeError,match='Parity failure'): h.check_parity(altered,refs)
    altered=copy.deepcopy(data); altered[1]['accepted_updates']=1
    with pytest.raises(RuntimeError,match='count mismatch'): h.check_parity(altered,refs)


def test_missing_duplicate_and_incomplete_parity():
    data=rows(); refs=references(data)
    with pytest.raises(RuntimeError,match='Incomplete'): h.check_parity(data,refs,expected=252)
    with pytest.raises(RuntimeError,match='Duplicate'): h.check_parity(data+data,refs)
    del refs['M0'][h.key(data[0])]
    with pytest.raises(RuntimeError,match='Missing'): h.check_parity(data,refs)


def test_d0_metrics_invariance_is_fail_closed():
    data=rows(); assert h.check_d0(data)['cells']==1
    data[1]['mean_pose_NEES']+=1e-7
    with pytest.raises(RuntimeError,match='D0 neutral'): h.check_d0(data)


def test_independent_d5_requires_all_twelve_cells():
    data=rows()
    with pytest.raises(RuntimeError,match='Incomplete independent'): h.independent_d5_parity(data,[data[0]],1e-8)


def test_d0_predict_reuses_frozen_three_state_kernels():
    c=h.extension_contract('gyro_bias',1); x=np.array([.2,.1,.3])
    filters=[h.make_filter(m,x,c) for m in h.MODELS]
    def model(x):return x[2],np.array([0.,0.,1.])
    case=dict(anchor=[3.,2.,1.],robot_z_m=.5)
    for k in range(8):
        for name,f in zip(h.MODELS,filters):
            f.predict(.2,.002,.2)
            result=h.update_filter(name,f,'D0',.1,3.,model,case,np.zeros(2),np.diag([h.RS,h.RR]),1.345)
            assert result['status']=='DR_only'
            assert f.pose.shape==(3,) and f.Ppose.shape==(3,3)
        np.testing.assert_array_equal(filters[0].pose,filters[1].pose)
        np.testing.assert_array_equal(filters[0].Ppose,filters[1].Ppose)


def test_observation_kernels_are_exactly_frozen_imports():
    assert h.make_filter is h.rf.make_filter and h.update_filter is h.rf.update_filter
    assert h.extension_contract('noise_pair',1)['gyro_bias_magnitude_dps']==0.
