"""A13 (exploratory): EKF with the LoS-only FFD LUT (TX/RX angle model) versus the ideal curve s = -cos(2 yaw).

  python scripts/drive_sim/compare_angle_model.py --s1 S1 --h-dir S2 --lut-dir S4 --out DEV_RESULTS/ANGLE_MODEL_ABLATION.json --seeds 10
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
KEEP = ("range_s_P0", "range_s_P0_noturn", "range_s_P1_T60", "range_s_P1_T20", "range_s_P1_T10", "inverse_heading_P0", "odom_imu")
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def ideal_lut(step: float = 2.0) -> HsLut:
    th = np.arange(0.0, 90.01, step)
    ph = np.arange(-180.0, 180.0, step)
    a = np.radians(ph)
    s = -np.cos(2.0 * (a[:, None] + a[None, :]))              # yaw_antenna = pi - phi_tx - phi_rx for the ceiling-anchor / up-facing robot geometry
    return HsLut(dict(theta_deg=th, phi_deg=ph, s=np.repeat(s[None], len(th), 0)))


def work(args):
    seed, drift, snr_idx, model = args
    g = _G
    rows, _ = E.run_unit(g["worlds"], g["lut"][model], sensor=g["sensor"], mismatch_sigma=g["mismatch"][model], anchor_xyz=g["anchor"], robot_z=g["robot_z"],
                         range_offset=g["range_offset"], snr_db=g["snr"][snr_idx], snr_idx=snr_idx, drift_idx=drift, seed=seed, compare_filters=False)
    for r in rows:
        r["model"] = model
    return [r for r in rows if r["baseline"] in KEEP]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--nproc", type=int, default=4)
    args = ap.parse_args()
    setup = CorridorSetup()
    doc = json.loads((args.lut_dir / "hs_lut_meta.json").read_text())
    lut = {"lut": HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(args.lut_dir / "hs_lut_2deg.npy"))),
           "ideal": ideal_lut()}
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    res = {"lut": [], "ideal": []}
    for lat in (0.0, 0.35):
        for mount in (0.0, 45.0):
            h = np.load(args.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            w = E.make_world(args.s1 / f"timeline_y{lat:g}_Tnone.csv", h, freqs, lat, mount, None)
            tr = w.truth
            meas = O.observe(w.h, freqs, None, None)["s"]
            for m in res:
                res[m].append((meas - s_model(lut[m], setup.anchor_position, setup.robot_antenna_z_m, tr[:, 0], tr[:, 1], tr[:, 2], mount))[np.isfinite(meas)])
    mismatch = {m: float(np.sqrt(np.mean(np.concatenate(v) ** 2))) for m, v in res.items()}
    out = dict(mismatch_rms=mismatch)
    _G.update(lut=lut, sensor=S.SensorNoise(), mismatch=mismatch, anchor=tuple(setup.anchor_position), robot_z=setup.robot_antenna_z_m, snr=[30.0, 10.0],
              range_offset=doc["range_bias"]["mean_m"])
    E.POS_PROCESS_STD = 0.01
    rows = []
    for lat in (0.0, 0.35):
        for mount in (0.0, 45.0):
            h = np.load(args.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            _G["worlds"] = {p: E.make_world(args.s1 / f"timeline_y{lat:g}_T{tag(p)}.csv", h, freqs, lat, mount, p) for p in PERIODS}
            units = [(seed, d, si, m) for m in ("lut", "ideal") for d in (0, 1, 2) for si in range(2) for seed in range(args.seeds)]
            with mp.get_context("fork").Pool(args.nproc) as pool:
                for r in pool.imap(work, units, chunksize=1):
                    rows += r
            print("done", lat, mount, len(rows), flush=True)
    df = pd.DataFrame(rows)
    ok = df[df.error.fillna("") == ""]
    key = ["lateral", "mount_deg", "drift", "snr_db", "seed", "baseline"]
    a = ok[ok.model == "lut"].set_index(key)
    b = ok[ok.model == "ideal"].set_index(key)
    j = a[["heading_rmse_deg", "pos_rmse_m", "nees_mean"]].join(b[["heading_rmse_deg", "pos_rmse_m", "nees_mean"]], lsuffix="_lut", rsuffix="_ideal", how="inner").reset_index()
    j["rel_change"] = (j.heading_rmse_deg_ideal - j.heading_rmse_deg_lut) / j.heading_rmse_deg_lut
    t = j.groupby(["mount_deg", "baseline"]).agg(lut_median=("heading_rmse_deg_lut", "median"), ideal_median=("heading_rmse_deg_ideal", "median"), rel_change_median=("rel_change", "median"),
                                                  ideal_better_share=("rel_change", lambda x: float((x < 0).mean())), pos_lut=("pos_rmse_m_lut", "median"), pos_ideal=("pos_rmse_m_ideal", "median")).round(3)
    out["by_mount_baseline"] = {f"m{m}_{b}": row.to_dict() for (m, b), row in t.iterrows()}
    out["n_pairs"] = int(len(j))
    args.out.write_text(json.dumps(out, indent=1))
    pd.set_option("display.width", 200)
    print(json.dumps({k: out[k] for k in ("mismatch_rms", "n_pairs")}))
    print(t.to_string())


if __name__ == "__main__":
    main()
