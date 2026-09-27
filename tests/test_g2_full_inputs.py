import json
import math

import numpy as np
import pytest

from rt_cp_uwb_py.g2_full_inputs import (IDENTITY_KEYS, Registry, check_rotation, digest,
                                        identity, inside_prisms, point_triangle_distance, prism_boundary,
                                        quat_wxyz_to_matrix, read_frames)


def test_identity_fills_every_key_with_explicit_null():
    ident = identity(family='L1', case_id=100001)
    assert list(ident) == list(IDENTITY_KEYS) and ident['unit_id'] is None and ident['replicate'] is None
    with pytest.raises(ValueError, match='UNKNOWN_IDENTITY_KEYS'):
        identity(family='L1', rx=[0, 0, 0])


def test_target_id_depends_on_identity_not_on_key_order_or_coordinates():
    a = identity(family='C3', case_id=1, unit_id='C3_T00', frame=5)
    b = dict(reversed(list(a.items())))
    assert digest(a) == digest(b)
    assert digest(a) != digest(identity(family='C3', case_id=1, unit_id='C3_T00', frame=6))


def test_quaternion_conversion_matches_axis_rotation_and_rejects_non_unit():
    assert np.allclose(quat_wxyz_to_matrix([1, 0, 0, 0]), np.eye(3))
    half = math.sqrt(.5)  # 90 deg about +z (w, x, y, z)
    assert np.allclose(quat_wxyz_to_matrix([half, 0, 0, half]), [[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    with pytest.raises(ValueError, match='QUATERNION_NOT_UNIT'):
        quat_wxyz_to_matrix([1, 0, 0, .1])


def test_improper_or_non_orthonormal_rotation_is_rejected():
    check_rotation(np.diag([1., -1., -1.]))
    for bad in (np.diag([1., 1., -1.]), np.diag([1., 2., .5]), np.full((3, 3), np.nan)):
        with pytest.raises(ValueError):
            check_rotation(bad)


def test_registry_reuses_identical_records():
    reg = Registry()
    k1 = reg.add(dict(tx_rotation=np.eye(3).tolist()))
    assert reg.add(dict(tx_rotation=np.eye(3).tolist())) == k1 and len(reg.items) == 1


def frame_row(unit, frame, physical):
    return dict(unit_id=unit, frame=frame, canonical_scene_hash=digest(physical), physical=physical)


PHYS = dict(scene=dict(size=[5, 4, 3]), tag_pose=dict(position=[1, 1, 1.2], yaw_rad=0.), object=None)


def test_frames_reject_hash_mismatch_and_duplicates(tmp_path):
    good = frame_row('U', 0, PHYS)
    p = tmp_path/'F.jsonl'
    p.write_text(json.dumps(good) + '\n')
    frames, total = read_frames(p, {('U', 0)})
    assert total == 1 and frames[('U', 0)]['hash'] == good['canonical_scene_hash']
    p.write_text(json.dumps(dict(good, canonical_scene_hash='0'*64)) + '\n')
    with pytest.raises(ValueError, match='FRAME_SHA_MISMATCH'):
        read_frames(p, set())
    p.write_text((json.dumps(good) + '\n')*2)
    with pytest.raises(ValueError, match='DUPLICATE_FRAME'):
        read_frames(p, set())


def test_point_triangle_distance_face_edge_vertex():
    tri = np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]])
    pts = np.array([[.2, .2, .5], [.5, -.3, 0.], [-.3, -.4, 0.]])
    assert np.allclose(point_triangle_distance(pts, tri), [.5, .3, .5])


def test_prism_is_one_sided_negative_normal():
    # Sheet in z=0 with +z normal: material occupies -0.1 < z < 0 (NEGATIVE_NORMAL, thickness 0.1).
    tri = np.array([[[0., 0., 0.], [2., 0., 0.], [0., 2., 0.]]])
    boundary, n = prism_boundary(tri, .1)
    assert np.allclose(n, [[0, 0, 1]]) and boundary.shape == (1, 8, 3, 3)
    pts = np.array([[.3, .3, .02], [.3, .3, -.05], [.3, .3, -.15]])
    assert inside_prisms(pts, tri, n, .1)[:, 0].tolist() == [False, True, False]
    d = point_triangle_distance(pts, boundary.reshape(-1, 3, 3))
    assert np.allclose(d, [.02, .05, .05])
