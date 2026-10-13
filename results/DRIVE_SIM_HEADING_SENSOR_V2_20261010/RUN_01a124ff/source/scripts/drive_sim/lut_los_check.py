"""S4 gate L2 (needs Sionna): LUT vs unmodified PathSolver with ``max_depth=0`` (LoS only), single-port-anchor chain.

  python scripts/drive_sim/lut_los_check.py --lut results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy --out results/DRIVE_SIM_20261007/S4/LUT_LOS_CHECK.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS / "g2_completion"))
import corridor_sionna_run as C  # noqa: E402
import mitsuba as mi  # noqa: E402
import sionna.rt as rt  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, geometry_angles  # noqa: E402
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, CorridorSetup  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lut", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261007)
    args = ap.parse_args()
    import drjit as dr
    dr.set_thread_count(1)
    setup = CorridorSetup()
    banks = C.load_banks()
    freq = banks[0]["freqs_hz"]
    meta = json.loads((args.lut.parent / "hs_lut_meta.json").read_text())["meta"]
    step = meta["phi_deg"][2]
    lut = HsLut(dict(theta_deg=np.array(meta["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, step), s=np.load(args.lut)))
    rng = np.random.default_rng(args.seed)
    cfg = dict(max_depth=0, los=True, specular_reflection=False, refraction=False)
    scene, _ = C.build_scene(setup, args.out.parent / "scene_lut_check")
    txp, rxp = C.make_ports(banks)
    solver, rows = rt.PathSolver(), []
    lo, hi = setup.robot_x_range_m
    for _ in range(args.n):
        x, y, yaw = rng.uniform(lo, hi), rng.uniform(-0.7, 0.7), rng.uniform(-50.0, 230.0)
        if "tx" in scene.transmitters:
            scene.remove("tx"); scene.remove("rx")
        scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=C.euler(ANCHOR_ROTATION)))
        scene.add(rt.Receiver("rx", position=setup.robot_position(x, y).tolist(), orientation=C.euler(setup.robot_rotation(yaw))))
        h = np.zeros((len(freq), 2, 2), complex)
        for fi in range(len(freq)):
            C.set_bin(scene, banks, txp, rxp, fi, freq[fi])
            coef, tau, _, _ = C.solve(solver, scene, cfg)
            h[fi] = (coef * np.exp(-2j * np.pi * freq[fi] * tau)[None, None, :]).sum(-1)
        s_sim = float(O.observe(h[None], freq, None, None, tx=0)["s"][0])
        th, pt, pr = geometry_angles(setup.anchor_position, setup.robot_position(x, y), yaw)
        rows.append(dict(x=float(x), y=float(y), yaw_deg=float(yaw), s_sionna=s_sim, s_lut=float(lut(th, pt, pr)), abs_ds=abs(s_sim - float(lut(th, pt, pr)))))
        print(json.dumps(rows[-1]), flush=True)
    rep = dict(rows=rows, abs_ds_max=max(r["abs_ds"] for r in rows), threshold=5e-3, passed=bool(max(r["abs_ds"] for r in rows) <= 5e-3))
    args.out.write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
