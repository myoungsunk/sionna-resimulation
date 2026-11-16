"""Freeze, execute and verify G1-INT-001/KS-TRANSFER in the registered order."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import numpy as np
import scipy


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
D23 = PARENT / "continuation_d2_d3"
STRUCT = PARENT / "structure_sc_ki"
D4 = PARENT / "continuation_d4"
PRIOR = PARENT / "attempt_02"
PUBLICATION = PARENT.parent.parent / "g1_int_diag001_publication_20261115"
PLAN_PATH = "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/ADDITIONAL_INTEGRITY_VALIDATION_PLAN_KO.md"
PLAN_COMMIT = "aa95e6cda82695a59e40549f41eb067d98b9b1a7"
LOCK = HERE / "RUN_CONTRACT.json"
BASE = PARENT / "RUN_CONTRACT.json"
ROUTES = ("R2", "R4", "R5")
FIELDS = ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S", "mask")
STAGES = ("PREFLIGHT", "V8", "V1", "V2", "V4", "V3", "V9", "V5", "V6", "D4", "V7", "D6", "KS")

sys.path[0:0] = [str(PARENT), str(D23), str(STRUCT)]
from d1_shuffle import dump, sha, verify_file
from ks_diagnostics import BLOCKS, BOOTSTRAP_REPS, BOOTSTRAP_SEED, COVERAGE, RMSE, WINDOW


def utc():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def item(path):
    return dict(path=str(path), sha256=sha(path))


def prior_output(folder, name):
    receipt = read(folder / "EXECUTION.json")
    if receipt["status"] != "PASS_EXECUTION":
        raise ValueError(f"Prerequisite execution failed: {folder}")
    return verify_file(dict(path=str(folder / name), sha256=receipt["outputs"][name]))


def freeze(contract, retry, *, previous_contract=None, previous_sources=None):
    import ks_fit
    import ks_diagnostics
    import ks_replay
    from run_d2_d3 import authenticate as authenticate_d23
    from run_structure import authenticate as authenticate_structure

    if contract.exists():
        raise FileExistsError("The freeze destination already exists")
    d23_lock, base = authenticate_d23()
    struct_lock, checked_base = authenticate_structure()
    if base != checked_base:
        raise ValueError("Inherited D2/D3 and SC/KI inputs disagree")
    checked = [(PRIOR / "VERIFICATION.json", "report_results_sha256", PRIOR / "RESULTS.json"),
               (D23 / "VERIFICATION.json", "results_sha256", D23 / "RESULTS.json"),
               (STRUCT / "VERIFICATION.json", "execution_sha256", STRUCT / "run_01" / "EXECUTION.json"),
               (D4 / "VERIFICATION.json", "execution_sha256", D4 / "run_02" / "EXECUTION.json")]
    for receipt, key, target in checked:
        validation = read(receipt)
        if validation["status"] != "PASS_REAGGREGATION" or validation[key] != sha(target):
            raise ValueError(f"Unverified prior output: {target}")
    for stage in ("d2", "d3"):
        if read(D23 / "VERIFICATION.json")["output_checks"][stage] != sha(D23 / stage / "EXECUTION.json"):
            raise ValueError(f"Prior execution verification mismatch: {stage}")
    if read(D4 / "VERIFICATION.json")["contract_sha256"] != sha(D4 / "RUN_CONTRACT_RETRY_02.json"):
        raise ValueError("D4 retry contract verification mismatch")
    prior_dirs = [PRIOR / "d0", PRIOR / "d5", D23 / "d2", D23 / "d3", STRUCT / "run_01", D4 / "run_02"]
    extra = [*[(folder / "EXECUTION.json") for folder in prior_dirs],
             *[path for receipt, _, target in checked for path in (receipt, target)],
             BASE, D23 / "CONTINUATION_CONTRACT.json", STRUCT / "RUN_CONTRACT.json", D4 / "RUN_CONTRACT_RETRY_02.json",
             prior_output(PRIOR / "d5", "FOLDS.json"), prior_output(D23 / "d3", "RESULTS.json"),
             prior_output(D4 / "run_02", "RESULTS.json"), prior_output(D4 / "run_02", "HGB_FEATURE_SUPPORT.json")]
    for cell in base["cells"]:
        key = "_".join(cell[name] for name in ("anchor", "bias", "route"))
        extra.extend([prior_output(PRIOR / "d0", f"{key}.npz"), prior_output(D23 / "d2", f"{key}.npz")])
    for holdout in ROUTES:
        extra.append(prior_output(PRIOR / "d5", f"B_B0_{holdout}.npz"))
        extra.extend(prior_output(D23 / "d2", f"M3_{holdout}_donor_{r}.npz") for r in ROUTES if r != holdout)
    for route in ("R2", "R5"):
        extra.append(prior_output(STRUCT / "run_01", f"{route}_SC_trace.npz"))
    inherited = (d23_lock["sources"] + struct_lock["sources"] + struct_lock["s2_sources"] +
                 list(base["provenance"]["native_files"].values()) + list(struct_lock["model_assets"].values()))
    for cell in base["cells"]:
        inherited.extend(cell[key] for key in ("online", "evaluator"))
    inputs = {r["path"]: r for r in [*inherited, *[item(path) for path in extra]]}
    for record in inputs.values():
        verify_file(record)
    plan = subprocess.check_output(["git", "-C", str(PUBLICATION), "show", f"{PLAN_COMMIT}:{PLAN_PATH}"])
    plan_file = HERE / "PLAN_FROZEN.md"
    if plan_file.exists():
        if plan_file.read_bytes() != plan:
            raise ValueError("Frozen plan bytes changed")
    else:
        with plan_file.open("xb") as handle:
            handle.write(plan)
    lock = {
        "question": "G1-INT-001/KS-TRANSFER", "role": "IMPLEMENTER", "frozen_utc": utc(),
        "repository": "myoungsunk/sionna-resimulation", "branch": "research/g1-sweep-heading-floor-spec-20261113",
        "plan_commit": PLAN_COMMIT, "plan": item(plan_file), "derived_sources": [
            item(path) for path in (Path(__file__), Path(ks_fit.__file__), Path(ks_diagnostics.__file__), Path(ks_replay.__file__))],
        "governance": struct_lock["governance"], "inputs": list(inputs.values()), "order": STAGES,
        "scope": base["scope"] | {"primary": "B/B0/R2,R4,R5", "V5": "B/B0/R4", "V9": "B/B0/R2,R5",
                                  "D6": "B/B0/R2,R4,R5", "V7": "A/B paired B0 and L2 descriptive"},
        "rules": {"parity_max": 1e-10, "residual_decomposition_max": 1e-12, "D3_window": WINDOW,
                  "V8_distance_edges_m": ks_fit.DISTANCE_EDGES.tolist(), "V8_min_centers": 30,
                  "V8_min_distinct_complete_20s_windows": 2, "V8_ratio": [.5, 2.],
                  "V8_variance_floor": ks_fit.MIN_VARIANCE, "V8_extrapolation_above": .5,
                  "V1_ratio": [.7, 1.3], "lag_edges_m": ks_fit.LAG_EDGES.tolist(), "min_pairs": ks_fit.MIN_PAIRS,
                  "fast_lengths_m": ks_fit.FAST_LENGTHS.tolist(), "slow_lengths_m": ks_fit.SLOW_LENGTHS.tolist(),
                  "V2_near_min_fraction": .05, "V2_donor_length_ratio": 2., "V4_trace": "original E0",
                  "V4_correlation": .8, "V3_heading_gate": .75, "V3_rmse_ratio": 1.25, "V3_uncap_above": .10,
                  "V3_uncap_rule": "restore slow only; paired absolute CI including .75 inconclusive",
                  "V5_widths_m": [.25, .5, 1.], "V5_recovery": .90, "V6_range_xy_delta": .05,
                  "V7_A_over_B": 2., "D6_native": 9.210340371976184, "D6_alternative": 13.8,
                  "D6_equivalence_band": .03, "bootstrap_s": BLOCKS, "bootstrap_min_blocks": 8,
                  "bootstrap_reps": BOOTSTRAP_REPS, "bootstrap_seed": BOOTSTRAP_SEED, "M2": base["M2"],
                  "pooled_pose_heading_primary_CI_floor": .80, "KI_history_seconds": 10., "KI_history_cap": 100,
                  "length_lookup": "per-step predicted prior bin; integrate delta-distance/length; carry across unsupported bins",
                  "Rref_timing": "inherited previous posterior lookup, equivalently current prior when D5 sigma knots are flat",
                  "missing_bin": "fallback to baseline white; record packet count; no unsupported V3 claims",
                  "V3_unidentified_length": "longest near-minimum supported length for diagnostic replay",
                  "conditional_admission": "V8, V1, V2 PASS and V3 a,c PASS, with a prime diagnostic only"},
        "provenance": "New source files are individually content-locked before execution. Frozen inherited evidence is read-only.",
        "use": "Single frozen RF run/seed in the stated corridor; A and B0/L2 paired, no new RF or hardware.",
    }
    if retry is not None:
        parent_contract = previous_contract or LOCK
        source_dir = previous_sources or HERE / "executed_source_attempt_01"
        previous = read(retry / "EXECUTION.json")
        if previous["status"] != "FAIL_EXECUTION" or previous["contract_sha256"] != sha(parent_contract):
            raise ValueError("First attempt provenance mismatch")
        original = read(parent_contract)
        previous_hashes = []
        for record in original["derived_sources"]:
            path = Path(record["path"])
            if sha(path) != record["sha256"]:
                path = source_dir / path.name
            verify_file(record | {"path": str(path)})
            previous_hashes.append(item(path))
        lock["retry"] = dict(previous_contract=item(parent_contract), previous_execution=item(retry / "EXECUTION.json"),
                             previous_sources=previous_hashes, previous_completed_stages=previous["completed_stages"],
                             correction=("record the unsupported V5 width and resume with prior outputs"
                                         if previous_contract else "load the frozen native module after path binding"))
        for key in ("plan", "inputs", "governance", "rules", "scope", "order"):
            if original[key] != json.loads(json.dumps(lock[key])):
                raise ValueError(f"Retry altered the previously frozen {key}")
    dump(contract, lock)
    print(f"FROZEN {sha(contract)}", flush=True)


def authenticate(contract):
    lock = read(contract)
    if lock["plan_commit"] != PLAN_COMMIT or tuple(lock["order"]) != STAGES:
        raise ValueError("Plan identity or order changed")
    for record in [lock["plan"], *lock["derived_sources"], *lock["inputs"], *lock["governance"]]:
        verify_file(record)
    if "retry" in lock:
        retry = lock["retry"]
        prior_sources = retry["previous_sources"] if "previous_sources" in retry else [retry["previous_runner"]]
        for record in (retry["previous_contract"], retry["previous_execution"], *prior_sources):
            verify_file(record)
    return lock


def read_setup(lock):
    from run_d2_d3 import load_cases
    from run_structure import authenticate as structure_auth, cases_from
    from d0_d5 import controls_for, replay_sigma

    structural, base = structure_auth()
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from d3 import motion_arcs
    from replay_s2 import parity, read_npz

    core, online, model, sources = load_original_model(base["native"])
    if online.GATE != lock["rules"]["D6_native"]:
        raise ValueError("Native shadow threshold changed")
    all_cases = load_cases(base, model)
    replay_cases = cases_from(structural)
    residual_errors = {}
    for key, case in all_cases.items():
        case["controls"] = controls_for(case["packet"])
        saved_d2 = read_npz(D23 / "d2" / f"{key}.npz")
        checks = parity(saved_d2, {"mask": case["e0"]["mask"], "t": case["packet"]["t"], "pose_id": case["packet"]["pose_id"]})
        residual_errors[key] = float(np.max(np.abs(case["eps"] - saved_d2["truth_residual_r_s"])))
        if residual_errors[key] > 1e-12:
            raise ValueError(f"D2 residual parity failed: {key}")
    primary = {r: all_cases[f"B_B0_{r}"] for r in ROUTES}
    baseline_checks = {}
    for route, ka in replay_cases.items():
        case = primary[route]
        if not np.array_equal(ka["table"], np.full_like(ka["table"], ka["table"][0])):
            raise ValueError("Current-prior and inherited Rref lookup no longer equivalent")
        native = online.replay(case["packet"], case["controls"], "W0", core, model, case["spec"])
        loro = replay_sigma(ka["packet"], ka["controls"], ka["mask"], core, online, model, ka["spec"], ka["table"])
        baseline_checks[route] = dict(E0=parity(native, {k: case["e0"][k] for k in FIELDS}),
                                      LORO=parity(loro, {k: ka["loro"][k] for k in FIELDS}))
    fit_cases, fit_checks = {}, {}
    for fold in ROUTES:
        fit_cases[fold], fit_checks[fold] = {}, {}
        for route, case in primary.items():
            packet, spec, mask = case["packet"], case["spec"], case["e0"]["mask"]
            table = replay_cases[fold]["table"]
            ref = replay_cases[route]["loro"] if route == fold else replay_sigma(
                packet, case["controls"], mask, core, online, model, spec, table)
            arc, yaw = motion_arcs(packet, ref)
            if route != fold:
                old = read_npz(D23 / "d2" / f"M3_{fold}_donor_{route}.npz")
                fit_checks[fold][route] = parity(
                    {**ref, "arc": arc, "yaw": yaw, "t": packet["t"], "pose_id": packet["pose_id"]}, old)
            d = np.linalg.norm(ref["prior"][:, :2] - np.asarray(spec["anchor"][:2]), axis=1)
            fit_cases[fold][route] = dict(t=packet["t"], arc=arc, yaw=yaw, eps=case["eps"],
                                         g=np.abs(ref["H"][:, 1, 2]), d=d, mask=mask, Rref=ref["Reff"])
    return core, online, model, all_cases, primary, replay_cases, fit_cases, dict(
        native_hashes=sources, original_and_loro=baseline_checks, donors=fit_checks, residual_abs_error=residual_errors)


def noise_for(params, fold, variant):
    from ks_fit import DISTANCE_EDGES
    from ks_replay import Noise

    def choose(distance, g):
        index = int(np.searchsorted(DISTANCE_EDGES, distance, side="right")) - 1
        if index not in params[fold]:
            return None
        row = params[fold][index]
        if variant == "oracle":
            v, length = row["oracle_slow"], row["oracle_length"]
        elif variant == "distance":
            v, length = row["slow_distance"], row["distance_slow_length"]
        elif variant in ("sensitivity", "sensitivity_matched_distance_length"):
            beta = row["beta"]
            field = "slow_length" if variant == "sensitivity" else "distance_slow_length"
            v, length = (None if beta is None else beta[0] + beta[1] * g ** 2), row[field]
        else:
            raise ValueError(f"Unknown variance variant: {variant}")
        fields = (row["white"], row["fast"], v, row["fast_length"], length)
        return None if any(value is None for value in fields) else Noise(*fields)
    return choose


def save_trace(out, label, trace):
    np.savez_compressed(out / f"{label}.npz", **trace)


def v3(params, replay_cases, primary, core, online, model, out):
    from verify_s2 import from_trace
    from ks_diagnostics import scores_with_blocks, v3_status
    from ks_replay import check_trace, clipping_summary, replay_ks

    route = "R4"
    case = replay_cases[route]
    truth, time = primary[route]["truth"], case["packet"]["t"]
    rows = {"LORO": from_trace(case["loro"], truth)}
    checks, clipping = {}, {}

    def run(label, variant, *, uncap=False):
        trace = replay_ks(case, core, online, model, noise_for(params, route, variant), uncap_slow=uncap)
        checks[label] = check_trace(trace, case)
        clipping[label] = clipping_summary(trace)
        save_trace(out, f"V3_{label}", trace)
        rows[label] = from_trace(trace, truth)

    for label, variant in (("a", "oracle"), ("b", "distance"), ("c", "sensitivity_matched_distance_length")):
        run(label, variant)
    activity = clipping["a"]["fraction"]
    if activity is not None and activity > .10:
        run("a_prime", "oracle", uncap=True)
    contrasts = [(label, "LORO") for label in checks] + [("c", "b")] + ([("a_prime", "a")] if "a_prime" in checks else [])
    score = scores_with_blocks({route: rows}, {route: time}, contrasts)
    decision = {label: v3_status(score, label, clipping[label]["supported"]) for label in checks}
    return dict(scores=score, decisions=decision, checks=checks, clipping=clipping,
                a_prime_executed="a_prime" in checks, a_prime_activity_threshold=.10)


def v9(replay_cases, primary, core, online, model, out):
    from replay_s2 import parity, read_npz, validate_trace
    from verify_s2 import from_trace
    from ks_replay import check_trace, replay_v9
    from ks_diagnostics import scores_with_blocks

    rows, times, checks = {}, {}, {}
    for route in ("R2", "R5"):
        case, truth = replay_cases[route], primary[route]["truth"]
        rows[route] = {"LORO": from_trace(case["loro"], truth)}
        rows[route]["SC_historical"] = from_trace(read_npz(STRUCT / "run_01" / f"{route}_SC_trace.npz"), truth)
        times[route] = case["packet"]["t"]
        checks[route] = {}
        expected_schedule = None
        for arm in ("SC", "GM", "FIXED_GAIN"):
            trace = replay_v9(case, core, online, model, arm=arm, fixed_schedule=True)
            validate_trace(trace)
            checks[route][arm] = check_trace(trace, case, forced_gain=arm == "FIXED_GAIN", expect_zero_nuisance=arm != "GM")
            if arm == "SC":
                expected_schedule = {k: trace[k] for k in ("D", "alpha", "q", "lookup_distance", "R_ref")}
            else:
                for key, expected in expected_schedule.items():
                    np.testing.assert_array_equal(trace[key], expected)
            if arm == "FIXED_GAIN":
                checks[route]["fixed_gain_parity"] = parity(trace, {key: case["loro"][key] for key in ("x", "prior", "K", "mask")})
            save_trace(out, f"V9_{route}_{arm}", trace)
            rows[route][arm] = from_trace(trace, truth)
    contrasts = [(arm, "LORO") for arm in ("SC_historical", "SC", "GM", "FIXED_GAIN")] + [("GM", "SC")]
    score = scores_with_blocks(rows, times, contrasts)
    restored = {}
    for route in rows:
        point = score["point"][route]
        restored[route] = {metric: dict(
            archived_sc_ratio=point["SC_historical"][metric] / point["LORO"][metric],
            matched_sc_ratio=point["SC"][metric] / point["LORO"][metric],
            gm_ratio=point["GM"][metric] / point["LORO"][metric]) for metric in RMSE}
        for data in restored[route].values():
            data["gm_restores_matched_sc_limit"] = bool(data["matched_sc_ratio"] > 1.25 >= data["gm_ratio"])
    return dict(scores=score, checks=checks, accuracy=restored, case_schedule="frozen LORO prior")


def final_replay(params, replay_cases, primary, core, online, model, out):
    from verify_s2 import from_trace
    from ks_replay import check_trace, replay_ks
    from ks_diagnostics import scores_with_blocks

    rows, times, checks = {}, {}, {}
    for route, case in replay_cases.items():
        truth = primary[route]["truth"]
        rows[route] = {"LORO": from_trace(case["loro"], truth), "E0": from_trace(primary[route]["e0"], truth)}
        times[route] = case["packet"]["t"]
        checks[route] = {}
        for arm in ("KS", "KI"):
            trace = replay_ks(case, core, online, model, noise_for(params, route, "sensitivity"), arm=arm)
            checks[route][arm] = check_trace(trace, case)
            save_trace(out, f"KS_{route}_{arm}", trace)
            rows[route][arm] = from_trace(trace, truth)
    score = scores_with_blocks(rows, times, [("KS", "LORO"), ("KI", "LORO"), ("KS", "KI")])
    gates = {}
    bounds = score["blocks"]["10"]["by_group"]["pooled"]
    for arm in ("KS", "KI"):
        metrics = score["point"]
        per_route = {r: all(metrics[r][arm][m] >= .75 for m in COVERAGE) and
                        all(metrics[r][arm][m] <= 1.25 * metrics[r]["LORO"][m] for m in RMSE) for r in ROUTES}
        pooled = metrics["pooled"][arm]
        p_floor = all(bounds["absolute_ci95"][arm][m][0] >= .80 for m in ("pose95_coverage", "heading95_coverage"))
        p_points = min(pooled["pose95_coverage"], pooled["heading95_coverage"]) >= .90
        p_nees = 1.5 <= pooled["mean_nees3"] <= 6.
        p_accuracy = all(pooled[m] <= 1.10 * metrics["pooled"]["LORO"][m] for m in RMSE)
        eligible = p_floor and p_points and p_nees and p_accuracy and all(per_route.values())
        gates[arm] = dict(status="INCONCLUSIVE" if bounds["reference_only"] else ("PASS" if eligible else "FAIL"),
                          route_pass=per_route, pooled_points=p_points, pooled_nees=p_nees,
                          pooled_accuracy=p_accuracy, pooled_ci=p_floor)
    return dict(status="EXECUTED", scores=score, checks=checks, assessment=gates)


def resume_v5(lock, out, receipt):
    retry = lock["retry"]
    parent = verify_file(retry["previous_execution"])
    previous = read(parent)
    if tuple(previous["completed_stages"]) != STAGES[:STAGES.index("V5")] or previous["status"] != "FAIL_EXECUTION":
        raise ValueError("Resume expects a completed prefix ending at V9")
    for name, digest in previous["outputs"].items():
        source = verify_file({"path": str(parent.parent / name), "sha256": digest})
        dest = out / name
        with dest.open("xb") as handle, source.open("rb") as origin:
            shutil.copyfileobj(origin, handle)
        if sha(dest) != digest:
            raise ValueError(f"Resume output copy failed: {name}")
    receipt.update(completed_stages=previous["completed_stages"].copy(), resumed_from=retry["previous_execution"],
                   reused_outputs=previous["outputs"])
    print("Verified and reused stages through V9", flush=True)
    return (read(out / "V8.json"), read(out / "V1.json"), read(out / "V2.json"), read(out / "V3.json"),
            {fold: {int(k): value for k, value in bins.items()} for fold, bins in read(out / "FITTED_PARAMETERS.json").items()})


def execute(contract, out, *, resume=False):
    from ks_fit import v1_v2, v8
    from ks_replay import Noise, check_trace, replay_ks, synthetic_checks
    import ks_diagnostics as diag

    lock = authenticate(contract)
    out.mkdir(exist_ok=False)
    receipt = dict(question=lock["question"], contract_sha256=sha(contract), started_utc=utc(),
                   command=sys.argv, python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
                   platform=platform.platform(), completed_stages=[])

    def complete(stage, result):
        if stage != STAGES[len(receipt["completed_stages"])]:
            raise ValueError(f"Execution order violated: {stage}")
        dump(out / f"{stage}.json", result)
        receipt["completed_stages"].append(stage)
        print(f"{stage} complete", flush=True)

    try:
        core, online, model, cases, primary, ka, fit_cases, preflight = read_setup(lock)
        from replay_s2 import parity

        if resume:
            transfer, first, second, oracle, params = resume_v5(lock, out, receipt)
        else:
            preflight["synthetic"] = synthetic_checks()
            preflight["ks_identity"] = {}
            for route, case in ka.items():
                preflight["ks_identity"][route] = {}
                for arm in ("KS", "KI"):
                    trace = replay_ks(case, core, online, model, lambda d, g: None, arm=arm)
                    check_trace(trace, case)
                    preflight["ks_identity"][route][arm] = parity(trace, {key: case["loro"][key] for key in FIELDS})
                for arm, special in (("KS", "independent"), ("KI", "empty_history")):
                    trace = replay_ks(case, core, online, model, lambda d, g: Noise(1e-4, .001, .002, .15, .75),
                                      arm=arm, check_special=special)
                    check_trace(trace, case, history_enabled=False)
                    actual = trace | {"Reff": trace["R_ref"]} if arm == "KS" else trace
                    preflight["ks_identity"][route][special] = parity(actual, {key: case["loro"][key] for key in FIELDS})
            complete("PREFLIGHT", preflight)
            transfer, internal = v8(fit_cases)
            complete("V8", transfer)
            first, second, params = v1_v2(fit_cases, internal)
            complete("V1", first)
            complete("V2", second)
            dump(out / "FITTED_PARAMETERS.json", params)
            complete("V4", diag.v4(primary, core, online, out))
            oracle = v3(params, ka, primary, core, online, model, out)
            complete("V3", oracle)
            complete("V9", v9(ka, primary, core, online, model, out))
        complete("V5", diag.v5(primary["R4"], core, online, model, out))
        complete("V6", diag.v6(read(D23 / "d3" / "RESULTS.json")))
        complete("D4", dict(status="INHERITED", result=item(D4 / "run_02" / "RESULTS.json"),
                            HGB_features=item(D4 / "run_02" / "HGB_FEATURE_SUPPORT.json"),
                            verification=item(D4 / "VERIFICATION.json")))
        complete("V7", diag.v7(cases, out))
        complete("D6", diag.d6(primary, ka, core, online, model, out))
        gates = {"V8": transfer["status"], "V1": first["status"], "V2": second["status"],
                 **{f"V3_{arm}": oracle["decisions"][arm]["status"] for arm in ("a", "c")}}
        final = final_replay(params, ka, primary, core, online, model, out) if set(gates.values()) == {"PASS"} else {
            "status": "STOP_NOT_ADMITTED", "entrance_gates": gates}
        complete("KS", final)
        receipt.update(status="PASS_EXECUTION", exit_code=0, candidate_stage=final["status"])
    except Exception as exc:
        receipt.update(status="FAIL_EXECUTION", exit_code=1, error=repr(exc))
        raise
    finally:
        receipt.update(finished_utc=utc(), outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()})
        dump(out / "EXECUTION.json", receipt)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("freeze", "run"))
    cli.add_argument("--contract", type=Path, default=LOCK)
    cli.add_argument("--retry", type=Path)
    cli.add_argument("--previous-contract", type=Path)
    cli.add_argument("--previous-sources", type=Path)
    cli.add_argument("--resume-v5", action="store_true")
    cli.add_argument("--out", type=Path, default=HERE / "run_01")
    options = cli.parse_args()
    if options.phase == "freeze":
        freeze(options.contract, options.retry, previous_contract=options.previous_contract, previous_sources=options.previous_sources)
    else:
        execute(options.contract, options.out, resume=options.resume_v5)
