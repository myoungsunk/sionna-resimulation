"""User-run deterministic UNIT tests only; no frozen RF experiment is executed."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from d6_d9_common import DiagnosticFilter, arc, eval_covariance, range_h, ut_propagate
from d6_nonlinearity_mc import commands
from d7_cir_multipath_audit import NUMERIC_FEATURES, ONLINE_KEYS, one_feature
from d8_polarization_quality import (QUALITY_FEATURES, fit_ridge,
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
    train=[{'s_fp':str(x/50.),'error_s':str(.1+x/200.)}
           for x in range(100)]
    p=fit_ridge(train,'s','Q1_S_ONLY',10.)
    result=predict_variance({'s_fp':'.3'},p)
    assert 1e-4<=result<=4.
    params={'models':{'Q3_CIR_POL':{'s':{'feature_names':[],
      'intercept':math.log(.0081),'floor':1e-4,'cap':4.},
      'r':{'feature_names':[],'intercept':math.log(.0068578637),
           'floor':1e-5,'cap':9.}, 'rho_sr_train_centered':.3}}}
    R=covariance_for({},params,'F3_CIR_R',True)
    assert R[0]*R[1] - R[2]**2 >0
    assert METHODS['F0_ORIGINAL']==(False,False,False)


def test_3state_frozen_baseline_update_equivalent_to_clone():
    x=np.array([1.,.2,0.1])
    f=DiagnosticFilter(x)
    f2=DiagnosticFilter(x)
    def obs(y):
        return float(.25+.02*y[0]+.5*y[2]),np.array([.02,0.,.5])
    for fobj in (f,f2):
        fobj.predict(.12,.003,.2)
        fobj.update('C',.3,3.5,obs,(4.,0.,2.65),.45)
    assert np.array_equal(f.f.x,f2.f.x)
    assert np.array_equal(f.f.P,f2.f.P)
