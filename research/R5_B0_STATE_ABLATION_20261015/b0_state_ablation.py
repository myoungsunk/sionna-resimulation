"""B0-only 3-state (bias structurally fixed) vs 4-state (bias estimated)
on the SAME validated R2 archived recursive trajectories.
No model fit, filtering change or reinterpretation of historical output.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
BLOBS={
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_score.py":"03a6616c082788a0d796458ca505964843fe897f",
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d"}
CASES=("R2_aA_m0","R2_aA_m45")
CHANNELS=("full","los")
METHODS=("DR3","DR4","S3","S4","J3","J4","SR3","SR4")
PAIR=(("DR3","DR4"),("S3","S4"),("J3","J4"),("SR3","SR4"))
def readsha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def gitblob(path):
 p=Path(path);h=hashlib.sha1()
 h.update(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def save(path,doc):Path(path).write_text(json.dumps(doc,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errs=[]
 if os.getenv("GITHUB_ACTIONS")!="true":errs.append("ACTION_REQUIRED")
 git=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if git!=os.getenv("GITHUB_SHA"):errs.append("GIT_SHA_MISMATCH")
 for path,sha in BLOBS.items():
  f=ROOT/path
  if not f.exists():errs.append("FROZEN_SOURCE_MISSING:"+path)
  elif gitblob(f)!=sha:errs.append("SOURCE_CHANGED:"+path)
 try:ast.parse((HERE/"b0_state_ablation.py").read_text())
 except Exception as e:errs.append("SCRIPT_SYNTAX:"+str(e))
 wf=ROOT/".github/workflows/r5-b0-bias-state-ablation.yml"
 if not wf.is_file():errs.append("WORKFLOW_MISSING")
 elif not(0<=wf.read_text().find("b0_state_ablation.py --phase pre")<
        wf.read_text().find("b0_state_ablation.py --phase run")):
  errs.append("WF_AUDIT_ORDER")
 doc={"decision":"GO" if not errs else "HOLD","git_sha":git,"errors":errs,
      "RF_zip_SHA":RF_SHA,"R2_zip_SHA":R2_SHA,
      "state_contract":"3state no b, 4state b estimated; same B0 true bias=0",
      "not_a_conclusive_causal_attribution":True,"scientific_PASS":False}
 save(out/"PRE_AUDIT.json",doc)
 print("B0_STATE_PRE "+json.dumps({"decision":doc["decision"],"errors":errs}),flush=True)
 return 0 if not errs else 2
def fetch_npz(z,basename,np):
 match=[x for x in z.namelist() if x==basename or x.endswith("/"+basename)]
 if len(match)!=1:raise RuntimeError("ARCHIVE_MEMBER_MISSING_OR_DUP:"+basename)
 with np.load(io.BytesIO(z.read(match[0])),allow_pickle=False) as obj:
  return {k:obj[k].copy() for k in obj.files}
def wrap(np,x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def run(raw,r2,receipt,out):
 import numpy as np
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 audit=json.loads(Path(receipt).read_text())
 if audit["decision"]!="GO" or audit["git_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("PREAUDIT_NOT_GO")
 if readsha(raw)!=RF_SHA or readsha(r2)!=R2_SHA:
  raise RuntimeError("ARCHIVE_SHA_BAD")
 with zipfile.ZipFile(raw) as z0,zipfile.ZipFile(r2) as z1:
  if z0.testzip() or z1.testzip():raise RuntimeError("ZIP_CRC_FAIL")
  entries=json.loads(z0.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  index={(x["case"],x["channel"]):x for x in entries["per_case"]}
  rows=[];comp=[]
  for case in CASES:
   for ch in CHANNELS:
    m=index[(case,ch)];rawbytes=z0.read("P2_OUT/"+m["trace_file"])
    if hashlib.sha256(rawbytes).hexdigest()!=m["trace_sha256"]:
     raise RuntimeError("FROZEN_RF_TRACE_SHA_CHANGED")
    with np.load(io.BytesIO(rawbytes),allow_pickle=False) as d:
     t=d["t_s"].copy();truth=d["truth_for_offline_scoring_only"].copy();ids=d["pose_id"].copy()
    state=fetch_npz(z1,f"{case}_{ch}_B0_seed0_recursive.npz",np)
    if not(np.array_equal(state["t_s"],t) and np.array_equal(state["pose_id"],ids)
          and list(state["names"])==list(METHODS)):raise RuntimeError("REPLAY_ID_MISMATCH")
    used=t>=30
    def score(name):
     j=METHODS.index(name);isfour=name.endswith("4")
     mu=state["estimate"][:,j];P=state["covariance"][:,j]
     e=mu[used,:3]-truth[used,:3];e[:,2]=wrap(np,e[:,2])
     cp=P[used,:3,:3]
     if np.min(np.linalg.eigvalsh(cp))<=0:raise RuntimeError("POSE_COV_INVALID")
     nh=e[:,2]**2/cp[:,2,2]
     ne=np.einsum("bi,bi->b",e,np.linalg.solve(cp,e[...,None])[:,:,0])
     result={"case":case,"channel":ch,"method":name,"states":4 if isfour else 3,
       "frames":int(used.sum()),"heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
       "heading_signed_mean_deg":float(np.degrees(np.mean(e[:,2]))),
       "heading_nees":float(np.mean(nh)),"heading95":float(np.mean(nh<=3.841458820694124)),
       "xy_rmse_m":float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
       "pose_nees":float(np.mean(ne)),"pose95":float(np.mean(ne<=7.814727903251179)),
       "gate_applied":int(np.sum(state["status"][used,j]=="APPLIED")),
       "gate_rejected":int(np.sum(state["status"][used,j]=="REJECT")),
       "bias_final_dps":float(np.degrees(mu[-1,3])) if isfour else None,
       "bias_rmse_dps":float(np.degrees(np.sqrt(np.mean(mu[used,3]**2)))) if isfour else None}
     return result,e[:,2]
    pairscores={}
    for name in METHODS:
     result,err=score(name);rows.append(result);pairscores[name]=(result,err)
    for first,second in PAIR:
     rowa,e3=pairscores[first];rowb,e4=pairscores[second]
     comp.append({"case":case,"channel":ch,"family":first[:-1],
       "heading_rmse_3state_deg":rowa["heading_rmse_deg"],
       "heading_rmse_4state_deg":rowb["heading_rmse_deg"],
       "four_minus_three_rmse_deg":rowb["heading_rmse_deg"]-rowa["heading_rmse_deg"],
       "three_to_four_heading_error_delta_RMS_deg":float(np.degrees(np.sqrt(np.mean((e4-e3)**2)))),
       "three_to_four_pose_nees_difference":rowb["pose_nees"]-rowa["pose_nees"],
       "gate_accepted_three":rowa["gate_applied"],
       "gate_accepted_four":rowb["gate_applied"],
       "four_state_spurious_final_bias_dps":rowb["bias_final_dps"]})
    print("B0_STATE_CASE "+json.dumps({"case":case,"channel":ch,
       "J3":pairscores["J3"][0]["heading_rmse_deg"],
       "J4":pairscores["J4"][0]["heading_rmse_deg"],
       "S3":pairscores["S3"][0]["heading_rmse_deg"],
       "S4":pairscores["S4"][0]["heading_rmse_deg"]}),flush=True)
  for name,records in (("B0_STATE_METRICS.csv",rows),("B0_STATE_COMPARISONS.csv",comp)):
   with (out/name).open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
  focus=[x for x in comp if x["channel"]=="full" and x["family"] in ("S","J","SR")]
  result={"schema":"R5_B0_3STATE_4STATE_SJ_SR_FROZEN_V1",
    "status":"B0_STRUCTURAL_BIAS_ABLATION_REPRODUCED",
    "case_channel_count":4,"metric_rows":len(rows),"paired_comparisons":len(comp),
    "focus_full_B0":focus,"warnings":["Not a strict causal separation: adding b state changes prediction uncertainty and RF gates",
        "Offline evaluation B0 fixed true gyro bias zero; 4state bias is freely estimated",
        "One corridor, one seed, time points correlated, source is original validated R2 replay"],
    "scientific_PASS":False}
  save(out/"B0_STATE_FINAL.json",result)
  print("B0_STATE_FINAL "+json.dumps(result),flush=True)
 return 0
def main():
 a=argparse.ArgumentParser()
 a.add_argument("--phase",required=True,choices=["pre","run"])
 a.add_argument("--out",required=True)
 a.add_argument("--raw");a.add_argument("--r2");a.add_argument("--audit")
 p=a.parse_args()
 return pre(p.out) if p.phase=="pre" else run(p.raw,p.r2,p.audit,p.out)
if __name__=="__main__":raise SystemExit(main())
