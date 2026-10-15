"""N4-B: frozen Full RF range+s residual structure, held-route Gaussian likelihood.

Preserves original LoS FFD LUT and all observation packets. Source/asset audit
precedes all scientific work. Ground truth used only to construct regression
targets and offline score. The conditional model is NOT used in the EKF here.

Two crucial distinctions:
  1. E[e^2|q] != Var(e|q) when mean bias is nonzero.
  2. q extracted from the same RF measurement can make p(e|q) informative
     for prediction yet invalid as an unnormalized p(z|x) EKF likelihood.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RFROOT=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
R2=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
B0=ROOT/"research/R5_FULLRF_B0_GATES_20261015"
PHY=ROOT/"research/PHYSICS_RS_STAGED_20261015/code"
MANIFEST=ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R0_R=0.0068578637
R0_S=0.0081
B_OLD=-0.5315983906250129
PINNED={
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py":"24b7b0103a232662afaf5b1b79bfb542aa7123db",
 "research/PHYSICS_RS_STAGED_20261015/code/features.py":"c556da153739aaf99d2558c84c1a515c3da41a97",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
}
CASES=7
FOLDS=("R2","R4","R5")
SIMPLE=("log_fp_power","early8","delay_rms_ns","eta_fp_win80",
        "mount_feature","anchor_x_feature")
G4=SIMPLE+("detector_s_span","detector_delay_span_ns")
NQ=G4+("range_m","s_fp")
MODELS={
 "R0":None,
 "GLOBAL_DIAG":(),
 "GLOBAL_JOINT":(),
 "POWER_BIN_JOINT":("log_fp_power",),
 "SIMPLE_DIAG":SIMPLE,
 "SIMPLE_JOINT":SIMPLE,
 "SIMPLE_G4":G4,
 "SIMPLE_WITH_RANGE_S_SELF":NQ,
 "G5_RESEARCH_ONLY":None,
}
TWO_PI=2*math.pi

def hash_file(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def gitblob(path):
 f=Path(path)
 h=hashlib.sha1(b"blob "+str(f.stat().st_size).encode()+b"\0")
 with f.open("rb") as s:
  for c in iter(lambda:s.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def save(path,obj):
 Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def preflight(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];src={};assets={}
 if os.environ.get("GITHUB_ACTIONS")!="true":errors.append("REQUIRES_CLOUD_ACTIONS")
 try:
  rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
  if rev!=os.environ.get("GITHUB_SHA"):errors.append("NOT_EXACT_GIT_SHA")
 except Exception as ex:
  rev=None;errors.append("GIT_REV_ERROR:"+str(ex))
 for p,expected in PINNED.items():
  f=ROOT/p
  if not f.is_file():errors.append("FROZEN_SOURCE_MISSING:"+p);continue
  sha=gitblob(f);src[p]=sha
  if sha!=expected:errors.append("FROZEN_SOURCE_CHANGED:"+p)
 try:
  m=json.loads(MANIFEST.read_text())
  known={x["path"]:x for x in m["assets"]}
  needed=[v for case in m["cases"] for v in (case["full_path"],case["los_path"],case["samples_path"])]
  needed.append("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy")
  for p in needed:
   f=ROOT/p
   if not f.is_file():errors.append("FROZEN_H_MISSING:"+p);continue
   sha=hash_file(f);assets[p]=sha
   if p not in known or sha!=known[p]["sha256"] or f.stat().st_size!=known[p]["bytes"]:
    errors.append("FROZEN_H_HASH_DIFF:"+p)
 except Exception as ex:errors.append("RAW_ASSET_AUDIT:"+repr(ex))
 try:ast.parse((HERE/"n4b_rf_errors.py").read_text(encoding="utf-8"))
 except Exception as ex:errors.append("SCRIPT_AST_FAILURE:"+repr(ex))
 wf=ROOT/".github/workflows/r5-n4b-rf-errors.yml"
 if not wf.exists():errors.append("AUDIT_FIRST_WORKFLOW_MISSING")
 else:
  text=wf.read_text()
  toks=("n4b_rf_errors.py --phase pre","n4b_rf_errors.py --phase test",
        "n4b_rf_errors.py --phase run","actions: read","if: always()")
  if any(t not in text for t in toks):errors.append("WORKFLOW_REQUIRED_TOKEN_MISSING")
  elif not(text.index(toks[0])<text.index(toks[1])<text.index(toks[2])):
   errors.append("WORKFLOW_NOT_AUDIT_FIRST")
 r={"stage":"N4-B","decision":"GO" if not errors else "HOLD","source_sha":rev,
    "pinned_git_blobs":src,"asset_verified_count":len(assets),
    "raw_original_archive_sha256":RF_SHA,
    "R0":{"range_variance_m2":R0_R,"s_variance":R0_S,"r_s_corr":0},
    "errors":errors,"scientific_PASS":False}
 save(out/"PRE_AUDIT.json",r)
 print("N4B_PRE "+json.dumps({"decision":r["decision"],"assets":len(assets),
                            "errors":errors}),flush=True)
 return 0 if not errors else 2

def setup():
 import numpy as np
 import pandas as pd
 sys.path.insert(0,str(B0))
 sys.path.insert(0,str(PHY))
 sys.path.insert(0,str(R2))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 return np,pd

def row_cov(np,Y,w):
 W=np.asarray(w,float);W=W/W.sum()
 mu=np.einsum("n,ni->i",W,Y)
 e=Y-mu
 C=np.einsum("n,ni,nj->ij",W,e,e)
 return mu,C
def fix_cov(np,C,correlated):
 C=np.asarray(C,float).copy()
 C=(C+C.T)*.5
 C[0,0]=max(C[0,0],R0_R*.10)
 C[1,1]=max(C[1,1],R0_S*.10)
 if not correlated:C[0,1]=C[1,0]=0
 else:
  rho=np.clip(C[0,1]/np.sqrt(C[0,0]*C[1,1]),-.90,.90)
  C[0,1]=C[1,0]=rho*np.sqrt(C[0,0]*C[1,1])
 if np.min(np.linalg.eigvalsh(C))<=0:raise RuntimeError("N4B_COV_NONSPD")
 return C
def add_nll(np,e,mu,cov):
 dif=e-mu
 # Covariance shape N x 2 x 2
 inv=np.linalg.solve(cov,dif[...,None])[...,0]
 det=np.linalg.slogdet(cov)
 if not np.all(det[0]>0):raise RuntimeError("NONPD_COVARIANCE_MODEL")
 d2=np.einsum("ni,ni->n",dif,inv)
 nll=math.log(2*math.pi)+.5*(det[1]+d2)
 if not np.isfinite(nll).all():raise RuntimeError("NONFINITE_HOLDOUT_NLL")
 return nll,d2
def fit_model(np,train,test,w,name,feature_groups):
 from sklearn.preprocessing import StandardScaler
 from sklearn.linear_model import Ridge
 n=len(test);Y=train[["e_r","e_s"]].to_numpy(float)
 if name=="R0":
  mu=np.zeros((n,2),float)
  cov=np.repeat(np.diag([R0_R,R0_S])[None,:,:],n,axis=0)
  return mu,cov,{"features":[], "bins":0,"learned_mean":False,
     "cond_on_same_measurement":False,"mean_0":0.,"mean_1":0.}
 feats=(feature_groups["G5"]+["mount_feature","anchor_x_feature"]
            if name=="G5_RESEARCH_ONLY" else MODELS[name])
 if feats is None:raise RuntimeError("MODEL_NOT_REGISTERED")
 if feats:
  Xtrain=train[list(feats)].to_numpy(float)
  Xtest=test[list(feats)].to_numpy(float)
  scaler=StandardScaler()
  A=scaler.fit_transform(Xtrain)
  B=scaler.transform(Xtest)
  fitted=Ridge(alpha=30.,fit_intercept=True)
  fitted.fit(A,Y,sample_weight=w)
  mtrain=fitted.predict(A);mtest=fitted.predict(B)
 else:
  mglobal=np.average(Y,axis=0,weights=w)
  mtrain=np.repeat(mglobal[None,:],len(train),axis=0)
  mtest=np.repeat(mglobal[None,:],n,axis=0)
 residual=Y-mtrain
 global_residual_mu,global_cov=row_cov(np,residual,w)
 correlated=name not in ("GLOBAL_DIAG","SIMPLE_DIAG")
 global_cov=fix_cov(np,global_cov,correlated)
 if name in ("GLOBAL_DIAG","GLOBAL_JOINT"):
  return mtest+global_residual_mu, np.repeat(global_cov[None,:,:],n,axis=0),{
    "features":[],"bins":1,"learned_mean":True,
    "cond_on_same_measurement":False,
    "mean_0":float(np.mean(mtest[:,0])),"mean_1":float(np.mean(mtest[:,1])),
    "global_cross_cov":float(global_cov[0,1])}
 # Covariance stratification: train tertiles of first-path power (simple)
 # or first-path threshold sensitivity (G4/G5). Training-only cutpoints.
 binfield=("detector_s_span" if name in ("SIMPLE_G4","G5_RESEARCH_ONLY",
      "SIMPLE_WITH_RANGE_S_SELF") else "log_fp_power")
 btrain=train[binfield].to_numpy(float)
 btest=test[binfield].to_numpy(float)
 cuts=np.unique(np.quantile(btrain,[1/3,2/3]))
 idx_train=np.searchsorted(cuts,btrain,side="right")
 idx_test=np.searchsorted(cuts,btest,side="right")
 covs=np.zeros((n,2,2),float);means=mtest.copy()
 stats=[]
 for b in range(len(cuts)+1):
  tr=idx_train==b;te=idx_test==b
  if not np.any(te):continue
  if int(tr.sum())<15:raise RuntimeError("BAD_STRATA_SIZE:"+name+":"+str(b))
  raw_mu,raw_cov=row_cov(np,residual[tr],w[tr])
  # Conservative shrinkage to global covariance and zero bin-mean error,
  # preventing tiny bins from declaring unjustified high confidence.
  effective_w=(w[tr].sum()**2)/(w[tr]**2).sum()
  alpha=effective_w/(effective_w+100.)
  bin_mean=alpha*raw_mu+(1-alpha)*global_residual_mu
  C=alpha*raw_cov+(1-alpha)*global_cov
  C=fix_cov(np,C,correlated)
  means[te]+=bin_mean
  covs[te]=C
  stats.append({"bin":b,"n_train":int(tr.sum()),"n_test":int(te.sum()),
                "rho":float(C[0,1]/math.sqrt(C[0,0]*C[1,1])),
                "Vr":float(C[0,0]),"Vs":float(C[1,1]),
                "mu_r_residual":float(bin_mean[0]),
                "mu_s_residual":float(bin_mean[1])})
 if not np.all(np.linalg.eigvalsh(covs)>0):raise RuntimeError("BIN_COV_ASSIGNMENT_INVALID:"+name)
 return means,covs,{"features":list(feats),"bins":stats,
    "bin_feature":binfield,"cutpoints_train":cuts.tolist(),
    "cond_on_same_measurement":bool("range_m" in feats or "s_fp" in feats
            or "abs_s_fp" in feats),
    "research_only":name=="G5_RESEARCH_ONLY"}

def independent_n4b_test():
 np,pd=setup()
 from features import GROUPS
 rng=np.random.default_rng(24)
 A=rng.normal(size=(128,2))
 train=pd.DataFrame({"e_r":.45+A[:,0]*.14,
   "e_s":-.10+.6*A[:,0]*.12+A[:,1]*.05})
 for col in set(SIMPLE+G4+NQ+tuple(GROUPS["G5"])):
  if col not in train:train[col]=rng.normal(size=len(train))
 test=train.iloc[:12].copy()
 for model in MODELS:
  mu,cov,info=fit_model(np,train,test,np.ones(len(train)),model,GROUPS)
  nll,d2=add_nll(np,test[["e_r","e_s"]].to_numpy(float),mu,cov)
  assert np.isfinite(nll).all() and np.min(np.linalg.eigvalsh(cov))>0
 mean,center=row_cov(np,train[["e_r","e_s"]].to_numpy(float),np.ones(len(train)))
 assert abs(mean[0]-.45)<.1
 assert abs(center[0,1])>1e-6
 # Site persistence can be produced by a deterministic ramp; don't equate ACF to physics.
 seq=np.arange(100,dtype=float)
 assert np.corrcoef(seq[:-1],seq[1:])[0,1]>.99
 print("N4B_UNIT_PASS "+json.dumps({"models":len(MODELS),
    "checks":["R0","MODEL_POSITIVE_DEFINITE","CENTERED_COVARIANCE",
              "SIGNED_MEANS","CONDITIONAL_NLL","TEMPORAL_CONFOUNDING"]}),flush=True)
 return 0

def create_dataset(np,pd,manifest):
 from r5_b0_hard_soft import prepare_features
 from features import extract
 all_data,lut=prepare_features(np,pd,manifest)
 meta={c["id"]:c for c in manifest["cases"]}
 all_data["mount_feature"]=all_data["case"].map(lambda c:float(meta[c]["mount_deg"])/45.)
 all_data["anchor_x_feature"]=all_data["case"].map(lambda c:float(meta[c]["anchor"][0])/10.)
 # Primary training/evaluation target is residual against THE FROZEN EKF4 LoS
 # reference, at GT pose in offline reference only.
 all_data["e_s"]=all_data["e_total_eval"]
 all_data["range_true_model"]=0.
 for c in manifest["cases"]:
  sel=all_data["case"]==c["id"]
  anchor=c["anchor"];z=c["robot_z_m"]
  frame=all_data.loc[sel]
  pred=np.sqrt((frame.x_eval.to_numpy(float)-anchor[0])**2+
        (frame.y_eval.to_numpy(float)-anchor[1])**2+
        (z-anchor[2])**2)+B_OLD
  all_data.loc[sel,"range_true_model"]=pred
 all_data["e_r"]=all_data["range_m"]-all_data["range_true_model"]
 # Audited FP tap/strongest channel classification for switch diagnostics,
 # identical 4N Hann observer. No GT fed into this extraction.
 freqs=np.load(RFROOT/"freqs_hz.npy",allow_pickle=False)
 nf=len(freqs)
 dt=1/(4*nf*(freqs[1]-freqs[0]))
 extra=[]
 for case in manifest["cases"]:
  samples=json.loads((ROOT/case["samples_path"]).read_text())
  ids=np.array([v["pose_id"] for v in samples],dtype=int)
  for channel,key in (("full","full_path"),("los","los_path")):
   h=np.load(ROOT/case[key],mmap_mode="r",allow_pickle=False)
   for start in range(0,len(h),80):
    stop=min(start+80,len(h))
    part=extract(h[start:stop,:,:,0],freqs)
    extra.append(pd.DataFrame({"case":case["id"],"channel":channel,
        "pose_id":ids[start:stop],"fp_tap":part["tap"],
        "strong_port":part["branch"]}))
 fp=pd.concat(extra,ignore_index=True)
 if fp.duplicated(["case","channel","pose_id"]).any():raise RuntimeError("N4B_FP_DUP")
 all_data=all_data.merge(fp,on=["case","channel","pose_id"],validate="one_to_one")
 if len(all_data)!=19038:raise RuntimeError("FULL_PAIRS_COUNT_WRONG")
 expected=all_data["fp_tap"].to_numpy(float)*dt*299792458.
 if np.max(np.abs(expected-all_data["range_m"].to_numpy(float)))>1e-10:
  raise RuntimeError("PHYSICAL_FIRST_PATH_INDEX_INVALID")
 if not np.all(np.isfinite(all_data[["e_r","e_s"]].to_numpy(float))):
  raise RuntimeError("NONFINITE_RF_RESIDUAL")
 return all_data

def checked_zip(path):
 if hash_file(path)!=RF_SHA:raise RuntimeError("ORIGINAL_RF_ARCHIVE_CHANGED")
 archive=zipfile.ZipFile(path)
 if archive.testzip():raise RuntimeError("ORIGINAL_RF_ARCHIVE_CRC_FAILED")
 return archive

def original_14_parity(np,df,archive):
 indexed=df.set_index(["case","channel","pose_id"],verify_integrity=True)
 meta=json.loads(archive.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
 scores=[]
 for item in meta["per_case"]:
  raw=archive.read("P2_OUT/"+item["trace_file"])
  if hashlib.sha256(raw).hexdigest()!=item["trace_sha256"]:
   raise RuntimeError("ORIGINAL_TRACE_SOURCE_SHA_BAD")
  with np.load(io.BytesIO(raw),allow_pickle=False) as z:
   keys=[(item["case"],item["channel"],int(i)) for i in z["pose_id"]]
   frame=indexed.loc[keys]
   dx=float(np.max(np.abs(z["z_r_m"]-frame.range_m.to_numpy(float))))
   ds=float(np.max(np.abs(z["z_s"]-frame.s_fp.to_numpy(float))))
  if max(dx,ds)>1e-12:raise RuntimeError("ARCHIVED_RANGE_S_PARITY_FAIL:"+str((item["case"],item["channel"],dx,ds)))
  scores.append({"case":item["case"],"channel":item["channel"],
    "rows":len(keys),"r_max_abs_error":dx,"s_max_abs_error":ds})
 if len(scores)!=14 or sum(x["rows"] for x in scores)!=14502:
  raise RuntimeError("ORIGINAL_RF_COUNT_BAD")
 return scores

def feature_splits(np,df):
 # Site-disjoint at identical x,y, but routes share one corridor.
 from scipy.spatial import cKDTree
 xy=df[["x_eval","y_eval"]].to_numpy(float)
 for held in FOLDS:
  test=df["route"].to_numpy()==held
  train=(~test)&(cKDTree(xy[test]).query(xy,k=1)[0]>1e-4)
  if train.sum()<100 or test.sum()<100:raise RuntimeError("EMPTY_ROUTE_SPLIT")
  if held in set(df.loc[train,"route"]):raise RuntimeError("TARGET_LEAK")
  yield held,train,test

def site_weights(np,pd,df):
 keys=list(zip(df.x_eval.round(5),df.y_eval.round(5)))
 count=pd.Series(keys).value_counts()
 w=np.array([1/count[k] for k in keys],float)
 return w/w.mean()

def corr(np,x,y):
 a=np.asarray(x,float);b=np.asarray(y,float)
 if len(a)<3 or np.std(a)<1e-12 or np.std(b)<1e-12:return None
 return float(np.corrcoef(a,b)[0,1])
def group_stats(np,case,channel,frame):
 E=frame[["e_r","e_s"]].to_numpy(float)
 mu,C=row_cov(np,E,np.ones(len(E)))
 rho=corr(np,E[:,0],E[:,1])
 def sd(x):return float(np.std(x))
 return {"case":case,"channel":channel,"count":int(len(E)),
  "mu_r_m":float(mu[0]),"mu_s":float(mu[1]),
  "Vr_m2":float(C[0,0]),"Vs":float(C[1,1]),
  "C_rs_m":float(C[0,1]),"rho_rs":rho,
  "raw_second_moment_r":float(np.mean(E[:,0]**2)),
  "raw_second_moment_s":float(np.mean(E[:,1]**2)),
  "mu_r_over_noise_sigma":float(mu[0]/math.sqrt(R0_R)),
  "mu_s_over_noise_sigma":float(mu[1]/math.sqrt(R0_S))}

def temporal_diagnostics(np,pd,full,pred_oof):
 table=[]
 for case,g in full.groupby("case",sort=True):
  g=g.sort_values("pose_id").copy()
  if len(g)!=g.pose_id.nunique():raise RuntimeError("DUP_TIMELINE")
  dx=np.hypot(np.diff(g.x_eval.to_numpy(float)),np.diff(g.y_eval.to_numpy(float)))
  stationary=dx<1e-4
  s=g.e_s.to_numpy(float);r=g.e_r.to_numpy(float)
  tap=np.round(g.fp_tap.to_numpy(float)).astype(int)
  branch=np.round(g.strong_port.to_numpy(float)).astype(int)
  for segment,valid in (("all",np.ones(len(g)-1,bool)),
                         ("fixed_xy_yaw",stationary),
                         ("moving",~stationary),
                         ("same_fp_tap",(np.diff(tap)==0)),
                         ("fp_tap_changed",(np.diff(tap)!=0)),
                         ("rx_strong_port_changed",(np.diff(branch)!=0))):
   if not np.any(valid):continue
   residual=pred_oof.reindex(pd.MultiIndex.from_frame(g[["case","pose_id"]]))
   if residual.isna().any().any():raise RuntimeError("OOF_RESIDUAL_ALIGNMENT_FAIL")
   after_r=r-residual["mu_r"].to_numpy(float)
   after_s=s-residual["mu_s"].to_numpy(float)
   for kind,a,b in (("raw_r",r[:-1],r[1:]),("raw_s",s[:-1],s[1:]),
                    ("centered_model_r",after_r[:-1],after_r[1:]),
                    ("centered_model_s",after_s[:-1],after_s[1:])):
    table.append({"case":case,"route":g.route.iloc[0],
      "mount_deg":int(g.mount_feature.iloc[0]*45),
      "segment_type":segment,"field":kind,
      "n_pairs":int(valid.sum()),"lag1_corr":corr(np,a[valid],b[valid]),
      "mean_abs_first":float(np.mean(np.abs(a[valid]))),
      "mean_abs_second":float(np.mean(np.abs(b[valid])))})
 return table

def run(out,pre,rf_archive):
 np,pd=setup()
 from features import GROUPS
 from sklearn.metrics import r2_score
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 prev=json.loads(Path(pre).read_text())
 if prev["decision"]!="GO" or prev["source_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("SOURCE_AUDIT_REQUIRED")
 manifest=json.loads(MANIFEST.read_text())
 all_df=create_dataset(np,pd,manifest)
 with checked_zip(rf_archive) as a:
  parity=original_14_parity(np,all_df,a)
 full=all_df[all_df.channel=="full"].copy()
 if len(full)!=9519 or full.duplicated(["case","pose_id"]).any():
  raise RuntimeError("N4B_FULL_POSE_PAIR_COUNT")
 source_stats=[group_stats(np,str(k[0]),str(k[1]),g)
               for k,g in all_df.groupby(["case","channel"],sort=True)]
 raw_pair=all_df.pivot(index=["case","pose_id"],columns="channel",values=["e_r","e_s"])
 paired=[]
 for case in [c["id"] for c in manifest["cases"]]:
  sub=raw_pair.loc[case]
  dr=sub[("e_r","full")]-sub[("e_r","los")]
  ds=sub[("e_s","full")]-sub[("e_s","los")]
  paired.append({"case":case,"n":len(sub),
    "MP_range_mean_m":float(dr.mean()),"MP_s_mean":float(ds.mean()),
    "MP_range_rmse_m":float(np.sqrt(np.mean(dr**2))),
    "MP_s_rmse":float(np.sqrt(np.mean(ds**2))),
    "MP_range_s_corr":corr(np,dr,ds)})
 models=list(MODELS)
 scores=[];predrows=[];splits=[];model_meta=[]
 for held,tr,te in feature_splits(np,full):
  train=full.loc[tr].copy();test=full.loc[te].copy()
  w=site_weights(np,pd,train)
  X_test=test[["e_r","e_s"]].to_numpy(float)
  refmean,refcov=row_cov(np,train[["e_r","e_s"]].to_numpy(float),w)
  splits.append({"held_route":held,"n_train":len(train),"n_test":len(test),
    "train_routes":sorted(train.route.unique().tolist()),
    "train_mount_angles":sorted(train.mount_feature.unique().tolist()),
    "test_mount_angles":sorted(test.mount_feature.unique().tolist()),
    "all_heldout_science":"same corridor; mount45 absent when training heldout R2"})
  for name in models:
   mu,C,meta=fit_model(np,train,test,w,name,GROUPS)
   likelihood,chi2=add_nll(np,X_test,mu,C)
   data=test[["case","route","pose_id","x_eval","y_eval","mount_feature",
     "anchor_x_feature","range_m","s_fp","log_fp_power","fp_tap","strong_port",
     "e_r","e_s"]].reset_index(drop=True).copy()
   data["model"]=name
   data["mu_r"]=mu[:,0];data["mu_s"]=mu[:,1]
   data["Vr"]=C[:,0,0];data["Vs"]=C[:,1,1];data["C_rs"]=C[:,0,1]
   data["rho_rs"]=C[:,0,1]/np.sqrt(C[:,0,0]*C[:,1,1])
   data["nll"]=likelihood;data["chi2"]=chi2
   predrows.append(data)
   model_meta.append({"held_route":held,"model":name,**meta})
   for case,positions in data.groupby("case").indices.items():
    ix=np.asarray(positions,int)
    r=test.iloc[ix] if False else data.iloc[ix]
    scores.append({
       "held_route":held,"case":str(case),"model":name,
       "n":len(ix),"nll_mean":float(likelihood[ix].mean()),
       "chi2_mean":float(chi2[ix].mean()),
       "chi2_95coverage":float(np.mean(chi2[ix]<=5.991464547107979)),
       "r_centered_error_mean":float(np.mean((X_test-mu)[ix,0])),
       "s_centered_error_mean":float(np.mean((X_test-mu)[ix,1])),
       "r_normalized_square_mean":float(np.mean((X_test-mu)[ix,0]**2/C[ix,0,0])),
       "s_normalized_square_mean":float(np.mean((X_test-mu)[ix,1]**2/C[ix,1,1])),
       "r_95coverage":float(np.mean((X_test-mu)[ix,0]**2<=3.841458820694124*C[ix,0,0])),
       "s_95coverage":float(np.mean((X_test-mu)[ix,1]**2<=3.841458820694124*C[ix,1,1])),
       "rho_mean":float(np.mean(C[ix,0,1]/np.sqrt(C[ix,0,0]*C[ix,1,1]))),
       "r_mean_fit":float(mu[ix,0].mean()),"s_mean_fit":float(mu[ix,1].mean()),
       "r_var_fit":float(C[ix,0,0].mean()),"s_var_fit":float(C[ix,1,1].mean()),
    })
   print("N4B_FOLD_MODEL "+json.dumps({"held":held,"model":name,
      "n":len(test),"nll":float(likelihood.mean()),
      "coverage":float(np.mean(chi2<=5.991464547107979))}),flush=True)
 prediction=pd.concat(predrows,ignore_index=True)
 if len(prediction)!=len(full)*len(models):raise RuntimeError("OOF_PRED_COUNT")
 prediction.to_csv(out/"N4B_OOF_PREDICTIONS.csv.gz",index=False,compression="gzip")
 scores_frame=pd.DataFrame(scores)
 scores_frame.to_csv(out/"N4B_HELDOUT_LIKELIHOOD.csv",index=False)
 pd.DataFrame(source_stats).to_csv(out/"N4B_EMPIRICAL_JOINT_RS.csv",index=False)
 pd.DataFrame(paired).to_csv(out/"N4B_FULL_MINUS_NATIVE_LOS.csv",index=False)
 pd.DataFrame(parity).to_csv(out/"N4B_RF_OBSERVER_PARITY.csv",index=False)
 pd.DataFrame(model_meta).to_json(out/"N4B_TRAIN_ONLY_MODEL_CONFIG.json",orient="records",indent=2)
 pd.DataFrame(splits).to_json(out/"N4B_SPLITS.json",orient="records",indent=2)
 overall=[]
 for model,g in prediction.groupby("model"):
  overall.append({"model":model,"n":len(g),
    "mean_joint_nll":float(g.nll.mean()),
    "chi2_mean":float(g.chi2.mean()),
    "joint_95coverage":float(np.mean(g.chi2.to_numpy(float)<=5.991464547107979)),
    "mean_pred_mu_r":float(g.mu_r.mean()),"mean_pred_mu_s":float(g.mu_s.mean()),
    "mean_pred_Vr":float(g.Vr.mean()),"mean_pred_Vs":float(g.Vs.mean()),
    "mean_pred_Crs":float(g.C_rs.mean())})
 # Quantify model calibration and site persistence on OOF SIMPLE_JOINT residuals.
 simple=prediction[prediction.model=="SIMPLE_JOINT"].copy()
 simple["site_x"]=(simple.x_eval//1.5).astype(int)
 simple["site_y"]=(simple.y_eval//1.5).astype(int)
 simple["site_id"]=simple.case+":"+simple.site_x.astype(str)+":"+simple.site_y.astype(str)
 simple["res_r"]=simple.e_r-simple.mu_r
 simple["res_s"]=simple.e_s-simple.mu_s
 site_agg=simple.groupby("site_id",sort=True).agg(
    case=("case","first"),n=("case","size"),
    mean_r=("res_r","mean"),mean_s=("res_s","mean"),
    sd_r=("res_r","std"),sd_s=("res_s","std"))
 min_samples=5
 sites=site_agg[site_agg.n>=min_samples]
 if len(sites)<15:raise RuntimeError("INSUFFICIENT_SPATIAL_BLOCKS")
 simple["res_r_site_oracle_diagnostic_only"]=simple.res_r-simple.site_id.map(site_agg.mean_r)
 simple["res_s_site_oracle_diagnostic_only"]=simple.res_s-simple.site_id.map(site_agg.mean_s)
 total_var=[float(np.var(simple[k])) for k in ("res_r","res_s")]
 within_var=[float(np.var(simple[k])) for k in
    ("res_r_site_oracle_diagnostic_only","res_s_site_oracle_diagnostic_only")]
 site_receipt={"n_site_blocks_total":len(site_agg),
   "n_site_blocks_ge5":len(sites),"min_samples":min_samples,
   "site_block_definition":"case + floor(x/1.5m) + floor(y/1.5m) offline GT",
   "total_oof_residual_variances":total_var,
   "within_site_centered_variances_oracle":within_var,
   "apparent_spatial_effect_variance_fraction":
    [float(max(0,1-b/max(a,1e-300))) for a,b in zip(total_var,within_var)],
   "independence_note":"Site mean uses oracle held-out residuals; cannot be online correction. Same corridor, same scene, varying yaw within site."}
 site_agg.reset_index().to_csv(out/"N4B_SITE_BLOCK_MEANS_ORACLE.csv",index=False)
 fulltest=simple.set_index(["case","pose_id"])[["mu_r","mu_s"]]
 acf=temporal_diagnostics(np,pd,full,fulltest)
 pd.DataFrame(acf).to_csv(out/"N4B_TEMPORAL_ACF_STRATA.csv",index=False)
 temporal_summary=[]
 for field in ("raw_r","raw_s","centered_model_r","centered_model_s"):
  for segment in ("all","moving","fixed_xy_yaw","fp_tap_changed","same_fp_tap"):
   q=[r for r in acf if r["field"]==field and r["segment_type"]==segment and r["lag1_corr"] is not None]
   if q:
    temporal_summary.append({"field":field,"segment":segment,
      "n_pairs":sum(r["n_pairs"] for r in q),
      "weighted_lag1_corr":sum(r["lag1_corr"]*r["n_pairs"] for r in q)/sum(r["n_pairs"] for r in q),
      "n_case_strata":len(q)})
 # Paired spatial-block resampling of conditional likelihood improvements.
 samples=prediction[["case","route","x_eval","y_eval","pose_id","model","nll"]].copy()
 samples["block"]=(samples.case+":"+np.floor(samples.x_eval/1.5).astype(int).astype(str)+":"+
  np.floor(samples.y_eval/1.5).astype(int).astype(str))
 base=samples[samples.model=="R0"][["case","pose_id","nll","block"]].rename(columns={"nll":"nll_R0"})
 global_model=samples[samples.model=="GLOBAL_JOINT"][["case","pose_id","nll"]].rename(columns={"nll":"nll_GLOBAL"})
 simple_group=samples.merge(base,on=["case","pose_id"],how="left",validate="many_to_one",
                            suffixes=("","_base"))
 simple_group=simple_group.merge(global_model,on=["case","pose_id"],how="left",validate="many_to_one")
 if simple_group[["nll_R0","nll_GLOBAL"]].isna().any().any():
  raise RuntimeError("OOF_PAIRED_NLL_INCOMPLETE")
 boot=[]
 rng=np.random.default_rng(20261015)
 for model in ("GLOBAL_JOINT","POWER_BIN_JOINT","SIMPLE_DIAG","SIMPLE_JOINT",
               "SIMPLE_G4","G5_RESEARCH_ONLY","SIMPLE_WITH_RANGE_S_SELF"):
  sub=simple_group[simple_group.model==model].copy()
  perblock=sub.groupby("block").agg(
    nd=("nll","size"),model_total=("nll","sum"),
    R0_total=("nll_R0","sum"),GLOBAL_total=("nll_GLOBAL","sum"))
  weights=perblock.nd.to_numpy(float)
  a=perblock.model_total.to_numpy(float)
  b=perblock.R0_total.to_numpy(float)
  c=perblock.GLOBAL_total.to_numpy(float)
  ci=[];ci_g=[]
  for i in range(300):
   ids=rng.integers(0,len(perblock),size=len(perblock))
   ci.append(float((a[ids]-b[ids]).sum()/weights[ids].sum()))
   ci_g.append(float((a[ids]-c[ids]).sum()/weights[ids].sum()))
  boot.append({"model":model,"blocks":len(perblock),
    "mean_nll_minus_R0":float((a-b).sum()/weights.sum()),
    "within_corridor_block_bootstrap95_vs_R0":np.quantile(ci,[.025,.975]).tolist(),
    "mean_nll_minus_GLOBAL_JOINT":float((a-c).sum()/weights.sum()),
    "within_corridor_block_bootstrap95_vs_GLOBAL_JOINT":np.quantile(ci_g,[.025,.975]).tolist()})
 pd.DataFrame(boot).to_csv(out/"N4B_HELDOUT_NLL_BLOCK_CI.csv",index=False)
 summary={
   "schema":"N4B_RF_RESIDUAL_MEAN_COV_TEMPORAL_HELDOUT_V1",
   "status":"N4B_AUDITED_RESIDUAL_AND_LIKELIHOOD_COMPLETE",
   "source_sha":os.getenv("GITHUB_SHA"),
   "original_RF_archive_sha256":RF_SHA,
   "n_full_observations":len(full),
   "n_channels":14,"original_archive_observations":sum(r["rows"] for r in parity),
   "R0":{"mu_r":0,"mu_s":0,"Vr":R0_R,"Vs":R0_S,"Crs":0},
   "splits":splits,
   "heldout_aggregate_likelihood":overall,
   "heldout_case_likelihood":scores,
   "empirical_full_and_los_residual_stats":source_stats,
   "full_minus_native_los":paired,
   "site_persistence_test":site_receipt,
   "lag1_observed_time_strata":temporal_summary,
   "NLL_block_bootstrap":boot,
   "scientific_PASS":False,
   "unverified":[
    "This is a conditional residual density p(e_r,e_s|packet features), not a valid normalized sensor likelihood p(z|x) for EKF",
    "Same-packet range/s predictors and complex frequency G5 features are research-only exploratory",
    "Native noise-free H has no independent RF sensor-noise replicates",
    "Spatial block persistence cannot distinguish multipath bias, antenna geometry, FP detector systematic response and angular sweep",
    "Temporal lag-1 correlation along deterministic moving/rotating path is not stochastic autocorrelation at identical conditions",
    "Cross-validated likelihood performance is within one corridor, not independent-scene validation",
    "R0 independent Gaussian measurement model is a nominal filter assumption, not measured thermal noise floor",
    "No new N4-C covariance has been applied to EKF or qualified by NEES in this task"]
 }
 save(out/"N4B_FINAL.json",summary)
 print("N4B_FINAL "+json.dumps({"status":summary["status"],
   "n_full":len(full),"n_original":summary["original_archive_observations"],
   "overall":overall,"empirical_paired":paired,
   "site_test":site_receipt,"lag1":temporal_summary,
   "bootstrap":boot},ensure_ascii=False),flush=True)
 return 0

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","test","run"),required=True)
 p.add_argument("--out")
 p.add_argument("--audit")
 p.add_argument("--raw")
 a=p.parse_args()
 if a.phase=="pre":return preflight(a.out)
 if a.phase=="test":return independent_n4b_test()
 if not a.out or not a.audit or not a.raw:raise RuntimeError("RUN_ARGUMENTS_MISSING")
 return run(a.out,a.audit,a.raw)

if __name__=="__main__":raise SystemExit(main())
