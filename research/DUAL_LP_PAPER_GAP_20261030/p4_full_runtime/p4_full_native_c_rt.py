#!/usr/bin/env python3
"""P4 FULL C0+ NEW-C RF exact Native Sionna 2.0.1 runner.

--stage canary: 6 P3 existing C poses * 9 original frequencies, fresh Full
    plus separate Native LoS, and direct-path extraction from the Full native
    solver. Real P3 frozen native H is an immutable oracle and all 3 H versions
    are compared. No P4 EKF performed.
--stage shard: read exact full preapproved canary receipt and deterministic
    missing C original route pose keys; calculate true Full PathSolver at every
    one of the 257 original frequencies; Native LoS from unique *actual* Full
    direct path only if canary passed and per-shard independent 3-bin spotchecks
    pass; else use separate Full + Native LoS per bin (locked fallback).
    Store H/tau/counts/raw detector and SHA per actual new C pose. No fill.

Original P3/P1/P2/P4 Pilot data immutable. One simulated Corridor scene.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,io,json,math,os,pathlib,platform,subprocess,sys,time,traceback,zipfile
from collections import Counter
import numpy as np
ROOT=pathlib.Path.cwd()
AM=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P4_FULL_20261102"
P3=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P3_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
BANK=pathlib.Path(os.getenv("DLP_FULL_BANK_DIR","/tmp/dlp_full_banks"))
CANARY=pathlib.Path(os.getenv("DLP_FULL_CANARY_DIR","/tmp/dlp_full_canary"))
OUT=pathlib.Path(os.getenv("DLP_FULL_OUT","/tmp/dlp_full_native"))
OUT.mkdir(parents=True,exist_ok=True)
C=299792458.0;N=257;DF=1950000.0
START=time.monotonic();RESULTS=[];FAIL=[];VALIDATION={};LOG=[]
def sha(path):
  h=hashlib.sha256()
  with pathlib.Path(path).open("rb") as f:
    for b in iter(lambda:f.read(1<<20),b""):h.update(b)
  return h.hexdigest()
def hs(b):return hashlib.sha256(b).hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
def ensure(ok,msg):
  if not bool(ok):raise RuntimeError(msg)
def make_observer(h):
  a=np.asarray(h)
  ensure(a.shape==(N,2,2),"NATIVE_FREQUENCY_TWO_RX_TWO_TX_H_REQUIRED")
  w=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
  CIR=np.fft.ifft(a[:,:,0]*w[:,None],n=4*N,axis=0)*N
  mag=np.abs(CIR)
  port=int(mag.max(axis=0).argmax())
  peak=float(mag[:,port].max());ensure(peak>0,"NO_VALID_NATIVE_RX_PORT")
  tap=int(np.argmax(mag[:,port]>=.3*peak))
  P=np.abs(CIR[tap])**2;den=float(P.sum())
  ensure(den>0 and np.isfinite(den),"NO_VALID_COMMON_FIRST_TAP_POWER")
  s=float((P[0]-P[1])/den)
  ensure(abs(s)<=1+1e-12 and np.isfinite(s),"INVALID_SIGNED_RATIO")
  return dict(tap=tap,port=port,signed_s=s,r_m=float(tap*C/(1028*DF)))
def read_timeline(p):
  with pathlib.Path(p).open(newline="",encoding="utf-8") as f:
    return list(csv.DictReader(f))
def source_identity():
  cfg=J(AM/"P4_FULL_CONFIG_LOCK.json")
  p3=J(P3/"P3_NATIVE_RT_APPEND_ONLY_AMENDMENT_V1.json")
  input_lock=J(P1/"P1_INPUT_LOCK.json")
  ensure(cfg["status"] in ("PROPOSER_LOCKED_AUDIT_PENDING","FROZEN_NATIVE_FULL_C0PLUS_ONLY"),
         "P4_FULL_CONTRACT_UNRECOGNIZED")
  ensure(cfg["geometry"]["anchor_C_xyz_m"]==[16,.8,2.65] and
         cfg["geometry"]["missing_native_C"]==3097,"P4_FULL_FIXED_GEOMETRY_OR_UNIVERSE_DRIFT")
  old=cfg["inputs"]
  old_zip=ROOT/old["old_39_zip"]
  ensure(sha(old_zip)==old["old_zip_sha256"],"P3_39_NATIVE_ORIGINAL_SHA_CHANGED")
  with zipfile.ZipFile(old_zip) as z:ensure(z.testzip() is None,"P3_OLD_ZIP_CRC_CHANGED")
  files={"scripts/corridor_sionna_run.py":p3["source_contract"]["corridor_sionna_py_git_blob"],
      "scripts/g2_completion/sionna_native_runtime.py":p3["source_contract"]["ffd_adapter_py_git_blob"],
      "src/qclean_uwb/scenarios/corridor.py":"eba1ab64d5e2117bfd519ceb5cac077b24caf3f8",
      "results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json":p3["source_contract"]["solver_config_blob"]}
  for path,oldsha in files.items():
    got=subprocess.check_output(["git","hash-object",path],text=True).strip()
    ensure(got==oldsha,"PINNED_SOURCE_GIT_BLOB_DRIFT:"+path)
  ensure(cfg["solver"]["full"]==p3["rf"]["solver_full"] and
         cfg["solver"]["los"]==p3["rf"]["solver_los"],"NATIVE_PATHSOLVER_SETTING_DRIFT")
  return cfg,p3,input_lock
def stage_bank(cfg,p3,lock):
  sys.path.insert(0,str(ROOT/"scripts"))
  sys.path.insert(0,str(ROOT/"src"))
  sys.path.insert(0,str(ROOT/"scripts/g2_completion"))
  import mitsuba as mi
  mi.set_variant("llvm_ad_mono_polarized")
  import drjit as dr
  dr.set_thread_count(1)
  import corridor_sionna_run as CR
  basedir=ROOT
  for b in lock["ffd_bank_source"]["banks"]:
    f=list(BANK.rglob(b["filename"]))
    ensure(len(f)==1 and sha(f[0])==b["sha256"] and f[0].stat().st_size==b["bytes"],
       "P4_FULL_ORIGINAL_PHYSICAL_BANK_SHA_ERROR:"+b["filename"])
    dest=basedir/b["filename"]
    ensure(not dest.exists() and not dest.is_symlink(),"BANK_STAGING_COLLISION")
    dest.symlink_to(f[0])
  CR.BANK_DIR=basedir
  bank=CR.load_banks()
  freq=np.asarray(bank[0]["freqs_hz"],dtype=float)
  ensure(np.array_equal(freq,6250400000.+DF*np.arange(N)),"ORIGINAL_FFD_FREQUENCY_DRIFT")
  setup=CR.CorridorSetup(anchor_x_m=16.0,anchor_y_m=.8)
  ensure(all(r["passed"] for r in setup.validate()),"BAD_C0_FIXED_CORRIDOR")
  scene,mesh=CR.build_scene(setup,OUT/"scene")
  original=J(ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/CASES.json")[0]["material_bindings"]
  observed={a["object"]:a["ply_sha256"] for a in mesh}
  expected={a["object"]:a["ply_sha256"] for a in original}
  ensure(observed==expected,"CORRIDOR_SIX_SURFACES_CHANGED")
  expected_materials={a["object"]:(a["itu_type"],a["thickness_m"]) for a in original}
  ensure(all((r["itu_type"],r["thickness_m"])==expected_materials[r["object"]] for r in mesh),
         "ORIGINAL_C0_RADIO_MATERIAL_DRIFT")
  scene.add(CR.rt.Transmitter("tx",position=setup.anchor_position.tolist(),
      orientation=CR.euler(CR.ANCHOR_ROTATION)))
  scene.add(CR.rt.Receiver("rx",position=setup.robot_position(7.,0.).tolist(),
      orientation=CR.euler(setup.robot_rotation(0.))))
  tx,rx=CR.make_ports(bank)
  solver=CR.rt.PathSolver()
  VER={n:__import__("importlib.metadata",fromlist=["version"]).version(n)
       for n in ("sionna-rt","mitsuba","drjit")}
  for n,e in (("sionna-rt","2.0.1"),("mitsuba","3.8.0"),("drjit","1.3.1")):
    ensure(VER[n]==e,"NATIVE_RT_RUNTIME_VERSION_DRIFT:"+n)
  return CR,mi,dr,setup,scene,solver,bank,freq,tx,rx,VER,observed
def set_pose(CR,mi,setup,scene,row):
  xy=(float(row["x_m"]),float(row["y_m"]))
  yaw=float(row["yaw_deg"])
  ensure(setup.robot_x_range_m[0]<=xy[0]<=setup.robot_x_range_m[1] and
      abs(xy[1])<=setup.robot_y_limit_m,"ROBOT_OUT_OF_FIXED_C0_CLEARANCE")
  scene.receivers["rx"].position=mi.Point3f(*setup.robot_position(*xy).tolist())
  scene.receivers["rx"].orientation=mi.Point3f(*CR.euler(setup.robot_rotation(yaw)))
  range_m=float(np.linalg.norm(setup.robot_position(*xy)-setup.anchor_position))
  return range_m
def solve(CR,solver,scene,banks,tx,rx,freq,fi,cfg):
  CR.set_bin(scene,banks,tx,rx,fi,float(freq[fi]))
  coef,tau,inter,obj=CR.solve(solver,scene,cfg)
  tau=np.asarray(tau,dtype=float).reshape(-1)
  coef=np.asarray(coef,dtype=np.complex128).reshape(2,2,len(tau))
  ensure(len(tau)>0 and np.isfinite(tau).all() and np.isfinite(coef).all(),
         "MISSING_OR_NONFINITE_NATIVE_PATH")
  H=np.sum(coef*np.exp(-2j*np.pi*float(freq[fi])*tau)[None,None,:],axis=-1)
  return H,tau,coef
def direct_index(tau,range_m,atol=1e-12):
  geometric_delay=range_m/C
  candidates=np.flatnonzero(abs(np.asarray(tau)-geometric_delay)<=atol)
  ensure(len(candidates)==1,"NO_UNIQUE_REAL_FULL_DIRECT_NATIVE_PATH:"+str(len(candidates)))
  return int(candidates[0])
def source_rows(cfg,lock):
  c=read_timeline(ROOT/cfg["inputs"]["old_39_csv"])
  old={(x["route"],int(x["pose_id"])):x for x in c}
  original_t={}
  for route in ("R2","R4","R5"):
    path=next(x["path"] for x in lock["base_assets"] if x["kind"]=="TIMELINE_TNONE" and
       "timeline_"+route+"_" in x["path"])
    tr=read_timeline(ROOT/path)
    expected=cfg["geometry"]["routes_n"][route]
    ensure(len(tr)==expected and len({int(z["pose_id"]) for z in tr})==expected,
      "ORIGINAL_C0_TIMELINE_DUPLICATE_OR_MISSING")
    for k,v in enumerate(tr):
      row=dict(route=route,pose_id=int(v["pose_id"]),t_s=float(v["t_s"]),
       x_m=float(v["x"]),y_m=float(v["y"]),yaw_deg=float(v["yaw_body_deg"]),
       original_timeline_index=k,source="ORIGINAL_C0_TNONE")
      original_t[route,row["pose_id"]]=row
  ensure(len(original_t)==3136 and len(old)==39,"FIXED_C0_OR_OLD_P3_SAMPLE_UNIVERSE_DRIFT")
  for key,row in old.items():
    source=original_t[key]
    for field,oldname,eps in (("x_m","x_m",1e-6),("y_m","y_m",1e-6),
         ("yaw_deg","yaw_deg",1e-6),("t_s","original_t_s",1e-9)):
      ensure(abs(source[field]-float(row[oldname]))<=eps,
         "P3_39_NOT_MATCHED_TO_C0_TIME_POSE:"+str(key)+":"+field)
  missing=[original_t[key] for key in sorted(original_t) if key not in old]
  ensure(len(missing)==3097,"MISSING_COUNT_CHANGED")
  return original_t,old,missing
def original_p3_h(cfg,route,pose_id):
  with zipfile.ZipFile(ROOT/cfg["inputs"]["old_39_zip"]) as z:
    name=f"traces/P3_NATIVE_C_{route}_pose{pose_id}_full.npz"
    with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as d:
      return d["H_native_full"].copy(),d["H_native_los"].copy(),d["full_path_counts"].copy()
def canary(cfg,p3,lock,args):
  original,old,missing=source_rows(cfg,lock)
  CR,mi,dr,setup,scene,solver,banks,freq,tx,rx,versions,meshes=stage_bank(cfg,p3,lock)
  samples=cfg["direct_path_option"]["smoke_pose_keys"]
  frequencies=cfg["direct_path_option"]["smoke_bin_indices"]
  rows=[];failed=[]
  fast_relmax=0.;full_relmax=0.;native_los_relmax=0.;max_tau=0.;full_countdiff=0
  for route,pose in samples:
    row=original[route,int(pose)]
    rng=set_pose(CR,mi,setup,scene,row)
    oldF,oldL,oldcount=original_p3_h(cfg,route,int(pose))
    for fi in frequencies:
      Hfull,tau,coef=solve(CR,solver,scene,banks,tx,rx,freq,fi,cfg["solver"]["full"])
      direct_id=direct_index(tau,rng,cfg["direct_path_option"]["max_delay_s"])
      H_direct=coef[:,:,direct_id]*np.exp(-2j*np.pi*freq[fi]*tau[direct_id])
      H_los,tau_l,_=solve(CR,solver,scene,banks,tx,rx,freq,fi,cfg["solver"]["los"])
      denominator=lambda x:max(np.linalg.norm(x),1e-300)
      def relative(x,y):return float(np.linalg.norm(x-y)/denominator(y))
      rowv=dict(route=route,pose_id=int(pose),fi=fi,
        path_count_full=len(tau),previous_p3_full_count=int(oldcount[fi]),
        full_vs_frozen_p3=relative(Hfull,oldF[fi]),
        direct_from_full_vs_fresh_native_los=relative(H_direct,H_los),
        direct_from_full_vs_original_native_los=relative(H_direct,oldL[fi]),
        fresh_native_los_vs_original=relative(H_los,oldL[fi]),
        direct_delay_abs_s=float(abs(tau[direct_id]-rng/C)))
      rows.append(rowv)
      fast_relmax=max(fast_relmax,rowv["direct_from_full_vs_fresh_native_los"],
         rowv["direct_from_full_vs_original_native_los"])
      full_relmax=max(full_relmax,rowv["full_vs_frozen_p3"])
      native_los_relmax=max(native_los_relmax,rowv["fresh_native_los_vs_original"])
      max_tau=max(max_tau,rowv["direct_delay_abs_s"])
      full_countdiff=max(full_countdiff,abs(len(tau)-int(oldcount[fi])))
    print("P4_FULL_NATIVE_CANARY_POSE",route,pose,"9bins",len(frequencies),
      "max_direct_rel",fast_relmax,"elapsed",round(time.monotonic()-START,2),flush=True)
  max_tol=float(cfg["direct_path_option"]["max_relative_complex_error"])
  enabled=fast_relmax<=max_tol and full_relmax<=max_tol and native_los_relmax<=max_tol and
      max_tau<=float(cfg["direct_path_option"]["max_delay_s"]) and full_countdiff==0
  # No threshold may be changed after results. Failing optimization is not
  # a solver failure: automatically use true separate NativeLoS per bin.
  decision="FULL_DIRECT_CERTIFIED" if enabled else "SEPARATE_FULL_AND_LOS"
  result=dict(schema="DLP_P4_FULL_NATIVE_RT_OPTIMIZATION_CANARY_V1",
   status="PASS_WITH_MODE_DECISION",algorithm_mode=decision,
   direct_from_full_permitted=bool(enabled),n_poses=len(samples),n_frequency_cases=len(rows),
   original_39_sha256=cfg["inputs"]["old_zip_sha256"],
   source_git_sha=os.environ.get("GITHUB_SHA"),runner_sha256=sha(__file__),
   exact_physical_solver_config=cfg["solver"],mesh_sha256=meshes,
   runtime_package_versions=versions,
   metrics=dict(max_full_vs_original=max(v["full_vs_frozen_p3"] for v in rows),
     max_direct_vs_native=max(v["direct_from_full_vs_fresh_native_los"] for v in rows),
     max_direct_vs_original=max(v["direct_from_full_vs_original_native_los"] for v in rows),
     max_fresh_los_vs_original=max(v["fresh_native_los_vs_original"] for v in rows),
     max_delay_s=max_tau,max_path_count_difference=full_countdiff),
   source_old_C_native_pose_ids=samples,frequency_bin_indices=frequencies,
   one_original_C0_scene=True,no_new_R4_EKF_run=True,
   failure_policy="Predeclared fallback to separate full+LoS if optimized direct path parity fails",
   example_rows=rows[:12],n_new_C_H_computed=0)
  (OUT/"P4_FULL_CANARY_QA.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
  with (OUT/"P4_FULL_CANARY_ALL_54_FREQUENCIES.csv").open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
  print("P4_FULL_CANARY_FINAL",decision,"max_direct_rel",fast_relmax,
    "max_full_rel",full_relmax,"freq_checked",len(rows),flush=True)
  return 0
def shard(cfg,p3,lock,args):
  assert args.route in ("R2","R4","R5")
  assert args.shard is not None
  original,old,missing=source_rows(cfg,lock)
  chunk=int(cfg["work"]["max_missing_poses_per_shard"])
  items=[x for x in missing if x["route"]==args.route]
  total=(len(items)+chunk-1)//chunk
  ensure(0<=args.shard<total,"OUT_OF_BOUNDS_SHARD")
  block=items[args.shard*chunk:(args.shard+1)*chunk]
  ensure(0<len(block)<=chunk,"EMPTY_SHARD")
  canary_path=CANARY/"P4_FULL_CANARY_QA.json"
  gate=J(canary_path)
  ensure(gate["status"]=="PASS_WITH_MODE_DECISION" and
       gate["algorithm_mode"] in ("FULL_DIRECT_CERTIFIED","SEPARATE_FULL_AND_LOS")
       and gate["n_frequency_cases"]==54 and gate["original_39_sha256"]==cfg["inputs"]["old_zip_sha256"],
       "NO_VERIFIED_FULL_C_NATIVE_CANARY")
  mode=gate["algorithm_mode"]
  CR,mi,dr,setup,scene,solver,banks,freq,tx,rx,versions,mesh=stage_bank(cfg,p3,lock)
  records=[];fail=[];native_solver_calls=0;actual_spotchecks=0
  for ii,row in enumerate(block):
    key=(row["route"],row["pose_id"])
    try:
      rng=set_pose(CR,mi,setup,scene,row)
      Hfull=np.zeros((N,2,2),np.complex128)
      Hlos=np.zeros_like(Hfull)
      countsF=np.zeros(N,np.int32);countsL=np.zeros(N,np.int32)
      offsetsF=[0];offsetsL=[0];tauF=[];tauL=[]
      max_direct_delay=0.;max_spotcheck=0.
      for fi in range(N):
        Hf,tau,coef=solve(CR,solver,scene,banks,tx,rx,freq,fi,cfg["solver"]["full"])
        native_solver_calls+=1
        direct=direct_index(tau,rng,cfg["direct_path_option"]["max_delay_s"])
        if mode=="FULL_DIRECT_CERTIFIED":
          Hd=coef[:,:,direct]*np.exp(-2j*np.pi*float(freq[fi])*tau[direct])
          Td=np.asarray([tau[direct]],dtype=float)
          if ii in (0,len(block)//2,len(block)-1) and fi in cfg["direct_path_option"]["worker_independent_spotcheck_bins"]:
            Href,ref_tau,_=solve(CR,solver,scene,banks,tx,rx,freq,fi,cfg["solver"]["los"])
            native_solver_calls+=1;actual_spotchecks+=1
            rel=float(np.linalg.norm(Hd-Href)/max(np.linalg.norm(Href),1e-300))
            max_spotcheck=max(max_spotcheck,rel)
            ensure(rel<=cfg["direct_path_option"]["max_relative_complex_error"],
                 "SHARD_FULL_DERIVED_DIRECT_LOS_VS_STANDALONE_MISMATCH")
        else:
          Hd,Td,_=solve(CR,solver,scene,banks,tx,rx,freq,fi,cfg["solver"]["los"])
          native_solver_calls+=1
          ensure(len(Td)==1,"NATIVE_LOS_ONLY_EXPECT_1_PATH")
        max_direct_delay=max(max_direct_delay,abs(float(Td[0])-rng/C))
        Hfull[fi]=Hf;Hlos[fi]=Hd
        countsF[fi]=len(tau);countsL[fi]=len(Td)
        tauF.extend(tau.tolist());tauL.extend(Td.tolist())
        offsetsF.append(len(tauF));offsetsL.append(len(tauL))
      ensure(max_direct_delay<=cfg["direct_path_option"]["max_delay_s"],
         "GEOMETRIC_DIRECT_DELAY_DRIFT")
      ensure(np.isfinite(Hfull).all() and np.isfinite(Hlos).all() and countsF.min()>=1 and countsL.min()==1,
         "INVALID_FULL_OR_LOS_NATIVE_H")
      d_full=make_observer(Hfull);d_los=make_observer(Hlos)
      file=f"P4_FULL_C_{args.route}_pose{row['pose_id']}_native.npz"
      np.savez_compressed(OUT/file,
        H_native_full=Hfull,H_native_los=Hlos,
        full_path_counts=countsF,los_path_counts=countsL,
        full_tau_s=np.asarray(tauF,float),los_tau_s=np.asarray(tauL,float),
        full_tau_offsets=np.asarray(offsetsF,np.int64),
        los_tau_offsets=np.asarray(offsetsL,np.int64),
        frequency_hz=freq,route=np.array(args.route),pose_id=np.array(int(row["pose_id"])),
        original_t_s=np.array(float(row["t_s"])),original_timeline_index=np.array(int(row["original_timeline_index"])),
        robot_xyz=np.array([row["x_m"],row["y_m"],.45],float),
        robot_yaw_deg=np.array(float(row["yaw_deg"])),
        anchor_xyz=setup.anchor_position,
        H_native_direct_method=np.array(mode),
        native_los_signed_s=np.array(d_los["signed_s"]),
        native_full_signed_s=np.array(d_full["signed_s"]),
        native_los_first_tap=np.array(d_los["tap"]),
        native_full_first_tap=np.array(d_full["tap"]),
        native_los_raw_r_m=np.array(d_los["r_m"]),
        native_full_raw_r_m=np.array(d_full["r_m"]))
      records.append(dict(route=args.route,pose_id=row["pose_id"],time_s=row["t_s"],
         original_timeline_index=row["original_timeline_index"],status="PASS",
         native_H_file=file,sha256=sha(OUT/file),bytes=(OUT/file).stat().st_size,
         full_paths_min=int(countsF.min()),full_paths_max=int(countsF.max()),
         los_paths_min=int(countsL.min()),los_paths_max=int(countsL.max()),
         max_direct_delay_s=float(max_direct_delay),
         max_spotcheck_los_complex_rel=float(max_spotcheck),
         native_full_s=d_full["signed_s"],native_los_s=d_los["signed_s"],
         native_full_raw_r_m=d_full["r_m"],native_los_raw_r_m=d_los["r_m"],
         native_full_first_tap=d_full["tap"],native_los_first_tap=d_los["tap"],
         direct_loS_from_actual_full_path=(mode=="FULL_DIRECT_CERTIFIED")))
      print("P4_C_NATIVE_SHARD_POSE",args.route,args.shard,row["pose_id"],
        "completed",len(records),"/",len(block),"calls",native_solver_calls,
        "elapsed_s",round(time.monotonic()-START,2),flush=True)
    except Exception as ex:
      fail.append(dict(route=args.route,pose_id=row["pose_id"],error=repr(ex),traceback=traceback.format_exc()))
      print("P4_C_NATIVE_SHARD_POSE_FAIL",args.route,row["pose_id"],repr(ex),flush=True)
      # Preserve invalid proof but do not silently generate missing NPZ.
      break
    finally:
      progress=dict(schema="P4_FULL_C_NEW_NATIVE_RT_SHARD_PROGRESS_V1",
       status="IN_PROGRESS" if ii+1<len(block) and not fail else ("FAIL" if fail else "COMPLETE"),
       route=args.route,shard=args.shard,algorithm=mode,n_expected=len(block),
       n_completed=len(records),records=records,failed=fail,runner_sha256=sha(__file__),
       pathsolver_calls=native_solver_calls,spotcheck_calls=actual_spotchecks,
       source_canary_run=gate.get("run_id"),one_simulation_scene_n=1,
       time_elapsed_s=time.monotonic()-START)
      (OUT/"P4_FULL_NATIVE_SHARD_RECEIPT.json").write_text(json.dumps(progress,indent=2,allow_nan=False)+"\n")
  status="PASS" if not fail and len(records)==len(block) else "FAIL"
  (OUT/"P4_FULL_NATIVE_SHARD_RECEIPT.json").write_text(json.dumps(dict(progress,status=status),indent=2,allow_nan=False)+"\n")
  print("P4_FULL_C_NATIVE_SHARD_FINAL",args.route,args.shard,status,
        "n",len(records),"of",len(block),"calls",native_solver_calls,flush=True)
  return 0 if status=="PASS" else 1

if __name__=="__main__":
  p=argparse.ArgumentParser()
  p.add_argument("--stage",choices=("canary","shard"),required=True)
  p.add_argument("--route",choices=("R2","R4","R5"),default=None)
  p.add_argument("--shard",type=int,default=None)
  args=p.parse_args()
  try:
    cfg,p3,lock=source_identity()
    if args.stage=="canary":rc=canary(cfg,p3,lock,args)
    else:rc=shard(cfg,p3,lock,args)
  except Exception as e:
    print("P4_FULL_NATIVE_FATAL",repr(e),traceback.format_exc(),flush=True)
    (OUT/"P4_FULL_NATIVE_FATAL.json").write_text(json.dumps(dict(
     status="BLOCKED",stage=args.stage,route=args.route,shard=args.shard,
     error=repr(e),traceback=traceback.format_exc(),
     code_sha256=sha(__file__),github_run=os.environ.get("GITHUB_RUN_ID")),indent=2)+"\n")
    rc=1
  sys.exit(rc)
