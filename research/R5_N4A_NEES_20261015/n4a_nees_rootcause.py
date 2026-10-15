"""N4-A: forensic decomposition of extreme Pose NEES in held-out N1 recursion.

Strictly READ-ONLY analysis of verified N1 posterior x/P and original
ground truth / RF packets. No physical feature fitting, changed R_s,
new EKF model, or post-hoc gate tuning is performed.

Pose = [x(m), y(m), yaw(rad)], bias is a separate fourth state.
NEES_pose = NEES_yaw + NEES_XY_conditioned_on_yaw (exact Schur split).
Temporal/gate and counterfactual error-versus-covariance breakdowns
are DIAGNOSTICS, not proof of a causal physical multipath mechanism.
"""
from __future__ import annotations
import argparse
import ast
import csv
import gzip
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
R2CODE = ROOT / "research/EKF4_RANGE_S_STAGED_20261014"
PHYS = ROOT / "research/PHYSICS_RS_STAGED_20261015/code"
UWB = ROOT / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"

RAW_SHA = "88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
N1_SHA = "b633d0af900f26ab7d5a42c905adcb4abc01e5b262a154c774d10d5740fbaa40"
N1_SOURCE_SHA = "e189b444977ac9050e04320c8ee703fa2a5f4337"
PINNED_BLOBS = {
 "research/R5_N0_N3_20261015/n1_bias_policies.py":"4ac2ca823dc7475a4330396042ef3084fda6bdf5",
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "research/PHYSICS_RS_STAGED_20261015/code/stage_c.py":"1a215ef1ab0f2f56cc60960742545be6873c7eb0",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/sensor_v2.py":"87ce04aa3c43130f3499008840fa395174f1124e",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
}
CASES=("R2_aA_m0","R2_aA_m45")
CHANNELS=("full","los")
LEVELS={"L0":.01,"L1":.05,"L2":.20}
METHODS=("R0_J4","SOFT_G5_RS","SOFT_G5_MEAN","SOFT_G5_MEAN_RS")
POSE_SCALES=(.1,.1,math.radians(5.))
CHI3_95=7.814727903251179
CHI1_95=3.841458820694124

def file_sha(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def git_blob(path):
 p=Path(path)
 h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def dump(path,data):
 p=Path(path)
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")

def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];observed={}
 if os.getenv("GITHUB_ACTIONS")!="true":
  errors.append("GITHUB_ACTIONS_RUNNER_REQUIRED")
 try:
  head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
  if head!=os.getenv("GITHUB_SHA"):errors.append("CHECKOUT_NOT_EXACT_COMMIT")
 except Exception as exc:
  head=None;errors.append("CANNOT_VERIFY_GIT_HEAD:"+repr(exc))
 for name,expected in PINNED_BLOBS.items():
  path=ROOT/name
  if not path.is_file():errors.append("PINNED_SOURCE_MISSING:"+name);continue
  actual=git_blob(path);observed[name]=actual
  if actual!=expected:errors.append("PINNED_SOURCE_CHANGED:"+name)
 try:ast.parse((HERE/"n4a_nees_rootcause.py").read_text(encoding="utf-8"))
 except Exception as exc:errors.append("SELF_SYNTAX_ERROR:"+repr(exc))
 wf=ROOT/".github/workflows/r5-n4a-nees-rootcause.yml"
 if not wf.is_file():errors.append("WORKFLOW_MISSING")
 else:
  text=wf.read_text()
  needed=("n4a_nees_rootcause.py --phase pre","n4a_nees_rootcause.py --phase test",
          "n4a_nees_rootcause.py --phase run","if: always()","actions: read")
  for item in needed:
   if item not in text:errors.append("WORKFLOW_CONTRACT_MISSING:"+item)
  if all(item in text for item in needed):
   if not (text.index(needed[0])<text.index(needed[1])<text.index(needed[2])):
    errors.append("AUDIT_NOT_BEFORE_NUMERIC_EXECUTION")
 receipt={"stage":"N4-A","decision":"GO" if not errors else "HOLD",
   "git_sha":head,"pinned_source_git_blobs":observed,
   "original_R2_RF_archive_sha256":RAW_SHA,
   "original_N1_L0L1L2_archive_sha256":N1_SHA,
   "original_N1_source_commit":N1_SOURCE_SHA,
   "methods":list(METHODS),"bias_levels":LEVELS,
   "errors":errors,"scientific_PASS":False}
 dump(out/"N4A_PRE_AUDIT.json",receipt)
 print("N4A_PRE "+json.dumps({"decision":receipt["decision"],"errors":errors},
                                 ensure_ascii=False),flush=True)
 return 0 if not errors else 2

