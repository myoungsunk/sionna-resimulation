"""N4-Q4: oracle-versus-actual pre-RF DR4/J4 geometric observability.

This is an independent diagnostic of frozen R2 posterior histories. GT is
scoring-only except the original frozen sensor-v2 control generator.
Positive-weight cubature (6 sigma points in x/y/yaw) propagates prior
uncertainty through actual nonlinear frozen FFD/LUT. No new filter policy
or RF sensor likelihood is introduced.
"""
from __future__ import annotations
import argparse,ast,csv,gzip,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
POL=ROOT/"research/R5_N4B_POL_V1_20261015"
SOURCE={
 "research/N4_Q_GEOM_RF_20261015/q0q3_geometry_integrity.py":"dde4e5f20ef16b5c1b61e47a9728307b8b9a13eb",
 "research/R5_N4B_POL_V1_20261015/n4b_pol_geometry.py":"565d6f2704f40f770da5f70a40314141a3d621a1",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9"
}
UPSTREAM="748b7d1b91e06b1825fdd49bc10bf387fae3786aebd63eac18f194e275170d67"
RAW_RF="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_SHA="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
CASES=("R2_aA_m0","R2_aA_m45")
METHODS=("DR4","J4")
CHANNELS=("full","los")
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(p):
 p=Path(p);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(p,v):
 Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def pre(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 err=[];head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if os.getenv("GITHUB_ACTIONS")!="true":err.append("REQUIRE_ACTIONS")
 if head!=os.getenv("GITHUB_SHA"):err.append("WRONG_COMMIT")
 for p,exp in SOURCE.items():
  file=ROOT/p
  if not file.is_file():err.append("SOURCE_MISSING:"+p)
  elif blob(file)!=exp:err.append("SOURCE_CHANGED:"+p)
 try:ast.parse((HERE/"q4_prior_observability.py").read_text())
 except Exception as e:err.append("SCRIPT_SYNTAX:"+repr(e))
 wf=ROOT/".github/workflows/n4q-q4-prior.yml"
 if not wf.exists():err.append("WORKFLOW_MISSING")
 else:
  s=wf.read_text()
  if not(0<=s.find("q4_prior_observability.py --phase pre")<
         s.find("q4_prior_observability.py --phase test")<
         s.find("q4_prior_observability.py --phase run") and
         "if: always()" in s and "actions: read" in s):
   err.append("AUDIT_ORDER")
 rec={"status":"Q4_SOURCE_AUDIT","decision":"GO" if not err else "HOLD",
      "head":head,"original_Q0Q3_SHA":UPSTREAM,"original_R2_SHA":R2_SHA,
      "errors":err,"scientific_PASS":False}
 save(out/"Q4_PRE_AUDIT.json",rec)
 print("Q4_PRE "+json.dumps({"decision":rec["decision"],"errors":err}),flush=True)
 return 0 if not err else 2
def zcheck(p,digest):
 if sha(p)!=digest:raise RuntimeError("ARCHIVE_SOURCE_CHANGED:"+str(p))
 z=zipfile.ZipFile(p)
 if z.testzip():raise RuntimeError("ARCHIVE_CRC_ERROR")
 return z
def member(z,name):
 hits=[p for p in z.namelist() if p==name or p.endswith("/"+name)]
 if len(hits)!=1:raise RuntimeError("MISSING_OR_DUPLICATE:"+name)
 return hits[0]
def environment():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
  str(ROOT/"research/R5_N4B_20261015"),
  str(ROOT/"research/R5_N4B_POL_V1_20261015"),
  str(ROOT/"research/R5_FULLRF_B0_GATES_20261015"),
  str(ROOT/"research/PHYSICS_RS_STAGED_20261015/code"),
  str(BASE),
  str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src")
 ]
 from p3_rf_adapter4 import FrozenLut
 from r2_bias_replay import predict_one,build_positive_bias_controls,METHODS,INITIAL_POSE_STD,BIAS_PRIOR_STD
 import n4b_pol_geometry as pol
 return np,pd,FrozenLut,pol,predict_one,build_positive_bias_controls,METHODS,INITIAL_POSE_STD,BIAS_PRIOR_STD
