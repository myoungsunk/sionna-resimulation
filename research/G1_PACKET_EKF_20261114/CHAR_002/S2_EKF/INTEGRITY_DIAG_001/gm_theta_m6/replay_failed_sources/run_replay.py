"""Freeze and run the M6 fixed-mask replays, then verify their archive."""

import argparse
from pathlib import Path
from traceback import format_exc

import numpy as np

from run_characterization import (
    ROOT, REV, characterization_inputs, check_records, m5, receipt, verified_native,
)

GRID = (1.5, 2., 3., 4.)
SEEDS = tuple(range(10, 15))
NEAR_ROUTES = ("R2", "R4")


def replay_items(estimate):
    """Resolve the registered arm matrix before any candidate scores exist."""
    arms = []
    for route in m5.ROUTES:
        fold = estimate["k2"]["folds"][route]
        sigma = fold["sigma_rad"]
        if not np.isfinite(sigma) or sigma <= 0.:
            raise ValueError(f"Missing supported LORO sigma for {route}")

        def add(name, arm, seeds, **parameters):
            arms.append(dict(route=route, name=name, seeds=list(seeds),
                             kw=dict(arm=arm, **parameters)))

        for deg in GRID:
            add(f"G1_{deg:g}", "G1", (10,), sigma_rad=np.deg2rad(deg).item())
        add("G1_LORO", "G1", SEEDS, sigma_rad=sigma)
        add("G2_LORO", "G2", (10,), sigma_rad=sigma)
        add("G3_LORO", "G3", (10,), sigma_rad=sigma)
        if route in NEAR_ROUTES:
            add("G4", "G4", (10,))
            add("G5psi", "G5psi", (10,), sigma_rad=sigma)
            add("G5y", "G5y", (10,), sigma_rad=sigma)
        hybrid = estimate["hybrid"]
        if hybrid is not None:
            addl = hybrid["folds"][route]
            if any(addl["supported_bins"]):
                add("G1_KI", "G1", SEEDS, sigma_rad=sigma,
                    q_table=[[0., 1.5, 3., 6., 10.], addl["q_s"], addl["supported_bins"]])
        distance = fold["distance_table"]
        if distance is not None:
            table = [distance["knots_m"], distance["sigma_rad"]]
            for name, seeds in (("G1", SEEDS), ("G2", (10,)), ("G3", (10,))):
                add(name + "d", name, seeds, sigma_table=table)
    return arms


def freeze(source, out):
    char_contract = m5.item(source / "RUN_CONTRACT.json")
    char_receipt = m5.item(source / "EXECUTION.json")
    lock = m5.read(m5.checked(char_contract))
    check_records(lock)
    execution = m5.read(m5.checked(char_receipt))
    if execution["status"] != "PASS_EXECUTION" or execution["contract_sha256"] != char_contract["sha256"]:
        raise ValueError("Characterization did not complete with the fixed contract")
    estimate = m5.output_of(source, "K1_PRIME_K2.json")
    prediction = m5.read(m5.checked(estimate))
    m5.output_of(source, "K4_BASELINE.json")
    m5.output_of(source, "K5.json")
    spec = dict(study=lock["study"], role=lock["role"], stage="replay", frozen_utc=m5.utc(),
                classification=lock["classification"], plan=lock["plan"], scope=lock["scope"],
                inputs=dict(contract=char_contract, execution=char_receipt, characterization=estimate),
                sources=[m5.item(ROOT / name) for name in ("run_replay.py", "gm_replay.py", "gm_checks.py")],
                variants=replay_items(prediction), sigma_grid_deg=GRID, seeds=SEEDS,
                k1_verdict=prediction["k1"]["verdict"], k2_verdict=prediction["k2"]["verdict"],
                hybrid_requested=prediction["k1"]["trigger_hybrid"], gate="fixed seed 10 E0 mask",
                covariance_reference="same seed, route-specific G0 Reff",
                stationarity_length_m=1., rotation_length_deg=10., max_past_s=10., max_past_packets=100,
                near_distance_m=3., parity_absolute_tolerance=m5.TOL,
                scoring=dict(blocks_s=[5, 10, 20], draws=1500, seed=20261115,
                             route=dict(coverage_min=.75, lower_min=.60, rmse_increase_max=.25, mirrors=0),
                             pooled=dict(coverage_min=.90, lower_min=.80, rmse_increase_max=.10,
                                         mean_nees3=[1.5, 6.], mirrors=0), min_adjacent_grid=2,
                             min_passing_pooled_seeds=4, max_marginal_increase=.25))
    check_records(spec)
    out.mkdir(parents=True, exist_ok=True)
    m5.write(out / "RUN_CONTRACT.json", spec)


