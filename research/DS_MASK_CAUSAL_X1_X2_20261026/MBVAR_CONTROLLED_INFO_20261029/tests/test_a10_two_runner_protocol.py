"""No research data accessed: source/input immutability and pair-compare negative fixtures."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

CODE=Path(__file__).resolve().parents[1]/"code"
sys.path.insert(0,str(CODE))
import a10_cross_runner_replay as X


def _row(cid, field):
    P=np.array([[.002,.00001,0,0],[.00001,.003,0,0],
                [0,0,.0001,.0000001],[0,0,.0000001,.000001]],float)
    return dict(case=cid,field=field,role="LOW" if cid=="K1" else "REV60",
                cell="TIME_1" if cid=="K1" else "TIME_HIGH_5",
                sensor_seed=2 if cid=="K1" else 0,arm="ORACLE_CORR_BATCH",
                cost=53.5,cost_E=55.,class_v31="CONVERGED_SMOOTH",
                ms_best_k=0,n_alt_ambiguous=0,alt_ambiguous_starts="",
                max_alt_dref_within_1chi2=0.1,solver_status="CONVERGED",
                nees4_C10=0.7,nees4_independent=0.7,
                **{f"xend_{j}":float(j) for j in range(4)},
                **{f"C10rot_{i}{j}":float(P[i,j]) for i in range(4)
                   for j in range(i,4)})


def pair():
    rows=[_row("K1",10),_row("K2",11)]
    common=dict(schema="A010_DEV2_2RUNNER_REPLAY_V1",
                allowed_cases=["K1","K2"],archive={"foo":"a"*64},
                source_code_sha256={"code/x.py":"b"*64},
                contract_id="MBVAR-INFO-001",contract_sha256=X.CONTRACT_SHA,
                governance_git_sha=X.GOVERNANCE_SHA,
                run_request_sha256=X.RUN_REQUEST_SHA,
                science_status="SCIENCE_DRAFT",science_release_allowed=False,
                independent_auditor_signed=False,
                source_git_sha="c"*40,input_sha256=X.EXPECTED_SOURCE_INPUT_SHA,
                manifest_sha256="d"*64,
                input_evidence=[{"case":"K1"},{"case":"K2"}],rows=rows)
    a=dict(common,runner_id="vm-a",runner_replica="a",runner_boot_id="boot-a",
           environment={"cpu":"amd"})
    b=dict(copy.deepcopy(common),runner_id="vm-b",runner_replica="b",
           runner_boot_id="boot-b",environment={"cpu":"intel"})
    return a,b


def compare(tmp_path,a,b):
    ap=tmp_path/"a.json";bp=tmp_path/"b.json"
    X.safe_json(ap,a);X.safe_json(bp,b)
    return X.compare(ap,bp,tmp_path/"result")


def test_positive_two_isolated_runner_receipts(tmp_path):
    a,b=pair()
    assert compare(tmp_path,a,b)==0
    result=json.loads((tmp_path/"result"/"TWO_RUNNER_COMPARISON.json").read_text())
    assert result["status"]=="TECHNICAL_REPLAY_PASS"
    assert result["numerical"]["pass_"] and result["numerical"]["n_rows"]==2
    assert not result["science_freeze_allowed"]
    assert result["dev3"]==result["holdout2"]==result["rt"]=="NO-GO"


@pytest.mark.parametrize("attack",[
    "one_vm","same_replica","input_sha","source_sha","code_sha",
    "receipt_archive","manifest_sha","change_cost","change_state",
    "change_covariance","change_class","change_mode_count","change_mode_list",
    "change_start","change_nees","missing_case","changed_science_authority"
])
def test_pair_comparison_negative_fixtures(tmp_path,attack):
    a,b=pair()
    if attack=="one_vm":b["runner_boot_id"]=a["runner_boot_id"]
    if attack=="same_replica":b["runner_replica"]="a"
    if attack=="input_sha":b["input_sha256"]="f"*64
    if attack=="source_sha":b["source_git_sha"]="f"*40
    if attack=="code_sha":b["source_code_sha256"]["code/x.py"]="f"*64
    if attack=="receipt_archive":b["archive"]["foo"]="e"*64
    if attack=="manifest_sha":b["manifest_sha256"]="e"*64
    if attack=="change_cost":b["rows"][0]["cost"]+=1e-3
    if attack=="change_state":b["rows"][0]["xend_1"]+=.5
    if attack=="change_covariance":b["rows"][0]["C10rot_00"]*=1.05
    if attack=="change_class":b["rows"][0]["class_v31"]="NOT_CERTIFIED"
    if attack=="change_mode_count":b["rows"][0]["n_alt_ambiguous"]=1
    if attack=="change_mode_list":b["rows"][0]["alt_ambiguous_starts"]="psi+1"
    if attack=="change_start":b["rows"][0]["ms_best_k"]=3
    if attack=="change_nees":b["rows"][0]["nees4_independent"]+=.2
    if attack=="missing_case":b["rows"].pop()
    if attack=="changed_science_authority":b["science_release_allowed"]=True
    with pytest.raises(SystemExit):
        compare(tmp_path,a,b)


@pytest.mark.parametrize("replica",["a","b"])
def test_cannot_replay_as_local_or_non_authorized_job(monkeypatch,tmp_path,replica):
    monkeypatch.delenv("MBVAR_A010_DEV2_PREFLIGHT",raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS",raising=False)
    with pytest.raises(SystemExit,match="ERR_A010_REPLAY_SCOPE"):
        X.replay(tmp_path,replica)


def test_only_legacy_k1_k2_can_be_replayed():
    assert X.FORENSIC_CASES==("K1","K2")
    assert X.EXPECTED_SOURCE_INPUT_SHA==X.CAN.CANON_SHA
    assert X.NUMERIC_LIMITS["state_dref"]==1e-6
    assert X.NUMERIC_LIMITS["C10_natural_rel"]==1e-3


def test_missing_or_modified_run_request_fails_before_data_access(monkeypatch,tmp_path):
    monkeypatch.setattr(X,"EXP",tmp_path)
    with pytest.raises((FileNotFoundError,SystemExit)):
        X.guard_archive()
    (tmp_path/"RUN_REQUEST.json").write_text("{}")
    with pytest.raises(SystemExit,match="ERR_A010_FORENSIC_RUN_REQUEST_CHANGED"):
        X.guard_archive()
