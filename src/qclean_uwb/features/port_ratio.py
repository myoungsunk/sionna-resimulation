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


def los_two_port_ratio(yaw_deg, tx_port: str = "LP_plus45") -> np.ndarray:
    """Ideal on-axis LoS curve for a ceiling anchor and an up-facing robot.

    Ideal +45/-45 ports, boresights facing each other.  The anchor is flipped by
    diag(1,-1,-1), so its local +45 port radiates along world angle -45 deg and its -45
    port along +45 deg.  Robot RX ports lie at world angles 45+yaw (p1) and -45+yaw (p2).

    * anchor TX +45: p1 ~ -sin(yaw), p2 ~ cos(yaw)  ->  ratio = |tan(yaw + 45 deg)|
    * anchor TX -45: p1 ~  cos(yaw), p2 ~ sin(yaw)  ->  ratio = |tan(yaw - 45 deg)|
    """
    yaw = np.radians(np.asarray(yaw_deg, dtype=float))
    if tx_port == "LP_plus45":
        return port_difference_ratio(-np.sin(yaw), np.cos(yaw))
    if tx_port == "LP_minus45":
        return port_difference_ratio(np.cos(yaw), np.sin(yaw))
    raise ValueError(f"unknown tx_port {tx_port!r}")
