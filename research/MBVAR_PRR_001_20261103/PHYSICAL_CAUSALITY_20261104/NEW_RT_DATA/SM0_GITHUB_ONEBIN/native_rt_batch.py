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
    demand(manifest["npz_sha256"]==cfg["original_ffd_sha256"],"BANK_MANIFEST_CHANGED")
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
