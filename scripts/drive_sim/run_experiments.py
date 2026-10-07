"""S6: run the experiment matrix (baselines x lateral x mount offset x drift x SNR x seeds) on stored noise-free H.

  python scripts/drive_sim/run_experiments.py --s1 results/DRIVE_SIM_20261007/S1 --h-dir results/DRIVE_SIM_20261007/S2 \
      --lut results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy --out results/DRIVE_SIM_20261007/S6 --snr-db 35 20 --seeds 50 --nproc 4

No Sionna needed.  A (lateral, mount) block whose ``results_*.csv`` exists is skipped (resumable).  The SNR levels are deliberately a required
argument: they are fixed after ``snr_calibration.py`` and before the first filter run (PREREG "snr_values_db_at_10m_los_copol").
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
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.config import build_manifest  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

PERIODS = (None, 10.0, 20.0, 60.0)
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def work(args):
    seed, drift_idx, snr_idx = args
    g = _G
    rows, series = E.run_unit(g["worlds"], g["lut"], sensor=g["sensor"], mismatch_sigma=g["mismatch"], anchor_xyz=g["anchor"], robot_z=g["robot_z"],
                              range_offset=g["range_offset"], snr_db=g["snr"][snr_idx], snr_idx=snr_idx, drift_idx=drift_idx, seed=seed,
                              compare_filters=g["compare"])
    return rows, series, (seed, drift_idx, snr_idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--snr-db", type=float, nargs="+", required=True)
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--laterals", type=float, nargs="*", default=[0.0, 0.35])
    ap.add_argument("--mounts", type=float, nargs="*", default=[0.0, 45.0])
    ap.add_argument("--drifts", type=int, nargs="*", default=[0, 1, 2])
    ap.add_argument("--mismatch-sigma", type=float, default=0.09)
    ap.add_argument("--range-sigma", type=float, default=0.05)
    ap.add_argument("--nproc", type=int, default=4)
    ap.add_argument("--max-samples", type=int, default=0, help="smoke test: truncate every timeline")
    ap.add_argument("--no-compare-filters", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    setup = CorridorSetup()
    meta = json.loads((args.lut.parent / "hs_lut_meta.json").read_text())["meta"]
    lut = HsLut(dict(theta_deg=np.array(meta["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["phi_deg"][2]), s=np.load(args.lut)))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    sensor = S.SensorNoise(range_sigma_m=args.range_sigma)
    range_offset = O.los_range_bias(freqs)
    _G.update(lut=lut, sensor=sensor, mismatch=args.mismatch_sigma, anchor=tuple(setup.anchor_position), robot_z=setup.robot_antenna_z_m,
              range_offset=range_offset, snr=args.snr_db, compare=not args.no_compare_filters)
    config = dict(snr_db=args.snr_db, seeds=args.seeds, laterals=args.laterals, mounts=args.mounts, drifts=args.drifts, mismatch_sigma=args.mismatch_sigma,
                  sensor=sensor.__dict__, range_offset_m=range_offset, drift_levels=[d.__dict__ for d in S.DRIFT_LEVELS], baselines=E.BASELINES,
                  filters_compared=list(E.FILTER_KINDS_COMPARED), max_samples=args.max_samples)
    for lat in args.laterals:
        for mount in args.mounts:
            csv_path = args.out / f"results_y{lat:g}_m{mount:g}.csv"
            if csv_path.exists():
                print("skip", csv_path)
                continue
            t0 = time.monotonic()
            h = np.load(args.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            _G["worlds"] = {p: E.make_world(args.s1 / f"timeline_y{lat:g}_T{tag(p)}.csv", h, freqs, lat, mount, p, max_samples=args.max_samples or None) for p in PERIODS}
            units = [(seed, d, si) for d in args.drifts for si in range(len(args.snr_db)) for seed in range(args.seeds)]
            rows, series = [], {}
            ctx = mp.get_context("fork")
            with ctx.Pool(args.nproc) as pool:
                for r, s, key in pool.imap(work, units, chunksize=1):
                    rows += r
                    for name, (he, pe) in s.items():
                        series.setdefault(name, {})[key] = (he, pe)
                    if len(rows) % 200 < len(r):
                        print(f"y{lat:g} m{mount:g}: {len(rows)} runs, {time.monotonic() - t0:.0f}s", flush=True)
            for name, d in series.items():
                keys = sorted(d)
                L = max(len(d[k][0]) for k in keys)
                arr = np.full((len(keys), L), np.nan, np.float32)
                for i, k in enumerate(keys):
                    arr[i, : len(d[k][0])] = d[k][0]
                np.save(args.out / f"ts_heading_y{lat:g}_m{mount:g}_{name}.npy", arr)
                json.dump([list(map(int, k)) for k in keys], (args.out / f"ts_index_y{lat:g}_m{mount:g}_{name}.json").open("w"))
            pd.DataFrame(rows).to_csv(csv_path, index=False)
            (args.out / f"manifest_y{lat:g}_m{mount:g}.json").write_text(json.dumps(build_manifest(config=config, inputs=[args.lut, args.h_dir / f"H_y{lat:g}_m{mount:g}.npy"],
                                                                                                    outputs=[csv_path]), indent=1, default=str))
            print(f"done y{lat:g} m{mount:g}: {len(rows)} runs in {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
