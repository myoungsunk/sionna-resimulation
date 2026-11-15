"""Run each MODEL-003 v3 S3-R case/path under the frozen distance chain."""

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_model003_s1 import CASES, open_case
from run_tb3_model003_s2 import PATHS, fixed_checkpoints, timeline_data
from run_tb3_model003_s3 import HEADING_BOUND, XY_BOUND, restart_transform, score_state, wrap_rad
from run_tb3_production import utc_now, verify
from tb3_model003_filter import initial_covariance
from tb3_model003_motion import BIAS_DEG_PER_S, SIGNS, TB3_HOLD_DRIFT_DEG_PER_S, TB3_SCALE
from tb3_model003_motion import generate_motion, geometry_from_rows
from tb3_model003_s3_inputs import paired_observations, wheel_controls
from tb3_model003_v3_integrity import evaluate_level
from tb3_model003_v3_range import RangeModel, initialize_range, predict_range, update_range
from validate_tb3_g4 import load_model


SEEDS = tuple(range(40))
LEVELS = (*BIAS_DEG_PER_S, *TB3_SCALE)
RANGE_ARMS = ("R4", "R-M", "R-MC")
INPUT_FILES = dict(selection="RANGING_RULE_SELECTION_V3.json", parity="PARITY_V3.json",
                   characterization="CHARACTERIZATION_003_V3.json", transfer="TRANSFER_PRECHECK.json",
                   futility="FUTILITY_V3.json", timeline="TIMELINE_PACKETS.csv")


def ready(root, manifest):
    if manifest["question_id"] != "G1-MODEL-003" or manifest["stage"] != "S3-R":
        raise ValueError("Invalid MODEL-003 v3 stage manifest")
    for key, name in INPUT_FILES.items():
        verify(root/name, manifest["sha256"][key])
    docs = {key: read(root/name) for key, name in INPUT_FILES.items() if key != "timeline"}
    for key in ("selection", "parity", "characterization", "transfer", "futility"):
        if docs[key]["status"] != "PASS":
            raise ValueError(f"S3-R requires passing {key}")
    if not manifest.get("transfer_commit") or not manifest.get("plan_commit"):
        raise ValueError("S2-T and the S3 policy must be committed before filtering")
    selected = docs["selection"]["selected"]
    if selected != docs["parity"]["selected_rule"] or selected != docs["characterization"]["chains"]["OR"]["rule"]:
        raise ValueError("S3-R observation chain or parity does not match")
    return docs


def initial_pose(truth, path, zero_heading):
    draws = []
    for seed in SEEDS:
        digest = hashlib.sha256(f"G1-MODEL-003/{path}/initial/{seed}".encode()).digest()
        rng = np.random.default_rng(int.from_bytes(digest[:16], "big"))
        draws.append(rng.standard_normal(3)*np.sqrt(np.diag(initial_covariance())[:3]))
    draws = np.asarray(draws)
    if zero_heading:
        draws[:, 2] = 0
    value = truth + draws
    value[:, 2] = wrap_rad(value[:, 2])
    return value


def prepare(rows, path, spacing):
    geometry = geometry_from_rows(rows)
    motion = generate_motion(**geometry, path_id=path, seeds=SEEDS)
    truth = np.array([[float(row["truth_x_m"]), float(row["truth_y_m"]),
                       math.radians(float(row["truth_yaw_deg"]))] for row in rows])
    cp = fixed_checkpoints(rows, path, spacing)
    if not len(cp):
        raise ValueError(f"No evaluation checkpoint for {path}")
    return dict(truth=truth, dt=np.diff(geometry["elapsed_s"], prepend=geometry["elapsed_s"][0]),
                rows=rows, cp=cp, motion=motion,
                wheel=np.asarray(wheel_controls(rows, geometry, path, seeds=SEEDS)["distance_m"]),
                restart={i: restart_transform(truth, i) for i, mode in enumerate(geometry["motion"])
                         if mode == "restart"})


