"""Mathematical unit tests only (not archived-RF performance certification)."""
import math
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ekf3 import (  # noqa: E402
    CHI2_1_99, CHI2_2_99, EKF3, sinc_with_derivative, wrap,
)

P0 = np.diag([0.1**2, 0.1**2, math.radians(5)**2])
ANCHOR = (4.0, 0.0, 2.65)
Z = 0.45
OFFSET = -0.5315983906250129


def s_model(x):
    """Locally affine RF polarization response with full x/y/yaw dependence."""
    H = np.array([0.16, -0.04, 0.8])
    return float(0.1 + H @ x), H.copy()


def ekf(x=(1.2, -0.3, 0.5), P=None):
    return EKF3(np.array(x), np.diag([0.6, 0.8, 0.2]) if P is None else P)


def test_initial_p0_and_mutable_copies():
    x = np.array([0.0, 0.0, 4*math.pi])
    p = P0.copy()
    f = EKF3(x, p)
    x[0] = 99
    p[0, 0] = 99
    assert np.allclose(f.x, [0, 0, 0])
    assert np.allclose(f.P, P0)
    assert f.x.shape == (3,) and f.P.shape == (3, 3)


def test_predict_straight_and_stationary_turn():
    f = ekf((0, 0, 0), np.eye(3) * 1e-3)
    r = f.predict(1.2, 0.0, 0.2)
    assert np.allclose(r.post_x, [1.2, 0, 0])
    assert r.F.shape == (3, 3) and r.G.shape == (3, 2)
    turn = f.predict(0, math.pi / 2, .2)
    assert np.allclose(turn.post_x[:2], [1.2, 0], atol=1e-13)
    assert turn.post_x[2] == pytest.approx(math.pi/2)


def test_arc_exact_geometry():
    f = ekf((0, 0, 0), P0)
    f.predict(2, math.pi / 2, .2)
    exp = 2 * math.sin(math.pi / 4) / (math.pi / 4) * math.sqrt(.5)
    assert np.allclose(f.x[:2], [exp, exp], atol=1e-12)


def test_angular_wrap_on_prediction():
    f = ekf((0, 0, math.pi-0.01), P0)
    f.predict(0, .02, .2)
    assert f.x[2] == pytest.approx(-math.pi+.01)
    assert wrap(-math.pi) == -math.pi


def test_sinc_derivative_near_zero():
    assert sinc_with_derivative(0) == (1.0, 0.0)
    for h in [1e-7, 1e-5, 1e-3, .8]:
        s, sp = sinc_with_derivative(h)
        eps = min(1e-6, abs(h)*0.25)
        true = (math.sin(h+eps)/(h+eps)-math.sin(h-eps)/(h-eps))/(2*eps)
        assert sp == pytest.approx(true, abs=1e-7)
        assert s == pytest.approx(math.sin(h)/h, abs=2e-14)


def test_prediction_F_and_G_finite_difference():
    x = np.array([1.0, -0.5, .71]); inp = [0.29, -0.24]
    f = EKF3(x, P0)
    rec = f.predict(*inp, .2, Q_input=np.zeros((2,2)))
    eps=1e-6
    for i in range(3):
        shift=np.zeros(3);shift[i]=eps
        plus=EKF3(x+shift,P0).predict(*inp,.2,Q_input=np.zeros((2,2))).post_x
        minus=EKF3(x-shift,P0).predict(*inp,.2,Q_input=np.zeros((2,2))).post_x
        approx=(plus-minus)/(2*eps)
        assert np.allclose(approx,rec.F[:,i],atol=1e-9)
    for i in range(2):
        inp_p=inp.copy();inp_m=inp.copy();inp_p[i]+=eps;inp_m[i]-=eps
        plus=EKF3(x,P0).predict(*inp_p,.2,Q_input=np.zeros((2,2))).post_x
        minus=EKF3(x,P0).predict(*inp_m,.2,Q_input=np.zeros((2,2))).post_x
        approx=(plus-minus)/(2*eps)
        assert np.allclose(approx,rec.G[:,i],atol=1e-9)


