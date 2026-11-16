"""Stage 3 seed sensitivity diagnostic for G1-INT-001/M5 HF-KI."""

import argparse
from pathlib import Path
import sys

import numpy as np

from run_hfki import (
    COUNTS, KEYS, NAV, REV, ROOT, ROUTES, SEEDS, array_sha, arrays, auth,
    bindings, cases_from, checked, grid_equal, item, model_env, output_of,
    parity, read, save_trace, scores, sha, utc, write,
)


ALL_SEEDS = (10, *SEEDS)
ELL_M = 0.5
EXPOSURE_FIELDS = ("F", "g", "arc", "yaw", "dwell", "s_updated")
COMPARATORS = {"A0": list(ROUTES), "X2": ["R5"]}


def freeze(out):
    previous = {}
    for index in range(3):
        stage = out.parent / f"stage{index}"
        verification = read(stage / "VERIFICATION.json")
        if verification["status"] != "PASS_VERIFICATION":
            raise ValueError(f"Stage {index} verification is required")
        records = {name: item(checked(dict(path=stage / name, sha256=digest)))
                   for name, digest in verification["inputs_and_execution"].items()}
        if read(stage / "EXECUTION.json")["status"] != "PASS_EXECUTION":
            raise ValueError(f"Stage {index} execution did not pass")
        previous[str(index)] = records | {"VERIFICATION.json": item(stage / "VERIFICATION.json")}
    lock2 = auth(out.parent / "stage2", 2)
    cohort = output_of(out.parent / "stage0", "CHECKS.json")
    band = output_of(out.parent / "stage2", "BAND.json")
    scores2 = output_of(out.parent / "stage2", "SCORES.json")
    verdict = read(checked(band))
    evidence = read(checked(scores2))
    if (verdict["status"] != "NO_BAND"
            or evidence["X1"]["mirror_fail_count"] < 1
            or not evidence["X1"]["fixed_g_nominal_information_below_M1D"]):
        raise ValueError("This diagnostic requires NO_BAND and R5 X1 branch failure under lower fixed-g information")
    source = read(checked(cohort))["seed_packets"]
    packets = {str(seed): {route: source[f"{route}_B0_Full_{seed}__online.npz"] for route in ROUTES}
               for seed in SEEDS}
    for records in packets.values():
        for record in records.values():
            checked(record)
    write_lock = dict(stage=3, role="IMPLEMENTER", study="G1-INT-001/M5", frozen_utc=utc(),
                      classification="DIAGNOSTIC_ONLY", plan=lock2["plan"], scope=lock2["scope"],
                      source=item(Path(__file__).resolve()), parents=previous,
                      stage0_cohort=cohort, stage2_band=band, stage2_scores=scores2,
                      seeds=ALL_SEEDS, online_packets=packets, comparators=COMPARATORS,
                      entry="X2_NECESSARY: assess recurrent versus seed-sensitive R5 branch failure after X1",
                      A2="NOT_RUN_NO_BAND",
                      gate="Reuse the exact seed-10 E0 gate mask for each route and seed",
                      initial="Use the seed-10 x0 and P0 in all five seeds; keep RF, z, grid and model fixed",
                      controls="Use seed-specific B0 wheel/gyro controls; verify dt retains the seed-10 grid",
                      variance="Per-seed A0 packet Reff from the frozen E0-LORO sigma_b table",
                      X2=dict(mode="D", ell_m=ELL_M, yaw_deg=10., route="R5"),
                      E_STOCH=dict(max_flipped_seeds_to_support=2, denominator=5),
                      scoring=lock2["scoring"], parity_tolerance=lock2["parity_tolerance"],
                      gate_counts=lock2["gate_counts"], crossings=lock2["crossings"])
    out.mkdir(parents=True, exist_ok=False)
    write(out / "RUN_CONTRACT.json", write_lock)
    print("Stage 3 diagnostic contract", sha(out / "RUN_CONTRACT.json"), flush=True)


