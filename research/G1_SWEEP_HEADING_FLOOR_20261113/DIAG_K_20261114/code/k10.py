"""G1-DIAG-002 K10 exploratory scale-threshold diagnostic on the fixed Q1 bank."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy
from scipy.special import gammainccinv


CASE_COUNTS = {
    "R2_aA_m0": 21, "R2_aB_m0": 21, "R4_aA_m0": 10,
    "R4_aB_m0": 10, "R5_aA_m0": 30, "R5_aB_m0": 30,
}
SEED = 2026111401
ORDERS_PER_CASE = 200
SWEEP_SEEDS = set(range(20))
A0, B0 = 3.0, 2.0
THRESHOLD = 1.5
Q1_SHA256 = "ede1a041dc275a57ca49751257d5c264f861a147e58b42166e0d737902111c3e"
K4_SHA256 = "2c8a7607fc16a2eab5160e046334f94f635f70617d8646f9de7cad71ebeb2c1a"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checked_bytes(path, expected):
    data = path.read_bytes()
    if sha256(data) != expected:
        raise ValueError(f"Frozen input checksum mismatch: {path}")
    return data


def station_scores(q1_data, k4):
    groups_by_case = {case: {} for case in CASE_COUNTS}
    for row in csv.DictReader(io.StringIO(q1_data.decode("utf-8-sig"), newline="")):
        case = row["case"]
        if case not in groups_by_case:
            raise ValueError(f"Unexpected Q1 case: {case}")
        group, seed = int(row["group"]), int(row["seed"])
        sweeps = groups_by_case[case].setdefault(group, {})
        if seed in sweeps:
            raise ValueError(f"Duplicate Q1 sweep: {case}/{group}/{seed}")
        error, variance = float(row["err"]), float(row["r_e1"])
        if not np.isfinite([error, variance]).all() or variance <= 0:
            raise ValueError(f"Invalid Q1 error or variance: {case}/{group}/{seed}")
        sweeps[seed] = error, variance
    k4_cases = {row["case"]: row for row in k4["oracle_parameters"]}
    if set(k4_cases) != set(CASE_COUNTS) or len(k4["oracle_parameters"]) != len(CASE_COUNTS):
        raise ValueError("Unexpected case keys in the published K4 result")
    if any(k4.get(k) != expected for k, expected in (
        ("classification", "DIAGNOSTIC_ONLY"), ("s2_prime_verdict", "STOP"),
        ("step3", "HELD"), ("q1_sha256", Q1_SHA256),
    )):
        raise ValueError("Unexpected K4 provenance")
    scores = {}
    for case, count in CASE_COUNTS.items():
        sites = groups_by_case[case]
        if len(sites) != count or any(set(v) != SWEEP_SEEDS for v in sites.values()):
            raise ValueError(f"Unexpected physical station or sweep inventory: {case}")
        ids = sorted(sites)
        z2 = []
        for group in ids:
            values = np.asarray([sites[group][seed] for seed in sorted(SWEEP_SEEDS)])
            z2.append((np.mean(values[:, 0]) / np.mean(np.sqrt(values[:, 1]))) ** 2)
        z2 = np.asarray(z2, dtype=np.float64)
        prior = k4_cases[case]
        if prior["sites"] != count or prior["sweeps"] != count * len(SWEEP_SEEDS):
            raise ValueError(f"K4 inventory mismatch: {case}")
        np.testing.assert_allclose(z2.mean(), prior["kappa"], rtol=1e-13, atol=1e-13,
                                   err_msg=f"K4 scale mismatch for {case}")
        scores[case] = ids, z2
    return scores


def posterior_medians(ordered_z2):
    visits = np.arange(1, ordered_z2.shape[1] + 1)
    shape = A0 + 0.5 * visits
    scale = B0 + 0.5 * np.cumsum(ordered_z2, axis=1)
    return scale / gammainccinv(shape, 0.5)


def summarize_threshold(medians):
    n_orders, horizon = medians.shape
    exceeded = medians > THRESHOLD
    observed = exceeded.any(axis=1)
    first = np.where(observed, exceeded.argmax(axis=1) + 1, 0)
    hits = np.bincount(first, minlength=horizon + 1)
    cumulative = np.cumsum(hits[1:])
    median_hits = np.flatnonzero(2 * cumulative >= n_orders)
    median_visit = int(median_hits[0] + 1) if median_hits.size else None
    by_10 = int(cumulative[9]) if horizon >= 10 else None
    by_end = int(observed.sum())
    return {
        "orders": n_orders,
        "supported_distinct_visits": horizon,
        "first_hit_counts_by_visit": hits[1:].tolist(),
        "cumulative_first_hit_fractions_by_visit": (cumulative / n_orders).tolist(),
        "first_hit_visit_by_order": [int(i) if i else None for i in first],
        "orders_crossed_by_10": by_10,
        "fraction_crossed_by_10": by_10 / n_orders if by_10 is not None else None,
        "orders_crossed_by_end": by_end,
        "fraction_crossed_by_end": by_end / n_orders,
        "orders_right_censored_at_end": n_orders - by_end,
        "median_first_hit_visit": median_visit,
        "median_first_hit_status": "OBSERVED" if median_visit is not None else "RIGHT_CENSORED",
        "median_first_hit_lower_bound_exclusive": None if median_visit is not None else horizon,
        "terminal_posterior_median_kappa": float(np.median(medians[:, -1])),
    }


def calculate(q1_path, k4_path):
    q1 = checked_bytes(q1_path, Q1_SHA256)
    k4 = json.loads(checked_bytes(k4_path, K4_SHA256))
    scores = station_scores(q1, k4)
    rng = np.random.default_rng(SEED)
    results = {}
    for case, (ids, z2) in scores.items():
        perms = np.stack([rng.permutation(len(ids)) for _ in range(ORDERS_PER_CASE)])
        np.testing.assert_array_equal(np.sort(perms, axis=1),
                                      np.broadcast_to(np.arange(len(ids)), perms.shape))
        medians = posterior_medians(z2[perms])
        if not np.isfinite(medians).all():
            raise ValueError(f"Nonfinite posterior medians: {case}")
        np.testing.assert_allclose(medians[:, -1], medians[0, -1], rtol=1e-13, atol=1e-13)
        result = summarize_threshold(medians)
        result.update(station_ids=ids, station_z2=z2.tolist(), k4_mean_z2=float(z2.mean()),
                      rng_order_index_sha256=sha256(perms.astype("<i4").tobytes()))
        results[case] = result

    return {
        "question_id": "G1-DIAG-002",
        "diagnostic": "K10",
        "classification": "DIAGNOSTIC_ONLY",
        "analysis_status": "EXPLORATORY",
        "s2_prime_verdict": "STOP",
        "step3": "HELD",
        "source_spec_commit": "2068954c07770cffee1a8745e53e0383c5ef8c96",
        "k4_publication_commit": "b070c8685e03133cfe4b846b530181acf66260b8",
        "q1_commit": "42fe9c7",
        "inputs": {"q1_sweep_rows_sha256": Q1_SHA256, "k4_oracle_scale_sha256": K4_SHA256},
        "driver_sha256": sha256(Path(__file__).read_bytes()),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "argv": sys.argv,
        "seed": SEED,
        "permutation_protocol": (
            "PCG64 via default_rng(seed), one stream advanced case-major in output case order. "
            "Each order uniformly permutes sorted physical group IDs, once each. "
            "Indices are zero-based, serialized as little-endian int32 for the per-case order SHA-256."
        ),
        "orders_per_case": ORDERS_PER_CASE,
        "station_statistic": "z_s^2 = (mean_seed(error_deg) / mean_seed(sqrt(R_E1)))^2, same as K4",
        "prior": {"family": "inverse-gamma", "shape": A0, "scale": B0},
        "posterior": "InvGamma(a0 + N/2, b0 + sum(z_s^2)/2)",
        "threshold_kappa": THRESHOLD,
        "crossing_rule": "First observed distinct visit at which the posterior median is strictly > 1.5.",
        "censoring_rule": "No hit by station inventory end is right-censored. Median first-hit visit is the earliest visit with at least half of all orders crossing.",
        "interpretation": (
            "First-hit fractions describe order sensitivity conditional on the observed station bank. "
            "Other-case hit fractions are descriptive and baseline null truth is unknown. "
            "Threshold crossing is an exploratory event, whose persistence and operational reliability are unassessed."
        ),
        "cases": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--q1", type=Path, required=True)
    parser.add_argument("--k4", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = calculate(args.q1, args.k4)
    with args.out.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    print("K10 EXPLORATORY", {case: row["orders_crossed_by_end"]
                              for case, row in result["cases"].items()}, flush=True)


if __name__ == "__main__":
    main()
