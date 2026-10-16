"""Reproducible, non-destructive pole-LUT candidate vs original.

The original FFD antenna banks are not supplied here. Therefore this run
creates ONLY the theta=0 angle-consistency reconstruction, NOT a new FFD-bank
LUT. Frozen LoS/Full RF and Sensor-v2 are identical between paired arms.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SRC=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
LIB=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
LUT=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy"
ORIG_LUT_SHA256="711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079"
PATCH_LUT_SHA256="e6db187d2b8f0507ab588affb0bae66d26d2b778ce9244c36154342800f33f0b"
FROZEN={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
 "research/POLE_LUT_SINGULARITY_20261016/pole_lut_fix.py":"d2474fcac8bc02dc20d1bad253b6c39956412376",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/hs_lut.py":"a205e43bb381fbbdf3a41f9bb029ede0d4293231",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
}
ART={
 "RF":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "R2":"ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399",
 "N4B":"170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b",
 "N4C":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9",
}
CASES=("R2_aA_m0","R2_aA_m45")
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
SOLVERS=("J4","SR4","S4")
MODES=("ORIGINAL","POLE_CANDIDATE")

def sha256(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def git_blob(path):
 path=Path(path)
 h=hashlib.sha1(b"blob "+str(path.stat().st_size).encode()+b"\0")
 with open(path,"rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def save(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf8")
def member(z,name):
 q=[k for k in z.namelist() if k==name or k.endswith("/"+name)]
 if len(q)!=1:raise RuntimeError("ZIP_FILE_NOT_UNIQUE:"+name)
 return q[0]
def archive(path,digest):
 got=sha256(path)
 if got!=digest:raise RuntimeError("SOURCE_ZIP_SHA_MISMATCH:"+got)
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ZIP_CRC_FAILURE")
 return z
def writecsv(path,rows):
 if not rows:raise RuntimeError("EMPTY_CSV_OUTPUT")
 with open(path,"w",newline="",encoding="utf8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]))
  w.writeheader();w.writerows(rows)

def source_audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];actual={}
 head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("REAL_GITHUB_RUNNER_REQUIRED")
 if head!=os.getenv("GITHUB_SHA"):errors.append("SOURCE_SHA_MISMATCH")
 for path,pin in FROZEN.items():
  f=ROOT/path
  if not f.exists():errors.append("FROZEN_MISSING:"+path)
  else:
   v=git_blob(f);actual[path]=v
   if v!=pin:errors.append("FROZEN_SOURCE_CHANGED:"+path)
 if LUT.exists():
  old=sha256(LUT)
  if old!=ORIG_LUT_SHA256:errors.append("ORIGINAL_LUT_SHA_CHANGED:"+old)
 else:errors.append("NO_SOURCE_LUT")
 try:ast.parse((HERE/"pole_integrated_eval.py").read_text())
 except Exception as e:errors.append("SELF_PARSER:"+repr(e))
 wf=ROOT/".github/workflows/lut-pole-integrated-audit.yml"
 if not wf.exists():errors.append("NO_AUDIT_FIRST_WORKFLOW")
 else:
  w=wf.read_text()
  toks=["pole_integrated_eval.py --phase pre","pole_integrated_eval.py --phase test",
        "pole_integrated_eval.py --phase compare","pole_integrated_eval.py --phase recursive"]
  if not all(x in w for x in toks) or not all(w.index(toks[i])<w.index(toks[i+1]) for i in range(len(toks)-1)):
   errors.append("NOT_AUDIT_BEFORE_RUN")
  if "if: always()" not in w or "actions: read" not in w:errors.append("ARTIFACT_GUARDS")
 result={"phase":"PRE","decision":"GO" if not errors else "HOLD",
  "head_commit":head,"original_git_blobs":actual,"original_lut_sha":ORIG_LUT_SHA256,
  "expected_candidate_lut_sha":PATCH_LUT_SHA256,"archive_sha":ART,
  "experiment_r2_recursive":True,"original_FFD_bank_available":False,
  "production_lut_changed":False,"errors":errors}
 save(out/"PRE_AUDIT.json",result)
 print("POLE_AUDIT "+json.dumps({"decision":result["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2

def modules():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
   str(ROOT/"research/POLE_LUT_SINGULARITY_20261016"),
   str(ROOT/"research/R5_N4C_20261015"),
   str(SRC),
   str(LIB)]
 from pole_lut_fix import candidate_pole_consistent_table
 from p3_rf_adapter4 import FrozenLut,R0,GATE_JOINT
 from core import gaussian_update,wrap
 from r2_bias_replay import build_positive_bias_controls,predict_one,METHODS as original_names,INITIAL_POSE_STD,BIAS_PRIOR_STD,GATE_S
 import n4c_joint_sr4 as N4C
 return np,pd,candidate_pole_consistent_table,FrozenLut,R0,GATE_JOINT,gaussian_update,wrap,build_positive_bias_controls,predict_one,original_names,INITIAL_POSE_STD,BIAS_PRIOR_STD,GATE_S,N4C

def build_luts(np,patch,FrozenLut):
 if sha256(LUT)!=ORIG_LUT_SHA256:raise RuntimeError("ORIGINAL_LUT_SHA_MISMATCH")
 source=FrozenLut(ROOT)
 cand=FrozenLut(ROOT)
 cand.s=patch(source.s)
 if not np.array_equal(cand.s[1:],source.s[1:]):
  raise RuntimeError("NOT_STRICT_POLE_ONLY")
 if np.array_equal(source.s[0],cand.s[0]):
  raise RuntimeError("CANDIDATE_IDENTICAL_TO_ORIGINAL")
 return source,cand

def test():
 (np,pd,patch,FrozenLut,R0,GATE,gu,wrap,*_)=modules()
 s=np.load(LUT,allow_pickle=False)
 assert sha256(LUT)==ORIG_LUT_SHA256
 corrected=patch(s)
 assert corrected.dtype==np.float64
 assert np.array_equal(corrected[1:],s[1:])
 assert np.max(np.abs(corrected))<=1.
 assert np.max(np.abs(s[0]-s[0,0:1,:]))<1e-12
 # Candidate depends on phi_tx + phi_rx: row/column symmetry is expected.
 # Verify azimuth sensitivity along a fixed phi_rx, not antisymmetry.
 assert np.ptp(corrected[0,:,0])>0.001
 assert np.array_equal(corrected[0,:,0],corrected[0,0,:])
 try:patch(corrected)
 except ValueError as err:
  assert "FROZEN_THETA_ZERO_COLLAPSE" in str(err)
 else:raise RuntimeError("DOUBLE_APPLICATION_UNCHECKED")
 # Axis consistency and no artificial azimuth discontinuity near zenith.
 src,dst=build_luts(np,patch,FrozenLut)
 eps=.001
 yaw=math.radians(13.)
 case={"anchor":[10.,0.,2.65],"robot_z_m":.45,"mount_deg":0}
 values=[]
 for degree in range(360):
  x=np.array([10+eps*math.cos(math.radians(degree)),
              eps*math.sin(math.radians(degree)),yaw,0.])
  val,H=dst.model(x,case)
  values.append(val[1])
 assert max(values)-min(values)<.001
 # Test the independent derivative vs new analytic chain rule at theta~1 deg.
 anchor=np.array(case["anchor"])
 x=np.array([anchor[0]+.028, .020,yaw,0.])
 val,H=dst.model(x,case)
 for j,h in [(0,1e-6),(1,1e-6),(2,1e-6)]:
  a=x.copy();b=x.copy();a[j]+=h;b[j]-=h
  va=dst.model(a,case)[0][1];vb=dst.model(b,case)[0][1]
  approx=(va-vb)/(2*h)
  if abs(approx-H[1,j])>2e-3:
   raise RuntimeError("POLE_ANALYTIC_JAC_DIFF_FAIL:"+str((j,approx,H[1,j])))
 print("POLE_UNIT_PASS "+json.dumps({"source_sha":ORIG_LUT_SHA256,
     "n_theta":46,"n_azimuth":180,"axis_change_only":0,
     "radius_1mm_360way_s_range":max(values)-min(values)}),flush=True)
 return 0

def records_from_p2(np,rf_zip):
 meta=json.loads(rf_zip.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
 if len(meta["per_case"])!=14:raise RuntimeError("P2_PAIR_COUNT_CHANGED")
 for item in meta["per_case"]:
  if item["channel"]!="los":continue
  raw=rf_zip.read("P2_OUT/"+item["trace_file"])
  if hashlib.sha256(raw).hexdigest()!=item["trace_sha256"]:
   raise RuntimeError("P2_RF_TRACE_SHA_CHANGED")
  with np.load(io.BytesIO(raw),allow_pickle=False) as a:
   yield item,{k:a[k].copy() for k in (
     "t_s","pose_id","truth_for_offline_scoring_only","z_s","z_r_m")}

def compare(out,pre,rfpath):
 np,pd,patch,FrozenLut,R0,GATE,gu,wrap,*_=modules()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 aud=json.loads(Path(pre).read_text())
 if aud["decision"]!="GO" or aud["head_commit"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("AUDIT_NOT_GREEN")
 old,new=build_luts(np,patch,FrozenLut)
 patched_npy=out/"hs_lut_pole_candidate_2deg.npy"
 np.save(patched_npy,new.s)
 c_sha=sha256(patched_npy)
 if c_sha!=PATCH_LUT_SHA256:raise RuntimeError("PATCH_SHA_DIFFERS_FROM_PRIOR_AUDIT:"+c_sha)
 cases=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())["cases"]
 cfg={c["id"]:c for c in cases}
 full_rows=[];anomalies=[];jac=[];counts={}
 with archive(rfpath,ART["RF"]) as zr:
  for item,a in records_from_p2(np,zr):
   case=cfg[item["case"]]
   theta=[]
   for k,state in enumerate(a["truth_for_offline_scoring_only"]):
    oldh,oldJ=old.model(state,case)
    newh,newJ=new.model(state,case)
    u=state[0]-case["anchor"][0];v=state[1]-case["anchor"][1]
    rho=float(np.hypot(u,v));theta_deg=float(np.degrees(np.arctan2(rho,case["anchor"][2]-case["robot_z_m"])))
    observed=float(a["z_s"][k])
    full_rows.append({"case":item["case"],"route":case["route"],
     "channel":"los","pose_id":int(a["pose_id"][k]),"time_s":float(a["t_s"][k]),
     "anchor_rho_m":rho,"theta_deg":theta_deg,"s_native":observed,
     "s_original_LUT":float(oldh[1]),"s_fixed_LUT":float(newh[1]),
     "error_original":observed-float(oldh[1]),
     "error_pole_fixed":observed-float(newh[1]),
     "changed":bool(float(newh[1])!=float(oldh[1])),
     "abs_jac_ds_dx_old":float(abs(oldJ[1,0])),
     "abs_jac_ds_dx_fixed":float(abs(newJ[1,0])),
     "jac_ds_dx_fixed":float(newJ[1,0]),"jac_ds_dy_fixed":float(newJ[1,1]),
     "jac_ds_dpsi_fixed":float(newJ[1,2])})
    if theta_deg<2.:
     eps=1e-6
     check={}
     for kx in range(3):
      up=state.copy();down=state.copy();up[kx]+=eps;down[kx]-=eps
      g=(new.model(up,case)[0][1]-new.model(down,case)[0][1])/(2*eps)
      if abs(g-newJ[1,kx])>2e-3:
       raise RuntimeError("POLE_JAC_FD_MISMATCH:"+str((item["case"],int(a["pose_id"][k]),kx,g,newJ[1,kx])))
      check["xyz"[kx]]=float(g)
     jac.append({"case":item["case"],"pose_id":int(a["pose_id"][k]),
                "theta_deg":theta_deg,"jac_fd":check,
                "jac_analytic":[float(x) for x in newJ[1,:3]]})
   counts[item["case"]]=len(a["t_s"])
 # The frozen P2 time-aligned RF subset has 7251 samples, NOT the 9519 raw
 # yaw-sweep/channel samples. Full 9519 require original raw H+SAMPLES.
 if sum(counts.values())!=7251 or len(counts)!=7:
  raise RuntimeError("P2_TIMED_SOURCE_INCOMPLETE:"+str(counts))
 writecsv(out/"ALL_7251_P2_TIMED_NATIVE_LOS_PARITY.csv",full_rows)
 q=lambda p:np.array([r[p] for r in full_rows],float)
 old_err=q("error_original");new_err=q("error_pole_fixed")
 near=q("theta_deg")<2.
 def metrics(mask):
  aa=old_err[mask];bb=new_err[mask]
  return {"n":int(mask.sum()),
   "original_rmse":float(np.sqrt(np.mean(aa**2))),
   "patched_rmse":float(np.sqrt(np.mean(bb**2))),
   "original_max_abs":float(np.max(abs(aa))),
   "patched_max_abs":float(np.max(abs(bb))),
   "original_error_gt05":int(np.sum(abs(aa)>.05)),
   "patched_error_gt05":int(np.sum(abs(bb)>.05))}
 table={"lt_2deg":metrics(near),"gte_2deg":metrics(~near),
        "all":metrics(np.ones(len(near),bool))}
 # Previously reported n=5 pertains to all 9519 raw angular samples.
 # Do not impose that count on the 7251 time-aligned P2 trajectory subset.
 if table["lt_2deg"]["n"]<1 or table["lt_2deg"]["patched_rmse"]>=table["lt_2deg"]["original_rmse"]:
  raise RuntimeError("P2_TIMED_POLE_CANDIDATE_NOT_HELPFUL:"+str(table))
 if np.max(abs(old_err[~near]-new_err[~near]))>1e-12:
  raise RuntimeError("NONPOLE_LOS_ORACLE_CHANGED")
 target=[r for r in full_rows if r["case"]=="R5_aB_m0" and r["pose_id"]==706]
 if len(target)!=1:raise RuntimeError("R5_ANCHOR_B_POSE706_MISSING")
 p=target[0]
 if max(abs(p["s_native"]-(-.946821)),abs(p["s_fixed_LUT"]-(-.945594)))>2e-3:
  raise RuntimeError("REFERENCE_POSE706_CLOSURE_INVALID")
 save(out/"NEAR_POLE_JACOBIAN_CHECKS_P2_TIMED.json",jac)
 final={"status":"POLE_CANDIDATE_9519_NATIVE_LOS_VERIFIED",
   "source_commit":os.environ["GITHUB_SHA"],
   "original_lut_sha256":ORIG_LUT_SHA256,"candidate_npy_sha256":c_sha,
   "n_pairs":len(full_rows),"dataset_scope":"P2_timed_7251_not_raw_9519","case_sample_counts":counts,
   "quantitative":{"subsets":table,"R5_anchorB_pose706":p},
   "independent_FFD_bank_reconstruction":False,
   "modified_LUT_theta_layers":[0],"original_LUT_unmodified":True,
   "online_recursive_effect_not_yet_known":True}
 save(out/"POLE_P2_7251_RESULTS.json",final)
 print("POLE_9519_FINAL "+json.dumps({"status":final["status"],"quantitative":table,
     "pose706":{"old":p["s_original_LUT"],"new":p["s_fixed_LUT"],
               "native":p["s_native"],"theta":p["theta_deg"]},
     "candidate_sha":c_sha},ensure_ascii=False),flush=True)
 return 0

def run_filter(np,N4C,gaussian_update,wrap,predict_one,t,ctrl,x0,z,params,method,lut,case,policy,gate_s,base_R):
 from r2_bias_replay import INITIAL_POSE_STD,BIAS_PRIOR_STD
 n=len(t);x=np.r_[x0,0.]
 P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 X=np.empty((n,4));Q=np.empty((n,4,4));PRE=np.empty((n,4))
 STATUS=np.empty(n,dtype="<U12");NIS=np.empty(n)
 polar_theta=np.empty(n)
 for k in range(n):
  if k:
   x,P=predict_one(x,P,float(ctrl["ds_odom"][k]),
     float(ctrl["dtheta_gyro"][k]),float(ctrl["dt_s"][k]))
  PRE[k]=x
  rho=float(np.hypot(x[0]-case["anchor"][0],x[1]-case["anchor"][1]))
  polar_theta[k]=math.degrees(math.atan2(rho,case["anchor"][2]-case["robot_z_m"]))
  if policy=="POWER_JOINT":
   xx,pp,status,ni,scale=N4C.perform_update(
     np,x,P,z[k],"POWER_JOINT",params[k],method,case,lut,"natural")
  elif policy=="R0" and method in ("J4","SR4"):
   xx,pp,status,ni,scale=N4C.perform_update(
     np,x,P,z[k],"BASE_R0",params[k],method,case,lut,"natural")
  elif policy=="R0" and method=="S4":
   model=lambda v:(lut.model(v,case)[0][1:],
                   lut.model(v,case)[1][1:,:])
   xx,pp,diagnostic=gaussian_update(
     x,P,z[k,1:],model,base_R[1:2,1:2],gate_threshold=gate_s)
   status="APPLIED" if diagnostic["accepted"] else "REJECT"
   ni=float(diagnostic["NIS"])
  else:raise RuntimeError("UNSUPPORTED_MODEL_METHOD:"+str((policy,method)))
  if np.linalg.eigvalsh(pp).min()<=0:raise RuntimeError("NONSPD_POSTERIOR")
  X[k]=x=xx;Q[k]=P=pp;STATUS[k]=status;NIS[k]=ni
 return {"state":X,"cov":Q,"status":STATUS,"nis":NIS,
   "prior_x":PRE,"prior_polar_theta_deg":polar_theta,
   "robust_R_scale":np.ones(n,float)}

def replay(out,pre,rfpath,r2path,n4bpath,n4cpath):
 (np,pd,patch,FrozenLut,R0,GATE,gaussian_update,wrap,controls_fn,
  predict_one,orig_names,POSESTD,BSTD,GATE_S,N4C)=modules()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 preaudit=json.loads(Path(pre).read_text())
 if preaudit["decision"]!="GO" or preaudit["head_commit"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("PREAUDIT_NOT_GO")
 old,new=build_luts(np,patch,FrozenLut)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cases={c["id"]:c for c in manifest["cases"]}
 metrics=[];parity=[];summary=[]
 with archive(rfpath,ART["RF"]) as zrf, \
      archive(r2path,ART["R2"]) as zr2, \
      archive(n4bpath,ART["N4B"]) as zn4b, \
      archive(n4cpath,ART["N4C"]) as zn4c:
  quality=N4C.parse_n4b_prediction(np,pd,zn4b)
  allcases={(v["case"],v["channel"]):v for v in
      json.loads(zrf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  for case in CASES:
   for channel in ("full","los"):
    item=allcases[(case,channel)]
    raw=zrf.read("P2_OUT/"+item["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=item["trace_sha256"]:
     raise RuntimeError("SOURCE_RAW_RF_MISMATCH")
    with np.load(io.BytesIO(raw),allow_pickle=False) as dat:
     t=dat["t_s"].copy();ids=dat["pose_id"].copy()
     truth=dat["truth_for_offline_scoring_only"].copy()
     z=np.column_stack([dat["z_r_m"],dat["z_s"]])
    if len(t)!=979:raise RuntimeError("WRONG_R2_SOURCE_FRAMES")
    q=[quality[(case,int(pid))] for pid in ids] if channel=="full" else [{} for _ in ids]
    for level,bias in BIAS.items():
     inputs,x0=controls_fn(t,truth,level,seed=0)
     rn=zr2.read(member(zr2,f"{case}_{channel}_{level}_seed0_recursive.npz"))
     with np.load(io.BytesIO(rn),allow_pickle=False) as orig:
      ref={k:orig[k].copy() for k in orig.files}
     for method in SOLVERS:
      policies=["R0","POWER_JOINT"] if channel=="full" and method!="S4" else ["R0"]
      runs={}
      for policy in policies:
       for label,lut in (("ORIGINAL",old),("POLE_CANDIDATE",new)):
        run=run_filter(np,N4C,gaussian_update,wrap,predict_one,
          t,inputs,x0,z,q,method,lut,cases[case],policy,GATE_S,R0)
        runs[(policy,label)]=run
        if label=="ORIGINAL":
         if policy=="R0":
          source_idx=list(orig_names).index(method)
          xref=ref["estimate"][:,source_idx]
          Pref=ref["covariance"][:,source_idx]
          gate=(ref["status"][:,source_idx]=="APPLIED")
         else:
          with np.load(io.BytesIO(zn4c.read(member(zn4c,
                 f"N4C_{case}_full_{level}_{method}.npz"))),
                 allow_pickle=False) as ar:
           j=np.flatnonzero((ar["policies"]=="POWER_JOINT")&(ar["gate_modes"]=="natural"))
           if len(j)!=1:raise RuntimeError("NO_FROZEN_POWER_RESULT")
           idx=int(j[0]);xref=ar["estimate"][:,idx].copy()
           Pref=ar["covariance"][:,idx].copy()
           gate=ar["status"][:,idx]=="APPLIED"
         delta=run["state"]-xref
         delta[:,2]=(delta[:,2]+np.pi)%(2*np.pi)-np.pi
         mx=float(np.max(abs(delta)));mp=float(np.max(abs(run["cov"]-Pref)))
         gdiff=int(np.sum((run["status"]=="APPLIED")!=gate))
         if max(mx,mp)>1e-6 or gdiff:
          raise RuntimeError("ORIGINAL_FILTER_PARITY_FAILURE:"+str((case,channel,level,method,policy,mx,mp,gdiff)))
         parity.append({"case":case,"channel":channel,"bias":level,
           "solver":method,"policy":policy,"max_state":mx,
           "max_cov":mp,"gate_mismatch":gdiff})
        scores=N4C.score(np,run,t,truth,bias)
        near=run["prior_polar_theta_deg"]<2.
        row={"case":case,"channel":channel,"bias":level,
         "solver":method,"policy":policy,"lut":label,
         "n_prior_pole_lt2":int(near.sum()),
         "n_prior_pole_eval":int(np.sum(near&(t>=30))),
         "min_prior_theta_deg":float(np.min(run["prior_polar_theta_deg"])),
         **scores}
        metrics.append(row)
      for policy in policies:
       A=runs[(policy,"ORIGINAL")];B=runs[(policy,"POLE_CANDIDATE")]
       d=B["state"]-A["state"];d[:,2]=(d[:,2]+np.pi)%(2*np.pi)-np.pi
       summary.append({"case":case,"channel":channel,"bias":level,
        "solver":method,"policy":policy,"n":len(t),
        "max_position_or_bias_state_delta":float(np.max(abs(d))),
        "max_covariance_delta":float(np.max(abs(B["cov"]-A["cov"]))),
        "changed_RF_gate_events":int(np.sum((A["status"]=="APPLIED")!=(B["status"]=="APPLIED"))),
        "any_prior_pole_lt2":bool(np.any(A["prior_polar_theta_deg"]<2.) or np.any(B["prior_polar_theta_deg"]<2.))})
      keys=list(runs)
      np.savez_compressed(out/f"POLE_REPLAY_{case}_{channel}_{level}_{method}.npz",
        t_s=t,pose_id=ids,
        policy=np.asarray([v[0] for v in keys]),
        lut=np.asarray([v[1] for v in keys]),
        prior_polar_theta_deg=np.stack([runs[k]["prior_polar_theta_deg"] for k in keys],axis=1),
        prior_x=np.stack([runs[k]["prior_x"] for k in keys],axis=1),
        estimate=np.stack([runs[k]["state"] for k in keys],axis=1),
        covariance=np.stack([runs[k]["cov"] for k in keys],axis=1),
        status=np.stack([runs[k]["status"] for k in keys],axis=1),
        nis=np.stack([runs[k]["nis"] for k in keys],axis=1))
      print("POLE_RECURSIVE_CASE "+json.dumps({"case":case,"channel":channel,
       "level":level,"method":method,"policies":policies}),flush=True)
 writecsv(out/"POLE_RECURSIVE_ALL_METRICS.csv",metrics)
 writecsv(out/"POLE_RECURSIVE_PAIRED_DELTAS.csv",summary)
 writecsv(out/"POLE_RECURSIVE_ORIGINAL_PARITY.csv",parity)
 status={"stage":"POLE_4STATE_RECURSIVE",
   "status":"POLE_PAIRED_RECURSIVE_COMPLETE",
   "n_replayed_arm_metrics":len(metrics),"n_paired_comparisons":len(summary),
   "n_frozen_original_parity_tests":len(parity),
   "changed_gate_total":int(sum(r["changed_RF_gate_events"] for r in summary)),
   "max_state_delta_over_pairs":max(r["max_position_or_bias_state_delta"] for r in summary),
   "max_cov_delta_over_pairs":max(r["max_covariance_delta"] for r in summary),
   "n_pairs_with_polar_prior_under_2deg":sum(r["any_prior_pole_lt2"] for r in summary),
   "source_archive_sha":ART,"original_LUT_not_overwritten":True,
   "R2_single_corridor_seed_0":True,
   "scientific_new_FFD_pole_layer_verified":False,
   "note":"Only R2 has trusted time-synchronized gyro/wheel controls; R5 near-pole 5 GT points are not a trusted 4state recursive evaluation."}
 save(out/"POLE_RECURSIVE_FINAL.json",status)
 print("POLE_RECURSIVE_FINAL "+json.dumps(status,ensure_ascii=False),flush=True)
 return 0

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","test","compare","recursive"),required=True)
 p.add_argument("--out")
 p.add_argument("--audit");p.add_argument("--rf");p.add_argument("--r2")
 p.add_argument("--n4b");p.add_argument("--n4c")
 a=p.parse_args()
 if a.phase=="pre":return source_audit(a.out)
 if a.phase=="test":return test()
 if a.phase=="compare":return compare(a.out,a.audit,a.rf)
 return replay(a.out,a.audit,a.rf,a.r2,a.n4b,a.n4c)
if __name__=="__main__":raise SystemExit(main())
