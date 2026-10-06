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