def authorized(out):
    base = bindings()
    lock = read(out / "RUN_CONTRACT.json")
    if lock["stage"] != 3 or lock["plan"]["commit"] != REV:
        raise ValueError("Wrong Stage 3 contract")
    for record in (lock["source"], lock["stage0_cohort"], lock["stage2_band"], lock["stage2_scores"]):
        checked(record)
    for records in (*lock["parents"].values(), *lock["online_packets"].values()):
        for record in records.values():
            checked(record)
    lock2 = auth(out.parent / "stage2", 2)
    return base, lock, lock2, cases_from(lock2)


def seed_cases(seed, lock, frozen):
    built = {}
    for route, case in frozen.items():
        original = case["packet"]
        if seed == 10:
            candidate = original
        else:
            candidate = arrays(checked(lock["online_packets"][str(seed)][route]))
            if set(candidate) != set(KEYS):
                raise ValueError(f"{route}/{seed}: online input fields differ")
            for key in set(KEYS) - {"ds", "gy", "x0"}:
                np.testing.assert_array_equal(candidate[key], original[key], err_msg=key)
            candidate["x0"] = original["x0"]
        controls = {key: candidate[key] for key in ("ds", "gy", "dt")}
        built[route] = case | {"packet": candidate, "controls": controls}
    return built


def collect(seed_dir, cases, lock2):
    from exposure_replay import check_trace
    from replay_s2 import validate_trace

    common, details = {}, {}
    for route, case in cases.items():
        baseline = arrays(seed_dir / f"{route}_A0.npz")
        grid_equal(case["packet"], baseline)
        validate_trace(baseline)
        np.testing.assert_array_equal(baseline["mask"], case["baseline"]["mask"])
        count = (int(baseline["mask"].sum()), baseline["mask"].size)
        if count != COUNTS[route]:
            raise ValueError(f"{route}: gate counts differ")
        common[route] = {"BASE": baseline}
        details[route] = dict(mask_count=count[0], packet_count=count[1],
                              x0_sha256=array_sha(case["packet"]["x0"]),
                              P0_sha256=array_sha(case["packet"]["P0"]),
                              controls_sha256={key: array_sha(value) for key, value in case["controls"].items()})
        if seed_dir.name == "seed10":
            details[route]["A0_parity"] = parity(baseline, case["baseline"])
    case = cases["R5"]
    baseline = common["R5"]["BASE"]
    trace = arrays(seed_dir / "R5_X2.npz")
    grid_equal(case["packet"], trace)
    validate_trace(trace)
    details["R5"]["X2_trace"] = check_trace(trace, case["packet"], case["controls"], baseline, "D", ELL_M)
    np.testing.assert_array_equal(trace["Reff"], baseline["Reff"])
    if seed_dir.name == "seed10":
        archived = arrays(checked(lock2["exposure"]["R5_D05"]))
        details["R5"]["X2_parity"] = parity(trace, archived, NAV + EXPOSURE_FIELDS)
    row = dict(A0=scores(common, cases),
               X2=scores({"R5": {"BASE": baseline, "X2": trace}}, cases))
    return row, details


def branch_summary(rows, lock):
    pairs = {}
    x2_seeds, a0_seeds = [], []
    for seed, row in rows.items():
        a0 = row["A0"]["branch"]["R5"]["BASE"]["mirror_fail_count"]
        x2 = row["X2"]["branch"]["R5"]["X2"]["mirror_fail_count"]
        pairs[seed] = dict(A0_R5=a0, X2_R5=x2)
        if a0:
            a0_seeds.append(int(seed))
        if x2:
            x2_seeds.append(int(seed))
    limit = lock["E_STOCH"]["max_flipped_seeds_to_support"]
    return dict(A2=lock["A2"], mirror_fail_counts=pairs, A0_R5_seeds_with_mirror=a0_seeds,
                X2_R5_seeds_with_mirror=x2_seeds, X2_seed_count=len(x2_seeds),
                E_STOCH="SUPPORTED" if len(x2_seeds) <= limit else "NOT_SUPPORTED_BY_FROZEN_RULE",
                A0_R5_seed_dependent=0 < len(a0_seeds) < len(rows),
                adoption="NOT_TESTED_NO_A2_BAND")