def start_level(inp, path, level, zero_heading, model, *, initialize=initialize_range):
    tb3 = level.startswith("TB3")
    motion_dim = 5 if tb3 else 4
    signs = SIGNS[:1] if level == "B0" else SIGNS
    gyro = np.asarray(inp["motion"]["gyro_increment_rad"][level])
    if level == "B0" and not np.array_equal(gyro[..., 0], gyro[..., 1]):
        raise ValueError("B0 gyro draws differ across signs")
    gyro = gyro[..., :len(signs)].reshape(len(inp["rows"]), -1)
    initial = np.zeros((len(SEEDS)*len(signs), motion_dim))
    initial[:, :3] = np.repeat(initial_pose(inp["truth"][0], path, zero_heading), len(signs), axis=0)
    p0 = initial_covariance(.0085 if tb3 else None)
    cov = np.broadcast_to(p0, (len(initial), motion_dim, motion_dim)).copy()
    if model is not None:
        initial, cov = initialize(initial, cov, model)
    bg = math.radians(TB3_HOLD_DRIFT_DEG_PER_S if tb3 else BIAS_DEG_PER_S[level])
    bg = bg*np.tile(signs, len(SEEDS))
    return dict(mean=initial, cov=cov, gyro=gyro, signs=signs, bg=bg, md=motion_dim,
                wheel=np.repeat(inp["wheel"], len(signs), axis=1), tb3=tb3)


def checkpoint_site(path, row, slot):
    if path != "TEACH_REPEAT":
        return f"{path}/{slot}"
    return f"{path}/{row['station_id']}"


def checkpoint_rows(inp, state, case, path, arm, scenario, i, slot, mean, cov, dr, s_counts=None):
    e, xy, head, bias = score_state(mean, cov, state["bg"], inp["truth"][i])
    if not all(np.isfinite(x).all() for x in (e, xy, head, bias)):
        raise FloatingPointError("Nonfinite checkpoint state")
    row = inp["rows"][i]
    for seed_index, seed in enumerate(SEEDS):
        for sign_index, sign in enumerate(SIGNS):
            run = seed_index if scenario in ("B0", "B0_ZERO") else seed_index*len(SIGNS)+sign_index
            idx = i, seed, sign
            xy_error = float(np.linalg.norm(e[run, :2]))
            heading = float(e[run, 2])
            reference = dr[idx] if dr is not None else (heading, xy_error)
            counts = {} if s_counts is None else {name: int(value[run]) for name, value in s_counts.items()}
            yield dict(case=case, arm=arm, level=scenario, sign=sign, seed=seed, path=path,
                       site_id=checkpoint_site(path, row, slot), checkpoint_id=int(row["sequence"]),
                       checkpoint_order=i, phase=row["phase"], heading_included=bool(head[run] <= HEADING_BOUND),
                       xy_included=bool(xy[run] <= XY_BOUND), nees_heading=float(head[run]),
                       nees_xy_normalized=float(xy[run]/2.), nees_bg=float(bias[run]),
                       heading_error_rad=heading, heading_error_signed_rad=heading, xy_error_m=xy_error,
                       dr_heading_error_rad=reference[0], dr_xy_error_m=reference[1],
                       **(dict(s_total=0, s_rejected=0, s_unavailable=0) | counts))


def rows_and_contributions(inp, path, case, arm, scenario, state, measured, model, dr=None):
    from tb3_model003_filter import predict

    cp = inp["cp"]
    checkpoint_slots = {packet: j for j, packet in enumerate(cp)}
    mean, cov = state["mean"], state["cov"]
    runs = len(mean)
    measurements = None if measured is None else np.repeat(measured[..., 0], len(state["signs"]), axis=1)
    evidence = []
    contributions = {mode: dict(attempted=0, available=0, accepted=0, sum_abs_heading_update_rad=0.,
                                 range_mean_outside_support=0, range_variance_outside_support=0)
                     for mode in ("straight", "turn", "hold")}
    for i, row in enumerate(inp["rows"]):
        if i:
            restart = inp["restart"].get(i)
            angular = None
            if state["tb3"]:
                angular = np.zeros(runs) if restart is not None else np.abs(state["gyro"][i])
            args = mean, cov, state["wheel"][i], state["gyro"][i], inp["dt"][i]
            options = dict(angular_travel_rad=angular, restart_pose=restart)
            if model is None:
                mean, cov = predict(*args, motion_dim=state["md"], **options)
            else:
                mean, cov = predict_range(*args, model, **options)
        if measurements is not None:
            prior = mean[:, 2].copy()
            mean, cov, update = update_range(mean, cov, measurements[i], model)
            mode = ("hold" if row["motion"] in ("hold", "restart") else
                    "turn" if row["motion"] in ("sweep", "in_place", "turn") else "straight")
            counts = contributions[mode]
            counts["attempted"] += runs
            counts["available"] += int(np.sum(update["available"]))
            counts["accepted"] += int(np.sum(update["accepted"]))
            counts["sum_abs_heading_update_rad"] += float(np.sum(np.abs(wrap_rad(mean[:, 2] - prior))))
            counts["range_mean_outside_support"] += int(np.sum(update["mean_out_of_support"]))
            counts["range_variance_outside_support"] += int(np.sum(update["variance_out_of_support"]))
        if i not in checkpoint_slots:
            continue
        evidence.extend(checkpoint_rows(inp, state, case, path, arm, scenario, i, checkpoint_slots[i],
                                        mean, cov, dr))
    return evidence, contributions


