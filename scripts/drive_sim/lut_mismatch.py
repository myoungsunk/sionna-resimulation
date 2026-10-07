"""S4 report: LUT (LoS-only) vs the full simulation along the trajectories -> mismatch sigma for the filter's R_s.

  python scripts/drive_sim/lut_mismatch.py --s1 S1 --h-dir S2 --lut S4/hs_lut_2deg.npy --out S4/LUT_MISMATCH.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--laterals", type=float, nargs="*", default=[0.0, 0.35])
    ap.add_argument("--mounts", type=float, nargs="*", default=[0.0, 45.0])
    args = ap.parse_args()
    setup = CorridorSetup()
    meta = json.loads((args.lut.parent / "hs_lut_meta.json").read_text())["meta"]
    lut = HsLut(dict(theta_deg=np.array(meta["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["phi_deg"][2]), s=np.load(args.lut)))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    report, allres = {}, []
    for lat in args.laterals:
        for mount in args.mounts:
            h = np.load(args.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            w = E.make_world(args.s1 / f"timeline_y{lat:g}_Tnone.csv", h, freqs, lat, mount, None)
            obs = O.observe(w.h, w.freqs, None, None)
            tr = w.truth
            s_lut, jac = s_model(lut, setup.anchor_position, setup.robot_antenna_z_m, tr[:, 0], tr[:, 1], tr[:, 2], mount, with_jac=True)
            res = obs["s"] - s_lut
            slope = np.abs(jac[:, 2]) * np.pi / 180.0                 # |ds / d yaw| per degree
            phase = np.array([r["phase"] for r in w.rows])
            bins = [(0, 0.005), (0.005, 0.015), (0.015, 0.03), (0.03, 1.0)]
            ok = np.isfinite(res)
            entry = dict(n=int(ok.sum()), bias=float(np.mean(res[ok])), sigma=float(np.std(res[ok])), rms=float(np.sqrt(np.mean(res[ok] ** 2))),
                         fp_index_median=int(np.median(obs["index"])),
                         by_slope_per_deg={f"{lo}-{hi}": dict(n=int((ok & (slope >= lo) & (slope < hi)).sum()),
                                                              rms=float(np.sqrt(np.mean(res[ok & (slope >= lo) & (slope < hi)] ** 2))) if (ok & (slope >= lo) & (slope < hi)).any() else None) for lo, hi in bins},
                         by_phase={p: float(np.sqrt(np.mean(res[ok & (phase == p)] ** 2))) for p in sorted(set(phase)) if (ok & (phase == p)).any()})
            report[f"y{lat:g}_m{mount:g}"] = entry
            allres.append(res[ok])
    allres = np.concatenate(allres)
    report["overall"] = dict(n=int(allres.size), bias=float(allres.mean()), sigma=float(allres.std()), rms=float(np.sqrt(np.mean(allres ** 2))))
    report["note"] = "rms overall is the number to pass as --mismatch-sigma to run_experiments.py (fixed once, for all conditions)"
    args.out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report["overall"]))


if __name__ == "__main__":
    main()
