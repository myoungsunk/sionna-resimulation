#!/usr/bin/env python3
"""Paired CPU physical-slip *route segment* dynamics audit.

RF OFF deliberately: isolate real plant slip, actuator timing and 6x6 EKF
model mismatch on continuous DRIVE->BRAKE->BODY-PROBE->RESUME. Risk trigger is
a scheduled timer only; NOT an online RF reliability detector, and *not*
Sionna-RF heading improvement evidence. No user source or frozen output writes.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
from qclean_uwb.drivesim.body_dynamics import (
    GroundSlipConfig,DriveDynamicsConfig,DifferentialDriveBodyPlant)
from qclean_uwb.drivesim.body_sensor_adapter import (
    draw_sensor_v2_realization,SensorAdapterConfig)
from qclean_uwb.drivesim.body_sensor_stream import BodySensorStream
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6,V2BodyFilterConfig
from qclean_uwb.drivesim.body_probe_controller import ProbeMotionConfig
from qclean_uwb.drivesim.body_probe_loop import ProbeLoopClock
from qclean_uwb.drivesim.body_route_segment import DriveStopProbeResume,ScheduledRouteConfig


def wrap(x):
    return (x+np.pi)%(2*np.pi)-np.pi


def one(seed,slip_mode,mount,prior_seed):
    realization=draw_sensor_v2_realization(level=1,seed=seed)
    geo=realization.geometry()
    slip=GroundSlipConfig() if slip_mode=="neutral" else GroundSlipConfig(
        baseline_left=0.,baseline_right=.05,baseline_icr_offset_m=.005,
        event_rate_per_s=.0502516793,mean_event_duration_s=.15,
        event_longitudinal_scale=.02,event_icr_scale_m=.005)
    plant=DifferentialDriveBodyPlant(geometry=geo,drive=DriveDynamicsConfig(max_step_s=.02),
        slip=slip,pose0=(7.,.1,0.),seed=seed)
    noise=SensorAdapterConfig()
    stream=BodySensorStream(geo,realization,noise=noise,seed=seed)
    nominal=np.array([7.,.1,0.,0.,0.,0.])
    rng=np.random.default_rng([2301026,int(prior_seed)])
    prior_draw=rng.normal(size=3)*[.10,.10,np.deg2rad(5.)]
    nominal[:3]+=prior_draw
    p0=np.diag([.01,.01,np.deg2rad(5.)**2,np.deg2rad(.12)**2,.0104**2,.0064**2])
    cfg=V2BodyFilterConfig(use_range=False,use_s=False,
        mount_deg=float(mount),bias_rw_std=noise.bias_rw_rad_s_sqrt_s,
        gyro_N_rad_sqrt_s=noise.gyro_N_rad_sqrt_s,
        k_s=noise.k_distance_m,k_theta=noise.k_yaw_rad,
        k_stheta=noise.k_yaw_distance_rad2_m)
    ekf=ProbeEKF6(cfg,None,nominal,p0,rf_mode="off")
    route=DriveStopProbeResume(plant=plant,sensors=stream,ekf=ekf,
        mount_deg=mount,
        route_cfg=ScheduledRouteConfig(trigger_after_drive_s=2.,resume_drive_s=2.,
            stop_timeout_s=5.,stop_hold_s=.4,drive_v_m_s=.2),
        probe_cfg=ProbeMotionConfig(offsets_deg=(0.,10.,20.),
            max_total_duration_s=30.,max_stage_duration_s=15.),
        clock=ProbeLoopClock(sensor_dt_s=.2,physics_dt_s=.02,max_duration_s=30.))
    result=route.run()
    tr=result["full_P6_trace"]
    pos=np.asarray([x["true_pose_xyyaw"] for x in result["physical_oracle_eval_only"]])
    est=tr["x_after_RF"]
    err=est[:,:3]-pos
    err[:,2]=wrap(err[:,2])
    nees=np.asarray([float(e@np.linalg.solve(P[:3,:3],e))
        for e,P in zip(err,tr["P_after_RF"])])
    phases=np.asarray(tr["phase"])
    after=np.array([p=="RESUME_DRIVE_POST_PROBE" for p in phases])
    if not after.any():raise ValueError("SCHEDULED_RESUME_NOT_REACHED")
    counts={str(p):int((phases==p).sum()) for p in np.unique(phases)}
    slipavg=np.asarray([x["slip_right_avg"] for x in result["physical_oracle_eval_only"]])
    xydrift=float(np.linalg.norm(pos[-1,:2]-np.array([7.,.1])))
    return dict(seed=int(seed),prior_random_seed=int(prior_seed),physical_slip_arm=slip_mode,
        mount_deg=float(mount),status=result["status"],n_ticks=len(phases),
        elapsed_s=float(tr["t_s"][-1]),
        slip_event_count=int(sum(x["slip_event"] for x in result["physical_oracle_eval_only"])),
        right_physical_slip_mean=float(slipavg.mean()),
        phase_counts=counts,
        initial_true_pose=[7.,.1,0.],initial_estimated_pose=nominal[:3].tolist(),
        pos_rmse_m=float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))),
        heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(err[:,2]**2)))),
        post_resume_pos_rmse_m=float(np.sqrt(np.mean(np.sum(err[after,:2]**2,axis=1)))),
        post_resume_heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(err[after,2]**2)))),
        final_true_xy_move_m=xydrift,
        final_true_y_m=float(pos[-1,1]),
        final_true_heading_deg=float(np.degrees(pos[-1,2])),
        pose_nees_mean=float(nees.mean()),
        pose_nees_upper_975_fraction=float(np.mean(nees>9.348403604)),
        P6_min_eigenvalue=float(np.min(np.linalg.eigvalsh(tr["P_after_RF"]))))


def run(seeds,mounts):
    rows=[];errors=[]
    for mount in mounts:
        for seed in seeds:
            for arm in ("neutral","hypothesis"):
                try:
                    rows.append(one(seed,arm,mount,prior_seed=1000+seed))
                except Exception as e:
                    errors.append(dict(seed=seed,mount=mount,arm=arm,error=str(e)))
    grouped={}
    for mount in mounts:
        for arm in ("neutral","hypothesis"):
            valid=[x for x in rows if x["mount_deg"]==mount and x["physical_slip_arm"]==arm]
            if not valid:continue
            grouped[f"mount{mount}_{arm}"]=dict(n=len(valid),
                mean_heading_rmse_deg=float(np.mean([r["heading_rmse_deg"] for r in valid])),
                mean_pos_rmse_m=float(np.mean([r["pos_rmse_m"] for r in valid])),
                mean_pose_nees=float(np.mean([r["pose_nees_mean"] for r in valid])),
                mean_true_end_y_m=float(np.mean([r["final_true_y_m"] for r in valid])),
                mean_elapsed_s=float(np.mean([r["elapsed_s"] for r in valid])))
    return dict(status="MINIMAL_SCHEDULED_ROUTE_PHYSICAL_SLIP_DIAGNOSTIC",
        n_run=len(rows),n_failed=len(errors),failures=errors,
        sensor_seed_ids=list(seeds),mounts_deg=list(mounts),
        arms=["neutral","hypothesis"],
        trigger="SCHEDULED_AT_2S_NOT_RISK_DETECTOR",
        RF_sionna="OFF_NOT_AN_RF_BENEFIT_EXPERIMENT",
        physical_slip_hypothesis="constant right wheel 5pct, lateral ICR=0.005m plus episodic stress; not hardware-fitted",
        parameters_q_r_gate="ORIGINAL_V2_SENSOR_ASSUMPTIONS_NO_TUNING",
        per_arm_means=grouped,per_run=rows,
        cross_geometry="NOT_TESTED",scientific_PASS=False,F01="OPEN",F02="OPEN")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--seeds",type=int,nargs="+",default=list(range(10)))
    p.add_argument("--mounts",type=float,nargs="+",default=[0.,45.])
    args=p.parse_args()
    if args.out_dir.exists():raise FileExistsError("NEW_OUTPUT_ONLY")
    summary=run(args.seeds,args.mounts)
    args.out_dir.mkdir(parents=True,exist_ok=False)
    (args.out_dir/"ROUTE_SLIP_SUMMARY.json").write_text(
        json.dumps(summary,indent=2,allow_nan=False)+"\n")
    if summary["per_run"]:
        with (args.out_dir/"ROUTE_SLIP_PER_RUN.csv").open("w",newline="") as f:
            keys=[k for k in summary["per_run"][0] if k!="phase_counts"]
            writer=csv.DictWriter(f,fieldnames=keys)
            writer.writeheader()
            for item in summary["per_run"]:writer.writerow({k:item[k] for k in keys})
    print(json.dumps({k:summary[k] for k in
        ("status","n_run","n_failed","per_arm_means","scientific_PASS")},indent=2))
    return 0 if not summary["failures"] else 3


if __name__=="__main__":raise SystemExit(main())
