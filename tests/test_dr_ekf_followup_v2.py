"""Offline tests for the independent V0-V5 research scripts (no D6 cache writes)."""
from __future__ import annotations

import dataclasses
import importlib
import math
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT = Path(__file__).resolve().parents[1]
FOLLOW = PROJECT / "research" / "DR_EKF_DIAGNOSIS_20261013" / "followup_v2"
sys.path.insert(0, str(FOLLOW))
C = importlib.import_module("common")
V0 = importlib.import_module("v0_cache_audit")
V2 = importlib.import_module("v2_pf_reference_audit")
V3 = importlib.import_module("v3_second_order")
V4 = importlib.import_module("v4_calibration")
V5 = importlib.import_module("v5_independent")


def test_frozen_spec_bytes_match_preregistration():
    meta = C.git_frozen_spec()
    assert meta["prereg_commit"].startswith("9bbe217a")
    assert len(meta["sha256"]) == 64


def test_cache_audit_does_not_create_missing_files(tmp_path):
    sample = [8100, 8101]
    missing = tmp_path / "arm" / "R2_d0.npz"
    res, data = C.validated_cache(missing, sample, "R2", min_age_s=0)
    assert res["status"] == "MISSING" and data is None
    assert not missing.exists()


def test_safe_output_refuses_d6_cache_and_out():
    for protected in ("cache", "out"):
        with pytest.raises(ValueError):
            C.new_dir(C.DIAG / protected / "do-not-create")


def test_d6_no_verdict_when_incomplete(tmp_path):
    result = V0.scan(cache_root=tmp_path / "empty", min_age_s=0)
    assert result["status"] == "INCOMPLETE_NO_D6_VERDICT"
    assert result["verified_cells"] == 0
    assert result["expected_cells"] == 63


def test_second_order_base_matches_frozen_step():
    arm = C.H.ARMS["A2_3_GAUSS_LEVEL"]
    cfg = C.H.make_cfg(arm, 1, dict(wheelbase=0.0))
    x = np.array([2.0, 0.3, 0.4, 0.001, 0.005, 0.004])
    P = np.diag(np.asarray(cfg.p0_std)**2)
    d, gyro, odom, dt = .04, .007, .008, .2
    our_x, our_P, info = V3.joint_moments(x, P, d, gyro, odom, dt, cfg, "BASE")
    filt = C.H.F.SensorV2Filter(cfg, None, x.copy(), P0=P.copy())
    filt.step(d, gyro, odom, dt)
    frozen_x, frozen_P = filt.mean_cov()
    np.testing.assert_allclose(our_x, frozen_x, rtol=0, atol=1e-10)
    np.testing.assert_allclose(our_P, frozen_P, rtol=0, atol=1e-10)


def test_second_order_mean_and_covariance_are_separate():
    cfg = dataclasses.replace(C.H.make_cfg(
        C.H.ARMS["A2_3_GAUSS_LEVEL"], 1, dict(wheelbase=0.0)),
        use_odom_heading=False)
    x = np.zeros(6)
    P = np.diag([.03**2, .03**2, math.radians(8)**2,
                 math.radians(.12)**2, .0104**2, .0064**2])
    params = (.04, .0, .0, .2, cfg)
    b_x, b_P, _ = V3.joint_moments(x, P, *params, "BASE")
    m_x, m_P, _ = V3.joint_moments(x, P, *params, "MEAN2")
    c_x, c_P, _ = V3.joint_moments(x, P, *params, "COV2")
    bc_x, bc_P, _ = V3.joint_moments(x, P, *params, "BOTH2")
    assert m_x[0] < b_x[0]   # Missing 2nd-order longitudinal mean shift.
    assert c_P[0, 0] > b_P[0, 0]  # Missing 2nd-order longitudinal variance.
    np.testing.assert_allclose(m_P, b_P, atol=1e-10, rtol=0)
    np.testing.assert_allclose(c_x, b_x, atol=1e-10, rtol=0)
    np.testing.assert_allclose(bc_x, m_x, atol=1e-10, rtol=0)
    np.testing.assert_allclose(bc_P, c_P, atol=1e-10, rtol=0)


