"""ODO-Q: verified sensor-v2 odometry process-noise audit and genuine J4/SR4 recurrence.

Q_native is the ORIGINAL physically specified distance/gyro input covariance.
All Qd-scaled and legacy-Euler lateral variants are predeclared *stress controls*
and are NOT claimed as actual measured TB3 encoder/wheel noise.
Frozen RF r/s, mean, joint R(q), FFD LUT and NIS threshold never change.
GT enters only offline motion input generation and separate scoring.
"""
from __future__ import annotations
import argparse,ast,csv,hashlib,io,json,math,os,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SRC=ROOT/"research/EKF4_RANGE_S_STAGED_20261014"
SENSOR=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
ARCHIVES={
 "raw_rf":"88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
 "r2":"ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399",
 "n4b":"170a646f8167f1e440316abf42b614afa4efc3d77037c0e19bf470a817fc334b",
 "n4c":"f807346e806adcc88ce5772d901cb82f83e423d56c1b5f7b846b6871fcaefad9",
}
BLOBS={
 "research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
 "research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
 "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
 "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
 "research/R5_N4C_20261015/n4c_joint_sr4.py":"40c795fa8799c4090c0766ebdccf6e2be83df6a0",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/sensor_v2.py":"87ce04aa3c43130f3499008840fa395174f1124e",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
 "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
}
CASES=("R2_aA_m0","R2_aA_m45")
BIAS={"B0":0.,"L0":.01,"L1":.05,"L2":.20}
SOLVERS=("J4","SR4")
METHODS_FULL=(("BASE_R0","NATIVE"),
 ("POWER_JOINT","NATIVE"),("POWER_JOINT","D2"),
 ("POWER_JOINT","D4"),("POWER_JOINT","D16"),("POWER_JOINT","D64"),
 ("POWER_JOINT","LEGACY_LATERAL_PROXY"))
METHODS_LOS=(("BASE_R0","NATIVE"),
 ("BASE_R0","D4"),("BASE_R0","LEGACY_LATERAL_PROXY"))
ORIGINAL_K_DISTANCE=2e-5
GYRO_N_DEG_SQRT_S=.015
FROZEN_R0_R=.0068578637
FROZEN_R0_S=.0081
GYRO_VAR_FACTOR=math.radians(GYRO_N_DEG_SQRT_S)**2
SEED_AUDIT=list(range(1000,1032))

def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def blob(path):
 p=Path(path);h=hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0")
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def save(path,data):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def checked(path,digest):
 got=sha(path)
 if got!=digest:raise RuntimeError("ARCHIVE_SHA_CHANGED:"+str(path)+":"+got)
 z=zipfile.ZipFile(path)
 if z.testzip():raise RuntimeError("BAD_ZIP_CRC")
 return z
def member(z,name):
 found=[f for f in z.namelist() if f==name or f.endswith("/"+name)]
 if len(found)!=1:raise RuntimeError("MISSING_OR_DUP_ARCHIVE_MEMBER:"+name)
 return found[0]
