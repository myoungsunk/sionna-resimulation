"""How the x-shift (yaw0), y-shift (B) and amplitude (A) change the flat parts of the |s|-vs-yaw curve.

Model: s(psi) = B + sigma*A*cos 2(psi - yaw0); observable r = |s|; slope = |dr/dpsi| (per degree).
A region is 'flat' where slope < THR per degree. Writes FLAT_AXES.json.
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
THR = 0.01
PSI = np.arange(0.0, 180.0, 0.05)


def curve(A, B, yaw0, sigma=-1):
    return np.abs(B + sigma * A * np.cos(np.deg2rad(2 * (PSI - yaw0))))


def slope(r):
    return np.abs(np.gradient(np.r_[r, r[0]], 0.05)[:-1])


def flat_frac(*curves):
    g = np.sqrt(sum(slope(c) ** 2 for c in curves))
    return float(np.mean(g < THR))


def main():
    out = {"thr_per_deg": THR}
    out["A_B_grid"] = [dict(A=A, B=B, flat=flat_frac(curve(A, B, 0.0)))
                       for A in (0.7, 0.8, 0.9, 0.95, 1.0) for B in (0.0, 0.05, 0.1, 0.15, 0.2) if A + abs(B) <= 1.0 + 1e-9]
    out["pair_offset"] = []
    for d in (0, 5, 10, 15, 22, 30, 45):
        c1, c2 = curve(0.95, 0.0, d / 2, -1), curve(0.95, 0.0, -d / 2, +1)
        out["pair_offset"].append(dict(offset_deg=d, single=flat_frac(c1), joint=flat_frac(c1, c2)))
    # the same offset measured from the simulation fits (TX+45 vs TX-45 yaw0 difference), plus the joint flat fraction
    sh = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    rows = []
    for p in sh["positions"]:
        f = {tn: p["tx"][tn]["fit_full"] for tn in p["tx"]}
        (n1, a), (n2, b) = list(f.items())
        d = (a["yaw0_deg"] - b["yaw0_deg"] + 45) % 90 - 45
        c1, c2 = curve(a["A"], a["B"], a["yaw0_deg"], -1), curve(b["A"], b["B"], b["yaw0_deg"], +1)
        rows.append(dict(x=p["x"], y=p["y"], yaw0_diff_deg=float(d), single=[flat_frac(c1), flat_frac(c2)], joint=flat_frac(c1, c2),
                         joint_if_synced=flat_frac(c1, curve(b["A"], b["B"], a["yaw0_deg"], +1))))
    out["positions"] = rows
    (ROOT / "results/CORRIDOR_SCAN_20261006/FLAT_AXES.json").write_text(json.dumps(out, indent=1))
    print("A,B grid:")
    for r in out["A_B_grid"]:
        print(f"  A={r['A']:.2f} B={r['B']:.2f} flat={r['flat']:.3f}")
    print("pair offset:", [(r["offset_deg"], round(r["single"], 3), round(r["joint"], 3)) for r in out["pair_offset"]])
    print("sim positions: mean single %.3f, joint %.3f, if synced %.3f; mean |yaw0 diff| %.1f" % (
        np.mean([np.mean(r["single"]) for r in rows]), np.mean([r["joint"] for r in rows]), np.mean([r["joint_if_synced"] for r in rows]),
        np.mean([abs(r["yaw0_diff_deg"]) for r in rows])))


if __name__ == "__main__":
    main()
