"""Packaging/launch tests; test bytes are not antenna or RF evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "cloud_runner", ROOT / "scripts/drive_sim/run_body_probe_v2_cloud.py")
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


def assets(tmp_path):
    expected = {}
    for name in ("LP_plus45_bank.npz", "LP_minus45_bank.npz"):
        path = tmp_path / name
        path.write_bytes(b"unit-test-only " + name.encode())
        expected[name] = cloud.sha256(path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"npz_sha256": expected}), encoding="utf8")
    cfg = {"rf": {"mode": "range_only", "bank_dir": None, "bank_manifest": None},
           "cloud_assets": {"bank_sha256": expected,
                            "manifest_sha256": cloud.sha256(manifest)}}
    return cloud.resolve_config(cfg, tmp_path, manifest)


def test_template_keeps_model_and_original_manifest():
    original = json.loads((ROOT / "configs/body_probe/ekf_native_noisy_body_v1.json").read_text())
    template = json.loads(cloud.DEFAULT_CONFIG.read_text())
    assets_contract = template.pop("cloud_assets")
    template["rf"]["bank_dir"] = None
    template["rf"]["bank_manifest"] = None
    assert template == original
    assert cloud.sha256(cloud.DEFAULT_MANIFEST) == assets_contract["manifest_sha256"]
    assert set(assets_contract["bank_sha256"]) == {"LP_plus45_bank.npz", "LP_minus45_bank.npz"}


def test_resolution_does_not_mutate_template(tmp_path):
    template = {"rf": {"mode": "range_only"}}
    before = copy.deepcopy(template)
    cfg = cloud.resolve_config(template, tmp_path, tmp_path / "manifest.json")
    assert template == before
    assert Path(cfg["rf"]["bank_dir"]).is_absolute()


def test_valid_unit_assets(tmp_path):
    cfg = assets(tmp_path)
    assert cloud.verify_assets(cfg) == cfg["cloud_assets"]["bank_sha256"]


@pytest.mark.parametrize("kind,error", [
    ("missing", "BANK_MISSING"), ("pointer", "BANK_IS_LFS_POINTER"),
    ("wrong_hash", "BANK_SHA_MISMATCH"), ("manifest", "BANK_MANIFEST_SHA_MISMATCH")])
def test_invalid_assets_are_blocked(tmp_path, kind, error):
    cfg = assets(tmp_path)
    bank = tmp_path / "LP_plus45_bank.npz"
    if kind == "missing":
        bank.unlink()
    elif kind == "pointer":
        bank.write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
    elif kind == "wrong_hash":
        bank.write_bytes(b"other unit bytes")
    else:
        Path(cfg["rf"]["bank_manifest"]).write_text("{}")
    with pytest.raises(ValueError, match=error):
        cloud.verify_assets(cfg)


def test_default_is_precheck_only(tmp_path, monkeypatch):
    cfg = assets(tmp_path)
    template = tmp_path / "config.json"
    template.write_text(json.dumps(cfg))
    calls = []
    def run(cmd):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cloud.subprocess, "run", run)
    out = tmp_path / "not_created"
    assert cloud.main(["--config", str(template), "--bank-dir", str(tmp_path),
                       "--bank-manifest", cfg["rf"]["bank_manifest"], "--out", str(out)]) == 0
    assert len(calls) == 1 and "--execute-native" not in calls[0]
    assert not out.exists() and not out.with_name(out.name + ".config.json").exists()


def test_execution_retains_config_and_native_arguments(tmp_path, monkeypatch):
    cfg = assets(tmp_path)
    template = tmp_path / "config.json"
    template.write_text(json.dumps(cfg))
    calls = []
    monkeypatch.setattr(cloud.subprocess, "run",
                        lambda cmd: calls.append(cmd) or SimpleNamespace(returncode=0))
    out = tmp_path / "run01"
    assert cloud.main(["--config", str(template), "--bank-dir", str(tmp_path),
                       "--bank-manifest", cfg["rf"]["bank_manifest"],
                       "--out", str(out), "--execute-native"]) == 0
    assert len(calls) == 2 and "--execute-native" in calls[1]
    assert json.loads(out.with_name("run01.config.json").read_text())["rf"] == cfg["rf"]
    # Native runner owns creation of --out; the wrapper does not pre-create it.
    assert not out.exists()


def test_precheck_failure_blocks_execution(tmp_path, monkeypatch):
    cfg = assets(tmp_path)
    template = tmp_path / "config.json"
    template.write_text(json.dumps(cfg))
    calls = []
    monkeypatch.setattr(cloud.subprocess, "run",
                        lambda cmd: calls.append(cmd) or SimpleNamespace(returncode=2))
    out = tmp_path / "run01"
    assert cloud.main(["--config", str(template), "--bank-dir", str(tmp_path),
                       "--bank-manifest", cfg["rf"]["bank_manifest"],
                       "--out", str(out), "--execute-native"]) == 2
    assert len(calls) == 1 and not out.with_name("run01.config.json").exists()
