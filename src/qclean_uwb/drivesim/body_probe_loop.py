"""Causal body-probe plant -> sensor-v2 EKF -> controller -> native RF loop.

No run is triggered at import. Real Sionna solve occurs only when controller fires
a packet at the actual physics pose/time. No fixed-truth H is substituted.
This first stage handles a single station, not whole-route A-H campaigns.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from .body_dynamics import DifferentialDriveBodyPlant
from .body_sensor_stream import BodySensorStream
from .body_probe_controller import ProbeBodyController, ProbeMotionConfig
from .body_ekf_bridge import ProbeEKF6
from .body_pose_channel import RFPoseRequest, FirstPathReceiver


@dataclass(frozen=True)
class ProbeLoopClock:
    sensor_dt_s: float = 0.2
    physics_dt_s: float = 0.02
    max_duration_s: float = 90.

    def ratio(self)->int:
        vals=(self.sensor_dt_s,self.physics_dt_s,self.max_duration_s)
        if any(not math.isfinite(v) or v<=0 for v in vals):
            raise ValueError("invalid clock settings")
        n=round(self.sensor_dt_s/self.physics_dt_s)
        if n<1 or not math.isclose(n*self.physics_dt_s,self.sensor_dt_s,abs_tol=1e-10):
            raise ValueError("sensor clock must exactly contain physics substeps")
        return int(n)


class BodyProbeLoop:
    """One physically timed probe with full-state EKF and optional native RF backend.

    The controller reads estimated yaw/gyro rate only; RF backend reads physical
    body pose only. Event time is the real end of a sensor interval, not a
    precomputed ideal-yaw pose. Calibration/source provenance is retained.
    """

    def __init__(self,*,plant:DifferentialDriveBodyPlant,
                 sensors:BodySensorStream,ekf:ProbeEKF6,
                 controller:ProbeBodyController,station_id:int=0,
                 mount_deg:float=0.,receiver:FirstPathReceiver|None=None,
                 rf_backend:Any=None,clock:ProbeLoopClock=ProbeLoopClock()):
        if not math.isclose(plant.t_s,sensors.t_s,abs_tol=1e-10) or not math.isclose(plant.t_s,ekf.last_t,abs_tol=1e-10):
            raise ValueError("plant, sensor and EKF must share an initial clock")
        if not math.isclose(plant.drive.max_step_s,clock.physics_dt_s,rel_tol=0,abs_tol=1e-10) and plant.drive.max_step_s<clock.physics_dt_s:
            raise ValueError("physics clock larger than plant max step")
        if not math.isclose(mount_deg,ekf.cfg.mount_deg,abs_tol=1e-12):
            raise ValueError("RF RX mounting configuration mismatch")
        self.nphysics=clock.ratio()
        self.clock=clock;self.plant=plant;self.sensors=sensors;self.ekf=ekf
        self.controller=controller;self.station_id=int(station_id);self.mount_deg=float(mount_deg)
        self.receiver=receiver;self.rf_backend=rf_backend
        self.cmd_v=0.;self.cmd_w=0.
        self.rf_oracle=[]
        self.rf_measured=[]
        self.native_channel_evidence=[]  # exact-pose H; never passed into EKF
        self.body_oracle=[]
        self.control_log=[]
        self.status="NOT_RUN"

    def run(self)->dict:
        if self.status!="NOT_RUN":
            raise RuntimeError("probe loop can be executed only once")
        if self.ekf.rf_mode!="off" and (self.rf_backend is None or self.receiver is None):
            raise ValueError("RF_BACKEND_OR_RECEIVER_MISSING; no synthetic fallback")
        nsteps=int(self.clock.max_duration_s/self.clock.sensor_dt_s)
        self.status="RUNNING"
        for k in range(nsteps):
            v0,w0=self.cmd_v,self.cmd_w
            ticks=[self.plant.step(command_v_m_s=v0,command_w_rad_s=w0,
                                   dt_s=self.clock.physics_dt_s)
                   for _ in range(self.nphysics)]
            measured=self.sensors.measure(ticks)
            phase=self.controller.phase
            self.ekf.start_interval(measured,phase=phase,probe_id=self.station_id,
                                    command_v_m_s=v0,command_w_rad_s=w0)
            # The feedback rate is derived from measured IMU and current *estimated*
            # bias/scale. Never use BodyTick.true_body_w_rad_s for feedback.
            est=self.ekf.estimate
            rate=(measured.dtheta_gyro-est[3]*measured.dt_s)/(
                    (1+est[4])*measured.dt_s)
            control=self.controller.update(estimated_yaw_rad=float(est[2]),
                                           estimated_yaw_rate_rad_s=float(rate),
                                           dt_s=measured.dt_s)
            self.cmd_v=float(control.command_linear_m_s)
            self.cmd_w=float(control.command_angular_rad_s)
            self.control_log.append(dict(t_s=measured.t_s,phase=control.phase,
                target_offset_deg=control.target_offset_deg,command_v_m_s=self.cmd_v,
                command_w_rad_s=self.cmd_w,rf_fire=control.rf_fire,
                rf_point_index=control.rf_point_index,
                return_complete=control.done,failed=control.failed))
            self.body_oracle.append(dict(t_s=measured.t_s,
                true_pose_xyyaw=tuple(ticks[-1].true_pose_xyyaw),
                motor_angles_delta_rad=(sum(q.motor_delta_left_rad for q in ticks),
                                        sum(q.motor_delta_right_rad for q in ticks)),
                true_yaw_increment_rad=sum(q.true_delta_yaw_rad for q in ticks),
                true_body_forward_m=sum(q.true_body_forward_m for q in ticks),
                slip_event=any(q.slip_episode_active for q in ticks),
                slip_left_avg=float(np.mean([q.slip_left for q in ticks])),
                slip_right_avg=float(np.mean([q.slip_right for q in ticks])),
                icr_offset_avg_m=float(np.mean([q.icr_offset_m for q in ticks])),
                body_lateral_m=sum(q.true_body_lateral_m for q in ticks),
                true_gyro_bias_rad_s=self.sensors.bias_rad_s))
            if control.rf_fire:
                request=RFPoseRequest(
                    packet_id=f"station{self.station_id}_pt{control.rf_point_index}_t{k+1}",
                    t_s=measured.t_s,
                    true_pose_xyyaw=tuple(ticks[-1].true_pose_xyyaw),
                    mount_deg=self.mount_deg,station_id=self.station_id,
                    point_index=int(control.rf_point_index))
                if self.rf_backend is not None:
                    raw=self.rf_backend.generate(request)
                    if not math.isclose(raw.request.t_s,request.t_s,abs_tol=1e-10):
                        raise ValueError("RF_BACKEND_TIMESTAMP_MISMATCH")
                    if raw.request!=request:
                        raise ValueError("RF_BACKEND_POSE_OR_POINT_MISMATCH")
                    observed,oracle=self.receiver.receive(raw)
                    self.native_channel_evidence.append(raw)
                    self.rf_oracle.append(oracle)
                    self.rf_measured.append(dict(packet_id=observed.packet_id,
                        point_index=request.point_index,station_id=request.station_id,
                        t_s=observed.t_s,range_m=observed.range_m,
                        s=observed.s,detected=observed.detected,
                        P1=observed.power[0],P2=observed.power[1],
                        first_path_tap=observed.selected_tap,
                        estimate_yaw_pre_rf_rad=float(self.ekf.estimate[2])))
                    self.ekf.apply_rf(observed)
                elif self.ekf.rf_mode!="off":
                    raise RuntimeError("RF_REQUIRED_BUT_MISSING")
            self.ekf.finish_interval()
            if control.failed:
                self.status="CONTROL_TIMEOUT"
                break
            if control.done:
                self.status="CONTROL_COMPLETE_RF_COLLECTED" if self.ekf.rf_mode!="off" else "CONTROL_COMPLETE_RF_DISABLED"
                break
        if self.status=="RUNNING": self.status="CLOCK_BUDGET_EXCEEDED"
        return self.report()

    def report(self)->dict:
        trace=self.ekf.traces()
        return dict(status=self.status,station_id=self.station_id,mount_deg=self.mount_deg,
                    t_last_s=float(self.plant.t_s),n_ticks=len(self.control_log),
                    n_rf_packets=len(self.rf_measured),full_P6_trace=trace,
                    measured_rf_packets=list(self.rf_measured),
                    physical_oracle_eval_only=list(self.body_oracle),
                    rf_oracle_eval_only=list(self.rf_oracle),
                    native_channels_oracle_only=list(self.native_channel_evidence),
                    controller_log=list(self.control_log),
                    scientific_PASS=False,
                    limits=dict(cross_angle_covariance="NOT_IMPLEMENTED",
                                full_route="NOT_IMPLEMENTED",
                                Sionna_parity="NOT_RUN",
                                physical_calibration="NOT_MEASURED",
                                F01="OPEN",F02="OPEN"))
