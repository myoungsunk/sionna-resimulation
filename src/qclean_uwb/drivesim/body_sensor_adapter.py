"""Physical wheel-shaft / true yaw to sensor-v2 compatible measured inputs.

Plant geometry and ground slip are NEVER injected a second time. Truth/oracle
is returned separately from estimator inputs.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from .body_dynamics import BodyTick, WheelGeometry
from .sensors import DRIFT_LEVELS

NAMESPACE = 2201008

@dataclass(frozen=True)
class RunRealization:
    gyro_bias_rad_s: float
    gyro_scale: float
    wheel_asymmetry: float
    wheelbase_error: float
    common_scale: float = 0.
    def geometry(self, radius_m=0.033, wheelbase_m=0.287):
        return WheelGeometry(radius_m,wheelbase_m,self.common_scale,self.wheel_asymmetry,self.wheelbase_error)

def draw_sensor_v2_realization(*,level:int,seed:int,common_scale:float=0.):
    if level not in range(len(DRIFT_LEVELS)) or not math.isfinite(common_scale):
        raise ValueError("bad drift level/scale")
    signs=np.random.default_rng([NAMESPACE,int(seed),1]).choice([-1.,1.],4)
    d=DRIFT_LEVELS[level]
    return RunRealization(signs[0]*math.radians(d.gyro_bias_dps),signs[1]*d.gyro_sf,
                          signs[2]*d.wheel_ratio,signs[3]*d.wheelbase_err,common_scale)

@dataclass(frozen=True)
class SensorAdapterConfig:
    gyro_N_rad_sqrt_s: float=math.radians(.015)
    bias_rw_rad_s_sqrt_s: float=0.
    k_distance_m: float=2e-5
    k_yaw_rad: float=1e-4
    k_yaw_distance_rad2_m: float=1e-5

def sensor_v2_from_physics(ticks:list[BodyTick],sample_times_s:list[float], *,
    geometry:WheelGeometry,realization:RunRealization,
    noise:SensorAdapterConfig=SensorAdapterConfig(), seed:int=0,
    pose0:tuple[float,float,float]=(0.,0.,0.)):
    """Aggregate *aligned* physics ticks into measured encoder/gyro increments.
    Returns (inputs, evaluation_only). sample_times include t=0.
    """
    if geometry!=realization.geometry(geometry.nominal_radius_m,geometry.nominal_wheelbase_m):
        raise ValueError("GEOMETRY_REALIZATION_MISMATCH")
    t=np.asarray(sample_times_s,float)
    if len(t)<2 or not np.isfinite(t).all() or t[0]!=0 or np.any(np.diff(t)<=0):
        raise ValueError("invalid sensor timestamps")
    if not ticks or any(q.dt_s<=0 for q in ticks):
        raise ValueError("invalid physics trace")
    expected=0.
    for q in ticks:
        expected+=q.dt_s
        if not math.isclose(q.t_s,expected,abs_tol=1e-8):
            raise ValueError("physics time discontinuity")
    if not math.isclose(t[-1],ticks[-1].t_s,abs_tol=1e-8):
        raise ValueError("unmatched final sampling time")
    idx=0
    L=[]; R=[]; Y=[]; F=[]; P=[]; SL=[]
    for ts in t[1:]:
        start=idx
        while idx<len(ticks) and ticks[idx].t_s<ts-1e-8:
            idx+=1
        if idx>=len(ticks) or not math.isclose(ticks[idx].t_s,ts,abs_tol=1e-8):
            raise ValueError("sampling endpoint not aligned to physics tick")
        group=ticks[start:idx+1]; idx+=1
        L.append(sum(q.motor_delta_left_rad for q in group))
        R.append(sum(q.motor_delta_right_rad for q in group))
        Y.append(sum(q.true_delta_yaw_rad for q in group))
        F.append(sum(q.true_body_forward_m for q in group))
        P.append(group[-1].true_pose_xyyaw)
        SL.append(any(q.slip_episode_active or q.slip_left!=0 or q.slip_right!=0 or q.icr_offset_m!=0 for q in group))
    n=len(L); dt=np.diff(t); F=np.array(F); Y=np.array(Y)
    fields=(noise.gyro_N_rad_sqrt_s,noise.bias_rw_rad_s_sqrt_s,noise.k_distance_m,noise.k_yaw_rad,noise.k_yaw_distance_rad2_m)
    if not all(math.isfinite(v) and v>=0 for v in fields):
        raise ValueError("invalid sensor noise")
    qd=noise.k_distance_m*np.abs(F)
    qt=noise.k_yaw_rad*np.abs(Y)+noise.k_yaw_distance_rad2_m*np.abs(F)
    rngw=np.random.default_rng([NAMESPACE,int(seed),2])
    nd=rngw.standard_normal((n,2))*np.sqrt(np.column_stack([qd,qt]))
    b=geometry.nominal_wheelbase_m; r=geometry.nominal_radius_m
    sl=r*np.array(L)+nd[:,0]-b*nd[:,1]/2
    sr=r*np.array(R)+nd[:,0]+b*nd[:,1]/2
    bias=np.empty(n+1); bias[0]=realization.gyro_bias_rad_s
    rngb=np.random.default_rng([NAMESPACE,int(seed),4])
    for i in range(n): bias[i+1]=bias[i]+rngb.standard_normal()*noise.bias_rw_rad_s_sqrt_s*math.sqrt(dt[i])
    rngg=np.random.default_rng([NAMESPACE,int(seed),3])
    dg=(1+realization.gyro_scale)*Y+bias[:-1]*dt+rngg.standard_normal(n)*noise.gyro_N_rad_sqrt_s*np.sqrt(dt)
    inputs=dict(t_s=t,dt_s=np.r_[0.,dt],ds_odom=np.r_[0.,(sl+sr)/2],
                dtheta_odom=np.r_[0.,(sr-sl)/b],dtheta_gyro=np.r_[0.,dg],
                encoder_angle_rad=np.column_stack([np.r_[0.,sl/r],np.r_[0.,sr/r]]),
                wheel_nominal_increment_m=np.column_stack([np.r_[0.,sl],np.r_[0.,sr]]),
                wheel_base_nominal=b)
    evaluation_only=dict(true_pose_xyyaw=np.vstack([np.asarray(pose0),np.asarray(P)]),
        true_body_yaw_increment=np.r_[0.,Y],
        true_motor_angles_increment=np.column_stack([np.r_[0.,L],np.r_[0.,R]]),
        slip_episode_mask=np.r_[False,SL],true_bias_rad_s=bias,true_parameters=realization)
    return inputs,evaluation_only
