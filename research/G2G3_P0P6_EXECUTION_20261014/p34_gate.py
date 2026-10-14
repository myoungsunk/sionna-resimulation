#!/usr/bin/env python3
"""Pre-run binding of approved source files and immutable frozen H3 contracts."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
def sha(p):
 return hashlib.sha256(p.read_bytes()).hexdigest()
def main(stage,case):
 out=REPO/"outputs/g2g3_p34_audit"
 out.mkdir(parents=True,exist_ok=True)
 key=stage+("_"+case if case else "")
 path=out/(key+".json")
 if path.exists():raise FileExistsError(path)
 receipt=dict(stage=stage,case=case,execution_sha=subprocess.check_output(
   ["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),run_decision="HOLD",
   source_sha256={},frozen_sha256={},audited_code_matches_execution_sha=False,
   independent_reviewer=False,scientific_PASS=False,findings=[])
 try:
  approval_file=("APPROVAL_P3.json" if stage=="P3" else "APPROVAL_P4.json")
  a=json.loads((ROOT/approval_file).read_text())
  if a["decision"]!="GO_WITH_CLAIM_LIMITATION":
   raise RuntimeError("HARD_EXECUTION_BLOCK: stage not source approved")
  if stage=="P4" and case not in a["authorized_cases"]:
   raise RuntimeError("HARD_EXECUTION_BLOCK: case outside audit")
  for name,git_blob in a["source_blobs"].items():
   f=REPO/name
   if not f.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: missing reviewed source "+name)
   actual=subprocess.check_output(["git","hash-object",str(f)],text=True).strip()
   if actual!=git_blob:raise RuntimeError("HARD_EXECUTION_BLOCK: source Git blob drift "+name)
   receipt["source_sha256"][name]=sha(f)
  contract=json.loads((ROOT/"P34_CONTRACT.json").read_text())
  h3=REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics/h3_offline/results/H3_OFFLINE_20261014_01a1380d"
  for p in (REPO/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json",
            h3/"h3_offline.py",h3/"CONTRACT.json",
            REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics/E1_P3_FROZEN_LORO_20261012.json"):
   if not p.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: missing frozen model "+str(p))
   receipt["frozen_sha256"][str(p.relative_to(REPO))]=sha(p)
  # Early cross-contract contamination check
  from_model=json.loads((h3/"CONTRACT.json").read_text())
  if "FROZEN_R0_ZERO_MEAN" not in from_model["stage4_RF_models"]:
   raise RuntimeError("HARD_EXECUTION_BLOCK: frozen R0 contract changed")
  if not contract.get("prohibitions"):raise RuntimeError("HARD_EXECUTION_BLOCK: no claim gates")
  receipt["audited_code_matches_execution_sha"]=True
  receipt["run_decision"]="GO_WITH_CLAIM_LIMITATION"
  receipt["findings"].append(dict(severity="CLAIM_BLOCK",scope=stage,
     note="Independent signed RF probability and fault DR prior are not calibrated; this is original R0 physical data one-step evidence only."))
  rc=0
 except Exception as exc:
  receipt["findings"].append(dict(severity="HARD_EXECUTION_BLOCK",affected=key,reason=str(exc)))
  rc=2
 path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False))
 print("P34_AUDIT",key,receipt["run_decision"],flush=True)
 return rc
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("stage",choices=["P3","P4"])
 p.add_argument("--case",default="")
 a=p.parse_args()
 sys.exit(main(a.stage,a.case))
