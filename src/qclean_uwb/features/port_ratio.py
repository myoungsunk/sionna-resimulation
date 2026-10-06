"""Two-port difference/sum ratio used for the corridor yaw sweep.

``ratio = |p1 - p2| / |p1 + p2|`` with p1, p2 the complex responses of the two
polarization ports (here the +45 / -45 pair).  The ratio is unbounded when
p1 = -p2, so near-zero denominators are returned as ``inf`` instead of being
clipped.
"""
from __future__ import annotations

import numpy as np


def port_difference_ratio(p1, p2) -> np.ndarray:
    p1 = np.asarray(p1, dtype=complex)
    p2 = np.asarray(p2, dtype=complex)
    num = np.abs(p1 - p2)
    den = np.abs(p1 + p2)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0.0, num / den, np.inf)


def los_two_port_ratio(yaw_deg) -> np.ndarray:
    """Ideal on-axis LoS curve for a ceiling anchor and an up-facing robot.

    Ideal +45/-45 ports, boresights facing each other, anchor TX port +45
    (world E-angle -45 deg because the anchor is flipped by diag(1,-1,-1)).
    Robot RX ports lie at world angles 45+yaw and -45+yaw, so
    p1 ~ -sin(yaw), p2 ~ cos(yaw) and ratio = |tan(yaw + 45 deg)|.
    """
    yaw = np.radians(np.asarray(yaw_deg, dtype=float))
    return port_difference_ratio(-np.sin(yaw), np.cos(yaw))
