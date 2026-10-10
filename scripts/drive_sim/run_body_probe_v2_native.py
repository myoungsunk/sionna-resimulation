#!/usr/bin/env python3
"""Explicit opt-in runner for body-slip -> streaming sensor-v2 EKF -> exact Sionna RF.

Default command is PRECHECK ONLY (does not generate a trajectory or RF H).
--execute-native must be provided to run the heavy native PathSolver.
Output directory must not pre-exist, and frozen source/results are read-only.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))

from qclean_uwb.drivesim.body_dynamics import (
    WheelGeometry,DriveDynamicsConfig,GroundSlipConfig,DifferentialDriveBodyPlant)
from qclean_uwb.drivesim.body_sensor_adapter import (
    draw_sensor_v2_realization, SensorAdapterConfig)
from qclean_uwb.drivesim.body_sensor_stream import BodySensorStream
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6, V2BodyFilterConfig
from qclean_uwb.drivesim.body_probe_controller import ProbeBodyController, ProbeMotionConfig
from qclean_uwb.drivesim.body_probe_loop import BodyProbeLoop, ProbeLoopClock
from qclean_uwb.drivesim.body_pose_channel import (
    NativeSionnaAtPose,NativeSolverSettings,FirstPathReceiver)
from qclean_uwb.drivesim.hs_lut import HsLut
from qclean_uwb.drivesim.config import build_manifest,file_sha256


def lut_from_assets(p:Path,meta_path:Path):
    meta=json.loads(meta_path.read_text(encoding="utf-8"))["meta"]
    theta=np.asarray(meta["theta_deg"],float)
    start,stop,step=map(float,meta["phi_deg"])
    phi=np.arange(start,stop,step,dtype=float)
    array=np.load(p,allow_pickle=False)
    return HsLut(dict(theta_deg=theta,phi_deg=phi,s=array))


def prerequisite_report(cfg:dict)->dict:
    issues=[]
    if cfg.get("schema_version")!="body-probe-ekf-native-v1":
        issues.append("CONFIG_SCHEMA_MISMATCH")
    rf=cfg["rf"]
    if rf["mode"] not in ("off","range_only","independent_scalar_diagnostic"):
        issues.append("JOINT_COVARIANCE_OR_UNKNOWN_MODE_NOT_EXECUTABLE")
    if rf["mode"]!="off":
        for key in ("bank_dir","bank_manifest"):
            path=rf.get(key)
            if not path or not Path(path).exists():
                issues.append(f"REQUIRED_RF_{key.upper()}_MISSING")
        if rf["mode"]=="independent_scalar_diagnostic":
            for key in ("lut_npy","lut_meta"):
                path=rf.get(key)
                if not path or not Path(path).is_file():
                    issues.append(f"REQUIRED_{key.upper()}_MISSING")
    try:
        ProbeMotionConfig(**cfg["probe"]).validate()
        ProbeLoopClock(**cfg["clock"]).ratio()
        DriveDynamicsConfig(motor_time_constant_s=cfg["physical"]["motor_time_constant_s"],
            max_wheel_accel_rad_s2=cfg["physical"]["max_wheel_accel_rad_s2"],
            max_wheel_speed_rad_s=cfg["physical"]["max_wheel_speed_rad_s"],
            max_step_s=cfg["clock"]["physics_dt_s"]).validate()
        x0=np.asarray(cfg["initial_filter"]["x0"],float)
        P0=np.asarray(cfg["initial_filter"]["P0_diagonal"],float)
        if x0.shape!=(6,) or P0.shape!=(6,) or not np.isfinite(x0).all() or not np.isfinite(P0).all() or (P0<=0).any():
            issues.append("INVALID_INITIAL_P6")
    except (ValueError,KeyError,TypeError) as e:
        issues.append(f"CONFIG_VALIDATION_FAILURE:{e}")
    return dict(status="PREREQUISITES_READY_NOT_EXECUTED" if not issues else "BLOCKED_PRECONDITION",
                issues=issues,scientific_PASS=False,
                note="This precheck never invokes native Sionna or motion simulation.")


def build_run(cfg:dict,out:Path):
    p=cfg["physical"];s=cfg["sensor"];rf=cfg["rf"];prior=cfg["initial_filter"]
    realization=draw_sensor_v2_realization(level=int(s["level"]),seed=int(s["seed"]))
    geo=realization.geometry(radius_m=float(p["nominal_radius_m"]),wheelbase_m=float(p["nominal_wheelbase_m"]))
    slip_mode=p["slip_mode"]
    if slip_mode not in ("neutral","hypothesis"):
        raise ValueError("SLIP_MODE_MUST_BE_NEUTRAL_OR_HYPOTHESIS")
    slip=GroundSlipConfig(
        event_rate_per_s=0. if slip_mode=="neutral" else float(p["physical_slip_event_rate_per_s"]),
        mean_event_duration_s=float(p["physical_slip_mean_duration_s"]),
        event_longitudinal_scale=0. if slip_mode=="neutral" else float(p["physical_slip_event_longitudinal_scale"]),
        event_icr_scale_m=0. if slip_mode=="neutral" else float(p["physical_slip_event_icr_scale_m"]))
    drive=DriveDynamicsConfig(
        motor_time_constant_s=float(p["motor_time_constant_s"]),
        max_wheel_accel_rad_s2=float(p["max_wheel_accel_rad_s2"]),
        max_wheel_speed_rad_s=float(p["max_wheel_speed_rad_s"]),
        max_step_s=float(cfg["clock"]["physics_dt_s"]))
    physical=DifferentialDriveBodyPlant(geometry=geo,drive=drive,slip=slip,
        pose0=tuple(map(float,p["init_true_xyyaw_rad"])),seed=int(s["seed"]))
    noise=SensorAdapterConfig(
        gyro_N_rad_sqrt_s=float(s["gyro_N_rad_sqrt_s"]),
        bias_rw_rad_s_sqrt_s=float(s["bias_rw_rad_s_sqrt_s"]),
        k_distance_m=float(s["k_distance_m"]),k_yaw_rad=float(s["k_yaw_rad"]),
        k_yaw_distance_rad2_m=float(s["k_yaw_distance_rad2_m"]))
    sensors=BodySensorStream(geo,realization,noise=noise,seed=int(s["seed"]))
    mode=rf["mode"]
    lut=lut_from_assets(Path(rf["lut_npy"]),Path(rf["lut_meta"])) if mode=="independent_scalar_diagnostic" else None
    filtercfg=V2BodyFilterConfig(use_range=mode!="off",
        use_s=mode=="independent_scalar_diagnostic",
        anchor_xyz=(float(rf["anchor_x_m"]),0.,2.65),
        mount_deg=float(rf["mount_deg"]),
        known_wheelbase_error=float(prior["known_wheelbase_error"]),
        range_offset=float(prior["range_offset_m"]),
        range_sigma=float(prior["range_sigma_m"]),
        range_extra_sigma=float(prior["range_extra_sigma_m"]),
        s_mismatch_sigma=float(prior["s_mismatch_sigma"]),
        gyro_N_rad_sqrt_s=noise.gyro_N_rad_sqrt_s,
        k_s=noise.k_distance_m,k_theta=noise.k_yaw_rad,
        k_stheta=noise.k_yaw_distance_rad2_m,
        bias_rw_std=noise.bias_rw_rad_s_sqrt_s,
        noise_var_cir_tap=6.*__import__(
            "qclean_uwb.drivesim.observation",fromlist=["noise_var_from_snr"]
        ).noise_var_from_snr(float(rf["snr_db"])))
    ekf=ProbeEKF6(filtercfg,lut,np.asarray(prior["x0"],float),
                  np.diag(np.asarray(prior["P0_diagonal"],float)),rf_mode=mode)
    controller=ProbeBodyController(float(ekf.estimate[2]),
                                  ProbeMotionConfig(
                                      **dict(cfg["probe"],offsets_deg=tuple(cfg["probe"]["offsets_deg"]))))
    native=None;receiver=None
    if mode!="off":
        native=NativeSionnaAtPose(output_scene_dir=out/"native_scene",
            bank_dir=Path(rf["bank_dir"]),bank_manifest=Path(rf["bank_manifest"]),
            anchor_x_m=float(rf["anchor_x_m"]),mount_deg=float(rf["mount_deg"]),
            settings=NativeSolverSettings(max_depth=int(rf["native_full_max_depth"]),
                seed=int(rf["native_full_seed"]),compute_los=bool(rf["compute_los"])))
        receiver=FirstPathReceiver(snr_db=float(rf["snr_db"]),
                                  range_sigma_m=float(rf["range_sigma_m"]),
                                  seed=int(s["seed"]),rf_channel_kind=rf["channel_kind"])
    loop=BodyProbeLoop(plant=physical,sensors=sensors,ekf=ekf,controller=controller,
        mount_deg=float(rf["mount_deg"]),rf_backend=native,
        receiver=receiver,clock=ProbeLoopClock(**cfg["clock"]))
    return loop,realization,filtercfg


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",type=Path,default=ROOT/"configs/body_probe/ekf_native_noisy_body_v1.json")
    ap.add_argument("--out",type=Path)
    ap.add_argument("--execute-native",action="store_true",
                    help="explicitly allow new Sionna H at actual physical probe poses")
    args=ap.parse_args()
    cfg=json.loads(args.config.read_text(encoding="utf-8"))
    report=prerequisite_report(cfg)
    if not args.execute_native:
        print(json.dumps(report,indent=2,ensure_ascii=False))
        return 0 if not report["issues"] else 2
    if report["issues"]:
        print(json.dumps(report,indent=2,ensure_ascii=False),file=sys.stderr)
        return 2
    if args.out is None or args.out.exists():
        raise ValueError("new --out required; overwrite of any existing result is prohibited")
    args.out.mkdir(parents=True,exist_ok=False)
    try:
        loop,realization,filtercfg=build_run(cfg,args.out)
        result=loop.run()
        trace=result.pop("full_P6_trace")
        oracle=result.pop("physical_oracle_eval_only")
        rf_oracle=result.pop("rf_oracle_eval_only")
        native_channels=result.pop("native_channels_oracle_only")
        measured=result.pop("measured_rf_packets")
        controls=result.pop("controller_log")
        np.savez_compressed(args.out/"STATE_TRACE.npz",**trace)
        np.savez_compressed(args.out/"ORACLE_EVAL_ONLY.npz",
            t_s=np.array([r["t_s"] for r in oracle],float),
            true_xyyaw=np.array([r["true_pose_xyyaw"] for r in oracle],float),
            true_motor_angle_increment_rad=np.array([r["motor_angles_delta_rad"] for r in oracle],float),
            true_yaw_increment_rad=np.array([r["true_yaw_increment_rad"] for r in oracle],float),
            true_body_lateral_m=np.array([r["body_lateral_m"] for r in oracle],float),
            true_body_forward_m=np.array([r["true_body_forward_m"] for r in oracle],float),
            true_slip_left_avg=np.array([r["slip_left_avg"] for r in oracle],float),
            true_slip_right_avg=np.array([r["slip_right_avg"] for r in oracle],float),
            true_icr_offset_avg_m=np.array([r["icr_offset_avg_m"] for r in oracle],float),
            true_gyro_bias_rad_s=np.array([r["true_gyro_bias_rad_s"] for r in oracle],float),
            physical_slip_event=np.array([r["slip_event"] for r in oracle],bool))
        (args.out/"PROBE_RF_PACKETS.json").write_text(json.dumps(measured,indent=2),encoding="utf-8")
        times=np.array([r["t_s"] for r in measured],dtype=float)
        corresponding=np.searchsorted(trace["t_s"],times,side="left")
        if len(corresponding) and (
            (corresponding>=len(trace["t_s"])).any() or
            not np.allclose(trace["t_s"][corresponding],times,rtol=0,atol=1e-8)
        ):
            raise ValueError("RF_SAMPLE_INDEX_NOT_ALIGNED")
        np.savez_compressed(args.out/"PROBE_RF_PACKETS.npz",
            time_rf_s=times,corresponding_state_index=corresponding,
            station_id=np.array([r["station_id"] for r in measured],dtype=int),
            point_index=np.array([r["point_index"] for r in measured],dtype=int),
            P1_firstpath=np.array([r["P1"] for r in measured],dtype=float),
            P2_firstpath=np.array([r["P2"] for r in measured],dtype=float),
            s_firstpath=np.array([r["s"] for r in measured],dtype=float),
            range_m=np.array([r["range_m"] for r in measured],dtype=float),
            detected=np.array([r["detected"] for r in measured],dtype=bool),
            selected_tap=np.array([r["first_path_tap"] for r in measured],dtype=int),
            yaw_body_est_before_rf_rad=np.array(
                [r["estimate_yaw_pre_rf_rad"] for r in measured],dtype=float))
        if native_channels:
            # The complex full/LoS channel is an evaluation/provenance-only artifact.
            # It MUST NOT be used as an online filter feature or fixed-XY lookup.
            rf_dump=dict(freqs_hz=native_channels[0].freqs_hz,
                time_rf_s=np.array([r.request.t_s for r in native_channels],float),
                true_body_pose_xyyaw=np.array(
                    [r.request.true_pose_xyyaw for r in native_channels],float),
                rx_mount_deg=np.array([r.request.mount_deg for r in native_channels],float),
                H_full=np.stack([r.H_full for r in native_channels]),
                packet_id=np.array([r.request.packet_id for r in native_channels],dtype=str))
            if all(r.H_los is not None for r in native_channels):
                rf_dump["H_los"]=np.stack([r.H_los for r in native_channels])
            np.savez_compressed(args.out/"RF_NATIVE_CHANNELS_ORACLE_ONLY.npz",**rf_dump)
        (args.out/"COVARIANCE_STATUS.json").write_text(json.dumps(dict(
            Sigma_sr="NOT_FITTED",Sigma_probe_cross_angle="NOT_FITTED",
            joint_site_point="NOT_IMPLEMENTED",source_independent_geometry="NOT_VALIDATED",
            scientific_PASS=False),indent=2),encoding="utf-8")
        (args.out/"RF_ORACLE_RECEIPT.json").write_text(json.dumps(rf_oracle,indent=2,default=str),encoding="utf-8")
        (args.out/"BODY_CONTROL_LOG.json").write_text(json.dumps(controls,indent=2),encoding="utf-8")
        (args.out/"EXECUTION_STATUS.json").write_text(json.dumps(
            dict(result,realization=asdict(realization),filter_config=asdict(filtercfg)),
            indent=2,default=str),encoding="utf-8")
        sources=[args.config]
        sources += [ROOT/p for p in (
            "src/qclean_uwb/drivesim/body_dynamics.py",
            "src/qclean_uwb/drivesim/body_sensor_adapter.py",
            "src/qclean_uwb/drivesim/body_sensor_stream.py",
            "src/qclean_uwb/drivesim/body_probe_controller.py",
            "src/qclean_uwb/drivesim/body_ekf_bridge.py",
            "src/qclean_uwb/drivesim/filter_v2.py",
            "src/qclean_uwb/drivesim/sensor_v2.py",
            "src/qclean_uwb/drivesim/body_pose_channel.py",
            "src/qclean_uwb/drivesim/body_probe_loop.py",
            "scripts/drive_sim/run_body_probe_v2_native.py",
            "scripts/corridor_sionna_run.py"
        )]
        if cfg["rf"]["mode"]!="off":
            rf=cfg["rf"]; sources += [Path(rf["bank_manifest"])]
            sources += [Path(rf["bank_dir"])/f"{n}_bank.npz" for n in ("LP_plus45","LP_minus45")]
            if rf["lut_npy"]: sources += [Path(rf["lut_npy"]),Path(rf["lut_meta"])]
        targets=[args.out/p for p in ("STATE_TRACE.npz","ORACLE_EVAL_ONLY.npz",
            "PROBE_RF_PACKETS.json","PROBE_RF_PACKETS.npz","COVARIANCE_STATUS.json",
            "RF_ORACLE_RECEIPT.json","BODY_CONTROL_LOG.json","EXECUTION_STATUS.json")]
        if native_channels:targets.append(args.out/"RF_NATIVE_CHANNELS_ORACLE_ONLY.npz")
        manifest=build_manifest(config=dict(cfg,applied_realization=asdict(realization),
            applied_filter_config=asdict(filtercfg),run_status=result["status"],
            new_physical_RF=True,scientific_PASS=False),
            inputs=sources,outputs=targets,command=sys.argv)
        (args.out/"MANIFEST.json").write_text(json.dumps(manifest,indent=2,default=str),encoding="utf-8")
        print(json.dumps(dict(status=result["status"],duration_s=result["t_last_s"],
            rf_packets=result["n_rf_packets"],out=str(args.out),
            scientific_PASS=False),ensure_ascii=False))
        return 0 if result["status"].startswith("CONTROL_COMPLETE") else 3
    except BaseException as exc:
        (args.out/"FAILURE.json").write_text(json.dumps(
            dict(status="FAILED_PARTIAL_OR_PRECONDITION",
                 error=repr(exc),traceback=traceback.format_exc(),scientific_PASS=False),
            indent=2),encoding="utf-8")
        raise


if __name__=="__main__":
    raise SystemExit(main())