def sigma_points(np,mean,P):
 x=np.asarray(mean,float)
 P=np.asarray(P,float)
 if x.shape!=(3,) or P.shape!=(3,3):raise RuntimeError("POSE_DIMENSIONS")
 sym=(P+P.T)*.5
 if np.linalg.eigvalsh(sym).min()<=0:raise RuntimeError("POSE_COV_NOT_PD")
 L=np.linalg.cholesky(sym)*math.sqrt(3)
 return np.asarray([x+L[:,i]*sign for i in range(3) for sign in (-1,1)])
def test():
 np,pd,Lut,pol,*_=environment()
 rng=np.random.default_rng(14)
 for j in range(10):
  P=rng.normal(size=(3,3));P=P@P.T*.01+.003*np.eye(3)
  mu=rng.normal(size=3)
  points=sigma_points(np,mu,P)
  np.testing.assert_allclose(points.mean(axis=0),mu,atol=1e-12)
  np.testing.assert_allclose(np.cov(points,rowvar=False,bias=True),P,atol=1e-12)
 lut=Lut(ROOT)
 case={"anchor":[4,0,2.65],"mount_deg":0,"robot_z_m":.45}
 x=np.array([2.,-.5,.2])
 P=np.diag([.02,.02,math.radians(5.)**2])
 q=sigma_points(np,x,P)
 for y in q:
  v=pol.physical_features(np,lut,y,case)
  assert np.isfinite(v["s_los_expected"]) and v["Ipsi_nominal"]>=0
 print("Q4_UNIT_PASS "+json.dumps({"cubature_covariance_tests":10,"FFD_sigma_probes":len(q)}),flush=True)
 return 0
