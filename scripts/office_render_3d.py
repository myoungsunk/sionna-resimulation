"""Render the office setup (E-shaped aisles, partitions, desks, one ceiling anchor) as an interactive 3D page with a plan view.

No RF calculation is performed.   python scripts/office_render_3d.py [--out-dir results/OFFICE_SETUP_20261007]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import plotly.graph_objects as go  # noqa: E402
from plotly.offline import get_plotlyjs  # noqa: E402

from qclean_uwb.scenarios.office import MATERIALS, OfficeSetup, box_quads  # noqa: E402

C_LOS, C_NLOS, C_PART, C_DESK, C_ANCHOR = "#2a78d6", "#eb6834", "#7f8da0", "#b8935a", "#0b0b0b"
TRIS = np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2], [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]])


def box_trace(lo, hi, color, opacity, name):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    return go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=TRIS[:, 0], j=TRIS[:, 1], k=TRIS[:, 2], color=color, opacity=opacity, flatshading=True,
                     name=name, hoverinfo="name", showlegend=False)


def merged_boxes(boxes, color, opacity, name):
    xs, ys, zs, ii, jj, kk = [], [], [], [], [], []
    for n, b in enumerate(boxes):
        x0, y0, z0 = b["lo"]
        x1, y1, z1 = b["hi"]
        v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
        xs += v[:, 0].tolist(); ys += v[:, 1].tolist(); zs += v[:, 2].tolist()
        ii += (TRIS[:, 0] + 8 * n).tolist(); jj += (TRIS[:, 1] + 8 * n).tolist(); kk += (TRIS[:, 2] + 8 * n).tolist()
    return go.Mesh3d(x=xs, y=ys, z=zs, i=ii, j=jj, k=kk, color=color, opacity=opacity, flatshading=True, name=name, hoverinfo="name", showlegend=False)


def build(s: OfficeSetup):
    L, W, H = s.length_m, s.width_m, s.height_m
    tr, idx = [], {}
    q = lambda c: go.Mesh3d(x=c[:, 0], y=c[:, 1], z=c[:, 2], i=[0, 0], j=[1, 2], k=[2, 3], color="#8b97a6", opacity=0.0, hoverinfo="skip", showlegend=False)
    for name, (c, op, col) in {"floor": (np.array([[0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0]]), 0.30, "#9aa7b5"),
                               "wall_y0": (np.array([[0, 0, 0], [L, 0, 0], [L, 0, H], [0, 0, H]]), 0.07, "#8b97a6"),
                               "wall_y1": (np.array([[0, W, 0], [L, W, 0], [L, W, H], [0, W, H]]), 0.07, "#8b97a6"),
                               "wall_x0": (np.array([[0, 0, 0], [0, W, 0], [0, W, H], [0, 0, H]]), 0.07, "#8b97a6"),
                               "wall_x1": (np.array([[L, 0, 0], [L, W, 0], [L, W, H], [L, 0, H]]), 0.07, "#8b97a6")}.items():
        tr.append(go.Mesh3d(x=c[:, 0], y=c[:, 1], z=c[:, 2], i=[0, 0], j=[1, 2], k=[2, 3], color=col, opacity=op, name=name, hoverinfo="name", showlegend=False))
    idx["shell"] = list(range(len(tr)))
    # aisles (E) tinted on the floor
    a = s.aisle_m
    for (x0, y0, x1, y1) in [(0, 0, a, W)] + [(0, y, L, y + a) for y in s.arm_y0_m]:
        tr.append(go.Mesh3d(x=[x0, x1, x1, x0], y=[y0, y0, y1, y1], z=[0.01] * 4, i=[0, 0], j=[1, 2], k=[2, 3], color="#d6c46a", opacity=0.28, hoverinfo="skip", showlegend=False))
    boxes = s.boxes()
    tr.append(merged_boxes([b for b in boxes if b["group"] == "partitions"], C_PART, 0.85, "칸막이"))
    tr.append(merged_boxes([b for b in boxes if b["group"] == "desks"], C_DESK, 0.95, "책상"))
    A = s.anchor_position
    tr.append(go.Scatter3d(x=[A[0], A[0]], y=[A[1], A[1]], z=[A[2], 0], mode="lines", line=dict(color=C_ANCHOR, width=3, dash="dot"), hoverinfo="skip", showlegend=False))
    tr.append(go.Scatter3d(x=[A[0]], y=[A[1]], z=[A[2]], mode="markers", marker=dict(size=8, color=C_ANCHOR, symbol="square"),
                           hovertext=["앵커 %.2f, %.2f, %.2f" % tuple(A)], hoverinfo="text", showlegend=False))
    for (x0, y0), (x1, y1) in s.path_segments():
        tr.append(go.Scatter3d(x=[x0, x1], y=[y0, y1], z=[0.03, 0.03], mode="lines", line=dict(color="#a07d00", width=3, dash="dash"), hoverinfo="skip", showlegend=False))
    pts = s.sample_points()
    st = [s.los_status(x, y) for x, y in pts]
    for flag, col, sym, nm in ((True, C_LOS, "circle", "LoS 열림"), (False, C_NLOS, "diamond", "LoS 막힘")):
        sel = [i for i in range(len(pts)) if st[i]["clear"] is flag]
        tr.append(go.Scatter3d(x=[pts[i][0] for i in sel], y=[pts[i][1] for i in sel], z=[s.robot_antenna_z_m] * len(sel), mode="markers",
                               marker=dict(size=5, color=col, symbol=sym, line=dict(color="#fff", width=1)), name=nm,
                               hovertext=[f"태그 ({pts[i][0]:.1f}, {pts[i][1]:.1f}) · {nm}" + ("" if flag else " · " + ", ".join(st[i]["blockers"][:2])) for i in sel], hoverinfo="text", showlegend=False))
        idx["pts_" + ("los" if flag else "nlos")] = [len(tr) - 1]
    for flag, col in ((True, C_LOS), (False, C_NLOS)):
        xs, ys, zs = [], [], []
        for i, p in enumerate(pts):
            if st[i]["clear"] is flag:
                xs += [p[0], A[0], None]; ys += [p[1], A[1], None]; zs += [s.robot_antenna_z_m, A[2], None]
        tr.append(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=col, width=1.5), opacity=0.5, hoverinfo="skip", showlegend=False, visible=False))
        idx["lines_" + ("los" if flag else "nlos")] = [len(tr) - 1]
    return tr, idx, pts, st


def layout(s):
    ax = lambda t, r: dict(title=t, range=r, backgroundcolor="rgba(0,0,0,0)", showbackground=False, zeroline=False)
    return go.Layout(margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                     scene=dict(xaxis=ax("x (m)", [0, s.length_m]), yaxis=ax("y (m)", [0, s.width_m]), zaxis=ax("z (m)", [0, s.height_m]),
                                aspectmode="manual", aspectratio=dict(x=s.length_m / 6, y=s.width_m / 6, z=s.height_m / 6), camera=CAMS["전체"]), height=560)


CAMS = {"전체": dict(eye=dict(x=-0.9, y=-1.9, z=1.25), up=dict(x=0, y=0, z=1)), "위에서": dict(eye=dict(x=0.0, y=0.001, z=2.8), up=dict(x=0, y=1, z=0)),
        "통로 높이": dict(eye=dict(x=-1.5, y=-0.35, z=0.28), up=dict(x=0, y=0, z=1))}


def plan_svg(s, pts, st):
    sc, m = 40.0, 28
    W, H = int(s.length_m * sc + 2 * m), int(s.width_m * sc + 2 * m + 16)
    px = lambda x: m + x * sc
    py = lambda y: m + (s.width_m - y) * sc
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="사무실 평면도" xmlns="http://www.w3.org/2000/svg">',
         f'<rect class="env" x="{px(0)}" y="{py(s.width_m)}" width="{s.length_m*sc}" height="{s.width_m*sc}"/>']
    a = s.aisle_m
    for (x0, y0, x1, y1) in [(0, 0, a, s.width_m)] + [(0, y, s.length_m, y + a) for y in s.arm_y0_m]:
        g.append(f'<rect class="aisle" x="{px(x0)}" y="{py(y1)}" width="{(x1-x0)*sc}" height="{(y1-y0)*sc}"/>')
    for b in s.boxes():
        cls = "desk" if b["group"] == "desks" else "part"
        g.append(f'<rect class="{cls}" x="{px(b["lo"][0])}" y="{py(b["hi"][1])}" width="{max((b["hi"][0]-b["lo"][0])*sc, 2.2)}" height="{max((b["hi"][1]-b["lo"][1])*sc, 2.2)}"><title>{b["name"]}</title></rect>')
    for x in range(0, int(s.length_m) + 1, 2):
        g.append(f'<text class="tk" x="{px(x)}" y="{py(0)+14}" text-anchor="middle">{x}</text>')
    for y in range(0, int(s.width_m) + 1, 2):
        g.append(f'<text class="tk" x="{px(0)-6}" y="{py(y)+4}" text-anchor="end">{y}</text>')
    for i, (x, y) in enumerate(pts):
        ok = st[i]["clear"]
        tip = f'태그 ({x:.1f}, {y:.1f}) · ' + ("LoS 열림" if ok else "LoS 막힘: " + ", ".join(st[i]["blockers"][:3]))
        m_ = f'<circle class="pl" cx="{px(x)}" cy="{py(y)}" r="5"/>' if ok else f'<path class="pn" d="M{px(x)} {py(y)-6.5} L{px(x)+6.5} {py(y)} L{px(x)} {py(y)+6.5} L{px(x)-6.5} {py(y)} Z"/>'
        g.append(f'<g>{m_}<title>{tip}</title></g>')
    g.append(f'<rect class="anc" x="{px(s.anchor_x_m)-6}" y="{py(s.anchor_y_m)-6}" width="12" height="12"><title>앵커 (천장) {s.anchor_x_m:g}, {s.anchor_y_m:g}</title></rect>')
    g.append("</svg>")
    return "\n".join(g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=ROOT / "results" / "OFFICE_SETUP_20261007")
    args = ap.parse_args()
    s = OfficeSetup()
    checks = s.validate()
    if not all(c["passed"] for c in checks):
        raise SystemExit("validation failed: " + json.dumps([c for c in checks if not c["passed"]]))
    tr, idx, pts, st = build(s)
    fig = go.Figure(data=tr, layout=layout(s))
    n_clear = sum(x["clear"] for x in st)
    boxes = s.boxes()
    data = dict(setup=s.snapshot()["config"], counts=dict(desks=sum(b["group"] == "desks" for b in boxes), partitions=sum(b["group"] == "partitions" for b in boxes),
                                                          points=len(pts), los=n_clear, nlos=len(pts) - n_clear, objects=len(s.objects())),
                materials={k: dict(itu=v[0], t=v[1]) for k, v in MATERIALS.items()}, checks=checks, idx=idx, cams=CAMS,
                notches=s.notches(), anchor=s.anchor_position.round(3).tolist(),
                layout=dict(rows=s.rows_per_notch, per_row=s.n_cubicles, open_end_m=round(s.length_m - (s.cubicle_x0_m + s.cubicle_pitch_m * s.n_cubicles), 2), row_depth_m=round(s.row_depth_m(0), 2)))
    page = ((ROOT / "scripts" / "office_page_template.html").read_text(encoding="utf8")
            .replace("/*__PLOTLY__*/", get_plotlyjs().replace("�", "\\uFFFD")).replace("__FIG__", fig.to_json())
            .replace("__PLAN__", plan_svg(s, pts, st)).replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "office_setup_3d.html"
    out.write_text(page, encoding="utf8")
    snap = s.snapshot()
    pl = [dict(x=round(float(x), 3), y=round(float(y), 3), los_clear=st[i]["clear"], blockers=st[i]["blockers"]) for i, (x, y) in enumerate(pts)]
    (args.out_dir / "OFFICE_SETUP.json").write_text(json.dumps(dict(
        status="SETUP_VISUALISATION_ONLY_NO_RF_RUN", created_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), command=" ".join(sys.argv),
        config=snap["config"], config_sha256=snap["config_sha256"], checks=checks, materials=MATERIALS, material_note="partitions and desks are ASSUMED materials",
        sample_points=pl, outputs={out.name: hashlib.sha256(out.read_bytes()).hexdigest()}), indent=1, ensure_ascii=False), encoding="utf8")
    print(json.dumps(dict(out=str(out), mb=round(out.stat().st_size / 1e6, 2), counts=data["counts"]), indent=1))


if __name__ == "__main__":
    main()
