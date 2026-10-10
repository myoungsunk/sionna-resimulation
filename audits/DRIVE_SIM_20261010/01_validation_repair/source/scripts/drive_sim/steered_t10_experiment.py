"""A20: steered T10 probe through the filter (open-loop command).  Definitions: S0/PREREG_AMENDMENTS.md A18/A20.

  python scripts/drive_sim/steered_t10_experiment.py --s1 S1 --h-dir S2 --lut-dir S4 --trace-root S2 --out DEV_RESULTS/STEERED_T10_A20.csv [--seeds 10]
Then:  python scripts/drive_sim/steered_t10_experiment.py --analyze DEV_RESULTS/STEERED_T10_A20.csv --out DEV_RESULTS/STEERED_T10_A20.json
Local R1 development H stores only.  The steered probe channels are assembled from the stored Method-B traces at the commanded antenna yaw.
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
from qclean_uwb.drivesim import rf_store as RS  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut  # noqa: E402
from qclean_uwb.drivesim.steered_probe import steer_rows  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

ERR = {"S10e0": 0.0, "S10e5": 5.0, "S10em5": -5.0}
BASES = [b for b in E.BASELINES if b["name"] in ("range_s_P0", "range_s_P1_T10")] + [
    dict(name=f"range_s_P1S_T10_{k}", period=k, use_range=True, use_s=True, use_odom_heading=True) for k in ERR]
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def probe_h(rows, ids_unused, trace_dirs, banks, mount):
    """Channels of the probe rows of ``rows`` (yaw as given) assembled from the traces."""
    idx = [i for i, r in enumerate(rows) if r["probe_id"] >= 0]
    poses = [dict(x=rows[i]["x"], y=rows[i]["y"], yaw_body_deg=rows[i]["yaw_body_deg"], pose_id=k) for k, i in enumerate(idx)]
    h, rep = RS.assemble(poses, trace_dirs, banks, mount)
    return idx, h, rep


def build_worlds(a, lat, mount, banks, freqs):
    h_store = np.load(a.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
    trace_dirs = [a.trace_root / f"traces_y{lat:g}"]
    worlds, checks = {}, {}
    for p in (None, 10.0):
        worlds[p] = E.make_world(a.s1 / f"timeline_y{lat:g}_T{tag(p)}.csv", h_store, freqs, lat, mount, p)
    sweep = worlds[10.0]
    # self-check: re-assembling the stored sweep probe rows from the traces reproduces the stored H store
    idx, hh, _ = probe_h(sweep.rows, None, trace_dirs, banks, mount)
    ref = np.asarray(sweep.h)[idx]
    checks["rebuild_vs_stored_max_rel_err"] = float(np.max(np.linalg.norm((hh - ref).reshape(len(idx), -1), axis=1) / np.linalg.norm(ref.reshape(len(idx), -1), axis=1)))
    for key, err in ERR.items():
        rows = steer_rows(sweep.rows, mount, err)
        idx, hh, rep = probe_h(rows, None, trace_dirs, banks, mount)
        h = np.array(sweep.h)
        h[idx] = hh
        worlds[key] = E.World(rows, h, np.asarray(freqs, float), lat, mount, key)
    return worlds, checks


def work(args):
    seed, drift, si = args
    g = _G
    rows, _ = E.run_unit(g["worlds"], g["lut"], sensor=S.SensorNoise(), mismatch_sigma=0.18, anchor_xyz=g["anchor"], robot_z=g["robot_z"], range_offset=g["range_offset"],
                         snr_db=g["snr"][si], snr_idx=si, drift_idx=drift, seed=seed, compare_filters=False, baselines=BASES)
    return rows


def run(a):
    setup = CorridorSetup()
    doc = json.loads((a.lut_dir / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(a.lut_dir / "hs_lut_2deg.npy")))
    banks = RS.load_banks()
    freqs = banks[0].freqs_hz
    _G.update(lut=lut, anchor=tuple(setup.anchor_position), robot_z=setup.robot_antenna_z_m, snr=[30.0, 10.0], range_offset=doc["range_bias"]["mean_m"])
    E.POS_PROCESS_STD = 0.01
    out, checks = [], {}
    for lat in (0.0, 0.35):
        for mount in (0.0, 45.0):
            _G["worlds"], ck = build_worlds(a, lat, mount, banks, freqs)
            checks[f"y{lat:g}_m{mount:g}"] = ck
            print("rebuild check", lat, mount, ck, flush=True)
            with mp.get_context("fork").Pool(a.nproc) as pool:
                for r in pool.imap(work, [(s, d, si) for d in (0, 1, 2) for si in range(2) for s in range(a.seeds)], chunksize=1):
                    out += r
            print("done", lat, mount, len(out), flush=True)
    pd.DataFrame(out).to_csv(a.out, index=False)
    a.out.with_suffix(".checks.json").write_text(json.dumps(checks, indent=1))


def analyze(a):
    df = pd.read_csv(a.analyze)
    df = df[(df["filter"] == "ekf") & (df.error.fillna("") == "")]
    key = ["lateral", "mount_deg", "drift", "snr_db", "seed"]
    sweep = df[df.baseline == "range_s_P1_T10"].set_index(key)
    rng = np.random.default_rng(20261008)
    res = []
    for name in ("range_s_P1S_T10_S10e0", "range_s_P1S_T10_S10e5", "range_s_P1S_T10_S10em5", "range_s_P0"):
        t = df[df.baseline == name].set_index(key)
        j = t.join(sweep, lsuffix="_x", rsuffix="_sweep", how="inner")
        for mount, g in j.groupby("mount_deg"):
            d = (g.heading_rmse_common_deg_x - g.heading_rmse_common_deg_sweep).to_numpy()
            med = np.median(rng.choice(d, size=(2000, len(d)), replace=True), axis=1)
            res.append(dict(variant=name.replace("range_s_", ""), mount_deg=float(mount), n=int(len(d)), delta_common_median=float(np.median(d)), ci95=[float(np.percentile(med, 2.5)), float(np.percentile(med, 97.5))],
                            share_better=float((d < 0).mean()), share_worse=float((d > 0).mean()), rmse_common_median=float(g.heading_rmse_common_deg_x.median()),
                            rmse_common_median_sweep=float(g.heading_rmse_common_deg_sweep.median()), rmse_all_median=float(g.heading_rmse_deg_x.median()),
                            rmse_probe_median=float(g.heading_rmse_probe_deg_x.median()) if g.heading_rmse_probe_deg_x.notna().any() else None,
                            frac10_mean=float(g.wrong_branch_frac_10_x.mean()), nees_mean=float(g.nees_mean_x.mean()), nees_cov95=float(g.nees_cov95_x.mean()),
                            elapsed_s=float(g.duration_s_x.median())))
    out = pd.DataFrame(res)
    pd.set_option("display.width", 250)
    print(out.round(3).to_string(index=False))
    a.out.write_text(json.dumps(dict(definition="A20", rows=res), indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path)
    ap.add_argument("--h-dir", type=Path)
    ap.add_argument("--lut-dir", type=Path)
    ap.add_argument("--trace-root", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--nproc", type=int, default=4)
    ap.add_argument("--analyze", type=Path)
    a = ap.parse_args()
    analyze(a) if a.analyze else run(a)


if __name__ == "__main__":
    main()
