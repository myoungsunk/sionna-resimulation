"""D7/D7.1 on frozen BLOCK_C inputs. One worker per case/bias cohort."""
import argparse
import json
from dataclasses import asdict
from math import radians
from pathlib import Path

from check_d7_limits import SPEC_COMMIT, D4_SHA, d4_inputs, load_frozen_case
import numpy as np

from diag_inputs import CASES, COHORTS, WORK, control_paths, init_modules, sha256
from diag_jc import Term, replay
from diag_metrics import checkpoints, paired_bootstrap, score_sufficient, CHI1_95, CHI2_95
from d7_d1 import decompose_d1
from diag_spatial import trajectory_inputs, unique_pose_indices
from run_diag import scenario_key, stats, utc, write_json
from diag_replay import wrap

ROOT = Path("/d7/main")
GATE_ROOT = Path("/d7/attempt_02")
VARIANTS = ("JC_upper", "JC_infinite", "JC_K_upper", "JC_K_infinite")


def checked_results():
    manifest = json.loads((WORK/"MANIFEST.json").read_text(encoding="utf-8"))
    return manifest["outputs_sha256"]


def frozen_file(case, name, hashes):
    path = WORK / "results" / case / name
    key = path.relative_to(WORK).as_posix()
    if sha256(path) != hashes[key]:
        raise ValueError(f"Frozen input hash mismatch: {key}")
    return path


def donor_stats(case, phases, out):
    hashes = checked_results()
    file = frozen_file(case, "D4_PACKET_WINDOW.npz", hashes)
    with np.load(file, allow_pickle=False) as a:
        t, pose, distance, s_error, clean_range = [a[k] for k in
                            ("t", "pose", "distance_m", "error", "range_full_m")]
    meta = phases[case]["case"]
    mu = phases[case]["mu"]
    xy = pose[:, :2] - meta["anchor"][:2]
    height = meta["anchor"][2] - meta["robot_z_m"]
    predicted = np.sqrt(np.sum(xy**2, axis=1) + height**2) - .5315983906250129
    r_error = clean_range - mu - predicted
    _, coords, ss = trajectory_inputs(distance, pose, s_error)
    _, _, rr = trajectory_inputs(distance, pose, r_error)
    result = {}
    for channel, e in ((0, rr), (1, ss)):
        eligible = np.flatnonzero((t >= 30) & np.isfinite(e))
        idx = unique_pose_indices(coords, eligible)
        if not len(idx):
            raise ValueError(f"Insufficient donor poses for {case}, channel {channel}")
        result[str(channel)] = {"sum_squares": float(np.sum(e[idx]**2)),
                                "unique_poses": len(idx), "source_sha256": sha256(file)}
    write_json(out, result)
    return result


def resolve_fit(fit, suffix, resolution):
    upper = float(fit[f"length_fit_bounds_{suffix}"][1])
    candidate = float(fit[f"fit_candidate_length_{suffix}"])
    length = fit[f"length_{suffix}"]
    if np.isclose(candidate, upper, rtol=1e-8, atol=0):
        return {"flag": "upper", "length": upper, "search_upper": upper, "resolution": resolution}
    if fit["status"] != "OK" or length is None:
        raise ValueError(f"Unresolved D4 fit: {fit}")
    return {"flag": "white" if length <= resolution else "ar",
            "length": length, "search_upper": upper, "resolution": resolution}


def input_receipt(root):
    run_dir = ROOT
    for case in CASES:
        entry = json.loads((GATE_ROOT/f"GATE_{case}.json").read_text(encoding="utf-8"))
        if entry["status"] != "PASS" or entry["spec_commit"] != SPEC_COMMIT:
            raise ValueError("D7 comparison gate not satisfied")
    r = json.loads((root/"range_input_diagnostic.json").read_text(encoding="utf-8"))
    for case in CASES:
        if r[case]["diff_max_abs_m"] > 1e-13:
            raise ValueError("Measured and clean range mismatch")
    return run_dir


