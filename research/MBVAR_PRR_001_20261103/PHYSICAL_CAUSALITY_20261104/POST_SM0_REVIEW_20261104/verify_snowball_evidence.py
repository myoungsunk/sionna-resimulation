#!/usr/bin/env python3
"""Standalone evidence read: archived Snowball P3 native RT, no Sionna calls.

Validates original archive vs GitHub repository bytes, all SHA-listed payloads,
32 actual raw RF H/tau/path files, repeats, parity and paired contrasts.
Does not reuse the production code's validator/FFT/extractor.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tarfile
import numpy as np

REPO=Path(__file__).resolve()
while REPO.parent!=REPO and not (REPO/"scripts/corridor_sionna_run.py").is_file():
    REPO=REPO.parent
if not (REPO/"scripts/corridor_sionna_run.py").is_file():
    raise RuntimeError("ERR_REPO_ROOT")
ROOT=REPO/"research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0_GITHUB_ONEBIN"
EV=ROOT/"snowball_20261104"
OUT=Path(os.environ.get("MBVAR_RT_AUDIT_OUT","/tmp/mbvar_rt_evidence_audit"))
POSES=(194,234,500,525)
SCENES=("C00_DIRECT","C01_FLOOR","C10_PARALLEL_PLATE","C11_OBLIQUE_PLATE")
REF=REPO/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/H_LoS_R4_aB_m0.npy"
CODE_EXPECTED="79226718784565a5b7d414350ed2eeb884363ad547654d555065275df5ff9de4"

def require(x,why):
    if not x:raise RuntimeError(why)
def sha(data):return hashlib.sha256(data).hexdigest()
def sha_file(path):
    with Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def read_tar(path):
    result={}
    with tarfile.open(path,"r:gz") as tar:
        for item in tar:
            if item.isdir():continue
            require(item.isfile(),"ERR_UNSAFE_TAR_MEMBER "+item.name)
            require(not item.name.startswith("/") and ".." not in Path(item.name).parts,"ERR_TAR_PATH")
            require(item.name not in result,"ERR_TAR_DUPLICATE "+item.name)
            f=tar.extractfile(item)
            require(f is not None,"ERR_TAR_UNREADABLE "+item.name)
            result[item.name]=f.read()
    return result
def sha_list(payload):
    out={}
    for line in payload.decode("utf-8").splitlines():
        m=re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)",line.strip())
        require(m is not None,"ERR_SHA_RECEIPT_FORMAT "+line)
        _,path=m.groups()
        require(path not in out,"ERR_SHA_LIST_DUPLICATE "+path)
        out[path]=m.group(1)
    return out
def numeric_close(a,b,atol=1e-11,rtol=1e-8):
    return np.isfinite(a) and np.isfinite(b) and abs(a-b)<=atol+rtol*max(abs(a),abs(b))
def fp_extract(h):
    """Independent extraction for the fixed TX first column only."""
    w=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
    cir=np.fft.ifft(h[:,:,0]*w[:,None],n=1028,axis=0)*257
    env=np.abs(cir)
    rx=int(np.argmax(env.max(axis=0)))
    hit=np.flatnonzero(env[:,rx]>=.3*env[:,rx].max())
    require(len(hit)>0,"ERR_FP_MISSING")
    tap=int(hit[0])
    powers=np.abs(cir[tap])**2
    return tap,float((powers[0]-powers[1])/powers.sum()),float(tap*299792458/(1028*1950000))
def cplx_h_from_paths(raw):
    H=raw["H_complex_rx_rx_tx"]
    f=raw["frequencies_hz"]
    tau=raw["path_delay_s"]
    a=raw["path_coefficient"]
    counts=raw["path_counts"]
    offsets=raw["offsets"]
    require(H.shape==(257,2,2) and f.shape==(257,) and counts.shape==(257,) and offsets.shape==(258,),"ERR_RF_SCHEMA")
    require(int(offsets[-1])==len(tau)==a.shape[0] and a.shape[1:]==(2,2),"ERR_RAGGED_PATH_SCHEMA")
    require(np.array_equal(np.diff(offsets),counts),"ERR_RAGGED_OFFSETS")
    require(np.isfinite(H).all() and np.isfinite(a).all() and np.isfinite(tau).all(),"ERR_NONFINITE_H_TAU")
    max_relative=0
    for k in range(257):
        beg,end=map(int,offsets[k:k+2])
        ph=np.complex64(-2j*np.pi*float(f[k]))*tau[beg:end]
        reconstructed=(a[beg:end].transpose(1,2,0)*np.exp(ph)[None,None,:]).sum(-1)
        error=float(np.linalg.norm(reconstructed-H[k])/(np.linalg.norm(H[k])+1e-300))
        max_relative=max(max_relative,error)
    return max_relative
def run():
    OUT.mkdir(parents=True,exist_ok=True)
    bundle=sha_list((EV/"BUNDLE_SHA256.txt").read_bytes())
    # Snowball listed 9 companion files, all names must exist and match bytes.
    require(len(bundle)==9,"ERR_BUNDLE_RECEIPT_COUNT")
    for name,dig in bundle.items():
        p=EV/name
        require(p.is_file() and sha_file(p)==dig,"ERR_GITHUB_BUNDLE_SHA "+name)
    require(sha_file(ROOT/"native_rt_batch.py")==CODE_EXPECTED,"ERR_EXECUTED_PRODUCTION_SOURCE_SHA")
    prior=read_tar(EV/"previous_failure.tar.gz")
    current=read_tar(EV/"rerun.tar.gz")
    hashes=sha_list((EV/"OUTPUT_SHA256.txt").read_bytes())
    oldhashes=sha_list((EV/"previous_OUTPUT_SHA256.txt").read_bytes())
    # Require all 151 listed payloads. The original tar may also contain the
    # external hash-list itself: require every other file to be listed.
    require(len(hashes)==151 and len(oldhashes)==19,"ERR_RECORDED_FILE_COUNTS")
    for payload,ledger,prefix in ((current,hashes,"NEW"),(prior,oldhashes,"OLD")):
        for name,dig in ledger.items():
            require(name in payload,"ERR_"+prefix+"_FILE_MISSING "+name)
            require(sha(payload[name])==dig,"ERR_"+prefix+"_FILE_SHA "+name)
        extra=set(payload)-set(ledger)
        require(extra<=set(("OUTPUT_SHA256.txt","previous_OUTPUT_SHA256.txt")),"ERR_"+prefix+"_UNACCOUNTED_FILES "+str(sorted(extra)))
    c00=json.loads((EV/"C00_QA.json").read_text())
    qa=json.loads((EV/"PAIRED_QA.json").read_text())
    require(c00["status"]=="C00_257BIN_STRICT_PARITY_PASS" and c00["n_expected"]==c00["n_pass"]==8,"ERR_C00_COUNT")
    require(qa["status"]=="PAIRED_257BIN_TECHNICAL_PASS_NOT_SCIENCE" and qa["n_expected"]==qa["n_pass"]==24,"ERR_PAIRED_COUNT")
    require(c00["lock_sha256"]==qa["lock_sha256"],"ERR_MIXED_SCENE_LOCK")
    pairs=list(csv.DictReader((EV/"paired_contrasts.csv").open(newline="")))
    require(len(pairs)==16,"ERR_PAIRED_CSV_ROWS")
    index={(r["arm"],int(r["pose"])):r for r in pairs}
    require(set(index)=={(a,p) for a in SCENES for p in POSES},"ERR_PAIRED_KEYSET")
    qacatalog={tuple(d["key"]):d for d in c00["details"]+qa["details"]}
    require(len(qacatalog)==32,"ERR_QA_KEY_DUPLICATE")
    all_H={}
    stats=[]
    reference=np.load(REF,mmap_mode="r",allow_pickle=False)
    for arm in SCENES:
      for pose in POSES:
       for rep in (0,1):
        key=f"out/{arm}-{pose}-r{rep}"
        name=key+"/RAW_COMPLEX_H_AND_PATHS.npz"
        mf=json.loads(current[key+"/MANIFEST.json"])
        require(mf["file_sha256"]["RAW_COMPLEX_H_AND_PATHS.npz"]==sha(current[name]),"ERR_MANIFEST_RAW_SHA")
        require(mf["solver_calls_made"]==257 and mf["status"]=="COMPLETED","ERR_SOLVER_CALL_STATUS")
        require(mf["lock_sha256"]==c00["lock_sha256"],"ERR_SOURCE_LOCK_VARIANT")
        q=qacatalog[(arm,pose,rep)]
        require(q["status"]=="PASS" and q["sha_raw_zip"]==sha(current[name]),"ERR_QA_RAW_BINDING")
        with np.load(io.BytesIO(current[name]),allow_pickle=False) as raw:
            maxrel=cplx_h_from_paths(raw)
            H=raw["H_complex_rx_rx_tx"].copy()
        require(maxrel<=1e-7,"ERR_PATH_SUM_FIELD "+key)
        assert H.shape==(257,2,2)
        require(sha(np.ascontiguousarray(H).tobytes())==q["hash_complex_H"],"ERR_QA_H_SHA "+key)
        tap,signed,rm=fp_extract(H)
        require(tap==q["source_firstpath_tap"],"ERR_FP_TAP "+key)
        require(numeric_close(signed,float(q["signed_s"])) and numeric_close(rm,float(q["range_unoffset_m"])),"ERR_FP_OBSERVATION "+key)
        if arm=="C00_DIRECT":
            r=float(np.linalg.norm(H[:,:,0]-reference[pose,:,:,0])/(np.linalg.norm(reference[pose,:,:,0])+1e-300))
            require(r<=1e-5 and numeric_close(r,float(q["source_los_relative_l2"])),"ERR_C00_DIRECT_PARITY "+key)
        all_H[(arm,pose,rep)]=H
        stats.append(dict(scene=arm,pose=pose,repeat=rep,
                          reconstructed_complex_H_relative_max=maxrel,
                          path_count=int(mf["solver_calls_made"]),
                          fp_tap=tap,signed_s=signed))
    repeat_n=0
    for arm in SCENES:
      for pose in POSES:
        require(np.array_equal(all_H[(arm,pose,0)],all_H[(arm,pose,1)]),"ERR_REPEAT_H_NOT_IDENTICAL")
        repeat_n+=1
        H=all_H[(arm,pose,0)]
        H0=all_H[("C00_DIRECT",pose,0)]
        contrast=float(np.linalg.norm(H-H0)/(np.linalg.norm(H0)+1e-300))
        require(numeric_close(contrast,float(index[(arm,pose)]["H_rel_l2"])),"ERR_PAIRED_REL_L2")
        tap,signed,rm=fp_extract(H);t0,s0,r0=fp_extract(H0)
        require(tap-t0==int(index[(arm,pose)]["tap_change"]),"ERR_PAIRED_TAP")
        require(numeric_close(signed-s0,float(index[(arm,pose)]["delta_signed_s"])),"ERR_PAIRED_SIGNED")
        require(numeric_close(rm-r0,float(index[(arm,pose)]["delta_raw_r_m"])),"ERR_PAIRED_RANGE")
    # Previous failure: 4 originally failed C00 first repeats, never erased.
    old_bad=0
    for pose in POSES:
        key=f"out/C00_DIRECT-{pose}-r0"
        require(key+"/MANIFEST.json" in prior,"ERR_HISTORICAL_FAIL_MISSING")
        mf=json.loads(prior[key+"/MANIFEST.json"])
        require(mf["solver_calls_made"]==257,"ERR_OLD_SOLVER_COUNT")
        require(mf["direct_reference_relative_L2"]>1e-5,"ERR_OLD_FAILURE_RELABELED")
        old_bad+=1
    receipt=dict(schema="MBVAR_PRR_POST_SM0_INDEPENDENT_BYTES_ARITHMETIC_QA_V1",
                 audit_role="SAME_CONVERSATION_DIFFERENT_IMPLEMENTATION_NOT_EXTERNAL_REVIEW",
                 commit="e69fcdd6123d3d056cd95ea210ac8eb732f17628",
                 production_sha256=CODE_EXPECTED,
                 source_lock_sha256=c00["lock_sha256"],
                 bundle_sha_receipts=9,
                 rerun_files_hash_verified=len(hashes),
                 previous_files_hash_verified=len(oldhashes),
                 current_native_H_raw_key_count=len(stats),
                 archived_solver_calls=32*257,
                 repeated_complex_H_identical_configs=repeat_n,
                 previous_failed_c00_keys=old_bad,
                 c00_qa_status=c00["status"],paired_qa_status=qa["status"],
                 max_raw_path_H_reconstruction_relative_error=max(x["reconstructed_complex_H_relative_max"] for x in stats),
                 science_claim="PHYSICAL_NUMERIC_TECHNICAL_PILOT_ONLY",
                 EKF_performance_evaluated=False,time_correlation_identified=False,
                 no_Sionna_invocation=True,independent_auditor_signed=False)
    (OUT/"POST_SM0_EVIDENCE_BYTE_ARITHMETIC_QA.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print("POST_SM0_ARCHIVED_EVIDENCE_ARITHMETIC_PASS",json.dumps(receipt,sort_keys=True))
if __name__=="__main__":run()
