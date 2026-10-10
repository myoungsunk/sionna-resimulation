import numpy as np
import pytest

from qclean_uwb.features.reflection_attribution import C0, GROUPS, classify_paths, fit_abs_cos, image_delays

L, HW, HT = 20.0, 1.2, 2.7


def test_floor_reflection_delay_matches_closed_form():
    tx, rx = [4.0, 0.0, 2.65], [9.0, 0.3, 0.45]
    d = np.hypot(5.0, 0.3)
    expected = np.sqrt(d ** 2 + (2.65 + 0.45) ** 2) / C0
    assert image_delays(tx, rx, L, HW, HT)[("floor",)] == pytest.approx(expected, rel=1e-12)


def test_classify_assigns_groups_and_flags_unmatched():
    tx, rx = [4.0, 0.0, 2.65], [9.0, 0.3, 0.45]
    t = image_delays(tx, rx, L, HW, HT)
    tau = np.array([t[()], t[("floor",)], t[("ceiling",)], t[("wall_y_pos",)], t[("end_x_max",)], t[("floor", "ceiling")], 5e-8])
    label, order, _ = classify_paths(tau, tx, rx, L, HW, HT)
    assert [GROUPS[i] for i in label[:-1]] == ["los", "floor", "ceiling", "side_walls", "end_walls", "multi_bounce"]
    assert label[-1] == -1 and order[-1] == -1


def test_fit_recovers_depth_and_tilt():
    yaw = np.arange(0.0, 181.0, 10.0)
    ratio = 0.7 * np.abs(np.cos(np.radians(2 * (yaw - 12.0))))
    m, y0, rmse = fit_abs_cos(yaw, ratio)
    assert (m, y0) == pytest.approx((0.7, 12.0), abs=1e-3) and rmse < 1e-6
