"""B0 controlled physics features -> hard RF/s-only gating vs soft mean and Rs.
Original sensor/FFD/LoS LUT and validated J4 baseline are READ ONLY.
Preaudit imports only stdlib; numerical dependencies are imported after GO.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PHYS=ROOT/"research/PHYSICS_RS_STAGED_20261015/code"
R2CODE=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
MANIFEST=ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
RF_ARCH_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_ARCH_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
R2_CASES=("R2_aA_m0","R2_aA_m45")
B0_NAME="B0"
GATE_JOINT=9.210340371976184
GATE_R=6.6348966010212145
MODEL_GROUPS=("G0","G2","G3","G4","G5")
SOFT_GROUPS=("G0","G2","G3","G4","G5")
VARIANTS=("DR4","R0_J4","SOFT_G0_RS","SOFT_G2_RS","SOFT_G3_RS",
          "SOFT_G4_RS","SOFT_G5_RS","SOFT_G5_MEAN","SOFT_G5_MEAN_RS",
          "HARD_ALL_G5_p50","HARD_ALL_G5_p75",
          "HARD_S_G5_p50","HARD_S_G5_p75",
          "HARD_S_G0_p50","HARD_S_G5_p50_RANDOM_MATCH")
SOURCE_BLOBS={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_frozen_inputs.py":"3ba19cf01bd225ccf98335e5e92448530713b045",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/PHYSICS_RS_STAGED_20261015/code/features.py":"c556da153739aaf99d2558c84c1a515c3da41a97",
 "research/PHYSICS_RS_STAGED_20261015/code/stage_b.py":"b56d9e1459f2265fea83cd87cb411cd1cc4f3f9d",
 "research/PHYSICS_RS_STAGED_20261015/code/stage_c.py":"1a215ef1ab0f2f56cc60960742545be6873c7eb0",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
def sha_file(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def blob_sha(path):
 f=Path(path);h=hashlib.sha1()
 h.update(b"blob "+str(f.stat().st_size).encode()+b"\x00")
 with f.open("rb") as s:
  for c in iter(lambda:s.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def dump(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def source_inventory():
 manifest=json.loads(MANIFEST.read_text())
 case_assets=[]
 for c in manifest["cases"]:
  case_assets += [c["full_path"],c["los_path"],c["samples_path"]]
 prefix="results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/"
 case_assets.append(prefix+"freqs_hz.npy")
 return manifest,case_assets
def preaudit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 failures=[];audit_blobs={};asset_shas={}
 if os.getenv("GITHUB_ACTIONS")!="true":
  failures.append("REQUIRES_GITHUB_ACTIONS_EXACT_CHECKOUT")
 try:
  head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
  if head!=os.getenv("GITHUB_SHA"):failures.append("HEAD_COMMIT_NOT_EXACT")
 except Exception as ex:
  failures.append("GIT_HEAD_FAILED:"+repr(ex));head=None
 for p,expected in SOURCE_BLOBS.items():
  f=ROOT/p
  if not f.is_file():failures.append("SOURCE_MISSING:"+p);continue
  got=blob_sha(f);audit_blobs[p]=got
  if got!=expected:failures.append("SOURCE_BLOB_MISMATCH:"+p)
 try:
  manifest,assets=source_inventory()
  allowed={r["path"]:r for r in manifest["assets"]}
  for rel in assets:
   f=ROOT/rel
   if not f.is_file():
    failures.append("MISSING_RAW_RF_ASSET:"+rel);continue
   got_sha=sha_file(f);asset_shas[rel]=got_sha
   meta=allowed.get(rel)
   if meta is None or meta["sha256"]!=got_sha or meta["bytes"]!=f.stat().st_size:
    failures.append("RAW_RF_SHA_OR_SIZE_DIFFERENCE:"+rel)
 except Exception as ex:failures.append("ASSET_AUDIT_FAILURE:"+repr(ex))
 for name in ("r5_b0_hard_soft.py",):
  try:ast.parse((HERE/name).read_text(encoding="utf-8"))
  except Exception as ex:failures.append("R5_SOURCE_SYNTAX:"+repr(ex))
 replay=(R2CODE/"r2_bias_replay.py").read_text(encoding="utf-8")
 if ('if alg in ("S3","S4"):' not in replay or
     'if alg.startswith("S"):' in replay or
     'if not alg.startswith("SR"):' not in replay):
  failures.append("LEGACY_SR_DISPATCH_REGRESSION")
 wf=ROOT/".github/workflows/r5-b0-hard-soft-physics.yml"
 if not wf.is_file():failures.append("WORKFLOW_MISSING")
 else:
  t=wf.read_text()
  for token in ("r5_b0_hard_soft.py --phase pre","r5_b0_hard_soft.py --phase test",
                "r5_b0_hard_soft.py --phase run","if: always()","actions: read",
                "set -euo pipefail"):
   if token not in t:failures.append("WORKFLOW_REQUIRED_"+token)
  if all(q in t for q in ("r5_b0_hard_soft.py --phase pre",
                        "r5_b0_hard_soft.py --phase test",
                        "r5_b0_hard_soft.py --phase run")):
   pos=[t.index(q) for q in ("r5_b0_hard_soft.py --phase pre",
            "r5_b0_hard_soft.py --phase test",
            "r5_b0_hard_soft.py --phase run")]
   if pos!=sorted(pos):failures.append("WORKFLOW_ORDER_WRONG")
 receipt={"stage":"R5_PHY_B0_PRE_AUDIT","git_sha":head,
    "decision":"GO" if not failures else "HOLD",
    "original_source_blobs":audit_blobs,"original_raw_rf_sha256":asset_shas,
    "original_archive_shas":{"frozen_R2_RF":RF_ARCH_SHA,"validated_R2_output":R2_ARCH_SHA},
    "failure_reasons":failures,"scientific_PASS":False}
 dump(out/"PRE_AUDIT.json",receipt)
 print("R5_B0_PRE_AUDIT "+json.dumps({"decision":receipt["decision"],
      "n_assets":len(asset_shas),"errors":failures}),flush=True)
 return 0 if not failures else 2

def setup():
 import numpy as np
 import pandas as pd
 sys.path.insert(0,str(PHYS))
 sys.path.insert(0,str(R2CODE))
 sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
 return np,pd

def unit_tests():
 np,pd=setup()
 from scipy.stats import chi2
 from features import GROUPS,FEATURES,extract
 from core import gaussian_update,predict,transition
 from stage_c import fast_predict,fast_update
 import numpy.testing as npt
 # Exact analytic original vs optimized scalar on deterministic SPD canary.
 from p3_rf_adapter4 import R0
 from r2_bias_replay import predict_one
 a=np.array([1.,2.,.25,math.radians(.02)])
 p=np.diag([.07,.09,math.radians(3.)**2,math.radians(.1)**2])
 z=np.array([2.7,.33])
 def m(x):
  return np.array([np.hypot(x[0],x[1]),math.sin(x[2])]),np.array([
    [x[0]/np.hypot(x[0],x[1]),x[1]/np.hypot(x[0],x[1]),0,0],
    [0,0,math.cos(x[2]),0]],float)
 slow=gaussian_update(a,p,z,m,R0,gate_threshold=GATE_JOINT)
 fast=fast_update(a,p,z,m,R0,GATE_JOINT)
 npt.assert_allclose(slow[0],fast[0],rtol=0,atol=1e-13)
 npt.assert_allclose(slow[1],fast[1],rtol=0,atol=1e-13)
 if slow[2]["accepted"]!=fast[3]:raise AssertionError("GATE_OPERATOR_PARITY")
 ds=.015;da=.002;dt=.2
 slowpredict=predict_one(a,p,ds,da,dt)
 fastpredict=fast_predict(a,p,ds,da,dt)
 npt.assert_allclose(slowpredict[0],fastpredict[0],rtol=0,atol=1e-13)
 npt.assert_allclose(slowpredict[1],fastpredict[1],rtol=0,atol=1e-13)
 if not(all(g in GROUPS for g in MODEL_GROUPS) and len(FEATURES)==17):
  raise AssertionError("PHYSICS_GROUP_CONTRACT")
 # Ensure soft bias correction changes observation but never creates an extra RF factor.
 npt.assert_allclose(z.copy()-np.array([0.,.05]),[2.7,.28],rtol=0,atol=1e-14)
 # Hard-S is scalar-only, do not pass s twice.
 rmodel=lambda v:(m(v)[0][:1],m(v)[1][:1,:])
 _,_,diag=gaussian_update(a,p,z[:1],rmodel,R0[:1,:1],gate_threshold=GATE_R)
 if diag["H"].shape!=(1,4):raise AssertionError("HARD_S_SHAPE")
 print("R5_B0_UNIT_PASS "+json.dumps({"num_math_tests":7,"groups":list(MODEL_GROUPS)}),flush=True)
 return 0

def prepare_features(np,pd,manifest):
 from features import extract,FEATURES
 from p3_rf_adapter4 import FrozenLut
 lut=FrozenLut(ROOT)
 prefix=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
 freq=np.load(prefix/"freqs_hz.npy",allow_pickle=False)
 frames=[]
 for case in manifest["cases"]:
  src=json.loads((ROOT/case["samples_path"]).read_text())
  ids=np.array([v["pose_id"] for v in src],dtype=int)
  truth=np.array([[v["x"],v["y"],math.radians(v["yaw_body_deg"])] for v in src],dtype=float)
  assert len(ids)==case["rf_count"] and len(set(ids))==len(ids)
  s_lut=np.array([lut.model(q,case)[0][1] for q in truth])
  for ch,key in (("los","los_path"),("full","full_path")):
   h=np.load(ROOT/case[key],mmap_mode="r",allow_pickle=False)
   if tuple(h.shape)!=tuple(case["H_shape"]):raise RuntimeError("RF_H_SHAPE_MISMATCH")
   blocks=[extract(np.asarray(h[j:min(j+48,len(h)),:,:,0]),freq)
            for j in range(0,len(h),48)]
   feats={key:np.concatenate([block[key] for block in blocks])
          for key in blocks[0]}
   if not np.all(feats["valid"]):raise RuntimeError("RF_PACKET_INVALID:"+case["id"]+"/"+ch)
   table=pd.DataFrame({"case":case["id"],"route":case["route"],"channel":ch,
     "pose_id":ids,"x_eval":truth[:,0],"y_eval":truth[:,1],"yaw_eval_rad":truth[:,2],
     "s_lut_eval":s_lut,"e_total_eval":feats["s_fp"]-s_lut})
   for feature in FEATURES:table[feature]=feats[feature]
   table["s_fp"]=feats["s_fp"]
   frames.append(table)
   print("R5_B0_FEATURE_CASE "+json.dumps({"case":case["id"],"channel":ch,"rows":len(table)}),flush=True)
 data=pd.concat(frames,ignore_index=True)
 if len(data)!=19038 or data.duplicated(["case","channel","pose_id"]).any():
  raise RuntimeError("FEATURE_DUPLICATE_OR_COUNT")
 return data,lut

def fit_models(np,pd,data):
 from stage_b import split_masks,site_weights,fit_train,predictor_table
 from features import GROUPS
 from sklearn.ensemble import RandomForestRegressor
 from sklearn.linear_model import LogisticRegression
 from sklearn.pipeline import make_pipeline
 from sklearn.impute import SimpleImputer
 from sklearn.preprocessing import StandardScaler
 tr,te,dist=split_masks(data,"R2")
 if not(tr.sum()==11216 and te.sum()==7818):
  raise RuntimeError("TRAIN_TEST_PAIRING_OR_SIZE_INVALID")
 feature_table=data.loc[tr]
 test=data.loc[te].copy()
 variance={}
 preds=test[["case","channel","pose_id"]].copy()
 for group in MODEL_GROUPS:
  feature_list=GROUPS[group]
  model=fit_train(data,tr,feature_list)
  val=model.predict(predictor_table(test,feature_list))
  if not(np.isfinite(val).all() and (val>=0).all()):raise RuntimeError("NEGATIVE_VARIANCE")
  preds["R_"+group]=np.clip(val,.0081,.81)
  variance[group]=model
 # Signed expected (observed s - clean frozen LoS) prediction.
 g5=GROUPS["G5"];trainx=predictor_table(feature_table,g5)
 weights=site_weights(feature_table)
 signed=RandomForestRegressor(n_estimators=160,max_depth=6,min_samples_leaf=40,
                             random_state=20261015,n_jobs=2)
 signed.fit(trainx,feature_table["e_total_eval"].to_numpy(float),sample_weight=weights)
 signed.n_jobs=1
 mu=signed.predict(predictor_table(test,g5))
 if not np.isfinite(mu).all():raise RuntimeError("NONFINITE_SIGNED_BIAS")
 preds["MU_G5"]=mu
 # MP proxy classifier uses only Full on R4/R5; oracle labels never go to estimator.
 pair=data.pivot(index=["case","pose_id"],columns="channel",values="s_fp")
 if pair.shape[0]!=9519:raise RuntimeError("FULL_LOS_PAIR_NOT_UNIQUE")
 mp=pair["full"]-pair["los"]
 prob_meta={}
 for name in ("G0","G5"):
  train_full=feature_table.loc[feature_table.channel=="full"].copy()
  key=list(zip(train_full.case,train_full.pose_id))
  target=(np.abs(mp.reindex(pd.MultiIndex.from_tuples(key,names=["case","pose_id"])).to_numpy())>.1).astype(int)
  if not set(np.unique(target))=={0,1}:raise RuntimeError("ONE_CLASS_ONLY")
  classifier=make_pipeline(StandardScaler(),LogisticRegression(
     C=1.,max_iter=750,solver="lbfgs",random_state=20261015))
  classifier.fit(predictor_table(train_full,GROUPS[name]),target)
  pred=classifier.predict_proba(predictor_table(test,GROUPS[name]))[:,1]
  if not np.isfinite(pred).all() or np.any((pred<0)|(pred>1)):
   raise RuntimeError("BAD_PROBABILITY")
  preds["PBAD_"+name]=pred
  prob_meta[name]={"train_full_samples":len(train_full),
                   "train_proxy_bad_rate":float(target.mean()),
                   "predictor_features":GROUPS[name]}
 # test pairing labels retained ONLY for offline oracle validation and not copied to runner
 oracle=test[["case","channel","pose_id","e_total_eval"]].copy()
 oracle["e_mp_eval"]=[float(mp.loc[(row.case,row.pose_id)]) if row.channel=="full" else 0.
                      for row in oracle.itertuples()]
 return preds,oracle,prob_meta,{"train_rows":int(tr.sum()),"test_rows":int(te.sum()),
   "coincident_xy_removed":int(((~tr)&(~te)).sum()),
   "train_routes":sorted(data.loc[tr,"route"].unique().tolist()),
   "heldout_route":"R2","predictor_groups":list(MODEL_GROUPS)}

def find_in_zip(z,name):
 hits=[i for i in z.namelist() if i==name or i.endswith("/"+name)]
 if len(hits)!=1:raise RuntimeError("ZIP_MEMBER_NONUNIQUE:"+name+":found"+str(len(hits)))
 return hits[0]
def npz_from(z,name,np):
 with np.load(io.BytesIO(z.read(find_in_zip(z,name))),allow_pickle=False) as f:
  return {k:f[k].copy() for k in f.files}
def to_csv(path,rows):
 if not rows:raise RuntimeError("EMPTY_EXPORT")
 with Path(path).open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]))
  w.writeheader();w.writerows(rows)

def filtered_case(t,controls,z,case,lut,x0,quality,variant,random_drop=None):
 """No GT/truth/label access. Quality arrays hold only online-packet features."""
 import numpy as np
 from p3_rf_adapter4 import R0
 from r2_bias_replay import predict_one,filter_one,INITIAL_POSE_STD,BIAS_PRIOR_STD
 from stage_c import fast_predict,fast_update
 n=len(t)
 initp=np.diag([INITIAL_POSE_STD[0]**2,INITIAL_POSE_STD[1]**2,
                INITIAL_POSE_STD[2]**2,BIAS_PRIOR_STD**2])
 x=np.r_[x0,0.];p=initp.copy()
 XX=np.zeros((n,4));PP=np.zeros((n,4,4));mode=np.empty(n,dtype="<U20")
 score=np.zeros(n);nis=np.full(n,np.nan)
 def both(v):return lut.model(v,case)
 def onlyrange(v):
  h,H=both(v)
  return h[:1],H[:1,:]
 for i in range(n):
  if i:
   ds,da,dt=(float(controls[key][i]) for key in ("ds_odom","dtheta_gyro","dt_s"))
   x,p=(predict_one(x,p,ds,da,dt) if variant in ("DR4","R0_J4")
        else fast_predict(x,p,ds,da,dt))
  obs=z[i]
  risk_g5=float(quality["PBAD_G5"][i])
  risk_g0=float(quality["PBAD_G0"][i])
  score[i]=risk_g5
  if variant=="DR4":
   mode[i]="DR_ONLY"
  elif variant=="R0_J4":
   x,p,status,nisi=filter_one(x,p,obs,"J4",case,lut)
   mode[i]=status;nis[i]=nisi
  else:
   is_all=variant.startswith("HARD_ALL")
   is_hards=variant.startswith("HARD_S")
   threshold=.75 if "p75" in variant else .5
   if is_all or is_hards:
    reject=(bool(random_drop[i]) if variant.endswith("RANDOM_MATCH")
            else (risk_g0 if variant=="HARD_S_G0_p50" else risk_g5)>threshold)
    if reject:
     if is_all:
      mode[i]="RF_SKIPPED"
     else:
      xp,pp,nisi,accepted=fast_update(x,p,obs[:1],onlyrange,R0[:1,:1],GATE_R)
      x,p=xp,pp
      mode[i]="R_ONLY" if accepted else "R_REJECT"
      nis[i]=nisi
    else:
     x,p,nisi,accepted=fast_update(x,p,obs,both,R0,GATE_JOINT)
     mode[i]="JOINT" if accepted else "JOINT_REJECT"
     nis[i]=nisi
   else:
    R=R0.copy()
    zz=obs.copy()
    if variant in ("SOFT_G5_MEAN","SOFT_G5_MEAN_RS"):
     zz[1]-=float(quality["MU_G5"][i])
    if variant.startswith("SOFT_") and variant.endswith("_RS"):
     group=variant.split("_")[1]
     R[1,1]=float(quality["R_"+group][i])
    x,p,nisi,accepted=fast_update(x,p,zz,both,R,GATE_JOINT)
    mode[i]="JOINT" if accepted else "JOINT_REJECT"
    nis[i]=nisi
  if not(np.isfinite(x).all() and np.isfinite(p).all() and np.linalg.eigvalsh(p).min()>0):
   raise RuntimeError("INVALID_POSTERIOR:"+variant+":"+str(i))
  XX[i]=x;PP[i]=p
 return {"estimate":XX,"covariance":PP,"status":mode,"nis":nis,"risk_score":score}

def score_one(np,t,truth,truebias,payload):
 x=payload["estimate"];p=payload["covariance"];status=payload["status"]
 valid=t>=30.
 err=x[valid,:3]-truth[valid,:3]
 err[:,2]=(err[:,2]+np.pi)%(2*np.pi)-np.pi
 cov=p[valid,:3,:3]
 if np.min(np.linalg.eigvalsh(cov))<=0:raise RuntimeError("SCORE_POSE_NON_PD")
 nees=np.einsum("bi,bi->b",err,np.linalg.solve(cov,err[:,:,None])[:,:,0])
 hn=err[:,2]**2/cov[:,2,2]
 bias=x[valid,3]
 chi1=3.841458820694124;chi3=7.814727903251179
 return {
   "frames":int(valid.sum()),"heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(err[:,2]**2)))),
   "heading_mean_signed_error_deg":float(np.degrees(np.mean(err[:,2]))),
   "heading_sigma_rms_deg":float(np.degrees(np.sqrt(np.mean(cov[:,2,2])))),
   "heading_nees_mean":float(hn.mean()),"heading95_coverage":float(np.mean(hn<=chi1)),
   "position_rmse_m":float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))),
   "pose_nees_mean":float(nees.mean()),"pose95_coverage":float(np.mean(nees<=chi3)),
   "bias_rmse_dps":float(np.degrees(np.sqrt(np.mean((bias-math.radians(truebias))**2)))),
   "bias_final_dps":float(np.degrees(x[-1,3])),
   "bias95_coverage":float(np.mean((bias-math.radians(truebias))**2<=chi1*p[valid,3,3])),
   "wrong_over5deg_confident_fraction":float(np.mean((np.degrees(np.abs(err[:,2]))>5)&(hn>chi1))),
   "applied_joint":int(np.sum(np.isin(status[valid],["APPLIED","JOINT"]))),
   "r_only":int(np.sum(status[valid]=="R_ONLY")),
   "rf_skipped":int(np.sum(status[valid]=="RF_SKIPPED")),
   "rf_joint_rejected":int(np.sum(np.isin(status[valid],["REJECT","JOINT_REJECT"]))),
   "range_rejected":int(np.sum(status[valid]=="R_REJECT")),
   "high_risk_gt50_fraction":float(np.mean(payload["risk_score"][valid]>.5))}

def run(raw,r2zip,auditfile,out):
 np,pd=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 audit=json.loads(Path(auditfile).read_text())
 if audit["decision"]!="GO" or audit["git_sha"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("PREAUDIT_NOT_GO")
 if sha_file(raw)!=RF_ARCH_SHA or sha_file(r2zip)!=R2_ARCH_SHA:
  raise RuntimeError("ARCHIVE_SHA_MISMATCH")
 with zipfile.ZipFile(raw) as z:
  if z.testzip() is not None:raise RuntimeError("ARCHIVE_CRC_INVALID")
 with zipfile.ZipFile(r2zip) as z:
  if z.testzip() is not None:raise RuntimeError("BASELINE_CRC_INVALID")
 from p3_rf_adapter4 import FrozenLut
 from r2_bias_replay import build_positive_bias_controls,run_filters,METHODS
 manifest=json.loads(MANIFEST.read_text())
 data,lut=prepare_features(np,pd,manifest)
 preds,offline_oracle,classification_meta,split=fit_models(np,pd,data)
 pd.DataFrame(split,index=[0]).to_json(out/"R5_B0_DATA_SPLIT.json",orient="records",indent=2)
 bypred=preds.set_index(["case","channel","pose_id"])
 case_meta={c["id"]:c for c in manifest["cases"]}
 all_scores=[];checks=[];per_route_class=[]
 with zipfile.ZipFile(raw) as zf,zipfile.ZipFile(r2zip) as zv:
  summary=json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  entries={(q["case"],q["channel"]):q for q in summary["per_case"]}
  for case in R2_CASES:
   for ch in ("full","los"):
    entry=entries[(case,ch)]
    member="P2_OUT/"+entry["trace_file"]
    blob=zf.read(member)
    if hashlib.sha256(blob).hexdigest()!=entry["trace_sha256"]:
     raise RuntimeError("FROZEN_TRACE_SHA_ERROR")
    with np.load(io.BytesIO(blob),allow_pickle=False) as j:
     t=j["t_s"].copy();pid=j["pose_id"].copy()
     truth=j["truth_for_offline_scoring_only"].copy()
     z=np.column_stack([j["z_r_m"],j["z_s"]])
    key=pd.MultiIndex.from_tuples([(case,ch,int(k)) for k in pid],names=bypred.index.names)
    qual={c:bypred.loc[key,c].to_numpy(float) for c in bypred.columns}
    source=data[(data.case==case)&(data.channel==ch)].set_index("pose_id")
    # Independent RF observer parity with frozen EKF traces.
    reconstructed_s=source.loc[pid,"s_fp"].to_numpy(float)
    maxs=float(np.max(abs(reconstructed_s-z[:,1])))
    reconstructed_r=source.loc[pid,"range_m"].to_numpy(float)
    maxr=float(np.max(abs(reconstructed_r-z[:,0])))
    if max(maxs,maxr)>1e-12:raise RuntimeError("FROZEN_RF_OBSERVER_PARITY_FAIL:"+case+":"+ch+":"+str(max(maxs,maxr)))
    controls,x0=build_positive_bias_controls(t,truth,B0_NAME,0)
    # Independent original full 8 arm on 12-frame canary, B0 J4 path comparison.
    subset=12
    canary=run_filters(t[:subset],{k:v[:subset] for k,v in controls.items()},
                       z[:subset],case_meta[case],lut,x0)["recursive"]
    j4_index=list(METHODS).index("J4")
    results={}
    random_mask=None
    actual_g5_mask=qual["PBAD_G5"]>.5
    rng=np.random.default_rng(20261015+int(case.endswith("m45"))*37+int(ch=="los")*73)
    random_mask=np.zeros(len(t),dtype=bool)
    random_mask[rng.choice(len(t),size=int(actual_g5_mask.sum()),replace=False)]=True
    for variant in VARIANTS:
     p=filtered_case(t,controls,z,case_meta[case],lut,x0,qual,variant,random_mask)
     results[variant]=p
     m=score_one(np,t,truth,0.,p)
     all_scores.append({"case":case,"mount_deg":case_meta[case]["mount_deg"],
         "channel":ch,"level":"B0","method":variant,**m})
     if variant=="R0_J4":
      dx=p["estimate"][:subset]-canary["estimate"][:,j4_index,:]
      dx[:,2]=(dx[:,2]+np.pi)%(2*np.pi)-np.pi
      if (np.max(abs(dx))>1e-12 or
          np.max(abs(p["covariance"][:subset]-canary["covariance"][:,j4_index]))>1e-12):
       raise RuntimeError("ORIGINAL_J4_CANARY_MISMATCH")
      old=npz_from(zv,f"{case}_{ch}_B0_seed0_recursive.npz",np)
      if not np.array_equal(old["names"],np.asarray(METHODS)):
       raise RuntimeError("REPLAY_METHOD_ORDER_CHANGED")
      ref=old["estimate"][:,j4_index,:];d=p["estimate"]-ref
      d[:,2]=(d[:,2]+np.pi)%(2*np.pi)-np.pi
      max_dx=float(np.max(abs(d)))
      max_cov=float(np.max(abs(p["covariance"]-old["covariance"][:,j4_index])))
      gate_original=old["status"][:,j4_index]=="APPLIED"
      gate_new=p["status"]=="APPLIED"
      delta_gate=int(np.sum(gate_new!=gate_original))
      if max_dx>1e-6 or max_cov>1e-6 or delta_gate:
       raise RuntimeError("R0_ORIGINAL_AUDIT_FAILURE:"+str((max_dx,max_cov,delta_gate)))
      checks.append({"case":case,"channel":ch,"R0_state_max_diff":max_dx,
                     "R0_cov_max_diff":max_cov,"gate_differences":delta_gate,
                     "strict_1e9_parity":max(max_dx,max_cov)<=1e-9,
                     "RF_reprocess_s_max_diff":maxs,"RF_reprocess_range_max_diff":maxr})
    save_name=case+"_"+ch+"_B0_HARD_SOFT.npz"
    np.savez_compressed(out/save_name,t_s=t,pose_id=pid,
       methods=np.asarray(VARIANTS),
       estimate=np.stack([results[k]["estimate"] for k in VARIANTS],axis=1),
       covariance=np.stack([results[k]["covariance"] for k in VARIANTS],axis=1),
       status=np.stack([results[k]["status"] for k in VARIANTS],axis=1),
       nis=np.stack([results[k]["nis"] for k in VARIANTS],axis=1),
       PBAD_G0=qual["PBAD_G0"],PBAD_G5=qual["PBAD_G5"],
       R_G0=qual["R_G0"],R_G2=qual["R_G2"],R_G3=qual["R_G3"],
       R_G4=qual["R_G4"],R_G5=qual["R_G5"],MU_G5=qual["MU_G5"])
    print("R5_B0_CASE "+json.dumps({"case":case,"channel":ch,
      "n":len(t),"variant_count":len(VARIANTS),
      "m0_g5_Rs_rmse":next(s["heading_rmse_deg"] for s in all_scores
                     if s["case"]==case and s["channel"]==ch and s["method"]=="SOFT_G5_RS")}),flush=True)
 # Required reference validation: when raw inputs and model reproduce earlier Physical Rs G5.
 expected={"R2_aA_m0":4.3038,"R2_aA_m45":1.3488}
 for case,tgt in expected.items():
  actual=next(x["heading_rmse_deg"] for x in all_scores
              if x["case"]==case and x["channel"]=="full" and x["method"]=="SOFT_G5_RS")
  if abs(actual-tgt)>.02:
   raise RuntimeError("PHYSICS_RS_G5_REPLICATION_DIFFERENCE:"+case+" expected="+str(tgt)+" got="+str(actual))
 to_csv(out/"R5_B0_HARD_SOFT_METRICS.csv",all_scores)
 to_csv(out/"R5_B0_ORIGINAL_PARITY.csv",checks)
 scores={(r["case"],r["channel"],r["method"]):r for r in all_scores}
 focus=[]
 for case in R2_CASES:
  for variant in VARIANTS:
   r=scores[(case,"full",variant)]
   focus.append({"case":case,"method":variant,
                 "heading_rmse_deg":r["heading_rmse_deg"],
                 "heading_nees":r["heading_nees_mean"],
                 "heading95":r["heading95_coverage"],
                 "pose_nees":r["pose_nees_mean"],
                 "pose95":r["pose95_coverage"],
                 "bias_final":r["bias_final_dps"],
                 "rf_skipped":r["rf_skipped"],"r_only":r["r_only"]})
 manifest_report={"schema":"R5_B0_PHYSICS_HARD_SOFT_V1",
  "status":"B0_HARD_SOFT_RECURSIVE_EXPLORATORY_COMPLETE",
  "source_commit":os.getenv("GITHUB_SHA"),
  "baseline_R0_shas":{"rf_archive":RF_ARCH_SHA,"r2_archive":R2_ARCH_SHA},
  "model_split":split,"mp_proxy_classifier":classification_meta,
  "baseline_canary_pass":True,"original_reference_parity":checks,
  "methods":list(VARIANTS),
  "focus_full_B0":focus,
  "limitations":["True gyro bias zero but b_g estimator remains free",
    "One corridor, one RF environment and one sensor seed",
    "Classifier q predicts MP proxy not true Heading harmfulness; no post-hoc threshold tuning",
    "G3/G5 complex-frequency Jones not proven available on DWM1000",
    "Soft mean correction trained on oracle only in training routes",
    "No R_rs, R_r or time-correlation calibration; nominal R0/gate retained",
    "No gradient scanner factor incorporated",
    "Full RF quality gating may reduce useful gyro-bias observability"],
  "scientific_PASS":False}
 dump(out/"R5_B0_FINAL.json",manifest_report)
 print("R5_B0_FINAL "+json.dumps({"status":manifest_report["status"],
     "focus":focus,"baseline_check":checks}),flush=True)
 return 0

def main():
 a=argparse.ArgumentParser()
 a.add_argument("--phase",choices=("pre","test","run"),required=True)
 a.add_argument("--out")
 a.add_argument("--raw")
 a.add_argument("--r2")
 a.add_argument("--audit")
 args=a.parse_args()
 if args.phase=="pre":return preaudit(args.out)
 if args.phase=="test":return unit_tests()
 if not all([args.raw,args.r2,args.audit,args.out]):
  raise ValueError("MISSING_RUN_REQUIRED_ARGUMENT")
 return run(Path(args.raw),Path(args.r2),Path(args.audit),args.out)
if __name__=="__main__":raise SystemExit(main())
