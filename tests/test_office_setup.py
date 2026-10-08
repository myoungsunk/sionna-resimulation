import numpy as np

from qclean_uwb.scenarios.office import OfficeSetup, box_quads, segment_hits_box, segment_hits_quad


def test_validation_passes():
    failed = [c for c in OfficeSetup().validate() if not c["passed"]]
    assert not failed, failed


def test_twelve_islands_and_24_desks_facing_plus_and_minus_x():
    s = OfficeSetup()
    boxes = s.boxes()
    desks = [b for b in boxes if b["group"] == "desks"]
    assert len(desks) == 24 == 2 * len(s.col_x_m) * s.n_rows
    assert sum(b["group"] == "partitions" for b in boxes) == 12
    assert sum(b["name"].endswith("plus_x") for b in desks) == sum(b["name"].endswith("minus_x") for b in desks) == 12
    # desk wide side (1.4 m) runs along y, depth (0.7 m) along x
    d = desks[0]
    assert np.isclose(d["hi"][1] - d["lo"][1], s.desk_lwh_m[0]) and np.isclose(d["hi"][0] - d["lo"][0], s.desk_lwh_m[1])
    objs = s.objects()
    assert len(objs) == 6 + 12 + 24  # one sheet per physical slab: envelope, partitions, desk tops
    assert {o["group"] for o in objs} == {"floor", "ceiling", "outer_walls", "partitions", "desks"}


def test_box_quads_area():
    quads = box_quads((0, 0, 0), (1, 2, 3))
    assert np.isclose(sum(np.linalg.norm(np.cross(q[1] - q[0], q[3] - q[0])) for q in quads), 2 * (2 + 3 + 6))


def test_segment_box_hits():
    lo, hi = (0, 0, 0), (1, 1, 1)
    assert segment_hits_box((-1, 0.5, 0.5), (2, 0.5, 0.5), lo, hi)
    assert not segment_hits_box((-1, 2, 0.5), (2, 2, 0.5), lo, hi)


def test_path_is_free_and_los_is_mixed():
    s = OfficeSetup()
    pts = s.sample_points()
    assert len(pts) > 15
    assert all(s.is_free(x, y, 0.3) for x, y in pts)
    flags = [s.los_status(x, y)["clear"] for x, y in pts]
    assert any(flags) and not all(flags)


def test_closed_y12_end_has_no_path_beyond_the_corridor_tops():
    s = OfficeSetup()
    assert all(y1 <= s.corridor_top_y_m + 1e-9 and y0 <= s.corridor_top_y_m + 1e-9 for (_, y0), (_, y1) in s.path_segments())
    assert max(b["hi"][1] for b in s.boxes()) < s.width_m


def test_islands_block_a_low_line_and_not_a_vertical_one():
    s = OfficeSetup()
    d = [b for b in s.boxes() if b["group"] == "desks"][0]
    c = [(d["lo"][i] + d["hi"][i]) / 2 for i in range(3)]
    assert segment_hits_box((c[0], c[1], 0.2), (c[0], c[1], 2.5), d["lo"], d["hi"])


def test_box_faces_point_outward():
    lo, hi = np.array([0.0, 0.0, 0.0]), np.array([1.0, 2.0, 3.0])
    c = 0.5 * (lo + hi)
    for f in box_quads(lo, hi):
        n = np.cross(f[1] - f[0], f[3] - f[0])
        assert n @ (f.mean(0) - c) > 0


def test_runner_interface_and_allowed_positions():
    s = OfficeSetup()
    assert s.robot_rotation(0.0).shape == (3, 3) and np.allclose(s.robot_rotation(90.0) @ [1, 0, 0], [0, 1, 0], atol=1e-12)
    assert len(s.yaw_sweep_deg) == 19 and s.yaw_sweep_deg[-1] == 180.0
    assert all(s.position_allowed(x, y) for x, y in s.example_xy_m)
    assert not s.position_allowed(1.85, 10.15)  # inside the first island
    g = s.link_geometry(s.anchor_x_m, s.anchor_y_m)
    assert abs(g["anchor_off_boresight_deg"]) < 1e-6 and np.isclose(g["range_m"], s.anchor_position[2] - s.robot_antenna_z_m)


def test_every_object_is_exactly_one_flat_sheet():
    """Sionna RT applies a full slab to every intersected surface, so a physical slab must be ONE sheet (no closed boxes)."""
    for o in OfficeSetup().objects():
        assert len(o["quads"]) == 1
        q = np.asarray(o["quads"][0])
        assert q.shape == (4, 3)
        n = np.cross(q[1] - q[0], q[3] - q[0])
        assert np.allclose([(q[2] - q[0]) @ n], [0.0], atol=1e-9)  # planar


def test_a_straight_line_crosses_each_object_at_most_once():
    s = OfficeSetup()
    rng = np.random.default_rng(1)
    for _ in range(200):
        p0 = rng.uniform([0, 0, 0.05], [s.length_m, s.width_m, 2.6])
        p1 = rng.uniform([0, 0, 0.05], [s.length_m, s.width_m, 2.6])
        for o in s.objects():
            # a single planar sheet is crossed at most once by a segment: both end points on the same side => no crossing
            q = np.asarray(o["quads"][0])
            n = np.cross(q[1] - q[0], q[3] - q[0])
            if np.sign((p0 - q[0]) @ n) == np.sign((p1 - q[0]) @ n):
                assert not segment_hits_quad(p0, p1, q)


def test_segment_quad_hits():
    quad = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    assert segment_hits_quad((0.5, 0.5, -1), (0.5, 0.5, 1), quad)
    assert not segment_hits_quad((0.5, 0.5, 0.2), (0.5, 0.5, 1), quad)
    assert not segment_hits_quad((2.0, 0.5, -1), (2.0, 0.5, 1), quad)


def test_geometric_los_uses_the_rf_sheets():
    s = OfficeSetup()
    blocked = [(x, y) for x, y in s.example_xy_m if not s.los_status(x, y)["clear"]]
    assert blocked
    names = {b for x, y in blocked for b in s.los_status(x, y)["blockers"]}
    assert names and all(n.startswith(("partition_", "desk_")) for n in names)
