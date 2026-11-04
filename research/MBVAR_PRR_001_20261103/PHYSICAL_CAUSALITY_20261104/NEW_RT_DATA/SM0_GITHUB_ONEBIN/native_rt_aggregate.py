#!/usr/bin/env python3
"""Standalone stored H/CIR/receipt QA. Does NOT invoke Sionna or optimizer.

C00 stage: exactly four poses x two repeat reports, requires all eight full
257-bin direct path parity checks PASS before any reflector stage.
Paired stage: compare C01,C10,C11 to validated C00, preserving failed keys.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
LOCK=HERE/"P3_NATIVE_CONTROLLED_SCENE_PREEXECUTION_LOCK_DRAFT.json"
ARMS=("C00_DIRECT","C01_FLOOR","C10_PARALLEL_PLATE","C11_OBLIQUE_PLATE")
POSES=(194,234,500,525)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def doc(p):return json.loads(Path(p).read_text())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+"\n")
def audit_key(folder,arm,pose,rep):
    p=Path(folder)/f"{arm}-{pose}-r{rep}"
    mf=p/"MANIFEST.json";npz=p/"RAW_COMPLEX_H_AND_PATHS.npz"
    status=dict(key=[arm,pose,rep],source_dir=str(p),status="MISSING",why=None)
    if not mf.is_file():
        status["why"]="MISSING_MANIFEST";return status
    m=doc(mf)
    status["manifest_status"]=m.get("status")
    status["source_git_sha"]=m.get("source_sha")
    status["source_lock_sha256"]=m.get("lock_sha256")
    if m.get("arm")!=arm or m.get("pose_id")!=pose or m.get("repeat_index")!=rep:
        status["why"]="KEY_MANIFEST_MISMATCH";return status
    if m.get("lock_sha256")!=sha(LOCK):
        status["why"]="LOCK_SHA_MISMATCH";return status
    if m.get("solver_calls_made")!=257:
        status["why"]="NOT_257_SOLVER_CALLS";return status
    if m.get("status") not in ("COMPLETED","DIRECT_PARITY_FAIL","STOP_WITH_RAW_EVIDENCE"):
        status["why"]="SOURCE_STATUS_INVALID";return status
    if not npz.is_file() or sha(npz)!=m.get("file_sha256",{}).get(npz.name):
        status["why"]="RAW_FILE_MISSING_OR_SHA_MISMATCH";return status
    with np.load(npz,allow_pickle=False) as a:
        H=a["H_complex_rx_rx_tx"]
        freq=a["frequencies_hz"]
        offsets=a["offsets"]
        counts=a["path_counts"]
        taus=a["path_delay_s"]
        coef=a["path_coefficient"]
        if (H.shape!=(257,2,2) or freq.shape!=(257,) or
            offsets.shape!=(258,) or counts.shape!=(257,) or
            int(offsets[-1])!=len(taus) or coef.shape!=(len(taus),2,2) or
            not np.array_equal(np.diff(offsets),counts) or
            not np.isfinite(H).all() or not np.isfinite(taus).all()):
            status["why"]="RAW_ARRAY_SCHEMA";return status
        status["hash_complex_H"]=hashlib.sha256(np.ascontiguousarray(H).tobytes()).hexdigest()
        status["sum_path_count"]=int(counts.sum())
        status["sha_raw_zip"]=sha(npz)
        status["source_firstpath_tap"]=m.get("observation",{}).get("fp_tap")
        status["range_unoffset_m"]=m.get("observation",{}).get("raw_r_m")
        status["signed_s"]=m.get("observation",{}).get("s")
        status["source_los_relative_l2"]=m.get("direct_reference_relative_L2")
        if arm=="C00_DIRECT":
            if m.get("direct_parity")!="PASS" or m.get("status")!="COMPLETED":
                status["why"]="C00_257BIN_DIRECT_PARITY_FAIL";return status
        else:
            if m.get("status")!="COMPLETED":
                status["why"]="REFLECTION_SCENE_COMPUTATION_FAILED";return status
        status["status"]="PASS"
    return status
def compare_pair(folder,c00folder,arm,pose,rep):
    import numpy as np
    test=Path(folder)/f"{arm}-{pose}-r{rep}"/"RAW_COMPLEX_H_AND_PATHS.npz"
    ctrl=Path(c00folder)/f"C00_DIRECT-{pose}-r{rep}"/"RAW_COMPLEX_H_AND_PATHS.npz"
    if not test.is_file() or not ctrl.is_file():return dict(status="MISSING_PAIRED_H")
    with np.load(test,allow_pickle=False) as x,np.load(ctrl,allow_pickle=False) as c:
        H=x["H_complex_rx_rx_tx"];H0=c["H_complex_rx_rx_tx"]
        same=np.array_equal(x["frequencies_hz"],c["frequencies_hz"])
        if H.shape!=(257,2,2) or H0.shape!=H.shape or not same:
            return dict(status="NOT_MATCHED_OR_INVALID_FREQUENCY")
        e=H-H0
        return dict(status="PAIR_PILOT_OBSERVATION_NOT_SCIENCE",
            rel_l2=float(np.linalg.norm(e)/(np.linalg.norm(H0)+1e-300)),
            max_abs_complex_H=float(np.max(np.abs(e))),
            max_port_power_shift=float(np.max(np.abs(np.abs(H)**2-np.abs(H0)**2))),
            H0_sha256=hashlib.sha256(np.ascontiguousarray(H0).tobytes()).hexdigest())
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage",choices=("c00","paired"),required=True)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--c00-root",type=Path)
    a=p.parse_args()
    if a.stage=="paired" and a.c00_root is None:p.error("--c00-root is required")
    lock=doc(LOCK)
    arms=ARMS[:1] if a.stage=="c00" else ARMS[1:]
    keys=[(arm,pose,rep) for arm in arms for pose in POSES for rep in range(2)]
    details=[audit_key(a.root,*k) for k in keys]
    passing=sum(x["status"]=="PASS" for x in details)
    status="C00_257BIN_STRICT_PARITY_PASS" if a.stage=="c00" and passing==8 else (
        "PAIRED_257BIN_TECHNICAL_PASS_NOT_SCIENCE" if a.stage=="paired" and passing==24 else "STOP_GATE_FAILED")
    if a.stage=="paired":
        c00=doc(a.c00_root/"C00_QA.json")
        if c00.get("status")!="C00_257BIN_STRICT_PARITY_PASS" or c00.get("lock_sha256")!=sha(LOCK):
            status="STOP_C00_GATE_MISSING"
        for x in details:
            arm,pose,rep=x["key"]
            x["paired_contrast"]=compare_pair(a.root,a.c00_root,arm,pose,rep) if x["status"]=="PASS" else dict(status="NOT_EVALUATED")
    result=dict(schema="MBVAR_P3_NATIVE_RT_AGGREGATE_V1",
        status=status,stage=a.stage,lock_sha256=sha(LOCK),
        n_expected=len(keys),n_pass=passing,n_failed_or_missing=len(keys)-passing,
        expected_solver_calls=len(keys)*257,
        complete_full_257_bins_per_key=True,
        original_SM0_257bin_STOP_preserved=True,
        science_status="NONINDEPENDENT_EXPLORATORY_NUMERIC_PILOT_ONLY",
        independent_auditor_signed=False,
        dev3_science_untouched=True,details=details)
    a.out.mkdir(parents=True,exist_ok=True)
    write(a.out/("C00_QA.json" if a.stage=="c00" else "PAIRED_QA.json"),result)
    with (a.out/"QA_KEY_LIST.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["arm","pose","repeat","status","reason","raw_sha256"])
        writer.writeheader()
        for x in details:
            arm,pose,rep=x["key"]
            writer.writerow(dict(arm=arm,pose=pose,repeat=rep,status=x["status"],
                                 reason=x.get("why") or "",raw_sha256=x.get("sha_raw_zip") or ""))
    print("MBVAR_RT_AGGREGATE",a.stage,status,"pass",passing,"of",len(keys),flush=True)
    if status in ("STOP_GATE_FAILED","STOP_C00_GATE_MISSING"):raise SystemExit(1)
if __name__=="__main__":main()
