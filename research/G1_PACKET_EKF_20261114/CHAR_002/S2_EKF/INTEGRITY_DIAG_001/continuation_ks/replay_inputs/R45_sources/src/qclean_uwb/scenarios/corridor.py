"""Corridor scenario: ceiling anchor (boresight down) and floor robot (antenna fixed z).

Conventions follow the existing native Sionna inputs (Z-up, right-handed, metres):

* An antenna's local +z is its boresight (theta = 0 of the FFD bank).
* ``rotation`` maps antenna-local axes to world axes (columns = local x, y, z in world).
* Ceiling anchors use ``diag(1, -1, -1)`` (the same matrix used for `tx_rotation` in
  `SIONNA_NATIVE41_REFRESH_*/CONFIG.json`), so boresight points to world -z.
* The robot antenna uses ``Rz(yaw)``, so boresight points to world +z.
* Dual linear ports are the +45 / -45 pair (``LP_plus45``, ``LP_minus45``; arm ``LP_DIAG``).
  Their nominal E-field directions at boresight are (x + y)/sqrt2 and (x - y)/sqrt2 in the
  antenna-local frame. This is nominal; it has not been read back from the FFD banks.

All numeric defaults below are placeholders chosen for the first visualisation, not
measured values. Override them through ``CorridorSetup``.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

import numpy as np

PORT_PAIR = ("LP_plus45", "LP_minus45")
ARM = "LP_DIAG"
ANCHOR_ROTATION = np.diag([1.0, -1.0, -1.0])
_INV_SQRT2 = 1.0 / math.sqrt(2.0)
PORT_LOCAL_E = {
    "LP_plus45": np.array([_INV_SQRT2, _INV_SQRT2, 0.0]),
    "LP_minus45": np.array([_INV_SQRT2, -_INV_SQRT2, 0.0]),
}


def rot_z(yaw_deg: float) -> np.ndarray:
    """Body-to-world rotation for a pure yaw (counter-clockwise seen from +z)."""
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def is_rotation(matrix: np.ndarray, atol: float = 1e-9) -> bool:
    m = np.asarray(matrix, dtype=float).reshape(3, 3)
    return bool(np.allclose(m.T @ m, np.eye(3), atol=atol) and np.isclose(np.linalg.det(m), 1.0, atol=atol))


@dataclass(frozen=True)
class CorridorSetup:
    # Corridor interior; x along the corridor, y across, z up. Floor top at z = 0.
    length_m: float = 20.0
    width_m: float = 2.4
    height_m: float = 2.7
    # Anchor: ceiling mounted, centred across the corridor.
    anchor_x_m: float = 4.0
    anchor_y_m: float = 0.0
    anchor_standoff_m: float = 0.05  # antenna reference point below the ceiling
    # Robot: antenna reference point height is fixed; xy and yaw vary.
    robot_antenna_z_m: float = 0.45
    robot_body_lwh_m: tuple = (0.60, 0.40, 0.40)  # along heading, across, height
    robot_clearance_m: float = 0.10  # keep-out between robot body and walls
    robot_x_range_m: tuple = (1.0, 19.0)
    # Example robot placement shown in the figure, plus the yaw sweep.
    # Index 0 is directly below the anchor; the rest are spread along the corridor.
    example_xy_m: tuple = ((4.0, 0.0), (7.0, 0.35), (11.0, -0.5), (15.0, 0.0))
    main_index: int = 1  # the position drawn with the yaw-sweep ring
    yaw_sweep_deg: tuple = tuple(float(a) for a in range(0, 181, 10))
    yaw_display_deg: float = 30.0
    port_pair: tuple = PORT_PAIR
    arm: str = ARM

    # ---- derived geometry -------------------------------------------------
    @property
    def y_half(self) -> float:
        return self.width_m / 2.0

    @property
    def robot_y_limit_m(self) -> float:
        """Largest |y| for the robot centre so that a rotated body still clears the walls."""
        l, w, _ = self.robot_body_lwh_m
        return self.y_half - self.robot_clearance_m - math.hypot(l, w) / 2.0

    @property
    def anchor_position(self) -> np.ndarray:
        return np.array([self.anchor_x_m, self.anchor_y_m, self.height_m - self.anchor_standoff_m])

    def robot_position(self, x: float, y: float) -> np.ndarray:
        return np.array([x, y, self.robot_antenna_z_m])

    def robot_rotation(self, yaw_deg: float) -> np.ndarray:
        return rot_z(yaw_deg)

    def surfaces(self) -> dict:
        """Six interior boundary quads (4 corners each, counter-clockwise from inside)."""
        L, h, H = self.length_m, self.y_half, self.height_m
        q = lambda *pts: np.array(pts, dtype=float)
        return {
            "floor": q((0, -h, 0), (L, -h, 0), (L, h, 0), (0, h, 0)),
            "ceiling": q((0, -h, H), (0, h, H), (L, h, H), (L, -h, H)),
            "wall_y_neg": q((0, -h, 0), (0, -h, H), (L, -h, H), (L, -h, 0)),
            "wall_y_pos": q((0, h, 0), (L, h, 0), (L, h, H), (0, h, H)),
            "end_x_min": q((0, -h, 0), (0, h, 0), (0, h, H), (0, -h, H)),
            "end_x_max": q((L, -h, 0), (L, -h, H), (L, h, H), (L, h, 0)),
        }

    def antenna_frame(self, rotation: np.ndarray) -> dict:
        """Boresight and the two port E-field directions in world coordinates."""
        r = np.asarray(rotation, dtype=float)
        return {
            "boresight": r @ np.array([0.0, 0.0, 1.0]),
            **{p: r @ PORT_LOCAL_E[p] for p in self.port_pair},
        }

    def link_geometry(self, x: float, y: float, yaw_deg: float) -> dict:
        """Range and off-boresight angles of the anchor <-> robot line of sight."""
        a, r = self.anchor_position, self.robot_position(x, y)
        d = r - a
        rng = float(np.linalg.norm(d))
        u = d / rng
        bore_a = ANCHOR_ROTATION @ np.array([0.0, 0.0, 1.0])
        bore_r = self.robot_rotation(yaw_deg) @ np.array([0.0, 0.0, 1.0])
        off_a = math.degrees(math.acos(float(np.clip(bore_a @ u, -1, 1))))
        off_r = math.degrees(math.acos(float(np.clip(bore_r @ -u, -1, 1))))
        # Direction of the other terminal expressed in each antenna's local frame (theta, phi).
        la = ANCHOR_ROTATION.T @ u
        lr = self.robot_rotation(yaw_deg).T @ -u
        phi_a = math.degrees(math.atan2(la[1], la[0]))
        phi_r = math.degrees(math.atan2(lr[1], lr[0]))
        return dict(range_m=rng, anchor_off_boresight_deg=off_a, robot_off_boresight_deg=off_r,
                    anchor_phi_deg=phi_a, robot_phi_deg=phi_r,
                    horizontal_m=float(np.hypot(d[0], d[1])), vertical_m=float(-d[2]))

    # ---- validation -------------------------------------------------------
    def validate(self) -> list[dict]:
        """Return named checks; each has ``name``, ``passed`` and ``detail``."""
        checks = []

        def add(name, passed, detail=""):
            checks.append(dict(name=name, passed=bool(passed), detail=detail))

        a = self.anchor_position
        add("anchor_inside_corridor", 0 < a[0] < self.length_m and abs(a[1]) < self.y_half and 0 < a[2] < self.height_m,
            f"anchor={a.round(3).tolist()}")
        add("anchor_rotation_valid", is_rotation(ANCHOR_ROTATION), "diag(1,-1,-1)")
        add("anchor_boresight_down", np.allclose(self.antenna_frame(ANCHOR_ROTATION)["boresight"], [0, 0, -1]))
        add("robot_antenna_above_body", self.robot_antenna_z_m >= self.robot_body_lwh_m[2],
            f"antenna z={self.robot_antenna_z_m} body h={self.robot_body_lwh_m[2]}")
        add("robot_antenna_below_ceiling", self.robot_antenna_z_m < a[2])
        add("robot_y_limit_positive", self.robot_y_limit_m > 0, f"|y|<= {self.robot_y_limit_m:.3f} m")
        lo, hi = self.robot_x_range_m
        half_l = math.hypot(*self.robot_body_lwh_m[:2]) / 2.0
        add("robot_x_range_inside", half_l + self.robot_clearance_m <= lo < hi <= self.length_m - half_l - self.robot_clearance_m,
            f"x in [{lo}, {hi}]")
        for i, (x, y) in enumerate(self.example_xy_m):
            ok = lo <= x <= hi and abs(y) <= self.robot_y_limit_m
            add(f"example_{i}_in_allowed_region", ok, f"xy=({x}, {y})")
        ok_rot = all(is_rotation(self.robot_rotation(yaw)) for yaw in self.yaw_sweep_deg)
        add("robot_rotations_valid", ok_rot, f"{len(self.yaw_sweep_deg)} yaw values")
        ok_up = all(np.allclose(self.antenna_frame(self.robot_rotation(yaw))["boresight"], [0, 0, 1]) for yaw in self.yaw_sweep_deg)
        add("robot_boresight_up_for_all_yaw", ok_up)
        z_const = len({round(float(self.robot_position(x, y)[2]), 12) for x, y in self.example_xy_m}) == 1
        add("robot_antenna_z_constant", z_const)
        pol_ok = all(
            abs(float(f[self.port_pair[0]] @ f[self.port_pair[1]])) < 1e-12
            and abs(float(f[self.port_pair[0]] @ f["boresight"])) < 1e-12
            for f in (self.antenna_frame(ANCHOR_ROTATION), *(self.antenna_frame(self.robot_rotation(y)) for y in self.yaw_sweep_deg))
        )
        add("polarization_ports_orthogonal_and_transverse", pol_ok)
        return checks

    def snapshot(self) -> dict:
        data = asdict(self)
        blob = json.dumps(data, sort_keys=True, default=list)
        return dict(config=json.loads(blob), config_sha256=hashlib.sha256(blob.encode()).hexdigest())
