"""Render the scan-position plan page (SVG top view + table) from SCAN_PLAN.json.   python scripts/corridor_render_scan_plan.py"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "CORRIDOR_PLAN_20261007"
plan = json.loads((D / "SCAN_PLAN.json").read_text())
L, W = plan["corridor"]["length"], plan["corridor"]["width"]
AX, AY = plan["corridor"]["anchor"]
X0, Y0, SX, SY = 46, 34, 44.0, 70.0  # px origin, px per metre in x and (stretched) in y
VW, VH = int(X0 + L * SX + 26), int(Y0 + W * SY + 50)
px = lambda x: X0 + x * SX
py = lambda y: Y0 + (W / 2 - y) * SY  # +y drawn upward
H_ANCHOR = 2.65 - 0.45  # anchor antenna height above the robot antenna

svg = [f'<svg viewBox="0 0 {VW} {VH}" role="img" aria-label="복도 위에서 본 스캔 위치" xmlns="http://www.w3.org/2000/svg">']
svg.append(f'<rect class="corr" x="{px(0)}" y="{py(W/2)}" width="{L*SX}" height="{W*SY}"/>')
svg.append(f'<rect class="zone" x="{px(plan["x_range"][0])}" y="{py(plan["y_limit"])}" width="{(plan["x_range"][1]-plan["x_range"][0])*SX}" height="{2*plan["y_limit"]*SY}"/>')
svg.append(f'<line class="mid" x1="{px(0)}" x2="{px(L)}" y1="{py(0)}" y2="{py(0)}"/>')
for m in range(0, 21, 2):
    svg.append(f'<text class="tick" x="{px(m)}" y="{py(-W/2)+16}" text-anchor="middle">{m}</text>')
svg.append(f'<text class="tick" x="{px(L/2)}" y="{py(-W/2)+36}" text-anchor="middle">가로 x: 복도 방향 (m) · 세로 y: 복도 폭 방향 (m, 확대해 그림)</text>')
for yv in (-1.2, 0, 1.2):
    svg.append(f'<text class="tick" x="{X0-8}" y="{py(yv)+4}" text-anchor="end">{yv:g}</text>')
# iso off-boresight lines of the anchor (theta = 20, 40, 60, 70, 80 deg)
for th in (20, 40, 60, 70, 80):
    r = H_ANCHOR * math.tan(math.radians(th))
    for sgn in (1, -1):
        pts = []
        for i in range(0, 61):
            y = -W / 2 + W * i / 60
            if abs(y - AY) <= r:
                x = AX + sgn * math.sqrt(r * r - (y - AY) ** 2)
                if 0 <= x <= L:
                    pts.append(f"{px(x):.1f},{py(y):.1f}")
        if len(pts) > 1:
            svg.append(f'<polyline class="iso" points="{" ".join(pts)}"/>')
            xl = AX + sgn * r
            if 0.5 < xl < L - 0.5:
                svg.append(f'<text class="isot" x="{px(xl)}" y="{Y0-4}" text-anchor="middle">{th}°</text>')
STY = {"existing": ("c1", "기존"), "A": ("c2", "A 격자"), "B": ("c3", "B 검증")}
for tier in ("A", "B", "existing"):
    for r in (q for q in plan["positions"] if q["tier"] == tier):
        cx, cy = px(r["x"]), py(r["y"])
        tip = f'{STY[tier][1]} · x {r["x"]:g}, y {r["y"]:g} m · θ {r["theta_deg"]}° · φ {r["phi_deg"]}° · 거리 {r["range_m"]} m'
        if tier == "existing":
            m = f'<circle class="mk c1" cx="{cx}" cy="{cy}" r="5.5"/>'
        elif tier == "A":
            m = f'<rect class="mk c2" x="{cx-5}" y="{cy-5}" width="10" height="10" rx="1.5"/>'
        else:
            m = f'<path class="mk c3" d="M{cx} {cy-7} L{cx+7} {cy} L{cx} {cy+7} L{cx-7} {cy} Z"/>'
        svg.append(f'<g class="pt">{m}<title>{tip}</title></g>')
svg.append(f'<rect class="anchor" x="{px(AX)-6}" y="{py(AY)-6}" width="12" height="12"/><title>앵커 · 천장 (x 4, y 0)</title>')
svg.append("</svg>")

rows = "".join(f'<tr><td><span class="sw {STY[r["tier"]][0]}"></span>{STY[r["tier"]][1]}</td><td class="n">{r["x"]:g}</td><td class="n">{r["y"]:g}</td><td class="n">{r["theta_deg"]}</td><td class="n">{r["phi_deg"]}</td><td class="n">{r["range_m"]}</td></tr>' for r in plan["positions"])
n, cov, mins = plan["counts"], plan["theta_range"], plan["minutes_4cores"]
page = (D / "template.html").read_text(encoding="utf8")
for k, v in {"__SVG__": "\n".join(svg), "__ROWS__": rows, "__NEX__": str(n["existing"]), "__NA__": str(n["A"]), "__NB__": str(n["B"]),
             "__MINA__": f'{mins["A"]/60:.1f}', "__MINB__": f'{mins["B"]/60:.1f}', "__MINAB__": f'{(mins["A"]+mins["B"])/60:.1f}',
             "__TOTAL__": str(n["existing"] + n["A"] + n["B"]), "__YLIM__": f'{plan["y_limit"]:.2f}', "__XLO__": f'{plan["x_range"][0]:g}', "__XHI__": f'{plan["x_range"][1]:g}'}.items():
    page = page.replace(k, v)
(D / "corridor_scan_plan.html").write_text(page, encoding="utf8")
print(D / "corridor_scan_plan.html", len(page) // 1000, "kB")
