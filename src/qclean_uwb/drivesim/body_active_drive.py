"""Causal drive / low-RF-confidence trigger / physical probe / resume bridge.

A research orchestration contract, not a validated RF covariance model or science PASS.
The *same* physical plant, gyro/wheel RNG streams and 6-state EKF are used before,
during and after a probe. Probe s is withheld until a supplied joint updater is called.
No oracle truth enters any quality or posterior updater.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Sequence

import numpy as np

from .body_probe_loop import BodyProbeLoop, ProbeLoopClock
from .body_probe_controller import ProbeBodyController, ProbeMotionConfig
from .body_pose_channel import RFPoseRequest

QualityFn = Callable[[Any,np.ndarray,np.ndarray],float]
SingleSFn = Callable[[Any,Any,float],dict]
ProbeJointFn = Callable[[Any,list[dict]],dict]


@dataclass(frozen=True)
class ActiveDrivePolicy:
    threshold_good: float=0.5
    cooldown_drive_steps: int=50
    max_probes: int=3
    probe_offsets_deg: tuple[float,...]=(0.,10.,20.)
    physics_dt_s:float=.02
    sensor_dt_s:float=.2
    max_probe_duration_s:float=90.

    def validate(self):
        if not 0 < self.threshold_good < 1:
            raise ValueError("threshold_good not in (0,1)")
        if self.cooldown_drive_steps<0 or self.max_probes<0:
            raise ValueError("negative cooldown or max probes")
        if len(self.probe_offsets_deg) not in (2,3) or self.probe_offsets_deg[0]!=0:
            raise ValueError("only 2 or 3 yaw samples (first angle zero)")
        c=ProbeLoopClock(self.sensor_dt_s,self.physics_dt_s,self.max_probe_duration_s)
        c.ratio()


class ContinuousRFQualityDrive:
    """Drive every command, inspect every observed RF, sometimes call a true body probe.

    Invariant: receiver RF H uses true physical pose **inside RF oracle only**;
    quality_fn and posterior_fn receive measured packets, x6 and P6 only.

    Expected EKF: ProbeEKF6 in range_only mode. The good-quality per-tick s update
    is injected by one callback and the 2/3-angle joint update by another.
    Callbacks must carry independent source/model IDs and their uncertainty
    assumptions; no built-in invented covariance/probability is substituted.
    """

    def __init__(self,*,plant,sensors,ekf,receiver,rf_backend,
                 quality_fn:QualityFn,
                 single_s_update:SingleSFn,
                 probe_joint_update:ProbeJointFn,
                 policy:ActiveDrivePolicy=ActiveDrivePolicy(),
                 probe_motion:ProbeMotionConfig|None=None,
                 station_id_start:int=0):
        policy.validate()
        if ekf.rf_mode!="range_only":
            raise ValueError("SINGLE_OR_BATCH_S_DOUBLE_UPDATE_RISK: EKF must be range_only")
        if ekf.lut is None:
            # For the real network, single_s_update requires a calibrated FP LUT.
            # Mock tests may use a toy site model but never call this scientific proof.
            pass
        if any(f is None for f in (quality_fn,single_s_update,probe_joint_update,receiver,rf_backend)):
            raise ValueError("quality and both s posterior callbacks, RF receiver/backend required")
        for f in (quality_fn,single_s_update,probe_joint_update):
            if not callable(f):
                raise TypeError("quality/s update contract is not callable")
        if not math.isclose(plant.t_s,sensors.t_s,abs_tol=1e-8) or not math.isclose(plant.t_s,ekf.last_t,abs_tol=1e-8):
            raise ValueError("drive plant, sensor and EKF clocks not aligned")
        if not math.isclose(ekf.cfg.mount_deg,rf_backend.mount_deg if hasattr(rf_backend,'mount_deg') else ekf.cfg.mount_deg,abs_tol=1e-8):
            raise ValueError("antenna mount mismatch")
        self.plant,self.sensors,self.ekf,self.receiver,self.backend=plant,sensors,ekf,receiver,rf_backend
        self.quality,self.good_update,self.joint_update=quality_fn,single_s_update,probe_joint_update
        self.policy=policy
        self.clock=ProbeLoopClock(policy.sensor_dt_s,policy.physics_dt_s,policy.max_probe_duration_s)
        self.motion=probe_motion or ProbeMotionConfig(offsets_deg=policy.probe_offsets_deg)
        if tuple(self.motion.offsets_deg)!=tuple(policy.probe_offsets_deg):
            raise ValueError("physical probe offsets differ from policy")
        self.stations=station_id_start
        self.driving_steps=0
        self.last_probe_step=-10**9
        self.events=[]
        self.normal_records=[]
        self.probe_reports=[]
        self._is_running=False

    def _physical_interval(self,v,w):
        return [self.plant.step(command_v_m_s=float(v),command_w_rad_s=float(w),
                                dt_s=self.policy.physics_dt_s)
                for _ in range(self.clock.ratio())]

    def drive_one(self,v:float,w:float)->dict:
        if self._is_running:
            raise RuntimeError("nested drive step not allowed")
        self._is_running=True
        try:
            ticks=self._physical_interval(v,w)
            measured=self.sensors.measure(ticks)
            self.ekf.start_interval(measured,phase="DRIVE",
                command_v_m_s=float(v),command_w_rad_s=float(w))
            # Physics-only, never to quality/update functions.
            request=RFPoseRequest(packet_id=f"drive_{self.driving_steps}_t{measured.t_s:.6f}",
                t_s=measured.t_s,true_pose_xyyaw=tuple(ticks[-1].true_pose_xyyaw),
                mount_deg=float(self.ekf.cfg.mount_deg),station_id=-1,point_index=0)
            chan=self.backend.generate(request)
            if chan.request != request:raise ValueError("RF request/body truth mismatch")
            packet,oracle=self.receiver.receive(chan)
            if packet.packet_id!=request.packet_id:raise ValueError("RF packet ID mismatch")
            # Apply only range now; s is NEVER assimilated before computing trust.
            self.ekf.apply_rf(packet)
            estimate_before_s=self.ekf.estimate.copy()
            covariance_before_s=self.ekf.covariance.copy()
            q=float(self.quality(packet,estimate_before_s,covariance_before_s))
            if not np.isfinite(q) or not 0<=q<=1:
                raise ValueError("quality must be probability-like in [0,1]")
            if packet.detected and np.isfinite(packet.s) and q>=self.policy.threshold_good:
                detail=self.good_update(self.ekf,packet,q)
                if not isinstance(detail,dict):
                    raise ValueError("single s updater must give source/status dict")
                if not detail.get("model_id"):
                    raise ValueError("unidentified single-s covariance/model")
            else:detail=dict(status="RF_s_WITHHELD",model_id="reliability")
            self.ekf.finish_interval()
            self.driving_steps+=1
            # Metrics can read truth later from the isolated RF request receipt only.
            entry=dict(drive_step=self.driving_steps,actual_elapsed_s=self.plant.t_s,
                       quality_good=q,range_packet=bool(packet.detected),
                       s_status=detail.get("status"),good_model_id=detail["model_id"],
                       x6_before_s=estimate_before_s,P6_before_s=covariance_before_s,
                       x6_after=self.ekf.estimate,P6_after=self.ekf.covariance,
                       rf_packet_id=packet.packet_id,
                       physical_oracle_packet_id=oracle["packet_id"])
            self.normal_records.append(entry)
            want=(packet.detected and np.isfinite(packet.s) and q<self.policy.threshold_good)
            can=(self.driving_steps-self.last_probe_step>=self.policy.cooldown_drive_steps
                 and len(self.probe_reports)<self.policy.max_probes)
            if want and can:
                self.last_probe_step=self.driving_steps
                self._execute_probe(trigger=entry)
                entry["probe_trigger"]=True
            else:
                entry["probe_trigger"]=False
                if want and not can:
                    self.events.append(dict(kind="TRIGGER_SUPPRESSED_BY_BUDGET",
                                            step=self.driving_steps,q=q))
            return entry
        finally:self._is_running=False

    def _execute_probe(self,*,trigger):
        # The previously observed moving RF packet is NOT included in site packet.
        # Actual braking and settling inside BodyProbeLoop, without fake zero-latency.
        ref_est=float(self.ekf.estimate[2])
        controller=ProbeBodyController(ref_est,self.motion)
        current_station=self.stations
        self.stations+=1
        probe=BodyProbeLoop(plant=self.plant,sensors=self.sensors,
            ekf=self.ekf,controller=controller,station_id=current_station,
            mount_deg=float(self.ekf.cfg.mount_deg),receiver=self.receiver,
            rf_backend=self.backend,clock=self.clock)
        old_n=len(self.ekf.records)
        report=probe.run()
        pkt=report["measured_rf_packets"]
        station_event=dict(kind="PROBE_EVENT",trigger_drive_step=trigger["drive_step"],
                           original_trigger_packet=trigger["rf_packet_id"],
                           station_id=current_station,physical_clock_after_s=report["t_last_s"],
                           mode="FULL_PHYSICAL_BODY_MOCK_OR_NATIVE_BACKEND",
                           probe_status=report["status"],n_points=len(pkt),
                           old_ekf_record_count=old_n,
                           new_ekf_record_count=len(self.ekf.records),
                           joint_result=None)
        if report["status"]=="CONTROL_COMPLETE_RF_COLLECTED" and len(pkt)==len(self.motion.offsets_deg):
            assert all(p["packet_id"]!=trigger["rf_packet_id"] for p in pkt)
            # The supplied posterior module must handle cross-time correlations.
            # Do not mistake these packets for same-instant iid updates.
            r=self.joint_update(self.ekf,list(pkt))
            if not isinstance(r,dict) or not r.get("covariance_model_id"):
                raise ValueError("missing site/point posterior covariance model receipt")
            if r.get("scientific_PASS",False):
                raise ValueError("joint model cannot self-declare scientific PASS")
            P=self.ekf.covariance
            if not np.isfinite(P).all() or np.linalg.eigvalsh(P).min() < -1e-9:
                raise FloatingPointError("joint batch update damaged 6x6 covariance")
            # Synchronize most recent recorded posterior with the updated filter.
            # Otherwise output trace would hide the carried-forward correction.
            if self.ekf.pending is not None:
                raise RuntimeError("probe posterior must run after finish_interval")
            last=self.ekf.records[-1]
            last["x_after_RF"]=self.ekf.estimate.copy()
            last["P_after_RF"]=P.copy()
            last["site_joint_model_id"]=r["covariance_model_id"]
            station_event["joint_result"]=r
        else:
            station_event["joint_result"]={"status":"NO_VALID_PROBE_PACKET_BATCH",
                                          "covariance_model_id":"NO_UPDATE"}
        self.probe_reports.append(report)
        self.events.append(station_event)

    def run(self,commands:Sequence[tuple[float,float]])->dict:
        for v,w in commands:
            self.drive_one(v,w)
        return dict(n_drive_steps=self.driving_steps,
                    n_triggered_probes=len(self.probe_reports),
                    elapsed_s=float(self.plant.t_s),events=self.events,
                    normal_records=self.normal_records,
                    probe_reports=self.probe_reports,
                    trace=self.ekf.traces(),scientific_PASS=False,
                    limitations=dict(first_cluster_receiver="EXTERNAL_CONTRACT",
                        posterior="SUPPLIED_CALLBACK_UNCALIBRATED_UNLESS_INDEPENDENTLY_CHECKED",
                        full_route_physical_motion="BODY_PLANT_ASSUMPTIONS",
                        native_RF="REAL_ONLY_IF_NATIVE_PROVIDER_NOT_MOCK",
                        cross_geometry="NOT_VALIDATED",F01="OPEN",F02="OPEN"))
