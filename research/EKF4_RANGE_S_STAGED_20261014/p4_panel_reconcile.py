"""Audit-bound final interpretation, preserving old failures and new no-step cases.

This does NOT modify original R5 candidate solver. It must not convert a
zero-displacement original sample or representational cost ambiguity into
a newly accepted MAP update. There is no new inference in this run.
"""
import argparse,hashlib,json,os,zipfile,collections
from pathlib import Path
from datetime import datetime,timezone
from p4_panel_reconcile_audit import PANEL_SHA,THREE_SHA,ROOT,digest

def load_member(z,suffix):
 paths=[x for x in z.namelist() if x.endswith(suffix)]
 if len(paths)!=1:raise RuntimeError("EXPECTED_ONE_MEMBER:"+suffix)
 return json.loads(z.read(paths[0]))
def run(panel,three,audit,out):
 a=json.loads(Path(audit).read_text())
 if a["decision"]!="GO" or a["source_SHA"]!=os.environ.get("GITHUB_SHA"):
  raise RuntimeError("PREAUDIT_NOT_GO")
 for k,v in a["sources"].items():
  if digest(ROOT/k)!=v:raise RuntimeError("SOURCE_CHANGED_AFTER_AUDIT:"+k)
 if digest(panel)!=PANEL_SHA or digest(three)!=THREE_SHA:
  raise RuntimeError("IMMUTABLE_SOURCE_RECEIPT_CHANGED")
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 with zipfile.ZipFile(panel) as p,zipfile.ZipFile(three) as t:
  if p.testzip() or t.testzip():raise RuntimeError("ZIP_CRC_ERROR")
  full=load_member(p,"/r5_full_geometry/FULL_GEOMETRY_FINAL.json")
  phi=load_member(p,"/r5_phi/PHI_FINAL.json")
  src=load_member(p,"/r5_stratified/STRATIFIED_FINAL.json")
  rt=load_member(t,"/r5_three_result/ROUNDTRIP_FINAL.json")
  if not(full["reproduced"]==4124 and src["tested"]==185 and
         src["new_statuses"]["DIAGNOSTIC_ERROR"]==3 and
         rt["strict_violations"]==3 and len(phi["cases"])==2):
   raise RuntimeError("INPUT_POPULATION_MISMATCH")
  old_cases=[json.loads(p.read(path)) for path in p.namelist()
    if "/r5_stratified/CASE_" in path and path.endswith(".json")]
  if len(old_cases)!=185:raise RuntimeError("MISSING_CASE_RECORDS")
  rtby={(x["case"],x["channel"],x["k"],x["method"]):x for x in rt["cases"]}
  new=[];c=collections.Counter()
  all_sha=set();contract_errors=[]
  for r in old_cases:
   key=(r["case"],r["channel"],r["k"],r["method"])
   original_status=r["new_terminal_status"]
   strategy=r.get("strategy")
   result_status=original_status
   if original_status=="DIAGNOSTIC_ERROR":
    check=rtby.get(key)
    if not check or "STRICT_ORIGINAL_OBJECTIVE_NONINCREASING_VIOLATED" not in r["exception"]:
      contract_errors.append("ERROR_NOT_MATCHED:"+str(key));continue
    if not(check["candidate_strategy"]=="ORIGINAL_START"
            and check["reported_J_delta"]==0.
            and 0.<check["roundtrip_state_reconstructed_delta_J"]<
                 check["cost_uncertainty_32eps"]):
      contract_errors.append("UNRESOLVED_NON_ROUNDOFF_COST_VIOLATION:"+str(key))
      continue
    result_status="NO_STEP_ROUNDTRIP_NUMERICAL_INCONCLUSIVE"
   elif strategy=="ORIGINAL_START":
    if original_status!="NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED" or r.get("delta_J_vs_original_failed")!=0.:
      contract_errors.append("ORIGINAL_START_NOT_ZERO_COST:"+str(key));continue
    result_status="NO_STEP_ORIGINAL_FAILURE_RETAINED"
   elif original_status in ("NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED","NONSMMOOTH_LOCAL_UNVERIFIED"):
    if r.get("delta_J_vs_original_failed",1.)>0:
      contract_errors.append("TRUE_POSITIVE_COST_INCREASE:"+str(key));continue
   else:
    contract_errors.append("UNRECOGNIZED_STATUS:"+str(key));continue
   if r["source_sha256"] in all_sha:
    contract_errors.append("DUPLICATE_FIXTURE_SHA:"+str(key));continue
   all_sha.add(r["source_sha256"])
   c[result_status]+=1
   new.append({"case":r["case"],"channel":r["channel"],"k":r["k"],
      "method":r["method"],"original_frozen_failure":r["old_status"],
      "initial_extended_status":original_status,"candidate_strategy":strategy,
      "audited_interpretation_status":result_status,
      "source_failure_sha256":r["source_sha256"]})
  if len(new)!=185 or contract_errors:
   raise RuntimeError("RECONCILIATION_NOT_EXHAUSTIVE:"+repr(contract_errors[:20]))
  if not(c["NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED"]==170
         and c["NONSMMOOTH_LOCAL_UNVERIFIED"]==5
         and c["NO_STEP_ORIGINAL_FAILURE_RETAINED"]==7
         and c["NO_STEP_ROUNDTRIP_NUMERICAL_INCONCLUSIVE"]==3):
   raise RuntimeError("RECONCILED_STATUS_COUNTS_UNEXPECTED:"+repr(dict(c)))
  final={
    "schema":"R5_EXPANDED_185_CASES_AUDITED_INTERPRETATION_V1",
    "status":"RECONCILED_185_NO_UNACCOUNTED_CASES",
    "git_sha":os.environ["GITHUB_SHA"],
    "input_panel_sha256":PANEL_SHA,
    "input_three_case_sha256":THREE_SHA,
    "original_4124_failures_unchanged":True,
    "all_original_failure_statuses_reproduced":full["reproduced"]==4124,
    "total_original_4124":full["reproduced"],
    "near_grid_0p001deg_count":full["near_0p001"],
    "source_LoS_phi_cases":len(phi["cases"]),
    "panel_tested":185,
    "new_statuses":dict(c),
    "no_accepted_original_start_fallback":True,
    "no_accepted_strict_cost_increase":True,
    "internal_roundtrip_delta_Js":[x["roundtrip_state_reconstructed_delta_J"] for x in rt["cases"]],
    "cost_uncertainty_32eps":[x["cost_uncertainty_32eps"] for x in rt["cases"]],
    "limitations":["R5 Clarke hull based on finite sample, not stationarity proof",
                   "No posterior covariance validation",
                   "No Full RF yaw scan data",
                   "Panel stratified from failed population; cannot estimate global performance gain."],
    "scientific_PASS":False,
    "cases":new,
    "time_utc":datetime.now(timezone.utc).isoformat()}
 (out/"RECONCILED_FINAL.json").write_text(json.dumps(final,indent=2)+"\n")
 print("R5_RECONCILED_FINAL "+json.dumps({k:final[k] for k in
   ("status","total_original_4124","panel_tested","new_statuses",
    "no_accepted_strict_cost_increase","scientific_PASS")}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 for k in ("panel","three","audit","out"):p.add_argument("--"+k,required=True)
 a=p.parse_args();raise SystemExit(run(a.panel,a.three,a.audit,a.out))
