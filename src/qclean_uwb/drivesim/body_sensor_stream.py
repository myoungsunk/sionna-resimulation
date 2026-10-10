"""Streaming gyro/encoder adapter for the physical body plant.

Generates independent sensor measurements *from wheel shaft angles and true yaw*.
Unlike frozen sensor_v2.generate(), physical slip/geometry is NOT re-injected.
The RNG streams retain state across sensor intervals. Truth stays outside inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .body_dynamics import BodyTick, WheelGeometry
from .body_sensor_adapter import RunRealization, SensorAdapterConfig, NAMESPACE


@dataclass(frozen=True)
class MeasuredIncrement:
    t_s: float
    dt_s: float
    ds_odom: float
    dtheta_odom: float
    dtheta_gyro: float
    encoder_left_rad: float
    encoder_right_rad: float
    wheel_nominal_left_m: float
    wheel_nominal_right_m: float

    def estimator_only(self) -> dict:
        return dict(t_s=self.t_s, dt_s=self.dt_s, ds_odom=self.ds_odom,
                    dtheta_odom=self.dtheta_odom, dtheta_gyro=self.dtheta_gyro,
                    encoder_left_rad=self.encoder_left_rad,
                    encoder_right_rad=self.encoder_right_rad)


class BodySensorStream:
    """Continuous RNG across 5 Hz windows; input truth is physics-only.

    A zero-time dummy draw mirrors frozen sensor-v2's sample-0 RNG consumption.
    Any physical slip is expressed in body motion, not a second encoder slip event.
    """

    def __init__(self, geometry: WheelGeometry, realization: RunRealization, *,
                 noise: SensorAdapterConfig = SensorAdapterConfig(), seed: int = 0):
        expected = realization.geometry(geometry.nominal_radius_m,
                                        geometry.nominal_wheelbase_m)
        if geometry != expected:
            raise ValueError("GEOMETRY_REALIZATION_MISMATCH")
        vals = (noise.gyro_N_rad_sqrt_s, noise.bias_rw_rad_s_sqrt_s,
                noise.k_distance_m, noise.k_yaw_rad, noise.k_yaw_distance_rad2_m)
        if not all(math.isfinite(v) and v >= 0 for v in vals):
            raise ValueError("invalid stream noise configuration")
        self.geometry, self.realization, self.noise = geometry, realization, noise
        self._wheel = np.random.default_rng([NAMESPACE, int(seed), 2])
        self._gyro = np.random.default_rng([NAMESPACE, int(seed), 3])
        self._bias_rng = np.random.default_rng([NAMESPACE, int(seed), 4])
        # Frozen sensor-v2 draws its first row at dt=0.
        self._wheel.standard_normal(2)
        self._gyro.standard_normal()
        self._bias_rng.standard_normal()
        self.bias_rad_s = realization.gyro_bias_rad_s
        self.t_s = 0.0

    def measure(self, ticks: list[BodyTick]) -> MeasuredIncrement:
        if not ticks:
            raise ValueError("empty physical interval")
        start = self.t_s
        elapsed = 0.0
        for tick in ticks:
            if not math.isfinite(tick.dt_s) or tick.dt_s <= 0:
                raise ValueError("invalid physical tick")
            elapsed += tick.dt_s
            if not math.isclose(tick.t_s, start + elapsed, abs_tol=1e-8):
                raise ValueError("PHYSICAL_TICK_GAP_OR_OVERLAP")
        if not math.isfinite(elapsed) or elapsed <= 0:
            raise ValueError("invalid sensor interval")
        dphi_l = sum(q.motor_delta_left_rad for q in ticks)
        dphi_r = sum(q.motor_delta_right_rad for q in ticks)
        dth_true = sum(q.true_delta_yaw_rad for q in ticks)
        ds_true = sum(q.true_body_forward_m for q in ticks)
        # Reuse sensor-v2 aggregate d/yaw variances, but source left/right increments
        # come from REAL shaft rotation. Do not apply diameter/wheelbase/slip twice.
        qd = self.noise.k_distance_m * abs(ds_true)
        qt = self.noise.k_yaw_rad * abs(dth_true) + self.noise.k_yaw_distance_rad2_m * abs(ds_true)
        nd, nt = self._wheel.standard_normal(2) * np.sqrt([qd, qt])
        b = self.geometry.nominal_wheelbase_m
        r = self.geometry.nominal_radius_m
        ml = r * dphi_l + nd - b * nt / 2
        mr = r * dphi_r + nd + b * nt / 2
        gyro = ((1.0 + self.realization.gyro_scale) * dth_true
                + self.bias_rad_s * elapsed
                + self._gyro.standard_normal() * self.noise.gyro_N_rad_sqrt_s * math.sqrt(elapsed))
        self.bias_rad_s += self._bias_rng.standard_normal() * self.noise.bias_rw_rad_s_sqrt_s * math.sqrt(elapsed)
        self.t_s = float(ticks[-1].t_s)
        return MeasuredIncrement(t_s=self.t_s, dt_s=elapsed,
                                 ds_odom=(ml + mr) / 2,
                                 dtheta_odom=(mr - ml) / b,
                                 dtheta_gyro=gyro,
                                 encoder_left_rad=ml / r, encoder_right_rad=mr / r,
                                 wheel_nominal_left_m=ml, wheel_nominal_right_m=mr)
