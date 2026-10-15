"""Q4-R0/R1: frozen source audit and zero-fit, posthoc prior covariance stress.

Do NOT fit, pick or tune a calibration policy on held-out R2 ground truth.
R4/R5 frozen SAMPLES have no trusted t_s/gyro/wheel stream: this module
explicitly inspects that prerequisite. R1 candidate multipliers/floors are
fixed *before* score; experimental pilot only, not held-out scientific GO.
x^- is unchanged in ALL R1 arms; covariance transformation is PSD.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
MANIFEST=ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
ART={
 "r2":"ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399",
 "rf":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "q4":"599267063f87546ca76cf6f7c755977c74c8b298c18fbb89e73066dd34be3164",
 "n4c":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9",
}
BLOBS={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/N4_Q_GEOM_RF_20261015/q4_prior_observability.py":"28ec3676bbe5f1cca27ca67d6564a221635f1da4",
 "research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
}
LEVELS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
CASES=("R2_aA_m0","R2_aA_m45")
CALS=("RAW","SCALAR4","SCALAR16","SCALAR64","D_XY2_YAW4_B2","EIG_XY_10CM","COMBINED_PSD")
METHODS=("DR4","J4","SR4","POWER_J4","POWER_SR4")

def filehash(f):
 h=hashlib.sha256()
 with open(f,"rb") as fp:
  for c in iter(lambda:fp.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def blobhash(f):
 p=Path(f);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as fp:
  for c in iter(lambda:fp.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def save(f,v):
 f=Path(f);f.parent.mkdir(parents=True,exist_ok=True)
 f.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def checked(path,expected):
 if filehash(path)!=expected:raise RuntimeError("ARCHIVE_SHA_MISMATCH:"+str(path))
 z=zipfile.ZipFile(path);broken=z.testzip()
 if broken:raise RuntimeError("ARCHIVE_CRC_ERROR:"+str(broken))
 return z
def member(z,name):
 matches=[q for q in z.namelist() if q==name or q.endswith("/"+name)]
 if len(matches)!=1:raise RuntimeError("NONUNIQUE_ARCHIVE_MEMBER:"+name)
 return matches[0]
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 issues=[]
 try:
  head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
  if head!=os.getenv("GITHUB_SHA"):issues.append("SOURCE_REV_MISMATCH")
 except Exception as exc:head=None;issues.append("GIT_ERROR:"+repr(exc))
 if os.getenv("GITHUB_ACTIONS")!="true":issues.append("CLOUD_RUN_REQUIRED")
 for name,expected in BLOBS.items():
  f=ROOT/name
  if not f.exists():issues.append("FROZEN_NOT_FOUND:"+name)
  elif blobhash(f)!=expected:issues.append("FROZEN_CHANGED:"+name)
 try:ast.parse((HERE/"q4r_posthoc.py").read_text())
 except Exception as exc:issues.append("SOURCE_SYNTAX:"+repr(exc))
 wf=ROOT/".github/workflows/n4q-q4r-r0r1.yml"
 if not wf.exists():issues.append("WORKFLOW_NOT_FOUND")
 else:
  s=wf.read_text()
  seq=["q4r_posthoc.py --phase pre","q4r_posthoc.py --phase test","q4r_posthoc.py --phase run"]
  if not all(token in s for token in seq) or not s.index(seq[0])<s.index(seq[1])<s.index(seq[2]):
   issues.append("AUDIT_ORDER_VIOLATION")
  if "if: always()" not in s or "actions: read" not in s:issues.append("AUDIT_ARTIFACT_RULE")
 m=json.loads(MANIFEST.read_text())
 # Genuine R4/R5 timed wheel/gyro streams MUST NOT be inferred from
 # 1303 spatial+in-place yaw scan samples.
 sample_q={}
 for c in m["cases"]:
  if c["route"] not in ("R4","R5"):continue
  f=ROOT/c["samples_path"]
  if not f.exists():issues.append("R4R5_SOURCE_SAMPLES_MISSING:"+c["id"]);continue
  d=json.loads(f.read_text())
  has_motion=bool(d and all(k in d[0] for k in ("t_s","ds_odom","dtheta_gyro","dt_s")))
  sample_q[c["id"]]={"n_samples":len(d),"keys":sorted(d[0].keys()),
                  "contains_verified_timed_controls":has_motion}
 training=all(q["contains_verified_timed_controls"] for q in sample_q.values()) and len(sample_q)==4
 doc={"stage":"Q4-R0","decision":"GO" if not issues else "HOLD",
      "source_sha":head,"frozen_sources":BLOBS,"archive_sha256":ART,
      "R4R5_motion_metadata":sample_q,
      "GT_prior_calibration_training_eligible":training,
      "R1_pilot_alternatives_fixed_a_priori":list(CALS),
      "scientific_generalization_allowed":False,"errors":issues}
 save(out/"Q4R0_AUDIT.json",doc)
 print("Q4R0_PRE "+json.dumps({"decision":doc["decision"],"R4R5_timed_training_eligible":training,
                           "issues":issues}),flush=True)
 return 0 if not issues else 2

def fixP(np,P,policy):
 P=(P+P.T)*.5
 if np.linalg.eigvalsh(P).min()<=0:raise RuntimeError("FROZEN_P_NONSPD")
 if policy=="RAW":return P.copy()
 if policy.startswith("SCALAR"):
  scale={"SCALAR4":4.,"SCALAR16":16.,"SCALAR64":64.}[policy]
  return scale*P
 if policy=="D_XY2_YAW4_B2":
  D=np.diag([2.,2.,4.,2.]);return D@P@D
 C=P.copy()
 if policy not in ("EIG_XY_10CM","COMBINED_PSD"):raise ValueError(policy)
 # Direction is learned from the current P only; NO oracle error included.
 cond=P[:2,:2]-np.outer(P[:2,2],P[2,:2])/P[2,2]
 _,U=np.linalg.eigh(cond)
 u=np.r_[U[:,0],0.,0.]
 C+=.01*np.outer(u,u)
 if policy=="COMBINED_PSD":
  C+=np.diag([.01,.01,math.radians(5.)**2,math.radians(.025)**2])
 return (C+C.T)*.5

def evaluate(np,x,P,t,truth,true_bias):
 m=t>=30.
 X=x[m];S=P[m]
 E=X-np.column_stack([truth,np.full(len(truth),math.radians(true_bias))])[m]
 E[:,2]=(E[:,2]+np.pi)%(2*np.pi)-np.pi
 po=S[:,:3,:3]
 nev=np.einsum("ni,ni->n",E,np.linalg.solve(S,E[...,None])[:,:,0])
 nepose=np.einsum("ni,ni->n",E[:,:3],np.linalg.solve(po,E[:,:3,None])[:,:,0])
 neh=E[:,2]**2/po[:,2,2]
 nib=E[:,3]**2/S[:,3,3]
 xycond=po[:,:2,:2]-po[:,:2,2,None]*po[:,None,2,:2]/po[:,2,2,None,None]
 econd=E[:,:2]-po[:,:2,2]/po[:,2,2,None]*E[:,2,None]
 nexy=np.einsum("ni,ni->n",econd,np.linalg.solve(xycond,econd[...,None])[:,:,0])
 if max(abs(nepose-neh-nexy))>1e-7*max(1.,max(nepose)):
  raise RuntimeError("SCHUR_DECOMP_INVALID")
 return {"n":int(m.sum()),
  "heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(E[:,2]**2)))),
  "xy_rmse_m":float(np.sqrt(np.mean(np.sum(E[:,:2]**2,axis=1)))),
  "bias_rmse_dps":float(np.degrees(np.sqrt(np.mean(E[:,3]**2)))),
  "heading_nees":float(neh.mean()),"pose_nees":float(nepose.mean()),
  "conditional_xy_nees":float(nexy.mean()),"state4_nees":float(nev.mean()),
  "bias_nees":float(nib.mean()),"heading_95":float((neh<=3.841458820694124).mean()),
  "pose_95":float((nepose<=7.814727903251179).mean()),
  "state4_95":float((nev<=9.487729036781154).mean()),
  "bias_95":float((nib<=3.841458820694124).mean()),
  "heading_sigma_median_deg":float(np.degrees(np.median(np.sqrt(S[:,2,2])))),
  "state_logdet_median":float(np.median(np.linalg.slogdet(S)[1])),
  "pose_logdet_median":float(np.median(np.linalg.slogdet(po)[1])),
  "frac_pose_nees_gt100":float((nepose>100).mean()),
  "top5pct_pose_NEES_share":float(np.sort(nepose)[-max(1,math.ceil(.05*len(nepose))):].sum()/nepose.sum())}

def setup():
 import numpy as np
 sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 from r2_bias_replay import build_positive_bias_controls,predict_one,METHODS as R2_METHODS
 return np,build_positive_bias_controls,predict_one,R2_METHODS

def test():
 np,_,_,_=setup()
 rng=np.random.default_rng(15)
 for i in range(20):
  a=rng.normal(size=(4,4));p=a@a.T*.001+np.diag([.01,.01,.001,.00001])
  for pol in CALS:
   q=fixP(np,p,pol)
   if np.linalg.eigvalsh(q).min()<=0:raise RuntimeError("NONSPD_CAL:"+pol)
   if pol=="RAW" and np.max(abs(q-p))>1e-14:raise RuntimeError("RAW_CHANGED")
   if np.linalg.eigvalsh(q-p).min()<-1e-12 and pol!="D_XY2_YAW4_B2":
    raise RuntimeError("PSD_INFLATION_NEGATIVE:"+pol)
  # D P D is PD but not guaranteed P_cal-P PSD. Do not assert monotonic variance direction.
 print("Q4R1_UNIT_PASS "+json.dumps({"spds":20,"policies":list(CALS)}),flush=True)
 return 0

def execute(out,auditpath,r2path,rfpath,q4path,n4cpath):
 np,control,predict,R2_METHODS=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(auditpath).read_text())
 if a["decision"]!="GO" or a["source_sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("R0_AUDIT_NOT_GO")
 scores=[];source_parity=[]
 with checked(r2path,ART["r2"]) as zr,checked(rfpath,ART["rf"]) as zf, \
      checked(q4path,ART["q4"]) as zq,checked(n4cpath,ART["n4c"]) as zc:
  qmeta=json.loads(zq.read(member(zq,"Q4_FINAL.json")))
  if qmeta["total_evaluated_records"]!=26528 or qmeta["status"]!="Q4_PRIOR_SIXPOINT_CUBATURE_COMPLETE":
   raise RuntimeError("ORIGINAL_Q4_NOT_AUDITED")
  n4cmeta=json.loads(zc.read(member(zc,"N4C_FINAL.json")))
  if n4cmeta["n_metric_rows"]!=304:raise RuntimeError("N4C_SOURCE_PARTIAL")
  index={(r["case"],r["channel"]):r for r in
         json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  for case in CASES:
   for channel in ("full","los"):
    desc=index[(case,channel)]
    raw=zf.read("P2_OUT/"+desc["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=desc["trace_sha256"]:
     raise RuntimeError("FROZEN_RF_TRACE_SHA_CHANGED")
    with np.load(io.BytesIO(raw),allow_pickle=False) as qq:
     t=qq["t_s"].copy();pose=qq["truth_for_offline_scoring_only"].copy()
     ids=qq["pose_id"].copy()
    for bias,bias_dps in LEVELS.items():
     controls,x0=control(t,pose,bias,seed=0)
     z=zr.read(member(zr,f"{case}_{channel}_{bias}_seed0_recursive.npz"))
     with np.load(io.BytesIO(z),allow_pickle=False) as vv:
      ref={k:vv[k].copy() for k in vv.files}
     if not np.array_equal(ref["t_s"],t) or not np.array_equal(ref["pose_id"],ids):
      raise RuntimeError("FROZEN_R2_IDS_MISMATCH")
     for method in METHODS:
      if method.startswith("POWER"):
       if channel=="los":continue
       source_method="J4" if method=="POWER_J4" else "SR4"
       original=zc.read(member(zc,f"N4C_{case}_{channel}_{bias}_{source_method}.npz"))
       with np.load(io.BytesIO(original),allow_pickle=False) as v:
        mask=(v["policies"]=="POWER_JOINT")&(v["gate_modes"]=="natural")
        if mask.sum()!=1:raise RuntimeError("N4C_POWER_MODEL_NOT_FOUND")
        ii=int(np.flatnonzero(mask)[0])
        x=v["estimate"][:,ii,:].copy();P=v["covariance"][:,ii,:,:].copy()
        if not np.array_equal(v["pose_id"],ids):raise RuntimeError("N4C_POWER_TIME_MISMATCH")
      else:
       ii=list(R2_METHODS).index(method)
       x=ref["estimate"][:,ii,:].copy()
       P=ref["covariance"][:,ii,:,:].copy()
      xp=np.empty_like(x);Pp=np.empty_like(P)
      for k in range(len(t)):
       if k:
        xp[k],Pp[k]=predict(x[k-1],P[k-1],
         float(controls["ds_odom"][k]),float(controls["dtheta_gyro"][k]),
         float(controls["dt_s"][k]))
       else:
        xp[k],Pp[k]=x[k],P[k]
      if method=="J4" and channel=="full" and bias in ("B0","L2"):
       # Independently agree with Q4 original first-prior heading metrics.
       qcase=next(q for q in qmeta["full_J4_focus"] if q["case"]==case and q["bias"]==bias)
       error=xp[:,2]-pose[:,2];error=(error+np.pi)%(2*np.pi)-np.pi
       m=t>=30
       meanerror=float(np.degrees(np.mean(abs(error[m]))))
       if abs(meanerror-qcase["mean_abs_prior_heading_error_deg"])>1e-9:
        raise RuntimeError("ORIGINAL_Q4_FROZEN_PRIOR_PARITY:"+str((case,bias,meanerror)))
       source_parity.append({"case":case,"bias":bias,"mean_error":meanerror,
        "original_q4":qcase["mean_abs_prior_heading_error_deg"]})
      for pol in CALS:
       Ps=np.stack([fixP(np,p,pol) for p in Pp])
       stat=evaluate(np,xp,Ps,t,pose,bias_dps)
       scores.append({"case":case,"channel":channel,"bias":bias,
        "method":method,"calibration":pol,
        "scope":"fixed_predeclared_no_fit_retrospective_P_only",
        **stat})
     print("Q4R1_CASE "+json.dumps({"case":case,"channel":channel,"bias":bias,
        "methods":5 if channel=="full" else 3}),flush=True)
 def dumpcsv(name,rows):
  with (out/name).open("w",newline="",encoding="utf8") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 dumpcsv("Q4R1_POSTHOC_ALL.csv",scores)
 raw=[s for s in scores if s["calibration"]=="RAW"]
 q4f=[s for s in scores if s["channel"]=="full" and s["bias"] in ("B0","L2") and
     s["method"] in ("J4","POWER_J4")]
 status={"Q4R0":"PASS_SOURCE_FROZEN","Q4R1":"TECHNICAL_PASS_ZERO_FIT_PILOT",
   "Q4R2":"REQUIRES_PREDECLARED_POLICY_AND_RECURSIVE_EXECUTION",
   "Q4R3":"PENDING_RECURSIVE_STRESS",
   "SCIENTIFIC_FULL_PASS":"BLOCKED_INPUT_INDEPENDENT_TIMED_R4R5_AND_SCENE"}
 final={"stage":"Q4-R0/R1","status":"Q4R1_POSTHOC_PILOT_COMPLETE",
  "source_sha":os.environ["GITHUB_SHA"],"n_rows":len(scores),"n_source_parity":len(source_parity),
  "calibration_hyperparameters_fitted_on_R2":False,
  "source_audit_training_eligible":a["GT_prior_calibration_training_eligible"],
  "all_results_are_posthoc_covariance_only":True,
  "fixed_candidate_list":list(CALS),"stage_status":status,
  "focus":q4f,"audit_source_original_Q4":source_parity,
  "warnings":["Posthoc covariance scaling does NOT alter Heading or Gyro Bias point estimates",
    "Predeclared factors are physics controls, NOT fitted on an independent train scene",
    "R4/R5 raw SAMPLES have no verified t_s, gyro and wheel controls",
    "R2 has been repeatedly inspected and is not final untouched test",
    "Full RF original Sionna channel lacks independent stochastic RF realizations",
    "Spatial/time correlated 829 frames are not 829 independent samples",
    "Do not choose the best candidate by heldout R2 and claim scientific calibration"],
  "scientific_PASS":False}
 save(out/"Q4R1_FINAL.json",final)
 print("Q4R1_FINAL "+json.dumps({"status":final["status"],"n_rows":len(scores),
   "source_training_eligible":a["GT_prior_calibration_training_eligible"],
   "focus":[{"case":s["case"],"bias":s["bias"],"model":s["method"],
    "cal":s["calibration"],"headingNEES":s["heading_nees"],"poseNEES":s["pose_nees"],
    "pose95":s["pose_95"],"heading95":s["heading_95"],
    "heading_sigma":s["heading_sigma_median_deg"]} for s in q4f]},ensure_ascii=False),flush=True)
 return 0
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=("pre","test","run"))
 p.add_argument("--out")
 p.add_argument("--audit");p.add_argument("--r2");p.add_argument("--rf")
 p.add_argument("--q4");p.add_argument("--n4c")
 a=p.parse_args()
 return audit(a.out) if a.phase=="pre" else test() if a.phase=="test" else \
   execute(a.out,a.audit,a.r2,a.rf,a.q4,a.n4c)
if __name__=="__main__":raise SystemExit(main())
