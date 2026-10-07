"""Office scenario: open room with desk islands (two desks back to back + a partition) and white (free) corridors; geometry only, no RF.

Modelled on the occupancy map the user supplied (white = walkable) and their description: a 10 x 12 m room (x across, y along the long side),
12 islands = 3 columns (along x) x 4 positions (along y). Each island is two desks whose wide sides touch (back to back) with a thin partition
between them; one desk faces +x, the other -x, so 2 x 4 x 3 = 24 desks. The y = 12 end is closed (wall); the walkable network is a comb, an
"E" turned so that its teeth run along y: a bar near y = 0 and four corridors (left wall, between columns 1-2, between columns 2-3, right wall)
that end at the closed y = 12 side.

Plan view (x across, y up, floor top z = 0, metres)::

    y=12 +-----------------------------+   closed wall
         |  [d|d]  [d|d]  [d|d]        |   island = desk | partition | desk
         |  [d|d]  [d|d]  [d|d]        |
         |  [d|d]  [d|d]  [d|d]        |
         |  [d|d]  [d|d]  [d|d]        |
         |  ....   ....   ....         |   open floor
    y=0  +-------- connecting bar ------+

All dimensions are placeholders read off the picture (about 73 px per metre); materials of partitions and desks are assumptions.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

import numpy as np

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
    length_m: float = 10.0               # x
    width_m: float = 12.0                # y
    height_m: float = 2.7
    col_x_m: tuple = (1.85, 4.9, 8.15)   # island centre x of the three columns (read off the map)
    n_rows: int = 4
    top_margin_m: float = 1.85           # top wall to the first island centre
    row_pitch_m: float = 1.75
    desk_lwh_m: tuple = (1.4, 0.7, 0.75)  # width along y (the wide side), depth along x, height
    partition_h_m: float = 1.4
    partition_t_m: float = 0.04
    partition_gap_m: float = 0.02        # gap between desk and the partition between the two desks
    corridor_x_m: tuple = (0.5, 3.3, 6.55, 9.5)  # centre lines of the four vertical corridors
    bottom_bar_y_m: float = 0.75         # connecting bar of the comb (the y = 12 end is closed)
    corridor_top_y_m: float = 11.25      # the four corridors end here, in front of the closed wall
    anchor_x_m: float = 5.0
    anchor_y_m: float = 2.2
    anchor_standoff_m: float = 0.05
    robot_antenna_z_m: float = 0.45
    robot_body_lwh_m: tuple = (0.60, 0.40, 0.40)
    robot_clearance_m: float = 0.10
    sample_step_m: float = 1.5

    @property
    def anchor_position(self) -> np.ndarray:
        return np.array([self.anchor_x_m, self.anchor_y_m, self.height_m - self.anchor_standoff_m])

    def row_y_m(self) -> list:
        return [self.width_m - self.top_margin_m - k * self.row_pitch_m for k in range(self.n_rows)]

    def boxes(self) -> list:
        """Per island: a thin partition (normal x) between two desks that face +x and -x (back to back)."""
        out = []
        dw, dd, dh = self.desk_lwh_m  # width (y), depth (x), height
        t, h, g = self.partition_t_m, self.partition_h_m, self.partition_gap_m
        for c, xc in enumerate(self.col_x_m):
            for r, yc in enumerate(self.row_y_m()):
                y0, y1 = yc - dw / 2, yc + dw / 2
                out.append(dict(name=f"partition_c{c}_r{r}", group="partitions", lo=(xc - t / 2, y0, 0.0), hi=(xc + t / 2, y1, h)))
                out.append(dict(name=f"desk_c{c}_r{r}_plus_x", group="desks", lo=(xc + t / 2 + g, y0, 0.0), hi=(xc + t / 2 + g + dd, y1, dh)))
                out.append(dict(name=f"desk_c{c}_r{r}_minus_x", group="desks", lo=(xc - t / 2 - g - dd, y0, 0.0), hi=(xc - t / 2 - g, y1, dh)))
        return out

    def objects(self) -> list:
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
            objs.append(dict(name=b["name"], group=b["group"], material=MATERIALS[b["group"]][0], thickness_m=MATERIALS[b["group"]][1], quads=box_quads(b["lo"], b["hi"])))
        return objs

    # ---- walkable network ----------------------------------------------
    def path_segments(self) -> list:
        """Bar near y = 0 plus the four corridors that run up to the closed y = 12 side, as ((x0, y0), (x1, y1))."""
        xs = self.corridor_x_m
        segs = [((xs[0], self.bottom_bar_y_m), (xs[-1], self.bottom_bar_y_m))]
        segs += [((x, self.bottom_bar_y_m), (x, self.corridor_top_y_m)) for x in xs]
        return segs

    def sample_points(self) -> np.ndarray:
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
        a, r = self.anchor_position, self.tag_position(x, y)
        blockers = [b["name"] for b in self.boxes() if segment_hits_box(r, a, b["lo"], b["hi"])]
        return dict(clear=not blockers, blockers=blockers)

    def is_free(self, x: float, y: float, margin: float = 0.0) -> bool:
        """Inside the room and at least ``margin`` away from every desk and partition footprint."""
        if not (margin <= x <= self.length_m - margin and margin <= y <= self.width_m - margin):
            return False
        for b in self.boxes():
            if b["lo"][0] - margin < x < b["hi"][0] + margin and b["lo"][1] - margin < y < b["hi"][1] + margin:
                return False
        return True

    def validate(self) -> list[dict]:
        checks = []

        def add(name, passed, detail=""):
            checks.append(dict(name=name, passed=bool(passed), detail=detail))

        a = self.anchor_position
        add("anchor_inside_room", 0 < a[0] < self.length_m and 0 < a[1] < self.width_m and 0 < a[2] < self.height_m, f"anchor={a.round(3).tolist()}")
        bx = self.boxes()
        add("solids_inside_room", all(b["lo"][0] >= 0 and b["hi"][0] <= self.length_m and b["lo"][1] >= 0 and b["hi"][1] <= self.width_m for b in bx), f"{len(bx)} solids")
        add("closed_end_has_wall_gap", max(b["hi"][1] for b in bx) < self.width_m - 0.5, f"top of islands y={max(b['hi'][1] for b in bx):.2f}, wall at y={self.width_m:g}")
        desks = [b for b in bx if b["group"] == "desks"]
        parts = [b for b in bx if b["group"] == "partitions"]
        ov = lambda p, q: all(p["lo"][k] < q["hi"][k] and q["lo"][k] < p["hi"][k] for k in range(3))
        add("desks_do_not_overlap", not any(ov(d1, d2) for i, d1 in enumerate(desks) for d2 in desks[i + 1:]), f"{len(desks)} desks")
        add("desks_do_not_intersect_partitions", not any(ov(d, p) for d in desks for p in parts), f"{len(parts)} partitions")
        half = 0.5 * max(self.robot_body_lwh_m[:2]) + self.robot_clearance_m
        pts = self.sample_points()
        add("tag_path_free_with_clearance", all(self.is_free(x, y, half) for x, y in pts), f"{len(pts)} points, clearance {half:.2f} m")
        ih = self.desk_lwh_m[1] + self.partition_t_m / 2 + self.partition_gap_m  # island half width along x
        add("corridors_between_columns", all(self.col_x_m[i] + ih + half < self.corridor_x_m[i + 1] < self.col_x_m[i + 1] - ih - half for i in range(len(self.col_x_m) - 1)), "corridor centre lines clear the islands")
        add("tag_antenna_below_partition_top", self.robot_antenna_z_m < self.partition_h_m)
        add("anchor_boresight_down", True, "diag(1,-1,-1), same as the corridor")
        return checks

    def snapshot(self) -> dict:
        data = asdict(self)
        blob = json.dumps(data, sort_keys=True, default=list)
        return dict(config=json.loads(blob), config_sha256=hashlib.sha256(blob.encode()).hexdigest())
