"""Independent, source-pinned audit of the High-bin Vr-only recursive experiment.

Re-score 112 posterior arms directly from original archived RF GT, test
R_packet invariants, compare 16 baseline NPZ traces to frozen N4-C.
No source is rebuilt and no best model is selected on R2.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE_BLOB="46583c5c47951739222898b3e01a9ecccda0e779"
SHA={
 "new":"71b5433020133af75386edd03410bcf073b47a9d17f4cb749d0bf7c24b761475",
 "n4c":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9",
 "rf":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
}
R0_R=.0068578637
VARIANTS=("POWER_RAW","HIGH_R0","HIGH_2R0","HIGH_4R0")
CASE=("R2_aA_m0","R2_aA_m45")
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
SOLVER=("J4","SR4")
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(p,obj):
 Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False,ensure_ascii=False)+"\n")
def member(z,name):
 names=[x for x in z.namelist() if x==name or x.endswith("/"+name)]
 if len(names)!=1:raise RuntimeError("BAD_ARCHIVE_MEMBER:"+name)
 return names[0]
def validate_zip(p,digest):
 if sha(p)!=digest:raise RuntimeError("ARTIFACT_HASH_MISMATCH:"+p)
 z=zipfile.ZipFile(p)
 if z.testzip():raise RuntimeError("ARTIFACT_CRC_MISMATCH")
 return z
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if rev!=os.getenv("GITHUB_SHA") or os.getenv("GITHUB_ACTIONS")!="true":
  errors.append("NOT_EXACT_GITHUB_RUNNER")
 orig=ROOT/"research/HIGH_VR_RANGE_ONLY_20261016/high_vr_range_only.py"
 if not orig.is_file() or blob(orig)!=SOURCE_BLOB:
  errors.append("FROZEN_ORIGINAL_VR_EXPERIMENT_CHANGED")
 try:ast.parse((HERE/"high_vr_independent_review.py").read_text())
 except Exception as e:errors.append("SELF_PYTHON_SYNTAX:"+repr(e))
 w=ROOT/".github/workflows/n4-power-high-vr-review.yml"
 if not w.is_file():errors.append("MISSING_INDEPENDENT_WORKFLOW")
 else:
  s=w.read_text()
  p=s.find("high_vr_independent_review.py --phase pre")
  q=s.find("high_vr_independent_review.py --phase run")
  if not 0<=p<q or "if: always()" not in s or "actions: read" not in s:
   errors.append("NOT_AUDIT_FIRST_OR_NO_ARTIFACT")
 receipt={"decision":"GO" if not errors else "HOLD","head":rev,
  "original_source_git_blob":SOURCE_BLOB,"archived_sha":SHA,"errors":errors}
 save(out/"PRE_AUDIT.json",receipt)
 print("HIGH_VR_REVIEW_PRE "+json.dumps({"decision":receipt["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2
def env():
 import numpy as np
 import pandas as pd
 return np,pd
def complete(out,pre,newzip,n4czip,rfzip):
 np,pd=env()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(pre).read_text())
 if a["decision"]!="GO" or a["head"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("INDEPENDENT_AUDIT_HOLD")
 with validate_zip(newzip,SHA["new"]) as zn,validate_zip(n4czip,SHA["n4c"]) as zc,validate_zip(rfzip,SHA["rf"]) as zrf:
  final=json.loads(zn.read(member(zn,"HIGH_VR_FINAL.json")))
  m1=pd.read_csv(io.BytesIO(zn.read(member(zn,"HIGH_VR_ALL_RECURSIVE.csv"))))
  m2=pd.read_csv(io.BytesIO(zn.read(member(zn,"HIGH_VR_ONE_STEP_FIXED_PRIOR.csv"))))
  parity=pd.read_csv(io.BytesIO(zn.read(member(zn,"HIGH_VR_SOURCE_PARITY.csv"))))
  los=pd.read_csv(io.BytesIO(zn.read(member(zn,"HIGH_VR_LOS_R0_GUARDS.csv"))))
  bins=pd.read_csv(io.BytesIO(zn.read(member(zn,"HIGH_VR_POWER_STRATUM.csv"))))
  if not(final["status"]=="HIGH_VR_RANGE_ONLY_RECURSIVE_PILOT_COMPLETE" and
     len(m1)==112 and len(m2)==112 and len(parity)==32 and len(los)==16 and len(bins)==2):
   raise RuntimeError("ORIGINAL_EXPERIMENT_COMPLETENESS_FAILURE")
  if not np.array_equal(parity.gate_differences.to_numpy(),np.zeros(32)):
   raise RuntimeError("BASELINE_GATE_MISMATCH")
  if max(float(parity.state_max.max()),float(parity.cov_max.max()))>1e-6:
   raise RuntimeError("SOURCE_STATE_COV_MISMATCH")
  config={(c["case"],c["channel"]):c for c in
    json.loads(zrf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  counted=0;controls=[];diagnostics=[]
  for case in CASE:
   for level,true_bias in BIAS.items():
    zdesc=config[(case,"full")]
    b=zrf.read("P2_OUT/"+zdesc["trace_file"])
    if hashlib.sha256(b).hexdigest()!=zdesc["trace_sha256"]:
     raise RuntimeError("FROZEN_GT_SOURCE_MISMATCH")
    with np.load(io.BytesIO(b),allow_pickle=False) as ff:
     T=ff["t_s"].copy();ids=ff["pose_id"].copy()
     GT=ff["truth_for_offline_scoring_only"].copy()
    take=T>=30
    for solver in SOLVER:
     original=zc.read(member(zc,f"N4C_{case}_full_{level}_{solver}.npz"))
     with np.load(io.BytesIO(original),allow_pickle=False) as st:
      match=np.flatnonzero((st["policies"]=="POWER_JOINT")&(st["gate_modes"]=="natural"))
      if len(match)!=1:raise RuntimeError("SOURCE_POWER_FROZEN_MISSING")
      ref_i=int(match[0]);refx=st["estimate"][:,ref_i]
      refP=st["covariance"][:,ref_i]
      refgate=(st["status"][:,ref_i]=="APPLIED")
     name=f"VR_ONLY_{case}_{level}_{solver}.npz"
     with np.load(io.BytesIO(zn.read(member(zn,name))),allow_pickle=False) as p:
      d={k:p[k].copy() for k in p.files}
     if not (np.array_equal(d["t_s"],T) and np.array_equal(d["pose_id"],ids)
         and len(d["variant"])==7 and d["R_packet"].shape==(979,7,2,2)
         and d["covariance"].shape==(979,7,4,4)):
      raise RuntimeError("ID_SHAPE_ALIGNMENT_ERROR")
     high=d["high_bin"].astype(bool);q=d["q_power"]
     threshold=float(final["r2_fold_power_cutpoints"][1])
     if not np.array_equal(high,q>=threshold):
      raise RuntimeError("ORIGINAL_TRAIN_POWER_BIN_BOUNDARY_CHANGED")
     refidx=np.flatnonzero((d["variant"]=="POWER_RAW")&(d["gate_mode"]=="natural"))
     if len(refidx)!=1:raise RuntimeError("RAW_POWER_REFERENCE_MISSING")
     i0=int(refidx[0])
     X=d["estimate"];PP=d["covariance"];R=d["R_packet"]
     dx=X[:,i0]-refx;dx[:,2]=(dx[:,2]+np.pi)%(2*np.pi)-np.pi
     if np.max(abs(dx))>1e-6 or np.max(abs(PP[:,i0]-refP))>1e-6:
      raise RuntimeError("INDEPENDENT_BASELINE_STATE_PARITY")
     for j in range(len(d["variant"])):
      var=str(d["variant"][j]);g=str(d["gate_mode"][j])
      if (var=="POWER_RAW" and g!="natural") or (g not in ("natural","power_mask")):
       raise RuntimeError("METHOD_UNEXPECTED")
      expected=R[:,i0].copy()
      if var!="POWER_RAW":
       floor={"HIGH_R0":R0_R,"HIGH_2R0":2*R0_R,"HIGH_4R0":4*R0_R}[var]
       expected[high,0,0]=np.maximum(expected[high,0,0],floor)
      if not np.array_equal(expected,R[:,j]):
       raise RuntimeError("NON_VR_BAND_MODIFIED:"+str((case,level,solver,var,g)))
      if not np.all(np.linalg.eigvalsh(R[:,j])>0):
       raise RuntimeError("R_COND_COV_NOT_SPD")
      if g=="power_mask" and not np.array_equal((d["status"][:,j]=="APPLIED"),refgate):
       raise RuntimeError("COMMON_GATE_FORCED_WRONGLY")
      er=X[take,j,:3]-GT[take]
      er[:,2]=(er[:,2]+np.pi)%(2*np.pi)-np.pi
      P3=PP[take,j,:3,:3]
      if not np.all(np.linalg.eigvalsh(P3)>0):raise RuntimeError("POSE_COV_NOT_SPD")
      NEES=np.einsum("ni,ni->n",er,np.linalg.solve(P3,er[...,None])[:,:,0])
      xyt=P3[:,:2,:2]-P3[:,:2,2,None]*P3[:,None,2,:2]/P3[:,2,2,None,None]
      err_cond=er[:,:2]-P3[:,:2,2]/P3[:,2,2,None]*er[:,2,None]
      xynees=np.einsum("ni,ni->n",err_cond,np.linalg.solve(xyt,err_cond[...,None])[:,:,0])
      hd_nees=er[:,2]**2/P3[:,2,2]
      if max(abs(NEES-xynees-hd_nees))>1e-6:
       raise RuntimeError("SCHUR_POSE_HEADING_XY_IDENTITY")
      original_score=m1[
       (m1.case==case)&(m1.bias==level)&(m1.solver==solver)&
       (m1.variant==var)&(m1.gate_mode==g)]
      if len(original_score)!=1:raise RuntimeError("SCORE_ROW_NOT_UNIQUE")
      s=original_score.iloc[0]
      verify={
       "heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(er[:,2]**2)))),
       "xy_rmse_m":float(np.sqrt(np.mean(np.sum(er[:,:2]**2,axis=1)))),
       "pose_nees":float(np.mean(NEES)),
       "conditional_xy_nees":float(np.mean(xynees)),
       "pose_95coverage":float(np.mean(NEES<=7.814727903251179)),
       "rf_applied":int(np.sum(d["status"][take,j]=="APPLIED")),
       "accepted_high":int(np.sum((d["status"][take,j]=="APPLIED")&high[take])),
      }
      for key,v in verify.items():
       if abs(v-float(s[key]))>1e-8:
        raise RuntimeError("INDEPENDENT_SCORE_RECOMPUTE_FAILED:"+str((case,level,solver,var,g,key,v,s[key])))
      counted+=1
     for var in ("HIGH_R0","HIGH_2R0","HIGH_4R0"):
      a=m1.query("case==@case and bias==@level and solver==@solver and variant==@var and gate_mode=='natural'").iloc[0]
      b=m1.query("case==@case and bias==@level and solver==@solver and variant=='POWER_RAW' and gate_mode=='natural'").iloc[0]
      forced=m1.query("case==@case and bias==@level and solver==@solver and variant==@var and gate_mode=='power_mask'").iloc[0]
      controls.append({"case":case,"bias":level,"solver":solver,"policy":var,
       "delta_heading_rmse_deg":float(a.heading_rmse_deg-b.heading_rmse_deg),
       "delta_bias_rmse_dps":float(a.bias_rmse_dps-b.bias_rmse_dps),
       "delta_xy_rmse_m":float(a.xy_rmse_m-b.xy_rmse_m),
       "delta_condXY_nees":float(a.conditional_xy_nees-b.conditional_xy_nees),
       "delta_narrowXY_nees":float(a.conditional_xy_narrow_nees-b.conditional_xy_narrow_nees),
       "delta_pose95":float(a.pose_95coverage-b.pose_95coverage),
       "natural_vs_fixed_gate_condXY_diff":float(a.conditional_xy_nees-forced.conditional_xy_nees),
       "natural_vs_fixed_gate_heading_diff":float(a.heading_rmse_deg-forced.heading_rmse_deg),
       "natural_minus_frozen_accept_high":int(a.accepted_high-b.accepted_high)})
   # each case+level had one / repeated two solver same packet source.
  if counted!=112 or len(controls)!=48:raise RuntimeError("AUDIT_EXPECTED_ARMS_MISSING")
  if not np.allclose(m2.heading_sq_change_deg2_lowmid,0,atol=1e-13):
   raise RuntimeError("ONE_STEP_NONHIGH_PACKET_CHANGED")
  # No gain-only refit on R2, and potential wins must survive both mounts.
  comp=pd.DataFrame(controls)
  verdict=[]
  for var,g in comp.groupby("policy"):
   verdict.append({"policy":var,"n_conditions":len(g),
     "heading_nonworse_all":bool((g.delta_heading_rmse_deg<=1e-9).all()),
     "bias_nonworse_all":bool((g.delta_bias_rmse_dps<=1e-9).all()),
     "XY_nonworse_all":bool((g.delta_xy_rmse_m<=1e-9).all()),
     "condXY_nees_improved_all":bool((g.delta_condXY_nees<0).all()),
     "pose95_nonworse_all":bool((g.delta_pose95>=0).all()),
     "high_gate_changed_any":bool((g.natural_minus_frozen_accept_high!=0).any())})
  comp.to_csv(out/"INDEPENDENT_PAIRED_ALL.csv",index=False)
  pd.DataFrame(verdict).to_csv(out/"INDEPENDENT_GATES.csv",index=False)
  doc={"status":"HIGH_VR_ONLY_ORIGINAL_NUMERIC_INDEPENDENT_PASS",
    "original_zip_sha":SHA,
    "verified_full_recursive_arms":counted,
    "original_parity_records":len(parity),
    "los_r0_guard_records":len(los),
    "one_step_common_prior_records":len(m2),
    "high_bin_count_r2":final["n_high_bin_summary"],
    "candidate_gate_conditions":verdict,
    "conditional_xy_highVr_corrects_overconfidence":False,
    "scientific_calibrated_posterior":False,
    "dataset":"repeatedly inspected R2 single scene RF seed0",
    "caveat":"Fixed marginal V_s,C_rs does not fix conditional Var(s|r). LoS POWER transfer not evaluated."}
  save(out/"INDEPENDENT_FINAL.json",doc)
  print("HIGH_VR_REVIEW_FINAL "+json.dumps({
    "status":doc["status"],"checked":counted,"candidate_verdict":verdict,
    "L2_J4":[x for x in controls if x["bias"]=="L2" and x["solver"]=="J4"]},
    ensure_ascii=False),flush=True)
 return 0
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","run"),required=True)
 p.add_argument("--out",required=True)
 p.add_argument("--receipt");p.add_argument("--new");p.add_argument("--n4c");p.add_argument("--rf")
 a=p.parse_args()
 return audit(a.out) if a.phase=="pre" else complete(a.out,a.receipt,a.new,a.n4c,a.rf)
if __name__=="__main__":raise SystemExit(main())
