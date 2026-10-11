"""Scheduled continuous drive -> sensor-verified stop -> physical probe -> resume.

This tests time continuity, covariance propagation, physical slip/drift and
post-probe motion. Trigger is a fixed *schedule*, NOT an RF risk detector; it is
not the validated full R2/R4/R5 experiment. Causal control never reads oracle.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .body_dynamics import DifferentialDriveBodyPlant
from .body_sensor_stream import BodySensorStream
from .body_ekf_bridge import ProbeEKF6
from .body_probe_controller import ProbeBodyController,ProbeMotionConfig,wrap
from .body_probe_loop import BodyProbeLoop, ProbeLoopClock


@dataclass(frozen=True)
class ScheduledRouteConfig:
    trigger_after_drive_s: float=10.
    resume_drive_s: float=10.
    stop_timeout_s: float=5.
    stop_hold_s: float=.4
    drive_v_m_s: float=.2
    stop_v_meas_threshold_m_s: float=.01
    stop_w_meas_threshold_deg_s: float=1.5
    heading_hold_gain_s_inv: float=2.
    heading_hold_max_deg_s: float=25.

    def validate(self,clock):
        vals=(self.trigger_after_drive_s,self.resume_drive_s,
             self.stop_timeout_s,self.stop_hold_s,self.drive_v_m_s,
             self.stop_v_meas_threshold_m_s,self.stop_w_meas_threshold_deg_s,
             self.heading_hold_gain_s_inv,self.heading_hold_max_deg_s)
        if any(not math.isfinite(x) or x<=0 for x in vals):
            raise ValueError("invalid scheduled route settings")
        for sec in (self.trigger_after_drive_s,self.resume_drive_s,self.stop_timeout_s):
            if abs(sec/clock.sensor_dt_s-round(sec/clock.sensor_dt_s))>1e-9:
                raise ValueError("route duration must align to estimator clock")


class DriveStopProbeResume:
    def __init__(self,*,plant:DifferentialDriveBodyPlant,
                 sensors:BodySensorStream,ekf:ProbeEKF6,
                 rf_backend=None,receiver=None,station_id=0,mount_deg=0.,
                 route_cfg:ScheduledRouteConfig=ScheduledRouteConfig(),
                 probe_cfg:ProbeMotionConfig=ProbeMotionConfig(),
                 clock:ProbeLoopClock=ProbeLoopClock()):
        route_cfg.validate(clock);clock.ratio();probe_cfg.validate()
        if any(abs(z)>1e-8 for z in (plant.t_s,sensors.t_s,ekf.last_t)):
            raise ValueError("route mode must start at global time zero")
        if abs(mount_deg-ekf.cfg.mount_deg)>1e-10:raise ValueError("mount mismatch")
        self.plant,self.sensors,self.ekf=plant,sensors,ekf
        self.rf_backend,self.receiver=rf_backend,receiver
        self.clock,self.route_cfg,self.probe_cfg=clock,route_cfg,probe_cfg
        self.station_id,self.mount_deg=int(station_id),float(mount_deg)
        self.report_cache=None
        self.control_records=[]
        self.oracle_records=[]

    def _one_tick(self,cmd_v,cmd_w,phase):
        dt=self.clock.physics_dt_s
        ticks=[self.plant.step(command_v_m_s=float(cmd_v),command_w_rad_s=float(cmd_w),
                               dt_s=dt) for _ in range(self.clock.ratio())]
        measurement=self.sensors.measure(ticks)
        self.ekf.start_interval(measurement,phase=phase,probe_id=-1,
                                command_v_m_s=cmd_v,command_w_rad_s=cmd_w)
        self.ekf.finish_interval()
        x=self.ekf.estimate
        measured_yaw_rate=(measurement.dtheta_gyro-x[3]*measurement.dt_s)/(
            (1+x[4])*measurement.dt_s)
        self.oracle_records.append(dict(
            t_s=measurement.t_s,
            true_pose_xyyaw=tuple(ticks[-1].true_pose_xyyaw),
            motor_angles_delta_rad=(
                sum(q.motor_delta_left_rad for q in ticks),
                sum(q.motor_delta_right_rad for q in ticks)),
            true_yaw_increment_rad=sum(q.true_delta_yaw_rad for q in ticks),
            true_body_forward_m=sum(q.true_body_forward_m for q in ticks),
            true_body_lateral_m=sum(q.true_body_lateral_m for q in ticks),
            slip_event=any(q.slip_episode_active for q in ticks),
            slip_left_avg=float(np.mean([q.slip_left for q in ticks])),
            slip_right_avg=float(np.mean([q.slip_right for q in ticks])),
            icr_offset_avg_m=float(np.mean([q.icr_offset_m for q in ticks])),
            true_gyro_bias_rad_s=self.sensors.bias_rad_s))
        self.control_records.append(dict(t_s=measurement.t_s,phase=phase,
            command_v_m_s=float(cmd_v),command_w_rad_s=float(cmd_w),
            estimated_yaw_rad=float(x[2]),controller_source="ESTIMATED_ONLY"))
        # Safety boundary check is a *simulation guard*, never a steering input.
        xt,yt,_=ticks[-1].true_pose_xyyaw
        if xt<1. or xt>19. or abs(yt)>.739:
            raise ValueError("PHYSICAL_ROUTE_OUTSIDE_CORRIDOR")
        return measurement,measured_yaw_rate

    def run(self)->dict:
        if self.report_cache is not None:raise RuntimeError("route can only run once")
        r=self.route_cfg
        goal_heading=float(self.ekf.estimate[2])
        for _ in range(round(r.trigger_after_drive_s/self.clock.sensor_dt_s)):
            # This is an intentionally scheduled event, not a q_site risk trigger.
            self._one_tick(r.drive_v_m_s,0.,"DRIVE_BEFORE_SCHEDULED_TRIGGER")
        hold=0.;stop_done=False
        for _ in range(round(r.stop_timeout_s/self.clock.sensor_dt_s)):
            measured,rate=self._one_tick(0.,0.,"BRAKE_AND_SETTLE")
            v=measured.ds_odom/measured.dt_s
            stable=abs(v)<=r.stop_v_meas_threshold_m_s and abs(rate)<=math.radians(r.stop_w_meas_threshold_deg_s)
            hold=hold+measured.dt_s if stable else 0.
            if hold>=r.stop_hold_s:
                stop_done=True;break
        if not stop_done:raise RuntimeError("CAUSAL_MEASURED_STOP_TIMEOUT")
        ref=float(self.ekf.estimate[2])
        controller=ProbeBodyController(ref,self.probe_cfg)
        probe=BodyProbeLoop(plant=self.plant,sensors=self.sensors,ekf=self.ekf,
            controller=controller,station_id=self.station_id,
            mount_deg=self.mount_deg,receiver=self.receiver,rf_backend=self.rf_backend,
            clock=self.clock)
        probe_result=probe.run()
        if not probe_result["status"].startswith("CONTROL_COMPLETE"):
            raise RuntimeError("PROBE_DID_NOT_COMPLETE:" + probe_result["status"])
        self.oracle_records.extend(probe_result["physical_oracle_eval_only"])
        self.control_records.extend(probe_result["controller_log"])
        for _ in range(round(r.resume_drive_s/self.clock.sensor_dt_s)):
            err=wrap(goal_heading-float(self.ekf.estimate[2]))
            w=float(np.clip(r.heading_hold_gain_s_inv*err,
                -math.radians(r.heading_hold_max_deg_s),
                math.radians(r.heading_hold_max_deg_s)))
            self._one_tick(r.drive_v_m_s,w,"RESUME_DRIVE_POST_PROBE")
        full_trace=self.ekf.traces()
        n=len(full_trace["t_s"])
        if len(self.oracle_records)!=n or len(self.control_records)!=n:
            raise RuntimeError("FULL_ROUTE_PHYSICAL_TRACE_NOT_ALIGNED")
        out=dict(probe_result)
        out["full_P6_trace"]=full_trace
        out["physical_oracle_eval_only"]=self.oracle_records
        out["controller_log"]=self.control_records
        out["n_ticks"]=n
        out["t_last_s"]=float(self.plant.t_s)
        out["scheduled_trigger_type"]="SCHEDULED_NOT_AN_RF_RISK_DETECTOR"
        out["stop_verified_by"]="ESTIMATED_WHEEL_DISTANCE_AND_GYRO_RATE"
        out["full_route_classification"]="MINIMAL_SEGMENT_NOT_R2_R4_R5"
        out["physical_motion_time_s"]=float(self.plant.t_s)
        out["limits"]=dict(probe_result["limits"],full_route="MINIMAL_SEGMENT_ONLY",
             actual_risk_trigger="NOT_IMPLEMENTED",
             R2_R4_R5_CONTINUOUS="NOT_RUN")
        self.report_cache=out
        return out
