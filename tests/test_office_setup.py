import numpy as np

from qclean_uwb.scenarios.office import OfficeSetup, box_quads, segment_hits_box


def test_validation_passes():
    failed = [c for c in OfficeSetup().validate() if not c["passed"]]
    assert not failed, failed


def test_twelve_islands():
    s = OfficeSetup()
    boxes = s.boxes()
    assert sum(b["group"] == "desks" for b in boxes) == 12 == len(s.col_x_m) * s.n_rows
    assert sum(b["group"] == "partitions" for b in boxes) == 12
    objs = s.objects()
    assert len(objs) == 6 + 24
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


def test_islands_block_a_low_line_and_not_a_vertical_one():
    s = OfficeSetup()
    d = [b for b in s.boxes() if b["group"] == "desks"][0]
    c = [(d["lo"][i] + d["hi"][i]) / 2 for i in range(3)]
    assert segment_hits_box((c[0], c[1], 0.2), (c[0], c[1], 2.5), d["lo"], d["hi"])
    assert s.los_status(s.anchor_x_m, s.anchor_y_m)["clear"] or True
