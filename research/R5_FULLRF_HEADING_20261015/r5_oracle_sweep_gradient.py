"""R5-4 initial oracle angular Full vs native-LoS sweep integrity/gradient study.
No new Full RF, no measured gyro yaw, no deployable Heading factor.
Raw inputs: original archived Full/LoS s and true yaw for offline geometry diagnostics.
"""
from __future__ import annotations
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/OUTPUT"
D=ROOT/"research/R5_FULLRF_HEADING_20261015"
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for v in iter(lambda:f.read(1<<20),b""):h.update(v)
 return h.hexdigest()
def write(p,d):
 Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def audit(out):
 out.mkdir(parents=True,exist_ok=False)
 err=[]
 if os.getenv("GITHUB_ACTIONS")!="true":err.append("GITHUB_REQUIRED")
 rev=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
 if rev!=os.getenv("GITHUB_SHA"):err.append("SHA_MISMATCH")
 files={}
 for fn in ("01_FEATURES.csv","02_LABELS_EVAL_ONLY.csv"):
  p=SRC/fn
  if not p.is_file() or p.stat().st_size<100000:err.append("SOURCE_FILE_INVALID:"+fn)
  else:files[fn]=sha(p)
 try:ast.parse((D/"r5_oracle_sweep_gradient.py").read_text())
 except Exception as ex:err.append("SOURCE_SYNTAX:"+str(ex))
 wf=(ROOT/".github/workflows/r5-oracle-sweep-gradient.yml")
 if not wf.exists():err.append("WORKFLOW_MISSING")
 else:
  w=wf.read_text()
  if not(w.find("r5_oracle_sweep_gradient.py --phase pre")>=0 and
         w.find("r5_oracle_sweep_gradient.py --phase pre")<w.find("r5_oracle_sweep_gradient.py --phase run")):
   err.append("AUDIT_NOT_FIRST")
 record={"schema":"R5_4_EXISTING_FULL_SWEEP_STATIC_AUDIT_V1",
  "decision":"GO" if not err else "HOLD","git_sha":rev,"sources":files,
  "scope":"offline true-yaw matched Full/direct-native-LoS s; no measured gyro, no LUT reverse inference",
  "errors":err,"scientific_PASS":False}
 write(out/"PRE_AUDIT.json",record)
 print("R5_4_PRE_AUDIT "+json.dumps({"decision":record["decision"],"errors":err}),flush=True)
 return 0 if not err else 2
