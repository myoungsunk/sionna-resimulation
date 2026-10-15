"""R5-2 source-backed, read-only physical feature analysis; no RF/heading model is changed.
Ground truth / oracle outcomes are used only AFTER feature table import for offline scoring.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,json,math,os,subprocess
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
SRC=REPO/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
DIR=REPO/"research/R5_FULLRF_HEADING_20261015"
FEATURE=SRC/"OUTPUT/01_FEATURES.csv"
LABEL=SRC/"OUTPUT/02_LABELS_EVAL_ONLY.csv"
METADATA=SRC/"OUTPUT/FEATURE_STATUS.json"
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def audit(out):
 out.mkdir(parents=True,exist_ok=False)
 errs=[]
 if os.getenv("GITHUB_ACTIONS")!="true":errs.append("GITHUB_CLOUD_REQUIRED")
 try:
  got=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
  if got!=os.getenv("GITHUB_SHA"):errs.append("HEAD_SHA_MISMATCH")
 except Exception as e:errs.append("HEAD_ERROR:"+str(e))
 for filename in ["r5_passive_features.py"]:
  try:ast.parse((DIR/filename).read_text())
  except Exception as e:errs.append("SCRIPT_SYNTAX:"+repr(e))
 m=json.loads(METADATA.read_text()) if METADATA.is_file() else {}
 if m.get("rows")!=9519 or m.get("state")!="completed":errs.append("FEATURE_STATUS_INVALID")
 sources={}
 for p in (FEATURE,LABEL):
  if not p.is_file():errs.append("SOURCE_MISSING:"+str(p))
  else:
   sources[p.name]={"sha256":sha(p),"size":p.stat().st_size}
   if p.stat().st_size<100000:errs.append("SOURCE_NOT_FULL_BYTES:"+p.name)
 if not errs:
  with FEATURE.open() as f:feature_head=next(csv.reader(f))
  with LABEL.open() as f:label_head=next(csv.reader(f))
  required_f={"case","route","pose_id","s","power1","power2","D1_mean_ns","D2_rx1","D2_rx2","P1_jsd","P4_shape_L1","P5_log_power"}
  required_y={"case","route","pose_id","e_MP","e_s","e_range","true_yaw_deg","s_lut_truth"}
  if not required_f.issubset(feature_head):errs.append("FEATURE_COLUMNS_MISSING:"+str(required_f-set(feature_head)))
  if not required_y.issubset(label_head):errs.append("ORACLE_LABEL_FIELDS_MISSING:"+str(required_y-set(label_head)))
 w=REPO/".github/workflows/r5-passive-feature-audit.yml"
 if not w.is_file():errs.append("WORKFLOW_MISSING")
 else:
  s=w.read_text()
  if not("r5_passive_features.py --phase pre" in s and
          s.index("r5_passive_features.py --phase pre")<s.index("r5_passive_features.py --phase run") and
          "if: always()" in s):errs.append("AUDIT_FIRST_WORKFLOW_FAIL")
 result={"phase":"R5_2_PRE_AUDIT","decision":"GO" if not errs else "HOLD",
         "git_sha":os.getenv("GITHUB_SHA"),"input_sources":sources,
         "feature_status":m,"errors":errs,"scientific_PASS":False}
 write(out/"PRE_AUDIT.json",result)
 print("R5_2_AUDIT "+json.dumps({"decision":result["decision"],"errors":errs}),flush=True)
 return 0 if not errs else 2
def run(out,auditfile):
 import numpy as np
 import pandas as pd
 out.mkdir(parents=True,exist_ok=False)
 audit_record=json.loads(Path(auditfile).read_text())
 if audit_record.get("decision")!="GO" or audit_record.get("git_sha")!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("R5_2_PREAUDIT_NOT_GO")
 for name,meta in audit_record["input_sources"].items():
  p=SRC/"OUTPUT"/name
  if sha(p)!=meta["sha256"]:raise RuntimeError("R5_2_INPUT_CHANGED:"+name)
 feat=pd.read_csv(FEATURE)
 labels=pd.read_csv(LABEL)
 if len(feat)!=9519 or len(labels)!=9519:
  raise RuntimeError("R5_2_FEATURE_LABEL_ROW_COUNT")
 key=["case","route","pose_id"]
 if feat.duplicated(key).any() or labels.duplicated(key).any():
  raise RuntimeError("DUPLICATE_JOIN_ID")
 rows=feat.merge(labels,on=key,validate="one_to_one",sort=False)
 if len(rows)!=9519:raise RuntimeError("PAIRED_ROW_MISMATCH")
 # This is an oracle outcome e_MP, not a deployable online predictor.
 y=rows["e_MP"].to_numpy(dtype=float)
 if not np.isfinite(y).all():raise RuntimeError("NONFINITE_E_MP")
 bad=np.abs(y)>.1
 features=["s","power1","power2","P5_log_power","D1_mean_ns","D1_diff_ns",
           "D2_rx1","D2_rx2","P1_jsd","P2_peak_difference_ns","P3_early_asymmetry","P4_shape_L1"]
 metrics=[]
 for col in features:
  if col not in rows:continue
  vals=pd.to_numeric(rows[col],errors="coerce").to_numpy(float)
  valid=np.isfinite(vals)
  if valid.sum()<100:continue
  spearman=float(pd.Series(vals[valid]).corr(pd.Series(np.abs(y[valid])),method="spearman"))
  pearson=float(np.corrcoef(vals[valid],np.abs(y[valid]))[0,1]) if np.std(vals[valid])>1e-14 else None
  metrics.append({"feature":col,"n":int(valid.sum()),
    "pearson_abs_e_MP":pearson,"spearman_abs_e_MP":spearman,
    "feature_mean":float(np.mean(vals[valid])),"feature_std":float(np.std(vals[valid]))})
 summaries=[]
 for route,block in rows.groupby("route",sort=True):
  val=block["e_MP"].to_numpy(float)
  summaries.append({"route":route,"rows":len(block),"mp_bias":float(np.mean(val)),
    "mp_rmse":float(np.sqrt(np.mean(val*val))),
    "mp_abs_gt_0p1_rate":float(np.mean(np.abs(val)>.1)),
    "distinct_case_station":int(block[["case","station_group"]].drop_duplicates().shape[0])})
 # Mathematically verify first-path s definition but never treat raw power ratio as extra independent RF information.
 expected=(rows["power1"].to_numpy(float)-rows["power2"].to_numpy(float))/np.maximum(
   rows["power1"].to_numpy(float)+rows["power2"].to_numpy(float),1e-300)
 deviation=np.abs(expected-rows["s"].to_numpy(float))
 if not np.isfinite(deviation).all():raise RuntimeError("INVALID_POWER_RATIO")
 maxdev=float(np.max(deviation))
 if maxdev>1e-6:raise RuntimeError("S_POWER_IDENTITY_FAIL:"+str(maxdev))
 def export(p,records):
  with p.open("w",newline="",encoding="utf-8") as f:
   w=csv.DictWriter(f,fieldnames=list(records[0]))
   w.writeheader();w.writerows(records)
 export(out/"R5_2_FEATURE_CORRELATIONS.csv",metrics)
 export(out/"R5_2_ROUTE_SUMMARY.csv",summaries)
 result={"stage":"R5_2","status":"OFFLINE_FEATURE_AUDIT_COMPLETED",
    "rows":len(rows),"routes":sorted(rows.route.unique().tolist()),
    "unique_cases":int(rows.case.nunique()),
    "distinct_case_station_groups":int(rows[["case","station_group"]].drop_duplicates().shape[0]),
    "multipath_proxy":"abs(s_full - s_direct_native_LoS)>0.1",
    "multipath_proxy_positive_fraction":float(bad.mean()),
    "power_ratio_max_abs_difference":maxdev,
    "feature_correlations":metrics,"route_summaries":summaries,
    "dependency":"archived 2026-10-10 Full/LoS amplitude-derived features only",
    "not_established":["heading_error_predictive_quality","heldout_scene_generalization",
       "calibrated_R_s(q)","actual_extra_angle_Full_joint_EKF",
       "hardware_CIR_availability"],
    "scientific_PASS":False}
 write(out/"R5_2_FINAL.json",result)
 print("R5_2_FINAL "+json.dumps({"status":result["status"],
   "rows":result["rows"],"routes":result["routes"],
   "cases":result["unique_cases"],"stations":result["distinct_case_station_groups"],
   "mp_proxy_rate":result["multipath_proxy_positive_fraction"],
   "max_s_power_diff":maxdev,"correlations":metrics}),flush=True)
 return 0
if __name__=="__main__":
 a=argparse.ArgumentParser()
 a.add_argument("--phase",choices=["pre","run"],required=True)
 a.add_argument("--out",required=True)
 a.add_argument("--audit")
 b=a.parse_args()
 raise SystemExit(audit(Path(b.out)) if b.phase=="pre" else run(Path(b.out),b.audit))
