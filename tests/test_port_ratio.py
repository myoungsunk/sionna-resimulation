import numpy as np
import pytest

from qclean_uwb.features.port_ratio import los_two_port_ratio, port_difference_ratio


def test_equal_ports_give_zero_and_opposite_ports_give_infinity():
    assert port_difference_ratio(1 + 1j, 1 + 1j) == pytest.approx(0.0)
    assert np.isinf(port_difference_ratio(1.0, -1.0))


def test_ratio_is_invariant_to_common_complex_scale():
    a, b = 0.3 - 0.2j, -0.1 + 0.4j
    assert port_difference_ratio(a, b) == pytest.approx(port_difference_ratio(2j * a, 2j * b))


def test_ideal_los_curve_matches_tan_yaw_plus_45():
    yaw = np.array([0.0, 10.0, 30.0, 100.0, 135.0])
    np.testing.assert_allclose(los_two_port_ratio(yaw)[[0, 1, 2, 3]], np.abs(np.tan(np.radians(yaw[:4] + 45))), rtol=1e-9)
    assert los_two_port_ratio(135.0) == pytest.approx(0.0, abs=1e-12)


def test_minus45_tx_curve_is_mirror_image_about_90_degrees():
    yaw = np.array([0.0, 20.0, 60.0, 90.0])
    np.testing.assert_allclose(los_two_port_ratio(180.0 - yaw, "LP_minus45"), los_two_port_ratio(yaw, "LP_plus45"), rtol=1e-9, atol=1e-12)
    with pytest.raises(ValueError):
        los_two_port_ratio(0.0, "RHCP")


def test_ideal_fp_power_ratio_is_abs_cos_2yaw_and_symmetric_in_ports():
    from qclean_uwb.features.port_ratio import los_fp_power_ratio
    yaw = np.array([0.0, 22.5, 45.0, 90.0, 135.0])
    np.testing.assert_allclose(los_fp_power_ratio(yaw), np.abs(np.cos(np.radians(2 * yaw))), atol=1e-12)
    assert los_fp_power_ratio(45.0) == pytest.approx(0.0, abs=1e-12)


def test_angle_match_recovers_ideal_yaw_and_has_four_candidates():
    from qclean_uwb.features.angle_match import representative_yaw, yaw_candidates
    from qclean_uwb.features.port_ratio import los_fp_power_ratio
    yaw = np.arange(0.0, 181.0, 10.0)
    est, err = representative_yaw(los_fp_power_ratio(yaw), yaw)
    np.testing.assert_allclose(err, 0.0, atol=1e-6)
    cand = np.sort(yaw_candidates(np.cos(np.radians(60.0))))
    np.testing.assert_allclose(cand, [30.0, 60.0, 120.0, 150.0], atol=1e-9)


def test_angle_match_error_is_large_where_the_curve_is_flat():
    from qclean_uwb.features.angle_match import representative_yaw
    _, err = representative_yaw(0.95, 0.0)   # true yaw 0 (ideal ratio 1), measured 0.95
    assert abs(float(err)) > 8.0

