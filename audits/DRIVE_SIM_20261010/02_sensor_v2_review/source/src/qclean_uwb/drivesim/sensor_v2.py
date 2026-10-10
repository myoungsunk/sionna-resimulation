"""Versioned wheel/yaw sensor generator. Truth lives only in evaluation output."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import numpy as np
from .sensors import DRIFT_LEVELS

NAMESPACE = 2201008
STREAMS = dict(drift=1, wheel=2, gyro=3, bias=4, slip=5, initial=6, observation=7)
ERROR_TERMS = ('gyro_bias', 'gyro_sf', 'wheel_asymmetry', 'wheelbase',
               'common_scale', 'wheel_noise', 'gyro_noise', 'bias_rw', 'slip')
CONDITIONS = {'none': (), 'all': ERROR_TERMS}
CONDITIONS.update({s: (s,) for s in ERROR_TERMS})
CONDITIONS.update(bias_asymmetry=('gyro_bias', 'wheel_asymmetry'),
                  asymmetry_wheelbase=('wheel_asymmetry', 'wheelbase'),
                  noise_pair=('wheel_noise', 'gyro_noise'))

@dataclass(frozen=True)
class SensorV2Config:
    model_version: str = 'sensor-v2'
    level: int = 1
    condition: str = 'all'
    radius_nominal_m: float = .033
    wheelbase_nominal_m: float = .287
    common_scale: float = 0.0             # uncalibrated assumption; neutral default
    bias_rw_rad_s_sqrt_s: float = 0.0    # fixed residual bias is default
    gyro_N_rad_sqrt_s: float = math.radians(.015)
    k_distance_m: float = 2e-5
    k_yaw_rad: float = 1e-4
    k_yaw_distance_rad2_m: float = 1e-5
    slip_mode: str = 'time'             # time | legacy-event | off
    slip_rate_per_s: float = -math.log1p(-.01)/.2
    slip_probability_per_sample: float = .01
    slip_t3_scale_rad: float = math.radians(.5)

    def __post_init__(self):
        numeric = (self.radius_nominal_m, self.wheelbase_nominal_m, self.common_scale,
                   self.bias_rw_rad_s_sqrt_s, self.gyro_N_rad_sqrt_s,
                   self.k_distance_m, self.k_yaw_rad, self.k_yaw_distance_rad2_m,
                   self.slip_rate_per_s, self.slip_probability_per_sample,
                   self.slip_t3_scale_rad)
        if not all(math.isfinite(v) for v in numeric):
            raise ValueError('sensor-v2 configuration must be finite')
        if self.model_version != 'sensor-v2' or self.condition not in CONDITIONS:
            raise ValueError('unsupported model/condition')
        if self.level not in range(len(DRIFT_LEVELS)):
            raise ValueError('unknown sensitivity level')
        if self.slip_mode not in ('time', 'legacy-event', 'off'):
            raise ValueError('unsupported slip mode')
        if self.radius_nominal_m <= 0 or self.wheelbase_nominal_m <= 0 or self.common_scale <= -1:
            raise ValueError('invalid geometry')
        nonnegative = (self.bias_rw_rad_s_sqrt_s, self.gyro_N_rad_sqrt_s,
                       self.k_distance_m, self.k_yaw_rad, self.k_yaw_distance_rad2_m,
                       self.slip_rate_per_s, self.slip_t3_scale_rad)
        if min(nonnegative) < 0 or not 0 <= self.slip_probability_per_sample <= 1:
            raise ValueError('invalid noise/rate')

    def manifest(self):
        return dict(asdict(self), seed_namespace=NAMESPACE, streams=STREAMS,
                    levels=[asdict(x) for x in DRIFT_LEVELS],
                    units='m, s, rad; bias rad/s; gyro N rad/sqrt(s); bias RW rad/s/sqrt(s)',
                    gyro_definition='Var(delta_angle)=N^2 dt',
                    slip_std_rad=math.sqrt(3)*self.slip_t3_scale_rad,
                    level_interpretation='assumption-based sensitivity, not hardware performance')


def rng(seed, stream):
    return np.random.default_rng([NAMESPACE, int(seed), STREAMS[stream]])


def wrap(a):
    return (a + np.pi) % (2*np.pi) - np.pi


def integrate(ds, dtheta, pose0=(0., 0., 0.)):
    ds, dtheta = np.asarray(ds, float), np.asarray(dtheta, float)
    if ds.shape != dtheta.shape or ds.ndim != 1 or ds[0] != 0 or dtheta[0] != 0:
        raise ValueError('increments must be 1D and begin at zero')
    out = np.empty((len(ds), 3)); out[0] = pose0
    for k in range(1, len(ds)):
        p = out[k-1]; a = dtheta[k]
        out[k, :2] = p[:2] + ds[k]*np.sinc(a/(2*np.pi))*np.array([np.cos(p[2]+a/2), np.sin(p[2]+a/2)])
        out[k, 2] = p[2]+a
    return out


def motion_increments(t, pose, yaw_unwrapped=False, tolerance=1e-9, convention="se2"):
    if convention not in ("se2", "legacy-euler"): raise ValueError("unknown motion convention")
    t, pose = np.asarray(t, float), np.asarray(pose, float)
    if pose.shape != (len(t), 3) or len(t) < 2 or not np.all(np.diff(t) > 0) or not np.isfinite(pose).all():
        raise ValueError('invalid timestamps/poses')
    delta = np.diff(pose[:, 2])
    a = delta if yaw_unwrapped else wrap(delta)
    if np.any(np.abs(a) >= np.pi):
        raise ValueError('ambiguous turn >= pi per interval; resample path')
    mid = pose[:-1, 2]+(a/2 if convention == "se2" else 0.)
    dp = np.diff(pose[:, :2], axis=0)
    lateral = -dp[:, 0]*np.sin(mid)+dp[:, 1]*np.cos(mid)
    if np.max(np.abs(lateral)) > tolerance:
        raise ValueError('path does not follow constant-curvature nonholonomic intervals')
    signed = (dp[:, 0]*np.cos(mid)+dp[:, 1]*np.sin(mid))
    if convention == "se2": signed /= np.sinc(a/(2*np.pi))
    return np.r_[0., signed], np.r_[0., a]


def wheel_transform(b):
    return np.array([[.5, .5], [-1/b, 1/b]])


def wheel_covariance(q_distance, q_yaw, b):
    inv = np.linalg.inv(wheel_transform(b))
    return inv @ np.diag([q_distance, q_yaw]) @ inv.T


def generate(t, ds, dtheta, cfg, seed, parameters=None):
    """Inference inputs contain measurements only; actual drift/variance are evaluation-only.

    e_b convention: b_true=b_nom/(1+e_b). Radius convention: r_true=r_nom/m,
    m_L=(1+c)(1-eps/2), m_R=(1+c)(1+eps/2). Raw encoder angles are rad.
    """
    t, ds, dtheta = map(lambda x: np.asarray(x, float), (t, ds, dtheta))
    if any(x.ndim != 1 or not np.isfinite(x).all() for x in (t, ds, dtheta)):
        raise ValueError('sensor-v2 increments/time must be finite 1D arrays')
    if t.shape != ds.shape or ds.shape != dtheta.shape or len(t)<2 or not np.all(np.diff(t)>0) or ds[0]!=0 or dtheta[0]!=0:
        raise ValueError('invalid increments/time')
    enabled = CONDITIONS[cfg.condition]
    level = DRIFT_LEVELS[cfg.level]
    signs = rng(seed, 'drift').choice([-1., 1.], 4)
    p = dict(gyro_bias=signs[0]*math.radians(level.gyro_bias_dps), gyro_sf=signs[1]*level.gyro_sf,
             wheel_asymmetry=signs[2]*level.wheel_ratio, wheelbase=signs[3]*level.wheelbase_err,
             common_scale=cfg.common_scale)
    if parameters:
        if set(parameters)-set(p): raise ValueError('unknown generated parameter')
        p.update(parameters)
    p = {k: (v if k in enabled else 0.) for k,v in p.items()}
    if not all(np.isfinite(v) for v in p.values()):
        raise ValueError('generated sensor parameters must be finite')
    if 1+p['gyro_sf'] <= 0 or 1+p['wheelbase'] <= 0 or abs(p['wheel_asymmetry']) >= 2 or 1+p['common_scale'] <= 0:
        raise ValueError('invalid true geometry/scale')
    dt = np.r_[0., np.diff(t)]
    b = cfg.wheelbase_nominal_m/(1+p['wheelbase'])
    m = (1+p['common_scale'])*np.array([1-p['wheel_asymmetry']/2, 1+p['wheel_asymmetry']/2])
    wheel_true = np.column_stack([ds-b*dtheta/2, ds+b*dtheta/2])
    nominal_clean = wheel_true*m
    qd = cfg.k_distance_m*np.abs(ds) if 'wheel_noise' in enabled else np.zeros_like(ds)
    qt = cfg.k_yaw_rad*np.abs(dtheta)+cfg.k_yaw_distance_rad2_m*np.abs(ds) if 'wheel_noise' in enabled else np.zeros_like(ds)
    # Generate distance/yaw-independent noise, mapped back to correlated L/R increments.
    nd = rng(seed, 'wheel').standard_normal((len(t), 2))*np.sqrt(np.column_stack([qd, qt]))
    measured = nominal_clean + nd @ np.linalg.inv(wheel_transform(cfg.wheelbase_nominal_m)).T
    slip_rng = rng(seed, 'slip')
    eligible = (np.abs(ds)<1e-12)&(np.abs(dtheta)>1e-9)
    probability = -np.expm1(-cfg.slip_rate_per_s*dt) if cfg.slip_mode=='time' else np.full(len(t), cfg.slip_probability_per_sample)
    event = eligible & (slip_rng.random(len(t))<probability) & ('slip' in enabled) & (cfg.slip_mode!='off')
    slip = event*slip_rng.standard_t(3, len(t))*cfg.slip_t3_scale_rad
    measured += np.column_stack([-cfg.wheelbase_nominal_m*slip/2, cfg.wheelbase_nominal_m*slip/2])
    bias = np.full(len(t), p['gyro_bias'])
    if 'bias_rw' in enabled:
        bias += np.cumsum(rng(seed, 'bias').standard_normal(len(t))*cfg.bias_rw_rad_s_sqrt_s*np.sqrt(dt))
    ngvar = cfg.gyro_N_rad_sqrt_s**2*dt if 'gyro_noise' in enabled else np.zeros_like(dt)
    gyro = (1+p['gyro_sf'])*dtheta + np.r_[bias[0], bias[:-1]]*dt + rng(seed,'gyro').standard_normal(len(t))*np.sqrt(ngvar)
    odom = measured @ wheel_transform(cfg.wheelbase_nominal_m).T
    measured[0]=0; odom[0]=0; gyro[0]=0; event[0]=False; slip[0]=0
    inputs = dict(t_s=t.copy(), dt_s=dt, ds_odom=odom[:,0], dtheta_odom=odom[:,1], dtheta_gyro=gyro,
                  encoder_angle_rad=measured/cfg.radius_nominal_m, wheel_nominal_increment_m=measured,
                  wheel_base_nominal=cfg.wheelbase_nominal_m)
    evaluation = dict(true_increments=np.column_stack([ds,dtheta]), true_wheel_increment_m=wheel_true,
                      true_radius_m=cfg.radius_nominal_m/m, true_wheelbase_m=np.array(b),
                      true_parameters=np.array(list(p.values())), parameter_names=np.array(list(p)),
                      true_bias_rad_s=bias, slip_event=event, slip_yaw_rad=slip, slip_eligible=eligible,
                      generated_variance=np.column_stack([qd,ngvar,qt]),
                      true_wheel_Q=np.stack([np.stack([qd+cfg.wheelbase_nominal_m**2*qt/4, qd-cfg.wheelbase_nominal_m**2*qt/4],axis=-1),
                                             np.stack([qd-cfg.wheelbase_nominal_m**2*qt/4, qd+cfg.wheelbase_nominal_m**2*qt/4],axis=-1)],axis=-2))
    return inputs, evaluation