def setup(out):
    spec = m5.read(out / "RUN_CONTRACT.json")
    if spec["stage"] != "replay" or spec["plan"]["commit"] != REV:
        raise ValueError("Wrong execution contract")
    check_records(spec)
    lock = m5.read(spec["inputs"]["contract"]["path"])
    check_records(lock)
    base = m5.bindings()
    from run_stage3 import seed_cases

    frozen = m5.cases_from(lock)
    cases = {seed: seed_cases(seed, lock, frozen) for seed in SEEDS}
    return spec, lock, base, cases


def schedule(lock, route, case):
    archived = m5.arrays(m5.checked(lock["archived_a2"][route]))
    m5.grid_equal(case["packet"], archived)
    base = case["baseline"]
    np.testing.assert_array_equal(base["Reff"], archived["R_ref"])
    np.testing.assert_array_equal(base["mask"], archived["mask"])
    distance = np.linalg.norm(base["prior"][:, :2] - np.array([10., 0.]), axis=1)
    return archived, dict(a2_variance=np.column_stack([archived["V"], archived["causal"]]), near=distance < 3.)


def verify_receipt(directory):
    record = m5.read(directory / "EXECUTION.json")
    if record["exit_code"] != 0 or record["contract_sha256"] != m5.sha(directory / "RUN_CONTRACT.json"):
        raise ValueError(f"Invalid prerequisite receipt: {directory}")
    for name, digest in record["outputs"].items():
        m5.checked(dict(path=directory / name, sha256=digest))
    return record


def stage_dir(out, stage, parent=None):
    directory = out / stage
    directory.mkdir(exist_ok=True)
    upstream = m5.item(out / "RUN_CONTRACT.json")
    input_receipt = None
    if parent:
        verify_receipt(out / parent)
        input_receipt = m5.item(out / parent / "EXECUTION.json")
    m5.write(directory / "RUN_CONTRACT.json",
             dict(stage=stage, replay_contract=upstream, prior_stage=input_receipt, frozen_utc=m5.utc()))
    return directory


def online_inputs(case, native):
    return case["packet"], case["controls"], case["baseline"], *native


def tested(reports, name, function):
    try:
        result = function()
        reports[name] = dict(status="FAIL" if result.get("status") == "FAIL" else "PASS", details=result)
    except (ValueError, AssertionError, RuntimeError, np.linalg.LinAlgError) as exc:
        reports[name] = dict(status="FAIL", error=str(exc), traceback=format_exc())
    return reports[name]["status"] == "PASS"


def implementation_stage(out, spec, lock, cases, native, hashes):
    from d0_d5 import replay_sigma
    from gm_checks import check_trace, geometry_checks, information_barrier, parity, synthetic_checks
    from gm_replay import replay

    directory = stage_dir(out, "implementation")
    with receipt(directory, "implementation") as run:
        run["native_source_hashes"] = hashes
        checks = dict(baseline={}, synthetic={}, routes={})
        for seed, routes in cases.items():
            seed_dir = directory / f"seed{seed}"
            seed_dir.mkdir()
            for route, case in routes.items():
                archived = m5.arrays(m5.checked(lock["archived_a0"][str(seed)][route]))
                fixed = case["baseline"]["mask"]
                g0 = replay_sigma(case["packet"], case["controls"], fixed, *native, case["sigma_b"])
                m5.grid_equal(case["packet"], archived)
                checks["baseline"][f"{seed}/{route}"] = m5.parity(g0, archived)
                m5.save_trace(seed_dir, route, "G0", case, g0)
                case["baseline"] = g0
            print(f"Implementation: archived G0 parity seed {seed} complete", flush=True)

        common = tested(checks["synthetic"], "independent_update_AR_and_information_bound", synthetic_checks)
        for route, case in cases[10].items():
            route_checks = checks["routes"][route] = {}
            args = online_inputs(case, native)
            g0 = case["baseline"]
            for arm in ("G1", "G2", "G3"):
                tested(route_checks, f"{arm}_off", lambda arm=arm: parity(replay(*args, arm=arm), g0))
            geometric = g0 | dict(h_nav=g0["h"], b_theta_prior=np.zeros(len(g0["x"])))
            tested(route_checks, "geometry_G0", lambda: geometry_checks(
                geometric, native[2], native[3], raise_on_failure=False))
            lw = next(row["kw"] for row in spec["variants"] if row["route"] == route and row["name"] == "G1_LORO")

            def barrier():
                trace = replay(*args, **lw)
                return information_barrier(trace, *args, **lw)

            if common and all(route_checks[key]["status"] == "PASS" for key in ("G1_off", "geometry_G0")):
                tested(route_checks, "causality_G1", barrier)
            tested(route_checks, "causality_G3", lambda: information_barrier(
                replay(*args, arm="G3", sigma_rad=lw["sigma_rad"]), *args, arm="G3", sigma_rad=lw["sigma_rad"]))
            if route in NEAR_ROUTES:
                archived, fixed = schedule(lock, route, case)
                tested(route_checks, "G4_archived_A2", lambda: parity(
                    replay(*args, arm="G4", **(fixed | dict(near=np.zeros_like(fixed["near"])))), archived))
                for arm in ("G5psi", "G5y"):
                    tested(route_checks, f"{arm}_off", lambda arm=arm: parity(
                        replay(*args, arm=arm, disable_beta=True, **fixed), replay(*args, arm="G4", **fixed)))
            hybrid = next((row["kw"] for row in spec["variants"]
                           if row["route"] == route and row["name"] == "G1_KI"), None)
            if hybrid is not None:
                zero = [[0., 1.5, 3., 6., 10.], [0.] * 4, [True] * 4]
                tested(route_checks, "G1_KI_off", lambda: parity(
                    replay(*args, **(hybrid | dict(q_table=zero))), replay(*args, **lw)))
                tested(route_checks, "G1_KI_sigma_off", lambda: parity(
                    replay(*args, **(hybrid | dict(q_table=zero, sigma_rad=0.))), g0))
                tested(route_checks, "G1_KI_causal_sum", lambda: check_trace(
                    replay(*args, **hybrid), *args[:3], native[0], native[3], **hybrid))
            print(f"Implementation: {route} parity and checks complete", flush=True)
        m5.write(directory / "CHECKS.json", checks)
    return checks


