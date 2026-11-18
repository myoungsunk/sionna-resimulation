"""Plot frozen Office RT coordinates without executing any ray tracing."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
SOURCE_ROOT = Path("D:/SLAM_bot/OFFICE_FIX_REAUDIT_20261008")
sys.path.insert(0, str(SOURCE_ROOT / "src"))
from qclean_uwb.scenarios.office import OfficeSetup  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_poses(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("t_s", "x_m", "y_m", "z_m", "yaw_body_deg", "yaw_antenna_deg"):
            row[key] = float(row[key])
        for key in ("pose_id", "rf_sample"):
            row[key] = int(row[key])
    return rows


def main() -> None:
    plan = json.loads((INPUTS / "RUN_PLAN.json").read_text(encoding="utf-8"))
    scene = json.loads((INPUTS / "SCENE_METADATA.json").read_text(encoding="utf-8"))
    setup = OfficeSetup(**scene["setup"]["config"])
    assert setup.snapshot()["config_sha256"] == scene["setup"]["config_sha256"] == plan["config_sha256"]
    model_file = SOURCE_ROOT / "src/qclean_uwb/scenarios/office.py"
    normalized_sha = hashlib.sha256(model_file.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert normalized_sha == "3c6e6918695a5a64718259255a79d8ce85f104fe64874b8e8bb50792fe905cd5"
    boxes = setup.boxes()
    assert Counter(box["group"] for box in boxes) == {"desks": 24, "partitions": 12}
    assert len(plan["positions"]) == 35
    assert len({(row["x"], row["y"]) for row in plan["positions"]}) == 35
    anchor = np.array(scene["anchor"], float)
    np.testing.assert_allclose(anchor, setup.anchor_position, atol=1e-12, rtol=0)

    routes = {}
    expected = {"O01": 192, "O02": 207, "O03": 412}
    for name in expected:
        route = read_poses(INPUTS / f"{name}_ROUTE_POSE.csv")
        radio = read_poses(INPUTS / f"{name}_RADIO_POSE.csv")
        assert len(radio) == expected[name]
        assert [row for row in route if row["rf_sample"] == 1] == radio
        assert all(0 <= row["x_m"] <= 10 and 0 <= row["y_m"] <= 12 for row in route)
        assert all(row["t_s"] <= after["t_s"] for row, after in zip(route, route[1:]))
        assert all(abs(row["z_m"] - 0.45) < 1e-12 for row in radio)
        routes[name] = (route, radio)

    plt.rcParams.update({
        "font.family": "Malgun Gothic", "font.size": 11,
        "axes.unicode_minus": False, "axes.titleweight": "bold",
        "figure.facecolor": "white", "axes.facecolor": "#FAFAFA",
        "savefig.facecolor": "white", "svg.fonttype": "none",
        "pdf.fonttype": 42,
    })
    colors = {"O01": "#2563EB", "O02": "#D97706", "O03": "#7C3AED"}
    desk_color, partition_color, anchor_color = "#D5D9DE", "#535D69", "#0F766E"

    def background(ax):
        for box in boxes:
            lo, hi = np.array(box["lo"]), np.array(box["hi"])
            ax.add_patch(Rectangle(lo[:2], *(hi - lo)[:2],
                                   facecolor=partition_color if box["group"] == "partitions" else desk_color,
                                   edgecolor=partition_color if box["group"] == "partitions" else "#B6BDC7",
                                   linewidth=0.45, zorder=2))
        ax.add_patch(Rectangle((0, 0), 10, 12, fill=False, edgecolor="#35404D", linewidth=1.6, zorder=3))
        ax.scatter(*anchor[:2], marker="*", s=235, color=anchor_color, edgecolor="white", linewidth=0.7, zorder=12)
        ax.annotate("앵커 O0", xy=anchor[:2], xytext=(10, 9), textcoords="offset points",
                    color=anchor_color, fontsize=10, fontweight="bold", zorder=14,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=1.5))
        ax.set(xlim=(-0.4, 10.4), ylim=(-0.4, 12.55), xlabel="x (m)", ylabel="y (m)")
        ax.set_xticks(np.arange(0, 11, 1))
        ax.set_yticks(np.arange(0, 13, 1))
        ax.grid(color="#E5E7EB", linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)
        ax.set_aspect("equal", adjustable="box")
        ax.tick_params(labelsize=9, length=2.5, color="#9AA2AD")
        for spine in ax.spines.values():
            spine.set_visible(False)

    def sweep_panel(ax):
        background(ax)
        for index, row in enumerate(plan["positions"], start=1):
            clear = row["los_clear"]
            ax.scatter(row["x"], row["y"], s=48, marker="o" if clear else "X",
                       color="#2563EB" if clear else "#C24136", edgecolor="white", linewidth=0.6, zorder=7)
            # Labels use the order in RUN_PLAN.json, not a reordered spatial grid.
            side = -1 if row["x"] > 9 else 1
            ax.annotate(f"S{index:02d}", (row["x"], row["y"]), xytext=(side * 7, 5),
                        textcoords="offset points", ha="left" if side > 0 else "right",
                        fontsize=8, color="#334155", zorder=9,
                        bbox=dict(facecolor="white", alpha=0.76, edgecolor="none", pad=0.5))
        ax.set_title("방향 sweep · 35위치 / 665 RF pose", fontsize=14, y=1.06, pad=0)
        ax.text(0.5, 1.015, "각 위치 yaw 0°–180°, 10° 간격 · 주파수 257 bin", transform=ax.transAxes,
                ha="center", va="bottom", fontsize=10, color="#566273")
        ax.legend(handles=[
            Line2D([], [], marker="o", linestyle="none", color="#2563EB", label="기하상 LoS 25위치"),
            Line2D([], [], marker="X", linestyle="none", color="#C24136", label="기하상 차폐 10위치"),
        ], loc="lower center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=False, fontsize=9)

    def route_panel(ax, name):
        background(ax)
        route, radio = routes[name]
        xy = np.array([[row["x_m"], row["y_m"]] for row in route])
        rf_xy = np.array([[row["x_m"], row["y_m"]] for row in radio])
        color = colors[name]
        ax.plot(*xy.T, color=color, linewidth=2, alpha=0.78, zorder=4)
        ax.scatter(*rf_xy.T, s=11, color=color, edgecolor="white", linewidth=0.18, zorder=5)
        # Show antenna heading at a small subset of the actual RF rows.
        pick = np.unique(np.linspace(0, len(radio) - 1, 13, dtype=int))
        theta = np.deg2rad([radio[i]["yaw_antenna_deg"] for i in pick])
        ax.quiver(rf_xy[pick, 0], rf_xy[pick, 1], 0.48 * np.cos(theta), 0.48 * np.sin(theta),
                  angles="xy", scale_units="xy", scale=1, width=0.0042,
                  headwidth=3.8, headlength=4.7, color=color, zorder=6)
        start, end = xy[0], xy[-1]
        closed = np.linalg.norm(start - end) < 1e-8
        ax.scatter(*start, marker="o", s=125, facecolor="white", edgecolor=color, linewidth=2.1, zorder=10)
        if closed:
            ax.scatter(*end, marker="s", s=22, color=color, zorder=11)
            ax.annotate("시작·끝", start, xytext=(10, -22), textcoords="offset points", fontsize=10,
                        color=color, zorder=14, bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=1))
        else:
            ax.scatter(*end, marker="s", s=75, color=color, edgecolor="white", linewidth=0.7, zorder=10)
            for label, point, offset in (("시작", start, (8, -20)), ("끝", end, (8, 8))):
                ax.annotate(label, point, xytext=offset, textcoords="offset points", fontsize=10,
                            color=color, zorder=14, bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=1))
        length = np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()
        unique_rf = len({(round(row["x_m"], 9), round(row["y_m"], 9)) for row in radio})
        ax.set_title(f"{name} · {len(radio):,} RF pose", fontsize=14, y=1.06, pad=0)
        ax.text(0.5, 1.015, f"주행 길이 {length:.1f} m · 중복 제외 RF 위치 {unique_rf}곳",
                transform=ax.transAxes, ha="center", va="bottom", fontsize=10, color="#566273")
        ax.legend(handles=[
            Line2D([], [], color=color, linewidth=2, label="주행 경로"),
            Line2D([], [], marker="o", color=color, linestyle="none", markersize=4, label="실제 RF 샘플"),
            Line2D([], [], marker=r"$\rightarrow$", color=color, linestyle="none", markersize=12, label="안테나 heading 일부"),
        ], loc="lower center", bbox_to_anchor=(0.5, -0.13), ncol=3, frameon=False, fontsize=9,
                  columnspacing=1.1, handletextpad=0.4)

    fig, axes = plt.subplots(2, 2, figsize=(14.2, 16.8))
    fig.subplots_adjust(left=0.065, right=0.98, bottom=0.125, top=0.89, hspace=0.40, wspace=0.15)
    sweep_panel(axes[0, 0])
    for ax, name in zip((axes[0, 1], axes[1, 0], axes[1, 1]), routes):
        route_panel(ax, name)
    fig.suptitle("오피스 RT 데이터 추출 위치와 주행 경로", fontsize=22, fontweight="bold", y=0.965)
    fig.text(0.5, 0.936, "10 × 12 m 평면 · 앵커 O0=(5, 2.2, 2.65) m · 수신 안테나 z=0.45 m", ha="center", fontsize=12, color="#475569")
    fig.legend(handles=[
        Rectangle((0, 0), 1, 1, facecolor=desk_color, label="책상 상판 24개"),
        Line2D([], [], color=partition_color, linewidth=3, label="칸막이 12장"),
        Line2D([], [], marker="*", color=anchor_color, linestyle="none", markersize=13, label="천장 앵커 O0"),
    ], loc="lower center", bbox_to_anchor=(0.5, 0.033), ncol=3, frameon=False, fontsize=11)
    fig.text(0.5, 0.017, "선은 주행 순서, 점은 실제 H 계산 pose의 위치입니다. 같은 위치의 여러 heading·재방문 pose는 겹쳐 보입니다.",
             ha="center", fontsize=10, color="#566273")
    for ext in ("png", "pdf", "svg"):
        fig.savefig(ROOT / f"office-rt-map.{ext}", dpi=170)
    fig.savefig(ROOT / "office-rt-map-preview.png", dpi=95)
    plt.close(fig)

    # Full-size individual panels keep coordinate labels readable on a narrow screen.
    for panel in ("sweep", *routes):
        fig, ax = plt.subplots(figsize=(8.4, 10.2))
        fig.subplots_adjust(left=0.095, right=0.97, bottom=0.15, top=0.90)
        sweep_panel(ax) if panel == "sweep" else route_panel(ax, panel)
        fig.savefig(ROOT / f"office-{panel.lower()}-map.png", dpi=170)
        plt.close(fig)

    # S-labels are a plotting aid; write their exact source coordinates for inspection.
    with (ROOT / "SWEEP_STATION_LABELS.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["map_label", "x_m", "y_m", "geometric_los_clear"])
        writer.writeheader()
        for i, row in enumerate(plan["positions"], 1):
            writer.writerow(dict(map_label=f"S{i:02d}", x_m=row["x"], y_m=row["y"], geometric_los_clear=row["los_clear"]))

    summary = {
        "purpose": "Plot existing RT sampling coordinates only; no RT or estimation executed",
        "office_source_commit": "819fa93b152ca3cdf66297af09ff073880bd9d9b",
        "office_source_lf_sha256": normalized_sha,
        "setup_config_sha256": plan["config_sha256"],
        "remote_sweep_source": "/home/KMS/OFFICE_SNOWBALL_20261008_819fa93/source/results/OFFICE_RUN_PLAN_20261008/RUN_PLAN.json",
        "remote_route_sources": "/home/KMS/OFFICE_M0_RF_20261026_01a17631/POSES/O0[123]_{RADIO,ROUTE}_POSE.csv",
        "input_sha256": {p.name: sha256(p) for p in sorted(INPUTS.iterdir()) if p.is_file()},
        "sweep_positions": len(plan["positions"]), "sweep_rf_poses": len(plan["positions"]) * len(plan["yaw_deg"]),
        "routes": {},
        "checks": {"geometry_config_equal": True, "radio_equals_flagged_route_subset": True,
                   "radio_rows_match_H_counts": True, "coords_within_room": True, "time_monotonic": True},
    }
    for name, (route, radio) in routes.items():
        xy = np.array([[row["x_m"], row["y_m"]] for row in route])
        summary["routes"][name] = dict(
            route_rows=len(route), radio_rows=len(radio),
            unique_radio_xy=len({(round(row["x_m"], 9), round(row["y_m"], 9)) for row in radio}),
            start_xy=xy[0].tolist(), end_xy=xy[-1].tolist(),
            length_m=float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()),
            radio_phase_counts=dict(Counter(row["phase"] for row in radio)))
    summary["output_sha256"] = {p.name: sha256(p) for p in sorted(ROOT.glob("*.png"))}
    (ROOT / "MAP_PROVENANCE.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "PASS", "sweep_positions": summary["sweep_positions"], "routes": summary["routes"],
                      "checks": summary["checks"], "image": str(ROOT / "office-rt-map.png")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
