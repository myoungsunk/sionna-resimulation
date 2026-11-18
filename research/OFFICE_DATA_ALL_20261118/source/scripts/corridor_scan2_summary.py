"""Summary of the 61-position scan batch against the angle model, by anchor off-boresight angle theta and by tier (A grid / B validation).

Per curve (position x TX): rms of |s_sim| - |s_angle_model| (rms_d), share of that deviation a rigid yaw shift explains
(SHIFT_VS_LOCAL_SCAN2.json) and the yaw error of the angle-model template (single sample, candidate nearest the true yaw).
Writes SCAN2_SUMMARY.json.     python scripts/corridor_scan2_summary.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

D = ROOT / "results" / "CORRIDOR_SCAN2_20261007"
BINS = [(0, 30), (30, 50), (50, 65), (65, 75), (75, 90)]


def main():
    setup, banks = CorridorSetup(), sf.Banks()
    plan = {(r["x"], r["y"]): r for r in json.loads((ROOT / "results/CORRIDOR_PLAN_20261007/SCAN_PLAN.json").read_text())["positions"]}
    fit = json.loads((D / "SHIFT_FIT_SCAN2.json").read_text())
    svl = {(r["x"], r["y"], r["tx"]): r for r in json.loads((D / "SHIFT_VS_LOCAL_SCAN2.json").read_text())["rows"]}
    rows = []
    for p in fit["positions"]:
        meta = plan[(p["x"], p["y"])]
        for tn in sf.TX:
            s_full = np.array(p["tx"][tn]["s_full"])
            dense, _ = tc.model_curve(banks, setup, p["x"], p["y"], tn)
            err = tc.err_from_curve(s_full, np.abs(dense))
            r = svl[(p["x"], p["y"], tn)]
            rows.append(dict(x=p["x"], y=p["y"], tx=tn, tier=meta["tier"], theta=meta["theta_deg"], rms_d=r["rms_d"], expl_shift=r["expl_shift"],
                             expl_shift_const_gain=r["expl_shift_const_gain"], yaw_rmse=float(np.sqrt(np.mean(err ** 2))), yaw_err=err.tolist()))
    out = dict(rows=rows, by_theta=[], by_tier={})
    for lo, hi in BINS:
        sel = [r for r in rows if lo <= r["theta"] < hi]
        if sel:
            e = np.concatenate([r["yaw_err"] for r in sel])
            out["by_theta"].append(dict(theta_lo=lo, theta_hi=hi, n_curves=len(sel), median_rms_d=float(np.median([r["rms_d"] for r in sel])),
                                        median_expl_shift=float(np.median([r["expl_shift"] for r in sel])), yaw_rmse=float(np.sqrt(np.mean(e ** 2))),
                                        within5=float(np.mean(np.abs(e) <= 5))))
    for t in ("A", "B"):
        sel = [r for r in rows if r["tier"] == t]
        e = np.concatenate([r["yaw_err"] for r in sel])
        out["by_tier"][t] = dict(n_curves=len(sel), median_rms_d=float(np.median([r["rms_d"] for r in sel])), median_expl_shift=float(np.median([r["expl_shift"] for r in sel])),
                                 yaw_rmse=float(np.sqrt(np.mean(e ** 2))), within5=float(np.mean(np.abs(e) <= 5)))
    (D / "SCAN2_SUMMARY.json").write_text(json.dumps(out, indent=1))
    for b in out["by_theta"]:
        print(f"theta {b['theta_lo']:2d}-{b['theta_hi']:2d}: n={b['n_curves']:3d} median rms_d {b['median_rms_d']:.3f} expl_shift {b['median_expl_shift']:.2f} yaw RMSE {b['yaw_rmse']:5.2f} within5 {b['within5']*100:3.0f}%")
    for t, v in out["by_tier"].items():
        print(f"tier {t}: n={v['n_curves']} median rms_d {v['median_rms_d']:.3f} expl_shift {v['median_expl_shift']:.2f} yaw RMSE {v['yaw_rmse']:.2f} within5 {v['within5']*100:.0f}%")


if __name__ == "__main__":
    main()
