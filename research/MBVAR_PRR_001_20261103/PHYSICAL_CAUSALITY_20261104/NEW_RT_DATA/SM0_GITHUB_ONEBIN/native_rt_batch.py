#!/usr/bin/env python3
"""Native RT controlled floor+plate pilot. Default: no solver, static QA only."""
from __future__ import annotations
import argparse,csv,hashlib,importlib.metadata,json,math,os
import platform,sys,time,traceback
from pathlib import Path

HERE=Path(__file__).resolve().parent
for parent in (Path.cwd(), *HERE.parents):
    if (parent/"scripts/corridor_sionna_run.py").is_file():
        ROOT=parent
        break
else:raise RuntimeError("ERR_RT_ROOT_NOT_FOUND")
LOCK=HERE/"P3_NATIVE_CONTROLLED_SCENE_PREEXECUTION_LOCK_DRAFT.json"
ORIG=ROOT/"research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0/INPUT_LOCK_DRAFT_002.json"
BLOCK=Path("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C")
CASE="R4_aB_m0"
ARMS=("C00_DIRECT","C01_FLOOR","C10_PARALLEL_PLATE","C11_OBLIQUE_PLATE")
def demand(ok,why):
    if not bool(ok):raise RuntimeError(why)
def h(p):
    a=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):a.update(b)
    return a.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+"\n")
def preflight(bank=None):
    cfg=load(LOCK);orig=load(ORIG)
    demand(cfg["schema"]=="MBVAR_PRR_NATIVE_RT_PREEXECUTION_LOCK_V1","BAD_LOCK_SCHEMA")
    demand(cfg["pose_ids"]==[194,234,500,525],"POSE_SELECTION_CHANGED")
    demand([x["id"] for x in cfg["scenes"]]==list(ARMS),"ARM_UNIVERSE_CHANGED")
    demand(cfg["frequency"]["n_bins"]==257,"FREQUENCY_BINS_CHANGED")
    demand(cfg["simulated_workload"]["proposed_total_solver_calls_if_2_repeats"]==8224,"CALL_COUNT_WRONG")
    demand(cfg["governance"]["original_SM0_expansion"]=="NO-GO","ORIGINAL_STOP_CHANGED")
    demand(cfg["governance"]["HOLDOUT2"]=="NO-GO","HOLDOUT_OPENED")
    expected=orig["source_sha256"]
    for name,digest in cfg["original_source_sha256"].items():
        demand(expected.get(name)==digest,"CONTRACT_ORIGINAL_HASH_MISMATCH:"+name)
    required=["scripts/corridor_sionna_run.py",
       "scripts/g2_completion/sionna_native_runtime.py",
       "src/qclean_uwb/scenarios/corridor.py",
       "results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json",
       "results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json",
       str(BLOCK/"freqs_hz.npy"),str(BLOCK/"H_LoS_R4_aB_m0.npy"),
       str(BLOCK/CASE/"SAMPLES.json"),str(BLOCK/CASE/"MANIFEST.json"),
       str(BLOCK/"INPUTS/timeline_R4_Tnone.csv")]
    for name in required:
        file=ROOT/name
        demand(name in expected and file.is_file(),"MISSING_SOURCE:"+name)
        demand(h(file)==expected[name],"SOURCE_BYTES_CHANGED:"+name)
    manifest=load(ROOT/"results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json")
    demand(all(manifest["npz_sha256"].get(k)==v for k,v in cfg["original_ffd_sha256"].items()),
           "BANK_LP_PLUS_MINUS_MANIFEST_CHANGED")
    if bank is not None:
        for name,digest in cfg["original_ffd_sha256"].items():
            p=Path(bank)/name
            demand(p.is_file() and h(p)==digest,"BANK_SOURCE_SHA:"+name)
    s=load(ROOT/"results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json")["solver"]
    demand(s["max_depth"]==3 and s["seed"]==20260924,"SOLVER_SOURCE_CHANGED")
    demand(s["samples_per_src"]==100000 and s["max_num_paths_per_src"]==1000000,"SOLVER_COST_CHANGED")
    for arm in cfg["scenes"]:
        should=["floor","concrete_plate"] if arm["id"] in ARMS[2:] else ["floor"]
        demand(arm["objects"]==should,"ARM_OBJECTS_CHANGED")
        demand(arm["solver_max_depth"]==(0 if arm["id"]==ARMS[0] else 3),"ARM_DEPTH_CHANGED")
    for pose in cfg["pose_ids"]:get_pose(pose)
    return cfg,s
