"""Freeze and run the mount-0 G1-INT-001 exposure diagnostics."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

import numpy as np


ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
DIAG = ROOT.parent / "G1_INT_DIAG_001_20261115"
PUBLICATION = WORK / "g1_mount45_b0_publication_20261116"
STRUCTURE = DIAG / "structure_sc_ki" / "RUN_CONTRACT.json"
SPEC_REV = "71f2d1e"
SPEC_NAME = "SPEC_EXPOSURE_M1_M4_KO.md"
SPEC_PATH = f"research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/{SPEC_NAME}"
KS = DIAG / "continuation_ks"
FOLLOWUP = DIAG / "continuation_checks_c1_c8"
ROUTES = ("R2", "R4", "R5")
SCOPE = dict(anchor="B", bias="B0", routes=list(ROUTES), rf="Full", seed=10, mount_deg=0.)
COUNTS = {"R2": (971, 979), "R4": (728, 742), "R5": (1384, 1415)}
ARMS = {"D05": ("D", .5), "D10": ("D", 1.), "D20": ("D", 2.),
        "D025": ("D", .25), "G05": ("G", .5), "I05": ("I", .5)}
M2_ARMS = ("BASE", "FULL", "H", "L")
ONLINE_KEYS = ("t", "pose_id", "z", "muMB", "x0", "P0", "ds", "gy", "dt")
TRACE_KEYS = ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S", "mask")


def utc():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def item(path):
    return dict(path=str(path), sha256=sha(path))


def checked(record):
    path = Path(record["path"])
    if sha(path) != record["sha256"]:
        raise ValueError(f"SHA-256 differs for {path}")
    return path


def output_of(execution, filename):
    path = execution.parent / filename
    checked(dict(path=path, sha256=read(execution)["outputs"][filename]))
    return item(path)


def grid(reference, other):
    if any(not np.array_equal(reference[key], other[key]) for key in ("t", "pose_id")):
        raise ValueError("Mismatched packet grid")


def bind_structure():
    sys.path.insert(0, str(STRUCTURE.parent))
    from run_structure import authenticate, cases_from

    structure, base = authenticate(STRUCTURE)
    if structure["scope"] != SCOPE or tuple(cell["route"] for cell in structure["cells"]) != ROUTES:
        raise ValueError("The structure contract does not bind mount 0 B/B0 seed 10")
    sys.path[:0] = [str(KS), str(DIAG / "continuation_d2_d3")]
    return structure, base, cases_from


def freeze(lock_path):
    if lock_path.exists():
        raise FileExistsError(lock_path)
    structure, base, _ = bind_structure()
    rev = subprocess.check_output(["git", "-C", str(PUBLICATION), "rev-parse", f"{SPEC_REV}^{{commit}}"],
                                  text=True).strip()
    spec = subprocess.check_output(["git", "-C", str(PUBLICATION), "show", f"{rev}:{SPEC_PATH}"])
    snapshot = ROOT / SPEC_NAME
    if snapshot.exists():
        if snapshot.read_bytes() != spec:
            raise ValueError("Specification snapshot differs from Git")
    else:
        with snapshot.open("xb") as stream:
            stream.write(spec)

    v3_receipt = KS / "run_03" / "EXECUTION.json"
    v3_contract = KS / "RUN_CONTRACT_RETRY_03.json"
    c1_receipt = FOLLOWUP / "run_01" / "EXECUTION.json"
    c1_contract = FOLLOWUP / "RUN_CONTRACT_C1_C6.json"
    c1_validation = FOLLOWUP / "VERIFICATION.json"
    v3, c1 = read(v3_receipt), read(c1_receipt)
    if (v3["status"] != "PASS_EXECUTION" or "V3" not in v3["completed_stages"]
            or v3["contract_sha256"] != sha(v3_contract)):
        raise ValueError("V3(a) execution and contract do not match")
    if ("C1" not in c1["completed"] or c1["contract_sha256"] != sha(c1_contract)
            or read(c1_validation)["status"] != "PASS_REAGGREGATION"):
        raise ValueError("C1 execution and reaggregation evidence do not match")
    source_files = [Path(__file__), ROOT / "exposure_replay.py", ROOT / "exposure_score.py",
                    STRUCTURE.parent / "run_structure.py", DIAG / "d1_shuffle.py", DIAG / "d0_d5.py",
                    DIAG / "continuation_d2_d3" / "d2.py", DIAG / "continuation_d2_d3" / "d3.py",
                    KS / "ks_diagnostics.py", FOLLOWUP / "run_followup.py"]
    source_files += [Path(base["s2"]) / f"{name}.py" for name in ("metrics_s2", "verify_s2", "replay_s2")]
    cells = [{key: cell[key] for key in ("route", "online", "evaluator", "fixed_gate_trace", "loro_trace")}
             for cell in structure["cells"]]
    contract = dict(
        question="G1-INT-001/EXPOSURE M1–M4", role="IMPLEMENTER", classification="DIAGNOSTIC_ONLY",
        frozen_utc=utc(), scope=SCOPE, specification=dict(commit=rev, path=SPEC_PATH, snapshot=item(snapshot)),
        parents=[item(path) for path in (STRUCTURE, DIAG / "RUN_CONTRACT.json", v3_contract, v3_receipt,
                                        c1_contract, c1_receipt, c1_validation)],
        sources=[item(path) for path in source_files], model_assets=structure["model_assets"],
        governance=structure["governance"], cells=cells,
        oracle=dict(V3_a=output_of(v3_receipt, "V3_a.npz"), C1_KI=output_of(c1_receipt, "C1_R4_KI.npz"),
                    c1_scores=output_of(c1_receipt, "C1.json"),
                    schedule="V3(a) Reff_ss + V_l_op + causal_s; fixed by R4 packet index"),
        gate=dict(fixed=True, counts=COUNTS, rejects="predict-only", score_grid="all packets"),
        online_fields=ONLINE_KEYS, reference_noise="frozen E0-LORO per-packet Reff",
        arms=ARMS, primary="D05", yaw_deg=10., g_threshold_s_per_rad=1.5, dwell_s=10.,
        dwell_bounds=[.2, .6], density_history=dict(s=10., accepted_cap=100, current_excluded=True),
        bootstrap=dict(seconds=[5, 10, 20], draws=1500, seed=20261115, paired=True, reference_if_full_blocks_below=8),
        rules=dict(route=dict(coverage=["heading", "XY", "pose"], min=.75, ci10_lower_min=.60,
                              rmse_ratio_max=1.25, max_mirror=0),
                   pooled=dict(coverage=["heading", "pose"], min=.90, ci10_lower_min=.80,
                               nees3=[1.5, 6.0], rmse_ratio_max=1.10, max_mirror=0),
                   branch=dict(crossing_x_m=10., adjacent_crossing_bound=True, mirror_duration_s=2.,
                               mirror_y_truth_min_m=.2, warning_seconds_before=5., warning_abs_z=3.,
                               expected_counts={"R2": 2, "R4": 1, "R5": 3})),
        M2=dict(high_fraction_min=.9, both_fraction_min=.5, improvement_metric="R4 heading95"),
        M3=dict(ells_m=[.5, 1., 2.], target_median=20.4, target_p95=42.8, median_ratio_bounds=[.5, 2.],
                reference_group="R4 dwell >= 0.6, accepted packets, ell=0.5 m; report full grid too",
                heading_sigma_approximation="1/sqrt(sum accepted g^2/(R_ss*F)) on fixed E0-LORO path "
                "within causal inclusive 10 s; conditional polarization-only, no cross-state/process covariance"),
        preflight=dict(tol=1e-10, disabled=["D ell=0", "I ell=0"], c1_replay="FULL",
                       scalar_check="independent reconstruction on truncated R4 preflight and all D/G runs"),
        stop_gates=dict(S2_prime="STOP", Step3="HOLD", sealed=["G-T2", "G-V"], adaptive_innovation=False))
    write(lock_path, contract)
    print(f"Frozen contract {lock_path.name}: {sha(lock_path)}", flush=True)


def authenticate(lock_path):
    from replay_s2 import read_npz
    lock = read(lock_path)
    structure, base, _ = bindings
    for receipt in lock["sources"] + lock["parents"] + lock["governance"] + list(lock["model_assets"].values()):
        checked(receipt)
    checked(lock["specification"]["snapshot"])
    if lock["scope"] != structure["scope"] or set(lock["online_fields"]) != set(ONLINE_KEYS):
        raise ValueError("Input scope or online interface drifted")
    for cell in lock["cells"]:
        if cell not in [{key: row[key] for key in cell} for row in structure["cells"]]:
            raise ValueError("Cell provenance drifted")
        for key in ("online", "evaluator", "fixed_gate_trace", "loro_trace"):
            checked(cell[key])
    oracle = {key: read_npz(checked(lock["oracle"][key])) for key in ("V3_a", "C1_KI")}
    checked(lock["oracle"]["c1_scores"])
    return lock, base, oracle


def load_inputs(lock, cases_from, structure):
    from exposure_score import crossings
    from replay_s2 import read_npz

    cases, truth, times, pass_points = {}, {}, {}, {}
    for route, case in cases_from(structure).items():
        cell = next(cell for cell in lock["cells"] if cell["route"] == route)
        packet = {key: case["packet"][key] for key in ONLINE_KEYS}
        baseline = {key: case["loro"][key] for key in TRACE_KEYS + ("t", "pose_id")}
        if case["spec"] != {"anchor": (10., 0., 2.65), "robot_z_m": .45, "mount_deg": 0.}:
            raise ValueError(f"{route}: unexpected SourceFFD geometry")
        if (int(baseline["mask"].sum()), len(packet["t"])) != COUNTS[route]:
            raise ValueError(f"{route}: unexpected gate count")
        evaluator = read_npz(checked(cell["evaluator"]))
        grid(packet, evaluator)
        times[route], truth[route] = packet["t"], evaluator["truth"]
        pass_points[route] = crossings(truth[route], times[route])
        if len(pass_points[route]) != lock["rules"]["branch"]["expected_counts"][route]:
            raise ValueError(f"{route}: unexpected passage count")
        cases[route] = (packet, case["controls"], baseline, case["spec"])
    return cases, truth, times, pass_points


def oracle_schedule(oracle, baseline):
    a, c1 = oracle["V3_a"], oracle["C1_KI"]
    for trace in (a, c1):
        grid(baseline, trace)
        np.testing.assert_array_equal(trace["mask"], baseline["mask"])
    variance = a["Reff"][:, 1, 1] + a["V_l_op"] + a["causal"][:, 1]
    np.testing.assert_array_equal(variance, c1["Reff"][:, 1, 1])
    np.testing.assert_array_equal(c1["Reff"][:, 0, 0], baseline["Reff"][:, 0, 0])
    if not np.isfinite(variance).all() or np.any(variance <= 0.):
        raise ValueError("Invalid oracle variance")
    return variance


def apply(case, model_env, mode, ell=.5, oracle_variance=None):
    from exposure_replay import check_trace, replay

    packet, controls, baseline, spec = case
    trace = replay(packet, controls, baseline, *model_env, spec, mode, ell, oracle_variance)
    checks = check_trace(trace, packet, controls, baseline, mode, ell, oracle_variance)
    return trace, checks


def truncate(case, count):
    packet, controls, baseline, spec = case
    p = {key: value if key in ("x0", "P0") else value[:count] for key, value in packet.items()}
    u = {key: value if key == "x0" else value[:count] for key, value in controls.items()}
    return p, u, {key: value[:count] for key, value in baseline.items()}, spec


def preflight(cases, model_env, oracle, variance, passages):
    from exposure_replay import check_parity

    identity, bases = {}, {}
    for route, case in cases.items():
        baseline = case[2]
        base, _ = apply(case, model_env, "D", 0.)
        unit_density, _ = apply(case, model_env, "I", 0.)
        np.testing.assert_array_equal(unit_density["F"], 1.)
        identity[route] = dict(D_disabled=check_parity(base, baseline),
                               I_unit_density=check_parity(unit_density, baseline))
        bases[route] = base
        print(f"{route}: E0-LORO parity passed for disabled D and unit-density I", flush=True)
    full, full_check = apply(cases["R4"], model_env, "FULL", oracle_variance=variance)
    identity["R4"]["C1_KI"] = check_parity(full, oracle["C1_KI"])
    sample, scalar_check = apply(truncate(cases["R4"], 64), model_env, "D", .5)
    if not np.any(sample["mask"] & ~sample["s_updated"]):
        raise ValueError("Preflight did not exercise the scalar update")
    return bases, full, dict(status="PASS", identity=identity, counts=COUNTS, passages=passages,
                             r4_scalar_update=scalar_check, c1_full_replay=full_check,
                             online_fields=ONLINE_KEYS, evaluator_usage="grid, passage count, offline scoring only")


def score_m2(traces, truth, times):
    from exposure_score import branch_metrics
    from ks_diagnostics import scores_with_blocks
    from verify_s2 import from_trace

    route = "R4"
    rows = {arm: from_trace(traces[arm], truth[route]) for arm in M2_ARMS}
    result = scores_with_blocks({route: rows}, {route: times[route]},
                                [(arm, "BASE") for arm in M2_ARMS[1:]], blocks=(5, 10, 20))
    point = result["point"][route]
    coverage = {arm: point[arm]["heading95_coverage"] for arm in M2_ARMS}
    delta = {arm: coverage[arm] - coverage["BASE"] for arm in M2_ARMS[1:]}
    if delta["FULL"] <= 0.:
        raise ValueError("C1 KI reference improvement is not positive")
    ratios = {arm: delta[arm] / delta["FULL"] for arm in ("H", "L")}
    status = "LOCATION_OTHER"
    if ratios["H"] >= .9 and ratios["L"] < .5:
        status = "LOCATION_HIGH_G"
    elif min(ratios.values()) >= .5:
        status = "LOCATION_BOTH"
    return result | dict(status=status, classification="ORACLE_DIAGNOSTIC_ONLY", improvement=delta,
                         improvement_fraction_of_full=ratios,
                         oracle_assignment=dict(H=int(np.sum(traces["H"]["mask"] & (traces["H"]["g"] >= 1.5))),
                                                L=int(np.sum(traces["L"]["mask"] & (traces["L"]["g"] < 1.5)))),
                         branch={arm: branch_metrics(traces[arm], truth[route], times[route]) for arm in M2_ARMS})


def distribution(values):
    if not len(values):
        return dict(n=0, median=None, p95=None)
    median, p95 = np.quantile(values, [.5, .95])
    return dict(n=len(values), median=float(median), p95=float(p95))


def score_m3(lock, cases, truth, variance):
    from d3 import motion_arcs
    from exposure_replay import density_factors, dwell_fraction
    from replay_s2 import wrap

    scores, data = {}, {}
    for route, (packet, _, trace, _) in cases.items():
        t, mask = packet["t"], trace["mask"]
        g = np.abs(trace["H"][:, 1, 2])
        dwell = dwell_fraction(t, g)
        arc, _ = motion_arcs(packet, trace)
        error = np.rad2deg(np.abs(wrap(trace["x"][:, 2] - truth[route][:, 2])))
        first = np.searchsorted(t, t - lock["dwell_s"], side="left")
        bins = {"lt_0.2": dwell < .2, "0.2_to_lt_0.6": (.2 <= dwell) & (dwell < .6), "ge_0.6": dwell >= .6}
        output = dict(t=t, pose_id=packet["pose_id"], mask=mask, g=g, dwell=dwell, arc=arc, heading_abs_error_deg=error)
        stats = {"F": {}}
        for ell in lock["M3"]["ells_m"]:
            f = density_factors(t, arc, mask, ell)
            info = mask * g**2 / (trace["Reff"][:, 1, 1] * f)
            running = np.r_[0., np.cumsum(info)]
            window_info = running[1:] - running[first]
            sigma = np.full(len(t), np.nan)
            valid = window_info > 0
            sigma[valid] = np.rad2deg(1. / np.sqrt(window_info[valid]))
            key = str(ell)
            output[f"F_{key}"], output[f"heading_sigma_deg_{key}"] = f, sigma
            stats["F"][key] = {}
            for label, select in bins.items():
                sigma_rows = select & valid
                stats["F"][key][label] = dict(
                    full_grid=distribution(f[select]), accepted=distribution(f[select & mask]),
                    heading_abs_error_deg=distribution(error[select]),
                    approximate_heading_sigma_deg=distribution(sigma[sigma_rows]),
                    abs_error_over_approximate_sigma=distribution(error[sigma_rows] / sigma[sigma_rows]))
        if route == "R4":
            ratio = variance / trace["Reff"][:, 1, 1]
            output["c1_variance_ratio"] = ratio
            stats["c1_accepted_ratio"] = distribution(ratio[mask])
            stats["c1_ratio_by_bin"] = {label: distribution(ratio[mask & select]) for label, select in bins.items()}
        scores[route], data[route] = stats, output
    m3 = lock["M3"]
    selected = scores["R4"]["F"]["0.5"]["ge_0.6"]["accepted"]
    relative = selected["median"] / m3["target_median"]
    return dict(status="ACCOUNTING_CONSISTENT" if m3["median_ratio_bounds"][0] <= relative <= m3["median_ratio_bounds"][1]
                else "ACCOUNTING_INCONSISTENT", reference=m3, selected=selected, ratio_of_target=relative, routes=scores), data


def save_trace(path, case, trace):
    packet = case[0]
    np.savez_compressed(path, t=packet["t"], pose_id=packet["pose_id"], **trace)


def run(lock_path, out):
    from exposure_score import evaluate
    from qclean_uwb.fp_sc.e0_baseline import load_original_model

    lock, base, oracle = authenticate(lock_path)
    structure, _, cases_from = bindings
    out.mkdir(exist_ok=False)
    receipt = dict(question=lock["question"], started_utc=utc(), contract_sha256=sha(lock_path),
                   command=sys.argv, python=sys.version, numpy=np.__version__, completed=[])
    try:
        cases, truth, times, passages = load_inputs(lock, cases_from, structure)
        core, online, model, receipt["native_source_hashes"] = load_original_model(base["native"])
        env = core, online, model
        variance = oracle_schedule(oracle, cases["R4"][2])
        bases, full, checks = preflight(cases, env, oracle, variance, passages)
        write(out / "PREFLIGHT.json", checks)
        receipt["completed"].append("PREFLIGHT")
        traces, replay_checks = {}, {}
        for route, case in cases.items():
            traces[route] = {"BASE": bases[route]}
            save_trace(out / f"{route}_BASE.npz", case, bases[route])
            replay_checks[route] = {}
            for label, (mode, ell) in lock["arms"].items():
                trace, check = apply(case, env, mode, ell)
                save_trace(out / f"{route}_{label}.npz", case, trace)
                traces[route][label], replay_checks[route][label] = trace, check
            print(f"{route}: six M1/M4 arms and scalar checks complete", flush=True)
        write(out / "REPLAY_CHECKS.json", replay_checks)
        write(out / "M1_M4.json", evaluate(traces, truth, times))
        receipt["completed"].append("M1_M4")

        m2_traces = dict(BASE=bases["R4"], FULL=full)
        save_trace(out / "R4_M2_FULL.npz", cases["R4"], full)
        for mode in ("H", "L"):
            trace, check = apply(cases["R4"], env, mode, oracle_variance=variance)
            m2_traces[mode] = trace
            save_trace(out / f"R4_M2_{mode}.npz", cases["R4"], trace)
            write(out / f"R4_M2_{mode}_CHECK.json", check)
        write(out / "M2.json", score_m2(m2_traces, truth, times))
        receipt["completed"].append("M2")
        print("M2 oracle diagnostics complete", flush=True)

        m3, m3_data = score_m3(lock, cases, truth, variance)
        write(out / "M3.json", m3)
        for route, data in m3_data.items():
            np.savez_compressed(out / f"{route}_M3.npz", **data)
        receipt["completed"].append("M3")
        receipt.update(status="PASS_EXECUTION", exit_code=0)
        print("M3 information accounting complete", flush=True)
    except BaseException as error:
        receipt.update(status="FAIL_EXECUTION", exit_code=1, error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        receipt["finished_utc"] = utc()
        receipt["outputs"] = {path.name: sha(path) for path in sorted(out.iterdir()) if path.is_file()}
        write(out / "EXECUTION.json", receipt)

def verify(lock_path, out):
    from exposure_replay import check_parity, check_trace
    from exposure_score import evaluate
    from replay_s2 import read_npz, validate_trace

    lock, _, oracle = authenticate(lock_path)
    structure, _, cases_from = bindings
    receipt_path = out / "EXECUTION.json"
    receipt = read(receipt_path)
    if (receipt["status"] != "PASS_EXECUTION" or receipt["contract_sha256"] != sha(lock_path)
            or receipt["completed"] != ["PREFLIGHT", "M1_M4", "M2", "M3"]):
        raise ValueError("Incomplete preflight or execution")
    for name, digest in receipt["outputs"].items():
        checked(dict(path=out / name, sha256=digest))
    cases, truth, times, passages = load_inputs(lock, cases_from, structure)
    variance = oracle_schedule(oracle, cases["R4"][2])
    traces, m2_traces = {}, {}
    for route, case in cases.items():
        packet, controls, baseline, _ = case
        traces[route] = {}
        for arm in ("BASE", *ARMS):
            trace = read_npz(out / f"{route}_{arm}.npz")
            grid(packet, trace)
            validate_trace(trace)
            if arm == "BASE":
                check_parity(trace, baseline)
            mode, ell = ARMS.get(arm, ("D", 0.))
            check_trace(trace, packet, controls, baseline, mode, ell)
            traces[route][arm] = trace
    m2_traces["BASE"] = traces["R4"]["BASE"]
    packet, controls, baseline, _ = cases["R4"]
    for arm in M2_ARMS[1:]:
        trace = read_npz(out / f"R4_M2_{arm}.npz")
        grid(packet, trace)
        validate_trace(trace)
        check_trace(trace, packet, controls, baseline, arm, .5, variance)
        m2_traces[arm] = trace
    c1_parity = check_parity(m2_traces["FULL"], oracle["C1_KI"])
    m3, arrays = score_m3(lock, cases, truth, variance)
    for name, observed in {"M1_M4": evaluate(traces, truth, times), "M2": score_m2(m2_traces, truth, times),
                           "M3": m3}.items():
        if read(out / f"{name}.json") != observed:
            raise ValueError(f"{name} reaggregation differs")
    for route, data in arrays.items():
        actual = read_npz(out / f"{route}_M3.npz")
        if data.keys() != actual.keys():
            raise ValueError("M3 output has different fields")
        for field, expected in data.items():
            np.testing.assert_array_equal(actual[field], expected)

    # Independently reconstruct the main point scores from saved pose blocks.
    cutoffs = (7.814727903251179, 5.991464547107979, 1.96)
    observed = read(out / "M1_M4.json")["point"]
    keys = ("heading95_coverage", "xy95_coverage", "pose95_coverage",
            "heading_rmse_deg", "xy_rmse_cm", "mean_nees3")
    deltas = []
    rows_by_arm = {arm: [] for arm in ("BASE", *ARMS)}
    for route, by_arm in traces.items():
        for arm, trace in by_arm.items():
            delta = trace["x"][:, :3] - truth[route]
            delta[:, 2] = (delta[:, 2] + np.pi) % (2 * np.pi) - np.pi
            p3 = trace["P"][:, :3, :3]
            p2, e2 = p3[:, :2, :2], delta[:, :2]
            nees3 = np.einsum("ni,ni->n", delta, np.linalg.solve(p3, delta[..., None])[..., 0])
            nees2 = np.einsum("ni,ni->n", e2, np.linalg.solve(p2, e2[..., None])[..., 0])
            arrays = np.column_stack((np.abs(delta[:, 2]) <= cutoffs[2] * np.sqrt(p3[:, 2, 2]),
                                      nees2 <= cutoffs[1], nees3 <= cutoffs[0],
                                      np.rad2deg(delta[:, 2])**2, (e2**2).sum(axis=1) * 1e4, nees3))
            rows_by_arm[arm].append(arrays)
    for arm, groups in rows_by_arm.items():
        for group, arrays in zip((*ROUTES, "pooled"), (*groups, np.concatenate(groups)), strict=True):
            means = arrays.mean(axis=0)
            means[3:5] = np.sqrt(means[3:5])
            reference = [observed[group][arm][key] for key in keys]
            np.testing.assert_allclose(means, reference, rtol=1e-12, atol=1e-12)
            deltas.append(float(np.max(np.abs(means - reference))))
    result = dict(status="PASS_REAGGREGATION", role="IMPLEMENTER_SELF_CHECK", verified_utc=utc(),
                  contract_sha256=sha(lock_path), execution_sha256=sha(receipt_path),
                  output_hashes=len(receipt["outputs"]), m1_m4_trace_count=sum(map(len, traces.values())),
                  m2_trace_count=len(m2_traces) - 1, c1_replay_parity=c1_parity,
                  checks=["all fixed masks and updates", "M1/M4/M2 point scores and block estimates",
                          "M3 arrays and rollups", "direct-solve point score cross-check"],
                  independent_formula_max_abs=max(deltas), branch_passage_counts={k: len(v) for k, v in passages.items()})
    write(out / "VERIFICATION.json", result)
    print(f"Reaggregation passed, {result['output_hashes']} output hashes verified", flush=True)


def main():
    global bindings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "verify"))
    parser.add_argument("--contract", type=Path, default=ROOT / "RUN_CONTRACT.json")
    parser.add_argument("--out", type=Path, default=ROOT / "run_01")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.contract)
    else:
        bindings = bind_structure()
        {"run": run, "verify": verify}[args.action](args.contract, args.out)


if __name__ == "__main__":
    main()