def execute(out):
    from traceback import format_exc

    base, lock, lock2, frozen = authorized(out)
    from d0_d5 import replay_sigma
    from exposure_replay import replay

    target = out / "EXECUTION.json"
    if target.exists() or any(out.glob("seed*")):
        raise FileExistsError("Stage 3 execution has existing evidence")
    receipt = dict(stage=3, started_utc=utc(), command=sys.argv, contract_sha256=sha(out / "RUN_CONTRACT.json"),
                   software=dict(python=sys.version, numpy=np.__version__))
    try:
        native, receipt["native_source_hashes"] = model_env(base)
        expected = read(checked(lock["parents"]["2"]["EXECUTION.json"]))["native_source_hashes"]
        if receipt["native_source_hashes"] != expected:
            raise ValueError("Native source identity differs from verified Stage 2")
        rows, details = {}, {}
        for seed in lock["seeds"]:
            cases = seed_cases(seed, lock, frozen)
            seed_dir = out / f"seed{seed}"
            seed_dir.mkdir(exist_ok=False)
            for route, case in cases.items():
                packet, controls = case["packet"], case["controls"]
                baseline = replay_sigma(packet, controls, case["baseline"]["mask"], *native, case["sigma_b"])
                save_trace(seed_dir, route, "A0", case, baseline)
                if route == "R5":
                    x2 = replay(packet, controls, baseline, *native, "D", ELL_M)
                    save_trace(seed_dir, route, "X2", case, x2)
            rows[str(seed)], details[str(seed)] = collect(seed_dir, cases, lock2)
            print("Stage 3 seed", seed, "A0 and X2 replay and checks complete", flush=True)
        write(out / "CHECKS.json", details)
        write(out / "SCORES.json", rows)
        write(out / "BAND.json", branch_summary(rows, lock))
        receipt.update(status="PASS_EXECUTION", exit_code=0)
    except Exception as exc:
        receipt.update(status="FAIL_EXECUTION", exit_code=1, error=str(exc), traceback=format_exc())
        raise
    finally:
        receipt["finished_utc"] = utc()
        receipt["outputs"] = {path.relative_to(out).as_posix(): sha(path) for path in sorted(out.rglob("*"))
                              if path.is_file() and path.name != "RUN_CONTRACT.json"}
        write(target, receipt)


def verify(out):
    _, lock, lock2, frozen = authorized(out)
    receipt = read(out / "EXECUTION.json")
    if receipt["status"] != "PASS_EXECUTION" or receipt["contract_sha256"] != sha(out / "RUN_CONTRACT.json"):
        raise ValueError("Stage 3 execution or contract differs")
    expected = {f"seed{seed}/{route}_A0.npz" for seed in ALL_SEEDS for route in ROUTES}
    expected.update({f"seed{seed}/R5_X2.npz" for seed in ALL_SEEDS})
    expected.update({"CHECKS.json", "SCORES.json", "BAND.json"})
    if set(receipt["outputs"]) != expected:
        raise ValueError("Stage 3 evidence set differs")
    for name, digest in receipt["outputs"].items():
        checked(dict(path=out / name, sha256=digest))
    rows, details = {}, {}
    for seed in lock["seeds"]:
        rows[str(seed)], details[str(seed)] = collect(out / f"seed{seed}", seed_cases(seed, lock, frozen), lock2)
    if rows != read(out / "SCORES.json") or details != read(out / "CHECKS.json"):
        raise ValueError("Stage 3 check or score reaggregation differs")
    if branch_summary(rows, lock) != read(out / "BAND.json"):
        raise ValueError("Stage 3 branch verdict differs")
    write(out / "VERIFICATION.json",
          dict(stage=3, status="PASS_VERIFICATION", role="IMPLEMENTER_SELF_CHECK", verified_utc=utc(),
               inputs_and_execution={name: sha(out / name) for name in ("RUN_CONTRACT.json", "EXECUTION.json")},
               output_hashes=len(expected), details="20 traces, frozen identities, X2 schedule, score and branch reaggregation"))
    print("Stage 3 verification passed for", len(expected), "outputs", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("freeze", "execute", "verify", "pipeline"))
    parser.add_argument("--output-root", type=Path, default=ROOT / "attempt_02")
    args = parser.parse_args()
    out = args.output_root / "stage3"
    if args.phase == "pipeline":
        freeze(out)
        execute(out)
        verify(out)
    else:
        {"freeze": freeze, "execute": execute, "verify": verify}[args.phase](out)


if __name__ == "__main__":
    main()
