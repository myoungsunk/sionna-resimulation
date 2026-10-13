"""Figure: corridor, all driven routes (R1, R2, R4, R5) and the two anchor positions.

  python scripts/drive_sim/plot_routes_anchors.py --s1 results/DRIVE_SIM_20261007/S1 --out results/DRIVE_SIM_20261007/FIGURES
Data: truth timelines only (S1/timeline_y*_T10.csv, S1/routes/timeline_R*_T10.csv); no RF.  Writes routes_anchors_overview.png + .manifest.json.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim.config import build_manifest  # noqa: E402
from qclean_uwb.drivesim.routes import ANCHORS  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2dd"
BLUE, ORANGE, VIOLET, GREEN = "#2a78d6", "#eb6834", "#4a3aa7", "#1b8a5a"
DRIVE = ("drive", "drive_out", "drive_back")


def read(path):
    rows = list(csv.DictReader(Path(path).open()))
    g = lambda k, f=float: np.array([f(r[k]) for r in rows])  # noqa: E731
    return dict(t=g("t_s"), x=g("x"), y=g("y"), phase=np.array([r["phase"] for r in rows]), probe=g("probe_id", int))


def panel(ax, s, curves, title, note):
    ax.set_xlim(-0.6, 20.6)
    ax.set_ylim(-1.45, 1.45)
    ax.set_aspect("equal")
    ax.add_patch(plt.Rectangle((0, -s.y_half), s.length_m, 2 * s.y_half, fc="#f1f0ec", ec=INK2, lw=1.2, zorder=0))
    ax.axhline(s.robot_y_limit_m, color=INK2, ls=(0, (4, 4)), lw=0.7, zorder=1)
    ax.axhline(-s.robot_y_limit_m, color=INK2, ls=(0, (4, 4)), lw=0.7, zorder=1)
    for d, col, lab in curves:
        m = np.isin(d["phase"], DRIVE)
        ax.plot(d["x"][m], d["y"][m], color=col, lw=1.8, zorder=3, label=lab)
        pk = d["probe"] >= 0
        if pk.any():
            px = sorted({(round(x, 3), round(y, 3)) for x, y in zip(d["x"][pk], d["y"][pk])})
            ax.scatter(*zip(*px), s=18, facecolor=SURFACE, edgecolor=col, lw=1.3, zorder=4)
        ax.scatter([d["x"][0]], [d["y"][0]], marker="o", s=44, color=col, edgecolor=SURFACE, lw=1.2, zorder=5)
        ax.scatter([d["x"][-1]], [d["y"][-1]], marker="s", s=40, color=col, edgecolor=SURFACE, lw=1.2, zorder=5)
    for name, (ax_x, ax_y) in ANCHORS.items():
        ax.scatter([ax_x], [ax_y], marker="^", s=110, color=INK, zorder=7)
        ax.plot([ax_x, ax_x], [ax_y, 0.88], color=INK2, lw=0.6, zorder=6)
        ax.text(ax_x, 0.9, f"anchor {name} (x = {ax_x:g} m)", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_title(title, loc="left", fontsize=10.5)
    ax.text(20.5, 1.38, note, ha="right", va="top", fontsize=8, color=INK2)
    ax.set_ylabel("y [m]")
    if any(lab for _, _, lab in curves):
        ax.legend(loc="lower right", frameon=False, fontsize=8, ncol=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    s = CorridorSetup()
    rd = args.s1 / "routes"
    r1a, r1b = read(args.s1 / "timeline_y0_T10.csv"), read(args.s1 / "timeline_y0.35_T10.csv")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "axes.edgecolor": GRID, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE})
    fig, axs = plt.subplots(4, 1, figsize=(12, 10.2), sharex=True)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.91, bottom=0.06, hspace=0.38)
    fig.suptitle("Corridor 20 m × 2.4 m × 2.7 m: tag (robot) routes and anchor positions (top view, true scale)", x=0.06, ha="left", fontsize=13, fontweight="bold")
    panel(axs[0], s, [(r1a, BLUE, "y0 = 0"), (r1b, ORANGE, "y0 = 0.35 m")],
          "R1  straight out-and-back (x 1.2 → 18.8 → 1.2, 180° in-place turn at the end)", "o start  ■ end  ○ probe stops (T = 10 s)")
    panel(axs[1], s, [(read(rd / "timeline_R2_T10.csv"), BLUE, "")], "R2  rectangle / loop closure (start = end)", "")
    panel(axs[2], s, [(read(rd / "timeline_R4_T10.csv"), VIOLET, "")], "R4  zigzag (±0.45 m, 35.7°)", "")
    panel(axs[3], s, [(read(rd / "timeline_R5_T10.csv"), GREEN, "")], "R5  serpentine (lanes y = +0.45 / 0 / −0.45 m)", "")
    axs[3].set_xlabel("x along the corridor [m]")
    fig.text(0.06, 0.945, "dashed lines: allowed robot region |y| ≤ %.2f m; anchors 5 cm below the ceiling (z = 2.65 m) above y = 0, boresight down; robot antenna z = 0.45 m" % s.robot_y_limit_m, fontsize=8.5, color=INK2)
    out = args.out / "routes_anchors_overview.png"
    fig.savefig(out, dpi=150)
    inputs = sorted([str(args.s1 / "timeline_y0_T10.csv"), str(args.s1 / "timeline_y0.35_T10.csv")] + [str(rd / f"timeline_R{r}_T10.csv") for r in (2, 4, 5)])
    import json
    man = build_manifest(config=dict(figure="routes_anchors_overview", source="truth timelines T10, CorridorSetup defaults, ANCHORS A/B"), inputs=inputs, outputs=[str(out)], command=sys.argv)
    (args.out / "routes_anchors_overview.manifest.json").write_text(json.dumps(man, indent=2, default=str))
    print("wrote", out)


if __name__ == "__main__":
    main()
