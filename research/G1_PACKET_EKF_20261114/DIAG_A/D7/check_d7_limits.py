"""D7 entry gate on the original BLOCK_C packet streams."""
import argparse
import json
import os
from pathlib import Path

for env in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[env] = "1"

import numpy as np

import diag_replay
from diag_inputs import CASES, WORK, control_paths, init_modules, load_case, sha256
from diag_jc import Term, replay
from run_diag import write_json

D4_SHA = "6208455eada004ead57b9db4ae14dae037e530e82888596f8700fe977eb8b4e8"
SPEC_COMMIT = "f3c2717d45326f4226c4e548c0f25db116c51026"


def reference_replay(data, controls, initial, scales=None):
    args = [data[k] for k in ("model", "case", "z", "mu", "R", "t")]
    if scales is None:
        return diag_replay.replay(*args, controls, initial, [(1, 0)], ffd=data["ffd"])
    # D6 replay is unmodified. Its sigma table is supplied by D4 for this comparison.
    original = diag_replay.SIGMA_NODES
    try:
        diag_replay.SIGMA_NODES = scales
        return diag_replay.replay(*args, controls, initial, [(1, 0)],
                                  ffd=data["ffd"], variance=True)
    finally:
        diag_replay.SIGMA_NODES = original


def compare(reference, actual):
    delta = actual["state"] - reference["state"]
    delta[..., 2] = diag_replay.wrap(delta[..., 2])
    row = {
        "state_max_abs": np.abs(delta).max(),
        "covariance_max_abs": np.abs(actual["covariance"] - reference["covariance"]).max(),
        "nis_max_abs": np.abs(actual["nis"] - reference["nis"]).max(),
        "accept_mask_difference_count": np.count_nonzero(actual["accepted"] != reference["accepted"]),
        "observations_compared": actual["accepted"].size,
    }
    # Reuse pre-existing batch replay tolerances from run_diag.parity.
    row["pass"] = (row["state_max_abs"] <= 2e-10
                   and row["covariance_max_abs"] <= 2e-10
                   and row["nis_max_abs"] <= 2e-8
                   and row["accept_mask_difference_count"] == 0)
    return row


def d4_inputs():
    path = WORK/"results/D4_SUMMARY.json"
    if sha256(path) != D4_SHA:
        raise ValueError("D4 summary hash mismatch")
    return json.loads(path.read_text(encoding="utf-8"))["case_cohort"]


def load_frozen_case(case, out):
    if case.startswith(("R4", "R5")):
        import p0_initial
        from source_model import SourceFFD
        p0_initial.OUT = out / case
        p0_initial.OUT.mkdir(parents=True, exist_ok=True)
        return load_case(case, ffd_model=SourceFFD())
    return load_case(case)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=CASES)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    init_modules()
    from p3_rf_adapter4 import RR
    data = load_frozen_case(args.case, args.out.parent/"bank_audit")
    np.testing.assert_array_equal(data["R"][:, 0, 0], RR)
    d4 = d4_inputs()[args.case]
    if [row["rho_m"] for row in d4["distance_scale"]] != diag_replay.DISTANCE_NODES:
        raise ValueError("Unexpected D4 distance knot positions")
    scales = tuple(float(row["s_rms"]) for row in d4["distance_scale"])
    seeds = list(range(20))
    controls, initial, _ = control_paths(data, "B0", 0, seeds)
    j4 = compare(reference_replay(data, controls, initial),
                 replay(data, controls, initial, (Term(1, "white", 0.0),)))
    jv = compare(reference_replay(data, controls, initial, scales),
                 replay(data, controls, initial, (Term(1, "white", scales),)))
    gate = {"spec_commit": SPEC_COMMIT, "classification": "DIAGNOSTIC_ONLY",
            "case": args.case, "cohort": "B0", "seeds": seeds, "c_r": "disabled",
            "original_range_covariance_m2": RR, "sigma_knots": scales, "d4_sha256": D4_SHA,
            "J4": j4, "J-V": jv, "status": "PASS" if j4["pass"] and jv["pass"] else "FAIL"}
    write_json(args.out, gate)
    print(args.case, gate["status"], flush=True)
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
