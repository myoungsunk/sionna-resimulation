"""Frozen calibration-only tables for an exploratory EKF s residual model.

Distance is the geometric link length. Phase is antenna yaw modulo 90 degrees
relative to fixed world axes: it is NOT measured polarization alignment.
Cell RMS includes bias; it does not assert independent zero-mean noise.
"""
from dataclasses import dataclass
import numpy as np


def antenna_phase_deg(heading_rad, mount_deg=0.0):
    return np.abs((np.degrees(heading_rad) + mount_deg + 45.0) % 90.0 - 45.0)


@dataclass
class ResidualTable:
    distance_edges: tuple
    phase_edges: tuple
    scalar_rms: float
    distance_rms: np.ndarray
    joint_rms: np.ndarray
    distance_support: tuple
    mode: str = "constant"

    def __post_init__(self):
        if self.mode not in ("constant", "distance", "joint"):
            raise ValueError("UNKNOWN_UNCERTAINTY_MODE")
        if not np.isfinite(self.scalar_rms) or self.scalar_rms <= 0:
            raise ValueError("INVALID_FALLBACK_RMS")
        for edges in (self.distance_edges, self.phase_edges):
            if not np.isfinite(edges).all() or np.any(np.diff(edges) <= 0):
                raise ValueError("INVALID_UNCERTAINTY_EDGES")
        if np.shape(self.distance_rms) != (len(self.distance_edges) + 1,):
            raise ValueError("INVALID_DISTANCE_TABLE")
        if np.shape(self.joint_rms) != (len(self.distance_edges) + 1, len(self.phase_edges) + 1):
            raise ValueError("INVALID_JOINT_TABLE")
        for table in (self.distance_rms, self.joint_rms):
            if np.isinf(table).any() or np.any(np.asarray(table)[np.isfinite(table)] <= 0):
                raise ValueError("INVALID_TABLE_RMS")
        if len(self.distance_support) != 2 or not np.isfinite(self.distance_support).all() or self.distance_support[0] > self.distance_support[1]:
            raise ValueError("INVALID_DISTANCE_SUPPORT")

    def sigma(self, xy, heading_rad, anchor_xyz, robot_z, mount_deg):
        xy = np.asarray(xy, float)
        if not np.isfinite(xy).all() or not np.isfinite(heading_rad):
            raise ValueError("NONFINITE_ONLINE_STATE")
        d = float(np.linalg.norm(np.r_[xy, robot_z] - anchor_xyz))
        if self.mode == "constant" or not self.distance_support[0] <= d <= self.distance_support[1]:
            return self.scalar_rms
        i = int(np.searchsorted(self.distance_edges, d))
        fallback = float(self.distance_rms[i])
        if not np.isfinite(fallback):
            fallback = self.scalar_rms
        if self.mode == "distance":
            return fallback
        j = int(np.searchsorted(self.phase_edges, antenna_phase_deg(heading_rad, mount_deg)))
        value = float(self.joint_rms[i, j])
        return value if np.isfinite(value) else fallback
