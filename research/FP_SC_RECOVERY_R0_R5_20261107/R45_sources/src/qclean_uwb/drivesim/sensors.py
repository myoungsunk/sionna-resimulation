"""S5 sensor generators: gyro, wheel odometry (TB3 geometry) and the UWB range randomisation.  All parameters are placeholders.

The three sensors are generated independently from the *true* motion increments of the scripted trajectory:
per 5 Hz sample the true path length ``ds`` and the true heading increment ``dtheta`` (radians).

* Gyro:      dtheta_g = (1 + SF) * dtheta + b * dt + ARW * sqrt(dt) * N(0,1)          (wheel slip does not affect it)
* Odometry:  wheel increments sL, sR from (ds, dtheta) and wheelbase b_true; wheel diameters differ by ``E_d``
             (eta_R - eta_L = eps_d), the controller assumes wheelbase b_true * (1 + E_b);
             ds_o = (sL' + sR')/2 + N(0, k_s |ds|),  dtheta_o = (sR' - sL')/b_est + N(0, k_t |dtheta| + k_st |ds|) + slip
             (Thrun-style non-systematic noise; slip = heavy-tailed event, probability p per rotating sample, t(3) * scale)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

WHEEL_BASE_M = 0.287          # TurtleBot3 Waffle Pi (turtlebot3 package value; verify on the real robot)
WHEEL_RADIUS_M = 0.033


@dataclass(frozen=True)
class DriftLevel:
    name: str
    gyro_bias_dps: float
    gyro_sf: float            # |scale-factor error|, fraction
    wheel_ratio: float        # |E_d|, fraction (diameter ratio error)
    wheelbase_err: float      # |E_b|, fraction


DRIFT_LEVELS = (
    DriftLevel("low", 0.01, 0.005, 0.002, 0.005),
    DriftLevel("mid", 0.05, 0.010, 0.005, 0.0075),
    DriftLevel("high", 0.20, 0.015, 0.010, 0.010),
)


@dataclass(frozen=True)
class SensorNoise:
    arw_deg_sqrt_s: float = 0.015          # ICM-20648 datasheet rate noise 0.015 dps/sqrt(Hz)
    k_s_m: float = 2e-5                    # var(ds)   = k_s |ds|            [m^2 per m]
    k_theta_rad: float = 1e-4              # var(dth)  = k_theta |dth| + k_stheta |ds|  [rad^2 per rad]
    k_stheta_rad2_per_m: float = 1e-5
    slip_probability: float = 0.01         # per rotating sample
    slip_scale_deg: float = 0.5            # scale of the Student-t(3) slip error
    range_sigma_m: float = 0.05            # extra random UWB range component (sweep 0.05 / 0.10)


def draw_drift(level: DriftLevel, rng: np.random.Generator) -> dict:
    """Run-level systematic errors with random signs (the drift *realisation*; magnitudes come from the level)."""
    sgn = lambda: float(rng.choice([-1.0, 1.0]))  # noqa: E731
    return dict(bias_rad_s=math.radians(level.gyro_bias_dps) * sgn(), sf=level.gyro_sf * sgn(), eps_d=level.wheel_ratio * sgn(),
                e_b=level.wheelbase_err * sgn())


def true_increments(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """True path length [m] and heading increment [rad] between consecutive samples (first sample: 0)."""
    x = np.array([r["x"] for r in rows])
    y = np.array([r["y"] for r in rows])
    yaw = np.radians([r["yaw_body_deg"] for r in rows])
    ds = np.r_[0.0, np.hypot(np.diff(x), np.diff(y))]
    dth = np.r_[0.0, np.diff(yaw)]
    return ds, dth


def generate_inputs(ds: np.ndarray, dth: np.ndarray, drift: dict, noise: SensorNoise, dt: float, rng: np.random.Generator,
                    wheel_base: float = WHEEL_BASE_M) -> dict:
    n = len(ds)
    arw = math.radians(noise.arw_deg_sqrt_s) * math.sqrt(dt)
    gyro = (1.0 + drift["sf"]) * dth + drift["bias_rad_s"] * dt + arw * rng.standard_normal(n)
    sl = ds - dth * wheel_base / 2.0
    sr = ds + dth * wheel_base / 2.0
    eta_l, eta_r = -drift["eps_d"] / 2.0, drift["eps_d"] / 2.0
    sl2, sr2 = sl * (1.0 + eta_l), sr * (1.0 + eta_r)
    b_est = wheel_base * (1.0 + drift["e_b"])
    ds_o = (sl2 + sr2) / 2.0 + np.sqrt(noise.k_s_m * np.abs(ds)) * rng.standard_normal(n)
    th_sigma = np.sqrt(noise.k_theta_rad * np.abs(dth) + noise.k_stheta_rad2_per_m * np.abs(ds))
    th_o = (sr2 - sl2) / b_est + th_sigma * rng.standard_normal(n)
    rotating = (np.abs(dth) > 1e-9) & (np.abs(ds) < 1e-12)
    slip = rotating & (rng.random(n) < noise.slip_probability)
    th_o = th_o + slip * math.radians(noise.slip_scale_deg) * rng.standard_t(3, n)
    for a in (gyro, ds_o, th_o):
        a[0] = 0.0
    return dict(dtheta_gyro=gyro, ds_odom=ds_o, dtheta_odom=th_o, wheel_base_nominal=wheel_base)


def noise_model_for_filter(noise: SensorNoise, dt: float) -> dict:
    """Variances the filter is told (it knows the noise structure, not the drift realisation)."""
    return dict(arw_var=(math.radians(noise.arw_deg_sqrt_s)) ** 2 * dt, k_s=noise.k_s_m, k_theta=noise.k_theta_rad, k_stheta=noise.k_stheta_rad2_per_m,
                range_var=noise.range_sigma_m ** 2)
