"""N4-C independent retrospective audit of actual archived Full and LoS 304 recursive arms.
Read-only, stdlib only. No experiment rerun, fitting, gate retuning or performance inference.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,os,subprocess,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
N4C_SHA="f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9"
CODE_BLOB="40c795fa8799c4090c0766ebdccf6e2be83df6a0"

def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()
def blob(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with open(p,"rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()
def save(path,obj):
 Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def preflight(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[]
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("ACTIONS_REQUIRED")
 rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if rev!=os.getenv("GITHUB_SHA"):errors.append("HEAD_MISMATCH")
 f=ROOT/"research/R5_N4C_20261015/n4c_joint_sr4.py"
 if not f.is_file() or blob(f)!=CODE_BLOB:errors.append("ORIGINAL_N4C_SOURCE_CHANGED")
 try:ast.parse((HERE/"n4c_review.py").read_text())
 except Exception as e:errors.append("SOURCE_SYNTAX:"+repr(e))
 wf=ROOT/".github/workflows/r5-n4c-verify-report.yml"
 if not wf.is_file():errors.append("WORKFLOW_NOT_FOUND")
 else:
  w=wf.read_text()
  if not(0<=w.find("n4c_review.py --phase pre")<w.find("n4c_review.py --phase run")
         and "if: always()" in w and "actions: read" in w):
   errors.append("WORKFLOW_FIRST_AUDIT_REQUIRED")
 receipt={"stage":"N4-C postrun audit","decision":"GO" if not errors else "HOLD",
   "source_commit":rev,"N4C_result_sha256":N4C_SHA,
   "errors":errors}
 save(out/"PRE_AUDIT.json",receipt)
 print("N4C_POST_PRE "+json.dumps(receipt),flush=True)
 return 0 if not errors else 2
def member(z,name):
 choices=[n for n in z.namelist() if n==name or n.endswith("/"+name)]
 if len(choices)!=1:raise RuntimeError("ZIP_MEMBER_COUNT_BAD:"+name)
 return choices[0]
def records(z,name):
 return list(csv.DictReader(io.StringIO(z.read(member(z,name)).decode("utf-8"))))
def asnum(row):
 for k in ("heading_rmse_deg","heading_nees","heading_95coverage","xy_rmse_m",
           "pose_nees","pose_95coverage","bias_rmse_dps","bias_95coverage"):
  row[k]=float(row[k])
 return row
def execute(out,auditfile,path):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 receipt=json.loads(Path(auditfile).read_text())
 if receipt["decision"]!="GO" or receipt["source_commit"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("POSTAUDIT_HOLD")
 if sha(path)!=N4C_SHA:raise RuntimeError("N4C_SOURCE_ARTIFACT_CHANGED")
 with zipfile.ZipFile(path) as z:
  if z.testzip():raise RuntimeError("N4C_ARCHIVE_CRC_FAIL")
  meta=json.loads(z.read(member(z,"N4C_FINAL.json")))
  if meta["status"]!="N4C_RECURSIVE_EXPLORATORY_COMPLETE" or meta["n_metric_rows"]!=304:
   raise RuntimeError("N4C_UNVERIFIED_OR_INCOMPLETE")
  rows=[asnum(r) for r in records(z,"N4C_RECURSIVE_ALL_METRICS.csv")]
  ref=[r for r in rows if r["policy"]=="BASE_R0" and r["gate_mode"]=="natural"]
  idx={(r["case"],r["channel"],r["bias"],r["method"],r["policy"],r["gate_mode"]):r for r in rows}
  if len(rows)!=len(idx):raise RuntimeError("DUPLICATE_METRIC_ARMS")
  full=[r for r in rows if r["channel"]=="full" and r["gate_mode"]=="natural"]
  powers=[r for r in full if r["policy"]=="POWER_JOINT"]
  comparisons=[]
  for p in powers:
   original=idx[(p["case"],"full",p["bias"],p["method"],"BASE_R0","natural")]
   comparisons.append({"case":p["case"],"bias":p["bias"],"method":p["method"],
    "rmse":p["heading_rmse_deg"],"base_rmse":original["heading_rmse_deg"],
    "bias_rmse":p["bias_rmse_dps"],"base_bias_rmse":original["bias_rmse_dps"],
    "xy_rmse":p["xy_rmse_m"],"base_xy_rmse":original["xy_rmse_m"],
    "pose_nees":p["pose_nees"],"base_pose_nees":original["pose_nees"],
    "coverage":p["pose_95coverage"],"base_coverage":original["pose_95coverage"],
    "all_four_nondegradation":
     p["heading_rmse_deg"]<=original["heading_rmse_deg"]+1e-9 and
     p["bias_rmse_dps"]<=original["bias_rmse_dps"]+1e-9 and
     p["pose_nees"]<=original["pose_nees"]+1e-9 and
     p["pose_95coverage"]>=original["pose_95coverage"]-1e-9})
  if len(powers)!=16 or not all(r["all_four_nondegradation"] for r in comparisons):
   raise RuntimeError("POWER_JOINT_RESULT_NOT_PAIRED")
  fixed=[]
  for row in rows:
   if row["channel"]!="full" or row["gate_mode"]!="common":continue
   paired=idx[(row["case"],"full",row["bias"],row["method"],row["policy"],"natural")]
   orig=idx[(row["case"],"full",row["bias"],row["method"],"BASE_R0","natural")]
   fixed.append({"case":row["case"],"bias":row["bias"],"method":row["method"],
    "policy":row["policy"],
    "mean_heading_change_common_vs_natural":row["heading_rmse_deg"]-paired["heading_rmse_deg"],
    "pose_nees_common":row["pose_nees"],"pose_nees_natural":paired["pose_nees"],
    "gate_accepted_common":int(row["rf_applied"]),"gate_accepted_natural":int(paired["rf_applied"]),
    "gate_accepted_R0":int(orig["rf_applied"])})
  los=[r for r in rows if r["channel"]=="los" and r["gate_mode"]=="natural"]
  matched=[]
  for row in los:
   if row["policy"]=="BASE_R0":continue
   orig=idx[(row["case"],"los",row["bias"],row["method"],"BASE_R0","natural")]
   matched.append({"case":row["case"],"bias":row["bias"],"method":row["method"],
    "policy":row["policy"],
    "heading_rmse_change":row["heading_rmse_deg"]-orig["heading_rmse_deg"],
    "pose_nees_change":row["pose_nees"]-orig["pose_nees"]})
  output={"status":"N4C_INDEPENDENT_OUTPUT_AUDIT_PASS",
   "source_archive_sha256":N4C_SHA,"n_metrics":len(rows),
   "model_power_condition":comparisons,"common_gate_controls":fixed,
   "Full_to_LoS_global_calibration_transfer":matched,
   "power_all_condition_math_criteria_met":True,
   "power_scientific_posterior_calibration_PASS":False,
   "scope_warnings":[
     "POWER_JOINT uses first-path power from same RF packet to predict sensor error; normalized Bayesian observation likelihood unverified",
     "All 16 policy comparisons are one corridor and one motion noise seed per level",
     "Only global calibration transfer was tested on LoS. Power/G4/Simple/5 actual LoS predictors were not evaluated",
     "Pass of mean NEES reduction does not imply nominal chi-square mean NEES 3 or 95% covariance coverage",
     "Common mask comparison is counterfactual and can differ from online-available gate policy"],
   "scientific_PASS":False}
 save(out/"N4C_INDEPENDENT_REVIEW.json",output)
 for filename,table in (("N4C_POWER_JOINT.csv",comparisons),
                         ("N4C_FIXED_GATE_ABLATION.csv",fixed),
                         ("N4C_LOS_GLOBAL_TRANSFER.csv",matched)):
  with (out/filename).open("w",newline="",encoding="utf-8") as f:
   w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
 print("N4C_POST_FINAL "+json.dumps({"status":output["status"],
   "power":comparisons,
   "common_gate_L2":[r for r in fixed if r["bias"]=="L2"],
   "los_transfer_L2":[r for r in matched if r["bias"]=="L2"]}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=("pre","run"))
 p.add_argument("--out",required=True);p.add_argument("--audit");p.add_argument("--input")
 a=p.parse_args()
 raise SystemExit(preflight(a.out) if a.phase=="pre" else execute(a.out,a.audit,a.input))
