"""User-run deterministic UNIT tests only; no frozen RF experiment is executed."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from d6_d9_common import (DiagnosticFilter, B_OLD, RR, RS, arc,
                          eval_covariance, range_h, ut_propagate)
from ekf3 import EKF3
from d6_nonlinearity_mc import commands
from d7_cir_multipath_audit import NUMERIC_FEATURES, ONLINE_KEYS, one_feature
from d8_polarization_quality import (QUALITY_FEATURES, RANGE_LABELS, fit_ridge,
                                      online_vector, predict_variance,
                                      split_exclude_overlap)
from d9_quality_aware_fusion import covariance_for, METHODS


def test_straight_banana_sign_and_variance_deterministic():
    # A symmetric yaw distribution biases x backwards by 2nd order.
    ang = math.radians(20)
    L=10.
    assert L*(math.cos(ang)-1)<0
    assert (L*(math.cos(ang)-1))==pytest.approx(-L*ang**2/2,rel=.011)
    assert len(commands('outback',5,4))==9


def test_arc_at_zero_turn_and_4state_ut_covariance():
    old=np.array([1.,2.,.1])
    got=arc(old,3.,0.)
    assert got[:2]==pytest.approx(old[:2]+3*np.array([math.cos(.1),math.sin(.1)]))
    x=np.r_[old,0.]
    P=np.diag([.01,.01,.05,.001])
    y,C=ut_propagate(x,P,2.,.02,.2)
    assert y.shape==(4,) and C.shape==(4,4)
    assert np.linalg.eigvalsh(C).min()>0


def test_bias4_update_does_not_consume_oracle():
    x=np.array([0.2,0.0,0.1])
    q=DiagnosticFilter(x,bias_state=True,bias_std_dps=.1)
    def s_model(z):
        return float(.25+.1*z[0]+.5*z[2]), np.array([.1,0.,.5])
    q.predict(.1,.01,.2)
    status,nis=q.update('C',.29,4.,s_model,(4.,0.,2.65),.45)
    assert status in ('applied','rejected_NIS')
    assert math.isfinite(nis)
    assert q.Ppose.shape==(3,3)
    e=np.array([.1,.1,.01])
    assert np.isfinite(eval_covariance(e,q.Ppose)[0])


def test_known_port_power_ratio_not_new_info():
    p1,p2=2.,1.
    s=(p1-p2)/(p1+p2)
    assert (1+s)/(1-s)==pytest.approx(p1/p2)
    assert 's_fp' in NUMERIC_FEATURES
    assert not any('truth' in name or 'oracle' in name or 'error' in name
                   for name in ONLINE_KEYS)


def test_synthetic_cir_features_observer_parity():
    # Port polarimetric and delay features, with no RF scene or truth.
    cir=np.zeros((64,2),complex)
    cir[5,0]=3.+2j
    cir[5,1]=1.+.5j
    cir[20,0]=.2-.1j
    cir[20,1]=1.+.2j
    det={'index':np.array([5]),'peak_idx':np.array([5])}
    o=one_feature(cir,det,0,None,.15,guard=4)
    p=abs(cir[5])**2
    assert o['s_fp']==pytest.approx((p[0]-p[1])/(p[0]+p[1]))
    assert 0.<o['late_energy_fraction']<1.
    assert o['phase_valid']==1
    assert math.isfinite(o['first_late_s_difference'])


def test_quality_model_never_accepts_label_features():
    row={'s_fp':.3,'error_s':2.,'true_heading_rad':.5}
    with pytest.raises(RuntimeError):
        online_vector(row,('error_s',))
    assert set(QUALITY_FEATURES['Q3_CIR_POL']) <= set(NUMERIC_FEATURES)
    assert 'phase_fp_rad' not in QUALITY_FEATURES['Q3_CIR_POL']
    assert 'phase_fp_rad' in QUALITY_FEATURES['Q4_COMPLEX_PHASE']


def test_route_holdout_xy_neighbor_bins_removed():
    t=[{'true_x_m':'1.00002','true_y_m':'0','route':'R2'},
       {'true_x_m':'1.5','true_y_m':'0','route':'R2'}]
    h=[{'true_x_m':'0.99998','true_y_m':'0','route':'R4'}]
    kept,drop=split_exclude_overlap(t,h,1e-4)
    assert drop==1 and len(kept)==1
    assert kept[0]['true_x_m']=='1.5'


def test_ridge_predictor_uses_train_only_and_clips():
    train = [{'s_fp':str(x/50.), 'error_s':str(.1+x/200.),
              'error_range_B_OLD_m':str(.10+x/100.),
              'error_range_E1_FULL_LORO_m':str(-.1+x/150.)}
             for x in range(100)]
    p = fit_ridge(train,'s','Q1_S_ONLY',10.)
    result = predict_variance({'s_fp':'.3'},p)
    assert 1e-4 <= result <= 4.
    p_range=fit_ridge(train,'r','Q1_S_ONLY',10.,range_model='E1_FULL_LORO')
    assert p_range['target_label']=='error_range_E1_FULL_LORO_m'
    assert p_range['range_model']=='E1_FULL_LORO'
    assert RANGE_LABELS['E1_FULL_LORO']==p_range['target_label']
    assert METHODS['F0_ORIGINAL']==(False,False,False)


def test_3state_diagnostic_matches_independent_original_EKF3_all_arms():
    x=np.array([1.,.2,0.1])
    P=np.diag([.01,.01,math.radians(5.)**2])
    def obs(y):
        return float(.25+.02*y[0]+.5*y[2]),np.array([.02,0.,.5])
    anchor=(4.,0.,2.65)
    for arm in ('D0','A','B','C'):
        baseline=EKF3(x,P)
        diagnostic=DiagnosticFilter(x)
        for ds,gyro in [(.12,.003),(.04,-.002),(.21,.008)]:
            baseline.predict(ds,gyro,.2)
            diagnostic.predict(ds,gyro,.2)
            s=float(obs(baseline.x)[0]+.01)
            physical_r=float(range_h(baseline.x,anchor,.45)[0]+.02)
            if arm=='D0':
                expected='DR_only';nis=None
            elif arm=='A':
                step=baseline.update_heading(s,RS,s_model=obs)
                expected,nis=step.status,step.NIS
            elif arm=='B':
                step=baseline.update_range(physical_r+B_OLD,RR,
                        anchor_xyz_m=anchor,tag_height_m=.45,range_offset_m=B_OLD)
                expected,nis=step.status,step.NIS
            else:
                step=baseline.update_joint(s,physical_r+B_OLD,RS,RR,0.,
                        s_model=obs,anchor_xyz_m=anchor,tag_height_m=.45,
                        range_offset_m=B_OLD)
                expected,nis=step.status,step.NIS
            status,new_nis=diagnostic.update(arm,s,physical_r,obs,anchor,.45)
            assert status==expected
            assert new_nis==nis
            assert np.array_equal(baseline.x,diagnostic.f.x)
            assert np.array_equal(baseline.P,diagnostic.f.P)
