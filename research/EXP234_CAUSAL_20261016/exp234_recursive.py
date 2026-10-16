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


def exp2(out,args):
 np,pd,frozen,gaussian_update,wrap,generate,predict,names,FrozenLut,R0=setup()
 verify_receipt(args.audit);out=Path(out);out.mkdir(parents=True,exist_ok=False)
 entries=[];steps=[];parities=[];per_arm_checks=[];series_info=[]
 with checked(args.rf,SHA["RF"]) as zr,checked(args.r2,SHA["R2"]) as ref, \
      checked(args.n4b,SHA["N4B"]) as zq,checked(args.n4c,SHA["N4C"]) as zc:
  pair,cases,quality,lut,cuts,coefs,covs=verify_meta(np,pd,frozen,None,zr,zq,zc)
  for case in CASES:
   for bias,true_b in LEVELS.items():
    raw=r2_native(np,zr,pair[(case,"full")])
    t=raw["t_s"];pids=raw["pose_id"]
    truth=raw["truth_for_offline_scoring_only"]
    obs=np.stack([raw["z_r_m"],raw["z_s"]],axis=-1)
    controls,x0=generate(t,truth,bias,seed=0)
    q=[quality[(case,int(pid))]["POWER_BIN_JOINT"] for pid in pids]
    for solver in SOLVERS:
     saved=zc.read(member(zc,f"N4C_{case}_full_{bias}_{solver}.npz"))
     with np.load(io.BytesIO(saved),allow_pickle=False) as z:
      active=np.flatnonzero((z["policies"]=="POWER_JOINT")&(z["gate_modes"]=="natural"))
      if len(active)!=1:raise RuntimeError("BAD_ORIGINAL_POWER_POLICY")
      orig_mask=(z["status"][:,int(active[0])]=="APPLIED").copy()
     runs={}
     for policy in EXP2_POLICIES:
      for gate in EXP2_GATES:
       key=(policy,gate)
       run=run_estimator(np,frozen,gaussian_update,predict,
         t,controls,x0,obs,cases[case],lut,q,policy,solver,gate,orig_mask)
       runs[key]=run
       if policy=="R0" and gate=="natural":
        parities.append(check_original(np,run,ref,names,case,"full",bias,solver,None))
       if policy=="FULL" and gate=="natural":
        parities.append(check_original(np,run,ref,names,case,"full",bias,solver,zc))
       s=frozen.score(np,run,t,truth,true_b)
       diag=condxy(np,run["state"],run["cov"],truth,t)
       ev=t>=30
       row={"case":case,"mount_deg":cases[case]["mount_deg"],"bias":bias,"solver":solver,
        "policy":policy,"gate_mode":gate,"common_gate_source":"frozen_original_POWER" if gate=="power_mask" else "natural",
        "n":int(ev.sum()),**s,**diag,
        "mean_abs_K_b_s":float(np.mean(abs(run["K"][ev,3,1]))),
        "mean_abs_K_b_r":float(np.mean(abs(run["K"][ev,3,0]))),
        "mean_abs_K_h_s":float(np.mean(abs(run["K"][ev,2,1]))),
        "longest_reject_run":int(max(
          [len(x) for x in "".join("1" if v=="REJECT" else "0" for v in run["status"][ev]).split("0")]+[0])),
        "median_NIS":float(np.median(run["nis"][ev]))}
       entries.append(row)
     # Factor ablation invariants, natural joint and fixed mask must keep original observation.
     rawrun=runs[("FULL","natural")]
     if not np.array_equal((rawrun["status"]=="APPLIED"),orig_mask):
      raise RuntimeError("FROZEN_GATE_PARITY_FAIL")
     if not np.array_equal(
         runs[("R0","power_mask")]["status"]=="APPLIED",orig_mask):
      raise RuntimeError("COMMON_GATE_CONTRACT_INVALID")
     # A one-step counterfactual is evaluated from the same original POWER prior;
     # matched posterior is the archived frozen POWER path.
     if bias in ("B0","L2"):
      eligible=np.flatnonzero(t>=30)
      for pol in EXP2_POLICIES:
       group=[]
       for k in eligible:
        xp=rawrun["prior_x"][k];PP=rawrun["prior_P"][k]
        mu,R=select(np,pol,q[k]["mean"],q[k]["cov"],R0)
        h,H=lut.model(xp,cases[case]);innov=obs[k]-h-mu
        nis=float(innov@np.linalg.solve(H@PP@H.T+R,innov))
        if orig_mask[k]:
         if solver=="J4":
          new,newP,_=gaussian_update(xp,PP,obs[k]-mu,
            lambda xx:lut.model(xx,cases[case]),R)
         else:
          new,newP=frozen.correlated_sr4(np,xp,PP,obs[k],mu,R,lut,cases[case])
        else:new,newP=xp.copy(),PP.copy()
        ee=new[2]-truth[k,2];ee=float(wrap(ee))
        eb=new[3]-math.radians(true_b)
        pstate=rawrun["state"][k]
        power_ee=float(wrap(pstate[2]-truth[k,2]))
        power_eb=pstate[3]-math.radians(true_b)
        group.append([ee**2-power_ee**2,eb**2-power_eb**2,nis])
       v=np.asarray(group,float)
       steps.append({"case":case,"bias":bias,"solver":solver,
        "mode":"fixed_original_POWER_prior_and_Gate",
        "policy":pol,"n":len(v),
        "delta_heading_squared_error_deg2":float(v[:,0].mean()*(180/math.pi)**2),
        "delta_bias_squared_error_dps2":float(v[:,1].mean()*(180/math.pi)**2),
        "mean_own_preGate_NIS":float(v[:,2].mean())})
     keys=list(runs)
     np.savez_compressed(out/f"EXP2_{case}_{bias}_{solver}.npz",
       t_s=t,pose_id=pids,policy=np.asarray([a for a,b in keys]),
       gate_mode=np.asarray([b for a,b in keys]),
       estimate=np.stack([runs[k]["state"] for k in keys],axis=1),
       covariance=np.stack([runs[k]["cov"] for k in keys],axis=1),
       prior_x=np.stack([runs[k]["prior_x"] for k in keys],axis=1),
       prior_P=np.stack([runs[k]["prior_P"] for k in keys],axis=1),
       nis=np.stack([runs[k]["nis"] for k in keys],axis=1),
       K=np.stack([runs[k]["K"] for k in keys],axis=1),
       status=np.stack([runs[k]["status"] for k in keys],axis=1))
     print("EXP2_CASE "+json.dumps({"case":case,"bias":bias,"solver":solver,
       "policies":len(keys)}),flush=True)
 csvout(out/"EXP2_SIXWAY_PLUS_ABLATIONS.csv",entries)
 csvout(out/"EXP2_COMMON_PRIOR_ONE_STEP.csv",steps)
 csvout(out/"EXP2_BASELINE_PARITY.csv",parities)
 report={"status":"EXP2_FROZEN_SIXWAY_PLUS_FACTORIAL_RECURSIVE_COMPLETED",
   "n_recursive_arms":len(entries),"n_matched_one_step":len(steps),
   "original_N4C_R0_POWER_parity":len(parities),
   "n_independent_RF_scenes":1,"input_splits":"R4_R5_train_R2_test",
   "six_required":EXP2_POLICIES[:6],
   "all_variants":EXP2_POLICIES,"gate_types":EXP2_GATES,
   "B0_L2_J4":[x for x in entries if x["bias"] in ("B0","L2") and x["solver"]=="J4"],
   "limitations":["common POWER gate forced in offline replay; not a deployable gate",
     "same corridor and sensor seed0 across levels",
     "correlated SR4 nonlinear order may differ from J4",
     "R2 repeatedly tested; not a fresh independent scene"],
   "scientific_generalization_PASS":False}
 save(out/"EXP2_FINAL.json",report)
 print("EXP2_FINAL "+json.dumps({"status":report["status"],"arms":len(entries),
   "one_step":len(steps),"parities":len(parities),
   "L2_J4":[{k:v for k,v in s.items() if k in (
       "case","policy","gate_mode","heading_rmse_deg","xy_rmse_m",
       "bias_rmse_dps","pose_nees","conditional_xy_nees","pose_95coverage","rf_applied"
       )} for s in entries if s["bias"]=="L2" and s["solver"]=="J4"]},
   ensure_ascii=False),flush=True)
 return 0

