"""Frozen 14 RF traces and prior/packet/gate identity for R4 P4.

No ground truth is read into estimator; P3 source receipt is reused by hash.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, zipfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from p4_pre_run_audit import require_p4_audit, digest, P3_SHA, P3_ARTIFACT_SHA, RF_ARTIFACT_SHA, P3_SOURCE_SHA
from p3_frozen_inputs import load_frozen_rf_trace, open_verified_archive
from p3_rf_adapter4 import FrozenLut,GATE_JOINT,R0
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
P0=ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
def json_member(z,suffix):
    matches=[x for x in z.namelist() if x.endswith(suffix)]
    if len(matches)!=1:
        raise RuntimeError("ZIP_MEMBER_AMBIGUOUS_OR_MISSING:"+suffix+":"+str(matches[:5]))
    return json.loads(z.read(matches[0]))

def validate_inputs(archive,p3_artifact,audit):
    require_p4_audit(audit)
    if digest(p3_artifact)!=P3_ARTIFACT_SHA:
        raise RuntimeError("P3_ARTIFACT_ZIP_SHA_CHANGED")
    if digest(archive)!=RF_ARTIFACT_SHA:
        raise RuntimeError("FROZEN_RF_ZIP_SHA_CHANGED")
    with zipfile.ZipFile(p3_artifact) as z:
        if z.testzip():raise RuntimeError("P3_ZIP_CRC_FAIL")
        p3=json_member(z,"/p3_final/P3_FINAL.json")
        idx=json_member(z,"/p3_final/P3_ADAPTER_INDEX.json")
        if p3["status"]!="P3_INPUT_ELIGIBLE_AND_ADAPTER_PARITY_PASS" or not p3["P3_technical_PASS"] or p3["source_commit"]!=P3_SHA:
            raise RuntimeError("P3_FINAL_RECEIPT_NOT_VERIFIED")
        if idx["source_commit"]!=P3_SHA or idx["sample_count"]!=14502:
            raise RuntimeError("P3_ADAPTER_RECEIPT_NOT_VERIFIED")
        for rel,sha in P3_SOURCE_SHA.items():
            if rel in p3["source_sha256"] and p3["source_sha256"][rel]!=sha:
                raise RuntimeError("P3_PREVIOUS_AND_CURRENT_SOURCE_DIFFER:"+rel)
        if p3["parity_receipt_sha256"]!=hashlib.sha256(
            z.read(next(k for k in z.namelist() if k.endswith("/p3_parity/P3_PARITY_FINAL.json")))).hexdigest():
            raise RuntimeError("P3_PARITY_RECEIPT_SHA_NOT_MATCHED")
    with open_verified_archive(archive) as z:
        summary=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
        if summary["R0"]!={"Rs":.0081,"Rr_m2":.0068578637,"Rsr":0.,"range_offset_m":-.5315983906250129}:
            raise RuntimeError("FROZEN_R0_CHANGED")
        if len(summary["per_case"])!=14:
            raise RuntimeError("FROZEN_RF_TRACE_COUNT_DIFFER")
        manifest=json.loads(P0.read_text())
        meta={c["id"]:c for c in manifest["cases"]}
        if {(d["case"],d["channel"]) for d in summary["per_case"]}!={(c,ch) for c in meta for ch in ("los","full")}:
            raise RuntimeError("FROZEN_RF_CASE_SET_MISMATCH")
        cases=[];count=0;gates=0;detected=0
        for d in summary["per_case"]:
            trace=load_frozen_rf_trace(z,d)
            n=len(trace.t_s);count+=n
            detected+=int(np.count_nonzero(trace.detected))
            gates+=int(np.count_nonzero(trace.status=="rejected_NIS"))
            cases.append({"case":trace.case_id,"channel":trace.channel,
                          "trace_file":d["trace_file"],"trace_sha256":d["trace_sha256"],
                          "n":n,"detected":int(np.count_nonzero(trace.detected)),
                          "rejected":int(np.count_nonzero(trace.status=="rejected_NIS")),
                          "eligible":int(np.count_nonzero(trace.status=="applied")),
                          "t_min_s":float(trace.t_s[0]),
                          "t_max_s":float(trace.t_s[-1]),
                          "anchor":meta[trace.case_id]["anchor"],
                          "mount_deg":meta[trace.case_id]["mount_deg"],
                          "route":meta[trace.case_id]["route"]})
        if not(count==14502 and detected==14502 and gates==316):
            raise RuntimeError(f"FROZEN_RF_TIME_GATE_COUNTS_INVALID n={count},detected={detected},rejected={gates}")
    return {"cases":cases,"sample_count":count,"detected":detected,"rejected":gates,
            "eligible":detected-gates,
            "P3_sha":P3_SHA,"P3_archive_sha256":P3_ARTIFACT_SHA,
            "RF_archive_sha256":RF_ARTIFACT_SHA}

def load_cases(archive):
    manifest=json.loads(P0.read_text())
    by_id={c["id"]:c for c in manifest["cases"]}
    with open_verified_archive(archive) as z:
        summary=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
        for desc in summary["per_case"]:
            yield by_id[desc["case"]],load_frozen_rf_trace(z,desc)

def original_joint_posterior(archive, case_id, channel):
    """Frozen C arm posterior only; never reads truth/scoring arrays."""
    name=f"P2_OUT/{case_id}_{channel}_seed0_ONE_STEP.npz"
    with open_verified_archive(archive) as z:
        with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as d:
            return d["xplus"][:,2].copy(),d["Pplus"][:,2].copy()

def main():
    p=argparse.ArgumentParser()
    for name in ("archive","p3-artifact","audit","out"):p.add_argument("--"+name,required=True)
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    try:
        result=validate_inputs(a.archive,a.p3_artifact,a.audit)
        result.update({"schema":"P4_FROZEN_SAME_PRIOR_INPUT_INDEX_V1",
                       "git_sha":os.environ.get("GITHUB_SHA"),
                       "p4_pre_audit_sha256":digest(a.audit),
                       "status":"PASS","scientific_PASS":False,
                       "time_utc":datetime.now(timezone.utc).isoformat()})
        rc=0
    except Exception as exc:
        result={"status":"HARD_BLOCK","error":repr(exc),
                "git_sha":os.getenv("GITHUB_SHA"),"scientific_PASS":False};rc=2
    (out/"P4_INPUT_INDEX.json").write_text(json.dumps(result,indent=2)+"\n")
    print("P4_FROZEN_INPUTS "+json.dumps({k:result.get(k) for k in ("status","sample_count","rejected","eligible","error")}),flush=True)
    return rc
if __name__=="__main__":raise SystemExit(main())
