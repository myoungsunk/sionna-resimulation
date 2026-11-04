#!/usr/bin/env python3
"""One-bin native Sionna RT exploratory diagnosis, NOT original SM0 replacement.

One R4-B pose (194), one original center-frequency bin (128), one PathSolver
call, direct-only depth 0. No other pose, no full spectrum, no reflection
attribution, no old gate override. Original SM0 STOP_MISMATCH stays STOP.
"""
from __future__ import annotations
import csv, hashlib, importlib.metadata, json, math, os
from pathlib import Path
import platform, sys, time, traceback
import numpy as np

ROOT=Path.cwd()
ROOT_SM0=ROOT/"research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0"
LOCK=ROOT_SM0/"INPUT_LOCK_DRAFT_002.json"
BLOCK="results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
CFG="results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json"
BANK="results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json"
CASE="R4_aB_m0"; PID=194; FI=128
SOURCE_FILES=[
    "scripts/corridor_sionna_run.py",
    "scripts/g2_completion/sionna_native_runtime.py",
    "src/qclean_uwb/scenarios/corridor.py",
    "src/qclean_uwb/drivesim/observation.py",
    CFG, BANK,
    BLOCK+"/freqs_hz.npy",
    BLOCK+"/H_LoS_R4_aB_m0.npy",
    BLOCK+"/R4_aB_m0/MANIFEST.json",
    BLOCK+"/R4_aB_m0/SAMPLES.json",
    BLOCK+"/INPUTS/timeline_R4_Tnone.csv",
]
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as fh:
        for b in iter(lambda:fh.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()
def require(ok,reason):
    if not ok:raise RuntimeError(reason)
def write_json(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def main(outdir,bankdir):
    out=Path(outdir)
    require(not out.exists(),"ERR_RT_ONEBIN_OUTPUT_ALREADY_EXISTS")
    out.mkdir(parents=True)
    receipt=dict(schema="MBVAR_PRR_SM0_ONEBIN_NEW_EXPLORATORY_NATIVE_RT_V1",
                 authority="USER_DIRECT_REQUEST_2026_11_04",
                 source_pr28_sha="5e13c6025074d74c90644412d5a006f6c2a20e13",
                 source="Original R4-B 194 archived field; one frequency bin only",
                 case=CASE,pose_id=PID,frequency_bin=FI,max_solver_calls=1,
                 max_unique_pose_configs=1,full_257_bin_verified=False,
                 original_SM0_first_pose_STOP_preserved=True,
                 method="REAL_SIONNA_PATHSOLVER_ONE_BIN_DIRECT_ONLY",
                 r5_or_a010_science_claim=False,dev3_independent=False,
                 original_direct_f64_257bin_relative_L2=2.4708055186762222e-5,
                 original_direct_f64_strict_tol=1e-5,
                 independent_auditor_signed=False, status="PREFLIGHT_RUNNING")
    write_json(out/"MANIFEST.json",receipt)
    started=time.monotonic();calls=0
    try:
        lock=json.loads(LOCK.read_text())
        expected=lock["source_sha256"]
        for file in SOURCE_FILES:
            require(file in expected,"ERR_RT_SOURCE_NOT_IN_PRIOR_MANIFEST "+file)
            p=ROOT/file
            require(p.is_file(),"ERR_RT_SOURCE_MISSING "+file)
            require(sha(p)==expected[file],"ERR_RT_SOURCE_SHA "+file)
        require(sha(LOCK)!="", "ERR_RT_LOCK_FILE")
        banks_expected=lock["bank_sha256"]
        for n in ("LP_plus45_bank.npz","LP_minus45_bank.npz"):
            p=Path(bankdir)/n
            require(p.is_file(),"ERR_RT_BANK_MISSING "+n)
            require(sha(p)==banks_expected[n],"ERR_RT_BANK_SHA "+n)
        data=json.loads((ROOT/BLOCK/CASE/"SAMPLES.json").read_text())
        pose=data[PID]
        require(int(pose["pose_id"])==PID,"ERR_RT_POSE_SOURCE_ID")
        trows=list(csv.DictReader((ROOT/BLOCK/"INPUTS/timeline_R4_Tnone.csv").open()))
        q=[x for x in trows if int(x["pose_id"])==PID]
        require(len(q)==1,"ERR_RT_TIMELINE_ID")
        for key in ("x","y","yaw_body_deg"):
            require(abs(float(pose[key])-float(q[0][key]))<=6e-7,"ERR_RT_POSE_TIMELINE_"+key)
        freq_archive=np.load(ROOT/BLOCK/"freqs_hz.npy",allow_pickle=False)
        require(freq_archive.ndim==1 and len(freq_archive)==257,"ERR_RT_FREQUENCY_COUNT")
        require(FI==128,"ERR_RT_ONEBIN_NOT_FROZEN")
        cjson=json.loads((ROOT/CFG).read_text())["solver"]
        require(cjson["seed"]==20260924 and cjson["max_depth"]==3,"ERR_RT_ORIGINAL_SOLVER_NOT_LOCKED")
        versions={n:importlib.metadata.version(n) for n in
                  ("numpy","scipy","sionna-rt","mitsuba","drjit")}
        required=dict(numpy="1.26.4",scipy="1.14.1",**{
                       "sionna-rt":"2.0.1","mitsuba":"3.8.0","drjit":"1.3.1"})
        require(versions==required,"ERR_RT_VERSIONS "+str(versions))
        import mitsuba as mi,drjit as dr
        mi.set_variant("llvm_ad_mono_polarized")
        require(mi.variant()=="llvm_ad_mono_polarized","ERR_RT_VARIANT")
        dr.set_thread_count(1)
        require(dr.thread_count()==1,"ERR_RT_THREADS")
        import sionna.rt as rt
        # Checkout alone does not add repository scripts/ to Python sys.path.
        # Both the direct script and the GitHub workflow must use pinned
        # imports; never substitute an unrelated package named corridor_*.
        sys.path.insert(0,str(ROOT/"scripts"))
        sys.path.insert(0,str(ROOT/"scripts"/"g2_completion"))
        sys.path.insert(0,str(ROOT/"src"))
        require((ROOT/"scripts"/"corridor_sionna_run.py").is_file(),
                "ERR_RT_ORIGINAL_CORRIDOR_MODULE_MISSING")
        import corridor_sionna_run as C
        C.BANK_DIR=Path(bankdir)
        banks=C.load_banks()
        freqs=np.asarray(banks[0]["freqs_hz"],float)
        require(np.array_equal(freqs,freq_archive),"ERR_RT_FREQUENCY_ARRAY")
        setup=C.CorridorSetup(anchor_x_m=10.)
        require(all(t["passed"] for t in setup.validate()),"ERR_RT_CORRIDOR_GEOMETRY")
        scene,bindings=C.build_scene(setup,out/"scene")
        expected_mesh={x["object"]:x["ply_sha256"] for x in
            json.loads((ROOT/BLOCK/CASE/"MANIFEST.json").read_text())["material_bindings"]}
        actual_mesh={x["object"]:x["ply_sha256"] for x in bindings}
        require(actual_mesh==expected_mesh,"ERR_RT_MESH_SHA")
        tx=setup.anchor_position;rx=setup.robot_position(float(pose["x"]),float(pose["y"]))
        scene.add(rt.Transmitter("tx",position=tx.tolist(),orientation=C.euler(C.ANCHOR_ROTATION)))
        scene.add(rt.Receiver("rx",position=rx.tolist(),
                             orientation=C.euler(setup.robot_rotation(float(pose["yaw_body_deg"])))))
        ports=C.make_ports(banks)
        C.set_bin(scene,banks,ports[0],ports[1],FI,float(freqs[FI]))
        cfg=dict(cjson)
        cfg.update(max_depth=0,los=True,specular_reflection=False,
                   refraction=False,diffraction=False,edge_diffraction=False,
                   diffuse_reflection=False)
        # The exact maximum count is independently enforced by this script:
        require(calls==0,"ERR_RT_SOLVER_BUDGET_EXCEEDED")
        solver=rt.PathSolver()
        start_solve=time.monotonic()
        paths=solver(scene,**cfg)
        calls+=1
        tau=np.asarray(paths.tau).reshape(-1).copy()
        a=np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])
        n=len(tau)
        require(n>=1,"ERR_RT_NO_DIRECT_LOS_PATH")
        H64=(a.reshape(2,2,n).astype(np.complex128)*
             np.exp(-2j*np.pi*float(freqs[FI])*tau.astype(float))[None,None,:]).sum(axis=-1)
        H32=(a.reshape(2,2,n)*np.exp(-2j*np.pi*np.float32(freqs[FI])*tau.astype(np.float32))[None,None,:]).sum(axis=-1)
        archived=np.load(ROOT/BLOCK/"H_LoS_R4_aB_m0.npy",mmap_mode="r")[PID,FI,:,0]
        direct64=np.asarray(H64[:,0],np.complex128)
        direct32=np.asarray(H32[:,0],np.complex128)
        ref=np.asarray(archived,np.complex128)
        err64=float(np.linalg.norm(direct64-ref)/(np.linalg.norm(ref)+1e-300))
        err32=float(np.linalg.norm(direct32-ref)/(np.linalg.norm(ref)+1e-300))
        require(np.isfinite(H64).all() and np.isfinite(tau).all(),"ERR_RT_NONFINITE")
        np.savez_compressed(out/"ONEBIN_RAW.npz",
                           H_direct_F64=H64,H_direct_approx32=H32,
                           original_archive_LoS=archived,
                           path_coefficients=a,path_delays_s=tau,
                           freq_hz=np.array(freqs[FI]),pose=np.asarray([pose["x"],pose["y"],pose["yaw_body_deg"]]))
        receipt.update(status="ONEBIN_RT_EXECUTED_NO_SCIENCE_RELEASE",
                       n_solver_calls=calls,frequency_hz=float(freqs[FI]),
                       solver_options=cfg,bank_sha256=banks_expected,
                       source_sha256={x:expected[x] for x in SOURCE_FILES},
                       pose=dict(x_m=float(pose["x"]),y_m=float(pose["y"]),
                                 yaw_body_deg=float(pose["yaw_body_deg"])),
                       material_mesh_sha256=actual_mesh,anchor_xyz_m=tx.tolist(),
                       rx_xyz_m=rx.tolist(),source_runtime_versions=versions,
                       machine=platform.platform(),python=sys.version,
                       numpy_paths=n,source_critic_LOS_rel_l2_float64=err64,
                       source_critic_LOS_rel_l2_approx32=err32,
                       old_frozen_f64_tolerance=1e-5,
                       single_bin_f64_within_old_tolerance=bool(err64<=1e-5),
                       solver_elapsed_seconds=time.monotonic()-start_solve,
                       total_walltime_seconds=time.monotonic()-started)
        print("MBVAR_ONEBIN_SIONNA_RT_SOLVER_EXECUTED",calls,"paths",n,
              "bin",FI,"f64_rel",err64,"approx32_rel",err32,flush=True)
    except BaseException as exc:
        receipt["status"]="BLOCKED_NO_MORE_CALLS" if calls==0 else "RT_ONEBIN_ERROR"
        receipt["error"]=repr(exc)
        receipt["n_solver_calls"]=calls
        receipt["error_traceback"]=traceback.format_exc()[-6000:]
        raise
    finally:
        receipt["wall_seconds"]=time.monotonic()-started
        write_json(out/"MANIFEST.json",receipt)
        receipt["output_sha256"]={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!="MANIFEST.json"}
        write_json(out/"MANIFEST.json",receipt)
if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--bank",required=True)
    args=ap.parse_args()
    main(args.out,args.bank)
