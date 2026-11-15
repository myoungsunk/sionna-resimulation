"""Run the frozen G1-INT-001 B/B0 comparison of SC and KI."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
DIAG = PARENT / "continuation_d2_d3"
PREVIOUS = PARENT / "attempt_02"
PUBLICATION = PARENT.parent.parent / "g1_int_diag001_publication_20261115"
LOCK = HERE / "RUN_CONTRACT.json"
BASE_SHA = "c5582baf48948a5a20a9c555c10ad708fd18326a27a5ad463f830f9c7b5333cc"
DIAG_SHA = "473aecc118a579c581333258cf06806db5dba0e0c9710f93e83d2ebf9cea9083"
DIAG_COMMIT = "0de38786d295f8f179a54e8b603a19c93dd72683"
ROUTES = ("R2", "R4", "R5")
ARMS = ("SC", "KI")
IDENTITY_KEYS = ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S", "sigma_b", "rho_before", "mask")

sys.path.insert(0, str(PARENT))
from d1_shuffle import dump, sha, verify_file


def utc():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def item(path):
    return {"path": str(path), "sha256": sha(path)}


def checked_output(directory, receipt, name):
    return verify_file({"path": str(directory / name), "sha256": receipt["outputs"][name]})


def freeze():
    base_path = PARENT / "RUN_CONTRACT.json"
    diag_path = DIAG / "CONTINUATION_CONTRACT.json"
    if sha(base_path) != BASE_SHA or sha(diag_path) != DIAG_SHA:
        raise ValueError("Prior frozen contracts changed")
    base = read(base_path)
    prev_check = read(PREVIOUS / "VERIFICATION.json")
    diag_check = read(DIAG / "VERIFICATION.json")
    if (prev_check["status"] != "PASS_REAGGREGATION" or prev_check["contract_sha256"] != BASE_SHA or
            diag_check["status"] != "PASS_REAGGREGATION" or diag_check["continuation_contract_sha256"] != DIAG_SHA):
        raise ValueError("Diagnostic prerequisites incomplete")
    records = {
        "d0": PREVIOUS / "d0" / "EXECUTION.json", "d5": PREVIOUS / "d5" / "EXECUTION.json",
        "d2": DIAG / "d2" / "EXECUTION.json", "d3": DIAG / "d3" / "EXECUTION.json"}
    for key, path in records.items():
        digest = (prev_check["d0_d5_execution_sha256"] if key in ("d0", "d5") else diag_check["output_checks"])[key]
        if sha(path) != digest or read(path)["exit_code"] != 0:
            raise ValueError(f"Invalid prerequisite receipt: {key}")
    fit_path = checked_output(records["d2"].parent, read(records["d2"]), "M3_FITS_AND_PAIR_TABLES.json")
    sigma_path = checked_output(records["d5"].parent, read(records["d5"]), "FOLDS.json")
    fits, sigmas = read(fit_path), read(sigma_path)
    revision = subprocess.check_output(["git", "-C", str(PUBLICATION), "rev-parse", "HEAD"], text=True).strip()
    if revision != DIAG_COMMIT:
        raise ValueError("Pinned D2/D3 publication checkout differs")
    cells = [c for c in base["cells"] if c["anchor"] == "B" and c["bias"] == "B0"]
    if tuple(c["route"] for c in cells) != ROUTES:
        raise ValueError("Frozen B/B0 cells missing or out of order")
    prerequisites = [base_path, diag_path, PREVIOUS / "VERIFICATION.json", DIAG / "VERIFICATION.json",
                     DIAG / "RESULTS.json", fit_path, sigma_path, *records.values()]
    for cell in cells:
        route = cell["route"]
        name = f"B_B0_{route}.npz"
        required_donors = set(ROUTES) - {route}
        fit, sigma = fits[route], sigmas[route]
        if (fit["held_out_route"] != route or set(fit["donor_routes"]) != required_donors or
                set(sigma["donor_routes"]) != required_donors or set(fit["fits"]) != {"r", "s"} or
                fit["q_knots_m"] != base["M1"]["q_knots_m"]):
            raise ValueError(f"Donor provenance inconsistent for {route}")
        if (len(sigma["sigma_b"]) != len(fit["q_knots_m"]) or min(sigma["sigma_b"]) <= 0 or
                not np.isfinite(sigma["sigma_b"]).all()):
            raise ValueError(f"Invalid frozen LORO table for {route}")
        for channel, model in fit["fits"].items():
            q = np.asarray(model["q_knots"])
            if (q.shape != (len(fit["q_knots_m"]),) or not np.isfinite(q).all() or
                    np.any(q < 0) or np.any(q > 1) or model["ell_m"] not in base["M1"]["ell_d_m"] or
                    model["ell_deg"] not in base["M1"]["ell_psi_deg"]):
                raise ValueError(f"Invalid frozen M1 q or lengths for {route}/{channel}")
        cell["fixed_gate_trace"] = item(checked_output(records["d0"].parent, read(records["d0"]), name))
        cell["loro_trace"] = item(checked_output(records["d5"].parent, read(records["d5"]), name))
        for key in ("online", "evaluator", "archive_trace"):
            verify_file(cell[key])
        cell["donors"] = sorted(required_donors)
        cell["sigma_b"] = sigma["sigma_b"]
        cell["kernel"] = {"q_knots_m": fit["q_knots_m"], "fits": {
            c: {k: model[k] for k in ("q_knots", "ell_m", "ell_deg")} for c, model in fit["fits"].items()}}

    code = [Path(__file__), HERE / "structure.py", HERE / "score_structure.py",
            PARENT / "d0_d5.py", PARENT / "d1_shuffle.py"]
    retry = read(PREVIOUS / "RETRY_RECEIPT.json")
    if sha(PARENT / "d0_d5.py") != retry["d0_d5_corrected_driver_sha256"]:
        raise ValueError("Reusable scoring and parity driver changed")
    for entry in base["governance"]:
        verify_file(entry)
    lock = {"study": "G1-INT-001", "role": "IMPLEMENTER", "frozen_utc": utc(), "prior_publication_commit": revision,
            "arms_in_order": list(ARMS), "baseline": "E0-LORO-sigma_b", "original_e0_reference": True,
            "scope": {"anchor": "B", "bias": "B0", "routes": list(ROUTES), "seed": 10, "mount_deg": 0., "rf": "Full"},
            "cells": cells, "sources": [item(p) for p in code], "governance": base["governance"],
            "prerequisites": [item(p) for p in prerequisites], "frozen_m1_fit": item(fit_path),
            "frozen_loro_fit": item(sigma_path), "model_assets": base["provenance"]["native_files"],
            "s2_sources": [r for r in base["provenance"]["code"] if Path(r["path"]).parent == Path(base["s2"])],
            "motion": "native transition, Q, x0, P0; each arm's wrapped premeasurement yaw increment and absolute encoder travel",
            "observation": "native SourceFFD h,H plus frozen muMB of both channels; no evaluator inside recursion",
            "gate": "bitwise per-packet D0 mask, as used by E0-LORO; rejects predict-only",
            "noise": {"R_ref_lookup": "LORO sigma at its arm's previous posterior distance, fixed BASE R",
                      "q_lookup": "linear q knots and endpoint values at its arm's current prior horizontal distance",
                      "white_floor_fraction": .05, "independent_thermal_component": "not separately identified",
                      "shared_marginal": "R_white + D D^T = R_ref; q_eff = min(q,0.95)"},
            "SC": {"initial_latent_covariance": "I_2", "initial_cross_covariance": "0",
                   "latent_gain_and_mean": "zero", "update": "augmented Joseph", "latent_phi": "exponential of negative cumulative motion increments"},
            "KI": {"max_age_s_inclusive": 10., "max_accepted_history": 100, "current_observation_excluded": True,
                   "k": "1 + 2 sum sqrt(q_eff,k q_eff,j) exp(-delta_arc/ell_d-delta_yaw_arc/ell_psi)",
                   "score_time_segments_s": [[0., 10.], [10., None]]},
            "M2_thresholds": base["M2"], "score": {"all_packets": True, "block_lengths_s": [5, 10],
                   "paired_bootstrap_replicates": 1500, "paired_bootstrap_seed": 20261115,
                   "candidate_tie_within_absolute_rmse_ratio": .01, "candidate_tie_order": ["KI", "SC"]},
            "implementation_gates": {"parity_tolerance": 1e-10, "sc_switches": ["q_zero", "phi_zero"],
                   "ki_switches": ["empty_history"], "synthetic_common_bias_floor": True,
                   "golden_comparator": "frozen D5 E0-LORO full trace on all 3 trajectories"},
            "boundary": "route-direct LORO of new sigma and correlation parameters; frozen upstream mean corrections, single seed and corridor; no tuning from evaluation errors"}
    dump(LOCK, lock)
    print(f"Frozen G1-INT-001: {sha(LOCK)}", flush=True)


def authenticate(lock_path=LOCK):
    lock = read(lock_path)
    required = lock["sources"] + lock["s2_sources"] + lock["governance"] + lock["prerequisites"] + list(lock["model_assets"].values())
    for receipt in required:
        verify_file(receipt)
    for cell in lock["cells"]:
        for key in ("online", "evaluator", "fixed_gate_trace", "loro_trace"):
            verify_file(cell[key])
    base_path = PARENT / "RUN_CONTRACT.json"
    if sha(base_path) != BASE_SHA:
        raise ValueError("Base contract no longer the frozen parent")
    base = read(base_path)
    if lock["M2_thresholds"] != base["M2"]:
        raise ValueError("Acceptance thresholds changed")
    sys.path[:0] = [base["s2"], str(Path(base["native"]) / "src")]
    return lock, base


def cases_from(lock):
    from d0_d5 import controls_for
    from replay_s2 import read_npz, validate_trace
    from qclean_uwb.fp_sc.e0_baseline import SPEC

    cases = {}
    for cell in lock["cells"]:
        route = cell["route"]
        packet = read_npz(cell["online"]["path"])
        e0 = read_npz(cell["fixed_gate_trace"]["path"])
        loro = read_npz(cell["loro_trace"]["path"])
        if any(not np.array_equal(packet[k], other[k]) for other in (e0, loro) for k in ("t", "pose_id")):
            raise ValueError(f"Reference grid mismatch in {route}")
        if e0["mask"].dtype.kind != "b" or not np.array_equal(e0["mask"], loro["mask"]):
            raise ValueError(f"E0 and E0-LORO gate mismatch in {route}")
        for trace in (e0, loro):
            validate_trace(trace)
        if np.any(packet["R"][:, [0, 1], [1, 0]] != 0.):
            raise ValueError(f"Frozen B/B0 base covariance unexpectedly nondiagonal in {route}")
        cases[route] = dict(packet=packet, controls=controls_for(packet), mask=e0["mask"], spec=SPEC,
                            loro=loro, table=np.asarray(cell["sigma_b"]), fit=cell["kernel"])
    return cases


def execute(lock_path, out):
    lock, base = authenticate(lock_path)
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from replay_s2 import parity
    from structure import replay_structure, synthetic_checks
    from score_structure import recheck_trace, score

    out.mkdir(exist_ok=False)
    receipt = {"study": lock["study"], "started_utc": utc(), "command": sys.argv,
               "contract_sha256": sha(lock_path), "python": sys.version, "numpy": np.__version__}
    try:
        checks = {"synthetic": synthetic_checks(), "identity": {}, "scored_trace": {}}
        core, online, model, sources = load_original_model(base["native"])
        receipt["native_hashes"] = sources
        cases = cases_from(lock)
        for arm in lock["arms_in_order"]:
            checks["identity"][arm] = {}
            checks["scored_trace"][arm] = {}
            for route, case in cases.items():
                args = (case["packet"], case["controls"], case["mask"], core, online, model, case["spec"], case["table"], case["fit"])
                errors = {}
                for switch in lock["implementation_gates"][f"{arm.lower()}_switches"]:
                    trace = replay_structure(*args, arm=arm, check_special=switch)
                    reference = {name: case["loro"][name] for name in IDENTITY_KEYS}
                    if switch == "phi_zero":
                        reference["R_ref"] = reference.pop("Reff")
                    errors[switch] = parity(trace, reference)
                checks["identity"][arm][route] = errors
                print(f"{arm} {route}: fixed-mask LORO parity passed", flush=True)
            for route, case in cases.items():
                args = (case["packet"], case["controls"], case["mask"], core, online, model, case["spec"], case["table"], case["fit"])
                trace = replay_structure(*args, arm=arm)
                checks["scored_trace"][arm][route] = recheck_trace(trace, case, arm)
                packet = case["packet"]
                np.savez_compressed(out / f"{route}_{arm}_trace.npz", t=packet["t"], pose_id=packet["pose_id"], **trace)
                print(f"{arm} {route}: replay and numeric invariants passed", flush=True)
        dump(out / "IMPLEMENTATION_CHECKS.json", checks)
        score(out, lock)
        receipt.update(status="PASS_EXECUTION", exit_code=0)
    except Exception as e:
        receipt.update(status="FAIL_EXECUTION", exit_code=1, error=str(e))
        raise
    finally:
        receipt.update(finished_utc=utc(), outputs={p.name: sha(p) for p in out.iterdir() if p.is_file()})
        dump(out / "EXECUTION.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("freeze", "run"))
    parser.add_argument("--contract", type=Path, default=LOCK)
    parser.add_argument("--out", type=Path, default=HERE / "run_01")
    args = parser.parse_args()
    freeze() if args.phase == "freeze" else execute(args.contract, args.out)