def prepare(root):
    input_receipt(root)
    ROOT.mkdir(exist_ok=False)
    d4 = d4_inputs()
    init_modules()
    info = {}
    for case in CASES:
        data = load_frozen_case(case, ROOT/"bank_audit")
        info[case] = {"case": data["case"], "mu": data["mu"][:, 0]}
        del data
    donors = {case: donor_stats(case, info, ROOT/f"DONOR_{case}.json") for case in CASES}
    result = {}
    for case in CASES:
        record = d4[case]
        resolution_deg = 4.76 if case == "R4_aB_m0" else 5.0
        rd = resolve_fit(record["range_residual_variogram"]["exponential_fit"], "m", .04)
        sd = resolve_fit(record["distance_variogram"]["exponential_fit"], "m", .04)
        sy = resolve_fit(record["rotation_yaw_correlation"]["exponential_fit"], "deg", resolution_deg)
        upper = {0: rd["flag"] == "upper", 1: "upper" in (sd["flag"], sy["flag"])}
        rvar = float(record["range_residual_variance_m2"])
        sigma_s = tuple(float(row["s_rms"]) for row in record["distance_scale"])
        range_term = Term(0, "white" if rd["flag"] == "white" else "ar", rvar,
                          distance_length=rd["length"])
        s_term = Term(1, "white" if "white" in (sd["flag"], sy["flag"]) else "ar", sigma_s,
                      distance_length=sd["length"], yaw_length=radians(sy["length"]))
        source_paths = [c for c in CASES if c != case and c.split("_")[1] == case.split("_")[1]]
        considers = {}
        for channel in (0, 1):
            if upper[channel]:
                sources = source_paths or [case]
                samples = [donors[c][str(channel)] for c in sources]
                v = sum(r["sum_squares"] for r in samples) / sum(r["unique_poses"] for r in samples)
                considers[channel] = {"variance": v, "sources": sources,
                                      "label": "OUT_OF_ROUTE" if source_paths else "IN_SAMPLE_VARIANCE"}
        if not upper[1]:
            considers[1] = {"variance": record["long_5m"]["moving_average"]["mean_square"],
                            "sources": [case], "label": "D4_IN_SAMPLE_W5"}
        main = (range_term, s_term)
        extra = tuple(Term(ch, "consider", c["variance"]) for ch, c in considers.items())
        replacement = tuple(Term(j, "consider", considers[j]["variance"]) if upper[j] else term
                            for j, term in enumerate(main))
        terms = {"JC_upper": main, "JC_infinite": replacement,
                 "JC_K_upper": main + extra,
                 "JC_K_infinite": replacement + tuple(t for t in extra if not upper[t.channel])}
        result[case] = {"range_fit": rd, "s_distance_fit": sd, "s_yaw_fit": sy,
                        "upper": upper, "consider_variance": considers,
                        "terms": {k: [asdict(x) for x in v] for k, v in terms.items()}}
    write_json(ROOT/"PARAMETERS.json", {"classification": "DIAGNOSTIC_ONLY", "spec": SPEC_COMMIT,
               "D4_sha256": D4_SHA, "cases": result, "donors": donors,
               "donor_weight": "equal per unique evaluation pose, pooled across same-anchor other routes",
               "initialization": "zero mean independent latent states, first estimated range for initial variance",
               "propagation": "literal D7 local Q; previous posterior range, odometric |ds| and bias-corrected gyro yaw increment",
               "limits": "0.04 m moving packet spacing; 5 deg yaw grid except 4.76 deg R4; white variance folded into R",
               "plus_K": "W5 s second moment unless upper, where corresponding donor second moment is used; no duplicate consider state"})


def arm_terms(rows):
    result = []
    for row in rows:
        fields = dict(row)
        if isinstance(fields["variance"], list):
            fields["variance"] = tuple(fields["variance"])
        for key in ("distance_length", "yaw_length"):
            if fields[key] is None:
                fields[key] = np.inf
        result.append(Term(**fields))
    return tuple(result)


