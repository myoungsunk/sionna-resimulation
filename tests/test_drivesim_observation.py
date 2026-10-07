import numpy as np
import pytest

from qclean_uwb.drivesim import observation as O
from qclean_uwb.features.fp_power import signed_s_single_tx

FREQ = np.linspace(6.2504e9, 6.7496e9, 257)


def random_h(n, seed=0):
    rng = np.random.default_rng(seed)
    h = np.zeros((n, 257, 2, 2), complex)
    for b in range(n):
        for rx in range(2):
            for tx in range(2):
                for _ in range(4):
                    h[b, :, rx, tx] += rng.normal() * 1e-4 * np.exp(-2j * np.pi * FREQ * rng.uniform(20e-9, 120e-9)) * np.exp(1j * rng.uniform(0, 6))
    return h


def test_batched_chain_matches_project_chain_exactly():
    h = random_h(12)
    obs = O.observe(h, FREQ, None, None, tx=0)
    for b in range(12):
        s, power, idx, delay = signed_s_single_tx(h[b], FREQ, tx=0)
        assert obs["s"][b] == pytest.approx(s, abs=1e-12)
        assert obs["index"][b] == idx
        assert obs["delay_s"][b] == pytest.approx(delay, abs=1e-18)
        np.testing.assert_allclose(obs["power"][b], power, rtol=1e-10)


def test_noise_is_zero_mean_with_requested_variance_and_deterministic():
    h = random_h(1)
    base = O.observe(h, FREQ, None, None)["s"][0]
    var = 1e-12
    runs = [O.observe(np.repeat(h, 400, axis=0), FREQ, var, np.random.default_rng(1))["s"]]
    again = O.observe(np.repeat(h, 400, axis=0), FREQ, var, np.random.default_rng(1))["s"]
    np.testing.assert_array_equal(runs[0], again)
    assert abs(np.nanmean(runs[0]) - base) < 0.02 and np.nanstd(runs[0]) > 0


def test_snr_definition_and_detection_threshold_follow_project_formula():
    v = O.noise_var_from_snr(20.0)
    assert O.free_space_power() / v == pytest.approx(100.0)
    assert O.detection_threshold(4.856640061591484e-16, n_branches=4) == pytest.approx(2.1066154614220773e-07, rel=1e-12)


def test_undetected_samples_are_nan():
    h = random_h(3) * 1e-6
    obs = O.observe(h, FREQ, 1e-10, np.random.default_rng(0))
    assert not obs["detected"].any() and np.isnan(obs["s"]).all() and np.isnan(obs["range_m"]).all()


def test_ideal_two_port_ratio_recovers_cos_2yaw_sign_convention():
    delay = 40e-9
    ph = np.exp(-2j * np.pi * FREQ * delay)
    yaw = np.radians(np.array([0.0, 30.0, 45.0, 60.0, 90.0]))
    h = np.zeros((len(yaw), 257, 2, 2), complex)
    h[:, :, 0, 0] = (-np.sin(yaw))[:, None] * ph      # RX +45 for TX +45 (ideal LoS, see port_ratio.los_two_port_ratio)
    h[:, :, 1, 0] = np.cos(yaw)[:, None] * ph
    s = O.observe(h * 1e-4, FREQ, None, None, tx=0)["s"]
    np.testing.assert_allclose(s, -np.cos(2 * yaw), atol=1e-9)
