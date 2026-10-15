"""N1 L0/L1/L2 full physical Hard/Soft recursive experiment.

Extends the already audited B0 experiment WITHOUT re-tuning G0/G5 features,
classifier probabilities, policy thresholds, R0, geometry, Q or original RF.
R2 test truth enters ONLY Sensor-v2 control generator and independent scoring.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PHY=ROOT/"research/PHYSICS_RS_STAGED_20261015/code"
R2=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
B0CODE=ROOT/"research/R5_FULLRF_B0_GATES_20261015"
N0_SHA="aade786b83357086c9e645fa9b87467a869289aa93040e3b48410f44af2d08fb"
RAW_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
CASE_IDS=("R2_aA_m0","R2_aA_m45")
BIAS_DPS={"L0":.01,"L1":.05,"L2":.20}
PINNED={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
"research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py":"24b7b0103a232662afaf5b1b79bfb542aa7123db",
"research/PHYSICS_RS_STAGED_20261015/code/features.py":"c556da153739aaf99d2558c84c1a515c3da41a97",
"research/PHYSICS_RS_STAGED_20261015/code/stage_b.py":"b56d9e1459f2265fea83cd87cb411cd1cc4f3f9d",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
}
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob_sha(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def write(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 failures=[];identity={}
 if os.getenv("GITHUB_ACTIONS")!="true":failures.append("GITHUB_ACTIONS_REQUIRED")
 git=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if git!=os.getenv("GITHUB_SHA"):failures.append("GIT_SHA_CHANGED")
 for name,expected in PINNED.items():
  path=ROOT/name
  if not path.is_file():failures.append("MISSING_PINNED:"+name)
  else:
   got=blob_sha(path);identity[name]=got
   if got!=expected:failures.append("PINNED_CHANGED:"+name)
 try:
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  metas={r["path"]:r for r in manifest["assets"]}
  assets=[p for c in manifest["cases"] for p in (c["full_path"],c["los_path"],c["samples_path"])]
  assets.append("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy")
  for name in assets:
   f=ROOT/name
   if not f.is_file():failures.append("RAW_MISSING:"+name)
   elif name not in metas or sha_file(f)!=metas[name]["sha256"]:
    failures.append("RAW_HASH_CHANGED:"+name)
 except Exception as e:failures.append("RAW_AUDIT_EXCEPTION:"+str(e))
 try:ast.parse((HERE/"n1_bias_policies.py").read_text())
 except Exception as e:failures.append("SOURCE_PARSE:"+repr(e))
 wf=ROOT/".github/workflows/r5-n0n3-n1.yml"
 if not wf.is_file():failures.append("WORKFLOW_MISSING")
 else:
  w=wf.read_text()
  first=w.find("n1_bias_policies.py --phase pre");test=w.find("n1_bias_policies.py --phase test");run=w.find("n1_bias_policies.py --phase run")
  if not(0<=first<test<run and "if: always()" in w and "actions: read" in w):
   failures.append("BAD_AUDIT_FIRST_WORKFLOW")
 record={"stage":"N1","decision":"GO" if not failures else "HOLD",
     "commit":git,"source_blobs":identity,"raw_input_count":len(assets) if "assets" in locals() else 0,
     "original_R2_SHA":R2_SHA,"original_RF_SHA":RAW_SHA,"N0_evidence_SHA":N0_SHA,
     "bias_levels":BIAS_DPS,"errors":failures,"scientific_PASS":False}
 write(out/"N1_PRE_AUDIT.json",record)
 print("N1_PRE "+json.dumps({"decision":record["decision"],"errors":failures}),flush=True)
 return 0 if not failures else 2
def readzip(path,digest):
 if sha_file(path)!=digest:raise RuntimeError("EVIDENCE_ARCHIVE_SHA_MISMATCH:"+str(path))
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ZIP_CRC_FAILED")
 return z
def member(z,basename):
 ms=[m for m in z.namelist() if m==basename or m.endswith("/"+basename)]
 if len(ms)!=1:raise RuntimeError("ZIP_MEMBER_NOT_UNIQUE:"+basename)
 return ms[0]
def verify_n0(path):
 with readzip(path,N0_SHA) as z:
  j=json.loads(z.read(member(z,"N0_RECONCILIATION.json")))
  if j["status"]!="N0_SCOPED_GO_POSE_NEES_NOT_NUMERICALLY_IDENTICAL":
   raise RuntimeError("N0_APPROVAL_NOT_SCOPED")
  if j.get("historical_pose_nees_strict_parity_PASS") is not False:
   raise RuntimeError("N0_UNEXPECTEDLY_PROMOTED_NUMERIC_PARITY")
 return True
def setup():
 import numpy as np
 import pandas as pd
 sys.path.insert(0,str(PHY))
 sys.path.insert(0,str(B0CODE))
 sys.path.insert(0,str(R2))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 return np,pd
def test():
 np,pd=setup()
 from r5_b0_hard_soft import unit_tests,VARIANTS
 from r2_bias_replay import BIAS_LEVELS,build_positive_bias_controls
 if any(BIAS_LEVELS[k]!=v for k,v in BIAS_DPS.items()):
  raise RuntimeError("BIAS_LEVEL_UNIT_MISMATCH")
 if "SOFT_G5_MEAN_RS" not in VARIANTS or "HARD_S_G5_p50_RANDOM_MATCH" not in VARIANTS:
  raise RuntimeError("MISSING_ABLATION_ARM")
 unit_tests()
 print("N1_UNIT_PASS "+json.dumps({"bias_levels":BIAS_DPS,"candidate_arms":len(VARIANTS)}),flush=True)
 return 0
def score_saved(np,z,name,t,truth,bias):
 from r5_b0_hard_soft import score_one
 from r2_bias_replay import METHODS
 j=list(METHODS).index(name)
 payload={"estimate":z["estimate"][:,j,:],"covariance":z["covariance"][:,j,:,:],
          "status":z["status"][:,j]}
 payload["risk_score"]=np.full(len(t),float("nan"))
 return score_one(np,t,truth,bias,payload)
def run(out,pre,n0,raw,r2archive):
 np,pd=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 pre_rec=json.loads(Path(pre).read_text())
 if pre_rec["decision"]!="GO" or pre_rec["commit"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("SOURCE_AUDIT_NOT_GO")
 verify_n0(n0)
 from r5_b0_hard_soft import prepare_features,fit_models,filtered_case,score_one,VARIANTS
 from r2_bias_replay import build_positive_bias_controls,METHODS
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 case_meta={c["id"]:c for c in manifest["cases"]}
 data,lut=prepare_features(np,pd,manifest)
 predicted,oracle,meta,split=fit_models(np,pd,data)
 if split["heldout_route"]!="R2" or split["train_routes"]!=["R4","R5"]:
  raise RuntimeError("ORACLE_ROUTE_LEAK")
 index=predicted.set_index(["case","channel","pose_id"])
 scores=[];parities=[];primary=[]
 with readzip(raw,RAW_SHA) as zf,readzip(r2archive,R2_SHA) as zr:
  rf_entries=json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  original={(r["case"],r["channel"]):r for r in rf_entries["per_case"]}
  for condition,true_bias in BIAS_DPS.items():
   for case in CASE_IDS:
    for channel in ("full","los"):
     entry=original[(case,channel)]
     rawbytes=zf.read("P2_OUT/"+entry["trace_file"])
     if hashlib.sha256(rawbytes).hexdigest()!=entry["trace_sha256"]:
      raise RuntimeError("RF_NPZ_SHA_DIFFERENCE")
     with np.load(io.BytesIO(rawbytes),allow_pickle=False) as p:
      t=p["t_s"].copy();ids=p["pose_id"].copy()
      truth=p["truth_for_offline_scoring_only"].copy()
      measurements=np.column_stack([p["z_r_m"],p["z_s"]])
     idkeys=pd.MultiIndex.from_tuples([(case,channel,int(k)) for k in ids],names=index.index.names)
     quality={key:index.loc[idkeys,key].to_numpy(float) for key in index.columns}
     ctrl,initial=build_positive_bias_controls(t,truth,condition,seed=0)
     refname=case+"_"+channel+"_"+condition+"_seed0_recursive.npz"
     with np.load(io.BytesIO(zr.read(member(zr,refname))),allow_pickle=False) as ref:
      arch={k:ref[k].copy() for k in ref.files}
     if not(np.array_equal(arch["t_s"],t) and np.array_equal(arch["pose_id"],ids)):
      raise RuntimeError("ARCHIVED_RECURSIVE_TIME_ID_MISMATCH")
     methods={}
     chosen=quality["PBAD_G5"]>.5
     rng=np.random.default_rng(20261015+(list(BIAS_DPS).index(condition)*131)+int(case.endswith("m45"))*37+int(channel=="los")*73)
     random_match=np.zeros(len(t),bool)
     random_match[rng.choice(len(t),size=int(chosen.sum()),replace=False)]=True
     for method in VARIANTS:
      payload=filtered_case(t,ctrl,measurements,case_meta[case],lut,initial,
                            quality,method,random_match)
      methods[method]=payload
      stat=score_one(np,t,truth,true_bias,payload)
      scores.append({"case":case,"mount_deg":case_meta[case]["mount_deg"],
         "channel":channel,"bias_level":condition,"true_bias_dps":true_bias,
         "method":method,**stat})
     # Preserve S4/SR4 baselines from the previously validated R2 artifact.
     for method in ("S4","SR4"):
      stat=score_saved(np,arch,method,t,truth,true_bias)
      scores.append({"case":case,"mount_deg":case_meta[case]["mount_deg"],
         "channel":channel,"bias_level":condition,"true_bias_dps":true_bias,
         "method":method,**stat})
     j=list(METHODS).index("J4")
     baseline=methods["R0_J4"]
     xdiff=baseline["estimate"]-arch["estimate"][:,j,:]
     xdiff[:,2]=(xdiff[:,2]+np.pi)%(2*np.pi)-np.pi
     dx=float(np.max(np.abs(xdiff)))
     dp=float(np.max(np.abs(baseline["covariance"]-arch["covariance"][:,j])))
     gate_diff=int(np.sum((baseline["status"]=="APPLIED")!=(arch["status"][:,j]=="APPLIED")))
     if dx>1e-6 or dp>1e-6 or gate_diff:
      raise RuntimeError("N1_BASELINE_NOT_REPRODUCED:"+str((case,channel,condition,dx,dp,gate_diff)))
     parities.append({"case":case,"channel":channel,"bias_level":condition,
       "R0_max_state_diff":dx,"R0_max_cov_diff":dp,
       "gate_diff":gate_diff,"strict_1e9":bool(max(dx,dp)<=1e-9)})
     np.savez_compressed(out/f"N1_{case}_{channel}_{condition}.npz",
       t_s=t,pose_id=ids,methods=np.asarray(VARIANTS),
       estimate=np.stack([methods[k]["estimate"] for k in VARIANTS],axis=1),
       covariance=np.stack([methods[k]["covariance"] for k in VARIANTS],axis=1),
       status=np.stack([methods[k]["status"] for k in VARIANTS],axis=1),
       risk_pbad=quality["PBAD_G5"],mean_bias_correction=quality["MU_G5"])
     print("N1_CASE "+json.dumps({"case":case,"channel":channel,"bias":condition,"parity_state":dx,
         "rows":len(VARIANTS)+2}),flush=True)
  expected={"L0":(4.3047,1.3487),"L1":(4.3257,1.3511),"L2":(4.3776,1.3610)}
  for k,(mount0,mount45) in expected.items():
   for case,val in (("R2_aA_m0",mount0),("R2_aA_m45",mount45)):
    found=next(x["heading_rmse_deg"] for x in scores if x["bias_level"]==k and
               x["case"]==case and x["channel"]=="full" and x["method"]=="SOFT_G5_RS")
    if abs(found-val)>.02:
     raise RuntimeError("LEGACY_PHYS_G5_C2_PARITY_FAIL:"+str((case,k,found,val)))
 def export(path,arr):
  with path.open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(arr[0]))
   w.writeheader();w.writerows(arr)
 export(out/"N1_ALL_BIAS_METHOD_METRICS.csv",scores)
 export(out/"N1_R0_PARITY.csv",parities)
 focus=[x for x in scores if x["channel"]=="full" and x["method"] in
   ("R0_J4","SOFT_G5_RS","SOFT_G5_MEAN","SOFT_G5_MEAN_RS",
    "HARD_ALL_G5_p50","HARD_S_G5_p50","HARD_S_G5_p75","S4","SR4","DR4")]
 final={"schema":"R5_N1_L0_L1_L2_RECURSIVE_PHYSICAL_POLICIES_V1",
  "status":"N1_BIAS_EXTENDED_TECHNICAL_PASS",
  "source_sha":os.getenv("GITHUB_SHA"),
  "original_frozen_R0_parity":parities,
  "n_metric_rows":len(scores),"n_traces":len(parities),
  "bias_levels":BIAS_DPS,"original_R0_Rs":.0081,
  "split":split,"candidate_models":list(VARIANTS),
  "primary_results":focus,
  "limitations":["B0 not re-evaluated (existing original B0 result)",
    "R2 held-out relative to R4/R5 training but same corridor",
    "Hard gate probabilities refer to |e_MP|>.1, not Heading harm",
    "RF/gate policy changes cause distinct posterior and acceptance schedules",
    "No calibrated complete pose uncertainty or independent scene test",
    "G3/G5 coherent-frequency features are research-only until hardware verified"],
  "scientific_PASS":False}
 write(out/"N1_FINAL.json",final)
 print("N1_FINAL "+json.dumps({"status":final["status"],
   "metric_rows":len(scores),"traces":len(parities),
   "full_results":[{"case":x["case"],"bias":x["bias_level"],"method":x["method"],
      "heading_rmse_deg":x["heading_rmse_deg"],"heading_nees":x["heading_nees_mean"],
      "pose_nees":x["pose_nees_mean"],"bias_rmse":x["bias_rmse_dps"]}
    for x in focus]}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=["pre","test","run"])
 p.add_argument("--out",required=False)
 p.add_argument("--audit");p.add_argument("--raw");p.add_argument("--r2");p.add_argument("--n0")
 a=p.parse_args()
 raise SystemExit(audit(a.out) if a.phase=="pre" else test() if a.phase=="test" else
                  run(a.out,a.audit,a.n0,a.raw,a.r2))
