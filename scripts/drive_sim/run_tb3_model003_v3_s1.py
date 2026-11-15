"""G1-MODEL-003 v3 S1′: distance-only detector selection, then LoS parity."""

import argparse
import math
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_model003_s1 import BATCH, CASES, DRAWS, ROUTES, SEED, SNRS, batches, observe_s, open_case, synthetic_los
from run_tb3_production import utc_now, verify
from tb3_model003_m1r_batch import m1r_values
from tb3_model003_s1_observation import RULES, channel_to_cir, range_candidates, self_check
from validate_tb3_g4 import load_model

QUESTION = "G1-MODEL-003"
TIMELINE_SHA256 = "4d591aa6b0bd2955b3e61cbda8fcba8eab8aafe431caed1a94f3c7c85f3d4cfd"
O30_TIE_M = 0.005
MAX_FAILURE = 0.01
MAX_PARITY = 0.005


def route_poses(data):
    out = {}
    for case, case_data in data.items():
        ids = sorted(set().union(*(case_data["by_set"][name] for name in ROUTES)))
        if not ids:
            raise ValueError(f"No frozen S1 ranging poses for {case}")
        out[case] = ids
    return out


def los_offsets(observation, df_hz, data, pose_ids):
    """One constant per candidate, pooled over unique matched noise-free RT LoS poses."""
    errors = {rule: [] for rule in RULES}
    anchor_summaries = {rule: {} for rule in RULES}
    for case, case_data in data.items():
        per_case = {rule: [] for rule in RULES}
        for ids in batches(pose_ids[case]):
            cir = channel_to_cir(case_data["los"][ids], observation)
            for rule, row in range_candidates(cir, df_hz).items():
                error = row["range_m"] - case_data["d"][ids]
                if not row["detected"].all() or not np.isfinite(error).all():
                    raise ValueError(f"Invalid deterministic LoS offset sample for {case}/{rule}")
                per_case[rule].append(error)
        for rule, items in per_case.items():
            values = np.concatenate(items)
            errors[rule].append(values)
            anchor_summaries[rule][case] = dict(poses=len(values), mean_m=float(values.mean()))
    return {rule: dict(mean_m=float(np.concatenate(values).mean()), poses=sum(map(len, values)),
                       cases=anchor_summaries[rule], source="noise-free G-T1 RT H_LoS")
            for rule, values in errors.items()}


def full_scores(observation, df_hz, data, pose_ids, offsets):
    """Use identical noisy full-H CIRs for all candidates and frozen v2 pose/draw weighting."""
    sums = {(rule, snr): np.zeros(5) for rule in RULES for snr in SNRS}
    for anchor, (case, case_data) in enumerate(data.items()):
        for draw in range(DRAWS):
            for snr in SNRS:
                rng = np.random.default_rng(np.random.SeedSequence([SEED, anchor, draw]))
                noise = observation.noise_var_from_snr(snr)
                for ids in batches(pose_ids[case]):
                    cir = channel_to_cir(case_data["full"][ids], observation, noise_var=noise, rng=rng)
                    threshold = observation.detection_threshold(noise, n_taps=cir.shape[1])
                    for rule, row in range_candidates(cir, df_hz, threshold=threshold).items():
                        found = row["detected"]
                        error = row["range_m"][found] - case_data["d"][ids][found]
                        residual = error - offsets[rule]["mean_m"]
                        sums[rule, snr] += (len(ids), len(error), error.sum(), residual.sum(), residual @ residual)
        print(f"{case}: distance-only scores at {len(pose_ids[case])} RF poses", flush=True)
    scores = {rule: {} for rule in RULES}
    for (rule, snr), (n, detected, bias, residual, squares) in sums.items():
        scores[rule][snr] = dict(attempted=int(n), detected=int(detected), failure_rate=float((n - detected)/n),
                                 raw_bias_m=float(bias/detected) if detected else None,
                                 residual_bias_m=float(residual/detected) if detected else None,
                                 residual_rms_m=float(np.sqrt(squares/detected)) if detected else None)
    return scores


def select_rule(scores):
    eligible = {
        rule: float(np.mean([row["residual_rms_m"] for row in scores[rule].values()]))
        for rule in RULES
        if all(scores[rule][snr]["failure_rate"] <= MAX_FAILURE for snr in SNRS)
    }
    if not eligible:
        return dict(status="FAIL", selected=None, min_rms_rule=None, min_mean_rms_m=None,
                    eligible_mean_rms_m={}, o30_gap_m=None)
    best = min(eligible, key=eligible.get)
    o30_gap = eligible["O30"] - eligible[best] if "O30" in eligible else None
    # Treat roundoff at the exactly 5 mm boundary as equality, for a strict < 5 mm tie.
    tie = (o30_gap is not None and o30_gap < O30_TIE_M
           and O30_TIE_M - o30_gap > 4 * math.ulp(max(eligible["O30"], eligible[best], O30_TIE_M)))
    return dict(status="PASS", selected="O30" if tie else best, min_rms_rule=best,
                min_mean_rms_m=eligible[best], eligible_mean_rms_m=eligible, o30_gap_m=o30_gap)


