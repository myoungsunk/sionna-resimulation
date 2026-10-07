import numpy as np

from qclean_uwb.scenarios.office import OfficeSetup, box_quads, segment_hits_box


def test_validation_passes():
    s = OfficeSetup()
    failed = [c for c in s.validate() if not c["passed"]]
    assert not failed, failed


def test_object_counts():
    s = OfficeSetup()
    boxes = s.boxes()
    assert sum(b["group"] == "desks" for b in boxes) == 2 * 2 * s.n_cubicles
    assert sum(b["group"] == "partitions" for b in boxes) == 2 * (1 + 2 * (s.n_cubicles + 1))
    objs = s.objects()
    assert len(objs) == 6 + len(boxes)
    assert {o["group"] for o in objs} == {"floor", "ceiling", "outer_walls", "partitions", "desks"}
    assert all(len(o["quads"]) in (1, 6) for o in objs)


def test_box_quads_are_planar_and_closed():
    quads = box_quads((0, 0, 0), (1, 2, 3))
    assert len(quads) == 6
    area = sum(np.linalg.norm(np.cross(q[1] - q[0], q[3] - q[0])) for q in quads)
    assert np.isclose(area, 2 * (1 * 2 + 1 * 3 + 2 * 3))


def test_segment_box_hits():
    lo, hi = (0, 0, 0), (1, 1, 1)
    assert segment_hits_box((-1, 0.5, 0.5), (2, 0.5, 0.5), lo, hi)
    assert not segment_hits_box((-1, 2, 0.5), (2, 2, 0.5), lo, hi)
    assert not segment_hits_box((2, 0.5, 0.5), (3, 0.5, 0.5), lo, hi)


def test_sample_points_are_in_aisles_and_los_is_mixed():
    s = OfficeSetup()
    pts = s.sample_points()
    assert len(pts) > 20
    assert all(s.in_aisle(x, y) for x, y in pts)
    flags = [s.los_status(x, y)["clear"] for x, y in pts]
    assert any(flags) and not all(flags)
    # tag right below the anchor sees it
    assert s.los_status(s.anchor_x_m, s.anchor_y_m)["clear"]


def test_desk_inside_notch_blocks_a_low_antenna_line():
    s = OfficeSetup()
    d = [b for b in s.boxes() if b["group"] == "desks"][0]
    centre = [(d["lo"][i] + d["hi"][i]) / 2 for i in range(3)]
    assert segment_hits_box((centre[0], centre[1], 0.2), (centre[0], centre[1], 2.5), d["lo"], d["hi"])
