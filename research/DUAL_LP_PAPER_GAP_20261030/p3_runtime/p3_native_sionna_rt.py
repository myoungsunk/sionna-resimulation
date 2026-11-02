#!/usr/bin/env python3
"""P3 C0+ actual Native Sionna-RT path canary. Not SourceFFD substitution.

FROZEN stage-1 smoke (3 fixed poses, 257 bins, Native LoS + max_depth=3 Full),
then stage-2 full 39 exact preselected poses (three route shards). Separate
original C0 and preceding SourceFFD output remain read-only and SHA verified.
Produces actual native paths.tau/counts, 2x2 complex H and independent
Hann/1028-tap detector r/s; signed residuals are descriptive, no EKF/P4.
"""
from __future__ import annotations
import argparse,csv,hashlib,importlib.metadata,json,math,os,pathlib,platform,subprocess,sys,time,traceback
from collections import Counter
import numpy as np

ROOT=pathlib.Path.cwd()
LOCK=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P3_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
P3_SRC=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/runs/P3_SOURCE_ONLY_CANARY_41390364274"
PILOT_ROOT=pathlib.Path(os.environ.get("DLP_FIXED_PILOT","/tmp/p3_native_fixed_pilot"))
BANKS=pathlib.Path(os.environ.get("DLP_FFD_BANKS","/tmp/p3_native_bank"))
ORIGINAL_MATS=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/CASES.json"
N=257;C=299792458.0;DF=1950000.0
CFG_LOCK_SHA="49658dc5532e990a9f8bc0968f96b46ce236167244762cbc817092ff34ce3fc8"
CONTRACT_SHA="24a5e0581c86a8b99659ebbea30b456fb79b6f4e88ee31860db04df85fafb588"
PRE_PLAN_SHA="efb9c7b1d91b865f143f8fa26fd3defb97eed02e385ee4137062ce336e9a0b61"
SRC_H_SHA="f30dcb0d6d16b112eda19a39f9a80618423d8b5e49c707cd3d236b037fc015f4"
AMPLITUDE_REL_TOL=5e-4;S_TOL=2e-5;TIME_TOL=1e-12;CONTROL_MAX_REL=2e-3
START=time.monotonic()
log_records=[];failures=[];gates={};files=[];manifest=None

