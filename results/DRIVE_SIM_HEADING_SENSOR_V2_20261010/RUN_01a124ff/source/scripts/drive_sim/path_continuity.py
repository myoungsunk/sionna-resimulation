"""S2 gate G3: path continuity along the whole trajectory.

Reads the per-position trace files, orders the stations along the drive (timeline CSV, phases drive_out / turn / drive_back) and reports
(a) paths that do not match any image-method sequence (must be 0) and (b) every place where the multiset of matched image sequences changes
between neighbouring stations, with the sequences that appeared or vanished.

  python scripts/drive_sim/path_continuity.py --timeline results/DRIVE_SIM_20261007/S1/timeline_y0_Tnone.csv --traces DIR --out G3.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim.paths import path_residuals, signature_diff  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402
from qclean_uwb.drivesim.rf_store import tag_of  # noqa: E402


DRIVE_PHASES = ("drive_out", "drive_back", "drive")      # R1 uses drive_out/drive_back, the added routes (R2/R4/R5) use drive


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", type=Path, required=True)
    ap.add_argument("--traces", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--anchor-x", type=float, default=4.0)
    args = ap.parse_args()
    stations, seen = [], set()
    for r in csv.DictReader(args.timeline.open()):
        key = (round(float(r["x"]), 6), round(float(r["y"]), 6))
        if r["phase"] in DRIVE_PHASES and key not in seen:
            seen.add(key)
            stations.append(key)
    setup = CorridorSetup(anchor_x_m=args.anchor_x)
    tols = (5e-14, 2e-13)                      # 5e-14 = pre-registered (PREREG G3); 2e-13 = float32 allowance for long paths (A8)
    sigs, unmatched_total, missing, bad = [], {t: 0 for t in tols}, [], []
    strict_unmatched_stations = []              # A15: every station with a delay residual above the pre-registered tolerance, not only the totals
    max_res, min_gap = 0.0, 1.0
    for x, y in stations:
        tag = tag_of(x, y)
        p = next((d / f"{tag}_trace.npz" for d in args.traces if (d / f"{tag}_trace.npz").exists()), None)
        if p is None:
            missing.append(tag)
            sigs.append(None)
            continue
        with np.load(p) as z:
            tau, status, rx_xy = z["tau"], str(z["status"]), (float(z["x"]), float(z["y"]))
        res, pick, cd, names = path_residuals(tau, setup.anchor_position, setup.robot_position(*rx_xy), setup.length_m, setup.y_half, setup.height_m)
        for t in tols:
            unmatched_total[t] += int((res > t).sum())
        max_res = max(max_res, float(res.max()))
        if (res > tols[0]).any():
            strict_unmatched_stations.append(dict(tag=tag, xy=[x, y], n_unmatched=int((res > tols[0]).sum()), max_residual_s=float(res.max())))
        min_gap = min(min_gap, float(np.diff(cd).min()))
        if status != "OK":
            bad.append(tag)
        sig = sorted(names[k] for k in pick)
        sigs.append(sig)
    changes = []
    for i in range(1, len(stations)):
        if sigs[i] is None or sigs[i - 1] is None:
            continue
        if sigs[i] != sigs[i - 1]:
            changes.append(dict(from_station=i - 1, to_station=i, xy=stations[i], **signature_diff(sigs[i - 1], sigs[i])))
    counts = sorted({len(s) for s in sigs if s is not None})
    if not stations:
        raise SystemExit(f"NO_STATIONS_FOUND in {args.timeline}: no row with phase in {DRIVE_PHASES} (an empty check must not pass)")
    rep = dict(stations=len(stations), missing_traces=missing, status_not_ok=bad, unmatched_paths_total={f"tol_{t:g}": v for t, v in unmatched_total.items()}, max_residual_s=max_res,
               min_gap_between_distinct_image_delays_s=min_gap, path_counts=counts,
               n_set_changes=len(changes), set_changes=changes, strict_unmatched_stations=strict_unmatched_stations, passed_strict_prereg_tol=bool(stations and not missing and not bad and unmatched_total[tols[0]] == 0),
               passed_relaxed_2e13=bool(stations and not missing and not bad and unmatched_total[tols[1]] == 0))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("stations", "unmatched_paths_total", "max_residual_s", "min_gap_between_distinct_image_delays_s", "path_counts", "n_set_changes", "passed_strict_prereg_tol", "passed_relaxed_2e13")}))


if __name__ == "__main__":
    main()
