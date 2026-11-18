"""Render the corridor anchor/robot setup as an interactive 3D page and a static PNG.

No RF calculation is performed. Outputs go to --out-dir (default
results/CORRIDOR_SETUP_20261006): corridor_setup_3d.html, corridor_setup_3d.png,
CORRIDOR_SETUP.json (config snapshot, checks, link table, provenance).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import plotly.graph_objects as go  # noqa: E402
from plotly.offline import get_plotlyjs  # noqa: E402

from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, PORT_LOCAL_E, CorridorSetup, rot_z  # noqa: E402

C_ANCHOR, C_ROBOT = "#2f6fdd", "#e8741c"
C_P45, C_M45 = "#a23fd0", "#0e9e8e"
C_SHELL, C_EDGE, C_LOS = "#7f93ab", "#8b97a6", "#d6a100"
BOX_TRIS = np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1],
                     [1, 5, 6], [1, 6, 2], [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]])


def box_mesh(center, size, rotation, color, opacity, name, hover=None):
    sx, sy, sz = (np.asarray(size) / 2.0)
    local = np.array([[-sx, -sy, -sz], [sx, -sy, -sz], [sx, sy, -sz], [-sx, sy, -sz],
                      [-sx, -sy, sz], [sx, -sy, sz], [sx, sy, sz], [-sx, sy, sz]])
    v = np.asarray(center) + local @ np.asarray(rotation).T
    return go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=BOX_TRIS[:, 0], j=BOX_TRIS[:, 1], k=BOX_TRIS[:, 2],
                     color=color, opacity=opacity, flatshading=True, name=name, hoverinfo="name" if hover is None else "text",
                     text=hover, showlegend=False)


def quad_mesh(corners, color, opacity, name):
    q = np.asarray(corners)
    return go.Mesh3d(x=q[:, 0], y=q[:, 1], z=q[:, 2], i=[0, 0], j=[1, 2], k=[2, 3], color=color, opacity=opacity,
                     name=name, hoverinfo="name", showlegend=False)


def line(points, color, width=4, dash="solid", name="", text=None):
    p = np.asarray(points)
    return go.Scatter3d(x=p[:, 0], y=p[:, 1], z=p[:, 2], mode="lines", line=dict(color=color, width=width, dash=dash),
                        name=name, hoverinfo="name" if text is None else "text", text=text, showlegend=False)


def arrow(origin, direction, length, color, name, width=6, cone=0.18):
    o, d = np.asarray(origin, float), np.asarray(direction, float)
    tip = o + d * length
    return [line([o, tip - d * cone * 0.5], color, width, name=name),
            go.Cone(x=[tip[0] - d[0] * cone], y=[tip[1] - d[1] * cone], z=[tip[2] - d[2] * cone], u=[d[0]], v=[d[1]], w=[d[2]],
                    sizemode="absolute", sizeref=cone, anchor="tip", showscale=False, colorscale=[[0, color], [1, color]],
                    name=name, hoverinfo="name", showlegend=False)]


def label(pos, text, color, size=12):
    return go.Scatter3d(x=[pos[0]], y=[pos[1]], z=[pos[2]], mode="text", text=[text], textfont=dict(color=color, size=size),
                        textposition="middle right", hoverinfo="skip", showlegend=False)


def antenna_axes(center, rotation, half_len, tag):
    out = []
    for port, color in zip(("LP_plus45", "LP_minus45"), (C_P45, C_M45)):
        e = np.asarray(rotation) @ PORT_LOCAL_E[port]
        out.append(line([center - e * half_len, center + e * half_len], color, 7, name=f"{tag} {port} E-axis (nominal)"))
    return out


def build_traces(s: CorridorSetup):
    t = []
    alpha = dict(floor=0.30, ceiling=0.10, wall_y_neg=0.10, wall_y_pos=0.10, end_x_min=0.06, end_x_max=0.06)
    for name, q in s.surfaces().items():
        t.append(quad_mesh(q, C_SHELL, alpha[name], name))
    L, h, H = s.length_m, s.y_half, s.height_m
    for z in (0, H):
        t.append(line([(0, -h, z), (L, -h, z), (L, h, z), (0, h, z), (0, -h, z)], C_EDGE, 2, name="corridor edge"))
    for x in (0, L):
        for y in (-h, h):
            t.append(line([(x, y, 0), (x, y, H)], C_EDGE, 2, name="corridor edge"))

    # Robot allowed xy region on the floor, and the fixed antenna-height plane outline.
    x0, x1 = s.robot_x_range_m
    yl = s.robot_y_limit_m
    zone = [(x0, -yl, 0.004), (x1, -yl, 0.004), (x1, yl, 0.004), (x0, yl, 0.004)]
    t.append(quad_mesh(zone, C_ROBOT, 0.16, "robot xy allowed region"))
    z = s.robot_antenna_z_m
    t.append(line([(x0, -yl, z), (x1, -yl, z), (x1, yl, z), (x0, yl, z), (x0, -yl, z)], C_ROBOT, 2, "dot",
                  "robot antenna plane z=%.2f m (fixed)" % z))

    # Anchor.
    a = s.anchor_position
    t.append(box_mesh(a + [0, 0, 0.0], (0.16, 0.16, 0.035), np.eye(3), C_ANCHOR, 1.0, "anchor antenna (ceiling)"))
    t += antenna_axes(a, ANCHOR_ROTATION, 0.35, "anchor")
    t += arrow(a, [0, 0, -1], 0.9, C_ANCHOR, "anchor boresight (-z, toward floor)")
    foot = np.array([a[0], a[1], 0.006])
    t.append(line([a + [0, 0, -0.9], foot], C_ANCHOR, 2, "dot", "anchor boresight to floor"))
    t.append(go.Scatter3d(x=[foot[0]], y=[foot[1]], z=[foot[2]], mode="markers", marker=dict(size=4, color=C_ANCHOR),
                          name="boresight footprint", hoverinfo="name", showlegend=False))
    t.append(label(a + [0.15, 0, 0.0], "앵커 (천장, 보어사이트 ↓)", C_ANCHOR))

    # Robots: ghosts at the other example positions, the main robot highlighted with its yaw sweep.
    bl, bw, bh = s.robot_body_lwh_m
    for idx, (x, y) in enumerate(s.example_xy_m):
        main = idx == s.main_index
        yaw = s.yaw_display_deg if main else 0.0
        r = s.robot_rotation(yaw)
        tag = "robot (main)" if main else f"robot (example {idx})"
        op = 0.85 if main else 0.30
        t.append(box_mesh(np.array([x, y, bh / 2]), (bl, bw, bh), r, C_ROBOT, op, f"{tag} body"))
        ap = s.robot_position(x, y)
        t.append(line([ap - [0, 0, z - bh], ap], C_ROBOT, 3, name=f"{tag} antenna mount"))
        t.append(box_mesh(ap, (0.14, 0.14, 0.02), r, C_ROBOT, 1.0 if main else 0.5, f"{tag} antenna"))
        if main:
            t += antenna_axes(ap, r, 0.30, "robot")
            t += arrow(ap, [0, 0, 1], 0.7, C_ROBOT, "robot boresight (+z, up)")
            t.append(line([a, ap], C_LOS, 3, "dash", "line of sight"))
            g = s.link_geometry(x, y, yaw)
            mid = (a + ap) / 2
            t.append(label(mid + [0.1, 0, 0], f"R = {g['range_m']:.2f} m", C_LOS))
            # Yaw sweep ring and heading ticks at antenna height.
            ring = np.array([[x + 0.55 * math.cos(math.radians(k)), y + 0.55 * math.sin(math.radians(k)), z]
                             for k in range(0, 361, 5)])
            t.append(line(ring, C_ROBOT, 2, name="yaw sweep ring"))
            for yw in s.yaw_sweep_deg:
                d = rot_z(yw) @ np.array([1.0, 0, 0])
                t.append(line([ap + d * 0.55, ap + d * 0.72], C_ROBOT, 4, name=f"yaw {yw:.0f}°"))
            t.append(label(ap + [0.15, 0.0, 0.32], "로봇 (yaw sweep, 안테나 z 고정)", C_ROBOT))
            hd = rot_z(yaw) @ np.array([1.0, 0, 0])
            t += arrow(ap + [0, 0, -0.01], hd, 0.55, C_ROBOT, f"heading yaw={yaw:.0f}°", width=3, cone=0.1)

    # World triad.
    o = np.array([0.0, -h, 0.0])
    for d, nm in (([1, 0, 0], "x"), ([0, 1, 0], "y"), ([0, 0, 1], "z")):
        t.append(line([o, o + np.array(d) * 0.8], C_EDGE, 5, name=f"world {nm}"))
        t.append(label(o + np.array(d) * 0.9, nm, C_EDGE, 12))
    return t


CAMERAS = {
    "사선": dict(eye=dict(x=-1.15, y=-2.9, z=1.55), center=dict(x=0.0, y=0.0, z=-0.15)),
    "위에서": dict(eye=dict(x=0.001, y=-0.001, z=2.6), up=dict(x=0, y=1, z=0), center=dict(x=0, y=0, z=0)),
    "옆에서": dict(eye=dict(x=0.0, y=-3.4, z=0.25), center=dict(x=0, y=0, z=0)),
    "복도 방향": dict(eye=dict(x=-2.4, y=0.0, z=0.3), center=dict(x=0, y=0, z=0)),
}


def layout(s: CorridorSetup, closeup: bool):
    L, h, H = s.length_m, s.y_half, s.height_m
    mx = s.example_xy_m[s.main_index][0]
    xr = [s.anchor_x_m - 1.3, mx + 1.6] if closeup else [-0.3, L + 0.3]
    scene = dict(
        xaxis=dict(title="x (m)", range=xr, backgroundcolor="rgba(0,0,0,0)", showbackground=False),
        yaxis=dict(title="y (m)", range=[-h - 0.1, h + 0.1], showbackground=False),
        zaxis=dict(title="z (m)", range=[-0.05, H + 0.15], showbackground=False),
    )
    if closeup:
        span = xr[1] - xr[0]
        scene["aspectmode"] = "manual"
        scene["aspectratio"] = dict(x=span / (H + 0.2), y=(2 * h + 0.2) / (H + 0.2), z=1)
        scene["camera"] = dict(eye=dict(x=0.9, y=-1.55, z=0.75), center=dict(x=0, y=0, z=-0.1))
    else:
        scene["aspectmode"] = "manual"
        scene["aspectratio"] = dict(x=3.2, y=1.0, z=0.9)  # x compressed for display only
        scene["camera"] = CAMERAS["사선"]
    return dict(scene=scene, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
                height=560 if not closeup else 480, uirevision="keep")


def static_png(s: CorridorSetup, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(12, 5.2), dpi=130)
    ax = fig.add_subplot(111, projection="3d")
    for nm, q in s.surfaces().items():
        ax.add_collection3d(Poly3DCollection([q], facecolor=C_SHELL, alpha=0.30 if nm == "floor" else 0.07, edgecolor=C_EDGE, lw=0.5))
    a = s.anchor_position
    ax.scatter(*a, c=C_ANCHOR, s=60, marker="s")
    ax.quiver(*a, 0, 0, -0.9, color=C_ANCHOR, lw=2, arrow_length_ratio=0.15)
    for port, c in zip(("LP_plus45", "LP_minus45"), (C_P45, C_M45)):
        e = ANCHOR_ROTATION @ PORT_LOCAL_E[port] * 0.35
        ax.plot(*zip(a - e, a + e), c=c, lw=2.5)
    bl, bw, bh = s.robot_body_lwh_m
    for idx, (x, y) in enumerate(s.example_xy_m):
        main = idx == s.main_index
        yaw = s.yaw_display_deg if main else 0.0
        ap = s.robot_position(x, y)
        ax.scatter(x, y, bh / 2, c=C_ROBOT, s=240 if main else 90, marker="s", alpha=0.85 if main else 0.35)
        ax.scatter(*ap, c=C_ROBOT, s=25)
        if main:
            ax.plot(*zip(a, ap), c=C_LOS, ls="--", lw=1.5)
            ax.quiver(*ap, 0, 0, 0.7, color=C_ROBOT, lw=2, arrow_length_ratio=0.15)
            for port, c in zip(("LP_plus45", "LP_minus45"), (C_P45, C_M45)):
                e = rot_z(yaw) @ PORT_LOCAL_E[port] * 0.3
                ax.plot(*zip(ap - e, ap + e), c=c, lw=2.5)
    x0, x1 = s.robot_x_range_m
    yl = s.robot_y_limit_m
    ax.add_collection3d(Poly3DCollection([[(x0, -yl, 0.01), (x1, -yl, 0.01), (x1, yl, 0.01), (x0, yl, 0.01)]],
                                         facecolor=C_ROBOT, alpha=0.15))
    ax.set(xlim=(0, s.length_m), ylim=(-s.y_half, s.y_half), zlim=(0, s.height_m), xlabel="x (m)", ylabel="y (m)", zlabel="z (m)")
    ax.set_box_aspect((s.length_m / 3, s.width_m, s.height_m))
    ax.view_init(elev=24, azim=-62)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def link_table(s: CorridorSetup):
    rows = []
    for idx, (x, y) in enumerate(s.example_xy_m):
        yaw = s.yaw_display_deg if idx == s.main_index else 0.0
        g = s.link_geometry(x, y, yaw)
        rows.append(dict(example=idx, main=idx == s.main_index, robot_xy_m=[x, y], robot_yaw_deg=yaw, **{k: round(v, 3) for k, v in g.items()}))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=ROOT / "results" / "CORRIDOR_SETUP_20261006")
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()
    s = CorridorSetup()
    checks = s.validate()
    if not all(c["passed"] for c in checks):
        raise SystemExit("validation failed: " + json.dumps([c for c in checks if not c["passed"]]))
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    traces = build_traces(s)
    figs = {k: go.Figure(data=traces, layout=layout(s, k == "closeup")) for k in ("overview", "closeup")}
    template = (ROOT / "scripts" / "corridor_page_template.html").read_text(encoding="utf8")
    table = link_table(s)
    # plotly.js holds a literal U+FFFD in a regex; the escape is equivalent and keeps the page free of it.
    page = (template.replace("/*__PLOTLY__*/", get_plotlyjs().replace("\ufffd", "\\uFFFD"))
            .replace("__FIG_OVERVIEW__", figs["overview"].to_json())
            .replace("__FIG_CLOSEUP__", figs["closeup"].to_json())
            .replace("__CAMERAS__", json.dumps(CAMERAS, ensure_ascii=False))
            .replace("__DATA__", json.dumps(dict(
                setup=json.loads(json.dumps(s.snapshot()["config"], default=list)), derived=dict(
                    anchor=s.anchor_position.round(3).tolist(), robot_y_limit_m=round(s.robot_y_limit_m, 3)),
                links=table, checks=checks), ensure_ascii=False)))
    html_path = out / "corridor_setup_3d.html"
    html_path.write_text(page, encoding="utf8")
    png_path = out / "corridor_setup_3d.png"
    if not args.no_png:
        static_png(s, png_path)
    snap = s.snapshot()
    manifest = dict(
        status="SETUP_VISUALISATION_ONLY_NO_RF_RUN", created_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        command=" ".join(sys.argv), config=snap["config"], config_sha256=snap["config_sha256"], checks=checks, links=table,
        conventions=dict(coordinate_frame="Z-up right-handed, metres, floor top z=0", anchor_rotation=ANCHOR_ROTATION.tolist(),
                         robot_rotation="Rz(yaw), boresight +z", port_pair=list(s.port_pair), arm=s.arm,
                         port_E_nominal_note="nominal LP_plus45=(x+y)/sqrt2, LP_minus45=(x-y)/sqrt2 in antenna frame; not read back from FFD banks"),
        outputs={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (html_path, png_path) if p.exists()},
    )
    (out / "CORRIDOR_SETUP.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf8")
    print(json.dumps(dict(out=str(out), checks_passed=sum(c["passed"] for c in checks), checks_total=len(checks),
                          html_mb=round(html_path.stat().st_size / 1e6, 2)), indent=1))


if __name__ == "__main__":
    main()
