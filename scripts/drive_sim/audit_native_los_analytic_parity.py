#!/usr/bin/env python3
"""Independent post-fit LoS FFD analytic vs actual Sionna PathSolver H parity.

Calibration has ALREADY been committed to disk from separate physical XY sites
before this tool may read evaluation's true poses. Oracle inputs are for
evaluation/parity only; never fed back into calibration or online EKF.
"""
from __future__ import annotations
import argparse
import json
import numpy as np
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
from scripts.drive_sim.calibrate_body_range_los import load_verified_banks
from qclean_uwb.drivesim.hs_lut import los_h
from qclean_uwb.drivesim.observation import observe
from qclean_uwb.scenarios.corridor import CorridorSetup

def validate(banks,run_dir,meta):
    cm=json.loads(Path(meta).read_text())
    if cm.get("schema_version")!="INDEPENDENT_FFD_LOS_DETECTOR_CAL_V1":
        raise ValueError("FIT_MUST_EXIST_BEFORE_EVAL_PARITY")
    if cm["true_evaluation_RF_input"]!="NOT_USED":
        raise ValueError("CALIBRATION_WAS_NOT_INDEPENDENT")
    with np.load(Path(run_dir)/"RF_NATIVE_CHANNELS_ORACLE_ONLY.npz",allow_pickle=False) as z:
        native={k:z[k] for k in z.files}
    if "H_los" not in native:
        raise ValueError("NATIVE_LOS_CHANNEL_MISSING")
    f=banks[0].freqs_hz
    if not np.array_equal(f,native["freqs_hz"]):
        raise ValueError("FREQUENCY_BINS_DO_NOT_MATCH")
    setup=CorridorSetup(anchor_x_m=4.)
    matches=[]
    for i,(pose,mount) in enumerate(zip(native["true_body_pose_xyyaw"],native["rx_mount_deg"])):
        x,y,psi=map(float,pose)
        pos=setup.robot_position(x,y)
        dp=pos-setup.anchor_position
        dist=float(np.linalg.norm(dp))
        analytic=los_h(banks,dp/dist,np.degrees(psi)+float(mount),dist_m=dist)
        native_los=native["H_los"][i]
        err=float(np.linalg.norm(analytic-native_los)/(np.linalg.norm(native_los)+1e-300))
        predicted=observe(analytic[None],f,None,None)
        observed=observe(native_los[None],f,None,None)
        matches.append(dict(point_index=i,mount_deg=float(mount),
            complex_relative_l2_error=err,
            analytic_first_tap=int(predicted["index"][0]),
            native_first_tap=int(observed["index"][0]),
            analytic_range_m=float(predicted["range_m"][0]),
            native_los_range_m=float(observed["range_m"][0]),
            analytic_s=float(predicted["s"][0]),
            native_s=float(observed["s"][0])))
    passed=bool(all(r["complex_relative_l2_error"]<=1e-3
                    and r["analytic_first_tap"]==r["native_first_tap"] for r in matches))
    return dict(status="NATIVE_ANALYTIC_LOS_PARITY_PASS" if passed else "NATIVE_ANALYTIC_LOS_PARITY_FAIL",
        n_eval_rf=len(matches),evaluated_only_after_other_site_calibration=True,
        thresholds=dict(complex_relative_l2=1e-3,first_tap_difference=0),
        comparisons=matches,scientific_PASS=False,F01="OPEN",F02="OPEN")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bank-dir",required=True,type=Path)
    p.add_argument("--bank-manifest",required=True,type=Path)
    p.add_argument("--run-dir",required=True,type=Path)
    p.add_argument("--calibration",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError("PARITY_RECEIPT_OVERWRITE_PROHIBITED")
    banks,_=load_verified_banks(a.bank_dir,a.bank_manifest)
    result=validate(banks,a.run_dir,a.calibration)
    a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2,allow_nan=False))
    return 0 if result["status"].endswith("_PASS") else 2
if __name__=="__main__":raise SystemExit(main())
