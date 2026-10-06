"""For every simulated coordinate: antenna angles from the geometry -> yaw curve from the angles alone -> compare with the simulated curve.

Per robot position (x, y) the anchor-to-robot line gives
  * transmit direction in the anchor frame:   theta (off boresight) and phi_tx = -atan2(y - y_a, x - x_a)   (anchor frame is flipped about x),
  * receive direction in the robot frame:     the same theta, and phi_rx = (azimuth of the anchor seen from the robot) - yaw.
The angle-only curve reads both FFD patterns at exactly those directions (LoS only, no reflections, link length = the real range).
It is compared with the simulated curve of that position (all paths) and with the ideal on-axis curve.

  python scripts/corridor_angle_model_compare.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_shift_fit as sf  # noqa: E402
import corridor_tx_angle_sweep as ta  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

rmse = lambda a, b: float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "ANGLE_MODEL_COMPARE.json")
    ap.add_argument("--png", action="store_true", help="also write static PNG grids next to the JSON")
    args = ap.parse_args()
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    a = setup.anchor_position
    dz = a[2] - setup.robot_antenna_z_m
    rows = []
    for p in shift["positions"]:
        dx, dy = p["x"] - a[0], p["y"] - a[1]
        d_h = float(np.hypot(dx, dy))
        theta = float(np.degrees(np.arctan2(d_h, dz)))
        alpha = float(np.degrees(np.arctan2(dy, dx))) if d_h > 1e-9 else 0.0
        phi_tx = -alpha
        bearing = float(np.degrees(np.arctan2(-dy, -dx))) if d_h > 1e-9 else 0.0   # azimuth of the anchor seen from the robot, world frame
        rng = float(np.hypot(d_h, dz))
        ta.LINK_M = rng
        model = ta.one(banks, np.radians(theta), np.radians(phi_tx), rx_actual=True, tx_actual=True)
        row = dict(x=p["x"], y=p["y"], range_m=rng, theta_tx_deg=theta, phi_tx_deg=phi_tx, theta_rx_deg=theta, anchor_bearing_world_deg=bearing,
                   phi_rx_at_yaw0_deg=float((bearing + 180) % 360 - 180), tx={})
        for tn in sf.TX:
            d = p["tx"][tn]
            m = np.array(model[tn]["ratio"])
            ideal, los, full = np.array(d["ratio_ideal"]), np.array(d["ratio_los"]), np.array(d["ratio_full"])
            r_ideal, r_model, r_los = rmse(ideal, full), rmse(m, full), rmse(m, los)
            row["tx"][tn] = dict(ratio_angle_model=m.tolist(), ratio_ideal=ideal.tolist(), ratio_los_sim=los.tolist(), ratio_full_sim=full.tolist(),
                                 rmse_ideal_vs_full=r_ideal, rmse_model_vs_full=r_model, rmse_model_vs_los_sim=r_los,
                                 explained=None if r_ideal < 1e-6 else float(1 - (r_model / r_ideal) ** 2), fit_model=dict(yaw0=model[tn]["yaw0"], B=model[tn]["B"], A=model[tn]["A"]))
        rows.append(row)
    rows.sort(key=lambda r: (r["x"], r["y"]))
    args.out.write_text(json.dumps(dict(yaw_deg=sf.YAWS.tolist(), positions=rows), indent=1))
    for r in rows:
        t = r["tx"]
        print(f"({r['x']:5.1f},{r['y']:5.2f}) R={r['range_m']:5.2f} theta={r['theta_tx_deg']:5.1f} phi_tx={r['phi_tx_deg']:+6.1f} phi_rx(0)={r['phi_rx_at_yaw0_deg']:+7.1f} | "
              + " | ".join(f"{k[3:]}: ideal-vs-sim {v['rmse_ideal_vs_full']:.3f} model-vs-sim {v['rmse_model_vs_full']:.3f} model-vs-LoS {v['rmse_model_vs_los_sim']:.4f}" for k, v in t.items()))
    if args.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for tn in sf.TX:
            fig, axes = plt.subplots(3, 4, figsize=(15, 9.5), dpi=120, sharex=True, sharey=True)
            for ax, r in zip(axes.ravel(), rows):
                v = r["tx"][tn]
                ax.plot(sf.YAWS, v["ratio_ideal"], color="#7b8794", ls="--", lw=1.3, label="ideal on-axis")
                ax.plot(sf.YAWS, v["ratio_angle_model"], color="#2a78d6", lw=2, label="angle-only model (TX+RX angles, LoS)")
                ax.plot(sf.YAWS, v["ratio_full_sim"], color="#eb6834", lw=2, marker="o", ms=3.5, label="simulated (all paths)")
                ax.set_title(f"({r['x']:g}, {r['y']:g})  θ={r['theta_tx_deg']:.0f}°  φtx={r['phi_tx_deg']:+.0f}°  φrx(0°)={r['phi_rx_at_yaw0_deg']:+.0f}°\nRMSE ideal {v['rmse_ideal_vs_full']:.3f} → model {v['rmse_model_vs_full']:.3f}", fontsize=9)
                ax.grid(alpha=0.25)
            for ax in axes[-1]:
                ax.set_xlabel("robot yaw (deg)")
            for ax in axes[:, 0]:
                ax.set_ylabel("|P1-P2|/(P1+P2)")
            axes[0, 0].legend(fontsize=7, loc="lower left")
            fig.suptitle(f"Anchor {tn}: yaw curve from TX+RX angles vs simulated curve at each coordinate", fontsize=12)
            fig.tight_layout()
            fig.savefig(args.out.parent / f"angle_model_vs_simulated_{tn}.png")
            plt.close(fig)


if __name__ == "__main__":
    main()
