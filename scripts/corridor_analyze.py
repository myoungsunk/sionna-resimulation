"""Compute |p1-p2|/|p1+p2| along the yaw sweep from the corridor Sionna output.

p1 = robot RX port +45, p2 = robot RX port -45, for each anchor TX port (+45 / -45),
evaluated per frequency bin; the table reports median and inter-quartile range over the
257 bins. The LoS-only curve (paths with no interaction) is compared with the ideal
analytic curve |tan(yaw + 45 deg)| for the on-axis position.

  python scripts/corridor_analyze.py --sweep-dir results/CORRIDOR_SWEEP_20261006
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.features.port_ratio import los_two_port_ratio, port_difference_ratio  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

C0 = 299792458.0
TX = ("LP_plus45", "LP_minus45")


def los_only_H(z) -> np.ndarray:
    """H restricted to interaction-free paths, shape [yaw, bin, 2, 2]."""
    n_yaw, n_bin = len(z["yaw_deg"]), len(z["bin_index"])
    off, a, tau, inter, f = z["offsets"], z["a_cat"], z["tau_cat"], z["interactions_cat"], z["freqs_hz"]
    out = np.zeros((n_yaw, n_bin, 2, 2), np.complex128)
    n_los = np.zeros((n_yaw, n_bin), int)
    for bi in range(n_bin):
        for yi in range(n_yaw):
            k = bi * n_yaw + yi
            sl = slice(off[k], off[k + 1])
            is_los = ~inter[:, sl].any(axis=0)
            n_los[yi, bi] = is_los.sum()
            out[yi, bi] = (a[..., sl][..., is_los] * np.exp(-2j * np.pi * f[bi] * tau[sl][is_los])).sum(-1)
    return out, n_los


def first_path_delay_error(z) -> float:
    n_yaw, n_bin = len(z["yaw_deg"]), len(z["bin_index"])
    off, tau = z["offsets"], z["tau_cat"]
    dist = float(np.linalg.norm(z["robot_antenna_m"] - z["anchor_m"]))
    worst = 0.0
    for k in range(n_yaw * n_bin):
        worst = max(worst, abs(float(tau[off[k]:off[k + 1]].min()) - dist / C0))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-dir", type=Path, default=ROOT / "results" / "CORRIDOR_SWEEP_20261006")
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()
    setup = CorridorSetup()
    rows, series, checks = [], [], []
    yaws = np.array(setup.yaw_sweep_deg)
    for pos, (x, y) in enumerate(setup.example_xy_m):
        z = np.load(args.sweep_dir / f"pos{pos}" / f"position_{pos}_sweep.npz")
        H = z["H"]
        assert H.shape == (len(yaws), 257, 2, 2) and np.array_equal(z["yaw_deg"], yaws), f"COVERAGE position {pos}"
        Hl, n_los = los_only_H(z)
        total_pow = (np.abs(H) ** 2).sum((-1, -2))
        los_frac = (np.abs(Hl) ** 2).sum((-1, -2)) / total_pow
        g = setup.link_geometry(x, y, 0.0)
        checks.append(dict(position=pos, finite=bool(np.isfinite(H).all()), shape=list(H.shape), one_los_path_every_call=bool((n_los == 1).all()),
                           first_path_delay_error_s=first_path_delay_error(z), mean_paths=float(z["path_counts"].mean()),
                           los_power_fraction_median=float(np.median(los_frac)), range_m=round(g["range_m"], 3),
                           anchor_off_boresight_deg=round(g["anchor_off_boresight_deg"], 2)))
        for ti, tname in enumerate(TX):
            full = port_difference_ratio(H[:, :, 0, ti], H[:, :, 1, ti])    # [yaw, bin]
            los = port_difference_ratio(Hl[:, :, 0, ti], Hl[:, :, 1, ti])
            q25, med, q75 = (np.nanpercentile(np.where(np.isfinite(full), full, np.nan), q, axis=1) for q in (25, 50, 75))
            los_med = np.median(los, axis=1)
            series.append(dict(position=pos, xy=[x, y], tx_port=tname, yaw_deg=yaws.tolist(), median=med.tolist(), q25=q25.tolist(),
                               q75=q75.tolist(), los_only_median=los_med.tolist(), range_m=g["range_m"],
                               los_power_fraction_median=float(np.median(los_frac))))
            for yi, yaw in enumerate(yaws):
                rows.append(dict(position=pos, x_m=x, y_m=y, tx_port=tname, yaw_deg=yaw, ratio_median=med[yi], ratio_q25=q25[yi],
                                 ratio_q75=q75[yi], ratio_los_only_median=los_med[yi], ratio_ideal_los=float(los_two_port_ratio(yaw))))
    # On-axis (position 0) LoS-only curve vs ideal analytic curve, in dB, where the ideal ratio is in [0.25, 4].
    p0 = next(s for s in series if s["position"] == 0 and s["tx_port"] == TX[0])
    ideal = los_two_port_ratio(yaws)
    sel = (ideal > 0.25) & (ideal < 4.0)
    dev_db = np.abs(20 * np.log10(np.array(p0["los_only_median"])[sel]) - 20 * np.log10(ideal[sel]))
    null_yaw = float(yaws[int(np.argmin(p0["los_only_median"]))])
    peak_yaw = float(yaws[int(np.argmax(np.where(np.isfinite(p0["los_only_median"]), p0["los_only_median"], -1)))])
    validation = dict(
        status="SWEEP_COMPLETE_ANALYSED", positions=len(checks), per_position=checks,
        on_axis_los_vs_ideal=dict(max_abs_deviation_db=float(dev_db.max()), yaws_compared=yaws[sel].tolist(),
                                  los_only_null_yaw_deg=null_yaw, ideal_null_yaw_deg=135.0, los_only_peak_yaw_deg=peak_yaw, ideal_peak_yaw_deg=45.0),
        metric="abs(p1-p2)/abs(p1+p2); p1=robot RX +45 port, p2=robot RX -45 port, per anchor TX port; median over 257 bins",
        notes=["Ideal curve assumes ideal +45/-45 ports with aligned boresights; real FFD banks and the 8 degree port phase offset shift it.",
               "Ratio is unbounded at nulls of p1+p2; medians are over bins, nulls can move with frequency."])
    out = args.sweep_dir
    with (out / "ratio_table.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    (out / "ratio_series.json").write_text(json.dumps(dict(series=series, ideal=dict(yaw_deg=yaws.tolist(), ratio=ideal.tolist())), indent=1))
    (out / "VALIDATION.json").write_text(json.dumps(validation, indent=2))
    if not args.no_png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), sharey=True, dpi=130)
        for ax, tname in zip(axes, TX):
            for s in (s for s in series if s["tx_port"] == tname):
                c = colors[s["position"]]
                ax.fill_between(yaws, s["q25"], s["q75"], color=c, alpha=0.12, lw=0)
                ax.plot(yaws, s["median"], color=c, lw=2, marker="o", ms=4, label=f"x={s['xy'][0]:g}, y={s['xy'][1]:g}  R={s['range_m']:.1f} m")
            ax.plot(yaws, ideal, color="#777", ls="--", lw=1.2, label="ideal on-axis LoS |tan(yaw+45°)|")
            ax.set(yscale="log", xlabel="robot yaw (deg)", title=f"anchor TX {tname}", xticks=range(0, 181, 30))
            ax.grid(alpha=0.25)
        axes[0].set_ylabel("|p1-p2| / |p1+p2|")
        axes[0].legend(fontsize=8, loc="lower left")
        fig.tight_layout()
        fig.savefig(out / "ratio_vs_yaw.png")
    print(json.dumps(dict(rows=len(rows), on_axis_max_dev_db=round(float(dev_db.max()), 2), null_yaw=null_yaw, peak_yaw=peak_yaw)))


if __name__ == "__main__":
    main()
