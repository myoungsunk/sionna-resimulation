"""A9: experiment matrix for the added routes (R2 loop, R4 zigzag, R5 serpentine) and the two single-anchor systems A (x=4 m) and B (x=10 m).

  python scripts/drive_sim/run_route_experiments.py --s1-routes results/DRIVE_SIM_20261007/S1/routes --h-dir results/DRIVE_SIM_20261007/S2 \
      --lut results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy --out results/DRIVE_SIM_20261007/S6_routes --snr-db 30 10 --mismatch-sigma <fixed value> \
      --pos-process-std 0.01 --seeds 50 --nproc 4

H stores: <h-dir>/H_<route>_a<anchor>_m<mount>.npy (rf_b_apply output).  A block whose results CSV exists is skipped.  Each anchor is a separate
single-anchor system; the drift, noise and initial-error draws depend only on (seed, drift, SNR), so A and B are paired.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.config import build_manifest  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

PERIODS = (None, 10.0, 20.0, 60.0)
ANCHOR_X = {"A": 4.0, "B": 10.0}
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def work(args):
    seed, drift_idx, snr_idx = args
    g = _G
    rows, series = E.run_unit(g["worlds"], g["lut"], sensor=g["sensor"], mismatch_sigma=g["mismatch"], anchor_xyz=g["anchor_xyz"], robot_z=g["robot_z"],
                              range_offset=g["range_offset"], snr_db=g["snr"][snr_idx], snr_idx=snr_idx, drift_idx=drift_idx, seed=seed, compare_filters=g["compare"])
    return rows, series, (seed, drift_idx, snr_idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-version", choices=("legacy", "sensor-v2"), default="legacy")
    ap.add_argument("--s1-routes", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--snr-db", type=float, nargs="+", required=True)
    ap.add_argument("--mismatch-sigma", type=float, required=True)
    ap.add_argument("--pos-process-std", type=float, default=0.01)
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--routes", nargs="*", default=["R2", "R4", "R5"])
    ap.add_argument("--anchors", nargs="*", default=["A", "B"])
    ap.add_argument("--mounts", type=float, nargs="*", default=[0.0, 45.0])
    ap.add_argument("--drifts", type=int, nargs="*", default=[0, 1, 2])
    ap.add_argument("--range-sigma", type=float, default=0.05)
    ap.add_argument("--nproc", type=int, default=4)
    ap.add_argument("--max-samples", type=int, default=0)
    ap.add_argument("--no-compare-filters", action="store_true")
    args = ap.parse_args()
    if args.model_version != "legacy":
        ap.error("sensor-v2 uses run_sensor_v2.py with separate raw outputs; production launchers are legacy only")
    args.out.mkdir(parents=True, exist_ok=True)
    doc = json.loads((args.lut.parent / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(args.lut)))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    sensor = S.SensorNoise(range_sigma_m=args.range_sigma)
    E.POS_PROCESS_STD = args.pos_process_std
    _G.update(lut=lut, sensor=sensor, mismatch=args.mismatch_sigma, robot_z=CorridorSetup().robot_antenna_z_m, range_offset=doc["range_bias"]["mean_m"],
              snr=args.snr_db, compare=not args.no_compare_filters)
    config = dict(snr_db=args.snr_db, seeds=args.seeds, seed_start=args.seed_start, routes=args.routes, anchors=args.anchors, mounts=args.mounts, drifts=args.drifts,
                  mismatch_sigma=args.mismatch_sigma, pos_process_std=args.pos_process_std, sensor=sensor.__dict__, range_offset_m=doc["range_bias"]["mean_m"],
                  baselines=E.BASELINES, filters_compared=list(E.FILTER_KINDS_COMPARED), max_samples=args.max_samples)
    for route in args.routes:
        for anchor in args.anchors:
            setup = CorridorSetup(anchor_x_m=ANCHOR_X[anchor])
            _G["anchor_xyz"] = tuple(setup.anchor_position)
            for mount in args.mounts:
                csv_path = args.out / f"results_{route}_a{anchor}_m{mount:g}.csv"
                if csv_path.exists():
                    print("skip", csv_path)
                    continue
                t0 = time.monotonic()
                h = np.load(args.h_dir / f"H_{route}_a{anchor}_m{mount:g}.npy", mmap_mode="r")
                _G["worlds"] = {p: E.make_world(args.s1_routes / f"timeline_{route}_T{tag(p)}.csv", h, freqs, 0.0, mount, p, max_samples=args.max_samples or None,
                                                route=route, anchor=anchor) for p in PERIODS}
                units = [(seed, d, si) for d in args.drifts for si in range(len(args.snr_db)) for seed in range(args.seed_start, args.seed_start + args.seeds)]
                rows = []
                with mp.get_context("fork").Pool(args.nproc) as pool:
                    for r, _s, _key in pool.imap(work, units, chunksize=1):
                        rows += r
                pd.DataFrame(rows).to_csv(csv_path, index=False)
                (args.out / f"manifest_{route}_a{anchor}_m{mount:g}.json").write_text(json.dumps(build_manifest(
                    config=config, inputs=[args.lut, args.h_dir / f"H_{route}_a{anchor}_m{mount:g}.npy"], outputs=[csv_path]), indent=1, default=str))
                print(f"done {route} a{anchor} m{mount:g}: {len(rows)} runs in {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
