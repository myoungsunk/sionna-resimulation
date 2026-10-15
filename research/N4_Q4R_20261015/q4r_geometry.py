"""Q4-R3: original FFD cubature after TRUE Q4-R2 recursive prior calibration.

This is a preregistered zero-fit pilot, NOT scientific final prior calibration.
The original Q4 geometry-only coverage uses oracle GT for offline scoring.
Online features use each arm's predicted x^-,P^- only.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
ART={
 "r2_recursive":"4f979b13f32c0a269d10dd0d7d1dc39d6f8b82dca425fb2e9aacf3cfda22e510",
 "RF":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "Q4":"599267063f87546ca76cf6f7c755977c74c8b298c18fbb89e73066dd34be3164",
}
BLOBS={
 "research/N4_Q4R_20261015/q4r_recursive.py":"387ec31cdf7a3081b8986945f11439b952114704",
 "research/N4_Q_GEOM_RF_20261015/q4_prior_observability.py":"28ec3676bbe5f1cca27ca67d6564a221635f1da4",
 "research/R5_N4B_POL_V1_20261015/n4b_pol_geometry.py":"565d6f2704f40f770da5f70a40314141a3d621a1",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
}
CASES=("R2_aA_m0","R2_aA_m45")
BIAS=("B0","L2")
SOLVERS=("J4","SR4")
SELECT_FULL=(("BASE_R0","RAW"),("BASE_R0","Q_MEDIUM"),
  ("POWER_JOINT","RAW"),("POWER_JOINT","Q_MEDIUM"),
  ("POWER_JOINT","EIG_PLUS_YAW1"))
SELECT_LOS=(("BASE_R0","RAW"),("BASE_R0","Q_MEDIUM"))
def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(f,x):
 p=Path(f);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def verified(path,h):
 if sha(path)!=h:raise RuntimeError("ARCHIVED_EVIDENCE_CHANGED:"+str(path))
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("BAD_ZIP_CRC")
 return z
def member(z,name):
 a=[k for k in z.namelist() if k==name or k.endswith("/"+name)]
 if len(a)!=1:raise RuntimeError("MISSING_OR_DUP:"+name)
 return a[0]
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 err=[];head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":err.append("GITHUB_REQUIRED")
 if head!=os.getenv("GITHUB_SHA"):err.append("WRONG_HEAD")
 for p,v in BLOBS.items():
  if v.startswith("__"):err.append("UNPINNED_SOURCE:"+p);continue
  f=ROOT/p
  if not f.is_file():err.append("FROZEN_NOT_FOUND:"+p)
  elif blob(f)!=v:err.append("SOURCE_CHANGED:"+p)
 if ART["r2_recursive"].startswith("__"):err.append("MISSING_VALIDATED_RECURSIVE_ARCHIVE_HASH")
 try:ast.parse((HERE/"q4r_geometry.py").read_text())
 except Exception as e:err.append("PYTHON_SYNTAX:"+repr(e))
 wf=ROOT/".github/workflows/n4q-q4r-r3.yml"
 if not wf.is_file():err.append("WF_MISSING")
 else:
  w=wf.read_text()
  a=w.find("q4r_geometry.py --phase pre")
  b=w.find("q4r_geometry.py --phase test")
  c=w.find("q4r_geometry.py --phase run")
  if not 0<=a<b<c or "if: always()" not in w:err.append("AUDIT_FIRST_WORKFLOW_MISSING")
 receipt={"decision":"GO" if not err else "HOLD","head":head,
   "source_hashed":BLOBS,"artifacts":ART,"errors":err}
 save(out/"Q4R3_PRE_AUDIT.json",receipt)
 print("Q4R3_PRE "+json.dumps({"decision":receipt["decision"],"errors":err}),flush=True)
 return 0 if not err else 2
def setup():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
  str(ROOT/"research/N4_Q_GEOM_RF_20261015"),
  str(ROOT/"research/R5_N4B_POL_V1_20261015"),
  str(ROOT/"research/R5_N4B_20261015"),
  str(ROOT/"research/R5_FULLRF_B0_GATES_20261015"),
  str(ROOT/"research/PHYSICS_RS_STAGED_20261015/code"),
  str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"),
  str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src")
 ]
 import q4_prior_observability as q4
 import n4b_pol_geometry as pol
 from p3_rf_adapter4 import FrozenLut
 return np,pd,q4,pol,FrozenLut
def test():
 np,pd,q4,pol,Lut=setup()
 x=np.array([1.3,.4,math.radians(12)])
 P=np.diag([.03,.03,math.radians(8)**2,.00001])
 pts=q4.sigma_points(np,x[:3],P[:3,:3])
 np.testing.assert_allclose(np.mean(pts,axis=0),x[:3],atol=1e-12)
 L=Lut(ROOT);case={"anchor":[4,0,2.65],"mount_deg":0,"robot_z_m":.45}
 o=q4.measure_quality(np,L,pol,x,P,case,70.2075667)
 assert 0<=o["p_info_high_cubature"]<=1
 print("Q4R3_UNIT_PASS "+json.dumps({"FFD_points":len(pts),"p_info":o["p_info_high_cubature"]}),flush=True)
 return 0
def execute(out,receipt,r2archive,rfarchive,q4original):
 np,pd,q4,pol,Lut=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(receipt).read_text())
 if a["decision"]!="GO" or a["head"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("PREAUDIT_HOLD")
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cm={case["id"]:case for case in manifest["cases"]}
 lut=Lut(ROOT)
 rows=[]
 with verified(r2archive,ART["r2_recursive"]) as zr, \
      verified(rfarchive,ART["RF"]) as zf, verified(q4original,ART["Q4"]) as zq:
  r2_meta=json.loads(zr.read(member(zr,"Q4R2_FINAL.json")))
  if r2_meta["status"]!="Q4R2_FIXED_PRIOR_CORRECTIONS_RECURSIVE_PILOT_COMPLETE":
   raise RuntimeError("Q4R2_FROZEN_DATA_NOT_READY")
  q4base=json.loads(zq.read(member(zq,"Q4_FINAL.json")))
  cutoff=float(q4base["nominal_information_threshold_from_R4R5"])
  p2={(k["case"],k["channel"]):k for k in
   json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  for case in CASES:
   for channel in ("full","los"):
    src=p2[(case,channel)]
    raw=zf.read("P2_OUT/"+src["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=src["trace_sha256"]:
     raise RuntimeError("P2_TRACE_SHA_MISMATCH")
    with np.load(io.BytesIO(raw),allow_pickle=False) as v:
     t=v["t_s"].copy();ids=v["pose_id"].copy()
     truth=v["truth_for_offline_scoring_only"].copy()
    for b in BIAS:
     for sol in SOLVERS:
      zz=zr.read(member(zr,f"Q4R2_{case}_{channel}_{b}_{sol}.npz"))
      with np.load(io.BytesIO(zz),allow_pickle=False) as f:
       data={k:f[k].copy() for k in f.files}
      if not np.array_equal(data["t_s"],t) or not np.array_equal(data["pose_id"],ids):
       raise RuntimeError("RECURSIVE_PRIOR_BINDING_BAD")
      policies=SELECT_FULL if channel=="full" else SELECT_LOS
      for rfmodel,corr in policies:
       ix=np.flatnonzero((data["policy"]==rfmodel)&(data["correction"]==corr))
       if len(ix)!=1:raise RuntimeError("MISSING_R2_POLICY:"+str((rfmodel,corr)))
       xx=data["prior_x"][:,int(ix[0])];PP=data["prior_P"][:,int(ix[0])]
       valid=t>=30
       if int(valid.sum())!=829:raise RuntimeError("TIMEMASK_CHANGED")
       c=[]
       for k in np.flatnonzero(valid):
        result=q4.measure_quality(np,lut,pol,xx[k],PP[k],cm[case],cutoff)
        GT_iff=pol.physical_features(np,lut,truth[k],cm[case])
        h_gt=GT_iff["s_los_expected"]
        oracle_high=GT_iff["Ipsi_nominal"]>=cutoff
        geom_delta=result["LoS_s_cubature_mean"]-h_gt
        geom_sigma=result["LoS_s_cubature_std"]
        covered=abs(geom_delta)<=1.96*max(geom_sigma,1e-12)
        row={
          "case":case,"channel":channel,"bias":b,"solver":sol,
          "rfmodel":rfmodel,"prior_correction":corr,
          "time":float(t[k]),"pose_id":int(ids[k]),
          "oracle_Igeom":float(GT_iff["Ipsi_nominal"]),
          "point_Igeom":result["I_geom_point"],
          "operational_info":result["Iop_prior_ref_Rs"],
          "geometry_coverage95":bool(covered),
          "information_brier":(result["p_info_high_cubature"]-int(oracle_high))**2,
          "highconf_wrong_information":bool(
           (result["p_info_high_cubature"]>=.9 and not oracle_high) or
           (result["p_info_high_cubature"]<=.1 and oracle_high)),
          "geometry_sigma_s":float(geom_sigma),
          "error_s_predicted_minus_GT":float(geom_delta),
          "p_high":result["p_info_high_cubature"]
        }
        c.append(row)
       score={
         "case":case,"channel":channel,"bias":b,"solver":sol,
         "rfmodel":rfmodel,"prior_correction":corr,"n":len(c),
         "geometry_s_95coverage":float(np.mean([v["geometry_coverage95"] for v in c])),
         "information_brier":float(np.mean([v["information_brier"] for v in c])),
         "highconf_wrong_info":float(np.mean([v["highconf_wrong_information"] for v in c])),
         "geometry_sigma_s_median":float(np.median([v["geometry_sigma_s"] for v in c])),
         "median_p_high":float(np.median([v["p_high"] for v in c])),
       }
       rows.append(score)
       print("Q4R3_CASE "+json.dumps(score),flush=True)
 with (out/"Q4R3_GEOMETRY_CALIBRATION.csv").open("w",newline="",encoding="utf8") as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]))
  writer.writeheader();writer.writerows(rows)
 focus=[x for x in rows if x["channel"]=="full" and x["solver"]=="J4"]
 internal=[x for x in rows if x["channel"]=="full" and
  x["rfmodel"]=="POWER_JOINT" and x["prior_correction"]=="Q_MEDIUM"]
 los=[x for x in rows if x["channel"]=="los" and x["solver"]=="J4"]
 goal_met=all(x["geometry_s_95coverage"]>=.9 for x in internal)
 rec={"status":"Q4R3_ACTUAL_RECURSIVE_PRIOR_GEOMETRY_PILOT_COMPLETE",
  "source_commit":os.environ["GITHUB_SHA"],
  "n_metrics":len(rows),"R4R5_posterior_training_available":False,
  "predefined_PSD_calibration_provenance":"ZERO_FIT_PILOT_ONLY",
  "full_J4":focus,"los_J4_guards":los,
  "internal_90pct_geometric_coverage_exploratory":goal_met,
  "Q5_GO":False,"scientific_PASS":False,
  "blocked_reasons":["No independently trained covariance model on authentic R4/R5 sequential data",
    "Calibration model untested in independent RF scenes and time/seed distributions",
    "Geometry 95% coverage is not full 4-state Bayesian posterior coverage",
    "Earlier N4C POWER_JOINT uses same packet features; no normalized sensor likelihood proof",
    "Q5 requires calibrated online prior and separate trained risk heads",
    "Q6 full end-to-end deployment blocked until Q5 passes"]}
 save(out/"Q4R3_FINAL.json",rec)
 print("Q4R3_FINAL "+json.dumps({"status":rec["status"],"metrics":len(rows),
    "internal":internal,"los_guard":los,
    "internal_90pct_pilot":goal_met},ensure_ascii=False),flush=True)
 return 0
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("pre","test","run"),required=True)
 ap.add_argument("--out");ap.add_argument("--audit")
 ap.add_argument("--r2");ap.add_argument("--rf");ap.add_argument("--q4")
 a=ap.parse_args()
 return pre(a.out) if a.phase=="pre" else test() if a.phase=="test" else \
   execute(a.out,a.audit,a.r2,a.rf,a.q4)
if __name__=="__main__":raise SystemExit(main())
