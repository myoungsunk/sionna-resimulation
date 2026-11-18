"""Scan-position plan for the next corridor sweep batch (nothing is simulated here).

Existing 12 positions + tier A (regular x-y grid) + tier B (random validation positions, fixed seed).
Writes results/CORRIDOR_PLAN_20261007/SCAN_PLAN.json and the plan page.   python scripts/corridor_scan_plan.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

OUT = ROOT / "results" / "CORRIDOR_PLAN_20261007"
EXISTING = [(4.0, 0.0), (5.5, 0.0), (7.0, 0.0), (9.0, 0.0), (11.0, 0.0), (13.0, 0.0), (15.0, 0.0),
            (7.0, -0.7), (7.0, -0.35), (7.0, 0.35), (7.0, 0.7), (11.0, -0.5)]
# columns: (x values, y values).  Dense across the corridor up to x = 11, a thinner row set near the anchor (fills theta 12-30 deg) and far away.
GRID_COLUMNS = [([1.5, 2.5, 4.0, 5.5, 7.0, 9.0, 11.0], [-0.7, -0.35, 0.0, 0.35, 0.7]),
                ([3.0, 3.5, 4.5, 5.0], [-0.7, 0.0, 0.7]),
                ([13.0, 15.0, 17.5], [-0.7, 0.0, 0.7])]
N_RANDOM, SEED, MIN_DIST = 16, 20261007, 0.4
MIN_PER_POSITION_4CORES = 4.0  # four single-core sweeps run together take about 16 min


def main():
    s = CorridorSetup()
    lo, hi = s.robot_x_range_m
    lim = s.robot_y_limit_m
    ex = {(round(x, 3), round(y, 3)) for x, y in EXISTING}
    grid = sorted({(x, y) for xs, ys in GRID_COLUMNS for x in xs for y in ys if (x, y) not in ex})
    assert all(lo <= x <= hi and abs(y) <= lim for x, y in grid)
    rng = np.random.default_rng(SEED)
    taken = np.array(EXISTING + grid)
    rand = []
    strata = [(0, 40), (40, 60), (60, 75), (75, 90)]  # off-boresight theta bins, N_RANDOM / 4 validation points in each
    for lo_t, hi_t in strata:
        got = 0
        while got < N_RANDOM // len(strata):
            x, y = round(float(rng.uniform(1.0, 19.0)), 2), round(float(rng.uniform(-0.7, 0.7)), 2)
            th = s.link_geometry(x, y, 0.0)["anchor_off_boresight_deg"]
            pts = np.array(list(taken) + rand)
            if lo_t <= th < hi_t and np.min(np.hypot(pts[:, 0] - x, pts[:, 1] - y)) >= MIN_DIST:
                rand.append((x, y))
                got += 1
    rand.sort()
    rows = []
    for tier, pts in (("existing", EXISTING), ("A", grid), ("B", rand)):
        for x, y in pts:
            g = s.link_geometry(x, y, 0.0)
            rows.append(dict(tier=tier, x=x, y=y, range_m=round(g["range_m"], 2), theta_deg=round(g["anchor_off_boresight_deg"], 1),
                             phi_deg=round(g["anchor_phi_deg"], 1)))
    rows.sort(key=lambda r: ("existing", "A", "B").index(r["tier"]) * 1e6 + r["x"] * 100 + r["y"])
    n = {t: sum(r["tier"] == t for r in rows) for t in ("existing", "A", "B")}
    cover = {t: dict(theta_min=min(r["theta_deg"] for r in rows if r["tier"] == t), theta_max=max(r["theta_deg"] for r in rows if r["tier"] == t)) for t in n}
    plan = dict(corridor=dict(length=s.length_m, width=s.width_m, anchor=[s.anchor_x_m, s.anchor_y_m]), x_range=[lo, hi], y_limit=round(lim, 3),
                counts=n, theta_range=cover, minutes_4cores=dict(A=n["A"] * MIN_PER_POSITION_4CORES, B=n["B"] * MIN_PER_POSITION_4CORES),
                seed=SEED, min_dist_m=MIN_DIST, positions=rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SCAN_PLAN.json").write_text(json.dumps(plan, indent=1))
    print(n, cover, plan["minutes_4cores"])
    th = np.array([r["theta_deg"] for r in rows])
    print("theta histogram all (0-90 by 10):", np.histogram(th, bins=range(0, 100, 10))[0].tolist())
    print("theta histogram existing:", np.histogram([r['theta_deg'] for r in rows if r['tier']=='existing'], bins=range(0, 100, 10))[0].tolist())


if __name__ == "__main__":
    main()