def fit_range(data, fitted, level, arm, snr, offset):
    if arm == "DR":
        return None
    thermal_var = float(fitted["C1"][str(snr)]["sigma_r_m"])**2
    c2 = fitted["C2_by_snr"][str(snr)]
    white_var = c2["range"]["white_variance"]
    c6 = fitted["C6"]
    more = {}
    if arm != "R4":
        more = dict(mean_knots_m=c6["knots_m"], mean_bias_m=c6["bias_m"])
    if arm == "R-MC":
        axis = fitted["C3"]["range"]
        fits = (axis["distance_m"], axis["yaw_deg"])
        nugget = np.average([x["nugget"] for x in fits], weights=[x["pair_count"] for x in fits])
        more.update(c2_range=c2["range_conditional"], consider_variance_m2=fitted["C6_K"]["variance_m2"],
                    length_m=fits[0]["length"], length_rad=math.radians(fits[1]["length"]),
                    nugget=float(nugget), c3_white=any(x["mode"] == "WHITE" for x in fits))
    return RangeModel(arm, 5 if level.startswith("TB3") else 4, data["anchor"][:2],
                      data["rx_z"] - data["anchor"][2], offset, thermal_var, white_var, **more)


def score_range(args, docs, data, inp, measured, source_hashes, bank_hashes, start, chain_label):
    case, path = args.case, args.path
    chain = docs["characterization"]["chains"][chain_label]
    rule, offset = chain["rule"], chain["offset_m"]
    donors = "".join(a for a in "ABC" if a != case[-1])
    fitted = chain["anchor_fits"][donors]
    target = args.out / chain_label / str(args.snr)
    target.mkdir(parents=True, exist_ok=True)
    for scenario in (*LEVELS, "B0_ZERO"):
        level = "B0" if scenario == "B0_ZERO" else scenario
        dr = None
        for arm in ("DR", *RANGE_ARMS):
            model = fit_range(data, fitted, level, arm, args.snr, offset)
            state = start_level(inp, path, level, scenario == "B0_ZERO", model)
            file = target/f"{case}_{path}_{scenario}_{arm}.json"
            report = dict(case=case, path=path, arm=arm, level=scenario, snr=args.snr, chain=chain_label,
                          rule=rule, donors=donors, question_id="G1-MODEL-003", version=3,
                          manifest_sha256=sha(args.manifest), started_utc=start, source_sha256=source_hashes,
                          bank_sha256=bank_hashes, runner_sha256=sha(Path(__file__)),
                          stage_commit=read(args.manifest)["plan_commit"],
                          expected_scored_rows=len(inp["cp"])*2*len(SEEDS))
            try:
                checkpoints, contrib = rows_and_contributions(inp, path, case, arm, scenario, state,
                                                              measured if arm != "DR" else None, model, dr)
                report.update(status="PASS", rows=checkpoints, contributions=contrib)
            except (np.linalg.LinAlgError, FloatingPointError) as exc:
                report.update(status="NUMERICAL_FAIL", reason=str(exc))
                if arm == "DR":
                    raise
            if arm == "DR":
                dr = {(r["checkpoint_order"], r["seed"], r["sign"]): (r["heading_error_rad"], r["xy_error_m"])
                      for r in checkpoints}
            write(file, report | dict(finished_utc=utc_now()))
        print(f"{case}/{path} {chain_label} {args.snr} dB {scenario} complete", flush=True)


