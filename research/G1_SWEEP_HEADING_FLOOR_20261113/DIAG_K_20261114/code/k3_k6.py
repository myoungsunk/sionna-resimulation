"""G1-DIAG-002 K3–K6 offline filter contrasts.

This driver imports the frozen implementation. Only the requested measurement
variance, measurement bias, and revisit eligibility interventions are applied.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import csv
from functools import partial
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np


VISITS = 10
BOOTSTRAPS = 200
NR_SEED = 2026111401
BOOTSTRAP_SEED = 20261113
REPLAY_KEYS = ("err", "p_ee", "nees", "covered", "miss", "used", "reject", "invalid")
BOOT_KEYS = ("err", "p_ee", "nees", "covered")
FABLE_KAPPA = (0.46, 0.40, 0.14, 1.80, 0.46, 0.44)
MODEL_VARIANTS = {
    "independent": ("base", "scale", "bias"),
    "markov": ("base", "scale", "bias", "oracle_both", "skip"),
    "cell": ("base",),
    "nr_rand": ("base", "scale", "bias"),
    "nr_seq": ("base",),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("code", "inputs", "banks", "grid", "entry", "frozen", "q1", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.workers <= 24:
        parser.error("--workers must be in 1..24")
    return args


def oracle_parameters(q1_path, names, stations):
    by_site = defaultdict(list)
    seen = set()
    with q1_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            name = row["case"]
            group = int(row["group"])
            key = (name, group, int(row["seed"]))
            values = np.array([float(row["err"]), float(row["r_e1"])])
            if key in seen or not np.all(np.isfinite(values)) or values[1] <= 0:
                raise ValueError(f"Unusable or duplicate Q1 sweep: {key}")
            seen.add(key)
            by_site[name, group].append(values)
    expected_sites = {(name, g) for name in names for g in stations[name]["gids"]}
    if set(by_site) != expected_sites:
        raise ValueError("Q1 groups do not match the frozen physical stations")
    results = []
    for name, reference in zip(names, FABLE_KAPPA, strict=True):
        site_sweeps = [np.asarray(by_site[name, g]) for g in stations[name]["gids"]]
        moments = np.asarray([
            (np.mean(sweeps[:, 0]), np.mean(np.sqrt(sweeps[:, 1])))
            for sweeps in site_sweeps
        ])
        mu = float(np.mean(moments[:, 0]))
        kappa = float(np.mean((moments[:, 0] / moments[:, 1]) ** 2))
        if not np.isfinite(kappa) or kappa <= 0:
            raise ValueError(f"{name}: nonpositive oracle variance multiplier")
        delta = abs(kappa - reference)
        results.append(dict(case=name, mu_deg=mu, kappa=kappa, sites=len(moments),
                            sweeps=sum(map(len, site_sweeps)), fable_rounded_kappa=reference,
                            kappa_abs_diff_from_fable=delta, kappa_abs_diff_exceeds_001=delta > 0.01))
    return results


def no_repeat_paths(stations, names, cases, nominal, seed_count, lane_pool):
    independent = nominal[:, :VISITS]
    # Frozen independent RF seed identifiers equal the seed uniforms used by
    # all S2 models on entering a new group. Every NR visit enters a new group.
    rf_seeds = independent % seed_count
    rng = np.random.default_rng(NR_SEED)
    eligible = np.array([len(stations[names[c]]["gids"]) >= VISITS for c in cases])
    random_paths = np.flatnonzero(eligible)
    random_rows = np.empty((len(random_paths), VISITS), dtype=int)
    for slot, p in enumerate(random_paths):
        table = stations[names[cases[p]]]["rows"]
        sites = rng.permutation(len(table))[:VISITS]
        random_rows[slot] = table[sites, rf_seeds[p]]

    seq_paths = []
    seq_rows = []
    geometry = {}
    for c, name in enumerate(names):
        station = stations[name]
        base_paths = np.flatnonzero(cases == c)
        count = 0
        lane_report = {}
        for side, leg in lane_pool[name][1].items():
            windows = max(0, len(leg) - VISITS + 1)
            lane_report[str(side)] = {
                "ordered_group_ids": [int(station["gids"][g]) for g in leg],
                "ordered_x_m": station["x"][leg].tolist(),
                "ordered_y_m": station["y"][leg].tolist(),
                "windows_per_direction": windows,
            }
            for start in range(windows):
                forward = leg[start:start + VISITS]
                for sites in (forward, forward[::-1]):
                    p = base_paths[count % len(base_paths)]
                    seq_rows.append(station["rows"][sites, rf_seeds[p]])
                    seq_paths.append(p)
                    count += 1
        geometry[name] = {
            "status": "EVALUATED" if count else "INAPPLICABLE_NO_WITHIN_LANE_WINDOW",
            "paths": count,
            "crn_ids_reused": max(0, count - len(base_paths)),
            "lanes_y_gt_zero": lane_report,
        }

    sequence = (np.asarray(seq_paths, dtype=int),
                np.asarray(seq_rows, dtype=int).reshape(-1, VISITS))
    return (random_paths, random_rows), sequence, geometry


def revisit_mask(rows, seed_count):
    site_ids = rows // seed_count
    revisit = np.zeros_like(site_ids, dtype=bool)
    for k in range(1, site_ids.shape[1]):
        revisit[:, k] = np.any(site_ids[:, k:k + 1] == site_ids[:, :k], axis=1)
    return revisit


def simulate_arm(filter_module, bank, rows, paths, dr, assigned, rho, cal, bias, skip):
    def curves(k):
        j, chi2, valid, truth = bank.access(rows[:, k], k, paths)
        if skip is not None:
            valid = np.where(skip[:, k], 0, valid)
        return j, chi2, valid, truth

    if bias is None:
        outcome = filter_module.simulate(curves, dr[paths], assigned, rho, cal)
    else:
        frozen_branch_update = filter_module._branch_update
        path_bias = bias[assigned, None]

        def corrected_update(x, p, features, variance, sigma_a2, dr_absolute, gate):
            # Preserve J, window search, and branch selection on unshifted RF.
            # Shift candidate yaw only at the measurement update.
            corrected = replace(features, yaw_deg=filter_module.wrap(features.yaw_deg - path_bias))
            return frozen_branch_update(x, p, corrected, variance, sigma_a2, dr_absolute, gate)

        with patch.object(filter_module, "_branch_update", corrected_update):
            outcome = filter_module.simulate(curves, dr[paths], assigned, rho, cal)
    if skip is not None:
        if np.any(outcome["used"][skip] | outcome["reject"][skip]) or not np.all(outcome["invalid"][skip]):
            raise AssertionError("Revisit suppression reached an RF update")
        # Separate synthetic RF ineligibility from actual invalid RF outcomes.
        outcome["invalid"][skip] = False
    return outcome


def cluster_worker(args, names, stations, rho, cal, scale_cal, mu, case, dr, xy, nominal, outer, paths):
    import s2_primary_final as frozen
    import v33_filter as filt

    bank = frozen.GroupedBank(args.inputs, args.banks, args.grid, stations, xy[paths])
    local_cases = case[paths]
    local_dr = dr[paths]
    local_paths = np.arange(len(paths))
    variants = {}
    bias_variants = {"bias", "oracle_both", "skip"}
    scale_variants = {"scale", "oracle_both", "skip"}
    try:
        for model_i, model in enumerate(frozen.MODELS):
            rows = nominal[model_i, paths, :VISITS]
            rep_rows = outer[model_i, :BOOTSTRAPS, :, :VISITS][:, paths, :]
            if rep_rows.shape != (BOOTSTRAPS, len(paths), VISITS):
                raise ValueError(f"Unexpected bootstrap row dimensions: {rep_rows.shape}")
            variants[model] = {}
            for arm in MODEL_VARIANTS[model]:
                arm_cal = scale_cal if arm in scale_variants else cal
                bias = mu if arm in bias_variants else None
                skip = revisit_mask(rows, frozen.SEEDS) if arm == "skip" else None
                result = simulate_arm(filt, bank, rows, local_paths, local_dr,
                                      local_cases, rho, arm_cal, bias, skip)
                cluster = {key: [] for key in BOOT_KEYS}
                # Frozen runner groups multiple replicates per candidate call.
                for start in range(0, BOOTSTRAPS, 12):
                    reps = np.arange(start, min(start + 12, BOOTSTRAPS))
                    batch_rows = rep_rows[reps].reshape(-1, VISITS)
                    batch_paths = np.tile(local_paths, len(reps))
                    assigned = ((local_cases[None, :] + reps[:, None]) % len(names)).ravel()
                    batch_skip = revisit_mask(batch_rows, frozen.SEEDS) if arm == "skip" else None
                    result_batch = simulate_arm(filt, bank, batch_rows, batch_paths, local_dr,
                                                assigned, rho, arm_cal, bias, batch_skip)
                    for key in BOOT_KEYS:
                        cluster[key].append(result_batch[key].reshape(len(reps), len(paths), VISITS))
                variants[model][arm] = result, {key: np.concatenate(cluster[key]) for key in BOOT_KEYS}
                if paths[0] == 0:
                    print(f"cluster {model}/{arm} done on shard 0", flush=True)
        return variants
    finally:
        bank.close()


def point_stats(data, dr, rows, seed_count, skip=None):
    err = data["err"]
    distinct = VISITS - np.sum(revisit_mask(rows, seed_count), axis=1)
    coverage = float(np.mean(data["covered"]))
    nees = float(np.mean(data["nees"]))
    rmse = float(np.sqrt(np.mean(err**2)))
    dr_rmse = float(np.sqrt(np.mean(dr**2)))
    return {
        "paths": len(rows),
        "visits": rows.size,
        "included": int(np.count_nonzero(data["covered"])),
        "not_covered": int(np.count_nonzero(~data["covered"])),
        "coverage": coverage,
        "nees": nees,
        "rms_z": float(np.sqrt(nees)),
        "case_integrity_pass": coverage >= 0.88 and 0.5 <= nees <= 2.0,
        "mean_heading_error_deg": float(np.mean(err)),
        "heading_rmse_deg": rmse,
        "dr_rmse_deg": dr_rmse,
        "rmse_ratio": rmse / dr_rmse if dr_rmse else None,
        "mean_95_halfwidth_deg": float(np.mean(1.96 * np.sqrt(data["p_ee"]))),
        "distinct_station_p25_p50_p75": np.quantile(distinct, [.25, .50, .75]).tolist(),
        "coverage_by_visit": np.mean(data["covered"], axis=0).tolist(),
        "nees_by_visit": np.mean(data["nees"], axis=0).tolist(),
        "window_misses": int(np.count_nonzero(data["miss"])),
        "updates": int(np.count_nonzero(data["used"])),
        "gated": int(np.count_nonzero(data["reject"])),
        "invalid": int(np.count_nonzero(data["invalid"])),
        "intentional_revisit_skips": int(np.count_nonzero(skip)) if skip is not None else 0,
    }


def summary_metrics(data, dr):
    err = data["err"]
    axes = (1, 2)
    rmse = np.sqrt(np.mean(err**2, axis=axes))
    dr_rmse = np.sqrt(np.mean(dr**2, axis=axes))
    return dict(coverage=np.mean(data["covered"], axis=axes), nees=np.mean(data["nees"], axis=axes),
                mean_heading_error_deg=np.mean(err, axis=axes), heading_rmse_deg=rmse,
                rmse_ratio=rmse / dr_rmse,
                mean_95_halfwidth_deg=np.mean(1.96 * np.sqrt(data["p_ee"]), axis=axes))


def intervals(samples):
    if not all(np.isfinite(series).all() for series in samples.values()):
        raise ValueError("Nonfinite bootstrap metric")
    return {name: np.quantile(series, [.025, .975]).tolist() for name, series in samples.items()}


def summaries(names, data, dr, rows, cases, seed_count, cluster=None, rotated=None, skip=None):
    by_case, samples_by_case = {}, {}
    for c, name in enumerate(names):
        mask = cases == c
        if not np.any(mask):
            by_case[name] = {"status": "INAPPLICABLE_NO_ELIGIBLE_PATH"}
            continue
        local = {key: val[mask] for key, val in data.items()}
        point = point_stats(local, dr[mask], rows[mask], seed_count,
                            skip[mask] if skip is not None else None)
        if cluster is not None:
            # Every case has 33 or 34 paths depending on frozen bootstrap
            # rotation. Reduce per replicate to preserve its actual count.
            samples = defaultdict(list)
            for b in range(BOOTSTRAPS):
                selected = rotated[b] == c
                boot_local = {key: val[b:b + 1, selected] for key, val in cluster.items()}
                for key, val in summary_metrics(boot_local, dr[None, selected]).items():
                    samples[key].append(val[0])
            point["interval_type"] = "S2_STATION_CLUSTER_PERCENTILE"
        else:
            indices = np.random.default_rng(BOOTSTRAP_SEED + c).integers(
                np.count_nonzero(mask), size=(BOOTSTRAPS, np.count_nonzero(mask)))
            conditional = {k: local[k][indices] for k in BOOT_KEYS}
            samples = summary_metrics(conditional, dr[mask][indices])
            point["interval_type"] = "FIXED_STATION_BANK_PATH_PERCENTILE"
            point["station_cluster_interval"] = None
            point["interval_scope"] = (
                "Descriptive path-resampling interval conditional on the observed physical "
                "stations and realized paths. The frozen station-cluster procedure can "
                "leave fewer than ten eligible physical stations, especially for R4."
            )
        samples_by_case[name] = {k: np.asarray(v) for k, v in samples.items()}
        point["bootstrap_replicates"] = BOOTSTRAPS
        point["ci95"] = intervals(samples_by_case[name])
        by_case[name] = point
    return by_case, samples_by_case


def write_json(path, obj):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, allow_nan=False, indent=2)
        stream.write("\n")


def main():
    args = parse_args()
    sys.path.insert(0, str(args.code))
    import s2_primary_final as frozen
    import v33_filter as filt

    names, rho, _ = frozen.validate_entry(args)
    stations = frozen.build_stations(args.inputs, args.banks, names)
    if tuple(len(s["gids"]) for s in stations.values()) != frozen.EXPECTED:
        raise ValueError("Unexpected station inventory")
    calibration_file = args.frozen / "S1P_ERR_MODEL_LORO.json"
    calibration = frozen.load(calibration_file)
    cal = [frozen.Calibration(**calibration[name.split("_")[0]]["calibration"]) for name in names]
    parameters = oracle_parameters(args.q1, names, stations)
    mu = np.array([p["mu_deg"] for p in parameters])
    kappa = np.array([p["kappa"] for p in parameters])
    if any(c.constant_r is not None for c in cal):
        raise ValueError("Expected E1 curvature-based calibration for all cases")
    scale_cal = [replace(c, c_l=c.c_l * k) for c, k in zip(cal, kappa)]
    with np.load(args.frozen / "S2P_DRAWS.npz", allow_pickle=False) as draws:
        np.testing.assert_array_equal(draws["cases"], names)
        np.testing.assert_array_equal(draws["models"], frozen.MODELS)
        case, dr, xy, nominal, outer = [draws[k] for k in (
            "case_index", "dr", "xy", "nominal_rows", "outer_rows")]
    model_i = {m: i for i, m in enumerate(frozen.MODELS)}
    nr_rand, nr_seq, geometry = no_repeat_paths(
        stations, names, case, nominal[model_i["independent"]], frozen.SEEDS,
        frozen.legacy.station_pool(stations))
    for _, rows in (nr_rand, nr_seq):
        if np.any(revisit_mask(rows, frozen.SEEDS)):
            raise AssertionError("Duplicate physical station in a no-revisit path")
    all_paths = np.arange(len(case))
    rho_values = list(rho.values())
    rotated = (case[None, :] + np.arange(BOOTSTRAPS)[:, None]) % len(names)
    parts = list(np.array_split(all_paths, min(args.workers, len(all_paths))))
    evaluate = partial(cluster_worker, args, names, stations, rho_values, cal,
                       scale_cal, mu, case, dr[:, :VISITS], xy[:, :VISITS], nominal, outer)
    with ProcessPoolExecutor(max_workers=len(parts)) as workers:
        shards = list(workers.map(evaluate, parts))
    results, bootstrap_samples = {}, {}
    with np.load(args.frozen / "S2P_NOMINAL.npz", allow_pickle=False) as expected:
        np.testing.assert_array_equal(case, expected["case_index"])
        for model in frozen.MODELS:
            rows = nominal[model_i[model], :, :VISITS]
            for arm in MODEL_VARIANTS[model]:
                points = [shard[model][arm][0] for shard in shards]
                data = {k: np.concatenate([p[k] for p in points]) for k in REPLAY_KEYS}
                cluster = {k: np.concatenate([shard[model][arm][1][k] for shard in shards], axis=1)
                           for k in BOOT_KEYS}
                if arm == "base":
                    for key in REPLAY_KEYS:
                        np.testing.assert_array_equal(data[key], expected[f"{model}_{key}"][:, :VISITS])
                arm_skip = revisit_mask(rows, frozen.SEEDS) if arm == "skip" else None
                key = model, arm
                results[key], bootstrap_samples[key] = summaries(
                    names, data, dr[:, :VISITS], rows, case, frozen.SEEDS, cluster, rotated, arm_skip)

    bank = frozen.GroupedBank(args.inputs, args.banks, args.grid, stations, xy[:, :VISITS])
    try:
        for model, (paths, rows) in (("nr_rand", nr_rand), ("nr_seq", nr_seq)):
            for arm in MODEL_VARIANTS[model]:
                key = model, arm
                if not len(paths):
                    results[key] = {name: {"status": "INAPPLICABLE_NO_ELIGIBLE_PATH"} for name in names}
                    continue
                data = simulate_arm(filt, bank, rows, paths, dr[:, :VISITS], case[paths],
                                    rho_values, scale_cal if arm == "scale" else cal,
                                    mu if arm == "bias" else None, None)
                results[key], bootstrap_samples[key] = summaries(
                    names, data, dr[paths, :VISITS], rows, case[paths], frozen.SEEDS)
    finally:
        bank.close()

    parent_metadata = dict(
        classification="DIAGNOSTIC_ONLY", s2_prime_verdict="STOP", step3="HELD",
        visits=VISITS, frozen_nominal_replay="all three base models match visits 1–10 exactly",
        case_pass="coverage >= .88 and mean heading NEES in [0.5, 2.0]",
        cluster_draws="first 200 unchanged outer draws and rotated path case assignments from S2P_DRAWS",
        frozen_rho_by_case=rho,
        q1_sha256=hashlib.sha256(args.q1.read_bytes()).hexdigest(),
        calibration_sha256=hashlib.sha256(calibration_file.read_bytes()).hexdigest(),
        oracle_scale_definition="mean_station((mean_seed(error_deg)/mean_seed(sqrt(R_E1)))**2)",
        oracle_scale_scope=(
            "Candidate R_E1 is multiplied by kappa via c_L, with frozen R_cap,raw and r_bar. "
            "Frozen AR variance sigma_a2=rho*r_bar, AR process, and initial covariance are reused. "
            "White variance is max(kappa*R_E1-sigma_a2, 0.25*kappa*R_E1)."
        ),
        oracle_bias_definition="mean_station(mean_seed(aligned_wrapped_candidate_error_deg))",
        oracle_bias_scope="Subtract mu from candidate yaw in measurement update after unadjusted window and J selection.",
        oracle_parameters=parameters,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "K3_NR.json", dict(
        **parent_metadata, nr_seed=NR_SEED,
        random_path_count_scope="200 total frozen S2 paths with unchanged case assignments",
        crn="reuse frozen DR, XY, and independent RF seed for each path/visit",
        seq_geometry="same y-sign lanes and stable ascending x from frozen station_pool; enumerate forward and reverse",
        seq_crn_assignment="within each case, ascending frozen path IDs in sequence enumeration order (cycle only if path IDs exhausted)",
        nr_seq_geometry=geometry,
        arms={m: results[m, "base"] for m in MODEL_VARIANTS}))
    for variant, filename in (("scale", "K4_ORACLE_SCALE.json"), ("bias", "K5_ORACLE_BIAS.json")):
        write_json(args.out / filename, dict(
            **parent_metadata,
            arms={m: results[m, variant] for m in ("independent", "markov", "nr_rand")},
            matched_frozen_lever={m: results[m, "base"] for m in ("independent", "markov", "nr_rand")}))
    keys = {
        "K6-00": ("markov", "base"), "K6-10": ("markov", "scale"),
        "K6-01": ("nr_rand", "base"), "K6-11": ("nr_rand", "scale"),
        "K6-OB": ("markov", "oracle_both"), "K6-SKIP": ("markov", "skip"),
    }
    arms = {label: results[key] for label, key in keys.items()}
    contrasts = {}
    for name in names:
        point = {arm: arms[arm][name] for arm in keys}
        ob = bootstrap_samples["markov", "oracle_both"][name]
        skip = bootstrap_samples["markov", "skip"][name]
        metrics = ("coverage", "nees", "heading_rmse_deg", "rmse_ratio")
        contrasts[name] = {
            "skip_minus_ob": {k: point["K6-SKIP"][k] - point["K6-OB"][k] for k in metrics},
            "skip_minus_ob_station_cluster_ci95": intervals({k: skip[k] - ob[k] for k in metrics}),
            "scale_interaction_nr_minus_markov": {
                k: ((point["K6-11"][k] - point["K6-01"][k])
                    - (point["K6-10"][k] - point["K6-00"][k])) for k in metrics
            },
            "scale_interaction_station_cluster_ci95": None,
        }
    write_json(args.out / "K6_INTERACTION.json", dict(
        **parent_metadata, arms=arms, paired_contrasts=contrasts,
        comparison="All conditions use first ten visits. OB and SKIP share paths, RF, DR, XY, scale and bias.",
        skip_rule="Suppress RF update on all repeats of a physical group, including nonconsecutive revisits.",
        boundary="A skip contrast tests that intervention under oracle conditions; it cannot quantify a site-bias filter."
    ))


if __name__ == "__main__":
    main()
