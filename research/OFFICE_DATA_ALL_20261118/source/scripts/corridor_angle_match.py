"""Compare the corridor FP-power ratio with the ideal curve and estimate yaw by matching.

Reads ``fp_ratio_series.json``; writes ``deviation_table.csv``, ``angle_match_table.csv`` and
``ANGLE_MATCH.json`` next to it.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.features.angle_match import representative_yaw, yaw_candidates  # noqa: E402

TX_LABEL = {"LP_plus45": "+45", "LP_minus45": "-45"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-dir", type=Path, default=ROOT / "results" / "CORRIDOR_SWEEP_20261006")
    args = ap.parse_args()
    d = json.loads((args.sweep_dir / "fp_ratio_series.json").read_text())
    yaws = np.array(d["ideal"]["yaw_deg"])
    ideal = np.array(d["ideal"]["ratio"])
    dev_rows, ang_rows, summary, steps = [], [], [], []
    for s in d["series"]:
        if s["ratio_los_only"] is not None:
            los, full = np.array(s["ratio_los_only"]), np.array(s["ratio"])
            steps.append(dict(position=s["position"], range_m=round(s["range_m"], 2), tx_port=TX_LABEL[s["tx_port"]],
                              ratio_rmse_los_only_vs_ideal=float(np.sqrt(np.mean((los - ideal) ** 2))),
                              ratio_rmse_full_vs_los_only=float(np.sqrt(np.mean((full - los) ** 2))),
                              ratio_rmse_full_vs_ideal=float(np.sqrt(np.mean((full - ideal) ** 2)))))
        for variant, key in (("full", "ratio"), ("los_only", "ratio_los_only")):
            if s[key] is None:
                continue
            r = np.array(s[key])
            diff = r - ideal
            est, err = representative_yaw(r, yaws)
            cand = yaw_candidates(r)
            case = dict(position=s["position"], x_m=s["xy"][0], y_m=s["xy"][1], range_m=round(s["range_m"], 2), tx_port=TX_LABEL[s["tx_port"]], channel=variant)
            summary.append(dict(**case,
                                ratio_rmse=float(np.sqrt(np.mean(diff ** 2))), ratio_max_abs=float(np.max(np.abs(diff))), ratio_max_abs_at_yaw=float(yaws[np.argmax(np.abs(diff))]),
                                ratio_bias=float(np.mean(diff)), ratio_corr=float(np.corrcoef(r, ideal)[0, 1]),
                                angle_rmse_deg=float(np.sqrt(np.mean(err ** 2))), angle_max_abs_deg=float(np.max(np.abs(err))), angle_max_abs_at_yaw=float(yaws[np.argmax(np.abs(err))]),
                                angle_bias_deg=float(np.mean(err)),
                                angle_rmse_deg_excluding_flat=float(np.sqrt(np.mean(err[(ideal < 0.9)] ** 2)))))
            for k, yaw in enumerate(yaws):
                dev_rows.append(dict(**case, yaw_deg=yaw, ratio=r[k], ratio_ideal=ideal[k], diff=diff[k]))
                ang_rows.append(dict(**case, true_yaw_deg=yaw, ratio=round(r[k], 4), ideal_ratio_at_true=round(ideal[k], 4),
                                     candidates_deg=" / ".join(f"{c:.1f}" for c in sorted(cand[k])), estimate_deg=round(float(est[k]), 2), error_deg=round(float(err[k]), 2)))
    for name, rows in (("deviation_table.csv", dev_rows), ("angle_match_table.csv", ang_rows)):
        with (args.sweep_dir / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (args.sweep_dir / "ANGLE_MATCH.json").write_text(json.dumps(dict(
        method="match FP-power ratio to ideal |cos(2 yaw)|; 4 candidates per ratio; representative = candidate nearest the true yaw",
        yaw_grid_deg=yaws.tolist(), summary=summary, error_sources=steps, rows=ang_rows), indent=1))
    print(json.dumps(dict(cases=len(summary))))
    for s in summary:
        print(f"pos{s['position']} R={s['range_m']:5.2f} TX{s['tx_port']} {s['channel']:8s} ratio RMSE {s['ratio_rmse']:.3f} max {s['ratio_max_abs']:.3f}@{s['ratio_max_abs_at_yaw']:.0f}  "
              f"angle RMSE {s['angle_rmse_deg']:5.1f} max {s['angle_max_abs_deg']:5.1f}@{s['angle_max_abs_at_yaw']:.0f} bias {s['angle_bias_deg']:+5.1f}  RMSE(ideal<0.9) {s['angle_rmse_deg_excluding_flat']:.1f}")


if __name__ == "__main__":
    main()
