"""Stage 0–2 driver and evidence verifier for G1-INT-001/M5 HF-KI."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parent
ART = ROOT.parent
REPO = ART.parent / "g1_mount45_b0_publication_20261116"
DIAG = ART / "G1_INT_DIAG_001_20261115"
EXPOSURE = ART / "G1_EXPOSURE_M1_M4_20261116"
STRUCTURE = DIAG / "structure_sc_ki/RUN_CONTRACT.json"
BASE = DIAG / "RUN_CONTRACT.json"
KS = DIAG / "continuation_ks"
D3 = DIAG / "continuation_d2_d3/d3"
C1 = DIAG / "continuation_checks_c1_c8/run_01"
READINESS = ART / "G1_HFKI_M5_STAGE0_20261116/SEED_DATA_READINESS.json"
REV = "033abcc7f2940bd8437ccbebd145d2f9f229730b"
PLAN = "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/PLAN_M5_HFKI_STAGED_KO.md"
ROUTES = ("R2", "R4", "R5")
COUNTS = {"R2": (971, 979), "R4": (728, 742), "R5": (1384, 1415)}
PASSES = {"R2": 2, "R4": 1, "R5": 3}
GRID = (2, 3, 4, 6, 8)
SEEDS = (11, 12, 13, 14)
TOL = 1e-10
KEYS = ("t", "pose_id", "P0", "z", "muMB", "muBASE", "R", "D", "ds", "gy", "dt", "x0")
NAV = ("x", "P", "prior", "Pprior", "h", "H", "Reff", "K", "nu", "S")


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def array_sha(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def item(path):
    return dict(path=str(path), sha256=sha(path))


def checked(record):
    path = Path(record["path"])
    if sha(path) != record["sha256"]:
        raise ValueError(f"SHA-256 differs for {path}")
    return path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, allow_nan=False, ensure_ascii=False, indent=2)
        handle.write("\n")


def arrays(path):
    with np.load(path, allow_pickle=False) as file:
        return {name: file[name] for name in file.files}


def grid_equal(reference, other):
    for name in ("t", "pose_id"):
        np.testing.assert_array_equal(reference[name], other[name])


def parity(actual, expected, fields=NAV):
    np.testing.assert_array_equal(actual["mask"], expected["mask"])
    errors = {}
    for name in fields:
        if actual[name].dtype.kind == "b":
            np.testing.assert_array_equal(actual[name], expected[name])
            errors[name] = 0.
            continue
        np.testing.assert_allclose(actual[name], expected[name], atol=TOL, rtol=0., err_msg=name)
        errors[name] = float(np.max(np.abs(actual[name] - expected[name])))
    return errors


def output_of(directory, name):
    receipt = read(directory / "EXECUTION.json")
    return item(checked(dict(path=directory / name, sha256=receipt["outputs"][name])))


def bindings():
    base = read(BASE)
    sys.path[:0] = [str(DIAG), str(KS), str(DIAG / "continuation_d2_d3"), str(EXPOSURE),
                    base["s2"], str(Path(base["native"]) / "src")]
    return base


def source_receipts(base):
    files = [Path(__file__), ROOT / "hfki_replay.py", ROOT / "hfki_predict.py",
             EXPOSURE / "exposure_replay.py", EXPOSURE / "exposure_score.py",
             DIAG / "d0_d5.py", DIAG / "continuation_d2_d3/d3.py", DIAG / "continuation_d2_d3/d2.py",
             KS / "ks_diagnostics.py", KS / "ks_replay.py"]
    files += [Path(base["s2"]) / f"{name}.py" for name in ("verify_s2", "metrics_s2", "replay_s2")]
    return [item(path) for path in files]


def freeze(stage, out):
    from hfki_predict import distance_bin_contract

    plansha = subprocess.check_output(["git", "-C", str(REPO), "show", f"{REV}:{PLAN}"])
    structure = read(STRUCTURE)
    readiness = read(READINESS)
    if (structure["scope"] != dict(anchor="B", bias="B0", mount_deg=0., seed=10, rf="Full", routes=list(ROUTES))
            or readiness["status"] != "SEED_DATA_FEASIBLE" or readiness["plan"]["commit"] != REV
            or readiness["plan"]["sha256"] != hashlib.sha256(plansha).hexdigest()):
        raise ValueError("Parent scope or seed-data readiness differs")
    for record in structure["governance"]:
        checked(record)
    previous = []
    for index in range(stage):
        prior = ROOT / f"stage{index}"
        record = read(prior / "VERIFICATION.json")
        if record["status"] != "PASS_VERIFICATION":
            raise ValueError(f"Stage {index} verification is pending")
        for name, digest in record["inputs_and_execution"].items():
            checked(dict(path=prior / name, sha256=digest))
        previous.append(item(prior / "VERIFICATION.json"))
    d3 = {route: output_of(D3, f"B_B0_{route}.npz") for route in ROUTES}
    oracle = {"V3_a": output_of(KS / "run_03", "V3_a.npz"), "C1_KI": output_of(C1, "C1_R4_KI.npz")}
    old = EXPOSURE / "run_01"
    exposure = {route: output_of(old, f"{route}_I05.npz") for route in ROUTES}
    exposure["R5_D05"] = output_of(old, "R5_D05.npz")
    cells = []
    for cell in structure["cells"]:
        route = cell["route"]
        assert route in COUNTS
        for name in ("online", "evaluator", "loro_trace", "fixed_gate_trace"):
            checked(cell[name])
        cells.append({name: cell[name] for name in ("route", "online", "evaluator", "loro_trace",
                                                      "fixed_gate_trace", "sigma_b")})
    contract = dict(stage=stage, role="IMPLEMENTER", study="G1-INT-001/M5", frozen_utc=utc(),
                    classification="DIAGNOSTIC_ONLY", scope=structure["scope"], cells=cells,
                    plan=dict(commit=REV, path=PLAN, sha256=hashlib.sha256(plansha).hexdigest()),
                    sources=source_receipts(bindings()), model_assets=structure["model_assets"],
                    receipts=[item(path) for path in (BASE, STRUCTURE, READINESS, D3 / "EXECUTION.json",
                                                     KS / "run_03/EXECUTION.json", C1 / "EXECUTION.json",
                                                     old / "EXECUTION.json", old / "VERIFICATION.json")] + previous,
                    d3=d3, oracle=oracle, exposure=exposure, governance=structure["governance"],
                    parity_tolerance=TOL, gate_counts=COUNTS, crossings=PASSES,
                    parameters=dict(grid_deg=GRID, ell_m=1., yaw_length_deg=10., g_ref=1.,
                                    window_s=10., past_accepted_cap=100, A3_distance=distance_bin_contract(),
                                    X1_multiplier=4., x1_comparator="M1-D R5"),
                    scoring=dict(all_packets=True, pooled_coverage=["heading", "pose"], route_coverage=["heading", "xy", "pose"],
                                 route=[.75, .60, 1.25], pooled=[.90, .80, 1.10], nees=[1.5, 6.],
                                 marginal_ratio_ceiling=1.25, marginal_for_progression=False,
                                 mirror_max=0, blocks_s=[5, 10, 20], draws=1500, bootstrap_seed=20261115,
                                 minimal_adjacent_grid_values=3),
                    seed_stage0=dict(seeds=SEEDS, reuse_rf_and_z=True,
                                     sensor="native B0: wheel, gyro, noisy initial x0 seeded; P0 fixed",
                                     baseline_policy="Stage 0 persists input-only NPZ and uses no new seed for scores."),
                    stage2_middle_grid="lower of the two middle grid values for an even passing band, 4 deg without a band",
                    stages_scope="mount 0 anchor B B0 only; S2 prime STOP; Step 3 HOLD; sealed data excluded")
    if stage == 2:
        stage1 = ROOT / "stage1/PREDICT.json"
        predictions = read(stage1)
        contract["A3_donor_result"] = item(stage1)
        contract["A3_donor_tables"] = predictions["A3_range_KI"]["folds"]
    out.mkdir(exist_ok=False)
    write(out / "RUN_CONTRACT.json", contract)
    print("Stage", stage, "contract", sha(out / "RUN_CONTRACT.json"), flush=True)


def auth(out, stage):
    path = out / "RUN_CONTRACT.json"
    lock = read(path)
    if lock["stage"] != stage or lock["plan"]["commit"] != REV:
        raise ValueError("Stage or plan differs")
    list_assets = list(lock["model_assets"].values())
    for record in (lock["sources"] + lock["receipts"] + lock["governance"] + list_assets
                   + list(lock["d3"].values()) + list(lock["oracle"].values()) + list(lock["exposure"].values())):
        checked(record)
    if stage == 2:
        verified = checked(lock["A3_donor_result"])
        if read(verified)["A3_range_KI"]["folds"] != lock["A3_donor_tables"]:
            raise ValueError("Frozen Stage 2 A3 tables differ from Stage 1")
    return lock


def cases_from(lock):
    from exposure_score import crossings
    from replay_s2 import validate_trace

    cases = {}
    for cell in lock["cells"]:
        route = cell["route"]
        packet, truth, baseline, fixed = (arrays(checked(cell[name])) for name in
                                          ("online", "evaluator", "loro_trace", "fixed_gate_trace"))
        packet = {name: packet[name] for name in KEYS}
        for reference in (truth, baseline, fixed):
            grid_equal(packet, reference)
        validate_trace(baseline)
        np.testing.assert_array_equal(baseline["mask"], fixed["mask"])
        if (int(baseline["mask"].sum()), len(packet["t"])) != COUNTS[route]:
            raise ValueError(f"{route}: frozen gate count differs")
        points = crossings(truth["truth"], packet["t"])
        if len(points) != PASSES[route]:
            raise ValueError(f"{route}: unexpected anchor passage count")
        cases[route] = dict(packet=packet, controls={name: packet[name] for name in ("ds", "gy", "dt")},
                            baseline=baseline, truth=truth["truth"], passages=points, sigma_b=cell["sigma_b"])
    return cases


def model_env(base):
    from qclean_uwb.fp_sc.e0_baseline import SPEC, load_original_model

    if SPEC != {"anchor": (10., 0., 2.65), "robot_z_m": .45, "mount_deg": 0.}:
        raise ValueError("Wrong SourceFFD geometry")
    core, online, model, hashes = load_original_model(base["native"])
    return (core, online, model, SPEC), hashes


def run_hfki(case, native, **parameters):
    from hfki_replay import check_trace, replay
    from replay_s2 import validate_trace

    trace = replay(case["packet"], case["controls"], case["baseline"], *native, **parameters)
    checks = check_trace(trace, case["packet"], case["controls"], case["baseline"], **parameters)
    validate_trace(trace)
    return trace, checks


def seed_packets(out, cases):
    from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments, rng

    readiness = read(READINESS)
    cfg = SensorV2Config(level=1, condition="noise_pair", common_scale=0., bias_rw_rad_s_sqrt_s=0.)
    manifest = {}
    for route, case in cases.items():
        p, truth = case["packet"], case["truth"]
        t = p["t"]
        ds, angle = motion_increments(t, truth, convention="legacy-euler")
        for seed in SEEDS:
            controls, latent = generate(t, ds, angle, cfg, seed)
            x0 = truth[0] + rng(seed, "initial").standard_normal(3) * [.1, .1, math.radians(5.)]
            x0[2] = (x0[2] + math.pi) % (2. * math.pi) - math.pi
            new = p | dict(ds=controls["ds_odom"], gy=controls["dtheta_gyro"], dt=controls["dt_s"], x0=np.r_[x0, 0.])
            np.testing.assert_array_equal(latent["true_bias_rad_s"], 0.)
            fields = readiness["routes"][route]["in_memory_seed_probes"][str(seed)]["fields_sha256"]
            if not all(array_sha(new[name]) == digest for name, digest in fields.items()):
                raise ValueError(f"{route}/{seed}: candidate differs from readiness probe")
            path = out / f"{route}_B0_Full_{seed}__online.npz"
            np.savez_compressed(path, **new)
            reloaded = arrays(path)
            if set(reloaded) != set(KEYS) or any(not np.array_equal(new[key], reloaded[key]) for key in KEYS):
                raise ValueError(f"{path}: readback differs")
            manifest[path.name] = item(path)
    return manifest


def stage0(out, lock, cases, native):
    from hfki_replay import replay

    checks = {}
    for route, case in cases.items():
        trace, record = run_hfki(case, native, sigma_deg=0.)
        checks[route] = dict(zero_sigma=parity(trace, case["baseline"]), kernel_zero=record,
                             passages=case["passages"], mask_count=int(trace["mask"].sum()))
        print("Stage 0", route, "zero-sigma parity passed", flush=True)
    rpt = cases["R4"]
    a, c1 = (arrays(checked(lock["oracle"][name])) for name in ("V3_a", "C1_KI"))
    for reference in (a, c1):
        grid_equal(rpt["packet"], reference)
        np.testing.assert_array_equal(reference["mask"], rpt["baseline"]["mask"])
    oracle = dict(Reff=a["Reff"], V=a["V_l_op"], hazard=a["hazard"][:, 1])
    reproduced, test = run_hfki(rpt, native, sigma_deg=0., oracle=oracle)
    checks["C1_KI"] = dict(parity=parity(reproduced, c1), kernel=test)
    print("Stage 0 C1 schedule parity passed", flush=True)
    # A nonzero kernel and intentional future input change on a short prefix.
    n, cut = 96, 64
    p = {name: value if name in ("P0", "x0") else value[:n].copy() for name, value in rpt["packet"].items()}
    small = dict(packet=p, controls={name: p[name] for name in ("ds", "gy", "dt")},
                 baseline={name: value[:n] for name, value in rpt["baseline"].items()})
    trace, test = run_hfki(small, native, sigma_deg=4.)
    modified = {name: value.copy() for name, value in p.items()}
    modified["z"][cut:, :] += .01
    modified["ds"][cut:] += .001
    modified["truth"] = np.full((n, 3), np.nan)
    alt = replay(modified, {name: modified[name] for name in ("ds", "gy", "dt")}, small["baseline"],
                 *native, sigma_deg=4.)
    for name, value in trace.items():
        np.testing.assert_array_equal(value[:cut], alt[name][:cut])
    checks["nonzero"] = dict(kernel=test, prefix_invariance_rows=cut, poison_extra_truth="ignored")
    manifest = seed_packets(out, cases)
    write(out / "CHECKS.json", dict(status="PASS_IMPLEMENTATION", checks=checks, seed_packets=manifest,
                                  evaluator_shared_by_route=True))
    print("Stage 0 12 separately seeded online input NPZs verified", flush=True)


def stage1(out, lock, cases):
    from hfki_predict import predict
    from qclean_uwb.fp_sc.e0_baseline import SPEC

    d3 = {route: arrays(checked(lock["d3"][route])) for route in ROUTES}
    c1 = arrays(checked(lock["oracle"]["C1_KI"]))
    prepared = {route: case | {"loro": case["baseline"], "spec": SPEC} for route, case in cases.items()}
    result = predict(prepared, d3, c1)
    write(out / "PREDICT.json", result)
    print("Stage 1 trace-only prediction and donor tables complete", flush=True)


def density(case, native, multiplier=1.):
    from exposure_replay import check_trace, replay
    from replay_s2 import validate_trace

    p, controls, baseline = (case[name] for name in ("packet", "controls", "baseline"))
    reference = baseline
    if multiplier != 1.:
        variance = baseline["Reff"].copy()
        variance[:, 1, 1] *= multiplier
        reference = baseline | {"Reff": variance}
    trace = replay(p, controls, reference, *native, "I", .5)
    check = check_trace(trace, p, controls, reference, "I", .5)
    trace["s_infl"] = trace["Reff"][:, 1, 1] / baseline["Reff"][:, 1, 1]
    validate_trace(trace)
    return trace, check


def save_trace(out, route, arm, case, trace):
    packet = case["packet"]
    ready = {"t": packet["t"], "pose_id": packet["pose_id"]} | trace
    grid_equal(packet, ready)
    np.savez_compressed(out / f"{route}_{arm}.npz", **ready)


def scores(traces, cases):
    from exposure_score import _gates, branch_metrics
    from ks_diagnostics import RMSE, scores_with_blocks
    from verify_s2 import from_trace

    rows, times, branches = {}, {}, {}
    for route, by_arm in traces.items():
        case = cases[route]
        truth, t = case["truth"], case["packet"]["t"]
        rows[route], times[route], branches[route] = {}, t, {}
        for arm, trace in by_arm.items():
            np.testing.assert_array_equal(trace["mask"], by_arm["BASE"]["mask"])
            rows[route][arm] = from_trace(trace, truth)
            branches[route][arm] = branch_metrics(trace, truth, t)
            if len(branches[route][arm]["passages"]) != PASSES[route]:
                raise ValueError("Passage count differs")
    arms = list(next(iter(rows.values())))
    result = scores_with_blocks(rows, times, [(arm, "BASE") for arm in arms if arm != "BASE"], blocks=(5, 10, 20))
    gates, accuracy = {}, {}
    for arm in arms:
        gates[arm], accuracy[arm] = {}, {}
        for group, point in result["point"].items():
            pooled = group == "pooled"
            groups = list(rows) if pooled else [group]
            count = sum(branches[route][arm]["mirror_fail_count"] for route in groups)
            gate = _gates(point, result["blocks"]["10"]["by_group"][group], arm, pooled, count)
            gates[arm][group] = gate
            max_ratio = max(point[arm][name] / point["BASE"][name] for name in RMSE)
            label = "ACCURACY_PASS" if gate["accuracy_ok"] else "ACCURACY_FAIL"
            if pooled and 1.10 < max_ratio <= 1.25:
                label = "ACCURACY_MARGINAL"
            accuracy[arm][group] = label
    return result | dict(branch=branches, gates=gates, accuracy=accuracy)


def adjacent(values):
    runs = []
    for sigma in GRID:
        if sigma in values:
            if GRID[0] == sigma or GRID[GRID.index(sigma) - 1] not in values:
                runs.append([])
            runs[-1].append(sigma)
    return runs


def band(scores):
    gates = scores["gates"]
    groups = [*ROUTES, "pooled"]
    each = {group: [sigma for sigma in GRID if gates[f"A2_{sigma}"][group]["pass"]] for group in groups}
    integrity = {group: [sigma for sigma in GRID if gates[f"A2_{sigma}"][group]["integrity_ok"]] for group in groups}
    joint = [sigma for sigma in GRID if all(sigma in each[group] for group in groups)]
    joint_integrity = [sigma for sigma in GRID if all(sigma in integrity[group] for group in groups)]
    runs = adjacent(joint)
    passing = [values for values in runs if len(values) >= 3]
    if len(passing) > 1:
        raise ValueError("More than one disjoint passing band with the frozen grid")
    selected = passing[0][(len(passing[0]) - 1) // 2] if passing else 4
    status = "BAND_PASS" if passing else "SINGLE_POINT" if len(joint) == 1 else "NO_BAND"
    return dict(status=status, sigma_star_deg=selected, bands_deg=passing, joint_pass_deg=joint,
                adjacent_runs_deg=runs, pass_by_group_deg=each, integrity_by_group_deg=integrity,
                joint_integrity_deg=joint_integrity,
                common_route_pass_deg=[sigma for sigma in GRID if all(sigma in each[group] for group in ROUTES)],
                all_routes_have_passing_point=all(each[group] for group in ROUTES))


def nominal_polarization_information(trace, g=None):
    selected = trace["mask"] & trace.get("s_updated", trace["mask"])
    sensitivity = np.abs(trace["H"][:, 1, 2]) if g is None else g
    return float(np.sum(sensitivity[selected]**2 / trace["Reff"][selected, 1, 1]))


def final_stage2_scores(common, extra, cases, old_m1d):
    main = scores(common, cases)
    extras = {arm: scores({route: {"BASE": common[route]["BASE"], arm: trace}}, cases)
              for arm, (route, trace) in extra.items()}
    r4 = main["point"]["R4"]
    allocation = {str(sigma): dict(A2u_minus_A2_heading_pp=100. * (r4[f"A2u_{sigma}"]["heading95_coverage"] -
                                                                  r4[f"A2_{sigma}"]["heading95_coverage"]))
                  for sigma in GRID}
    for value in allocation.values():
        value["supports_E_ALLOC"] = value["A2u_minus_A2_heading_pp"] >= 5.
    _, x1 = extra["X1"]
    fixed_g = np.abs(cases["R5"]["baseline"]["H"][:, 1, 2])
    nominal = {
        label: dict(fixed_E0LORO_g=nominal_polarization_information(candidate, fixed_g),
                    own_prior_g=nominal_polarization_information(candidate))
        for label, candidate in (("M1_D", old_m1d), ("X1", x1))}
    x1_mirror = extras["X1"]["branch"]["R5"]["X1"]["mirror_fail_count"]
    comparison_ok = nominal["X1"]["fixed_E0LORO_g"] < nominal["M1_D"]["fixed_E0LORO_g"]
    return dict(common=main, isolated=extras, E_ALLOC=allocation,
                X1=dict(mirror_fail_count=x1_mirror, nominal_information_rad_inv2=nominal,
                        fixed_g_nominal_information_below_M1D=comparison_ok,
                        plan_readout="SUPPORTS_E_INFO" if x1_mirror else "REJECTS_E_INFO_IN_FROZEN_COMPARISON"))


def stage2(out, lock, cases, native):
    common, extra, checks = {}, {}, {}
    for route, case in cases.items():
        old = arrays(checked(lock["exposure"][route]))
        trace, row = density(case, native)
        checks[route] = {"A1": row | {"identity": parity(trace, old, NAV + ("F", "g", "dwell", "s_updated"))}}
        common[route] = dict(BASE=case["baseline"], A1=trace)
        save_trace(out, route, "BASE", case, case["baseline"])
        save_trace(out, route, "A1", case, trace)
        for label, uniform in (("A2", False), ("A2u", True)):
            for sigma in GRID:
                arm = f"{label}_{sigma}"
                candidate, checks[route][arm] = run_hfki(case, native, sigma_deg=sigma, uniform=uniform)
                common[route][arm] = candidate
                save_trace(out, route, arm, case, candidate)
        print("Stage 2", route, "A1 parity, A2 and A2u grids complete", flush=True)
    choice = band(scores(common, cases))
    write(out / "BAND.json", choice)
    sigma = choice["sigma_star_deg"]
    print("Stage 2 A2 interim band", choice["status"], "sigma_star", sigma, flush=True)
    for route, case in cases.items():
        table = lock["A3_donor_tables"][route]["table"]
        candidate, checks[route]["A3"] = run_hfki(case, native, sigma_deg=sigma, range_table=table)
        common[route]["A3"] = candidate
        save_trace(out, route, "A3", case, candidate)
    a4, checks["R4"]["A4"] = run_hfki(cases["R4"], native, sigma_deg=sigma, yaw_length_deg=float("inf"))
    x1, checks["R5"]["X1"] = density(cases["R5"], native, multiplier=lock["parameters"]["X1_multiplier"])
    extra = {"A4": ("R4", a4), "X1": ("R5", x1)}
    for arm, (route, trace) in extra.items():
        save_trace(out, route, arm, cases[route], trace)
    write(out / "CHECKS.json", checks)
    write(out / "SCORES.json", final_stage2_scores(common, extra, cases, arrays(checked(lock["exposure"]["R5_D05"]))))
    print("Stage 2 A3, A4, X1 and final scores complete", flush=True)


def execute(stage, out):
    base = bindings()
    lock = auth(out, stage)
    receipt_file = out / "EXECUTION.json"
    if receipt_file.exists():
        raise FileExistsError(receipt_file)
    receipt = dict(stage=stage, started_utc=utc(), command=sys.argv, contract_sha256=sha(out / "RUN_CONTRACT.json"),
                   software=dict(python=sys.version, numpy=np.__version__))
    try:
        cases = cases_from(lock)
        if stage == 1:
            stage1(out, lock, cases)
        else:
            native, receipt["native_source_hashes"] = model_env(base)
            {0: stage0, 2: stage2}[stage](out, lock, cases, native)
        receipt.update(status="PASS_EXECUTION", exit_code=0)
    except Exception as exc:
        import traceback

        receipt.update(status="FAIL_EXECUTION", exit_code=1, error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        receipt["finished_utc"] = utc()
        receipt["outputs"] = {path.name: sha(path) for path in sorted(out.iterdir()) if path.is_file() and path.name != "RUN_CONTRACT.json"}
        write(receipt_file, receipt)


def verify(stage, out):
    bindings()
    from replay_s2 import validate_trace

    lock = auth(out, stage)
    record = read(out / "EXECUTION.json")
    if record["status"] != "PASS_EXECUTION" or record["contract_sha256"] != sha(out / "RUN_CONTRACT.json"):
        raise ValueError(f"Stage {stage}: execution did not pass")
    for name, digest in record["outputs"].items():
        checked(dict(path=out / name, sha256=digest))
    cases = cases_from(lock)
    details = {}
    if stage == 0:
        checks = read(out / "CHECKS.json")
        if checks["status"] != "PASS_IMPLEMENTATION" or len(checks["seed_packets"]) != 12:
            raise ValueError("Incomplete Stage 0 evidence")
        for route, case in cases.items():
            for seed in SEEDS:
                name = f"{route}_B0_Full_{seed}__online.npz"
                candidate = arrays(checked(checks["seed_packets"][name]))
                if set(candidate) != set(KEYS):
                    raise ValueError("Unexpected candidate NPZ fields")
                for field in ("t", "pose_id", "z", "muBASE", "muMB", "R", "D", "P0"):
                    np.testing.assert_array_equal(candidate[field], case["packet"][field])
        details["source_and_output_checks"] = "passage counts, implementation check receipt, 12 candidate packets"
    elif stage == 1:
        from hfki_predict import predict
        from qclean_uwb.fp_sc.e0_baseline import SPEC

        prepared = {route: case | {"loro": case["baseline"], "spec": SPEC} for route, case in cases.items()}
        d3 = {route: arrays(checked(lock["d3"][route])) for route in ROUTES}
        c1 = arrays(checked(lock["oracle"]["C1_KI"]))
        if predict(prepared, d3, c1) != read(out / "PREDICT.json"):
            raise ValueError("Stage 1 reaggregation differs")
        details["source_and_output_checks"] = "prediction and donor reaggregation"
    else:
        from hfki_replay import check_trace

        choice = read(out / "BAND.json")
        common, extra = {}, {}
        all_arms = ("BASE", "A1", *(f"A2_{deg}" for deg in GRID), *(f"A2u_{deg}" for deg in GRID), "A3")
        for route, case in cases.items():
            common[route] = {}
            for arm in all_arms:
                trace = arrays(out / f"{route}_{arm}.npz")
                grid_equal(case["packet"], trace)
                validate_trace(trace)
                common[route][arm] = trace
                if arm.startswith("A2") or arm == "A3":
                    kwargs = {"range_table": lock["A3_donor_tables"][route]["table"]} if arm == "A3" else {
                        "uniform": arm.startswith("A2u")}
                    degrees = choice["sigma_star_deg"] if arm == "A3" else int(arm.split("_")[1])
                    check_trace(trace, case["packet"], case["controls"], case["baseline"], sigma_deg=degrees, **kwargs)
                elif arm == "A1":
                    parity(trace, arrays(checked(lock["exposure"][route])), NAV + ("F", "g", "dwell", "s_updated"))
                else:
                    parity(trace, case["baseline"])
        for name, route in (("A4", "R4"), ("X1", "R5")):
            trace = arrays(out / f"{route}_{name}.npz")
            grid_equal(cases[route]["packet"], trace)
            validate_trace(trace)
            extra[name] = (route, trace)
            if name == "A4":
                case = cases[route]
                check_trace(trace, case["packet"], case["controls"], case["baseline"],
                            sigma_deg=choice["sigma_star_deg"], yaw_length_deg=float("inf"))
            else:
                np.testing.assert_allclose(trace["s_infl"], 4. * trace["F"], rtol=0., atol=TOL)
        recalculated = final_stage2_scores(common, extra, cases, arrays(checked(lock["exposure"]["R5_D05"])))
        if recalculated != read(out / "SCORES.json") or band(recalculated["common"]) != choice:
            raise ValueError("Stage 2 saved scores or band differ")
        details |= dict(trace_count=3 * len(all_arms) + len(extra), reaggregated="scores, paired block intervals, gates and band")
    result = dict(stage=stage, status="PASS_VERIFICATION", role="IMPLEMENTER_SELF_CHECK", verified_utc=utc(),
                  inputs_and_execution={name: sha(out / name) for name in ("RUN_CONTRACT.json", "EXECUTION.json")},
                  output_hashes=len(record["outputs"]), details=details)
    write(out / "VERIFICATION.json", result)
    print("Stage", stage, "verification passed for", result["output_hashes"], "outputs", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("freeze", "run", "verify", "pipeline"))
    parser.add_argument("stage", type=int, choices=(0, 1, 2))
    args = parser.parse_args()
    if args.phase == "pipeline":
        for stage in range(args.stage, 3):
            out = ROOT / f"stage{stage}"
            freeze(stage, out)
            execute(stage, out)
            verify(stage, out)
        return
    out = ROOT / f"stage{args.stage}"
    {"freeze": freeze, "run": execute, "verify": verify}[args.phase](args.stage, out)


if __name__ == "__main__":
    main()
