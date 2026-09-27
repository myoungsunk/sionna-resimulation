import numpy as np
import pytest

from rt_cp_uwb_py.g2_full_inputs import digest
from rt_cp_uwb_py.g2_full_relocation import (frame_moves, overlay_index, relocate_common_row, relocate_frame,
                                             relocate_l_row, search_move)


def wall_at_y(y0):
    """Signed clearance to a slab occupying y >= y0 (air side y < y0)."""
    def f(points):
        points = np.atleast_2d(points)
        return y0 - points[:, 1], np.full(len(points), 'wall', dtype=object)
    return f


def test_search_uses_smallest_whole_mm_horizontal_move_away_from_material():
    m = search_move([1., 1.996, 1.2], wall_at_y(2.0), [], [5., 4., 3.])
    assert m['direction'] == '-y' and m['shift_m'] == 0.006 and m['after'][2] == 1.2
    assert m['clearance_after_m'] >= 0.01 and np.isclose(m['after'][1], 1.99)


def test_search_respects_room_margin_and_never_crosses_material():
    # Wall at y=2.0 and room edge at y=2.005: only -y is useful; +y would leave the room.
    m = search_move([1., 1.998, 1.2], wall_at_y(2.0), [], [5., 2.005, 3.])
    assert m['direction'] == '-y'
    with pytest.raises(ValueError, match='NO_RELOCATION'):
        search_move([.001, .001, 1.2], lambda p: (np.full(len(np.atleast_2d(p)), -1.), None), [], [5., 4., 3.])


def l_row():
    return dict(case_id=7, tx=[1., 1., 2.5], rx=[2., 2., 1.2], true_range_m=0.,
                source_row=dict(rx_x_m=2., rx_y_m=2., rx_z_m=1.2, tx_x_m=1., tx_y_m=1., tx_z_m=2.5, true_dist_m=0.))


def test_l_row_update_mirrors_r2_fields():
    move = dict(before=[2., 2., 1.2], after=[2., 1.99, 1.2])
    r = relocate_l_row(l_row(), {'rx': move})
    assert r['rx'] == [2., 1.99, 1.2] and r['source_row']['rx_y_m'] == 1.99
    assert np.isclose(r['true_range_m'], np.linalg.norm(np.subtract(r['rx'], r['tx'])))
    assert r['source_row']['true_dist_m'] == r['true_range_m'] and r['endpoint_relocation']['old']['rx'] == [2., 2., 1.2]
    with pytest.raises(ValueError, match='BEFORE_MISMATCH'):
        relocate_l_row(l_row(), {'rx': dict(before=[9, 9, 9], after=[0, 0, 0])})


def test_frame_and_common_row_update_hash_and_truth_record():
    physical = dict(scene=dict(size=[5, 4, 3]), tag_pose=dict(position=[2., 2., 1.2], yaw_rad=0.), object=None)
    frame = dict(unit_id='U', frame=0, physical=physical, canonical_scene_hash=digest(physical))
    move = dict(role='rx', before=[2., 2., 1.2], after=[2., 1.99, 1.2],
                linked_rows=[dict(family='C1_static', case_id=5)], linked_frames=[dict(unit_id='U', frame=0)])
    new = relocate_frame(frame, move)
    assert new['canonical_scene_hash'] == digest(new['physical']) != frame['canonical_scene_hash']
    row = dict(case_id=5, tx=[1., 1., 2.5], rx=[2., 2., 1.2], scene_hash=frame['canonical_scene_hash'],
               geometry_truth_status='ANTENNA_ENVELOPE_GEOMETRY', los_blocked=False, los_clear=True,
               metal_surface_distance_m=None, panel_specular_path_geometrically_valid=None)
    r = relocate_common_row(row, {'rx': move}, new['canonical_scene_hash'])
    assert r['scene_hash'] == new['canonical_scene_hash'] and r['los_clear'] is None
    assert r['endpoint_relocation']['previous_scene_hash'] == frame['canonical_scene_hash']
    assert r['endpoint_relocation']['previous_geometry_truth']['los_clear'] is True
    assert frame_moves(dict(moves=[move])) == {('U', 0): move}


def test_row_cannot_be_relocated_twice_for_the_same_role():
    move = dict(role='rx', linked_rows=[dict(family='L1', case_id=1)])
    with pytest.raises(ValueError, match='TWICE'):
        overlay_index(dict(moves=[move, dict(move)]))
