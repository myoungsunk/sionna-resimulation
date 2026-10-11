#!/usr/bin/env python3
"""Read-only, paired-trajectory evaluation of an actual native body-probe run.

Replays the EXACT same measured increments with RF disabled and evaluates both
estimates against EVALUATION_ONLY physical pose. This is a controlled estimator
ablation on one RF-enabled trajectory, NOT a counterfactual closed-loop policy,
nor statistical proof of RF heading correction. No oracle data enter the filters.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import numpy as np

from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6,V2BodyFilterConfig
from qclean_uwb.drivesim.body_sensor_stream import MeasuredIncrement


def wrap(a):
    return (a+np.pi)%(2*np.pi)-np.pi


def errors(est,truth):
    diff=np.asarray(est,dtype=float)[:,:3]-np.asarray(truth,dtype=float)
    diff[:,2]=wrap(diff[:,2])
    return diff


def summary(err,P,mask):
    k=np.flatnonzero(mask)
    if k.size==0:return dict(status="NO_SAMPLES")
    e=err[k]
    xy=np.linalg.norm(e[:,:2],axis=1)
    nees=[]
    for row,p in zip(e,P[k,:3,:3]):
        nees.append(float(row@np.linalg.solve(p,row)))
    nees=np.asarray(nees)
    return dict(n_ticks=int(k.size),heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
                heading_final_abs_deg=float(abs(np.degrees(e[-1,2]))),
                position_rmse_m=float(np.sqrt(np.mean(xy**2))),
                position_final_err_m=float(xy[-1]),pose_nees_mean=float(np.mean(nees)),
                pose_nees_p95=float(np.quantile(nees,.95)),
                pose_coverage95_descriptive=float(np.mean(nees<=7.814727903251179)),
                pos_p95_m=float(np.quantile(xy,.95)))


def evaluate(run_dir:Path)->dict:
    run_dir=Path(run_dir)
    with np.load(run_dir/"STATE_TRACE.npz",allow_pickle=False) as z:trace={k:z[k] for k in z.files}
    with np.load(run_dir/"ORACLE_EVAL_ONLY.npz",allow_pickle=False) as z:oracle={k:z[k] for k in z.files}
    with np.load(run_dir/"PROBE_RF_PACKETS.npz",allow_pickle=False) as z:rf={k:z[k] for k in z.files}
    man=json.loads((run_dir/"MANIFEST.json").read_text())
    cfg=man["config"]
    acfg=cfg["initial_filter"];scfg=cfg["sensor"];rcfg=cfg["rf"]
    n=len(trace["t_s"])
    if n<1 or oracle["true_xyyaw"].shape!=(n,3):
        raise ValueError("missing true pose per EKF tick")
    # Zero external RF updates, but the physical commanded path, wheel+IMU
    # measurements, initial 6-state calibration and Q remain exactly paired.
    fc=V2BodyFilterConfig(use_range=False,use_s=False,
        known_wheelbase_error=float(acfg["known_wheelbase_error"]),
        wheel_base=float(cfg["physical"]["nominal_wheelbase_m"]),
        mount_deg=float(rcfg["mount_deg"]),
        anchor_xyz=(float(rcfg["anchor_x_m"]),0.,2.65),robot_z=.45,
        gyro_N_rad_sqrt_s=float(scfg["gyro_N_rad_sqrt_s"]),
        k_s=float(scfg["k_distance_m"]),k_theta=float(scfg["k_yaw_rad"]),
        k_stheta=float(scfg["k_yaw_distance_rad2_m"]),
        bias_rw_std=float(scfg["bias_rw_rad_s_sqrt_s"]),
        range_sigma=float(acfg["range_sigma_m"]),
        range_extra_sigma=float(acfg["range_extra_sigma_m"]),
        s_mismatch_sigma=float(acfg["s_mismatch_sigma"]))
    P0=np.diag(np.asarray(acfg["P0_diagonal"],float))
    rf_off=ProbeEKF6(fc,None,np.asarray(acfg["x0"],float),P0,rf_mode="off")
    base=[]
    for i in range(n):
        rec=MeasuredIncrement(t_s=float(trace["t_s"][i]),dt_s=float(trace["dt_s"][i]),
            ds_odom=float(trace["ds_odom"][i]),dtheta_odom=float(trace["dtheta_odom"][i]),
            dtheta_gyro=float(trace["dtheta_gyro"][i]),
            encoder_left_rad=float(trace["encoder_left_rad"][i]),
            encoder_right_rad=float(trace["encoder_right_rad"][i]),
            wheel_nominal_left_m=float(trace["encoder_left_rad"][i])*float(cfg["physical"]["nominal_radius_m"]),
            wheel_nominal_right_m=float(trace["encoder_right_rad"][i])*float(cfg["physical"]["nominal_radius_m"]))
        rf_off.start_interval(rec,phase=str(trace["phase"][i]))
        base.append(rf_off.finish_interval())
    base_x=np.stack([rec["x_after_RF"] for rec in base])
    base_P=np.stack([rec["P_after_RF"] for rec in base])
    with_rf_x=np.asarray(trace["x_after_RF"],float)
    with_rf_P=np.asarray(trace["P_after_RF"],float)
    if base_x.shape!=with_rf_x.shape or base_P.shape!=with_rf_P.shape:
        raise ValueError("P6 shape mismatch")
    t=np.asarray(trace["t_s"],float)
    ids=np.asarray(rf["corresponding_state_index"],int)
    first_rf_index=int(ids.min()) if ids.size else n
    mask_all=np.ones(n,bool)
    mask_after=np.arange(n)>=first_rf_index
    true=oracle["true_xyyaw"]
    ep=errors(with_rf_x,true)
    eb=errors(base_x,true)
    # Native range is a quantized first arrival; compare against true antenna
    # distance as a diagnostic, not an assumption of unbiased LOS range.
    distance_true=np.linalg.norm(np.column_stack([
        true[ids,0]-float(rcfg["anchor_x_m"]),
        true[ids,1],
        np.full(len(ids),.45-2.65)]),axis=1) if len(ids) else np.zeros(0)
    measurement=np.asarray(rf["range_m"],float)
    range_error=measurement-distance_true
    out=dict(status="DESCRIPTIVE_SINGLE_PHYSICAL_TRAJECTORY_ABLATION",
        scientific_PASS=False,
        run_status=json.loads((run_dir/"EXECUTION_STATUS.json").read_text()).get("status"),
        n_ticks=n,n_rf_packets=int(len(ids)),
        comparison="identical physical path and inertial/wheel input; RF-off filter replay, NOT different commanded policy",
        experimental_arms=["range_only_physical_pose_sionna","rf_off_same_trajectory_replay"],
        metrics=dict(full_route_sensor_window={
            "range_only":summary(ep,with_rf_P,mask_all),
            "rf_off_replay":summary(eb,base_P,mask_all)},
            first_rf_to_end={
            "range_only":summary(ep,with_rf_P,mask_after),
            "rf_off_replay":summary(eb,base_P,mask_after)}),
        actual_packet_time_s=np.asarray(rf["time_rf_s"],float).tolist(),
        true_antenna_distances_m=distance_true.tolist(),
        measured_first_path_distances_m=measurement.tolist(),
        first_path_range_error_m=range_error.tolist(),
        true_final_pose=true[-1].tolist(),
        final_true_translation_from_station_m=float(np.linalg.norm(true[-1,:2]-np.asarray(cfg["physical"]["init_true_xyyaw_rad"][:2]))),
        final_true_yaw_change_deg=float(np.degrees(wrap(true[-1,2]-float(cfg["physical"]["init_true_xyyaw_rad"][2])))),
        random_seed_count=1,
        inferential_ci="UNAVAILABLE_ONE_SEED",
        RF_heading_update_performed=bool(cfg["rf"]["mode"]=="independent_scalar_diagnostic"),
        cross_angle_covariance="NOT_VALIDATED",
        native_full_los_RF_parity="NOT_VERIFIED_BY_THIS_SCRIPT",
        independent_environment_generalization="NOT_TESTED",
        F01="OPEN",F02="OPEN")
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-dir",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    result=evaluate(a.run_dir)
    if a.output.exists():
        raise FileExistsError("audit results are immutable; use a new path")
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print(json.dumps({k:result[k] for k in ("status","n_ticks","n_rf_packets","scientific_PASS")},indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
