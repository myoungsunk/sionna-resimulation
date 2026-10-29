"""Negative fixtures for the contract validator and manifest schema (CI_REQUIREMENTS: must fail closed)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import manifest as MF  # noqa: E402
import validate_contract as VC  # noqa: E402

G = "a" * 40


def _contract(tmp, lock=None, draft=True):
    body = "# C\nstage DRAFT\nP0_TO_RESOLVE_GOVERNANCE_SHA\n" if draft else "# C\n"
    if lock is not None:
        body += "\n## FROZEN_LOCK\n```json\n" + json.dumps(lock) + "\n```\n"
    p = tmp / "c.md"; p.write_text(body); return p


def _lock(**kw):
    base = dict(status="FROZEN", governance_git_sha=G, base_git_sha="b" * 40, p0_status="PASS",
                resolved={f: "ok" for f in VC.SCIENCE_FIELDS} | {f: "DEFERRED_PRE_P3_AMENDMENT" for f in VC.RF_FIELDS},
                splits={"S": {"DEV": [0, 1], "HOLDOUT": [1000, 1001]}})
    base.update(kw); return base


def test_draft_mode_does_not_unlock(tmp_path, capsys):
    assert VC.main(["--contract", str(_contract(tmp_path)), "--mode", "draft"]) == 0
    assert '"unlocks_experiments": false' in capsys.readouterr().out


def test_frozen_rejects_draft(tmp_path):
    assert VC.main(["--contract", str(_contract(tmp_path)), "--mode", "frozen", "--phase", "G2"]) == 1


def test_frozen_accepts_complete_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("MBVAR_GOVERNANCE_SHA", G)
    assert VC.main(["--contract", str(_contract(tmp_path, _lock(), draft=False)), "--mode", "frozen", "--phase", "G2"]) == 0


def test_negative_invalid_sha(tmp_path, monkeypatch):
    monkeypatch.setenv("MBVAR_GOVERNANCE_SHA", G)
    assert VC.main(["--contract", str(_contract(tmp_path, _lock(governance_git_sha="xyz"), draft=False)), "--mode", "frozen", "--phase", "G2"]) == 1


def test_negative_changed_governance(tmp_path, monkeypatch):
    monkeypatch.setenv("MBVAR_GOVERNANCE_SHA", "c" * 40)
    assert VC.main(["--contract", str(_contract(tmp_path, _lock(), draft=False)), "--mode", "frozen", "--phase", "G2"]) == 1


def test_negative_unresolved_science_field(tmp_path, monkeypatch):
    monkeypatch.setenv("MBVAR_GOVERNANCE_SHA", G)
    lk = _lock(); lk["resolved"]["HGEOMETRY"] = "P0_TO_RESOLVE_HGEOMETRY"
    assert VC.main(["--contract", str(_contract(tmp_path, lk, draft=False)), "--mode", "frozen", "--phase", "G2"]) == 1


def test_negative_rt_without_rf_amendment(tmp_path, monkeypatch):
    monkeypatch.setenv("MBVAR_GOVERNANCE_SHA", G)
    assert VC.main(["--contract", str(_contract(tmp_path, _lock(), draft=False)), "--mode", "frozen", "--phase", "G4"]) == 1


def test_negative_split_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv("MBVAR_GOVERNANCE_SHA", G)
    lk = _lock(splits={"S": {"DEV": [0, 1], "HOLDOUT": [1, 1000]}})
    assert VC.main(["--contract", str(_contract(tmp_path, lk, draft=False)), "--mode", "frozen", "--phase", "G2"]) == 1


def test_negative_manifest_missing_output_hash():
    m = dict(contract_id="MBVAR-INFO-001", phase="P1_S0", execution_status="PASS", utc_completed="2026-10-29T00:00:00Z",
             source_git_sha="a" * 40, governance_git_sha=G, contract_sha256="d" * 64, config_sha256="e" * 64, input_lock_sha256="f" * 64,
             source_code_sha256={"x": "1" * 64}, seed_ledger_sha256="2" * 64, run_command="python x", scientific_verdict="NOT_EVALUATED",
             independence_unit="mathematical_deterministic", limitations=["x"])
    assert any(e.startswith("missing:output_sha256") for e in MF.validate_manifest(m))
    m["output_sha256"] = {"a.csv": "not-a-hash"}
    assert any(e.startswith("object:output_sha256") for e in MF.validate_manifest(m))
