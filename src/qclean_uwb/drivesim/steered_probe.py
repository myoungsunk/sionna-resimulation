"""A18 steered probe: rotate in place to the heading at which the port power ratio is steepest, dwell, rotate back (36 samples).

Ideal model: s = -cos 2(psi + mount + 180 deg) is a function of the antenna yaw psi + mount only; the slope is steepest at psi + mount = 45 deg (mod 90).
"""
from __future__ import annotations

import math

N_PROBE = 36
STEP_DEG = 5.0


def target_offset_deg(base_deg: float, mount_deg: float, err_deg: float = 0.0) -> float:
    """Rotation Delta in [-45, 45) that brings the (estimated) antenna yaw to the nearest 45 deg (mod 90)."""
    return ((45.0 - mount_deg - (base_deg + err_deg) + 45.0) % 90.0) - 45.0


def steer_offsets_deg(base_deg: float, mount_deg: float, err_deg: float = 0.0, n: int = N_PROBE, step: float = STEP_DEG) -> list[float]:
    """Relative yaw of the ``n`` probe samples: ramp to the commanded rotation, dwell, ramp back to 0 (never faster than ``step`` per sample)."""
    delta = target_offset_deg(base_deg, mount_deg, err_deg)
    n_r = max(1, math.ceil(abs(delta) / step - 1e-12))
    ramp = [delta * i / n_r for i in range(1, n_r + 1)]
    back = [delta * (n_r - i) / n_r for i in range(1, n_r + 1)]
    dwell = n - 2 * n_r
    if dwell < 0:
        raise ValueError("rotation does not fit the probe budget")
    return ramp + [delta] * dwell + back


def steer_rows(rows: list[dict], mount_deg: float, err_deg: float = 0.0) -> list[dict]:
    """Rewrite the yaw of every probe segment of a timeline (rows with ``probe_id``, ``probe_offset_deg``, ``yaw_body_deg``); everything else is kept."""
    out = [dict(r) for r in rows]
    i = 0
    while i < len(out):
        pid = out[i]["probe_id"]
        if pid < 0:
            i += 1
            continue
        j = i
        while j < len(out) and out[j]["probe_id"] == pid:
            j += 1
        base = out[i]["yaw_body_deg"] - out[i]["probe_offset_deg"]
        offs = steer_offsets_deg(base, mount_deg, err_deg, n=j - i)
        for k, off in zip(range(i, j), offs):
            out[k]["yaw_body_deg"] = base + off
            out[k]["probe_offset_deg"] = off
        i = j
    return out
