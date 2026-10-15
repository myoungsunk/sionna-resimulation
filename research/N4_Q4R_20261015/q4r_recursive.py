"""Q4-R2: True recursive prior P-inflation pilot (all gates and posteriors recomputed).

No use of GT to calibrate P online. Fixed additive PSD perturbations are
experimental controls, NOT a learned independently validated calibration.
Includes R0, POWER_JOINT, J4/SR4, LoS guard, B0/L0/L1/L2, mount0/45.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
ART={
 "r1":"86dc05d64ddb2ddf5a688665f387b6d12346162491fa9435ecaecf6c8f1aefe9",
 "r2":"ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399",
 "rf":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "n4b":"170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b",
 "n4c":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9",
}
PINNED={
 "research/N4_Q4R_20261015/q4r_posthoc.py":"2c3a393228c31a4019f24896efb1cdf07925b4d1",
 "research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
}
# PSD additions are not selected using GT, and are fixed in code BEFORE running.
ADD={
 "RAW":(0,0,0,0),
 "Q_SMALL":(.02,.02,.2,.002),
 "Q_MEDIUM":(.05,.05,1.,.010),
 "Q_LARGE":(.10,.10,3.,.030),
}
ARMS_FULL=(("BASE_R0","RAW"),("BASE_R0","Q_SMALL"),("BASE_R0","Q_MEDIUM"),
 ("BASE_R0","Q_LARGE"),("BASE_R0","EIG_NARROW_10CM"),
 ("BASE_R0","EIG_PLUS_YAW1"),
 ("POWER_JOINT","RAW"),("POWER_JOINT","Q_SMALL"),
 ("POWER_JOINT","Q_MEDIUM"),("POWER_JOINT","EIG_NARROW_10CM"),
 ("POWER_JOINT","EIG_PLUS_YAW1"))
ARMS_LOS=(("BASE_R0","RAW"),("BASE_R0","Q_MEDIUM"),
 ("BASE_R0","EIG_NARROW_10CM"),("BASE_R0","EIG_PLUS_YAW1"))
CASES=("R2_aA_m0","R2_aA_m45")
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
METHODS=("J4","SR4")

def hfile(f):
 h=hashlib.sha256()
 with open(f,"rb") as inp:
  for b in iter(lambda:inp.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def gitblob(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def checked(f,expected):
 if hfile(f)!=expected:raise RuntimeError("FROZEN_ARTIFACT_SHA_MISMATCH:"+str(f))
 z=zipfile.ZipFile(f)
 if z.testzip():raise RuntimeError("FROZEN_ARCHIVE_BAD_CRC")
 return z
def member(z,name):
 matches=[q for q in z.namelist() if q==name or q.endswith("/"+name)]
 if len(matches)!=1:raise RuntimeError("ARCHIVE_MEMBER_MISSING_OR_DUP:"+name)
 return matches[0]
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("RUNNER_REQUIRED")
 if rev!=os.getenv("GITHUB_SHA"):errors.append("NOT_EXACT_SOURCE_COMMIT")
 for p,h in PINNED.items():
  if h.startswith("__"):errors.append("PINNED_BLOB_NOT_REPLACED:"+p);continue
  f=ROOT/p
  if not f.exists():errors.append("PINNED_ORIGINAL_MISSING:"+p)
  elif gitblob(f)!=h:errors.append("FROZEN_ORIGINAL_CHANGED:"+p)
 try:ast.parse((HERE/"q4r_recursive.py").read_text())
 except Exception as e:errors.append("SELF_CODE_SYNTAX:"+repr(e))
 wf=ROOT/".github/workflows/n4q-q4r-r2.yml"
 if not wf.exists():errors.append("WF_MISSING")
 else:
  w=wf.read_text()
  seq=["q4r_recursive.py --phase pre","q4r_recursive.py --phase test",
       "q4r_recursive.py --phase run"]
  if not all(x in w for x in seq) or not w.index(seq[0])<w.index(seq[1])<w.index(seq[2]):
   errors.append("PREAUDIT_NOT_FIRST")
  if "if: always()" not in w or "actions: read" not in w:errors.append("ARTIFACT_MISSING")
 doc={"decision":"GO" if not errors else "HOLD","source_sha":rev,
  "original_archive_digests":ART,"predeclared_PSD_updates":ADD,
  "source_original_sha":PINNED,"errors":errors}
 save(out/"Q4R2_PRE_AUDIT.json",doc)
 print("Q4R2_PRE "+json.dumps({"decision":doc["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2
def setup():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
   str(ROOT/"research/R5_N4C_20261015"),
   str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"),
   str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src")
 ]
 import n4c_joint_sr4 as parent
 from r2_bias_replay import build_positive_bias_controls,predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD,METHODS as original_names
 from p3_rf_adapter4 import FrozenLut
 return np,pd,parent,build_positive_bias_controls,predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD,original_names,FrozenLut
def repair(np,P,kind):
 P=(P+P.T)*.5
 if kind=="RAW":return P.copy()
 if kind in ADD:
  xyz=ADD[kind]
  dv=np.array([xyz[0]**2,xyz[1]**2,math.radians(xyz[2])**2,
               math.radians(xyz[3])**2])
  return P+np.diag(dv)
 if kind not in ("EIG_NARROW_10CM","EIG_PLUS_YAW1"):raise ValueError(kind)
 cond=P[:2,:2]-np.outer(P[:2,2],P[2,:2])/P[2,2]
 val,vec=np.linalg.eigh((cond+cond.T)*.5)
 u=np.r_[vec[:,0],0,0]
 C=P+(.1**2)*np.outer(u,u)
 if kind=="EIG_PLUS_YAW1":
  C+=np.diag([0,0,math.radians(1.)**2,math.radians(.01)**2])
 return (C+C.T)*.5
def test():
 np,pd,parent,*rest=setup()
 rng=np.random.default_rng(17)
 for i in range(25):
  A=rng.normal(size=(4,4))
  p=A@A.T*.001+np.diag([.005,.005,.001,.00005])
  for kind in set(k for _,k in ARMS_FULL+ARMS_LOS):
   C=repair(np,p,kind)
   assert np.linalg.eigvalsh(C).min()>0
   assert np.linalg.eigvalsh(C-p).min()>-1e-12
 print("Q4R2_UNIT_PASS "+json.dumps({"seed":17,"SPD_tests":25,
   "cal_types":list(set(k for _,k in ARMS_FULL+ARMS_LOS))}),flush=True)
 return 0
def simulate(np,parent,controls,x0,obs,t,casemeta,lut,q,method,
             rfmodel,pol,original_source):
 from r2_bias_replay import predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD
 n=len(t)
 x=np.r_[x0,0.];P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 prex=np.zeros((n,4));preP=np.zeros((n,4,4))
 postx=np.zeros((n,4));postP=np.zeros((n,4,4))
 status=np.empty(n,"<U24");nis=np.full(n,np.nan);scale=np.ones(n)
 for i in range(n):
  if i:
   x,P=predict_one(x,P,float(controls["ds_odom"][i]),
     float(controls["dtheta_gyro"][i]),float(controls["dt_s"][i]))
   P=repair(np,P,pol)
  prex[i]=x;preP[i]=P
  # Frozen N4C update: normalized R0/POWER policy, original gate.
  xx,PP,st,ni,robust=parent.perform_update(
    np,x,P,obs[i],rfmodel,q[i],method,casemeta,lut,"natural")
  if not np.isfinite(xx).all() or not np.isfinite(PP).all() or \
      np.linalg.eigvalsh(PP).min()<=0:
   raise RuntimeError("Q4R2_INVALID_POSTERIOR:"+str((method,rfmodel,pol,i)))
  postx[i]=x=xx;postP[i]=P=PP
  status[i]=st;nis[i]=ni;scale[i]=robust
 return {"prior_x":prex,"prior_P":preP,
   "state":postx,"cov":postP,"status":status,"nis":nis,"robust_R_scale":scale}
def execute(out,pre,r1file,rf,r2,n4b,n4c):
 np,pd,parent,controls_fn,predict,POSESTD,BSTD,original_names,FrozenLut=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 preaudit=json.loads(Path(pre).read_text())
 if preaudit["decision"]!="GO" or preaudit["source_sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("Q4R2_SOURCE_AUDIT_HOLD")
 scores=[];parity=[]
 with checked(r1file,ART["r1"]) as zr1, checked(rf,ART["rf"]) as zrf, \
    checked(r2,ART["r2"]) as zref,checked(n4b,ART["n4b"]) as zb,checked(n4c,ART["n4c"]) as zc:
  r1meta=json.loads(zr1.read(member(zr1,"Q4R1_FINAL.json")))
  if r1meta["status"]!="Q4R1_POSTHOC_PILOT_COMPLETE" or r1meta["source_audit_training_eligible"]:
   raise RuntimeError("UPSTREAM_TRAIN_STATUS_MISREPRESENTED")
  quality=parent.parse_n4b_prediction(np,pd,zb)
  lut=FrozenLut(ROOT)
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  case_meta={c["id"]:c for c in manifest["cases"]}
  traces={(q["case"],q["channel"]):q for q in
       json.loads(zrf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  for case in CASES:
   for channel in ("full","los"):
    src=traces[(case,channel)]
    raw=zrf.read("P2_OUT/"+src["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=src["trace_sha256"]:
     raise RuntimeError("RF_TRACE_SHA_CHANGED")
    with np.load(io.BytesIO(raw),allow_pickle=False) as a:
     t=a["t_s"].copy();ids=a["pose_id"].copy()
     truth=a["truth_for_offline_scoring_only"].copy()
     z=np.column_stack([a["z_r_m"],a["z_s"]])
    q=[quality[(case,int(pid))] for pid in ids] if channel=="full" else [{} for _ in ids]
    for bias,bias_dps in BIAS.items():
     controls,x0=controls_fn(t,truth,bias,seed=0)
     with np.load(io.BytesIO(zref.read(member(zref,f"{case}_{channel}_{bias}_seed0_recursive.npz"))),
         allow_pickle=False) as f:
      ref={k:f[k].copy() for k in f.files}
     for method in METHODS:
      arms=ARMS_FULL if channel=="full" else ARMS_LOS
      saved={}
      for rfmodel,pkind in arms:
       key=(rfmodel,pkind)
       state=simulate(np,parent,controls,x0,z,t,case_meta[case],lut,q,method,
         rfmodel,pkind,ref)
       saved[key]=state
       m=parent.score(np,state,t,truth,bias_dps)
       scores.append({"case":case,"channel":channel,"bias":bias,"method":method,
         "rfmodel":rfmodel,"prior_correction":pkind,"evaluation":"real_recursive_pilot",
         **m})
       if pkind=="RAW":
        if rfmodel=="BASE_R0":
         ii=list(original_names).index(method)
         xx=ref["estimate"][:,ii,:];PP=ref["covariance"][:,ii,:,:]
         frozen_gates=(ref["status"][:,ii]=="APPLIED")
        else:
         ar=zc.read(member(zc,f"N4C_{case}_{channel}_{bias}_{method}.npz"))
         with np.load(io.BytesIO(ar),allow_pickle=False) as f:
          k=np.flatnonzero((f["policies"]=="POWER_JOINT")&(f["gate_modes"]=="natural"))
          if len(k)!=1:raise RuntimeError("POWER_JOINT_REF_MISSING")
          ii=int(k[0])
          xx=f["estimate"][:,ii,:].copy();PP=f["covariance"][:,ii,:,:].copy()
          frozen_gates=(f["status"][:,ii]=="APPLIED")
        dx=state["state"]-xx;dx[:,2]=(dx[:,2]+np.pi)%(2*np.pi)-np.pi
        maxx=float(np.max(np.abs(dx)));maxP=float(np.max(np.abs(state["cov"]-PP)))
        mismatches=int(np.sum((state["status"]=="APPLIED")!=frozen_gates))
        if maxx>1e-6 or maxP>1e-6 or mismatches:
         raise RuntimeError("Q4R2_BASELINE_PARITY_FAIL:"+str((case,channel,bias,method,rfmodel,maxx,maxP,mismatches)))
        parity.append({"case":case,"channel":channel,"bias":bias,"method":method,
          "rfmodel":rfmodel,"state_max":maxx,"cov_max":maxP,"gate_mismatches":mismatches,
          "strict_1e9":bool(max(maxx,maxP)<1e-9)})
      keys=list(saved)
      np.savez_compressed(out/f"Q4R2_{case}_{channel}_{bias}_{method}.npz",
        t_s=t,pose_id=ids,policy=np.array([x[0] for x in keys]),
        correction=np.array([x[1] for x in keys]),
        prior_x=np.stack([saved[k]["prior_x"] for k in keys],axis=1),
        prior_P=np.stack([saved[k]["prior_P"] for k in keys],axis=1),
        estimate=np.stack([saved[k]["state"] for k in keys],axis=1),
        covariance=np.stack([saved[k]["cov"] for k in keys],axis=1),
        status=np.stack([saved[k]["status"] for k in keys],axis=1),
        nis=np.stack([saved[k]["nis"] for k in keys],axis=1))
      print("Q4R2_CASE "+json.dumps({"case":case,"channel":channel,"bias":bias,
        "method":method,"arms":len(arms)}),flush=True)
 with (out/"Q4R2_RECURSIVE_ALL.csv").open("w",newline="",encoding="utf8") as f:
  writer=csv.DictWriter(f,fieldnames=list(scores[0]))
  writer.writeheader();writer.writerows(scores)
 with (out/"Q4R2_BASELINE_PARITY.csv").open("w",newline="",encoding="utf8") as f:
  writer=csv.DictWriter(f,fieldnames=list(parity[0]))
  writer.writeheader();writer.writerows(parity)
 rec={"stage":"Q4-R2","status":"Q4R2_FIXED_PRIOR_CORRECTIONS_RECURSIVE_PILOT_COMPLETE",
  "source_commit":os.environ["GITHUB_SHA"],"n_arms":len(scores),
  "n_exact_source_parity":len(parity),"original_source_archive_sha256":ART,
  "arm_definition":{"full":ARMS_FULL,"los":ARMS_LOS},
  "full_L2": [s for s in scores if s["channel"]=="full" and s["bias"]=="L2"],
  "scientific_PASS":False,
  "warnings":["Zero-fit PSD corrections: NO independent posterior calibration training source",
    "No hyperparameter selection on R2 permitted",
    "Full RF uses same scene and gyro noise seed0 for all arms",
    "R2 is a repeatedly inspected retrospective pilot, not hidden final test",
    "The model changes next-step covariance and gate; not a valid comparison with R1 posthoc coverage alone",
    "POWER_JOINT depends on same packet first-path power in the learned quality model",
    "No new Full RF scenes or R4/R5 authenticated dynamic controls have been added"]}
 save(out/"Q4R2_FINAL.json",rec)
 print("Q4R2_FINAL "+json.dumps({"status":rec["status"],"arms":len(scores),
    "parity":len(parity),"full_L2":[{"mount":s["case"],"method":s["method"],
     "RF":s["rfmodel"],"prior":s["prior_correction"],"heading":s["heading_rmse_deg"],
     "bias":s["bias_rmse_dps"],"pose_NEES":s["pose_nees"],
     "pose95":s["pose_95coverage"],"heading95":s["heading_95coverage"]} for s in rec["full_L2"]]},
    ensure_ascii=False),flush=True)
 return 0
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("pre","test","run"),required=True)
 ap.add_argument("--out");ap.add_argument("--audit");ap.add_argument("--r1")
 ap.add_argument("--r2");ap.add_argument("--rf");ap.add_argument("--n4b");ap.add_argument("--n4c")
 a=ap.parse_args()
 return audit(a.out) if a.phase=="pre" else test() if a.phase=="test" else \
   execute(a.out,a.audit,a.r1,a.rf,a.r2,a.n4b,a.n4c)
if __name__=="__main__":raise SystemExit(main())
