"""MODEL-003 v3 signed-s development and prespecified s-only diagnostics."""

import argparse
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_model003_s1 import CASES, open_case
from run_tb3_model003_s2 import PATHS, timeline_data
from run_tb3_model003_s3 import wrap_rad
from run_tb3_model003_v3_s3_range import LEVELS, SEEDS, checkpoint_rows, fit_range, prepare, ready, start_level
from run_tb3_production import utc_now, verify
from tb3_model003_v3_integrity import evaluate_level
from tb3_model003_v3_joint import JointModel, initialize_joint, predict_joint, update_joint
from tb3_model003_v3_m1r import m1r_clipped
from validate_tb3_g4 import load_model


BASES = ("J-V", "J-C", "J-CS", "J-CI")
CANDIDATES = (*BASES, *(a+"+K" for a in BASES), "J-C+T", "J-CS+T", "J-C+K+T", "J-CS+K+T")
JOINT = ("J4", "J4+K", *CANDIDATES)
DIAGNOSTIC = ("S-V", "S-C")


def load_gate(path, expected_hash, input_manifest):
    verify(path, expected_hash)
    gate = read(path)
    if (gate["status"] not in ("PASS", "DEV_FAIL_RANGE") or gate["stage"] != "S3-R"
            or gate["manifest_sha256"] != sha(input_manifest)):
        raise ValueError("Invalid S3-R gate for signed-s execution")
    if (gate["status"] == "PASS") != (gate["selected"] in ("R4", "R-M", "R-MC")):
        raise ValueError("S3-R range-arm decision is inconsistent")
    return gate


def joint_settings(data, fitted, snr, level, arm, range_arm, offset, site_count, k_s):
    r_model = None if range_arm is None else fit_range(data, fitted, level, range_arm, snr, offset)
    axes = fitted["C3"]["s"]
    fits = (axes["distance_m"], axes["yaw_deg"])
    nugget = np.average([x["nugget"] for x in fits], weights=[x["pair_count"] for x in fits])
    c4 = fitted["C4"]["TEACH_REPEAT"]["rho"]
    return JointModel(
        arm, 5 if level.startswith("TB3") else 4, data["anchor"][:2], data["rx_z"] - data["anchor"][2],
        fitted["C1"][str(snr)]["sigma_s"]**2, fitted["C2_by_snr"][str(snr)]["s"],
        range_options=r_model, length_m=fits[0]["length"], length_rad=np.deg2rad(fits[1]["length"]),
        nugget=float(nugget), c3_white=any(x["mode"] == "WHITE" for x in fits),
        site_corr=float(np.clip(0. if c4 is None else c4, 0., 1.)), site_count=site_count,
        consider_s_variance=k_s if "+K" in arm else 0., tail_df=fitted["C7"]["nu_use"] if "+T" in arm else None,
    )


def site_map(inp, path, spacing):
    labels = []
    distance = 0.
    for row in inp["rows"]:
        distance += float(row["distance_increment_m"])
        if path == "TEACH_REPEAT":
            label = row["station_id"] or inp["rows"][0]["station_id"]
        else:
            label = max(0, int(np.ceil(distance/spacing) - 1))
        labels.append(label)
    unique = {label: idx for idx, label in enumerate(dict.fromkeys(labels))}
    return [unique[x] for x in labels], len(unique)


