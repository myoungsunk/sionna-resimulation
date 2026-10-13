import importlib.util
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import multivariate_normal, norm


spec = importlib.util.spec_from_file_location("i2_batch", Path(__file__).parents[1] / "i2_batch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ConditionalBatchTarget = module.ConditionalBatchTarget
batch_posterior = module.batch_posterior


def inputs():
    public = dict(t_s=np.arange(4) * .2, dt_s=np.array([0., .2, .2, .2]),
                  ds_odom=np.array([0., .04, .035, .05]),
                  dtheta_gyro=np.array([0., .01, -.02, .03]),
                  dtheta_odom=np.array([0., .012, -.015, .025]),
                  range_m=np.array([1., 1.04, 1.08, 1.1]),
                  range_mask=np.array([False, True, False, True]),
                  x0=np.zeros(6))
    config = dict(p0_std=[.03, .03, .04, .002, .01, .006], wheel_base=.287,
                  anchor_xyz=[1., 0., 1.], robot_z=.5, k_s=2e-5,
                  k_theta=1e-4, k_stheta=1e-5,
                  gyro_N_rad_sqrt_s=.0003, range_sigma=.05)
    return public, config


def test_conditional_factor_matches_direct_gaussian():
    public, config = inputs()
    target = ConditionalBatchTarget(public, config, "DR")
    state = np.array([0., 0., 0., .001, .007, .004])
    md, mg, ld, lgd, lgg, log_odo = target.conditional(state)
    bg, sf, eps = state[3:]
    b1, b2 = -eps / target.b, -(1 - eps ** 2 / 4) / (1 + sf)
    h = (1 - eps ** 2 / 4) * (target.g - bg * target.dt) / (1 + sf) + eps * target.d / target.b
    total = 0.
    for k in range(3):
        s = b1 ** 2 * target.qd[k] + b2 ** 2 * target.qg[k] + target.qo[k]
        c = np.array([target.qd[k] * b1, target.qg[k] * b2])
        direct_cov = np.diag([target.qd[k], target.qg[k]]) - np.outer(c, c) / s
        factor = np.array([[ld[k], 0.], [lgd[k], lgg[k]]])
        np.testing.assert_allclose(factor @ factor.T, direct_cov, rtol=1e-12, atol=1e-20)
        residual = target.o[k] - h[k]
        np.testing.assert_allclose([md[k], mg[k]], c * residual / s)
        noise = np.array([md[k], mg[k]]) + factor @ np.array([.4, -.7])
        joint_cov = np.array([[target.qd[k], 0., c[0]], [0., target.qg[k], c[1]], [c[0], c[1], s]])
        lhs = multivariate_normal.logpdf(np.r_[noise, residual], cov=joint_cov)
        rhs = norm.logpdf(residual, scale=np.sqrt(s)) + multivariate_normal.logpdf(noise, mean=[md[k], mg[k]], cov=direct_cov)
        assert lhs == pytest.approx(rhs, abs=1e-10)
        total += norm.logpdf(residual, scale=np.sqrt(s))
    assert log_odo == pytest.approx(total, abs=1e-12)


def test_range_likelihood_matches_direct_and_no_truth_access():
    public, config = inputs()
    zp, zn = np.zeros(6), np.zeros((2, 3))
    dr = ConditionalBatchTarget(public, config, "DR")
    range_target = ConditionalBatchTarget(public, config, "RANGE")
    ll_dr, poses = dr.evaluate(zp, zn, trajectory=True)
    r = np.sqrt((poses[:, 0] - 1) ** 2 + poses[:, 1] ** 2 + .5 ** 2)
    expected = np.sum(norm.logpdf(public["range_m"][public["range_mask"]], loc=r[public["range_mask"]], scale=.05))
    assert range_target.evaluate(zp, zn) - ll_dr == pytest.approx(expected)
    public["true_position"] = object()
    public["true_calibration"] = object()
    assert ConditionalBatchTarget(public, config, "RANGE").evaluate(zp, zn) == range_target.evaluate(zp, zn)
    changed = dict(public, range_m=public["range_m"] + .1)
    assert ConditionalBatchTarget(changed, config, "RANGE").evaluate(zp, zn) != range_target.evaluate(zp, zn)


def test_sampler_deterministic_and_reference_unapproved():
    public, config = inputs()
    settings = dict(burn=50, retained=10, thin=1, chains=4, pCN_beta=.2)
    first = batch_posterior(public, config, [3], "DR", 12, settings)
    public["truth"] = object()
    second = batch_posterior(public, config, [3], "DR", 12, settings)
    np.testing.assert_array_equal(first["samples"], second["samples"])
    assert first["samples"].shape == (4, 10, 6)
    assert first["pose_samples"].shape == (4, 10, 1, 3)
    assert first["reference_status"] == "REFERENCE_NOT_VALIDATED"
    assert not np.array_equal(first["samples"][0], first["samples"][1])


def test_invalid_shapes_times_and_scale_are_rejected():
    public, config = inputs()
    with pytest.raises(ValueError, match="dt_s"):
        ConditionalBatchTarget(dict(public, dt_s=np.zeros(4)), config, "DR")
    with pytest.raises(ValueError, match="range shapes"):
        ConditionalBatchTarget(dict(public, range_m=np.zeros(3)), config, "RANGE")
    target = ConditionalBatchTarget(public, config, "DR")
    zp = np.zeros(6)
    zp[4] = -101
    assert target.evaluate(zp, np.zeros((2, 3))) == -np.inf


def test_pcn_prior_preserving_transition_identity():
    old = np.array([.4, -.8, .1])
    new = np.array([-.2, .3, .9])
    beta = .3
    rho = np.sqrt(1 - beta ** 2)
    forward = np.sum(norm.logpdf(new, loc=rho * old, scale=beta))
    reverse = np.sum(norm.logpdf(old, loc=rho * new, scale=beta))
    prior_old = np.sum(norm.logpdf(old))
    prior_new = np.sum(norm.logpdf(new))
    assert prior_old + forward == pytest.approx(prior_new + reverse, abs=1e-12)


def test_analytical_yaw_and_constant_curvature_position():
    public, config = inputs()
    public["dtheta_gyro"] = np.array([0., .1, .1, .1])
    public["dtheta_odom"] = public["dtheta_gyro"].copy()
    public["ds_odom"] = np.array([0., .04, .04, .04])
    target = ConditionalBatchTarget(public, config, "DR")
    _, path = target.evaluate(np.zeros(6), np.zeros((2, 3)), trajectory=True)
    np.testing.assert_allclose(path[-1], [.4 * np.sin(.3), .4 * (1 - np.cos(.3)), .3], atol=1e-14)
