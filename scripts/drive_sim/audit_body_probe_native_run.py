#!/usr/bin/env python3
"""Read-only audit of an already-created native body-probe run directory.

A PASS here means stored software traces match the data contract. It does NOT
validate Sionna RT physics, hardware motion/slip, NEES calibration, or the RF
heading benefit. This tool never starts or modifies a run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

P6_STAGES = (
    "P_pred_before_odom", "P_after_odom", "P_after_range",
    "P_before_RF", "P_after_RF")
X6_STAGES = (
    "x_pred_before_odom", "x_after_odom", "x_after_range",
    "x_before_RF", "x_after_RF")


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda:fp.read(2**20),b""):
            h.update(chunk)
    return h.hexdigest()


def audit_run(root: Path) -> dict:
    root=Path(root)
    issues=[]
    receipt={"root":str(root),"scientific_PASS":False,
             "type":"READ_ONLY_STORED_SOFTWARE_TRACE_AUDIT",
             "validated_areas":[],"not_validated":[
                 "NATIVE_SIONNA_PHYSICAL_ACCURACY",
                 "RF_LOS_AND_FFD_PARITY",
                 "REAL_ROBOT_AND_GROUND_SLIP",
                 "HEADING_BENEFIT_AND_NEES_COVERAGE",
                 "MULTI_ANGLE_JOINT_RF_COVARIANCE"]}

    required=("STATE_TRACE.npz","ORACLE_EVAL_ONLY.npz","PROBE_RF_PACKETS.npz",
              "EXECUTION_STATUS.json","MANIFEST.json")
    missing=[x for x in required if not (root/x).is_file()]
    if missing:
        return dict(receipt,status="BLOCKED",issues=["MISSING:"+str(x) for x in missing])
    try:
        run=json.loads((root/"EXECUTION_STATUS.json").read_text())
        manifest=json.loads((root/"MANIFEST.json").read_text())
        config=manifest["config"]
        for item in manifest.get("outputs",[]):
            path=Path(item["path"])
            if not path.is_absolute():path=root/path
            if not path.is_file():
                issues.append("MANIFEST_OUTPUT_MISSING:"+str(path))
            elif sha(path)!=item["sha256"]:
                issues.append("OUTPUT_HASH_MISMATCH:"+str(path.name))
        receipt["run_status"]=run.get("status")
        receipt["n_rf_packets_expected"]=len(config["probe"]["offsets_deg"])
        if run.get("status")!="CONTROL_COMPLETE_RF_COLLECTED":
            issues.append("PROBE_NOT_COMPLETED")
        with np.load(root/"STATE_TRACE.npz",allow_pickle=False) as z:
            trace={name:z[name] for name in z.files}
        with np.load(root/"ORACLE_EVAL_ONLY.npz",allow_pickle=False) as z:
            oracle={name:z[name] for name in z.files}
        with np.load(root/"PROBE_RF_PACKETS.npz",allow_pickle=False) as z:
            rf={name:z[name] for name in z.files}
        times=np.asarray(trace["t_s"],float)
        n=len(times)
        receipt["n_estimator_ticks"]=n
        if n==0 or not np.isfinite(times).all() or np.any(np.diff(times)<=0):
            issues.append("ESTIMATOR_TIME_INVALID")
        for name in X6_STAGES:
            arr=np.asarray(trace[name],float)
            if arr.shape!=(n,6) or not np.isfinite(arr).all():
                issues.append("INVALID_STATE:"+name)
        min_eig={}
        for name in P6_STAGES:
            arr=np.asarray(trace[name],float)
            if arr.shape!=(n,6,6) or not np.isfinite(arr).all():
                issues.append("INVALID_P6:"+name)
                continue
            skew=np.max(np.abs(arr-np.swapaxes(arr,1,2)))
            ev=np.linalg.eigvalsh((arr+np.swapaxes(arr,1,2))/2)
            mineig=float(ev.min())
            min_eig[name]=mineig
            threshold=1e-9*max(1.,float(np.max(np.abs(arr))))
            if skew>threshold or mineig< -threshold:
                issues.append("P6_NOT_PSD:"+name)
        receipt["minimum_P6_eigenvalues"]=min_eig
        if len(times) and "true_xyyaw" in oracle:
            if oracle["true_xyyaw"].shape!=(n,3):
                issues.append("PHYSICAL_POSE_SHAPE_MISMATCH")
            elif not np.allclose(oracle["t_s"],times,atol=1e-7,rtol=0):
                issues.append("ORACLE_AND_ESTIMATOR_CLOCK_MISMATCH")
        if config["physical"]["slip_mode"]=="neutral":
            if np.asarray(oracle["physical_slip_event"],bool).any():
                issues.append("NEUTRAL_SLIP_EVENT_DETECTED")
        receipt["physical_slip_mode"]=config["physical"]["slip_mode"]
        if len(times)>0 and "F" in trace and "G" in trace and "Q_input" in trace:
            try:
                p0=np.diag(np.asarray(config["initial_filter"]["P0_diagonal"],float))
                max_residual=0.
                for k in range(n):
                    prev=p0 if k==0 else trace["P_after_RF"][k-1]
                    predicted=(trace["F"][k] @ prev @ trace["F"][k].T +
                               trace["G"][k] @ trace["Q_input"][k] @ trace["G"][k].T)
                    max_residual=max(max_residual,float(np.max(np.abs(
                        predicted-trace["P_pred_before_odom"][k]))))
                receipt["max_prediction_P6_residual"]=max_residual
                if max_residual>1e-8:
                    issues.append("P6_PREDICTION_RECONSTRUCTION_MISMATCH")
            except (ValueError,KeyError) as exc:
                issues.append("P6_PREDICTION_RECONSTRUCTION_ERROR:"+str(exc))
        pr=np.asarray(rf["time_rf_s"],float)
        idx=np.asarray(rf["corresponding_state_index"],int)
        receipt["n_rf_packets"]=len(pr)
        if len(pr)!=receipt["n_rf_packets_expected"]:
            issues.append("RF_PACKET_COUNT_NOT_EXPECTED")
        if len(idx)!=len(pr) or (len(idx) and (idx.min()<0 or idx.max()>=n)):
            issues.append("RF_PACKET_INDEX_OUT_OF_RANGE")
        elif not np.allclose(times[idx],pr,rtol=0,atol=1e-7):
            issues.append("RF_PACKET_TIMESTAMP_NOT_MATCHED")
        positive=np.asarray(rf["detected"],bool)
        P1=np.asarray(rf["P1_firstpath"],float)
        P2=np.asarray(rf["P2_firstpath"],float)
        observed=np.asarray(rf["s_firstpath"],float)
        den=P1+P2
        if (positive & ((den<=0)|(~np.isfinite(observed)))).any():
            issues.append("DETECTED_RF_INVALID_POWER")
        valid=positive & (den>0)
        if valid.any() and not np.allclose(
            observed[valid],(P1[valid]-P2[valid])/den[valid],rtol=0,atol=1e-10):
            issues.append("RF_S_POWER_RATIO_MISMATCH")
        if config["rf"]["mode"]=="range_only":
            for lhs,rhs in (("x_after_range","x_after_RF"),
                            ("P_after_range","P_after_RF")):
                if not np.allclose(trace[lhs],trace[rhs],rtol=0,atol=1e-10):
                    issues.append("RANGE_ONLY_UNEXPECTED_S_UPDATE:"+lhs)
        native_path=root/"RF_NATIVE_CHANNELS_ORACLE_ONLY.npz"
        if native_path.is_file():
            with np.load(native_path,allow_pickle=False) as z:
                h=np.asarray(z["H_full"])
                if h.shape!=(len(pr),257,2,2) or not np.isfinite(h).all():
                    issues.append("NATIVE_H_SHAPE_OR_FINITE_ERROR")
                if not np.allclose(z["time_rf_s"],pr,atol=1e-7,rtol=0):
                    issues.append("RF_CHANNEL_CLOCK_MISMATCH")
                if len(idx)==len(pr) and (not len(idx) or (idx.min()>=0 and idx.max()<n)):
                    if not np.allclose(z["true_body_pose_xyyaw"],oracle["true_xyyaw"][idx],
                                       atol=1e-7,rtol=0):
                        issues.append("RF_CHANNEL_TRUE_POSE_MISMATCH")
        else:
            issues.append("NATIVE_CHANNEL_ARCHIVE_MISSING")
        receipt["validated_areas"]=["MANIFEST_OUTPUT_SHA256","P6_SHAPES_AND_PSD",
            "P6_PREDICTION_REPLAY","TRUE_POSE_PACKET_ALIGNMENT",
            "RF_POWERS_RATIO","NEUTRAL_SLIP_STATUS","RANGE_ONLY_UPDATE_POLICY"]
    except (OSError,KeyError,ValueError,TypeError,IndexError) as exc:
        issues.append("UNREADABLE_OR_INCOMPATIBLE_OUTPUT:"+type(exc).__name__+":"+str(exc))
    receipt["issues"]=issues
    receipt["status"]="STORED_TRACE_AUDIT_PASS_NOT_SCIENCE" if not issues else "FAIL"
    return receipt


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True,type=Path,help="existing run output dir; read-only")
    ap.add_argument("--receipt",type=Path,help="new audit result path, never overwrite")
    args=ap.parse_args()
    result=audit_run(args.out)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if args.receipt:
        if args.receipt.exists() or not args.receipt.parent.is_dir():
            raise ValueError("new audit receipt path required")
        args.receipt.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return 0 if not result["issues"] else 2


if __name__=="__main__":
    raise SystemExit(main())