def track_fold(inp, case, path, arm, scenario, state, measured, model, dr, data, rf, sites):
    model_source, obs, banks, rule = rf
    cp = {packet: j for j, packet in enumerate(inp["cp"])}
    mean, cov = state["mean"], state["cov"]
    runs = len(mean)
    observed = np.repeat(measured, len(state["signs"]), axis=1)
    evidence = []
    schema = (
        "s_total", "s_rejected", "s_unavailable", "s_gate_rejected",
        "s_effective_rejected", "m1r_clipped",
    )
    completed = {name: np.zeros(runs, dtype=int) for name in schema}
    contrib = {phase: dict(attempted=0, available=0, accepted=0, effective_rejected=0,
                           range_accepted=0, m1r_clipped=0, sum_abs_heading_update_rad=0.,
                           range_mean_outside_support=0)
               for phase in ("straight", "turn", "hold")}
    weights = []
    for i, row in enumerate(inp["rows"]):
        if i:
            restart = inp["restart"].get(i)
            angular = None
            if state["tb3"]:
                angular = np.zeros(runs) if restart is not None else np.abs(state["gyro"][i])
            mean, cov = predict_joint(mean, cov, state["wheel"][i], state["gyro"][i], inp["dt"][i], model,
                                      angular_travel_rad=angular, restart_pose=restart)
        requested = mean[:, 2].copy()
        s, jac, var, clipped = m1r_clipped(model_source, obs, banks, mean, cov, data["anchor"],
                                          data["rx_z"], rule, batch_poses=128)
        mean, cov, event = update_joint(mean, cov, observed[i, :, 0], observed[i, :, 1], s, jac, var, model,
                                        site_index=sites[i] if arm.startswith("J-CS") else None)
        completed["s_total"] += 1
        completed["s_unavailable"] += event["s_unavailable"]
        completed["s_rejected"] += event["s_rejected"] | event["s_unavailable"]
        completed["s_gate_rejected"] += event["s_gate_rejected"]
        completed["s_effective_rejected"] += event["s_effective_rejected"]
        completed["m1r_clipped"] += clipped
        mode = ("hold" if row["motion"] in ("hold", "restart") else
                "turn" if row["motion"] in ("sweep", "in_place", "turn") else "straight")
        report = contrib[mode]
        report["attempted"] += runs
        for what, mask in (("available", event["s_available"]), ("accepted", event["s_accepted"]),
                           ("effective_rejected", event["s_effective_rejected"]),
                           ("range_accepted", event["r_accepted"]), ("m1r_clipped", clipped),
                           ("range_mean_outside_support", event["mean_out_of_support"])):
            report[what] += int(np.sum(mask))
        report["sum_abs_heading_update_rad"] += float(np.sum(np.abs(wrap_rad(mean[:, 2]-requested))))
        if "+T" in arm:
            w = event["student_weight"]
            weights.append(w[np.isfinite(w)])
        if i in cp:
            evidence.extend(checkpoint_rows(inp, state, case, path, arm, scenario, i, cp[i], mean, cov, dr,
                                            s_counts=completed))
            for value in completed.values():
                value[:] = 0
    tail = dict(n=0)
    if weights and any(len(w) for w in weights):
        values = np.concatenate(weights)
        tail = dict(n=len(values), quantile={str(q): float(np.quantile(values,q))
                                           for q in (0., .01, .10, .50, .90, .99, 1.)},
                    effective_reject_fraction=float(np.mean(values < .1)))
    return evidence, contrib, tail


