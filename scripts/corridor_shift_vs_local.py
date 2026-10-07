"""Is the multipath deviation of |s| a rigid yaw shift of the angle-model curve, or a local deformation?

d(yaw) = |s_sim| - |s_angle_model|  (angle model = LoS-only with both antenna patterns read at the actual angles; no geometry beyond
the LoS direction).  A pure x-shift of the angle-model curve would give d = -delta * r'(yaw): zero at the flat peaks, largest on the slopes.
Reported per curve: share of sum(d^2) explained by (a) one-parameter shift, (b) shift + constant + gain, and where |d| lives relative to
the curve's slope.   python scripts/corridor_shift_vs_local.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_case_check as cc  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402


def main():
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    rows = []
    for p in sorted(shift["positions"], key=lambda q: (q["x"], q["y"])):
        if p["off_boresight_deg"] < 1:
            continue
        for tn in sf.TX:
            dense_abs, ext = tc.model_curve(banks, setup, p["x"], p["y"], tn)
            r_ang = np.abs(np.interp(sf.YAWS, cc.GRID, dense_abs))
            slope_dense = np.gradient(np.abs(dense_abs), 0.1)
            slope = np.interp(sf.YAWS, cc.GRID, slope_dense)
            r_sim = np.abs(np.array(p["tx"][tn]["s_full"]))
            d = r_sim - r_ang
            sst = float(np.sum(d ** 2))
            # (a) pure shift: d = -delta * r'
            g = -slope
            delta = float(g @ d / (g @ g))
            sse_a = float(np.sum((d - delta * g) ** 2))
            # (b) shift + constant + gain on the angle-model curve
            X = np.c_[g, np.ones_like(g), r_ang]
            coef, *_ = np.linalg.lstsq(X, d, rcond=None)
            sse_b = float(np.sum((d - X @ coef) ** 2))
            steep = np.abs(slope) >= 0.02
            flat = np.abs(slope) < 0.01
            rows.append(dict(x=p["x"], y=p["y"], tx=tn, rms_d=float(np.sqrt(np.mean(d ** 2))), shift_deg=delta,
                             expl_shift=1 - sse_a / sst, expl_shift_const_gain=1 - sse_b / sst,
                             share_ss_steep=float(np.sum(d[steep] ** 2) / sst), frac_steep=float(steep.mean()),
                             share_ss_flat=float(np.sum(d[flat] ** 2) / sst), frac_flat=float(flat.mean()),
                             corr_abs_d_abs_slope=float(np.corrcoef(np.abs(d), np.abs(slope))[0, 1])))
    med = lambda k: float(np.median([r[k] for r in rows]))
    out = dict(rows=rows, n=len(rows), median={k: med(k) for k in ("rms_d", "expl_shift", "expl_shift_const_gain", "share_ss_steep", "frac_steep", "share_ss_flat", "frac_flat", "corr_abs_d_abs_slope")})
    (ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_VS_LOCAL.json").write_text(json.dumps(out, indent=1))
    for r in rows:
        print(f"({r['x']:4.1f},{r['y']:5.2f}) {r['tx'][3:]:9s} rms_d {r['rms_d']:.3f} shift {r['shift_deg']:6.1f} expl shift {r['expl_shift']:5.2f} +c,g {r['expl_shift_const_gain']:5.2f} | SS in steep {r['share_ss_steep']:.2f} (frac {r['frac_steep']:.2f}) in flat {r['share_ss_flat']:.2f} (frac {r['frac_flat']:.2f}) corr {r['corr_abs_d_abs_slope']:5.2f}")
    print("median", {k: round(v, 3) for k, v in out["median"].items()})


if __name__ == "__main__":
    main()
