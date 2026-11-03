#!/usr/bin/env python3
"""Prospective fixed-pose R1/Anchor B Native RT check for precision V1.
IDs and adapter are committed BEFORE observing new Native results.
This is a P0-only diagnostic, NOT P1 917-pose acquisition.
"""
from __future__ import annotations
import argparse, importlib.util, json, pathlib, sys, traceback
import numpy as np
BASE=pathlib.Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
IDS=(75,305,610,809)  # held out from prior 8 canary
sys.path.insert(0,str(BASE/"runtime"))
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r1b_native as native
from precision_bridge import source_render_for_rt, observe, C

def run(args):
    contract,rows=native.load_contract(BASE/"00_REQUEST_CONTRACT_FROZEN_V2.json")
    assert all(i not in contract["canary"]["pose_ids"] for i in IDS)
    out=pathlib.Path(args.out)
    assert not out.exists(), "Append-only output path required"
    out.mkdir(parents=True)
    engine=native.initialize(contract,args.banks,out)
    results=[]
    status="HOLD"
    try:
        for pose in IDS:
            original=native.acquire_pose(contract,rows[pose],engine,out)
            with np.load(out/f"pose_{pose:04d}.npz",allow_pickle=False) as z:
                hsource=z["source_physical_h"]
                hnative=z["H_los"][:,:,0]
                hcompat=source_render_for_rt(hsource,z["freq_hz"],z["xyz_m"],z["anchor_xyz_m"])
                reference=observe(hnative)
                comp=observe(hcompat)
                rel=float(np.linalg.norm(hcompat-hnative)/np.linalg.norm(hnative))
                item=dict(pose_id=pose,original_complex_rel=original["native_source_complex_relative"],
                          bridge_complex_rel=rel,
                          bridge_s_abs=abs(comp["s"]-reference["s"]),
                          bridge_tap_mismatch=int(comp["tap"]!=reference["tap"]),
                          bridge_port_mismatch=int(comp["port"]!=reference["port"]),
                          raw_sha256=original["raw_sha256"])
                results.append(item)
                print("PROSPECTIVE_POSE",json.dumps(item),flush=True)
        rel=np.array([q["bridge_complex_rel"] for q in results])
        ss=np.array([q["bridge_s_abs"] for q in results])
        limits=contract["tolerances"]
        scores=dict(complex_max=float(rel.max()),complex_rms=float(np.sqrt(np.mean(rel**2))),
                    s_max=float(ss.max()),s_rms=float(np.sqrt(np.mean(ss**2))))
        passed=len(results)==len(IDS) and scores["complex_max"]<=limits["native_complex_relative_max"] and scores["complex_rms"]<=limits["native_complex_relative_rms"] and scores["s_max"]<=limits["native_s_abs_max"] and scores["s_rms"]<=limits["native_s_rmse"] and all(q["bridge_tap_mismatch"]==q["bridge_port_mismatch"]==0 for q in results)
        status="PROSPECTIVE_NATIVE_NUMERIC_PASS" if passed else "PROSPECTIVE_NATIVE_NUMERIC_HOLD"
        receipt=dict(schema="DLP_R1B_PRECISION_V1_PROSPECTIVE_RT",status=status,
                original_v2_science_status="HOLD_RF_PARITY",
                new_native_pose_ids=list(IDS),solver_calls=2*257*len(results),
                approval_scope="P0_ONLY_NUMERIC_EXPERIMENT_NOT_FULL_RF_OR_EKF",
                frozen_tolerances=limits,metrics=scores,records=results,
                no_native_tau_input_to_source=True,nonfitted_adapter=True,
                independent_science_audit="PENDING",
                source_sha=engine[-1]["source_git_sha"])
        native.writej(out/"PREC_V1_PROSPECTIVE_NATIVE_QA.json",receipt)
    except Exception as e:
        native.writej(out/"PREC_V1_PROSPECTIVE_FAILURE.json",dict(error=str(e),
                       traceback=traceback.format_exc(),completed=results))
        partial=native.preserve_partial(out)
        if partial is not None:print("PRESERVED_PARTIAL",partial,flush=True)
        raise
    print("PROSPECTIVE_VERDICT",status,flush=True)
    return 0 if status=="PROSPECTIVE_NATIVE_NUMERIC_PASS" else 2

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--banks",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    args=p.parse_args()
    raise SystemExit(run(args))
