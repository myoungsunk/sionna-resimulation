"""Office scenario: E-shaped walkable aisles with cubicle partitions and desks (geometry only, no RF).

Plan view (x along the long side, y across; floor top z = 0, metres)::

    y=12  +--------------------------------------------+
          |  arm 2 (aisle)                             |
          +--+-----------------------------------------+
          |  |  notch 2: cubicle rows (partitions+desks)|
          |s +-----------------------------------------+
          |p |  arm 1 (aisle)                          |
          |i +-----------------------------------------+
          |n |  notch 1: cubicle rows                   |
          |e +-----------------------------------------+
          |  |  arm 0 (aisle)                          |
    y=0   +--+-----------------------------------------+

The walkable region is the spine (left) plus three arms, an "E". Each notch between two arms holds two rows of cubicles that open to the
aisles: side dividers every 2.8 m, a back partition on the notch centre line and one desk per cubicle against that back partition.
All dimensions are placeholders (the user asked for default values); materials of partitions and desks are assumptions.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

import numpy as np

# material name (ITU type) and thickness (m) per object group; partitions and desks are ASSUMED, not specified by the user
MATERIALS = {
    "floor": ("concrete", 0.2), "ceiling": ("concrete", 0.2), "outer_walls": ("plasterboard", 0.0125),
    "partitions": ("chipboard", 0.04), "desks": ("wood", 0.03),
}
GROUPS = tuple(MATERIALS)


def box_quads(lo, hi) -> list:
    """Six outward faces of an axis-aligned box as (4, 3) corner arrays."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    q = lambda *p: np.array(p, float)
    return [q((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)), q((x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)),
            q((x0, y0, z0), (x0, y0, z1), (x1, y0, z1), (x1, y0, z0)), q((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)),
            q((x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)), q((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0))]


def segment_hits_box(p0, p1, lo, hi) -> bool:
    """Slab test: does the segment p0 -> p1 intersect the axis-aligned box [lo, hi]?"""
    p0, p1, lo, hi = (np.asarray(v, float) for v in (p0, p1, lo, hi))
    d = p1 - p0
    t0, t1 = 0.0, 1.0
    for k in range(3):
        if abs(d[k]) < 1e-12:
            if p0[k] < lo[k] or p0[k] > hi[k]:
                return False
            continue
        a, b = (lo[k] - p0[k]) / d[k], (hi[k] - p0[k]) / d[k]
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return True