def compare_inputs(data, cp, case, key):
    p = WORK/"results"/case
    with np.load(p/f"{key}_D5_CHECKPOINT.npz", allow_pickle=False) as b, \
         np.load(p/f"{key}_D6_CHECKPOINT.npz", allow_pickle=False) as v:
        for prior in (b, v):
            np.testing.assert_array_equal(prior["checkpoint_index"], cp["checkpoint_index"])
            np.testing.assert_array_equal(prior["site"], cp["site_id"])
        return {"J4": b["base"], "R4": b["r4"], "DR4": b["dr"], "J-V": v["variance"]}


def metrics(data, cp, result, bias, base, observed_error):
    score = stats(result, data, cp, bias)
    heading = wrap(result["state"][..., 2] - data["pose"][:, 2])
    a = decompose_d1(observation_error=observed_error, innovation=result["innovation"],
                    transition=result["transition"], jacobian=result["jacobian"],
                    gain=result["gain"], accepted=result["accepted"], heading_error_rad=heading,
                    heading_nees=heading**2/result["covariance"][..., 2, 2],
                    checkpoint_index=cp["checkpoint_index"], distance_m=cp["distance_m"])
    update = result["heading_update_rad"]
    ev = data["t"] >= 30
    rotation = update[:, ev & data["rotation"]].sum(axis=1)
    straight = update[:, ev & ~data["rotation"]].sum(axis=1)
    share = rotation.sum()/(rotation+straight).sum()
    row = {"frame": score_sufficient(score["frame"].sum(axis=0)),
           "frame_per_seed": score_sufficient(score["frame"]),
           "paired_checkpoint": {k: paired_bootstrap(score["checkpoint"], v, site_id=cp["site_id"])
                                 for k, v in base.items()},
           "heading_update_straight_rad_per_seed": straight,
           "heading_update_rotation_rad_per_seed": rotation,
           "heading_update_rotation_share": share, "D1": a}
    return row, score


def execute(case, level, sign):
    key = scenario_key(level, sign)
    out = ROOT/case
    out.mkdir(exist_ok=True)
    print("START", case, key, utc(), flush=True)
    init_modules()
    data = load_frozen_case(case, out/f"BANK_{key}")
    cp = checkpoints(data["t"], data["pose"])
    control, initial, bias = control_paths(data, level, sign, range(20))
    base = compare_inputs(data, cp, case, key)
    poses = np.column_stack([data["pose"], np.zeros(len(data["t"]))])
    expected = np.concatenate([data["model"](poses[i:i+64], data["case"])[0]
                               for i in range(0, len(poses), 64)])
    observed_error = data["z"] - data["mu"] - expected
    params = json.loads((ROOT/"PARAMETERS.json").read_text(encoding="utf-8"))["cases"][case]
    result, arrays, done = {}, {}, {}
    for name in VARIANTS:
        terms = arm_terms(params["terms"][name])
        if terms in done:
            result[name] = {"identical_to": done[terms], **result[done[terms]]}
            continue
        a = replay(data, control, initial, terms, save_linearization=True)
        result[name], score = metrics(data, cp, a, bias, base, observed_error)
        for field in ("frame", "checkpoint", "checkpoint_error", "checkpoint_covariance"):
            arrays[f"{name}_{field}"] = score[field]
        done[terms] = name
        print("ARM", case, key, name, utc(), flush=True)
    np.savez_compressed(out/f"{key}.npz", **base, **arrays, site=cp["site_id"],
                        checkpoint_index=cp["checkpoint_index"], distance=cp["checkpoint_distance_m"],
                        time_s=data["t"][cp["checkpoint_index"]])
    write_json(out/f"{key}.json", {"classification": "DIAGNOSTIC_ONLY", "case": case, "bias": level,
                                   "sign": sign, "arms": result, "seeds": list(range(20))})
    print("COMPLETE", case, key, utc(), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--case", choices=CASES)
    p.add_argument("--level")
    p.add_argument("--sign", type=int)
    a = p.parse_args()
    if a.prepare:
        prepare(Path("/d7"))
    elif a.case is not None and (a.level, a.sign) in COHORTS:
        execute(a.case, a.level, a.sign)
    else:
        p.error("Provide --prepare or a valid case/level/sign cohort")


if __name__ == "__main__":
    main()
