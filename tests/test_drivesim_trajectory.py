import math

import numpy as np
import pytest

from qclean_uwb.drivesim.trajectory import (TrajectoryConfig, check_anchor_axis_clearance, build_samples, check_region, motion_increments, probe_offsets_deg,
                                            rf_tasks, unique_poses)


def rows(**kw):
    return build_samples(TrajectoryConfig(**kw))


def test_probe_sequence_has_36_samples_19_distinct_yaws_and_returns_to_zero():
    o = probe_offsets_deg()
    assert len(o) == 36 and o[-1] == 0.0 and len(set(o) | {0.0}) == 19 and min(o) == -45 and max(o) == 45


def test_sample_counts_without_and_with_probe():
    n0 = len(rows(probe_period_s=None))
    assert n0 == 441 + 36 + 440
    n10 = len(rows(probe_period_s=10.0))
    probes = sum(1 for r in rows(probe_period_s=10.0) if r["phase"] == "probe") // 36
    assert n10 == n0 + 36 * probes and probes == 17   # g multiples of 50 in 1..879 -> 17


def test_drive_poses_do_not_depend_on_probe_period():
    a = [r for r in rows(probe_period_s=None) if r["phase"] != "probe"]
    b = [r for r in rows(probe_period_s=20.0) if r["phase"] != "probe"]
    assert [(r["x"], r["y"], r["yaw_body_deg"]) for r in a] == [(r["x"], r["y"], r["yaw_body_deg"]) for r in b]


def test_probe_sets_are_nested_by_drive_time():
    def stations(T):
        return {(r["x"], r["y"]) for r in rows(probe_period_s=T) if r["phase"] == "probe"}
    assert stations(20.0) <= stations(10.0) and stations(60.0) <= stations(20.0)


def test_kinematic_consistency_position_follows_heading():
    r = rows(probe_period_s=10.0)
    for a, b in zip(r, r[1:]):
        if a["phase"] in ("drive_out", "drive_back") and b["phase"] == a["phase"] and b["drive_g"] == a["drive_g"] + 1:
            d = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
            assert d == pytest.approx(0.04, abs=1e-12)
            assert math.atan2(b["y"] - a["y"], b["x"] - a["x"]) == pytest.approx(math.radians(a["yaw_body_deg"]), abs=1e-9) or a["phase"] == "drive_back"


def test_stationary_during_probe_and_turn_and_wobble_held():
    r = rows(probe_period_s=10.0)
    for ph in ("probe", "turn"):
        sel = [x for x in r if x["phase"] == ph]
        assert sel
    for pid in range(17):
        p = [x for x in r if x["probe_id"] == pid]
        assert len({(x["x"], x["y"]) for x in p}) == 1 and len(p) == 36
        base = p[-1]["yaw_body_deg"]          # last sample is offset 0 -> the held heading
        assert all(x["yaw_body_deg"] == pytest.approx(base + x["probe_offset_deg"]) for x in p)
    turn = [x for x in r if x["phase"] == "turn"]
    assert len(turn) == 36 and all(t["turn_phase"] for t in turn) and not any(x["turn_phase"] for x in r if x["phase"] != "turn")
    inc = np.diff([t["yaw_body_deg"] for t in turn])
    assert np.allclose(inc, 5.0)


def test_heading_is_continuous_across_turn_and_stays_in_region():
    r = rows(probe_period_s=10.0)
    yaw = [x["yaw_body_deg"] for x in r if x["phase"] in ("drive_out", "turn", "drive_back")]
    assert max(abs(np.diff(yaw))) <= 5.0 + 2 * 4.0 * 2 * math.pi / 12 * 0.2 + 1e-9
    check_region(r)
    for y0 in (0.0, 0.35):
        check_region(rows(y0_m=y0, probe_period_s=10.0))


def test_wobble_bounded_and_deterministic():
    r = rows()
    out = [x["yaw_body_deg"] for x in r if x["phase"] == "drive_out"]
    assert max(abs(v) for v in out) <= 4.0 + 1e-9
    assert rows() == rows()


def test_unique_poses_and_tasks_cover_every_sample_and_mount_shifts_yaw_only():
    variants = [rows(probe_period_s=T) for T in (None, 10.0, 20.0, 60.0)]
    poses, ids = unique_poses(variants)
    assert all(len(i) == len(v) for i, v in zip(ids, variants))
    assert len(poses) == len({p["pose_id"] for p in poses})
    t0, t45 = rf_tasks(poses, 0.0), rf_tasks(poses, 45.0)
    assert sum(len(t["pose_ids"]) for t in t0) == len(poses)
    assert [t["tag"] for t in t0] == [t["tag"] for t in t45]
    for a, b in zip(t0, t45):
        assert [y + 45.0 for y in a["antenna_yaw_deg"]] == pytest.approx(b["antenna_yaw_deg"])
    probe_task = max(t0, key=lambda t: len(t["antenna_yaw_deg"]))
    assert len(probe_task["antenna_yaw_deg"]) >= 19


def test_motion_increments_zero_path_during_rotation():
    r = rows(probe_period_s=10.0)
    m = motion_increments(r)
    idx = [i for i, x in enumerate(r) if x["phase"] in ("probe", "turn")]
    assert np.allclose(m["ds_m"][idx[1:]], 0.0, atol=1e-12) or np.allclose([m["ds_m"][i] for i in idx if r[i - 1]["phase"] == r[i]["phase"]], 0.0)


def test_anchor_axis_clearance_guard():
    r = rows(probe_period_s=10.0)
    assert check_anchor_axis_clearance(r) > 0.01
    with pytest.raises(ValueError):
        check_anchor_axis_clearance(r, anchor_xy=(r[10]["x"], r[10]["y"]))
