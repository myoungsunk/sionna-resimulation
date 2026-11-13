"""Paired aligned sweep bias diagnostic for G1-MODEL-001 v3.3 §2.6."""
from __future__ import annotations

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import numpy as np

from run_step2 import CASES
from v33_baseline import M0_EXCLUDED, _train_group as train_m0_group
from v33_observation import (
    SEEDS,
    SIGMA_XY,
    TRAIN_SEED,
    ObservationCase,
    ObservationInputs,
    _train_group as train_m1_group,
    snap_xy,
)

REQUIRED_IMPROVED = 4
REQUIRED_REDUCTION = 0.30
NEGATIVE_TAIL_DEG = -5.0


def _group_errors(task):
    """Use each model's best aligned minimum for the same RF sweep and XY."""
    m0 = train_m0_group(task).winner_error
    m1 = train_m1_group(task).winner_error
    if m0.shape != m1.shape or not np.isfinite(m0).all() or not np.isfinite(m1).all():
        case, group, _ = task
        raise ValueError(f"Unpaired or nonfinite aligned sweep errors: {case.name}/{group}")
    return m0, m1


def summarize(errors_by_case):
    """Compute both case-equal reductions without treating RF seeds as stations."""
    cases = {}
    for name, (m0, m1) in errors_by_case.items():
        m0, m1 = np.asarray(m0), np.asarray(m1)
        if (m0.ndim != 1 or not m0.size or m0.shape != m1.shape
                or not np.isfinite(m0).all() or not np.isfinite(m1).all()):
            raise ValueError(f"Expected nonempty paired aligned errors for {name}")
        a, b = float(np.mean(m0)), float(np.mean(m1))
        abs_a, abs_b = abs(a), abs(b)
        cases[name] = {
            "paired_sweeps": int(m0.size),
            "M0": {"mean_signed_error_deg": a, "fraction_below_minus_5_deg": float(np.mean(m0 < NEGATIVE_TAIL_DEG))},
            "M1-R(J_joint)": {"mean_signed_error_deg": b, "fraction_below_minus_5_deg": float(np.mean(m1 < NEGATIVE_TAIL_DEG))},
            "absolute_bias_decreased": abs_b < abs_a,
            "relative_absolute_bias_reduction": None if abs_a == 0.0 else (abs_a - abs_b) / abs_a,
        }

    reductions = [case["relative_absolute_bias_reduction"] for case in cases.values()]
    abs_m0 = [abs(case["M0"]["mean_signed_error_deg"]) for case in cases.values()]
    abs_m1 = [abs(case["M1-R(J_joint)"]["mean_signed_error_deg"]) for case in cases.values()]
    mean_casewise = float(np.mean(reductions)) if None not in reductions else None
    mean_m0, mean_m1 = float(np.mean(abs_m0)), float(np.mean(abs_m1))
    reduction_in_mean = None if mean_m0 == 0.0 else (mean_m0 - mean_m1) / mean_m0
    improved = sum(case["absolute_bias_decreased"] for case in cases.values())
    if mean_casewise is None or reduction_in_mean is None:
        status = "UNDEFINED_BASELINE_DENOMINATOR"
    elif improved >= REQUIRED_IMPROVED and min(mean_casewise, reduction_in_mean) >= REQUIRED_REDUCTION:
        status = "SUPPORTS_OBSERVATION_MODEL_CONTRIBUTION"
    elif (mean_casewise >= REQUIRED_REDUCTION) != (reduction_in_mean >= REQUIRED_REDUCTION):
        status = "REDUCTION_INTERPRETATIONS_DISAGREE"
    else:
        status = "CRITERION_NOT_MET"
    return {
        "status": status,
        "supports_partial_d1_observation_model_contribution": status == "SUPPORTS_OBSERVATION_MODEL_CONTRIBUTION",
        "case_count": len(cases),
        "cases_with_reduced_absolute_bias": improved,
        "case_equal_mean_casewise_relative_reduction": mean_casewise,
        "case_equal_relative_reduction_of_mean_absolute_bias": reduction_in_mean,
        "case_equal_M0_mean_absolute_bias_deg": mean_m0,
        "case_equal_M1_R_mean_absolute_bias_deg": mean_m1,
        "minimum_improved_cases": REQUIRED_IMPROVED,
        "minimum_relative_reduction_both_definitions": REQUIRED_REDUCTION,
        "denominators": {
            "mean_casewise_relative_reduction": "Each case uses its own absolute M0 mean signed error. Average over all five common cases.",
            "relative_reduction_of_mean_absolute_bias": "Divide the difference of equal-case mean absolute biases by the equal-case M0 mean absolute bias.",
            "zero_baseline": "A zero baseline denominator is undefined; do not drop the case or claim support.",
            "negative_tail": "Within each case use the same paired valid sweeps as the mean signed errors.",
        },
        "cases": cases,
    }


def bias_check(root, banks, names=CASES, workers=1):
    """Compare the five common mount-0 cases using the frozen training XY stream."""
    names = tuple(sorted(names))
    if names != tuple(sorted(CASES)):
        raise ValueError("The §2.6 five-case comparison needs all six frozen case IDs for XY assignment")
    inputs = ObservationInputs(root, banks)
    rng = np.random.Generator(np.random.PCG64(TRAIN_SEED))
    tasks = []
    counts = {}
    for name in names:
        case = ObservationCase(inputs, name)
        groups = sorted(case.group_ids)
        offsets = rng.normal(0.0, SIGMA_XY, (len(groups), SEEDS, 2))
        if name in M0_EXCLUDED:
            continue
        evaluated, _, direct = snap_xy(offsets)
        tasks.extend((case, group, xy) for group, xy in zip(groups, evaluated))
        counts[name] = {
            "physical_stations": len(groups),
            "expected_sweeps": len(groups) * SEEDS,
            "direct_position_sweeps": int(direct.sum()),
        }

    grouped = {name: ([], []) for name in counts}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for (case, _, _), (m0, m1) in zip(tasks, pool.map(_group_errors, tasks), strict=True):
            grouped[case.name][0].append(m0)
            grouped[case.name][1].append(m1)
    report = summarize({name: tuple(map(np.concatenate, parts)) for name, parts in grouped.items()})
    for name, row in report["cases"].items():
        row.update(counts[name])
        row["invalid_sweeps"] = row["expected_sweeps"] - row["paired_sweeps"]
    report.update(
        observation_arms=["M0", "M1-R(J_joint)"],
        excluded_m0_parity=sorted(M0_EXCLUDED.intersection(names)),
        xy_seed=TRAIN_SEED,
        rf_seed_range=[0, SEEDS - 1],
        signed_error="wrap180(estimated heading - true heading)",
        negative_tail_threshold_deg=NEGATIVE_TAIL_DEG,
        aligned_truth_centered_half_width_deg=10.0,
        scope="Offline paired comparison on the fixed RF bank. No causal filtering or held-out calibration is fit here.",
    )
    return report


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--banks", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    report = bias_check(args.inputs, args.banks, workers=args.workers)
    with (args.out / "S1P_BIAS_CHECK.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