def fold(args, docs, gate):
    start = utc_now()
    case, path, scenario, arm = args.case, args.path, args.level, args.arm
    allowed = JOINT if gate["status"] == "PASS" else DIAGNOSTIC
    if arm not in allowed:
        raise ValueError("S3-R outcome does not authorize this signed-s arm")
    level = "B0" if scenario == "B0_ZERO" else scenario
    chain = docs["characterization"]["chains"][args.chain]
    rule = chain["rule"]
    donors = "".join(a for a in "ABC" if a != case[-1])
    fitted = chain["anchor_fits"][donors]
    offset = chain["offset_m"]
    index_path = args.results_root/"CASES.json"
    verify(index_path, docs["characterization"]["production_cases_sha256"])
    data = open_case(args.results_root, read(index_path)[case], case)
    if data["input_sha256"] != docs["characterization"]["input_sha256"][case]:
        raise ValueError("S3-J RF inputs differ from S2")
    model_source, obs, banks, freq, src, bank_hashes = load_model(args)
    rows = timeline_data(args.frozen/"TIMELINE_PACKETS.csv")[case][path]
    for row in rows:
        for key in ("rf_pose_id", "thermal_noise_seed"):
            row[key] = int(row[key])
    spacing = chain["anchor_fits"]["ABC"]["site_spacing_m"]["s"]
    inp = prepare(rows, path, spacing)
    packet_sites, site_count = site_map(inp, path, spacing)
    k_s = chain["C5_K_by_path"][path][donors]
    settings = joint_settings(data, fitted, args.snr, level, arm, gate["selected"], offset, site_count, k_s)
    state = start_level(inp, path, level, scenario == "B0_ZERO", settings, initialize=initialize_joint)
    rf_file = args.out/"rf"/str(args.snr)/f"{case}_{path}.npz"
    rf_receipt = read(rf_file.with_suffix(".json"))
    if (rf_receipt["rules"][args.chain] != rule or rf_receipt["manifest_sha256"] != sha(args.manifest)
            or (rf_receipt["case"], rf_receipt["path"], rf_receipt["snr"]) != (case, path, args.snr)):
        raise ValueError("S3-J RF observations differ from their range-stage provenance")
    verify(rf_file, rf_receipt["sha256"])
    with np.load(rf_file, allow_pickle=False) as archive:
        measured = archive[args.chain]
    if measured.shape != (len(rows), len(SEEDS), 2):
        raise ValueError("S3-J RF packet and seed grid differs from the frozen timeline")
    range_dir = args.out/args.chain/str(args.snr)
    dr_file = range_dir/f"{case}_{path}_{scenario}_DR.json"
    dr_receipt = read(dr_file)
    if dr_receipt["status"] != "PASS" or dr_receipt["manifest_sha256"] != sha(args.manifest):
        raise ValueError("S3-J requires its frozen paired DR")
    dr = {(r["checkpoint_order"], r["seed"], r["sign"]): (r["heading_error_rad"], r["xy_error_m"])
          for r in dr_receipt["rows"]}
    target = args.out/"joint"/args.chain/str(args.snr)
    target.mkdir(parents=True, exist_ok=True)
    file = target/f"{case}_{path}_{scenario}_{arm}.json"
    report = dict(question_id="G1-MODEL-003", version=3, case=case, path=path, level=scenario,
                  arm=arm, range_arm=gate["selected"], phase="S3-J" if arm in JOINT else "DIAGNOSTIC_ONLY",
                  chain=args.chain, rule=rule, snr=args.snr, donors=donors,
                  input_manifest_sha256=sha(args.manifest), range_stage_sha256=sha(args.range_stage),
                  paired_dr_sha256=sha(dr_file), rf_observations_sha256=rf_receipt["sha256"],
                  runner_sha256=sha(Path(__file__)),
                  source_sha256=src, bank_sha256=bank_hashes, started_utc=start)
    try:
        evidence, contrib, weights = track_fold(inp, case, path, arm, scenario, state, measured, settings,
                                                dr, data, (model_source, obs, banks, rule), packet_sites)
        report.update(status="PASS", rows=evidence, contributions=contrib, student_weights=weights)
    except (np.linalg.LinAlgError, FloatingPointError) as exc:
        report.update(status="NUMERICAL_FAIL", reason=str(exc))
    write(file, report | dict(finished_utc=utc_now()))
    print(f"{case}/{path} {arm} {scenario}: {report['status']}", flush=True)


def compare(reference, rows):
    def pair(row):
        return row["checkpoint_id"], row["seed"], row["sign"]
    order = {pair(r): r for r in reference}
    if set(order) != {pair(r) for r in rows}:
        raise ValueError("J − R checkpoint pairing differs")
    def error(z, key):
        return float(np.sqrt(np.mean([x[key]**2 for x in z])))
    return dict(heading_rmse_delta_deg=float(np.rad2deg(error(rows,"heading_error_rad") -
                                                       error(reference,"heading_error_rad"))),
                xy_rmse_delta_m=error(rows,"xy_error_m")-error(reference,"xy_error_m"))


