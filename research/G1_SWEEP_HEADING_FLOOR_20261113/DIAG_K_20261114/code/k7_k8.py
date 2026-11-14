"""K7/K8 oracle diagnostics, using the frozen Q1 observation and candidate code."""
import argparse
import csv
import hashlib
import inspect
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

CASES = ("R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0")
FROZEN_Q1_CSV_SHA256 = "ede1a041dc275a57ca49751257d5c264f861a147e58b42166e0d737902111c3e"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    return None if isinstance(value, float) and not np.isfinite(value) else value


def read_q1(path):
    if path.suffix == ".csv":
        if sha(path) != FROZEN_Q1_CSV_SHA256:
            raise ValueError("Q1 sweep CSV SHA-256 differs from the frozen manifest")
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
    else:
        rows = json.loads(path.read_bytes())
    index = {(row["case"], int(row["group"]), int(row["seed"])): row for row in rows}
    if len(index) != len(rows):
        raise ValueError("Duplicate frozen Q1 sweep key")
    return index


def paired_observation(case, full, los, seeds):
    inputs = case.inputs
    nv = inputs.obs.noise_var_from_snr(30)
    if full.shape != los.shape:
        raise ValueError(f"Channel shapes differ for {case.name}")
    observed, taps = [], []
    for seed in range(seeds):
        rng_full = np.random.default_rng(seed)
        rng_los = np.random.default_rng(seed)
        if rng_full.bit_generator.state != rng_los.bit_generator.state:
            raise ValueError("Paired observation RNG states differ")
        expected = inputs.obs.observe(full, inputs.freqs, nv, rng_full, tx=0)
        paired = inputs.obs.observe(los, inputs.freqs, nv, rng_los, tx=0)
        if rng_full.bit_generator.state != rng_los.bit_generator.state:
            raise ValueError("Paired observations consumed different RNG draws")
        np.testing.assert_array_equal(expected["s"], case.observed[seed])
        np.testing.assert_array_equal(expected["index"], case.taps[seed])
        observed.append(paired["s"])
        taps.append(paired["index"])
    paired = copy(case)
    paired.observed, paired.taps = np.asarray(observed), np.asarray(taps)
    return paired


def features(case, group, feature, calibration, seeds):
    valid = [seed for seed in range(seeds) if case.n_valid(group, seed) >= 3]
    if len(valid) != len(feature.winner_error):
        raise ValueError(f"Feature/seed count mismatch for {case.name} group {group}")
    flat = ~np.isfinite(feature.winner_raw)
    raw = np.where(flat, calibration["cap_raw"], feature.winner_raw)
    return dict(zip(valid, zip(feature.winner_error, calibration["c_l"] * raw, flat)))


def sweep_rows(case, group, offsets, full, los, frozen, seeds):
    for seed in range(seeds):
        key = (case.name, int(group), seed)
        has_full = seed in full
        has_los = seed in los
        if has_full != (key in frozen):
            raise ValueError(f"Q1 valid sweep mismatch: {key}")
        err_full, r_full, flat_full = full.get(seed, (np.nan, np.nan, None))
        err_los, r_los, flat_los = los.get(seed, (np.nan, np.nan, None))
        dx, dy = offsets[seed]
        if has_full:
            ref = frozen.pop(key)
            actual = [err_full, r_full, dx, dy]
            expected = [float(ref[field]) for field in ("err", "r_e1", "dx", "dy")]
            np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12,
                                       err_msg=f"Frozen Q1 full realization mismatch: {key}")
            if str(bool(flat_full)).lower() != str(ref["flat"]).lower():
                raise ValueError(f"Frozen Q1 flat flag mismatch: {key}")
        yield dict(case=key[0], group=key[1], seed=seed, dx=dx, dy=dy,
                   valid_full=has_full, valid_los=has_los, paired=has_full and has_los,
                   e_full=err_full, e_los=err_los, e_mp=(err_full - err_los + 180.0) % 360.0 - 180.0,
                   sqrt_r_full=np.sqrt(r_full), sqrt_r_los=np.sqrt(r_los),
                   flat_full=flat_full, flat_los=flat_los)


