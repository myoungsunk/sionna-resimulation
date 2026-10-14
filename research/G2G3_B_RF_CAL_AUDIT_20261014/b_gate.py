#!/usr/bin/env python3
"""Stdlib-only source-bound PRE-RUN audit, before B fixture, acquisition, or data scoring."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs"/"B_RF_SIGNED"
INPUT=REPO/"inputs"/"B_RF_SIGNED"

def audit(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    dest=OUT/("PRE_RUN_"+stage+".json")
    if dest.exists():raise FileExistsError("Cannot overwrite pre-run receipt")
    review=json.loads((ROOT/"APPROVAL.json").read_text())
    contract=json.loads((ROOT/"CONTRACT.json").read_text())
    receipt=dict(
        audit_id=review["audit_id"]+"/"+stage,
        intended_stage=stage,
        execution_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
        review_reference_commit=review["review_reference_commit"],
        audit_policy_commit=review["audit_policy_commit"],
        reviewer_external=False,
        audit_method="Source-level assistant review + cloud git blob compare + independent math check",
        source_sha256={},input_sha256={},run_decision="HOLD",
        audited_code_matches_execution_sha=False,
        claim_scope="Descriptive and heldout-route validation only; no calibrated posterior",findings=[]
    )
    status=2
    try:
        if review["review_decision"]!="GO_WITH_CLAIM_LIMITATION":
            raise RuntimeError("HARD_EXECUTION_BLOCK: approval not granted")
        if stage not in review["authorized_stages"]:
            raise RuntimeError("HARD_EXECUTION_BLOCK: stage outside approval")
        for path,expect in review["source_git_blobs"].items():
            src=REPO/path
            if not src.is_file():
                raise RuntimeError("HARD_EXECUTION_BLOCK: missing audited source "+path)
            got=subprocess.check_output(["git","hash-object",str(src)],cwd=REPO,text=True).strip()
            if got!=expect:
                raise RuntimeError("HARD_EXECUTION_BLOCK: Git blob differs "+path+" "+got)
            receipt["source_sha256"][path]=hashlib.sha256(src.read_bytes()).hexdigest()
        if stage=="evaluate":
            src=INPUT/"frozen_source.zip"
            if not src.is_file():
                raise RuntimeError("HARD_EXECUTION_BLOCK: missing frozen source zip")
            digest=hashlib.sha256(src.read_bytes()).hexdigest()
            if digest!=contract["source"]["zip_sha256"]:
                raise RuntimeError("HARD_EXECUTION_BLOCK: input zip checksum changed")
            receipt["input_sha256"][str(src.relative_to(REPO))]=digest
            f=OUT/"B_MATH_AUDIT.json"
            if not f.is_file() or json.loads(f.read_text())["status"]!="PASS":
                raise RuntimeError("HARD_EXECUTION_BLOCK: B math fixture not passed")
        receipt["audited_code_matches_execution_sha"]=True
        receipt["run_decision"]="GO_WITH_CLAIM_LIMITATION"
        receipt["findings"].append(dict(
            severity="CLAIM_BLOCK",
            affected="Independent RF/DR calibration and G2/G3 pose/generalization",
            decision="Continue numerical+descriptive B diagnostics; no scientific calibration claim."))
        status=0
    except Exception as e:
        receipt["findings"].append(dict(severity="HARD_EXECUTION_BLOCK",
            affected=stage,decision="Stop this dependent stage only",reason=str(e)))
    dest.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False))
    print("B_PRE_RUN",stage,receipt["run_decision"],receipt["findings"],flush=True)
    return status

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("stage",choices=["bootstrap","fixture","acquire","evaluate"])
    args=ap.parse_args()
    raise SystemExit(audit(args.stage))
