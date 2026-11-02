"""P3 typed adapter algebra, Jacobian and destructive negative controls.

These tests run in audited GitHub Actions, after source ZIP identity gate.
"""
from __future__ import annotations
from dataclasses import fields
import io
import math
import os
from pathlib import Path
import numpy as np
import pytest

from p3_frozen_inputs import (FrozenRFTrace, open_verified_archive,
                               EXPECTED_ARCHIVE_SHA)
from p3_rf_adapter4 import (FrozenLut,B_OLD,R0,PERMUTE_SR_TO_RS,
                             reorder_original_joint,GATE_JOINT)

CASE={"id":"R2_aA_m0","anchor":[4.,0.,2.65],
      "robot_z_m":.45,"mount_deg":0.}
CASE_MOUNT45={**CASE,"mount_deg":45.}

@pytest.fixture(scope="session",autouse=True)
def require_p3_audit():
    # The pre-existing P2 conftest.py is deliberately bypassed with
    # --noconftest. P3 has its OWN source-bound pre-execution audit.
    from p3_frozen_inputs import assert_audit
    assert_audit(os.environ["EKF4_P3_AUDIT_RECEIPT"])


@pytest.fixture(scope="module")
def lut():
    return FrozenLut()

def test_original_EKF3_s_range_to_EKF4_range_s_order_and_invariance():
    P=PERMUTE_SR_TO_RS
    z_old=np.array([.4,2.3])
    h_old=np.array([.3,2.0])
    H_old=np.array([[1.,.2,.3],[.4,.5,0.]])
    R_old=np.array([[.0081,.001],[.001,.0068578637]])
    prior=np.diag([.1,.2,.3])
    S_old=H_old@prior@H_old.T+R_old
    K_old=np.linalg.solve(S_old,H_old@prior).T
    nu_old=z_old-h_old
    a=reorder_original_joint(z_old,h_old,H_old,R_old,nu_old,S_old,K_old)
    assert np.array_equal(a["z"],z_old[::-1])
    assert np.array_equal(a["h"],h_old[::-1])
    assert np.array_equal(a["H"],H_old[::-1])
    np.testing.assert_array_equal(a["R"],P@R_old@P.T)
    np.testing.assert_array_equal(a["innovation"],P@nu_old)
    np.testing.assert_array_equal(a["S"],P@S_old@P.T)
    np.testing.assert_array_equal(a["K"],K_old@P.T)
    old_nis=nu_old@np.linalg.solve(S_old,nu_old)
    new_nis=a["innovation"]@np.linalg.solve(a["S"],a["innovation"])
    assert abs(old_nis-new_nis)<1e-12
    dx_old=K_old@nu_old
    dx_new=a["K"]@a["innovation"]
    np.testing.assert_allclose(dx_old,dx_new,rtol=0,atol=1e-14)

def test_exact_range_offset_only_once_and_bias_column_zero(lut):
    x=np.array([5.61,.52,.28,.0008])
    h,H=lut.model(x,CASE)
    d=math.sqrt((x[0]-4.)**2+x[1]**2+(.45-2.65)**2)
    assert h.shape==(2,) and H.shape==(2,4)
    assert abs(h[0]-(d+B_OLD))<1e-12
    assert abs((h[0]-B_OLD)-d)<1e-12
    assert not math.isclose(h[0]-B_OLD,h[0],abs_tol=1e-3)
    np.testing.assert_array_equal(H[:,3],np.zeros(2))
    np.testing.assert_allclose(H[0],[(x[0]-4.)/d,x[1]/d,0.,0.],
                               atol=1e-12,rtol=0)
    np.testing.assert_array_equal(R0,np.diag([.0068578637,.0081]))

