"""N4-B/M: FFD-polarization matching, Heading sensitivity and conditional RF reliability.
Re-run ORIGINAL N4-B with geometry features added. Original FFD/LUT/observer,
full complex H and EKF4 states are read-only. The primary physics features
use GT pose ORACLE geometry (offline scientific ceiling). A separate test
evaluates ORIGINAL pre-RF Joint4 priors, and is NOT confused with oracle
features or deployed probabilities.

New feature naming POL-V1 avoids collisions with the older Physics G0-G5.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE=ROOT/"research/R5_N4B_20261015"
R2=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
PHY=ROOT/"research/PHYSICS_RS_STAGED_20261015/code"
OBS=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
MANIFEST=ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
N4B_SHA="170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b"
R0_S=.0081
CHI2=5.991464547107979
PINNED={
"research/R5_N4B_20261015/n4b_rf_errors.py":"abd654dd9efde61fc7baffc350188b2a8b4904a3",
"research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py":"24b7b0103a232662afaf5b1b79bfb542aa7123db",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
"research/PHYSICS_RS_STAGED_20261015/code/features.py":"c556da153739aaf99d2558c84c1a515c3da41a97",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
}
GEOM_FIELDS=("p_m1_los","p_m2_los","p_dom_los","balance_los",
 "s_los_expected","Hpsi_lut","Ipsi_nominal",
 "relative_rx_az_cos","relative_rx_az_sin","relative_tx_az_cos",
 "relative_tx_az_sin","theta_elev","body_mount_cos","body_mount_sin")
BASELINE_MODELS=("R0","POWER_BIN_JOINT","SIMPLE_DIAG","SIMPLE_JOINT","SIMPLE_G4","G5_RESEARCH_ONLY")
ADD_MODELS={
 "SIMPLE_PLUS_PORT_DOM":("SIMPLE","p_dom_los"),
 "SIMPLE_PLUS_BALANCE":("SIMPLE","balance_los"),
 "SIMPLE_PLUS_SIGNED_LOS":("SIMPLE","s_los_expected"),
 "SIMPLE_PLUS_HPSI":("SIMPLE","Hpsi_lut"),
 "SIMPLE_PLUS_IEFF":("SIMPLE","Ipsi_nominal"),
 "SIMPLE_PLUS_ORIENTATION":("SIMPLE","body_mount_cos","body_mount_sin"),
 "SIMPLE_PLUS_FFD_ALL":("SIMPLE","s_los_expected","balance_los","Hpsi_lut",
      "Ipsi_nominal","relative_rx_az_cos","relative_rx_az_sin",
      "relative_tx_az_cos","relative_tx_az_sin","theta_elev"),
 "SIMPLE_G4_PLUS_FFD_ALL":("G4","s_los_expected","balance_los","Hpsi_lut",
      "Ipsi_nominal","relative_rx_az_cos","relative_rx_az_sin",
      "relative_tx_az_cos","relative_tx_az_sin","theta_elev"),
 "G5_PLUS_FFD_ALL_RESEARCH_ONLY":("G5","s_los_expected","balance_los",
      "Hpsi_lut","Ipsi_nominal","relative_rx_az_cos","relative_rx_az_sin",
      "relative_tx_az_cos","relative_tx_az_sin","theta_elev"),
}
ALL_MODELS=BASELINE_MODELS+tuple(ADD_MODELS)
POSE_REF_COV=(.1**2,.1**2,math.radians(5)**2)

def sha(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(path):
 p=Path(path)
 h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def store(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def checked(path,digest):
 if sha(path)!=digest:raise RuntimeError("ARCHIVE_SHA_MISMATCH:"+str(path))
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ARCHIVE_CRC_INVALID:"+str(path))
 return z
def member(z,basename):
 matches=[k for k in z.namelist() if k==basename or k.endswith("/"+basename)]
 if len(matches)!=1:raise RuntimeError("ARCHIVE_MEMBER_COUNT:"+basename+":"+str(len(matches)))
 return matches[0]

def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];origin={}
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("GITHUB_ACTIONS_REQUIRED")
 try:
  head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
  if head!=os.getenv("GITHUB_SHA"):errors.append("NOT_EXACT_GIT_SHA")
 except Exception as e:
  head=None;errors.append("SOURCE_REV_ERROR:"+repr(e))
 for rel,exp in PINNED.items():
  path=ROOT/rel
  if not path.is_file():errors.append("MISSING_FROZEN_SOURCE:"+rel)
  else:
   got=blob(path);origin[rel]=got
   if got!=exp:errors.append("FROZEN_SOURCE_MODIFIED:"+rel)
 try:
  mf=json.loads(MANIFEST.read_text())
  indexed={x["path"]:x for x in mf["assets"]}
  paths=[p for case in mf["cases"] for p in (case["full_path"],case["los_path"],case["samples_path"])]
  paths.append("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy")
  for rel in paths:
   file=ROOT/rel
   if not file.is_file():errors.append("MISSING_FROZEN_INPUT:"+rel)
   elif rel not in indexed or sha(file)!=indexed[rel]["sha256"] or file.stat().st_size!=indexed[rel]["bytes"]:
    errors.append("FROZEN_INPUT_MISMATCH:"+rel)
 except Exception as e:errors.append("FROZEN_INPUT_AUDIT:"+repr(e))
 try:ast.parse((HERE/"n4b_pol_geometry.py").read_text(encoding="utf-8"))
 except Exception as e:errors.append("SELF_AST_FAILED:"+repr(e))
 wf=ROOT/".github/workflows/r5-n4b-pol-geometry.yml"
 if not wf.is_file():errors.append("WORKFLOW_MISSING")
 else:
  text=wf.read_text()
  req=("n4b_pol_geometry.py --phase pre","n4b_pol_geometry.py --phase test",
       "n4b_pol_geometry.py --phase run","actions: read","if: always()")
  if any(k not in text for k in req):errors.append("WORKFLOW_CONTRACT_MISSING")
  elif not text.index(req[0])<text.index(req[1])<text.index(req[2]):
   errors.append("NOT_AUDIT_FIRST")
 doc={"decision":"GO" if not errors else "HOLD",
  "stage":"N4-B-POL-V1","source_sha":head,"frozen_git_blobs":origin,
  "frozen_raw_files":len(paths) if "paths" in locals() else None,
  "archive_sha256":{"RF":RF_SHA,"N4B_original":N4B_SHA,"R2":R2_SHA},
  "oracle_warning":"GT pose used for offline physical upper bound; not online EKF feature",
  "issues":errors,"scientific_PASS":False}
 store(out/"PRE_AUDIT.json",doc)
 print("POL_PRE "+json.dumps({"decision":doc["decision"],"issues":errors}),flush=True)
 return 0 if not errors else 2

def environment():
 import numpy as np
 import pandas as pd
 sys.path.insert(0,str(BASE))
 sys.path.insert(0,str(ROOT/"research/R5_FULLRF_B0_GATES_20261015"))
 sys.path.insert(0,str(PHY))
 sys.path.insert(0,str(R2))
 sys.path.insert(0,str(OBS))
 import n4b_rf_errors as old
 from features import GROUPS
 from p3_rf_adapter4 import FrozenLut
 return np,pd,old,GROUPS,FrozenLut

def physical_features(np,lut,x,case,P=None):
 """Actual FFD LUT at given pose; signed linear polarization axis features."""
 pose=np.asarray(x,float)
 if pose.ndim!=1 or len(pose)<3:raise RuntimeError("POSE_REQUIRED")
 h,H=lut.model(pose[:3],case)
 s=float(h[1])
 if not np.isfinite(s) or not np.isfinite(H).all() or abs(s)>1.000001:
  raise RuntimeError("FFD_S_OUTSIDE_VALID_DOMAIN:"+str(s))
 s=float(np.clip(s,-1,1))
 M1=(1+s)/2;M2=(1-s)/2;balance=max(0.,1-s*s)
 u,v=pose[0]-case["anchor"][0],pose[1]-case["anchor"][1]
 rho=math.hypot(u,v)
 phi_tx=math.atan2(-v,u)
 phi_rx=math.atan2(-v,-u)-pose[2]-math.radians(case["mount_deg"])
 theta=math.atan2(rho,case["anchor"][2]-case["robot_z_m"])
 body=pose[2]+math.radians(case["mount_deg"])
 # Simple co/cross ideal LP comparison; n=1,2 axes differ by pi/2,
 # not by pi. This is NOT a substitute for actual FFD polarization.
 ideal1=math.cos(body-math.pi/4)**2
 ideal2=math.cos(body-3*math.pi/4)**2
 if P is None:P=np.diag(POSE_REF_COV)
 P=np.asarray(P,float)
 if P.shape==(4,4):P=P[:3,:3]
 if P.shape!=(3,3) or np.linalg.eigvalsh(P).min()<=0:
  raise RuntimeError("PRIOR_COV_INVALID")
 Hxy=H[1,:2];Hpsi=float(H[1,2])
 vpsi=float(P[2,2])
 cross=P[:2,2]
 cond=P[:2,:2]-np.outer(cross,cross)/vpsi
 cond=(cond+cond.T)/2
 if np.linalg.eigvalsh(cond).min()<=0:raise RuntimeError("PRIOR_SCHUR_NOT_PD")
 Heff=Hpsi+Hxy@cross/vpsi
 residual_var=R0_S+Hxy@cond@Hxy
 Ieff=float(Heff**2/residual_var)
 return {
  "p_m1_los":M1,"p_m2_los":M2,"p_dom_los":max(M1,M2),
  "balance_los":balance,"s_los_expected":s,
  "Hpsi_lut":Hpsi,"Ipsi_nominal":Ieff,
  "relative_rx_az_cos":math.cos(phi_rx),"relative_rx_az_sin":math.sin(phi_rx),
  "relative_tx_az_cos":math.cos(phi_tx),"relative_tx_az_sin":math.sin(phi_tx),
  "theta_elev":theta,
  "body_mount_cos":math.cos(body),"body_mount_sin":math.sin(body),
  "heading_information_raw":Hpsi*Hpsi/R0_S,
  "ideal_P1_no_projection":ideal1,"ideal_P2_no_projection":ideal2,
  "ideal_port1_vs_FFD_difference":ideal1-M1,
  "position_coupled_prediction_var":float(residual_var),
  "Ipsi_effective_prior_covariance":Ieff,
 }

def feature_table(np,pd,full,lut,manifest,geometry_source="GT"):
 bycase={c["id"]:c for c in manifest["cases"]}
 out=[]
 for case,frame in full.groupby("case",sort=True):
  desc=bycase[case]
  for r in frame.itertuples(index=False):
   pose=[r.x_eval,r.y_eval,r.yaw_eval_rad]
   f=physical_features(np,lut,pose,desc)
   f.update({"case":case,"pose_id":int(r.pose_id)})
   out.append(f)
 g=pd.DataFrame(out)
 if len(g)!=9519 or g.duplicated(["case","pose_id"]).any():raise RuntimeError("GEOM_FRAME_COUNT")
 df=full.merge(g,on=["case","pose_id"],validate="one_to_one")
 if len(df)!=9519:raise RuntimeError("PHYSICAL_GEOMETRY_DROPPED")
 if not np.allclose(df.p_m1_los+df.p_m2_los,1,atol=1e-12):
  raise RuntimeError("FFD_LP_FRACTION_IDENTITY_FAIL")
 if not np.allclose(df.balance_los,1-df.s_los_expected**2,atol=1e-12):
  raise RuntimeError("FFD_BALANCE_IDENTITY_FAIL")
 if not np.isfinite(df[list(GEOM_FIELDS)].to_numpy(float)).all():
  raise RuntimeError("NONFINITE_GEOMETRY_FEATURE")
 return df

def signed_reference(np,train,test,w,features,binfield,diagonal,old):
 """Identical N4-B Ridge/stratified centered covariance fit, with supplied feature names."""
 from sklearn.preprocessing import StandardScaler
 from sklearn.linear_model import Ridge
 Y=train[["e_r","e_s"]].to_numpy(float)
 A=StandardScaler()
 Z=A.fit_transform(train[features].to_numpy(float))
 Zte=A.transform(test[features].to_numpy(float))
 reg=Ridge(alpha=30.,fit_intercept=True)
 reg.fit(Z,Y,sample_weight=w)
 mean_train=reg.predict(Z);means=reg.predict(Zte)
 residual=Y-mean_train
 global_mean,global_cov=old.row_cov(np,residual,w)
 global_cov=old.fix_cov(np,global_cov,not diagonal)
 cuts=np.unique(np.quantile(train[binfield].to_numpy(float),[1/3,2/3]))
 bx=np.searchsorted(cuts,train[binfield].to_numpy(float),side="right")
 bt=np.searchsorted(cuts,test[binfield].to_numpy(float),side="right")
 cov=np.zeros((len(test),2,2))
 for bin_id in range(len(cuts)+1):
  tr=bx==bin_id;te=bt==bin_id
  if not np.any(te):continue
  if tr.sum()<15:raise RuntimeError("TRAIN_COV_BIN_TOO_SMALL")
  raw_mu,raw_cov=old.row_cov(np,residual[tr],w[tr])
  neff=w[tr].sum()**2/(w[tr]**2).sum()
  alpha=neff/(neff+100)
  mu_b=alpha*raw_mu+(1-alpha)*global_mean
  C=old.fix_cov(np,alpha*raw_cov+(1-alpha)*global_cov,not diagonal)
  means[te]+=mu_b
  cov[te]=C
 if np.linalg.eigvalsh(cov).min()<=0:raise RuntimeError("COV_FAILED")
 return means,cov

def make_fit(np,train,test,w,name,old,groups):
 if name in BASELINE_MODELS:
  return old.fit_model(np,train,test,w,name,groups)[:2]
 config=ADD_MODELS[name]
 raw=config[0]
 if raw=="SIMPLE":
  feats=list(old.SIMPLE)+list(config[1:])
  bins="log_fp_power";diagonal=True
 elif raw=="G4":
  feats=list(old.G4)+list(config[1:])
  bins="detector_s_span";diagonal=False
 elif raw=="G5":
  feats=list(groups["G5"])+["mount_feature","anchor_x_feature"]+list(config[1:])
  bins="detector_s_span";diagonal=False
 else:raise RuntimeError("UNKNOWN_POLAR_ABLATION:"+name)
 return signed_reference(np,train,test,w,feats,bins,diagonal,old)

def unit():
 np,pd,old,groups,FrozenLut=environment()
 rng=np.random.default_rng(20261015)
 inputs=pd.DataFrame({"e_r":rng.normal(.05,.1,300),"e_s":rng.normal(.02,.17,300)})
 for f in set(list(old.G4)+list(old.SIMPLE)+list(groups["G5"])+list(GEOM_FIELDS)):
  if f not in inputs:inputs[f]=rng.normal(0,1,len(inputs))
 w=np.ones(300)
 for name,features,binname,diag in [
  ("SIMPLE_DIAG",list(old.SIMPLE),"log_fp_power",True),
  ("SIMPLE_G4",list(old.G4),"detector_s_span",False),
  ("SIMPLE_JOINT",list(old.SIMPLE),"log_fp_power",False)]:
  a,c,_=old.fit_model(np,inputs.iloc[:250],inputs.iloc[250:],
                        w[:250],name,groups)
  b,d=signed_reference(np,inputs.iloc[:250],inputs.iloc[250:],
                         w[:250],features,binname,diag,old)
  np.testing.assert_allclose(a,b,atol=1e-12,rtol=1e-12)
  np.testing.assert_allclose(c,d,atol=1e-12,rtol=1e-12)
 # Actual frozen FFD, nominal geometry and finite-diff derivative canary.
 lut=FrozenLut(ROOT)
 case={"anchor":[4,0,2.65],"mount_deg":0,"robot_z_m":.45}
 for pose in ([1.2,.5,math.radians(37)],[3.,1.,math.radians(-42)]):
  f=physical_features(np,lut,pose,case)
  assert abs(f["p_m1_los"]+f["p_m2_los"]-1)<1e-12
  assert 0<=f["balance_los"]<=1 and f["Ipsi_nominal"]>=0
  epsilon=math.radians(1e-4)
  p1=np.array(pose,float);p2=p1.copy()
  p1[2]+=epsilon;p2[2]-=epsilon
  h1=lut.model(p1,case)[0][1];h2=lut.model(p2,case)[0][1]
  deriv=(h1-h2)/(2*epsilon)
  if abs(deriv-f["Hpsi_lut"])>2e-3:
   raise RuntimeError("HPSI_FFD_FINITE_DIFFERENCE_FAIL:"+str((deriv,f["Hpsi_lut"])))
 assert abs(math.cos(0-math.pi/4)**2+.5-1)<1e-12
 print("POL_UNIT_PASS "+json.dumps({"base_model_parity":3,
    "FFD_Hpsi_fd":2,"new_feature_groups":len(ADD_MODELS),
    "orthogonal_port_axis":"pi/2 not pi"}),flush=True)
 return 0

def fit_all(np,pd,old,groups,full):
 rows=[];pred=[];splits=[];modelparams={}
 for held,train_mask,test_mask in old.feature_splits(np,full):
  tr=full.loc[train_mask].copy()
  te=full.loc[test_mask].copy()
  w=old.site_weights(np,pd,tr)
  split={"held_route":held,"train_rows":len(tr),"test_rows":len(te),
    "train_mount":sorted(tr.mount_feature.unique().tolist()),
    "test_mount":sorted(te.mount_feature.unique().tolist())}
  splits.append(split)
  Y=te[["e_r","e_s"]].to_numpy(float)
  for name in ALL_MODELS:
   mu,C=make_fit(np,tr,te,w,name,old,groups)
   nll,chi2=old.add_nll(np,Y,mu,C)
   table=te[["case","route","pose_id","x_eval","y_eval",
         "mount_feature","anchor_x_feature","e_r","e_s",
         "s_los_expected","p_dom_los","balance_los","Hpsi_lut",
         "Ipsi_nominal","body_mount_cos","body_mount_sin"]].copy()
   table["model"]=name;table["nll"]=nll;table["chi2"]=chi2
   table["mu_r"]=mu[:,0];table["mu_s"]=mu[:,1]
   table["Vr"]=C[:,0,0];table["Vs"]=C[:,1,1];table["C_rs"]=C[:,0,1]
   pred.append(table)
   for case,idx in table.groupby("case").indices.items():
    loc=np.asarray(idx,int)
    rows.append({"held_route":held,"case":case,"model":name,
      "n":len(loc),"nll_mean":float(np.mean(nll[loc])),
      "joint95":float(np.mean(chi2[loc]<=CHI2)),
      "chi2_mean":float(np.mean(chi2[loc])),
      "Vr_mean":float(np.mean(C[loc,0,0])),
      "Vs_mean":float(np.mean(C[loc,1,1])),
      "Crs_mean":float(np.mean(C[loc,0,1])),
      "mu_r_mean":float(np.mean(mu[loc,0])),"mu_s_mean":float(np.mean(mu[loc,1]))})
   print("POL_MODEL "+json.dumps({"fold":held,"model":name,
      "nll":float(np.mean(nll)),"coverage":float(np.mean(chi2<=CHI2))}),flush=True)
 return pd.DataFrame(rows),pd.concat(pred,ignore_index=True),splits

def audit_old_predictions(np,pd,pred,old_zip):
 with checked(old_zip,N4B_SHA) as z:
  prior=json.loads(z.read(member(z,"N4B_FINAL.json")))
  if prior["status"]!="N4B_AUDITED_RESIDUAL_AND_LIKELIHOOD_COMPLETE":
   raise RuntimeError("N4B_ORIGINAL_EXPERIMENT_NOT_PASS")
  with gzip.open(io.BytesIO(z.read(member(z,"N4B_OOF_PREDICTIONS.csv.gz"))),"rt") as f:
   prev=pd.read_csv(f)
 for name in BASELINE_MODELS:
  a=pred[pred.model==name].sort_values(["case","pose_id"])
  b=prev[prev.model==name].sort_values(["case","pose_id"])
  if len(a)!=9519 or len(b)!=9519 or not np.array_equal(a.pose_id,b.pose_id) or not np.array_equal(a.case,b.case):
   raise RuntimeError("OLD_N4B_BASELINE_ALIGNMENT_MISMATCH:"+name)
  for key in ("nll","mu_r","mu_s","Vr","Vs","C_rs"):
   diff=np.max(np.abs(a[key].to_numpy(float)-b[key].to_numpy(float)))
   if diff>1e-8:raise RuntimeError("N4B_BASELINE_DIFFERENCE:"+name+"/"+key+"/"+str(diff))
 return {"n_baseline_arms":len(BASELINE_MODELS),
   "parity_packets":9519*len(BASELINE_MODELS),"max_tol":1e-8}

def bootstrap(np,pd,pred):
 b=pred[["case","pose_id","x_eval","y_eval","model","nll"]].copy()
 b["block"]=(b.case+":"+np.floor(b.x_eval/1.5).astype(int).astype(str)+":"+
             np.floor(b.y_eval/1.5).astype(int).astype(str))
 b=b.pivot(index=["case","pose_id","block"],columns="model",values="nll").reset_index()
 if len(b)!=9519:raise RuntimeError("MODEL_PACKET_ALIGNMENT_FAIL")
 out=[];rng=np.random.default_rng(20261015)
 contrasts=[
  ("SIMPLE_PLUS_SIGNED_LOS","SIMPLE_DIAG"),
  ("SIMPLE_PLUS_BALANCE","SIMPLE_DIAG"),
  ("SIMPLE_PLUS_HPSI","SIMPLE_DIAG"),
  ("SIMPLE_PLUS_IEFF","SIMPLE_DIAG"),
  ("SIMPLE_PLUS_FFD_ALL","SIMPLE_DIAG"),
  ("SIMPLE_G4_PLUS_FFD_ALL","SIMPLE_G4"),
  ("G5_PLUS_FFD_ALL_RESEARCH_ONLY","G5_RESEARCH_ONLY"),
 ]
 for candidate,base in contrasts:
  diff=b[candidate].to_numpy(float)-b[base].to_numpy(float)
  group=pd.DataFrame({"block":b.block,"diff":diff}).groupby("block").agg(
      total=("diff","sum"),n=("diff","size"))
  totals=group.total.to_numpy(float);sizes=group.n.to_numpy(float)
  bs=[]
  for i in range(300):
   sample=rng.integers(0,len(group),len(group))
   bs.append(float(totals[sample].sum()/sizes[sample].sum()))
  out.append({"candidate":candidate,"reference":base,
    "delta_nll":float(np.mean(diff)),
    "spatial_block_boot95":np.quantile(bs,[.025,.975]).tolist(),
    "blocks":len(group),"independent_scene":False})
 return out

def prior_stress(np,pd,old,groups,full,lut,mf,refzip):
 """For R2 only: train on R4/R5 oracle geometry; test on causal J4 pre-update pose/P."""
 from r2_bias_replay import predict_one,build_positive_bias_controls,METHODS,INITIAL_POSE_STD,BIAS_PRIOR_STD
 detail=[]
 trmask,temask=next((a,b) for route,a,b in old.feature_splits(np,full) if route=="R2")
 train=full.loc[trmask].copy()
 test=full.loc[temask].copy()
 w=old.site_weights(np,pd,train)
 name="SIMPLE_PLUS_FFD_ALL"
 features=list(old.SIMPLE)+list(ADD_MODELS[name][1:])
 from sklearn.preprocessing import StandardScaler
 from sklearn.linear_model import Ridge
 scaler=StandardScaler().fit(train[features])
 ridge=Ridge(alpha=30.).fit(scaler.transform(train[features]),
                          train[["e_r","e_s"]].to_numpy(float),sample_weight=w)
 residual=train[["e_r","e_s"]].to_numpy(float)-ridge.predict(scaler.transform(train[features]))
 globmu,globC=old.row_cov(np,residual,w)
 globC=old.fix_cov(np,globC,False)
 binfield="log_fp_power";cuts=np.unique(np.quantile(train[binfield],[1/3,2/3]))
 bins=np.searchsorted(cuts,train[binfield],side="right")
 Cbin={};mubin={}
 for b in range(len(cuts)+1):
  pick=bins==b
  effective=w[pick].sum()**2/(w[pick]**2).sum()
  alpha=effective/(effective+100)
  m,C=old.row_cov(np,residual[pick],w[pick])
  mubin[b]=alpha*m+(1-alpha)*globmu
  Cbin[b]=old.fix_cov(np,alpha*C+(1-alpha)*globC,False)
 desc={c["id"]:c for c in mf["cases"]}
 with checked(refzip,R2_SHA) as z:
  for level in ("B0","L2"):
   for case in ("R2_aA_m0","R2_aA_m45"):
    zname=f"{case}_full_{level}_seed0_recursive.npz"
    with np.load(io.BytesIO(z.read(member(z,zname))),allow_pickle=False) as v:
     archive={key:v[key].copy() for key in v.files}
    if list(archive["names"])!=list(METHODS):raise RuntimeError("PRIOR_METHOD_LIST_CHANGED")
    src=test[test.case==case].set_index("pose_id")
    # Original R2 Full archive contains the correct truth/t timeline only
    # for the 979 RF-update frames, not all 1303 yaw-sweep records.
    i=list(METHODS).index("J4")
    times=archive["t_s"];ids=archive["pose_id"].astype(int)
    truth=src.loc[ids,["x_eval","y_eval","yaw_eval_rad"]].to_numpy(float)
    ctr,x0=build_positive_bias_controls(times,truth,level,seed=0)
    xs=archive["estimate"][:,i,:];Ps=archive["covariance"][:,i,:,:]
    maprow=[];badprior=0
    for k,pid in enumerate(ids):
     if k==0:
      pred=np.r_[x0,0.];cov=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
     else:
      pred,cov=predict_one(xs[k-1],Ps[k-1],
        float(ctr["ds_odom"][k]),float(ctr["dtheta_gyro"][k]),float(ctr["dt_s"][k]))
     physical=physical_features(np,lut,pred,desc[case],cov)
     row=src.loc[int(pid)].copy()
     for g in GEOM_FIELDS:row[g]=physical[g]
     maprow.append(row)
    prior=pd.DataFrame(maprow)
    if len(prior)!=len(ids):raise RuntimeError("PRIOR_POSE_BINDING")
    truthdf=src.loc[ids]
    for prior_name,subset in (("ORACLE_GT",truthdf),("CAUSAL_J4_PRIOR",prior)):
     x=subset[features].to_numpy(float)
     mu=ridge.predict(scaler.transform(x))
     bidx=np.searchsorted(cuts,subset[binfield].to_numpy(float),side="right")
     R=np.stack([Cbin[j] for j in bidx])
     mu+=np.stack([mubin[j] for j in bidx])
     e=truthdf[["e_r","e_s"]].to_numpy(float)
     nll,chisq=old.add_nll(np,e,mu,R)
     detail.append({"case":case,"bias_level":level,"test_pose_source":prior_name,
       "n":len(ids),"mean_nll":float(nll.mean()),
       "joint95":float(np.mean(chisq<=CHI2)),
       "note":"pre-RF pose predicted from original past Joint4 states; training geometry was oracle GT"})
 return detail

def main_run(out,pre,raw,n4b,r2ref):
 np,pd,old,groups,FrozenLut=environment()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 receip=json.loads(Path(pre).read_text())
 if receip["decision"]!="GO" or receip["source_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("PREAUDIT_NOT_GO")
 manifest=json.loads(MANIFEST.read_text())
 data=old.create_dataset(np,pd,manifest)
 with checked(raw,RF_SHA) as f:
  orig=old.original_14_parity(np,data,f)
 if sum(x["rows"] for x in orig)!=14502:raise RuntimeError("OBSERVER_INPUT_PARITY_COUNT")
 full=data[data.channel=="full"].copy()
 if len(full)!=9519:raise RuntimeError("ORIGINAL_FULL_POSES_COUNT")
 lut=FrozenLut(ROOT)
 enriched=feature_table(np,pd,full,lut,manifest)
 measurements=enriched[["case","pose_id","route","x_eval","y_eval","yaw_eval_rad",
   "mount_feature","anchor_x_feature","s_los_expected","p_m1_los","p_m2_los",
   "balance_los","p_dom_los","Hpsi_lut","Ipsi_nominal",
   "ideal_P1_no_projection","ideal_port1_vs_FFD_difference",
   "heading_information_raw"]].copy()
 measurements.to_csv(out/"POL_V1_GEOMETRY_ORACLE.csv.gz",index=False,compression="gzip")
 matched=abs(enriched.ideal_port1_vs_FFD_difference.to_numpy(float))
 bycase=[]
 for case,g in enriched.groupby("case"):
  bycase.append({"case":case,"mount_deg":int(g.mount_feature.iloc[0]*45),
    "n":len(g),"median_los_port_dominance":float(g.p_dom_los.median()),
    "median_los_balance":float(g.balance_los.median()),
    "median_abs_heading_jacobian":float(abs(g.Hpsi_lut).median()),
    "median_Ipsi_nominal":float(g.Ipsi_nominal.median()),
    "median_ideal_port1_vs_actual_FFD_diff":float(abs(g.ideal_port1_vs_FFD_difference).median()),
    "abs_signed_e_s_mean":float(abs(g.e_s.mean())),
    "s_e_squared":float(np.mean(g.e_s.to_numpy(float)**2)),
    "r_e_squared":float(np.mean(g.e_r.to_numpy(float)**2))})
 score,pred,splits=fit_all(np,pd,old,groups,enriched)
 parity=audit_old_predictions(np,pd,pred,n4b)
 pred.to_csv(out/"POL_V1_HELDOUT_PREDICTIONS.csv.gz",index=False,compression="gzip")
 score.to_csv(out/"POL_V1_CASE_SCORES.csv",index=False)
 import scipy.stats
 evals=[]
 for name,g in pred.groupby("model",sort=True):
  evals.append({"model":name,"n":len(g),"pooled_nll":float(g.nll.mean()),
    "pooled_95coverage":float(np.mean(g.chi2<=CHI2)),
    "calibrated_chi2_mean":float(g.chi2.mean()),
    "oracle_geometric_features_in_training":bool(name in ADD_MODELS)})
 boot=bootstrap(np,pd,pred)
 prior_stress_results=prior_stress(np,pd,old,groups,enriched,lut,manifest,r2ref)
 pd.DataFrame(bycase).to_csv(out/"POL_V1_GEOMETRY_BY_CASE.csv",index=False)
 pd.DataFrame(evals).to_csv(out/"POL_V1_MODEL_SUMMARY.csv",index=False)
 pd.DataFrame(boot).to_csv(out/"POL_V1_BLOCK_BOOTSTRAP.csv",index=False)
 pd.DataFrame(prior_stress_results).to_csv(out/"POL_V1_PRE_RF_PRIOR_TRANSFER.csv",index=False)
 result={"schema":"N4B_POL_V1_FFD_LOS_MATCHING_CONDITIONAL_RF_ERROR",
   "status":"AUDITED_GEOMETRIC_N4B_REEXECUTION_COMPLETE",
   "source_sha":os.getenv("GITHUB_SHA"),
   "original_n4b_model_parity":parity,
   "original_archive_parity_frames":sum(x["rows"] for x in orig),
   "full_obs":len(enriched),
   "physical_oracle_features":{
      "M1_M2":"(1±s_LOS_GT)/2","dominance":"(1+|s_LOS_GT|)/2",
      "balance":"1-s_LOS_GT^2",
      "Heading_slope":"Hpsi from actual frozen 3D FFD LUT",
      "conditional_information":"nominal 0.1m/5deg diagonal P0; R0_S=.0081",
      "tx_rx_angles":"anchor-relative azimuths, not merely mount+heading"},
   "model_summary":evals,
   "case_physical_descriptives":bycase,
   "per_route_mount_splits":splits,
   "paired_bootstrap":boot,
   "pre_rf_prior_transfer":prior_stress_results,
   "intended_scope":"oracle physical feasibility of mount-heading-polarization reliability conditioning, not a ready EKF likelihood",
   "hard_stops":["not normalized p(z|state) from oracle pose", "no independent RF scenes",
     "pre-RF prior assessment is R2 only; no trained causal online prior density",
     "nominal Ipsi uses fixed covariance, not recursive time-varying posterior",
     "G5 Jones-frequency features not validated on DWM1000",
     "95% coverage and NLL are offline conditional residual metrics, not Pose NEES"],
   "scientific_DEPLOYMENT_PASS":False}
 store(out/"POL_V1_FINAL.json",result)
 print("POL_FINAL "+json.dumps({"status":result["status"],
    "model_summary":evals,"cases":bycase,"bootstrap":boot,
    "preRF":prior_stress_results,
    "original_parity":parity},ensure_ascii=False),flush=True)
 return 0

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",required=True,choices=("pre","test","run"))
 p.add_argument("--out");p.add_argument("--audit");p.add_argument("--raw")
 p.add_argument("--n4b");p.add_argument("--r2")
 a=p.parse_args()
 if a.phase=="pre":return audit(a.out)
 if a.phase=="test":return unit()
 if not all((a.out,a.audit,a.raw,a.n4b,a.r2)):raise RuntimeError("N4B_POL_REQUIRED_ARGS")
 return main_run(a.out,a.audit,a.raw,a.n4b,a.r2)
if __name__=="__main__":raise SystemExit(main())