@dataclass(frozen=True)
class OfficeSetup:
    length_m: float = 10.0
    width_m: float = 12.0
    height_m: float = 2.7
    aisle_m: float = 1.8                 # spine width and the width of every arm
    arm_y0_m: tuple = (0.0, 5.1, 10.2)  # lower edge of each arm; notches lie between arms (3.3 m deep)
    cubicle_pitch_m: float = 1.6
    cubicle_x0_m: float = 2.0            # first side divider (spine is 1.8 m wide)
    n_cubicles: int = 4                  # per row; the rest of the notch up to the far wall stays open (wider end of the three aisles)
    rows_per_notch: int = 3              # rows of cubicles between two arms (was 2)
    partition_h_m: float = 1.4
    partition_t_m: float = 0.04
    desk_lwh_m: tuple = (1.4, 0.7, 0.75)
    desk_gap_m: float = 0.05             # desk to back partition
    anchor_x_m: float = 5.0
    anchor_y_m: float = 6.0              # above the middle arm
    anchor_standoff_m: float = 0.05
    robot_antenna_z_m: float = 0.45
    robot_body_lwh_m: tuple = (0.60, 0.40, 0.40)
    sample_step_m: float = 1.5

    # ---- geometry -----------------------------------------------------
    @property
    def anchor_position(self) -> np.ndarray:
        return np.array([self.anchor_x_m, self.anchor_y_m, self.height_m - self.anchor_standoff_m])

    def notches(self) -> list:
        """(y_lo, y_hi) of the two cubicle zones between the arms."""
        a = self.aisle_m
        return [(self.arm_y0_m[i] + a, self.arm_y0_m[i + 1]) for i in range(len(self.arm_y0_m) - 1)]

    def row_depth_m(self, n: int) -> float:
        ylo, yhi = self.notches()[n]
        return (yhi - ylo) / self.rows_per_notch

    def boxes(self) -> list:
        """Axis-aligned solids: dicts with name, group, lo, hi (partitions are thin boxes).

        Each notch holds ``rows_per_notch`` rows of cubicles, all with the same depth. Partition lines (full length) separate the rows, side
        dividers every ``cubicle_pitch_m`` close each cubicle, and every cubicle gets one desk against the partition line on its 'back' side:
        the first row's back is its upper line, the middle rows' back is their upper line and the last row's back is also its lower line
        (so the last two rows are back to back).
        """
        out = []
        t, h = self.partition_t_m, self.partition_h_m
        dl, dw, dh = self.desk_lwh_m
        g = t / 2 + self.desk_gap_m
        x_first = self.cubicle_x0_m
        x_last = self.cubicle_x0_m + self.cubicle_pitch_m * self.n_cubicles
        R = self.rows_per_notch
        for n, (ylo, yhi) in enumerate(self.notches()):
            d = self.row_depth_m(n)
            line = [ylo + k * d for k in range(R + 1)]  # row r spans line[r] .. line[r+1]
            for k in range(1, R):
                out.append(dict(name=f"back_partition_{n}_{k}", group="partitions", lo=(x_first, line[k] - t / 2, 0.0), hi=(x_last, line[k] + t / 2, h)))
            for r in range(R):
                y0 = line[r] + (t / 2 if r > 0 else 0.0)
                y1 = line[r + 1] - (t / 2 if r < R - 1 else 0.0)
                for i in range(self.n_cubicles + 1):
                    x = x_first + self.cubicle_pitch_m * i
                    out.append(dict(name=f"divider_{n}_row{r}_{i}", group="partitions", lo=(x - t / 2, y0, 0.0), hi=(x + t / 2, y1, h)))
                # rows 0..R-2: desk below their upper line; last row: desk above its lower line (back to back with the row below)
                for k in range(self.n_cubicles):
                    xc = x_first + self.cubicle_pitch_m * (k + 0.5)
                    if r < R - 1:
                        lo_y, hi_y = line[r + 1] - g - dw, line[r + 1] - g
                    else:
                        lo_y, hi_y = line[r] + g, line[r] + g + dw
                    out.append(dict(name=f"desk_{n}_row{r}_{k}", group="desks", lo=(xc - dl / 2, lo_y, 0.0), hi=(xc + dl / 2, hi_y, dh)))
        return out

    def objects(self) -> list:
        """Everything the ray tracer needs: name, group, ITU material, thickness, quads. One closed box per desk, one thin box per partition,
        and the six envelope faces (floor, ceiling, four walls)."""
        L, W, H = self.length_m, self.width_m, self.height_m
        q = lambda *p: np.array(p, float)
        env = {
            "floor": ("floor", [q((0, 0, 0), (L, 0, 0), (L, W, 0), (0, W, 0))]),
            "ceiling": ("ceiling", [q((0, 0, H), (0, W, H), (L, W, H), (L, 0, H))]),
            "wall_y_min": ("outer_walls", [q((0, 0, 0), (0, 0, H), (L, 0, H), (L, 0, 0))]),
            "wall_y_max": ("outer_walls", [q((0, W, 0), (L, W, 0), (L, W, H), (0, W, H))]),
            "wall_x_min": ("outer_walls", [q((0, 0, 0), (0, W, 0), (0, W, H), (0, 0, H))]),
            "wall_x_max": ("outer_walls", [q((L, 0, 0), (L, 0, H), (L, W, H), (L, W, 0))]),
        }
        objs = [dict(name=n, group=g, material=MATERIALS[g][0], thickness_m=MATERIALS[g][1], quads=quads) for n, (g, quads) in env.items()]
        for b in self.boxes():
            objs.append(dict(name=b["name"], group=b["group"], material=MATERIALS[b["group"]][0], thickness_m=MATERIALS[b["group"]][1],
                             quads=box_quads(b["lo"], b["hi"])))
        return objs

    # ---- walkable path -------------------------------------------------
    def path_segments(self) -> list:
        """Centre lines of the E: spine then the three arms, as ((x0, y0), (x1, y1))."""
        c = self.aisle_m / 2
        L = self.length_m
        segs = [((c, self.arm_y0_m[0] + c), (c, self.arm_y0_m[-1] + c))]
        segs += [((c, y + c), (L - c, y + c)) for y in self.arm_y0_m]
        return segs

    def sample_points(self) -> np.ndarray:
        """Tag positions every ``sample_step_m`` along the E (de-duplicated at the junctions), shape (n, 2)."""
        pts = []
        for (x0, y0), (x1, y1) in self.path_segments():
            n = max(1, int(round(math.hypot(x1 - x0, y1 - y0) / self.sample_step_m)))
            for k in range(n + 1):
                p = (x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n)
                if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 0.3 for q in pts):
                    pts.append(p)
        return np.array(pts)

    def tag_position(self, x: float, y: float) -> np.ndarray:
        return np.array([x, y, self.robot_antenna_z_m])

    def los_status(self, x: float, y: float) -> dict:
        """Geometric LoS between the anchor and a tag antenna at (x, y): clear or the names of the solids on the segment."""
        a, r = self.anchor_position, self.tag_position(x, y)
        blockers = [b["name"] for b in self.boxes() if segment_hits_box(r, a, b["lo"], b["hi"])]
        return dict(clear=not blockers, blockers=blockers)

    def in_aisle(self, x: float, y: float, margin: float = 0.0) -> bool:
        L, a = self.length_m, self.aisle_m
        if 0 + margin <= x <= a - margin and margin <= y <= self.width_m - margin:
            return True
        return any(y0 + margin <= y <= y0 + a - margin and margin <= x <= L - margin for y0 in self.arm_y0_m)

    # ---- checks ---------------------------------------------------------
    def validate(self) -> list[dict]:
        checks = []

        def add(name, passed, detail=""):
            checks.append(dict(name=name, passed=bool(passed), detail=detail))

        a = self.anchor_position
        add("anchor_inside_envelope", 0 < a[0] < self.length_m and 0 < a[1] < self.width_m and 0 < a[2] < self.height_m, f"anchor={a.round(3).tolist()}")
        add("arms_fit_in_envelope", self.arm_y0_m[-1] + self.aisle_m <= self.width_m + 1e-9 and self.arm_y0_m[0] >= 0, f"arms y0={list(self.arm_y0_m)}")
        add("row_depth_fits_desk", all(self.row_depth_m(n) > self.desk_lwh_m[1] + self.partition_t_m + self.desk_gap_m for n in range(len(self.notches()))), f"row depth={self.row_depth_m(0):.2f} m")
        last_x = self.cubicle_x0_m + self.cubicle_pitch_m * self.n_cubicles
        add("cubicles_inside_x_range", last_x + self.partition_t_m / 2 < self.length_m and self.cubicle_x0_m > self.aisle_m, f"last divider x={last_x:.2f}, open end {self.length_m - last_x:.2f} m")
        bx = self.boxes()
        inside = all(b["lo"][0] >= 0 and b["hi"][0] <= self.length_m and any(lo - 1e-9 <= b["lo"][1] and b["hi"][1] <= hi + 1e-9 for lo, hi in self.notches()) for b in bx)
        add("solids_inside_notches", inside, f"{len(bx)} solids")
        desks = [b for b in bx if b["group"] == "desks"]
        overlap = any(all(d1["lo"][k] < d2["hi"][k] and d2["lo"][k] < d1["hi"][k] for k in range(3)) for i, d1 in enumerate(desks) for d2 in desks[i + 1:])
        add("desks_do_not_overlap", not overlap, f"{len(desks)} desks")
        parts = [b for b in bx if b["group"] == "partitions"]
        hit = any(all(d["lo"][k] < p["hi"][k] and p["lo"][k] < d["hi"][k] for k in range(3)) for d in desks for p in parts)
        add("desks_do_not_intersect_partitions", not hit)
        pts = self.sample_points()
        clear = self.aisle_m / 2 - 0.5 * max(self.robot_body_lwh_m[:2])
        add("tag_path_in_aisles_with_clearance", all(self.in_aisle(x, y, 0.5 * max(self.robot_body_lwh_m[:2])) for x, y in pts), f"{len(pts)} points, clearance to aisle edge {clear:.2f} m")
        add("tag_antenna_below_partition_top", self.robot_antenna_z_m < self.partition_h_m)
        add("anchor_boresight_down", True, "diag(1,-1,-1), same as the corridor")
        return checks

    def snapshot(self) -> dict:
        data = asdict(self)
        blob = json.dumps(data, sort_keys=True, default=list)
        return dict(config=json.loads(blob), config_sha256=hashlib.sha256(blob.encode()).hexdigest())