def exp3(out,args):
 np,pd,frozen,gaussian_update,wrap,generate,predict,names,FrozenLut,R0=setup()
 verify_receipt(args.audit);out=Path(out);out.mkdir(parents=True,exist_ok=False)
 metrics=[];residuals=[];parities=[]
 with checked(args.rf,SHA["RF"]) as zr,checked(args.r2,SHA["R2"]) as ref, \
      checked(args.n4b,SHA["N4B"]) as zq,checked(args.n4c,SHA["N4C"]) as zc:
  pair,cases,quality,lut,cuts,coefs,covs=verify_meta(np,pd,frozen,None,zr,zq,zc)
  with gzip.open(io.BytesIO(zq.read(member(zq,"N4B_OOF_PREDICTIONS.csv.gz"))),"rt") as f:
   allpred=pd.read_csv(f)
  idx=allpred[(allpred.model=="POWER_BIN_JOINT")&(allpred.route=="R2")].set_index(["case","pose_id"])
  for case in CASES:
   src=r2_native(np,zr,pair[(case,"full")])
   t=src["t_s"];pids=src["pose_id"];truth=src["truth_for_offline_scoring_only"]
   z=np.column_stack([src["z_r_m"],src["z_s"]])
   q=[quality[(case,int(pid))]["POWER_BIN_JOINT"] for pid in pids]
   # Cross-check oracle r error from the original per-packet N4B source.
   gt_r=np.array([lut.model(truth[k],cases[case])[0][0] for k in range(len(t))])
   residual=z[:,0]-gt_r-np.array([p["mean"][0] for p in q])
   orig_err=idx.loc[[(case,int(pid)) for pid in pids]]
   discrepancy=float(np.max(abs((z[:,0]-gt_r)-orig_err.e_r.to_numpy())))
   if discrepancy>5e-6:raise RuntimeError("EXP3_ORIGINAL_RF_ERROR_NOT_PAIRED")
   corrections={
     "ORIGINAL":np.zeros(len(t)),
     "TRAIL25":lowpass(np,residual,25,False),
     "TRAIL50":lowpass(np,residual,50,False),
     "CENTER25_ORACLE":lowpass(np,residual,25,True),
     "CENTER50_ORACLE":lowpass(np,residual,50,True),
     "SHIFT25_PLACEBO":np.roll(lowpass(np,residual,25,False),125),
     "GLOBAL_MEAN_ORACLE":np.full(len(t),float(np.mean(residual))),
     "RAW_RANGE_ORACLE":residual.copy()
   }
   for name,trend in corrections.items():
    rem=residual-trend
    def corr_lag(a,lag=1):
     return float(np.corrcoef(a[:-lag],a[lag:])[0,1]) if len(a)>lag+3 else None
    # Only one physical scene: this ACF has deterministic spatial dependence.
    residuals.append({"case":case,"variant":name,"n":len(t),
       "correction_r_mean_m":float(np.mean(trend)),
       "correction_r_std_m":float(np.std(trend)),
       "retained_residual_r_mean_m":float(np.mean(rem)),
       "retained_residual_r_std_m":float(np.std(rem)),
       "retained_lag1":corr_lag(rem),
       "original_lag1":corr_lag(residual),
       "mean_correction_95_135_m":float(np.mean(trend[(t>=95)&(t<=135)])),
       "is_oracle_using_GT":name!="ORIGINAL",
       "contains_future_source":name.startswith("CENTER"),
       "time_matched_negative_placebo":name=="SHIFT25_PLACEBO"})
   for bias in ("B0","L2"):
    controls,x0=generate(t,truth,bias,seed=0)
    for solver in SOLVERS:
     orig=zc.read(member(zc,f"N4C_{case}_full_{bias}_{solver}.npz"))
     with np.load(io.BytesIO(orig),allow_pickle=False) as za:
      j=np.flatnonzero((za["policies"]=="POWER_JOINT")&(za["gate_modes"]=="natural"))
      if len(j)!=1:raise RuntimeError("N4C_BASELINE_MISSING")
      i=int(j[0]);original_states=za["estimate"][:,i,:].copy()
      original_cov=za["covariance"][:,i,:,:].copy()
      orig_mask=(za["status"][:,i]=="APPLIED")
     runs={}
     for variant in EXP3_VARIANTS:
      zz=z.copy();zz[:,0]-=corrections[variant]
      run=run_estimator(np,frozen,gaussian_update,predict,t,controls,x0,
         zz,cases[case],lut,q,"FULL",solver,"natural")
      runs[variant]=run
      if variant=="ORIGINAL":
       dd=run["state"]-original_states;dd[:,2]=(dd[:,2]+np.pi)%(2*np.pi)-np.pi
       if max(float(np.max(abs(dd))),float(np.max(abs(run["cov"]-original_cov))))>1e-6 \
          or not np.array_equal(run["status"]=="APPLIED",orig_mask):
        raise RuntimeError("ORIGINAL_POWER_ORACLE_SIM_PARITY_FAILED")
       parities.append({"case":case,"bias":bias,"solver":solver,
        "state_max":float(np.max(abs(dd))),"cov_max":float(np.max(abs(run["cov"]-original_cov)))})
      out_=frozen.score(np,run,t,truth,LEVELS[bias])
      vals=condxy(np,run["state"],run["cov"],truth,t)
      within=(t>=95)&(t<=135)
      C=run["cov"][within,:3,:3];xx=run["state"][within,:3];tr=truth[within]
      e=xx-tr;e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
      v=C[:,:2,:2]-C[:,:2,2,None]*C[:,None,2,:2]/C[:,2,2,None,None]
      conditioned=e[:,:2]-C[:,:2,2]/C[:,2,2,None]*e[:,2,None]
      win_ne=np.einsum("ni,ni->n",conditioned,
                      np.linalg.solve(v,conditioned[...,None])[:,:,0])
      metrics.append({"case":case,"bias":bias,"solver":solver,
       "variant":variant,"oracle_gt_used_for_correction":variant!="ORIGINAL",
       "noncausal_future_dependency":variant.startswith("CENTER"),
       "n_window":int(sum(within)),"condxy_nees_95_135":float(win_ne.mean()),
       "xy_RMSE_95_135_m":float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
       **out_,**vals})
     keys=list(runs)
     np.savez_compressed(out/f"EXP3_{case}_{bias}_{solver}.npz",
       t_s=t,pose_id=pids,variant=np.asarray(keys),
       raw_range=z[:,0],offline_true_range=gt_r,original_rf_residual=residual,
       oracle_corrections=np.stack([corrections[k] for k in keys],axis=1),
       estimate=np.stack([runs[k]["state"] for k in keys],axis=1),
       covariance=np.stack([runs[k]["cov"] for k in keys],axis=1),
       prior_x=np.stack([runs[k]["prior_x"] for k in keys],axis=1),
       prior_P=np.stack([runs[k]["prior_P"] for k in keys],axis=1),
       status=np.stack([runs[k]["status"] for k in keys],axis=1),
       NIS=np.stack([runs[k]["nis"] for k in keys],axis=1))
     print("EXP3_CASE "+json.dumps({"case":case,"bias":bias,"solver":solver,
       "arms":len(keys),"r2_range_error_parity_max":discrepancy}),flush=True)
 csvout(out/"EXP3_ORACLE_RECURSIVE.csv",metrics)
 csvout(out/"EXP3_LPF_DIAGNOSTIC.csv",residuals)
 csvout(out/"EXP3_BASELINE_PARITY.csv",parities)
 info={"status":"EXP3_GT_ORACLE_RANGE_LOW_PASS_ABLATION_COMPLETE",
   "n_arms":len(metrics),"n_baseline_parity":len(parities),
   "all_gt_corrected_are_oracle_and_not_online":True,
   "orig_q_mu_R_Q_unchanged":True,
   "new_filter_P_is_recomputed_in_recursion":True,
   "nominal_conditional_XY_NEES":2,
   "focus":[v for v in metrics if v["bias"]=="L2" and v["solver"]=="J4"],
   "original_residual_checks":residuals,
   "limitations":[
    "Computing e_r requires TRUE Range from ground truth, unavailable online",
    "TRAIL windows are trailing only but still offline oracle owing to GT",
    "CENTER windows use future samples and are noncausal oracle",
    "Removing residual changes estimated state, Jacobians, gating and P trajectories",
    "If NEES improves, proves only possible source-specific signal effect, not origin of colored noise",
    "One corridor and no independently generated multipath trials"],
   "scientific_causal_colored_noise_proven":False}
 save(out/"EXP3_FINAL.json",info)
 print("EXP3_FINAL "+json.dumps({"status":info["status"],"arms":len(metrics),
   "parity":len(parities),
   "L2J4":[{k:v for k,v in x.items() if k in(
    "case","variant","heading_rmse_deg","bias_rmse_dps","xy_rmse_m",
    "conditional_xy_nees","condxy_nees_95_135","pose_nees","pose_95coverage",
    "rf_applied")} for x in metrics if x["bias"]=="L2" and x["solver"]=="J4"]},
    ensure_ascii=False),flush=True)
 return 0

