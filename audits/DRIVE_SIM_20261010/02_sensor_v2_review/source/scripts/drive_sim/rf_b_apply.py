"""Method B, step 2: apply the FFD banks to the stored Jones traces and write the H store of one (lateral, mount).

  python scripts/drive_sim/rf_b_apply.py --poses results/DRIVE_SIM_20261007/S1/rf_poses_y0.json --traces TRACE_DIR [TRACE_DIR ...] \
      --mount 0 --out results/DRIVE_SIM_20261007/S2/H_y0_m0.npy

H layout: [pose_id, bin(257), rx(+45,-45), tx(+45,-45)], complex128.  Needs the LP_plus45 / LP_minus45 bank files (Git LFS).
Fails unless every position has a usable trace (status OK, 0 unmatched paths); ``--allow-missing`` only for smoke tests.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim.config import build_manifest  # noqa: E402
from qclean_uwb.drivesim.rf_store import assemble, load_banks  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", type=Path, required=True)
    ap.add_argument("--traces", type=Path, nargs="+", required=True)
    ap.add_argument("--mount", type=float, required=True, help="antenna mount offset in degrees (antenna yaw = body yaw + mount)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--allow-missing", action="store_true")
    args = ap.parse_args()
    t0 = time.monotonic()
    poses = json.loads(args.poses.read_text())
    banks = load_banks()
    h, report = assemble(poses, args.traces, banks, args.mount, allow_missing=args.allow_missing)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, h)
    man = build_manifest(config=dict(mount_deg=args.mount, bins=int(h.shape[1]), layout="[pose_id, bin, rx(+45,-45), tx(+45,-45)]", report=report),
                         inputs=[args.poses], outputs=[args.out])
    man["elapsed_s"] = round(time.monotonic() - t0, 2)
    args.out.with_suffix(".manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(dict(out=str(args.out), shape=list(h.shape), **{k: report[k] if not isinstance(report[k], list) else len(report[k]) for k in report}), indent=1))


if __name__ == "__main__":
    main()
