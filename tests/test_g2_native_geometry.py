import numpy as np
import pytest

from rt_cp_uwb_py.g2_native_geometry import (
    basis, clip_coplanar_owners, hollow_column_thickness, polygon_from_triangles,
)


def square(x0=0, x1=1, z=0):
    q = np.array([[x0, 0, z], [x1, 0, z], [x1, 1, z], [x0, 1, z]], dtype=float)
    return q, q[[[0, 1, 2], [0, 2, 3]]]


def test_floor_owns_contact_regardless_of_opposite_winding():
    q, tri = square()
    before = tri.copy()
    remaining, cuts = clip_coplanar_owners(tri[:, ::-1], q[::-1], [('floor', tri)])
    assert remaining.shape == (0, 3, 3)
    assert cuts == [dict(owner_wall_id='floor', removed_area_m2=1.)]
    np.testing.assert_array_equal(tri, before)


def test_partial_support_keeps_overhang_without_duplicate_cut():
    q, tri = square(0, 2)
    _, floor = square()
    remaining, cuts = clip_coplanar_owners(tri, q, [('floor', floor), ('duplicate', floor)])
    assert len(cuts) == 1
    polygon = polygon_from_triangles(remaining, basis(q))
    assert polygon.area == pytest.approx(1.)
    assert np.min(remaining[:, :, 0]) == pytest.approx(1.)


def test_parallel_separated_board_not_removed():
    q, tri = square(z=.01)
    _, floor = square()
    remaining, cuts = clip_coplanar_owners(tri, q, [('floor', floor)])
    np.testing.assert_array_equal(remaining, tri)
    assert cuts == []


@pytest.mark.parametrize('width, expected', [(.25, .05), (.15, .0375)])
def test_column_has_real_air_cavity(width, expected):
    thickness = hollow_column_thickness([[0, 0, 0], [width, width, 3]])
    assert thickness == pytest.approx(expected)
    assert width - 2 * thickness >= width / 2 - 1e-12


def test_flat_column_rejected():
    with pytest.raises(ValueError):
        hollow_column_thickness([[0, 0, 0], [0, .25, 3]])