def open_checked(path,digest):
 got=file_sha(path)
 if got!=digest:raise RuntimeError("FROZEN_ARCHIVE_SHA_CHANGED:"+str(path)+":"+got)
 z=zipfile.ZipFile(path)
 failed=z.testzip()
 if failed:raise RuntimeError("FROZEN_ARCHIVE_CRC_FAIL:"+failed)
 return z

def member(z,basename):
 matches=[name for name in z.namelist()
          if name==basename or name.endswith("/"+basename)]
 if len(matches)!=1:raise RuntimeError("ARCHIVE_MEMBER_NOT_UNIQUE:"+basename+":"+str(len(matches)))
 return matches[0]

def wrap(np,v):
 return (np.asarray(v)+np.pi)%(2*np.pi)-np.pi

def decompose(np,estimate,cov,truth):
 """Vectorized exact Schur complement, plus unit-normalized condition no."""
 if estimate.ndim!=2 or estimate.shape[1]!=4 or cov.shape!=(len(estimate),4,4):
  raise RuntimeError("N4A_STATE_DIM_MISMATCH")
 if truth.shape!=(len(estimate),3):raise RuntimeError("N4A_TRUTH_SHAPE_BAD")
 ep=estimate[:,:3]-truth
 ep[:,2]=wrap(np,ep[:,2])
 pp=cov[:,:3,:3]
 if not(np.isfinite(pp).all() and np.isfinite(ep).all()):
  raise RuntimeError("N4A_NONFINITE_POSE")
 if np.max(np.abs(pp-np.swapaxes(pp,1,2)))>1e-10:
  raise RuntimeError("N4A_POSTERIOR_NOT_SYMMETRIC")
 eig=np.linalg.eigvalsh(pp)
 if np.min(eig)<=0:raise RuntimeError("N4A_POSE_NOT_PD")
 psi_v=pp[:,2,2]
 pxy=pp[:,:2,:2]
 cross=pp[:,:2,2]
 conditional=pxy-cross[:,:,None]*cross[:,None,:]/psi_v[:,None,None]
 conditional=(conditional+np.swapaxes(conditional,1,2))*.5
 val,vec=np.linalg.eigh(conditional)
 if np.min(val)<=0:raise RuntimeError("N4A_SCHUR_NOT_PD")
 ec=ep[:,:2]-(cross/psi_v[:,None])*ep[:,2,None]
 nees_head=ep[:,2]**2/psi_v
 nees_xy=np.einsum("ni,ni->n",ec,np.linalg.solve(conditional,ec[:,:,None])[:,:,0])
 pose_nees=np.einsum("ni,ni->n",ep,np.linalg.solve(pp,ep[:,:,None])[:,:,0])
 eigproj=np.einsum("nik,ni->nk",vec,ec)
 eigen_nees=eigproj**2/val
 # tolerances are absolute + relative in double precision
 residual=np.abs(pose_nees-(nees_head+nees_xy))
 if np.any(residual>2e-7*np.maximum(1.,pose_nees)):
  bad=int(np.argmax(residual/np.maximum(1.,pose_nees)))
  raise RuntimeError("N4A_SCHUR_PARITY_FAIL:"+str((bad,residual[bad],pose_nees[bad])))
 if np.any(np.abs(nees_xy-eigen_nees.sum(axis=1))>2e-7*np.maximum(1.,nees_xy)):
  raise RuntimeError("N4A_EIGEN_DECOMP_INCONSISTENT")
 scale=np.asarray(POSE_SCALES)
 normalized=pp/scale[None,:,None]/scale[None,None,:]
 eigen_unitless=np.linalg.eigvalsh(normalized)
 if np.min(eigen_unitless)<=0:raise RuntimeError("NORMALIZED_COV_NOT_PD")
 # Raw covariance condition across x[m],y[m],psi[rad] depends on units:
 # only condition number in fixed explicitly scaled coordinates is shown.
 rawxy=np.einsum("ni,ni->n",ep[:,:2],
            np.linalg.solve(pxy,ep[:,:2,None])[:,:,0])
 return {
   "err":ep,"err_xy_cond":ec,
   "pose_nees":pose_nees,"heading_nees":nees_head,"conditional_xy_nees":nees_xy,
   "conditional_xy_first_eigen_nees":eigen_nees[:,0],
   "conditional_xy_second_eigen_nees":eigen_nees[:,1],
   "conditional_xy_eigen_small":val[:,0],
   "conditional_xy_eigen_large":val[:,1],
   "conditional_xy_condition":val[:,1]/val[:,0],
   "marginal_xy_nees_NOT_ADDITIVE":rawxy,
   "heading_sigma_deg":np.degrees(np.sqrt(psi_v)),
   "heading_variance":psi_v,
   "xy_error_norm":np.linalg.norm(ep[:,:2],axis=1),
   "xy_cond_error_norm":np.linalg.norm(ec,axis=1),
   "eigen_condition_pose_unit_normalized":eigen_unitless[:,-1]/eigen_unitless[:,0],
   "pose_min_eigen_unit_normalized":eigen_unitless[:,0],
   "conditional_xy_logdet":np.linalg.slogdet(conditional)[1],
   "decomp_error":residual,
   "cov_pose":pp,
 }

