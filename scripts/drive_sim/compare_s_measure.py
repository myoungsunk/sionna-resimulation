"""A11 (exploratory): `s` from the first-path power (fp) versus `s` from the total received power per port (rx), same filter and noise draws.

  python scripts/drive_sim/compare_s_measure.py --s1 S1 --h-dir S2 --lut-dir S4 --out DEV_RESULTS/S_MEASURE_COMPARISON.json --seeds 10
Needs both LUTs: build_hs_lut.py (fp) and build_hs_lut.py --measure rx.  R1 timelines/H stores (lateral 0 and 0.35, mount 0 and 45).
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

PERIODS = (None, 10.0, 20.0, 60.0)
_G: dict = {}
KEEP = ("range_s_P0", "range_s_P0_noturn", "range_s_P1_T60", "range_s_P1_T20", "range_s_P1_T10", "odom_imu")


def tag(v):
    return "none" if v is None else f"{v:g}"


def load_lut(d: Path, measure: str) -> tuple[HsLut, dict]:
    suffix = "" if measure == "fp" else "_rx"
    doc = json.loads((d / f"hs_lut{suffix}_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(d / f"hs_lut{suffix}_2deg.npy")))
    return lut, doc


def work(args):
    seed, drift, snr_idx, measure = args
    g = _G
    rows, _ = E.run_unit(g["worlds"], g["lut"][measure], sensor=g["sensor"], mismatch_sigma=g["mismatch"][measure], anchor_xyz=g["anchor"], robot_z=g["robot_z"],
                         range_offset=g["range_offset"], snr_db=g["snr"][snr_idx], snr_idx=snr_idx, drift_idx=drift, seed=seed, compare_filters=False, measure=measure)
    for r in rows:
        r["measure"] = measure
    return [r for r in rows if r["baseline"] in KEEP]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--snr-db", type=float, nargs="+", default=[30.0, 10.0])
    ap.add_argument("--nproc", type=int, default=4)
    args = ap.parse_args()
    setup = CorridorSetup()
    luts = {m: load_lut(args.lut_dir, m) for m in ("fp", "rx")}
    lut = {m: v[0] for m, v in luts.items()}
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    # 1. mismatch of each measure on the noise-free simulated channel
    mm, slope = {"fp": [], "rx": []}, {"fp": [], "rx": []}
    for lat in (0.0, 0.35):
        for mount in (0.0, 45.0):
            h = np.load(args.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            w = E.make_world(args.s1 / f"timeline_y{lat:g}_Tnone.csv", h, freqs, lat, mount, None)
            tr = w.truth
            clean_fp = O.observe(w.h, freqs, None, None)["s"]
            clean_rx = O.rx_energy_s(w.h[..., 0])[0]
            for m, meas in (("fp", clean_fp), ("rx", clean_rx)):
                pred, jac = s_model(lut[m], setup.anchor_position, setup.robot_antenna_z_m, tr[:, 0], tr[:, 1], tr[:, 2], mount, with_jac=True)
                ok = np.isfinite(meas)
                mm[m].append((meas - pred)[ok])
                slope[m].append(np.abs(jac[:, 2][ok]) * np.pi / 180.0)
    mismatch = {m: float(np.sqrt(np.mean(np.concatenate(v) ** 2))) for m, v in mm.items()}
    slope_med = {m: float(np.median(np.concatenate(v))) for m, v in slope.items()}
    info = {m: float(np.median(mismatch[m] / np.maximum(np.concatenate(slope[m]), 1e-6))) for m in mm}      # heading noise per measurement [deg]
    out = dict(mismatch_rms=mismatch, median_abs_slope_per_deg=slope_med, median_heading_noise_per_measurement_deg=info)
    _G.update(lut=lut, sensor=S.SensorNoise(), mismatch=mismatch, anchor=tuple(setup.anchor_position), robot_z=setup.robot_antenna_z_m, snr=args.snr_db,
              range_offset=json.loads((args.lut_dir / "hs_lut_meta.json").read_text())["range_bias"]["mean_m"])
    E.POS_PROCESS_STD = 0.01
    rows = []
    for lat in (0.0, 0.35):
        for mount in (0.0, 45.0):
            h = np.load(args.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            _G["worlds"] = {p: E.make_world(args.s1 / f"timeline_y{lat:g}_T{tag(p)}.csv", h, freqs, lat, mount, p) for p in PERIODS}
            units = [(seed, d, si, m) for m in ("fp", "rx") for d in (0, 1, 2) for si in range(len(args.snr_db)) for seed in range(args.seeds)]
            with mp.get_context("fork").Pool(args.nproc) as pool:
                for r in pool.imap(work, units, chunksize=1):
                    rows += r
            print("done", lat, mount, len(rows), flush=True)
    df = pd.DataFrame(rows)
    ok = df[df.error.fillna("") == ""]
    key = ["lateral", "mount_deg", "drift", "snr_db", "seed", "baseline"]
    fp = ok[ok.measure == "fp"].set_index(key)
    rx = ok[ok.measure == "rx"].set_index(key)
    j = fp[["heading_rmse_deg", "pos_rmse_m", "nees_mean"]].join(rx[["heading_rmse_deg", "pos_rmse_m", "nees_mean"]], lsuffix="_fp", rsuffix="_rx", how="inner").reset_index()
    j["rel_change_heading"] = (j.heading_rmse_deg_rx - j.heading_rmse_deg_fp) / j.heading_rmse_deg_fp
    table = j.groupby(["mount_deg", "baseline"]).agg(fp_median=("heading_rmse_deg_fp", "median"), rx_median=("heading_rmse_deg_rx", "median"),
                                                       rel_change_median=("rel_change_heading", "median"), rx_better_share=("rel_change_heading", lambda x: float((x < 0).mean())),
                                                       pos_fp=("pos_rmse_m_fp", "median"), pos_rx=("pos_rmse_m_rx", "median"), nees_fp=("nees_mean_fp", "median"), nees_rx=("nees_mean_rx", "median")).round(3)
    out["by_mount_baseline"] = {f"m{m}_{b}": row.to_dict() for (m, b), row in table.iterrows()}
    out["n_pairs"] = int(len(j))
    args.out.write_text(json.dumps(out, indent=1))
    pd.set_option("display.width", 200)
    print(json.dumps({k: out[k] for k in ("mismatch_rms", "median_abs_slope_per_deg", "median_heading_noise_per_measurement_deg", "n_pairs")}, indent=1))
    print(table.to_string())


if __name__ == "__main__":
    main()
