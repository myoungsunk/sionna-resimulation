"""Freeze inputs, reproduce E0, then run G1-CHAR-002 S2 arms."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
import scipy

from metrics_s2 import Trace, classify_motion, evaluate_stage
from replay_s2 import (ARMS, D_MAX, NU, Learned, b0_reference, fit_sweep, geometry,
                       learned_replay, parity, read_npz, sha, validate_trace)


SPEC_COMMIT = "6c175a53fbbbb19f990881f7dfcf82a3760dab70"
NATIVE_COMMIT = "beb845665661ad8c68d07c88f6d268da4832e493"
ROUTES = {"R2": 979, "R4": 742, "R5": 1415}
CASES = {"2a": "B0", "2b": "L2", "2c": "A_B0"}


def now():
    return datetime.now(timezone.utc).isoformat()


def put(path, obj):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def data_paths(args, stage, route):
    root = args.release if stage == "2a" else args.extensions
    prefix = f"{route}_{CASES[stage]}_Full_10"
    expected = ["online", "evaluator"]
    if stage == "2b":
        expected.append("reference")
    return {kind: root / f"{prefix}__{kind}.npz" for kind in expected}


def models(doc):
    fit = doc["fits"]
    return {key.split("_", 1)[0]: Learned.load(value) for family in fit.values() for key, value in family.items()
            if key.split("_", 1)[0] in ("R1", "R2", "S1", "S2", "S3")}


def freeze(args, fit_paths, source_files):
    contract_path = args.out / "RUN_CONTRACT.json"
    if contract_path.exists():
        raise FileExistsError(contract_path)
    spec = args.char / "CHAR_002" / "SPEC_S2_EKF_KO.md"
    snapshot = {"question_id": "G1-CHAR-002-S2", "role": "IMPLEMENTER", "created_utc": now(),
                "scope": ["2a", "2b", "2c"], "status": "DIAGNOSTIC_ONLY", "seals": ["S2′ STOP", "Step 3 HOLD", "G-T2/G-V SEALED"],
                "spec_commit": SPEC_COMMIT, "native_commit": NATIVE_COMMIT, "spec_sha256": sha(spec),
                "native_source_hashes": {str(path.relative_to(args.native)): sha(path) for path in source_files},
                "fit_sha256": sha(fit_paths["model"]),
                "fit_sweep_inputs": {str(path): sha(path) for path in (*fit_paths["sweep"], *fit_paths["samples"])},
                "s1_fit_code_sha256": sha(fit_paths["code"]),
                "s2_code_sha256": {name: sha(Path(__file__).with_name(name)) for name in ("run_s2.py", "replay_s2.py", "metrics_s2.py")},
                "governance": {"COMMON_CONTRACT.md": "a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
                               "ROLE_IMPLEMENTER.md": "2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da"},
                "thresholds": {"pooled_pose95_min": .90, "route_pose95_min": .75, "pooled_heading95_min": .90,
                               "rmse_increase_cost_cutoff": .10, "parity_normalized_tolerance": 1e-10},
                "stage_requirements": {"2a": "B0 release SHA and archived E0 replay parity",
                                       "2b": "L2 A2 controls, exact frozen inputs and A2 E0 replay parity",
                                       "2c": "B z generator parity, A packet and explicitly frozen A baseline inputs"},
                "arms": {"E0": "original frozen W0 including muMB_s", "E1": "R1/S1", "E2": "R2/S2", "E3": "R2/S3 primary",
                         "E4": "R2/S3 plus yaw-correlated latent state", "E5": "per-trajectory oracle R2/S3 fit on its evaluation packets"},
                "gate": "fixed original W0 shadow-gate mask from each condition's E0; E1–E5 zero s mean adjustment",
                "frozen_predictors": "range and 180° folded relative bearing from predicted prior; lookup fixed through update, no lookup Jacobian",
                "distance_extrapolation_m": D_MAX, "distance_mean": "continue S1 linear location as fitted",
                "student_t": {"nu/E3-E4": NU, "weight_iterations": 3, "variance_step": "divide current R_ss by w each iteration"},
                "yaw_state": {"form": "unit-scale AR(1), Q_c=1-phi^2; c_s=sqrt(share)*sigma_s*c; white R_ss=(1-share)*sigma_s^2 before reweighting",
                              "reset_m": .02, "reset_rule": "Euclidean XY displacement of consecutive priors", "fit":"dense49 TEACH only"},
                "bootstrap": {"sizes_s": [5, 10], "repetitions": 1500, "seed": 20261115},
                "motion_labels": "CHAR-001 rules applied to evaluator truth on the packet time grid",
                "stage_2a_inputs": {route: {kind: {"path": str(p), "sha256": sha(p)} for kind, p in data_paths(args, "2a", route).items()}
                                     for route in ROUTES},
                "release_lock_sha256": sha(args.lock), "environment": {"platform": platform.platform(), "python": sys.version,
                                                                        "numpy": np.__version__, "scipy": scipy.__version__},
                "precommit_command": sys.argv}
    put(contract_path, snapshot)


def bind(args, stage, report):
    packet_sets = {}
    bound = {}
    if stage == "2a":
        records = {entry["asset_name"]: entry for entry in json.loads(args.lock.read_bytes())["files"]}
        for name, spec in records.items():
            path = args.release / name if "__" in name else args.native / name
            if path.stat().st_size != spec["size"] or sha(path) != spec["sha256"]:
                raise ValueError(f"Release identity mismatch: {name}")
    for route, n in ROUTES.items():
        paths = data_paths(args, stage, route)
        bound[route] = {kind: {"path": str(path), "sha256": sha(path)} for kind, path in paths.items()}
        packet = read_npz(paths["online"])
        if packet["z"].shape != (n, 2) or np.any(np.diff(packet["t"]) <= 0) or np.any(np.diff(packet["pose_id"]) <= 0):
            raise ValueError(f"Packet identity or timing mismatch: {stage} {route}")
        packet_sets[route] = (paths, packet)
    report["inputs"] = bound
    return packet_sets


def oracle_models(truth, z, model, spec, fit_path):
    sys.path.insert(0, str(fit_path.parent))
    import char2_fit_eval as training
    d, angle = geometry(truth, spec)
    h_truth, _ = model.batch(np.column_stack([truth, np.zeros(len(truth))]), spec, gradient=False)
    e = z - h_truth
    bins = training.bins(angle)
    ranges = training.r_models()[2].fit(e[:, 0], bins, d)
    pol = training.s_models()[3].fit(e[:, 1], bins, d)
    return Learned.load(ranges.describe()), Learned.load(pol.describe()), {"range": ranges.describe(), "pol": pol.describe()}


def check_baseline(bound, stage, core, online, model, spec):
    traces, errors = {}, {}
    for route, (paths, packet) in bound.items():
        controls = {key: packet[key] for key in ("ds", "gy", "dt")}
        controls["x0"] = packet["x0"][:3]
        base = online.replay(packet, controls, "W0", core, model, spec)
        validate_trace(base)
        if stage == "2b":
            archive = read_npz(paths["reference"])
            for key in ("pose_id", "t"):
                if not np.array_equal(archive[key], packet[key]):
                    raise ValueError(f"L2 reference join mismatch: {route} {key}")
            expected = {key: archive[key] for key in ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "mask")}
        else:
            expected = b0_reference(packet)
        errors[route] = parity(base, expected)
        traces[route] = (controls, base)
        largest = max(row["max_normalized_error"] for row in errors[route].values())
        print("E0_PARITY_PASS", stage, route, largest, flush=True)
    return traces, errors


def replay_stage(args, stage, core, online, model, spec, learned, yawfit, fit_code):
    out = args.out / stage
    out.mkdir()
    report = {"stage": stage, "started_utc": now(), "command": sys.argv, "run_contract_sha256": sha(args.out / "RUN_CONTRACT.json")}
    try:
        bound = bind(args, stage, report)
        put(out / "INPUTS.json", report["inputs"])
        baseline, errors = check_baseline(bound, stage, core, online, model, spec)
        put(out / "E0_PARITY.json", {"status": "PASS", "tolerance": 1e-10, "routes": errors})
        traces, oracle_fit = {}, {}
        for route, (paths, packet) in bound.items():
            controls, base = baseline[route]
            d, bearing = geometry(base["prior"], spec)
            base.update(prior_range=d, prior_bearing_deg=bearing)
            per_arm = {"E0": base}
            for arm, (r, s) in {"E1": ("R1", "S1"), "E2": ("R2", "S2"), "E3": ("R2", "S3"), "E4": ("R2", "S3")}.items():
                per_arm[arm] = learned_replay(packet, controls, base["mask"], core, online, model, spec, arm, learned[r], learned[s], yawfit)
            # Evaluator is loaded only after all online arms for this trajectory have completed.
            ev = read_npz(paths["evaluator"])
            for key in ("pose_id", "t"):
                if not np.array_equal(ev[key], packet[key]):
                    raise ValueError(f"Evaluator join mismatch: {route} {key}")
            truth = ev["truth"]
            rfit, sfit, oracle_fit[route] = oracle_models(truth, packet["z"], model, spec, fit_code)
            per_arm["E5"] = learned_replay(packet, controls, base["mask"], core, online, model, spec, "E5", rfit, sfit, yawfit)
            segments = classify_motion(truth)
            traces[route] = {}
            for arm in ARMS:
                tr = per_arm[arm]
                extrap = tr["prior_range"] > D_MAX
                path = out / f"{route}_{arm}_trace.npz"
                np.savez_compressed(path, **tr, t=packet["t"], pose_id=packet["pose_id"], extrapolated=extrap, motion=segments)
                traces[route][arm] = Trace(packet["t"], tr["x"], tr["P"], truth, extrap, tr["prior_bearing_deg"], segments, tr["mask"])
            print("ARM_TRACES_COMPLETE", stage, route, flush=True)
        put(out / "ORACLE_FIT_DIAGNOSTIC.json", oracle_fit)
        results = evaluate_stage(traces, expected_cases=tuple(ROUTES), bootstrap_seed=20261115)
        put(out / "RESULTS.json", results)
        report.update(status="PASS_EXECUTION", exit_code=0)
    except Exception as error:
        report.update(status="FAIL_EXECUTION", exit_code=1, error=str(error))
        raise
    finally:
        report.update(finished_utc=now(), outputs={p.name: sha(p) for p in out.iterdir() if p.is_file()})
        put(out / "EXECUTION.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("release", "native", "lock", "char", "teach-poses", "extensions", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--stage", choices=tuple(CASES), required=True)
    args = parser.parse_args()
    if args.stage == "2c":
        raise ValueError("2c requires a bound anchor-A baseline and a generator-parity receipt")
    args.out.mkdir(parents=True, exist_ok=True)
    fit_paths = {"model": args.char / "CHAR_002" / "out" / "FIT.json",
                 "code": args.char / "CHAR_002" / "scripts" / "char2_fit_eval.py",
                 "sweep": [args.char / "CHAR_001" / "out" / f"ERRORS_G-T1_{anchor}.csv.gz" for anchor in ("A", "B", "C")],
                 "samples": [args.teach_poses / f"G-T1_{anchor}" / "SAMPLES.json" for anchor in ("A", "B", "C")]}
    learned = models(json.loads(fit_paths["model"].read_bytes()))
    sys.path.insert(0, str(args.native / "src"))
    from qclean_uwb.fp_sc.e0_baseline import SPEC, load_original_model

    core, online, model, _ = load_original_model(args.native)
    contract = args.out / "RUN_CONTRACT.json"
    yaw_path = args.out / "FIT_S2.json"
    if not contract.exists():
        freeze(args, fit_paths, sorted(args.native.rglob("*.py")))
        if args.stage != "2a":
            raise ValueError("2a must pass before extensions")
    if not yaw_path.exists():
        put(yaw_path, fit_sweep(fit_paths["sweep"], fit_paths["samples"], learned["S3"]))
    yawfit = json.loads(yaw_path.read_bytes())
    if args.stage != "2a" and not (args.out / "2a" / "RESULTS.json").is_file():
        raise ValueError("2a result is missing")
    replay_stage(args, args.stage, core, online, model, SPEC, learned, yawfit, fit_paths["code"])


if __name__ == "__main__":
    main()
