"""Run a locked single-anchor LOAO fold of G1-MODEL-003."""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_model003_s1 import CASES, PA, open_case
from run_tb3_model003_s2 import CURVES, PATHS, bin_key, fixed_checkpoints, timeline_data
from run_tb3_production import utc_now, verify
from tb3_model003_filter import initial_covariance, predict, update_rf
from tb3_model003_m1r_batch import m1r_batch
from tb3_model003_motion import BIAS_DEG_PER_S, DEFAULT_SEEDS, SIGNS, generate_motion, geometry_from_rows
from tb3_model003_s3_inputs import paired_observations, wheel_controls
from validate_tb3_g4 import load_model


ARMS = ("DR", "R4", "J4", "J-V", "J-C", "J-CS", "J-CI", "J4+K", "J-V+K", "J-C+K", "J-CS+K", "J-CI+K")
LEVELS = (*BIAS_DEG_PER_S, "TB3_r1.3.1", "TB3_r2.1.0")
TB3_BG_DPS = 0.0005
XY_BOUND = 5.991464547107979
HEADING_BOUND = 3.841458820694124


class UndefinedDistancePrior(Exception):
    """The fixed M1-R quadrature has a node outside positive range."""


def wrap_rad(a):
    return (a+np.pi) % (2*np.pi)-np.pi


def initial_pose(truth, path):
    draws = []
    for seed in DEFAULT_SEEDS:
        name = hashlib.sha256(f"G1-MODEL-003/{path}/initial/{seed}".encode()).digest()
        rng = np.random.default_rng(int.from_bytes(name[:16], "big"))
        draws.append(rng.standard_normal(3) * np.sqrt(np.diag(initial_covariance())[:3]))
    origin = truth + np.repeat(draws, len(SIGNS), axis=0)
    origin[:, 2] = wrap_rad(origin[:, 2])
    return origin


def restart_transform(truth, i):
    offset = wrap_rad(truth[i, 2]-truth[i-1, 2])
    c, s = np.cos(offset), np.sin(offset)
    translation = truth[i, :2] - np.array([[c, -s], [s, c]]) @ truth[i-1, :2]
    return np.r_[translation, offset]


def path_inputs(rows, path, spacing):
    geometry = geometry_from_rows(rows)
    motion = generate_motion(**geometry, path_id=path)
    truth = np.array([[float(r["truth_x_m"]), float(r["truth_y_m"]), math.radians(float(r["truth_yaw_deg"]))]
                      for r in rows])
    cp = fixed_checkpoints(rows, path, spacing)
    dt = np.diff(geometry["elapsed_s"], prepend=geometry["elapsed_s"][0])
    wheel = wheel_controls(rows, geometry, path)["distance_m"]
    distance = np.cumsum(geometry["distance_increment_m"])
    packet_sites = ([r["station_id"] or rows[0]["station_id"] for r in rows] if path == "TEACH_REPEAT"
                    else (np.maximum(0, np.ceil(distance/spacing)-1).astype(int)).tolist())
    site_index = {value: i for i, value in enumerate(dict.fromkeys(packet_sites))}
    return dict(geometry=geometry, motion=motion, rows=rows, truth=truth, cp=cp, dt=dt, wheel=wheel,
                initial=initial_pose(truth[0], path), packet_sites=packet_sites, site_index=site_index,
                restart={i: restart_transform(truth, i) for i, mode in enumerate(geometry["motion"])
                         if mode == "restart"})


def variance_setup(fit, distance, snr):
    c2, c1, c3 = fit["C2"], fit["C1"][str(snr)], fit["C3"]
    knots = np.asarray(c2["knots_m"])
    sig = np.array([c2["sigma_r_m"], c2["sigma_b"]])
    constant = np.array([np.mean(np.interp(distance, knots, values)**2) for values in sig])
    thermal = np.square([c1["sigma_r_m"], c1["sigma_s"]])
    return dict(knots=knots, sig=sig, constant=constant, thermal=thermal,
                distance_length=np.array([c3[name]["distance_m"]["length"] for name in ("range", "s")]),
                yaw_length=np.radians([c3[name]["yaw_deg"]["length"] for name in ("range", "s")]),
                site_corr=float(np.clip(fit["C4"]["TEACH_REPEAT"]["rho"], 0, 1)))


