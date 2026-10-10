"""S4: build the LoS-only h_s look-up table from the FFD banks and check its interpolation error (gate L1 of PREREG_AMENDMENTS A4).

  python scripts/drive_sim/build_hs_lut.py --out results/DRIVE_SIM_20261007/S4        # about 7 min, numpy only
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
from qclean_uwb.drivesim.hs_lut import HsLut, build_lut, los_s_direct, range_bias_from_banks  # noqa: E402
from qclean_uwb.drivesim.rf_store import load_banks  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--n-check", type=int, default=500)
    ap.add_argument("--range-bias-only", action="store_true", help="recompute only the range offset and merge it into the existing hs_lut_meta.json")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    banks = load_banks()
    if args.range_bias_only:
        meta_path = args.out / "hs_lut_meta.json"
        doc = json.loads(meta_path.read_text())
        doc["range_bias"] = range_bias_from_banks(banks)
        meta_path.write_text(json.dumps(doc, indent=1))
        print(json.dumps(doc["range_bias"]))
        return
    t0 = time.monotonic()
    lut = build_lut(banks, args.step, args.step, progress=lambda i, n: print(f"theta row {i}/{n}", flush=True) if i % 5 == 0 else None)
    build_s = time.monotonic() - t0
    npy = args.out / f"hs_lut_{args.step:g}deg.npy"
    np.save(npy, lut["s"])
    meta = dict(theta_deg=lut["theta_deg"].tolist(), phi_deg=[float(lut["phi_deg"][0]), float(lut["phi_deg"][-1]), args.step], d_ref_m=lut["d_ref_m"],
                layout="s[theta, phi_tx, phi_rx]; phi grid = -180 + k*step", build_seconds=round(build_s, 1))
    f = HsLut(lut)
    rng = np.random.default_rng(20261007)
    pts = np.column_stack([rng.uniform(5, 85, args.n_check), rng.uniform(-180, 180, args.n_check), rng.uniform(-180, 180, args.n_check)])
    err = np.abs(np.array([f(*p) for p in pts]) - np.array([los_s_direct(banks, *p) for p in pts]))
    range_bias = range_bias_from_banks(banks)
    gate = dict(max=float(err.max()), median=float(np.median(err)), n=args.n_check, passed=bool(err.max() <= 1e-2 and np.median(err) <= 1e-3),
                thresholds=dict(max=1e-2, median=1e-3))
    (args.out / "hs_lut_meta.json").write_text(json.dumps(dict(meta=meta, gate_L1_interpolation=gate, range_bias=range_bias), indent=1))
    man = build_manifest(config=dict(meta=meta, gate_L1=gate), inputs=[Path(__file__), ROOT / "src/qclean_uwb/drivesim/hs_lut.py"], outputs=[npy])
    (args.out / "hs_lut_manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(gate))


if __name__ == "__main__":
    main()