def audit(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errors=[];observed={}
 head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 if head!=os.getenv("GITHUB_SHA"):errors.append("WRONG_GIT_REV")
 if os.getenv("GITHUB_ACTIONS")!="true":errors.append("REQUIRE_REAL_GITHUB_ACTIONS")
 for k,expected in BLOBS.items():
  f=ROOT/k
  if not f.exists():errors.append("FROZEN_SOURCE_MISSING:"+k)
  else:
   actual=blob(f);observed[k]=actual
   if actual!=expected:errors.append("FROZEN_SOURCE_CHANGED:"+k)
 try:ast.parse((HERE/"odom_q_experiment.py").read_text(encoding="utf-8"))
 except Exception as exc:errors.append("SCRIPT_SYNTAX:"+repr(exc))
 wf=ROOT/".github/workflows/odom-q-physical-v1.yml"
 if not wf.exists():errors.append("WORKFLOW_MISSING")
 else:
  v=wf.read_text()
  t=["odom_q_experiment.py --phase audit","odom_q_experiment.py --phase test",
     "odom_q_experiment.py --phase run"]
  if not all(p in v for p in t) or not (v.index(t[0])<v.index(t[1])<v.index(t[2])):
   errors.append("AUDIT_MUST_RUN_BEFORE_NUMERICS")
  if "if: always()" not in v or "actions: read" not in v:
   errors.append("AUDIT_OUTPUT_RULE_NOT_MET")
 # Fail if the proposed Q model is not the original simulated motion-input Q.
 f=(ROOT/"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py").read_text()
 g=(SENSOR/"qclean_uwb/drivesim/sensor_v2.py").read_text()
 c=(ROOT/"research/EKF4_RANGE_S_STAGED_20261014/core.py").read_text()
 if "2e-5*abs(ds)" not in f or "math.radians(.015)**2*dt" not in f:
  errors.append("FROZEN_ODOM_Q_NOT_EXPECTED")
 for needle in ("k_distance_m: float = 2e-5","gyro_N_rad_sqrt_s: float = math.radians(.015)",
   "qd = cfg.k_distance_m*np.abs(ds)","ngvar = cfg.gyro_N_rad_sqrt_s**2*dt"):
  if needle not in g:errors.append("SIMULATED_SENSOR_Q_NOT_EXPECTED:"+needle)
 for needle in ("G[:2, 0] = c*u","G[:2, 1] = v","F[2, 3] = -dt",
  "F@P@F.T+G@Q_input@G.T"):
  if needle not in c:errors.append("TRANSITION_JACOBIAN_NOT_EXPECTED:"+needle)
 document={"stage":"ODO-Q-PRE","decision":"GO" if not errors else "HOLD",
  "head_sha":head,"source_git_blobs":observed,"archive_sha256":ARCHIVES,
  "current_Q_distance_variance":"2e-5*abs(measured_ds_odom)",
  "generator_Q_distance_variance":"2e-5*abs(true_ds) (offline only)",
  "current_gyro_variance":"deg(0.015)^2*dt",
  "generator_gyro_variance":"deg(0.015)^2*dt",
  "wheel_yaw_noise_unused_in_frozen_heading_predict":True,
  "new_Q_D2_to_D64_are_hypothesis_stress_not_measured_sensor_noise":True,
  "legacy_lateral_proxy_is_deterministic_motion_model_mismatch_proxy_not_new_random_sensor":True,
  "source_errors":errors,"scientific_PASS":False}
 save(out/"SOURCE_AUDIT.json",document)
 print("ODOM_Q_AUDIT "+json.dumps({"decision":document["decision"],"errors":errors}),flush=True)
 return 0 if not errors else 2

def setup():
 import numpy as np
 import pandas as pd
 sys.path[:0]=[
  str(ROOT/"research/R5_N4C_20261015"),str(SRC),str(SENSOR)]
 import n4c_joint_sr4 as parent
 from core import predict,transition,wrap
 from p3_rf_adapter4 import FrozenLut,R0
 from r2_bias_replay import (
  build_positive_bias_controls,predict_one,METHODS,INITIAL_POSE_STD,BIAS_PRIOR_STD)
 from qclean_uwb.drivesim.sensor_v2 import (
  SensorV2Config,generate,motion_increments)
 return np,pd,parent,predict,transition,wrap,FrozenLut,R0,build_positive_bias_controls, \
  predict_one,METHODS,INITIAL_POSE_STD,BIAS_PRIOR_STD,SensorV2Config,generate,motion_increments

def q_native(np,ds,dt):
 if dt<=0:raise RuntimeError("NONPOSITIVE_DT")
 return np.diag([ORIGINAL_K_DISTANCE*abs(ds),GYRO_VAR_FACTOR*dt,0.])
def predict_variant(np,predict,transition,x,P,ds,gyro,dt,variant):
 if variant=="NATIVE" or variant=="LEGACY_LATERAL_PROXY":
  scale=1.
 elif variant in ("D2","D4","D16","D64"):
  scale={"D2":2.,"D4":4.,"D16":16.,"D64":64.}[variant]
 else:raise RuntimeError("UNKNOWN_Q_VARIANT:"+variant)
 qq=q_native(np,ds,dt)
 qq[0,0]*=scale
 out,Pnew,F,G=predict(x,P,ds,gyro,dt,qq)
 # G Q G^T is global XY+Yaw process covariance.
 Qworld=G@qq@G.T
 lateral_std=0.
 if variant=="LEGACY_LATERAL_PROXY":
  # The generator truth follows the legacy Euler convention whereas
  # core.transition integrates a finite-turn SE2 arc. Their projected
  # transverse discrepancy magnitude is approximately ds*sin(a/2).
  # Treat it as a *hypothetical* independent per-step model error only.
  a=gyro-x[3]*dt
  phi=x[2]+a/2
  tvec=np.array([-math.sin(phi),math.cos(phi),0.,0.],float)
  lateral_std=abs(ds*math.sin(a/2))
  extra=(lateral_std**2)*np.outer(tvec,tvec)
  Pnew=(Pnew+extra+Pnew.T+extra.T)/2
  Qworld=Qworld+extra
 if not np.isfinite(Pnew).all() or np.linalg.eigvalsh(Pnew).min()<=0:
  raise RuntimeError("NONSPD_PREDICTION")
 return out,Pnew,F,G,Qworld,float(qq[0,0]),lateral_std

def unit():
 np,pd,parent,predict,transition,wrap,_,_,_,original_predict,*rest=setup()
 rng=np.random.default_rng(2201)
 dif=[]
 for j in range(50):
  x=np.array([1.2,-.3,rng.uniform(-2,2),rng.normal(0,.005)])
  A=rng.normal(size=(4,4))
  P=A@A.T*.003+np.diag([.02,.02,.01,.00005])
  ds=rng.uniform(-.08,.08);gyro=rng.uniform(-.06,.06)
  dt=.2
  a,b,_,G,Qw,qd,lat=predict_variant(np,predict,transition,x,P,ds,gyro,dt,"NATIVE")
  orig,Po=original_predict(x,P,ds,gyro,dt)
  dif.append(max(float(np.max(abs(a-orig))),float(np.max(abs(b-Po)))))
  if not np.allclose(Qw,G@q_native(np,ds,dt)@G.T,rtol=0,atol=1e-15):
   raise RuntimeError("WORLD_POSITION_Q_PROJECTION")
  h=1e-6
  for col in (0,1):
   eps=[ds,gyro]
   eps[col]+=h
   p1=transition(x,eps[0],eps[1],dt)[0]
   eps[col]-=2*h
   p2=transition(x,eps[0],eps[1],dt)[0]
   d=(p1-p2)/(2*h);d[2]=float(wrap(d[2]))
   if max(abs(d-G[:,col]))>2e-5:raise RuntimeError("G_FINITE_DIFFERENCE_ERROR")
  for k in ("D2","D4","D16","D64","LEGACY_LATERAL_PROXY"):
   a,C,F,G,Qw,qd,lateral=predict_variant(np,predict,transition,x,P,ds,gyro,dt,k)
   if np.linalg.eigvalsh(C).min()<=0:raise RuntimeError("NONSPD_VARIANT")
   if np.linalg.eigvalsh(C-Po).min()<-1e-12:
    raise RuntimeError("Q_VARIANT_NOT_A_PSD_ADDITION:"+k)
   if k.startswith("D") and not np.isclose(Qw[2,2],G[2,1]**2*GYRO_VAR_FACTOR*dt):
    raise RuntimeError("GYRO_Q_MUST_REMAIN_FROZEN")
 # Stationary yaw: gyro input-noise should NOT directly add X/Y covariance.
 q=np.diag([0.,GYRO_VAR_FACTOR*.2,0.])
 xx=np.array([1.,2.,1.,0.]); _,F,G=transition(xx,0.,.05,.2)
 if max(abs((G@q@G.T)[:2,:2]).ravel())>1e-20:raise RuntimeError("YAW_ONLY_LAT_NOISE_INVENTED")
 if max(dif)>1e-13:raise RuntimeError("ORIGINAL_NATIVE_Q_NOT_REPRODUCED")
 print("ODOM_Q_UNIT_PASS "+json.dumps({"50_native_max_abs_diff":max(dif),
  "checks":["G_fd","Global_Q_xy","NATIVE_R2_PREDICT_PARITY","PSD_stress",
     "gyro_noise_unchanged","stationary_yaw_zero_wheel_position_noise"]}),flush=True)
 return 0

def sensor_monte_carlo(np,truth,t,level,make_controls,SensorV2Config,generate,motion_increments):
 ds,dtheta=motion_increments(t,truth,convention="legacy-euler")
 kdist=ORIGINAL_K_DISTANCE;N=math.radians(GYRO_N_DEG_SQRT_S)
 cfg=SensorV2Config(level=1,condition="noise_pair",
    common_scale=0.,bias_rw_rad_s_sqrt_s=0.) if level=="B0" else \
  SensorV2Config(level=["L0","L1","L2"].index(level),condition="all",
    slip_mode="off",common_scale=0.,bias_rw_rad_s_sqrt_s=0.)
 params=None if level=="B0" else {
    "gyro_bias":math.radians({"L0":.01,"L1":.05,"L2":.20}[level]),
    "gyro_sf":0.,"wheel_asymmetry":0.,"wheelbase":0.,"common_scale":0.}
 d_error=[];g_error=[];qdtrue=[];qdmeasured=[]
 for seed in SEED_AUDIT:
  controls,offline=generate(t,ds,dtheta,cfg,seed,parameters=params)
  actual=controls["ds_odom"];angle=controls["dtheta_gyro"]
  dt=np.diff(t)
  positive=np.abs(ds[1:])>1e-12
  e=actual[1:]-ds[1:]
  eg=angle[1:]-dtheta[1:]-math.radians(BIAS[level])*dt
  nd=np.sqrt(kdist*np.abs(ds[1:]))
  ng=N*np.sqrt(dt)
  assert (offline["generated_variance"][1:,0]==kdist*np.abs(ds[1:])).all()
  assert np.allclose(offline["generated_variance"][1:,1],ng**2,rtol=1e-12,atol=0)
  if not positive.any():raise RuntimeError("NO_POSITIVE_WHEEL_ODOM_MOTION")
  d_error.extend((e[positive]/nd[positive]).tolist())
  g_error.extend((eg/ng).tolist())
  qdtrue.extend((kdist*np.abs(ds[1:])).tolist())
  qdmeasured.extend((kdist*np.abs(actual[1:])).tolist())
 # Original seed0 motion inputs EXACT parity (no GT inside estimator).
 frozen,x0=make_controls(t,truth,level,seed=0)
 fresh,off=generate(t,ds,dtheta,cfg,0,parameters=params)
 for key in ("ds_odom","dtheta_gyro","dt_s"):
  if not np.array_equal(fresh[key],frozen[key]):
   raise RuntimeError("ACTUAL_SENSOR_GENERATOR_DIFFERS_FROM_FROZEN_R2:"+key)
 d_error=np.array(d_error);g_error=np.array(g_error)
 qdtrue=np.array(qdtrue);qdmeasured=np.array(qdmeasured)
 return {
  "level":level,"n_seeds":len(SEED_AUDIT),
  "n_wheel_distances":len(d_error),"n_gyro_angles":len(g_error),
  "wheel_std_residual_variance":float(np.var(d_error)),
  "wheel_std_residual_mean":float(d_error.mean()),
  "gyro_std_residual_variance":float(np.var(g_error)),
  "gyro_std_residual_mean":float(g_error.mean()),
  "median_measured_qd_over_true_qd":float(np.median(qdmeasured[qdtrue>0]/qdtrue[qdtrue>0])),
  "mean_relative_qd_abs_difference":float(
    np.mean(abs(qdmeasured[qdtrue>0]-qdtrue[qdtrue>0])/qdtrue[qdtrue>0])),
  "original_seed0_control_parity":"BIT_EXACT",
  "source_truth_used_in_generator_only":True,
 }

def vec_metrics(np,results,t,truth,bias):
 x=results["state"];P=results["cov"]
 e=x[:,:3]-truth[:,:3];e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
 m=t>=30;e=e[m];S=P[m,:3,:3]
 C=S[:,:2,:2]-S[:,:2,2:3]@S[:,2:3,:2]/S[:,2:3,2:3]
 C=(C+C.swapaxes(-1,-2))/2
 em=e[:,:2]-S[:,:2,2]/S[:,2,2,None]*e[:,2,None]
 l,U=np.linalg.eigh(C)
 coef=np.einsum("nij,nj->ni",U.transpose(0,2,1),em)
 ne1=coef[:,0]**2/l[:,0];ne2=coef[:,1]**2/l[:,1]
 nec=ne1+ne2;nepsi=e[:,2]**2/S[:,2,2]
 pose_nees=np.einsum("ni,ni->n",e,np.linalg.solve(S,e[...,None])[:,:,0])
 if np.max(abs(pose_nees-nec-nepsi))>1e-6:
  raise RuntimeError("POSE_SCHUR_NEES_DECOMPOSITION_BROKEN")
 xx=results["prior_x"][m];PP=results["prior_P"][m]
 status=results["status"][m]
 return {
  "conditional_xy_nees":float(np.mean(nec)),
  "conditional_xy_narrow_nees":float(np.mean(ne1)),
  "conditional_xy_wide_nees":float(np.mean(ne2)),
  "conditional_xy_narrow_sigma_median_cm":float(np.median(np.sqrt(l[:,0]))*100),
  "conditional_xy_wide_sigma_median_cm":float(np.median(np.sqrt(l[:,1]))*100),
  "conditional_xy_narrow_95coverage":float(np.mean(ne1<=3.841458820694124)),
  "conditional_xy_95coverage":float(np.mean(nec<=5.991464547107979)),
  "heading_nees":float(np.mean(nepsi)),
  "pose_nees_check":float(np.mean(pose_nees)),
  "pose_95coverage_check":float(np.mean(pose_nees<=7.814727903251179)),
  "conditioned_xy_cov_min_eig_median_m2":float(np.median(l[:,0])),
  "conditioned_xy_cov_max_eig_median_m2":float(np.median(l[:,1])),
  "RF_accepts":int(np.sum(status=="APPLIED")),
  "RF_rejects":int(np.sum(status=="REJECT")),
  "prior_heading_std_median_deg":float(np.median(np.degrees(np.sqrt(PP[:,2,2])))),
  "posterior_heading_std_median_deg":float(np.median(np.degrees(np.sqrt(S[:,2,2])))),
 }

def recurse(np,core_predict,transition,parent,controls,x0,z,q,method,policy,variant,case,lut):
 from r2_bias_replay import INITIAL_POSE_STD,BIAS_PRIOR_STD
 n=len(z)
 x=np.r_[x0,0.];P=np.diag([*(INITIAL_POSE_STD**2),BIAS_PRIOR_STD**2])
 prex=np.empty((n,4));preP=np.empty((n,4,4))
 X=np.empty((n,4));PP=np.empty((n,4,4))
 st=np.empty(n,dtype="<U12");nis=np.full(n,np.nan)
 qworld=np.zeros((n,4,4));qd=np.zeros(n);lat=np.zeros(n)
 for i in range(n):
  if i:
   x,P,F,G,qworld[i],qd[i],lat[i]=predict_variant(
     np,core_predict,transition,x,P,float(controls["ds_odom"][i]),
     float(controls["dtheta_gyro"][i]),float(controls["dt_s"][i]),variant)
  prex[i]=x;preP[i]=P
  xx,pn,status,ni,scale=parent.perform_update(
    np,x,P,z[i],policy,q[i],method,case,lut,"natural")
  if not(np.isfinite(xx).all() and np.isfinite(pn).all() and np.linalg.eigvalsh(pn).min()>0):
   raise RuntimeError("Q_RECURRENCE_NONSPD:"+str((policy,variant,method,i)))
  X[i]=x=xx;PP[i]=P=pn
  st[i]=status;nis[i]=ni
 return {"prior_x":prex,"prior_P":preP,
   "state":X,"cov":PP,"status":st,"nis":nis,
   "qworld":qworld,"qdist":qd,"qlateral_std":lat}

def execute(out,rec,rf,r2,n4b,n4c):
 (np,pd,parent,core_predict,transition,wrap,FrozenLut,R0,controls_fn,
     original_predict,original_names,POSESTD,BSTD,SensorCfg,generate,motion)=setup()
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 pre=json.loads(Path(rec).read_text())
 if pre["decision"]!="GO" or pre["head_sha"]!=os.environ["GITHUB_SHA"]:
  raise RuntimeError("AUDIT_REQUIRED")
 if not(np.allclose(R0,np.diag([FROZEN_R0_R,FROZEN_R0_S]),rtol=0,atol=1e-12)):
  raise RuntimeError("R0_NOT_FROZEN")
 summary=[];parity=[];samples=[];Qdiag=[]
 with checked(rf,ARCHIVES["raw_rf"]) as zrf,checked(r2,ARCHIVES["r2"]) as zr2, \
      checked(n4b,ARCHIVES["n4b"]) as zb,checked(n4c,ARCHIVES["n4c"]) as zc:
  model=parent.parse_n4b_prediction(np,pd,zb)
  archive_map={(a["case"],a["channel"]):a for a in
    json.loads(zrf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))["per_case"]}
  manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
  metas={case["id"]:case for case in manifest["cases"]}
  for case in CASES:
   for channel in ("full","los"):
    src=archive_map[(case,channel)]
    raw=zrf.read("P2_OUT/"+src["trace_file"])
    if hashlib.sha256(raw).hexdigest()!=src["trace_sha256"]:
     raise RuntimeError("RAW_OBSERVER_PACKET_HASH_DIFFERENT")
    with np.load(io.BytesIO(raw),allow_pickle=False) as f:
     t=f["t_s"].copy();ids=f["pose_id"].copy()
     truth=f["truth_for_offline_scoring_only"].copy()
     z=np.column_stack([f["z_r_m"],f["z_s"]])
    if len(t)!=979:raise RuntimeError("NOT_FROZEN_979")
    lut=FrozenLut(ROOT)
    quality=[model[(case,int(pid))] for pid in ids] if channel=="full" else [{} for _ in ids]
    for level,bb in BIAS.items():
     controls,x0=controls_fn(t,truth,level,seed=0)
     if case=="R2_aA_m0" and channel=="full":
      diag=sensor_monte_carlo(np,truth,t,level,controls_fn,SensorCfg,generate,motion)
      samples.append(diag)
      print("ODOM_Q_GENERATOR_AUDIT "+json.dumps(diag),flush=True)
     with np.load(io.BytesIO(zr2.read(member(zr2,f"{case}_{channel}_{level}_seed0_recursive.npz"))),allow_pickle=False) as f:
      ref={k:f[k].copy() for k in f.files}
     for solver in SOLVERS:
      saved={};policies=METHODS_FULL if channel=="full" else METHODS_LOS
      for rf_policy,variant in policies:
       trace=recurse(np,core_predict,transition,parent,controls,x0,z,quality,
         solver,rf_policy,variant,metas[case],lut)
       saved[(rf_policy,variant)]=trace
       score=parent.score(np,trace,t,truth,bb)
       other=vec_metrics(np,trace,t,truth,bb)
       if abs(score["pose_nees"]-other["pose_nees_check"])>1e-8 or \
          abs(score["pose_95coverage"]-other["pose_95coverage_check"])>1e-12:
        raise RuntimeError("POSE_CONDITIONAL_SPLIT_SCORE_PARITY")
       mask=t>=30;Q=trace["qworld"][mask]
       row={"case":case,"mount_deg":metas[case]["mount_deg"],
         "channel":channel,"bias":level,"solver":solver,
         "RF_model":rf_policy,"odometry_Q":variant,"seed":0,
         "wheel_Qd_factor":1 if variant in ("NATIVE","LEGACY_LATERAL_PROXY") else
             int(variant[1:]),
         "true_simulator_encoder_k_distance_m":ORIGINAL_K_DISTANCE,
         "R0_or_POWER_R_s_changed":False,
         "mean_gyro_Q_input_rad2":float(np.mean(Q[:,2,2])),
         "mean_world_Qxx_m2":float(np.mean(Q[:,0,0])),
         "mean_world_Qyy_m2":float(np.mean(Q[:,1,1])),
         "mean_world_Qxy_m2":float(np.mean(Q[:,0,1])),
         "max_model_mismatch_lateral_std_m":float(np.max(trace["qlateral_std"])),
         **score,**other}
       summary.append(row)
       if rf_policy=="BASE_R0" and variant=="NATIVE":
        pos=list(original_names).index(solver)
        xx=ref["estimate"][:,pos,:];p0=ref["covariance"][:,pos,:,:]
        status=(ref["status"][:,pos]=="APPLIED")
       elif rf_policy=="POWER_JOINT" and variant=="NATIVE":
        zname=f"N4C_{case}_{channel}_{level}_{solver}.npz"
        with np.load(io.BytesIO(zc.read(member(zc,zname))),allow_pickle=False) as f:
         loc=np.flatnonzero((f["policies"]=="POWER_JOINT")&(f["gate_modes"]=="natural"))
         if len(loc)!=1:raise RuntimeError("N4C_REF_POWER_MISSING")
         ix=int(loc[0]);xx=f["estimate"][:,ix,:]
         p0=f["covariance"][:,ix,:,:]
         status=(f["status"][:,ix]=="APPLIED")
         if not np.array_equal(f["pose_id"],ids):raise RuntimeError("N4C_ID_CHANGED")
       else:xx=p0=status=None
       if xx is not None:
        diff=trace["state"]-xx;diff[:,2]=wrap(diff[:,2])
        max_state=float(np.max(abs(diff)))
        max_cov=float(np.max(abs(trace["cov"]-p0)))
        gate_diff=int(np.sum((trace["status"]=="APPLIED")!=status))
        if max(max_state,max_cov)>1e-6 or gate_diff:
         raise RuntimeError("BASELINE_ORIGINAL_PARITY_INVALID:"+str(
           (case,level,solver,rf_policy,max_state,max_cov,gate_diff)))
        parity.append({"case":case,"channel":channel,"bias":level,
          "solver":solver,"RF_model":rf_policy,"max_state":max_state,
          "max_cov":max_cov,"gate_differences":gate_diff})
      pairs=list(saved)
      np.savez_compressed(out/f"QOD_{case}_{channel}_{level}_{solver}.npz",
        t_s=t,pose_id=ids,policies=np.asarray([q[0] for q in pairs]),
        Q_variants=np.asarray([q[1] for q in pairs]),
        prior_x=np.stack([saved[k]["prior_x"] for k in pairs],axis=1),
        prior_P=np.stack([saved[k]["prior_P"] for k in pairs],axis=1),
        state=np.stack([saved[k]["state"] for k in pairs],axis=1),
        covariance=np.stack([saved[k]["cov"] for k in pairs],axis=1),
        status=np.stack([saved[k]["status"] for k in pairs],axis=1),
        nis=np.stack([saved[k]["nis"] for k in pairs],axis=1),
        qdist=np.stack([saved[k]["qdist"] for k in pairs],axis=1),
        qworld=np.stack([saved[k]["qworld"] for k in pairs],axis=1))
      print("ODOM_Q_CASE "+json.dumps({"case":case,"channel":channel,"bias":level,
        "solver":solver,"n_policies":len(pairs)}),flush=True)
 def write_csv(path,rows):
  with (out/path).open("w",newline="",encoding="utf-8") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 write_csv("ODOM_Q_ALL_RECURSIVE.csv",summary)
 write_csv("ODOM_Q_SOURCE_PARITY.csv",parity)
 write_csv("ODOM_Q_SENSOR_MC.csv",samples)
 mains=[r for r in summary if r["channel"]=="full" and r["bias"] in ("B0","L2")]
 diag={"status":"ODOM_Q_ACTUAL_GENERATOR_AND_RECURSIVE_STRESS_COMPLETE",
   "source_commit":os.environ["GITHUB_SHA"],
   "n_recursive_arms":len(summary),"n_baseline_parity":len(parity),
   "source_archive_hashes":ARCHIVES,
   "simulator_white_noise_verified":True,
   "real_hardware_noise_measured":False,
   "generator_independent_seed_audit":samples,
   "arm_definition":{"full":METHODS_FULL,"los":METHODS_LOS},
   "focus_full_B0_L2":mains,
   "scientific_CALIBRATED_Q_PASS":False,
   "frozen_gyro_Q":True,"frozen_Rs_and_Range_s_mean_cov":True,
   "limitations":[
     "Odometry process Q of the original filter ALREADY uses sensor-v2 white-noise coefficients",
     "Qd scaled x2..64 uses invented measurement uncertainty for sensitivity, NOT physical re-measurement",
     "Legacy lateral Q is a deterministic propagation-mismatch proxy, not an independently random wheel noise",
     "Original R2 sensor seed0, trajectory and FullRF packet, no independent scene",
     "The physically generated wheel yaw noise is NOT used by the original gyro-heading predictor",
     "POSE conditional XY error may be dominated by RF bias or geometry even with correct sensor Q",
     "Higher P/NEES coverage alone is not success if Heading/Bias RMSE worsens",
     "Ground truth used only in source model diagnosis, sensor stream generation and output scoring"]}
 save(out/"ODOM_Q_FINAL.json",diag)
 print("ODOM_Q_FINAL "+json.dumps({"status":diag["status"],"n":len(summary),
  "parity":len(parity),
  "mc":samples,
  "focus":[{"case":r["case"],"bias":r["bias"],"method":r["solver"],
    "rf":r["RF_model"],"Q":r["odometry_Q"],"head":r["heading_rmse_deg"],
    "biasRMSE":r["bias_rmse_dps"],"xyRMSE":r["xy_rmse_m"],
    "poseNEES":r["pose_nees"],"condXY":r["conditional_xy_nees"],
    "narrowXY":r["conditional_xy_narrow_nees"],
    "pose95":r["pose_95coverage"],"gate":r["RF_accepts"]}
    for r in mains]},ensure_ascii=False),flush=True)
 return 0

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--phase",choices=("audit","test","run"),required=True)
 ap.add_argument("--out");ap.add_argument("--receipt")
 ap.add_argument("--rf");ap.add_argument("--r2")
 ap.add_argument("--n4b");ap.add_argument("--n4c")
 a=ap.parse_args()
 if a.phase=="audit":return audit(a.out)
 if a.phase=="test":return unit()
 if not all((a.out,a.receipt,a.rf,a.r2,a.n4b,a.n4c)):
  raise RuntimeError("MISSING_RUN_ARGS")
 return execute(a.out,a.receipt,a.rf,a.r2,a.n4b,a.n4c)

if __name__=="__main__":raise SystemExit(main())
