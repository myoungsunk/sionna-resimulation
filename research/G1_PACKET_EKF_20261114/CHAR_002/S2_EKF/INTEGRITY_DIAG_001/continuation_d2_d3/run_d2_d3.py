"""Continue the frozen G1 integrity diagnostics with D2, then D3."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PRIOR = PARENT / "attempt_02"
PUBLICATION = PARENT.parent.parent / "g1_int_diag001_publication_20261115"
FROZEN_SHA = "c5582baf48948a5a20a9c555c10ad708fd18326a27a5ad463f830f9c7b5333cc"
ROUTES = ("R2", "R4", "R5")
LOCK = HERE / "CONTINUATION_CONTRACT.json"
sys.path.insert(0, str(PARENT))
from d1_shuffle import dump, sha, verify_file


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def item(path):
    return {"path": str(path), "sha256": sha(path)}


def freeze():
    import d2
    import d3
    import m3

    prior_contract = PARENT / "RUN_CONTRACT.json"
    if sha(prior_contract) != FROZEN_SHA or sha(PRIOR / "RUN_CONTRACT.json") != FROZEN_SHA:
        raise ValueError("The frozen original design changed")
    base = read(prior_contract)
    for receipt in [base["provenance"]["original_plan"], base["provenance"]["amendment"], *base["governance"]]:
        verify_file(receipt)
    prior_files = [PRIOR / name for name in ("RESULTS.json", "VERIFICATION.json", "RETRY_RECEIPT.json",
                                            "d0/EXECUTION.json", "d5/EXECUTION.json", "d5/FOLDS.json")]
    checks = read(PRIOR / "VERIFICATION.json")
    balance = read(PRIOR / "RESULTS.json")
    if (checks["status"] != "PASS_REAGGREGATION" or checks["contract_sha256"] != FROZEN_SHA or
            checks["report_results_sha256"] != sha(PRIOR / "RESULTS.json") or balance["total_d1_replays"] != 4812):
        raise ValueError("The completed D0/D5/D1 prerequisite failed verification")
    for phase in ("d0", "d5"):
        if checks["d0_d5_execution_sha256"][phase] != sha(PRIOR / phase / "EXECUTION.json"):
            raise ValueError(f"Previous {phase} execution checksum does not match")
    rev = subprocess.check_output(["git", "-C", str(PUBLICATION), "rev-parse", "HEAD"], text=True).strip()
    if rev != "2c05da52684ac95fdabe5239c29b4c7a0a27c9b9":
        raise ValueError("Publication reference changed")
    source = [Path(module.__file__) for module in (d2, d3, m3)] + [Path(__file__), PARENT / "d0_d5.py",
             PARENT / "d1_shuffle.py", PARENT / "e0_batch.py"]
    lock = {"study": "G1-INT-DIAG-001", "role": "IMPLEMENTER", "classification": "DIAGNOSTIC_ONLY",
            "ordered_stages": ["D2", "D3"], "frozen_utc": now(), "prior_publication_commit": rev,
            "base_contract": item(prior_contract), "prerequisites": [item(path) for path in prior_files],
            "governance": base["governance"], "sources": [item(path) for path in source], "scope": base["scope"],
            "claim_scope": "fixed corridor/seed; B/B0 determines hypothesis and priority; L2 paired, A descriptive; no SC/KI execution or adoption",
            "D2": {"execution_config": d2.DEFAULTS,
                   "window_s": 20., "min_accepted": 30, "windows_total_min": 10, "windows_per_trajectory_min": 2,
                   "H2_spearman_support": .7, "H2_spearman_reject_below": .5, "sensitivity_acf_cap_seconds": 5.,
                   "lag_pair_rule": "accepted order; (1,2),(3,4),... up to floor(n/2), stop at first nonpositive pair; |Δt|≤5s pair filter for sensitivity",
                   "truth_z2": "all packets primary, accepted-only sensitivity; centered reference residual variance over accepted",
                   "H7": {"d1_xy_gain_min": .03, "d1_min_valid": 90, "numerical_transfer_tol_m": 1e-12,
                          "interpretation": "fixed-trajectory first-order XY response; D1 provides nonlinear replay evidence"}},
            "D3": {"half_seconds": 5., "half_distance_m": .25, "half_yaw_deg": 5., "min_window_packets": 10,
                   "target_heading95": .90, "target_cell": "B_B0_R4", "oracle_baseline": "original E0 hand sigma table and frozen per-case mask",
                   "route_mean": "mean of all finite pre-gate residuals; slow centered across supported packets; all edits preserve unsupported packets",
                   "physical_sensitivity": "retain oracle subtraction for the primary analysis; if any accepted B/B0 R4 s-arm observation is outside bounds, replay the three s arms on their common legal support with those edits reverted. A changed branch is inconclusive",
                   "block_bootstrap_s": [5, 10], "block_bootstrap_reps": 1500, "block_bootstrap_seed": 20261115},
            "M3": {**base["M3"], "status": "RUN_IN_D2_D3", "split": "B B0 two other donor routes per held-out route; do not use held-out samples in M1 fit or M3 registration",
                   "reference": "refilter each donor using the target fold D5 sigma table and original donor mask; prior endpoints from these predictions",
                   "motion": "sum of absolute encoder distance and wrapped pre-update E0 yaw increments; cumulative angle rad",
                   "variance_comparison": "D3 window recomputed on matched R_ref donor-motion support; q compared in same knot-distance bins"},
            "M1": {**base["M1"], "implemented_in_this_run": "joint fit required for M3 diagnostics and D3 matched-scale comparison only"}}
    dump(LOCK, lock)
    print(f"Frozen continuation: {sha(LOCK)}", flush=True)


def authenticate():
    lock = read(LOCK)
    for receipt in [lock["base_contract"], *lock["prerequisites"], *lock["sources"], *lock["governance"]]:
        verify_file(receipt)
    if lock["base_contract"]["sha256"] != FROZEN_SHA:
        raise ValueError("Wrong frozen parent")
    prior_contract = read(PARENT / "RUN_CONTRACT.json")
    for receipt in prior_contract["provenance"]["native_files"].values():
        verify_file(receipt)
    retry = read(PRIOR / "RETRY_RECEIPT.json")
    if sha(PARENT / "d0_d5.py") != retry["d0_d5_corrected_driver_sha256"]:
        raise ValueError("D0/D5 driver changed after retry")
    sys.path[:0] = [prior_contract["s2"], str(Path(prior_contract["native"]) / "src")]
    return lock, prior_contract


def load_cases(base, model):
    from d0_d5 import bind, key_for
    from replay_s2 import read_npz, validate_trace
    from qclean_uwb.fp_sc.e0_baseline import SPEC

    receipt = read(PRIOR / "d0" / "EXECUTION.json")
    cases = {}
    for cell in base["cells"]:
        key = key_for(cell)
        packet, truth = bind(cell)
        e0_path = PRIOR / "d0" / f"{key}.npz"
        verify_file({"path": str(e0_path), "sha256": receipt["outputs"][e0_path.name]})
        e0 = read_npz(e0_path)
        validate_trace(e0)
        for coordinate in ("t", "pose_id"):
            if not np.array_equal(e0[coordinate], packet[coordinate]):
                raise ValueError(f"D0 packet grid changed: {key}/{coordinate}")
        spec = dict(SPEC, anchor=tuple(base["anchors"][cell["anchor"]]))
        h, _ = model.batch(np.column_stack([truth, np.zeros(len(truth))]), spec, gradient=False)
        epsilon = packet["z"] - h - packet["muMB"]
        if not np.isfinite(epsilon).all():
            raise ValueError(f"Nonfinite evaluator residuals: {key}")
        cases[key] = {"packet": packet, "truth": truth, "spec": spec, "e0": e0, "eps": epsilon}
    if len(cases) != base["scope"]["n_expected"]:
        raise ValueError("Frozen cells missing or duplicated")
    return cases


def d2_fit_m3(cases, out, core, online, model):
    from d0_d5 import controls_for, replay_sigma
    from d3 import motion_arcs
    from m3 import fit_fold, prepare_donor
    from replay_s2 import validate_trace

    folds = read(PRIOR / "d5" / "FOLDS.json")
    by_fold = {}
    for target in ROUTES:
        donor_inputs = {}
        sigma = np.asarray(folds[target]["sigma_b"])
        for donor in (r for r in ROUTES if r != target):
            case = cases[f"B_B0_{donor}"]
            packet, spec, mask = case["packet"], case["spec"], case["e0"]["mask"]
            ref = replay_sigma(packet, controls_for(packet), mask, core, online, model, spec, sigma)
            validate_trace(ref)
            if not np.array_equal(mask, ref["mask"]):
                raise ValueError("M3 donor gate changed")
            arc, yaw = motion_arcs(packet, ref)
            file = out / f"M3_{target}_donor_{donor}.npz"
            np.savez_compressed(file, prior=ref["prior"], Reff=ref["Reff"], arc=arc, yaw=yaw,
                                t=packet["t"], pose_id=packet["pose_id"], mask=mask)
            donor_inputs[donor] = prepare_donor(packet, case["eps"], ref, spec["anchor"], arc, yaw)
        by_fold[target] = fit_fold(donor_inputs, fold=target)
        print(f"D2 M3 {target} fit complete", flush=True)
    dump(out / "M3_FITS_AND_PAIR_TABLES.json", by_fold)


def d3_m3_comparison(cases, d2_out, config):
    from d3 import decompose
    from m3 import compare_slow, prepare_donor
    from replay_s2 import read_npz

    fits = read(d2_out / "M3_FITS_AND_PAIR_TABLES.json")
    table = {}
    for target in ROUTES:
        donor_inputs, slow_by_route = {}, {}
        for donor in (r for r in ROUTES if r != target):
            case = cases[f"B_B0_{donor}"]
            packet = case["packet"]
            ref = read_npz(d2_out / f"M3_{target}_donor_{donor}.npz")
            if any(not np.array_equal(ref[k], packet[k]) for k in ("t", "pose_id")):
                raise ValueError(f"Misaligned D2 donor reference {target}/{donor}")
            arc, yaw = ref["arc"], ref["yaw"]
            donor_inputs[donor] = prepare_donor(packet, case["eps"], ref, case["spec"]["anchor"], arc, yaw)
            parts = decompose(case["eps"], packet["t"], arc, yaw, config)
            slow_by_route[donor] = (parts["slow"], parts["support"])
        table[target] = compare_slow(donor_inputs, fits[target], slow_by_route)
    return table


def run(stage):
    lock, base = authenticate()
    from qclean_uwb.fp_sc.e0_baseline import load_original_model

    root = LOCK.parent
    d2_out = root / "d2"
    if stage == "d3":
        d2_receipt = read(d2_out / "EXECUTION.json")
        if d2_receipt["exit_code"] != 0 or d2_receipt["continuation_contract_sha256"] != sha(LOCK):
            raise ValueError("D3 requires a successful D2 under this continuation contract")
        for name, expected in d2_receipt["outputs"].items():
            verify_file({"path": str(d2_out / name), "sha256": expected})
    out = root / stage
    out.mkdir(exist_ok=False)
    receipt = {"phase": f"G1-INT-DIAG-001/{stage.upper()}", "started_utc": now(), "command": sys.argv,
               "continuation_contract_sha256": sha(LOCK), "base_contract_sha256": FROZEN_SHA,
               "python": sys.version, "numpy": np.__version__}
    try:
        core, online, model, native = load_original_model(base["native"])
        receipt["native_source_hashes"] = native
        cases = load_cases(base, model)
        d1 = read(PRIOR / "RESULTS.json")
        if stage == "d2":
            import d2

            by_cell = {}
            for key, c in cases.items():
                arrays, by_cell[key] = d2.compute_case(c["packet"], c["truth"], c["e0"], c["eps"], core, online,
                                                     lock["D2"]["execution_config"])
                np.savez_compressed(out / f"{key}.npz", **arrays)
                print(f"D2 {key} complete", flush=True)
            s_only = d1["D1"]["by_cell"]["B_B0_R4"]["s_only"]
            gain = s_only["eligible"]["xy95_coverage"]["delta_from_e0"]
            aggregation = d2.aggregate(by_cell, gain, s_only["valid_reps"], lock["D2"]["execution_config"])
            d2_fit_m3(cases, out, core, online, model)
            result = {"by_cell": by_cell, "aggregate": aggregation, "M3_file": "M3_FITS_AND_PAIR_TABLES.json"}
        else:
            import d3

            by_cell = {}
            for key, c in cases.items():
                arrays, by_cell[key] = d3.compute_case(c, core, online, model, lock["D3"], primary=key == "B_B0_R4")
                np.savez_compressed(out / f"{key}.npz", **arrays)
                print(f"D3 {key} complete", flush=True)
            table = d3_m3_comparison(cases, d2_out, lock["D3"])
            dump(out / "M3_SLOW_SCALE_COMPARISON.json", table)
            result = {"by_cell": by_cell, "M3_file": "M3_SLOW_SCALE_COMPARISON.json"}
            result["decision"] = d3.priority(read(d2_out / "RESULTS.json"), result, d1, lock["D3"]["target_heading95"])
        dump(out / "RESULTS.json", result)
        receipt.update(exit_code=0, status="PASS_EXECUTION", cells=len(cases))
    except Exception as error:
        receipt.update(exit_code=1, status="FAIL_EXECUTION", error=str(error))
        raise
    finally:
        receipt.update(finished_utc=now(), outputs={p.name: sha(p) for p in out.iterdir() if p.is_file()})
        dump(out / "EXECUTION.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("freeze", "d2", "d3"))
    stage = parser.parse_args().stage
    freeze() if stage == "freeze" else run(stage)
