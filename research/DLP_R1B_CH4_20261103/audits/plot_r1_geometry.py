#!/usr/bin/env python3
"""Plot immutable R1 input geometry only; never imports RF or filter code."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "research/DLP_R1B_CH4_20261103"
CONTRACT = CASE / "00_REQUEST_CONTRACT_FROZEN_V2.json"
CONTRACT_SHA256 = "a31a537dd35823d10c1d74ee0cf488d439b7ba2c70114309e024b451a9468596"
COLORS = {"drive_out": "#17679A", "turn": "#D27922", "drive_back": "#247D68"}
PHASE_LABELS = {"drive_out": "Outbound", "turn": "In-place turn", "drive_back": "Inbound"}
EXPECTED_IDS = [0, 150, 221, 440, 458, 476, 696, 916]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path: Path) -> dict:
    try:
        name = str(path.relative_to(ROOT))
    except ValueError:
        name = str(path)
    return {"path": name, "bytes": path.stat().st_size, "sha256": digest(path)}


def style_axis(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#D6DCE1", linewidth=0.65, alpha=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=9)


def phases_plot(ax, x, y, phase, *, bridge=False):
    for name in ("drive_out", "turn", "drive_back"):
        ix = np.flatnonzero(phase == name)
        if bridge and ix[0] > 0:
            ix = np.r_[ix[0] - 1, ix]
        ax.plot(x[ix], y[ix], color=COLORS[name], lw=1.8,
                label=PHASE_LABELS[name], zorder=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=CASE / "figures")
    parser.add_argument("--replace-draft", action="store_true",
                        help="Regenerate this script's draft presentation files; never changes inputs.")
    args = parser.parse_args()
    output = args.out_dir.resolve()
    paths = [output / f"R1_GEOMETRY.{suffix}" for suffix in ("png", "pdf")]
    provenance_path = output / "R1_GEOMETRY_PROVENANCE.json"
    if not args.replace_draft and any(path.exists() for path in [*paths, provenance_path]):
        raise SystemExit("Refusing to overwrite prior figure/provenance; choose a new --out-dir.")
    if digest(CONTRACT) != CONTRACT_SHA256:
        raise SystemExit("Frozen V2 contract hash mismatch.")
    contract = json.loads(CONTRACT.read_text())
    pose_record = contract["inputs"]["pose_csv"]
    csv_path = ROOT / pose_record["path"]
    if digest(csv_path) != pose_record["sha256"]:
        raise SystemExit("Original CSV hash mismatch.")
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    columns = ("idx", "pose_id", "t_s", "x", "y", "yaw_body_deg")
    data = {name: np.array([float(row[name]) for row in rows]) for name in columns}
    phase = np.array([row["phase"] for row in rows])
    t, x, y, yaw = (data[name] for name in ("t_s", "x", "y", "yaw_body_deg"))
    ids = np.array(contract["canary"]["pose_ids"], dtype=int)
    assert ids.tolist() == EXPECTED_IDS
    assert len(rows) == 917 and np.all(data["idx"] == np.arange(917))
    assert np.all(data["pose_id"] == np.arange(917)) and np.all(np.diff(t) > 0)
    assert np.all(np.isfinite(np.column_stack([t, x, y, yaw])))
    anchor = np.array(contract["geometry"]["anchor_xyz_m"], dtype=float)
    tag_z = float(contract["geometry"]["tag_z_m"])
    xyz = np.column_stack([x, y, np.full(len(rows), tag_z)])
    distance = np.linalg.norm(xyz - anchor[None, :], axis=1)
    turn = np.flatnonzero(phase == "turn")
    assert np.all(x[turn] == x[turn[0]]) and np.all(y[turn] == y[turn[0]])
    assert int(np.sum(t >= 30.0)) == contract["population"]["t_ge_30_n"] == 767

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.labelsize": 10, "axes.titlesize": 11,
                         "axes.titleweight": "bold", "axes.titlelocation": "left",
                         "savefig.facecolor": "white", "pdf.fonttype": 42,
                         "svg.fonttype": "none"})
    fig = plt.figure(figsize=(13.2, 8.6), facecolor="white")
    grid = fig.add_gridspec(2, 12, left=0.07, right=0.975, bottom=0.17,
                            top=0.845, hspace=0.5, wspace=1.3)
    plan = fig.add_subplot(grid[0, :8])
    height = fig.add_subplot(grid[0, 8:])
    heading = fig.add_subplot(grid[1, :6])
    ranges = fig.add_subplot(grid[1, 6:])
    for ax in (plan, height, heading, ranges):
        style_axis(ax)
    fig.text(0.07, 0.956, "R1 / Anchor B: original input geometry", size=19, weight="bold")
    fig.text(0.07, 0.914,
             "y0.35 / Tnone   |   917 poses   |   0.0–183.2 s   |   mount 0°   |   eight preregistered canary poses",
             color="#4C5964", size=11)

    # Positions are never shifted to separate outbound/inbound traces.
    phases_plot(plan, x, y, phase)
    plan.scatter([x[turn[0]]], [y[turn[0]]], c=COLORS["turn"], s=100, zorder=4)
    plan.scatter(x[ids], y[ids], s=43, facecolors="white", edgecolors="#26323D", lw=1.1, zorder=5)
    offsets = {0: (4, -19), 150: (-8, -24), 221: (-4, -24),
               696: (7, 12), 916: (5, 11)}
    for k, offset in offsets.items():
        text = {0: "0: start", 916: "916: end"}.get(k, str(k))
        plan.annotate(text, (x[k], y[k]), xytext=offset, textcoords="offset points",
                      fontsize=9, color="#26323D", zorder=6)
    plan.annotate("440 / 458 / 476\nsame XY, changing yaw", (x[440], y[440]),
                  xytext=(14.3, 0.215), textcoords="data", fontsize=9,
                  arrowprops={"arrowstyle": "-", "lw": 0.8, "color": "#65717A"})
    for first, last, name in ((90, 109, "drive_out"), (743, 762, "drive_back")):
        plan.annotate("", (x[last], y[last]), (x[first], y[first]),
                      arrowprops={"arrowstyle": "-|>", "lw": 1.8, "color": COLORS[name]})
    plan.scatter(anchor[0], anchor[1], marker="*", color="#B84045", s=150, zorder=5)
    plan.annotate("Anchor B  (10, 0) m", anchor[:2], xytext=(11, 7),
                  textcoords="offset points", color="#963C41", fontsize=9)
    plan.set(xlim=(0.5, 20.1), ylim=(-0.05, 0.515), xlabel="x (m)", ylabel="y (m)")
    plan.set_title("(a) Plan view: original lateral variation", pad=10)
    plan.text(0.02, 0.47, f"Actual y: {y.min():.3f}–{y.max():.3f} m; unequal axis scales",
              transform=plan.transAxes, fontsize=9, color="#4C5964")
    plan.legend(loc="lower left", bbox_to_anchor=(0.01, 0.19), ncol=3,
                frameon=False, fontsize=9, columnspacing=1.4, handlelength=2.0)

    height.axhline(0, color="#6D767E", lw=1.1)
    height.plot([x.min(), x.max()], [tag_z, tag_z], color=COLORS["drive_out"], lw=2.1)
    height.plot([anchor[0], anchor[0]], [0, anchor[2]], color="#B84045", lw=1, ls="--")
    height.scatter(anchor[0], anchor[2], marker="*", color="#B84045", s=150, zorder=5)
    height.annotate("Anchor B\nz = 2.65 m", (anchor[0], anchor[2]), xytext=(8, 6),
                    textcoords="offset points", fontsize=9, color="#963C41")
    height.text(1.2, 0.73, "Tag z = 0.45 m", color=COLORS["drive_out"], fontsize=9)
    height.annotate("", (19.4, anchor[2]), (19.4, tag_z),
                    arrowprops={"arrowstyle": "<->", "lw": 1, "color": "#4C5964"})
    height.text(20.0, (anchor[2] + tag_z) / 2, "Δz = 2.20 m", rotation=90,
                va="center", fontsize=9, color="#4C5964")
    height.set(xlim=(0, 21.3), ylim=(-0.18, 3.3), xlabel="x (m)", ylabel="z (m)")
    height.set_yticks([0, 1, 2, 3])
    height.set_title("(b) Heights: XZ projection", pad=10)

    for ax in (heading, ranges):
        ax.axvspan(30.0, t[-1], color="#D8DEE4", alpha=0.23, zorder=0)
        ax.axvspan(t[turn[0]], t[turn[-1]], color=COLORS["turn"], alpha=0.09, zorder=0)
        ax.axvline(30.0, color="#596772", lw=0.9, ls=(0, (3, 3)), zorder=2)
        ax.set_xlim(-3, 188)
        ax.set_xticks([0, 30, 60, 90, 120, 150, 180])
        ax.set_xlabel("Time (s)")
    phases_plot(heading, t, yaw, phase, bridge=True)
    heading.scatter(t[ids], yaw[ids], s=32, facecolors="white", edgecolors="#26323D", lw=1, zorder=5)
    yaw_offsets = {0: (4, 10), 150: (-7, 10), 221: (-8, 10),
                   440: (-27, 10), 458: (-27, 0), 476: (8, -6),
                   696: (-8, -19), 916: (-17, -19)}
    for k in ids:
        heading.annotate(str(k), (t[k], yaw[k]), xytext=yaw_offsets[int(k)],
                         textcoords="offset points", fontsize=8.5, color="#26323D")
    heading.set_ylim(-28, 205)
    heading.set_yticks([0, 90, 180])
    heading.set_ylabel("Body yaw (deg, as stored)")
    heading.set_title("(c) Heading and all eight canary pose IDs", pad=10)

    phases_plot(ranges, t, distance, phase, bridge=True)
    ranges.scatter(t[ids], distance[ids], s=32, facecolors="white", edgecolors="#26323D", lw=1, zorder=5)
    for k in (221, 696):
        ranges.annotate(f"{k}: {distance[k]:.3f} m", (t[k], distance[k]), xytext=(6, 15),
                        textcoords="offset points", fontsize=8.5, color=COLORS[phase[k]])
    ranges.set_ylim(1.65, 10.25)
    ranges.set_ylabel("Geometric tag–B distance (m)")
    ranges.set_title("(d) Three-dimensional distance from coordinates", pad=10)
    ranges.text(0.035, 0.95, r"$d=\sqrt{(x-10)^2+y^2+(0.45-2.65)^2}$",
                transform=ranges.transAxes, fontsize=10, va="top", color="#4C5964")

    fig.text(0.07, 0.102,
             "Gray time regions: t ≥ 30 s, 767 poses. Orange interval: in-place turn, 88.2–95.2 s. Circles: selected canary poses.",
             fontsize=9.3, color="#35444F")
    fig.text(0.07, 0.069,
             "Input geometry only. Canary selection was frozen before RF outcomes; no RF channels or filter results are used here.",
             fontsize=9.3, color="#35444F")
    fig.text(0.07, 0.037,
             "Source: results/DRIVE_SIM_20261007/S1/timeline_y0.35_Tnone.csv  |  SHA-256: 53e76f41cb95…7225c4",
             fontsize=8.7, color="#66737D")
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(paths[0], dpi=220, metadata={"Title": "R1 original geometry / Anchor B", "Software": "Matplotlib"})
    fig.savefig(paths[1], metadata={"Title": "R1 original geometry / Anchor B",
                                    "Author": "DLP-R1B-CH4-001 computational input audit",
                                    "CreationDate": None, "ModDate": None})
    plt.close(fig)

    phase_records = {}
    for name in ("drive_out", "turn", "drive_back"):
        ix = np.flatnonzero(phase == name)
        nearest = int(ix[np.argmin(distance[ix])])
        phase_records[name] = {"n": len(ix), "pose_id_first_last": [int(ix[0]), int(ix[-1])],
                               "time_first_last_s": [float(t[ix[0]]), float(t[ix[-1]])],
                               "nearest_pose_id": nearest, "minimum_distance_m": float(distance[nearest])}
    provenance = {
        "schema": "DLP_R1B_IMMUTABLE_INPUT_GEOMETRY_FIGURE_V1",
        "scope": "Presentation of original immutable inputs only; no RF, SourceFFD or EKF outputs consumed or executed.",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": [file_record(csv_path), file_record(CONTRACT)],
        "code": file_record(Path(__file__).resolve()),
        "command": [sys.executable, *sys.argv],
        "versions": {"python": sys.version.split()[0], "numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "geometry": contract["geometry"],
        "actual_csv_values": {
            "n": len(rows), "n_t_ge_30": int(np.sum(t >= 30.0)),
            "time_min_max_s": [float(t.min()), float(t.max())],
            "dt_min_max_s": [float(np.diff(t).min()), float(np.diff(t).max())],
            "x_min_max_m": [float(x.min()), float(x.max())],
            "y_min_max_m": [float(y.min()), float(y.max())],
            "yaw_min_max_deg": [float(yaw.min()), float(yaw.max())],
            "distance_min_max_m": [float(distance.min()), float(distance.max())],
            "phases": phase_records,
        },
        "canaries": [{"pose_id": int(k), "t_s": float(t[k]), "phase": str(phase[k]),
                       "xyz_m": xyz[k].tolist(), "yaw_body_deg": float(yaw[k]),
                       "geometric_distance_m": float(distance[k])} for k in ids],
        "definitions": {
            "distance_m": "Euclidean norm([x,y,tag_z] - anchor_xyz); no measurement offset and no RF observation.",
            "phase": "Original CSV phase field; no inferred or relabeled phases.",
            "yaw": "Original yaw_body_deg values, without wrapping or modifying them.",
            "xy": "Original CSV x/y values; no lateral shifting, averaging, resampling or smoothing.",
            "axis_scale": "Plan view intentionally uses unequal x/y axis scales, explicitly labeled.",
            "coincident_canaries": "IDs 440,458,476 have identical XY; grouped in plan view and separately labeled in yaw/time.",
            "selection": contract["canary"]["selection_basis"],
        },
        "outputs": [file_record(path) for path in paths],
        "scientific_release": False,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"outputs": [str(p) for p in [*paths, provenance_path]],
                      "y_min_max_m": provenance["actual_csv_values"]["y_min_max_m"],
                      "source_csv_sha256": digest(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
