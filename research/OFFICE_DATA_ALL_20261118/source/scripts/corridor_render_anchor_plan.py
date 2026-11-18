"""Render the two-anchor sweep plan page from SCAN_PLAN.json.   python scripts/corridor_render_anchor_plan.py"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "CORRIDOR_ANCHOR_PLAN_20261007"
plan = json.loads((D / "SCAN_PLAN.json").read_text())
L, W = plan["corridor"]["length"], plan["corridor"]["width"]
X0, SX, SY = 60, 44.0, 78.0
VW, PH = int(X0 + L * SX + 26), int(W * SY + 96)
px = lambda x: X0 + x * SX
CLS = {"A1": ("c1", "앵커 1 (y = 0, 기존)"), "A2": ("c2", "앵커 2 (y = −0.4, 신규)")}


def panel(name):
    ay = plan["anchors"][name]
    cls = CLS[name][0]
    py = lambda y: 40 + (W / 2 - y) * SY
    g = [f'<svg viewBox="0 0 {VW} {PH}" role="img" aria-label="{CLS[name][1]} 위에서 본 태그 위치" xmlns="http://www.w3.org/2000/svg">']
    g.append(f'<rect class="corr" x="{px(0)}" y="{py(W/2)}" width="{L*SX}" height="{W*SY}"/>')
    g.append(f'<line class="mid" x1="{px(0)}" x2="{px(L)}" y1="{py(0)}" y2="{py(0)}"/>')
    g.append(f'<line class="yline" x1="{px(0)}" x2="{px(L)}" y1="{py(ay)}" y2="{py(ay)}"/>')
    for m in range(0, 21, 2):
        g.append(f'<text class="tick" x="{px(m)}" y="{py(-W/2)+16}" text-anchor="middle">{m}</text>')
    for yv in (-1.2, ay, 1.2) if ay != 0 else (-1.2, 0, 1.2):
        g.append(f'<text class="tick" x="{px(0)-8}" y="{py(yv)+4}" text-anchor="end">{yv:g}</text>')
    g.append(f'<text class="tick" x="{px(L/2)}" y="{py(-W/2)+36}" text-anchor="middle">x (m) · 점선: 앵커와 같은 y 선 (태그가 이 선 위에서 움직임)</text>')
    pts = [r for r in plan["positions"] if r["anchor"] == name]
    for i, r in enumerate(sorted(pts, key=lambda q: q["x"])):
        cx, cy = px(r["x"]), py(r["y"])
        tip = f'{CLS[name][1]} · 태그 x {r["x"]:g}, y {r["y"]:g} m · θ {r["theta_deg"]}° · φ {r["phi_deg"]}° · 거리 {r["range_m"]} m'
        m = f'<circle class="mk {cls}" cx="{cx}" cy="{cy}" r="5.5"/>' if name == "A1" else f'<rect class="mk {cls}" x="{cx-5}" y="{cy-5}" width="10" height="10" rx="1.5"/>'
        g.append(f'<g class="pt">{m}<title>{tip}</title></g>')
        g.append(f'<text class="tl" x="{cx}" y="{cy-11 if i % 2 == 0 else cy+20}" text-anchor="middle">{r["theta_deg"]:.0f}°</text>')
    g.append(f'<rect class="anchor" x="{px(plan["anchor_x"])-6}" y="{py(ay)-6}" width="12" height="12"/><title>앵커 · 천장 (x {plan["anchor_x"]:g}, y {ay:g})</title>')
    g.append("</svg>")
    return "\n".join(g)


SIDE = {"left": "앵커 왼쪽", "below": "바로 아래", "right": "앵커 오른쪽"}
rows = "".join(f'<tr><td><span class="sw {CLS[r["anchor"]][0]}"></span>{CLS[r["anchor"]][1]}</td><td>{"재사용" if r["status"]=="existing" else "신규"}</td><td>{SIDE[r["side"]]}</td><td class="n">{r["x"]:g}</td><td class="n">{r["y"]:g}</td><td class="n">{r["theta_deg"]}</td><td class="n">{r["phi_deg"]}</td><td class="n">{r["range_m"]}</td></tr>' for r in plan["positions"])
page = (D / "template.html").read_text(encoding="utf8")
for k, v in {"__P1__": panel("A1"), "__P2__": panel("A2"), "__ROWS__": rows, "__N1__": str(plan["counts"]["A1"]), "__N2__": str(plan["counts"]["A2"]),
             "__TOTAL__": str(plan["total"]), "__NEW__": str(plan["new_positions"]), "__HOURS__": str(plan["hours_4cores"]), "__AX__": f'{plan["anchor_x"]:g}'}.items():
    page = page.replace(k, v)
(D / "anchor_sweep_plan.html").write_text(page, encoding="utf8")
print(D / "anchor_sweep_plan.html", len(page) // 1000, "kB")
