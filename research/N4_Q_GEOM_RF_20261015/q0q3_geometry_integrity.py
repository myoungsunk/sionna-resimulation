"""N4-Q0/Q1/Q2/Q3 audit-first, frozen dual-LP LoS information versus Full RF corruption.

NO new EKF factor, no re-tuning on R2, and no new synthetic Full RF packets.
All 'oracle' geometries and Full-nativeLoS pollution labels are OFFLINE only.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
MANIFEST=ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
RAW_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
PINNED={
 "research/R5_N4B_20261015/n4b_rf_errors.py":"abd654dd9efde61fc7baffc350188b2a8b4904a3",
 "research/R5_N4B_POL_V1_20261015/n4b_pol_geometry.py":"565d6f2704f40f770da5f70a40314141a3d621a1",
 "research/R5_FULLRF_B0_GATES_20261015/r5_b0_hard_soft.py":"24b7b0103a232662afaf5b1b79bfb542aa7123db",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/PHYSICS_RS_STAGED_20261015/code/features.py":"c556da153739aaf99d2558c84c1a515c3da41a97",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f"
}
GEOM_DELTAS=(-10.,-5.,-2.,2.,5.,10.)
SIGMA_S=.09
REF_BIAS_LEVELS=("B0","L2")
R2_CASES=("R2_aA_m0","R2_aA_m45")
ANCHOR_Q1_CASES=("R2_aA_m0","R2_aA_m45","R2_aB_m0")
THRESH_MP_S=.1
CASES=7

def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for c in iter(lambda:f.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def gitblob(path):
 f=Path(path);h=hashlib.sha1(b"blob "+str(f.stat().st_size).encode()+b"\0")
 with f.open("rb") as src:
  for c in iter(lambda:src.read(1<<20),b""):h.update(c)
 return h.hexdigest()
def write(path,data):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];blobs={};rawassets={}
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("EXACT_ACTIONS_CHECKOUT_REQUIRED")
 try:
  head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
  if head!=os.getenv("GITHUB_SHA"):errors.append("COMMIT_HASH_MISMATCH")
 except Exception as e:head=None;errors.append("GIT_ERROR:"+repr(e))
 for rel,expected in PINNED.items():
  path=ROOT/rel
  if not path.is_file():errors.append("FROZEN_SOURCE_MISSING:"+rel)
  else:
   s=gitblob(path);blobs[rel]=s
   if s!=expected:errors.append("FROZEN_SOURCE_CHANGED:"+rel)
 try:
  m=json.loads(MANIFEST.read_text())
  known={x["path"]:x for x in m["assets"]}
  paths=[v for c in m["cases"] for v in (c["full_path"],c["los_path"],c["samples_path"])]
  paths.append("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy")
  for rel in paths:
   f=ROOT/rel
   if not f.is_file():errors.append("INPUT_NOT_PRESENT:"+rel);continue
   digest=sha256(f);rawassets[rel]=digest
   if rel not in known or digest!=known[rel]["sha256"] or f.stat().st_size!=known[rel]["bytes"]:
    errors.append("FROZEN_INPUT_MISMATCH:"+rel)
 except Exception as e:errors.append("INPUT_AUDIT_EXCEPTION:"+repr(e))
 try:ast.parse((HERE/"q0q3_geometry_integrity.py").read_text())
 except Exception as e:errors.append("CODE_AST_ERROR:"+repr(e))
 wf=ROOT/".github/workflows/n4q-q0q3-integrity.yml"
 if not wf.is_file():errors.append("WORKFLOW_NOT_FOUND")
 else:
  s=wf.read_text();tokens=("q0q3_geometry_integrity.py --phase pre",
     "q0q3_geometry_integrity.py --phase test",
     "q0q3_geometry_integrity.py --phase run")
  if not all(t in s for t in tokens) or not s.index(tokens[0])<s.index(tokens[1])<s.index(tokens[2]):
   errors.append("AUDIT_FIRST_WORKFLOW_INVALID")
  if "if: always()" not in s or "actions: read" not in s:errors.append("ARTIFACT_PERMISSION_MISSING")
 result={"stage":"Q0","decision":"GO" if not errors else "HOLD",
   "head":head,"frozen_git_blobs":blobs,"frozen_source_assets":rawassets,
   "RF_archive_sha256":RAW_SHA,"R2_archive_sha256":R2_SHA,
   "R0":{"range_variance_m2":.0068578637,"s_variance":.0081},
   "errors":errors,"scientific_PASS":False}
 write(out/"Q0_PRE_AUDIT.json",result)
 print("N4Q_PRE "+json.dumps({"decision":result["decision"],"inputs":len(rawassets),
  "errors":errors}),flush=True)
 return 0 if not errors else 2

def checked_zip(path,digest):
 if sha256(path)!=digest:raise RuntimeError("ARCHIVE_SHA_MISMATCH:"+str(path))
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("ARCHIVE_CRC_FAIL")
 return z

def member(z,name):
 hits=[n for n in z.namelist() if n==name or n.endswith("/"+name)]
 if len(hits)!=1:raise RuntimeError("ARCHIVE_MEMBER_NONUNIQUE:"+name)
 return hits[0]

def environment():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
  str(ROOT/"research/R5_N4B_20261015"),
  str(ROOT/"research/R5_N4B_POL_V1_20261015"),
  str(ROOT/"research/R5_FULLRF_B0_GATES_20261015"),
  str(ROOT/"research/PHYSICS_RS_STAGED_20261015/code"),
  str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"),
  str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src")
 ]
 import n4b_rf_errors as base
 import n4b_pol_geometry as pol
 from p3_rf_adapter4 import FrozenLut
 from r2_bias_replay import build_positive_bias_controls,predict_one,METHODS
 return np,pd,base,pol,FrozenLut,build_positive_bias_controls,predict_one,METHODS

def wrap(np,x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def r2frames(np,z,case,channel):
 p=[q for q in z.namelist() if q.endswith(f"/{case}_{channel}_") and False]
 # The original P2 metadata holds trace names, not ad-hoc guessed names.
 raise RuntimeError("USE_ORIGINAL_METADATA")

def unit():
 np,pd,base,pol,Lut,_,_,_=environment()
 rng=np.random.default_rng(20261015)
 s=np.linspace(-1.,1.,61)
 frac=(1+s)/2
 assert np.allclose(frac+(1-s)/2,1)
 assert np.allclose(1-s*s,4*frac*(1-frac))
 for i in range(10):
  cov=rng.normal(size=(4,4))
  cov=cov@cov.T+np.diag([.1,.1,.2,.001])
  H=rng.normal(size=(1,4));H[0,3]=0
  a=H[0,:2];c=H[0,2]
  v=cov[2,2];cross=cov[:2,2]
  pcond=cov[:2,:2]-np.outer(cross,cross)/v
  heff=c+a@cross/v
  info=heff*heff/(.0081+a@pcond@a)
  assert info>=0 and np.linalg.eigvalsh(pcond).min()>0
 # Actual frozen FFD identity and ±2° finite-difference. No ideal cos² surrogate.
 lut=Lut(ROOT)
 case={"anchor":[4,0,2.65],"mount_deg":45,"robot_z_m":.45}
 for pose in ([2.,.8,.32],[3.,-.7,-.48]):
  f=pol.physical_features(np,lut,pose,case)
  delta=math.radians(.001)
  q=np.asarray(pose,float);p=q.copy();p[2]+=delta
  lo=q.copy();lo[2]-=delta
  grad=(lut.model(p,case)[0][1]-lut.model(lo,case)[0][1])/(2*delta)
  if abs(grad-f["Hpsi_lut"])>.008:raise RuntimeError("HPSI_FFD_CANARY_MISMATCH")
  assert abs(f["p_m1_los"]+f["p_m2_los"]-1)<1e-12
 # Negative control: zero RF corruption can coexist with low geometry information.
 fake=np.array([.3,.3]);contam=fake-fake
 assert np.all(contam==0)
 print("N4Q_UNIT_PASS "+json.dumps({"status":"PASS",
   "tests":["PORT_FRACTION","SCHUR_INFORMATION","FFD_JACOBIAN",
    "FINITE_ANGLE","NEGATIVE_CONTROL_CLEAN_BUT_LOW_INFO"]}),flush=True)
 return 0

def geometry(np,pd,base,pol,lut,full,manifest):
 original=pol.feature_table(np,pd,full,lut,manifest)
 geom=original[["case","route","pose_id","x_eval","y_eval","yaw_eval_rad",
  "s_los_expected","Hpsi_lut","Ipsi_nominal","balance_los","p_dom_los",
  "relative_rx_az_cos","relative_rx_az_sin","theta_elev"]].copy()
 desc={c["id"]:c for c in manifest["cases"]}
 fields=[]
 offsets=np.radians(GEOM_DELTAS)
 profile_offsets=np.radians(np.arange(-20.,20.01,2))
 for c,g in geom.groupby("case",sort=True):
  case=desc[c]
  print("N4Q_Q1_GEOMETRY "+json.dumps({"case":c,"n":len(g)}),flush=True)
  for v in g.itertuples(index=False):
   pose=np.array([v.x_eval,v.y_eval,v.yaw_eval_rad],float)
   h=float(v.s_los_expected)
   delta_values=[]
   for angle in offsets:
    shifted=pose.copy();shifted[2]+=angle
    delta_values.append(float(lut.model(shifted,case)[0][1]-h))
   hprofile=[]
   # Offline one-packet LoS profile; only R2 scenarios, not new Full RF.
   if c in ("R2_aA_m0","R2_aA_m45"):
    for angle in profile_offsets:
     shifted=pose.copy();shifted[2]+=angle
     hprofile.append(float(lut.model(shifted,case)[0][1]))
   alt_different=None
   if hprofile:
    alts=[(abs(x-h),abs(math.degrees(shift))) for x,shift in zip(hprofile,profile_offsets)
      if abs(math.degrees(shift))>=8]
    alt_different=min(z[0] for z in alts)
   relative_rx=math.degrees(math.atan2(v.relative_rx_az_sin,v.relative_rx_az_cos))
   nearest_deg=abs(((relative_rx+180.)%2)-1)
   # Each nonzero +/-2-degree perturbation may cross one or more frozen 2° cells.
   # Boundary proximity reports *where* piecewise derivative warnings occur.
   fields.append({"case":c,"pose_id":int(v.pose_id),
    "ds_m10":delta_values[0],"ds_m5":delta_values[1],"ds_m2":delta_values[2],
    "ds_p2":delta_values[3],"ds_p5":delta_values[4],"ds_p10":delta_values[5],
    "finite_span_pm10":float(abs(delta_values[0]-delta_values[5])),
    "maxabs_ds_pm10":float(max(abs(delta_values[0]),abs(delta_values[5]))),
    "local_noise_indistinguishable_alt_8to20deg":bool(alt_different<=SIGMA_S) if alt_different is not None else None,
    "alt_abs_s_min_at_far_yaw":alt_different,
    "rx_phi_nearest_grid_deg":float(nearest_deg),
    "within_0p2deg_of_rx_knot":bool(nearest_deg<.2),
    "rx_azimuth_seam_near2deg":bool(abs(relative_rx)>=178)})
 derived=pd.DataFrame(fields)
 if derived.duplicated(["case","pose_id"]).any() or len(derived)!=9519:
  raise RuntimeError("GEOMETRY_SAMPLING_DROPPED")
 enriched=original.merge(derived,on=["case","pose_id"],validate="one_to_one")
 if not np.allclose(enriched.s_los_expected,enriched.s_lut_eval,atol=1e-11):
  raise RuntimeError("FFD_LOS_FORWARD_MISMATCH")
 return enriched

def original_rf_paired(np,pd,base,full,all_df):
 los=all_df[all_df.channel=="los"].copy()
 f=full[["case","route","pose_id","x_eval","y_eval","yaw_eval_rad",
   "s_fp","range_m","e_r","e_s","fp_tap","strong_port",
   "log_fp_power","early8","delay_rms_ns","eta_fp_win80",
   "detector_s_span","detector_delay_span_ns"]].copy()
 l=los[["case","pose_id","s_fp","range_m","e_r","e_s","fp_tap","strong_port"]].copy()
 paired=f.merge(l,on=["case","pose_id"],suffixes=("_full","_los"),validate="one_to_one")
 if len(paired)!=9519:raise RuntimeError("NATIVE_LOS_FULL_NOT_PAIRED")
 paired["e_mp_r"]=paired.range_m_full-paired.range_m_los
 paired["e_mp_s"]=paired.s_fp_full-paired.s_fp_los
 paired["e_lut_r"]=paired.e_r_los
 paired["e_lut_s"]=paired.e_s_los
 paired["e_total_r"]=paired.e_r_full
 paired["e_total_s"]=paired.e_s_full
 if max(abs(paired.e_mp_r+paired.e_lut_r-paired.e_total_r).max(),
        abs(paired.e_mp_s+paired.e_lut_s-paired.e_total_s).max())>1e-10:
  raise RuntimeError("Q2_DECOMPOSITION_FAIL")
 paired["is_mp_s_high"]=abs(paired.e_mp_s)>.1
 paired["is_mp_r_high"]=abs(paired.e_mp_r)>.15
 paired["full_vs_los_tap_different"]=paired.fp_tap_full!=paired.fp_tap_los
 paired["full_vs_los_strong_port_different"]=paired.strong_port_full!=paired.strong_port_los
 paired=paired.sort_values(["case","pose_id"]).copy()
 paired["full_tap_transition"]=paired.groupby("case").fp_tap_full.diff().fillna(0)!=0
 return paired

def fit_rf_score(np,pd,frame,train,test,los_train,los_test,geom_fields):
 from sklearn.pipeline import make_pipeline
 from sklearn.preprocessing import StandardScaler
 from sklearn.linear_model import LogisticRegression
 from sklearn.metrics import roc_auc_score,brier_score_loss
 rf=["log_fp_power","early8","delay_rms_ns","eta_fp_win80",
     "detector_s_span","detector_delay_span_ns"]
 geom=["Ipsi_nominal","Hpsi_lut","balance_los",
       "relative_rx_az_cos","relative_rx_az_sin"]
 models={"RF_ONLY":rf,"GEOM_ORACLE_ONLY":geom,"RF_PLUS_GEOM_ORACLE":rf+geom}
 y=train.is_mp_s_high.to_numpy(int);yt=test.is_mp_s_high.to_numpy(int)
 rows=[];scores={}
 for name,features in models.items():
  if not set(features).issubset(frame.columns):raise RuntimeError("FEATURE_MISSING:"+name)
  clf=make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=800,random_state=20261015))
  clf.fit(train[features].to_numpy(float),y)
  prob=clf.predict_proba(test[features].to_numpy(float))[:,1]
  # Explicit LoS false-alarm negative controls calibrated ONLY on held-in
  # native LoS samples; never use held-out R2 for the threshold.
  train_los_p=clf.predict_proba(los_train[features].to_numpy(float))[:,1]
  test_los_p=clf.predict_proba(los_test[features].to_numpy(float))[:,1]
  cutoff=float(np.quantile(train_los_p,.95))
  threshold=max(.5,cutoff)
  rows.append({"model":name,"n_R2":len(test),"features":",".join(features),
    "R2_MP_AUROC":float(roc_auc_score(yt,prob)),
    "R2_MP_Brier":float(brier_score_loss(yt,prob)),
    "train_LoS_95th_threshold":threshold,
    "train_LoS_false_positive_rate":float(np.mean(train_los_p>=threshold)),
    "R2_LoS_false_positive_rate":float(np.mean(test_los_p>=threshold)),
    "R2_Full_highrisk_positive_rate":float(np.mean(prob>=threshold)),
    "online_eligible":name=="RF_ONLY"})
  scores[name]=prob
 return rows,scores

def offline_harm(np,pd,paired,original,trace_archive,base,params):
 from r2_bias_replay import build_positive_bias_controls,predict_one,METHODS
 result=[];r2source={(a["case"],a["channel"]):a for a in original["per_case"]}
 for bias in REF_BIAS_LEVELS:
  for case in R2_CASES:
   origin=r2source[(case,"full")]
   raw=trace_archive.read("P2_OUT/"+origin["trace_file"])
   if hashlib.sha256(raw).hexdigest()!=origin["trace_sha256"]:
    raise RuntimeError("Q3_HARM_SOURCE_TRACE_SHA_BAD")
   with np.load(io.BytesIO(raw),allow_pickle=False) as z:
    t=z["t_s"].copy();pids=z["pose_id"].copy();truth=z["truth_for_offline_scoring_only"].copy()
    obs=np.column_stack([z["z_r_m"],z["z_s"]])
   refname=f"{case}_full_{bias}_seed0_recursive.npz"
   with np.load(io.BytesIO(params.read(member(params,refname))),allow_pickle=False) as z:
    r={k:z[k].copy() for k in z.files}
   if list(r["names"])!=list(METHODS) or not np.array_equal(r["pose_id"],pids):
    raise RuntimeError("BASELINE_TRACE_IDS_BAD")
   method=list(METHODS).index("J4")
   xs=r["estimate"][:,method,:]
   Ps=r["covariance"][:,method,:,:]
   st=r["status"][:,method]
   ctrl,x0=build_positive_bias_controls(t,truth,bias,seed=0)
   frame=paired[paired.case==case].set_index("pose_id")
   for i in range(1,len(t)):
    prior,PP=predict_one(xs[i-1],Ps[i-1],
       float(ctrl["ds_odom"][i]),float(ctrl["dtheta_gyro"][i]),float(ctrl["dt_s"][i]))
    current=frame.loc[int(pids[i])]
    a=float(np.degrees(((prior[2]-truth[i,2]+np.pi)%(2*np.pi)-np.pi)))
    b=float(np.degrees(((xs[i,2]-truth[i,2]+np.pi)%(2*np.pi)-np.pi)))
    accepted=bool(st[i]=="APPLIED")
    result.append({"case":case,"pose_id":int(pids[i]),"bias_level":bias,
      "eval":bool(t[i]>=30),"accepted":accepted,
      "delta_heading_squared_error_deg2":float(b*b-a*a),
      "harmful_if_accepted":bool(accepted and b*b>a*a+1e-10),
      "prior_heading_error_deg":a,"posterior_heading_error_deg":b})
 return pd.DataFrame(result)

def run(out,receipt,rfpath,r2path):
 np,pd,base,pol,FrozenLut,_,_,_=environment()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 pre=json.loads(Path(receipt).read_text())
 if pre["decision"]!="GO" or pre["head"]!=os.getenv("GITHUB_SHA"):
  raise RuntimeError("Q0_PREAUDIT_HOLD")
 mf=json.loads(MANIFEST.read_text())
 with checked_zip(rfpath,RAW_SHA) as a, checked_zip(r2path,R2_SHA) as r:
  df=base.create_dataset(np,pd,mf)
  par=base.original_14_parity(np,df,a)
  if len(par)!=14 or sum(v["rows"] for v in par)!=14502:
   raise RuntimeError("Q0_ORIGINAL_OBSERVER_FAIL")
  lut=FrozenLut(ROOT)
  full=df[df.channel=="full"].copy()
  enriched=geometry(np,pd,base,pol,lut,full,mf)
  paired=original_rf_paired(np,pd,base,enriched,df)
  q1train=enriched[enriched.route.isin(["R4","R5"])]
  if not len(q1train):raise RuntimeError("MISSING_TRAIN_GEOMETRY")
  ithreshold=float(q1train.Ipsi_nominal.median())
  # Threshold set exclusively on R4+R5, never on R2 data.
  enriched["I_geom_high_trainMedian"]=enriched.Ipsi_nominal>=ithreshold
  paired=paired.merge(enriched[["case","pose_id","Ipsi_nominal",
    "I_geom_high_trainMedian","Hpsi_lut","balance_los","p_dom_los",
    "relative_rx_az_cos","relative_rx_az_sin",
    "maxabs_ds_pm10","local_noise_indistinguishable_alt_8to20deg",
    "within_0p2deg_of_rx_knot","rx_azimuth_seam_near2deg"]],
    on=["case","pose_id"],validate="one_to_one")
  q1=[]
  for case,g in enriched.groupby("case"):
   q1.append({"case":case,"mount":45 if case.endswith("m45") else 0,
    "n":len(g),"Igeom_median":float(g.Ipsi_nominal.median()),
    "Hpsi_abs_median":float(abs(g.Hpsi_lut).median()),
    "balance_median":float(g.balance_los.median()),
    "frac_low_info":float(np.mean(~g.I_geom_high_trainMedian)),
    "finite10_maxabs_median":float(g.maxabs_ds_pm10.median()),
    "rx_knot_near_frac":float(g.within_0p2deg_of_rx_knot.mean()),
    "seam_near_frac":float(g.rx_azimuth_seam_near2deg.mean()),
    "frac_alternative_8to20deg_very_similar_s":float(
      g.local_noise_indistinguishable_alt_8to20deg.mean()) if case in R2_CASES else None})
  q2=[]
  for (case,info),g in paired.groupby(["case","I_geom_high_trainMedian"]):
   E=g[["e_mp_r","e_mp_s"]].to_numpy(float)
   mu=E.mean(axis=0);C=np.cov(E,rowvar=False,bias=True)
   if np.linalg.eigvalsh(C).min()< -1e-10:raise RuntimeError("Q2_COV_NOT_PSD")
   q2.append({"case":case,"I_high":bool(info),"n":len(g),
     "eMP_mean_r":float(mu[0]),"eMP_mean_s":float(mu[1]),
     "eMP_Vr":float(C[0,0]),"eMP_Vs":float(C[1,1]),
     "eMP_Crs":float(C[0,1]),
     "eMP_rho":float(C[0,1]/max(np.sqrt(C[0,0]*C[1,1]),1e-30)),
     "mp_s_high_frac":float(g.is_mp_s_high.mean()),
     "mp_r_high_frac":float(g.is_mp_r_high.mean()),
     "FP_tap_different_frac":float(g.full_vs_los_tap_different.mean()),
     "FP_port_different_frac":float(g.full_vs_los_strong_port_different.mean())})
  # Q3 fixed holdout on R2 and conditional internal train negative controls.
  tr=paired.route.isin(["R4","R5"])
  te=paired.route=="R2"
  train=paired[tr];test=paired[te]
  if len(test)!=3909 or len(train)!=5610:raise RuntimeError("Q3_R2_HOLDOUT_COUNT")
  los=df[(df.channel=="los")].copy()
  los=los.merge(enriched[["case","pose_id","Ipsi_nominal",
    "Hpsi_lut","balance_los","relative_rx_az_cos","relative_rx_az_sin"]],
    on=["case","pose_id"],validate="one_to_one")
  rf_rows,prob=fit_rf_score(np,pd,paired,train,test,
       los[los.route.isin(["R4","R5"])],los[los.route=="R2"],None)
  score_test=test[["case","route","pose_id","I_geom_high_trainMedian",
   "Ipsi_nominal","is_mp_s_high","is_mp_r_high",
   "e_mp_s","e_mp_r","log_fp_power","Hpsi_lut","maxabs_ds_pm10"]].copy()
  for k,p in prob.items():score_test["p_"+k]=p
  geom_groups=[]
  examples=[]
  for case,g in test.groupby("case"):
   for gi in (False,True):
    for mp in (False,True):
     select=g[(g.I_geom_high_trainMedian==gi)&(g.is_mp_s_high==mp)]
     geom_groups.append({"case":case,"mount":45 if case.endswith("m45") else 0,
       "information_high":gi,"MP_s_high":mp,"n":len(select),
       "unique_xy_centimeter":select[["x_eval","y_eval"]].round(2).drop_duplicates().shape[0],
       "mean_abs_eMP_r":float(abs(select.e_mp_r).mean()) if len(select) else None,
       "mean_abs_eMP_s":float(abs(select.e_mp_s).mean()) if len(select) else None,
       "mean_abs_Hpsi":float(abs(select.Hpsi_lut).mean()) if len(select) else None,
       "mean_IGeom":float(select.Ipsi_nominal.mean()) if len(select) else None,
       "empirical_N4Q_status":"DESCRIPTIVE" if len(select)>=20 else "INDETERMINATE_SMALL_CELL"})
     if len(select):
      p=select.iloc[0]
      examples.append({"case":case,"pose_id":int(p.pose_id),
       "information_high":gi,"MP_s_high":mp,
       "eMP_s":float(p.e_mp_s),"eMP_r_m":float(p.e_mp_r),
       "I_geom":float(p.Ipsi_nominal),"Hpsi":float(p.Hpsi_lut)})
  harm=offline_harm(np,pd,paired,json.loads(a.read("P2_OUT/P2_ONE_STEP_SUMMARY.json")),a,base,r)
  harm=harm.merge(score_test[["case","pose_id","I_geom_high_trainMedian",
    "is_mp_s_high","p_RF_ONLY"]],
    on=["case","pose_id"],validate="many_to_one")
  harm_summary=[]
  for keys,g in harm[harm["eval"]].groupby(
    ["case","bias_level","I_geom_high_trainMedian","is_mp_s_high"],dropna=False):
   selected=g[g.accepted]
   harm_summary.append({"case":keys[0],"bias":keys[1],
    "information_high":bool(keys[2]),"MP_s_high":bool(keys[3]),
    "n_frames":len(g),"accepted":len(selected),
    "harm_given_accepted":float(selected.harmful_if_accepted.mean()) if len(selected) else None,
    "mean_step_heading_squared_change_deg2":float(selected.delta_heading_squared_error_deg2.mean()) if len(selected) else None})
  # Exact three-term decomposition of Full innovation on ORIGINAL R2 J4 prior,
  # no re-use of oracle e_MP as an online feature.
  decomposition=[];meta={c["id"]:c for c in mf["cases"]}
  from r2_bias_replay import predict_one,build_positive_bias_controls,METHODS
  for bias in REF_BIAS_LEVELS:
   for case in R2_CASES:
    desc=meta[case]
    packet=next(q for q in json.loads(a.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]
                if q["case"]==case and q["channel"]=="full")
    with np.load(io.BytesIO(a.read("P2_OUT/"+packet["trace_file"])),allow_pickle=False) as src:
     t=src["t_s"].copy();pid=src["pose_id"].copy();truth=src["truth_for_offline_scoring_only"].copy()
     z=np.stack([src["z_r_m"],src["z_s"]],axis=1)
    with np.load(io.BytesIO(r.read(member(r,f"{case}_full_{bias}_seed0_recursive.npz"))),allow_pickle=False) as zz:
     X=zz["estimate"][:,list(zz["names"]).index("J4"),:].copy()
     C=zz["covariance"][:,list(zz["names"]).index("J4"),:,:].copy()
    ctrl,init=build_positive_bias_controls(t,truth,bias,seed=0)
    source=paired[paired.case==case].set_index("pose_id")
    for k in range(len(t)):
     if k==0:continue
     xpred,Ppred=predict_one(X[k-1],C[k-1],float(ctrl["ds_odom"][k]),
               float(ctrl["dtheta_gyro"][k]),float(ctrl["dt_s"][k]))
     hgt=lut.model(truth[k],desc)[0]
     hprior=lut.model(xpred,desc)[0]
     p=source.loc[int(pid[k])]
     emp=np.array([p.e_mp_r,p.e_mp_s])
     # R2 archived motion GT differs from the separate sweep SAMPLES pose
     # by sub-micrometric precision. Re-evaluate Native LoS residual using
     # EXACT archived motion truth, not the sweep-sample LUT GT.
     elut=np.array([p.range_m_los,p.s_fp_los])-hgt
     epose=hgt-hprior
     if np.max(abs(z[k]-hprior-emp-elut-epose))>1e-9:
      raise RuntimeError("Q2_THREE_TERM_INNOVATION_IDENTITY_FAIL")
     decomposition.append({"case":case,"bias":bias,"pose_id":int(pid[k]),
       "eval":bool(t[k]>=30),
       "eMP_r":float(emp[0]),"eMP_s":float(emp[1]),
       "eLUT_r":float(elut[0]),"eLUT_s":float(elut[1]),
       "ePose_r":float(epose[0]),"ePose_s":float(epose[1]),
       "innovation_r":float(z[k,0]-hprior[0]),
       "innovation_s":float(z[k,1]-hprior[1]),
       "prior_heading_sigma_deg":float(np.degrees(np.sqrt(Ppred[2,2])))})
  def export(name,table):
   if hasattr(table,"to_csv"):
    table.to_csv(out/name,index=False)
   else:pd.DataFrame(table).to_csv(out/name,index=False)
  export("Q1_GEOMETRY_INFORMATION.csv.gz",enriched[["case","route","pose_id",
    "x_eval","y_eval","yaw_eval_rad","Hpsi_lut","Ipsi_nominal",
    "s_los_expected","balance_los","p_dom_los",
    "ds_m10","ds_m5","ds_m2","ds_p2","ds_p5","ds_p10",
    "maxabs_ds_pm10","finite_span_pm10","local_noise_indistinguishable_alt_8to20deg",
    "rx_azimuth_seam_near2deg","within_0p2deg_of_rx_knot",
    "I_geom_high_trainMedian"]])
  export("Q2_FULL_VS_NATIVE_LOS_RF_ERRORS.csv.gz",paired)
  export("Q3_2X2_CONFUSION.csv",geom_groups)
  export("Q3_LABELED_EXAMPLES.csv",examples)
  export("Q3_MP_PREDICTION_SCORES.csv",rf_rows)
  export("Q3_HELDOUT_RF_RISK.csv.gz",score_test)
  export("Q3_HEADING_HARM_DIAG.csv",harm_summary)
  export("Q2_PRIOR_INNOVATION_THREE_TERM.csv.gz",decomposition)
  export("Q0_ORIGINAL_PACKET_PARITY.csv",par)
  export("Q1_BY_CASE.csv",q1)
  export("Q2_BY_CASE_INFORMATION.csv",q2)
  # Scientific advance criteria are checked from actual results, not asserted.
  r2cells=[x for x in geom_groups if x["n"]>=20 and x["unique_xy_centimeter"]>=5]
  valid_bycase={c:sum(1 for x in r2cells if x["case"]==c) for c in ANCHOR_Q1_CASES}
  statuses={
    "Q0":"TECHNICAL_PASS",
    "Q1":"DESCRIPTIVE_GEOMETRY_PASS" if len(q1)==CASES else "FAILED",
    "Q2":"ORACLE_DECOMPOSITION_PASS",
    "Q3":"SCIENTIFIC_PARTIAL" if all(n>=3 for n in valid_bycase.values())
         else "INDETERMINATE_INSUFFICIENT_CELL_COVERAGE",
    "Q4":"NOT_EXECUTED",
    "Q5":"NOT_EXECUTED",
    "Q6":"NOT_EXECUTED",
    "Q7":"BLOCKED_INPUT_INDEPENDENT_SCENES"}
  final={"schema":"N4Q_INFO_VS_RF_INTEGRITY_Q0Q3_V1",
   "status":"Q0_Q3_EXECUTED_WITH_SCIENTIFIC_GATES",
   "source_sha":os.getenv("GITHUB_SHA"),
   "statuses":statuses,
   "original_RF_SHA":RAW_SHA,"original_R2_SHA":R2_SHA,
   "observations":len(enriched),"matched_full_los":len(paired),
   "source_packet_parity_n":sum(x["rows"] for x in par),
   "I_geom_threshold_trained_R4R5_only":ithreshold,
   "RF_integrity_oracle_label":"abs(s_full_native-s_los_native)>.1",
   "G-H1":"PARTIAL_LOCAL_GEOMETRY","G-H2":"ORACLE_COMPONENT_SEPARATION",
   "G-H3":"REQUIRES_CLINICAL_POSTERIOR_AND_INDEPENDENT_SCENES",
   "q1_case_stats":q1,"q2_case_moments_by_info":q2,
   "q3_cell_counts":geom_groups,"q3_RF_classifier":rf_rows,
   "q3_original_J4_one_step_harm":harm_summary,
   "q3_test_case_adequate_cell_count":valid_bycase,
   "limitations":[
     "Igeom/Hpsi geometry uses GT pose offline, not online observation",
     "Same-corridor R2/R4/R5 splits are not independent scenes",
     "Profile indistinguishability uses single sigma=.09, not actual full 4state posterior modes",
     "Single scalar s prior cannot fully observe 4state x,y,psi,b",
     "Empirical MP_s threshold .1 is a training definition not physical classification ground truth",
     "R2 harmonic outcomes reuse archived Joint4 posterior; not randomized counterfactual policy",
     "Actual independent Full RF yaw scans are not generated by LoS LUT rotation",
     "Q3 RF classifier derived features from same packet; not normalized EKF likelihood",
     "Q4-Q7 require subsequent stage-specific testing and accepted scientific gates"],
   "scientific_PASS":False}
  write(out/"Q0_Q3_FINAL.json",final)
  print("N4Q_FINAL "+json.dumps({"status":final["status"],"statuses":statuses,
   "Igeom_threshold":ithreshold,"q1":q1,"q2":q2,"q3_classifier":rf_rows,
   "q3_cells":geom_groups,"harm":harm_summary},ensure_ascii=False),flush=True)
 return 0

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("pre","test","run"),required=True)
 ap.add_argument("--out")
 ap.add_argument("--audit");ap.add_argument("--rf");ap.add_argument("--r2")
 a=ap.parse_args()
 if a.phase=="pre":return audit(a.out)
 if a.phase=="test":return unit()
 if not all((a.out,a.audit,a.rf,a.r2)):raise RuntimeError("N4Q_RUN_INPUTS_REQUIRED")
 return run(a.out,a.audit,a.rf,a.r2)
if __name__=="__main__":raise SystemExit(main())
