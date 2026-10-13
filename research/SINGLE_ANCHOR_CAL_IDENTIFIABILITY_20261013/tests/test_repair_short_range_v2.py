import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from repair_short_range_v2 import *
from repair_short_range_run import cases

@pytest.fixture
def model():
    _,p,c,_=next(cases());return IndependentOneStep(p,c)

def test_reflection_full_invariance_and_involution(model):
    t=S0BatchTarget(model.p,model.c,'RANGE');x=draw_proposal(t,np.random.default_rng(81),64)
    y=reflected(model,x,t);z=reflected(model,y,t)
    assert np.max(abs(model.full(x)-model.full(y)))<1e-10
    assert np.max(abs((z[:,1]-x[:,1]+np.pi)%(2*np.pi)-np.pi))<1e-12
    assert np.allclose(z[:,[0,2,3,4,5,6]],x[:,[0,2,3,4,5,6]],rtol=0,atol=0)
    assert np.max(abs(model.likelihood(x,True)[2]-model.likelihood(y,True)[2]))<1e-12
    assert np.all(reflection_branch(model,x)!=reflection_branch(model,y))

def test_reflection_jacobian_eta(model):
    x=draw_proposal(S0BatchTarget(model.p,model.c,'RANGE'),np.random.default_rng(91),1)[0]
    for eta in [False,True]:
        q=x.copy()
        if eta:q[0]=np.log(q[0])
        def fn(z):
            z=z.copy()
            if eta:z[0]=np.exp(z[0])
            v=reflected(model,z[None])[0]
            if eta:v[0]=np.log(v[0])
            return v
        eps=1e-6;J=np.column_stack([(fn(q+eps*np.eye(7)[j])-fn(q-eps*np.eye(7)[j]))/(2*eps) for j in range(7)])
        assert abs(abs(np.linalg.det(J))-1)<1e-6

def test_transition_guard(model):
    model.p=dict(model.p);model.p['range_m']=np.ones(3)
    with pytest.raises(ValueError):reflected(model,np.zeros((1,7)))

def test_dynamic_replicate_counts_preserve_thresholds():
    base=dict(mean=[0.]*8,sd=[1.]*8,quantiles=[[0.]*3]*8,sector_mass=[1/12]*12)
    chk=compare_v2([base]*16,[base]*16)
    assert chk['moment_pass'] and chk['sector_pass'] and chk['replicate_counts']==[16,16]
    changed=dict(base,quantiles=[[.101]*3]*8)
    assert not compare_v2([base]*16,[changed]*16)['moment_pass']
    a=np.zeros((15,795));b=np.zeros((16,795));c=simultaneous(a,b)
    assert c['df']==14 and c['passes'] and 5<c['critical_value']<6

def test_basin_partition():
    x=np.zeros((100,7));x[:,1]=np.linspace(-np.pi,np.pi,100,endpoint=False);w=np.full(100,.01)
    assert np.isclose(basin_mass(x,w,[-1.,1.]).sum(),1)
    assert len(basin_mass(x,w,[]))==1

def test_short_mh_mirror_kernel(model):
    t=S0BatchTarget(model.p,model.c,'RANGE');x,diag=joint_mh_v2(t,model,999,burn=10,retained=20,nchains=2)
    assert x.shape==(2,20,7) and diag['max_reflection_logdensity_error']<1e-10
    assert np.all(np.isfinite(x))
