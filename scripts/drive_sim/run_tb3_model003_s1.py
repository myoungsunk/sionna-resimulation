"""Run the G1-MODEL-003 S1 observation gate on G-T1 only."""

import argparse
import math
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import utc_now, verify
from tb3_model003_s1_observation import RULES, channel_to_cir, range_candidates, self_check, signed_s_at_tap
from validate_tb3_g4 import load_model


CASES = ("G-T1_A", "G-T1_B", "G-T1_C")
PA = {"P-A_TEACH", "P-A_REPEAT"}
ROUTES = PA | {"P-A_PRIME", "P-B", "C1", "C2", "C3", "C4"}
SNRS = (20, 30)
BATCH = 64
SEED = 20261115
DRAWS = 20


def batches(ids):
    for start in range(0, len(ids), BATCH):
        yield ids[start:start + BATCH]


def open_case(root, indexed, case):
    directory = root / "H" / case
    manifest = directory / "MANIFEST.json"
    verify(manifest, indexed["manifest_sha256"])
    hashes = read(manifest)["output_sha256"]
    required = ("H_LoS.npy", "H_full.npy")
    pose_names = ("rf_poses.json", "SAMPLES.json", "SCENE_ENTRY.json")
    for name in [*(directory / name for name in required),
                 *(root / "poses" / case / name for name in pose_names)]:
        verify(name, hashes[name.relative_to(root).as_posix()])
    poses, samples, scene = [read(root / "poses" / case / p) for p in pose_names]
    los, full = [np.load(directory / name, mmap_mode="r", allow_pickle=False) for name in required]
    if los.shape != full.shape or los.shape != (len(poses), 257, 2, 2):
        raise ValueError(f"Invalid case channel arrays at {case}")
    if [p["pose_id"] for p in poses] != list(range(len(poses))):
        raise ValueError(f"Unexpected pose ordering at {case}")
    anchor = np.asarray(scene["anchors_xyz_m"][case[-1]], dtype=float)
    delta = np.array([[p["x"], p["y"], scene["rx_z_m"]] for p in poses]) - anchor
    d = np.linalg.norm(delta, axis=1)
    yaw = np.array([p["yaw_body_deg"] for p in poses])
    by_set = {name: sorted({r["pose_id"] for r in samples if r["set"] == name})
              for name in sorted({r["set"] for r in samples})}
    return dict(los=los, full=full, direction=delta / d[:, None], d=d, yaw=yaw, by_set=by_set,
                input_sha256={"manifest": indexed["manifest_sha256"], **hashes})


def synthetic_los(model, banks, data, ids):
    return np.stack([model.los_h(banks, data["direction"][i], float(data["yaw"][i]), float(data["d"][i]))
                     for i in ids])


def check_origin(model, obs, banks, df, cases):
    result = {}
    for case, data in cases.items():
        ids = sorted(set().union(*(data["by_set"][name] for name in PA)))
        if not ids:
            raise ValueError(f"G-T1 P-A pose coverage empty: {case}")
        mismatches = []
        for ii in batches(ids):
            h = synthetic_los(model, banks, data, ii)
            ref = range_candidates(channel_to_cir(h, obs), df, rules=("O30",))["O30"]
            rt = range_candidates(channel_to_cir(data["los"][ii], obs), df, rules=("O30",))["O30"]
            match = (ref["index"] == rt["index"]) & ref["detected"] & rt["detected"]
            mismatches.extend(dict(pose_id=i, synthetic=int(ref["index"][j]), rt=int(rt["index"][j]))
                              for j, i in enumerate(ii) if not match[j])
        result[case] = dict(poses=len(ids), matches=len(ids)-len(mismatches), mismatches=mismatches)
    total = sum(x["poses"] for x in result.values())
    good = sum(x["matches"] for x in result.values())
    return dict(status="PASS" if good / total >= 0.99 else "FAIL", match_fraction=good / total,
                poses=total, matches=good, cases=result, applied_delay_offset_s=0.0)