def sse(np,e,P):
 return np.einsum("ni,ni->n",e,np.linalg.solve(P,e[:,:,None])[:,:,0])

def shapley(np,old,new):
 # Pure algebraic attribution of paired estimator (e,P) differences.
 # NOT causal attribution to Range vs s vs Bias.
 e0=old["err"];e1=new["err"]
 P0=old["cov_pose"];P1=new["cov_pose"]
 n00=sse(np,e0,P0);n01=sse(np,e0,P1)
 n10=sse(np,e1,P0);n11=sse(np,e1,P1)
 point=.5*((n10-n00)+(n11-n01))
 covariance=.5*((n01-n00)+(n11-n10))
 if np.max(np.abs((point+covariance)-(n11-n00)))>1e-6:
  raise RuntimeError("N4A_SHAPLEY_IDENTITY_FAILED")
 return {"reference":n00,"corrected":n11,"point_contribution":point,
         "covariance_contribution":covariance}

def quantiles(np,x):
 a=np.asarray(x,float)
 return {"mean":float(a.mean()),"median":float(np.median(a)),
         "p90":float(np.quantile(a,.90)),"p95":float(np.quantile(a,.95)),
         "p99":float(np.quantile(a,.99)),"max":float(a.max())}

def tail_fraction(np,x,portion):
 arr=np.asarray(x,float)
 if len(arr)==0 or arr.sum()<=0:return 0.
 n=max(1,int(math.ceil(len(arr)*portion)))
 return float(np.sort(arr)[-n:].sum()/arr.sum())

def summary(np,d,eval_mask,time,status,method,case,level,channel):
 p=d["pose_nees"][eval_mask]
 h=d["heading_nees"][eval_mask]
 xy=d["conditional_xy_nees"][eval_mask]
 count=int(eval_mask.sum())
 gates=np.asarray(status)[eval_mask]
 if count!=829:raise RuntimeError("N4A_WRONG_EVAL_LENGTH:"+str(count))
 return {
  "case":case,"channel":channel,"bias_level":level,"method":method,
  "frames":count,
  "heading_rmse_deg":float(np.sqrt(np.mean(np.degrees(d["err"][eval_mask,2])**2))),
  "xy_rmse_m":float(np.sqrt(np.mean(d["xy_error_norm"][eval_mask]**2))),
  "pose_nees_mean":float(p.mean()),
  "heading_nees_mean":float(h.mean()),
  "conditional_xy_nees_mean":float(xy.mean()),
  "conditional_xy_share_pose_nees":float(xy.sum()/p.sum()),
  "pose95_coverage":float(np.mean(p<=CHI3_95)),
  "heading95_coverage":float(np.mean(h<=CHI1_95)),
  "conditional_xy_95_coverage":float(np.mean(xy<=5.991464547107979)),
  "tail_top1pct_pose_nees_share":tail_fraction(np,p,.01),
  "tail_top5pct_pose_nees_share":tail_fraction(np,p,.05),
  "fraction_pose_nees_gt100":float(np.mean(p>100.)),
  "fraction_pose_nees_gt1000":float(np.mean(p>1000.)),
  "conditional_xy_small_eig_m2_median":float(np.median(d["conditional_xy_eigen_small"][eval_mask])),
  "conditional_xy_large_eig_m2_median":float(np.median(d["conditional_xy_eigen_large"][eval_mask])),
  "conditional_xy_cond_p95":float(np.quantile(d["conditional_xy_condition"][eval_mask],.95)),
  "normalized_pose_cov_cond_p95":float(np.quantile(d["eigen_condition_pose_unit_normalized"][eval_mask],.95)),
  "conditional_small_eigen_N_contrib_mean":float(np.mean(d["conditional_xy_first_eigen_nees"][eval_mask])),
  "conditional_large_eigen_N_contrib_mean":float(np.mean(d["conditional_xy_second_eigen_nees"][eval_mask])),
  "gate_joint_accepted":int(np.sum(np.isin(gates,["APPLIED","JOINT"]))),
  "gate_joint_rejected":int(np.sum(np.isin(gates,["REJECT","JOINT_REJECT"]))),
  "gate_hard_skipped":int(np.sum(gates=="RF_SKIPPED")),
  "max_decomposition_absolute_error":float(np.max(d["decomp_error"])),
 }

