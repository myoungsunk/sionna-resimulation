"""P3 full 14-trace, all-time-point EKF4 observation/H/R parity.

Audit+input receipt must pass first. No MAP, no filter posterior updates.
Original trace reference order is [s,range]; output order [range,s].
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import traceback
import numpy as np

from p3_frozen_inputs import assert_audit, open_verified_archive, load_frozen_rf_trace, sha_file
from p3_rf_adapter4 import (FrozenLut, GATE_JOINT, R0, B_OLD,
                            make_ekf4_observation, reorder_original_joint)

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
P0=REPO/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"

# These are fixed parity requirements, not tolerances tuned against results.
LIMIT_H=1e-8
LIMIT_JACOBIAN=1e-5
LIMIT_INNOVATION=1e-8
LIMIT_R_S_K=1e-7
LIMIT_NIS=1e-7

def write_csv(path,rows):
    if not rows:
        return
    with Path(path).open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def compare(trace,k,case,lut):
    x4=np.r_[trace.prior_x[k],0.]
    frame=make_ekf4_observation(trace,k,x4,case,lut)
    ref=reorder_original_joint(
        np.array([trace.z_s[k],trace.z_range[k]]),
        trace.predicted_sr[k],np.column_stack((trace.H_sr[k],np.zeros(2))),
        trace.R_sr[k],trace.nu_sr[k],trace.S_sr[k],
        np.vstack((trace.K_sr[k],np.zeros((1,2)))))
    if frame.z.shape!=(2,) or frame.h.shape!=(2,) or frame.H.shape!=(2,4):
        raise RuntimeError("P3_INVALID_OUTPUT_SCHEMA")
    d_h=np.abs(frame.h-ref["h"])
    d_H=np.abs(frame.H-ref["H"])
    d_R=np.abs(frame.R-ref["R"])
    d_nu=np.abs((frame.z-frame.h)-ref["innovation"])
    # Reconstruct original innovation covariance and gain for algebraic
    # permutation consistency only; do NOT run an estimator update.
    P4=np.zeros((4,4))
    P4[:3,:3]=trace.prior_P[k]
    P4[3,3]=math.radians(.1)**2
    S=frame.H@P4@frame.H.T+frame.R
    K=np.linalg.solve(S,frame.H@P4).T
    nu=frame.z-frame.h
    nis=float(nu@np.linalg.solve(S,nu))
    dS=np.abs(S-ref["S"])
    dK=np.abs(K-ref["K"])
    dNIS=abs(nis-float(trace.nis[k]))
    original_accepted=trace.status[k]=="applied"
    our_accepted=nis<=GATE_JOINT
    # Preserve old status as reference, never use it to tune P3 gate.
    if original_accepted!=our_accepted:
        raise RuntimeError("P3_GATE_PERMUTATION_MISMATCH")
    if not (np.max(d_h)<=LIMIT_H and np.max(d_H)<=LIMIT_JACOBIAN
            and np.max(d_R)<=1e-12 and np.max(d_nu)<=LIMIT_INNOVATION
            and np.max(dS)<=LIMIT_R_S_K and np.max(dK)<=LIMIT_R_S_K
            and dNIS<=LIMIT_NIS):
        raise RuntimeError("P3_OBSERVATION_OR_JACOBIAN_PARITY_FAIL")
    if not (np.array_equal(frame.R,R0) and
            np.array_equal(frame.H[:,3],np.zeros(2))):
        raise RuntimeError("P3_WRONG_CANONICAL_R_OR_BIAS_COLUMN")
    original_pole=trace.pole_rho[k]<=.1
    if frame.quality["near_anchor_pole"]!=original_pole:
        raise RuntimeError("P3_ESTIMATED_POLE_MASK_MISMATCH")
    return {
        "case":trace.case_id,"channel":trace.channel,"step":k,
        "t_s":float(trace.t_s[k]),"pose_id":int(trace.pose_id[k]),
        "detected":True,"original_status":str(trace.status[k]),
        "h_r_delta":float(d_h[0]),"h_s_delta":float(d_h[1]),
        "H_r_max_delta":float(np.max(d_H[0])),
        "H_s_max_delta":float(np.max(d_H[1])),
        "R_max_delta":float(np.max(d_R)),
        "innovation_max_delta":float(np.max(d_nu)),
        "S_max_delta":float(np.max(dS)),
        "K_max_delta":float(np.max(dK)),
        "NIS_delta":float(dNIS),
        "near_pole":frame.quality["near_anchor_pole"]}

def run(archive,audit,inputs,out):
    a=assert_audit(audit)
    prior=json.loads(Path(inputs).read_text())
    if not(prior["status"]=="PASS" and prior["git_sha"]==os.environ["GITHUB_SHA"]
           and prior["verified_steps"]==14502 and prior["case_channel_count"]==14):
        raise RuntimeError("P3_INPUT_RECEIPT_NOT_PASS")
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    summary={
      "schema":"P3_ALL_14502_FROZEN_RF_MODEL_PARITY_V1",
      "git_sha":os.environ["GITHUB_SHA"],
      "run_id":os.environ.get("GITHUB_RUN_ID"),
      "source_receipt_sha256":sha_file(inputs),
      "audit_receipt_sha256":sha_file(audit),
      "observations_order":["range_raw_m","s"],
      "R0_order":["range_m2","s_dimensionless"],
      "limit_h":LIMIT_H,"limit_jac":LIMIT_JACOBIAN,
      "scientific_PASS":False,"status":"STARTED","cases":[]}
    (out/"P3_STARTED.json").write_text(json.dumps(summary,indent=2)+"\n")
    rows=[]
    try:
        m=json.loads(P0.read_text())
        by_id={c["id"]:c for c in m["cases"]}
        lut=FrozenLut(REPO)
        with open_verified_archive(archive) as z:
            archived=json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
            for desc in archived["per_case"]:
                trace=load_frozen_rf_trace(z,desc)
                case=by_id[trace.case_id]
                n=len(trace.t_s)
                first_after=int(np.flatnonzero(trace.t_s>=30.)[0])
                canary_indices=sorted({0,first_after,n//2,n-1})
                # Every canary is verified independently before full trace.
                for k in canary_indices:
                    if trace.detected[k]:
                        compare(trace,k,case,lut)
                trace_rows=[]
                for k in range(n):
                    if not trace.detected[k]:
                        trace_rows.append({
                          "case":trace.case_id,"channel":trace.channel,
                          "step":k,"detected":False})
                        continue
                    trace_rows.append(compare(trace,k,case,lut))
                rows.extend(trace_rows)
                tested=[r for r in trace_rows if r["detected"]]
                record={
                    "case":trace.case_id,"channel":trace.channel,
                    "samples":n,"canary_checked":len(canary_indices),
                    "full_detected_parity_checks":len(tested),
                    "not_detected":n-len(tested),
                    "gate_rejected":sum(r["original_status"]=="rejected_NIS" for r in tested),
                    "max_h_range_abs":max(r["h_r_delta"] for r in tested),
                    "max_h_s_abs":max(r["h_s_delta"] for r in tested),
                    "max_H_range_abs":max(r["H_r_max_delta"] for r in tested),
                    "max_H_s_abs":max(r["H_s_max_delta"] for r in tested),
                    "max_S_abs":max(r["S_max_delta"] for r in tested),
                    "max_K_abs":max(r["K_max_delta"] for r in tested),
                    "max_NIS_abs":max(r["NIS_delta"] for r in tested),
                    "estimated_pole_count":sum(r["near_pole"] for r in tested)}
                summary["cases"].append(record)
                print("P3_CASE_PARITY "+json.dumps(record,ensure_ascii=False),flush=True)
                (out/"P3_PARITY_PROGRESS.json").write_text(
                    json.dumps({"cases":summary["cases"],"checked":len(rows)},
                               indent=2,ensure_ascii=False)+"\n")
        if len(rows)!=14502 or sum(bool(r["detected"]) for r in rows)!=14502:
            raise RuntimeError("NOT_ALL_FROZEN_TIMESTAMPS_PARITY_CHECKED")
        write_csv(out/"P3_PARITY.csv",rows)
        write_csv(out/"P3_CASE_STATUS.csv",summary["cases"])
        summary.update({
          "status":"PASS",
          "verified_timepoints":len(rows),
          "detected_parity_points":14502,
          "canary_count":sum(c["canary_checked"] for c in summary["cases"]),
          "max_h_abs":max(max(c["max_h_range_abs"],c["max_h_s_abs"]) for c in summary["cases"]),
          "max_H_abs":max(max(c["max_H_range_abs"],c["max_H_s_abs"]) for c in summary["cases"]),
          "max_NIS_abs":max(c["max_NIS_abs"] for c in summary["cases"]),
          "max_K_abs":max(c["max_K_abs"] for c in summary["cases"]),
          "rejected_gate_points":sum(c["gate_rejected"] for c in summary["cases"]),
          "finished_utc":datetime.now(timezone.utc).isoformat()
        })
        (out/"P3_PARITY_FINAL.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
        print("P3_PARITY_FINAL "+json.dumps({
           "status":"PASS","timepoints":14502,
           "max_h":summary["max_h_abs"],"max_H":summary["max_H_abs"],
           "max_NIS":summary["max_NIS_abs"],"max_K":summary["max_K_abs"]},
           ensure_ascii=False),flush=True)
        return 0
    except Exception as exc:
        summary.update(status="FAIL",error=type(exc).__name__+":"+str(exc),
                       traceback=traceback.format_exc(),completed_rows=len(rows))
        write_csv(out/"P3_PARITY_PARTIAL.csv",rows)
        (out/"P3_PARITY_FINAL.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
        raise

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--audit",type=Path,required=True)
    parser.add_argument("--inputs",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(run(args.archive,args.audit,args.inputs,args.out))
