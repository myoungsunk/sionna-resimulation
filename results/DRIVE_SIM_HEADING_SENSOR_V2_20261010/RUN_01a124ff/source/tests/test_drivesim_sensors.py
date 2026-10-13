import math

import numpy as np
import pytest

from qclean_uwb.drivesim import sensors as S
from qclean_uwb.drivesim.trajectory import TrajectoryConfig, build_samples


def inc():
    rows = build_samples(TrajectoryConfig(probe_period_s=20.0))
    return rows, *S.true_increments(rows)


def zero_noise():
    return S.SensorNoise(arw_deg_sqrt_s=0.0, k_s_m=0.0, k_theta_rad=0.0, k_stheta_rad2_per_m=0.0, slip_probability=0.0, range_sigma_m=0.0)


def test_error_free_sensors_reproduce_the_truth():
    rows, ds, dth = inc()
    out = S.generate_inputs(ds, dth, dict(bias_rad_s=0.0, sf=0.0, eps_d=0.0, e_b=0.0), zero_noise(), 0.2, np.random.default_rng(0))
    np.testing.assert_allclose(out["dtheta_gyro"][1:], dth[1:], atol=1e-12)
    np.testing.assert_allclose(out["ds_odom"][1:], ds[1:], atol=1e-12)
    np.testing.assert_allclose(out["dtheta_odom"][1:], dth[1:], atol=1e-12)


def test_gyro_bias_and_scale_factor_integrate_to_expected_heading_error():
    rows, ds, dth = inc()
    drift = dict(bias_rad_s=math.radians(0.2), sf=0.015, eps_d=0.0, e_b=0.0)
    g = S.generate_inputs(ds, dth, drift, zero_noise(), 0.2, np.random.default_rng(0))["dtheta_gyro"]
    t = 0.2 * (len(ds) - 1)
    expected = 1.015 * dth.sum() + math.radians(0.2) * t
    assert g.sum() == pytest.approx(expected, rel=1e-9)


def test_wheel_diameter_ratio_gives_straight_line_heading_drift_eps_over_b():
    n = 100
    ds = np.r_[0.0, np.full(n, 0.04)]
    dth = np.zeros(n + 1)
    drift = dict(bias_rad_s=0.0, sf=0.0, eps_d=0.005, e_b=0.0)
    o = S.generate_inputs(ds, dth, drift, zero_noise(), 0.2, np.random.default_rng(0))
    assert o["dtheta_odom"].sum() == pytest.approx(0.005 * ds.sum() / S.WHEEL_BASE_M, rel=1e-9)     # 0.5 % -> ~1.0 deg per metre
    assert math.degrees(0.005 / S.WHEEL_BASE_M) == pytest.approx(0.998, abs=0.01)


def test_wheelbase_error_scales_rotation_only():
    ds = np.r_[0.0, np.zeros(36)]
    dth = np.r_[0.0, np.full(36, math.radians(5.0))]
    o = S.generate_inputs(ds, dth, dict(bias_rad_s=0.0, sf=0.0, eps_d=0.0, e_b=0.01), zero_noise(), 0.2, np.random.default_rng(0))
    assert o["dtheta_odom"].sum() == pytest.approx(math.pi / 1.01, rel=1e-9)                         # 180 deg turn -> ~1.8 deg error
    assert o["ds_odom"].sum() == pytest.approx(0.0, abs=1e-12)


def test_slip_only_on_rotating_samples_and_noise_scales_with_motion():
    rows, ds, dth = inc()
    noise = S.SensorNoise(slip_probability=1.0)
    o = S.generate_inputs(ds, dth, dict(bias_rad_s=0.0, sf=0.0, eps_d=0.0, e_b=0.0), noise, 0.2, np.random.default_rng(1))
    straight = (np.abs(dth) < 0.05) & (ds > 0)
    rotating = (np.abs(dth) > 1e-9) & (ds < 1e-12)
    assert np.std(o["dtheta_odom"][rotating] - dth[rotating]) > 5 * np.std(o["dtheta_odom"][straight] - dth[straight])


def test_draw_drift_has_requested_magnitudes():
    rng = np.random.default_rng(0)
    d = S.draw_drift(S.DRIFT_LEVELS[2], rng)
    assert abs(d["sf"]) == 0.015 and abs(d["eps_d"]) == 0.010 and abs(math.degrees(d["bias_rad_s"]) - 0.2) < 1e-12 or abs(abs(math.degrees(d["bias_rad_s"])) - 0.2) < 1e-12
