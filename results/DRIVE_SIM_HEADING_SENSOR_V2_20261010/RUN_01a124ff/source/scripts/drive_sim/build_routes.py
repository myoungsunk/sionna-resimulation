"""A9: build timelines, pose sets and position task lists for the added routes R2 (loop), R4 (zigzag), R5 (serpentine).

  python scripts/drive_sim/build_routes.py --out results/DRIVE_SIM_20261007/S1/routes

Per route and probe period T in {none, 10, 20, 60}: timeline_<R>_T<T>.csv; rf_poses_<R>.json (union over T); rf_tasks_<R>_m0.json (one task per
position, used by rf_b_trace.py for either anchor); ROUTES_MANIFEST.json (config hash, chosen wobble seed, anchor clearances, SHA256 of outputs).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim.config import build_manifest  # noqa: E402
from qclean_uwb.drivesim.routes import SPECS, anchor_clearance, build_route_samples, choose_wobble_seed  # noqa: E402
from qclean_uwb.drivesim.trajectory import TrajectoryConfig, rf_tasks, samples_sha256, unique_poses  # noqa: E402

PERIODS = (None, 10.0, 20.0, 60.0)
COLS = ["idx", "t_s", "drive_g", "phase", "x", "y", "yaw_body_deg", "turn_phase", "probe_id", "probe_offset_deg", "pose_id"]


def tag(v):
    return "none" if v is None else f"{v:g}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--routes", nargs="*", default=list(SPECS))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    outputs, summary = [], {}
    for name in args.routes:
        spec = SPECS[name]()
        seed, worst = choose_wobble_seed(spec, TrajectoryConfig())
        variants = [build_route_samples(spec, TrajectoryConfig(wobble_seed=seed, probe_period_s=T)) for T in PERIODS]
        poses, ids = unique_poses(variants)
        for T, rows, pid in zip(PERIODS, variants, ids):
            p = args.out / f"timeline_{name}_T{tag(T)}.csv"
            with p.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLS)
                for r, i in zip(rows, pid):
                    w.writerow([r[c] if c != "pose_id" else i for c in COLS])
            outputs.append(p)
        p = args.out / f"rf_poses_{name}.json"
        p.write_text(json.dumps(poses, separators=(",", ":")))
        outputs.append(p)
        tasks = rf_tasks(poses, 0.0)
        p = args.out / f"rf_tasks_{name}_m0.json"
        p.write_text(json.dumps(tasks, separators=(",", ":")))
        outputs.append(p)
        clear = {k: min(anchor_clearance(v)[k] for v in variants) for k in ("A", "B")}
        summary[name] = dict(wobble_seed=seed, rf_poses=len(poses), rf_positions=len(tasks), min_anchor_axis_clearance_m=clear,
                             samples={tag(T): len(r) for T, r in zip(PERIODS, variants)}, duration_s={tag(T): r[-1]["t_s"] for T, r in zip(PERIODS, variants)},
                             sha256={tag(T): samples_sha256(r) for T, r in zip(PERIODS, variants)})
    man = build_manifest(config=dict(base=TrajectoryConfig().snapshot(), routes=args.routes, summary=summary), inputs=[Path(__file__), ROOT / "src/qclean_uwb/drivesim/routes.py"],
                         outputs=outputs)
    (args.out / "ROUTES_MANIFEST.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
