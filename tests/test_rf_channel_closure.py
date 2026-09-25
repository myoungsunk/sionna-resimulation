import numpy as np
import pytest
from rt_cp_uwb_py.rf_channel_closure import slab_reflection_check,contribution_cir

@pytest.mark.parametrize('epsilon',[1,2.5,4-.2j,12-2j])
@pytest.mark.parametrize('sine',[0,.5,.95])
def test_slab_matrix_energy(epsilon,sine):
    for v in slab_reflection_check(epsilon,6.5e9,.0125,sine).values():
        assert v['absolute_error']<1e-12
        assert v['outgoing_power']<=1+1e-12
        if complex(epsilon).imag==0:assert abs(v['outgoing_power']-1)<1e-12
        if epsilon==1:assert abs(v['first_internal_return'])<1e-14

def test_cir_direct_sum_and_delay():
    n=257;m=4*n;f=6.2504e9+1.95e6*np.arange(n)
    h=np.exp(-2j*np.pi*np.arange(n)*23/m)[:,None,None]*(1+2j)
    cir,t=contribution_cir(h,f)
    oracle=n/m*(np.exp(2j*np.pi*np.outer(np.arange(m),np.arange(n))/m)@(np.hanning(n)*h[:,0,0]))
    np.testing.assert_allclose(cir[:,0,0],oracle,rtol=1e-11,atol=2e-12)
    assert np.argmax(abs(cir[:,0,0]))==23
    assert t[1]==1/(m*1.95e6)

@pytest.mark.parametrize('f',[[2,1],[1,1],[1,np.nan]])
def test_cir_rejects_bad_frequency(f):
    with pytest.raises(ValueError):contribution_cir(np.ones((2,1,1)),f)


def test_small_finite_mirror_recovers_local_derivative_without_relaxing_gate():
    from rt_cp_uwb_py.rf_volume_events import VolumeScene,IdealTriangle
    from rt_cp_uwb_py.rf_volume_producer import connect_branch
    from rt_cp_uwb_py.rf_volume_channel import ray_tube_spreading
    from rt_cp_uwb_py.rf_channel_closure import planar_reflection_spreading
    tri=np.array([[-1e-5,-1,0],[1e-5,-1,0],[0,1,0]])
    scene=VolumeScene([],ideal_surfaces=[IdealTriangle(tri,'PEC','finite')]);eps=lambda m,f:1
    path=connect_branch(scene,[-.5,0,1],[.5,0,1],6.5e9,eps,'R',[.5,0,-1])
    with pytest.raises(ValueError):ray_tube_spreading(scene,path,6.5e9,eps)
    result=planar_reflection_spreading(scene,path,6.5e9,eps)
    assert result['rejected_stencils']
    assert result['image_relative_error']<1e-5
    assert result['amplitude_per_m']==pytest.approx(1/np.sqrt(5),rel=1e-5)
