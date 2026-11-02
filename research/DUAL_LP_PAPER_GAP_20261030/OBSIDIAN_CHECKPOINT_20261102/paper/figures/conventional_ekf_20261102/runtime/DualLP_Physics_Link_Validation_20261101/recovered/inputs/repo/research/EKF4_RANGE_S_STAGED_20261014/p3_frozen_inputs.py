"""Immutable archived RF one-step trace loader and input eligibility contract.

IMPORTANT: truth_for_offline_scoring_only is not exposed by FrozenRFTrace.
No RF estimation, optimizer, calibration or score uses ground truth here.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXPECTED_ARCHIVE_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
P0_PATH=REPO/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"

@dataclass(frozen=True)
class FrozenRFTrace:
    case_id: str
    channel: str
    t_s: np.ndarray
    pose_id: np.ndarray
    prior_x: np.ndarray
    prior_P: np.ndarray
    z_s: np.ndarray
    z_range: np.ndarray
    detected: np.ndarray
    predicted_sr: np.ndarray
    H_sr: np.ndarray
    R_sr: np.ndarray
    S_sr: np.ndarray
    K_sr: np.ndarray
    nu_sr: np.ndarray
    nis: np.ndarray
    status: np.ndarray
    pole_rho: np.ndarray

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def assert_audit(path):
    a=json.loads(Path(path).read_text(encoding="utf-8"))
    if not (os.getenv("GITHUB_ACTIONS")=="true" and a["git_sha"]==os.environ["GITHUB_SHA"]
            and a["decision"]=="GO"):
        raise RuntimeError("P3_PRE_AUDIT_MISSING_OR_WRONG_SOURCE")
    for name, expected in a["source_sha256"].items():
        f=(REPO/".github/workflows/ekf4-r4-p3-frozen-rf.yml") if name=="workflow" else (
            (HERE/name) if "/" not in name else (REPO/name))
        if not f.is_file() or sha_file(f)!=expected:
            raise RuntimeError("SOURCE_CHANGED_AFTER_P3_AUDIT:"+name)
    return a

def load_frozen_rf_trace(zf, desc):
    name="P2_OUT/"+desc["trace_file"]
    raw=zf.read(name)
    if sha_bytes(raw)!=desc["trace_sha256"]:
        raise RuntimeError("FROZEN_TRACE_SHA256_MISMATCH:"+name)
    with np.load(io.BytesIO(raw),allow_pickle=False) as d:
        keys=("t_s","pose_id","xminus","Pminus","z_s","z_r_m","detected",
              "predicted_z","H","R","S","K","innovation","NIS",
              "status","estimated_pole_rho_m")
        if any(k not in d.files for k in keys):
            raise RuntimeError("FROZEN_TRACE_SCHEMA_MISSING:"+name)
        # Intentionally never read d['truth_for_offline_scoring_only'].
        v={k:d[k].copy() for k in keys}
    n=len(v["t_s"])
    shapes={
        "pose_id":(n,), "xminus":(n,3),"Pminus":(n,3,3),
        "z_s":(n,), "z_r_m":(n,), "detected":(n,),
        "predicted_z":(n,3,2),"H":(n,3,2,3),
        "R":(n,3,2,2),"S":(n,3,2,2),"K":(n,3,3,2),
        "innovation":(n,3,2),"NIS":(n,3),
        "status":(n,3),"estimated_pole_rho_m":(n,)
    }
    if any(v[k].shape != shape for k,shape in shapes.items()):
        raise RuntimeError("FROZEN_TRACE_SHAPE_MISMATCH:"+name)
    if n<=0 or not np.all(np.isfinite(v["t_s"])) or not np.all(np.diff(v["t_s"])>0):
        raise RuntimeError("FROZEN_TRACE_NONMONOTONIC_TIME:"+name)
    if len(np.unique(v["pose_id"]))!=n or not np.all(np.diff(v["pose_id"])>0):
        raise RuntimeError("FROZEN_TRACE_DUPLICATE_OR_UNSORTED_POSE_ID:"+name)
    for k in ("xminus","Pminus","z_s","z_r_m","estimated_pole_rho_m"):
        if not np.isfinite(v[k]).all():
            raise RuntimeError("FROZEN_TRACE_NONFINITE_INPUT:"+name+":"+k)
    if not np.allclose(v["Pminus"],np.swapaxes(v["Pminus"],-1,-2),rtol=1e-12,atol=1e-12):
        raise RuntimeError("FROZEN_TRACE_NONSYMMETRIC_PRIOR:"+name)
    if float(np.min(np.linalg.eigvalsh(v["Pminus"])))<=0.:
        raise RuntimeError("FROZEN_TRACE_NOT_PD_PRIOR:"+name)
    active=np.asarray(v["detected"],bool)
    if not np.any(active):
        raise RuntimeError("FROZEN_TRACE_NO_DETECTION:"+name)
    for k in ("predicted_z","H","R","S","innovation"):
        data=v[k][active,2,:2] if k in ("predicted_z","innovation") else (
            v[k][active,2,:2,:3] if k=="H" else v[k][active,2,:2,:2])
        if not np.isfinite(data).all():
            raise RuntimeError("ACTIVE_JOINT_RF_NONFINITE:"+name+":"+k)
    if not np.isfinite(v["NIS"][active,2]).all():
        raise RuntimeError("ACTIVE_JOINT_NIS_NONFINITE:"+name)
    if np.min(np.linalg.eigvalsh(v["R"][active,2,:2,:2])) <= 0:
        raise RuntimeError("ACTIVE_JOINT_R_NOT_POSITIVE:"+name)
    if not set(v["status"][:,2]).issubset({"applied","rejected_NIS","missing"}):
        raise RuntimeError("INVALID_ORIGINAL_GATE_LABEL:"+name)
    for k in ("t_s","pose_id","xminus","Pminus","z_s","z_r_m","detected"):
        v[k].setflags(write=False)
    return FrozenRFTrace(
        desc["case"],desc["channel"],
        v["t_s"],v["pose_id"],v["xminus"],v["Pminus"],
        v["z_s"],v["z_r_m"],v["detected"],
        v["predicted_z"][:,2,:2],
        v["H"][:,2,:2,:3],v["R"][:,2,:2,:2],
        v["S"][:,2,:2,:2],v["K"][:,2,:,:2],
        v["innovation"][:,2,:2],v["NIS"][:,2],
        v["status"][:,2],v["estimated_pole_rho_m"])

def open_verified_archive(archive):
    if sha_file(archive)!=EXPECTED_ARCHIVE_SHA:
        raise RuntimeError("FROZEN_RF_ARCHIVE_SHA256_MISMATCH")
    zf=zipfile.ZipFile(archive)
    if zf.testzip() is not None:
        zf.close()
        raise RuntimeError("FROZEN_RF_ZIP_CRC_MISMATCH")
    return zf

def verify(archive,audit,out):
    receipt=assert_audit(audit)
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    final={"schema":"P3_FROZEN_SOURCE_RECEIPT_V1",
           "git_sha":os.environ["GITHUB_SHA"],
           "run_id":os.environ.get("GITHUB_RUN_ID"),
           "audit_sha256":sha_file(audit),
           "source_run_id":38331588521,
           "artifact_id":11782748118,
           "archive_sha256":EXPECTED_ARCHIVE_SHA,
           "scientific_PASS":False,
           "status":"STARTED","cases":[]}
    (out/"P3_SOURCE_STARTED.json").write_text(json.dumps(final,indent=2)+"\n")
    try:
        manifest=json.loads(P0_PATH.read_text())
        indexed={c["id"]:c for c in manifest["cases"]}
        with open_verified_archive(archive) as z:
            summ=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
            p0=json.loads(z.read("P2_VERIFY_P0_RUNTIME.json"))
            if not (summ["status"]=="ONE_STEP_FROZEN_RF_EXECUTED_MATHEMATICAL_CHECKS_PASS"
                    and len(summ["per_case"])==14 and summ["R0"]=={
                        "Rs":.0081,"Rr_m2":.0068578637,
                        "Rsr":0.,"range_offset_m":-.5315983906250129}
                    and p0["status"]=="PASS_LOCAL_SHA256_SHAPE_POSE_PREFLIGHT"
                    and p0["assets"]==39):
                raise RuntimeError("ORIGINAL_ONE_STEP_OR_P0_SUMMARY_MISMATCH")
            expected={(c,"los") for c in indexed}|{(c,"full") for c in indexed}
            actual={(d["case"],d["channel"]) for d in summ["per_case"]}
            if actual!=expected or len(set(actual))!=14:
                raise RuntimeError("MISSING_OR_DUPLICATE_RF_CASE_CHANNEL")
            allowed={"P2_OUT/"+d["trace_file"] for d in summ["per_case"]}
            found={n for n in z.namelist() if n.endswith("_ONE_STEP.npz")}
            if found!=allowed:
                raise RuntimeError("UNEXPECTED_OR_MISSING_RAW_TRACE")
            pair={}
            total=0
            for d in summ["per_case"]:
                trace=load_frozen_rf_trace(z,d)
                key=trace.case_id
                c=indexed[key]
                if d["n_steps"]!=len(trace.t_s):
                    raise RuntimeError("ORIGINAL_TRACE_LENGTH_MISMATCH")
                total+=len(trace.t_s)
                pair.setdefault(key,{})[trace.channel]=trace
                row={"case":key,"channel":trace.channel,"samples":len(trace.t_s),
                     "detected":int(np.count_nonzero(trace.detected)),
                     "applied":int(np.count_nonzero(trace.status=="applied")),
                     "rejected":int(np.count_nonzero(trace.status=="rejected_NIS")),
                     "estimated_pole_le_0p1":int(np.count_nonzero(trace.pole_rho<=0.1)),
                     "trace_sha256":d["trace_sha256"],
                     "route":c["route"],"anchor":c["anchor"],"mount_deg":c["mount_deg"],
                     "t_first":float(trace.t_s[0]),"t_last":float(trace.t_s[-1])}
                final["cases"].append(row)
            for key,channels in pair.items():
                if set(channels)!={"los","full"}:
                    raise RuntimeError("SINGLE_CHANNEL_CASE:"+key)
                a,b=channels["los"],channels["full"]
                for attr in ("t_s","pose_id","prior_x","prior_P"):
                    if not np.array_equal(getattr(a,attr),getattr(b,attr)):
                        raise RuntimeError("LOS_FULL_COMMON_PRIOR_VIOLATION:"+key+":"+attr)
            if total!=14502:
                raise RuntimeError("ORIGINAL_RF_TIMESTAMP_TOTAL_MISMATCH")
        final.update(status="PASS",case_channel_count=14,
                     expected_steps=14502,verified_steps=total,
                     independent_rf_scene_count=1,
                     original_p0_39_assets_reused=True,
                     verified_utc=datetime.now(timezone.utc).isoformat())
        (out/"P3_SOURCE_RECEIPT.json").write_text(json.dumps(final,indent=2,ensure_ascii=False)+"\n")
        print("P3_SOURCE_FINAL "+json.dumps({"status":"PASS","traces":14,
              "steps":total,"archive_sha256":EXPECTED_ARCHIVE_SHA}),flush=True)
        return 0
    except Exception as e:
        final.update(status="FAIL",error=type(e).__name__+":"+str(e))
        (out/"P3_SOURCE_RECEIPT.json").write_text(json.dumps(final,indent=2,ensure_ascii=False)+"\n")
        raise

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--audit",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    raise SystemExit(verify(args.archive,args.audit,args.out))
