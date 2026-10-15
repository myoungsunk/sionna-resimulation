"""N3 incremental physical features audit and route-heldout comparisons.

Compares original Power/Range/Dual-LP/CIR source metrics and PHY G0-G5
with common fixed learners, folds, and offline-only Full/LoS error labels.
No Heading-ground-truth risk predictor or EKF policy is trained here.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PHY=ROOT/"research/PHYSICS_RS_STAGED_20261015/code"
B0=ROOT/"research/R5_FULLRF_B0_GATES_20261015"
N0_SHA="aade786b83357086c9e645fa9b87467a869289aa93040e3b48410f44af2d08fb"
RF_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
PINNED={
 "research/PHYSICS_RS_STAGED_20261015/code/features.py":"c556da153739aaf99d2558c84c1a515c3da41a97",
 "research/PHYSICS_RS_STAGED_20261015/code/stage_b.py":"b56d9e1459f2265fea83cd87cb411cd1cc4f3f9d",
 "research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py":"24b7b0103a232662afaf5b1b79bfb542aa7123db",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9"}
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob_sha(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\x00")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 failures=[];sources={}
 if os.getenv("GITHUB_ACTIONS")!="true":failures.append("GITHUB_ONLY")
 commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if commit!=os.getenv("GITHUB_SHA"):failures.append("NOT_EXACT_GIT_SHA")
 for key,val in PINNED.items():
  f=ROOT/key
  if not f.is_file():failures.append("MISSING_SOURCE:"+key)
  else:
   actual=blob_sha(f);sources[key]=actual
   if actual!=val:failures.append("FROZEN_SOURCE_CHANGED:"+key)
 try:
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  original={q["path"]:q for q in manifest["assets"]}
  todo=[v for c in manifest["cases"] for v in (c["full_path"],c["los_path"],c["samples_path"])]
  todo.append("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy")
  for rel in todo:
   path=ROOT/rel
   if not path.is_file():failures.append("MISSING_RAW_H:"+rel)
   elif rel not in original or sha_file(path)!=original[rel]["sha256"]:
    failures.append("RAW_H_MISMATCH:"+rel)
 except Exception as e:failures.append("RAW_AUDIT_ERROR:"+str(e))
 try:ast.parse((HERE/"n3_feature_incremental.py").read_text())
 except Exception as e:failures.append("N3_SCRIPT_SYNTAX:"+str(e))
 wf=ROOT/".github/workflows/r5-n0n3-n3.yml"
 if not wf.is_file():failures.append("WORKFLOW_MISSING")
 else:
  w=wf.read_text()
  if not(0<=w.find("n3_feature_incremental.py --phase pre")<
         w.find("n3_feature_incremental.py --phase test")<
         w.find("n3_feature_incremental.py --phase run") and
         "if: always()" in w and "actions: read" in w):
   failures.append("AUDIT_FIRST_WORKFLOW_FAIL")
 receipt={"stage":"N3","decision":"GO" if not failures else "HOLD",
          "source_commit":commit,"verified_git_blobs":sources,
          "raw_assets_verified":len(todo) if "todo" in locals() else 0,
          "N0_SHA":N0_SHA,"RF_SHA":RF_SHA,"errors":failures,
          "scientific_PASS":False}
 save(out/"N3_PRE_AUDIT.json",receipt)
 print("N3_PRE "+json.dumps({"decision":receipt["decision"],"errors":failures}),flush=True)
 return 0 if not failures else 2
def readzip(path,digest):
 if sha_file(path)!=digest:raise RuntimeError("ARCHIVE_SHA_CHANGED")
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ARCHIVE_CRC_FAIL")
 return z
def member(z,name):
 names=[x for x in z.namelist() if x==name or x.endswith("/"+name)]
 if len(names)!=1:raise RuntimeError("DUPLICATE_MISSING_MEMBER:"+name)
 return names[0]
def verify_n0(p):
 with readzip(p,N0_SHA) as z:
  f=json.loads(z.read(member(z,"N0_RECONCILIATION.json")))
  if f["status"]!="N0_SCOPED_GO_POSE_NEES_NOT_NUMERICALLY_IDENTICAL":
   raise RuntimeError("UNSCOPED_N0")
def deps():
 import numpy as np
 import pandas as pd
 sys.path.insert(0,str(PHY))
 sys.path.insert(0,str(B0))
 sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 return np,pd
def legacy_extract(np,h,freq):
 """Measure old dual-port CIR shape/FP powers on same 30% shared leading tap."""
 h=np.asarray(h,dtype=np.complex128)
 nf=len(freq);nt=4*nf;n=len(h)
 window=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
 c=np.fft.ifft(h*window[None,:,None],n=nt,axis=1)*nf
 p=np.abs(c)**2
 ii=np.arange(n);strongport=np.abs(c).max(axis=1).argmax(axis=1)
 strong=np.abs(c)[ii,:,strongport];peak=strong.max(axis=1)
 fp=(strong>=.3*peak[:,None]).argmax(axis=1)
 if np.any(fp+80>nt):raise RuntimeError("FP_WINDOW_TRUNCATED")
 pp=p[ii,fp,:]
 ix=fp[:,None]+np.arange(80)
 pw=p[ii[:,None],ix,:]
 e80=pw.sum(axis=1);e16=pw[:,:16,:].sum(axis=1)
 q1=pw[:,:16,0]/np.maximum(e16[:,0,None],np.finfo(float).tiny)
 q2=pw[:,:16,1]/np.maximum(e16[:,1,None],np.finfo(float).tiny)
 mix=.5*(q1+q2)
 positive=np.finfo(float).tiny
 # Exact limiting behavior: zeros contribute 0 log 0.
 JSD=.5*np.sum(np.where(q1>0,q1*np.log(np.maximum(q1,positive)/np.maximum(mix,positive)),0),axis=1)+.5*np.sum(np.where(q2>0,q2*np.log(np.maximum(q2,positive)/np.maximum(mix,positive)),0),axis=1)
 eps=1e-300
 out={
  "old_logp1":np.log10(np.maximum(pp[:,0],eps)),
  "old_logp2":np.log10(np.maximum(pp[:,1],eps)),
  "old_fp_to_peak":(pp.sum(axis=1)/np.maximum(p.max(axis=1).sum(axis=1),eps)),
  "old_port1_early8":pw[:,:8,0].sum(axis=1)/np.maximum(e80[:,0],eps),
  "old_port2_early8":pw[:,:8,1].sum(axis=1)/np.maximum(e80[:,1],eps),
  "old_dual_jsd":np.maximum(JSD,0),
  "old_shape_l1":np.abs(q1-q2).sum(axis=1),
  "old_fp_tap":fp.astype(float),
  "old_strong_port":strongport.astype(float),
 }
 for name,val in out.items():
  if not np.isfinite(val).all():raise RuntimeError("LEGACY_FEATURE_NONFINITE:"+name)
 return out
def test():
 np,pd=deps()
 from features import extract
 from p3_rf_adapter4 import FrozenLut
 freq=np.linspace(6.2504e9,6.7496e9,257)
 h=np.ones((4,257,2),np.complex128);h[:,:,1]*=.6
 a=legacy_extract(np,h,freq)
 b=legacy_extract(np,h*100,freq)
 for k in ("old_fp_to_peak","old_port1_early8","old_port2_early8","old_dual_jsd","old_shape_l1"):
  np.testing.assert_allclose(a[k],b[k],rtol=0,atol=1e-12)
 for k in ("old_logp1","old_logp2"):
  np.testing.assert_allclose(b[k]-a[k],4.,rtol=0,atol=1e-12)
 c=extract(h,freq)
 assert np.isfinite(c["s_fp"]).all()
 print("N3_UNIT_PASS "+json.dumps({"legacy_reconstruction":True,"energy_scale_invariance":True}),flush=True)
 return 0
def build_data(np,pd,manifest):
 from r5_b0_hard_soft import prepare_features
 from features import GROUPS,FEATURES
 data,lut=prepare_features(np,pd,manifest)
 root=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
 f=np.load(root/"freqs_hz.npy",allow_pickle=False)
 chunks=[]
 for case in manifest["cases"]:
  for ch,key in (("los","los_path"),("full","full_path")):
   h=np.load(ROOT/case[key],mmap_mode="r",allow_pickle=False)
   for start in range(0,len(h),64):
    end=min(len(h),start+64)
    q=legacy_extract(np,h[start:end,:,:,0],f)
    q["case"]=np.repeat(case["id"],end-start)
    q["channel"]=np.repeat(ch,end-start)
    q["pose_id"]=np.array([v["pose_id"] for v in json.loads((ROOT/case["samples_path"]).read_text())])[start:end]
    chunks.append(pd.DataFrame(q))
 legacy=pd.concat(chunks,ignore_index=True)
 if legacy.duplicated(["case","channel","pose_id"]).any():raise RuntimeError("EXTRA_FEATURE_ID_DUPLICATE")
 data=data.merge(legacy,on=["case","channel","pose_id"],validate="one_to_one")
 if len(data)!=19038:raise RuntimeError("FULL_PHYSICS_PAIR_COUNT_WRONG")
 if not np.isfinite(data[FEATURES].to_numpy(float)).all():raise RuntimeError("ORIGINAL_PHY_NONFINITE")
 return data
def groups():
 from features import GROUPS
 old=["old_fp_to_peak","old_port1_early8","old_port2_early8","old_dual_jsd","old_shape_l1"]
 base=GROUPS["G0"]
 no_j=list(dict.fromkeys(GROUPS["G1"]+GROUPS["G2"]+GROUPS["G4"]))
 gr={
 "RANGE":["range_m"],
 "POWER_RANGE":["range_m","log_fp_power"],
 "G0_BASE":base,
 "G0_SIGNED":["range_m","log_fp_power","s_fp"],
 "PORT1_PORT2":["range_m","old_logp1","old_logp2"],
 "LEGACY_CIR":list(dict.fromkeys(base+old)),
 "PHY_G1":GROUPS["G1"],
 "PHY_G2":GROUPS["G2"],
 "PHY_G3_RESEARCH_ONLY":GROUPS["G3"],
 "PHY_G4":GROUPS["G4"],
 "PHY_G5_RESEARCH_ONLY":GROUPS["G5"],
 "ALL_WITHOUT_JONES":list(dict.fromkeys(no_j+old)),
 "ALL_MERGED_RESEARCH_ONLY":list(dict.fromkeys(GROUPS["G5"]+old))
 }
 for label,fs in gr.items():
  if len(fs)!=len(set(fs)):raise RuntimeError("FEATURE_DUPLICATION:"+label)
 return gr
def make_splits(np,pd,data):
 from stage_b import split_masks,site_weights
 for held in ("R2","R4","R5"):
  tr,te,dist=split_masks(data,held)
  if tr.sum()<100 or te.sum()<100:raise RuntimeError("EMPTY_SPLIT")
  if set(data.loc[tr,"route"]) & {held}:raise RuntimeError("TEST_ROUTE_LEAK")
  if np.min(dist[tr])<=1e-4:raise RuntimeError("TEST_XY_LEAK")
  yield held,tr,te
def run(out,pre,n0,original_RF):
 np,pd=deps()
 from features import GROUPS
 from stage_b import site_weights
 from sklearn.ensemble import RandomForestRegressor,RandomForestClassifier
 from sklearn.metrics import r2_score,brier_score_loss,roc_auc_score
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(pre).read_text())
 if a["decision"]!="GO" or a["source_commit"]!=os.getenv("GITHUB_SHA"):raise RuntimeError("PREAUDIT_NOT_GO")
 verify_n0(n0)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 data=build_data(np,pd,manifest)
 # Verify exact original 14 frozen observer traces, not only source RF bytes.
 indexed=data.set_index(["case","channel","pose_id"],verify_integrity=True)
 with readzip(original_RF,RF_SHA) as z:
  raw=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  parity=[]
  for desc in raw["per_case"]:
   payload=z.read("P2_OUT/"+desc["trace_file"])
   if hashlib.sha256(payload).hexdigest()!=desc["trace_sha256"]:raise RuntimeError("ORIGINAL_NPZ_CHANGED")
   with np.load(io.BytesIO(payload),allow_pickle=False) as zz:
    ids=zz["pose_id"].astype(int)
    key=[(desc["case"],desc["channel"],int(k)) for k in ids]
    ref=indexed.loc[key]
    ds=float(np.max(np.abs(ref["s_fp"].to_numpy(float)-zz["z_s"])))
    dr=float(np.max(np.abs(ref["range_m"].to_numpy(float)-zz["z_r_m"])))
    if max(ds,dr)>1e-12:raise RuntimeError("OBSERVER_PARITY_ERROR:"+str((desc["case"],ds,dr)))
    parity.append({"case":desc["case"],"channel":desc["channel"],"n":len(ids),"s_max":ds,"r_max":dr})
 if sum(r["n"] for r in parity)!=14502:raise RuntimeError("P3_R0_COUNT_DIFFERENT")
 # Pooled full paired oracle eMP outcomes, never included in predictor features.
 orig=data[["case","channel","pose_id","s_fp"]].pivot(
      index=["case","pose_id"],columns="channel",values="s_fp")
 if len(orig)!=9519:raise RuntimeError("FULL_LOS_NATIVE_PAIR_LOSS")
 bad=(np.abs(orig["full"]-orig["los"])>.1)
 key=pd.MultiIndex.from_frame(data[["case","pose_id"]])
 data["MP_BAD_EVAL_ONLY"]=np.array(bad.loc[key],dtype=bool)
 g=groups()
 required=set(sum(g.values(),[]))
 if not required.issubset(data.columns):
  raise RuntimeError("FEATURE_MISSING:"+str(required-set(data.columns)))
 results=[];preds=[];splits=[]
 for held,tr,te in make_splits(np,pd,data):
  fulltr=tr & (data["channel"].to_numpy()=="full")
  fullte=te & (data["channel"].to_numpy()=="full")
  y_train=data.loc[tr,"e_total_eval"].to_numpy(float)**2
  y_test=data.loc[te,"e_total_eval"].to_numpy(float)**2
  y_mp=data.loc[fulltr,"MP_BAD_EVAL_ONLY"].to_numpy(bool)
  y_mp_test=data.loc[fullte,"MP_BAD_EVAL_ONLY"].to_numpy(bool)
  w_reg=site_weights(data.loc[tr])
  w_clf=site_weights(data.loc[fulltr])
  if len(np.unique(y_mp))!=2 or len(np.unique(y_mp_test))!=2:
   raise RuntimeError("NO_MIXED_MP_CLASSES:"+held)
  splits.append({"held_route":held,"train_rows":int(tr.sum()),"test_rows":int(te.sum()),
    "train_full":int(fulltr.sum()),"test_full":int(fullte.sum()),
    "train_routes":sorted(data.loc[tr,"route"].unique().tolist())})
  for model,features in g.items():
   X=data[features].to_numpy(float)
   if not np.isfinite(X).all():raise RuntimeError("FEATURE_NAN:"+model)
   reg=RandomForestRegressor(n_estimators=160,max_depth=6,min_samples_leaf=40,
                              random_state=20261015,n_jobs=2)
   reg.fit(X[tr],y_train,sample_weight=w_reg);reg.n_jobs=1
   predicted=reg.predict(X[te])
   if not(np.isfinite(predicted).all() and np.all(predicted>=0)):
    raise RuntimeError("BAD_REG_PREDICTION")
   eff=np.clip(predicted,.0081,.81)
   test=data.loc[te]
   for channel in ("full","los"):
    m=test.channel.to_numpy()==channel
    y=y_test[m];v=predicted[m];r=eff[m]
    w=site_weights(test.loc[m])
    results.append({"fold":held,"model":model,"task":"e_total_squared",
     "channel":channel,"n":int(m.sum()),"n_features":len(features),
     "target_metric":"conditional second moment of s_full/s_los minus LoS LUT",
     "r2":float(r2_score(y,v,sample_weight=w)),
     "gaussian_nll":float(np.average(.5*(np.log(2*np.pi*r)+y/r),weights=w)),
     "error95_coverage":float(np.average(y<=3.841458820694124*r,weights=w)),
     "brier":None,"auroc":None})
   # Shared RF algorithm; classifier only Full, label native Full minus native LoS.
   clf=RandomForestClassifier(n_estimators=160,max_depth=6,min_samples_leaf=40,
                               random_state=20261015,n_jobs=2)
   clf.fit(X[fulltr],y_mp.astype(int),sample_weight=w_clf);clf.n_jobs=1
   prob=np.clip(clf.predict_proba(X[fullte])[:,1],1e-6,1-1e-6)
   results.append({"fold":held,"model":model,"task":"MP_proxy",
      "channel":"full","n":int(fullte.sum()),"n_features":len(features),
      "target_metric":"abs(s_full_native - s_los_native) > 0.1",
      "r2":None,"gaussian_nll":None,"error95_coverage":None,
      "brier":float(brier_score_loss(y_mp_test,prob)),
      "auroc":float(roc_auc_score(y_mp_test,prob))})
   chosen=data.loc[fullte,["case","route","pose_id","x_eval"]]
   for row,prediction,actual in zip(chosen.itertuples(index=False),prob,y_mp_test):
    preds.append({"case":row.case,"route":row.route,"pose_id":int(row.pose_id),
      "station_block":str(row.route)+":"+str(math.floor(float(row.x_eval)/1.5)),
      "model":model,"p_MP_proxy":float(prediction),"truth_only_bad":int(actual)})
   print("N3_FOLD_MODEL "+json.dumps({"fold":held,"model":model,
     "brier":results[-1]["brier"],"auroc":results[-1]["auroc"]}),flush=True)
 # Inspect the incremental effect WITH paired heldout block bootstrap; one physical scene only.
 prediction_df=pd.DataFrame(preds)
 prediction_df.to_csv(out/"N3_HELDOUT_PREDICTIONS.csv.gz",index=False,compression="gzip")
 result_frame=pd.DataFrame(results)
 result_frame.to_csv(out/"N3_HELDOUT_RESULTS.csv",index=False)
 pd.DataFrame(parity).to_csv(out/"N3_OBSERVER_PARITY.csv",index=False)
 pd.DataFrame(splits).to_json(out/"N3_SPLITS.json",orient="records",indent=2)
 aggregated=[]
 for model,sub in result_frame.groupby("model"):
  for task,channel in (("MP_proxy","full"),("e_total_squared","full"),("e_total_squared","los")):
   q=sub[(sub.task==task)&(sub.channel==channel)]
   if not len(q):continue
   w=q.n.to_numpy(float)
   metrics={"model":model,"task":task,"channel":channel,"n":int(q.n.sum())}
   for col in ("brier","auroc","r2","gaussian_nll","error95_coverage"):
    if np.isfinite(q[col].to_numpy(float)).all():
     metrics[col]=float(np.average(q[col],weights=w))
    else:metrics[col]=None
   aggregated.append(metrics)
 rng=np.random.default_rng(20261015)
 boot=[]
 for model in ("PHY_G5_RESEARCH_ONLY","ALL_MERGED_RESEARCH_ONLY","LEGACY_CIR","ALL_WITHOUT_JONES"):
  pair=prediction_df[prediction_df.model.isin(["G0_BASE",model])].copy()
  pair["loss_sq"]=(pair.p_MP_proxy-pair.truth_only_bad)**2
  grid=pair.groupby(["station_block","model"])["loss_sq"].agg(["sum","count"]).reset_index()
  blocks=sorted(set(grid.station_block))
  A=grid[grid.model=="G0_BASE"].set_index("station_block").reindex(blocks)
  B=grid[grid.model==model].set_index("station_block").reindex(blocks)
  if A.isna().any().any() or B.isna().any().any():
   raise RuntimeError("BOOTSTRAP_PAIRED_GROUP_MISSING")
  diffs=[]
  for i in range(500):
   chosen=rng.integers(0,len(blocks),len(blocks))
   ba=float(A["sum"].to_numpy()[chosen].sum()/A["count"].to_numpy()[chosen].sum())
   bb=float(B["sum"].to_numpy()[chosen].sum()/B["count"].to_numpy()[chosen].sum())
   diffs.append(bb-ba)
  boot.append({"control":"G0_BASE","candidate":model,
     "brier_candidate_minus_G0":float(B["sum"].sum()/B["count"].sum()-A["sum"].sum()/A["count"].sum()),
     "block_bootstrap_95_CI":np.quantile(diffs,[.025,.975]).tolist(),
     "block_count":len(blocks),
     "bootstrap_unit":"route+1.5m corridor x block (not independent scene)"})
 final={"stage":"N3","status":"N3_INCREMENTAL_PHYSICAL_FEATURE_EVALUATION_COMPLETE",
  "input_pose_pairs":9519,"feature_rows_both_channels":len(data),
  "exact_R0_parity":parity,"source_splits":splits,
  "feature_groups":g,"model_configuration":"RF 160 trees, max depth 6, leaf >=40; same all arms",
  "aggregated":aggregated,"paired_bootstrap":boot,
  "unavailable":["measured thermal SNR","hardware port calibration","genuine inter-packet time jitter if no timestamps",
    "R4/R5 true Heading update harm target with matched gyro pre-RF priors",
    "measured relative yaw gyro Gradient"],
  "warnings":["R2/R4/R5 holdouts are same corridor",
    "Each physics feature may depend on frequency-resolved coherent H not available from actual DWM1000",
    "Ground truth and native LoS oracle only used for training labels/evaluation; never predictors",
    "Bootstrap CIs quantify within-corridor blocks, not independent RF scenes",
    "Conditional error squared is not centered covariance; no direct EKF R calibration",
    "G0 signed and separate P1/P2 representations contain no new physical measurement"],
  "scientific_PASS":False}
 save(out/"N3_FINAL.json",final)
 print("N3_FINAL "+json.dumps({"status":final["status"],"summary":aggregated,
                 "incremental":boot,"parity_count":sum(x["n"] for x in parity)}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","test","run"),required=True)
 p.add_argument("--out");p.add_argument("--audit");p.add_argument("--n0");p.add_argument("--raw")
 a=p.parse_args()
 raise SystemExit(pre(a.out) if a.phase=="pre" else test() if a.phase=="test" else
  run(a.out,a.audit,a.n0,a.raw))
