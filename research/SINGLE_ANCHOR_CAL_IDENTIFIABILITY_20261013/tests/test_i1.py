import sys,json
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from i1_model import forward,build_whitener,whiten,effective
from i1_structural_observability import datasets,gauge_tests,nonlinear_families,HERE
from qclean_uwb.drivesim.filter_v2 import transition,odometry_model
SPEC=json.loads((HERE/'I1_SPEC.json').read_text())

@pytest.mark.parametrize('cal',[[0,0,0],[.0008,.004,.003]])
def test_forward_and_jacobian(cal):
    d=datasets(SPEC)['CIRCULAR_TANGENT'];theta=d['theta'].copy();theta[3:]=cal;anchor=np.array(SPEC['anchors']['A'])
    values,pose,J=forward(theta,d,anchor,True,True)
    x=theta.copy()
    for k in range(1,len(pose)):
        x,_,_=transition(x,d['d'][k],d['g'][k],d['dt'][k],.287)
        np.testing.assert_allclose(x[:3],pose[k],atol=1e-12)
    for j,h in enumerate([1e-5,1e-5,1e-6,1e-7,1e-6,1e-6]):
        a=theta.copy();b=theta.copy();a[j]+=h;b[j]-=h
        fd=(forward(a,d,anchor,True)[0]-forward(b,d,anchor,True)[0])/(2*h)
        np.testing.assert_allclose(J[:,:,j],fd,atol=SPEC['jacobian_test_atol'],rtol=1e-5)

def test_exact_gauge_and_calibration_family():
    data=datasets(SPEC)
    for d in data.values():assert gauge_tests(d,np.array(SPEC['anchors']['A']),SPEC)['pass_rotation']
    for p in nonlinear_families(data,SPEC)['pairs']:
        assert p['DR_observation_difference']<1e-12
        assert p['mirror_range_difference']<1e-12
        assert p['range_difference_from_zero_cal']>1e-9

def test_nuisance_projection():
    J=np.zeros((3,6));J[:,3]=[1,0,1];J[:,5]=[0,1,1];J[:,4]=J[:,3]
    assert effective(J,1e-10)['rank']==1
    assert np.linalg.norm(np.array(effective(J,1e-10)['matrix'])[0])<1e-12

def test_whitener_against_dense_generative_covariance():
    d=datasets(SPEC)['CIRCULAR_TANGENT'];d={k:v[:6].copy() if k!='theta' else v.copy() for k,v in d.items()}
    anchor=np.array(SPEC['anchors']['A']);theta=d['theta'];ops,values,J=build_whitener(theta,d,anchor,SPEC,True)
    n=len(d['t']);dim=4*n;E=np.zeros((6,dim));raw=np.zeros((n,2,dim));_,pose=forward(theta,d,anchor,True)
    for k in range(n):
        if k:
            xp=np.r_[pose[k-1],theta[3:]];_,F,G=transition(xp,d['d'][k],d['g'][k],d['dt'][k],.287)
            _,H,B=odometry_model(xp,d['d'][k],d['g'][k],d['dt'][k],.287)
            Q=np.diag([SPEC['k_s']*abs(d['d'][k]),SPEC['gyro_N']**2*d['dt'][k],SPEC['k_theta']*abs(d['o'][k])+SPEC['k_stheta']*abs(d['d'][k])])
            E=F@E;E[:,4*k:4*k+3]-=G@np.sqrt(Q)
            raw[k,0]=H@E;raw[k,0,4*k:4*k+3]+=B@np.sqrt(Q)
        H=np.zeros(6);H[:2]=(pose[k,:2]-anchor[:2])/values[k,1]
        raw[k,1]=H@E;raw[k,1,4*k+3]+=SPEC['range_sigma_m']
    W=whiten(raw,ops)
    np.testing.assert_allclose(W@W.T,np.eye(len(ops)),atol=1e-10)