def range_scores(obs, df, cases):
    sums = {(rule, snr): np.zeros(4) for rule in RULES for snr in SNRS}
    sizes = {}
    for anchor, (case, data) in enumerate(cases.items()):
        ids = sorted(set().union(*(data["by_set"][name] for name in ROUTES)))
        if not ids:
            raise ValueError(f"Original G-T1 pose coverage empty: {case}")
        sizes[case] = len(ids)
        for draw in range(DRAWS):
            for snr in SNRS:
                rng = np.random.default_rng(np.random.SeedSequence([SEED, anchor, draw]))
                var = obs.noise_var_from_snr(snr)
                for ii in batches(ids):
                    cir = channel_to_cir(data["full"][ii], obs, noise_var=var, rng=rng)
                    rows = range_candidates(cir, df, threshold=obs.detection_threshold(var, n_taps=cir.shape[1]))
                    for rule, row in rows.items():
                        valid = row["detected"]
                        error = row["range_m"][valid] - data["d"][ii][valid]
                        sums[rule, snr] += (len(ii), len(error), error.sum(), error @ error)
        print(f"{case}: ranging at {len(ids)} RF poses", flush=True)
    table = {}
    for rule in RULES:
        table[rule] = {}
        for snr in SNRS:
            n, valid, s, sq = sums[rule, snr]
            table[rule][snr] = dict(attempted=int(n), detected=int(valid), failure_rate=float(1 - valid / n),
                                    bias_m=float(s / valid) if valid else None,
                                    rmse_m=float(np.sqrt(sq / valid)) if valid else None)
    eligible = {rule: np.mean([m["rmse_m"] for m in row.values()]) for rule, row in table.items()
                if all(m["failure_rate"] <= 0.01 for m in row.values())}
    best = min(eligible, key=eligible.get) if eligible else None
    mean_rmse = None if best is None else float(eligible[best])
    chosen = ("O30" if best and "O30" in eligible and eligible["O30"] - mean_rmse < 0.01 else best)
    return dict(status="PASS" if chosen else "FAIL", selected=chosen, min_rmse_rule=best,
                min_mean_rmse_m=mean_rmse, results=table, selected_pose_counts=sizes,
                seed=SEED, thermal_draws_per_pose=DRAWS, pose_batch_size=BATCH)


def range_offset(model, obs, banks, freq, rules):
    rng = np.random.default_rng(20261007)
    distances = np.arange(2.0, 16.0, 0.01)
    ph = np.exp(-2j * np.pi * freq[None, :] * (distances[:, None] - 1.0) / model.C0) / distances[:, None]
    df = float(freq[1] - freq[0])
    values = {rule: [] for rule in rules}
    for _ in range(150):
        th, pt, pr = np.radians((rng.uniform(10, 80), rng.uniform(-180, 180), rng.uniform(-180, 180)))
        direction = model.ANCHOR_ROTATION @ np.array([np.sin(th)*np.cos(pt), np.sin(th)*np.sin(pt), np.cos(th)])
        yaw = np.degrees(np.arctan2(-direction[1], -direction[0]) - pr)
        h = model.los_h(banks, direction, yaw, dist_m=1.0)[None] * ph[..., None, None]
        taps = range_candidates(channel_to_cir(h, obs), df, rules=rules)
        for rule in rules:
            if not taps[rule]["detected"].all():
                raise ValueError(f"Invalid deterministic offset calibration for {rule}")
            values[rule].append(float(np.mean(taps[rule]["range_m"] - distances)))
    return {rule: dict(mean_m=float(np.mean(rows)), std_over_directions_m=float(np.std(rows)),
                       directions=len(rows), seed=20261007) for rule, rows in values.items()}


def observe_s(h, obs, df, rule):
    cir = channel_to_cir(h, obs)
    fields = range_candidates(cir, df, rules=(rule,))[rule]
    return signed_s_at_tap(cir, fields["tap"], fields["detected"])


