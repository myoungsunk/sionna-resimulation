import math

import numpy as np
import pytest

from qclean_uwb.drivesim import routes as R
from qclean_uwb.drivesim.trajectory import TrajectoryConfig, rf_tasks, unique_poses


def rows(name, T=None, seed=20261007, **kw):
    return R.build_route_samples(R.SPECS[name](), TrajectoryConfig(wobble_seed=seed, probe_period_s=T, **kw))


def test_zigzag_geometry_matches_the_figure():
    spec = R.r4_spec()
    assert len(spec.legs) == 14 and spec.legs[0].heading_deg == 35.7 and spec.legs[1].heading_deg == -35.7
    assert spec.legs[0].length_m == pytest.approx(0.9 / math.sin(math.radians(35.7)))
    assert 14 * 0.9 / math.tan(math.radians(35.7)) == pytest.approx(17.53, abs=0.02)        # x extent 1.2 -> 18.73


def test_nominal_endpoints_and_lanes():
    r2 = R.r2_spec()
    x = r2.start[0] + sum(l.length_m * math.cos(math.radians(l.heading_deg)) for l in r2.legs)
    y = r2.start[1] + sum(l.length_m * math.sin(math.radians(l.heading_deg)) for l in r2.legs)
    assert x == pytest.approx(r2.start[0], abs=1e-9) and y == pytest.approx(r2.start[1], abs=1e-9)           # closed rectangle
    r5 = R.r5_spec()
    ys = np.cumsum([0.0] + [l.length_m * math.sin(math.radians(l.heading_deg)) for l in r5.legs]) + r5.start[1]
    assert sorted(set(np.round(ys, 6))) == [-0.45, 0.0, 0.45]


@pytest.mark.parametrize("name", ["R2", "R4", "R5"])
def test_samples_are_kinematically_consistent_and_turns_are_flagged(name):
    r = rows(name, T=20.0)
    for a, b in zip(r, r[1:]):
        moved = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
        if b["phase"] == "drive" and b["drive_g"] == a["drive_g"] + 1:
            assert moved == pytest.approx(0.04, abs=1e-12)
            ang = math.atan2(b["y"] - a["y"], b["x"] - a["x"]) - math.radians(a["yaw_body_deg"])
            assert math.sin(ang) == pytest.approx(0.0, abs=1e-9) and math.cos(ang) > 0
        else:
            assert moved == pytest.approx(0.0, abs=1e-12)           # turns and probes are in place
    assert any(x["turn_phase"] for x in r) and all(x["turn_phase"] == (x["phase"] == "turn") for x in r)
    steps = np.abs(np.diff([x["yaw_body_deg"] for x in r if x["phase"] in ("drive", "turn")]))
    assert steps.max() < 6.0                                          # no jumps at corners (wobble keeps the sample step small)


def test_corner_turn_counts_and_total_lengths():
    def n(name):
        r = rows(name)
        return sum(1 for a, b in zip(r, r[1:]) if a["phase"] != "turn" and b["phase"] == "turn")
    assert n("R2") == 3 and n("R4") == 13 and n("R5") == 4
    assert rows("R2")[-1]["drive_g"] == pytest.approx(round(0.9 / 0.04) * 2 + round(17.6 / 0.04) * 2)


def test_probe_sets_nested_and_pose_union_covers_all_variants():
    def stations(T):
        return {(r["x"], r["y"]) for r in rows("R4", T) if r["phase"] == "probe"}
    assert stations(20.0) <= stations(10.0) and stations(60.0) <= stations(20.0)
    variants = [rows("R5", T) for T in (None, 10.0, 20.0, 60.0)]
    poses, ids = unique_poses(variants)
    assert all(len(i) == len(v) for i, v in zip(ids, variants))
    assert len(rf_tasks(poses, 0.0)) <= len(poses)


@pytest.mark.parametrize("name", ["R2", "R4", "R5"])
def test_guards_select_a_seed_and_hold(name):
    spec = R.SPECS[name]()
    seed, worst = R.choose_wobble_seed(spec, TrajectoryConfig())
    r = rows(name, 10.0, seed=seed)
    assert min(R.anchor_clearance(r).values()) >= 0.02
    assert max(abs(x["y"]) for x in r) <= 0.74 and 1.0 <= min(x["x"] for x in r) and max(x["x"] for x in r) <= 19.0
