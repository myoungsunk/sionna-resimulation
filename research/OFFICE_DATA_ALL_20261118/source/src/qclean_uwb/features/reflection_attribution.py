"""Link a distorted yaw-sweep curve to the actual specular reflection paths.

* ``image_delays`` enumerates specular reflection sequences (up to depth 3) of a rectangular corridor
  with the image method and returns their exact delays.
* ``classify_paths`` assigns each simulated path (by delay) to LoS, a single-bounce surface group, or
  multi-bounce.  Delay matching does not depend on stored object ids; where two surfaces give the same delay
  (robot on the corridor axis) the side walls share one group.
* ``fit_abs_cos`` fits ``r(yaw) = m * |cos(2 (yaw - yaw0))|``.  For ideal +-45 deg ports an elliptically
  polarised incident field gives exactly this curve: ``m`` is the ellipse purity ``2uv/(u^2+v^2)`` (1 = linear)
  and ``yaw0`` its tilt, so reflections that add an unequal circular component lower ``m`` and shift ``yaw0``.
"""
from __future__ import annotations

import itertools

import numpy as np
from scipy.optimize import least_squares

C0 = 299792458.0
GROUPS = ("los", "floor", "ceiling", "side_walls", "end_walls", "multi_bounce")
_SURFACE_GROUP = {"floor": "floor", "ceiling": "ceiling", "wall_y_neg": "side_walls", "wall_y_pos": "side_walls",
                  "end_x_min": "end_walls", "end_x_max": "end_walls"}


def planes(length, half_width, height):
    return {"floor": (2, 0.0), "ceiling": (2, height), "wall_y_neg": (1, -half_width), "wall_y_pos": (1, half_width),
            "end_x_min": (0, 0.0), "end_x_max": (0, length)}


def _mirror(point, plane):
    axis, coord = plane
    q = np.array(point, float)
    q[axis] = 2.0 * coord - q[axis]
    return q


def image_delays(tx, rx, length, half_width, height, max_order=3):
    """Return ``{sequence: delay_s}`` for all reflection sequences without immediate repeats; () is LoS."""
    pl = planes(length, half_width, height)
    out = {(): float(np.linalg.norm(np.asarray(rx, float) - np.asarray(tx, float))) / C0}
    for order in range(1, max_order + 1):
        for seq in itertools.product(pl, repeat=order):
            if any(a == b for a, b in zip(seq, seq[1:])):
                continue
            img = np.asarray(rx, float)
            for name in reversed(seq):
                img = _mirror(img, pl[name])
            out[seq] = float(np.linalg.norm(np.asarray(tx, float) - img)) / C0
    return out


def classify_paths(tau, tx, rx, length, half_width, height, tol=5e-14):
    """Group index (into GROUPS) per path, plus -1 for unmatched; also the reflection order per path."""
    table = image_delays(tx, rx, length, half_width, height)
    seqs = list(table)
    d = np.array([table[s] for s in seqs])
    order = np.array([len(s) for s in seqs])
    tau = np.asarray(tau, float)
    pick = np.abs(tau[:, None] - d[None, :]).argmin(axis=1)
    ok = np.abs(tau - d[pick]) <= tol
    label = np.full(tau.shape, -1, int)
    for i, p in enumerate(pick):
        if not ok[i]:
            continue
        seq = seqs[p]
        label[i] = 0 if len(seq) == 0 else (GROUPS.index(_SURFACE_GROUP[seq[0]]) if len(seq) == 1 else GROUPS.index("multi_bounce"))
    return label, np.where(ok, order[pick], -1), table


def fit_abs_cos(yaw_deg, ratio):
    """Fit ``m * |cos(2 (yaw - yaw0))|``; returns (m, yaw0_deg in [-45, 45), rmse)."""
    y = np.radians(np.asarray(yaw_deg, float))
    r = np.asarray(ratio, float)
    best = None
    for y0 in np.radians(np.arange(-45.0, 45.0, 5.0)):
        for m0 in (0.5, 1.0):
            res = least_squares(lambda p: p[0] * np.abs(np.cos(2 * (y - p[1]))) - r, [m0, y0], bounds=([0.0, -np.pi], [2.0, np.pi]))
            if best is None or res.cost < best.cost:
                best = res
    m, y0 = best.x
    y0 = (np.degrees(y0) + 45.0) % 90.0 - 45.0
    return float(m), float(y0), float(np.sqrt(2 * best.cost / len(r)))
