"""S1: build truth timelines, the RF pose set and the A-method task lists for every lateral y0 and mount offset.

  python scripts/drive_sim/build_trajectories.py --out results/DRIVE_SIM_20261007/S1

Writes, per y0: timeline_y<y0>_T<period|none>.csv, rf_poses_y<y0>.json (union over all T), rf_tasks_y<y0>_m<mount>.json,
plus TRAJECTORY_MANIFEST.json (config hash, SHA256 of every output, command line).
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
from qclean_uwb.drivesim.trajectory import TrajectoryConfig, build_samples, check_anchor_axis_clearance, check_region, rf_tasks, samples_sha256, unique_poses  # noqa: E402

LATERALS = (0.0, 0.35)
PERIODS = (None, 10.0, 20.0, 60.0)
MOUNTS = (0.0, 45.0)
COLS = ["idx", "t_s", "drive_g", "phase", "x", "y", "yaw_body_deg", "turn_phase", "probe_id", "probe_offset_deg", "pose_id"]


def tag(v):
    return "none" if v is None else f"{v:g}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--laterals", type=float, nargs="*", default=list(LATERALS))
    ap.add_argument("--mounts", type=float, nargs="*", default=list(MOUNTS))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    outputs, summary, axis_clearance = [], {}, {}
    for y0 in args.laterals:
        variants = []
        for T in PERIODS:
            rows = build_samples(TrajectoryConfig(y0_m=y0, probe_period_s=T))
            check_region(rows)
            axis_clearance[(y0, tag(T))] = check_anchor_axis_clearance(rows)
            variants.append(rows)
        poses, ids = unique_poses(variants)
        for T, rows, pid in zip(PERIODS, variants, ids):
            p = args.out / f"timeline_y{y0:g}_T{tag(T)}.csv"
            with p.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLS)
                for r, i in zip(rows, pid):
                    w.writerow([r[c] if c != "pose_id" else i for c in COLS])
            outputs.append(p)
        p = args.out / f"rf_poses_y{y0:g}.json"
        p.write_text(json.dumps(poses, separators=(",", ":")))
        outputs.append(p)
        for m in args.mounts:
            tasks = rf_tasks(poses, m)
            p = args.out / f"rf_tasks_y{y0:g}_m{m:g}.json"
            p.write_text(json.dumps(tasks, separators=(",", ":")))
            outputs.append(p)
            summary[f"y{y0:g}_m{m:g}"] = dict(min_distance_to_anchor_axis_m=min(v for (yy, _), v in axis_clearance.items() if yy == y0), rf_poses=len(poses), rf_positions=len(tasks),
                                             a_method_hours_4core_at_11p7s=round(len(poses) * 11.7 / 3600, 2),
                                             samples={tag(T): len(r) for T, r in zip(PERIODS, variants)},
                                             sha256={tag(T): samples_sha256(r) for T, r in zip(PERIODS, variants)})
    cfg = dict(base=TrajectoryConfig().snapshot(), laterals=args.laterals, periods=[tag(t) for t in PERIODS], mounts=args.mounts, summary=summary)
    man = build_manifest(config=cfg, inputs=[Path(__file__), ROOT / "src/qclean_uwb/drivesim/trajectory.py"], outputs=outputs)
    (args.out / "TRAJECTORY_MANIFEST.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