def run(out,receipt_path):
 import numpy as np
 import pandas as pd
 from scipy.stats import ncx2,chi2
 out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(receipt_path).read_text())
 if a["decision"]!="GO" or a["git_sha"]!=os.getenv("GITHUB_SHA"):raise RuntimeError("AUDIT_NOT_GO")
 for fn,s in a["sources"].items():
  if sha(SRC/fn)!=s:raise RuntimeError("SOURCE_CHANGED:"+fn)
 x=pd.read_csv(SRC/"01_FEATURES.csv")
 y=pd.read_csv(SRC/"02_LABELS_EVAL_ONLY.csv")
 k=["case","route","pose_id"]
 if x.duplicated(k).any() or y.duplicated(k).any():raise RuntimeError("DUPLICATED_JOINS")
 d=x.merge(y,on=k,validate="one_to_one")
 if len(d)!=9519:raise RuntimeError("INCOMPLETE_SOURCE")
 sigma2=.0081
 rows=[]
 for (case,site),g in d.groupby(["case","station_group"],sort=True):
  if len(g)<11:continue
  # Compare full/direct-native-LoS at identical stored yaw, not to precomputed LUT.
  # Geometry uses offline true yaw for angle matching, never for a production estimator.
  g=g.sort_values("true_yaw_deg",kind="stable")
  full=g["s"].to_numpy(float)
  los=g["s_los"].to_numpy(float)
  delta=full-los
  yaw=g["true_yaw_deg"].to_numpy(float)
  if not(np.isfinite(full).all() and np.isfinite(los).all() and np.isfinite(yaw).all()):
   continue
  if np.max(np.abs(np.diff(yaw)))>60:
   # Sorting/wrap ambiguities: record nonvalid rather than assert a physical scan.
   continue
  n=len(g)
  D=np.diff(np.eye(n),axis=0)
  C=sigma2*(D@D.T)
  if np.min(np.linalg.eigvalsh(C))<=0:raise RuntimeError("DIFF_C_NOT_PD")
  diff=D@delta
  noncentrality=float(diff@np.linalg.solve(C,diff))
  chance=float(ncx2.sf(chi2.ppf(.95,n-1),n-1,noncentrality))
  # model mismatch mean and gradient are orthogonal diagnostics.
  rows.append({"case":case,"station_group":site,"route":str(g.route.iloc[0]),
       "n":n,"yaw_min_deg":float(yaw.min()),"yaw_max_deg":float(yaw.max()),
       "s_full_span":float(np.ptp(full)),"s_los_span":float(np.ptp(los)),
       "mp_mean":float(np.mean(delta)),"mp_rms":float(np.sqrt(np.mean(delta**2))),
       "mp_abs_mean":float(np.mean(np.abs(delta))),
       "mp_gt0p1_any":bool(np.max(np.abs(delta))>.1),
       "mp_gt0p1_fraction":float(np.mean(np.abs(delta)>.1)),
       "delta_gradient_rms":float(np.sqrt(np.mean(np.diff(delta)**2))),
       "noncentrality_diff":noncentrality,
       "hypothetical_detection_probability":chance,
       "cov_assumption":"iid s noise R=.0081, D C D^T",
       "online_eligible":False})
 if not rows:raise RuntimeError("NO_EXISTING_SWEEPS")
 table=pd.DataFrame(rows)
 # Hypothetical detector power under original R0, not measured false positive or observed rejection.
 outcsv=out/"R5_4_EXISTING_FULL_SWEEP_GRADIENT_DIAG.csv"
 table.to_csv(outcsv,index=False)
 agg=[]
 for name,g in table.groupby("route"):
  agg.append({"route":name,"groups":len(g),
    "mean_gradient_power":float(g["hypothetical_detection_probability"].mean()),
    "fraction_MP_any_gt_0p1":float(g.mp_gt0p1_any.mean()),
    "fraction_MP_any_but_gradient_power_lt_0p2":float(np.mean(g.mp_gt0p1_any & (g.hypothetical_detection_probability<.2))),
    "mean_angular_span_deg":float(np.mean(g.yaw_max_deg-g.yaw_min_deg))})
 outsum={"schema":"R5_4_EXISTING_FULL_RF_ANGLE_GRADIENT_ORACLE_V1",
    "status":"OFFLINE_EXISTING_SWEEP_GRADIENT_DIAG_COMPLETE",
    "actual_group_count":len(table),
    "group_rows_distribution":{str(k):int(v) for k,v in table.n.value_counts().sort_index().items()},
    "total_multiangle_samples":int(table.n.sum()),
    "angular_span_min_max_deg":[float((table.yaw_max_deg-table.yaw_min_deg).min()),
                                 float((table.yaw_max_deg-table.yaw_min_deg).max())],
    "overall_mean_hypothetical_gradient_detection_probability":float(table.hypothetical_detection_probability.mean()),
    "overall_MP_any_gt0p1_group_frac":float(table.mp_gt0p1_any.mean()),
    "MP_any_but_gradient_detection_lt0p2_group_frac":float(np.mean(table.mp_gt0p1_any & (table.hypothetical_detection_probability<.2))),
    "per_route":agg,
    "warnings":["This compares FULL RF with oracle matched direct native LoS only; not frozen LUT prediction",
                "Relative yaw supplied by offline true pose, not gyro measurement",
                "No injected actual sensor noise; detection power is theoretical under iid R0",
                "Existing original RF slices have no recorded robot rotational dynamics/lever-arm correction",
                "Groups in same corridor are not independent environments",
                "No conclusion on heading EKF RMSE or NEES"],
    "scientific_PASS":False}
 write(out/"R5_4_FINAL.json",outsum)
 print("R5_4_ORACLE_SWEEP_FINAL "+json.dumps(outsum),flush=True)
 return 0
if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",required=True,choices=["pre","run"])
 ap.add_argument("--out",required=True)
 ap.add_argument("--audit")
 x=ap.parse_args()
 raise SystemExit(audit(Path(x.out)) if x.phase=="pre" else run(Path(x.out),x.audit))
