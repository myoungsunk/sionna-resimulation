"""Independent Q4-R stage gate from immutable full R1/R2/R3 and original Q4 archives.

No re-fit or rerun of filters. Recompute results from archived CSV (stdlib).
PASS means code/source/numerical parity; scientific GO requires independent
training AND real recursive point-error + covariance consistency jointly.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,os,subprocess,zipfile
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
ART={
 "r1":"86dc05d64ddb2ddf5a688665f387b6d12346162491fa9435ecaecf6c8f1aefe9",
 "r2":"4f979b13f32c0a269d10dd0d7d1dc39d6f8b82dca425fb2e9aacf3cfda22e510",
 "r3":"6cf473eb82b867e6b45c01500cdadaf088e8bdbf0f2f9ab616477c3080a5ff8d",
 "q4":"599267063f87546ca76cf6f7c755977c74c8b298c18fbb89e73066dd34be3164",
}
PINNED={
 "research/N4_Q4R_20261015/q4r_posthoc.py":"2c3a393228c31a4019f24896efb1cdf07925b4d1",
 "research/N4_Q4R_20261015/q4r_recursive.py":"387ec31cdf7a3081b8986945f11439b952114704",
 "research/N4_Q4R_20261015/q4r_geometry.py":"0d3eb79b27d3e2d60e9160f87e33b3935188005d",
}
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for v in iter(lambda:f.read(1<<20),b""):h.update(v)
 return h.hexdigest()
def blob(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for v in iter(lambda:f.read(1<<20),b""):h.update(v)
 return h.hexdigest()
def save(p,obj):
 Path(p).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def member(z,name):
 matches=[s for s in z.namelist() if s==name or s.endswith("/"+name)]
 if len(matches)!=1:raise RuntimeError("EVIDENCE_MEMBER_COUNT:"+name)
 return matches[0]
def openzip(p,exp):
 got=sha(p)
 if got!=exp:raise RuntimeError("EVIDENCE_ARCHIVE_HASH_MISMATCH:"+str(p)+":"+got)
 z=zipfile.ZipFile(p)
 if z.testzip():raise RuntimeError("ARCHIVE_CRC_FAILED")
 return z
def loadcsv(z,name):
 return list(csv.DictReader(io.StringIO(z.read(member(z,name)).decode("utf-8"))))
def writecsv(path,rows):
 with Path(path).open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 e=[];head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":e.append("RUNNER_REQUIRED")
 if head!=os.getenv("GITHUB_SHA"):e.append("CHECKOUT_DIFFERENT")
 for p,h in PINNED.items():
  f=ROOT/p
  if not f.exists():e.append("MISSING_SOURCE:"+p)
  elif blob(f)!=h:e.append("ORIGINAL_BLOB_DIFFERENCE:"+p)
 try:ast.parse((HERE/"q4r_review.py").read_text())
 except Exception as ex:e.append("CODE_AST_FAILURE:"+repr(ex))
 wf=ROOT/".github/workflows/n4q-q4r-review.yml"
 if not wf.exists():e.append("WORKFLOW_MISSING")
 else:
  w=wf.read_text()
  s=w.find("q4r_review.py --phase pre")
  t=w.find("q4r_review.py --phase run")
  if not 0<=s<t or "if: always()" not in w or "actions: read" not in w:
   e.append("WORKFLOW_AUDIT_NOT_FIRST")
 rec={"decision":"GO" if not e else "HOLD","git_sha":head,"archives":ART,
      "immutable_source_blobs":PINNED,"errors":e}
 save(out/"PRE_AUDIT.json",rec)
 print("Q4R_REVIEW_PRE "+json.dumps({"decision":rec["decision"],"errors":e}),flush=True)
 return 0 if not e else 2
def execute(out,prepath,r1p,r2p,r3p,q4p):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 p=json.loads(Path(prepath).read_text())
 if p["decision"]!="GO" or p["git_sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("NO_PRIOR_SOURCE_AUDIT")
 with openzip(r1p,ART["r1"]) as r1,openzip(r2p,ART["r2"]) as r2, \
      openzip(r3p,ART["r3"]) as r3,openzip(q4p,ART["q4"]) as q4:
  m1=json.loads(r1.read(member(r1,"Q4R1_FINAL.json")))
  m2=json.loads(r2.read(member(r2,"Q4R2_FINAL.json")))
  m3=json.loads(r3.read(member(r3,"Q4R3_FINAL.json")))
  orig=json.loads(q4.read(member(q4,"Q4_FINAL.json")))
  if m1["status"]!="Q4R1_POSTHOC_PILOT_COMPLETE" or m2["status"]!=\
       "Q4R2_FIXED_PRIOR_CORRECTIONS_RECURSIVE_PILOT_COMPLETE" or m3["status"]!=\
       "Q4R3_ACTUAL_RECURSIVE_PRIOR_GEOMETRY_PILOT_COMPLETE":
   raise RuntimeError("UPSTREAM_R1_R2_R3_NOT_SUCCESS")
  r1rows=loadcsv(r1,"Q4R1_POSTHOC_ALL.csv")
  r2rows=loadcsv(r2,"Q4R2_RECURSIVE_ALL.csv")
  r3rows=loadcsv(r3,"Q4R3_GEOMETRY_CALIBRATION.csv")
  parity=loadcsv(r2,"Q4R2_BASELINE_PARITY.csv")
  if (len(r1rows),len(r2rows),len(r3rows),len(parity))!=(448,240,56,48):
   raise RuntimeError("Q4R_COMPLETENESS_MISMATCH")
  if any(int(p["gate_mismatches"])!=0 or float(p["state_max"])>1e-6 or
     float(p["cov_max"])>1e-6 for p in parity):
   raise RuntimeError("Q4R_BASELINE_FROZEN_SOURCE_PARITY")
  # Important R1 negative control: posthoc P NEVER changes original estimates.
  r1idx=defaultdict(list)
  for r in r1rows:
   k=(r["case"],r["channel"],r["bias"],r["method"])
   r1idx[k].append(r)
  for k,rs in r1idx.items():
   for f in ("heading_rmse_deg","xy_rmse_m","bias_rmse_dps"):
    vals=[float(v[f]) for v in rs]
    if max(vals)-min(vals)>1e-11:raise RuntimeError("RETROSPECTIVE_STATE_CHANGED:"+str((k,f)))
  # Strict original J4 baseline Q4 geometric diagnostic parity.
  origidx={(r["case"],r["channel"],r["bias"],r["method"]):r
    for r in orig["full_J4_focus"]}
  q3idx={(r["case"],r["channel"],r["bias"],r["solver"],r["rfmodel"],
          r["prior_correction"]):r for r in r3rows}
  original_geometry=[]
  for row in orig["full_J4_focus"]:
   k=(row["case"],"full",row["bias"],"J4","BASE_R0","RAW")
   got=q3idx.get(k)
   if got is None:raise RuntimeError("MISSING_ORIGINAL_Q4_CONTROL:"+str(k))
   delta=abs(float(got["geometry_s_95coverage"])-
     float(row["s_LoS_GT_coverage95_from_prior_cubature"]))
   if delta>1e-9:raise RuntimeError("RAW_Q4_GEOMETRY_PARITY_FAIL:"+str((k,delta)))
   original_geometry.append({"case":row["case"],"bias":row["bias"],"diff":delta})
  r2idx={(r["case"],r["channel"],r["bias"],r["method"],
    r["rfmodel"],r["prior_correction"]):r for r in r2rows}
  paired=[]
  for r in r2rows:
   if r["prior_correction"]=="RAW":continue
   k=(r["case"],r["channel"],r["bias"],r["method"],r["rfmodel"],"RAW")
   ref=r2idx[k]
   paired.append({"case":r["case"],"channel":r["channel"],"bias":r["bias"],
    "method":r["method"],"rfmodel":r["rfmodel"],"prior":r["prior_correction"],
    "change_heading_RMSE":float(r["heading_rmse_deg"])-float(ref["heading_rmse_deg"]),
    "change_bias_RMSE":float(r["bias_rmse_dps"])-float(ref["bias_rmse_dps"]),
    "change_pose_NEES":float(r["pose_nees"])-float(ref["pose_nees"]),
    "change_pose_coverage":float(r["pose_95coverage"])-float(ref["pose_95coverage"])})
  # All arms must pass BOTH full RF geometry and no degradation/LoS guard,
  # and require independently trained calibration model. No post-hoc R2 fitting.
  geom_pass={}
  for k,v in q3idx.items():
   if v["channel"]=="full":
    g=(v["solver"],v["rfmodel"],v["prior_correction"])
    geom_pass.setdefault(g,[]).append(float(v["geometry_s_95coverage"]))
  pilot_above90={str(k):all(x>=.9 for x in vals) for k,vals in geom_pass.items()}
  report={
    "schema":"Q4R_ALL_STAGES_INDEPENDENT_ARCHIVE_GATE_V1",
    "status":"Q4R_PILOT_COMPLETE_SCIENTIFIC_CALIBRATION_NOT_ACHIEVED",
    "source_sha":os.environ["GITHUB_SHA"],
    "original_archive_sha":ART,
    "R0_training_eligible":m1["source_audit_training_eligible"],
    "R1_posthoc_score_rows":len(r1rows),
    "R2_true_recursive_arms":len(r2rows),
    "R3_original_FFD_geometry_arms":len(r3rows),
    "source_reproduction_tests":len(parity),
    "original_Q4_coverage_parity":original_geometry,
    "any_R3_full_geometry_90pct_pilot":any(pilot_above90.values()),
    "full_geometry_90pct_by_policy":pilot_above90,
    "actual_recursive_effects":paired,
    "Q4R_SCOPED_TECHNICAL_PASS":True,
    "Q4R_CALIBRATION_SCIENTIFIC_PASS":False,
    "Q5_GO":False,
    "Q6_GO":False,
    "blockers":[
      "R4/R5 SAMPLES contain pose/Yaw sweeps but no validated gyro/wheel/timing per timepoint",
      "Calibration candidates fixed a priori without GT fitting; no independent scene/seed",
      "Inflating P in true recursion alters RF acceptance/Gain, usually degrades Heading/Bias on L2",
      "Full RF geometry prediction under revised recursive prior is not 90% across mounts",
      "Original R2 repeatedly inspected cannot be hidden final validation data",
      "Posthoc covariance calibration cannot change original estimator point error",
      "POWER_JOINT trained on same-packet power requires proper normalization before Bayesian credibility"
    ]}
  save(out/"STAGE_GATES.json",report)
  writecsv(out/"Q4R_RECURSIVE_PAIRED_EFFECTS.csv",paired)
  print("Q4R_REVIEW_FINAL "+json.dumps({"status":report["status"],
      "R1":len(r1rows),"R2":len(r2rows),"R3":len(r3rows),
      "baseline_parity":len(parity),"any_geom90":report["any_R3_full_geometry_90pct_pilot"],
      "training_source":m1["source_audit_training_eligible"],
      "sample_l2":[r for r in paired if r["bias"]=="L2" and r["method"]=="J4" and
      r["channel"]=="full" and r["prior"] in ("Q_MEDIUM","EIG_NARROW_10CM")]},
    ensure_ascii=False),flush=True)
 return 0
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","run"),required=True)
 p.add_argument("--out");p.add_argument("--audit");p.add_argument("--r1")
 p.add_argument("--r2");p.add_argument("--r3");p.add_argument("--q4")
 a=p.parse_args()
 return pre(a.out) if a.phase=="pre" else execute(a.out,a.audit,a.r1,a.r2,a.r3,a.q4)
if __name__=="__main__":raise SystemExit(main())
