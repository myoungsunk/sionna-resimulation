"""Inspect already archived N4-B results; no estimator/model retraining.
Verify artifact SHA/CRC and per-case, mount/anchor holdout predictions.
"""
import argparse,ast,collections,csv,gzip,hashlib,io,json,math,os,random,statistics,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
ARCHIVE_SHA="170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b"
BASE_CODE_BLOB="abd654dd9efde61fc7baffc350188b2a8b4904a3"
BASE_SOURCE_COMMIT="7d8d20c9a95364fb6a9ae7caa720b2b22019ecab"
def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()
def gitblob(path):
 f=Path(path);h=hashlib.sha1(b"blob "+str(f.stat().st_size).encode()+b"\0")
 with f.open("rb") as src:
  for a in iter(lambda:src.read(1<<20),b""):h.update(a)
 return h.hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 e=[];rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if os.environ.get("GITHUB_ACTIONS")!="true":e.append("GITHUB_ACTIONS_ONLY")
 if rev!=os.environ.get("GITHUB_SHA"):e.append("GIT_REV_MISMATCH")
 f=ROOT/"research/R5_N4B_20261015/n4b_rf_errors.py"
 if not f.exists() or gitblob(f)!=BASE_CODE_BLOB:e.append("ORIGINAL_N4B_AUDITED_CODE_CHANGED")
 try:ast.parse((HERE/"n4b_verify_report.py").read_text())
 except Exception as ex:e.append("SOURCE_AST_ERROR:"+str(ex))
 w=ROOT/".github/workflows/r5-n4b-report-verify.yml"
 if not w.exists():e.append("WORKFLOW_MISSING")
 else:
  t=w.read_text()
  if not(0<=t.find("n4b_verify_report.py --phase pre")<
         t.find("n4b_verify_report.py --phase run") and "if: always()" in t):
   e.append("WORKFLOW_AUDIT_ORDER")
 r={"decision":"GO" if not e else "HOLD","source_sha":rev,
    "input_artifact_sha":ARCHIVE_SHA,"N4B_original_code_sha":BASE_CODE_BLOB,"errors":e}
 save(out/"PRE_AUDIT.json",r)
 print("N4B_VERIFY_PRE "+json.dumps(r),flush=True)
 return 0 if not e else 2
def member(z,name):
 m=[x for x in z.namelist() if x==name or x.endswith("/"+name)]
 if len(m)!=1:raise RuntimeError("NOT_UNIQUE:"+name)
 return m[0]
def readcsv(z,name,gz=False):
 raw=z.read(member(z,name))
 f=(gzip.open(io.BytesIO(raw),"rt",encoding="utf8") if gz else io.StringIO(raw.decode()))
 with f:return list(csv.DictReader(f))
