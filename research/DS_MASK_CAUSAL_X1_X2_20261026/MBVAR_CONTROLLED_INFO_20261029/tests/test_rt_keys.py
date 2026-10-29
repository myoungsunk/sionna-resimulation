"""AMENDMENT-003 §E: RF cache key must change with every physical/numerical input and be invariant to yaw 0/360."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import rt_keys as K  # noqa: E402

H = "a" * 64


def base():
    return dict(scene_geometry_sha256=H, materials_sha256="b" * 64, anchor_xyz_m=[2.0, 2.0, 2.65], pose_xy_m=[3.0, 7.0], yaw_deg=0.0,
                robot_z_m=0.45, mount_deg=0.0, ffd_bank_sha256=["c" * 64, "d" * 64], solver="sionna-rt", solver_version="X",
                max_depth=3, solver_flags=dict(los=True, specular=True, diffuse=False), freq_grid_sha256="e" * 64, extractor_sha256="f" * 64)


def test_yaw_0_360_same_key():
    a = base(); b = base(); b["yaw_deg"] = 360.0
    assert K.rf_cache_key(a) == K.rf_cache_key(b)


@pytest.mark.parametrize("field,val", [("scene_geometry_sha256", "1" * 64), ("materials_sha256", "2" * 64), ("anchor_xyz_m", [2.0, 2.0, 2.6]),
                                       ("pose_xy_m", [3.0, 7.05]), ("yaw_deg", 5.0), ("robot_z_m", 0.5), ("mount_deg", 90.0),
                                       ("ffd_bank_sha256", ["c" * 64, "0" * 64]), ("solver_version", "Y"), ("max_depth", 2),
                                       ("solver_flags", dict(los=True, specular=True, diffuse=True)), ("freq_grid_sha256", "3" * 64),
                                       ("extractor_sha256", "4" * 64)])
def test_every_input_changes_key(field, val):
    a = base(); b = base(); b[field] = val
    assert K.rf_cache_key(a) != K.rf_cache_key(b)


def test_bank_order_irrelevant_flag_order_irrelevant():
    a = base(); b = base(); b["ffd_bank_sha256"] = list(reversed(b["ffd_bank_sha256"])); b["solver_flags"] = dict(diffuse=False, specular=True, los=True)
    assert K.rf_cache_key(a) == K.rf_cache_key(b)


def test_negative_missing_or_bad_digest():
    a = base(); del a["materials_sha256"]
    with pytest.raises(ValueError):
        K.rf_cache_key(a)
    b = base(); b["scene_geometry_sha256"] = "scene_C10"
    with pytest.raises(ValueError):
        K.rf_cache_key(b)