def selected_parity(model, observation, banks, frequency, data, rule, out):
    """Regenerate selected-rule point-distance predictions before comparison to RT LoS."""
    df_hz = float(frequency[1] - frequency[0])
    summary, arrays = {}, {}
    errors = {"lut": [], "m1r": []}
    for case, case_data in data.items():
        pose_id = np.arange(len(case_data["d"]))
        rt = np.concatenate([observe_s(case_data["los"][ids], observation, df_hz, rule)
                             for ids in batches(pose_id)])
        lut = np.concatenate([observe_s(synthetic_los(model, banks, case_data, ids), observation, df_hz, rule)
                              for ids in batches(pose_id)])
        nominal, variance = m1r_values(model, observation, banks, case_data["direction"], case_data["yaw"],
                                       case_data["d"], 0., rule)
        summary[case] = dict(poses=len(pose_id))
        for name, values in (("lut", lut), ("m1r", nominal)):
            delta = np.abs(values - rt)
            finite = np.isfinite(delta)
            summary[case][name] = dict(invalid=int(np.count_nonzero(~finite)),
                                       p90_abs_delta_s=float(np.quantile(delta, .90)) if finite.all() else None)
            errors[name].append(delta)
        arrays.update({f"{case}_{key}": value for key, value in
                       dict(pose_id=pose_id, lut_s=lut, m1r_s=nominal, m1r_var=variance, rt_los_s=rt).items()})

    storage = out / "LUT_M1R_PARITY_V3.npz"
    np.savez_compressed(storage, **arrays)
    pooled = {}
    for name, case_errors in errors.items():
        delta = np.concatenate(case_errors)
        finite = np.isfinite(delta)
        pooled[name] = dict(p90_abs_delta_s=float(np.quantile(delta, .90)) if finite.all() else None,
                            max_abs_delta_s=float(delta.max()) if finite.all() else None,
                            invalid=int(np.count_nonzero(~finite)))
    good = all(item["invalid"] == 0 and item["p90_abs_delta_s"] <= MAX_PARITY for item in pooled.values())
    worst_p90 = max(item["p90_abs_delta_s"] for item in pooled.values()) if not any(
        item["invalid"] for item in pooled.values()) else None
    return dict(status="PASS" if good else "FAIL", selected_rule=rule, threshold_p90_abs_delta_s=MAX_PARITY,
                p90_abs_delta_s=worst_p90, pooled=pooled, cases=summary, m1r_prior_sigma_m=0.,
                prediction_file=storage.name, prediction_sha256=sha(storage))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results-root", "model-source", "banks-dir", "s0-report", "delay-origin", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("s0-sha256", "delay-origin-sha256", "code-commit"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    verify(args.s0_report, args.s0_sha256)
    s0 = read(args.s0_report)
    if (s0.get("question_id") != QUESTION or s0.get("version") != 3 or s0.get("stage") != "S0"
            or s0.get("status") != "PASS" or s0.get("timeline_sha256") != TIMELINE_SHA256):
        raise ValueError("S1′ requires a frozen v3 S0 PASS")
    verify(args.delay_origin, args.delay_origin_sha256)
    origin = read(args.delay_origin)
    if origin["status"] != "PASS" or (origin["matches"], origin["poses"]) != (6012, 6012):
        raise ValueError("Invalid v2 delay-origin receipt")
    started = utc_now()
    idx_path = args.results_root / "CASES.json"
    verify(idx_path, origin["production_cases_sha256"])
    index = read(idx_path)
    data = {case: open_case(args.results_root, index[case], case) for case in CASES}
    input_sha = {case: case_data["input_sha256"] for case, case_data in data.items()}
    if input_sha != origin["input_sha256"]:
        raise ValueError("G-T1 input hashes differ from the frozen delay-origin receipt")
    model, observation, banks, frequency, source_sha, banks_sha = load_model(args)
    self_check(observation)
    df_hz = float(frequency[1] - frequency[0])
    poses = route_poses(data)
    metadata = dict(question_id=QUESTION, version=3, stage="S1'", role="IMPLEMENTER", code_commit=args.code_commit,
                    s0_sha256=args.s0_sha256, timeline_sha256=TIMELINE_SHA256,
                    delay_origin_sha256=args.delay_origin_sha256, started_utc=started,
                    delay_origin_matches=origin["matches"], delay_origin_poses=origin["poses"],
                    production_cases_sha256=sha(idx_path), input_sha256=input_sha, banks_sha256=banks_sha,
                    source_sha256=source_sha | {name: sha(Path(__file__).with_name(name)) for name in
                                               (Path(__file__).name, "run_tb3_model003_s1.py",
                                                "tb3_model003_s1_observation.py", "tb3_model003_m1r_batch.py")})
    args.out.mkdir(mode=0o700, exist_ok=False, parents=True)
    offsets = los_offsets(observation, df_hz, data, poses)
    scores = full_scores(observation, df_hz, data, poses, offsets)
    choice = select_rule(scores)
    selection = choice | metadata | dict(
        results=scores, offsets=offsets, ranging_pose_sets=sorted(ROUTES),
        selected_pose_counts={case: len(ids) for case, ids in poses.items()},
        max_detection_failure_per_snr=MAX_FAILURE, o30_tie_width_m=O30_TIE_M,
        seed=SEED, thermal_draws_per_pose=DRAWS, pose_batch_size=BATCH, finished_utc=utc_now())
    selection_file = args.out / "RANGING_RULE_SELECTION_V3.json"
    write(selection_file, selection)
    if choice["status"] != "PASS":
        return 2
    rule = choice["selected"]
    parity = selected_parity(model, observation, banks, frequency, data, rule, args.out)
    write(args.out / "PARITY_V3.json",
          parity | metadata | dict(offsets=offsets, selection_sha256=sha(selection_file), finished_utc=utc_now()))
    return 0 if parity["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
