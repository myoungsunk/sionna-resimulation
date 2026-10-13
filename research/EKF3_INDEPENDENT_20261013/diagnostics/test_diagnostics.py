"""Unit contracts for offline diagnostic code. User runs; not an RF experiment."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from p3_compat import (
    B_OLD, corrected_ranges, frozen_detector, predict_e1_bias,
    assert_observation_parity, tap_metres,
)
from run_d0_d4 import (
    O, P3_MODEL, P3_SHA256, REPO, flat_eval_range, hash_file,
    covariance_terms, yaw_error, verify_p2_artifact_integrity,
)
from ekf3 import EKF3


def test_p3_freeze_model_sha256_and_fold_provenance():
    assert hash_file(P3_MODEL) == P3_SHA256
    frozen = json.loads(P3_MODEL.read_text(encoding="utf-8"))
    assert frozen["chosen"] == "E1_on_B"
    assert frozen["feature_schema"] == [
        "1", "r_raw", "r_raw^2", "peak_minus_first_tap_m",
        "that*r_raw", "log_peak", "first_over_peak", "mount==45",
    ]
    assert set(frozen["loro_fold_params"]) == {"R2", "R4", "R5"}
    assert not np.allclose(frozen["loro_fold_params"]["R2"]["E1"]["w"],
                           frozen["params"]["E1"]["w"])


def test_frozen_detector_matches_original_receiver_on_synthetic_H():
    freq = np.linspace(6250400000., 6749600000., 257)
    dist = np.array([2.1, 4.3, 7.5])
    # physically simple but not a stored real RF H.
    h = np.exp(-2j * np.pi * freq[None, :] * (dist[:, None] / O.C0))
    rx = np.stack([h, .7*h*np.exp(.15j)], axis=2)
    H = np.zeros((3,257,2,2),complex)
    H[:,:,:,0] = rx
    raw = O.observe(H,freq,None,None,tx=0)
    out = frozen_detector(H,freq,0.,O,chunk_size=2)
    expected = {
        "z_s":raw["s"],"z_r_m":raw["range_m"],
        "power":raw["power"],"first_arrival_tap":raw["index"]
    }
    checks = assert_observation_parity(out,expected,np.arange(3))
    assert checks["tap_identical"]
    assert np.allclose(out["s"],raw["s"],atol=1e-12)
    assert np.allclose(out["range_raw_m"],raw["range_m"],atol=1e-12)


def test_flat_detector_oracle_matches_original_flat_construction():
    freq = np.linspace(6250400000., 6749600000., 257)
    distances=np.array([2.5,3.9,8.25])
    actual=flat_eval_range(distances,freq,chunk_size=1)
    h=np.exp(-2j*np.pi*freq[None,:]*(distances[:,None]/O.C0))
    original=np.repeat(h[:,:,None],2,axis=2)[:,:,:,None]
    expected=O.observe(original,freq,None,None,tx=0)["range_m"]
    assert np.allclose(actual,expected,atol=1e-12)


def test_fractional_crossing_range_within_neighboring_taps():
    freq=np.linspace(6250400000.,6749600000.,257)
    h=np.exp(-2j*np.pi*freq[None,:]*(np.array([2.5,4.5])[:,None]/O.C0))
    H=np.zeros((2,257,2,2),complex);H[:,:,:,0]=np.stack([h,.8*h],axis=2)
    det=frozen_detector(H,freq,45.,O)
    tm=tap_metres(freq)
    # 30%-threshold preceding the first discrete crossing
    assert np.all(det["fractional_tap"]<=det["index"]+1e-12)
    assert np.all(det["fractional_tap"]>=np.maximum(det["index"]-1,0)-1e-12)
    assert np.all(np.isfinite(det["features"])) and det["features"].shape==(2,8)
    assert np.all(det["features"][:,-1]==1)
    assert np.allclose(det["r_d1_m"],tm*det["fractional_tap"])


def test_e1_predict_linear_standardization_exact():
    x=np.array([[1,2,4,.2,.4,-3.,.8,1], [1,3,9,.3,.9,-4.,.5,0]],float)
    params={"E1":{"w":[.1,.2,.3,.4,.5,.6,.7,.8],"mu":[0]*7,"sd":[2]*7}}
    y=predict_e1_bias(x,params)
    want=.1+(x[:,1:]/2)@np.array([.2,.3,.4,.5,.6,.7,.8])
    assert np.allclose(y,want)


def test_e1_and_d1_physical_range_and_los_negative_control():
    base=np.array([2.0,3.0])
    features=np.ones((2,8))
    fold={"C_const":-.5,"D1_offset":-.6,
          "E1":{"w":[.02]+[0]*7,"mu":[0]*7,"sd":[1]*7}}
    det={"range_raw_m":base,"r_d1_m":base-.03,"features":features}
    full=corrected_ranges(det,fold,channel="full",allow_e1_on_los=False)
    los=corrected_ranges(det,fold,channel="los",allow_e1_on_los=False)
    assert np.allclose(full["B_OLD"],base-B_OLD)
    assert np.allclose(full["C_CONST_LOS"],base+.5)
    assert np.allclose(full["D1_FRACTIONAL"],base-.03+.6)
    assert np.allclose(full["E1_FULL_LORO"],base-B_OLD-.02)
    assert "E1_FULL_LORO" not in los
    neg=corrected_ranges(det,fold,channel="los",allow_e1_on_los=True)
    assert "E1_ON_LOS_NEGCTRL" in neg


def test_range_only_change_cannot_change_A_same_prior():
    x=np.array([1.2,-.2,.3]);p=np.diag([.05,.08,.02])
    anchor=(4.,0.,2.65)
    def model(y):
        H=np.array([.06,-.04,.5])
        return float(.1 + H@y),H
    prior=EKF3(x,p)
    a1=prior.clone();a2=prior.clone();b1=prior.clone();b2=prior.clone()
    s=model(x)[0]+.04
    a1.update_heading(s,.0081,s_model=model)
    a2.update_heading(s,.0081,s_model=model)
    d=np.linalg.norm([x[0]-4,x[1],.45-2.65])
    b1.update_joint(s,d+B_OLD+.02,.0081,.0068578637,0,
                    s_model=model,anchor_xyz_m=anchor,tag_height_m=.45)
    b2.update_joint(s,d+B_OLD-.02,.0081,.0068578637,0,
                    s_model=model,anchor_xyz_m=anchor,tag_height_m=.45)
    assert np.array_equal(a1.x,a2.x) and np.array_equal(a1.P,a2.P)
    assert not np.array_equal(b1.x,b2.x)


def test_schur_nees_identity_exact_and_heading_wrap():
    p=np.array([[.3,.05,.02],[.05,.4,-.01],[.02,-.01,.02]])
    e=np.array([.3,.2,math.radians(4)])
    result=covariance_terms(e,p)
    assert result["pose_nees"]==pytest.approx(result["yaw_nees"]+result["conditional_xy_nees"])
    assert float(yaw_error(math.pi-.01,-math.pi+.01))==pytest.approx(-.02)


def test_overlap_score_requires_no_oracle_measurement_inputs():
    # Corrected RF range features are H-only; truth is deliberately absent.
    freq=np.linspace(6250400000.,6749600000.,257)
    H=np.ones((1,257,2,2),complex)
    det=frozen_detector(H,freq,0.,O)
    fold={"C_const":-.535,"D1_offset":-.6,
          "E1":{"w":[0]*8,"mu":[0]*7,"sd":[1]*7}}
    corr=corrected_ranges(det,fold,channel="full",allow_e1_on_los=False)
    assert np.all(np.isfinite(corr["E1_FULL_LORO"]))