def get_pose(pose):
    rows=load(ROOT/BLOCK/CASE/"SAMPLES.json")
    hits=[r for r in rows if int(r["pose_id"])==pose]
    demand(len(hits)==1 and int(rows[pose]["pose_id"])==pose,"POSE_INDEX_CHANGED")
    raw=hits[0]
    with (ROOT/BLOCK/"INPUTS/timeline_R4_Tnone.csv").open(newline="") as f:
        match=[x for x in csv.DictReader(f) if int(x["pose_id"])==pose]
    demand(len(match)==1,"TIMELINE_KEY_MISSING")
    for key in ("x","y","yaw_body_deg"):
        demand(abs(float(raw[key])-float(match[0][key]))<=6e-7,"POSE_TIMELINE_MISMATCH:"+key)
    return {k:float(raw[k]) for k in ("x","y","yaw_body_deg")}
def check_runtime():
    required={"numpy":"1.26.4","scipy":"1.14.1","sionna-rt":"2.0.1",
              "mitsuba":"3.8.0","drjit":"1.3.1"}
    got={k:importlib.metadata.version(k) for k in required}
    demand(got==required and sys.version_info[:2]==(3,11),"RUNTIME_VERSION_MISMATCH")
    return got
def imports():
    sys.path[:0]=[str(ROOT/"scripts"),str(ROOT/"scripts/g2_completion"),str(ROOT/"src")]
    import mitsuba as mi,drjit as dr
    mi.set_variant("llvm_ad_mono_polarized")
    dr.set_thread_count(1)
    demand(mi.variant()=="llvm_ad_mono_polarized" and dr.thread_count()==1,"DRJIT_VARIANT")
    import sionna.rt as rt
    import corridor_sionna_run as C
    demand(Path(C.__file__).resolve()==(ROOT/"scripts/corridor_sionna_run.py").resolve(),
           "WRONG_CORRIDOR_IMPORT")
    return rt,C

def plate_vertices(cfg,yaw):
    import numpy as np
    p=cfg["plate"];x,y,_=p["center_xyz_m"]
    dx=p["width_m"]*.5*math.cos(math.radians(yaw))
    dy=p["width_m"]*.5*math.sin(math.radians(yaw))
    lo,hi=p["z_min_m"],p["z_max_m"]
    return np.array([[x-dx,y-dy,lo],[x+dx,y+dy,lo],
                     [x+dx,y+dy,hi],[x-dx,y-dy,hi]],float)
def build_scene(cfg,arm,pose,out,rt,C):
    import numpy as np
    setup=C.CorridorSetup(anchor_x_m=10.)
    demand(all(v["passed"] for v in setup.validate()),"CORRIDOR_SETUP_INVALID")
    pdir=out/"scene";pdir.mkdir()
    floor=pdir/"floor.ply"
    C.write_ply(floor,setup.surfaces()["floor"])
    parts=[rt.SceneObject(fname=str(floor),name="floor",
        radio_material=rt.ITURadioMaterial(name="rm_floor",
                                 itu_type="concrete",thickness=.2))]
    meshes={"floor":h(floor)}
    if arm in ARMS[2:]:
        info=next(x for x in cfg["scenes"] if x["id"]==arm)
        plate=pdir/"concrete_plate.ply"
        C.write_ply(plate,plate_vertices(cfg,float(info["plate_yaw_deg"])))
        parts.append(rt.SceneObject(fname=str(plate),name="concrete_plate",
            radio_material=rt.ITURadioMaterial(name="rm_plate",
                                   itu_type="concrete",thickness=.2)))
        meshes["concrete_plate"]=h(plate)
    scene=rt.load_scene()
    scene.edit(add=parts)
    anchor=setup.anchor_position;rx=setup.robot_position(pose["x"],pose["y"])
    scene.add(rt.Transmitter("tx",position=anchor.tolist(),
                            orientation=C.euler(C.ANCHOR_ROTATION)))
    scene.add(rt.Receiver("rx",position=rx.tolist(),
                          orientation=C.euler(setup.robot_rotation(pose["yaw_body_deg"]))))
    demand(np.linalg.norm(anchor-rx)>0,"ANCHOR_RX_COLLISION")
    return scene,anchor,rx,meshes
def archive_channel(a,tau,freq):
    import numpy as np
    phase=np.complex64(-2j*np.pi*float(freq))*tau
    return (a*np.exp(phase)[None,None,:]).sum(-1)

