"""Retrain ONLY original N4B q-only POWER model after fixing five R5 LUT labels.

R4/R5 train R2 heldout; all train folds use exact original site weighting,
spatial exclusion, StandardScaler, Ridge(alpha=30), train tertile bin
means/covariances. First prove no-correction fit exactly reproduces all 9519
original POWER mean and covariance OOF predictions. GT never in EKF.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
AUDIT_BLOBS={
 "research/R5_N4B_20261015/n4b_rf_errors.py":"abd654dd9efde61fc7baffc350188b2a8b4904a3",
 "research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/POLE_LUT_SINGULARITY_20261016/pole_lut_fix.py":"d2474fcac8bc02dc20d1bad253b6c39956412376",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9"}
ART={
 "POLE_9519":"b0d41653fbecf8a01c4773e534edae8f501198cb7bf4cc27f066ccca66864636",
 "N4B":"170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b",
 "RAW":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "N4C":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9"}
CASES=("R2_aA_m0","R2_aA_m45")
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
FOLDS=("R2","R4","R5")
def hashfile(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for x in iter(lambda:f.read(1<<20),b""):h.update(x)
 return h.hexdigest()
def gitblob(path):
 p=Path(path)
 h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for x in iter(lambda:f.read(1<<20),b""):h.update(x)
 return h.hexdigest()
def save(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def verified(path,sha):
 h=hashfile(path)
 if h!=sha:raise RuntimeError("UPSTREAM_ARCHIVE_SHA_MISMATCH:"+str(path)+":"+h)
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ARCHIVED_CRC_INVALID")
 return z
def member(z,name):
 a=[q for q in z.namelist() if q==name or q.endswith("/"+name)]
 if len(a)!=1:raise RuntimeError("MEMBER_NOT_UNIQUE:"+name)
 return a[0]
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[]
 head=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
 if os.getenv("GITHUB_ACTIONS")!="true" or os.getenv("GITHUB_SHA")!=head:
  errors.append("WRONG_RUNNER_OR_SOURCE_SHA")
 for name,expected in AUDIT_BLOBS.items():
  p=ROOT/name
  if not p.is_file():errors.append("SOURCE_MISSING:"+name)
  elif gitblob(p)!=expected:errors.append("SOURCE_BLOB_CHANGED:"+name)
 try:ast.parse((HERE/"pole_power_refit.py").read_text())
 except Exception as e:errors.append("CODE_SYNTAX:"+repr(e))
 w=ROOT/".github/workflows/lut-pole-power-retrain.yml"
 if not w.is_file():errors.append("MISSING_WORKFLOW")
 else:
  s=w.read_text()
  toks=["pole_power_refit.py --phase pre","pole_power_refit.py --phase test",
       "pole_power_refit.py --phase run"]
  if not all(x in s for x in toks) or not s.index(toks[0])<s.index(toks[1])<s.index(toks[2]):
   errors.append("AUDIT_FIRST_RULE")
  if "if: always()" not in s:errors.append("MISSING_EVIDENCE")
 outdoc={"status":"GO" if not errors else "HOLD","source_sha":head,
     "audit_blobs":AUDIT_BLOBS,"archive_sha":ART,"errors":errors,
     "train_correction_is_GT_offline_only":True}
 save(out/"PRE_AUDIT.json",outdoc)
 print("POLE_POWER_PRE "+json.dumps({"status":outdoc["status"],"errors":errors}),flush=True)
 return 0 if not errors else 2

def setup():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
  str(ROOT/"research/R5_N4B_20261015"),
  str(ROOT/"research/R5_N4C_20261015"),
  str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"),
  str(ROOT/"research/POLE_LUT_SINGULARITY_20261016"),
  str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src")]
 import n4b_rf_errors as n4b
 import n4c_joint_sr4 as n4c
 from p3_rf_adapter4 import FrozenLut,R0
 from pole_lut_fix import candidate_pole_consistent_table
 from r2_bias_replay import build_positive_bias_controls
 return np,pd,n4b,n4c,FrozenLut,R0,candidate_pole_consistent_table,build_positive_bias_controls

def test():
 np,pd,n4b,n4c,FrozenLut,R0,patch,_=setup()
 n4c.simulation_unit_tests()
 # Original unconditional training input source has exactly one predictor, q.
 assert n4b.MODELS["POWER_BIN_JOINT"]==("log_fp_power",)
 rng=np.random.default_rng(20)
 train=pd.DataFrame({"e_r":rng.normal(size=240),"e_s":rng.normal(size=240),
    "log_fp_power":rng.normal(size=240)})
 test=train.iloc[:40]
 mu,C,info=n4b.fit_model(np,train,test,np.ones(len(train)),"POWER_BIN_JOINT",{"G5":[]})
 assert C.shape==(40,2,2) and np.linalg.eigvalsh(C).min()>0
 assert info["bin_feature"]=="log_fp_power"
 print("POLE_POWER_UNIT_PASS "+json.dumps({"N4B_SOURCE_FIT":"PASS","N4C_FROZEN_LINEAR_EQUIVALENCE":"PASS"}))
 return 0

def run(out,audit,patchzip,n4bzip,rfzip,n4czip):
 (np,pd,n4b,n4c,FrozenLut,R0,patch,controls_fn)=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 rec=json.loads(Path(audit).read_text())
 if rec["status"]!="GO" or rec["source_sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("NO_PRE_AUDIT")
 with verified(patchzip,ART["POLE_9519"]) as zp,verified(n4bzip,ART["N4B"]) as zb, \
      verified(rfzip,ART["RAW"]) as zr, verified(n4czip,ART["N4C"]) as zc:
  source=json.loads(zp.read(member(zp,"POLE_ALL_9519_FINAL.json")))
  if source["status"]!="POLE_RAW_9519_CORRECTED_PAIRED_SOURCE_VERIFIED":
   raise RuntimeError("NOT_AUDITED_9519_SOURCE")
  delta=pd.read_csv(io.BytesIO(zp.read(member(zp,"POLE_ALL_9519_SOURCE_OBSERVER_PARITY.csv"))))
  with gzip.open(io.BytesIO(zb.read(member(zb,"N4B_OOF_PREDICTIONS.csv.gz"))),"rt") as f:
   archived=pd.read_csv(f)
  base=archived[archived.model=="POWER_BIN_JOINT"].reset_index(drop=True).copy()
  if len(base)!=9519 or base.duplicated(["case","pose_id"]).any():
   raise RuntimeError("ORIGINAL_N4B_POWER_NO_9519")
  df=base.merge(delta[["case","pose_id","delta_label_for_Full_training"]],
                on=["case","pose_id"],validate="one_to_one",how="left")
  if len(df)!=9519 or df.delta_label_for_Full_training.isna().any():
   raise RuntimeError("INVALID_LOS_FULL_CORRECTION_JOIN")
  df["e_s_fixed"]=df.e_s+df.delta_label_for_Full_training
  modified=df[abs(df.delta_label_for_Full_training)>1e-12]
  if len(modified)!=5 or any(modified.route!="R5"):
   raise RuntimeError("UNEXPECTED_CORRECTED_TRAINING_LABELS")
  if not set(modified.case.unique()).issubset({"R5_aA_m0","R5_aB_m0"}):
   raise RuntimeError("POLE_FIX_UNEXPECTED_CASE")
  outputs=[];original_parity=[];folds=[]
  for held,training,test in n4b.feature_splits(np,df):
   train=df.loc[training].copy()
   evalset=df.loc[test].copy()
   weights=n4b.site_weights(np,pd,train)
   original_mean,original_cov,original_info=n4b.fit_model(
     np,train,evalset,weights,"POWER_BIN_JOINT",{"G5":[]})
   expected=evalset[["mu_r","mu_s","Vr","Vs","C_rs"]].to_numpy(float)
   measured=np.column_stack([original_mean[:,0],original_mean[:,1],
                       original_cov[:,0,0],original_cov[:,1,1],original_cov[:,0,1]])
   max_parity=float(np.max(abs(expected-measured)))
   if max_parity>1e-10:raise RuntimeError("ORIGINAL_N4B_POWER_NOT_REPRODUCED:"+str((held,max_parity)))
   original_parity.append({"held_route":held,"n_test":int(test.sum()),
                           "max_original_OOF_diff":max_parity})
   corrected=train.copy()
   corrected["e_s"]=corrected.e_s_fixed
   expected_test=evalset.copy()
   expected_test["e_s"]=expected_test.e_s_fixed
   mu,C,info=n4b.fit_model(np,corrected,expected_test,weights,
                        "POWER_BIN_JOINT",{"G5":[]})
   frame=evalset[["case","route","pose_id","e_r","e_s","e_s_fixed","log_fp_power"]].copy()
   frame["mu_r"]=mu[:,0];frame["mu_s"]=mu[:,1]
   frame["Vr"]=C[:,0,0];frame["Vs"]=C[:,1,1];frame["C_rs"]=C[:,0,1]
   frame["mu_r_old"]=expected[:,0];frame["mu_s_old"]=expected[:,1]
   frame["Vr_old"]=expected[:,2];frame["Vs_old"]=expected[:,3]
   frame["C_rs_old"]=expected[:,4]
   vals_old,_=n4b.add_nll(np,frame[["e_r","e_s"]].to_numpy(float),
                           original_mean,original_cov)
   vals_new,chi=n4b.add_nll(np,frame[["e_r","e_s_fixed"]].to_numpy(float),mu,C)
   frame["nll_old"]=vals_old;frame["nll_new"]=vals_new;frame["chi2_new"]=chi
   outputs.append(frame)
   folds.append({"held":held,"n_train":len(train),"n_test":len(evalset),
      "original_full_fit_parity":max_parity,
      "changed_train_labels":int(np.sum(abs(train.e_s_fixed-train.e_s)>1e-12)),
      "changed_test_labels":int(np.sum(abs(evalset.e_s_fixed-evalset.e_s)>1e-12)),
      "old_nll":float(np.mean(vals_old)),
      "new_nll":float(np.mean(vals_new)),
      "new_joint95":float(np.mean(chi<=5.991464547108)),
      "trained_power_cutpoints":info["cutpoints_train"],
      "new_power_bin_info":info["bins"]})
  data=pd.concat(outputs,ignore_index=True)
  data.to_csv(out/"POWER_POLE_RETRAINED_9519_OOF.csv.gz",index=False,compression="gzip")
  lookup=data.set_index(["case","pose_id"],verify_integrity=True)
  lut_original=FrozenLut(ROOT);lut_corrected=FrozenLut(ROOT)
  lut_corrected.s=patch(lut_original.s)
  meta=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  cases={v["id"]:v for v in meta["cases"]}
  traces={(v["case"],v["channel"]):v for v in
        json.loads(zr.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  reference_quality=n4c.parse_n4b_prediction(np,pd,zb)
  scores=[];parity=[]
  for case in CASES:
   item=traces[(case,"full")]
   raw=zr.read("P2_OUT/"+item["trace_file"])
   if hashlib.sha256(raw).hexdigest()!=item["trace_sha256"]:
    raise RuntimeError("ARCHIVED_R2_PACKET_CHANGED")
   with np.load(io.BytesIO(raw),allow_pickle=False) as z:
    t=z["t_s"].copy();pid=z["pose_id"].copy()
    truth=z["truth_for_offline_scoring_only"].copy()
    zz=np.column_stack([z["z_r_m"],z["z_s"]])
   oldq=[reference_quality[(case,int(k))] for k in pid]
   newq=[]
   for k in pid:
    k=int(k);val=lookup.loc[(case,k)]
    a={name:{"mean":q["mean"].copy(),"cov":q["cov"].copy()}
       for name,q in reference_quality[(case,k)].items()}
    a["POWER_BIN_JOINT"]={
       "mean":np.array([val["mu_r"],val["mu_s"]]),
       "cov":np.array([[val["Vr"],val["C_rs"]],[val["C_rs"],val["Vs"]]],float)}
    if np.linalg.eigvalsh(a["POWER_BIN_JOINT"]["cov"]).min()<=0:
     raise RuntimeError("RETRAINED_COV_NONSPD")
    newq.append(a)
   for level,b in BIAS.items():
    controls,x0=controls_fn(t,truth,level,seed=0)
    for solver in ("J4","SR4"):
     old=n4c.recurse(np,t,controls,x0,zz,oldq,solver,
                        "POWER_JOINT",lut_original,cases[case])
     base_file=zc.read(member(zc,f"N4C_{case}_full_{level}_{solver}.npz"))
     with np.load(io.BytesIO(base_file),allow_pickle=False) as a:
      j=np.flatnonzero((a["policies"]=="POWER_JOINT")&(a["gate_modes"]=="natural"))
      if len(j)!=1:raise RuntimeError("ORIG_POWER_REF_NOT_UNIQUE")
      idx=int(j[0]);xref=a["estimate"][:,idx];Pref=a["covariance"][:,idx]
      mask=a["status"][:,idx]=="APPLIED"
     diff=old["state"]-xref;diff[:,2]=(diff[:,2]+np.pi)%(2*np.pi)-np.pi
     dx=float(np.max(abs(diff)));dc=float(np.max(abs(old["cov"]-Pref)))
     dg=int(np.sum((old["status"]=="APPLIED")!=mask))
     if max(dx,dc)>1e-6 or dg:raise RuntimeError("N4C_OLD_NOT_FROZEN:"+str((dx,dc,dg)))
     parity.append({"case":case,"bias":level,"solver":solver,"state_diff":dx,"cov_diff":dc,"gate_diff":dg})
     new=n4c.recurse(np,t,controls,x0,zz,newq,solver,
                        "POWER_JOINT",lut_corrected,cases[case])
     a=n4c.score(np,old,t,truth,b)
     cc=n4c.score(np,new,t,truth,b)
     scores.append({"case":case,"bias":level,"solver":solver,
        "original_heading_rmse_deg":a["heading_rmse_deg"],
        "corrected_heading_rmse_deg":cc["heading_rmse_deg"],
        "original_xy_rmse_m":a["xy_rmse_m"],
        "corrected_xy_rmse_m":cc["xy_rmse_m"],
        "original_bias_rmse_dps":a["bias_rmse_dps"],
        "corrected_bias_rmse_dps":cc["bias_rmse_dps"],
        "original_pose_NEES":a["pose_nees"],
        "corrected_pose_NEES":cc["pose_nees"],
        "original_pose95":a["pose_95coverage"],
        "corrected_pose95":cc["pose_95coverage"],
        "original_gates":a["rf_applied"],
        "corrected_gates":cc["rf_applied"]})
     np.savez_compressed(out/f"POLE_REFIT_POWER_{case}_{level}_{solver}.npz",
        t_s=t,pose_id=pid,
        original_estimate=old["state"],original_cov=old["cov"],
        corrected_estimate=new["state"],corrected_cov=new["cov"],
        original_nis=old["nis"],corrected_nis=new["nis"],
        original_gate=old["status"],corrected_gate=new["status"])
   print("POLE_REFIT_CASE "+json.dumps({"case":case,"levels":4,"methods":2}),flush=True)
  with (out/"POLE_REFIT_R2_16_ARMS.csv").open("w",newline="",encoding="utf8") as fp:
   w=csv.DictWriter(fp,fieldnames=list(scores[0]));w.writeheader();w.writerows(scores)
  with (out/"POLE_REFIT_N4C_BASELINE_PARITY.csv").open("w",newline="",encoding="utf8") as fp:
   w=csv.DictWriter(fp,fieldnames=list(parity[0]));w.writeheader();w.writerows(parity)
  save(out/"POLE_REFIT_REPORT.json",{
    "status":"POLE_CORRECTED_POWER_OOF_AND_4STATE_RECURSION_RETRAINED",
    "n_full_labels":9519,"corrected_gt_labels":5,
    "unchanged_original_fold_full_parity_max":max(v["max_original_OOF_diff"] for v in original_parity),
    "folds":folds,"n_R2_power_recursive_arm_pairs":len(scores),
    "baseline_parities":len(parity),
    "results":scores,"original_N4B_source_git_sha":AUDIT_BLOBS["research/R5_N4B_20261015/n4b_rf_errors.py"],
    "limitations":["N4B POWER q-only refit only; P2 G5+geometry model not globally retrained",
      "R2 is repeatedly inspected single corridor seed0",
      "Full RF trained correction not clean LoS safe",
      "No independent FFD bank rebuild","Not a new Bayesian covariance consistency proof"],
    "scientific_generalization_PASS":False})
  print("POLE_REFIT_FINAL "+json.dumps({"n":len(scores),
      "old_parity":max(v["max_original_OOF_diff"] for v in original_parity),
      "R2_L2_J4":[v for v in scores if v["bias"]=="L2" and v["solver"]=="J4"],
      "folds":[{"held":f["held"],"old_nll":f["old_nll"],"new_nll":f["new_nll"],
                "n_train_changed":f["changed_train_labels"]} for f in folds]},ensure_ascii=False),flush=True)
 return 0
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("pre","test","run"),required=True)
 ap.add_argument("--out");ap.add_argument("--audit");ap.add_argument("--pole")
 ap.add_argument("--n4b");ap.add_argument("--rf");ap.add_argument("--n4c")
 a=ap.parse_args()
 if a.phase=="pre":return pre(a.out)
 if a.phase=="test":return test()
 return run(a.out,a.audit,a.pole,a.n4b,a.rf,a.n4c)
if __name__=="__main__":raise SystemExit(main())
