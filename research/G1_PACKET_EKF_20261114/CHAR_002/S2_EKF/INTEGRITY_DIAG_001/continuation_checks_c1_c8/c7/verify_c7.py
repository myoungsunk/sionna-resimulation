"""Independently reaggregate the C7 station proxy fit and compare its output hashes."""
from collections import defaultdict
from pathlib import Path
import csv
import hashlib
import json

import numpy as np


HERE = Path(__file__).resolve().parent


def digest(name):
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


def read(name):
    return json.loads((HERE / name).read_bytes())


def two_coefficient_nnls(matrix, y):
    # Enumerate all feasible active sets of the nonnegative two-coefficient model.
    solution = np.linalg.lstsq(matrix, y, rcond=None)[0]
    candidates = [np.zeros(2)]
    if np.all(solution >= 0.):
        candidates.append(solution)
    for i in range(2):
        coefficient = np.zeros(2)
        col = matrix[:, i]
        coefficient[i] = max(0., (col @ y) / (col @ col))
        candidates.append(coefficient)
    return min(candidates, key=lambda coeff: np.sum((matrix @ coeff - y) ** 2))


def validate():
    execution = read("EXECUTION_C7.json")
    assert execution["status"] == "PASS_EXECUTION"
    assert execution["contract_sha256"] == digest("RUN_CONTRACT_C7.json")
    assert execution["runner_sha256"] == digest("run_c7.py")
    for name, expected in execution["outputs"].items():
        assert digest(name) == expected
    stations = defaultdict(list)
    with (HERE / "C7_DONOR_ROWS.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            stations[row["role"], row["station"], row["anchor"]].append(row)
    assert len(stations) == 108
    assert all(len(rows) == 49 for rows in stations.values())
    support = []
    worst_smooth_delta = 0.
    for triple, rows in stations.items():
        yaw = np.asarray([float(r["relative_yaw_deg"]) for r in rows])
        raw = np.asarray([float(r["e_s"]) for r in rows])
        values, counts = [], []
        for yaw_i in yaw:
            window = raw[np.abs(yaw - yaw_i) <= 5. + 1e-10]
            values.append(float(np.mean(window)))
            counts.append(len(window))
        np.testing.assert_array_equal(counts, [int(r["window_n"]) for r in rows])
        assert min(counts) >= 3
        slow = np.asarray(values) - np.mean(values)
        actual = np.asarray([float(r["e_s_slow"]) for r in rows])
        np.testing.assert_allclose(slow, actual, rtol=0, atol=1e-12)
        worst_smooth_delta = max(worst_smooth_delta, float(np.max(np.abs(slow - actual))))
        support.extend(zip((triple,) * len(rows), rows, slow, strict=True))
    results = read("C7_RESULTS.json")
    worst_weighted_fit_delta = 0.
    for role, bins in results["fits"].items():
        for result in bins:
            low, high = result["distance_m"]
            groups = defaultdict(list)
            views = set()
            for (set_name, station, anchor), row, slow in support:
                if set_name == role and low <= float(row["d_xy_m"]) < high:
                    groups[station].append((float(row["g_per_rad"]), slow))
                    views.add((station, anchor))
            assert len(groups) == result["physical_stations"]
            assert len(views) == result["station_anchor_views"]
            assert sum(map(len, groups.values())) == result["yaw_centers"]
            matrices, targets = [], []
            for rows in groups.values():
                g, slow = np.asarray(rows).T
                matrices.extend((1 / np.sqrt(len(rows))) * np.column_stack([np.ones_like(g), g * g]))
                targets.extend(slow * slow / np.sqrt(len(rows)))
            fitted = two_coefficient_nnls(np.asarray(matrices), np.asarray(targets))
            np.testing.assert_allclose(fitted, result["beta"], rtol=1e-12, atol=1e-12)
            worst_weighted_fit_delta = max(worst_weighted_fit_delta, float(np.max(np.abs(fitted - result["beta"]))))
    return dict(status="PASS_REAGGREGATION", role="IMPLEMENTER_SELF_CHECK", verifier_sha256=digest("verify_c7.py"),
                execution_sha256=digest("EXECUTION_C7.json"), csv_rows=len(support), anchor_station_sweeps=len(stations),
                smoothed_residual_max_absolute_error=worst_smooth_delta,
                weighted_fit_max_absolute_error=worst_weighted_fit_delta, verified_receipted_outputs=len(execution["outputs"]))


if __name__ == "__main__":
    result = validate()
    with (HERE / "VERIFICATION_C7.json").open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write("\n")
