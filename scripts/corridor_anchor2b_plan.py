"""Anchor 2 at (4, -0.4) with the tag on the y = 0 line, theta kept equal to the anchor-1 positions (tag y = 0, anchor (4, 0)).

The horizontal anchor-tag distance r = 2.2 tan(theta) is kept, so x - 4 = +-sqrt(r^2 - 0.4^2): the tag x shifts (mm for far tags, up to 0.2 m near the anchor).
theta = 0 (tag below anchor 1) cannot be reproduced: with the tag at y = 0 the horizontal distance to anchor 2 is at least 0.4 m (theta >= 10.3 deg).
Writes SCAN_PLAN.json and positions.txt.   python scripts/corridor_anchor2b_plan.py
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

OUT = ROOT / "results" / "CORRIDOR_ANCHOR2B_20261007"
AX, AY = 4.0, -0.4
X1 = [1.5, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 7.0, 9.0, 11.0, 13.0, 13.48, 15.0, 17.5]  # anchor-1 data (tag y = 0, anchor (4, 0))


def main():
    s = CorridorSetup(anchor_x_m=AX, anchor_y_m=AY)
    s1 = CorridorSetup()
    rows = []
    for x1 in X1:
        r = abs(x1 - AX)
        if r < abs(AY) + 1e-9:
            continue
        x = round(AX + math.copysign(math.sqrt(r * r - AY * AY), x1 - AX), 3)
        g, g1 = s.link_geometry(x, 0.0, 0.0), s1.link_geometry(x1, 0.0, 0.0)
        rows.append(dict(x1=x1, x=x, y=0.0, shift_x=round(x - x1, 3), theta_deg=round(g["anchor_off_boresight_deg"], 2), theta_anchor1_deg=round(g1["anchor_off_boresight_deg"], 2),
                         phi_deg=round(g["anchor_phi_deg"], 1), range_m=round(g["range_m"], 3)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SCAN_PLAN.json").write_text(json.dumps(dict(anchor=[AX, AY], tag_y=0.0, positions=rows), indent=1))
    (OUT / "positions.txt").write_text("".join(f"{r['x']} {r['y']}\n" for r in rows))
    print(len(rows), "positions;", "max |theta - theta1| =", max(abs(r["theta_deg"] - r["theta_anchor1_deg"]) for r in rows))


if __name__ == "__main__":
    main()