def avg(xs):return sum(xs)/len(xs) if xs else None
def execute(out,receipt,source):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(receipt).read_text())
 if a["decision"]!="GO" or a["source_sha"]!=os.environ.get("GITHUB_SHA"):
  raise RuntimeError("PRE_AUDIT_HOLD")
 if sha(source)!=ARCHIVE_SHA:raise RuntimeError("ARCHIVE_SHA_CHANGED")
 with zipfile.ZipFile(source) as z:
  if z.testzip():raise RuntimeError("ZIP_CRC_BAD")
  d=json.loads(z.read(member(z,"N4B_FINAL.json")))
  if d["status"]!="N4B_AUDITED_RESIDUAL_AND_LIKELIHOOD_COMPLETE":
   raise RuntimeError("ORIGINAL_N4B_INCOMPLETE")
  if d["source_sha"]!=BASE_SOURCE_COMMIT or d["n_full_observations"]!=9519:
   raise RuntimeError("N4B_SOURCE_MISMATCH")
  f=readcsv(z,"N4B_HELDOUT_LIKELIHOOD.csv")
  stats=readcsv(z,"N4B_EMPIRICAL_JOINT_RS.csv")
  full=[r for r in stats if r["channel"]=="full"]
  pred=readcsv(z,"N4B_OOF_PREDICTIONS.csv.gz",True)
  if len(pred)!=9519*9:raise RuntimeError("HELDOUT_MODEL_PREDICTIONS_COUNT")
  models=("R0","GLOBAL_JOINT","POWER_BIN_JOINT","SIMPLE_DIAG",
          "SIMPLE_JOINT","SIMPLE_G4","G5_RESEARCH_ONLY")
  cases=sorted(set(x["case"] for x in f))
  summary=[]
  for case in cases:
   entries={x["model"]:x for x in f if x["case"]==case}
   if not all(m in entries for m in models):raise RuntimeError("MISSING_MODEL_CASE:"+case)
   row={"case":case,"n":int(entries["R0"]["n"])}
   for m in models:
    row[m+"_nll"]=float(entries[m]["nll_mean"])
    row[m+"_cov95"]=float(entries[m]["chi2_95coverage"])
   row["G4_minus_R0_nll"]=row["SIMPLE_G4_nll"]-row["R0_nll"]
   row["G4_minus_SIMPLE_nll"]=row["SIMPLE_G4_nll"]-row["SIMPLE_JOINT_nll"]
   row["G5_minus_G4_nll"]=row["G5_RESEARCH_ONLY_nll"]-row["SIMPLE_G4_nll"]
   summary.append(row)
  # Pair the exact SAME independent holdout packets for model comparisons.
  baseline={}
  for r in pred:
   if r["model"] in ("SIMPLE_JOINT","SIMPLE_G4","G5_RESEARCH_ONLY","R0","GLOBAL_JOINT"):
    k=(r["case"],int(r["pose_id"]))
    baseline.setdefault(k,{})[r["model"]]=float(r["nll"])
  if len(baseline)!=9519 or any(len(x)!=5 for x in baseline.values()):
   raise RuntimeError("PAIRED_PREDICTION_NOT_COMPLETE")
  labels={}
  for r in pred:
   if r["model"]=="R0":
    k=(r["case"],int(r["pose_id"]))
    block=(r["case"],int(math.floor(float(r["x_eval"])/1.5)),
           int(math.floor(float(r["y_eval"])/1.5)))
    labels[k]=block
  index=collections.defaultdict(list)
  for k,x in baseline.items():index[labels[k]].append(x)
  blocks=list(index)
  if len(blocks)!=180:raise RuntimeError("SPATIAL_BLOCK_COUNT_CHANGED")
  def paired_boot(candidate,reference):
   bdiff=[]
   for b in blocks:
    bdiff.append((sum(x[candidate]-x[reference] for x in index[b]),len(index[b])))
   base=sum(x[0] for x in bdiff)/sum(x[1] for x in bdiff)
   rng=random.Random(20261015)
   sims=[]
   for i in range(700):
    ids=[rng.randrange(len(bdiff)) for _ in bdiff]
    sims.append(sum(bdiff[j][0] for j in ids)/sum(bdiff[j][1] for j in ids))
   sims.sort()
   return {"contrast":candidate+"-minus-"+reference,
      "NLL_mean_difference":base,
      "bootstrap95_CI_within_one_corridor":[sims[int(.025*len(sims))],sims[int(.975*len(sims))]],
      "block_count":len(blocks)}
  bootstrap=[paired_boot("SIMPLE_G4","SIMPLE_JOINT"),
             paired_boot("G5_RESEARCH_ONLY","SIMPLE_G4"),
             paired_boot("SIMPLE_G4","R0"),
             paired_boot("SIMPLE_G4","GLOBAL_JOINT")]
  meta={r["case"]:{
   "mu_r":float(r["mu_r_m"]),"mu_s":float(r["mu_s"]),
   "Vr":float(r["Vr_m2"]),"Vs":float(r["Vs"]),"Crs":float(r["C_rs_m"]),
   "rho":float(r["rho_rs"])} for r in full}
  outcome={"status":"N4B_CASE_REVIEW_TECHNICAL_PASS",
   "source_sha":os.environ["GITHUB_SHA"],
   "archive_sha256":ARCHIVE_SHA,
   "per_case_heldout_likelihood":summary,
   "empirical_full_residual":meta,
   "model_incremental_bootstrap":bootstrap,
   "site_test":d["site_persistence_test"],
   "time_strata":d["lag1_observed_time_strata"],
   "limitations":["Mount45 was absent from R4+R5 model training when R2 heldout",
     "Three routes overlap one physical multipath scene",
     "Same-packet features condition residual density, not normalized p(z|state)",
     "Spatial blocks share path/yaw geometry and do not establish stochastic site effects"],
   "scientific_PASS":False}
  save(out/"N4B_CASE_REVIEW.json",outcome)
  with (out/"N4B_CASE_NLL.csv").open("w",newline="",encoding="utf8") as f:
   w=csv.DictWriter(f,fieldnames=list(summary[0]))
   w.writeheader();w.writerows(summary)
  print("N4B_VERIFY_FINAL "+json.dumps({"status":outcome["status"],
    "per_case":summary,"R2_empirical":{k:v for k,v in meta.items() if k.startswith("R2")},
    "bootstrap":bootstrap}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=("pre","run"))
 p.add_argument("--out",required=True)
 p.add_argument("--audit");p.add_argument("--input")
 a=p.parse_args()
 raise SystemExit(pre(a.out) if a.phase=="pre" else execute(a.out,a.audit,a.input))