def stats(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not values.size:
        return dict(n=0, mean=np.nan, rms=np.nan, max=np.nan)
    return dict(n=values.size, mean=values.mean(), rms=np.sqrt(np.mean(values**2)),
                max=values.max())


def k7_station(case, group, rows):
    site = case.groups[group]
    output = dict(case=case.name, group=int(group), x=site.x, y=site.y,
                  n_full=sum(row["valid_full"] for row in rows),
                  n_los=sum(row["valid_los"] for row in rows),
                  n_paired=sum(row["paired"] for row in rows))
    for field in ("e_full", "e_los", "e_mp", "sqrt_r_full", "sqrt_r_los"):
        summary = stats([row[field] for row in rows if row["paired"]])
        output[f"mean_{field}"] = summary["mean"]
        output[f"rms_{field}"] = summary["rms"]
    los = output["mean_sqrt_r_los"]
    output["sqrt_r_full_to_los"] = output["mean_sqrt_r_full"] / los if los > 0 else np.nan
    output["mean_e_full_q1"] = stats([row["e_full"] for row in rows])["mean"]
    output["mean_sqrt_r_full_q1"] = stats([row["sqrt_r_full"] for row in rows])["mean"]
    return output


def k7_summary(stations, sweeps):
    paired = [row for row in sweeps if row["paired"]]
    result = {"n_stations": len(stations), "n_paired_sweeps": len(paired),
              "n_sweep_slots": len(sweeps), "n_full_valid": sum(row["valid_full"] for row in sweeps),
              "n_los_valid": sum(row["valid_los"] for row in sweeps),
              "paired_sweep_errors": {field: stats([row[field] for row in paired])
                                      for field in ("e_full", "e_los", "e_mp")}}
    means = np.asarray([[row[f"mean_{field}"] for field in ("e_full", "e_los", "e_mp")]
                        for row in stations], dtype=float)
    means = means[np.isfinite(means).all(axis=1)]
    result["n_paired_stations"] = len(means)
    result["paired_station_error_means"] = {
        field: {**stats(means[:, index]), "quantiles": dict(zip(
            ("p10", "p50", "p90"), np.quantile(means[:, index], [.1, .5, .9]))) if len(means) else {}}
        for index, field in enumerate(("e_full", "e_los", "e_mp"))
    }
    if len(means) >= 2:
        var_full, var_los, var_mp = np.var(means, axis=0, ddof=1)
        cov_los_mp = np.cov(means[:, 1], means[:, 2], ddof=1)[0, 1]
        reconstructed = var_los + var_mp + 2 * cov_los_mp
        np.testing.assert_allclose(var_full, reconstructed, rtol=1e-12, atol=1e-12)
        result.update(var_full=var_full, var_los=var_los, var_mp=var_mp,
                      cov_los_mp=cov_los_mp, var_full_from_components=reconstructed,
                      V_model=var_los / var_full if var_full > 0 else np.nan)
    else:
        result.update(var_full=None, var_los=None, var_mp=None, cov_los_mp=None,
                      var_full_from_components=None, V_model=None)
    return result


def signed_s(taps):
    powers = np.abs(taps)**2
    total = powers.sum(axis=1)
    return np.divide(powers[:, 0] - powers[:, 1], total,
                     out=np.full(len(total), np.nan), where=total > 0)


def geometry(setup, case, station, tap_m):
    anchor = np.asarray(case.anchor, dtype=float)
    rx = np.array([station.x, station.y, case.z])
    direct = np.linalg.norm(rx - anchor)
    planes = {"ceiling": (2, setup.height_m), "floor": (2, 0.0),
              "side_plus_y": (1, setup.y_half), "side_minus_y": (1, -setup.y_half)}
    result = {"direct_m": direct, "anchor_ceiling_standoff_m": setup.height_m - anchor[2]}
    for name, (axis, plane) in planes.items():
        image = anchor.copy()
        image[axis] = 2 * plane - image[axis]
        excess = np.linalg.norm(rx - image) - direct
        result[f"{name}_excess_m"] = excess
        result[f"{name}_within_tap"] = bool(excess <= tap_m)
    return result


def k8_station(case, group, full, los, setup, q1):
    station = case.groups[group]
    inputs = case.inputs
    obs = inputs.obs
    ids = station.ids
    cir_full = obs.cir_batch(full[ids, ..., 0])
    cir_los = obs.cir_batch(los[ids, ..., 0])
    adaptive_full = obs.first_path_batch(cir_full, inputs.df)
    adaptive_los = obs.first_path_batch(cir_los, inputs.df)
    k0 = adaptive_los["index"]
    k_full = adaptive_full["index"]
    common_tap_full = cir_full[np.arange(len(ids)), k0]
    common_tap_los = cir_los[np.arange(len(ids)), k0]
    los_amp = np.abs(common_tap_los)
    common_s_los = signed_s(common_tap_los)
    common_s_full = signed_s(common_tap_full)
    np.testing.assert_allclose(common_s_los, case.los_clean[ids], equal_nan=True)
    np.testing.assert_allclose(adaptive_full["s"], case.full_clean[ids], equal_nan=True)
    fixed_delta = common_s_full - common_s_los
    adaptive_delta = case.full_clean[ids] - case.los_clean[ids]
    adaptive_minus_fixed = adaptive_delta - fixed_delta
    common = np.isfinite(fixed_delta) & np.isfinite(adaptive_delta)
    difference = np.abs(common_tap_full - common_tap_los)
    ratio = np.divide(difference, los_amp, out=np.full_like(los_amp, np.nan),
                      where=(los_amp > 0) & common[:, None])
    max_amp = los_amp.max(axis=1)
    conditioning = np.divide(los_amp, max_amp[:, None], out=np.full_like(los_amp, np.nan),
                             where=max_amp[:, None] > 0)
    both = common & np.isfinite(ratio).all(axis=1)
    switched = k_full != k0
    per_yaw = []
    for i, pose in enumerate(ids):
        per_yaw.append(dict(case=case.name, group=int(group), pose=int(pose),
                            yaw_deg=case.yaw[pose], relative_yaw_deg=station.relative[i],
                            k0_los=k0[i], k_adaptive_full=k_full[i], tap_switch=switched[i],
                            valid_common=common[i], valid_both_c=both[i],
                            c_plus45=ratio[i, 0], c_minus45=ratio[i, 1],
                            los_amp_plus45=los_amp[i, 0], los_amp_minus45=los_amp[i, 1],
                            los_relative_amp_plus45=conditioning[i, 0],
                            los_relative_amp_minus45=conditioning[i, 1],
                            delta_s_fixed=fixed_delta[i], delta_s_adaptive=adaptive_delta[i],
                            delta_s_adaptive_minus_fixed=adaptive_minus_fixed[i]))
    tap_m = inputs.hs.C0 / (cir_los.shape[1] * inputs.df)
    output = dict(case=case.name, group=int(group), x=station.x, y=station.y,
                  n_yaw=len(ids), n_common=int(common.sum()), n_both_c=int(both.sum()),
                  tap_m=tap_m, n_tap_switch=int(np.count_nonzero(switched & common)),
                  tap_switch_rate=stats(switched[common])["mean"],
                  abs_e_full_q1=abs(q1["mean_e_full_q1"]),
                  sqrt_r_full_q1=q1["mean_sqrt_r_full_q1"],
                  **geometry(setup, case, station, tap_m))
    common_metrics = {
        "c_plus45": ratio[both, 0], "c_minus45": ratio[both, 1],
        "c": ratio[both].max(axis=1), "abs_delta_s_fixed": np.abs(fixed_delta[both]),
        "abs_delta_s_adaptive": np.abs(adaptive_delta[both]),
        "delta_s_fixed": fixed_delta[both], "delta_s_adaptive": adaptive_delta[both],
        "abs_delta_s_adaptive_minus_fixed": np.abs(adaptive_minus_fixed[both]),
    }
    for name, values in common_metrics.items():
        summary = stats(values)
        output[f"mean_{name}"] = summary["mean"]
        output[f"max_{name}"] = summary["max"]
    for rx, branch in enumerate(("plus45", "minus45")):
        output[f"n_defined_c_{branch}"] = int(np.isfinite(ratio[:, rx]).sum())
        output[f"n_zero_los_amp_{branch}"] = int(np.count_nonzero(los_amp[:, rx] == 0))
        output[f"min_los_relative_amp_{branch}"] = (
            conditioning[common, rx].min() if common.any() else np.nan)
    return output, per_yaw


def k8_summary(rows):
    keys = ("abs_e_full_q1", "sqrt_r_full_q1", "max_c", "max_abs_delta_s_fixed",
            "max_abs_delta_s_adaptive")
    values = np.array([[row[key] for key in keys] for row in rows], dtype=float)
    valid = np.isfinite(values).all(axis=1)
    values = values[valid]
    correlations = {}
    for first, second in ((0, 2), (0, 3), (0, 4), (1, 2)):
        rho = np.nan
        if len(values) >= 3 and np.unique(values[:, first]).size > 1 and np.unique(values[:, second]).size > 1:
            rho = spearmanr(values[:, first], values[:, second]).statistic
        correlations[f"{keys[first]}_vs_{keys[second]}"] = rho
    retained = [row for row, keep in zip(rows, valid) if keep]
    within = [r["abs_e_full_q1"] for r in retained if r["ceiling_within_tap"]]
    outside = [r["abs_e_full_q1"] for r in retained if not r["ceiling_within_tap"]]
    standoffs = sorted({r["anchor_ceiling_standoff_m"] for r in retained})
    return dict(n_stations_total=len(rows), n_common_stations=len(values),
                spearman_common_station_sample=correlations,
                n_yaws=sum(r["n_yaw"] for r in rows),
                n_common_yaws=sum(r["n_common"] for r in rows),
                n_common_both_branch_yaws=sum(r["n_both_c"] for r in rows),
                n_common_yaw_tap_switches=sum(r["n_tap_switch"] for r in rows),
                ceiling_within_tap_abs_e=stats(within), ceiling_outside_tap_abs_e=stats(outside),
                ceiling_contrast_identifiable=bool(within and outside),
                distinct_standoff_m=standoffs, standoff_effect_identifiable=False)


def write_csv(path, rows):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(clean(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("code", "inputs", "banks", "loro", "q1", "out"):
        parser.add_argument(f"--{flag}", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"Choose a fresh output directory: {args.out}")
    sys.path.insert(0, str(args.code.resolve()))
    import v33_observation as v33
    from v32_observation import ObservationCase, ObservationInputs, SEEDS

    inputs = ObservationInputs(args.inputs, args.banks)
    from qclean_uwb.scenarios.corridor import CorridorSetup

    calibration = {key: value["calibration"] for key, value in json.loads(args.loro.read_bytes()).items()}
    frozen = read_q1(args.q1)
    n_frozen = len(frozen)
    xy_rng = np.random.Generator(np.random.PCG64(v33.TRAIN_SEED))
    k7_sites, k7_sweeps, k8_sites, k8_yaws = [], [], [], []
    case_hashes = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name in CASES:
            case = ObservationCase(inputs, name)
            case_hashes[name] = case.hashes
            groups = sorted(case.group_ids)
            offsets = xy_rng.normal(0.0, v33.SIGMA_XY, (len(groups), SEEDS, 2))
            evaluated, _, _ = v33.snap_xy(offsets)
            case_full = np.load(inputs.block / "FULL_RF" / f"H_{name}.npy", mmap_mode="r")
            case_los = np.load(inputs.block / f"H_LoS_{name}.npy", mmap_mode="r")
            paired_case = paired_observation(case, case_full, case_los, SEEDS)
            setup = CorridorSetup(anchor_x_m=float(case.anchor[0]))
            np.testing.assert_allclose(setup.anchor_position, case.anchor, rtol=0, atol=1e-12)
            np.testing.assert_allclose(setup.robot_antenna_z_m, case.z, rtol=0, atol=1e-12)
            full_feats = pool.map(v33._train_group, ((case, group, xy)
                                                   for group, xy in zip(groups, evaluated)))
            los_feats = pool.map(v33._train_group, ((paired_case, group, xy)
                                                  for group, xy in zip(groups, evaluated)))
            for group, xy, f_full, f_los in zip(groups, evaluated, full_feats, los_feats):
                full = features(case, group, f_full, calibration[case.route], SEEDS)
                los = features(paired_case, group, f_los, calibration[case.route], SEEDS)
                rows = list(sweep_rows(case, group, xy, full, los, frozen, SEEDS))
                k7_sweeps.extend(rows)
                row = k7_station(case, group, rows)
                k7_sites.append(row)
                site, yaws = k8_station(case, group, case_full, case_los, setup, row)
                k8_sites.append(site)
                k8_yaws.extend(yaws)
            print(f"{name}: completed {len(groups)} full-span paired stations", flush=True)
    if frozen:
        raise ValueError(f"{len(frozen)} frozen Q1 sweep rows were not reproduced")

    def by_case(rows, name):
        return [row for row in rows if row["case"] == name]

    args.out.mkdir(parents=True, exist_ok=False)
    provenance = dict(argv=sys.argv, q1_rows_checked=n_frozen, case_channel_and_sample_hashes=case_hashes,
                      files_sha256={str(path.resolve()): sha(path) for path in (
                          Path(__file__), args.q1, args.loro, args.code / "v33_observation.py",
                          args.code / "v32_observation.py", args.code / "v32_filter.py",
                          Path(inspect.getfile(inputs.obs)), Path(inspect.getfile(CorridorSetup)))},
                      xy_seed=v33.TRAIN_SEED, xy_sigma_m=v33.SIGMA_XY, seeds=SEEDS,
                      snr_db=30, tx=0)
    k7 = dict(provenance=provenance, cases={
        name: k7_summary(by_case(k7_sites, name), by_case(k7_sweeps, name)) for name in CASES},
        r4_b_abs_full_q1_station_mean_at_least_2_deg=[
            row for row in by_case(k7_sites, "R4_aB_m0") if abs(row["mean_e_full_q1"]) >= 2.0],
        definitions={"paired": "Both arms pass the frozen n_valid>=3 rule for the same station/seed",
                     "r_summary": "Station arithmetic mean of the per-sweep square root of capped calibrated E1 variance",
                     "V_model": "Ratio of ddof=1 station-mean variances on the same paired sweeps",
                     "noise": "Fresh equal RNG states and identical noise variance for both channels; "
                              "original Q1 sigma_s0_sq held fixed"})
    k8 = dict(provenance=provenance, cases={
        name: k8_summary(by_case(k8_sites, name)) for name in CASES},
        pooled=k8_summary(k8_sites), geometry=dict(
            width_m=setup.width_m, height_m=setup.height_m,
            source="Frozen BLOCK_C los_supplement.py: CorridorSetup(anchor_x_m=4.0 or 10.0); "
                   "anchor and robot heights checked against CASES.json",
            path_interpretation="Plane-image excess length, based on nominal geometry",
            standoff_effect="No controlled standoff intervention; descriptive ceiling groups only"),
        definitions={
            "common_yaw": "Both signed-s differences finite; station contamination and s summaries "
                          "also require finite c in both RX branches on the same yaws",
            "conditioning": "A zero LoS denominator is undefined. Report the branch LoS amplitude "
                            "relative to the larger of the two LoS branch amplitudes at the common tap",
            "delta_s": "Report both fixed-LoS-tap delta and native adaptive-tap delta",
            "association": "Station max c over both branches and common yaws; both max absolute delta_s "
                           "definitions reported. Q1 station average error and average sqrt_R use every "
                           "Q1-valid sweep. Correlations share the same finite station subset."})
    for filename, result in (("K7_LOS_ATTRIBUTION.json", k7), ("K8_TAP_CONTAMINATION.json", k8)):
        (args.out / filename).write_text(json.dumps(clean(result), indent=2, allow_nan=False) + "\n",
                                         encoding="utf-8")
    for filename, rows in (("K7_station_rows.csv", k7_sites), ("K7_sweep_rows.csv", k7_sweeps),
                           ("K8_station_rows.csv", k8_sites), ("K8_yaw_rows.csv", k8_yaws)):
        write_csv(args.out / filename, rows)


if __name__ == "__main__":
    main()
