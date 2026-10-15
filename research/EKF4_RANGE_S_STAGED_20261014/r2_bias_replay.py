"""R2 mount 0/45 Gyro-bias B0/L0/L1/L2 paired one-step AND recursive comparison.

FROZEN RF z_s / raw range from prior validated 14 trace, 979 R2 frames.
The only motion perturbation changed between levels is positive Gyro bias:
other deterministic gyro/wheel drift set zero, slip disabled, same original
sensor-v2 wheel/gyro white noise streams and initial errors (seed=0).
Simulator input builder reads truth only for generating truth-consistent
motion, NEVER inside run_filters (estimator receives controls and raw RF only).
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os,sys,traceback
from pathlib import Path
from datetime import datetime,timezone
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"))
from qclean_uwb.drivesim.sensor_v2 import SensorV2Config,generate,motion_increments,rng
from qclean_uwb.drivesim.sensors import DRIFT_LEVELS
from core import predict,gaussian_update,wrap
from p3_rf_adapter4 import FrozenLut,R0,RS,RR,GATE_JOINT
from p3_frozen_inputs import open_verified_archive,load_frozen_rf_trace
from r2_bias_audit import ARCHIVE,ROOT as AUDIT_ROOT

BIAS_LEVELS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
CASES=("R2_aA_m0","R2_aA_m45")
CHANNELS=("los","full")
METHODS=("DR3","DR4","S3","S4","J3","J4","SR3","SR4")
MODES=("one_step","recursive")
INITIAL_POSE_STD=np.array([.1,.1,math.radians(5.)])
BIAS_PRIOR_STD=math.radians(.1)
SEED=0
GATE_S=6.6348966010212145
# Require P3 frozen original archive SHA for every replay.
def sha_file(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for v in iter(lambda:f.read(1<<20),b""):h.update(v)
 return h.hexdigest()

def verify_audit(path):
 x=json.loads(Path(path).read_text())
 if x["decision"]!="GO" or x["git_sha"]!=os.environ.get("GITHUB_SHA"):
  raise RuntimeError("R2_BIAS_SOURCE_AUDIT_NOT_GO")
 for rel,h in x["source_sha256"].items():
  if sha_file(ROOT/rel)!=h:raise RuntimeError("SOURCE_CHANGED_AFTER_AUDIT:"+rel)
 return x

def build_positive_bias_controls(t,pose,level_name,seed=SEED):
 """This is sensor simulation, NOT inference. true pose stays outside run_filters."""
 if level_name not in BIAS_LEVELS:raise ValueError(level_name)
 b=BIAS_LEVELS[level_name]
 ds,dtheta=motion_increments(t,pose,convention="legacy-euler")
 if level_name=="B0":
  cfg=SensorV2Config(level=1,condition="noise_pair",
                      common_scale=0.,bias_rw_rad_s_sqrt_s=0.)
  inputs,offline=generate(t,ds,dtheta,cfg,seed)
 else:
  cfg=SensorV2Config(level=["L0","L1","L2"].index(level_name),
                     condition="all",slip_mode="off",
                     common_scale=0.,bias_rw_rad_s_sqrt_s=0.)
  params={"gyro_bias":math.radians(b),"gyro_sf":0.,
          "wheel_asymmetry":0.,"wheelbase":0.,"common_scale":0.}
  inputs,offline=generate(t,ds,dtheta,cfg,seed,parameters=params)
 actual_bias=np.asarray(offline["true_bias_rad_s"])
 if np.max(abs(actual_bias-math.radians(b)))>1e-14:
  raise RuntimeError("SENSOR_TRUE_BIAS_NOT_FROZEN")
 x0=np.asarray(pose[0]+rng(seed,"initial").standard_normal(3)*INITIAL_POSE_STD)
 x0[2]=float(wrap(x0[2]))
 # noise streams and initial pose are shared across levels, channels & mounts.
 return {key:np.asarray(inputs[key]).copy() for key in ("t_s","dt_s","ds_odom","dtheta_gyro")},x0

def predict_one(x,P,ds,gyro,dt):
 n=len(x)
 if n==4:
  q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
 else:
  q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt])
 xp,pp,_,_=predict(x,P,float(ds),float(gyro),float(dt),q)
 return xp,pp

def filter_one(x,P,z,alg,case,lut):
 """One raw RF measurement per named arm; no truth, no shared gate mask."""
 if alg.startswith("DR"):
  return x.copy(),P.copy(),"DR_ONLY",math.nan
 model=lambda q:lut.model(q,case)
 if alg.startswith("S"):
  m=lambda q:(model(q)[0][1:],model(q)[1][1:,:])
  xp,pp,diag=gaussian_update(x,P,z[1:],m,R0[1:,1:],
                              gate_threshold=GATE_S)
  return xp,pp,("APPLIED" if diag["accepted"] else "REJECT"),diag["NIS"]
 if alg.startswith("J"):
  xp,pp,diag=gaussian_update(x,P,z,model,R0,gate_threshold=GATE_JOINT)
  return xp,pp,("APPLIED" if diag["accepted"] else "REJECT"),diag["NIS"]
 if not alg.startswith("SR"):
  raise RuntimeError("UNKNOWN_ARM:"+alg)
 h,H=model(x);nu=z-h
 S=H@P@H.T+R0
 nis=float(nu@np.linalg.solve(S,nu))
 if nis>GATE_JOINT:
  return x.copy(),P.copy(),"REJECT",nis
 # Original scalar Range then freshly nonlinear s, each observed once.
 rm=lambda q:(model(q)[0][:1],model(q)[1][:1,:])
 sm=lambda q:(model(q)[0][1:],model(q)[1][1:,:])
 a,b,_=gaussian_update(x,P,z[:1],rm,R0[:1,:1])
 c,d,_=gaussian_update(a,b,z[1:],sm,R0[1:,1:])
 return c,d,"APPLIED",nis

def run_filters(t,controls,observations,case,lut,initial_pose):
 """NO truth, true_bias, ground truth or scoring parameters in this function."""
 n=len(t)
 x0=np.asarray(initial_pose,float)
 P3=np.diag(INITIAL_POSE_STD**2)
 P4=np.zeros((4,4));P4[:3,:3]=P3;P4[3,3]=BIAS_PRIOR_STD**2
 x4=np.r_[x0,0.]
 state={k:(x0.copy(),P3.copy()) if k.endswith("3") else (x4.copy(),P4.copy())
        for k in METHODS}
 dstate={k:state[k] for k in ("DR3","DR4")}
 results={}
 for mode in MODES:
  states=np.full((n,len(METHODS),4),np.nan)
  covs=np.full((n,len(METHODS),4,4),np.nan)
  stats=np.full((n,len(METHODS)),"NOT_RUN",dtype="<U24")
  nis=np.full((n,len(METHODS)),np.nan)
  current={k:(v[0].copy(),v[1].copy()) for k,v in state.items()}
  invalid=set()
  for step in range(n):
   if step:
    ds=float(controls["ds_odom"][step])
    da=float(controls["dtheta_gyro"][step])
    dt=float(controls["dt_s"][step])
   # ONE_STEP: propagate the two DR-only baselines ONCE per frame.
   # RF arms then inherit that identical DR-only prior and do not
   # propagate the already-predicted baseline a second time.
   if mode=="one_step" and step:
    dstate={name:predict_one(xx,PP,ds,da,dt)
            for name,(xx,PP) in dstate.items()}
   for j,alg in enumerate(METHODS):
    if alg in invalid:
     stats[step,j]="INVALID_PREVIOUS"
     continue
    source=dstate["DR"+alg[-1]] if mode=="one_step" else current[alg]
    x,P=(source[0].copy(),source[1].copy())
    try:
     if mode=="recursive" and step:
      x,P=predict_one(x,P,ds,da,dt)
     obs=np.asarray(observations[step],float)
     xx,pp,status,NIS=filter_one(x,P,obs,alg,case,lut)
     if not (np.isfinite(xx).all() and np.isfinite(pp).all() and np.linalg.eigvalsh(pp).min()>0):
      raise RuntimeError("NONFINITE_OR_NON_PD_FILTER")
     states[step,j,:len(xx)]=xx
     covs[step,j,:len(xx),:len(xx)]=pp
     stats[step,j]=status
     nis[step,j]=NIS
     if mode=="recursive":current[alg]=(xx.copy(),pp.copy())
    except Exception as exc:
     stats[step,j]="INVALID"
     invalid.add(alg) if mode=="recursive" else None
   # For one_step, dstate DR3/DR4 refer to current DR-only predicted prior,
   # not the post-update RF results. Source pairing verified by B0 parity.
  results[mode]={"estimate":states,"covariance":covs,"status":stats,"nis":nis}
 return results

def saved_one_step_DR_reference(objs,outputs):
 a=objs
 # Compare DR3(One-step) baseline with frozen P3 independent EKF3 prior.
 v=outputs["one_step"];ind=METHODS.index("DR3")
 xx=v["estimate"][:,:, :3][:,ind]
 pp=v["covariance"][:,:, :3,:3][:,ind]
 dx=xx-a["xminus"];dx[:,2]=wrap(dx[:,2])
 return float(np.max(np.abs(dx))),float(np.max(np.abs(pp-a["Pminus"])))

def replay(archive,audit,out):
 verify_audit(audit)
 if sha_file(archive)!=ARCHIVE:raise RuntimeError("SOURCE_ZIP_CHANGED")
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 final={"schema":"R2_MOUNT_BIAS_LEVEL_ONE_STEP_AND_RECURSIVE_V1",
        "git_sha":os.environ["GITHUB_SHA"],"run_id":os.getenv("GITHUB_RUN_ID"),
        "stage":"B0_L0_L1_L2_3STATE_4STATE",
        "source_zip_sha256":ARCHIVE,
        "noise_model":"gyro_bias_positive_only_plus_pair_white_noise",
        "bias_levels_dps":BIAS_LEVELS,"seed":SEED,
        "methods":METHODS,"modes":MODES,
        "scientific_PASS":False,"cases":[],"status":"STARTED"}
 (out/"START.json").write_text(json.dumps(final,indent=2)+"\n")
 lut=FrozenLut()
 with open_verified_archive(archive) as zf:
  summary=json.loads(zf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  case_meta={c["id"]:c for c in manifest["cases"]}
  pair={}
  for d in summary["per_case"]:
   if d["case"] in CASES:pair[(d["case"],d["channel"])]=d
  if len(pair)!=4:raise RuntimeError("FROZEN_R2_MOUNT_CASES_MISSING")
  reftruth=None;reft=None;refids=None
  traces={}
  for k,d in pair.items():
   raw=zf.read("P2_OUT/"+d["trace_file"])
   if hashlib.sha256(raw).hexdigest()!=d["trace_sha256"]:
    raise RuntimeError("ORIGINAL_NPZ_SHA_DIFF")
   with np.load(io.BytesIO(raw),allow_pickle=False) as data:
    truth=data["truth_for_offline_scoring_only"].copy()
    times=data["t_s"].copy()
    pose_ids=data["pose_id"].copy()
    obs=np.column_stack([data["z_r_m"],data["z_s"]])
    ref={"xminus":data["xminus"].copy(),"Pminus":data["Pminus"].copy()}
   if len(truth)!=979 or not np.all(np.isfinite(obs)):
    raise RuntimeError("ORIGINAL_R2_ARRAY_INVALID")
   if reftruth is None:reftruth=truth;reft=times;refids=pose_ids
   elif not(np.array_equal(truth,reftruth) and np.array_equal(times,reft)
            and np.array_equal(pose_ids,refids)):
    raise RuntimeError("MOUNT_OR_CHANNEL_NOT_IDENTICAL_TRUTH_TIME")
   traces[k]=(obs,ref)
  # Simulator truth is consumed ONLY here to make inputs, then kept out
  # of the mathematical estimator run_filters.
  for label,bias in BIAS_LEVELS.items():
   controls,x0=build_positive_bias_controls(reft,reftruth,label,SEED)
   for case_id in CASES:
    case=case_meta[case_id]
    for channel in CHANNELS:
     obs,archived=traces[(case_id,channel)]
     runs=run_filters(reft,controls,obs,case,lut,x0)
     if label=="B0":
      parity=saved_one_step_DR_reference(archived,runs)
      if max(parity)>1e-7:raise RuntimeError(f"ORIGINAL_B0_DR3_PRIOR_PARITY_FAIL:{case_id}/{channel}: {parity}")
     else:parity=None
     name=f"{case_id}_{channel}_{label}_seed{SEED}"
     for mode,res in runs.items():
      np.savez_compressed(out/(name+"_"+mode+".npz"),
             t_s=reft,pose_id=refids,
             names=np.asarray(METHODS),
             estimate=res["estimate"],covariance=res["covariance"],
             status=res["status"],nis=res["nis"])
     metrics={"case":case_id,"channel":channel,"level":label,
       "gyro_bias_true_dps":bias,"seed":SEED,
       "timepoints":len(reft),"mount_deg":case["mount_deg"],
       "B0_archived_DR_prior_parity":parity,
       "invalid_model_frames":{mode:int(np.count_nonzero(np.char.startswith(
          runs[mode]["status"],"INVALID"))) for mode in MODES},
       "source_trace_sha256":pair[(case_id,channel)]["trace_sha256"]}
     final["cases"].append(metrics)
     (out/"PROGRESS.json").write_text(json.dumps(final,indent=2)+"\n")
     print("R2_BIAS_CASE "+json.dumps(metrics),flush=True)
 final.update({"status":"RUN_COMPLETED",
               "total_case_level_channels":len(final["cases"]),
               "archived_truth_for_offline_scoring_only":"READ_ONLY_IN_INPUT_GENERATION_AND_SEPARATE_SCORER",
               "finished_utc":datetime.now(timezone.utc).isoformat()})
 (out/"FINAL.json").write_text(json.dumps(final,indent=2)+"\n")
 print("R2_BIAS_FINAL "+json.dumps({k:final[k] for k in
  ("status","total_case_level_channels","git_sha")}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 for n in ("archive","audit","out"):p.add_argument("--"+n,required=True)
 a=p.parse_args();raise SystemExit(replay(a.archive,a.audit,a.out))
