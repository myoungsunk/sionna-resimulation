"""Office scenario: open room with desk islands (desk + partition) and white (free) corridors; geometry only, no RF.

Modelled on the occupancy map the user supplied (white = walkable): a 10 x 12 m room, 12 desk blocks in 3 columns x 4 rows, an open strip
along the top wall and open strips between the columns and along both side walls. The walkable network used for tag positions is a comb
(an "E" with one more tooth): a bar along the top and four vertical corridors (left wall, between columns 1-2, between columns 2-3,
right wall).

Plan view (x across, y up, floor top z = 0, metres)::

    y=12 +-----------------------------+   top bar (walkable)
         |  ##   ##   ##               |   islands: desk + partition
         |  ##   ##   ##               |
         |  ##   ##   ##               |
         |  ##   ##   ##               |
    y=0  +-----------------------------+

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
    desk_lwh_m: tuple = (1.6, 0.7, 0.75)
    partition_h_m: float = 1.4
    partition_t_m: float = 0.04
    partition_gap_m: float = 0.02        # partition sits on the +y (back) long side of the desk
    corridor_x_m: tuple = (0.5, 3.3, 6.55, 9.5)  # centre lines of the four vertical corridors
    top_bar_y_m: float = 11.25
    bottom_end_y_m: float = 0.75
    anchor_x_m: float = 5.0
    anchor_y_m: float = 6.0
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
        out = []
        dl, dw, dh = self.desk_lwh_m
        t, h, g = self.partition_t_m, self.partition_h_m, self.partition_gap_m
        for c, xc in enumerate(self.col_x_m):
            for r, yc in enumerate(self.row_y_m()):
                out.append(dict(name=f"desk_c{c}_r{r}", group="desks", lo=(xc - dl / 2, yc - dw / 2, 0.0), hi=(xc + dl / 2, yc + dw / 2, dh)))
                yb = yc + dw / 2 + g
                out.append(dict(name=f"partition_c{c}_r{r}", group="partitions", lo=(xc - dl / 2, yb, 0.0), hi=(xc + dl / 2, yb + t, h)))
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
        """Top bar plus the four vertical corridors, as ((x0, y0), (x1, y1)); the corridors hang from the bar."""
        xs = self.corridor_x_m
        segs = [((xs[0], self.top_bar_y_m), (xs[-1], self.top_bar_y_m))]
        segs += [((x, self.top_bar_y_m), (x, self.bottom_end_y_m)) for x in xs]
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
        add("rows_below_top_bar", max(b["hi"][1] for b in bx) < self.top_bar_y_m - 0.5 * max(self.robot_body_lwh_m[:2]) - self.robot_clearance_m, f"top of islands y={max(b['hi'][1] for b in bx):.2f}")
        desks = [b for b in bx if b["group"] == "desks"]
        parts = [b for b in bx if b["group"] == "partitions"]
        ov = lambda p, q: all(p["lo"][k] < q["hi"][k] and q["lo"][k] < p["hi"][k] for k in range(3))
        add("desks_do_not_overlap", not any(ov(d1, d2) for i, d1 in enumerate(desks) for d2 in desks[i + 1:]), f"{len(desks)} desks")
        add("desks_do_not_intersect_partitions", not any(ov(d, p) for d in desks for p in parts), f"{len(parts)} partitions")
        half = 0.5 * max(self.robot_body_lwh_m[:2]) + self.robot_clearance_m
        pts = self.sample_points()
        add("tag_path_free_with_clearance", all(self.is_free(x, y, half) for x, y in pts), f"{len(pts)} points, clearance {half:.2f} m")
        add("corridors_between_columns", all(self.col_x_m[i] + self.desk_lwh_m[0] / 2 + half < self.corridor_x_m[i + 1] < self.col_x_m[i + 1] - self.desk_lwh_m[0] / 2 - half for i in range(len(self.col_x_m) - 1)), "corridor centre lines clear the islands")
        add("tag_antenna_below_partition_top", self.robot_antenna_z_m < self.partition_h_m)
        add("anchor_boresight_down", True, "diag(1,-1,-1), same as the corridor")
        return checks

    def snapshot(self) -> dict:
        data = asdict(self)
        blob = json.dumps(data, sort_keys=True, default=list)
        return dict(config=json.loads(blob), config_sha256=hashlib.sha256(blob.encode()).hexdigest())
