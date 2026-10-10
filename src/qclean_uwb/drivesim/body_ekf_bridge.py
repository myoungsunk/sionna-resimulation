"""Frozen sensor-v2 EKF bridged into a causal probe-time event loop.

Six-state order: x,y,yaw,gyro_bias,gyro_scale,wheel_asymmetry.
The frozen filter_v2 transition and correlated wheel-gyro update are invoked
without replacing them by legacy filters. All covariance stages are preserved.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .filters import FilterConfig, wrap
from .filter_v2 import SensorV2Filter, transition, covariance_diagnostic
from .hs_lut import s_model
from .body_sensor_stream import MeasuredIncrement

RF_MODES = ("off", "range_only", "independent_scalar_diagnostic", "joint_sr_diagnostic")


@dataclass
class V2BodyFilterConfig(FilterConfig):
    """Adds original frozen v2 options absent from production legacy FilterConfig."""
    model_version: str = "sensor-v2"
    known_wheelbase_error: float = 0.0
    gyro_N_rad_sqrt_s: float = math.radians(0.015)
    use_range: bool = True
    use_s: bool = False
    kind: str = "ekf"
    s_mode: str = "direct"
    pos_process_std: float = 0.0


def _state_cov(f) -> tuple[np.ndarray, np.ndarray]:
    x, P = f.mean_cov()
    return x.copy(), P.copy()


def _validate_cov(P: np.ndarray, label: str, ref: float) -> None:
    report = covariance_diagnostic(P, ref)
    if not report["valid"]:
        raise FloatingPointError(f"{label}: {report}")


class ProbeEKF6:
    """Single causal EKF run. RF observations can only be applied once per sample.

    Data produced by the plant is never available inside this filter.
    This first bridge supports zero/one RF packet per estimator tick.
    Multi-angle site covariance requires a separate temporally correlated batch
    estimator, which is deliberately NOT approximated here.
    """

    def __init__(self, config: V2BodyFilterConfig, lut, x0, P0=None,
                 *, rf_mode: str = "range_only"):
        if rf_mode not in RF_MODES:
            raise ValueError("unknown RF update policy")
        if rf_mode in ("independent_scalar_diagnostic", "joint_sr_diagnostic") and lut is None:
            raise ValueError("RF s update requires an explicit LoS LUT")
        if config.model_version != "sensor-v2" or config.kind != "ekf" or config.pos_process_std != 0:
            raise ValueError("frozen sensor-v2 EKF only; no covariance slack")
        if config.use_range != (rf_mode != "off") or config.use_s != (
                rf_mode in ("independent_scalar_diagnostic", "joint_sr_diagnostic")):
            raise ValueError("RF policy and filter flags disagree")
        xx=np.asarray(x0,dtype=float)
        if xx.shape!=(6,) or not np.isfinite(xx).all():
            raise ValueError("invalid 6-state initial estimate")
        self.f=SensorV2Filter(config,lut,xx,P0)
        self.cfg=config; self.lut=lut; self.rf_mode=rf_mode
        self.last_t=0.
        self.pending=None
        self.records=[]
        self._initial_scale=float(np.linalg.norm(_state_cov(self.f)[1],ord=2))
        _validate_cov(self.f.comps[0].P,"initial",self._initial_scale)

    @property
    def estimate(self)->np.ndarray:
        return _state_cov(self.f)[0]

    @property
    def covariance(self)->np.ndarray:
        return _state_cov(self.f)[1]

    def start_interval(self,m: MeasuredIncrement, *, phase: str, probe_id:int=-1,
                       command_v_m_s:float=0.,command_w_rad_s:float=0.) -> dict:
        if self.pending is not None:
            raise RuntimeError("finish the prior tick before another")
        if not math.isclose(m.t_s-self.last_t,m.dt_s,rel_tol=0,abs_tol=1e-8) or m.dt_s<=0:
            raise ValueError("sensor time gap")
        x_prev,P_prev=_state_cov(self.f)
        b=self.cfg.wheel_base/(1+self.cfg.known_wheelbase_error)
        x_pred,F,G=transition(x_prev,m.ds_odom,m.dtheta_gyro,m.dt_s,b)
        Q=np.diag([self.cfg.k_s*abs(m.ds_odom),
                   self.cfg.gyro_N_rad_sqrt_s**2*m.dt_s,
                   self.cfg.k_theta*abs(m.dtheta_odom)+self.cfg.k_stheta*abs(m.ds_odom)])
        P_pred=F@P_prev@F.T+G@Q@G.T
        scale=max(self._initial_scale,float(np.linalg.norm(P_pred,ord=2)))
        _validate_cov(P_pred,"before_odom",scale)
        r=self.f.step(m.ds_odom,m.dtheta_gyro,m.dtheta_odom,m.dt_s)
        if not np.allclose(r["F"],F,rtol=1e-11,atol=1e-11) or not np.allclose(r["Q"],Q,rtol=1e-11,atol=1e-11):
            raise RuntimeError("frozen v2 transition parity mismatch")
        x_odom,P_odom=_state_cov(self.f)
        _validate_cov(P_odom,"after_odom",scale)
        self._initial_scale=scale
        self.pending=dict(
            t_s=float(m.t_s),dt_s=float(m.dt_s),phase=str(phase),probe_id=int(probe_id),
            commanded_v_m_s=float(command_v_m_s),commanded_w_rad_s=float(command_w_rad_s),
            ds_odom=float(m.ds_odom),dtheta_odom=float(m.dtheta_odom),
            dtheta_gyro=float(m.dtheta_gyro),
            encoder_left_rad=float(m.encoder_left_rad),encoder_right_rad=float(m.encoder_right_rad),
            x_pred_before_odom=x_pred,P_pred_before_odom=P_pred,
            x_after_odom=x_odom,P_after_odom=P_odom,
            F=F,G=G,Q_input=Q,
            odom_H=r["H"].copy(),odom_C=r["C"].copy(),
            odom_innovation=float(r["innovation"]),odom_R=float(r["R"]),odom_S=float(r["S"]),
            odom_status=str(r["status"]),
            range_H=np.full(6,np.nan),s_H=np.full(6,np.nan),
            range_innovation=np.nan,range_R=np.nan,range_S=np.nan,range_status="missing",
            s_innovation=np.nan,s_R=np.nan,s_S=np.nan,s_status="missing",
            rf_packet_id=None,rf_detected=False,rf_selected_tap=-1,rf_s=np.nan,
            rf_range_m=np.nan,rf_realized_snr_db=np.nan,
            covariance_model_id="NOT_ESTIMATED")
        self.last_t=float(m.t_s)
        return self.pending

    def _model_range(self) -> tuple[float,np.ndarray]:
        x=self.estimate
        a=self.cfg.anchor_xyz
        delta=np.array([x[0]-a[0],x[1]-a[1],self.cfg.robot_z-a[2]])
        distance=float(np.linalg.norm(delta))
        if distance<=1e-12:
            raise ValueError("undefined range geometry")
        H=np.zeros(6);H[:2]=delta[:2]/distance
        return distance+self.cfg.range_offset,H

    def _model_s(self) -> tuple[float,np.ndarray]:
        x=self.estimate
        if np.linalg.norm(x[:2]-np.asarray(self.cfg.anchor_xyz[:2]))<=1e-6:
            raise ValueError("undefined RF azimuth geometry")
        value,jac=s_model(self.lut,self.cfg.anchor_xyz,self.cfg.robot_z,
                          float(x[0]),float(x[1]),float(x[2]),self.cfg.mount_deg,with_jac=True)
        H=np.zeros(6);H[:3]=jac
        return float(value),H

    def apply_rf(self, packet) -> None:
        """Consume measured {time, s, range, power, detected}; no oracle attributes."""
        rec=self.pending
        if rec is None:
            raise RuntimeError("RF must follow motion propagation")
        if rec["rf_packet_id"] is not None:
            raise RuntimeError("duplicate RF update in one interval")
        if not math.isclose(float(packet.t_s),rec["t_s"],abs_tol=1e-8):
            raise ValueError("RF packet time does not match estimator state time")
        rec["rf_packet_id"]=str(packet.packet_id)
        rec["rf_detected"]=bool(packet.detected)
        rec["rf_selected_tap"]=int(packet.selected_tap)
        rec["rf_s"]=float(packet.s)
        rec["rf_range_m"]=float(packet.range_m)
        rec["rf_realized_snr_db"]=float(packet.realized_snr_db)
        if not packet.detected or self.rf_mode=="off":
            return
        if self.rf_mode=="joint_sr_diagnostic":
            if packet.noise_cov_sr is None or not packet.covariance_model_id:
                raise ValueError("joint s/r update requires a sourced covariance model")
            self._joint_update(packet)
            return
        if self.cfg.use_range and np.isfinite(packet.range_m):
            _,H=self._model_range()
            y,R,S,status=self.f.range_record(float(packet.range_m))
            rec.update(range_H=H,range_innovation=float(y),range_R=float(R),
                       range_S=float(S),range_status=str(status))
            _validate_cov(self.covariance,"after_range",self._initial_scale)
            self.record_stage_range()
        if self.cfg.use_s and np.isfinite(packet.s):
            _,H=self._model_s()
            y,R,S,status=self.f.s_record(float(packet.s),packet.power)
            rec.update(s_H=H,s_innovation=float(y),s_R=float(R),
                       s_S=float(S),s_status=str(status))
            _validate_cov(self.covariance,"after_s",self._initial_scale)

    def _joint_update(self,packet) -> None:
        """Within-packet r/s cross covariance only; inter-angle correlations unresolved."""
        rec=self.pending
        if not np.isfinite(packet.range_m) or not np.isfinite(packet.s):
            rec["range_status"]=rec["s_status"]="missing"
            return
        cov=np.asarray(packet.noise_cov_sr,dtype=float)
        if cov.shape!=(2,2) or not np.isfinite(cov).all() or not np.allclose(cov,cov.T,rtol=0,atol=1e-12):
            raise ValueError("invalid Sigma_sr")
        if np.linalg.eigvalsh(cov).min()<=0:
            raise ValueError("Sigma_sr must be positive definite")
        hr,Hr=self._model_range()
        hs,Hs=self._model_s()
        x,P=_state_cov(self.f);H=np.stack((Hr,Hs))
        y=np.array([packet.range_m-hr,packet.s-hs])
        S=H@P@H.T+cov
        sign, logdet=np.linalg.slogdet(S)
        if sign<=0 or not np.isfinite(logdet):
            raise FloatingPointError("joint RF S invalid")
        nis=float(y@np.linalg.solve(S,y))
        status="rejected" if nis>9.210340371976184 else "applied"
        if status=="applied":
            K=np.linalg.solve(S,H@P).T
            c=self.f.comps[0]
            c.x=x+K@y;c.x[2]=wrap(c.x[2])
            M=np.eye(6)-K@H
            c.P=M@P@M.T+K@cov@K.T
            c.P=(c.P+c.P.T)/2
            _validate_cov(c.P,"after_joint_rf",self._initial_scale)
        rec.update(range_H=Hr,s_H=Hs,range_innovation=float(y[0]),
                   s_innovation=float(y[1]),range_R=float(cov[0,0]),
                   s_R=float(cov[1,1]),range_S=float(S[0,0]),
                   s_S=float(S[1,1]),range_status=status,s_status=status,
                   covariance_model_id=str(packet.covariance_model_id),
                   joint_sr_nis=nis,joint_sr_cross_R=float(cov[0,1]))

    def finish_interval(self)->dict:
        if self.pending is None: raise RuntimeError("no pending EKF interval")
        rec=self.pending
        x,P=_state_cov(self.f)
        # For no packet and rejected RF, all posterior stages remain after-odom.
        rec["x_after_range"]=rec.get("x_after_range",rec["x_after_odom"].copy())
        rec["P_after_range"]=rec.get("P_after_range",rec["P_after_odom"].copy())
        rec["x_before_RF"]=rec["x_after_range"].copy()
        rec["P_before_RF"]=rec["P_after_range"].copy()
        rec["x_after_RF"]=x.copy();rec["P_after_RF"]=P.copy()
        self.records.append(rec)
        self.pending=None
        return rec

    def record_stage_range(self) -> None:
        """Optional stage snapshot: invoke immediately after range and before s."""
        if self.pending is None: raise RuntimeError("no active interval")
        x,P=_state_cov(self.f)
        self.pending["x_after_range"]=x
        self.pending["P_after_range"]=P

    def traces(self)->dict:
        """Stack full-P6 stages; only records finalized sensor intervals."""
        if self.pending is not None:raise RuntimeError("finalize pending estimator tick")
        if not self.records:return {}
        out={}
        keys=(
            "x_pred_before_odom","P_pred_before_odom","x_after_odom","P_after_odom",
            "x_after_range","P_after_range","x_before_RF","P_before_RF","x_after_RF","P_after_RF",
            "F","G","Q_input","odom_H","odom_C","range_H","s_H",
            "t_s","dt_s","ds_odom","dtheta_odom","dtheta_gyro","encoder_left_rad","encoder_right_rad",
            "odom_innovation","odom_R","odom_S","odom_status",
            "range_innovation","range_R","range_S","range_status",
            "s_innovation","s_R","s_S","s_status",
            "rf_detected","rf_selected_tap","rf_s","rf_range_m","rf_realized_snr_db",
            "phase","probe_id","commanded_v_m_s","commanded_w_rad_s")
        for key in keys:out[key]=np.asarray([r[key] for r in self.records])
        return out
