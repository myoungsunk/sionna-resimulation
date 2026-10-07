"""A9: LUT-vs-simulation mismatch on the added routes and both anchors (feeds --mismatch-sigma of run_route_experiments.py).

  python scripts/drive_sim/lut_mismatch_routes.py --s1-routes S1/routes --h-dir S2 --lut S4/hs_lut_2deg.npy --out S4/LUT_MISMATCH_ROUTES.json
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

ANCHOR_X = {"A": 4.0, "B": 10.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1-routes", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--routes", nargs="*", default=["R2", "R4", "R5"])
    args = ap.parse_args()
    doc = json.loads((args.lut.parent / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(args.lut)))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    rep, allres = {}, []
    for route in args.routes:
        for anchor, ax in ANCHOR_X.items():
            setup = CorridorSetup(anchor_x_m=ax)
            for mount in (0.0, 45.0):
                h = np.load(args.h_dir / f"H_{route}_a{anchor}_m{mount:g}.npy", mmap_mode="r")
                w = E.make_world(args.s1_routes / f"timeline_{route}_Tnone.csv", h, freqs, 0.0, mount, None, route=route, anchor=anchor)
                obs = O.observe(w.h, w.freqs, None, None)
                tr = w.truth
                res = obs["s"] - s_model(lut, setup.anchor_position, setup.robot_antenna_z_m, tr[:, 0], tr[:, 1], tr[:, 2], mount)
                ok = np.isfinite(res)
                rep[f"{route}_a{anchor}_m{mount:g}"] = dict(n=int(ok.sum()), bias=float(res[ok].mean()), sigma=float(res[ok].std()), rms=float(np.sqrt(np.mean(res[ok] ** 2))))
                allres.append(res[ok])
    allres = np.concatenate(allres)
    rep["overall"] = dict(n=int(allres.size), bias=float(allres.mean()), sigma=float(allres.std()), rms=float(np.sqrt(np.mean(allres ** 2))))
    args.out.write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep["overall"]))


if __name__ == "__main__":
    main()
