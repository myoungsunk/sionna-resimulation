"""N4-C frozen Joint4/SR4 recursive RF mean/covariance/robust ablation.

Held-out R2, trained error densities from N4-B R4/R5. Preserves
[x,y,psi,b_g], motion model, fixed FFD LoS LUT and raw RF packets.
Offline ground truth is NEVER a filter input; used to synthesize the
same frozen sensor-v2 control stream, and post-hoc score only.

CAVEAT: N4-B packet-conditional p(e|q) is NOT a normalized p(z|x)
when q is derived from the same range/s channel. Those policies are
flagged EXPLORATORY; only unconditional trained mean/cov models
are direct Gaussian observation-model hypotheses.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
R2CODE=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
UWBLIB=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
RAW_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
N4B_SHA="170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b"
N4B_SOURCE_SHA="7d8d20c9a95364fb6a9ae7caa720b2b22019ecab"
R0_RANGE=.0068578637
R0_S=.0081
GATE_CHI2_2=9.210340371976184
ROBUST_CHI2=6.6348966010212145
CASES=("R2_aA_m0","R2_aA_m45")
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
BASE_METHODS=("J4","SR4")
ALL_POLICIES=(
 "BASE_R0",
 "GLOBAL_MEAN_ONLY",
 "GLOBAL_COV_ONLY_DIAG",
 "GLOBAL_MEAN_COV_DIAG",
 "GLOBAL_MEAN_COV_JOINT",
 "POWER_JOINT",
 "SIMPLE_DIAG",
 "SIMPLE_JOINT",
 "SIMPLE_G4",
 "G5_RESEARCH_ONLY",
 "ROBUST_GLOBAL_DIAG",
)
LOS_POLICIES=(
 "BASE_R0","GLOBAL_MEAN_ONLY","GLOBAL_COV_ONLY_DIAG",
 "GLOBAL_MEAN_COV_DIAG","GLOBAL_MEAN_COV_JOINT",
)
COMMON_GATE_POLICIES=(
 "GLOBAL_MEAN_COV_DIAG","GLOBAL_MEAN_COV_JOINT","SIMPLE_G4",
)
PINNED={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "research/R5_N4B_20261015/n4b_rf_errors.py":"abd654dd9efde61fc7baffc350188b2a8b4904a3",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
}

def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()

def git_blob(path):
 path=Path(path)
 h=hashlib.sha1(b"blob "+str(path.stat().st_size).encode()+b"\0")
 with path.open("rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()

def write(path,obj):
 path=Path(path)
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")

def preflight(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];observed={}
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("GITHUB_ACTIONS_REQUIRED")
 try:
  current=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
  if current!=os.getenv("GITHUB_SHA"):errors.append("SOURCE_COMMIT_DIFFERENT")
 except Exception as e:
  current=None;errors.append("GIT_REV_ERROR:"+repr(e))
 for rel,expect in PINNED.items():
  p=ROOT/rel
  if not p.is_file():errors.append("FROZEN_SOURCE_NOT_PRESENT:"+rel)
  else:
   val=git_blob(p);observed[rel]=val
   if val!=expect:errors.append("SOURCE_BLOB_DIFFERENT:"+rel)
 try:ast.parse((HERE/"n4c_joint_sr4.py").read_text())
 except Exception as e:errors.append("CODE_SYNTAX:"+repr(e))
 workflow=ROOT/".github/workflows/r5-n4c-joint-sr-recursive.yml"
 if not workflow.is_file():errors.append("WORKFLOW_NOT_FOUND")
 else:
  s=workflow.read_text()
  for item in ("n4c_joint_sr4.py --phase pre","n4c_joint_sr4.py --phase test",
               "n4c_joint_sr4.py --phase run","if: always()","actions: read"):
   if item not in s:errors.append("WORKFLOW_REQUIRED_TOKEN:"+item)
  a=s.find("n4c_joint_sr4.py --phase pre")
  b=s.find("n4c_joint_sr4.py --phase test")
  c=s.find("n4c_joint_sr4.py --phase run")
  if not 0<=a<b<c:errors.append("AUDIT_FIRST_VIOLATION")
 record={"stage":"N4-C","decision":"GO" if not errors else "HOLD",
   "git_sha":current,"original_source_git_blobs":observed,
   "frozen_rf_sha256":RAW_SHA,"frozen_R2_recursive_sha256":R2_SHA,
   "N4B_heldout_model_archive_sha256":N4B_SHA,
   "N4B_source_sha":N4B_SOURCE_SHA,
   "policies":ALL_POLICIES,"bias_levels":BIAS,
   "errors":errors,"scientific_PASS":False}
 write(out/"PRE_AUDIT.json",record)
 print("N4C_PRE "+json.dumps({"decision":record["decision"],
                             "errors":errors}),flush=True)
 return 0 if not errors else 2

def checked_zip(path,expected):
 got=sha_file(path)
 if got!=expected:raise RuntimeError("SOURCE_ARCHIVE_SHA_MISMATCH:"+str(path)+" "+got)
 z=zipfile.ZipFile(path)
 bad=z.testzip()
 if bad:raise RuntimeError("SOURCE_ARCHIVE_BAD_CRC:"+bad)
 return z

def member(z,basename):
 names=[x for x in z.namelist() if x==basename or x.endswith("/"+basename)]
 if len(names)!=1:raise RuntimeError("NOT_UNIQUE_MEMBER:"+basename+":"+str(len(names)))
 return names[0]

def array_from_npz(np,z,basename):
 with np.load(io.BytesIO(z.read(member(z,basename))),allow_pickle=False) as x:
  return {key:x[key].copy() for key in x.files}

def setup():
 import numpy as np
 import pandas as pd
 sys.path.insert(0,str(R2CODE))
 sys.path.insert(0,str(UWBLIB))
 return np,pd

def wrap(np,a):
 return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi

def selector(policy):
 names={
 "GLOBAL_MEAN_ONLY":"GLOBAL_DIAG",
 "GLOBAL_COV_ONLY_DIAG":"GLOBAL_DIAG",
 "GLOBAL_MEAN_COV_DIAG":"GLOBAL_DIAG",
 "GLOBAL_MEAN_COV_JOINT":"GLOBAL_JOINT",
 "POWER_JOINT":"POWER_BIN_JOINT",
 "SIMPLE_DIAG":"SIMPLE_DIAG",
 "SIMPLE_JOINT":"SIMPLE_JOINT",
 "SIMPLE_G4":"SIMPLE_G4",
 "G5_RESEARCH_ONLY":"G5_RESEARCH_ONLY",
 "ROBUST_GLOBAL_DIAG":"GLOBAL_DIAG",
 }
 return names.get(policy)

def measurement_parameters(np,policy,q):
 from p3_rf_adapter4 import R0
 if policy=="BASE_R0":return np.zeros(2),R0.copy()
 name=selector(policy)
 if name not in q:raise RuntimeError("QUALITY_DENSITY_MISSING:"+policy)
 sample=q[name]
 mean=np.asarray(sample["mean"],float)
 cov=np.asarray(sample["cov"],float).copy()
 if policy=="GLOBAL_MEAN_ONLY":
  cov=R0.copy()
 if policy=="GLOBAL_COV_ONLY_DIAG":
  mean=np.zeros(2)
 if policy in ("GLOBAL_COV_ONLY_DIAG","GLOBAL_MEAN_COV_DIAG","SIMPLE_DIAG",
               "ROBUST_GLOBAL_DIAG"):
  cov[0,1]=cov[1,0]=0.
 if not(np.isfinite(cov).all() and np.isfinite(mean).all() and np.min(np.linalg.eigvalsh(cov))>0):
  raise RuntimeError("INVALID_CONDITIONAL_RF_ERROR_MODEL:"+policy)
 if cov[0,0]<1e-10 or cov[1,1]<1e-10:raise RuntimeError("COV_TOO_SMALL")
 return mean,cov

def joint_prior_nis(np,x,P,z,mean,R,case,lut):
 h,H=lut.model(x,case)
 innov=z-mean-h
 S=H@P@H.T+R
 if np.min(np.linalg.eigvalsh(S))<=0:raise RuntimeError("JOINT_INNOVATION_COV_NOT_PD")
 return float(innov@np.linalg.solve(S,innov))

def correlated_sr4(np,x,P,z,mean,R,lut,case):
 """p(r,s|x)=p(r|x)p(s|r,x) with conditional whitening.
    Reevaluate BOTH h_r and h_s after the Range update; do not re-use
    s as an independent original measurement when C_rs != 0.
 """
 from core import gaussian_update
 vr=float(R[0,0])
 a=float(R[0,1]/vr)
 var_s=float(R[1,1]-R[0,1]**2/vr)
 if var_s<=0:raise RuntimeError("CONDITIONAL_POLARIZATION_COV_NON_PD")
 def h_range(q):
  h,H=lut.model(q,case);return h[:1],H[:1,:]
 def h_decorrelated_s(q):
  h,H=lut.model(q,case)
  return np.asarray([h[1]-a*h[0]]),H[1:2,:]-a*H[0:1,:]
 # Inference only consumes one packet. Conditioning uses the SAME observed r,
 # but residual and Jacobian are transformed together, avoiding double count.
 z_r=np.asarray([z[0]-mean[0]])
 z_s=np.asarray([z[1]-mean[1]-a*(z[0]-mean[0])])
 u,Q,_=gaussian_update(x,P,z_r,h_range,np.asarray([[vr]]))
 w,S,_=gaussian_update(u,Q,z_s,h_decorrelated_s,np.asarray([[var_s]]))
 return w,S

def perform_update(np,x,P,z,policy,q,method,case,lut,gate_mode,
                   shared_gate=None):
 from core import gaussian_update
 from r2_bias_replay import filter_one
 if policy=="BASE_R0" and gate_mode=="natural":
  x2,P2,status,nis=filter_one(x,P,z,method,case,lut)
  return x2,P2,status,float(nis),1.
 mean,R=measurement_parameters(np,policy,q)
 nis=joint_prior_nis(np,x,P,z,mean,R,case,lut)
 if gate_mode=="common":
  if shared_gate is None:raise RuntimeError("FIXED_GATE_MASK_NOT_GIVEN")
  allow=bool(shared_gate)
 elif policy=="ROBUST_GLOBAL_DIAG":
  allow=True
 else:
  allow=nis<=GATE_CHI2_2
 if not allow:return x.copy(),P.copy(),"REJECT",nis,1.
 robust_scale=1.
 if policy=="ROBUST_GLOBAL_DIAG":
  # Robust M-estimator style IRLS surrogate, not a normalized likelihood.
  weight=min(1.,math.sqrt(ROBUST_CHI2/max(nis,1e-15)))
  robust_scale=1./max(weight,.001)
  R=R*robust_scale
 if method=="J4":
  func=lambda xx:lut.model(xx,case)
  new,Pnew,_=gaussian_update(x,P,z-mean,func,R)
 elif method=="SR4":
  new,Pnew=correlated_sr4(np,x,P,z,mean,R,lut,case)
 else:raise RuntimeError("UNSUPPORTED_METHOD:"+method)
 if not(np.isfinite(new).all() and np.isfinite(Pnew).all()):
  raise RuntimeError("NONFINITE_POSTERIOR")
 if np.min(np.linalg.eigvalsh(Pnew))<=0:
  raise RuntimeError("NON_POSITIVE_DEFINITE_POSTERIOR")
 return new,Pnew,"APPLIED",nis,robust_scale

def recurse(np,t,controls,init,z,quality,method,policy,lut,case,
            gate_mode="natural",shared_gates=None):
 from r2_bias_replay import predict_one,INITIAL_POSE_STD,BIAS_PRIOR_STD
 n=len(t)
 xx=np.r_[init,0.]
 P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 X=np.empty((n,4),float);Q=np.empty((n,4,4),float)
 statuses=np.empty(n,dtype="<U12")
 nises=np.empty(n,float);robust=np.ones(n,float)
 for i in range(n):
  if i>0:
   xx,P=predict_one(xx,P,float(controls["ds_odom"][i]),
      float(controls["dtheta_gyro"][i]),float(controls["dt_s"][i]))
  x2,P2,status,nis,scale=perform_update(
    np,xx,P,z[i],policy,quality[i],method,case,lut,gate_mode,
    shared_gate=None if shared_gates is None else shared_gates[i])
  if not(np.isfinite(x2).all() and np.isfinite(P2).all()):
   raise RuntimeError("NONFINITE_FILTER_AT:"+str((method,policy,i)))
  X[i]=xx=x2
  Q[i]=P=P2
  statuses[i]=status
  nises[i]=nis
  robust[i]=scale
 return {"state":X,"cov":Q,"status":statuses,"nis":nises,"robust_R_scale":robust}

def score(np,result,t,truth,bias):
 mask=t>=30
 x=result["state"][mask];P=result["cov"][mask]
 err=x[:,:3]-truth[mask,:3]
 err[:,2]=wrap(np,err[:,2])
 p=P[:,:3,:3]
 if np.min(np.linalg.eigvalsh(p))<=0:raise RuntimeError("SCORE_POSE_COV_NOT_PD")
 psi_nees=err[:,2]**2/p[:,2,2]
 pose_nees=np.einsum("ni,ni->n",err,np.linalg.solve(p,err[...,None])[:,:,0])
 Pb=P[:,3,3]
 bias_err=x[:,3]-math.radians(bias)
 status=result["status"][mask]
 return {
 "frames":int(mask.sum()),
 "heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(err[:,2]**2)))),
 "heading_nees":float(psi_nees.mean()),
 "heading_95coverage":float(np.mean(psi_nees<=3.841458820694124)),
 "xy_rmse_m":float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))),
 "pose_nees":float(pose_nees.mean()),
 "pose_95coverage":float(np.mean(pose_nees<=7.814727903251179)),
 "bias_rmse_dps":float(np.degrees(np.sqrt(np.mean(bias_err**2)))),
 "bias_final_dps":float(np.degrees(result["state"][-1,3])),
 "bias_95coverage":float(np.mean(bias_err**2/Pb<=3.841458820694124)),
 "rf_applied":int(np.sum(status=="APPLIED")),
 "rf_rejected":int(np.sum(status=="REJECT")),
 "accepted_fraction":float(np.mean(status=="APPLIED")),
 "robust_scale_max":float(np.max(result["robust_R_scale"][mask])),
 "wrong_heading_over5deg_and_overconfident_fraction":float(np.mean(
  (abs(np.degrees(err[:,2]))>5)&(psi_nees>3.841458820694124)))}

def parse_n4b_prediction(np,pd,z):
 from collections import defaultdict
 with gzip.open(io.BytesIO(z.read(member(z,"N4B_OOF_PREDICTIONS.csv.gz"))),
                "rt",encoding="utf8") as g:
  df=pd.read_csv(g)
 expected_models=("GLOBAL_DIAG","GLOBAL_JOINT","POWER_BIN_JOINT",
    "SIMPLE_DIAG","SIMPLE_JOINT","SIMPLE_G4","G5_RESEARCH_ONLY")
 x=df[(df.route=="R2")&(df.channel.astype(str)=="full")] if "channel" in df else df[(df.route=="R2")]
 keys=["case","pose_id","model"]
 if x.duplicated(keys).any():raise RuntimeError("DUPLICATE_OOF_PREDICTION")
 if set(x["model"])!=set(set(df["model"])):raise RuntimeError("PARTIAL_OOF_MODEL_SET")
 ret=defaultdict(dict)
 for row in x.itertuples(index=False):
  cov=np.asarray([[float(row.Vr),float(row.C_rs)],[float(row.C_rs),float(row.Vs)]],float)
  if np.min(np.linalg.eigvalsh(cov))<=0:raise RuntimeError("PRELEARNED_COV_NOT_PD")
  ret[(str(row.case),int(row.pose_id))][str(row.model)]={
    "mean":np.array([float(row.mu_r),float(row.mu_s)]),"cov":cov}
 for (case,pose),v in ret.items():
  if not all(m in v for m in expected_models):
   raise RuntimeError("MISSING_HOLDOUT_PRELEARNED_MODEL:"+str((case,pose)))
 return ret

def simulation_unit_tests():
 np,pd=setup()
 from core import gaussian_update
 class ToyLut:
  def model(self,x,c):
   H=np.array([[.9,.4,0,0],[.2,-.35,1.1,0]],float)
   return H@x,H
 toy=ToyLut();rng=np.random.default_rng(16)
 R=np.array([[.006,.0025],[.0025,.009]],float)
 mu=np.array([.03,-.08])
 diff=[]
 for i in range(30):
  P0=rng.normal(size=(4,4));P0=P0@P0.T*.04+np.diag([.005,.005,.01,.001])
  x=rng.normal(size=4)*.1
  z=toy.model(x,{})[0]+mu+rng.normal(size=2)*.01
  Q,P,_=gaussian_update(x,P0,z-mu,lambda xx:toy.model(xx,{}),R)
  s,Ps=correlated_sr4(np,x,P0,z,mu,R,toy,{})
  diff.append(max(float(np.max(np.abs(Q-s))),float(np.max(np.abs(P-Ps)))))
 if max(diff)>1e-11:raise RuntimeError("CORRELATED_SR4_LINEAR_EQUIVALENCE_FAIL:"+str(max(diff)))
 # Baseline case, exact diagonal R and no mean must dispatch original.
 q={}
 x=np.array([1.,2.,.4,.02]);P=np.diag([.1,.1,.01,.0001])
 z=toy.model(x,{})[0]+.05
 for method in BASE_METHODS:
  t=perform_update(np,x,P,z,"BASE_R0",q,method,{},toy,"natural")
  from r2_bias_replay import filter_one
  ref=filter_one(x,P,z,method,{},toy)
  np.testing.assert_allclose(t[0],ref[0],rtol=0,atol=1e-15)
  np.testing.assert_allclose(t[1],ref[1],rtol=0,atol=1e-15)
  assert t[2]==ref[2]
 # Frozen case: gating after correction, and covariance-only uses zero mu.
 for policy in ("GLOBAL_MEAN_ONLY","GLOBAL_COV_ONLY_DIAG","GLOBAL_MEAN_COV_JOINT"):
  qc={"GLOBAL_DIAG":{"mean":mu,"cov":R},
      "GLOBAL_JOINT":{"mean":mu,"cov":R}}
  m,C=measurement_parameters(np,policy,qc)
  assert np.linalg.eigvalsh(C).min()>0
  if policy=="GLOBAL_COV_ONLY_DIAG":assert np.all(m==0)
  if policy=="GLOBAL_MEAN_ONLY":
   from p3_rf_adapter4 import R0
   np.testing.assert_allclose(C,R0)
 print("N4C_UNIT_PASS "+json.dumps({"linear_correlated_sr_joint_max_abs":max(diff),
   "n_equivalence_seeds":30,"tests":[
     "WHITENED_CORRELATED_SR4","BASELINE_ORIGINAL_JOINT_SR4",
     "MEAN_ONLY","COV_ONLY","POSITIVE_DEFINITE","ROBUST_POLICY"]}),flush=True)
 return 0

def execute(out,pre,rfzip,r2zip,n4bzip):
 np,pd=setup()
 from p3_rf_adapter4 import FrozenLut
 from r2_bias_replay import build_positive_bias_controls,METHODS
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(pre).read_text())
 if a["decision"]!="GO" or a["git_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("PREAUDIT_NOT_GO")
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cases={v["id"]:v for v in manifest["cases"]}
 lut=FrozenLut(ROOT)
 scores=[];parities=[];records=[]
 with checked_zip(rfzip,RAW_SHA) as zr,checked_zip(r2zip,R2_SHA) as zref,checked_zip(n4bzip,N4B_SHA) as zn:
  n4meta=json.loads(zn.read(member(zn,"N4B_FINAL.json")))
  if n4meta.get("status")!="N4B_AUDITED_RESIDUAL_AND_LIKELIHOOD_COMPLETE" or \
     n4meta.get("source_sha")!=N4B_SOURCE_SHA:
   raise RuntimeError("N4B_TRAINED_MODELS_NOT_FROZEN")
  if n4meta.get("n_full_observations")!=9519:
   raise RuntimeError("N4B_FULL_EVAL_NOT_COMPLETE")
  quality=parse_n4b_prediction(np,pd,zn)
  original=json.loads(zr.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  packet={(v["case"],v["channel"]):v for v in original["per_case"]}
  if len(packet)!=14:raise RuntimeError("ORIGINAL_RF_TRACE_COUNT_MISMATCH")
  r2index={}
  for case in CASES:
   for channel in ("full","los"):
    rec=packet[(case,channel)]
    raw=zr.read("P2_OUT/"+rec["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=rec["trace_sha256"]:
     raise RuntimeError("P2_SOURCE_TRACE_SHA_CHANGED")
    with np.load(io.BytesIO(raw),allow_pickle=False) as z:
     r2index[(case,channel)]={p:z[p].copy() for p in
       ("t_s","pose_id","truth_for_offline_scoring_only","z_r_m","z_s")}
  for lvl,truth_bias in BIAS.items():
   for case in CASES:
    for channel in ("full","los"):
     datum=r2index[(case,channel)]
     t=datum["t_s"];pose=datum["truth_for_offline_scoring_only"]
     pids=datum["pose_id"]
     z=np.column_stack([datum["z_r_m"],datum["z_s"]])
     if len(t)!=979:raise RuntimeError("NOT_979_POSES")
     controls,x0=build_positive_bias_controls(t,pose,lvl,seed=0)
     q=[quality[(case,int(p))] for p in pids]
     policies=ALL_POLICIES if channel=="full" else LOS_POLICIES
     refname=f"{case}_{channel}_{lvl}_seed0_recursive.npz"
     archive=array_from_npz(np,zref,refname)
     if not(np.array_equal(archive["pose_id"],pids) and
       np.array_equal(archive["t_s"],t) and list(archive["names"])==list(METHODS)):
      raise RuntimeError("R2_BASELINE_IDS_OR_METHODS_CHANGED")
     for method in BASE_METHODS:
      outstates={};policynames=[]
      original_index=list(METHODS).index(method)
      # Make exact reference status decisions before policy differences.
      original_mask=(archive["status"][:,original_index]=="APPLIED")
      for policy in policies:
       pred=recurse(np,t,controls,x0,z,q,method,policy,lut,cases[case])
       outstates[(policy,"natural")]=pred
       policynames.append((policy,"natural"))
       vals=score(np,pred,t,pose,truth_bias)
       row={"case":case,"channel":channel,"bias":lvl,
         "true_gyro_bias_dps":truth_bias,"method":method,
         "policy":policy,"gate_mode":"natural",
         "proper_observation_likelihood_candidate":bool(policy.startswith("GLOBAL_")
              or policy=="BASE_R0"),
         "conditional_packet_or_robust_heuristic":bool(policy in
            ("POWER_JOINT","SIMPLE_DIAG","SIMPLE_JOINT",
             "SIMPLE_G4","G5_RESEARCH_ONLY","ROBUST_GLOBAL_DIAG")),
         **vals}
       scores.append(row)
       if policy=="BASE_R0":
        reference=archive["estimate"][:,original_index,:]
        delta=pred["state"]-reference
        delta[:,2]=wrap(np,delta[:,2])
        max_x=float(np.max(np.abs(delta)))
        max_p=float(np.max(np.abs(pred["cov"]-archive["covariance"][:,original_index,:,:])))
        gate_diff=int(np.sum((pred["status"]=="APPLIED")!=original_mask))
        if max_x>1e-6 or max_p>1e-6 or gate_diff:
         raise RuntimeError("ORIGINAL_R2_RECURSIVE_PARITY_FAIL:"+str((case,lvl,channel,method,max_x,max_p,gate_diff)))
        parities.append({"case":case,"channel":channel,"bias":lvl,
         "method":method,"max_state_diff":max_x,"max_cov_diff":max_p,
         "gate_diff":gate_diff,"strict_1e9":bool(max(max_x,max_p)<1e-9)})
       if channel=="full" and policy in COMMON_GATE_POLICIES:
        counter=recurse(np,t,controls,x0,z,q,method,policy,lut,cases[case],
                        gate_mode="common",shared_gates=original_mask)
        outstates[(policy,"common")]=counter
        policynames.append((policy,"common"))
        scores.append({"case":case,"channel":channel,"bias":lvl,
            "true_gyro_bias_dps":truth_bias,"method":method,
            "policy":policy,"gate_mode":"common",
            "proper_observation_likelihood_candidate":False,
            "conditional_packet_or_robust_heuristic":True,
            **score(np,counter,t,pose,truth_bias)})
      # Save all actual posterior trajectories, covariance, status and NIS.
      np.savez_compressed(out/f"N4C_{case}_{channel}_{lvl}_{method}.npz",
       t_s=t,pose_id=pids,
       policies=np.asarray([x[0] for x in policynames]),
       gate_modes=np.asarray([x[1] for x in policynames]),
       estimate=np.stack([outstates[p]["state"] for p in policynames],axis=1),
       covariance=np.stack([outstates[p]["cov"] for p in policynames],axis=1),
       status=np.stack([outstates[p]["status"] for p in policynames],axis=1),
       nis=np.stack([outstates[p]["nis"] for p in policynames],axis=1))
      print("N4C_CASE "+json.dumps({"case":case,"channel":channel,"bias":lvl,
         "solver":method,"policy_count":len(policynames)}),flush=True)
 def write_csv(filename,rows):
  with (out/filename).open("w",newline="",encoding="utf-8") as f:
   writer=csv.DictWriter(f,fieldnames=list(rows[0]))
   writer.writeheader();writer.writerows(rows)
 write_csv("N4C_RECURSIVE_ALL_METRICS.csv",scores)
 write_csv("N4C_ORIGINAL_J4_SR4_PARITY.csv",parities)
 idx={(r["case"],r["channel"],r["bias"],r["method"],r["policy"],r["gate_mode"]):r for r in scores}
 comparisons=[]
 for case in CASES:
  for bias in BIAS:
   for method in BASE_METHODS:
    reference=idx[(case,"full",bias,method,"BASE_R0","natural")]
    for policy in ALL_POLICIES:
     row=idx[(case,"full",bias,method,policy,"natural")]
     comparisons.append({"case":case,"bias":bias,"solver":method,
        "policy":policy,"heading_delta_deg":row["heading_rmse_deg"]-reference["heading_rmse_deg"],
        "bias_rmse_delta_dps":row["bias_rmse_dps"]-reference["bias_rmse_dps"],
        "xy_rmse_delta_m":row["xy_rmse_m"]-reference["xy_rmse_m"],
        "pose_nees_ratio":row["pose_nees"]/reference["pose_nees"],
        "heading_nees_ratio":row["heading_nees"]/reference["heading_nees"],
        "pose_coverage_delta":row["pose_95coverage"]-reference["pose_95coverage"],
        "heading_coverage_delta":row["heading_95coverage"]-reference["heading_95coverage"]})
 write_csv("N4C_PAIRED_BASELINE_COMPARISONS.csv",comparisons)
 focus=[r for r in scores if r["channel"]=="full" and r["gate_mode"]=="natural" and
    r["policy"] in ("BASE_R0","GLOBAL_MEAN_ONLY","GLOBAL_COV_ONLY_DIAG",
     "GLOBAL_MEAN_COV_DIAG","GLOBAL_MEAN_COV_JOINT","SIMPLE_DIAG",
     "SIMPLE_G4","G5_RESEARCH_ONLY","ROBUST_GLOBAL_DIAG")]
 los_guard=[r for r in scores if r["channel"]=="los" and r["gate_mode"]=="natural" and
  r["policy"] in ("BASE_R0","GLOBAL_MEAN_COV_DIAG","GLOBAL_MEAN_COV_JOINT")]
 # Programmatic decision: a candidate must never worsen m45 AND must improve
 # heading, bias and pose uncertainty for all levels. Don't use result to tune.
 accepted=[]
 for policy in ALL_POLICIES[1:]:
  if any((case,"full",bias,method,policy,"natural") not in idx
      for case in CASES for bias in BIAS for method in BASE_METHODS):
   continue
  arms=[]
  for case in CASES:
   for bias in BIAS:
    for method in BASE_METHODS:
     a=idx[(case,"full",bias,method,policy,"natural")]
     b=idx[(case,"full",bias,method,"BASE_R0","natural")]
     arms.append(a["heading_rmse_deg"]<=b["heading_rmse_deg"]+1e-9 and
       a["bias_rmse_dps"]<=b["bias_rmse_dps"]+1e-9 and
       a["pose_nees"]<=b["pose_nees"]+1e-9 and
       a["pose_95coverage"]>=b["pose_95coverage"]-1e-9)
  if all(arms):accepted.append(policy)
 receipt={"schema":"N4C_J4_SR4_FROZEN_RECURSIVE_ABLATION_V1",
  "stage":"N4-C","status":"N4C_RECURSIVE_EXPLORATORY_COMPLETE",
  "source_sha":os.getenv("GITHUB_SHA"),"frozen_N4B_sha":N4B_SHA,
  "frozen_original_R2_sha":R2_SHA,"frozen_raw_RF_sha":RAW_SHA,
  "n_metric_rows":len(scores),"n_parity_tests":len(parities),
  "bias":BIAS,"methods":BASE_METHODS,"full_policies":ALL_POLICIES,
  "trained_N4B_route_R2_heldout":True,"n4b_conditional_predictions_test_data":True,
  "focus_full":focus,"los_calibration_stress_guard":los_guard,
  "all_condition_nondegradation_candidates":accepted,
  "scientific_PASS":False,
  "limitations":[
   "Packet-conditional covariance given same raw RF features is not a normalized measurement likelihood p(z|state)",
   "N4B heldout R2 is the same corridor as R4/R5 training and includes no independent multipath scene",
   "Only one RF channel realization and sensor-gyro noise seed per condition",
   "LoS transfer of calibration learned on Full is a stress test not a trained clean-LoS quality selector",
   "Empirical Gaussian observation errors may be temporally correlated and mean conditional on geometry",
   "Robust IRLS is a pseudo-likelihood, not a normalized Bayesian posterior",
   "Common mask counterfactual holds original R0 decisions, not causal physical interference identification",
   "Validated RMSE/NEES/coverage improvement is distinct from N4B heldout residual likelihood",
  ]}
 write(out/"N4C_FINAL.json",receipt)
 print("N4C_FINAL "+json.dumps({"status":receipt["status"],
   "rows":len(scores),"parity":len(parities),
   "all_condition_nondegradation_candidates":accepted,
   "focus":[{"case":r["case"],"bias":r["bias"],"method":r["method"],
     "policy":r["policy"],"heading":r["heading_rmse_deg"],"bias_rmse":r["bias_rmse_dps"],
     "pose_nees":r["pose_nees"],"pose95":r["pose_95coverage"],
     "accepted":r["rf_applied"]} for r in focus],
   "los_guard":[{"case":r["case"],"bias":r["bias"],"method":r["method"],"policy":r["policy"],
     "heading":r["heading_rmse_deg"],"pose_nees":r["pose_nees"]} for r in los_guard]},
  ensure_ascii=False),flush=True)
 return 0

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("pre","test","run"),required=True)
 ap.add_argument("--out")
 ap.add_argument("--audit");ap.add_argument("--raw");ap.add_argument("--r2");ap.add_argument("--n4b")
 arg=ap.parse_args()
 if arg.phase=="pre":return preflight(arg.out)
 if arg.phase=="test":return simulation_unit_tests()
 if not all([arg.out,arg.audit,arg.raw,arg.r2,arg.n4b]):raise RuntimeError("RUN_INPUTS_MISSING")
 return execute(arg.out,arg.audit,arg.raw,arg.r2,arg.n4b)

if __name__=="__main__":raise SystemExit(main())
