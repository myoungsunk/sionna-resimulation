"""Check the outputs of an office run: receipts, H shape/finiteness, and whether the first call has a LoS path (all interactions zero)
exactly where the geometric test says the line of sight is clear.   python scripts/office_verify_outputs.py --run-dir results/OFFICE_RUN_20261008
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.scenarios.office import OfficeSetup  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--expect", type=int, default=None, help="expected number of positions")
    args = ap.parse_args()
    s = OfficeSetup()
    rows, bad = [], []
    for rec in sorted(glob.glob(str(args.run_dir / "*/*_receipt.json"))):
        d = json.loads(Path(rec).read_text())
        tag = d["tag"]
        folder = Path(rec).parent
        H = np.load(folder / f"{tag}_H.npy")
        ok_shape = H.ndim == 4 and H.shape[2:] == (2, 2) and np.isfinite(H).all()
        x, y = d["robot_xy_m"]
        los_geo = s.los_status(x, y)["clear"]
        los_sim = None
        npz = folder / f"{tag}_sweep.npz"
        if npz.exists():
            z = np.load(npz)
            n0 = int(z["offsets"][1] - z["offsets"][0])
            los_sim = bool(n0 > 0 and (z["interactions_cat"][:, :n0] == 0).all(axis=0).any())
        rows.append(dict(tag=tag, x=x, y=y, H_shape=list(H.shape), ok=bool(ok_shape), los_geometric=los_geo, los_in_paths=los_sim, mean_paths=d["mean_paths"], seconds_per_call=d["seconds_per_call"]))
        if not ok_shape or (los_sim is not None and los_sim != los_geo):
            bad.append(tag)
    n = len(rows)
    print(json.dumps(dict(positions=n, expected=args.expect, bad=bad, median_seconds_per_call=float(np.median([r["seconds_per_call"] for r in rows])) if rows else None,
                          los_clear_geometric=sum(r["los_geometric"] for r in rows)), indent=1))
    (args.run_dir / "VERIFY.json").write_text(json.dumps(rows, indent=1))
    if bad or (args.expect is not None and n != args.expect):
        raise SystemExit("OFFICE_OUTPUT_CHECK_FAILED")


if __name__ == "__main__":
    main()
