"""Figure: the corridor, the driven route (both laterals), the anchor geometry and the heading/position time series.

  python scripts/drive_sim/plot_route.py --s1 results/DRIVE_SIM_20261007/S1 --out results/DRIVE_SIM_20261007/FIGURES
Data: S1/timeline_y{0,0.35}_T{none,10}.csv (truth only, no RF).  Writes route_overview.png and route_overview.manifest.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim.config import build_manifest  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2dd"
BLUE, ORANGE, VIOLET = "#2a78d6", "#eb6834", "#4a3aa7"


def read(path):
    rows = list(csv.DictReader(Path(path).open()))
    g = lambda k, f=float: np.array([f(r[k]) for r in rows])  # noqa: E731
    return dict(t=g("t_s"), x=g("x"), y=g("y"), yaw=g("yaw_body_deg"), phase=np.array([r["phase"] for r in rows]), probe=g("probe_id", int), g=g("drive_g", int))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    s = CorridorSetup()
    d0, d35 = read(args.s1 / "timeline_y0_T10.csv"), read(args.s1 / "timeline_y0.35_T10.csv")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.edgecolor": GRID, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE})
    fig = plt.figure(figsize=(13, 9.6))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.35, 1.0, 1.15], hspace=0.55, wspace=0.22, left=0.06, right=0.97, top=0.93, bottom=0.07)
    fig.suptitle("Corridor driving simulation: scripted route (truth)", x=0.06, ha="left", fontsize=14, fontweight="bold")

    # ---- A: top view
    ax = fig.add_subplot(gs[0, :])
    ax.set_xlim(-0.6, 20.6)
    ax.set_ylim(-1.45, 1.45)
    ax.add_patch(plt.Rectangle((0, -s.y_half), s.length_m, 2 * s.y_half, fc="#f1f0ec", ec=INK2, lw=1.2, zorder=0))
    ax.axhspan(-s.robot_y_limit_m, s.robot_y_limit_m, xmin=(1 + 0.6) / 21.2, xmax=(19 + 0.6) / 21.2, fc="none", ec=INK2, ls=(0, (4, 4)), lw=0.8, zorder=1)
    ax.text(1.1, -s.robot_y_limit_m - 0.05, "allowed robot region (|y| ≤ 0.74 m)", fontsize=8, color=INK2, va="top", ha="left")
    for d, col, lab in ((d0, BLUE, "lateral y0 = 0"), (d35, ORANGE, "lateral y0 = 0.35 m")):
        drive = np.isin(d["phase"], ["drive_out", "drive_back"])
        ax.plot(d["x"][drive], d["y"][drive], color=col, lw=2.0, solid_capstyle="round", label=lab, zorder=3)
        pk = d["probe"] >= 0
        px = sorted({(round(x, 4), round(y, 4)) for x, y in zip(d["x"][pk], d["y"][pk])})
        ax.scatter(*zip(*px), s=26, facecolor=SURFACE, edgecolor=col, lw=1.6, zorder=4)
        i0 = int(np.argmax(d["phase"] == "turn"))
        ax.scatter([d["x"][i0]], [d["y"][i0]], marker="D", s=46, color=col, edgecolor=SURFACE, lw=1.5, zorder=5)
        ax.scatter([d["x"][0]], [d["y"][0]], marker="o", s=62, color=col, edgecolor=SURFACE, lw=1.5, zorder=5)
    for xa in (6.0, 12.5):
        ax.annotate("", xy=(xa + 1.0, 0.0 + 0.0), xytext=(xa, 0.0), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.4), zorder=6)
    ax.text(6.5, -0.16, "out: heading 0°", ha="center", va="top", fontsize=8.5, color=INK)
    ax.annotate("", xy=(15.0, -0.30), xytext=(16.0, -0.30), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.4))
    ax.text(15.5, -0.36, "back: heading 180°", ha="center", va="top", fontsize=8.5, color=INK)
    ax.scatter([s.anchor_x_m], [s.anchor_y_m], marker="^", s=120, color=INK, zorder=7)
    ax.annotate("anchor (ceiling, x=4 m, y=0)\nboresight down, TX +45° port", (s.anchor_x_m, s.anchor_y_m), xytext=(4.6, 0.98), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8), va="center")
    ax.annotate("start x = 1.2 m", (d0["x"][0], d0["y"][0]), xytext=(0.2, -0.62), fontsize=8.5, color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.annotate("end x ≈ 18.8 m:\nin-place 180° turn (7.2 s)", (d0["x"][int(np.argmax(d0["phase"] == "turn"))], 0), xytext=(14.6, 0.98), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8), va="center")
    ax.set_xlabel("x along the corridor [m]")
    ax.set_ylabel("y [m]")
    ax.set_title("A  Top view (y axis stretched: the whole route stays within ~9 cm of its centre line). Circles = probe stops for T = 10 s, ◆ = turn point", loc="left", fontsize=10.5)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h, l, loc="upper left", frameon=False, ncol=2, bbox_to_anchor=(0.0, 1.0), fontsize=9)
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    # ---- B: side view
    ax = fig.add_subplot(gs[1, :])
    ax.set_xlim(-0.6, 20.6)
    ax.set_ylim(-0.25, 3.15)
    ax.add_patch(plt.Rectangle((0, 0), s.length_m, s.height_m, fc="#f1f0ec", ec=INK2, lw=1.2, zorder=0))
    a = s.anchor_position
    ax.scatter([a[0]], [a[2]], marker="v", s=110, color=INK, zorder=6)
    ax.text(a[0] + 0.25, a[2] + 0.12, "anchor z = 2.65 m", fontsize=8.5, color=INK, va="bottom")
    ax.axhline(s.robot_antenna_z_m, color=BLUE, lw=2.0, xmin=(1.2 + 0.6) / 21.2, xmax=(18.8 + 0.6) / 21.2, zorder=3)
    ax.text(15.0, s.robot_antenna_z_m - 0.09, "robot antenna z = 0.45 m (boresight up)", fontsize=8.5, color=INK, va="top", ha="center")
    for x in (1.2, 10.0, 18.8):
        ax.plot([a[0], x], [a[2], s.robot_antenna_z_m], color=INK2, lw=0.9, ls=(0, (3, 3)), zorder=2)
        ax.scatter([x], [s.robot_antenna_z_m], s=34, color=BLUE, edgecolor=SURFACE, lw=1.2, zorder=4)
        th = np.degrees(np.arctan2(abs(x - a[0]), a[2] - s.robot_antenna_z_m))
        ax.text((a[0] + x) / 2 + (0.35 if x > a[0] else -0.35), (a[2] + s.robot_antenna_z_m) / 2 + 0.05, f"θ = {th:.0f}°", fontsize=8.5, color=INK, ha="left" if x > a[0] else "right")
    ax.text(0.15, 2.82, "ceiling", fontsize=8.5, color=INK2)
    ax.text(0.15, 0.06, "floor", fontsize=8.5, color=INK2)
    ax.set_xlabel("x along the corridor [m]")
    ax.set_ylabel("z [m]")
    ax.set_title("B  Side view: line of sight to the anchor (θ = angle from the anchor's vertical axis)", loc="left", fontsize=10.5)
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    # ---- C: heading vs time ; D: position vs time
    for k, (d, title) in enumerate(((d0, "C  Body heading vs time (probe period T = 10 s)"), (d0, "D  Position x vs time"))):
        ax = fig.add_subplot(gs[2, k])
        for ph, col in (("drive_out", BLUE), ("turn", INK), ("drive_back", ORANGE)):
            m = d["phase"] == ph
            ax.plot(d["t"][m], (d["yaw"] if k == 0 else d["x"])[m], ".", ms=1.6, color=col, label={"drive_out": "drive out", "turn": "180° turn", "drive_back": "drive back"}[ph])
        m = d["phase"] == "probe"
        ax.plot(d["t"][m], (d["yaw"] if k == 0 else d["x"])[m], ".", ms=2.2, color=VIOLET, label="probe (±45°, 7.2 s each)")
        ax.set_xlabel("time [s]")
        ax.set_ylabel("body yaw [deg]" if k == 0 else "x [m]")
        ax.set_title(title, loc="left", fontsize=10.5)
        ax.grid(color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        if k == 0:
            ax.set_yticks([-45, 0, 45, 90, 135, 180, 225])
            ax.legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(0.0, 0.68), markerscale=5)
        else:
            ax.text(0.98, 0.93, "flat steps = probes and the turn (robot stopped)\nwithout probes the run lasts 183 s, with T = 10 s 306 s", transform=ax.transAxes, ha="right", va="top", fontsize=8, color=INK2)
    out = args.out / "route_overview.png"
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    man = build_manifest(config=dict(figure="route_overview", source="S1 timelines (truth), CorridorSetup defaults"),
                         inputs=[args.s1 / "timeline_y0_T10.csv", args.s1 / "timeline_y0.35_T10.csv", Path(__file__)], outputs=[out])
    (args.out / "route_overview.manifest.json").write_text(json.dumps(man, indent=1))
    print(out)


if __name__ == "__main__":
    main()
