#!/usr/bin/env python3
"""Strict stdlib-only source/inputs gate for each B2, C2, D0 run."""
from __future__ import annotations
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs/B2_PHYSICS_Q"
PRE=REPO/"outputs/BC_CROSSSCENE"

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    dest=OUT/f"PRE_RUN_{stage}.json"
    if dest.exists():raise FileExistsError("Cannot replace audit receipt "+str(dest))
    a=json.loads((ROOT/"APPROVAL.json").read_text())
    C=json.loads((ROOT/"CONTRACT.json").read_text())
    record=dict(stage=stage,source_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
      original_audit_policy="9beb061f354edef18e1f977f5d462d7e0d8b1f2e",
      audited_code_matches_execution_sha=False,source_sha256={},inputs_sha256={},
      run_decision="HOLD",scientific_claim="CLAIM_BLOCK_SOURCE_CALIBRATION",independent_human_reviewer=False,findings=[])
    ret=2
    try:
        if a["decision"]!="GO_WITH_CLAIM_LIMITATION" or stage not in a["authorized_stages"]:
            raise RuntimeError("HARD_EXECUTION_BLOCK: no source review or unauthorized scope")
        for name,expected in a["approved_git_blobs"].items():
            source=REPO/name
            if not source.is_file():raise RuntimeError("HARD_EXECUTION_BLOCK: source absent "+name)
            found=subprocess.check_output(["git","hash-object",str(source)],cwd=REPO,text=True).strip()
            if found!=expected:raise RuntimeError("HARD_EXECUTION_BLOCK: source hash changed "+name)
            record["source_sha256"][name]=digest(source)
        if stage in ("B2","C2","D0"):
            p=PRE/"INDEPENDENT_SCENE_RF_POSITIONS.csv"
            o=PRE/"H_EXTRACTION.json"
            if not p.is_file() or not o.is_file() or json.loads(o.read_text())["receiver_parity"]!="PASS":
                raise RuntimeError("HARD_EXECUTION_BLOCK: Office/A2/A2B source not verified")
            for x in (p,o):record["inputs_sha256"][str(x.relative_to(REPO))]=digest(x)
        if stage in ("C2","D0"):
            b=OUT/"B2_REPORT.json"
            if not b.is_file() or json.loads(b.read_text())["calculation"]!="PASS_CONDITIONAL_NORMALIZED_DENSITY":
                raise RuntimeError("HARD_EXECUTION_BLOCK: unvalidated signed B2 density")
            record["inputs_sha256"][str(b.relative_to(REPO))]=digest(b)
        if stage=="D0":
            c=OUT/"C2_REPORT.json"
            if not c.is_file() or json.loads(c.read_text())["numerical"]!="PASS_INDEPENDENT_EVENT_INTEGRALS":
                raise RuntimeError("HARD_EXECUTION_BLOCK: C2 numerical verification not available")
            record["inputs_sha256"][str(c.relative_to(REPO))]=digest(c)
        record["audited_code_matches_execution_sha"]=True
        record["run_decision"]="GO_WITH_CLAIM_LIMITATION"
        record["findings"].append(dict(severity="CLAIM_BLOCK",
            scope="independent dynamic DR prior, more than two RF scene families, actual full pose G2/G3",
            decision="run only B2/C2/D0 calculation; no scientific calibration adoption"))
        ret=0
    except Exception as e:
        record["findings"].append(dict(severity="HARD_EXECUTION_BLOCK",scope=stage,reason=str(e),decision="BLOCK_DEPENDENT_STAGE"))
    dest.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False))
    print("B2_AUDIT",stage,record["run_decision"],flush=True)
    return ret

if __name__=="__main__":
    raise SystemExit(main(sys.argv[1]))