def close(args, docs, gate):
    eligible = gate["status"] == "PASS"
    governing = args.chain == "OR" and args.snr == 30
    labels = JOINT if eligible else DIAGNOSTIC
    scope = docs["futility"]["chains"][args.chain]["paths"]
    spin = docs["characterization"]["chains"][args.chain]
    references = {}
    hashes = {}
    report = {}
    restricted = any(
        axis["requires_consider"] for donors in ("AB","AC","BC")
        for axis in (spin["anchor_fits"][donors]["C3"]["s"]["distance_m"],
                     spin["anchor_fits"][donors]["C3"]["s"]["yaw_deg"]))
    for arm in labels:
        details = {}
        for idx, level in enumerate((*LEVELS,"B0_ZERO")):
            rows, issues, paired, contributions = [], [], {}, {}
            for case in CASES:
                for path in PATHS:
                    label = f"{case}_{path}_{level}"
                    file = args.out/"joint"/args.chain/str(args.snr)/f"{label}_{arm}.json"
                    item = read(file)
                    expected = dict(case=case, path=path, level=level, arm=arm, chain=args.chain, snr=args.snr,
                                    range_stage_sha256=args.range_stage_sha256,
                                    input_manifest_sha256=sha(args.manifest))
                    if any(item[k] != v for k,v in expected.items()):
                        raise ValueError("Mismatched v3 signed-s fold")
                    hashes[file.name] = sha(file)
                    if item["status"] == "NUMERICAL_FAIL":
                        issues.append(dict(case=case, path=path, reason=item["reason"]))
                        continue
                    if item["status"] != "PASS" or {x["seed"] for x in item["rows"]} != set(SEEDS):
                        raise ValueError("Incomplete v3 signed-s fold")
                    rows.extend(item["rows"])
                    contributions[f"{case}/{path}"] = dict(phases=item["contributions"],
                                                            student_weights=item["student_weights"])
                    if eligible:
                        if label not in references:
                            ref = read(args.out/args.chain/str(args.snr)/f"{label}_{gate['selected']}.json")
                            references[label] = ref["rows"] if ref["status"] == "PASS" else None
                        if references[label] is not None:
                            paired[f"{case}/{path}"] = compare(references[label], item["rows"])
            if issues:
                details[level] = dict(integrity_pass=False, numerical_failures=issues)
                continue
            base = evaluate_level(rows, idx, range_only=False, harmlessness_required=False)
            excluded = [
                row for row in rows
                if level in ("B0","B0_ZERO")
                or (row["path"] != "P-B" and scope[row["path"]]["levels"][level]["accuracy_scope"] == "EXCLUDE")
            ]
            if excluded:
                harm = evaluate_level(excluded, idx, range_only=False, harmlessness_required=True)
                base.update(harmlessness_pass=harm["harmlessness_pass"],
                            harmlessness_checks=harm["harmlessness_checks"],
                            harmlessness_paths=sorted({r["path"] for r in excluded}))
            details[level] = base | dict(j_minus_range=paired, contributions=contributions)
        passed = all(details[l]["integrity_pass"] and details[l].get("harmlessness_pass") is not False for l in LEVELS)
        report[arm] = dict(levels=details, selection_eligible=(
            governing and eligible and arm in CANDIDATES and passed and (not restricted or "+K" in arm)))
    candidate = [a for a,x in report.items() if x["selection_eligible"]]
    selected = None
    if candidate:
        scored = {a: report[a]["levels"]["L1"]["pooled"]["point"]["heading_rmse_rad"] for a in candidate}
        tie = [a for a in candidate if np.rad2deg(scored[a]-min(scored.values())) < .1]
        selected = min(tie, key=lambda a: (BASES.index(a.split("+")[0]), a.count("+"), "+T" in a, a))
    status = (("PASS" if selected else "DEV_FAIL") if eligible else "DEV_FAIL_RANGE") if governing else "REPORT_ONLY"
    results = dict(question_id="G1-MODEL-003", version=3, status=status, selection=selected,
                   range_arm=gate["selected"], rule=spin["rule"], consider_required=restricted,
                   snr=args.snr, role="DEVELOPMENT" if eligible and governing else "DIAGNOSTIC_ONLY",
                   arm_results=report,
                   input_manifest_sha256=sha(args.manifest), range_stage_sha256=args.range_stage_sha256,
                   receipt_sha256=hashes, finished_utc=utc_now())
    name = "LOAO_RESULTS_V3.json" if governing else f"LOAO_REPORT_{args.chain}_{args.snr}.json"
    write(args.out/name, results)
    if governing:
        write(args.out/"PRIMARY_ARM_V3.json", {k:results[k] for k in ("question_id","version","status","selection",
                                                                    "range_arm","rule","role","finished_utc")}
              | dict(loao_results_sha256=sha(args.out/name)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fold","close"))
    for arg in ("frozen","manifest","range-stage","results-root","model-source","banks-dir","out"):
        parser.add_argument("--"+arg, type=Path, required=True)
    parser.add_argument("--range-stage-sha256", required=True)
    parser.add_argument("--arm", choices=(*JOINT,*DIAGNOSTIC))
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--path", choices=PATHS)
    parser.add_argument("--level", choices=(*LEVELS,"B0_ZERO"))
    parser.add_argument("--chain", choices=("OR","O30"), default="OR")
    parser.add_argument("--snr", type=int, choices=(20,30), default=30)
    args = parser.parse_args()
    docs = ready(args.frozen, read(args.manifest))
    gate = load_gate(args.range_stage, args.range_stage_sha256, args.manifest)
    if args.mode == "fold":
        fold(args, docs, gate)
    else:
        close(args, docs, gate)


if __name__ == "__main__":
    main()