def digest(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def J(path):return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
def require(ok,why):
    if not bool(ok):raise RuntimeError(why)
def gate(name,passed,info=None):
    gates[name]={"status":"PASS" if passed else "FAIL","info":info}
    print("P3_NATIVE_GATE",name,gates[name]["status"],str(info)[:500],flush=True)
    if not passed:failures.append(dict(stage="gate",id=name,info=info))
def independent_observer(H):
    H=np.asarray(H)
    require(H.shape==(N,2,2),"native H must be [257,2rx,2tx]")
    a=H[:,:,0]
    w=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
    h=np.fft.ifft(a*w[:,None],n=4*N,axis=0)*N
    env=np.abs(h)
    branch=int(env.max(axis=0).argmax())
    vmax=float(env[:,branch].max())
    require(vmax>0,"ZERO_RX_SIGNAL")
    tap=int(np.argmax(env[:,branch]>=.3*vmax))
    p=np.abs(h[tap])**2
    den=float(p.sum())
    require(den>0 and np.isfinite(den),"ZERO_POWER_ON_COMMON_FIRST_TAP")
    signed=float((p[0]-p[1])/den)
    raw_range=float(tap*C/(4*N*DF))
    require(abs(signed)<=1+1e-12,"SIGNED_S_INVALID")
    return dict(s=signed,r_m=raw_range,tap=tap,strong_rx=branch,powers=p.tolist())

def load_static(stage,route,out):
    am=J(LOCK/"P3_NATIVE_RT_APPEND_ONLY_AMENDMENT_V1.json")
    er=J(LOCK/"P3_NATIVE_RT_SOURCE_HASH_ERRATA_V1.json")
    p3=J(LOCK/"P3_CONFIG_LOCK.json")
    require(am["status"]=="FROZEN_EXECUTION_PERMISSION_FOR_BOUNDED_NATIVE_RT_CANARY","NO_EXPLICIT_RT_AMENDMENT")
    require(digest(LOCK/"P3_EXPERIMENT_CONTRACT_PROPOSER_LOCKED.md")==CONTRACT_SHA and
           digest(LOCK/"P3_CONFIG_LOCK.json")==CFG_LOCK_SHA,"P3_PREVIOUS_FROZEN_HASH_DRIFT")
    require(er["actual_source_path"]=="src/qclean_uwb/scenarios/corridor.py" and
           er["actual_git_blob"]=="eba1ab64d5e2117bfd519ceb5cac077b24caf3f8","INCORRECT_CORRIDOR_SOURCE_IDENTITY")
    for p,expected in [
      ("scripts/corridor_sionna_run.py",am["source_contract"]["corridor_sionna_py_git_blob"]),
      ("scripts/g2_completion/sionna_native_runtime.py",am["source_contract"]["ffd_adapter_py_git_blob"]),
      (er["actual_source_path"],er["actual_git_blob"]),
      ("results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json",
       am["source_contract"]["solver_config_blob"])]:
        sh=subprocess.check_output(["git","hash-object",p],text=True).strip()
        require(sh==expected,"SOLVER_SOURCE_GIT_BLOB_DRIFT:"+p)
    require(p3["scene"]["proposed_third"]["xyz_m"]==am["scene"]["new_C_xyz_m"]==[16,.8,2.65],
            "THIRD_ANCHOR_MOVED")
    path=PILOT_ROOT/"P3_FROZEN_PILOT_SELECTION_PLAN.json"
    require(digest(path)==PRE_PLAN_SHA,"39_POSE_PLAN_SHA_CHANGED")
    plan=J(path)
    require(plan["n_pilot_pose"]==39 and all(len(plan["routes"][r])==13 for r in ("R2","R4","R5")),
            "PLAN_NOT_PRESELECTED_13_PER_ROUTE")
    source=P3_SRC/"P3_C_SOURCE_ONLY_H_39_POSES.npy"
    require(digest(source)==SRC_H_SHA,"P3_SOURCE_REFERENCE_REPLACED")
    source_arr=np.load(source,allow_pickle=False,mmap_mode="r")
    source_keys=P3_SRC/"P3_C_SOURCE_ONLY_ARRAY_KEYS.csv"
    with source_keys.open(newline="") as f:k=list(csv.DictReader(f))
    require(len(k)==39 and source_arr.shape==(39,N,2),"SAVED_SOURCE_REFERENCE_MAPPING_INVALID")
    mapping={(r["route"],int(r["pose_id"])):int(r["source_array_row"]) for r in k}
    require(len(mapping)==39,"DUPLICATE_SOURCE_REFERENCE_KEYS")
    for rr,items in plan["routes"].items():
      require(all((rr,int(item["pose_id"])) in mapping for item in items),"MISSING_SOURCE_REFERENCE_KEYS")
    return am,plan,source_arr,mapping

def stage_banks(am):
    cache=ROOT
    for name,expect in [
       ("LP_plus45_bank.npz",am["actual_original_bank"]["LP_plus45_bank_npz_sha256"]),
       ("LP_minus45_bank.npz",am["actual_original_bank"]["LP_minus45_bank_npz_sha256"])]:
       matches=list(BANKS.rglob(name))
       require(len(matches)==1,"BANK_MISSING_OR_DUPLICATE:"+name)
       p=matches[0]
       require(digest(p)==expect,"REAL_FFD_BANK_HASH_NOT_MATCHED:"+name)
       target=cache/name
       require(not target.exists() and not target.is_symlink(),"SCRATCH_BANK_COLLISION")
       target.symlink_to(p)
    old=J(ROOT/"results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json")
    require(old["npz_sha256"]["LP_plus45_bank.npz"]==am["actual_original_bank"]["LP_plus45_bank_npz_sha256"]
        and old["npz_sha256"]["LP_minus45_bank.npz"]==am["actual_original_bank"]["LP_minus45_bank_npz_sha256"],
        "SIONNA_CANONICAL_FFD_MANIFEST_MISMATCH")
    import corridor_sionna_run as CR
    CR.BANK_DIR=cache
    banks=CR.load_banks()
    freq=np.asarray(banks[0]["freqs_hz"])
    require(np.array_equal(freq,6250400000.+DF*np.arange(N)),"FREQUENCY_GRID_NOT_ORIGINAL_C0")
    return CR,banks,freq

def geometry_checks(CR,am,setup,scene_dir,expected_anchor_xyz=None):
    import numpy as np
    # New C run is locked to C. The historical positive control MUST use A.
    # Caller-provided expectation is allowed only for the original A control.
    locked_C=np.asarray(am["scene"]["new_C_xyz_m"],float)
    expected=locked_C if expected_anchor_xyz is None else np.asarray(expected_anchor_xyz,float)
    require(np.array_equal(expected,locked_C) or np.array_equal(expected,[4.,0.,2.65]),
            "UNAUTHORIZED_ANCHOR_EXPECTATION")
    require(CR.np.allclose(setup.anchor_position,expected,atol=1e-12,rtol=0),
            "SCENE_ANCHOR_NOT_AS_SPECIFIED")
    require(CR.np.allclose(CR.ANCHOR_ROTATION,np.diag([1.,-1.,-1.])), "TX_BORESIGHT_DRIFT")
    validation=setup.validate()
    require(all(q["passed"] for q in validation),"CORRIDOR_SETUP_INVALID:"+str(validation))
    # Real material mesh hashes must equal original C0, otherwise the RF
    # environment changed; no blanket geometry equivalence is invented.
    original=J(ORIGINAL_MATS)[0]["material_bindings"]
    expected={z["object"]:z["ply_sha256"] for z in original}
    scene,bindings=CR.build_scene(setup,scene_dir)
    observed={z["object"]:z["ply_sha256"] for z in bindings}
    require(observed==expected,"C0_SURFACE_MESH_SHA_CHANGED:"+str({k:[observed.get(k),v] for k,v in expected.items() if observed.get(k)!=v}))
    for z in original:
       expect=am["scene"]["materials"][z["object"]]
       require([z["itu_type"],z["thickness_m"]]==expect,"SCENE_MATERIAL_CHANGED:"+z["object"])
    return scene,bindings,observed

def solve_one(CR,solver,scene,cfg,fi,freq,banks,ports,mode):
    txp,rxp=ports
    CR.set_bin(scene,banks,txp,rxp,fi,freq[fi])
    raw=solver(scene,**cfg)
    aa=np.asarray(raw.a[0])+1j*np.asarray(raw.a[1])
    tau=np.asarray(raw.tau).reshape(-1)
    n=int(tau.size)
    require(n>=1,"NO_PHYSICAL_NATIVE_PATH:"+mode+":bin"+str(fi))
    coef=np.asarray(aa).reshape((2,2,n))
    require(np.isfinite(coef).all() and np.isfinite(tau).all(),"NONFINITE_NATIVE_PATH:"+mode)
    H=(coef*np.exp(-2j*np.pi*float(freq[fi])*tau)[None,None,:]).sum(axis=-1)
    return np.asarray(H,np.complex128),tau,np.asarray(coef,np.complex128)

def native_pose(CR,setup,solver,bank,freq,am,plan,source_arr,mapping,row,stage,output):
    import mitsuba as mi
    route=row["route"];pose_id=int(row["pose_id"])
    source_pos=mapping[(route,pose_id)]
    source_H=np.asarray(source_arr[source_pos],np.complex128)
    x=float(row["x_m"]);y=float(row["y_m"]);yaw=float(row["yaw_body_deg"])
    require(1.0<=x<=19.0 and abs(y)<=setup.robot_y_limit_m,"ROBOT_POSE_NOT_IN_CLEAR_REGION")
    scene_folder=output/"_scene"/f"{route}_{pose_id}"
    scene,bindings,mesh_sha=geometry_checks(CR,am,setup,scene_folder)
    scene.add(CR.rt.Transmitter("tx",position=setup.anchor_position.tolist(),orientation=CR.euler(CR.ANCHOR_ROTATION)))
    scene.add(CR.rt.Receiver("rx",position=setup.robot_position(x,y).tolist(),
                             orientation=CR.euler(setup.robot_rotation(yaw))))
    tx,rx=CR.make_ports(bank)
    full=am["rf"]["solver_full"]
    los=am["rf"]["solver_los"]
    require(full==J(ROOT/"results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json")["solver"],
        "PINNED_FULL_RT_SOLVER_CONFIG_CHANGED")
    Hlos=np.empty((N,2,2),np.complex128);Hfull=np.empty_like(Hlos)
    los_counts=np.zeros(N,np.int32);full_counts=np.zeros(N,np.int32)
    los_offsets=[0];full_offsets=[0];los_tau=[];full_tau=[]
    timing=time.monotonic()
    for fi in range(N):
       mode_los,t_los,_=solve_one(CR,solver,scene,los,fi,freq,bank,(tx,rx),"LOS")
       mode_full,t_full,_=solve_one(CR,solver,scene,full,fi,freq,bank,(tx,rx),"FULL")
       Hlos[fi]=mode_los;Hfull[fi]=mode_full
       los_counts[fi]=len(t_los);full_counts[fi]=len(t_full)
       los_tau.extend(t_los.tolist());full_tau.extend(t_full.tolist())
       los_offsets.append(len(los_tau));full_offsets.append(len(full_tau))
       if fi in (0,64,128,192,256):
         print("P3_NATIVE_FREQ",route,pose_id,fi,"los_paths",len(t_los),"full_paths",len(t_full),
               "elapsed_s",round(time.monotonic()-timing,1),flush=True)
    ob_los=independent_observer(Hlos);ob_full=independent_observer(Hfull)
    src_ind=np.empty((N,2,2),dtype=np.complex128)
    src_ind[:,:,0]=source_H
    src_ind[:,:,1]=0
    ob_source=independent_observer(src_ind)
    denom=max(np.linalg.norm(source_H),1e-300)
    hrel=float(np.linalg.norm(Hlos[:,:,0]-source_H)/denom)
    serr=float(abs(ob_los["s"]-ob_source["s"]))
    taperr=int(ob_los["tap"]!=ob_source["tap"])
    xyz=setup.robot_position(x,y)
    physical_range=float(np.linalg.norm(xyz-setup.anchor_position))
    tau_model=physical_range/299792458.
    los_tau_min=np.asarray([np.min(np.asarray(los_tau)[los_offsets[i]:los_offsets[i+1]]) for i in range(N)])
    tauerr=float(np.max(abs(los_tau_min-tau_model)))
    checks={
      "source_complex_rel":hrel,
      "source_signed_s_abs":serr,
      "source_first_tap_mismatch":taperr,
      "native_los_delay_max_abs_s":tauerr,
      "path_counts_los_min":int(los_counts.min()),
      "path_counts_los_max":int(los_counts.max()),
      "path_counts_full_min":int(full_counts.min()),
      "path_counts_full_max":int(full_counts.max()),
      "path_count_full_multi_fraction":float(np.mean(full_counts>1)),
      "source_H_first_path_r_m":ob_source["r_m"],
      "native_los_first_path_r_m":ob_los["r_m"],
      "native_full_first_path_r_m":ob_full["r_m"],
      "native_los_signed_s":ob_los["s"],
      "native_full_signed_s":ob_full["s"],
      "native_los_first_tap":ob_los["tap"],
      "native_full_first_tap":ob_full["tap"],
      "full_minus_los_signed_s":ob_full["s"]-ob_los["s"],
    }
    stable=(hrel<=AMPLITUDE_REL_TOL and serr<=S_TOL and taperr==0 and
            tauerr<=TIME_TOL and los_counts.min()>=1 and full_counts.min()>=1)
    filename=f"P3_NATIVE_C_{route}_pose{pose_id}_{stage}.npz"
    np.savez_compressed(output/filename,
        H_native_los=Hlos,H_native_full=Hfull,
        frequency_hz=np.asarray(freq),
        los_path_counts=los_counts,full_path_counts=full_counts,
        los_tau_s=np.asarray(los_tau,dtype=float),full_tau_s=np.asarray(full_tau,dtype=float),
        los_tau_offsets=np.asarray(los_offsets,dtype=np.int64),
        full_tau_offsets=np.asarray(full_offsets,dtype=np.int64),
        route=np.array(route),pose_id=np.array(pose_id),
        time_s=np.array(float(row["t_s"])),
        robot_xyz=xyz,robot_yaw_deg=np.array(yaw),
        anchor_xyz=setup.anchor_position,
        source_comparison_s=np.array(ob_source["s"]),
        source_comparison_H_sha256=np.array(SRC_H_SHA),
        native_los_signed_s=np.array(ob_los["s"]),
        native_full_signed_s=np.array(ob_full["s"]),
        native_los_r_m=np.array(ob_los["r_m"]),
        native_full_r_m=np.array(ob_full["r_m"]),
        native_los_tap=np.array(ob_los["tap"]),
        native_full_tap=np.array(ob_full["tap"]))
    result=dict(route=route,pose_id=pose_id,stage=stage,
       time_s=float(row["t_s"]),pos_xy_m=[x,y],yaw_deg=yaw,
       new_anchor_xyz=setup.anchor_position.tolist(),
       status="PASS" if stable else "FAIL_PHYSICAL_C0PLUS_CANARY",
       source_reference="PRIOR_SOURCE_ONLY_C39_NOT_NATIVE_RT",
       native_paths_are_actual_solver=True,solver_backend="llvm_ad_mono_polarized",
       bins=N,solver_calls=514,material_mesh_sha256=mesh_sha,
       two_rx_two_tx_native_H=True,
       file=filename,file_sha256=digest(output/filename),bytes=(output/filename).stat().st_size,
       measured=checks,elapsed_s=time.monotonic()-timing)
    (output/(filename.replace(".npz",".json"))).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result

def smoke_control_A(CR,banks,freq,plan,am,solver,output):
    """Positive control: native RT for EXISTING anchor A against real archived A H.
    Three original frequencies only; original 7-case H remains read-only.
    """
    setup=CR.CorridorSetup(anchor_x_m=4,anchor_y_m=0.0)
    old=J(P1/"P1_INPUT_LOCK.json")
    controls=[]
    for row in am["bounded_work"]["smoke"]:
        route=row["route"];p=int(row["pose_id"])
        item=next(v for v in plan["routes"][route] if int(v["pose_id"])==p)
        case=next(c for c in old["primary_cases"] if c["case_id"]==route+"_aA_m0")
        Hlos=np.load(ROOT/case["los_path"],allow_pickle=False,mmap_mode="r")
        Hfull=np.load(ROOT/case["full_path"],allow_pickle=False,mmap_mode="r")
        scene_dir=output/"_control_scene"/route
        scene,_,_=geometry_checks(CR,am,setup,scene_dir,expected_anchor_xyz=[4.,0.,2.65])
        scene.add(CR.rt.Transmitter("tx",position=setup.anchor_position.tolist(),orientation=CR.euler(CR.ANCHOR_ROTATION)))
        scene.add(CR.rt.Receiver("rx",position=setup.robot_position(item["x_m"],item["y_m"]).tolist(),
              orientation=CR.euler(setup.robot_rotation(item["yaw_body_deg"]))))
        tx,rx=CR.make_ports(banks)
        for fi in (0,128,256):
            h0,_,_=solve_one(CR,solver,scene,am["rf"]["solver_los"],fi,freq,banks,(tx,rx),"CONTROL_A_LOS")
            h1,_,_=solve_one(CR,solver,scene,am["rf"]["solver_full"],fi,freq,banks,(tx,rx),"CONTROL_A_FULL")
            lo=float(np.linalg.norm(h0-Hlos[p,fi])/max(np.linalg.norm(Hlos[p,fi]),1e-300))
            fu=float(np.linalg.norm(h1-Hfull[p,fi])/max(np.linalg.norm(Hfull[p,fi]),1e-300))
            controls.append(dict(route=route,pose_id=p,bin=fi,original_A_LOS_complex_rel=lo,
                         original_A_FULL_complex_rel=fu,threshold=CONTROL_MAX_REL))
    maximum=max(max(c["original_A_LOS_complex_rel"],c["original_A_FULL_complex_rel"]) for c in controls)
    gate("SMOKE_POSITIVE_CONTROL_ORIGINAL_ANCHOR_A",maximum<=CONTROL_MAX_REL,
        dict(n=len(controls),max_rel=maximum,threshold=CONTROL_MAX_REL))
    (output/"A_ORIGINAL_NATIVE_POSITIVE_CONTROL.json").write_text(json.dumps(controls,indent=2)+"\n")

def main(args):
    global manifest
    output=pathlib.Path(args.out)
    output.mkdir(parents=True,exist_ok=True)
    print("P3_NATIVE_EXECUTOR_START",args.stage,args.route,"cwd",ROOT,flush=True)
    am,plan,source_arr,mapping=load_static(args.stage,args.route,output)
    sys.path.insert(0,str(ROOT/"scripts"))
    sys.path.insert(0,str(ROOT/"src"))
    sys.path.insert(0,str(ROOT/"scripts/g2_completion"))
    import mitsuba as mi
    mi.set_variant("llvm_ad_mono_polarized")
    import drjit as dr
    dr.set_thread_count(1)
    import corridor_sionna_run as CR
    CR,bank,freq=stage_banks(am)
    installed={n:importlib.metadata.version(n) for n in ("sionna-rt","mitsuba","drjit","numpy","scipy")}
    for n,version in [("sionna-rt","2.0.1"),("mitsuba","3.8.0"),("drjit","1.3.1")]:
       require(installed[n]==version,"SIONNA_PINNED_PACKAGE_VERSION_CHANGED:"+n+":"+installed[n])
    print("P3_NATIVE_CPU_RUNTIME",json.dumps(installed),flush=True)
    solver=CR.rt.PathSolver()
    setup=CR.CorridorSetup(anchor_x_m=16.0,anchor_y_m=.8)
    if args.stage=="smoke":
      poses=[next(p for p in plan["routes"][row["route"]]
                  if int(p["pose_id"])==int(row["pose_id"])) | {"route":row["route"]}
             for row in am["bounded_work"]["smoke"]]
      max_calls=am["bounded_work"]["smoke_solver_calls"]
    else:
      require(args.route in ("R2","R4","R5"),"INVALID_ROUTE")
      poses=[p|{"route":args.route} for p in plan["routes"][args.route]]
      max_calls=13*514
    require(len(poses)==(3 if args.stage=="smoke" else 13),"EXCEEDS_FIXED_POSE_BUDGET")
    require(max_calls==len(poses)*514,"P3_CALL_BUDGET_CHANGED")
    manifest={"schema":"P3_NATIVE_C_RT_CANARY_V1","stage":args.stage,"route":args.route,
      "status":"STARTED","expected_pose_count":len(poses),
      "expected_solver_calls":max_calls,"native_method":"Sionna-RT PathSolver, native full and native LoS",
      "original_C0_scene_count":1,"rt_not_measurement":True,
      "fixed_candidate_C":[16.,.8,2.65],"source_plan_sha256":PRE_PLAN_SHA,
      "saved_source_only_H_sha256":SRC_H_SHA,
      "software":installed,"original_locked_source_sha256":CONTRACT_SHA,
      "results":[],"failures":[],"code_sha256":digest(__file__),
      "started_utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
    (output/"P3_NATIVE_PROGRESS.json").write_text(json.dumps(manifest,indent=2)+"\n")
    all_results=[]
    for row in poses:
      try:
        res=native_pose(CR,setup,solver,bank,freq,am,plan,source_arr,mapping,row,args.stage,output)
        all_results.append(res);log_records.append(res)
        print("P3_NATIVE_POSE_COMPLETE",json.dumps({k:res[k] for k in ("route","pose_id","stage","status","elapsed_s")}),flush=True)
        if res["status"]!="PASS":
           failures.append(dict(kind="POSE_GATE",route=res["route"],pose_id=res["pose_id"],measured=res["measured"]))
      except Exception as e:
        item=dict(kind="POSE_CRASH",route=row["route"],pose_id=row["pose_id"],
                  detail=repr(e),traceback=traceback.format_exc())
        failures.append(item)
        print("P3_NATIVE_POSE_FATAL",repr(e),traceback.format_exc(),flush=True)
      manifest["results"]=all_results
      manifest["failures"]=failures
      (output/"P3_NATIVE_PROGRESS.json").write_text(json.dumps(manifest,indent=2)+"\n")
      if failures:break  # fail-closed; no outcome-based dropping, preserve exactly where stopped
    gate("NATIVE_C_LOS_AND_FULL_FIXED_POSES",len(all_results)==len(poses) and not failures,
         dict(n=len(all_results),expected=len(poses),failures=failures[:3]))
    if args.stage=="smoke" and not failures:
      smoke_control_A(CR,bank,freq,plan,am,solver,output)
    gate("SIONNA_NATIVE_PATH_METADATA",all(r["measured"]["path_counts_full_min"]>=1 and
         r["measured"]["path_counts_los_min"]>=1 for r in all_results) and len(all_results)==len(poses),
         dict(n=len(all_results),full_multi_bins=sum(int(r["measured"]["path_count_full_multi_fraction"]*N)
                    for r in all_results)))
    manifest["status"]="PASS" if not failures and not any(g["status"]=="FAIL" for g in gates.values()) else "FAIL"
    manifest["results"]=all_results;manifest["failures"]=failures;manifest["gates"]=gates
    manifest["solver_calls_per_pose"]=514
    manifest["pose_count"]=len(all_results)
    manifest["end_utc"]=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    manifest["runtime_s"]=time.monotonic()-START
    (output/"P3_NATIVE_EXECUTION_QA.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    print("P3_NATIVE_EXECUTION_END",manifest["status"],"poses",len(all_results),
          "failure_count",len(failures),"stage",args.stage,"route",args.route,flush=True)
    return 0 if manifest["status"]=="PASS" else 1

if __name__=="__main__":
   p=argparse.ArgumentParser()
   p.add_argument("--stage",choices=("smoke","full"),required=True)
   p.add_argument("--route",choices=("R2","R4","R5"),default=None)
   p.add_argument("--out",required=True)
   args=p.parse_args()
   try:code=main(args)
   except Exception as e:
      output=pathlib.Path(args.out);output.mkdir(parents=True,exist_ok=True)
      err=dict(stage=args.stage,route=args.route,status="BLOCKED",error=repr(e),
               traceback=traceback.format_exc(),time_s=time.monotonic()-START)
      (output/"P3_NATIVE_FATAL.json").write_text(json.dumps(err,indent=2)+"\n")
      print("P3_NATIVE_FATAL",repr(e),traceback.format_exc(),flush=True)
      code=1
   sys.exit(code)