def exp4(out,args):
 np,pd,frozen,gaussian_update,wrap,generate,predict,names,FrozenLut,R0=setup()
 verify_receipt(args.audit);out=Path(out);out.mkdir(parents=True,exist_ok=False)
 results=[];parities=[];pq=[]
 with checked(args.rf,SHA["RF"]) as zr,checked(args.r2,SHA["R2"]) as ref, \
      checked(args.n4b,SHA["N4B"]) as zq,checked(args.n4c,SHA["N4C"]) as zc:
  pair,cases,quality,lut,cuts,coefs,covs=verify_meta(np,pd,frozen,None,zr,zq,zc)
  for case in CASES:
   raw=r2_native(np,zr,pair[(case,"los")])
   t=raw["t_s"];pids=raw["pose_id"];truth=raw["truth_for_offline_scoring_only"]
   z=np.column_stack([raw["z_r_m"],raw["z_s"]])
   p=raw["power"]
   # The native clean LoS q is from exactly the same first-path tap as s.
   s_direct=(p[:,0]-p[:,1])/(p[:,0]+p[:,1])
   if np.max(abs(z[:,1]-s_direct))>1e-11:
    raise RuntimeError("LOS_S_AND_POWER_DIFFERENT_TAPS")
   native,q_los,bin_los=q_from_los(np,p,cuts,coefs,covs)
   qfull=np.asarray([q_from["POWER_BIN_JOINT"]["mean"] for q_from in
       [quality[(case,int(pid))] for pid in pids]])
   pq.append({"case":case,"n":len(t),"n_eval":int(sum(t>=30)),
    "median_q_los":float(np.median(q_los[t>=30])),
    "bin_low":int(sum(bin_los[t>=30]==0)),
    "bin_mid":int(sum(bin_los[t>=30]==1)),
    "bin_high":int(sum(bin_los[t>=30]==2)),
    "avg_native_los_power_correction_r_m":float(np.mean(
        [v["mean"][0] for v in native if True])),
    "source_note":"Native LoS power from P2 archive, NOT reused Full packet q"})
   for bias,true_b in LEVELS.items():
    controls,x0=generate(t,truth,bias,seed=0)
    for solver in SOLVERS:
     runs={}
     for variant in EXP4_POLICIES:
      outrec=run_estimator(np,frozen,gaussian_update,predict,
        t,controls,x0,z,cases[case],lut,native,variant,solver,"natural")
      runs[variant]=outrec
      if variant=="R0":
       parities.append(check_original(np,outrec,ref,names,case,"los",bias,solver,None))
      score=frozen.score(np,outrec,t,truth,true_b)
      diag=condxy(np,outrec["state"],outrec["cov"],truth,t)
      results.append({"case":case,"mount_deg":cases[case]["mount_deg"],
       "channel":"los","bias":bias,"solver":solver,
       "policy":variant,"q_origin":"native_clean_LoS_same_packet",
       **score,**diag})
     key=list(runs)
     np.savez_compressed(out/f"EXP4_LOS_{case}_{bias}_{solver}.npz",
       t_s=t,pose_id=pids,q_native_los=q_los,
       native_los_power=np.asarray(p),native_s=z[:,1],
       first_power_bin=bin_los,
       policy=np.asarray(key),
       mean_correction_r=np.array([a["mean"][0] for a in native]),
       mean_correction_s=np.array([a["mean"][1] for a in native]),
       estimate=np.stack([runs[k]["state"] for k in key],axis=1),
       covariance=np.stack([runs[k]["cov"] for k in key],axis=1),
       status=np.stack([runs[k]["status"] for k in key],axis=1),
       NIS=np.stack([runs[k]["nis"] for k in key],axis=1))
     print("EXP4_CASE "+json.dumps({"case":case,"bias":bias,"solver":solver,
       "arms":len(key)}),flush=True)
 csvout(out/"EXP4_NATIVE_LOS_RECURSIVE.csv",results)
 csvout(out/"EXP4_LOS_BASELINE_PARITY.csv",parities)
 csvout(out/"EXP4_LOS_POWER_BINS.csv",pq)
 status={"status":"EXP4_NATIVE_LOS_FULL_TRAINED_POWER_TRANSFER_COMPLETE",
   "n_recursive_arms":len(results),
   "n_baseline_R0_parity":len(parities),
   "native_LoS_q_source":"P2 native LoS first-path power P1/P2",
   "original_N4B_R2_fold_coefs":coefs.tolist(),
   "original_N4B_R2_fold_power_cuts":cuts.tolist(),
   "models":EXP4_POLICIES,
   "R4R5_timed_recursion":"BLOCKED_MISSING_AUTHENTICATED_CONTROLS",
   "R4R5_contract":test_R4R5_ineligible(),
   "B0_L2_J4":[v for v in results if v["bias"] in ("B0","L2") and v["solver"]=="J4"],
   "limitations":["LoS application of Full-trained POWER is a negative transfer test",
     "No oracle switch identifying real LoS is provided to filter",
     "Native LoS q power source not Full RF q; independent identical source tap",
     "R4/R5 one-step sweep samples lack true timed wheel/gyro control stream",
     "R2 is one frequently inspected corridor and seed0"],
   "generalization_PASS":False}
 save(out/"EXP4_FINAL.json",status)
 print("EXP4_FINAL "+json.dumps({"status":status["status"],
  "n":len(results),"parity":len(parities),
  "L2_J4":[{k:v for k,v in s.items() if k in(
   "case","policy","heading_rmse_deg","xy_rmse_m","bias_rmse_dps",
   "pose_nees","pose_95coverage","conditional_xy_nees","rf_applied")}
   for s in results if s["bias"]=="L2" and s["solver"]=="J4"]},
   ensure_ascii=False),flush=True)
 return 0

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=("audit","test","exp2","exp3","exp4"))
 p.add_argument("--out");p.add_argument("--audit");p.add_argument("--rf")
 p.add_argument("--r2");p.add_argument("--n4b");p.add_argument("--n4c")
 args=p.parse_args()
 if args.phase=="audit":return audit(args.out)
 if args.phase=="test":return unit()
 if not all([args.out,args.audit,args.rf,args.r2,args.n4b,args.n4c]):
  raise RuntimeError("REQUIRED_FROZEN_INPUTS_MISSING")
 funcs={"exp2":exp2,"exp3":exp3,"exp4":exp4}
 return funcs[args.phase](args.out,args)
if __name__=="__main__":raise SystemExit(main())
