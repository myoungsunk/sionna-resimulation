"""Frozen bank/detector range model is the only reason to change range_offset."""
import hashlib
import json
from pathlib import Path
import pytest
from scripts.drive_sim.prepare_calibrated_native_probe import load_validated_model,prepare


def fixture_files(tmp_path):
    manifest_sha="f"*64
    ffdhash={"LP_plus45_bank.npz":"a"*64,"LP_minus45_bank.npz":"b"*64}
    cfg=dict(rf=dict(mode="range_only",mount_deg=0.),
        sensor=dict(seed=0),
        initial_filter=dict(x0=[7.,.1,0.,0.,0.,0.],range_offset_m=0.),
        physical=dict(slip_mode="neutral",baseline_slip_left=0.,baseline_slip_right=0.),
        cloud_assets=dict(bank_sha256=ffdhash,manifest_sha256=manifest_sha),
        claims=dict(scientific_PASS=False))
    template=tmp_path/"template.json";template.write_text(json.dumps(cfg))
    meta=dict(schema_version="INDEPENDENT_FFD_LOS_DETECTOR_CAL_V1",
        true_evaluation_RF_input="NOT_USED",bank_sha256=ffdhash,
        bank_manifest_sha256=manifest_sha,
        train_site_xy=[[5.,.3]],holdout_site_xy=[[8.,-.3]],
        evaluation_xy_exclusion=[7.,.1],
        mount_models={"0":{"range_offset_m":-.6,"independent_site_validation_pass":True},
                      "45":{"range_offset_m":-.58,"independent_site_validation_pass":True}})
    meta["calibration_sha256"]=hashlib.sha256(
        json.dumps(meta,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    calibration=tmp_path/"calibration.json";calibration.write_text(json.dumps(meta))
    return template,calibration


def test_prepare_calibrated_config_does_not_change_filter_Q_R_gate_or_historical_defaults(tmp_path):
    t,c=fixture_files(tmp_path)
    raw=json.loads(t.read_text())
    a=prepare(t,c,mount_deg=0.,seed=4,slip_mode="neutral")
    assert a["initial_filter"]["range_offset_m"]==-0.6
    assert a["rf"]["mount_deg"]==0.
    assert a["sensor"]["seed"]==4
    assert a["physical"]["slip_mode"]=="neutral"
    assert a["physical"]["baseline_slip_right"]==0.
    assert a["claims"]["scientific_PASS"] is False
    assert a["initial_filter"]["x0"]==raw["initial_filter"]["x0"]


def test_deterministic_nonzero_slip_and_independent_initial_prior_are_explicit(tmp_path):
    t,c=fixture_files(tmp_path)
    a=prepare(t,c,mount_deg=45.,seed=5,slip_mode="hypothesis",prior_random_seed=101)
    b=prepare(t,c,mount_deg=45.,seed=5,slip_mode="hypothesis",prior_random_seed=101)
    assert a==b
    assert a["initial_filter"]["range_offset_m"]==-.58
    assert a["physical"]["baseline_slip_right"]==.05
    assert a["physical"]["baseline_icr_offset_m"]==.005
    assert a["initial_filter"]["x0"][:3] != [7.,.1,0.]
    assert a["prior_sampling"]["true_run_pose_not_read"]


def test_calibration_must_pass_independent_holdout_and_sha(tmp_path):
    t,c=fixture_files(tmp_path)
    meta=json.loads(c.read_text())
    meta["mount_models"]["0"]["independent_site_validation_pass"]=False
    meta.pop("calibration_sha256")
    meta["calibration_sha256"]=hashlib.sha256(
        json.dumps(meta,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    c.write_text(json.dumps(meta))
    with pytest.raises(ValueError,match="HOLDOUT_CALIBRATION_NOT_PASSED"):
        prepare(t,c,mount_deg=0.,seed=0,slip_mode="neutral")
    meta["mount_models"]["0"]["range_offset_m"]=-.58
    c.write_text(json.dumps(meta))
    with pytest.raises(ValueError,match="PROVENANCE_ORACLE_OR_HASH_FAILURE"):
        load_validated_model(c,0.)
