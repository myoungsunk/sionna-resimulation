"""Task lists for the S2 parity gates (no Sionna needed).

  python scripts/drive_sim/make_parity_tasks.py --out results/DRIVE_SIM_20261007/S2

* ``ref_positions_tasks.json``  the stored reference positions (44 at c13797a) -> rf_b_trace.py (G2 with --nodes all, G2' with --nodes 17)
* ``g4_a_tasks.json``           method-A runs at yaws outside the stored 0..180 deg range -> rf_a_runner.py (G4)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from drive_sim_s0_reference_check import stored_positions  # noqa: E402
from qclean_uwb.drivesim.rf_store import tag_of  # noqa: E402

G4_POSITIONS = [(5.5, 0.35), (11.0, -0.5), (15.0, 0.0)]      # none on the anchor's vertical axis (x=4, y=0)
# heading range about -50..230 deg; with the 45 deg mount the antenna yaw reaches about -5..275 deg
G4_YAWS = [-50.0, -30.0, 200.0, 230.0, 250.0, 275.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--anchor-b", action="store_true", help="tasks for the anchor-B check (positions along the new routes, yaws -50..275)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.anchor_b:
        pos = [(2.0, 0.45), (7.0, -0.45), (10.0, 0.40), (13.0, 0.0), (17.5, -0.45)]
        (args.out / "ref_positions_tasks.json").write_text(json.dumps([dict(task_id=i, tag=tag_of(x, y), x=x, y=y) for i, (x, y) in enumerate(pos)], indent=1))
        (args.out / "g4_a_tasks.json").write_text(json.dumps([dict(task_id=i, tag=tag_of(x, y), x=x, y=y, antenna_yaw_deg=[-50.0, 0.0, 35.7, 90.0, 135.0, 180.0, 230.0]) for i, (x, y) in enumerate(pos)], indent=1))
        print(len(pos), "anchor-B positions")
        return
    refs = stored_positions()
    ref_tasks = [dict(task_id=i, tag=tag_of(*r["xy"]), x=r["xy"][0], y=r["xy"][1]) for i, r in enumerate(refs)]
    (args.out / "ref_positions_tasks.json").write_text(json.dumps(ref_tasks, indent=1))
    g4 = [dict(task_id=i, tag=tag_of(x, y), x=x, y=y, antenna_yaw_deg=G4_YAWS) for i, (x, y) in enumerate(G4_POSITIONS)]
    (args.out / "g4_a_tasks.json").write_text(json.dumps(g4, indent=1))
    print(len(ref_tasks), "reference positions;", len(g4), "G4 positions x", len(G4_YAWS), "yaws")


if __name__ == "__main__":
    main()
