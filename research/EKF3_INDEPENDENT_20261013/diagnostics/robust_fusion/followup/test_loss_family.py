"""Analytic, fixed-prior, gate and failure-atomicity loss-family checks."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import loss_family as l

X=np.array([.2,.1,.03])
ANCHOR=[3.,2.,1.]
def model(x): return float(x[2]),np.array([0.,0.,1.])
def update(f,family='cauchy',parameter=2.,arm='A',zs=.1,zr=None):
    return f.update(arm,zs,zr,model,ANCHOR,.5,family=family,parameter=parameter)

@pytest.mark.parametrize('family,parameter',[('cauchy',1.7),('student_t',4.)])
@pytest.mark.parametrize('v',[np.array([.7]),np.array([.7,-1.2])])
def test_loss_derivatives(family,parameter,v):
    loss,w,g,h=l.block_loss(v,family,parameter)
    eps=1e-6
    eye=np.eye(len(v))
    ng=np.array([(l.block_loss(v+eps*e,family,parameter)[0]-
                 l.block_loss(v-eps*e,family,parameter)[0])/(2*eps) for e in eye])
    nh=np.column_stack([(l.block_loss(v+eps*e,family,parameter)[2]-
                        l.block_loss(v-eps*e,family,parameter)[2])/(2*eps) for e in eye])
    np.testing.assert_allclose(g,ng,atol=1e-9)
    np.testing.assert_allclose(h,nh,atol=1e-9)
    np.testing.assert_allclose(g,w*v,atol=0)

@pytest.mark.parametrize('df',[3.,4.,10.,100.])
def test_student_second_moment(df):
    r=np.array([[.04,.01],[.01,.3]])
    np.testing.assert_allclose(l.student_scale(r,df)*df/(df-2),r,atol=1e-16)

def test_student_weight_above_one_unclipped():
    assert l.block_loss(np.zeros(2),'student_t',4.)[1]==1.5
    f=l.LossFamilyPoseEKF(X)
    st=update(f,'student_t',4.,zs=X[2])
    assert st['robust_weight']==1.25
    assert st['R_effective'][0,0] < st['R0'][0,0]

@pytest.mark.parametrize('family,parameter',[('cauchy',1e6),('student_t',1e9)])
def test_large_parameter_gaussian_limit(family,parameter):
    f=l.LossFamilyPoseEKF(X); p=f.P.copy()
    r=l.RS; y=.1-X[2]
    h=np.array([[0.,0.,1.]])
    k=p@h.T/(h@p@h.T+r).item()
    st=update(f,family,parameter)
    np.testing.assert_allclose(f.pose,X+k[:,0]*y,atol=1e-9)
    a=np.eye(3)-k@h
    np.testing.assert_allclose(f.P,a@p@a.T+k*r@k.T,atol=1e-10)
    assert st['stationarity_norm'] <= 1e-7

@pytest.mark.parametrize('family,parameter',[('cauchy',1.),('student_t',4.)])
def test_joint_one_block_and_joseph(family,parameter):
    f=l.LossFamilyPoseEKF(X); p=f.P.copy()
    hr,_=l.range_h(X,ANCHOR,.5)
    st=update(f,family,parameter,'C',.1,hr+.1)
    assert st['observation_dimension']==2
    np.testing.assert_allclose(st['R_effective'],st['likelihood_scale']/st['robust_weight'])
    a=np.eye(3)-st['K']@st['H']
    np.testing.assert_allclose(f.P,a@p@a.T+st['K']@st['R_effective']@st['K'].T,atol=1e-15)
    assert np.linalg.eigvalsh(f.P)[0]>0
    assert st['optimization_claim']=='NONCONVEX_LOCAL_MINIMUM_ONLY'

@pytest.mark.parametrize('family,parameter',[('cauchy',.01),('student_t',3.)])
def test_gate_before_robust_and_no_mutation(family,parameter):
    f=l.LossFamilyPoseEKF(X); p=f.P.copy(); x=f.pose.copy()
    st=update(f,family,parameter,zs=100.)
    assert st['status']=='rejected_NIS'
    assert st['NIS']==float(np.array([100.-x[2]])@np.linalg.solve(np.array([[p[2,2]+l.RS]]),np.array([100.-x[2]])))
    assert st['robust_weight'] is None
    np.testing.assert_array_equal(f.pose,x)
    np.testing.assert_array_equal(f.P,p)

@pytest.mark.parametrize('zs,zr',[ (None,None),(float('nan'),float('inf')) ])
def test_missing(zs,zr):
    f=l.LossFamilyPoseEKF(X); x=f.pose.copy()
    assert update(f,arm='C',zs=zs,zr=zr)['status']=='missing'
    np.testing.assert_array_equal(f.pose,x)

def test_missing_joint_uses_scalar_student_dimension():
    f=l.LossFamilyPoseEKF(X)
    st=update(f,'student_t',4.,'C',X[2],None)
    assert st['observation_dimension']==1 and st['robust_weight']==1.25
    assert st['gate_threshold']==l.GATE_1D_99

def test_solver_failure_atomic(monkeypatch):
    f=l.LossFamilyPoseEKF(X); p=f.P.copy(); x=f.pose.copy()
    def fail(*args,**kwargs): raise RuntimeError('forced convergence failure')
    monkeypatch.setattr(l,'solve_map',fail)
    with pytest.raises(RuntimeError): update(f)
    np.testing.assert_array_equal(f.pose,x); np.testing.assert_array_equal(f.P,p)

@pytest.mark.parametrize('family,parameter',[('cauchy',0.),('student_t',2.),('student_t',float('inf'))])
def test_invalid_parameter(family,parameter):
    f=l.LossFamilyPoseEKF(X)
    with pytest.raises(ValueError): update(f,family,parameter)

def test_predict_original_parity_and_no_hidden_bias():
    f=l.LossFamilyPoseEKF(X); ref=l.DiagnosticFilter(X)
    f.predict(.1,.03,.2); ref.predict(.1,.03,.2)
    assert f.pose.shape==(3,) and f.P.shape==(3,3)
    np.testing.assert_array_equal(f.pose,ref.pose)
    np.testing.assert_array_equal(f.P,ref.Ppose)

def test_no_oracle_or_mean_interface():
    f=l.LossFamilyPoseEKF(X)
    with pytest.raises(TypeError):
        f.update('A',.1,None,model,ANCHOR,.5,family='cauchy',parameter=2.,truth=X)

def test_nonconvex_multistart_objective_and_stationarity():
    p=np.diag([.2,.3,.7]); h=np.array([[.1,.2,1.],[1.,0.,.3]])
    r=np.diag([.03,.08]); y=np.array([1.,.8])
    st=l.solve_map(y,h,p,r,'cauchy',.4)
    d=st['delta']; v=np.linalg.solve(np.linalg.cholesky(r),y-h@d)
    loss,w,g,_=l.block_loss(v,'cauchy',.4)
    objective=.5*d@np.linalg.solve(p,d)+loss
    assert objective<=l.block_loss(np.linalg.solve(np.linalg.cholesky(r),y),'cauchy',.4)[0]+1e-10
    assert st['stationarity_norm']<=1e-7
    assert st['attempted_starts']==2
    np.testing.assert_allclose(objective,st['objective'],atol=1e-14)

@pytest.mark.parametrize('family,parameter',[('cauchy',.1),('cauchy',2.),('student_t',3.),('student_t',100.)])
def test_stationary_stress_and_zero_sensitivity(family,parameter):
    rng=np.random.default_rng(445)
    p=np.diag([.1,.03,.02]); r=np.diag([.0081,.01])
    for index in range(12):
        h=rng.normal(size=(2,3)) if index else np.zeros((2,3))
        y=rng.normal(size=2)*.15
        scale=l.student_scale(r,parameter) if family=='student_t' else r
        st=l.solve_map(y,h,p,scale,family,parameter)
        assert st['stationarity_norm']<=1e-7
        if not index: np.testing.assert_array_equal(st['delta'],np.zeros(3))