def test():
 import numpy as np
 rng=np.random.default_rng(20261015)
 n=170
 A=rng.normal(size=(n,3,3))
 PP=A@np.swapaxes(A,1,2)+np.eye(3)[None]*.08
 B=np.zeros((n,4,4))
 B[:,:3,:3]=PP
 B[:,3,3]=1e-4
 estimate=rng.normal(size=(n,4))*.12
 truth=rng.normal(size=(n,3))*.06
 decomp=decompose(np,estimate,B,truth)
 assert np.allclose(decomp["pose_nees"],decomp["heading_nees"]+
                     decomp["conditional_xy_nees"],atol=1e-10,rtol=1e-10)
 assert np.allclose(decomp["conditional_xy_nees"],
                    decomp["conditional_xy_first_eigen_nees"]+
                    decomp["conditional_xy_second_eigen_nees"],atol=1e-10,rtol=1e-10)
 other=estimate.copy();other[:,0]+=.2
 alt=decompose(np,other,B*1.01,truth)
 shap=shapley(np,decomp,alt)
 assert np.allclose(shap["point_contribution"]+shap["covariance_contribution"],
                    shap["corrected"]-shap["reference"],rtol=1e-11,atol=1e-10)
 # Pose NEES is not marginal x/y NEES plus marginal yaw NEES in general.
 assert np.max(abs(decomp["pose_nees"]-
                  (decomp["marginal_xy_nees_NOT_ADDITIVE"]+
                   decomp["heading_nees"])))>.01
 assert wrap(np,np.array([math.pi+.01,-math.pi-.01])).shape==(2,)
 d=np.arange(829)
 assert math.isclose(tail_fraction(np,np.ones(829),.01),9/829)
 print("N4A_UNIT_PASS "+json.dumps({"synthetic_spd_covariances":n,
     "tests":["SCHUR","EIGEN","SHAPLEY","NONADDITIVE_MARGINAL",
              "WRAP","TAIL_CONCENTRATION","POSE_DIMENSIONS"]}),flush=True)
 return 0

