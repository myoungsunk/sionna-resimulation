#!/usr/bin/env python3
"""Stdlib-only source-bound gate before each stage including diagnostics."""
from __future__ import annotations
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs/G2G3_FULL_P0_P3"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    dest=OUT/("PRE_RUN_"+stage+".json")
    if dest.exists():raise FileExistsError("No audit overwrite "+stage)
    A=json.loads((ROOT/"APPROVAL.json").read_text())
    C=json.loads((ROOT/"CONTRACT.json").read_text())
    rec=dict(stage=stage,run_decision="HOLD",code_match=False,
      checkout_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
      review_commit=A["review_commit"],audit_policy=C["preaudit_policy"],
      source_sha256={},fixed_data_verified=False,
      findings=[],scientific_PASS=False)
    ret=2
    try:
        if A["decision"]!="GO_WITH_CLAIM_LIMITATION" or stage not in A["authorized_stages"]:
            raise RuntimeError("HARD_EXECUTION_BLOCK: approval absent")
        for name,gitsha in A["source_blobs"].items():
            p=REPO/name
            if not p.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: source not checked out "+name)
            actual=subprocess.check_output(["git","hash-object",str(p)],cwd=REPO,text=True).strip()
            if actual!=gitsha:raise RuntimeError("HARD_EXECUTION_BLOCK: source changed "+name)
            rec["source_sha256"][name]=sha(p)
        if stage in ("P1","P2","P3"):
            p=OUT/"P0_RESULT.json"
            if not p.is_file() or json.loads(p.read_text())["status"]!="PASS_SOURCE_AND_D0_G0_PARITY":
                raise RuntimeError("HARD_EXECUTION_BLOCK: frozen original H3 preflight missing")
            rec["fixed_data_verified"]=True
        if stage in ("P2","P3"):
            p=OUT/"P1_RESULT.json"
            if not p.is_file() or json.loads(p.read_text())["status"]!="PASS_R0_SOURCE_MODEL_AND_FACTOR":
                raise RuntimeError("HARD_EXECUTION_BLOCK: source observation and Range/S factor preflight missing")
        rec["run_decision"]="GO_WITH_CLAIM_LIMITATION";rec["code_match"]=True
        rec["findings"].append(dict(severity="CLAIM_BLOCK",
          scope="independently calibrated B2 for H3 observer and independent DR fault prior",
          decision="frozen R0 actual H3 numerical & performance exploratory, no new calibrated sensor claim"))
        ret=0
    except Exception as ex:
        rec["findings"].append(dict(severity="HARD_EXECUTION_BLOCK",
          scope=stage,decision="stop dependent stage",reason=str(ex)))
    dest.write_text(json.dumps(rec,ensure_ascii=False,indent=2,allow_nan=False))
    print("P0_P3_PRE_RUN",stage,rec["run_decision"],flush=True)
    return ret
if __name__=="__main__":
    raise SystemExit(audit(sys.argv[1]))
