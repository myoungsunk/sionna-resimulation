"""B0 gyro-bias prior variance sensitivity, 3/4-state controls.
TRUE gyro bias=0, packet stream frozen. This is a diagnostic, NOT a safe
procedure for unknown-bias deployment.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
SRC_BLOB={
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe"}
CASES=("R2_aA_m0","R2_aA_m45")
SIGMAS=(.001,.01,.03,.1)
def file_sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def gitblob(path):
 f=Path(path);h=hashlib.sha1()
 h.update(b"blob "+str(f.stat().st_size).encode()+b"\x00")
 with f.open("rb") as io0:
  for c in iter(lambda:io0.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def write(path,obj):Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 issues=[]
 if os.getenv("GITHUB_ACTIONS")!="true":issues.append("GITHUB_ONLY")
 rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if rev!=os.getenv("GITHUB_SHA"):issues.append("GIT_SHA_CHANGED")
 for path,expected in SRC_BLOB.items():
  f=ROOT/path
  if not f.is_file():issues.append("MISSING:"+path)
  elif gitblob(f)!=expected:issues.append("UNVERIFIED_BLOB:"+path)
 try:ast.parse((HERE/"b0_prior_sweep.py").read_text())
 except Exception as e:issues.append("SCRIPT_SYNTAX:"+str(e))
 wf=ROOT/".github/workflows/r5-b0-bias-prior-sweep.yml"
 if not wf.exists():issues.append("WORKFLOW_MISSING")
 else:
  s=wf.read_text();p=s.find("b0_prior_sweep.py --phase pre");q=s.find("b0_prior_sweep.py --phase run")
  if not 0<=p<q:issues.append("PREEXEC_NOT_FIRST")
 r={"decision":"GO" if not issues else "HOLD","git_sha":rev,"issues":issues,
    "input_RF_sha":RF_SHA,"input_R2_sha":R2_SHA,"status":"SOURCE_AUDIT"}
 write(out/"PRE_AUDIT.json",r)
 print("B0_PRIOR_PRE "+json.dumps(r),flush=True)
 return 0 if not issues else 2
def loadnpz(z,basename,np):
 candidates=[x for x in z.namelist() if x==basename or x.endswith("/"+basename)]
 if len(candidates)!=1:raise RuntimeError("NONUNIQUE_ZIP_MEMBER:"+basename)
 with np.load(io.BytesIO(z.read(candidates[0])),allow_pickle=False) as a:
  return {k:a[k].copy() for k in a.files}
def wrap(v):return (v+math.pi)%(2*math.pi)-math.pi
def evaluate(t,truth,z,controls,case,lut,x0,mode,sigma_dps,reference_gates):
 import numpy as np
 from p3_rf_adapter4 import R0
 from r2_bias_replay import predict_one,INITIAL_POSE_STD
 from core import gaussian_update
 p=np.diag([*(INITIAL_POSE_STD**2),math.radians(sigma_dps)**2])
 x=np.r_[x0,0.]
 est=np.zeros((len(t),4));cov=np.zeros((len(t),4,4));flags=[]
 def model(q):
  h,H=lut.model(q,case)
  if mode=="R_ONLY":return h[:1],H[:1,:]
  if mode=="S_ONLY":return h[1:],H[1:,:]
  return h,H
 for k in range(len(t)):
  if k:
   x,p=predict_one(x,p,float(controls["ds_odom"][k]),
          float(controls["dtheta_gyro"][k]),float(controls["dt_s"][k]))
  zk=z[k, :1] if mode=="R_ONLY" else z[k,1:] if mode=="S_ONLY" else z[k]
  RK=R0[:1,:1] if mode=="R_ONLY" else R0[1:,1:] if mode=="S_ONLY" else R0
  if mode=="J_FIXED_J4MASK" and not bool(reference_gates[k]):
   accepted=False
  else:
   gate=None if mode=="J_FIXED_J4MASK" else (6.6348966010212145 if mode in ("R_ONLY","S_ONLY") else 9.210340371976184)
   x,p,d=gaussian_update(x,p,zk,model,RK,gate_threshold=gate)
   accepted=bool(d["accepted"])
  flags.append(accepted)
  if np.linalg.eigvalsh(p).min()<=0:raise RuntimeError("POSTERIOR_NOT_PD")
  est[k]=x;cov[k]=p
 valid=t>=30
 e=est[valid,:3]-truth[valid,:3];e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
 c=cov[valid,:3,:3]
 heading_nees=e[:,2]**2/c[:,2,2]
 pose_nees=np.einsum("bi,bi->b",e,np.linalg.solve(c,e[...,None])[:,:,0])
 return est,cov,np.asarray(flags),{
    "heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
    "heading_NEES":float(heading_nees.mean()),
    "heading95":float(np.mean(heading_nees<=3.841458820694124)),
    "pose_NEES":float(pose_nees.mean()),
    "pose95":float(np.mean(pose_nees<=7.814727903251179)),
    "bias_final_dps":float(np.degrees(est[-1,3])),
    "bias_rmse_dps":float(np.degrees(np.sqrt(np.mean(est[valid,3]**2)))),
    "accepted":int(np.sum(np.asarray(flags)[valid]))}
def run(raw,r2,auditfile,out):
 import numpy as np
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 rec=json.loads(Path(auditfile).read_text())
 if rec.get("decision")!="GO" or rec.get("git_sha")!=os.getenv("GITHUB_SHA"):raise RuntimeError("AUDIT_HOLD")
 if file_sha(raw)!=RF_SHA or file_sha(r2)!=R2_SHA:raise RuntimeError("SOURCE_ZIP_CHANGED")
 sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 from r2_bias_replay import build_positive_bias_controls,METHODS
 from p3_rf_adapter4 import FrozenLut
 lut=FrozenLut(ROOT)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cases={q["id"]:q for q in manifest["cases"]}
 results=[];checks=[]
 with zipfile.ZipFile(raw) as za,zipfile.ZipFile(r2) as zb:
  if za.testzip() or zb.testzip():raise RuntimeError("ZIP_CRC_FAIL")
  index={(r["case"],r["channel"]):r for r in json.loads(za.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  for case in CASES:
   for ch in ("full","los"):
    q=index[(case,ch)]
    with np.load(io.BytesIO(za.read("P2_OUT/"+q["trace_file"])),allow_pickle=False) as a:
     t=a["t_s"].copy();truth=a["truth_for_offline_scoring_only"].copy()
     obs=np.column_stack([a["z_r_m"],a["z_s"]])
    baseline=loadnpz(zb,f"{case}_{ch}_B0_seed0_recursive.npz",np)
    gates=baseline["status"][:,list(METHODS).index("J4")]=="APPLIED"
    ctr,x0=build_positive_bias_controls(t,truth,"B0",0)
    modes=[("JOINT",s) for s in SIGMAS]+[("J_FIXED_J4MASK",.001),("J_FIXED_J4MASK",.1),("S_ONLY",.001),("S_ONLY",.1),("R_ONLY",.001),("R_ONLY",.1)]
    for mode,sigma in modes:
     xx,pp,acc,met=evaluate(t,truth,obs,ctr,cases[case],lut,x0,mode,sigma,gates)
     results.append({"case":case,"channel":ch,"mode":mode,"b_prior_sigma_dps":sigma,**met})
     if sigma==.1 and mode=="JOINT":
      jj=list(METHODS).index("J4");dx=xx-baseline["estimate"][:,jj,:]
      dx[:,2]=(dx[:,2]+np.pi)%(2*np.pi)-np.pi
      state_max=float(np.max(abs(dx)))
      P_max=float(np.max(abs(pp-baseline["covariance"][:,jj])))
      diff=int(np.sum(acc!=gates))
      if state_max>1e-6 or P_max>1e-6 or diff:
       raise RuntimeError("BASELINE_REPLAY_FAILED:"+str((state_max,P_max,diff)))
      checks.append({"case":case,"channel":ch,"R0_state_max_diff":state_max,
          "R0_cov_max_diff":P_max,"gate_differences":diff,"strict_1e9":max(state_max,P_max)<=1e-9})
    print("B0_PRIOR_CASE "+json.dumps({"case":case,"channel":ch,
       "joint_sigma":{str(k):next(r["heading_rmse_deg"] for r in results
                       if r["case"]==case and r["channel"]==ch and r["mode"]=="JOINT" and r["b_prior_sigma_dps"]==k)
                      for k in SIGMAS}}),flush=True)
 with (out/"B0_PRIOR_SWEEP_METRICS.csv").open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 final={"schema":"B0_4STATE_BIAS_PRIOR_SENSITIVITY_WITH_JOINT_S_RANGE_FROZEN_GATE_V1",
    "status":"B0_PRIOR_GRID_AUDITED_COMPLETE","n_rows":len(results),
    "original_R0_checks":checks,
    "full_mount0":[r for r in results if r["case"]=="R2_aA_m0" and r["channel"]=="full"],
    "full_mount45":[r for r in results if r["case"]=="R2_aA_m45" and r["channel"]=="full"],
    "warnings":["Very tight bias prior exploits known B0 truth; no unknown-bias deployment guarantee",
                "Fixed historical J4 gate schedule is retrospective diagnostic, not a new online policy",
                "Bias prior affects covariance and gating in addition to bias mean",
                "Only one corridor and one sensor seed, scientific_PASS=false"],"scientific_PASS":False}
 write(out/"B0_PRIOR_FINAL.json",final)
 print("B0_PRIOR_FINAL "+json.dumps({"status":final["status"],"focus_mount0":final["full_mount0"],
            "focus_mount45":final["full_mount45"]}),flush=True)
 return 0
def main():
 p=argparse.ArgumentParser();p.add_argument("--phase",choices=("pre","run"),required=True)
 p.add_argument("--out",required=True);p.add_argument("--raw");p.add_argument("--r2");p.add_argument("--audit")
 a=p.parse_args()
 return audit(a.out) if a.phase=="pre" else run(a.raw,a.r2,a.audit,a.out)
if __name__=="__main__":raise SystemExit(main())