def m1r_s(model, obs, banks, direction, yaw_deg, prior_distance_m, prior_sigma_m, rule):
    """Compute prior-distance integrated s, independent of measured RF range."""
    if prior_sigma_m < 0 or prior_distance_m <= 0:
        raise ValueError("Invalid geometric distance prior")
    if prior_sigma_m == 0:
        distances, weights = [prior_distance_m], np.ones(1)
    else:
        nodes, w = np.polynomial.hermite.hermgauss(5)
        distances = prior_distance_m + np.sqrt(2) * prior_sigma_m * nodes
        weights = w / math.sqrt(math.pi)
        if np.any(distances <= 0):
            raise ValueError("Nonpositive M1-R quadrature distance")
    h = np.stack([model.los_h(banks, direction, yaw_deg, float(d)) for d in distances])
    freq = banks[0].freqs_hz
    values = observe_s(h, obs, float(freq[1] - freq[0]), rule)
    mean = float(weights @ values)
    return mean, float(weights @ (values - mean)**2)


def parity(model, obs, banks, freq, cases, rule):
    df = float(freq[1] - freq[0])
    deltas, summary = [], {}
    for case, data in cases.items():
        delta = []
        for ii in batches(list(range(len(data["d"])))):
            h = synthetic_los(model, banks, data, ii)
            delta.extend(np.abs(observe_s(h, obs, df, rule) - observe_s(data["los"][ii], obs, df, rule)))
        if not np.isfinite(delta).all():
            raise ValueError(f"Nonfinite signed-s parity at {case}")
        summary[case] = dict(poses=len(delta), p90_abs_delta_s=float(np.quantile(delta, 0.90)),
                             max_abs_delta_s=float(max(delta)))
        deltas.extend(delta)
    pooled = float(np.quantile(deltas, 0.90))
    return dict(status="PASS" if pooled <= 0.005 else "FAIL", selected_rule=rule,
                p90_abs_delta_s=pooled, max_abs_delta_s=float(max(deltas)), cases=summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results-root", "release-receipt", "model-source", "banks-dir", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    release = read(args.release_receipt)
    if release.get("status") != "PASS" or release.get("s1_eligible") is not True:
        raise ValueError("S1 requires a PASS receipt with S1 eligibility")
    started = utc_now()
    args.out.mkdir(mode=0o700, exist_ok=False, parents=True)
    model, obs, banks, freq, source_sha, bank_sha = load_model(args)
    self_check(obs)
    df = float(freq[1]-freq[0])
    idx_path = args.results_root / "CASES.json"
    verify(idx_path, read(args.results_root / "GENERATION_RESULT.json")["cases_sha256"])
    index = read(idx_path)
    data = {case: open_case(args.results_root, index[case], case) for case in CASES}
    metadata = dict(question_id="G1-MODEL-003", role="IMPLEMENTER", started_utc=started,
                    release_sha256=sha(args.release_receipt), production_cases_sha256=sha(idx_path),
                    input_sha256={case: ctx["input_sha256"] for case, ctx in data.items()},
                    source_sha256=source_sha | {name: sha(Path(__file__).with_name(name)) for name in
                                               (Path(__file__).name, "tb3_model003_s1_observation.py")},
                    banks_sha256=bank_sha)
    origin = check_origin(model, obs, banks, df, data)
    write(args.out / "DELAY_ORIGIN.json", origin | metadata)
    print(f"S1 delay origin: {origin['matches']}/{origin['poses']} ({origin['status']})", flush=True)
    if origin["status"] != "PASS":
        return 2
    choice = range_scores(obs, df, data)
    write(args.out / "RANGING_RULE_SELECTION.json", choice | metadata)
    if choice["status"] != "PASS":
        return 2
    rule = choice["selected"]
    offsets = range_offset(model, obs, banks, freq, tuple(dict.fromkeys((rule, "O30"))))
    check = parity(model, obs, banks, freq, data, rule)
    write(args.out / "PARITY.json", check | metadata | dict(offsets=offsets, finished_utc=utc_now()))
    return 0 if check["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
