"""AMENDMENT-003 §E: RF cache key. Pure function; not yet used by any RT run.

A channel may be reused only when every physical and numerical input is identical. pose_key() (world.py) identifies a
pose for the synthetic field; it is NOT an RF cache key because it does not hash the scene mesh/materials, solver or
FFD/extractor settings.
"""
from __future__ import annotations

import hashlib
import json
import math

REQUIRED = ("scene_geometry_sha256", "materials_sha256", "anchor_xyz_m", "pose_xy_m", "yaw_deg", "robot_z_m", "mount_deg",
            "ffd_bank_sha256", "solver", "solver_version", "max_depth", "solver_flags", "freq_grid_sha256", "extractor_sha256")


def canonical_yaw_deg(yaw_deg: float) -> float:
    d = round(float(yaw_deg) % 360.0, 9)
    return 0.0 if d == 360.0 else d


def _num(v, nd=9):
    if isinstance(v, (list, tuple)):
        return [_num(x, nd) for x in v]
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("ERR_RF_KEY non-finite value")
        return round(v, nd) + 0.0
    return v


def rf_cache_key(spec: dict) -> str:
    missing = [k for k in REQUIRED if k not in spec]
    if missing:
        raise ValueError(f"ERR_RF_KEY missing fields {missing}")
    extra = sorted(set(spec) - set(REQUIRED))
    if extra:
        raise ValueError(f"ERR_RF_KEY unknown fields {extra}")
    for k in ("scene_geometry_sha256", "materials_sha256", "freq_grid_sha256", "extractor_sha256"):
        if not (isinstance(spec[k], str) and len(spec[k]) == 64 and all(c in "0123456789abcdef" for c in spec[k])):
            raise ValueError(f"ERR_RF_KEY {k} must be a sha256 hex digest")
    obj = {k: _num(spec[k]) for k in REQUIRED}
    obj["yaw_deg"] = canonical_yaw_deg(spec["yaw_deg"])
    obj["ffd_bank_sha256"] = sorted(spec["ffd_bank_sha256"])
    obj["solver_flags"] = {k: _num(v) for k, v in sorted(dict(spec["solver_flags"]).items())}
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
