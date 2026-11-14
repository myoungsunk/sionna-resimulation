"""Verify run receipts and recompute the diagnostic statistics from sweep rows."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

folder = Path(sys.argv[1])
frozen_folder = Path(sys.argv[2])
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
arms = ("detected", "oracle", "prior_frac", "prior_direct")
old = json.loads((frozen_folder/"out"/"SUMMARY.json").read_bytes())
assert summary["case_channel_pose_sha256"] == old["case_channel_pose_sha256"]
assert summary["shared_noisy_full_h_sha256"] == old["shared_noisy_full_h_sha256"]
assert summary["checks"]["frozen_three_arm_rows"] == len(rows)
assert 0 <= summary["checks"]["q1_max_abs"] <= 1e-12
for a in summary["cases"]:
    assert summary["checks"][a]["prior_direct"] <= 1e-9
by_key = {(r["case"],r["group"],r["seed"]): r for r in rows}
with (frozen_folder/"out"/"SWEEP_ROWS.csv").open(encoding="utf-8", newline="") as handle:
    for frozen in csv.DictReader(handle):
        cur = by_key.pop((frozen["case"], frozen["group"], frozen["seed"]))
        for arm in arms[:3]:
            p = float(cur[f"err_{arm}_deg"])
            ref = float(frozen[f"err_{arm}_deg"])
            np.testing.assert_allclose(p, ref, atol=1e-12, rtol=0.)
            for field in ("heading_edge", "valid_yaws"):
                assert cur[f"{field}_{arm}"] == frozen[f"{field}_{arm}"]
assert not by_key
assert sum(r["common_valid"] == "True" for r in rows) == summary["n_paired"]
for r in rows:
    assert (r["common_valid"] == "True") == all(np.isfinite(float(r[f"err_{a}_deg"])) for a in arms)
    valid = int(r["valid_yaws_detected"])
    for prefix in ("prior_direct", "geometry_nominal"):
        assert sum(int(r[f"{prefix}_oracle_{kind}_yaws"]) for kind in ("match", "early", "late")) == valid
    assert int(r["prior_direct_minus_nominal_taps"]) == int(r["prior_direct_index"]) - int(r["geometry_nominal_index"])
rng = np.random.default_rng(2026111403)
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
        group_ids = sorted({int(r["group"]) for r in paired})
        by_station = {g: [r for r in paired if int(r["group"]) == g] for g in group_ids}
        draw = rng.integers(0, len(group_ids), (2000, len(group_ids)))
        boot_counts = np.array([len(by_station[g]) for g in group_ids])[draw].sum(axis=1)
        boot_rmse = {}
        arm_rows = {}
        for arm in arms:
            values = np.array([float(r[f"err_{arm}_deg"]) for r in paired])
            means = [values[np.array([int(r["group"]) == group for r in paired])].mean() for group in group_ids]
            comparisons = {
                "rmse_deg": np.sqrt(values @ values / len(values)),
                "mean_signed_deg": values.mean(),
                "p95_abs_deg": np.quantile(abs(values), .95),
                "abs_gt5_fraction": np.mean(abs(values)>5),
                "station_mean_rms_deg": np.sqrt(np.mean(np.square(means))),
            }
            for metric, value in comparisons.items():
                np.testing.assert_allclose(value, record["arms"][arm][metric], atol=1e-12, rtol=1e-12)
            edge = sum(r[f"heading_edge_{arm}"] == "True" for r in subset)
            assert edge == record["arms"][arm]["n_heading_edge_all"]
            assert sum(np.isfinite(float(r[f"err_{arm}_deg"])) for r in subset) == record["arms"][arm]["n_valid"]
            comparisons["n_heading_edge"] = edge
            arm_rows[arm] = comparisons
            station_squared = np.array([
                sum(float(r[f"err_{arm}_deg"])**2 for r in by_station[g]) for g in group_ids
            ])
            boot_rmse[arm] = np.sqrt(station_squared[draw].sum(axis=1) / boot_counts)
        for pair, contrast in record["rmse_delta_deg"].items():
            a, b = pair.split("_minus_")
            np.testing.assert_allclose(arm_rows[a]["rmse_deg"]-arm_rows[b]["rmse_deg"],
                                       contrast["paired_delta"], atol=1e-12, rtol=1e-12)
            np.testing.assert_allclose(np.percentile(boot_rmse[a]-boot_rmse[b], [2.5, 97.5]),
                                       contrast["percentile95"], atol=1e-12, rtol=1e-12)
        for field, total in record["tap_counts"].items():
            if field == "detector_valid_yaws":
                recomputed = sum(int(r["valid_yaws_detected"]) for r in subset)
            elif field == "prior_differs_from_nominal_sweeps":
                recomputed = sum(int(r["prior_direct_minus_nominal_taps"]) != 0 for r in subset)
            else:
                recomputed = sum(int(r[field]) for r in subset)
            assert recomputed == total
        case_features[tag] = dict(paired=len(paired), delay_edge=record["n_delay_edge"], arms=arm_rows,
                                  n_sites=len(group_ids), rmse_delta=record["rmse_delta_deg"], tap_counts=record["tap_counts"],
                                  fractional_minus_ref_median=float(np.median([float(r["fractional_minus_reference_m"]) for r in paired])))
    all_stats[name]=case_features
verified = {"check": "PASS", "status": "DIAGNOSTIC_ONLY", "frozen_s2_prime": "STOP", "step_3": "HELD",
            "n_paired": summary["n_paired"], "checks": summary["checks"], "case_details": all_stats}
(folder/"VERIFIED.json").write_text(json.dumps(verified, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(f"PASS: receipt, {len(rows)} unique sweeps, frozen controls, paired metrics and station bootstrap")