def firstpath(H):
    import numpy as np
    demand(H.shape==(257,2,2) and np.isfinite(H).all(),"FULL_H_NOT_FINITE")
    w=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
    cir=np.fft.ifft(H[:,:,0]*w[:,None],n=1028,axis=0)*257
    env=np.abs(cir); rx=int(np.argmax(env.max(axis=0)))
    mx=float(env[:,rx].max())
    demand(mx>0 and np.isfinite(mx),"CIR_ZERO_POWER")
    cand=np.flatnonzero(env[:,rx]>=.3*mx)
    demand(len(cand)>0,"FIRSTPATH_NOT_FOUND")
    tap=int(cand[0]);power=np.abs(cir[tap])**2
    total=float(power.sum());demand(total>0 and np.isfinite(total),"FIRSTPATH_ZERO_POWER")
    s=float((power[0]-power[1])/total)
    demand(abs(s)<=1+1e-12,"SIGNED_POLARIZATION_RANGE")
    return dict(fp_tap=tap,s=s,raw_r_m=tap*299792458/(1028*1950000),
                plus_power=float(power[0]),minus_power=float(power[1])),cir
def solver_options(original,arm):
    opts=dict(original)
    opts.update(max_depth=0 if arm=="C00_DIRECT" else 3,los=True,
                specular_reflection=arm!="C00_DIRECT",refraction=False,
                diffraction=False,edge_diffraction=False,diffuse_reflection=False)
    return opts
def check_budget(args,cfg):
    demand(args.token=="I_AUTHORIZE_CPU_RT_STAGE","MANUAL_TOKEN_REQUIRED")
    demand(args.max_calls==257 and 30<=args.wall_seconds<=3600,"CONFIG_BUDGET_INVALID")
    demand(args.budget is not None and args.budget.is_file(),"USER_BUDGET_RECORD_MISSING")
    budget=load(args.budget)
    demand(budget.get("status")=="USER_APPROVED_FOR_CPU_RT","USER_BUDGET_NOT_SIGNED")
    demand(budget.get("science_class")=="USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY",
           "BUDGET_CLAIM_INDEPENDENCE")
    demand(budget.get("max_solver_calls",0)>=257 and
           budget.get("max_solver_calls",0)<=8224 and
           budget.get("max_job_wall_seconds",0)>=args.wall_seconds,
           "BUDGET_CEILING_EXCEEDED")
    demand(budget.get("pose_ids")==cfg["pose_ids"] and
           budget.get("arm_ids")==list(ARMS),"BUDGET_SCOPE_NOT_LOCKED")
    return budget
