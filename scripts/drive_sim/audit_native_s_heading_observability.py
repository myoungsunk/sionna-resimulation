#!/usr/bin/env python3
"""Read-only RF heading *observability*, NOT a filter update or claimed calibration.

Predicts LoS first-tap polarization ratio s at the saved *estimated* pose from
frozen FFD fields, never true pose. Finite-difference sensitivity and full-P6
predicted NIS are calculated for three real native full-RF packets. The LoS
vs full mismatch at truth is ORACLE EVALUATION ONLY; covariance between packet
angles, q_site and q_point is unavailable and no posterior is fabricated.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"src"))
from scripts.drive_sim.calibrate_body_range_los import load_verified_banks
from qclean_uwb.drivesim import observation as O
from qclean_uwb.drivesim.hs_lut import los_h
from qclean_uwb.scenarios.corridor import CorridorSetup


def predict_s(banks,setup,x,y,psi,mount):
    r=setup.robot_position(float(x),float(y))
    d=r-setup.anchor_position
    norm=float(np.linalg.norm(d))
    if norm<=2.2:raise ValueError("ANTENNA_AT_OR_NEAR_ANCHOR")
    H=los_h(banks,d/norm,np.degrees(psi)+mount,dist_m=norm)
    return float(O.observe(H[None],banks[0].freqs_hz,None,None,tx=0)["s"][0])


def sensitivity(banks,setup,x, mount):
    x=np.asarray(x,dtype=float)
    value=predict_s(banks,setup,*x[:3],mount)
    jac=np.zeros(6)
    for j,h in enumerate((.002,.002,.001)):
        plus=x.copy();minus=x.copy();plus[j]+=h;minus[j]-=h
        jac[j]=(predict_s(banks,setup,*plus[:3],mount)-predict_s(banks,setup,*minus[:3],mount))/(2*h)
    return value,jac


def analyze(bank_dir,manifest,run_dir):
    banks,source=load_verified_banks(bank_dir,manifest)
    root=Path(run_dir)
    with np.load(root/"STATE_TRACE.npz",allow_pickle=False) as z:
        trace={k:z[k] for k in z.files}
    with np.load(root/"PROBE_RF_PACKETS.npz",allow_pickle=False) as z:
        rf={k:z[k] for k in z.files}
    with np.load(root/"RF_NATIVE_CHANNELS_ORACLE_ONLY.npz",allow_pickle=False) as z:
        H={k:z[k] for k in z.files}
    original=json.loads((root/"EXECUTION_STATUS.json").read_text(encoding="utf8"))
    cfg=original["filter_config"]
    setup=CorridorSetup(anchor_x_m=float(cfg["anchor_xyz"][0]))
    mount=float(cfg["mount_deg"])
    rows=[]
    for j,i in enumerate(rf["corresponding_state_index"]):
        i=int(i)
        # Estimated XY/yaw from EKF ONLY, after odom and before RF.
        x=np.asarray(trace["x_before_RF"][i],float)
        P=np.asarray(trace["P_before_RF"][i],float)
        pred,J=sensitivity(banks,setup,x,mount)
        measured=float(rf["s_firstpath"][j])
        powers=(float(rf["P1_firstpath"][j]),float(rf["P2_firstpath"][j]))
        # Use the original frozen s_R assumptions (even though s wasn't applied).
        # Do not fit R to the evaluation multipath residuals.
        tap_var=float(cfg["noise_var_cir_tap"])
        thermal=O.thermal_var_rx_s(*powers,float(cfg["noise_var_bin"]),257) if cfg["s_kind"]=="rx" and cfg["noise_var_bin"]>0 else (
            float(8.*tap_var*powers[0]*powers[1]/(sum(powers)**3))
            if tap_var>0 and sum(powers)>0 else 0.0)
        R=float(thermal+cfg["s_var_inflation"]*cfg["s_mismatch_sigma"]**2)
        S=float(J@P@J+R)
        residual=measured-pred
        o_los=O.observe(H["H_los"][j][None],H["freqs_hz"],None,None)
        o_full=O.observe(H["H_full"][j][None],H["freqs_hz"],None,None)
        rows.append(dict(point_index=j,t_s=float(rf["time_rf_s"][j]),
            yaw_estimated_deg=float(np.degrees(x[2])),
            s_measured=measured,s_los_pred_from_estimated_pose=pred,
            innovation_s=float(residual),ds_dyaw_per_rad=float(J[2]),
            ds_dyaw_per_deg=float(J[2]*np.pi/180),
            H_state=J.tolist(),R_s_existing=float(R),
            S_s_predicted=float(S),
            NIS_s_diagnostic=float(residual**2/S) if S>0 else None,
            expected_s_LoS_at_truth_ORACLE=float(o_los["s"][0]),
            expected_s_full_at_truth_ORACLE=float(o_full["s"][0]),
            full_minus_los_ORACLE=float(o_full["s"][0]-o_los["s"][0]),
            current_P6_yaw_std_deg=float(np.degrees(np.sqrt(P[2,2])))))
    return dict(status="NATIVE_S_POLARIZATION_SENSITIVITY_READ_ONLY",
        n_packets=len(rows),RF_s_update_performed=False,
        receiver_input="ACTUAL_NATIVE_FULL_RF_s",
        predicted_model="ANALYTIC_FFD_LOS_at_ESTIMATED_POSE",
        cross_angle_Sigma_s="UNAVAILABLE_NO_SITE_INDEPENDENT_MULTIPATH_COVARIANCE",
        s_range_Sigma_sr="UNAVAILABLE",
        q_site_point="NOT_FITTED",
        source=source,
        rows=rows,
        F01="OPEN",F02="OPEN",scientific_PASS=False)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bank-dir",required=True,type=Path)
    ap.add_argument("--bank-manifest",required=True,type=Path)
    ap.add_argument("--run-dir",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    a=ap.parse_args()
    if a.out.exists():raise FileExistsError("NO_OVERWRITE_OBSERVABILITY")
    result=analyze(a.bank_dir,a.bank_manifest,a.run_dir)
    a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2,allow_nan=False))
if __name__=="__main__":main()
