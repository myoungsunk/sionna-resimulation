"""Recheck D2/D3 receipts and recompute D3 scores from the saved state traces."""

from pathlib import Path

import numpy as np

from run_d2_d3 import HERE, LOCK, PRIOR, authenticate, dump, read, sha, verify_file


def run():
    lock, base = authenticate()
    from d0_d5 import compare, key_for
    from replay_s2 import read_npz
    from verify_s2 import check_metric_rows, from_trace
    import d2
    import d3

    stages, receipts = {}, {}
    contract_hash = sha(LOCK)
    ids = {key_for(c) for c in base["cells"]}
    for stage in ("d2", "d3"):
        directory = HERE / stage
        receipt = read(directory / "EXECUTION.json")
        if (receipt["continuation_contract_sha256"] != contract_hash or receipt["exit_code"] != 0 or
                receipt["status"] != "PASS_EXECUTION" or receipt["cells"] != len(ids)):
            raise ValueError(f"Invalid phase receipt {stage}")
        for filename, digest in receipt["outputs"].items():
            verify_file({"path": str(directory / filename), "sha256": digest})
        receipts[stage] = receipt
        stages[stage] = read(directory / "RESULTS.json")
        if set(stages[stage]["by_cell"]) != ids:
            raise ValueError(f"Incomplete cases for {stage}")
    if receipts["d2"]["finished_utc"] >= receipts["d3"]["started_utc"]:
        raise ValueError("D3 began before D2 finished")
    d1 = read(PRIOR / "RESULTS.json")
    r4_prior = d1["D1"]["by_cell"]["B_B0_R4"]["s_only"]
    gain = r4_prior["eligible"]["xy95_coverage"]["delta_from_e0"]
    agg = d2.aggregate(stages["d2"]["by_cell"], gain, r4_prior["valid_reps"], lock["D2"]["execution_config"])
    if agg != stages["d2"]["aggregate"]:
        raise ValueError("D2 aggregate differs")
    decision = d3.priority(stages["d2"], stages["d3"], d1, lock["D3"]["target_heading95"])
    if decision != stages["d3"]["decision"]:
        raise ValueError("D3 priority differs")

    scores_checked = 0
    parity_error, reconstruction_error = 0., 0.
    primary_paired_contrast = None
    for cell in base["cells"]:
        key = key_for(cell)
        evaluator = read_npz(verify_file(cell["evaluator"]))
        p2 = read_npz(HERE / "d2" / f"{key}.npz")
        p3 = read_npz(HERE / "d3" / f"{key}.npz")
        for k in ("t", "pose_id", "mask"):
            if not np.array_equal(p2[k], p3[k]) or (k in evaluator and not np.array_equal(p3[k], evaluator[k])):
                raise ValueError(f"D2 and D3 packet support differs for {key}/{k}")
        if not np.array_equal(p2["truth_residual_r_s"], p3["eps"]):
            raise ValueError(f"D2 and D3 residuals differ for {key}")
        summary = stages["d3"]["by_cell"][key]
        parity_error = max(parity_error, *(v["max_normalized_error"] for v in summary["original_parity"].values()))
        keep = p3["decomposition_support"]
        error = p3["eps"][keep] - (p3["route_mean"] + p3["slow"][keep] + p3["fast"][keep])
        reconstruction_error = max(reconstruction_error, np.max(np.abs(error)))
        if len(p3["arm_names"]) != 10 or set(p3["arm_names"]) != set(summary["arms"]):
            raise ValueError(f"Missing D3 interventions for {key}")
        arm_rows = {}
        for i, arm in enumerate(p3["arm_names"]):
            states = {state: p3[state][i] for state in ("x", "P")}
            arm_rows[arm] = from_trace(states, evaluator["truth"])
            check_metric_rows(arm_rows[arm], summary["arms"][arm])
            scores_checked += 1
        if key == "B_B0_R4":
            contrast = compare([{"time": p3["t"], "e0": arm_rows["fast_s"], "loro": arm_rows["slow_s"]}])
            primary_paired_contrast = {"delta": contrast["loro_minus_e0"], "paired_95": contrast["moving_block_bootstrap_paired"]}
    if max(parity_error, reconstruction_error) > 1e-10:
        raise ValueError("D3 parity or residual reconstruction exceeds tolerance")

    fits = read(HERE / "d2" / "M3_FITS_AND_PAIR_TABLES.json")
    differences = read(HERE / "d3" / "M3_SLOW_SCALE_COMPARISON.json")
    if set(fits) != {"R2", "R4", "R5"} or set(fits) != set(differences):
        raise ValueError("M3 folds incomplete")
    candidates = 0
    for fold, result in fits.items():
        donors = set(fits) - {fold}
        if (set(result["donor_routes"]) != donors or set(differences[fold]) != donors or
                set(result["fits"]) != {"r", "s"}):
            raise ValueError(f"M3 holdout mismatch {fold}")
        candidates += len(result["position_kernel_candidates"])
        for donor in donors:
            n = stages["d2"]["by_cell"][f"B_B0_{donor}"]["packets"]
            for channel, row in result["donor_diagnostics"][donor]["by_channel"].items():
                bins = [row[slice_name] for slice_name in ("le_10_s", "gt_10_s")]
                if sum(b["n_pairs"] for b in bins) != n*(n-1)//2:
                    raise ValueError(f"M3 not all donor pairs counted for {fold}/{donor}/{channel}")
                for b in bins:
                    if sum(r["n_pairs"] for r in b["position_bins"]) != b["n_pairs"]:
                        raise ValueError(f"M3 incomplete position binning for {fold}/{donor}/{channel}")
    result = {"classification": "DIAGNOSTIC_ONLY", "D2": agg, "D3_priority": decision,
              "D3_slow_minus_fast_paired": primary_paired_contrast,
              "M3_candidate_rows": candidates, "reaggregated_D3_scores": scores_checked}
    dump(HERE / "RESULTS.json", result)
    dump(HERE / "VERIFICATION.json", {"status": "PASS_REAGGREGATION", "role": "IMPLEMENTER_SELF_CHECK",
                                   "continuation_contract_sha256": contract_hash,
                                   "output_checks": {p: sha(HERE / p / "EXECUTION.json") for p in receipts},
                                   "results_sha256": sha(HERE / "RESULTS.json"), "score_cases": scores_checked,
                                   "identity_max_normalized_error": parity_error,
                                   "residual_reconstruction_max_absolute_error": float(reconstruction_error),
                                   "verifier_sha256": sha(Path(__file__))})


if __name__ == "__main__":
    run()
