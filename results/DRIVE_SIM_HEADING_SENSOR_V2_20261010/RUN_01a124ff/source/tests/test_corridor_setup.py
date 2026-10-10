import numpy as np
import pytest

from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, CorridorSetup, is_rotation, rot_z


def test_default_setup_passes_all_checks():
    failed = [c for c in CorridorSetup().validate() if not c["passed"]]
    assert failed == []


def test_anchor_boresight_points_to_floor_and_matches_native_tx_rotation():
    assert is_rotation(ANCHOR_ROTATION)
    frame = CorridorSetup().antenna_frame(ANCHOR_ROTATION)
    np.testing.assert_allclose(frame["boresight"], [0, 0, -1])


@pytest.mark.parametrize("yaw", [0, 45, 90, 180, 270, 315])
def test_robot_boresight_stays_up_and_ports_rotate_with_yaw(yaw):
    setup = CorridorSetup()
    frame = setup.antenna_frame(rot_z(yaw))
    np.testing.assert_allclose(frame["boresight"], [0, 0, 1], atol=1e-12)
    plus = frame["LP_plus45"]
    expected = np.array([np.cos(np.radians(45 + yaw)), np.sin(np.radians(45 + yaw)), 0])
    np.testing.assert_allclose(plus, expected, atol=1e-12)


def test_robot_antenna_z_is_independent_of_xy():
    setup = CorridorSetup()
    assert {setup.robot_position(x, y)[2] for x, y in [(2, 0), (9, 0.4), (17, -0.6)]} == {setup.robot_antenna_z_m}


def test_link_geometry_directly_below_anchor_is_on_both_boresights():
    setup = CorridorSetup()
    g = setup.link_geometry(setup.anchor_x_m, setup.anchor_y_m, 0.0)
    assert g["anchor_off_boresight_deg"] == pytest.approx(0.0)
    assert g["robot_off_boresight_deg"] == pytest.approx(0.0)
    assert g["range_m"] == pytest.approx(setup.anchor_position[2] - setup.robot_antenna_z_m)


def test_validation_flags_robot_outside_allowed_region():
    bad = CorridorSetup(example_xy_m=((7.0, 1.1),))
    names = {c["name"] for c in bad.validate() if not c["passed"]}
    assert "example_0_in_allowed_region" in names


def test_config_hash_changes_with_config():
    assert CorridorSetup().snapshot()["config_sha256"] != CorridorSetup(length_m=25.0).snapshot()["config_sha256"]


def test_default_has_four_positions_with_one_below_anchor_and_19_yaws():
    setup = CorridorSetup()
    assert len(setup.example_xy_m) == 4
    assert setup.example_xy_m[0] == (setup.anchor_x_m, setup.anchor_y_m)
    assert setup.yaw_sweep_deg == tuple(float(a) for a in range(0, 181, 10))
