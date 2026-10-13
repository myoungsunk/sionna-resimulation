import sys
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from observability_checks import sensitivity,summarize,transition_jacobian,DT
from d6_d9_common import arc


def heading(p):return p[2],np.array([0.,0.,1.])


def test_d0_prior_does_not_establish_measurement_observability():
    O,n=sensitivity('straight','D0',False,heading,[4,0,2.65],.45)
    r=summarize(O,n,False)
    assert r['measurement_only_rank']==0
    assert r['prior_augmented_rank']==4
    assert r['gaussian_posterior_prior_only']


def test_heading_offset_gauge_is_distinguished_from_fixed_pose():
    O,n=sensitivity('straight','A',True,heading,[4,0,2.65],.45)
    assert summarize(O,n,False)['measurement_only_rank']==2
    assert summarize(O,n,True)['measurement_only_rank']==2
    assert summarize(O,n,False)['n_states']==5
    assert summarize(O,n,True)['n_states']==2


def test_bias_transition_jacobian_matches_finite_difference():
    p=np.array([.2,.3,.4]);d=.04;a=.02
    F=transition_jacobian(p,d,a,DT,4)
    eps=1e-6
    derivative=(arc(p,d,a-DT*eps)-arc(p,d,a+DT*eps))/(2*eps)
    np.testing.assert_allclose(F[:3,3],derivative,rtol=1e-7,atol=1e-10)


def test_posterior_equals_gaussian_batch_inverse():
    O,n=sensitivity('return','C',True,heading,[4,0,2.65],.45)
    r=summarize(O,n,False)
    from observability_checks import SCALES
    A=O*np.array([SCALES[k] for k in n])
    np.testing.assert_allclose(np.asarray(r['posterior_covariance_normalized'])@(np.eye(len(n))+A.T@A),np.eye(len(n)),atol=1e-10)