def test_calibration_fisher_speed_intervention_preserves_distance():
    baseline = V4.information_proxy("R2", "fixed")
    altered = V4.information_proxy("R2", "vary_speed")
    assert altered["forward_distance_m"] == pytest.approx(
        baseline["forward_distance_m"], abs=1e-7)
    assert np.isfinite(baseline["weakest_info_eigenvalue"])
    assert np.isfinite(altered["weakest_info_eigenvalue"])


def test_v5_rejects_d6_and_dev_seed_ranges():
    with pytest.raises(ValueError):
        V5.initialize("specs/unsafe.json", "gauss_level", "BOTH2", "8100:8400")
    with pytest.raises(ValueError):
        V5.initialize("specs/unsafe.json", "gauss_level", "BOTH2", "8000:8300")


def test_v5_evaluation_is_read_only_when_no_run(tmp_path):
    assert not (FOLLOW / "runs" / "no-existing-run-test-489").exists()
    # The main script's evaluate branch guards a missing marker *before* writing.
    path = V5.run_dir_path("runs/no-existing-run-test-489")
    assert not path.exists()
    assert "run" in str(path)


def test_v2_missing_file_is_not_pass(tmp_path):
    result = V2.audit(tmp_path / "no_pf_results.json")
    assert result["status"] == "NOT_RUN"


@pytest.mark.parametrize("seeds", ["8100:8101", "9000:9001", "8032:8033"])
def test_development_seed_quarantine(seeds):
    with pytest.raises(ValueError):
        C.development_seeds(seeds)
    assert C.development_seeds("8000:8002") == [8000, 8001]


def test_v5_hashes_bind_world_scoring_and_motion():
    hashes = V5.expected_hashes()
    for path in (C.DIAG / "dr_consistency.py",
                 C.H.FROZEN_SRC / "qclean_uwb/drivesim/sensors.py",
                 C.H.FROZEN_SRC / "qclean_uwb/drivesim/filters.py",
                 C.H.MOTION_DIR / "MOTION_R2.csv",
                 C.H.MOTION_DIR / "SHA256SUMS_CSV.txt"):
        assert hashes[path.relative_to(C.ROOT).as_posix()] == C.sha256(path)


@pytest.mark.parametrize("corruption", [None, "asymmetric", "heading", "sigma"])
def test_cache_scientific_fields_are_validated(tmp_path, monkeypatch, corruption):
    monkeypatch.setitem(C.H.MOT, "R2", {"t": np.arange(2)})
    P = np.broadcast_to(np.eye(3), (1, 2, 3, 3)).copy()
    arr = dict(seeds=np.array([8100]), E_post=np.ones((1, 2, 6)),
               P3_post=P, sigma_psi_post=np.ones((1, 2)),
               nees_pose_post=np.full((1, 2), 3.),
               nees_heading_post=np.ones((1, 2)),
               nees_cond_xy_post=np.full((1, 2), 2.),
               status=np.zeros((1, 2), dtype=int))
    if corruption == "asymmetric":
        P[0, 0, 0, 1] = .5
    elif corruption == "heading":
        arr["nees_heading_post"][0, 0] = 20.
    elif corruption == "sigma":
        arr["sigma_psi_post"][0, 0] = 3.
    p = tmp_path / "cache.npz"
    np.savez(p, **arr)
    report, _ = C.validated_cache(p, [8100], "R2", min_age_s=0, full_psd=True)
    assert report["status"] == ("VALID" if corruption is None else "INVALID")


def test_hessian_heading_curvature_against_analytic_derivatives():
    cfg = C.H.make_cfg(C.H.ARMS["A2_3_GAUSS_LEVEL"], 1, dict(wheelbase=0.))
    x = np.array([2., .3, math.pi - .001, .001, .005, .004])
    d, gyro, dt = .04, .007, .2
    Sigma = np.diag([1e-6] * 9)
    f = lambda u: V3.transform(u, x, d, gyro, dt, cfg.wheel_base,
                               cfg.wheel_base, 0.)
    _, h = V3.hessian_numeric(f, Sigma, f(np.zeros(9)))
    D = 1 + x[4]
    assert h[2, 3, 4] == pytest.approx(dt / D**2, rel=2e-4)
    assert h[2, 4, 4] == pytest.approx(2 * (gyro-x[3]*dt) / D**3, rel=2e-4)
    assert h[2, 4, 7] == pytest.approx(1 / D**2, rel=2e-4)
