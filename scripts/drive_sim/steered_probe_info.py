"""A18 stage 1: information-level comparison of the stored sweep probe and the steered probe (no RF, no filter run).

  python scripts/drive_sim/steered_probe_info.py --s1 S1 --lut-dir S4 --out DEV_RESULTS/STEERED_PROBE_INFO_A18.json
Definitions: S0/PREREG_AMENDMENTS.md A18.  Reuses the A16 B linearised batch information (observability_check.py).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import observability_check as OBS  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.drivesim.steered_probe import steer_rows  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

ERRORS = (0.0, 5.0, 10.0)


def read_full(path):
    rows = []
    for r in csv.DictReader(Path(path).open()):
        rows.append(dict(x=float(r["x"]), y=float(r["y"]), yaw_body_deg=float(r["yaw_body_deg"]), drive_g=int(r["drive_g"]), probe_id=int(r["probe_id"]),
                         probe_offset_deg=float(r["probe_offset_deg"]), phase=r["phase"], turn_phase=r["turn_phase"] == "True"))
    return rows


def to_obs_rows(rows):
    return [dict(x=r["x"], y=r["y"], yaw=math.radians(r["yaw_body_deg"]), drive_g=r["drive_g"], probe_id=r["probe_id"]) for r in rows]


def evaluate(rows, lut, anchor_xyz, robot_z, mount):
    obs = to_obs_rows(rows)
    info, Jx, traj = OBS.information(obs, lut, anchor_xyz, robot_z, mount, True, True)
    summ = OBS.summarize_info(info, Jx, obs)
    pr = np.array([r["probe_id"] >= 0 and r["drive_g"] >= OBS.COMMON_FROM for r in obs])
    _, js = s_model(lut, anchor_xyz, robot_z, traj[:, 0], traj[:, 1], traj[:, 2], mount, with_jac=True)
    slope = np.abs(js[:, 2]) * math.pi / 180.0                       # |ds/dpsi| per degree
    return dict(heading_std_common_mean_deg=summ["heading_std_common_mean_deg"], min_whitened_eig=summ["whitened_info_eigenvalues"][-1],
                mean_abs_slope_probe_per_deg=float(slope[pr].mean()) if pr.any() else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--lut-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    meta = json.loads((a.lut_dir / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(meta["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["meta"]["phi_deg"][2]), s=np.load(a.lut_dir / "hs_lut_2deg.npy")))
    cases = [("R1", "A", lat, f"timeline_y{lat:g}_T{{}}.csv", a.s1) for lat in (0.0, 0.35)]
    cases += [(r, an, 0.0, f"timeline_{r}_T{{}}.csv", a.s1 / "routes") for r in ("R2", "R4", "R5") for an in ("A", "B")]
    results = []
    for route, an, lat, pat, root in cases:
        setup = CorridorSetup(anchor_x_m=4.0 if an == "A" else 10.0)
        for mount in (0.0, 45.0):
            for sched in ("60", "20", "10"):
                rows = read_full(root / pat.format(sched))
                rec = dict(route=route, anchor=an, lateral=lat, mount_deg=mount, schedule=f"T{sched}", sweep=evaluate(rows, lut, setup.anchor_position, setup.robot_antenna_z_m, mount))
                for e in ERRORS:
                    rec[f"steer_err{e:g}"] = evaluate(steer_rows(rows, mount, e), lut, setup.anchor_position, setup.robot_antenna_z_m, mount)
                results.append(rec)
                print(route, an, lat, mount, sched, "std sweep %.3f steer %.3f" % (rec["sweep"]["heading_std_common_mean_deg"], rec["steer_err0"]["heading_std_common_mean_deg"]), flush=True)
    a.out.write_text(json.dumps(dict(definition="A18 stage 1", results=results), indent=1))


if __name__ == "__main__":
    main()
