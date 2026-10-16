"""EXP2, EXP3, EXP4: rigorous frozen R2 POWER_JOINT factor, oracle and clean LoS checks.

EXP2: Six required mean/cov arms + diag and cross-term ablations, using the
       original POWER gate mask or natural gates, fixed original wheel Q and LUT.
EXP3: GT-based signed-range low-frequency removal, noncausal oracle diagnostic.
       All prediction means/cov remain frozen; corrected r changes but q does not.
EXP4: TRUE native LoS packet first-path P1/P2 -> q -> frozen Full-trained POWER.
       Paired original R0, and mean/cov only negative controls.

Original R4/R5 samples lack validated times and wheel/gyro controls; those
recursions are forbidden and specified separately as new simulation request.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BLOBS={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
SHA={
 "RF":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "R2":"ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399",
 "N4B":"170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b",
 "N4C":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9"
}
CASES=("R2_aA_m0","R2_aA_m45")
LEVELS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
SOLVERS=("J4","SR4")
EXP2_POLICIES=("R0","MUR_ONLY","MUS_ONLY","MEAN_ONLY","COV_ONLY","FULL",
  "FULL_DIAG","FULL_NO_MUR","FULL_NO_MUS")
EXP2_GATES=("power_mask","natural")
EXP3_VARIANTS=("ORIGINAL","TRAIL25","TRAIL50","CENTER25_ORACLE","CENTER50_ORACLE",
  "SHIFT25_PLACEBO","GLOBAL_MEAN_ORACLE","RAW_RANGE_ORACLE")
EXP4_POLICIES=("R0","FULL","MEAN_ONLY","COV_ONLY","MUR_ONLY","MUS_ONLY")
GATE_CRITERION=9.210340371976184
B_OLD=-.5315983906250129
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as fp:
  for c in iter(lambda:fp.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def blob(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def save(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def checked(f,expected):
 if sha(f)!=expected:raise RuntimeError("ARCHIVE_SHA_MISMATCH:"+str(f))
 z=zipfile.ZipFile(f)
 if z.testzip():raise RuntimeError("ZIP_BAD_CRC")
 return z
def member(z,name):
 a=[s for s in z.namelist() if s==name or s.endswith("/"+name)]
 if len(a)!=1:raise RuntimeError("ARCHIVE_MEMBER_MISSING_OR_DUP:"+name)
 return a[0]
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("CLOUD_RUN_REQUIRED")
 if head!=os.getenv("GITHUB_SHA"):errors.append("GIT_SHA_MISMATCH")
 for p,h in BLOBS.items():
  f=ROOT/p
  if not f.exists():errors.append("FROZEN_SOURCE_MISSING:"+p)
  elif blob(f)!=h:errors.append("FROZEN_SOURCE_CHANGED:"+p)
 try:ast.parse((HERE/"exp234_recursive.py").read_text())
 except Exception as e:errors.append("CODE_SYNTAX:"+repr(e))
 w=ROOT/".github/workflows/r5-exp234-recursive.yml"
 if not w.exists():errors.append("WORKFLOW_MISSING")
 else:
  s=w.read_text()
  seq=("exp234_recursive.py --phase audit","exp234_recursive.py --phase test",
       "exp234_recursive.py --phase exp2","exp234_recursive.py --phase exp3",
       "exp234_recursive.py --phase exp4")
  if not all(x in s for x in seq) or not all(s.index(seq[i])<s.index(seq[i+1]) for i in range(len(seq)-1)):
   errors.append("AUDIT_FIRST_EXECUTION_ORDER")
  if "if: always()" not in s or "actions: read" not in s:errors.append("EVIDENCE_RULE")
 receipt={"source_commit":head,"status":"AUDITED" if not errors else "HOLD",
  "errors":errors,"original_git_blobs":BLOBS,"archive_sha256":SHA,
  "experiments":["EXP2","EXP3","EXP4_NATIVE_LOS"],
  "R4R5_sequential_recursion_eligible":False,
  "R2_last_hidden_test":False}
 save(out/"PRE_AUDIT.json",receipt)
 print("R5_EXP234_AUDIT "+json.dumps({"status":receipt["status"],"errors":errors}),flush=True)
 return 0 if not errors else 2
def setup():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
  str(ROOT/"research/R5_N4C_20261015"),
  str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"),
  str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src")
 ]
 import n4c_joint_sr4 as frozen
 from core import gaussian_update,wrap
 from r2_bias_replay import build_positive_bias_controls,predict_one,METHODS as ORIGINAL_METHODS
 from p3_rf_adapter4 import FrozenLut,R0
 return np,pd,frozen,gaussian_update,wrap,build_positive_bias_controls,predict_one,ORIGINAL_METHODS,FrozenLut,R0

def unit():
 np,pd,frozen,gaussian_update,wrap,*_=setup()
 frozen.simulation_unit_tests()
 rng=np.random.default_rng(20261016)
 for i in range(25):
  V=np.array([[rng.uniform(.004,.1),.003],[.003,rng.uniform(.003,.07)]])
  mu=rng.normal(0,.1,2)
  for mode in EXP2_POLICIES:
   a,R=select(np,mode,mu,V,np.diag([.0068578637,.0081]))
   assert R.shape==(2,2) and np.linalg.eigvalsh(R).min()>0
   if mode=="COV_ONLY":np.testing.assert_array_equal(a,np.zeros(2))
   if mode=="FULL":np.testing.assert_array_equal(R,V)
   if mode=="FULL_DIAG":assert R[0,1]==R[1,0]==0
   if mode=="MUR_ONLY":assert a[1]==0
   if mode=="MUS_ONLY":assert a[0]==0
 # Check low pass definitions including causal-only trailing and future-containing centered
 a=np.arange(60,dtype=float)
 tr=lowpass(np,a,25,False);ce=lowpass(np,a,25,True)
 assert tr[24]==12 and ce[24]==24 and tr[24]!=ce[24]
 print("R5_EXP234_UNIT_PASS "+json.dumps({"gaussian_tests":25,
   "N4C_original_whitened_equivalence":"PASS",
   "trailing_causal_centre_noncausal":"DISTINGUISHED"}),flush=True)
 return 0
def select(np,policy,original_mu,original_cov,R0):
 mu=np.asarray(original_mu,float)
 r=np.asarray(original_cov,float)
 if policy=="R0":return np.zeros(2,float),R0.copy()
 if policy=="MUR_ONLY":return np.array([mu[0],0.]),R0.copy()
 if policy=="MUS_ONLY":return np.array([0.,mu[1]]),R0.copy()
 if policy=="MEAN_ONLY":return mu.copy(),R0.copy()
 if policy=="COV_ONLY":return np.zeros(2,float),r.copy()
 if policy=="FULL":return mu.copy(),r.copy()
 if policy=="FULL_DIAG":return mu.copy(),np.diag(np.diag(r))
 if policy=="FULL_NO_MUR":return np.array([0.,mu[1]]),r.copy()
 if policy=="FULL_NO_MUS":return np.array([mu[0],0.]),r.copy()
 raise RuntimeError("UNKNOWN_MODE:"+str(policy))

def lowpass(np,arr,width,center):
 # Trailing is causal but oracle residual itself comes from full Ground Truth.
 a=np.asarray(arr,float);n=len(a);r=np.empty(n)
 if center:
  left=(width-1)//2;right=width-1-left
  for k in range(n):r[k]=np.mean(a[max(0,k-left):min(n,k+right+1)])
 else:
  sums=np.r_[0.,np.cumsum(a)]
  for k in range(n):
   start=max(0,k-width+1);r[k]=(sums[k+1]-sums[start])/(k+1-start)
 return r
def run_estimator(np,frozen,gaussian_update,predict,
       t,controls,x0,z,case,lut,params,mode,solver,
       gate_mode="natural",forced_mask=None):
 from r2_bias_replay import INITIAL_POSE_STD,BIAS_PRIOR_STD
 x=np.r_[x0,0.]
 P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 n=len(t)
 X=np.empty((n,4));PP=np.empty((n,4,4));priX=np.empty((n,4));priP=np.empty((n,4,4))
 NIS=np.empty(n);status=np.empty(n,dtype="<U12");K=np.empty((n,4,2));vr=np.empty(n)
 for k in range(n):
  if k>0:
   x,P=predict(x,P,float(controls["ds_odom"][k]),float(controls["dtheta_gyro"][k]),
     float(controls["dt_s"][k]))
  priX[k]=x;priP[k]=P
  mu,r=select(np,mode,params[k]["mean"],params[k]["cov"],
       np.diag([.0068578637,.0081]))
  if np.linalg.eigvalsh(r).min()<=0:raise RuntimeError("NOT_SPD_R")
  h,H=lut.model(x,case);nu=z[k]-h-mu
  S=H@P@H.T+r
  nis=float(nu@np.linalg.solve(S,nu))
  K[k]=np.linalg.solve(S,H@P).T;vr[k]=r[0,0]
  if gate_mode=="natural":accept=nis<=GATE_CRITERION
  elif gate_mode=="power_mask":
   if forced_mask is None:raise RuntimeError("MISSING_ORIGINAL_POWER_MASK")
   accept=bool(forced_mask[k])
  else:raise RuntimeError("UNKNOWN_GATE")
  if accept:
   if solver=="J4":
    xp,pp,diag=gaussian_update(x,P,z[k]-mu,lambda a:lut.model(a,case),r)
   elif solver=="SR4":
    xp,pp=frozen.correlated_sr4(np,x,P,z[k],mu,r,lut,case)
   else:raise RuntimeError("SOLVER")
  else:xp,pp=x.copy(),P.copy()
  if not(np.isfinite(xp).all() and np.isfinite(pp).all() and np.linalg.eigvalsh(pp).min()>0):
   raise RuntimeError("NONPOSITIVE_OR_NONFINITE:"+str((mode,k)))
  X[k]=x=xp;PP[k]=P=pp;status[k]="APPLIED" if accept else "REJECT";NIS[k]=nis
 return {"state":X,"cov":PP,"status":status,"nis":NIS,
         "robust_R_scale":np.ones(n),"prior_x":priX,"prior_P":priP,"K":K,
         "effective_Vr":vr}
def condxy(np,state,cov,truth,t):
 sel=t>=30;xx=state[sel];p=cov[sel,:3,:3]
 e=xx[:,:3]-truth[sel];e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
 h=e[:,2]**2/p[:,2,2]
 M=p[:,:2,:2]-p[:,:2,2,None]*p[:,None,2,:2]/p[:,2,2,None,None]
 v=e[:,:2]-p[:,:2,2]/p[:,2,2,None]*e[:,2,None]
 ne=np.einsum("ni,ni->n",v,np.linalg.solve(M,v[...,None])[:,:,0])
 l,U=np.linalg.eigh(M)
 if l.min()<=0:raise RuntimeError("NEGATIVE_COND_XY_EIG")
 proj=np.einsum("nij,ni->nj",U,v)
 eig_ne=proj[:,0]**2/l[:,0]
 total=h+ne
 check=np.einsum("ni,ni->n",e,np.linalg.solve(p,e[...,None])[:,:,0])
 if np.max(abs(total-check))>1e-7:raise RuntimeError("COND_XY_SCHUR_NEES_FAIL")
 return {"conditional_xy_nees":float(np.mean(ne)),
   "conditional_xy_minor_nees":float(np.mean(eig_ne)),
   "conditional_xy_95coverage":float(np.mean(ne<=5.9914645471)),
   "narrow_axis_95coverage":float(np.mean(eig_ne<=3.841458821)),
   "heading_nees_schur":float(np.mean(h)),
   "median_narrow_sigma_cm":float(np.median(np.sqrt(l[:,0]))*100)}
def verify_meta(np,pd,frozen,fr,zr,zq,zc):
 nf=json.loads(zr.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
 pair={(v["case"],v["channel"]):v for v in nf["per_case"]}
 rawmeta=json.loads(zq.read(member(zq,"N4B_FINAL.json")))
 if rawmeta["n_full_observations"]!=9519:raise RuntimeError("N4B_SIZE_WRONG")
 lut=__import__("p3_rf_adapter4").FrozenLut(ROOT)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cases={row["id"]:row for row in manifest["cases"]}
 quality=frozen.parse_n4b_prediction(np,pd,zq)
 with gzip.open(io.BytesIO(zq.read(member(zq,"N4B_OOF_PREDICTIONS.csv.gz"))),"rt") as g:
  db=pd.read_csv(g)
 d=db[(db.route=="R2")&(db.model=="POWER_BIN_JOINT")].copy()
 if len(d)!=3909:raise RuntimeError("EXPECTED_R2_OOF_3909")
 config=json.loads(zq.read(member(zq,"N4B_TRAIN_ONLY_MODEL_CONFIG.json")))
 cand=[r for r in config if r["held_route"]=="R2" and r["model"]=="POWER_BIN_JOINT"]
 if len(cand)!=1:raise RuntimeError("TRAIN_CONFIG_NOT_UNIQUE")
 cuts=np.asarray(cand[0]["cutpoints_train"],float)
 groups=np.searchsorted(cuts,d["log_fp_power"].to_numpy(float),side="right")
 A=np.stack([d.log_fp_power.to_numpy(float),*(groups==i for i in range(3))],axis=1)
 coefs=np.linalg.lstsq(A,d[["mu_r","mu_s"]].to_numpy(float),rcond=None)[0]
 residual=A@coefs-d[["mu_r","mu_s"]].to_numpy(float)
 if np.max(abs(residual))>1e-8:raise RuntimeError("RECONSTRUCTED_R2_PARAMS_NOT_EQUIVALENT")
 covs=[]
 for b in range(3):
  sel=d.iloc[np.flatnonzero(groups==b)]
  C=sel[["Vr","Vs","C_rs"]].to_numpy(float)
  if np.max(abs(C-C[0]))>1e-9:raise RuntimeError("COVARIANCE_BINS_NOT_UNIQUE")
  v=C[0];covs.append([[v[0],v[2]],[v[2],v[1]]])
 print("R5_EXP234_FROZEN_MODEL "+json.dumps({"cuts":cuts.tolist(),
    "mu_slope_intercepts":coefs.tolist(),"bin_covs":covs,"fit_max_error":float(abs(residual).max())}))
 return pair,cases,quality,lut,cuts,coefs,np.asarray(covs)
def r2_native(np,zr,desc):
 raw=zr.read("P2_OUT/"+desc["trace_file"])
 if hashlib.sha256(raw).hexdigest()!=desc["trace_sha256"]:
  raise RuntimeError("ORIGINAL_RF_PACKET_SHA_MISMATCH")
 with np.load(io.BytesIO(raw),allow_pickle=False) as a:
  return {k:a[k].copy() for k in a.files}
def q_from_los(np,power,cuts,coefs,covs):
 p=np.asarray(power,float)
 if p.ndim!=2 or p.shape[1]!=2 or not(np.isfinite(p).all() and (p>0).all()):
  raise RuntimeError("NATIVE_LOS_POWER_FORMAT_INVALID")
 q=np.log10(p.sum(axis=1))
 bins=np.searchsorted(cuts,q,side="right")
 x=np.stack([q,*(bins==b for b in range(3))],axis=1)
 means=x@coefs
 return [{"mean":means[k].copy(),"cov":covs[bins[k]].copy()} for k in range(len(q))],q,bins
def check_original(np,run,zref,names,case,channel,bias,solver,quality_file):
 key=list(names).index(solver)
 if quality_file is None:
  saved=zref.read(member(zref,f"{case}_{channel}_{bias}_seed0_recursive.npz"))
  with np.load(io.BytesIO(saved),allow_pickle=False) as a:
   X=a["estimate"][:,key,:].copy();P=a["covariance"][:,key,:,:].copy()
   st=a["status"][:,key].copy()
 else:
  z=quality_file.read(member(quality_file,f"N4C_{case}_{channel}_{bias}_{solver}.npz"))
  with np.load(io.BytesIO(z),allow_pickle=False) as a:
   ids=np.flatnonzero((a["policies"]=="POWER_JOINT")&(a["gate_modes"]=="natural"))
   if len(ids)!=1:raise RuntimeError("ORIGINAL_POWER_POLICY_NOT_UNIQUE")
   ix=int(ids[0]);X=a["estimate"][:,ix,:].copy()
   P=a["covariance"][:,ix,:,:].copy();st=a["status"][:,ix].copy()
 delta=run["state"]-X;delta[:,2]=(delta[:,2]+np.pi)%(2*np.pi)-np.pi
 maxx=float(np.max(abs(delta)));maxp=float(np.max(abs(run["cov"]-P)))
 nbad=int(np.sum((run["status"]=="APPLIED")!=(st=="APPLIED")))
 if max(maxx,maxp)>1e-6 or nbad:
  raise RuntimeError("FROZEN_ORIGINAL_RECURSIVE_PARITY_FAILED:"+
    str((case,bias,solver,quality_file is not None,maxx,maxp,nbad)))
 return {"case":case,"channel":channel,"bias":bias,"solver":solver,
   "model":"POWER" if quality_file else "R0",
   "max_state":maxx,"max_P":maxp,"n_gate_diff":nbad}
def openall(args):
 return checked(args.rf,SHA["RF"]),checked(args.r2,SHA["R2"]),\
        checked(args.n4b,SHA["N4B"]),checked(args.n4c,SHA["N4C"])
def verify_receipt(path):
 d=json.loads(Path(path).read_text())
 if d["status"]!="AUDITED" or d["source_commit"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("PRE_AUDIT_HOLD")
def csvout(name,rows):
 with open(name,"w",newline="",encoding="utf8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def test_R4R5_ineligible():
 # Must never fabricate timed odometry from one-step yaw sweep samples.
 meta=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 for c in meta["cases"]:
  if c["route"] in ("R4","R5"):
   assert "trace_t_s" not in c and "wheel_gyro_control_path" not in c
 return {"R4R5_verified_timed_controls":False,"reason":"Original SAMPLES file lacks authenticated t_s/ds_odom/dtheta_gyro/dt_s of actual traversal"}
