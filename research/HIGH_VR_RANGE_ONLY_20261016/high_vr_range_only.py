"""High-bin Range variance-only falsification for frozen POWER_JOINT.

This is a single-scene, single-motion-seed R2 causal-ablation pilot.
The ONLY new measurement-model parameter is R[0,0]=V_r at packets
in the original R4/R5-trained High-power stratum.
Invariant per packet: mu_r, mu_s, V_s, C_rs, q cutpoints, raw RF, model,
time/motion Q, original exact LoS FFD and 99% joint NIS gating rule.
An optional common POWER gate is offline attribution only, not deployment.
No posterior inflation. Ground truth is forbidden inside the estimator.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE={
 "research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
}
SHA={
 "rf":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "r2":"ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399",
 "n4b":"170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b",
 "n4c":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9",
}
CASES=("R2_aA_m0","R2_aA_m45")
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
SOLVERS=("J4","SR4")
R0_R=.0068578637
CHI2=9.210340371976184
VARIANTS=("POWER_RAW","HIGH_R0","HIGH_2R0","HIGH_4R0")
GATES=("natural","power_mask")
EVAL_START=30.

def sha256(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def member(z,name):
 a=[p for p in z.namelist() if p==name or p.endswith("/"+name)]
 if len(a)!=1:raise RuntimeError("ARCHIVED_FILE_MISSING_OR_DUPLICATE:"+name)
 return a[0]
def checkzip(path,digest):
 got=sha256(path)
 if got!=digest:raise RuntimeError("ARCHIVE_SHA_MISMATCH:"+str(path)+":"+got)
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ARCHIVE_CRC_FAILED")
 return z
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];observed={}
 rev=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("REQUIRE_GITHUB_ACTIONS")
 if rev!=os.getenv("GITHUB_SHA"):errors.append("EXACT_GIT_REV_REQUIRED")
 for rel,expected in SOURCE.items():
  file=ROOT/rel
  if not file.is_file():errors.append("MISSING_ORIGINAL_SOURCE:"+rel)
  else:
   observed[rel]=blob(file)
   if observed[rel]!=expected:errors.append("ORIGINAL_SOURCE_CHANGED:"+rel)
 try:ast.parse((HERE/"high_vr_range_only.py").read_text())
 except Exception as e:errors.append("MAIN_SOURCE_PARSE:"+repr(e))
 w=ROOT/".github/workflows/n4-power-high-vr-floor.yml"
 if not w.is_file():errors.append("WORKFLOW_MISSING")
 else:
  content=w.read_text()
  tokens=["high_vr_range_only.py --phase pre",
          "high_vr_range_only.py --phase test",
          "high_vr_range_only.py --phase run"]
  if not all(v in content for v in tokens) or not 0<=content.index(tokens[0])<content.index(tokens[1])<content.index(tokens[2]):
   errors.append("AUDIT_BEFORE_COMPUTATION_RULE")
  if "if: always()" not in content or "actions: read" not in content:errors.append("EVIDENCE_UPLOAD_RULE")
 record={"status":"HIGH_RANGE_VR_CODE_AUDIT","decision":"GO" if not errors else "HOLD",
   "sha":rev,"source_blob_observed":observed,"original_archive_sha":SHA,
   "models":list(VARIANTS),"R0_range_variance_m2":R0_R,
   "only_Vr_may_change":True,"R0_is_not_physical_noise_floor":True,
   "frozen": ["gyro_wheel_Q","LoS_FFD","raw_observation","s_variance",
       "Range_s_covariance","Range_s_signed_mean","99pct_gate_threshold"],
   "scientific_external_validation":False,"errors":errors}
 save(out/"SOURCE_AUDIT.json",record)
 print("HIGH_VR_AUDIT "+json.dumps({"decision":record["decision"],"errors":errors}),flush=True)
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
 from r2_bias_replay import build_positive_bias_controls,predict_one,METHODS as NAMES
 from core import gaussian_update
 from p3_rf_adapter4 import FrozenLut,R0
 return np,pd,parent,build_positive_bias_controls,predict_one,NAMES,gaussian_update,FrozenLut,R0

def adjust(np,original,variant,is_high):
 a=np.asarray(original,float)
 if a.shape!=(2,2) or not(np.linalg.eigvalsh(a)>0).all():
  raise RuntimeError("ORIGINAL_JOINT_COV_NOT_SPD")
 corrected=a.copy()
 if variant=="POWER_RAW" or not is_high:return corrected
 if variant not in VARIANTS:raise RuntimeError("UNKNOWN_VARIANT:"+variant)
 floor=R0_R*{"HIGH_R0":1.,"HIGH_2R0":2.,"HIGH_4R0":4.}[variant]
 corrected[0,0]=max(float(corrected[0,0]),float(floor))
 # Preserve Vs and Crs EXACTLY, including its sign and magnitude.
 if corrected[1,1]!=a[1,1] or corrected[0,1]!=a[0,1] or corrected[1,0]!=a[1,0]:
  raise RuntimeError("R_S_OR_CRS_CHANGED")
 if not (np.linalg.eigvalsh(corrected)>0).all():
  raise RuntimeError("REPLACEMENT_R_NOT_SPD")
 return corrected

def unit():
 np,pd,parent,*_=setup()
 from core import gaussian_update
 rng=np.random.default_rng(20261016)
 for _ in range(150):
  Cr=rng.uniform(-.003,.003)
  vr=rng.uniform(.002,.004)
  vs=rng.uniform(.004,.008)
  cov=np.array([[vr,Cr],[Cr,vs]])
  if np.linalg.eigvalsh(cov).min()<=0:continue
  for v in VARIANTS:
   a=adjust(np,cov,v,True)
   b=adjust(np,cov,v,False)
   assert np.array_equal(b,cov)
   assert np.array_equal(a[0,1:],cov[0,1:])
   assert np.array_equal(a[1],cov[1])
   assert np.linalg.eigvalsh(a).min()>0
   assert a[0,0]>=cov[0,0]
   assert a[1,1]-a[0,1]**2/a[0,0]>=cov[1,1]-cov[0,1]**2/cov[0,0]-1e-15
  # Re-evaluate covariance of conditional s|r, as it CHANGES when Vr changes.
 # Toy linear Gaussian: all variants maintain normalizable 2x2 Gaussian R.
 parent.simulation_unit_tests()
 print("HIGH_VR_UNIT_PASS "+json.dumps({"covariance_trials":150,
   "checks":["all_nonhigh_bit_identical","only_Vr_modified",
    "SPD","Schur_s_given_r_non_decreasing","N4C_correlated_SR4_linear_equivalence"]}),flush=True)
 return 0

def model_data(np,pd,parent,z):
 all_=parent.parse_n4b_prediction(np,pd,z)
 with gzip.open(io.BytesIO(z.read(member(z,"N4B_OOF_PREDICTIONS.csv.gz"))),
                "rt",encoding="utf8") as fh:
  df=pd.read_csv(fh)
 keep=df[(df.model=="POWER_BIN_JOINT")&(df.route=="R2")].copy()
 if len(keep)!=3909 or keep.duplicated(["case","pose_id"]).any():
  raise RuntimeError("OOF_R2_MISSING_OR_DUPLICATE")
 fq={(str(v.case),int(v.pose_id)):float(v.log_fp_power) for v in keep.itertuples(index=False)}
 raw=json.loads(z.read(member(z,"N4B_TRAIN_ONLY_MODEL_CONFIG.json")))
 good=[v for v in raw if v.get("held_route")=="R2" and v.get("model")=="POWER_BIN_JOINT"]
 if len(good)!=1:raise RuntimeError("ORIGINAL_TRAIN_CONFIG_MISSING")
 cuts=np.asarray(good[0].get("cutpoints_train"),float)
 if cuts.shape!=(2,) or not np.isfinite(cuts).all() or cuts[0]>=cuts[1]:
  raise RuntimeError("TRAIN_ONLY_POWER_CUTPOINTS_INVALID")
 if good[0].get("bin_feature")!="log_fp_power":
  raise RuntimeError("FEATURE_TRAIN_BIN_DIFFERENT")
 grouped={}
 for v in keep.itertuples(index=False):
  b=int(np.searchsorted(cuts,float(v.log_fp_power),side="right"))
  grouped.setdefault(b,set()).add(round(float(v.Vr),10))
 if set(grouped)!={0,1,2} or any(len(v)!=1 for v in grouped.values()):
  raise RuntimeError("POWER_TERTILE_COV_NOT_CONSTANT")
 original_vr={i:next(iter(v)) for i,v in grouped.items()}
 if not original_vr[2]<R0_R<original_vr[1]<original_vr[0]:
  raise RuntimeError("HIGH_POWER_NOT_ONLY_LOW_VR_GROUP")
 return all_,fq,cuts,original_vr

def shift_one(np,parent,gaussian_update,x,P,z,mean,R,method,case,lut,forced):
 nis=parent.joint_prior_nis(np,x,P,z,mean,R,case,lut)
 allow=nis<=CHI2 if forced is None else bool(forced)
 if not allow:return x.copy(),P.copy(),"REJECT",nis
 if method=="J4":
  q,C,_=gaussian_update(x,P,z-mean,lambda state:lut.model(state,case),R)
 else:
  q,C=parent.correlated_sr4(np,x,P,z,mean,R,lut,case)
 return q,C,"APPLIED",nis

def one_step_stats(np,origin,results,truth,mask,fields):
 # Independent same-Prior local counterfactuals, never changes future prior.
 out={}
 for variant,gmode in fields:
  sub=[r for r in results if r["variant"]==variant and r["gate"]==gmode]
  if not sub:raise RuntimeError("MISSING_ONE_STEP_ARM")
  sub=sub[0]
  selected=np.asarray(sub["idx"],int)
  post=np.asarray(sub["post"],float)
  prior=np.asarray(origin["prior_x"][selected],float)
  t=truth[selected]
  e0=prior[:,2]-t[:,2];e0=(e0+np.pi)%(2*np.pi)-np.pi
  e1=post[:,2]-t[:,2];e1=(e1+np.pi)%(2*np.pi)-np.pi
  sq=e1**2-e0**2
  delta_bias_sq=(post[:,3]-math.radians(float(mask["bias"])))**2-(prior[:,3]-math.radians(float(mask["bias"])))**2
  out[(variant,gmode)]={
   "n":len(selected),"high_n":int(np.sum(np.asarray(sub["is_high"]))),
   "harm_accepted_fraction":float(np.mean((sq>1e-14)[np.asarray(sub["accepted"],bool)])) if np.any(sub["accepted"]) else None,
   "mean_heading_sq_change_deg2":float(np.mean(sq)*(180/math.pi)**2),
   "mean_bias_sq_change_dps2":float(np.mean(delta_bias_sq)*(180/math.pi)**2),
   "accepted":int(np.sum(sub["accepted"]))}
 return out

def conditional_metrics(np,result,t,truth):
 valid=t>=EVAL_START
 X=result["state"][valid];P=result["cov"][valid]
 e=X[:,:3]-truth[valid];e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
 S=P[:,:3,:3];zz=S[:,2,2]
 c=S[:,:2,2]/zz[:,None]
 A=S[:,:2,:2]-np.einsum("ni,nj->nij",S[:,:2,2],c)
 A=(A+A.swapaxes(1,2))/2
 lam,U=np.linalg.eigh(A)
 if lam.min()<=0:raise RuntimeError("COND_XY_COV_NOT_SPD")
 E=e[:,:2]-c*e[:,2,None]
 coef=np.einsum("nji,nj->ni",U,E)
 terms=coef**2/lam
 head=e[:,2]**2/zz
 total=head+terms.sum(axis=1)
 full=np.einsum("ni,ni->n",e,np.linalg.solve(S,e[...,None])[:,:,0])
 if np.max(abs(total-full))>1e-6:
  raise RuntimeError("POSE_SCHUR_NEES_IDENTITY_FAILED")
 return {
  "conditional_xy_nees":float(np.mean(terms.sum(axis=1))),
  "conditional_xy_narrow_nees":float(np.mean(terms[:,0])),
  "conditional_xy_wide_nees":float(np.mean(terms[:,1])),
  "conditional_xy_95coverage":float(np.mean(terms.sum(axis=1)<=5.991464547107979)),
  "narrow_axis_95coverage":float(np.mean(terms[:,0]<=3.841458820694124)),
  "narrow_axis_std_median_cm":float(np.median(np.sqrt(lam[:,0]))*100),
  "heading_nees_schur":float(np.mean(head)),
  "pose_nees_schur":float(np.mean(total)),
 }

def recursion(np,parent,gaussian_update,predict,x0,controls,t,z,q,high,case,method,
              variant,gate_mode,mask,lut):
 from r2_bias_replay import INITIAL_POSE_STD,BIAS_PRIOR_STD
 n=len(t)
 x=np.r_[x0,0.];P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 X=np.empty((n,4));C=np.empty((n,4,4))
 priX=np.empty((n,4));priP=np.empty((n,4,4))
 status=np.empty(n,dtype="<U12");nises=np.empty(n)
 K=np.empty((n,4,2));min_eig_xy=np.empty(n)
 appliedR=np.empty((n,2,2))
 for i in range(n):
  if i:
   x,P=predict(x,P,float(controls["ds_odom"][i]),
           float(controls["dtheta_gyro"][i]),float(controls["dt_s"][i]))
  priX[i]=x;priP[i]=P
  qrow=q[i]["POWER_BIN_JOINT"]
  mean=np.asarray(qrow["mean"],float)
  original=np.asarray(qrow["cov"],float)
  r=adjust(np,original,variant,bool(high[i]))
  appliedR[i]=r
  h,H=lut.model(x,case)
  S=H@P@H.T+r
  K[i]=np.linalg.solve(S,H@P).T
  A=P[:3,:3]
  cond=A[:2,:2]-np.outer(A[:2,2],A[2,:2])/A[2,2]
  min_eig_xy[i]=np.linalg.eigvalsh(cond)[0]
  forced=None if gate_mode=="natural" else mask[i]
  if variant=="POWER_RAW" and gate_mode=="natural":
   xnew,Cnew,state,nis,scale=parent.perform_update(
       np,x,P,z[i],"POWER_JOINT",q[i],method,case,lut,"natural")
  else:
   xnew,Cnew,state,nis=shift_one(
       np,parent,gaussian_update,x,P,z[i],mean,r,method,case,lut,forced)
  if not(np.isfinite(xnew).all() and np.isfinite(Cnew).all()) or np.linalg.eigvalsh(Cnew).min()<=0:
   raise RuntimeError("INVALID_POSTERIOR:"+str((method,variant,i)))
  X[i]=x=xnew;C[i]=P=Cnew;status[i]=state;nises[i]=nis
 return {"state":X,"cov":C,"prior_x":priX,"prior_P":priP,
  "status":status,"nis":nises,"robust_R_scale":np.ones(n),
  "K":K,"applied_R":appliedR,"prior_cond_xy_min_eig":min_eig_xy}

def case_experiment(np,pd,parent,predict,gaussian_update,lut,case,meta,bias,method,
                    t,pids,z,truth,x0,controls,q,logpow,cuts,orig_x,orig_P,orig_gate):
 high=np.asarray(logpow)>=cuts[1]
 rows=[];traces={};one_stats={};one_rows=[]
 specs=[("POWER_RAW","natural"),
        ("HIGH_R0","natural"),("HIGH_2R0","natural"),("HIGH_4R0","natural"),
        ("HIGH_R0","power_mask"),("HIGH_2R0","power_mask"),("HIGH_4R0","power_mask")]
 for variant,mode in specs:
  result=recursion(np,parent,gaussian_update,predict,x0,controls,t,z,q,high,
       meta,method,variant,mode,orig_gate,lut)
  traces[(variant,mode)]=result
  if variant=="POWER_RAW":
   delta=result["state"]-orig_x
   delta[:,2]=(delta[:,2]+np.pi)%(2*np.pi)-np.pi
   pdiff=float(np.max(abs(result["cov"]-orig_P)))
   sdiff=float(np.max(abs(delta)))
   gate_diff=int(np.sum((result["status"]=="APPLIED")!=orig_gate))
   if max(pdiff,sdiff)>1e-6 or gate_diff:
    raise RuntimeError("FROZEN_N4C_POWER_PARITY_FAIL:"+str((case,bias,method,pdiff,sdiff,gate_diff)))
  report=parent.score(np,result,t,truth,BIAS[bias])
  cond=conditional_metrics(np,result,t,truth)
  if abs(report["pose_nees"]-cond["pose_nees_schur"])>1e-8:
   raise RuntimeError("SCORING_NEES_NOT_EQUAL_TO_SCHUR")
  good=t>=EVAL_START
  accepted=(result["status"]=="APPLIED")
  gain=result["K"][good]
  sgm=result["applied_R"][good,1,1]
  crs=result["applied_R"][good,0,1]
  vr=result["applied_R"][good,0,0]
  ishigh=high[good]
  qdiag=vr*sgm-crs**2
  if not (qdiag>0).all():raise RuntimeError("FINAL_CORRELATED_COV_NOT_SPD")
  nacc=int(np.sum(accepted[good]&ishigh))
  # Original q-only s marginal variance and cross covariance remain identical.
  rows.append({"case":case,"mount_deg":int(meta["mount_deg"]),
   "bias":bias,"solver":method,"channel":"full","variant":variant,
   "gate_mode":mode,
   "high_count":int(sum(ishigh)),"n_eval":int(sum(good)),
   "accepted_high":nacc,"accepted_other":int(sum(accepted[good]&~ishigh)),
   "high_accept_rate":float(nacc/max(1,sum(ishigh))),
   "mean_high_Vr_m2":float(np.mean(vr[ishigh])),
   "mean_Vs":float(np.mean(sgm)),
   "mean_Crs":float(np.mean(crs)),
   "mean_conditional_s_var":float(np.mean(sgm-crs**2/vr)),
   "median_gain_xyrange_norm":float(np.median(np.linalg.norm(gain[:,:2,0],axis=1))),
   "median_abs_Kpsi_s":float(np.median(abs(gain[:,2,1]))),
   "median_abs_Kbias_s":float(np.median(abs(gain[:,3,1]))),
   "median_prior_xy_cond_eig_min":float(np.median(result["prior_cond_xy_min_eig"][good])),
   **report,**cond})
 # One-step local counterfactual from exact original POWER natural PRIOR,
 # not recursively modified candidate priors; ground-truth scoring only.
 origin=traces[("POWER_RAW","natural")]
 eval_ix=np.flatnonzero(t>=EVAL_START)
 refpost=origin["state"][eval_ix]
 err0=refpost[:,2]-truth[eval_ix,2];err0=(err0+np.pi)%(2*np.pi)-np.pi
 for variant in VARIANTS:
  for gate_mode in ("natural","power_mask"):
   if variant=="POWER_RAW" and gate_mode=="power_mask":continue
   vals=[]
   for k in eval_ix:
    xx=origin["prior_x"][k];PP=origin["prior_P"][k]
    qrow=q[k]["POWER_BIN_JOINT"]
    rr=adjust(np,qrow["cov"],variant,bool(high[k]))
    xx2,pp2,st,nis=shift_one(np,parent,gaussian_update,xx,PP,z[k],
                  qrow["mean"],rr,method,meta,lut,
                  None if gate_mode=="natural" else orig_gate[k])
    de=xx2[2]-truth[k,2];de=(de+np.pi)%(2*np.pi)-np.pi
    bp=xx2[3]-math.radians(BIAS[bias])
    old=refpost[k-eval_ix[0],2]-truth[k,2];old=(old+np.pi)%(2*np.pi)-np.pi
    vals.append([float(de**2-old**2),float(bp**2-
       (refpost[k-eval_ix[0],3]-math.radians(BIAS[bias]))**2),st=="APPLIED",nis,bool(high[k])])
   arr=np.array(vals,float)
   low=arr[:,4]==0;hip=~low
   one_rows.append({"case":case,"bias":bias,"solver":method,
    "variant":variant,"gate_mode":gate_mode,"frames":len(vals),
    "accepted":int(np.sum(arr[:,2])),
    "accepted_high":int(np.sum(arr[hip,2])),
    "heading_sq_change_deg2":float(np.mean(arr[:,0])*(180/math.pi)**2),
    "bias_sq_change_dps2":float(np.mean(arr[:,1])*(180/math.pi)**2),
    "heading_sq_change_deg2_high":float(np.mean(arr[hip,0])*(180/math.pi)**2),
    "heading_sq_change_deg2_lowmid":float(np.mean(arr[low,0])*(180/math.pi)**2),
    "NIS_high_mean":float(np.mean(arr[hip,3]))})
 return rows,traces,one_rows,high

def execute(out,receipt,rfzip,r2zip,n4bzip,n4czip):
 np,pd,parent,controls_fn,predict,names,gaussian_update,FrozenLut,R0=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(receipt).read_text())
 if a["decision"]!="GO" or a["sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("SOURCE_PREAUDIT_REQUIRED")
 if abs(float(R0[0,0])-R0_R)>1e-12:
  raise RuntimeError("R0_RANGE_VARIANCE_CHANGED")
 summary=[];one=[];parity=[];controls_los=[];highbins=[]
 with checkzip(rfzip,SHA["rf"]) as zrf,checkzip(r2zip,SHA["r2"]) as zr2, \
       checkzip(n4bzip,SHA["n4b"]) as zb,checkzip(n4czip,SHA["n4c"]) as zc:
  qmodels,qpower,cuts,original_vr=model_data(np,pd,parent,zb)
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  metadata={row["id"]:row for row in manifest["cases"]}
  source={(v["case"],v["channel"]):v for v in
    json.loads(zrf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  lut=FrozenLut(ROOT)
  oldcsv=[]
  with zipfile.ZipFile(n4czip) as _unused:pass
  for case in CASES:
   for channel in ("full","los"):
    item=source[(case,channel)]
    b=zrf.read("P2_OUT/"+item["trace_file"])
    if hashlib.sha256(b).hexdigest()!=item["trace_sha256"]:
     raise RuntimeError("ORIGINAL_OBSERVER_PACKET_SHA_MISMATCH")
    with np.load(io.BytesIO(b),allow_pickle=False) as data:
     times=data["t_s"].copy();pids=data["pose_id"].copy()
     truth=data["truth_for_offline_scoring_only"].copy()
     z=np.column_stack([data["z_r_m"],data["z_s"]])
    if len(times)!=979 or len(set(pids))!=len(pids):
     raise RuntimeError("ORIGINAL_R2_NOT_979_OR_ID_DUP")
    if channel=="full":
     quality=[qmodels[(case,int(p))] for p in pids]
     powers=[qpower[(case,int(p))] for p in pids]
     high=np.asarray(powers)>=cuts[1]
     highbins.append({"case":case,"n_all":len(pids),
       "high_all":int(high.sum()),"high_eval":int((high & (times>=EVAL_START)).sum()),
       "power_quantile_cuts_R4R5_only":list(map(float,cuts)),
       "original_three_bin_Vr_m2":original_vr,
       "after_low_Mid_bins_unchanged":True})
    for level in BIAS:
     controls,x0=controls_fn(times,truth,level,seed=0)
     refname=f"{case}_{channel}_{level}_seed0_recursive.npz"
     with np.load(io.BytesIO(zr2.read(member(zr2,refname))),allow_pickle=False) as ar:
      reference={k:ar[k].copy() for k in ar.files}
     for solver in SOLVERS:
      idx=list(names).index(solver)
      if channel=="los":
       result=parent.recurse(np,times,controls,x0,z,[{}]*len(times),solver,
         "BASE_R0",lut,metadata[case])
       xref=reference["estimate"][:,idx];Pref=reference["covariance"][:,idx]
       diff=result["state"]-xref;diff[:,2]=(diff[:,2]+np.pi)%(2*np.pi)-np.pi
       max_state=float(np.max(abs(diff)));max_cov=float(np.max(abs(result["cov"]-Pref)))
       disagree=int(np.sum((result["status"]=="APPLIED")!=(reference["status"][:,idx]=="APPLIED")))
       if max(max_state,max_cov)>1e-6 or disagree:
        raise RuntimeError("ORIGINAL_LOS_PARITY_FAILED")
       parity.append({"case":case,"bias":level,"solver":solver,"channel":"los",
          "model":"BASE_R0","state_max":max_state,"cov_max":max_cov,
          "gate_differences":disagree})
       controls_los.append({"case":case,"bias":level,"solver":solver,
         **parent.score(np,result,times,truth,BIAS[level])})
       continue
      npz=zc.read(member(zc,f"N4C_{case}_full_{level}_{solver}.npz"))
      with np.load(io.BytesIO(npz),allow_pickle=False) as ar:
       index=np.flatnonzero((ar["policies"]=="POWER_JOINT")&(ar["gate_modes"]=="natural"))
       if len(index)!=1:raise RuntimeError("N4C_FROZEN_POWER_NOT_FOUND")
       ii=int(index[0]);xref=ar["estimate"][:,ii,:].copy()
       Pref=ar["covariance"][:,ii,:,:].copy()
       gate=(ar["status"][:,ii]=="APPLIED").copy()
       if not np.array_equal(ar["pose_id"],pids):raise RuntimeError("N4C_RF_ID_DIFFERENT")
      rows,traces,step,ishigh=case_experiment(
         np,pd,parent,predict,gaussian_update,lut,case,metadata[case],
         level,solver,times,pids,z,truth,x0,controls,quality,powers,cuts,xref,Pref,gate)
      summary.extend(rows);one.extend(step)
      nat=traces[("POWER_RAW","natural")]
      original=nat["state"]-xref;original[:,2]=(original[:,2]+np.pi)%(2*np.pi)-np.pi
      parity.append({"case":case,"bias":level,"solver":solver,"channel":"full",
        "model":"POWER_JOINT","state_max":float(np.max(abs(original))),
        "cov_max":float(np.max(abs(nat["cov"]-Pref))),
        "gate_differences":int(np.sum((nat["status"]=="APPLIED")!=gate))})
      # Strict no-input-leakage canary: R[1,1], R[0,1], both means remain
      # frozen on every packet for every arm, and only HIGH q is eligible.
      base=nat["applied_R"]
      for (var,mode),res in traces.items():
       R=res["applied_R"]
       if not (np.array_equal(R[:,1,1],base[:,1,1]) and
          np.array_equal(R[:,0,1],base[:,0,1]) and
          np.array_equal(R[:,1,0],base[:,1,0])):
        raise RuntimeError("CONSTRAINT_Vs_Crs_NOT_FIXED")
       if np.any(R[~ishigh]!=base[~ishigh]):
        raise RuntimeError("NONHIGH_R_CHANGED")
      keys=list(traces)
      np.savez_compressed(out/f"VR_ONLY_{case}_{level}_{solver}.npz",
        t_s=times,pose_id=pids,q_power=np.asarray(powers),
        high_bin=ishigh,variant=np.asarray([k[0] for k in keys]),
        gate_mode=np.asarray([k[1] for k in keys]),
        estimate=np.stack([traces[k]["state"] for k in keys],axis=1),
        covariance=np.stack([traces[k]["cov"] for k in keys],axis=1),
        prior_x=np.stack([traces[k]["prior_x"] for k in keys],axis=1),
        prior_P=np.stack([traces[k]["prior_P"] for k in keys],axis=1),
        NIS=np.stack([traces[k]["nis"] for k in keys],axis=1),
        status=np.stack([traces[k]["status"] for k in keys],axis=1),
        K_joint_linearization=np.stack([traces[k]["K"] for k in keys],axis=1),
        R_packet=np.stack([traces[k]["applied_R"] for k in keys],axis=1))
      print("HIGH_VR_CASE "+json.dumps({"case":case,"bias":level,
         "solver":solver,"arms":len(keys),"high_eval":int(sum(ishigh & (times>=EVAL_START)))}),flush=True)
 def writecsv(name,data):
  with (out/name).open("w",encoding="utf8",newline="") as fp:
   w=csv.DictWriter(fp,fieldnames=list(data[0]))
   w.writeheader();w.writerows(data)
 writecsv("HIGH_VR_ALL_RECURSIVE.csv",summary)
 writecsv("HIGH_VR_ONE_STEP_FIXED_PRIOR.csv",one)
 writecsv("HIGH_VR_SOURCE_PARITY.csv",parity)
 writecsv("HIGH_VR_LOS_R0_GUARDS.csv",controls_los)
 writecsv("HIGH_VR_POWER_STRATUM.csv",highbins)
 significant=[r for r in summary if r["bias"]=="L2" and r["gate_mode"]=="natural" and r["solver"]=="J4"]
 status={"status":"HIGH_VR_RANGE_ONLY_RECURSIVE_PILOT_COMPLETE",
    "source_sha":os.environ["GITHUB_SHA"],
    "n_recursive_comparisons":len(summary),"n_fixed_prior_one_step":len(one),
    "n_original_parity":len(parity),"n_los_guards":len(controls_los),
    "n_high_bin_summary":len(highbins),
    "fixed_original_R0_range":R0_R,"r2_fold_power_cutpoints":list(map(float,cuts)),
    "train_only_three_Vr":original_vr,"L2_J4":significant,
    "Q5_GO":False,"scientific_PASS":False,
    "limitations":[
       "R2 is repeatedly inspected; single corridor single RF realization and motion seed0",
       "R0 is an empirical covariance baseline, not a measured clean LoS thermal lower bound",
       "R_s marginal and C_rs fixed; s conditional variance given r changes algebraically when V_r changes",
       "Common POWER gate mask is retrospective, cannot be used by an online candidate",
       "Changing High Vr affects posterior heading and gyro bias via xy/psi cross covariance",
       "No Full-derived POWER correction applied to Native LoS in this test; LoS R0 frozen guard only",
       "This is a factor-ablation pilot, not calibrated Bayesian posterior correction"]}
 save(out/"HIGH_VR_FINAL.json",status)
 print("HIGH_VR_FINAL "+json.dumps({"status":status["status"],
    "n":len(summary),"one":len(one),"parity":len(parity),
    "highbins":highbins,"focus":significant},ensure_ascii=False),flush=True)
 return 0

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","test","run"),required=True)
 p.add_argument("--out");p.add_argument("--audit")
 p.add_argument("--rf");p.add_argument("--r2");p.add_argument("--n4b");p.add_argument("--n4c")
 a=p.parse_args()
 return pre(a.out) if a.phase=="pre" else unit() if a.phase=="test" else \
  execute(a.out,a.audit,a.rf,a.r2,a.n4b,a.n4c)
if __name__=="__main__":raise SystemExit(main())
