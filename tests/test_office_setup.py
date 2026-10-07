import numpy as np

from qclean_uwb.scenarios.office import OfficeSetup, box_quads, segment_hits_box


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
    assert len(objs) == 6 + 36
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