def test_analytic_lut_jacobian_against_independent_numeric_difference(lut):
    samples=[np.array([5.61091,.51373,.2931,.0005]),
             np.array([8.323,1.427,-.334,.0]),
             np.array([6.131,-1.249,1.092,-.0002])]
    for x in samples:
        h,H=lut.model(x,CASE)
        num=np.zeros((2,4))
        eps=1e-6
        for j in range(4):
            plus=x.copy();minus=x.copy()
            plus[j]+=eps;minus[j]-=eps
            num[:,j]=(lut.model(plus,CASE)[0]-lut.model(minus,CASE)[0])/(2*eps)
        np.testing.assert_allclose(H,num,rtol=0,atol=2e-4)

def test_yaw_units_and_mount_are_critical_negative_controls(lut):
    x=np.array([6.217,.613,.472,0.])
    h=lut.model(x,CASE)[0]
    wrong_mount=lut.model(x,CASE_MOUNT45)[0]
    wrong_yaw=lut.model(np.r_[x[:2],math.degrees(x[2]),x[3]],CASE)[0]
    assert abs(h[1]-wrong_mount[1])>1e-4
    assert abs(h[1]-wrong_yaw[1])>1e-4

def test_old_wrong_s_range_order_and_double_offset_are_detectable(lut):
    x=np.array([5.612,1.025,.361,0.])
    h,H=lut.model(x,CASE)
    wrong=np.array([h[1],h[0]])
    assert np.max(np.abs(wrong-h))>0.1
    wrong_range=h[0]+B_OLD
    assert abs(wrong_range-h[0])>.5
    assert not np.array_equal(R0,PERMUTE_SR_TO_RS@R0@PERMUTE_SR_TO_RS)

def test_lut_periodic_phi_seam_and_yaw_periodicity(lut):
    val_a,g_a=lut(45.,-180.+1e-9,-180.+1e-9)
    val_b,g_b=lut(45.,180.+1e-9,180.+1e-9)
    assert abs(val_a-val_b)<1e-9
    np.testing.assert_allclose(g_a,g_b,rtol=0,atol=1e-9)
    x=np.array([6.217,.613,.472,0.])
    v0,H0=lut.model(x,CASE)
    xt=x.copy();xt[2]+=2*math.pi
    v1,H1=lut.model(xt,CASE)
    np.testing.assert_allclose(v0,v1,atol=1e-11,rtol=0)
    np.testing.assert_allclose(H0,H1,atol=1e-9,rtol=0)

def test_covariance_and_gate_not_independent_of_state_prior(lut):
    x=np.array([5.21,.61,.32,0.])
    _,H=lut.model(x,CASE)
    P=np.array([[.05,-.01,0.,0.],[-.01,.09,.03,0.],
                [0.,.03,.07,0.],[0.,0.,0.,1e-6]])
    S=H@P@H.T+R0
    assert abs(S[0,1])>1e-6
    eig=np.linalg.eigvalsh(S)
    assert min(eig)>0
    # Wrong assumption S_sr=0 would give a different NIS.
    nu=np.array([.2,.15])
    nis=float(nu@np.linalg.solve(S,nu))
    wrong=float(nu@np.linalg.solve(np.diag(np.diag(S)),nu))
    assert abs(nis-wrong)>1e-5
    assert GATE_JOINT==pytest.approx(9.210340371976184,abs=0)

def test_truth_is_not_exposed_by_any_estimator_frozen_trace():
    attr={f.name for f in fields(FrozenRFTrace)}
    assert "truth_for_offline_scoring_only" not in attr
    assert "truth" not in attr
    assert set(["z_s","z_range","prior_x","prior_P"]).issubset(attr)

def test_invalid_archive_sha_fails_before_open(tmp_path):
    p=tmp_path/"tampered.zip"
    p.write_bytes(b"truncated or tampered archived RF data")
    with pytest.raises(RuntimeError,match="SHA256"):
        open_verified_archive(p)

def test_invalid_state_and_missing_lut_dimension_fail_closed(lut):
    with pytest.raises(ValueError,match="INVALID"):
        lut.model(np.array([1.,float("nan"),0.,0.]),CASE)
    with pytest.raises(ValueError,match="INVALID"):
        lut.model(np.zeros(5),CASE)
    assert not lut.quality(np.array([4.,0.,0.,0.]),CASE)["near_anchor_pole"] is False
