"""Write the run plan for the office simulation: all tag positions, a 6-position pilot, and the geometric LoS flags.   python scripts/office_make_run_plan.py"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.scenarios.office import OfficeSetup  # noqa: E402

OUT = ROOT / "results" / "OFFICE_RUN_PLAN_20261008"


def main():
    s = OfficeSetup()
    rows = []
    for x, y in s.example_xy_m:
        st, g = s.los_status(x, y), s.link_geometry(x, y)
        rows.append(dict(x=x, y=y, los_clear=st["clear"], blockers=st["blockers"], theta_deg=round(g["anchor_off_boresight_deg"], 1), range_m=round(g["range_m"], 2)))
    # pilot: three LoS-clear and three blocked positions, spread over the range of theta
    pilot = []
    for flag in (True, False):
        sel = sorted((r for r in rows if r["los_clear"] is flag), key=lambda r: r["theta_deg"])
        pilot += [sel[int(round(q * (len(sel) - 1)))] for q in (0.0, 0.5, 1.0)]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "positions_all.txt").write_text("".join(f"{r['x']} {r['y']}\n" for r in rows))
    (OUT / "positions_pilot.txt").write_text("".join(f"{r['x']} {r['y']}\n" for r in pilot))
    snap = s.snapshot()
    (OUT / "RUN_PLAN.json").write_text(json.dumps(dict(config_sha256=snap["config_sha256"], config=snap["config"], n_positions=len(rows), n_los_clear=sum(r["los_clear"] for r in rows),
                                                      yaw_deg=list(s.yaw_sweep_deg), positions=rows, pilot=[(r["x"], r["y"]) for r in pilot]), indent=1))
    print(len(rows), "positions;", sum(r["los_clear"] for r in rows), "LoS-clear;", "pilot:", [(r["x"], r["y"], r["los_clear"], r["theta_deg"]) for r in pilot])


if __name__ == "__main__":
    main()