def run(out,pre,rawpath,n1path):
 import numpy as np
 sys.path[:0]=[str(R2CODE),str(PHYS),str(UWB)]
 from r2_bias_replay import build_positive_bias_controls,predict_one
 from p3_rf_adapter4 import FrozenLut
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 receipt=json.loads(Path(pre).read_text())
 if receipt["decision"]!="GO" or receipt["git_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("N4A_SOURCE_PREAUDIT_NOT_GO")
 lut=FrozenLut(ROOT)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 meta={c["id"]:c for c in manifest["cases"]}
 focus_methods=METHODS
 all_summary=[];timebands=[];toprows=[];gate_groups=[];shapley_summary=[]
 original_parity=[]
 with open_checked(rawpath,RAW_SHA) as zf,open_checked(n1path,N1_SHA) as zn:
  n1audit=json.loads(zn.read(member(zn,"N1_PRE_AUDIT.json")))
  n1final=json.loads(zn.read(member(zn,"N1_FINAL.json")))
  if n1audit["decision"]!="GO" or n1final["status"]!="N1_BIAS_EXTENDED_TECHNICAL_PASS":
   raise RuntimeError("N1_UPSTREAM_NOT_AUDITED")
  if n1audit["commit"]!=N1_SOURCE_SHA or n1final["source_sha"]!=N1_SOURCE_SHA:
   raise RuntimeError("N1_SOURCE_COMMIT_MISMATCH")
  if n1final["n_metric_rows"]!=204 or n1final["n_traces"]!=12:
   raise RuntimeError("N1_COMPLETENESS_MISMATCH")
  with io.StringIO(zn.read(member(zn,"N1_ALL_BIAS_METHOD_METRICS.csv")).decode("utf-8")) as f:
   upstream=list(csv.DictReader(f))
  index={(r["case"],r["channel"],r["bias_level"],r["method"]):r for r in upstream}
  archived_rf=json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  rf_index={(r["case"],r["channel"]):r for r in archived_rf["per_case"]}
  if len(rf_index)!=14:raise RuntimeError("RF_ARCHIVED_TRACE_COUNT")
  truth_records={}
  for case in CASES:
   for channel in CHANNELS:
    src=rf_index[(case,channel)]
    blob=zf.read("P2_OUT/"+src["trace_file"])
    if hashlib.sha256(blob).hexdigest()!=src["trace_sha256"]:
     raise RuntimeError("SOURCE_TRACE_SHA_MISMATCH:"+case+"/"+channel)
    with np.load(io.BytesIO(blob),allow_pickle=False) as z:
     truth_records[(case,channel)]={
       "t":z["t_s"].copy(),
       "pose_id":z["pose_id"].copy(),
       "truth":z["truth_for_offline_scoring_only"].copy(),
       "z_r":z["z_r_m"].copy(),
       "z_s":z["z_s"].copy(),
     }
  for level,true_bias in LEVELS.items():
   for case in CASES:
    for channel in CHANNELS:
     base=truth_records[(case,channel)]
     t=base["t"];truth=base["truth"];pid=base["pose_id"]
     ctl,x0=build_positive_bias_controls(t,truth,level,seed=0)
     name=f"N1_{case}_{channel}_{level}.npz"
     with np.load(io.BytesIO(zn.read(member(zn,name))),allow_pickle=False) as z:
      arrays={k:z[k].copy() for k in z.files}
     if (not np.array_equal(arrays["t_s"],t) or
         not np.array_equal(arrays["pose_id"],pid) or
         arrays["estimate"].shape!=(979,15,4) or
         arrays["covariance"].shape!=(979,15,4,4) or
         arrays["status"].shape!=(979,15)):
      raise RuntimeError("N1_OUTPUT_ARRAY_OR_PROVENANCE_INVALID:"+name)
     names=list(arrays["methods"])
     if not all(m in names for m in METHODS):
      raise RuntimeError("N4A_MODEL_MISSING:"+name)
     mask=t>=30
     if mask.sum()!=829:raise RuntimeError("UNEXPECTED_EVAL_MASK")
     archive_method={}
     for method in focus_methods:
      jj=names.index(method)
      X=arrays["estimate"][:,jj,:]
      P=arrays["covariance"][:,jj,:,:]
      status=arrays["status"][:,jj]
      d=decompose(np,X,P,truth)
      archive_method[method]=d
      sm=summary(np,d,mask,t,status,method,case,level,channel)
      all_summary.append(sm)
      key=(case,channel,level,method)
      prior_score=index[key]
      for label,our,previous in (
          ("pose_nees",sm["pose_nees_mean"],float(prior_score["pose_nees_mean"])),
          ("heading_nees",sm["heading_nees_mean"],float(prior_score["heading_nees_mean"])),
          ("heading_rmse",sm["heading_rmse_deg"],float(prior_score["heading_rmse_deg"])),
          ("pose95",sm["pose95_coverage"],float(prior_score["pose95_coverage"]))):
       if abs(our-previous)>2e-7*max(1.,abs(previous)):
        raise RuntimeError("N1_INDEPENDENT_SCORE_PARITY_FAIL:"+str((key,label,our,previous)))
      original_parity.append({"case":case,"channel":channel,"bias_level":level,
         "method":method,"N1_score_parity":"PASS",
         "pose_NEES":sm["pose_nees_mean"],"Schur_residual_max":sm["max_decomposition_absolute_error"]})
      # complete debug trace with poster/prior decompositions and gate outcomes
      per_step=[]
      for k in range(len(t)):
       if k:
        ds,gyro,dt=(float(ctl[v][k]) for v in ("ds_odom","dtheta_gyro","dt_s"))
        # Same frozen physical/motion dynamics for all arms. The original
        # fast_predict is algebraically equivalent but uses a different
        # floating-point ordering; this is a diagnostic pre-update predictor.
        xp,Pp=predict_one(X[k-1],P[k-1],ds,gyro,dt)
        prior=decompose(np,xp[None,:],Pp[None,:,:],truth[k:k+1])
        prior_n=float(prior["pose_nees"][0])
        prior_h=float(prior["heading_nees"][0])
        prior_xy=float(prior["conditional_xy_nees"][0])
        phi_jump=math.degrees(float(wrap(np,X[k,2]-xp[2])))
        bias_jump=math.degrees(float(X[k,3]-xp[3]))
        dx_jump=float(np.linalg.norm(X[k,:2]-xp[:2]))
        Hpred=lut.model(xp,meta[case])
        innovation_r=float(base["z_r"][k]-Hpred[0][0])
        correction=float(arrays["mean_bias_correction"][k]) if method in ("SOFT_G5_MEAN","SOFT_G5_MEAN_RS") else 0.
        innovation_s=float(base["z_s"][k]-correction-Hpred[0][1])
        hyaw=float(Hpred[1][1,2])
        px_shrink=float(math.exp(float(d["conditional_xy_logdet"][k]-
                                        prior["conditional_xy_logdet"][0])))
        psi_shrink=float(d["heading_variance"][k]/prior["heading_variance"][0])
        accepted=bool(status[k] in ("APPLIED","JOINT"))
        rejected=bool(status[k] in ("REJECT","JOINT_REJECT"))
        if rejected and max(abs(phi_jump),abs(bias_jump),dx_jump)>1e-5:
         raise RuntimeError("REJECTED_POSTERIOR_NOT_PRIOR:"+str((case,level,channel,method,k)))
       else:
        prior_n=prior_h=prior_xy=None
        phi_jump=bias_jump=dx_jump=innovation_r=innovation_s=hyaw=None
        px_shrink=psi_shrink=None
        accepted=False;rejected=False
       per_step.append({
          "case":case,"channel":channel,"bias_level":level,"method":method,
          "t_s":float(t[k]),"pose_id":int(pid[k]),"eval":bool(mask[k]),
          "gate_status":str(status[k]),"gate_accepted":accepted,
          "risk_pbad_G5":float(arrays["risk_pbad"][k]),
          "pose_nees":float(d["pose_nees"][k]),
          "heading_nees":float(d["heading_nees"][k]),
          "xy_cond_nees":float(d["conditional_xy_nees"][k]),
          "xy_small_axis_nees":float(d["conditional_xy_first_eigen_nees"][k]),
          "xy_large_axis_nees":float(d["conditional_xy_second_eigen_nees"][k]),
          "heading_error_deg":float(math.degrees(d["err"][k,2])),
          "xy_error_m":float(d["xy_error_norm"][k]),
          "xy_cond_error_m":float(d["xy_cond_error_norm"][k]),
          "xy_cond_lambda_min_m2":float(d["conditional_xy_eigen_small"][k]),
          "xy_cond_lambda_max_m2":float(d["conditional_xy_eigen_large"][k]),
          "xy_cond_cov_logdet":float(d["conditional_xy_logdet"][k]),
          "normalized_pose_condition":float(d["eigen_condition_pose_unit_normalized"][k]),
          "prior_pose_nees":prior_n,"prior_heading_nees":prior_h,
          "prior_xy_cond_nees":prior_xy,
          "post_minus_prior_nees":float(d["pose_nees"][k]-prior_n) if prior_n is not None else None,
          "cov_xy_cond_det_ratio_post_over_prior":px_shrink,
          "cov_heading_variance_ratio_post_over_prior":psi_shrink,
          "rf_update_jump_heading_deg":phi_jump,
          "rf_update_jump_bias_dps":bias_jump,
          "rf_update_jump_xy_m":dx_jump,
          "rf_innovation_r_m":innovation_r,
          "rf_innovation_s_after_mean_correction":innovation_s,
          "H_s_psi_per_rad":hyaw,
        })
      top_idx=np.argsort(np.where(mask,d["pose_nees"],-np.inf))[-8:][::-1]
      for k in top_idx:
       row=per_step[int(k)].copy()
       row["severity_rank"]=int(np.where(top_idx==k)[0][0])+1
       toprows.append(row)
      timecodes=(np.floor(t/30).astype(int)*30).astype(int)
      for a in sorted(set(timecodes)):
       q=timecodes==a
       if not np.any(q):continue
       accepted=np.array([r["gate_accepted"] for r in per_step],bool)[q]
       ne=d["pose_nees"][q];xy=d["conditional_xy_nees"][q];heading=d["heading_nees"][q]
       timebands.append({
        "case":case,"channel":channel,"bias_level":level,"method":method,
        "time_start_s":a,"time_end_s":a+30,"n":int(q.sum()),
        "pose_nees_mean":float(ne.mean()),"pose_nees_max":float(ne.max()),
        "pose_NEES_sum_fraction_total_eval":float(ne.sum()/max(d["pose_nees"][mask].sum(),1e-300)),
        "xy_cond_nees_mean":float(xy.mean()),"heading_nees_mean":float(heading.mean()),
        "xy_cond_cov_min_eig_median":float(np.median(d["conditional_xy_eigen_small"][q])),
        "xy_cond_error_median":float(np.median(d["xy_cond_error_norm"][q])),
        "gate_accepted_fraction":float(accepted.mean()),
        "status_reject_fraction":float(np.mean(np.isin(np.asarray(status)[q],["REJECT","JOINT_REJECT"]))),
       })
      acceptedrows=[r for r in per_step if r["eval"] and r["gate_accepted"]]
      rejectedrows=[r for r in per_step if r["eval"] and r["gate_status"] in ("REJECT","JOINT_REJECT")]
      gate_groups.append({
        "case":case,"channel":channel,"bias_level":level,"method":method,
        "accepted_n":len(acceptedrows),"rejected_n":len(rejectedrows),
        "accepted_fraction_nees_increased_on_update":
           float(np.mean([r["post_minus_prior_nees"]>0 for r in acceptedrows])) if acceptedrows else None,
        "accepted_mean_increment_nees":
           float(np.mean([r["post_minus_prior_nees"] for r in acceptedrows])) if acceptedrows else None,
        "accepted_mean_xy_cond_logdet_ratio":
           float(np.mean([math.log(r["cov_xy_cond_det_ratio_post_over_prior"]) for r in acceptedrows])) if acceptedrows else None,
        "accepted_mean_heading_var_ratio":
           float(np.mean([r["cov_heading_variance_ratio_post_over_prior"] for r in acceptedrows])) if acceptedrows else None,
        "rejected_mean_increment_nees":
           float(np.mean([r["post_minus_prior_nees"] for r in rejectedrows])) if rejectedrows else None,
        "high_pose_nees_gt1000_n":int(sum(r["pose_nees"]>1000 for r in per_step if r["eval"])),
       })
      # use GZIP for full per-frame record; audit/debug reproducible.
      with gzip.open(out/f"N4A_TRACE_{case}_{channel}_{level}_{method}.csv.gz",
                     "wt",encoding="utf-8",newline="") as f:
       writer=csv.DictWriter(f,fieldnames=list(per_step[0].keys()))
       writer.writeheader()
       writer.writerows(per_step)
     if "R0_J4" in archive_method:
      reference=archive_method["R0_J4"]
      for target in ("SOFT_G5_RS","SOFT_G5_MEAN","SOFT_G5_MEAN_RS"):
       now=archive_method[target]
       shp=shapley(np,reference,now)
       shapley_summary.append({
         "case":case,"channel":channel,"bias_level":level,
         "reference":"R0_J4","candidate":target,
         "reference_pose_nees_mean":float(shp["reference"][mask].mean()),
         "candidate_pose_nees_mean":float(shp["corrected"][mask].mean()),
         "difference_nees_mean":float((shp["corrected"][mask]-shp["reference"][mask]).mean()),
         "point_error_change_contribution":float(shp["point_contribution"][mask].mean()),
         "covariance_change_contribution":float(shp["covariance_contribution"][mask].mean()),
         "attribution_identity_max_error":float(np.max(np.abs(
              shp["point_contribution"]+shp["covariance_contribution"]-
              shp["corrected"]+shp["reference"]))),
         "note":"exact algebraic error/P attribution, NOT independent causal mechanism"
       })
     print("N4A_CASE "+json.dumps({"case":case,"channel":channel,
       "bias_level":level,"mean_pose_nees":
        {m:round(archive_method[m]["pose_nees"][mask].mean(),4) for m in METHODS},
       "xy_share_g5_mean_rs":round(
         archive_method["SOFT_G5_MEAN_RS"]["conditional_xy_nees"][mask].sum()/
         archive_method["SOFT_G5_MEAN_RS"]["pose_nees"][mask].sum(),6)}),flush=True)
 # Detailed CSV + compact status receipt.
 def export(name,rows):
  with (out/name).open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 export("N4A_NEES_COMPONENTS.csv",all_summary)
 export("N4A_TIME_BANDS.csv",timebands)
 export("N4A_TOP_EVENTS.csv",toprows)
 export("N4A_GATE_ASSOCIATIONS.csv",gate_groups)
 export("N4A_POINT_VS_COV_ATTRIBUTION.csv",shapley_summary)
 export("N4A_N1_INDEPENDENT_SCORE_PARITY.csv",original_parity)
 focus=[r for r in all_summary
        if r["channel"]=="full" and r["method"] in ("R0_J4","SOFT_G5_MEAN_RS")]
 result={
   "schema":"R5_N4A_POSE_NEES_ROOTCAUSE_DECOMPOSITION_V1",
   "status":"N4A_ARCHIVED_POSE_NEES_DECOMPOSITION_COMPLETE",
   "source_sha":os.getenv("GITHUB_SHA"),
   "N1_original_source_sha":N1_SOURCE_SHA,
   "N1_artifact_sha256":N1_SHA,
   "RF_artifact_sha256":RAW_SHA,
   "n_cases":len(CASES),"n_levels":len(LEVELS),"n_channels":len(CHANNELS),
   "n_methods":len(METHODS),"n_scored_groups":len(all_summary),
   "n_eval_frame_per_group":829,
   "worst_schur_abs_error":max(r["max_decomposition_absolute_error"] for r in all_summary),
   "source_score_parity_pass":len(original_parity)==len(all_summary),
   "focus_full":focus,"point_vs_cov_shapley_full":
       [r for r in shapley_summary if r["channel"]=="full"],
   "scientific_PASS":False,
   "limitations":[
     "This is a forensic analysis of archived trajectories, not a new RF calibration or filter improvement",
     "Condition numbers of x,y,yaw must be computed with stated coordinate scales",
     "Spikes co-occurring with RF gate acceptance do not establish a causal gate mechanism",
     "Shapley point-vs-covariance split is algebraic, not physically causal",
     "Conditional XY residual depends on both position error and pose cross covariance",
     "Original single R2 corridor and gyro seed0 only; adjacent times are not independent",
     "N4-B and N4-C remain required before concluding that Range/s covariance causes failure",
   ]
 }
 dump(out/"N4A_FINAL.json",result)
 print("N4A_FINAL "+json.dumps({
   "status":result["status"],"trace_groups":len(all_summary),
   "worst_schur_abs_error":result["worst_schur_abs_error"],
   "focus_full":focus,"point_vs_cov_shapley_full":result["point_vs_cov_shapley_full"],
   "output_counts":{"timebands":len(timebands),"gate_groups":len(gate_groups),
     "severe_records":len(toprows)}},ensure_ascii=False),flush=True)
 return 0

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","test","run"),required=True)
 p.add_argument("--out")
 p.add_argument("--audit")
 p.add_argument("--raw")
 p.add_argument("--n1")
 a=p.parse_args()
 if a.phase=="pre":return audit(a.out)
 if a.phase=="test":return test()
 if not all((a.out,a.audit,a.raw,a.n1)):raise RuntimeError("MISSING_RUN_PARAMS")
 return run(a.out,a.audit,a.raw,a.n1)

if __name__=="__main__":
 raise SystemExit(main())