def test_prediction_Q_propagation_and_custom_offdiag():
    f=ekf(P=np.diag([.04,.03,.02])); before=f.P.copy()
    qu=np.array([[0.008,0.002],[0.002,0.003]])
    qm=np.diag([0.0001,0.0002,0.0003])
    step=f.predict(.4,-.2,.2,Q_input=qu,Q_model=qm)
    assert np.allclose(f.P,step.F@before@step.F.T+step.G@qu@step.G.T+qm)
    assert min(np.linalg.eigvalsh(f.P))>=0


def test_p0_sensor_v2_gyro_noise_law():
    f=ekf()
    r=f.predict(.25,.01,.2)
    assert r.Q_input[0,0] == pytest.approx(2e-5*.25)
    assert r.Q_input[1,1] == pytest.approx(math.radians(.015)**2*.2)
    assert r.Q_input[0,1] == 0


def test_prediction_bad_data_rejected_without_mutation():
    f=ekf(); x=f.x.copy();p=f.P.copy()
    for call in [lambda:f.predict(.1,0,0),lambda:f.predict(float('nan'),0,.2),
                 lambda:f.predict(.1,0,.2,Q_input=np.array([[1.,2.],[2.,1.]]))]:
        with pytest.raises(ValueError): call()
        assert np.array_equal(f.x,x) and np.array_equal(f.P,p)


def test_direct_s_full_H_and_Joseph():
    f=ekf()
    xp=f.x.copy();p=f.P.copy();measured=s_model(xp)[0]+.03
    rec=f.update_heading(measured,.09**2,s_model=s_model)
    H=rec.H;R=rec.R; K=p@H.T@np.linalg.inv(H@p@H.T+R)
    assert rec.status=='applied'
    assert np.allclose(H,[[.16,-.04,.8]])
    assert np.allclose(rec.K,K)
    assert np.allclose(f.x,xp+K[:,0]*.03)
    M=np.eye(3)-K@H
    assert np.allclose(f.P,M@p@M.T+K@R@K.T)
    assert np.linalg.eigvalsh(f.P).min()>=0


def test_absolute_heading_requires_explicit_validation_and_wrap():
    f=ekf((0,0,math.pi-.02))
    with pytest.raises(ValueError):
        f.update_heading(-math.pi+.04, math.radians(2)**2,kind='absolute_heading')
    r=f.update_heading(-math.pi+.04,math.radians(2)**2,kind='absolute_heading',validated_absolute=True)
    assert r.innovation[0]==pytest.approx(.06)
    assert np.allclose(r.H,[[0,0,1]])


