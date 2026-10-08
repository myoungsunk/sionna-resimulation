"""A16 part A: probe fairness.  Paired P1_T - P0 differences on the common stations and on all samples (descriptive, no test).

  run-r1   : R1 development H stores (local)  ->  CSV with the A16 columns
      python scripts/drive_sim/probe_fairness.py run-r1 --s1 S1 --h-dir S2 --lut-dir S4 --out DEV_RESULTS/PROBE_FAIRNESS_R1.csv --seeds 10
  analyze  : any results CSV(s) that carry heading_rmse_common_deg (R1 above, or route S6 CSVs re-run with the A16 code)
      python scripts/drive_sim/probe_fairness.py analyze --csv a.csv b.csv --out DEV_RESULTS/PROBE_FAIRNESS_R1.json
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

PERIODS = (None, 10.0, 20.0, 60.0)
KEEP = ("range_s_P0", "range_s_P1_T60", "range_s_P1_T20", "range_s_P1_T10")
KEY = ["route", "anchor", "lateral", "mount_deg", "drift", "snr_db", "seed"]
BOOT, BOOT_SEED = 2000, 20261008
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def work(args):
    from qclean_uwb.drivesim import experiment as E
    from qclean_uwb.drivesim import sensors as S
    seed, drift, snr_idx = args
    g = _G
    rows, _ = E.run_unit(g["worlds"], g["lut"], sensor=S.SensorNoise(), mismatch_sigma=g["mismatch"], anchor_xyz=g["anchor"], robot_z=g["robot_z"], range_offset=g["range_offset"],
                         snr_db=g["snr"][snr_idx], snr_idx=snr_idx, drift_idx=drift, seed=seed, compare_filters=False)
    return [r for r in rows if r["baseline"] in KEEP]


def run_r1(a):
    from qclean_uwb.drivesim import experiment as E
    from qclean_uwb.drivesim.hs_lut import HsLut
    from qclean_uwb.scenarios.corridor import CorridorSetup
    setup = CorridorSetup()
    doc = json.loads((a.lut_dir / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(a.lut_dir / "hs_lut_2deg.npy")))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    _G.update(lut=lut, mismatch=0.18, anchor=tuple(setup.anchor_position), robot_z=setup.robot_antenna_z_m, snr=[30.0, 10.0], range_offset=doc["range_bias"]["mean_m"])
    E.POS_PROCESS_STD = 0.01
    rows = []
    for lat in (0.0, 0.35):
        for mount in (0.0, 45.0):
            h = np.load(a.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            _G["worlds"] = {p: E.make_world(a.s1 / f"timeline_y{lat:g}_T{tag(p)}.csv", h, freqs, lat, mount, p) for p in PERIODS}
            with mp.get_context("fork").Pool(a.nproc) as pool:
                for r in pool.imap(work, [(s, d, si) for d in (0, 1, 2) for si in range(2) for s in range(a.seeds)], chunksize=1):
                    rows += r
            print("done", lat, mount, len(rows), flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(a.out, index=False)


def boot_ci(x, rng):
    x = np.asarray(x, float)
    med = np.median(rng.choice(x, size=(BOOT, len(x)), replace=True), axis=1)
    return float(np.percentile(med, 2.5)), float(np.percentile(med, 97.5))


def analyze(a):
    df = pd.concat([pd.read_csv(p) for p in a.csv], ignore_index=True)
    df = df[(df["filter"] == "ekf") & (df.get("error", pd.Series("", index=df.index)).fillna("") == "")]
    base = df[df.baseline == "range_s_P0"].set_index(KEY)
    rng = np.random.default_rng(BOOT_SEED)
    out = []
    for name in ("range_s_P1_T60", "range_s_P1_T20", "range_s_P1_T10"):
        t = df[df.baseline == name].set_index(KEY)
        j = t.join(base, lsuffix="_T", rsuffix="_P0", how="inner")
        for (route, anchor, mount), g in j.groupby(["route", "anchor", "mount_deg"], sort=True):
            for metric, cT, c0 in (("common", "heading_rmse_common_deg_T", "heading_rmse_common_deg_P0"), ("all_samples", "heading_rmse_deg_T", "heading_rmse_deg_P0")):
                d = (g[cT] - g[c0]).to_numpy()
                lo, hi = boot_ci(d, rng)
                out.append(dict(route=route, anchor=anchor, mount_deg=float(mount), schedule=name.replace("range_s_", ""), metric=metric, n=int(len(d)), p0_median_deg=float(g[c0].median()),
                                p1_median_deg=float(g[cT].median()), delta_median_deg=float(np.median(d)), ci95_lo=lo, ci95_hi=hi, q10=float(np.percentile(d, 10)), q90=float(np.percentile(d, 90)),
                                share_better=float((d < 0).mean()), share_worse=float((d > 0).mean()), elapsed_p0_s=float(g["duration_s_P0"].median()), elapsed_p1_s=float(g["duration_s_T"].median())))
    res = pd.DataFrame(out)
    pd.set_option("display.width", 220, "display.max_rows", 200)
    print(res.round(3).to_string(index=False))
    a.out.write_text(json.dumps(dict(definition="A16 part A", bootstrap=dict(n=BOOT, seed=BOOT_SEED), rows=out), indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-r1")
    r.add_argument("--s1", type=Path, required=True)
    r.add_argument("--h-dir", type=Path, required=True)
    r.add_argument("--lut-dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--seeds", type=int, default=10)
    r.add_argument("--nproc", type=int, default=3)
    r.set_defaults(fn=run_r1)
    n = sub.add_parser("analyze")
    n.add_argument("--csv", type=Path, nargs="+", required=True)
    n.add_argument("--out", type=Path, required=True)
    n.set_defaults(fn=analyze)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
