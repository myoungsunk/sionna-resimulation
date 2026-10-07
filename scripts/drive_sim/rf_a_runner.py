"""Method A (needs Sionna): direct PathSolver per (position, antenna yaw), 257 bins, via corridor_sionna_run.run_sweep.

Used for (i) the G1 reproducibility check, (ii) G4 out-of-range-yaw checks and (iii) the fallback if the method-B gates fail.
Always single thread (bit-reproducible, see S0 PREREG_AMENDMENTS A1).  A task whose receipt exists is skipped.

  python scripts/drive_sim/rf_a_runner.py --tasks results/DRIVE_SIM_20261007/S1/rf_tasks_y0_m0.json --out OUT --shard 0/4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS / "g2_completion"))
import corridor_sionna_run as C  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--bin-stride", type=int, default=1, help="1 = all 257 bins (production); >1 only for smoke tests")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    import drjit as dr
    dr.set_thread_count(1)
    shard, n_shards = (int(v) for v in args.shard.split("/"))
    tasks = json.loads(args.tasks.read_text())
    if args.only:
        tasks = [t for t in tasks if t["tag"] in set(args.only)]
    tasks = [t for i, t in enumerate(tasks) if i % n_shards == shard]
    if args.limit:
        tasks = tasks[: args.limit]
    setup = CorridorSetup()
    assert all(c["passed"] for c in setup.validate()), "SETUP_VALIDATION_FAILED"
    cfg = json.loads(C.SOLVER_SOURCE.read_text())["solver"]
    banks = C.load_banks()
    for t in tasks:
        d = args.out / t["tag"]
        if (d / f"{t['tag']}_receipt.json").exists():
            continue
        d.mkdir(parents=True, exist_ok=True)
        ns = SimpleNamespace(out=d, xy=[t["x"], t["y"]], tag=t["tag"], yaws=list(t["antenna_yaw_deg"]), bin_stride=args.bin_stride,
                             position=t["task_id"])
        (d / "SETUP_SNAPSHOT.json").write_text(json.dumps(setup.snapshot(), indent=2))
        C.run_sweep(ns, setup, cfg, banks)


if __name__ == "__main__":
    main()
