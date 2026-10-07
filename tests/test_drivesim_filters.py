import math
import time

import numpy as np
import pytest

from qclean_uwb.drivesim import filters as F
from qclean_uwb.drivesim import sensors as S
from qclean_uwb.drivesim.hs_lut import HsLut, s_model
from qclean_uwb.drivesim.trajectory import TrajectoryConfig, build_samples

ANCHOR = (4.0, 0.0, 2.65)


def synthetic_lut(step=2.0):
    th = np.arange(0.0, 90.01, step)
    ph = np.arange(-180.0, 180.0, step)
    a = np.radians(ph)
    s = -np.cos(2.0 * (a[:, None] + a[None, :]))              # ideal ports: s = -cos 2 yaw, yaw = pi - phi_tx - phi_rx
    return HsLut(dict(theta_deg=th, phi_deg=ph, s=np.repeat(s[None], len(th), 0)))


def world(period, seed, drift_level=2, mount=45.0, s_sigma=0.02, noise=None):
    rows = build_samples(TrajectoryConfig(probe_period_s=period))
    ds, dth = S.true_increments(rows)
    rng = np.random.default_rng(seed)
    drift = S.draw_drift(S.DRIFT_LEVELS[drift_level], rng)
    noise = noise or S.SensorNoise()
    inputs = S.generate_inputs(ds, dth, drift, noise, 0.2, rng)
    lut = synthetic_lut()
    x = np.array([r["x"] for r in rows]); y = np.array([r["y"] for r in rows]); yaw = np.radians([r["yaw_body_deg"] for r in rows])
    s_true = s_model(lut, ANCHOR, 0.45, x, y, yaw, mount)
    rng2 = np.random.default_rng(seed + 1000)
    dist = np.sqrt((x - ANCHOR[0]) ** 2 + y ** 2 + (ANCHOR[2] - 0.45) ** 2)
    obs = dict(s=s_true + s_sigma * rng2.standard_normal(len(x)), range_m=dist + noise.range_sigma_m * rng2.standard_normal(len(x)),
               detected=np.ones(len(x), bool), power=np.ones((len(x), 2)) * 1.0)
    flags = dict(turn_phase=np.array([r["turn_phase"] for r in rows]))
    truth = np.column_stack([x, y, yaw])
    return rows, inputs, obs, flags, truth, lut, mount


def run(kind, period, seed, use_s=True, use_range=True, init_noise=True, **kw):
    rows, inputs, obs, flags, truth, lut, mount = world(period, seed, **{k: v for k, v in kw.items() if k in ("drift_level", "mount")})
    cfg = F.FilterConfig(kind=kind, use_s=use_s, use_range=use_range, mount_deg=mount, s_mismatch_sigma=0.02,
                         noise_var_cir_tap=0.0, anchor_xyz=ANCHOR, range_quant_var=0.0, range_extra_sigma=0.0)
    rng = np.random.default_rng(seed + 7)
    x0 = np.array([truth[0, 0], truth[0, 1], truth[0, 2], 0.0, 0.0, 0.0]) + (rng.normal(size=6) * np.array(cfg.p0_std) * np.array([1, 1, 1, 0, 0, 0]) if init_noise else 0)
    out = F.run_filter(cfg, lut, inputs, obs, flags, x0)
    err = out["est"][:, :3] - truth
    err[:, 2] = F.wrap(err[:, 2])
    return out, err, rows


def test_dead_reckoning_with_perfect_sensors_reproduces_truth():
    rows = build_samples(TrajectoryConfig(probe_period_s=20.0))
    ds, dth = S.true_increments(rows)
    zero = S.SensorNoise(arw_deg_sqrt_s=0.0, k_s_m=0.0, k_theta_rad=0.0, k_stheta_rad2_per_m=0.0, slip_probability=0.0, range_sigma_m=0.0)
    inputs = S.generate_inputs(ds, dth, dict(bias_rad_s=0.0, sf=0.0, eps_d=0.0, e_b=0.0), zero, 0.2, np.random.default_rng(0))
    n = len(rows)
    obs = dict(s=np.zeros(n), range_m=np.zeros(n), detected=np.zeros(n, bool), power=np.ones((n, 2)))
    flags = dict(turn_phase=np.array([r["turn_phase"] for r in rows]))
    x0 = [rows[0]["x"], rows[0]["y"], math.radians(rows[0]["yaw_body_deg"]), 0, 0, 0]
    out = F.run_filter(F.FilterConfig(use_s=False, use_range=False), None, inputs, obs, flags, x0)
    truth = np.column_stack([[r["x"] for r in rows], [r["y"] for r in rows], np.radians([r["yaw_body_deg"] for r in rows])])
    np.testing.assert_allclose(out["est"][:, :2], truth[:, :2], atol=1e-9)
    np.testing.assert_allclose(F.wrap(out["est"][:, 2] - truth[:, 2]), 0.0, atol=1e-9)


def test_noise_model_helpers():
    assert F.thermal_var_s(1.0, 1.0, 0.01) == pytest.approx(8 * 0.01 / 8.0)
    assert F.wrap(3 * math.pi) == pytest.approx(math.pi) or F.wrap(3 * math.pi) == pytest.approx(-math.pi)


@pytest.mark.parametrize("kind", ["ekf", "iekf", "ukf", "gsf"])
def test_s_and_range_reduce_heading_error_with_probes_on_model_consistent_data(kind):
    t0 = time.time()
    dr_only, err_dr, _ = run(kind, None, 1, use_s=False, use_range=False)
    full, err_full, rows = run(kind, 20.0, 1)
    rms = lambda e: math.degrees(math.sqrt(np.mean(e[:, 2] ** 2)))  # noqa: E731
    assert rms(err_full) < 0.5 * rms(err_dr), (kind, rms(err_dr), rms(err_full))
    assert math.degrees(np.abs(err_full[-1, 2])) < 10.0
    assert time.time() - t0 < 60


def test_ekf_nees_is_consistent_on_model_consistent_data():
    nees = []
    for seed in range(4):
        out, err, _ = run("ekf", 20.0, seed)
        for e, P in zip(err[300:], out["cov3"][300:]):
            nees.append(float(e @ np.linalg.solve(P, e)))
    assert 1.0 < np.mean(nees) < 9.0           # 3 dof expected value 3; loose band for an EKF with a mildly nonlinear s model


def test_inverse_heading_baseline_runs_and_gate_counts_are_reported():
    rows, inputs, obs, flags, truth, lut, mount = world(20.0, 2)
    cfg = F.FilterConfig(kind="ekf", s_mode="inverse", mount_deg=mount, anchor_xyz=ANCHOR, s_mismatch_sigma=0.02, range_quant_var=0.0, range_extra_sigma=0.0)
    out = F.run_filter(cfg, lut, inputs, obs, flags, [truth[0, 0], truth[0, 1], truth[0, 2], 0, 0, 0])
    assert out["stats"]["s_updates"] + out["stats"]["s_rejected"] > 0 and np.isfinite(out["est"]).all()