def execute(args):
    import numpy as np
    cfg,orig=preflight(args.bank)
    demand(args.arm in ARMS and args.pose in cfg["pose_ids"] and
            args.repeat in (0,1),"UNREGISTERED_SIMULATION_KEY")
    budget=check_budget(args,cfg)
    if args.arm!="C00_DIRECT":
        demand(args.c00_qa and args.c00_qa.is_file(),"C00_QA_RECEIPT_MISSING")
        q=load(args.c00_qa)
        demand(q.get("status")=="C00_257BIN_STRICT_PARITY_PASS" and
               q.get("n_pass")==8 and q.get("lock_sha256")==h(LOCK),
               "C00_STRICT_PARITY_GATE_NOT_PASSED")
    runtime=check_runtime()
    pose=get_pose(args.pose)
    out=args.out
    demand(not out.exists(),"OUTPUT_WOULD_OVERWRITE_ORIGINAL")
    out.mkdir(parents=True)
    start=time.monotonic();calls=0
    result=dict(schema="MBVAR_P3_RT_CONTROLLED_PILOT_V1",
                status="RUN_STARTED",arm=args.arm,pose_id=args.pose,
                repeat_index=args.repeat,lock_sha256=h(LOCK),
                source_input_lock_sha256=h(ORIG),
                runtime=runtime,source_sha=os.getenv("GITHUB_SHA","LOCAL"),
                original_SM0_STOP_preserved=True,science_class="NONINDEPENDENT_EXPLORATORY",
                authorized_max_calls=257,budget=budget)
    save(out/"MANIFEST.json",result)
    try:
        rt,C=imports()
        C.BANK_DIR=args.bank
        banks=C.load_banks();freqs=np.asarray(banks[0]["freqs_hz"],float)
        demand(freqs.shape==(257,) and np.array_equal(freqs,
            np.load(ROOT/BLOCK/"freqs_hz.npy")),"FREQUENCY_GRID_DRIFT")
        scene,anchor,rx,meshes=build_scene(cfg,args.arm,pose,out,rt,C)
        ports=C.make_ports(banks);solver=rt.PathSolver()
        options=solver_options(orig,args.arm)
        H=np.empty((257,2,2),np.complex128);offsets=[0]
        all_a=[];all_tau=[];all_objects=[];all_inter=[]
        all_valid=[];pathcounts=[]
        for fi,freq in enumerate(freqs):
            demand(calls<args.max_calls,"MAX_SOLVER_CALLS")
            demand(time.monotonic()-start<args.wall_seconds,"WALL_CLOCK_LIMIT")
            C.set_bin(scene,banks,ports[0],ports[1],fi,float(freq))
            paths=solver(scene,**options)
            calls+=1
            tau=np.asarray(paths.tau).reshape(-1).copy();n=len(tau)
            demand(n>0 and np.isfinite(tau).all(),"EMPTY_OR_INVALID_PATH_TAU")
            a=(np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])).reshape(2,2,n)
            demand(np.isfinite(a).all(),"NONFINITE_PATH_COEFFICIENT")
            H[fi]=archive_channel(a,tau,freq)
            all_a.append(a.transpose(2,0,1).copy());all_tau.append(tau)
            all_objects.append(np.asarray(paths.objects).reshape(-1,n).T.copy())
            all_inter.append(np.asarray(paths.interactions).reshape(-1,n).T.copy())
            all_valid.append(np.asarray(paths.valid).reshape(-1,n).T.copy())
            pathcounts.append(n);offsets.append(offsets[-1]+n)
            if fi%32==0:print("RT_NATIVE_PROGRESS",args.arm,args.pose,args.repeat,fi+1,flush=True)
        obs,cir=firstpath(H)
        losdiff=None;parity="NOT_DIRECT"
        if args.arm=="C00_DIRECT":
            reference=np.load(ROOT/BLOCK/"H_LoS_R4_aB_m0.npy",mmap_mode="r")[args.pose,:,:,0]
            losdiff=float(np.linalg.norm(H[:,:,0]-reference)/(np.linalg.norm(reference)+1e-300))
            parity="PASS" if losdiff<=cfg["qa"]["original_archive_C00_LoS_max_rel_l2"] else "FAIL"
        np.savez_compressed(out/"RAW_COMPLEX_H_AND_PATHS.npz",
            H_complex_rx_rx_tx=H,complex_CIR=cir,frequencies_hz=freqs,
            offsets=np.asarray(offsets,np.int64),
            path_coefficient=np.concatenate(all_a),
            path_delay_s=np.concatenate(all_tau),
            path_objects=np.concatenate(all_objects),
            path_interactions=np.concatenate(all_inter),
            path_valid=np.concatenate(all_valid),
            path_counts=np.asarray(pathcounts,np.int32))
        result.update(status="COMPLETED" if parity!="FAIL" else "DIRECT_PARITY_FAIL",
            antenna_port_layout="257x2RXx2TX",mesh_sha256=meshes,
            anchor_xyz_m=anchor.tolist(),receiver_xyz_m=rx.tolist(),
            pose=pose,solver_options=options,observation=obs,
            direct_reference_relative_L2=losdiff,direct_parity=parity,
            source_reference_original_STOP_257bin="STOP_MISMATCH")
        print("RT_NATIVE_COMPLETED",args.arm,args.pose,args.repeat,"parity",parity,flush=True)
        demand(parity!="FAIL","ORIGINAL_DIRECT_PARITY_MISMATCH_PRESERVED")
    except BaseException as exc:
        result["status"]="STOP_WITH_RAW_EVIDENCE"
        result["error"]=repr(exc)
        result["traceback"]=traceback.format_exc()[-4500:]
        raise
    finally:
        result["solver_calls_made"]=calls
        result["total_wall_seconds"]=time.monotonic()-start
        result["file_sha256"]={p.name:h(p) for p in out.iterdir() if p.is_file() and p.name!="MANIFEST.json"}
        save(out/"MANIFEST.json",result)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--static",action="store_true")
    p.add_argument("--execute",action="store_true")
    p.add_argument("--bank",type=Path)
    p.add_argument("--arm",choices=ARMS)
    p.add_argument("--pose",type=int)
    p.add_argument("--repeat",type=int,default=0)
    p.add_argument("--out",type=Path)
    p.add_argument("--token",type=str)
    p.add_argument("--budget",type=Path)
    p.add_argument("--max-calls",type=int,default=257)
    p.add_argument("--wall-seconds",type=int,default=1200)
    p.add_argument("--c00-qa",type=Path)
    args=p.parse_args()
    if args.static:
        lock,solver=preflight(args.bank)
        print("RT_P3_STATIC_PREPARED_16_CONFIGURATIONS_8224_CALLS_UNAUTHORIZED")
        return
    demand(args.execute and args.bank and args.out and args.arm and args.pose is not None,
           "RT_EXECUTION_NOT_AUTHORIZED")
    execute(args)
if __name__=="__main__":main()