def path_k_variance(c5, path, anchors):
    windows = [v["window"] for c, v in c5[path].items() if c[-1] in anchors and v["window"]["n"]]
    n = sum(w["n"] for w in windows)
    mean = sum(w["mean"]*w["n"] for w in windows) / n
    return sum(w["n"]*(w["variance"]+(w["mean"]-mean)**2) for w in windows) / n


def score_state(mean, cov, bg, truth):
    e = mean[:, :4].copy()
    e[:, :3] -= truth
    e[:, 3] -= bg
    e[:, 2] = wrap_rad(e[:, 2])
    px = cov[:, :2, :2]
    xy = np.sum(e[:, :2]*np.linalg.solve(px, e[:, :2, None])[..., 0], axis=1)
    heading = e[:, 2]**2/cov[:, 2, 2]
    bias = e[:, 3]**2/cov[:, 3, 3]
    return e, xy, heading, bias


def fit_path(case, path, arm, level, data, inp, z, dr, model, obs, banks, rule, offset, settings, k_variance):
    rows, truth, cp = inp["rows"], inp["truth"], inp["cp"]
    tb3 = level.startswith("TB3")
    md = 5 if tb3 else 4
    base = arm.removesuffix("+K")
    colored = base in ("J-C", "J-CS")
    schmidt = base == "J-CS"
    use_k = arm.endswith("+K")
    active = md + 2*colored
    n = active + len(inp["site_index"])*schmidt + use_k
    runs = len(DEFAULT_SEEDS)*len(SIGNS)
    gyro = np.array(inp["motion"]["gyro_increment_rad"][level]).reshape(len(rows), runs)
    wheel = np.repeat(np.asarray(inp["wheel"]), len(SIGNS), axis=1)
    mean = np.zeros((runs, n))
    mean[:, :3] = inp["initial"]
    variance = np.zeros((n, n))
    variance[:md, :md] = initial_covariance(.0085 if tb3 else None)
    if colored:
        variance[md:active, md:active] = np.diag(settings["constant"])
    if schmidt:
        ii = np.arange(active, active+len(inp["site_index"]))
        variance[ii, ii] = 1.0
        variance[md+1, md+1] *= 1-settings["site_corr"]
    if use_k:
        variance[-1, -1] = k_variance
    cov = np.broadcast_to(variance, (runs,n,n)).copy()
    observed = (None if z is None else np.repeat(z, len(SIGNS), axis=1))
    anchor = data["anchor"]
    bg = math.radians(TB3_BG_DPS if tb3 else BIAS_DEG_PER_S[level])*np.tile(SIGNS, len(DEFAULT_SEEDS))
    intervals = np.searchsorted(cp, np.arange(len(rows))).clip(max=len(cp)-1)
    rejects, attempt, nondetect = (np.zeros((len(cp),runs), dtype=int) for _ in range(3))
    scored = {}
    contributions = {}
    checkpoint_indices = set(cp)
    for i, row in enumerate(rows):
        if i:
            travel = np.abs(gyro[i])
            vary = {}
            if colored:
                radial = (np.sum((mean[:, :2]-anchor[:2])**2, axis=1)+(data["rx_z"]-anchor[2])**2)**.5
                target = np.stack([np.interp(radial, settings["knots"], v)**2 for v in settings["sig"]], axis=1)
                if schmidt:
                    target[:, 1] *= 1-settings["site_corr"]
                phi = np.exp(-np.abs(wheel[i,:,None])/settings["distance_length"] -
                             travel[:,None]/settings["yaw_length"])
                vary = dict(colored_phi=phi, colored_target=target)
            reset = inp["restart"].get(i)
            mean, cov = predict(mean, cov, wheel[i], gyro[i], inp["dt"][i], motion_dim=md,
                                angular_travel_rad=(np.zeros(runs) if reset is not None else travel) if tb3 else None,
                                restart_pose=reset, **vary)
        if observed is not None:
            r_var = np.broadcast_to(settings["thermal"], (runs, 2)).copy()
            s_options = {}
            if base != "R4":
                try:
                    s, jac, s_range_var = m1r_batch(model, obs, banks, mean, cov, anchor, data["rx_z"], rule,
                                                    step_xy_m=.001, step_yaw_rad=np.deg2rad(.1))
                except ValueError as exc:
                    if str(exc) != "Nonpositive M1-R quadrature distance":
                        raise
                    raise UndefinedDistancePrior(f"packet {i}, sequence {row['sequence']}: {exc}") from exc
                s_options = dict(s_expected=s, s_jacobian=jac)
                r_var[:,1] += s_range_var
            if not colored:
                r_var += settings["constant"]
                if base == "J-V":
                    rho = np.sqrt(np.sum((mean[:,:2]-anchor[:2])**2, axis=1)+(data["rx_z"]-anchor[2])**2)
                    r_var[:,1] += np.interp(rho, settings["knots"], settings["sig"][1])**2 - settings["constant"][1]
            options = {}
            if schmidt or use_k:
                considered = np.zeros((runs,n))
                if schmidt:
                    rho = np.sqrt(np.sum((mean[:,:2]-anchor[:2])**2, axis=1)+(data["rx_z"]-anchor[2])**2)
                    considered[:, active+inp["site_index"][inp["packet_sites"][i]]] = (
                        np.interp(rho, settings["knots"], settings["sig"][1])*np.sqrt(settings["site_corr"]))
                if use_k:
                    considered[:, -1] = 1.0
                options["consider_s"] = considered
            diagonal = r_var[...,None]*np.eye(2)
            prior_heading = mean[:,2].copy()
            mean, cov, event = update_rf(mean, cov, observed[i], anchor[:2], data["rx_z"]-anchor[2], offset,
                                         diagonal, arm=arm, motion_dim=md,
                                         colored_columns=(md, md+1) if colored else None,
                                         ci_weight=.5 if base == "J-CI" else None, **s_options, **options)
            if base != "R4":
                block = intervals[i]
                attempt[block] += 1
                rejects[block] += ~event["accepted"]
                nondetect[block] += ~event["available"]
                phase = "sweep" if row["motion"] in ("sweep","hold","in_place") else "move"
                acc = contributions.setdefault(phase, np.zeros(3))
                acc += (runs, event["accepted"].sum(), np.abs(wrap_rad(mean[:,2]-prior_heading)).sum())
        if i in checkpoint_indices:
            scored[i] = score_state(mean, cov, bg, truth[i])
    evidence = []
    for block, i in enumerate(cp):
        e, xy, head, bias = scored[i]
        site = f"{path}/{inp['packet_sites'][i]}"
        repeat_tag = rows[i]["phase"]
        for run, (seed, sign) in enumerate((s,d) for s in DEFAULT_SEEDS for d in SIGNS):
            evidence.append(dict(case=case, arm=arm, level=level, sign=sign, seed=seed, site_id=site,
                                 checkpoint_id=int(rows[i]["sequence"]), checkpoint_order=int(i), phase=repeat_tag,
                                 path=path, heading_included=bool(head[run] <= HEADING_BOUND),
                                 xy_included=bool(xy[run] <= XY_BOUND), nees_heading=float(head[run]),
                                 nees_xy_normalized=float(xy[run]/2), nees_bg=float(bias[run]),
                                 s_rejected=int(rejects[block,run]), s_total=int(attempt[block,run]),
                                 s_unavailable=int(nondetect[block,run]), heading_error_rad=float(e[run,2]),
                                 xy_error_m=float(np.linalg.norm(e[run,:2])),
                                 dr_heading_error_rad=float(dr[i][run]) if dr is not None else float(e[run,2])))
    return evidence, {k: v.tolist() for k,v in contributions.items()}