def wrap(np,x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi
def measure_quality(np,lut,pol,mean,cov,case,cutoff):
 # Fixed reference info label: the geometry-only quantity is NOT allowed
 # to depend on learned sensor covariance or biased packet observations.
 point=pol.physical_features(np,lut,mean,case)
 effective=pol.physical_features(np,lut,mean,case,cov)
 samples=sigma_points(np,mean[:3],cov[:3,:3])
 q=[pol.physical_features(np,lut,s,case) for s in samples]
 isamp=np.asarray([k["Ipsi_nominal"] for k in q],float)
 ssamp=np.asarray([k["s_los_expected"] for k in q],float)
 hsam=np.asarray([k["Hpsi_lut"] for k in q],float)
 qprob=float(np.mean(isamp>=cutoff))
 return {
  "I_geom_point":float(point["Ipsi_nominal"]),
  "Iop_prior_ref_Rs":float(effective["Ipsi_nominal"]),
  "p_info_high_cubature":qprob,
  "point_info_high":bool(point["Ipsi_nominal"]>=cutoff),
  "Igeom_cubature_mean":float(isamp.mean()),
  "Igeom_cubature_std":float(isamp.std()),
  "LoS_s_cubature_mean":float(ssamp.mean()),
  "LoS_s_cubature_std":float(ssamp.std()),
  "Hpsi_cubature_mean":float(hsam.mean()),
  "Hpsi_cubature_std":float(hsam.std()),
  "s_point":float(point["s_los_expected"]),
 }
def execute(out,pre,q0,r2path,rfpath):
 np,pd,Lut,pol,predict,controls_fn,METHS,POSESTD,BSTD=environment()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 a=json.loads(Path(pre).read_text())
 if a["decision"]!="GO" or a["head"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("PRE_AUDIT_HOLD")
 lut=Lut(ROOT)
 source={}
 with zcheck(q0,UPSTREAM) as zq,zcheck(r2path,R2_SHA) as zr,zcheck(rfpath,RAW_RF) as zf:
  qbase=json.loads(zq.read(member(zq,"Q0_Q3_FINAL.json")))
  if qbase["statuses"]["Q0"]!="TECHNICAL_PASS" or \
     qbase["statuses"]["Q3"] not in ("SCIENTIFIC_PARTIAL","DESCRIPTIVE_GEOMETRY_PASS"):
   raise RuntimeError("Q3_SCIENTIFIC_GATE_HOLD")
  cutoff=float(qbase["I_geom_threshold_trained_R4R5_only"])
  with gzip.open(io.BytesIO(zq.read(member(zq,"Q1_GEOMETRY_INFORMATION.csv.gz"))),"rt",encoding="utf8") as f:
   qgeom=pd.read_csv(f)
  gtinfo=qgeom.set_index(["case","pose_id"])
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  cm={c["id"]:c for c in manifest["cases"]}
  source={(s["case"],s["channel"]):s
      for s in json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  data=[]
  for case in CASES:
   for channel in CHANNELS:
    src=source[(case,channel)]
    raw=zf.read("P2_OUT/"+src["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=src["trace_sha256"]:
     raise RuntimeError("ORIGINAL_RF_PACKET_SHA_MISMATCH")
    with np.load(io.BytesIO(raw),allow_pickle=False) as z:
     times=z["t_s"].copy();ids=z["pose_id"].copy()
     truth=z["truth_for_offline_scoring_only"].copy()
    for bias in BIAS:
     ctrl,x0=controls_fn(times,truth,bias,seed=0)
     old=f"{case}_{channel}_{bias}_seed0_recursive.npz"
     with np.load(io.BytesIO(zr.read(member(zr,old))),allow_pickle=False) as z:
      archived={k:z[k].copy() for k in z.files}
     if not np.array_equal(archived["t_s"],times) or not np.array_equal(archived["pose_id"],ids):
      raise RuntimeError("ORIGINAL_IDS_CHANGED")
     for family in METHODS:
      method=list(METHS).index(family)
      xs=archived["estimate"][:,method,:]
      Ps=archived["covariance"][:,method,:,:]
      if xs.shape!=(979,4) or Ps.shape!=(979,4,4):
       raise RuntimeError("ORIGINAL_FILTER_SHAPE_CHANGED")
      for k in range(1,len(times)):
       if times[k]<30:continue
       delta,gyro,dt=(float(ctrl[v][k]) for v in ("ds_odom","dtheta_gyro","dt_s"))
       xprev,Pprev=predict(xs[k-1],Ps[k-1],delta,gyro,dt)
       geom_gt=gtinfo.loc[(case,int(ids[k]))]
       obs=measure_quality(np,lut,pol,xprev,Pprev,cm[case],cutoff)
       oracle=float(geom_gt["Ipsi_nominal"])
       oracle_high=oracle>=cutoff
       pred_s_gt=float(lut.model(truth[k],cm[case])[0][1])
       sdiff=obs["LoS_s_cubature_mean"]-pred_s_gt
       sigma=max(obs["LoS_s_cubature_std"],1e-12)
       data.append({
        "case":case,"channel":channel,"bias":bias,"prior_family":family,
        "t_s":float(times[k]),"pose_id":int(ids[k]),
        "mount_deg":int(cm[case]["mount_deg"]),
        "truth_geom_info":oracle,"truth_info_high":bool(oracle_high),
        "GT_yaw_deg":float(np.degrees(truth[k,2])),
        "prior_yaw_error_deg":float(np.degrees(wrap(np,xprev[2]-truth[k,2]))),
        "prior_yaw_std_deg":float(np.degrees(np.sqrt(Pprev[2,2]))),
        "prior_geom_label_wrong":bool(obs["point_info_high"]!=oracle_high),
        "cubature_prob_squared_error":float((obs["p_info_high_cubature"]-float(oracle_high))**2),
        "point_label_squared_error":float((float(obs["point_info_high"])-float(oracle_high))**2),
        "cubature_s_LOS_mean_minus_truth":sdiff,
        "cubature_s_coverage95_geometry_only":bool(abs(sdiff)<=1.96*sigma),
        **obs
       })
       if (k==1 or k==len(times)-1) and channel=="full":
        print("Q4_CASE_PROGRESS "+json.dumps({"case":case,"bias":bias,
            "prior":family,"k":k}),flush=True)
 df=pd.DataFrame(data)
 if not len(df):raise RuntimeError("Q4_NO_DATA")
 df.to_csv(out/"Q4_PRIOR_GEOMETRY_FULL_RECORDS.csv.gz",
      index=False,compression="gzip")
 stats=[]
 for key,sub in df.groupby(["case","channel","bias","prior_family"]):
  stats.append({"case":key[0],"channel":key[1],"bias":key[2],"method":key[3],
    "n":len(sub),"oracle_Info_median":float(sub.truth_geom_info.median()),
    "prior_Info_median":float(sub.I_geom_point.median()),
    "actual_Iop_prior_median":float(sub.Iop_prior_ref_Rs.median()),
    "mean_abs_prior_heading_error_deg":float(abs(sub.prior_yaw_error_deg).mean()),
    "mean_prior_heading_sigma_deg":float(sub.prior_yaw_std_deg.mean()),
    "prior_geometric_highlow_flip_rate":float(sub.prior_geom_label_wrong.mean()),
    "cubature_brier_vs_GT_geom_label":float(sub.cubature_prob_squared_error.mean()),
    "point_label_brier_vs_GT_geom_label":float(sub.point_label_squared_error.mean()),
    "s_LoS_GT_coverage95_from_prior_cubature":float(sub.cubature_s_coverage95_geometry_only.mean()),
    "mean_sigma_s_geom":float(sub.LoS_s_cubature_std.mean())})
 pd.DataFrame(stats).to_csv(out/"Q4_PRIOR_VS_ORACLE_STATS.csv",index=False)
 focus=[s for s in stats if s["channel"]=="full" and s["method"]=="J4"]
 output={"schema":"N4Q_Q4_GEOMETRY_PRIOR_UNCERTAINTY_V1",
   "status":"Q4_PRIOR_SIXPOINT_CUBATURE_COMPLETE",
   "source_commit":os.getenv("GITHUB_SHA"),
   "source_Q0Q3_sha":UPSTREAM,"source_R2_sha":R2_SHA,
   "total_evaluated_records":len(df),
   "nominal_information_threshold_from_R4R5":cutoff,
   "full_J4_focus":focus,
   "scientific_PASS":False,
   "limitations":[
     "Actual DR4/J4 prior histories are frozen from original R2 filters, not proposed policy closed loop",
     "Cubature has 6 positive-weight Gaussian points in [x,y,psi]; poor Gaussian posterior can under-cover",
     "Oracle labels measure geometry class, not true Heading posterior Bayes information",
     "Prior model uses nominal reference R_s not physics-calibrated R_s",
     "Cubature comparison is a calibration negative control, not proof of online model improvement",
     "Original RF is one corridor, one multipath realization, one seed; no independent scenes"
   ]}
 save(out/"Q4_FINAL.json",output)
 print("Q4_FINAL "+json.dumps({"status":output["status"],
   "n":len(df),"full_J4_focus":focus}),flush=True)
 return 0
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--phase",choices=("pre","test","run"),required=True)
 p.add_argument("--out");p.add_argument("--audit");p.add_argument("--q0");p.add_argument("--r2");p.add_argument("--rf")
 a=p.parse_args()
 return pre(a.out) if a.phase=="pre" else test() if a.phase=="test" else execute(a.out,a.audit,a.q0,a.r2,a.rf)
if __name__=="__main__":raise SystemExit(main())
