#!/usr/bin/env python3
"""Stdlib-only source/content gate before EACH cloud experiment and diagnostic."""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OFF=REPO/"externalOffice"
OUT=REPO/"outputs"/"BC_CROSSSCENE"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/f"PRE_RUN_{stage}.json"
    if target.exists():raise RuntimeError("No audit receipt overwrite")
    approval=json.loads((ROOT/"APPROVAL.json").read_text())
    contract=json.loads((ROOT/"CONTRACT.json").read_text())
    record=dict(stage=stage,execution_sha=subprocess.check_output(
        ["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
        source_sha256={},external_sha256={},run_decision="HOLD",code_match=False,
        independent_reviewer=False,audit_method="assistant source-review + Git blob lock + actual cloud checkout parity",
        findings=[],scientific_PASS=False)
    try:
        if approval["run_authorization"]!="GO_WITH_CLAIM_LIMITATION" or stage not in approval["authorized_stages"]:
            raise RuntimeError("HARD_EXECUTION_BLOCK: audit authorization invalid")
        for key,expected in approval["approved_source_blobs"].items():
            p=REPO/key
            if not p.is_file():raise RuntimeError("HARD_EXECUTION_BLOCK: source file absent "+key)
            actual=subprocess.check_output(["git","hash-object",str(p)],cwd=REPO,text=True).strip()
            if actual!=expected:raise RuntimeError("HARD_EXECUTION_BLOCK: source changed "+key)
            record["source_sha256"][key]=sha(p)
        if stage in ("EXTRACT","B","C"):
            if not OFF.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: external office checkout missing")
            got=subprocess.check_output(["git","rev-parse","HEAD"],cwd=OFF,text=True).strip()
            if got!=contract["source_commit"]:
                raise RuntimeError("HARD_EXECUTION_BLOCK: external source commit mismatch")
            record["external_source_sha"]=got
            for p in [
                OFF/"results/OFFICE_RANGING_20261008/OFFICE_RANGING.json",
                OFF/"results/CORRIDOR_ANCHOR2_20261007/SHIFT_FIT_ANCHOR2.json",
                OFF/"results/CORRIDOR_ANCHOR2B_20261007/SHIFT_FIT_ANCHOR2B.json"
            ]:
                if not p.is_file():raise RuntimeError("HARD_EXECUTION_BLOCK: external scene metadata missing "+str(p))
                record["external_sha256"][str(p.relative_to(OFF))]=sha(p)
        if stage in ("B","C"):
            d=OUT/"H_EXTRACTION.json"
            if not d.exists() or not json.loads(d.read_text()).get("receiver_parity")=="PASS":
                raise RuntimeError("HARD_EXECUTION_BLOCK: prior office receiver parity not verified")
            record["receiver_source_sha256"]=sha(d)
        if stage=="C":
            b=OUT/"B_REPORT.json"
            if not b.exists() or json.loads(b.read_text()).get("numerical")!="PASS_INPUT_AND_NORMALIZED_DENSITY":
                raise RuntimeError("HARD_EXECUTION_BLOCK: no audited normalized B density")
            record["calibration_input_sha256"]=sha(b)
        record["code_match"]=True
        record["run_decision"]="GO_WITH_CLAIM_LIMITATION"
        record["findings"].append(dict(
            severity="CLAIM_BLOCK",scope="independent DR fault calibration + E1 model transfer + external probabilistic guarantees",
            decision="execute B/C numerical and descriptive diagnostics only"))
        result=0
    except Exception as exc:
        record["findings"].append(dict(severity="HARD_EXECUTION_BLOCK",
            scope=stage,decision="dependent stage blocked",reason=str(exc)))
        result=2
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False))
    print("BC_PRE_RUN_AUDIT",stage,record["run_decision"],flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("BOOTSTRAP","EXTRACT","B","C"))
    raise SystemExit(main(p.parse_args().stage))