def required_checks(row):
    name, arm = row["name"], row["kw"]["arm"]
    requirements = ["geometry_G0"]
    if arm in ("G1", "G2", "G3", "G5psi", "G5y"):
        requirements.append(f"{arm}_off")
    if arm == "G1":
        requirements.append("causality_G1")
    if arm == "G3":
        requirements.append("causality_G3")
    if arm in ("G4", "G5psi", "G5y"):
        requirements.append("G4_archived_A2")
    if name == "G1_KI":
        requirements += ["G1_KI_off", "G1_KI_sigma_off", "G1_KI_causal_sum"]
    return requirements


def replay_stage(out, stage, parent, seeds, spec, lock, cases, native, hashes, checks):
    from gm_checks import check_trace, geometry_checks
    from gm_replay import replay

    directory = stage_dir(out, stage, parent)
    with receipt(directory, stage) as run:
        run["native_source_hashes"] = hashes
        details = {}
        for seed in seeds:
            seed_dir = directory / f"seed{seed}"
            seed_dir.mkdir()
            details[str(seed)] = {}
            for route, case in cases[seed].items():
                ready = details[str(seed)][route] = {}
                args = online_inputs(case, native)
                rows = [row for row in spec["variants"] if row["route"] == route and seed in row["seeds"]]
                for row in rows:
                    name, options = row["name"], row["kw"].copy()
                    missing = [key for key in required_checks(row)
                               if checks["routes"][route].get(key, {}).get("status") != "PASS"]
                    if checks["synthetic"]["independent_update_AR_and_information_bound"]["status"] != "PASS":
                        missing.append("synthetic")
                    if missing:
                        ready[name] = dict(status="STOPPED_BY_IMPLEMENTATION_CHECK", checks=missing)
                        continue
                    if options["arm"] in ("G4", "G5psi", "G5y"):
                        options.update(schedule(lock, route, case)[1])

                    def execute_arm():
                        trace = replay(*args, **options)
                        check = check_trace(trace, *args[:3], native[0], native[3], **options)
                        geometry = geometry_checks(trace, native[2], native[3], raise_on_failure=False)
                        m5.save_trace(seed_dir, route, name, case, trace)
                        return dict(status=geometry["status"], replay=check, geometry=geometry)

                    tested(ready, name, execute_arm)
                print(f"{stage}: seed {seed}, {route}, {sum(r['status'] == 'PASS' for r in ready.values())}"
                      f"/{len(ready)} replays verified", flush=True)
        m5.write(directory / "CHECKS.json", details)


def run(out):
    spec, lock, base, cases = setup(out)
    native, hashes = verified_native(base)
    checks = implementation_stage(out, spec, lock, cases, native, hashes)
    replay_stage(out, "seed10", "implementation", (10,), spec, lock, cases, native, hashes, checks)
    replay_stage(out, "seed11_14", "seed10", SEEDS[1:], spec, lock, cases, native, hashes, checks)


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="command", required=True)
    freeze_parser = actions.add_parser("freeze")
    freeze_parser.add_argument("source", type=Path)
    freeze_parser.add_argument("out", type=Path)
    run_parser = actions.add_parser("run")
    run_parser.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.source, args.out)
    else:
        run(args.out)


if __name__ == "__main__":
    main()