def test_range_3D_slant_geometry_and_heading_cross_gain():
    cov=np.array([[.2,.03,.08],[.03,.4,-.05],[.08,-.05,.2]])
    f=ekf(P=cov)
    before=f.x.copy();d=math.sqrt((before[0]-4)**2+before[1]**2+(Z-2.65)**2)
    z=d+OFFSET+.05
    r=f.update_range(z,.0068578637,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    assert np.allclose(r.H,[[(before[0]-4)/d,before[1]/d,0]])
    assert abs(r.K[2,0])>0
    assert r.innovation[0]==pytest.approx(.05)


def test_gate_rejection_preserves_state_covariance():
    f=ekf();a=f.x.copy();p=f.P.copy()
    rec=f.update_range(400,.0068578637,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    assert rec.status=='rejected_NIS' and rec.NIS>CHI2_1_99
    assert np.array_equal(f.x,a) and np.array_equal(f.P,p)
    assert rec.S.shape==(1,1)


def test_joint_positive_covariance_offdiagonal_and_analytic_gain():
    f=ekf();a=f.x.copy();p=f.P.copy()
    s=s_model(a)[0]+.035
    d=np.linalg.norm([a[0]-4,a[1],Z-2.65])+OFFSET+.07
    out=f.update_joint(s,d,.01,.007,.004,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    assert out.status=='applied'; assert out.H.shape==(2,3)
    assert out.R.shape==(2,2) and out.R[0,1]==pytest.approx(.004)
    K=p@out.H.T@np.linalg.inv(out.H@p@out.H.T+out.R)
    assert np.allclose(out.K,K)
    assert out.NIS==pytest.approx(out.innovation@np.linalg.solve(out.S,out.innovation))
    assert np.allclose(out.post_x,a+K@out.innovation)
    assert np.linalg.eigvalsh(out.post_P).min()>-1e-12


def test_joint_rejects_invalid_R_correlation():
    f=ekf();a=f.x.copy();p=f.P.copy()
    with pytest.raises(ValueError):
        f.update_joint(.3,2,.01,.007,.05,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    assert np.array_equal(f.x,a) and np.array_equal(f.P,p)


def test_joint_missing_packet_fallback_is_single_observation():
    f=ekf();g=f.clone();h=f.clone()
    z=s_model(f.x)[0]+.025
    r=f.update_joint(z,None,.0081,.0068578637,0,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    expected=g.update_heading(z,.0081,s_model=s_model)
    assert r.name=='heading' and np.allclose(f.x,g.x) and np.allclose(f.P,g.P)
    f=ekf();g=f.clone()
    r=f.update_joint(None,3,.0081,.0068578637,0,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    g.update_range(3,.0068578637,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    assert r.name=='range' and np.allclose(f.x,g.x) and np.allclose(f.P,g.P)
    r=h.update_joint(None,None,.0081,.0068578637,0,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    assert r.status=='skipped_missing' and np.array_equal(h.x,r.post_x)


def test_joint_rejected_no_op_without_fallback():
    f=ekf();xp=f.x.copy();pp=f.P.copy()
    r=f.update_joint(s_model(xp)[0],1e3,.0081,.0068578637,0,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    assert r.status=='rejected_NIS' and r.NIS>CHI2_2_99
    assert np.array_equal(f.x,xp) and np.array_equal(f.P,pp)


def test_correlated_joint_differs_from_diagonal_and_is_more_informative_than_s_only():
    f=ekf();a=f.clone();b=f.clone()
    x=f.x.copy();z_s=s_model(x)[0]+.01;z_r=np.linalg.norm([x[0]-4,x[1],Z-2.65])+OFFSET+.02
    c=f.update_joint(z_s,z_r,.01,.007,.006,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    d=a.update_joint(z_s,z_r,.01,.007,0,s_model=s_model,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    b.update_heading(z_s,.01,s_model=s_model)
    assert not np.allclose(c.K,d.K)
    assert np.trace(f.P)<=np.trace(b.P)+1e-10


def test_prediction_and_filter_copy_per_arm_independent():
    f=ekf();a=f.clone();b=f.clone();c=f.clone()
    a.predict(.2,.02,.2);a.update_heading(s_model(a.x)[0]+.03,.0081,s_model=s_model)
    b.predict(.2,.02,.2);b.update_range(3,.0068578637,anchor_xyz_m=ANCHOR,tag_height_m=Z)
    c.predict(.2,.02,.2)
    assert not np.array_equal(a.x,b.x)
    assert not np.array_equal(a.P,c.P)
    assert np.array_equal(f.x,ekf().x)


def test_missing_scalar_does_not_change_filter():
    f=ekf();x=f.x.copy();p=f.P.copy()
    assert f.update_heading(float('nan'),.0081,s_model=s_model).status=='skipped_missing'
    assert f.update_range(None,.007,anchor_xyz_m=ANCHOR,tag_height_m=Z).status=='skipped_missing'
    assert np.array_equal(f.x,x) and np.array_equal(f.P,p)


def test_no_silent_bias_or_6_state_extension():
    f=ekf()
    assert f.x.size == 3
    assert 'bias' not in vars(f)
    with pytest.raises(ValueError): EKF3(np.zeros(6),np.eye(6))


def test_observer_raises_on_invalid_nan_h():
    f=ekf()
    with pytest.raises(ValueError):
        f.update_heading(0,.0081,s_model=lambda x:(float('nan'),np.array([1,0,0])))


def test_psd_validation_disallows_indefinite_prior():
    with pytest.raises(ValueError): EKF3([0,0,0],np.diag([.1,.1,-1]))


def test_expected_tiny_update_does_not_require_oracle_truth():
    f=EKF3([0,0,0],P0)
    vals=[]
    for i in range(15):
        f.predict(.02,.01,.2)
        # A precomputed model-consistent heading-like polarization measurement
        z=s_model(f.x)[0]
        out=f.update_heading(z,.01,s_model=s_model)
        vals.append(out.NIS)
    assert max(vals)==pytest.approx(0.0,abs=1e-15)
    assert np.isfinite(f.x).all() and np.isfinite(f.P).all()
