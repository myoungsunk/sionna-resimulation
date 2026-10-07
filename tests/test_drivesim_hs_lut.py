import numpy as np
import pytest

from qclean_uwb.drivesim import hs_lut as L
from qclean_uwb.scenarios.corridor import CorridorSetup


def ideal_banks():
    """Banks of ideal +-45 deg dipole-like patterns (E along (x +- y)/sqrt2 for any direction) for a fast test."""
    from qclean_uwb.drivesim import pattern_apply as P
    th = np.arange(0.0, 181.0, 5.0)
    ph = np.arange(-180.0, 181.0, 5.0)
    T, F = np.meshgrid(np.radians(th), np.radians(ph), indexing="ij")
    banks = []
    for sign in (+1, -1):
        e = np.array([1.0, sign * 1.0, 0.0]) / np.sqrt(2)
        et = e[0] * np.cos(T) * np.cos(F) + e[1] * np.cos(T) * np.sin(F) - e[2] * np.sin(T)
        ep = -e[0] * np.sin(F) + e[1] * np.cos(F)
        n_bin = 257
        banks.append(P.Bank(dict(theta_deg=th, phi_deg=ph, e_theta=np.repeat(et[None] + 0j, n_bin, 0), e_phi=np.repeat(ep[None] + 0j, n_bin, 0),
                                 freqs_hz=np.linspace(6.2504e9, 6.7496e9, n_bin))))
    return banks


def test_boresight_curve_is_minus_cos_2yaw_for_ideal_ports():
    banks = ideal_banks()
    for yaw in (0.0, 20.0, 45.0, 75.0, 130.0):
        # theta ~ 0 (robot straight below the anchor): s = -cos(2 yaw_antenna) up to the anchor flip; check |s| shape
        s = L.los_s_direct(banks, 1.0, 0.0, -yaw)
        assert abs(s) <= 1.0
    s0, s45 = L.los_s_direct(banks, 1.0, 0.0, 0.0), L.los_s_direct(banks, 1.0, 0.0, 45.0)
    assert abs(abs(s0) - 1.0) < 1e-2 and abs(s45) < 1e-2        # extremum at 0 deg, null at 45 deg


def test_lut_matches_direct_evaluation_and_gradient_is_consistent():
    banks = ideal_banks()
    lut = L.build_lut(banks, theta_step_deg=15.0, phi_step_deg=15.0, theta_max_deg=90.0)
    f = L.HsLut(lut)
    rng = np.random.default_rng(0)
    for _ in range(6):
        t, a, b = rng.uniform(5, 80), rng.uniform(-170, 170), rng.uniform(-170, 170)
        assert f(t, a, b) == pytest.approx(L.los_s_direct(banks, t, a, b), abs=0.08)       # coarse grid, loose bound
    # grid points are exact
    i, j, k = 3, 5, 7
    assert f(lut["theta_deg"][i], lut["phi_deg"][j], lut["phi_deg"][k]) == pytest.approx(lut["s"][i, j, k], abs=1e-12)
    # gradient equals finite differences of the interpolant
    t, a, b = 37.0, 12.0, -61.0
    v, g = f(t, a, b, with_grad=True)
    eps = 1e-4
    fd = [(f(t + eps, a, b) - f(t - eps, a, b)) / (2 * eps), (f(t, a + eps, b) - f(t, a - eps, b)) / (2 * eps), (f(t, a, b + eps) - f(t, a, b - eps)) / (2 * eps)]
    np.testing.assert_allclose(g, fd, atol=1e-6)


def test_lut_is_periodic_in_azimuth():
    banks = ideal_banks()
    f = L.HsLut(L.build_lut(banks, 30.0, 30.0))
    assert f(40.0, 175.0, -175.0) == pytest.approx(f(40.0, -185.0, 185.0), abs=1e-12)


def test_geometry_angles_roundtrip_with_los_direct():
    banks = ideal_banks()
    setup = CorridorSetup()
    anchor, robot = setup.anchor_position, setup.robot_position(9.0, 0.35)
    th, pt, pr = L.geometry_angles(anchor, robot, 30.0)
    d = (robot - anchor) / np.linalg.norm(robot - anchor)
    h = L.los_h(banks, d, 30.0)
    from qclean_uwb.drivesim import observation as O
    s_geo = O.observe(h[None], banks[0].freqs_hz, None, None)["s"][0]
    assert L.los_s_direct(banks, float(th), float(pt), float(pr)) == pytest.approx(s_geo, abs=1e-9)
