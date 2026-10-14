"""Audited source-bound cloud execution gate.

Run once BEFORE each scientific computation or diagnostic. Does not silently
convert failures of data/formula parity into PASS. Not a scientific claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs/g2g3_bf"


def main(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/("PRE_RUN_"+stage+".json")
    if target.exists():raise FileExistsError("Audit must not overwrite receipt")
    receipt=dict(audit_id="G2G3_BF_PRE_RUN_20261014/"+stage,
      source_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
      action="May exact frozen code and input safely perform this stage?",
      stage=stage,run_decision="HOLD",
      audited_code_matches_execution_sha=False,
      reviewer="assistant source review; no independent external human reviewer",
      source_sha256={},findings=[],scientific_PASS=False,
      scientific_claim="NOT_YET_EVALUATED")
    try:
        approval=json.loads((ROOT/"APPROVAL.json").read_text())
        contract=json.loads((ROOT/"CONTRACT.json").read_text())
        if stage not in ("environment","B","C","D","E0","F"):
            raise RuntimeError("Not approved stage")
        if approval["review_decision"]!="GO_WITH_CLAIM_LIMITATION":
            raise RuntimeError("HARD_EXECUTION_BLOCK: source review not approved")
        if approval["schema"]!="G2G3_BF_APPROVAL_V1" or contract["schema"]!="G2G3_BF_STAGED_AMENDMENT_20261014_01":
            raise RuntimeError("HARD_EXECUTION_BLOCK: unexpected contract/approval")
        if stage not in approval["authorized_stages"]:
            raise RuntimeError("HARD_EXECUTION_BLOCK: stage outside approval")
        for rel,git_blob in approval["source_git_blobs"].items():
            p=REPO/rel
            if not p.is_file():raise FileNotFoundError("HARD_EXECUTION_BLOCK: missing "+rel)
            observed=subprocess.check_output(["git","hash-object",str(p)],cwd=REPO,text=True).strip()
            if observed!=git_blob:
                raise RuntimeError("HARD_EXECUTION_BLOCK: source bytes differ from reviewed "+rel)
            receipt["source_sha256"][rel]=hashlib.sha256(p.read_bytes()).hexdigest()
        if stage in ("B","E0"):
            path=REPO/"inputs/range_audit/ACQUISITION.json"
            if not path.is_file():raise FileNotFoundError("HARD_EXECUTION_BLOCK: source artifact not acquired")
            acquired=json.loads(path.read_text())
            if acquired["zip_sha256"]!=contract["source_artifact"]["sha256"]:
                raise RuntimeError("HARD_EXECUTION_BLOCK: artifact SHA drift")
            for name,sha in acquired["file_sha256"].items():
                if hashlib.sha256((path.parent/name).read_bytes()).hexdigest()!=sha:
                    raise RuntimeError("HARD_EXECUTION_BLOCK: input bytes drift "+name)
            receipt["input_sha256"]=acquired["file_sha256"]
        if stage=="E0":
            for name in ("B_RESULT.json","C_RESULT.json"):
                if not (OUT/name).exists():raise RuntimeError("E0 requires "+name)
        if stage=="F":
            for name in ("B_RESULT.json","C_RESULT.json","D_RESULT.json","E0_RESULT.json"):
                if not (OUT/name).exists():raise RuntimeError("F missing dependent status "+name)
        receipt["audited_code_matches_execution_sha"]=True
        receipt["run_decision"]="GO_WITH_CLAIM_LIMITATION"
        receipt["scientific_claim"]="CLAIM_BLOCK_FULL_3STATE_AND_INDEPENDENT_CALIBRATION"
        receipt["findings"]=[
            dict(severity="CLAIM_BLOCK",scope="B calibrated model",
                 reason="R2/R5 independent spatial buffer zero; route-only fold overlap"),
            dict(severity="CASE_RESULT_INVALID",scope="D original G3 failed cell",
                 reason="Original GH TV 0.387>0.001; changed integration must pass independently"),
            dict(severity="DIAGNOSTIC_DEFECT_OR_WARNING",scope="optional metadata only",
                 reason="Cannot widen failure scope without checking scientific data")]
        status=0
    except Exception as exc:
        receipt["findings"].append(dict(
            severity="HARD_EXECUTION_BLOCK",scope=stage,reason=str(exc)))
        status=2
    target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False))
    print("PRE_RUN_AUDIT",stage,receipt["run_decision"],receipt["source_commit"],
          [v["severity"] for v in receipt["findings"]],flush=True)
    return status


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage")
    raise SystemExit(main(p.parse_args().stage))
