#!/usr/bin/env python3
"""Explicitly gated, one-stage-at-a-time VAB shadow study runner.

Default: plan only. S1/S2/S3 are new shadow studies, NOT the original
E1-02/E2 stages, and never activate a provider or operational FP correction.
Each science execution requires a NEW SHA-bound manifest and approval.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from pathlib import Path
import gzip
import hashlib
import io
import json
import sys
import traceback
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from qclean_uwb.fp_sc.followup.contracts import (
    ContractError, Policy, digest, jsonable, rooted, sha256, verify_files, write_json)
from qclean_uwb.fp_sc.followup.data import (
    load_shadow_online_only, load_shadow_reference_after_s1,
    load_shadow_truth_for_s3_only)
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.engine import OriginalAdapter
from qclean_uwb.fp_sc.e0_baseline import ORIGINAL_CODE
from qclean_uwb.fp_sc.followup.vab_shadow import (
    shadow_select_case, compare_shadow_observations, same_prior_shadow_one_step,
    crosscheck_s1_s2_for_s3, posthoc_s3_one_step_errors)

STAGES=("S1_SHADOW_SELECT","S2_OBSERVATION_COMPARE","S3_FIXED_PRIOR_EKF")
PREREQ={STAGES[0]:(),STAGES[1]:(STAGES[0],),
        STAGES[2]:(STAGES[0],STAGES[1])}
CODE_REQUIRED=(
    "scripts/fp_sc_vab_shadow_stages.py",
    "src/qclean_uwb/fp_sc/followup/vab_shadow.py",
    "src/qclean_uwb/fp_sc/followup/selection.py",
    "src/qclean_uwb/fp_sc/followup/detection.py",
    "src/qclean_uwb/fp_sc/followup/integrity.py",
    "src/qclean_uwb/fp_sc/followup/bridge.py",
    "src/qclean_uwb/fp_sc/followup/numerics.py",
    "src/qclean_uwb/fp_sc/followup/contracts.py",
    "src/qclean_uwb/fp_sc/followup/engine.py",
    "src/qclean_uwb/fp_sc/followup/data.py",
    "src/qclean_uwb/fp_sc/candidates.py",
    "src/qclean_uwb/fp_sc/candidate_revision.py",
    "src/qclean_uwb/fp_sc/e0_baseline.py",
    "src/qclean_uwb/drivesim/observation.py",
)
MODEL_REQUIRED=("LP_plus45_bank.npz", "LP_minus45_bank.npz")
BASELINE_REQUIRED=tuple(ORIGINAL_CODE) + (
    "research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/pilot.py",)
IDENTITY_FIELDS=("case","policy","policy_sha256","candidate_arm",
                 "candidate_mode","source_commit")


def plan():
    return dict(status="CODE_ONLY_NO_SCIENCE_RUN",stages=[
        {"stage":s,"requires_reviewed":list(PREREQ[s])} for s in STAGES],
        candidate="VAB_TWO_PORT_UNION",policy="FROZEN_R1_SHADOW",
        provider="NO_VALID_UNTRUSTED_DIAGNOSTIC",
        no_output_reuse=True,old_e1_e2_not_started=True,
        E4_closed_loop="SEPARATE_FUTURE_CONTRACT_AFTER_S3_REVIEW")


def identity(manifest):
    # Only common scientific inputs belong here: stage outputs/reviews differ
    # legitimately between stages and must not perturb the common identity.
    common = {key:manifest[key] for key in IDENTITY_FIELDS}
    common.update(identity_recipe="SHADOW_COMMON_LOCK_V2",
        code_files=manifest["code_files"],
        baseline_sources=manifest["baseline_sources"],
        model_files=manifest["model_files"],
        case_payloads={manifest["case"][key]:manifest["input_files"][manifest["case"][key]]
                       for key in ("online_npz", "evaluator_npz")})
    return digest(common)


def inspect_manifest(manifest_path, *, require_stage=None):
    root=ROOT
    path=Path(manifest_path).resolve()
    if not path.is_file():
        raise ContractError("MANIFEST_MISSING")
    m=json.loads(path.read_text(encoding="utf8"))
    if m.get("schema")!="FP_SC_VAB_SHADOW_STAGES_V1":
        raise ContractError("SHADOW_MANIFEST_SCHEMA")
    stage=m.get("stage")
    if stage not in STAGES or (require_stage is not None and stage!=require_stage):
        raise ContractError("SHADOW_STAGE_ID_MISMATCH")
    if m.get("candidate_arm")!="VAB" or m.get("candidate_mode")!="TWO_PORT_UNION":
        raise ContractError("SHADOW_VAB_BINDING_REQUIRED")
    if m.get("source_commit")!="e416cf62c0cde15151a1851168231da73a0cbfff":
        raise ContractError("SHADOW_SOURCE_BASE_UNREVIEWED")
    p=Policy(**m["policy"])
    if m["policy_sha256"]!=p.sha:
        raise ContractError("SHADOW_POLICY_NOT_LOCKED")
    if not set(CODE_REQUIRED)<=set(m.get("code_files",{})):
        raise ContractError("SHADOW_CODE_LOCK_INCOMPLETE")
    verify_files(root,m["code_files"])
    if not set(BASELINE_REQUIRED) <= set(m.get("baseline_sources", {})):
        raise ContractError("SHADOW_BASELINE_SOURCE_LOCK_EMPTY")
    verify_files(root,m["baseline_sources"])
    if not set(MODEL_REQUIRED) <= set(m.get("model_files", {})):
        raise ContractError("SHADOW_MODEL_LOCK_EMPTY")
    verify_files(root,m["model_files"])
    if not m.get("input_files"):
        raise ContractError("SHADOW_INPUT_LOCK_EMPTY")
    verify_files(root,m["input_files"])
    case=m.get("case")
    if not isinstance(case,dict) or set(case)!={"online_npz","evaluator_npz","expected_rows","metadata"}:
        raise ContractError("SHADOW_CASE_SPEC_MISSING")
    if case["metadata"].get("corpus")!="dynamic" or case["metadata"].get("case_id")!=m.get("case_id"):
        raise ContractError("SHADOW_CASE_ID_MISMATCH")
    if case["online_npz"] not in m["input_files"] or case["evaluator_npz"] not in m["input_files"]:
        raise ContractError("SHADOW_CASE_INPUT_UNLOCKED")
    if stage==STAGES[2] and not m.get("archived_context_verified"):
        raise ContractError("SHADOW_ONE_STEP_CONTEXT_NOT_REVIEWED")
    previous=m.get("previous",{})
    if set(previous)!=set(PREREQ[stage]):
        raise ContractError("SHADOW_PREVIOUS_GATES_INCOMPLETE")
    for predecessor in PREREQ[stage]:
        source=previous[predecessor]
        if set(source)!={"result_path","result_sha256","receipt_path","receipt_sha256",
                         "review_path","review_sha256"}:
            raise ContractError("SHADOW_PREVIOUS_PROVENANCE_INCOMPLETE")
        for kind in ("result","receipt","review"):
            rel=source[kind+"_path"]
            if m["input_files"].get(rel)!=source[kind+"_sha256"]:
                raise ContractError("SHADOW_PREVIOUS_NOT_SHA_LOCKED:"+kind)
        receipt=json.loads(rooted(root,source["receipt_path"]).read_text(encoding="utf8"))
        review=json.loads(rooted(root,source["review_path"]).read_text(encoding="utf8"))
        if (receipt.get("stage")!=predecessor or receipt.get("status")!="COMPLETE_TECHNICAL_ONLY"
                or receipt.get("identity_sha256")!=identity(m)
                or receipt.get("result_sha256")!=source["result_sha256"]):
            raise ContractError("SHADOW_PREVIOUS_RESULT_OR_IDENTITY_BAD")
        if (review.get("stage")!=predecessor or review.get("decision")!="ACCEPT_TO_NEXT_STAGE"
                or review.get("receipt_sha256")!=source["receipt_sha256"]
                or not review.get("reviewer") or not review.get("reviewed_at")):
            raise ContractError("SHADOW_PREVIOUS_REVIEW_NOT_ACCEPTED")
    return m,p


def authorize(manifest_path,approval_path,m):
    a=json.loads(Path(approval_path).read_text(encoding="utf8"))
    if (a.get("execute_shadow_science") is not True or
        a.get("stage")!=m["stage"] or a.get("case_id")!=m["case_id"] or
        a.get("manifest_sha256")!=sha256(Path(manifest_path)) or
        a.get("code_lock_sha256")!=digest(m["code_files"]) or
        not a.get("actor") or not a.get("issued_utc")):
        raise ContractError("SHADOW_EXPLICIT_STAGE_APPROVAL_MISSING")
    # A blanket E1/E2 science authorization cannot be silently inherited.
    if a.get("execute_science") or a.get("allowed_other_stages"):
        raise ContractError("SHADOW_APPROVAL_SCOPE_EXCEEDED")
    return a


def read_rows(relative):
    path=rooted(ROOT,relative)
    with gzip.open(path,"rt",encoding="utf8") as f:
        value=json.load(f)
    if not isinstance(value,list):
        raise ContractError("SHADOW_PRIOR_ROWS_NOT_LIST")
    return value


def gzip_result(path,rows):
    with path.open("xb") as handle:
        with gzip.GzipFile(filename="",mode="wb",fileobj=handle,mtime=0) as zipper:
            with io.TextIOWrapper(zipper,encoding="utf8",newline="") as f:
                json.dump(jsonable(rows),f,ensure_ascii=False,allow_nan=False,
                          separators=(",",":"))


def run(manifest_path,approval_path,out):
    m,policy=inspect_manifest(manifest_path)
    approve=authorize(manifest_path,approval_path,m)
    output=Path(out).resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ContractError("SHADOW_OUTPUT_MUST_BE_IN_REPO_FOR_AUDIT")
    output.mkdir(parents=True,exist_ok=False)
    receipt=dict(schema="FP_SC_VAB_SHADOW_RESULT_V1",stage=m["stage"],case_id=m["case_id"],
        status="RUNNING",identity_sha256=identity(m),
        identity_recipe="SHADOW_COMMON_LOCK_V2",
        common_locks=dict(code_files=m["code_files"], baseline_sources=m["baseline_sources"],
                          model_files=m["model_files"],
                          case_payloads={m["case"][key]:m["input_files"][m["case"][key]]
                              for key in ("online_npz","evaluator_npz")}),
        manifest_sha256=sha256(Path(manifest_path)),approval_sha256=sha256(Path(approval_path)),
        source_commit=m["source_commit"],candidate="VAB",provider_valid_count=0,
        production_fp_writes=0,EKF_closed_loop_calls=0,old_E1_02_calls=0,
        old_E2_calls=0,role="IMPLEMENTER_SELF_CHECK",
        independent_audit=False,utc_start=datetime.now(timezone.utc).isoformat())
    write_json(output/"RUN_RECEIPT.json",receipt)
    try:
        case=load_shadow_online_only(ROOT,m["case"],m["input_files"])
        stage=m["stage"]
        if stage==STAGES[0]:
            adapter=OriginalAdapter(ROOT,revision_evidence=RevisionEvidenceAdapter(
                arm="VAB",mode="TWO_PORT_UNION"))
            rows=shadow_select_case(case,adapter,policy)
        elif stage==STAGES[1]:
            prior_rows=read_rows(m["previous"][STAGES[0]]["result_path"])
            reference=load_shadow_reference_after_s1(ROOT,m["case"],m["input_files"],
                expected_t=case.t,expected_pose=case.pose_id)
            rows=compare_shadow_observations(case,prior_rows,reference)
        elif stage==STAGES[2]:
            prior_rows=read_rows(m["previous"][STAGES[0]]["result_path"])
            reviewed_s2=read_rows(m["previous"][STAGES[1]]["result_path"])
            receipt["s1_s2_row_identity"]=crosscheck_s1_s2_for_s3(case,prior_rows,reviewed_s2)
            adapter=OriginalAdapter(ROOT,revision_evidence=RevisionEvidenceAdapter(
                arm="VAB",mode="TWO_PORT_UNION"))
            rows=same_prior_shadow_one_step(case,prior_rows,adapter)
        else:
            raise ContractError("SHADOW_UNKNOWN_STAGE")
        gzip_result(output/"ROWS.json.gz",rows)
        # Ground truth is deliberately read ONLY after the numerical S3 state
        # outputs have been saved: it cannot influence the candidate/innovation.
        if stage==STAGES[2]:
            truth=load_shadow_truth_for_s3_only(ROOT,m["case"],m["input_files"],
                expected_t=case.t,expected_pose=case.pose_id)
            accuracy=posthoc_s3_one_step_errors(case,rows,truth)
            gzip_result(output/"POSTHOC_ONE_STEP_ACCURACY.json.gz",accuracy)
            receipt["posthoc_accuracy_sha256"]=sha256(output/"POSTHOC_ONE_STEP_ACCURACY.json.gz")
            receipt["posthoc_scope"]="FIXED_PRIOR_ONE_STEP_NOT_RECURSIVE"
        receipt.update(status="COMPLETE_TECHNICAL_ONLY",result_sha256=sha256(output/"ROWS.json.gz"),
            row_count=len(rows),utc_end=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        receipt.update(status="FAILED_PRESERVED",error=type(exc).__name__+":"+str(exc),
                       trace=traceback.format_exc())
        raise
    finally:
        write_json(output/"RUN_RECEIPT.json",receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("plan")
    check=sub.add_parser("preflight");check.add_argument("--manifest",required=True)
    action=sub.add_parser("run")
    action.add_argument("--manifest",required=True)
    action.add_argument("--approval",required=True)
    action.add_argument("--output",required=True)
    args=parser.parse_args()
    if args.command=="plan":
        print(json.dumps(plan(),ensure_ascii=False,indent=2));return
    if args.command=="preflight":
        m,p=inspect_manifest(args.manifest)
        print(json.dumps(dict(status="PASS_PREFLIGHT_NO_SCIENCE",stage=m["stage"],
            case_id=m["case_id"],policy_sha256=p.sha,source_commit=m["source_commit"],
            approval_not_inferred=True),ensure_ascii=False));return
    print(json.dumps(run(args.manifest,args.approval,args.output),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
