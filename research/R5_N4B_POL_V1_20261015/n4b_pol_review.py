"""N4B-POL independent read-only mount/anchor stratum audit.
Original N4B-POL measured RF & filter/data sources are immutable.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,statistics,subprocess,zipfile
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE_SHA="565d6f2704f40f770da5f70a40314141a3d621a1"
ARCHIVE_SHA="348c0761e7c6ec06057a5e80b799739e302ba869c9e6d368bce10628a8ba7bae"

def hfile(p):
 x=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):x.update(b)
 return x.hexdigest()
def gh_blob(p):
 p=Path(p)
 h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def export(path,records):
 with Path(path).open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]))
  w.writeheader();w.writerows(records)
def dump(path,obj):
 Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 failures=[]
 rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":failures.append("GITHUB_ACTIONS_REQUIRED")
 if rev!=os.getenv("GITHUB_SHA"):failures.append("SOURCE_HEAD_CHANGED")
 f=ROOT/"research/R5_N4B_POL_V1_20261015/n4b_pol_geometry.py"
 if not f.is_file() or gh_blob(f)!=SOURCE_SHA:failures.append("PINNED_ORIGINAL_GEOMETRY_SOURCE_CHANGED")
 try:ast.parse((HERE/"n4b_pol_review.py").read_text())
 except Exception as e:failures.append("SOURCE_INVALID:"+str(e))
 wf=ROOT/".github/workflows/r5-n4b-pol-review.yml"
 if not wf.is_file():failures.append("WORKFLOW_MISSING")
 else:
  w=wf.read_text()
  if not(0<=w.find("n4b_pol_review.py --phase pre")<
         w.find("n4b_pol_review.py --phase run") and
         "if: always()" in w and "actions: read" in w):
   failures.append("NOT_AUDIT_FIRST")
 result={"decision":"GO" if not failures else "HOLD","source_head":rev,
   "original_source_git_blob":SOURCE_SHA,"original_full_artifact_sha":ARCHIVE_SHA,
   "errors":failures}
 dump(out/"PRE_AUDIT.json",result)
 print("POL_REVIEW_PRE "+json.dumps(result),flush=True)
 return 0 if not failures else 2
def member(z,name):
 a=[x for x in z.namelist() if x==name or x.endswith("/"+name)]
 if len(a)!=1:raise RuntimeError("DUPLICATE_OR_MISSING_MEMBER:"+name)
 return a[0]
def readcsv(z,name):
 with gzip.open(io.BytesIO(z.read(member(z,name))),"rt",encoding="utf8",newline="") as f:
  return list(csv.DictReader(f))
def val(x,key):
 return float(x[key])
def mean(v):return statistics.mean(v)
def cov(r):
 n=len(r)
 if n<3:return None
 er=[val(x,"e_r") for x in r]
 es=[val(x,"e_s") for x in r]
 mr=mean(er);ms=mean(es)
 vr=mean([(a-mr)**2 for a in er])
 vs=mean([(a-ms)**2 for a in es])
 cr=mean([(a-mr)*(b-ms) for a,b in zip(er,es)])
 return {"n":n,"mu_r_m":mr,"mu_s":ms,"Vr_m2":vr,"Vs":vs,
   "C_rs_m":cr,"rho_rs":cr/(vr*vs)**.5 if vr*vs>0 else None,
   "r_rmse_m":mean([a*a for a in er])**.5,
   "s_rmse":mean([b*b for b in es])**.5}
def classify(row):
 dom=val(row,"p_dom_los")
 balance=val(row,"balance_los")
 hpsi=abs(val(row,"Hpsi_lut"))
 info=val(row,"Ipsi_nominal")
 return {
  "dominance_high90":dom>=.9,
  "balance_high80":balance>=.8,
  "heading_slope_high1":hpsi>=1.,
  "nominal_heading_info_high100":info>=100.,
 }
def mainrun(out,pre,archive):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 audit_doc=json.loads(Path(pre).read_text())
 if audit_doc["decision"]!="GO" or audit_doc["source_head"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("PRE_AUDIT_HOLD")
 if hfile(archive)!=ARCHIVE_SHA:raise RuntimeError("FINAL_ARTIFACT_SHA_DIFFERENCE")
 with zipfile.ZipFile(archive) as z:
  if z.testzip():raise RuntimeError("ARTIFACT_CRC_FAIL")
  meta=json.loads(z.read(member(z,"POL_V1_FINAL.json")))
  if meta["status"]!="AUDITED_GEOMETRIC_N4B_REEXECUTION_COMPLETE":
   raise RuntimeError("N4B_GEOM_EXECUTION_NOT_PASS")
  if meta["original_n4b_model_parity"]["parity_packets"]!=57114:
   raise RuntimeError("N4B_ORIGINAL_MODEL_PARITY_NOT_PASS")
  rows=readcsv(z,"POL_V1_HELDOUT_PREDICTIONS.csv.gz")
  if len(rows)!=9519*15:raise RuntimeError("MODEL_PRED_ROW_COUNT")
  arr={(r["case"],int(r["pose_id"]),r["model"]):r for r in rows}
  if len(arr)!=len(rows):raise RuntimeError("DUPLICATE_R2_PREDICTION")
  base=[r for r in rows if r["model"]=="SIMPLE_DIAG"]
  if len(base)!=9519:raise RuntimeError("BASE_MISSING")
  stratum=[]
  case_index=defaultdict(list)
  for r in base:case_index[r["case"]].append(r)
  for case,subset in case_index.items():
   for metric in ("dominance_high90","balance_high80","heading_slope_high1",
                  "nominal_heading_info_high100"):
    for yes in (True,False):
     picked=[r for r in subset if classify(r)[metric]==yes]
     if len(picked)<12:continue
     d={"case":case,"mount_deg":45 if case.endswith("m45") else 0,
        "polar_stratum":metric,"threshold_met":yes}
     d.update(cov(picked))
     stratum.append(d)
  aligned=[]
  for case,subset in case_index.items():
   for candidate in ("SIMPLE_PLUS_SIGNED_LOS","SIMPLE_PLUS_BALANCE",
                     "SIMPLE_PLUS_HPSI","SIMPLE_PLUS_IEFF",
                     "SIMPLE_PLUS_FFD_ALL","SIMPLE_G4_PLUS_FFD_ALL",
                     "G5_PLUS_FFD_ALL_RESEARCH_ONLY"):
    control=("SIMPLE_G4" if candidate.startswith("SIMPLE_G4") else
            "G5_RESEARCH_ONLY" if candidate.startswith("G5") else "SIMPLE_DIAG")
    differences=[]
    for r in subset:
     k=(case,int(r["pose_id"]))
     v=arr[k+(candidate,)];b=arr[k+(control,)]
     differences.append(val(v,"nll")-val(b,"nll"))
    aligned.append({"case":case,"model":candidate,"control":control,
      "n":len(differences),"delta_nll_mean":mean(differences),
      "pct_obs_improved":mean([x<0 for x in differences])})
  pre_prior=meta["pre_rf_prior_transfer"]
  audit_groups=[]
  for case in ("R2_aA_m0","R2_aA_m45"):
   for level in ("B0","L2"):
    aa=next(r for r in pre_prior if r["case"]==case and
       r["bias_level"]==level and r["test_pose_source"]=="ORACLE_GT")
    bb=next(r for r in pre_prior if r["case"]==case and
       r["bias_level"]==level and r["test_pose_source"]=="CAUSAL_J4_PRIOR")
    if aa["n"]!=979 or bb["n"]!=979 or aa["raw_route_vs_sample_max_pose_discrepancy"]>1e-5:
     raise RuntimeError("PRE_RF_PRIOR_MAPPING_NOT_VERIFIED")
    audit_groups.append({"case":case,"bias":level,
     "n":979,"oracle_nll":aa["mean_nll"],"causal_prior_nll":bb["mean_nll"],
     "nll_worsening_preRF_minus_oracle":bb["mean_nll"]-aa["mean_nll"],
     "oracle_joint95":aa["joint95"],"causal_prior_joint95":bb["joint95"],
     "joint95_change":bb["joint95"]-aa["joint95"]})
  export(out/"POL_V1_GEOMETRY_STRATA_RS.csv",stratum)
  export(out/"POL_V1_MOUNT_CASE_INCREMENTAL_NLL.csv",aligned)
  export(out/"POL_V1_CAUSAL_PRIOR_AUDIT.csv",audit_groups)
  report={"status":"N4B_POL_V1_INDEPENDENT_AUDIT_PASS",
    "original_source_artifact_sha":ARCHIVE_SHA,
    "source_sha":os.getenv("GITHUB_SHA"),
    "geometry_strata_count":len(stratum),"case_count":len(case_index),
    "new_feature_models":7,"mount_case_model_incremental_nll":aligned,
    "causal_prior_transfer":audit_groups,
    "scope":["physical oracle GT geometry not available in online EKF",
      "nominal heading information assumes diagonal 0.1m and 5deg prior",
      "s_LoS sign and port fractions are mathematically redundant",
      "large FFD vs ideal cosine mismatch means simple mount+heading approximation invalid",
      "R2 mount45 is out of training domain of R4/R5 mount0",
      "one corridor, one RF channel realization, no hardware Jones validation",
      "p(e|q) conditioned on same-packet q is not normalized p(z|state)",
      "R2 true causal prior transfer evaluated but trained geometry still oracle",
    ],"scientific_PASS":False}
  dump(out/"POL_V1_AUDITED_CASE_REVIEW.json",report)
  print("POL_REVIEW_FINAL "+json.dumps({"status":report["status"],
    "r2_strata":[r for r in stratum if r["case"].startswith("R2_aA")],
    "case_improvements":aligned,"prior":audit_groups},ensure_ascii=False),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=("pre","run"))
 p.add_argument("--out",required=True)
 p.add_argument("--input");p.add_argument("--audit")
 a=p.parse_args()
 raise SystemExit(audit(a.out) if a.phase=="pre" else mainrun(a.out,a.audit,a.input))
