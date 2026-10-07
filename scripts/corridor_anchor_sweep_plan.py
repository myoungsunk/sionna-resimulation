"""Plan for the two-anchor comparison (nothing is simulated here).

Anchor 1 = the earlier setting: ceiling anchor at (4, 0), tag on the y = 0 line; its yaw sweeps already exist (re-used, not re-run).
Anchor 2 = the same anchor moved only in y, to (4, -0.4); the tag stays on its own y = -0.4 line at exactly the same x list, so every
position has the same x and nearly the same theta as anchor 1.  The anchor-tag azimuth is 0 / 180 deg, only theta changes.
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
ANCHOR_X = 4.0
ANCHORS = {"A1": 0.0, "A2": -0.4}
# tag x list = every earlier position on the y = 0 line, with the folder that holds its sweep (anchor 1 data)
A1_DATA = {1.5: "CORRIDOR_SCAN2_20261007/x1.5_y0.0/x1.5_y0.0", 2.5: "CORRIDOR_SCAN2_20261007/x2.5_y0.0/x2.5_y0.0", 3.0: "CORRIDOR_SCAN2_20261007/x3.0_y0.0/x3.0_y0.0",
           3.5: "CORRIDOR_SCAN2_20261007/x3.5_y0.0/x3.5_y0.0", 4.0: "CORRIDOR_SWEEP_20261006/pos0/position_0", 4.5: "CORRIDOR_SCAN2_20261007/x4.5_y0.0/x4.5_y0.0",
           5.0: "CORRIDOR_SCAN2_20261007/x5.0_y0.0/x5.0_y0.0", 5.5: "CORRIDOR_SCAN_20261006/x5.5_y0.0/x5.5_y0.0", 7.0: "CORRIDOR_SCAN_20261006/x7.0_y0.0/x7.0_y0.0",
           9.0: "CORRIDOR_SCAN_20261006/x9.0_y0.0/x9.0_y0.0", 11.0: "CORRIDOR_SCAN_20261006/x11.0_y0.0/x11.0_y0.0", 13.0: "CORRIDOR_SCAN_20261006/x13.0_y0.0/x13.0_y0.0",
           13.48: "CORRIDOR_SCAN2_20261007/x13.48_y0.0/x13.48_y0.0", 15.0: "CORRIDOR_SWEEP_20261006/pos3/position_3", 17.5: "CORRIDOR_SCAN2_20261007/x17.5_y0.0/x17.5_y0.0"}
MIN_PER_POSITION_4CORES = 5.0  # about 20 min per position with four sweeps running together


def main():
    rows = []
    for name, ay in ANCHORS.items():
        s = CorridorSetup(anchor_x_m=ANCHOR_X, anchor_y_m=ay)
        lo, hi = s.robot_x_range_m
        for x in sorted(A1_DATA):
            assert lo <= x <= hi and abs(ay) <= s.robot_y_limit_m, (name, x)
            g = s.link_geometry(x, ay, 0.0)
            rows.append(dict(anchor=name, anchor_x=ANCHOR_X, anchor_y=ay, status="existing" if name == "A1" else "new", x=x, y=ay,
                             side="below" if x == ANCHOR_X else ("left" if x < ANCHOR_X else "right"),
                             theta_deg=round(g["anchor_off_boresight_deg"], 1), phi_deg=round(g["anchor_phi_deg"], 1), range_m=round(g["range_m"], 2),
                             data=("results/" + A1_DATA[x]) if name == "A1" else None))
    # theta = 0 appears once per anchor (listed under "left")
    n = len(rows)
    plan = dict(anchor_x=ANCHOR_X, anchors=ANCHORS, corridor=dict(length=20.0, width=2.4), counts={a: sum(r["anchor"] == a for r in rows) for a in ANCHORS},
                total=n, new_positions=sum(r["status"] == "new" for r in rows), hours_4cores=round(sum(r["status"] == "new" for r in rows) * MIN_PER_POSITION_4CORES / 60, 1), positions=rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SCAN_PLAN.json").write_text(json.dumps(plan, indent=1))
    print(plan["counts"], n, "positions,", plan["new_positions"], "new,", plan["hours_4cores"], "h")
    for r in rows[:15]:
        print(r["x"], r["theta_deg"], r["phi_deg"])


if __name__ == "__main__":
    main()
