"""Deterministic FFD hash/config preflight tests: no native Sionna or robot runs."""
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.drive_sim import preflight_body_probe_native as P


def fixture_config(tmp_path, monkeypatch):
    cfg=json.loads((P.ROOT/"configs/body_probe/ekf_native_noisy_body_v1.json").read_text())
    directory=tmp_path/"banks"
    directory.mkdir()
    f=np.linspace(6.2504e9,6.7496e9,257)
    for name in P.PORTS:
        np.savez_compressed(directory/f"{name}_bank.npz",freqs_hz=f,
                            theta_deg=np.array([0.,90.]),phi_deg=np.array([-180.,0.]),
                            e_theta=np.ones((257,2,2),dtype=complex),
                            e_phi=np.zeros((257,2,2),dtype=complex))
    manifest=tmp_path/"BANK_MANIFEST.json"
    manifest.write_text(json.dumps({"npz_sha256":{
        f"{name}_bank.npz":P.digest(directory/f"{name}_bank.npz") for name in P.PORTS}}))
    cfg["rf"]["bank_manifest"]=str(manifest)
    cfg["rf"]["bank_dir"]=str(directory)
    monkeypatch.setattr(P.metadata,"version",lambda name:P.EXPECTED_VERSIONS[name])
    monkeypatch.setattr(P,"git_state",lambda root:{"head":"fixed-head","worktree_clean":True})
    return cfg,directory


def test_preflight_checks_sha_versions_paths_without_running_sionna(tmp_path,monkeypatch):
    cfg,_=fixture_config(tmp_path,monkeypatch)
    r=P.validate_native_inputs(cfg,output_path=tmp_path/"new_run",expected_head="fixed-head")
    assert r["ready"] and r["status"]=="PREFLIGHT_PASS_NOT_EXECUTED"
    assert r["frequency_grid"]["count"]==257
    assert r["scientific_PASS"] is False
    assert "NO_ACTIVE_S_HEADING_UPDATE" in r["known_claim_limits"]


def test_preflight_rejects_bank_bit_change(tmp_path,monkeypatch):
    cfg,directory=fixture_config(tmp_path,monkeypatch)
    with (directory/"LP_minus45_bank.npz").open("ab") as f:
        f.write(b"tamper")
    r=P.validate_native_inputs(cfg,output_path=tmp_path/"new_run",expected_head="fixed-head")
    assert not r["ready"]
    assert "BANK_HASH_MISMATCH_LP_minus45_bank.npz" in r["issues"]


def test_preflight_rejects_occupied_result_directory_and_bad_git(tmp_path,monkeypatch):
    cfg,_=fixture_config(tmp_path,monkeypatch)
    directory=tmp_path/"existing_run";directory.mkdir()
    r=P.validate_native_inputs(cfg,output_path=directory,expected_head="wrong-head")
    assert not r["ready"]
    assert "OUTPUT_ALREADY_EXISTS_NO_OVERWRITE" in r["issues"]
    assert "SOURCE_HEAD_MISMATCH" in r["issues"]