def case_data(args, case):
    for f, provided_sha in ((args.timeline, args.timeline_sha256), (args.s2, args.s2_sha256),
                            (args.selection, args.selection_sha256), (args.parity, args.parity_sha256)):
        verify(f, provided_sha)
    characterized = read(args.s2)
    selected, parity = read(args.selection), read(args.parity)
    if (characterized["status"] != "PASS" or selected["status"] != "PASS" or parity["status"] != "PASS"
            or characterized["timeline_sha256"] != args.timeline_sha256
            or characterized["s1_receipts_sha256"]["RANGING_RULE_SELECTION.json"] != args.selection_sha256
            or characterized["s1_receipts_sha256"]["PARITY.json"] != args.parity_sha256
            or not (selected["selected"] == characterized["chains"]["OR"]["rule"] == parity["selected_rule"])):
        raise ValueError("S3 input linkage failed")
    index_path = args.results_root / "CASES.json"
    verify(index_path, characterized["production_cases_sha256"])
    index = read(index_path)
    return characterized, selected["selected"], parity, index


def run_fold(args):
    started = utc_now()
    characterized, rule, parity, index = case_data(args, args.case)
    if rule != "O30":
        raise ValueError("This execution path was locked for measured OR == O30")
    data = open_case(args.results_root, index[args.case], args.case)
    if data["input_sha256"] != characterized["input_sha256"][args.case]:
        raise ValueError("S3 input RF hashes differ from S2 input hashes")
    chain = characterized["chains"]["OR"]
    train_anchors = "".join(a for a in "ABC" if a != args.case[-1])
    fit = chain["anchor_fits"][train_anchors]
    model, obs, banks, freq, source, bank_hashes = load_model(args)
    # The training distance histogram is frozen at C2 bin resolution. It is
    # reconstructed from the frozen pose metadata without touching either H.
    distances = []
    for name in train_anchors:
        train_case = f"G-T1_{name}"
        pose_root = args.results_root / "poses" / train_case
        hashes = characterized["input_sha256"][train_case]
        for file in ("SCENE_ENTRY.json", "SAMPLES.json", "rf_poses.json"):
            verify(pose_root/file, hashes[f"poses/{train_case}/{file}"])
        scene = read(pose_root/"SCENE_ENTRY.json")
        poses = read(pose_root/"rf_poses.json")
        ids = bin_key(read(pose_root/"SAMPLES.json"), PA | {"P-A_PRIME", *CURVES})
        xyz = [[poses[i]["x"],poses[i]["y"],scene["rx_z_m"]] for i in ids]
        distances.extend(np.linalg.norm(np.asarray(xyz)-scene["anchors_xyz_m"][name], axis=1))
    settings = variance_setup(fit, np.array(distances), args.snr)
    spacing = max(1., 2*settings["distance_length"][1])
    rows = timeline_data(args.timeline)[args.case][args.path]
    for row in rows:
        for field in ("rf_pose_id", "thermal_noise_seed"):
            row[field] = int(row[field])
    inputs = path_inputs(rows, args.path, spacing)
    measured = None
    if args.arm != "DR":
        measured = paired_observations(data, rows, obs, float(freq[1]-freq[0]), (rule,), snr_db=args.snr)[rule]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    nominal = parity["offsets"][rule]["mean_m"]
    k_var = path_k_variance(chain["C5_by_path"], args.path, train_anchors) if args.arm.endswith("+K") else 0.
    if (args.arm == "DR") != (args.dr is None):
        raise ValueError("Every RF arm requires its matched DR receipt")
    dr_file = read(args.dr) if args.dr else None
    dr = None
    if dr_file is not None:
        if any(dr_file[k] != v for k,v in dict(case=args.case, path=args.path, level=args.level,
                                               arm="DR", snr=args.snr, or_rule=rule).items()):
            raise ValueError("Mismatched DR baseline receipt")
        dr = {int(i): np.array(v) for i, v in dr_file["error_by_packet"].items()}
    report = dict(question_id="G1-MODEL-003", arm=args.arm, case=args.case, path=args.path,
                  level=args.level, snr=args.snr, or_rule=rule, train_anchors=train_anchors,
                  started_utc=started, source_sha256=source, banks_sha256=bank_hashes,
                  s1_sha256=args.selection_sha256, parity_sha256=args.parity_sha256, s2_sha256=args.s2_sha256,
                  timeline_sha256=args.timeline_sha256, paired_dr_sha256=sha(args.dr) if args.dr else None,
                  source_file_sha256=sha(Path(__file__)))
    try:
        evidence, contributions = fit_path(args.case, args.path, args.arm, args.level, data, inputs, measured,
                                           dr, model, obs, banks, rule, nominal, settings, k_var)
    except UndefinedDistancePrior as exc:
        report.update(status="NUMERICAL_FAIL", reason=str(exc))
    else:
        report.update(status="PASS", receipt_rows=evidence, contributions=contributions)
        if args.arm == "DR":
            report["error_by_packet"] = {str(int(i)): [r["heading_error_rad"] for r in evidence
                                                        if r["checkpoint_order"] == int(i)] for i in inputs["cp"]}
    report["finished_utc"] = utc_now()
    temporary = args.out.with_suffix(".json.pending")
    write(temporary, report)
    temporary.replace(args.out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--path", choices=PATHS, required=True)
    parser.add_argument("--level", choices=LEVELS, required=True)
    parser.add_argument("--snr", type=int, choices=(20, 30), required=True)
    for name in ("results-root", "timeline", "model-source", "banks-dir", "s2", "selection", "parity", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("timeline", "s2", "selection", "parity"):
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--dr", type=Path)
    run_fold(parser.parse_args())


if __name__ == "__main__":
    main()
