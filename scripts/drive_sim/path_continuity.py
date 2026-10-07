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
from qclean_uwb.drivesim.paths import signature_diff  # noqa: E402
from qclean_uwb.drivesim.rf_store import tag_of  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", type=Path, required=True)
    ap.add_argument("--traces", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    stations, seen = [], set()
    for r in csv.DictReader(args.timeline.open()):
        key = (float(r["x"]), float(r["y"]))
        if r["phase"] in ("drive_out", "drive_back") and key not in seen:
            seen.add(key)
            stations.append(key)
    sigs, unmatched_total, missing, bad = [], 0, [], []
    for x, y in stations:
        tag = tag_of(x, y)
        p = next((d / f"{tag}_trace.npz" for d in args.traces if (d / f"{tag}_trace.npz").exists()), None)
        if p is None:
            missing.append(tag)
            sigs.append(None)
            continue
        with np.load(p) as z:
            sig, un, status = [str(s) for s in z["signature"]], int(z["unmatched"]), str(z["status"])
        unmatched_total += un
        if status != "OK":
            bad.append(tag)
        sigs.append(sig)
    changes = []
    for i in range(1, len(stations)):
        if sigs[i] is None or sigs[i - 1] is None:
            continue
        if sigs[i] != sigs[i - 1]:
            changes.append(dict(from_station=i - 1, to_station=i, xy=stations[i], **signature_diff(sigs[i - 1], sigs[i])))
    counts = sorted({len(s) for s in sigs if s is not None})
    rep = dict(stations=len(stations), missing_traces=missing, status_not_ok=bad, unmatched_paths_total=unmatched_total, path_counts=counts,
               n_set_changes=len(changes), set_changes=changes[:50], passed=bool(not missing and not bad and unmatched_total == 0))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("stations", "unmatched_paths_total", "path_counts", "n_set_changes", "passed")}))


if __name__ == "__main__":
    main()
