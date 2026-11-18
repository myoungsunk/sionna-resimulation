"""Why does a close-looking angle-model curve still give several degrees of yaw error?

Yaw error = metric mismatch / curve slope.  For every (curve, yaw) sample of the angle-model template this reports the metric
mismatch  dr = |s_measured| - template(true yaw),  the template slope g = |d template / d yaw| (per degree) and the oracle yaw error,
then splits the squared yaw error by slope bin.

  python scripts/corridor_error_budget.py
"""
from __future__ import annotations

import argparse
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

BINS = [(0.0, 0.005), (0.005, 0.01), (0.01, 0.02), (0.02, 0.03), (0.03, 1.0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "ERROR_BUDGET.json")
    args = ap.parse_args()
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    rows = []
    for p in sorted(shift["positions"], key=lambda q: (q["x"], q["y"])):
        if p["off_boresight_deg"] < 1:
            continue
        for tn in sf.TX:
            s_meas = np.array(p["tx"][tn]["s_full"])
            curve = np.abs(tc.model_curve(banks, setup, p["x"], p["y"], tn)[0])
            slope = np.abs(np.gradient(curve, 0.1))
            for k, yaw in enumerate(sf.YAWS):
                i = int(round(yaw * 10))
                g = float(np.mean(slope[max(i - 10, 0):i + 11]))          # slope averaged over +-1 deg
                dr = float(abs(s_meas[k]) - curve[i])
                cand = cc.invert(abs(s_meas[k]), curve)
                e = float(cand[np.argmin(np.abs(cand - yaw))] - yaw)
                rows.append(dict(x=p["x"], y=p["y"], tx=tn, yaw=float(yaw), r_meas=float(abs(s_meas[k])), r_model=float(curve[i]), dr=dr, slope=g, err=e, ncand=len(cand),
                                 err_linear=float(dr / g) if g > 1e-4 else None))
    a = lambda key: np.array([r[key] for r in rows])
    err, dr, g = a("err"), a("dr"), a("slope")
    sse = float(np.sum(err ** 2))
    table = []
    for lo, hi in BINS:
        m = (g >= lo) & (g < hi)
        table.append(dict(slope_lo=lo, slope_hi=hi, n=int(m.sum()), rms_dr=float(np.sqrt(np.mean(dr[m] ** 2))) if m.any() else None, rms_err=float(np.sqrt(np.mean(err[m] ** 2))) if m.any() else None,
                          share_of_sse=float(np.sum(err[m] ** 2) / sse), median_abs_err=float(np.median(np.abs(err[m]))) if m.any() else None))
    steep = g >= 0.02
    lin = np.array([r["err_linear"] if r["err_linear"] is not None else np.nan for r in rows])
    out = dict(n=len(rows), rms_dr=float(np.sqrt(np.mean(dr ** 2))), rms_slope=float(np.sqrt(np.mean(g ** 2))), rms_err=float(np.sqrt(np.mean(err ** 2))),
               rms_err_steep=float(np.sqrt(np.mean(err[steep] ** 2))), n_steep=int(steep.sum()), bins=table,
               uniform_slope_estimate=float(np.sqrt(np.mean(dr ** 2)) / np.sqrt(np.mean(g ** 2))),
               linear_prediction_rms_steep=float(np.sqrt(np.nanmean(lin[steep] ** 2))),
               by_yaw=[dict(yaw=float(y), rms_err=float(np.sqrt(np.mean(err[a("yaw") == y] ** 2))), rms_dr=float(np.sqrt(np.mean(dr[a("yaw") == y] ** 2))), mean_slope=float(np.mean(g[a("yaw") == y]))) for y in sf.YAWS],
               flat_formula_deg_per_sqrt_dr=float(np.degrees(np.sqrt(2.0 / 2.0))))   # |cos 2 yaw| near a peak: dr = 2 dpsi^2  ->  dpsi = sqrt(dr/2) rad
    args.out.write_text(json.dumps(out, indent=1))
    print(f"samples {out['n']}: RMS metric mismatch {out['rms_dr']:.3f}, RMS slope {out['rms_slope']:.4f}/deg -> uniform-slope yaw error {out['uniform_slope_estimate']:.1f} deg; actual RMS yaw error {out['rms_err']:.2f} deg")
    print(f"steep samples (slope >= 0.02/deg): n={out['n_steep']}, RMS yaw error {out['rms_err_steep']:.2f} deg, linear prediction dr/slope {out['linear_prediction_rms_steep']:.2f} deg")
    for t in table:
        print(f"slope {t['slope_lo']:.3f}-{t['slope_hi']:.3f}: n={t['n']:3d}  RMS dr {t['rms_dr']:.3f}  RMS yaw err {t['rms_err']:5.2f}  median |err| {t['median_abs_err']:5.2f}  share of squared error {t['share_of_sse']*100:4.1f}%")
    print("by true yaw:", [(d["yaw"], round(d["rms_err"], 1)) for d in out["by_yaw"]])


if __name__ == "__main__":
    main()
