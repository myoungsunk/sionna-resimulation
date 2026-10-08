"""Page: angle model versus simulated yaw curves at the office positions whose line of sight is blocked (10 positions x 2 anchor ports).
    python scripts/office_render_blocked.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.features import specular_model as sm  # noqa: E402
from qclean_uwb.scenarios.office import MATERIALS, OfficeSetup  # noqa: E402

OUT = ROOT / "results" / "OFFICE_ANALYSIS_20261008"
C0, F = 299792458.0, 6.25e9


def straight_through(setup, sheets, x, y, names):
    """Estimated power loss (dB) of the straight anchor-tag line through the blocking sheets (single slab each, TE/TM mean); crossing angle per sheet."""
    a, r = setup.anchor_position, setup.tag_position(x, y)
    u = (a - r) / np.linalg.norm(a - r)
    det, loss = [], 0.0
    for n in names:
        q = sheets[n]["quad"]
        nrm = np.cross(q[1] - q[0], q[3] - q[0])
        nrm /= np.linalg.norm(nrm)
        cos = abs(u @ nrm)
        mat, thk = MATERIALS[sheets[n]["group"]]
        tte, ttm = sm.slab_transmission(cos, sm.eta_complex(mat, F), thk, C0 / F)
        l = -10 * np.log10(0.5 * (abs(tte) ** 2 + abs(ttm) ** 2))
        loss += l
        det.append(dict(name=n, material=mat, thickness_m=thk, incidence_deg=round(float(np.degrees(np.arccos(cos))), 0), loss_db=round(float(l), 2)))
    return round(float(loss), 2), det


def plan_svg(setup, pos):
    sc, m = 30.0, 22
    W, H = int(setup.length_m * sc + 2 * m), int(setup.width_m * sc + 2 * m)
    px, py = (lambda x: m + x * sc), (lambda y: m + (setup.width_m - y) * sc)
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="막힌 위치 10곳의 평면도" xmlns="http://www.w3.org/2000/svg"><rect class="env" x="{px(0)}" y="{py(setup.width_m)}" width="{setup.length_m*sc}" height="{setup.width_m*sc}"/>']
    for b in setup.boxes():
        cls = "desk" if b["group"] == "desks" else "part"
        g.append(f'<rect class="{cls}" x="{px(b["lo"][0])}" y="{py(b["hi"][1])}" width="{max((b["hi"][0]-b["lo"][0])*sc, 1.6)}" height="{max((b["hi"][1]-b["lo"][1])*sc, 1.6)}"/>')
    ax, ay = setup.anchor_x_m, setup.anchor_y_m
    for i, p in enumerate(pos, 1):
        g.append(f'<line class="ln" x1="{px(ax)}" y1="{py(ay)}" x2="{px(p["x"])}" y2="{py(p["y"])}"/>')
    g.append(f'<rect class="anc" x="{px(ax)-5}" y="{py(ay)-5}" width="10" height="10"><title>앵커 (천장)</title></rect>')
    for i, p in enumerate(pos, 1):
        g.append(f'<g><circle class="pt" cx="{px(p["x"])}" cy="{py(p["y"])}" r="9"/><text class="pn" x="{px(p["x"])}" y="{py(p["y"])+4}" text-anchor="middle">{i}</text><title>{i}: ({p["x"]}, {p["y"]}) θ {p["theta_deg"]}°</title></g>')
    g.append("</svg>")
    return "".join(g)


def main():
    setup = OfficeSetup()
    sheets = {sh["name"]: sh for sh in setup.rf_sheets()}
    d = json.loads((OUT / "OFFICE_ANALYSIS.json").read_text())
    pos = sorted([p for p in d["positions"] if not p["los_clear"]], key=lambda p: (p["theta_deg"], p["x"]))
    for p in pos:
        p["loss_db"], p["crossings"] = straight_through(setup, sheets, p["x"], p["y"], p["blockers"])
        for tn, t in p["tx"].items():
            s, m = np.abs(t["s"]), np.abs(t["model"])
            t["corr_model"] = float(np.corrcoef(s, m)[0, 1])
    L = np.array([p["loss_db"] for p in pos])
    R = np.array([np.mean([t["rms_dev_model"] for t in p["tx"].values()]) for p in pos])
    T = np.array([p["theta_deg"] for p in pos])
    stats = dict(corr_theta_dev=float(np.corrcoef(T, R)[0, 1]), corr_loss_dev=float(np.corrcoef(L, R)[0, 1]), n=len(pos))
    allt = [t for p in pos for t in p["tx"].values()]
    stats.update(n_curves=len(allt), n_good=sum(t["yaw_rmse_model"] <= 5 for t in allt), n_corr_hi=sum(t["corr_model"] >= 0.9 for t in allt), n_bad=sum(t["yaw_rmse_model"] > 10 for t in allt),
                 model_better=sum(t["yaw_rmse_model"] < t["yaw_rmse_ideal"] for t in allt))
    data = dict(yaw_deg=d["yaw_deg"], model_yaw_deg=d["model_yaw_deg"], positions=pos, stats=stats)
    page = (ROOT / "scripts" / "office_blocked_template.html").read_text(encoding="utf8").replace("__PLAN__", plan_svg(setup, pos)).replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    (OUT / "office_blocked.html").write_text(page, encoding="utf8")
    (OUT / "OFFICE_BLOCKED.json").write_text(json.dumps(dict(stats=stats, positions=[dict(x=p["x"], y=p["y"], theta_deg=p["theta_deg"], blockers=p["blockers"], loss_db=p["loss_db"], crossings=p["crossings"],
                                                                                   tx={tn: {k: round(v, 4) for k, v in t.items() if isinstance(v, float)} for tn, t in p["tx"].items()}) for p in pos]), indent=1))
    print(stats)


if __name__ == "__main__":
    main()
