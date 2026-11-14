"""Recompute the diagnostic tables from downloaded sweep rows."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

folder = Path(sys.argv[1])
out = folder / "out"
for line in (folder/"SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
    checksum, filename = line.split("  ",1)
    if hashlib.sha256((folder/filename).read_bytes()).hexdigest() != checksum:
        raise ValueError(f"Checksum mismatch: {filename}")
summary = json.loads((out/"SUMMARY.json").read_text(encoding="utf-8"))
rows = list(csv.DictReader((out/"SWEEP_ROWS.csv").open(encoding="utf-8",newline="")))
station_rows = list(csv.DictReader((out/"STATION_ROWS.csv").open(encoding="utf-8",newline="")))
assert len(rows) == len({(r["case"],r["group"],r["seed"]) for r in rows}) == 2440
assert len(station_rows) == len({(r["case"],r["group"]) for r in rows}) == 122
assert summary["checks"]["q1_rows"] == 2440
assert summary["status"] == "DIAGNOSTIC_ONLY"
assert summary["frozen_s2_prime"] == "STOP" and summary["step_3"] == "HELD"
assert (folder/"EXIT.txt").read_text().strip() == "0"
assert set(summary["cases"]) == set(r["case"] for r in rows)
arms = ("detected","oracle","prior_frac")
all_stats = {}
for name, stats in summary["cases"].items():
    case_rows = [r for r in rows if r["case"] == name]
    subsets = {"whole":case_rows}
    if name == "R2_aA_m0":
        subsets["x_le_6_m"] = [r for r in case_rows if float(r["x_m"])<=6]
        subsets["x_ge_8_m"] = [r for r in case_rows if float(r["x_m"])>=8]
    case_features = {}
    for tag, subset in subsets.items():
        record = stats if tag == "whole" else stats[tag]
        paired = [r for r in subset if r["common_valid"] == "True"]
        assert len(paired) == record["n_paired"]
        assert len(subset) == record["n_sweep_slots"]
        assert len({r["group"] for r in subset}) == record["n_stations"]
        assert sum(r["fractional_window_edge"] == "True" for r in subset) == record["n_delay_edge"]
        group_ids = sorted({r["group"] for r in paired})
        arm_rows = {}
        for arm in arms:
            values = np.array([float(r[f"err_{arm}_deg"]) for r in paired])
            means = [values[np.array([r["group"] == group for r in paired])].mean() for group in group_ids]
            comparisons = {
                "rmse_deg": np.sqrt(values @ values / len(values)),
                "mean_signed_deg": values.mean(),
                "p95_abs_deg": np.quantile(abs(values), .95),
                "abs_gt5_fraction": np.mean(abs(values)>5),
                "station_mean_rms_deg": np.sqrt(np.mean(np.square(means))),
            }
            for metric, value in comparisons.items():
                np.testing.assert_allclose(value, record["arms"][arm][metric], atol=1e-12, rtol=1e-12)
            comparisons.update(n_heading_edge=record["arms"][arm]["n_heading_edge_all"])
            arm_rows[arm] = comparisons
        case_features[tag] = dict(paired=len(paired), delay_edge=record["n_delay_edge"], arms=arm_rows,
                                  n_sites=len(group_ids), rmse_delta=record["rmse_delta_deg"],
                                  fractional_minus_ref_median=float(np.median([float(r["fractional_minus_reference_m"]) for r in paired])))
    all_stats[name]=case_features
print(json.dumps({"check":"PASS", "n_paired":summary["n_paired"], "q1":summary["checks"],
                  "case_details":all_stats},ensure_ascii=False,indent=2))
