"""Plan for the two-anchor x-sweep (nothing is simulated here).

Anchor 1 at (16, 0), anchor 2 at (16, -0.4), both on the ceiling, boresight down. For each anchor the robot ("tag") stays on the anchor's own y
line and moves along x, so the anchor-tag direction has azimuth 0 / 180 deg and only the off-boresight angle theta changes.
Writes SCAN_PLAN.json and the plan page.        python scripts/corridor_anchor_sweep_plan.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

OUT = ROOT / "results" / "CORRIDOR_ANCHOR_PLAN_20261007"
ANCHOR_X = 16.0
ANCHORS = {"A1": 0.0, "A2": -0.4}
THETA_LEFT = [0, 10, 20, 30, 40, 50, 55, 60, 65, 70, 75, 80]  # tag on the long side (x < anchor x)
THETA_RIGHT = [20, 40, 50]                                      # tag on the short side (x > anchor x)
MIN_PER_POSITION_4CORES = 5.0  # about 20 min per position with four sweeps running together


def main():
    rows = []
    for name, ay in ANCHORS.items():
        s = CorridorSetup(anchor_x_m=ANCHOR_X, anchor_y_m=ay)
        lo, hi = s.robot_x_range_m
        dz = s.anchor_position[2] - s.robot_antenna_z_m
        for side, thetas, sgn in (("left", THETA_LEFT, -1), ("right", THETA_RIGHT, +1)):
            for th in thetas:
                x = round(ANCHOR_X + sgn * dz * math.tan(math.radians(th)), 2)
                assert lo <= x <= hi and abs(ay) <= s.robot_y_limit_m, (name, th, x)
                g = s.link_geometry(x, ay, 0.0)
                rows.append(dict(anchor=name, anchor_x=ANCHOR_X, anchor_y=ay, side=side, theta_target=th, x=x, y=ay,
                                 theta_deg=round(g["anchor_off_boresight_deg"], 1), phi_deg=round(g["anchor_phi_deg"], 1), range_m=round(g["range_m"], 2)))
    # theta = 0 appears once per anchor (listed under "left")
    n = len(rows)
    plan = dict(anchor_x=ANCHOR_X, anchors=ANCHORS, corridor=dict(length=20.0, width=2.4), counts={a: sum(r["anchor"] == a for r in rows) for a in ANCHORS},
                total=n, hours_4cores=round(n * MIN_PER_POSITION_4CORES / 60, 1), positions=rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SCAN_PLAN.json").write_text(json.dumps(plan, indent=1))
    print(plan["counts"], n, "positions,", plan["hours_4cores"], "h")
    for r in rows[:16]:
        print(r)


if __name__ == "__main__":
    main()
