"""Anchor 1 (4, 0) versus anchor 2B (anchor (4, -0.4), tag on y = 0, same theta): curve differences, yaw-estimation errors, and the earlier
anchor-2 result (tag on y = -0.4) for reference.  Writes ANCHOR2B_COMPARE.json and ANCHOR2B_CURVES.json (data of the curve page).
    python scripts/corridor_anchor2b_analysis.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_anchor_compare as ac  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from corridor_case_check import GRID  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

OUT = ROOT / "results/CORRIDOR_ANCHOR2B_20261007"
BINS = [(0, 20), (20, 40), (40, 60), (60, 72), (72, 90)]


def main():
    plan = json.loads((OUT / "SCAN_PLAN.json").read_text())
    s1 = {}
    for f in ("results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json", "results/CORRIDOR_SCAN2_20261007/SHIFT_FIT_SCAN2.json"):
        for p in json.loads((ROOT / f).read_text())["positions"]:
            if p["y"] == 0.0:
                s1[p["x"]] = p
    s2 = {p["x"]: p for p in json.loads((ROOT / "results/CORRIDOR_ANCHOR2_20261007/SHIFT_FIT_ANCHOR2.json").read_text())["positions"]}
    s2b = {p["x"]: p for p in json.loads((OUT / "SHIFT_FIT_ANCHOR2B.json").read_text())["positions"]}
    setup2, banks = CorridorSetup(anchor_y_m=-0.4), sf.Banks()
    rms = lambda a, b: float(np.sqrt(np.mean((np.abs(a) - np.abs(b)) ** 2)))
    r4 = lambda a: [round(float(v), 4) for v in a]
    rows, recs = [], []
    for pl in plan["positions"]:
        x1, xb = pl["x1"], pl["x"]
        rec = dict(x1=x1, x=xb, theta=pl["theta_deg"], phi=pl["phi_deg"], range_m=pl["range_m"], tx={})
        for tn in sf.TX:
            a1, a2, ab = (np.array(d[x]["tx"][tn]["s_full"]) for d, x in ((s1, x1), (s2, x1), (s2b, xb)))
            dense, _ = tc.model_curve(banks, setup2, xb, 0.0, tn)
            tpl = dict(angle_model=np.abs(dense), anchor1_curve=ac.curve_template(a1), ideal=np.abs(np.cos(2 * np.radians(GRID))))
            err = {k: ac.errors(ab, v) for k, v in tpl.items()}
            rows.append(dict(x1=x1, x=xb, tx=tn, theta=pl["theta_deg"], rms_1_vs_2b=rms(a1, ab), rms_1_vs_2=rms(a1, a2), rms_2_vs_2b=rms(a2, ab),
                             yaw_rmse={k: float(np.sqrt(np.mean(v ** 2))) for k, v in err.items()}, yaw_err={k: v.tolist() for k, v in err.items()}))
            rec["tx"][tn] = dict(a1=r4(np.abs(a1)), a2=r4(np.abs(a2)), a2b=r4(np.abs(ab)), model=r4(np.abs(dense)[::10]), rms_1_vs_2b=round(rows[-1]["rms_1_vs_2b"], 4),
                                 rms_1_vs_2=round(rows[-1]["rms_1_vs_2"], 4), rms_2_vs_2b=round(rows[-1]["rms_2_vs_2b"], 4), yaw_rmse={k: round(v, 2) for k, v in rows[-1]["yaw_rmse"].items()})
        recs.append(rec)
    out = dict(rows=rows, by_theta=[])
    for lo, hi in BINS:
        sel = [r for r in rows if lo <= r["theta"] < hi]
        if sel:
            d = dict(theta_lo=lo, theta_hi=hi, n_curves=len(sel), **{k: float(np.median([r[k] for r in sel])) for k in ("rms_1_vs_2b", "rms_1_vs_2", "rms_2_vs_2b")})
            for k in ("angle_model", "anchor1_curve", "ideal"):
                e = np.concatenate([r["yaw_err"][k] for r in sel])
                d[k] = dict(rmse=float(np.sqrt(np.mean(e ** 2))), within5=float(np.mean(np.abs(e) <= 5)))
            out["by_theta"].append(d)
    allr = {k: np.concatenate([r["yaw_err"][k] for r in rows]) for k in ("angle_model", "anchor1_curve", "ideal")}
    out["overall"] = {k: dict(rmse=float(np.sqrt(np.mean(v ** 2))), within5=float(np.mean(np.abs(v) <= 5))) for k, v in allr.items()}
    (OUT / "ANCHOR2B_COMPARE.json").write_text(json.dumps(out, indent=1))
    recs.sort(key=lambda r: (r["theta"], r["x"]))
    (OUT / "ANCHOR2B_CURVES.json").write_text(json.dumps(dict(yaw_deg=sf.YAWS.tolist(), model_yaw_deg=np.arange(0, 181, 1.0).tolist(), records=recs), separators=(",", ":")))
    for b in out["by_theta"]:
        print(f"theta {b['theta_lo']:2d}-{b['theta_hi']:2d} n={b['n_curves']:2d} median rms diff: 1 vs 2B {b['rms_1_vs_2b']:.3f} | 1 vs 2 {b['rms_1_vs_2']:.3f} | 2 vs 2B {b['rms_2_vs_2b']:.3f} || yaw RMSE(2B) angle {b['angle_model']['rmse']:5.2f} ({b['angle_model']['within5']*100:3.0f}%) anchor1 {b['anchor1_curve']['rmse']:5.2f} ideal {b['ideal']['rmse']:5.2f}")
    print("overall", {k: (round(v['rmse'], 2), round(v['within5'], 2)) for k, v in out["overall"].items()})


if __name__ == "__main__":
    main()