def fold(args, docs, inputs):
    start = utc_now()
    case = args.case
    path = args.path
    cases_index = args.results_root / "CASES.json"
    verify(cases_index, docs["characterization"]["production_cases_sha256"])
    data = open_case(args.results_root, read(cases_index)[case], case)
    if data["input_sha256"] != docs["characterization"]["input_sha256"][case]:
        raise ValueError("S3-R RF inputs differ from S2")
    _, obs, _, freq, source_hashes, bank_hashes = load_model(args)
    timeline = timeline_data(inputs/"TIMELINE_PACKETS.csv")
    rows = timeline[case][path]
    for row in rows:
        for key in ("rf_pose_id", "thermal_noise_seed"):
            row[key] = int(row[key])
    chains = ("OR", "O30") if args.snr == 30 else ("OR",)
    fits = docs["characterization"]["chains"]
    rules = {label: fits[label]["rule"] for label in chains}
    observations = paired_observations(data, rows, obs, float(freq[1] - freq[0]), rules,
                                       seeds=SEEDS, snr_db=args.snr)
    rf_dir = args.out/"rf"/str(args.snr)
    rf_dir.mkdir(parents=True, exist_ok=True)
    observation_file = rf_dir/f"{case}_{path}.npz"
    with observation_file.open("xb") as stream:
        np.savez(stream, **observations)
    write(observation_file.with_suffix(".json"), dict(sha256=sha(observation_file), case=case, path=path,
          snr=args.snr, rules=rules, manifest_sha256=sha(args.manifest)))
    for label in chains:
        spacing = fits[label]["anchor_fits"]["ABC"]["site_spacing_m"]["s"]
        inp = prepare(rows, path, spacing)
        score_range(args, docs, data, inp, observations[label], source_hashes, bank_hashes, start, label)


def summarize(args, docs):
    label = args.chain
    primary = docs["characterization"]["chains"][label]
    results = {}
    for arm in ("DR", *RANGE_ARMS):
        levels = {}
        for index, level in enumerate((*LEVELS, "B0_ZERO")):
            expected = [args.out/label/str(args.snr)/f"{c}_{p}_{level}_{arm}.json" for c in CASES for p in PATHS]
            receipts = [read(path) for path in expected]
            issues = []
            for receipt, case_path in zip(receipts, ((c,p) for c in CASES for p in PATHS), strict=True):
                if ((receipt["case"], receipt["path"]) != case_path or receipt["level"] != level
                        or receipt["arm"] != arm or receipt["chain"] != label or receipt["snr"] != args.snr):
                    raise ValueError("S3-R receipt identity mismatch")
                if receipt["manifest_sha256"] != sha(args.manifest):
                    raise ValueError("S3-R receipt uses a different input manifest")
                if receipt["status"] == "NUMERICAL_FAIL":
                    issues.append({k: receipt[k] for k in ("case", "path", "reason")})
                    continue
                if receipt["status"] != "PASS" or len(receipt["rows"]) != receipt["expected_scored_rows"]:
                    raise ValueError("S3-R receipt is incomplete")
                if {r["seed"] for r in receipt["rows"]} != set(SEEDS):
                    raise ValueError("S3-R sensor seed grid is incomplete")
            levels[level] = (dict(integrity_pass=False, numerical_failures=issues) if issues else
                             evaluate_level([row for rr in receipts for row in rr["rows"]], index, range_only=True,
                                            harmlessness_required=False))
            levels[level]["contributions"] = {f"{rr['case']}/{rr['path']}": rr["contributions"]
                                               for rr in receipts if rr["status"] == "PASS"}
        results[arm] = dict(levels=levels, passed_all_levels=all(levels[l]["integrity_pass"] for l in LEVELS))
    restricted = any(entry["requires_consider"]
                     for donors in ("AB", "AC", "BC")
                     for entry in primary["anchor_fits"][donors]["C3"]["range"].values()
                     if isinstance(entry, dict) and "requires_consider" in entry)
    eligible = [arm for arm in RANGE_ARMS if results[arm]["passed_all_levels"]
                and (not restricted or arm == "R-MC")]
    governing = label == "OR" and args.snr == 30
    selected = next(iter(eligible), None) if governing else None
    status = ("PASS" if selected else "DEV_FAIL_RANGE") if governing else "REPORT_ONLY"
    name = "RANGE_STAGE.json" if governing else f"RANGE_REPORT_{label}_{args.snr}.json"
    write(args.out/name, dict(question_id="G1-MODEL-003", version=3, stage="S3-R",
                             status=status, selected=selected, snr=args.snr, consider_required=restricted,
                             results=results, chain=primary["rule"], manifest_sha256=sha(args.manifest),
                             finished_utc=utc_now()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fold","close"))
    for arg in ("frozen", "manifest", "results-root", "model-source", "banks-dir", "out"):
        parser.add_argument("--"+arg, type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--path", choices=PATHS)
    parser.add_argument("--chain", choices=("OR","O30"), default="OR")
    parser.add_argument("--snr", type=int, choices=(20,30), default=30)
    args = parser.parse_args()
    docs = ready(args.frozen, read(args.manifest))
    if args.mode == "fold":
        fold(args, docs, args.frozen)
    else:
        summarize(args, docs)


if __name__ == "__main__":
    main()
