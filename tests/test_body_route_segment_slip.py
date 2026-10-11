"""Continuous time, nonzero physical slip drive→stop→probe→resume contract.

No native RF is invoked here; tests are exclusively dynamic/causal wiring.
"""
import numpy as np
from qclean_uwb.drivesim.body_dynamics import (
    DifferentialDriveBodyPlant,WheelGeometry,GroundSlipConfig,DriveDynamicsConfig)
from qclean_uwb.drivesim.body_sensor_adapter import RunRealization,SensorAdapterConfig
from qclean_uwb.drivesim.body_sensor_stream import BodySensorStream
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6,V2BodyFilterConfig
from qclean_uwb.drivesim.body_probe_controller import ProbeMotionConfig
from qclean_uwb.drivesim.body_probe_loop import ProbeLoopClock
from qclean_uwb.drivesim.body_route_segment import DriveStopProbeResume,ScheduledRouteConfig

def test_nonzero_slip_schedule_drive_stop_probe_resume_full_p6():
    run=RunRealization(0.,0.,.005,0.)
    geom=run.geometry()
    plant=DifferentialDriveBodyPlant(geometry=geom,
        drive=DriveDynamicsConfig(max_step_s=.02),
        slip=GroundSlipConfig(baseline_right=.05,baseline_icr_offset_m=.005),
        pose0=(7.,.1,0.),seed=22)
    noise=SensorAdapterConfig(gyro_N_rad_sqrt_s=0.,bias_rw_rad_s_sqrt_s=0.,
        k_distance_m=0.,k_yaw_rad=0.,k_yaw_distance_rad2_m=0.)
    sensor=BodySensorStream(geom,run,noise=noise,seed=22)
    cfg=V2BodyFilterConfig(use_range=False,use_s=False,bias_rw_std=0.,
        gyro_N_rad_sqrt_s=0.,k_s=0.,k_theta=0.,k_stheta=0.)
    # At zero Q some innovations have zero-variance status; this is a legal
    # covariance corner and must not be silently inflated.
    ekf=ProbeEKF6(cfg,None,[7.,.1,0.,0.,0.,0.],rf_mode="off")
    loop=DriveStopProbeResume(plant=plant,sensors=sensor,ekf=ekf,
       route_cfg=ScheduledRouteConfig(trigger_after_drive_s=2.,resume_drive_s=2.,
           stop_timeout_s=5.,stop_hold_s=.4),
       probe_cfg=ProbeMotionConfig(offsets_deg=(0.,10.),
           max_total_duration_s=20.,max_stage_duration_s=12.),
       clock=ProbeLoopClock(sensor_dt_s=.2,physics_dt_s=.02,max_duration_s=20.))
    out=loop.run()
    assert out["status"]=="CONTROL_COMPLETE_RF_DISABLED"
    assert out["scheduled_trigger_type"]=="SCHEDULED_NOT_AN_RF_RISK_DETECTOR"
    phases=[r["phase"] for r in out["controller_log"]]
    assert any(p.startswith("DRIVE_BEFORE") for p in phases)
    assert "BRAKE_AND_SETTLE" in phases
    assert "RESUME_DRIVE_POST_PROBE" in phases
    assert len(out["physical_oracle_eval_only"])==out["n_ticks"]
    trace=out["full_P6_trace"]
    assert trace["P_after_RF"].shape==(out["n_ticks"],6,6)
    assert np.min(np.linalg.eigvalsh(trace["P_after_RF"]))>=-1e-9
    assert np.all(np.diff(trace["t_s"])>0)
    assert np.allclose(trace["t_s"],[r["t_s"] for r in out["physical_oracle_eval_only"]])
    assert any(abs(r["slip_right_avg"]-.05)<1e-6 for r in out["physical_oracle_eval_only"])
    assert out["t_last_s"]>4.
    assert out["scientific_PASS"] is False
