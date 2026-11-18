"""Anchor 1 (4, 0) versus anchor 2 (4, -0.4): same device, same tag x list, tag on each anchor's own y line.

Per tag x and TX port: the yaw curves |s_full| of both anchors (19 yaws), their rms difference (pure environment effect, device identical), and yaw-estimation
errors of three templates for anchor 2:  (i) the angle model for anchor 2,  (ii) anchor 1's measured curve (periodic spline of its signed s),  (iii) the ideal |cos 2 yaw|.
Single-sample inversion; the candidate nearest the true yaw is taken (same convention as before).    python scripts/corridor_anchor_compare.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_case_check as cc  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

PLAN = ROOT / "results/CORRIDOR_ANCHOR_PLAN_20261007/SCAN_PLAN.json"
OUT = ROOT / "results/CORRIDOR_ANCHOR2_20261007"
BINS = [(0, 20), (20, 40), (40, 60), (60, 72), (72, 90)]


def curve_template(s_signed):
    """Signed 19-sample yaw curve -> dense |s| on cc.GRID (0..180 by 0.1), periodic spline (period 180 deg)."""
    y = np.asarray(s_signed, float).copy()
    y[-1] = y[0] = 0.5 * (y[0] + y[-1])
    return np.abs(CubicSpline(sf.YAWS, y, bc_type="periodic")(cc.GRID))


def errors(s_meas, curve_abs):
    err = []
    for k, yaw in enumerate(sf.YAWS):
        cand = cc.invert(abs(s_meas[k]), curve_abs)
        err.append(float(cand[np.argmin(np.abs(cand - yaw))] - yaw))
    return np.array(err)


def main():
    plan = json.loads(PLAN.read_text())
    s1 = {}
    for f in ("results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json", "results/CORRIDOR_SCAN2_20261007/SHIFT_FIT_SCAN2.json"):
        for p in json.loads((ROOT / f).read_text())["positions"]:
            if p["y"] == 0.0:
                s1[p["x"]] = p
    s2 = {p["x"]: p for p in json.loads((OUT / "SHIFT_FIT_ANCHOR2.json").read_text())["positions"]}
    setup2, banks = CorridorSetup(anchor_y_m=-0.4), sf.Banks()
    theta = {r["x"]: r["theta_deg"] for r in plan["positions"] if r["anchor"] == "A2"}
    rows = []
    for x in sorted(s2):
        if x not in s1:
            continue
        for tn in sf.TX:
            a1, a2 = np.array(s1[x]["tx"][tn]["s_full"]), np.array(s2[x]["tx"][tn]["s_full"])
            dense, _ = tc.model_curve(banks, setup2, x, -0.4, tn)
            tpl = dict(angle_model_A2=np.abs(dense), anchor1_curve=curve_template(a1), ideal=np.abs(np.cos(2 * np.radians(cc.GRID))))
            err = {k: errors(a2, v) for k, v in tpl.items()}
            rows.append(dict(x=x, tx=tn, theta=theta[x], rms_diff_abs=float(np.sqrt(np.mean((np.abs(a1) - np.abs(a2)) ** 2))),
                             rms_diff_signed=float(np.sqrt(np.mean((a1 - a2) ** 2))), yaw_rmse={k: float(np.sqrt(np.mean(v ** 2))) for k, v in err.items()},
                             yaw_err={k: v.tolist() for k, v in err.items()}))
    out = dict(rows=rows, by_theta=[])
    for lo, hi in BINS:
        sel = [r for r in rows if lo <= r["theta"] < hi]
        if not sel:
            continue
        d = dict(theta_lo=lo, theta_hi=hi, n_curves=len(sel), median_rms_diff_abs=float(np.median([r["rms_diff_abs"] for r in sel])))
        for k in ("angle_model_A2", "anchor1_curve", "ideal"):
            e = np.concatenate([r["yaw_err"][k] for r in sel])
            d[k] = dict(rmse=float(np.sqrt(np.mean(e ** 2))), within5=float(np.mean(np.abs(e) <= 5)))
        out["by_theta"].append(d)
    allr = {k: np.concatenate([r["yaw_err"][k] for r in rows]) for k in ("angle_model_A2", "anchor1_curve", "ideal")}
    out["overall"] = {k: dict(rmse=float(np.sqrt(np.mean(v ** 2))), within5=float(np.mean(np.abs(v) <= 5))) for k, v in allr.items()}
    out["overall"]["median_rms_diff_abs"] = float(np.median([r["rms_diff_abs"] for r in rows]))
    (OUT / "ANCHOR_COMPARE.json").write_text(json.dumps(out, indent=1))
    for r in rows:
        print(f"x {r['x']:5.2f} {r['tx'][3:]:8s} theta {r['theta']:5.1f} rms|d| anchor1 vs 2 {r['rms_diff_abs']:.3f} | yaw RMSE angle-model {r['yaw_rmse']['angle_model_A2']:5.2f} anchor1-curve {r['yaw_rmse']['anchor1_curve']:5.2f} ideal {r['yaw_rmse']['ideal']:5.2f}")
    for b in out["by_theta"]:
        print(f"theta {b['theta_lo']:2d}-{b['theta_hi']:2d} n={b['n_curves']:2d} median rms diff {b['median_rms_diff_abs']:.3f} | RMSE angle {b['angle_model_A2']['rmse']:5.2f} ({b['angle_model_A2']['within5']*100:3.0f}%) anchor1 {b['anchor1_curve']['rmse']:5.2f} ({b['anchor1_curve']['within5']*100:3.0f}%) ideal {b['ideal']['rmse']:5.2f}")
    print("overall", {k: (round(v['rmse'], 2), round(v['within5'], 2)) if isinstance(v, dict) else round(v, 3) for k, v in out["overall"].items()})


if __name__ == "__main__":
    main()
