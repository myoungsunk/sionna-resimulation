"""N0 immutable reconciliation of R2, B0 Hard/Soft and PHYSICS_RS sources.

This is an audit, not a re-fit. Only standard library used. Original
RF/estimator outputs are never edited. A historical sub-1e-9 failure
must be recorded and never silently promoted to exact numerical parity.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,os,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
B0_SHA="f31a04cf2ba39011a5d685b13985b947b1659e5b63c3a5910ec68175fa7e806a"
ORIG_RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
PINNED={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/PHYSICS_RS_STAGED_20261015/code/features.py":"c556da153739aaf99d2558c84c1a515c3da41a97",
 "research/PHYSICS_RS_STAGED_20261015/code/stage_b.py":"b56d9e1459f2265fea83cd87cb411cd1cc4f3f9d",
 "research/PHYSICS_RS_STAGED_20261015/code/stage_c.py":"1a215ef1ab0f2f56cc60960742545be6873c7eb0",
 "research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py":"24b7b0103a232662afaf5b1b79bfb542aa7123db",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
}
def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob_sha(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];got={}
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("GITHUB_ACTIONS_REQUIRED")
 try:
  head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
  if head!=os.getenv("GITHUB_SHA"):errors.append("NOT_EXACT_HEAD")
 except Exception as e:head=None;errors.append("HEAD_ERROR:"+str(e))
 for name,expect in PINNED.items():
  f=ROOT/name
  if not f.is_file():errors.append("FROZEN_NOT_FOUND:"+name)
  else:
   h=blob_sha(f);got[name]=h
   if h!=expect:errors.append("FROZEN_CHANGED:"+name)
 try:
  ast.parse((HERE/"n0_reconcile.py").read_text(),filename="n0_reconcile.py")
 except Exception as e:errors.append("SELF_AST_INVALID:"+repr(e))
 wf=ROOT/".github/workflows/r5-n0n3-n0.yml"
 if not wf.is_file():errors.append("WORKFLOW_NOT_FOUND")
 else:
  w=wf.read_text()
  for token in ("n0_reconcile.py --phase pre","n0_reconcile.py --phase run","actions: read","if: always()"):
   if token not in w:errors.append("WF_CONTRACT_MISSING:"+token)
  if w.find("n0_reconcile.py --phase pre")>w.find("n0_reconcile.py --phase run"):
   errors.append("PRE_NOT_FIRST")
 doc={"stage":"N0","decision":"GO" if not errors else "HOLD",
      "source_head":head,"frozen_source_git_blobs":got,
      "source_original_rf_sha":ORIG_RF_SHA,"source_r2_sha":R2_SHA,
      "source_b0_sha":B0_SHA,"errors":errors,"scientific_PASS":False}
 save(out/"N0_PRE_AUDIT.json",doc)
 print("N0_PRE "+json.dumps({"decision":doc["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2
def member(z,name):
 a=[k for k in z.namelist() if k==name or k.endswith("/"+name)]
 if len(a)!=1:raise RuntimeError("NONUNIQUE_ZIP_MEMBER:"+name+"="+str(len(a)))
 return a[0]
def parse_csv(z,name):
 return list(csv.DictReader(io.StringIO(z.read(member(z,name)).decode("utf-8"))))
def verifiedzip(path,expect):
 actual=sha256(path)
 if actual!=expect:raise RuntimeError("ARTIFACT_SHA_MISMATCH:"+str(path)+":"+actual)
 z=zipfile.ZipFile(path)
 broken=z.testzip()
 if broken:raise RuntimeError("ZIP_CRC_ERROR:"+broken)
 return z
def run(out,pre,r2path,b0path,rfpath):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 audit_result=json.loads(Path(pre).read_text())
 if audit_result.get("decision")!="GO" or audit_result["source_head"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("AUDIT_HOLD")
 with verifiedzip(r2path,R2_SHA) as z2,verifiedzip(b0path,B0_SHA) as z0,verifiedzip(rfpath,ORIG_RF_SHA) as zrf:
  baseline=parse_csv(z2,"R2_BIAS_METRICS.csv")
  updated=parse_csv(z0,"R5_B0_HARD_SOFT_METRICS.csv")
  parity=parse_csv(z0,"R5_B0_ORIGINAL_PARITY.csv")
  n0result=json.loads(z0.read(member(z0,"R5_B0_FINAL.json")))
  rf_summary=json.loads(zrf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  if len(baseline)!=256 or len(updated)!=60 or len(parity)!=4 or len(rf_summary["per_case"])!=14:
   raise RuntimeError("WRONG_RECORD_COUNTS")
  if not set(r["level"] for r in baseline)=={"B0","L0","L1","L2"}:
   raise RuntimeError("DRIFT_LEVEL_SET_CHANGED")
  source_ref={(x["case"],x["rf_channel"],x["level"],x["method"],x["evaluation_mode"]):x for x in baseline}
  comparisons=[];outlier=[]
  for x in updated:
   if x["method"] not in ("DR4","R0_J4"):continue
   mm="DR4" if x["method"]=="DR4" else "J4"
   key=(x["case"],x["channel"],"B0",mm,"recursive")
   ref=source_ref[key]
   if int(x["frames"])!=829 or int(ref["frames_valid"])!=829:
    raise RuntimeError("EVAL_FRAME_DIFFERENCE:"+str(key))
   deltas={}
   for field1,field2 in [("heading_rmse_deg","heading_rmse_deg"),
                         ("heading_nees_mean","heading_nees_mean"),
                         ("heading95_coverage","heading95_coverage"),
                         ("position_rmse_m","pose_rmse_m"),
                         ("pose_nees_mean","pose_nees_mean")]:
    u=float(x[field1]);v=float(ref[field2])
    d=abs(u-v);deltas[field1]=d
    if d>max(1e-5,1e-7*abs(v)):outlier.append({"condition":key,"field":field1,"delta":d})
   comparisons.append({"case":x["case"],"channel":x["channel"],"model":mm,"condition":"B0",
     "n_frames":829,"metrics_max_abs_delta":max(deltas.values()),**{"d_"+k:v for k,v in deltas.items()}})
  if len(comparisons)!=8:raise RuntimeError("BASELINE_PAIR_COUNT")
  original_known=max(float(x["R0_state_max_diff"]) for x in parity)
  strict_failed=[x for x in parity if str(x["strict_1e9_parity"]).lower() not in ("true","1")]
  if len(strict_failed)!=1 or original_known<1e-9:
   raise RuntimeError("HISTORIC_NUMERIC_EXCEPTION_NOT_PRESERVED")
  risk=n0result["model_split"]
  if risk["train_routes"]!=["R4","R5"] or risk["heldout_route"]!="R2":
   raise RuntimeError("LEAKED_MODEL_HOLDOUT")
  errors=outlier
  known_pose_nees_exception=(
    len(errors)==1 and errors[0]["condition"]==
    ("R2_aA_m0","full","B0","J4","recursive") and
    errors[0]["field"]=="pose_nees_mean" and errors[0]["delta"]<0.01)
  # Deliberately DO NOT relax the original numerical parity test.
  # Only allow scoped scientific comparisons while retaining the failed test.
  status=("N0_SCOPED_GO_POSE_NEES_NOT_NUMERICALLY_IDENTICAL" if known_pose_nees_exception
          else "N0_COMPARABLE_WITH_DOCUMENTED_NUMERIC_NONPARITY" if not errors
          else "N0_MISMATCH_HOLD")
  doc={"stage":"N0","status":status,
   "archive_sha256":{"rf":ORIG_RF_SHA,"r2":R2_SHA,"b0":B0_SHA},
   "frozen_LUT_identical":True,"observation_order":"[range_raw_m,s]",
   "Rr_m2":.0068578637,"Rs":.0081,"Rrs":0,
   "gyro_true_levels_dps":{"B0":0,"L0":.01,"L1":.05,"L2":.2},
   "bias_prior_std_dps":.1,"bias_random_walk":0.,
   "original_R2_seed":0,"validation_window":"t>=30s","R2_n_frame_per_case":829,
   "train_test_split":risk,"baseline_method_names":["DR4","S4","J4","SR4"],
   "old_B0_parity_strict_failed":strict_failed,
   "old_B0_R0_max_archive_state_difference":original_known,
   "old_B0_R0_gate_difference":sum(int(x["gate_differences"]) for x in parity),
   "record_counts":{"R2_metric_rows":len(baseline),"B0_metric_rows":len(updated),
                    "original_RF_traces":len(rf_summary["per_case"]),"comparable_rows":len(comparisons)},
   "comparison_errors":errors,"historical_pose_nees_strict_parity_PASS":not bool(errors),
   "documented_exception_not_promoted_to_PARITY_PASS":known_pose_nees_exception,
   "limitations":[
     "Source physics G0-G5 Rs-only results in separate published report, not original R2 baseline",
     "The old B0 Full mount0 code has documented sub-1e-7 trajectory drift from archived binary; strict exact parity false",
     "Single RF corridor, one gyro noise seed; no independent environment",
     "B0 not the efficacy condition for unknown gyro bias",
     "The B0 hard/soft reported 0.5/0.75 is classifier score threshold, not 84% accurate classifier"],
   "scientific_PASS":False}
  save(out/"N0_RECONCILIATION.json",doc)
  with (out/"N0_BASELINE_COMPARISON.csv").open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons)
  print("N0_FINAL "+json.dumps({"status":status,
      "max_comparison_metric_delta":max(x["metrics_max_abs_delta"] for x in comparisons),
      "strict_historic_parity_failed":len(strict_failed),
      "outliers":errors,"counts":doc["record_counts"]}),flush=True)
  return 0 if status!="N0_MISMATCH_HOLD" else 3
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=["pre","run"],required=True)
 p.add_argument("--out",required=True)
 p.add_argument("--audit");p.add_argument("--r2");p.add_argument("--b0");p.add_argument("--raw")
 a=p.parse_args()
 raise SystemExit(audit(a.out) if a.phase=="pre" else run(a.out,a.audit,a.r2,a.b0,a.raw))
