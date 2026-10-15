"""Independent read-only Q4 numerical audit and stage-gate evaluation.
Q4 uses prior x/P from ORIGINAL J4/DR4 and oracle GT solely for scoring.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
Q4_ZIP_SHA="599267063f87546ca76cf6f7c755977c74c8b298c18fbb89e73066dd34be3164"
Q4_SOURCE_BLOB="28ec3676bbe5f1cca27ca67d6564a221635f1da4"
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()
def gitblob(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with open(p,"rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()
def store(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[]
 head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("REQUIRE_CLOUD")
 if head!=os.getenv("GITHUB_SHA"):errors.append("REV_DIFFERENCE")
 f=ROOT/"research/N4_Q_GEOM_RF_20261015/q4_prior_observability.py"
 if not f.is_file() or gitblob(f)!=Q4_SOURCE_BLOB:errors.append("Q4_ORIGINAL_BLOB_CHANGED")
 try:ast.parse((HERE/"q4_independent_review.py").read_text())
 except Exception as e:errors.append("SOURCE_AST:"+repr(e))
 wf=ROOT/".github/workflows/n4q-q4-verify.yml"
 if not wf.is_file():errors.append("WORKFLOW_MISSING")
 else:
  w=wf.read_text()
  if not (0<=w.find("q4_independent_review.py --phase pre")<
          w.find("q4_independent_review.py --phase run") and
          "if: always()" in w and "actions: read" in w):
   errors.append("AUDIT_FIRST_VIOLATION")
 rec={"decision":"GO" if not errors else "HOLD","source_sha":head,
    "upstream_Q4_artifact_sha256":Q4_ZIP_SHA,"errors":errors}
 store(out/"PRE_AUDIT.json",rec)
 print("Q4_REVIEW_PRE "+json.dumps(rec),flush=True)
 return 0 if not errors else 2
def member(z,name):
 matching=[p for p in z.namelist() if p==name or p.endswith("/"+name)]
 if len(matching)!=1:raise RuntimeError("NONUNIQUE_MEMBER:"+name)
 return matching[0]
def execute(out,receipt,zip_path):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 r=json.loads(Path(receipt).read_text())
 if r["decision"]!="GO" or r["source_sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("PREAUDIT_HOLD")
 if sha(zip_path)!=Q4_ZIP_SHA:raise RuntimeError("Q4_EVIDENCE_SHA_MISMATCH")
 with zipfile.ZipFile(zip_path) as z:
  if z.testzip():raise RuntimeError("ARCHIVE_CRC_ERROR")
  final=json.loads(z.read(member(z,"Q4_FINAL.json")))
  if final["status"]!="Q4_PRIOR_SIXPOINT_CUBATURE_COMPLETE" or final["total_evaluated_records"]!=26528:
   raise RuntimeError("ORIGINAL_Q4_NOT_COMPLETE")
  records=list(csv.DictReader(io.StringIO(z.read(member(z,"Q4_PRIOR_VS_ORACLE_STATS.csv")).decode())))
  with gzip.open(io.BytesIO(z.read(member(z,"Q4_PRIOR_GEOMETRY_FULL_RECORDS.csv.gz"))),"rt",encoding="utf8") as f:
   raw=list(csv.DictReader(f))
  if len(records)!=32 or len(raw)!=26528:
   raise RuntimeError("RAW_AGG_COUNT_BAD")
  grouped={}
  for x in raw:
   key=(x["case"],x["channel"],x["bias"],x["prior_family"])
   grouped.setdefault(key,[]).append(x)
  expected={(x["case"],x["channel"],x["bias"],x["method"]):x for x in records}
  if set(grouped)!=set(expected):raise RuntimeError("GROUP_MISMATCH")
  for key,items in grouped.items():
   ref=expected[key]
   if len(items)!=829:raise RuntimeError("EVAL_GROUP_NOT_829")
   for field,agg in (
     ("prior_geometric_highlow_flip_rate","prior_geom_label_wrong"),
     ("cubature_brier_vs_GT_geom_label","cubature_prob_squared_error"),
     ("point_label_brier_vs_GT_geom_label","point_label_squared_error"),
     ("s_LoS_GT_coverage95_from_prior_cubature","cubature_s_coverage95_geometry_only")):
    got=sum(float(v[agg]) for v in items)/len(items)
    if abs(got-float(ref[field]))>1e-10:
     raise RuntimeError("ORIGINAL_Q4_METRIC_PARITY_FAILED:"+str(key)+"/"+field)
  pairs=[]
  for case in ("R2_aA_m0","R2_aA_m45"):
   for channel in ("full","los"):
    for bias in ("B0","L2"):
     x=expected[(case,channel,bias,"J4")]
     d=expected[(case,channel,bias,"DR4")]
     pairs.append({
       "case":case,"mount_deg":45 if case.endswith("m45") else 0,
       "channel":channel,"bias":bias,"n":829,
       "J4_geom_label_flip_rate":float(x["prior_geometric_highlow_flip_rate"]),
       "DR4_geom_label_flip_rate":float(d["prior_geometric_highlow_flip_rate"]),
       "J4_cubature_geom95":float(x["s_LoS_GT_coverage95_from_prior_cubature"]),
       "DR4_cubature_geom95":float(d["s_LoS_GT_coverage95_from_prior_cubature"]),
       "J4_brier_point":float(x["point_label_brier_vs_GT_geom_label"]),
       "J4_brier_cubature":float(x["cubature_brier_vs_GT_geom_label"]),
       "DR4_brier_point":float(d["point_label_brier_vs_GT_geom_label"]),
       "DR4_brier_cubature":float(d["cubature_brier_vs_GT_geom_label"]),
       "J4_prior_heading_abs_error_deg":float(x["mean_abs_prior_heading_error_deg"]),
       "J4_prior_heading_sigma_deg":float(x["mean_prior_heading_sigma_deg"]),
       "DR4_prior_heading_abs_error_deg":float(d["mean_abs_prior_heading_error_deg"]),
       "DR4_prior_heading_sigma_deg":float(d["mean_prior_heading_sigma_deg"])
     })
  all_calibrated=all(x["J4_cubature_geom95"]>=.90 and x["DR4_cubature_geom95"]>=.90 for x in pairs)
  result={"schema":"N4Q_Q4_PRIOR_INDEPENDENT_REVIEW_V1",
    "status":"Q4_NUMERICALLY_AUDITED_ONLINE_CALIBRATION_GATE_FAIL" if not all_calibrated else
             "Q4_SCIENTIFIC_GEOMETRY_CALIBRATION_PLAUSIBLE",
    "parent_Q4_SHA":Q4_ZIP_SHA,"source_sha":os.getenv("GITHUB_SHA"),
    "independent_metric_parity":"PASS",
    "paired_DR4_J4_B0_L2":pairs,
    "Q4_sigma_95_cov_tolerance":.90,
    "Q4_highconfidence_calibration_PASS":all_calibrated,
    "Q5_harm_classifier_online_deployment_GO":False,
    "Q5_offline_quality_comparison":"EXPLORATORY_ONLY",
    "Q6_joint4_sr4_new_geometry_weighting":"BLOCKED_Q4_CALIBRATION",
    "Q7_trajectory_scene":"BLOCKED_INPUT_INDEPENDENT_FULL_RF",
    "scope":["This is a reference-prior diagnostic, not a new EKF model",
      "Raw observations are noise-free Full/LoS complex channel, one scene",
      "Nominal 95% LoS predicted geometry coverage is not Bayesian posterior coverage",
      "Cubature estimates the existing overconfident Gaussian P, cannot repair it",
      "This gate deliberately prevents premature Q6 hard/soft gating from GT features"],
    "scientific_PASS":False}
 store(out/"Q4_STAGE_GATE.json",result)
 with (out/"Q4_DR4_VS_J4.csv").open("w",newline="",encoding="utf8") as f:
  w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
 print("Q4_REVIEW_FINAL "+json.dumps({"status":result["status"],
   "Q4_highconfidence_calibration_PASS":all_calibrated,"pairs":pairs},ensure_ascii=False),flush=True)
 return 0
if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("pre","run"),required=True)
 ap.add_argument("--out",required=True);ap.add_argument("--input");ap.add_argument("--audit")
 args=ap.parse_args()
 raise SystemExit(pre(args.out) if args.phase=="pre" else execute(args.out,args.audit,args.input))
