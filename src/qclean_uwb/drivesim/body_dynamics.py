"""Uncalibrated differential-drive physical truth plant for body-yaw RF probes.

Purely commanded wheel/motor/contact dynamics; never reads a filter estimate or an RF
oracle. No MC campaign or RF channel is generated here. Units: SI, yaw unwrapped.
The slip model is a *scenario model*, not a validated TurtleBot3 tire law.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

PHYSICAL_SLIP_NAMESPACE = 2201016  # distinct from archived sensor-v2's namespace 2201008


@dataclass(frozen=True)
class WheelGeometry:
    """Match archived sensor-v2: r_true=r_nom/m, b_true=b_nom/(1+e_b)."""

    nominal_radius_m: float = 0.033
    nominal_wheelbase_m: float = 0.287
    common_scale: float = 0.0
    wheel_asymmetry: float = 0.0
    wheelbase_error: float = 0.0

    def actual(self) -> tuple[float, float, float]:
        vals = (self.nominal_radius_m, self.nominal_wheelbase_m,
                self.common_scale, self.wheel_asymmetry, self.wheelbase_error)
        if not all(math.isfinite(v) for v in vals):
            raise ValueError("nonfinite geometry")
        m_l = (1 + self.common_scale) * (1 - self.wheel_asymmetry / 2)
        m_r = (1 + self.common_scale) * (1 + self.wheel_asymmetry / 2)
        if min(self.nominal_radius_m, self.nominal_wheelbase_m, m_l, m_r,
               1 + self.wheelbase_error) <= 0:
            raise ValueError("invalid wheel geometry")
        return (self.nominal_radius_m / m_l, self.nominal_radius_m / m_r,
                self.nominal_wheelbase_m / (1 + self.wheelbase_error))


@dataclass(frozen=True)
class DriveDynamicsConfig:
    """First-order wheel-speed tracking with hard velocity/acceleration limits.

    Defaults except nominal wheel geometry are *assumed*, not motor datasheet fits.
    """

    motor_time_constant_s: float = 0.10
    max_wheel_accel_rad_s2: float = 8.0
    max_wheel_speed_rad_s: float = 8.0
    max_step_s: float = 0.02

    def validate(self) -> None:
        values = (self.motor_time_constant_s, self.max_wheel_accel_rad_s2,
                  self.max_wheel_speed_rad_s, self.max_step_s)
        if not all(math.isfinite(v) for v in values) or self.motor_time_constant_s < 0 or min(values[1:]) <= 0:
            raise ValueError("invalid dynamics configuration")


@dataclass(frozen=True)
class GroundSlipConfig:
    """Coherent ground-contact episodes; ratios are signed effective speed losses.

    This is deliberately separate from archived sensor-v2's encoder *error* event.
    Nonzero parameters must be reported as hypotheses until physically calibrated.
    """

    baseline_left: float = 0.0
    baseline_right: float = 0.0
    baseline_icr_offset_m: float = 0.0
    event_rate_per_s: float = 0.0
    mean_event_duration_s: float = 0.15
    event_longitudinal_scale: float = 0.0
    event_icr_scale_m: float = 0.0
    ratio_min: float = -0.25
    ratio_max: float = 0.85
    activate_only_when_turning: bool = True

    def validate(self) -> None:
        vals = (self.baseline_left, self.baseline_right, self.baseline_icr_offset_m,
                self.event_rate_per_s, self.mean_event_duration_s,
                self.event_longitudinal_scale, self.event_icr_scale_m,
                self.ratio_min, self.ratio_max)
        if not all(math.isfinite(x) for x in vals):
            raise ValueError("nonfinite slip settings")
        if self.event_rate_per_s < 0 or self.mean_event_duration_s <= 0 or self.event_longitudinal_scale < 0 or self.event_icr_scale_m < 0:
            raise ValueError("invalid slip episode distribution")
        if not -1 < self.ratio_min <= min(self.baseline_left, self.baseline_right) <= max(self.baseline_left, self.baseline_right) <= self.ratio_max < 1:
            raise ValueError("invalid longitudinal slip limits")


@dataclass(frozen=True)
class BodyTick:
    """One interval of true motion. ORACLE values must never enter online estimator."""

    t_s: float
    dt_s: float
    commanded_v_m_s: float
    commanded_w_rad_s: float
    true_pose_xyyaw: tuple[float, float, float]
    true_body_vx_m_s: float
    true_body_vy_m_s: float
    true_body_w_rad_s: float
    true_body_forward_m: float
    true_body_lateral_m: float
    true_delta_yaw_rad: float
    wheel_rate_left_rad_s: float
    wheel_rate_right_rad_s: float
    motor_delta_left_rad: float
    motor_delta_right_rad: float
    slip_left: float
    slip_right: float
    icr_offset_m: float
    slip_event_started: bool
    slip_episode_active: bool


def exact_body_twist_step(x: float, y: float, yaw: float,
                          vx: float, vy: float, w: float, dt: float) -> tuple[float, float, float]:
    """Analytic SE(2) constant-body-twist increment (also supports lateral slip)."""
    if not all(math.isfinite(v) for v in (x, y, yaw, vx, vy, w, dt)) or dt <= 0:
        raise ValueError("invalid pose/twist/dt")
    a = w * dt
    if abs(a) < 1e-5:
        c = dt * (1 - a*a/6 + a**4/120)
        s = dt * (a/2 - a**3/24 + a**5/720)
    else:
        c = math.sin(a) / w
        s = 2 * math.sin(a/2)**2 / w
    dx_body = c * vx - s * vy
    dy_body = s * vx + c * vy
    co, si = math.cos(yaw), math.sin(yaw)
    return (x + co*dx_body - si*dy_body,
            y + si*dx_body + co*dy_body,
            yaw + a)


class DifferentialDriveBodyPlant:
    """Finite-response wheel plant; slip changes *true* body x/y/yaw.

    Instantiate with run-level physical geometry. No observation/filter values are
    used here. Seed controls only the *physical* slip stream, not IMU/encoder noise.
    """

    def __init__(self, *, geometry: WheelGeometry = WheelGeometry(),
                 drive: DriveDynamicsConfig = DriveDynamicsConfig(),
                 slip: GroundSlipConfig = GroundSlipConfig(),
                 pose0: tuple[float, float, float] = (0., 0., 0.), seed: int = 0):
        self.r_l, self.r_r, self.b_true = geometry.actual()
        drive.validate()
        slip.validate()
        if len(pose0) != 3 or not all(math.isfinite(v) for v in pose0):
            raise ValueError("invalid initial physical pose")
        self.geometry, self.drive, self.slip = geometry, drive, slip
        self.pose = tuple(float(v) for v in pose0)
        self.t_s = 0.0
        self.motor_l = self.motor_r = 0.0
        self.angle_l = self.angle_r = 0.0
        self._rng = np.random.default_rng([PHYSICAL_SLIP_NAMESPACE, int(seed)])
        self._event_remaining = 0.0
        self._event_l = self._event_r = self._event_icr = 0.0

    def _track_motor(self, current: float, target: float, dt: float) -> float:
        target = float(np.clip(target, -self.drive.max_wheel_speed_rad_s,
                               self.drive.max_wheel_speed_rad_s))
        error = target - current
        desired = error if self.drive.motor_time_constant_s == 0 else error*dt/self.drive.motor_time_constant_s
        delta = math.copysign(min(abs(desired), abs(error), self.drive.max_wheel_accel_rad_s2*dt), error)
        return current + delta

    def _ground_contact(self, dt: float, commanded_w: float) -> tuple[float, float, float, bool, bool]:
        started = False
        if self._event_remaining <= 0 and self.slip.event_rate_per_s > 0:
            turning = abs(commanded_w) > 1e-9 or abs(self.motor_r-self.motor_l) > 1e-9
            if (not self.slip.activate_only_when_turning or turning) and (
                self._rng.random() < -math.expm1(-self.slip.event_rate_per_s*dt)
            ):
                started = True
                self._event_remaining = max(dt, self._rng.exponential(self.slip.mean_event_duration_s))
                self._event_l, self._event_r = (
                    self._rng.standard_t(3)*self.slip.event_longitudinal_scale,
                    self._rng.standard_t(3)*self.slip.event_longitudinal_scale)
                self._event_icr = self._rng.standard_t(3)*self.slip.event_icr_scale_m
        active = self._event_remaining > 0
        slip_l = float(np.clip(self.slip.baseline_left+self._event_l, self.slip.ratio_min, self.slip.ratio_max))
        slip_r = float(np.clip(self.slip.baseline_right+self._event_r, self.slip.ratio_min, self.slip.ratio_max))
        icr = self.slip.baseline_icr_offset_m + self._event_icr
        if active:
            self._event_remaining = max(0.0, self._event_remaining-dt)
            if self._event_remaining == 0:
                self._event_l = self._event_r = self._event_icr = 0.0
        return slip_l, slip_r, icr, started, active

    def step(self, *, command_v_m_s: float, command_w_rad_s: float, dt_s: float) -> BodyTick:
        if not all(math.isfinite(x) for x in (command_v_m_s, command_w_rad_s, dt_s)) or not (0 < dt_s <= self.drive.max_step_s+1e-12):
            raise ValueError("nonfinite command or oversized integration interval")
        w_l_cmd = (command_v_m_s - self.geometry.nominal_wheelbase_m*command_w_rad_s/2)/self.geometry.nominal_radius_m
        w_r_cmd = (command_v_m_s + self.geometry.nominal_wheelbase_m*command_w_rad_s/2)/self.geometry.nominal_radius_m
        old_l, old_r = self.motor_l, self.motor_r
        new_l = self._track_motor(old_l, w_l_cmd, dt_s)
        new_r = self._track_motor(old_r, w_r_cmd, dt_s)
        # Piecewise-linear motor speed inside each integration interval.
        dphi_l = (old_l+new_l)*dt_s/2
        dphi_r = (old_r+new_r)*dt_s/2
        contact_l, contact_r, icr, event_started, active = self._ground_contact(dt_s, command_w_rad_s)
        u_l = (1-contact_l)*self.r_l*dphi_l/dt_s
        u_r = (1-contact_r)*self.r_r*dphi_r/dt_s
        vx = (u_l+u_r)/2
        w_body = (u_r-u_l)/self.b_true
        vy = -icr*w_body  # offset of instantaneous rotation center along body x
        self.pose = exact_body_twist_step(*self.pose, vx, vy, w_body, dt_s)
        self.motor_l, self.motor_r = new_l, new_r
        self.angle_l += dphi_l
        self.angle_r += dphi_r
        self.t_s += dt_s
        return BodyTick(t_s=self.t_s, dt_s=dt_s,
                        commanded_v_m_s=command_v_m_s, commanded_w_rad_s=command_w_rad_s,
                        true_pose_xyyaw=self.pose,
                        true_body_vx_m_s=vx, true_body_vy_m_s=vy,
                        true_body_w_rad_s=w_body,
                        true_body_forward_m=vx*dt_s, true_body_lateral_m=vy*dt_s,
                        true_delta_yaw_rad=w_body*dt_s,
                        wheel_rate_left_rad_s=new_l, wheel_rate_right_rad_s=new_r,
                        motor_delta_left_rad=dphi_l, motor_delta_right_rad=dphi_r,
                        slip_left=contact_l, slip_right=contact_r, icr_offset_m=icr,
                        slip_event_started=event_started, slip_episode_active=active)
