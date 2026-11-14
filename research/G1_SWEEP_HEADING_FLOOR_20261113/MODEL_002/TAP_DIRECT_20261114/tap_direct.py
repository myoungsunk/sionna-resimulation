"""Goal 1 direct prior-tap diagnosis on the frozen six-case Q1 sweep bank."""
import argparse
import csv
import hashlib
import inspect
import json
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from k7_k8 import CASES, clean, read_q1, sha, signed_s, write_csv

ARMS = ("detected", "oracle", "prior_frac", "prior_direct")
FIXED_BASE = "94bcc0814d80edf07fba40bf4536004b5ac5a079"
ORIGINAL_SUMMARY_SHA = "663c82bc7602e3999032bd4e0ab1cbefee5ed83b07edde2f8478442f6c1c2708"
ORIGINAL_SWEEPS_SHA = "abed7ec040eed4d02228efed58bd61fa29796ce575ab9b11c869b717e571caae"


def make_kernel(distances, freq, hann, c):
    return np.exp(2j * np.pi * (np.asarray(distances)[..., None] / c)
                  * (freq - freq[0])) * (hann / 4.0)


def ratio(values):
    return signed_s(np.asarray(values).reshape(-1, 2)).reshape(values.shape[:-1])


def select_distance(h_group, valid, center, sigma, freq, hann, c, noise_var):
    tap_m = c / (4 * len(freq) * (freq[1] - freq[0]))
    if sigma == 0.0:
        grid = np.array([center])
    else:
        half = 3.0 * sigma
        half_bins = int(np.ceil(half / (tap_m / 8.0)))
        grid = np.linspace(center - half, center + half, 2 * half_bins + 1)
    if grid[0] <= 0:
        raise ValueError("Unexpected nonpositive geometry window")
    tap = np.einsum("gf,pfr->gpr", make_kernel(grid, freq, hann, c), h_group, optimize=True)
    energy = (np.abs(tap[:, valid])**2).sum(axis=(1, 2))
    variance = noise_var * np.sum(hann**2) / 16.0
    score = energy / variance
    if sigma:
        score -= (grid - center)**2 / (2 * sigma**2)
    if not np.isfinite(score).all():
        raise ValueError("Nonfinite delay score")
    tied = np.flatnonzero(score == score.max())
    best = tied[np.argmin(np.abs(grid[tied] - center))]
    return grid[best], tap[best], len(grid) > 1 and best in (0, len(grid) - 1), energy[best] / variance


def prior_leading_tap(distances, inputs):
    """Map geometry to the pinned leading edge of a deterministic LoS template."""
    d = np.atleast_1d(np.asarray(distances, dtype=float))[:, None, None]
    freq = inputs.freqs[None, :, None]
    c = inputs.hs.C0
    if not (np.isfinite(d) & (d > 0) & (d < c / inputs.df)).all():
        raise ValueError("Geometry outside unambiguous CIR range")
    template = c / (4. * np.pi * freq * d) * np.exp(-2j * np.pi * freq * d / c)
    cir = inputs.obs.cir_batch(np.repeat(template, 2, axis=2))
    if not np.isfinite(cir).all() or np.any(np.abs(cir).max(axis=(1, 2)) <= 0):
        raise ValueError("Invalid geometry-only LoS template")
    return inputs.obs.first_path_batch(cir, inputs.df)["index"]


def validate_leading_edge(inputs):
    # Direct DFT of independently defined tap phases, no detector in reference.
    frequency = inputs.freqs
    n = len(frequency)
    length = 4 * n
    spacing = inputs.hs.C0 / (length * inputs.df)
    distances = spacing * np.array([7., 13.125, 20.49, 35.51, 67.9, 97.])
    position = np.arange(length)[:, None] / length - distances[None, :] / (length * spacing)
    tap_phase = 2j * np.pi * np.arange(n)[None, :, None] * position[:, None, :]
    hann = np.sin(np.pi * np.arange(n) / (n-1)) ** 2
    magnitude = np.abs(np.einsum("knd,n->kd", np.exp(tap_phase), hann / frequency))
    peak = magnitude.argmax(axis=0)
    crossed = magnitude >= 0.30 * magnitude.max(axis=0, keepdims=True)
    expected = crossed.argmax(axis=0)
    actual = prior_leading_tap(distances, inputs)
    np.testing.assert_array_equal(actual, expected)
    if not np.all(actual < peak):
        raise ValueError("Single-path geometry picks a peak instead of the leading edge")
    return {"single_path_cases": len(distances), "leading_indices": actual.tolist(),
            "peak_indices": peak.tolist(), "tap_spacing_m": spacing}


def validate_fourier(inputs):
    freq = inputs.freqs
    hann = inputs.obs.hann(len(freq))
    c = inputs.hs.C0
    rng = np.random.default_rng(22)
    h = rng.normal(size=(3, len(freq), 2)) + 1j * rng.normal(size=(3, len(freq), 2))
    tap = np.array([0, 1, 19, 72, 301, 1027])
    d = tap * c / (4 * len(freq) * inputs.df)
    direct = np.einsum("gf,pfr->pgr", make_kernel(d, freq, hann, c), h)
    expected = inputs.obs.cir_batch(h)[:, tap]
    np.testing.assert_allclose(direct, expected, atol=2e-10, rtol=2e-12)
    true_d = 7.1234
    amps = np.array([[1+2j, 2-1j], [2+1j, .4-.2j], [0.35+0.4j, 1.2+0.70j]])
    wave = np.exp(-2j * np.pi * (freq - freq[0]) * true_d / c)
    h_single = wave[None, :, None] * amps[:, None, :]
    est, values, edge, _ = select_distance(h_single, np.ones(len(amps), bool),
                                            7.2, .13, freq, hann, c, 1e-6)
    np.testing.assert_allclose(ratio(values), ratio(amps), atol=1e-13, rtol=0.0)
    if abs(est - true_d) > (c / (4 * len(freq) * inputs.df)) / 8 or edge:
        raise ValueError("Single-path fractional fit failed")
    return {"ifft_max_abs": float(np.max(np.abs(direct-expected))),
            "single_path_distance_error_m": abs(est - true_d),
            "single_path_max_abs_s_diff": float(np.max(np.abs(ratio(values)-ratio(amps))))}


def fixed_predictions(case, group, dx, dy, sigma, yaw_grid, extraction):
    """Compute FFD LoS polarization at fixed observed read locations."""
    from v32_observation import LOG_WEIGHTS, NODES, PRIMARY_IMU_K

    g = case.groups[group]
    inputs = case.inputs
    origin = np.array([g.x + dx, g.y + dy, case.z])
    v = origin - case.anchor
    center = np.linalg.norm(v)
    unit = v / center
    relative = g.relative + PRIMARY_IMU_K * np.abs(g.relative)
    yaw = yaw_grid[:, None] + relative
    lo, alpha = inputs.azimuth_interpolation(unit, (yaw + case.mount).ravel())
    indices = np.union1d(lo, lo + 1)
    channel = inputs.channel_knots(unit, indices)
    lo = np.searchsorted(indices, lo).reshape(yaw.shape)
    alpha = alpha.reshape(yaw.shape)[..., None]
    if extraction.shape not in ((1,), (len(g.ids),)):
        raise ValueError("Expected a sweep-common or pose-specific read location")
    unique, per_pose = np.unique(np.broadcast_to(extraction, (len(g.ids),)),
                                 return_inverse=True)
    freq = inputs.freqs
    c = inputs.hs.C0
    hann = inputs.obs.hann(len(freq))
    nodes = np.array([center]) if sigma == 0 else center + np.sqrt(2.) * sigma * NODES

    def at_node(d):
        # The omitted exp(-2pi i f0 d/c) is common to both ports and cancels in s.
        kernel = make_kernel(unique - d, freq, hann, c) * c / (freq * (4.*np.pi*d))
        field = np.einsum("gf,kfr->kgr", kernel, channel, optimize=True)
        a = field[lo, per_pose]
        b = field[lo + 1, per_pose]
        return ratio(a + alpha * (b - a))

    preds = np.stack([at_node(d) for d in nodes])
    if not np.isfinite(preds).all():
        raise ValueError(f"Nonfinite predicted s {case.name}/{group}")
    weights = np.zeros(1) if sigma == 0 else LOG_WEIGHTS
    return preds, weights


def check_predictions(case, group, dx, dy, oracle_dist, prior_dist, direct_idx):
    from v32_observation import PRIMARY_IMU_K

    g = case.groups[group]
    inputs = case.inputs
    c = inputs.hs.C0
    freq = inputs.freqs
    unit_vec = np.array([g.x+dx, g.y+dy, case.z]) - case.anchor
    d = np.linalg.norm(unit_vec)
    unit = unit_vec / d
    grid = np.array([g.yaw_deg-1., g.yaw_deg, g.yaw_deg+1.])
    az = grid[:, None] + g.relative + PRIMARY_IMU_K * np.abs(g.relative) + case.mount
    lo, alpha = inputs.azimuth_interpolation(unit, az.ravel())
    channel = inputs.channel_knots(unit)
    at_pose = channel[lo] + alpha[:, None, None] * (channel[lo+1]-channel[lo])
    at_pose *= (np.exp(-2j * np.pi * freq * d / c) * c / (4*np.pi*freq*d))[None, :, None]
    tap_ids = np.rint(oracle_dist * 4 * len(freq) * inputs.df / c).astype(int)
    cir = inputs.obs.cir_batch(at_pose)
    reference_oracle = cir[np.arange(len(lo)), np.tile(tap_ids, len(grid))]
    direct_dist = direct_idx * c / (4 * len(freq) * inputs.df)
    reference_direct = cir[:, direct_idx]
    kernel = make_kernel(prior_dist, freq, inputs.obs.hann(len(freq)), c)
    reference_prior = np.einsum("f,pfr->pr", kernel, at_pose)
    errors = {}
    for label, dist, ref in (("oracle", oracle_dist, reference_oracle),
                             ("prior", np.array([prior_dist]), reference_prior),
                             ("prior_direct", np.array([direct_dist]), reference_direct)):
        prediction, _ = fixed_predictions(case, group, dx, dy, 0., grid, dist)
        ref_s = ratio(ref).reshape(az.shape)
        np.testing.assert_allclose(prediction[0], ref_s, atol=1e-9, rtol=0)
        errors[label] = float(np.max(np.abs(prediction[0]-ref_s)))
    return errors


def baseline_group(task):
    from run_step1 import GRID, wrap
    from v32_filter import candidate_features
    import v33_observation as v33

    case, group, xy, calibration = task
    truth = case.groups[group].yaw_deg
    indices = np.flatnonzero(np.abs(wrap(GRID - truth)) <= 12. + 1e-10)
    costs, residuals = (np.full((len(xy), len(GRID)), np.nan) for _ in range(2))
    for seed, (dx, dy) in enumerate(xy):
        cost, residual = v33._curves(case, group, dx, dy, seeds=slice(seed, seed+1),
                                     yaw_indices=indices)
        costs[seed, indices], residuals[seed, indices] = cost[0], residual[0]
    n_valid = np.array([case.n_valid(group, seed) for seed in range(len(xy))])
    picked = candidate_features(costs, residuals, n_valid, truth, 10., max_candidates=None)
    valid = np.flatnonzero(picked.count)
    np.testing.assert_array_equal(valid, np.flatnonzero(n_valid >= 3))
    raw = picked.r_raw[valid, 0]
    flat = ~np.isfinite(raw)
    r = calibration["c_l"] * np.where(flat, calibration["cap_raw"], raw)
    rows = {}
    for at, seed in enumerate(valid):
        rows[int(seed)] = (
            float(wrap(picked.yaw_deg[seed, 0]-truth)), float(r[at]), bool(flat[at]),
            bool(picked.boundary[seed, 0]), int(n_valid[seed]))
    return rows


def fit_changed(case, group, dx, dy, sigma, observed, extraction, indices):
    from run_step1 import GRID, wrap
    from v32_filter import candidate_features
    from v32_observation import cost_curves

    pred, weights = fixed_predictions(case, group, dx, dy, sigma, GRID[indices], extraction)
    cost, residual = cost_curves(observed[None], pred, case.sigma_s0_sq, weights)
    costs, residuals = (np.full((1, len(GRID)), np.nan) for _ in range(2))
    costs[0, indices], residuals[0, indices] = cost[0].astype(np.float32), residual[0].astype(np.float32)
    truth = case.groups[group].yaw_deg
    n_valid = int(np.isfinite(observed).sum())
    picked = candidate_features(costs, residuals, np.array([n_valid]), truth, 10., max_candidates=None)
    if picked.count[0] == 0:
        if n_valid >= 3:
            raise ValueError(f"No winner among valid observations: {case.name}/{group}")
        return np.nan, False, n_valid
    return float(wrap(picked.yaw_deg[0, 0] - truth)), bool(picked.boundary[0, 0]), n_valid


def changed_group(task):
    from run_step1 import GRID, wrap
    import v33_observation as v33

    case, group, xy, h, cir, detected, k0, baseline, nv = task
    inputs, g = case.inputs, case.groups[group]
    freq = inputs.freqs
    c = inputs.hs.C0
    hann = inputs.obs.hann(len(freq))
    indices = np.flatnonzero(np.abs(wrap(GRID - g.yaw_deg)) <= 12. + 1e-10)
    oracle_idx = k0[g.ids]
    spacing = c / (4 * len(freq) * inputs.df)
    oracle_dist = oracle_idx * c / (4 * len(freq) * inputs.df)
    location = np.array([g.x, g.y, case.z]) - case.anchor
    geometric_d = np.linalg.norm(location)
    centers = [np.linalg.norm(np.array([g.x+dx, g.y+dy, case.z]) - case.anchor)
               for dx, dy in xy]
    template_taps = prior_leading_tap(np.r_[geometric_d, centers], inputs)
    reference_tap, prior_taps = template_taps[0], template_taps[1:]
    elevation = -np.degrees(np.arcsin((case.z-case.anchor[2])/geometric_d))
    rows = []
    for seed, (dx, dy) in enumerate(xy):
        detector_valid = detected[seed][g.ids]
        center = centers[seed]
        sigma = v33.projected_sigma(case, group, dx, dy)
        direct_idx = int(prior_taps[seed])
        direct_dist = np.array([direct_idx * spacing])
        direct_s = ratio(cir[seed][g.ids, direct_idx])
        delta_tap = direct_idx - oracle_idx[detector_valid]
        reference_delta = reference_tap - oracle_idx[detector_valid]
        chosen, frac_amps, edge, local_snr = select_distance(
            h[seed][g.ids], detector_valid, center, sigma, freq, hann, c, nv)
        oracle_s = ratio(cir[seed][g.ids, oracle_idx])
        frac_s = ratio(frac_amps)
        e0, _, _, boundary0, n0 = baseline.get(seed, (np.nan, np.nan, False, False, 0))
        e1, boundary1, n1 = fit_changed(case, group, dx, dy, sigma,
                                        np.where(detector_valid, oracle_s, np.nan),
                                        oracle_dist, indices)
        e2, boundary2, n2 = fit_changed(case, group, dx, dy, sigma,
                                        np.where(detector_valid, frac_s, np.nan),
                                        np.array([chosen]), indices)
        e3, boundary3, n3 = fit_changed(case, group, dx, dy, sigma,
                                        np.where(detector_valid, direct_s, np.nan),
                                        direct_dist, indices)
        if n0 == 0:
            n0 = case.n_valid(group, seed)
        rows.append({
            "case": case.name, "group": int(group), "seed": seed, "x_m": g.x, "y_m": g.y,
            "range_reference_m": geometric_d, "elevation_reference_deg": elevation,
            "prior_dx_m": dx, "prior_dy_m": dy, "d_geo_prior_m": center, "sigma_d_prior_m": sigma,
            "fractional_range_m": chosen, "fractional_minus_reference_m": chosen-geometric_d,
            "fractional_window_edge": bool(edge), "fractional_sum_signal_to_noise": local_snr,
            "detected_tap_mismatch_yaws": int(np.count_nonzero(
                (case.taps[seed, g.ids] != oracle_idx) & detector_valid)),
            "detected_tap_late_yaws": int(np.count_nonzero(
                (case.taps[seed, g.ids] > oracle_idx) & detector_valid)),
            "prior_direct_index": direct_idx,
            "geometry_nominal_index": int(reference_tap),
            "prior_direct_minus_nominal_taps": direct_idx - int(reference_tap),
            "prior_direct_oracle_delta_sum_taps": int(delta_tap.sum()),
            "prior_direct_oracle_match_yaws": int((delta_tap == 0).sum()),
            "prior_direct_oracle_early_yaws": int((delta_tap < 0).sum()),
            "prior_direct_oracle_late_yaws": int((delta_tap > 0).sum()),
            "geometry_nominal_oracle_match_yaws": int((reference_delta == 0).sum()),
            "geometry_nominal_oracle_early_yaws": int((reference_delta < 0).sum()),
            "geometry_nominal_oracle_late_yaws": int((reference_delta > 0).sum()),
            "common_valid": bool(np.isfinite([e0,e1,e2,e3]).all()),
            **{f"err_{arm}_deg": value for arm, value in zip(ARMS, (e0,e1,e2,e3))},
            **{f"heading_edge_{arm}": value for arm, value in zip(ARMS, (boundary0,boundary1,boundary2,boundary3))},
            **{f"valid_yaws_{arm}": value for arm, value in zip(ARMS, (n0,n1,n2,n3))},
        })
    return rows


def group_rows(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row)
    return list(groups.values())


def summarize(rows, rng):
    groups = group_rows(rows)
    paired = [row for row in rows if row["common_valid"]]
    paired_groups = group_rows(paired)
    station_means = []
    stratum = {"n_stations": len(groups), "n_sweep_slots": len(rows), "n_paired": len(paired),
               "n_delay_edge": sum(row["fractional_window_edge"] for row in rows),
               "n_detected_oracle_tap_mismatch_yaws": sum(row["detected_tap_mismatch_yaws"] for row in rows),
               "n_detected_oracle_late_yaws": sum(row["detected_tap_late_yaws"] for row in rows), "arms": {}}
    stratum["tap_counts"] = {
        field: sum(row[field] for row in rows)
        for field in rows[0]
        if field.endswith(("_match_yaws", "_early_yaws", "_late_yaws", "_delta_sum_taps"))
    }
    stratum["tap_counts"]["detector_valid_yaws"] = sum(row["valid_yaws_detected"] for row in rows)
    stratum["tap_counts"]["prior_differs_from_nominal_sweeps"] = sum(
        row["prior_direct_minus_nominal_taps"] != 0 for row in rows)
    if not paired:
        return stratum
    pmat = np.array([[r[f"err_{a}_deg"] for a in ARMS] for r in paired])
    sums, counts = [], []
    for g in paired_groups:
        gm = np.array([[r[f"err_{a}_deg"] for a in ARMS] for r in g])
        station_means.append(gm.mean(axis=0))
        sums.append((gm**2).sum(axis=0))
        counts.append(len(g))
    draws = rng.integers(0, len(counts), (2000,len(counts)))
    bs_rmse = np.sqrt(np.asarray(sums)[draws].sum(axis=1) / np.asarray(counts)[draws].sum(axis=1)[:, None])
    for k, arm in enumerate(ARMS):
        vals = pmat[:, k]
        stratum["arms"][arm] = {
            "n_valid": sum(np.isfinite(r[f"err_{arm}_deg"]) for r in rows),
            "n_heading_edge_all": sum(r[f"heading_edge_{arm}"] for r in rows),
            "rmse_deg": np.sqrt(np.mean(vals**2)), "mean_signed_deg": vals.mean(),
            "p95_abs_deg": np.quantile(np.abs(vals), .95), "abs_gt5_fraction": (np.abs(vals)>5).mean(),
            "station_mean_rms_deg": np.sqrt(np.mean(np.asarray(station_means)[:,k]**2)),
        }
    stratum["rmse_delta_deg"] = {}
    for to, fr in ((1,0),(2,0),(2,1),(3,0),(3,1)):
        key = f"{ARMS[to]}_minus_{ARMS[fr]}"
        diff = stratum["arms"][ARMS[to]]["rmse_deg"] - stratum["arms"][ARMS[fr]]["rmse_deg"]
        stratum["rmse_delta_deg"][key] = {"paired_delta": diff,
                                        "percentile95": np.quantile(bs_rmse[:,to]-bs_rmse[:,fr], [.025,.975]).tolist()}
    return stratum


def check_frozen_sweeps(sweeps, original):
    """Check every stored common field and all results of the three controls."""
    def key(row):
        return row["case"], int(row["group"]), int(row["seed"])

    by_key = {key(row): row for row in sweeps}
    max_diff = 0.
    with original.open(newline="", encoding="utf-8") as handle:
        for frozen in csv.DictReader(handle):
            row_key = key(frozen)
            current = by_key.pop(row_key)
            prior_controls_valid = np.isfinite([current[f"err_{arm}_deg"] for arm in ARMS[:3]]).all()
            for field, value in frozen.items():
                actual = prior_controls_valid if field == "common_valid" else current[field]
                if isinstance(actual, (str, bool, int, np.bool_, np.integer)):
                    if str(actual) != value:
                        raise ValueError(f"Frozen field mismatch {row_key}/{field}: {actual} != {value}")
                else:
                    prior = float(value)
                    np.testing.assert_allclose(actual, prior, atol=1e-12, rtol=1e-12,
                                               err_msg=f"{row_key}/{field}")
                    if np.isfinite(prior):
                        max_diff = max(max_diff, abs(actual - prior))
    if by_key:
        raise ValueError("Missing frozen extraction rows")
    return max_diff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("code", "inputs", "banks", "loro", "q1", "spec", "out",
                 "original-summary", "original-sweeps"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    opts = parser.parse_args()
    opts.out.mkdir(exist_ok=False)
    sys.path.insert(0, str(opts.code))
    from v32_observation import ObservationInputs, ObservationCase, SEEDS
    from v33_observation import snap_xy, TRAIN_SEED, SIGMA_XY

    if (sha(opts.original_summary) != ORIGINAL_SUMMARY_SHA or
            sha(opts.original_sweeps) != ORIGINAL_SWEEPS_SHA):
        raise ValueError("Original tap diagnostic receipt differs")
    original = json.loads(opts.original_summary.read_bytes())
    inputs = ObservationInputs(opts.inputs, opts.banks)
    for path, expected_sha in original["source_spec_and_input_sha256"].items():
        if path.startswith("/diag/"):
            continue
        if sha(Path(path)) != expected_sha:
            raise ValueError(f"Frozen source/input mismatch: {path}")
    checks = validate_fourier(inputs)
    checks["leading_edge"] = validate_leading_edge(inputs)
    print(f"LEADING_EDGE_PASS {checks['leading_edge']}", flush=True)
    calibration = {key: item["calibration"] for key,item in json.loads(opts.loro.read_bytes()).items()}
    q1 = read_q1(opts.q1)
    n_frozen = len(q1)
    xy_rng = np.random.Generator(np.random.PCG64(TRAIN_SEED))
    bs_rng = np.random.default_rng(2026111403)
    baseline_cache = {}
    layouts = {}
    case_hashes = {}
    noise_hashes = {}
    parity_max = 0.
    sweeps = []
    with ThreadPoolExecutor(max_workers=opts.workers) as workers:
        for name in CASES:
            case = ObservationCase(inputs, name)
            case_hashes[name] = case.hashes
            if case.hashes != original["case_channel_pose_sha256"][name]:
                raise ValueError(f"Case inputs differ from original: {name}")
            groups = sorted(case.group_ids)
            xy, _, _ = snap_xy(xy_rng.normal(0., SIGMA_XY, (len(groups), SEEDS, 2)))
            layouts[name] = dict(zip(groups, xy))
            tasks = ((case, group, p, calibration[case.route]) for group,p in zip(groups,xy))
            baseline_cache[name] = dict(zip(groups, workers.map(baseline_group, tasks)))
            for group, offsets in layouts[name].items():
                for seed, (dx,dy) in enumerate(offsets):
                    key = (name, group, seed)
                    saved = q1.pop(key, None)
                    new = baseline_cache[name][group].get(seed)
                    if (saved is None) != (new is None):
                        raise ValueError(f"Q1 active sweep mismatch {key}")
                    if new is None:
                        continue
                    err, r, flat, _, _ = new
                    values = np.array([err,r,dx,dy])
                    ref = np.array([float(saved[field]) for field in ("err","r_e1","dx","dy")])
                    np.testing.assert_allclose(values, ref, rtol=1e-12, atol=1e-12, err_msg=str(key))
                    parity_max = max(parity_max, float(np.max(np.abs(values-ref))))
                    if str(flat).lower() != saved["flat"].lower():
                        raise ValueError(f"Q1 flat flag mismatch {key}")
            print(f"BASELINE {name} {len(groups)} stations", flush=True)
        if q1:
            raise ValueError(f"Missing {len(q1)} frozen Q1 rows")
        checks["q1_rows"] = n_frozen
        checks["q1_max_abs"] = parity_max
        print(f"BASELINE_PASS rows={n_frozen} max_abs={parity_max:g}", flush=True)
        nv = inputs.obs.noise_var_from_snr(30)
        for name in CASES:
            case = ObservationCase(inputs, name)
            full = np.load(inputs.block/"FULL_RF"/f"H_{name}.npy", mmap_mode="r", allow_pickle=False)
            los = np.load(inputs.block/f"H_LoS_{name}.npy", mmap_mode="r", allow_pickle=False)
            k0 = inputs.obs.observe(los,inputs.freqs,None,None,tx=0)["index"]
            noisy_h, cir, detected = [], [], []
            digest = hashlib.sha256()
            for seed in range(SEEDS):
                obs = inputs.obs.observe(full,inputs.freqs,nv,np.random.default_rng(seed),tx=0,return_h=True)
                np.testing.assert_array_equal(obs["s"],case.observed[seed])
                np.testing.assert_array_equal(obs["index"],case.taps[seed])
                h = obs["h_noisy"]
                digest.update(memoryview(np.ascontiguousarray(h)).cast("B"))
                current_cir = inputs.obs.cir_batch(h)
                replay = inputs.obs.first_path_batch(current_cir, inputs.df)
                np.testing.assert_array_equal(replay["index"], obs["index"])
                np.testing.assert_array_equal(np.where(obs["detected"],replay["s"],np.nan), obs["s"])
                noisy_h.append(h)
                cir.append(current_cir)
                detected.append(obs["detected"])
            noise_hashes[name] = digest.hexdigest()
            if noise_hashes[name] != original["shared_noisy_full_h_sha256"][name]:
                raise ValueError(f"Noisy full channel differs from original: {name}")
            layout = layouts[name]
            check_group = next(iter(layout))
            first = case.groups[check_group]
            dx,dy = layout[check_group][0]
            predicted_d = np.linalg.norm(np.array([first.x+dx,first.y+dy,case.z])-case.anchor)
            oracle_d = k0[first.ids] * inputs.hs.C0 / (4*len(inputs.freqs)*inputs.df)
            direct_idx = prior_leading_tap(predicted_d, inputs)[0]
            checks[name] = check_predictions(case, check_group, dx, dy, oracle_d, predicted_d, direct_idx)
            tasks = ((case, group, xy, noisy_h, cir, detected, k0, baseline_cache[name][group], nv)
                     for group,xy in layout.items())
            for rows in workers.map(changed_group, tasks):
                sweeps.extend(rows)
            print(f"EXTRACTIONS {name} {len(layout)} stations", flush=True)
    if len(sweeps) != n_frozen or len({(r["case"],r["group"],r["seed"]) for r in sweeps}) != len(sweeps):
        raise ValueError("Incomplete sweep key grid")
    checks["frozen_three_arm_rows"] = len(sweeps)
    checks["frozen_three_arm_max_abs"] = check_frozen_sweeps(sweeps, opts.original_sweeps)
    print(f"FROZEN_ARMS_PASS rows={len(sweeps)} max_abs={checks['frozen_three_arm_max_abs']:g}", flush=True)
    estimates = {}
    station_rows = []
    for name in CASES:
        rows = [row for row in sweeps if row["case"]==name]
        estimates[name] = summarize(rows, bs_rng)
        for group in group_rows(rows):
            first = group[0]
            p = [r for r in group if r["common_valid"]]
            station_rows.append({k:first[k] for k in ("case","group","x_m","y_m","range_reference_m",
                                                       "elevation_reference_deg")} | {"n_paired":len(p)} |
                                {f"mean_{a}_deg":float(np.mean([r[f"err_{a}_deg"] for r in p])) if p else None
                                 for a in ARMS})
        if name == "R2_aA_m0":
            estimates[name]["x_le_6_m"] = summarize([r for r in rows if r["x_m"] <= 6], bs_rng)
            estimates[name]["x_ge_8_m"] = summarize([r for r in rows if r["x_m"] >= 8], bs_rng)
    write_csv(opts.out/"SWEEP_ROWS.csv", sweeps)
    write_csv(opts.out/"STATION_ROWS.csv", station_rows)
    files = [Path(__file__), opts.spec, opts.q1, opts.loro, opts.original_summary, opts.original_sweeps,
             Path(inspect.getfile(inputs.obs)),
             Path(inspect.getfile(sys.modules["k7_k8"])), *(opts.code / f for f in (
                 "v32_observation.py", "v33_observation.py", "v32_filter.py", "run_step1.py")),
             inputs.block/"CASES.json", inputs.block/"freqs_hz.npy"]
    summary = {"question": "G1-MODEL-002 Goal 1 geometry-only leading-edge tap", "status":"DIAGNOSTIC_ONLY",
               "frozen_s2_prime":"STOP", "step_3":"HELD", "base_commit": FIXED_BASE,
               "checks":checks, "cases":estimates, "n_stations":len(station_rows),
               "n_sweep_slots":len(sweeps), "n_paired":sum(r["common_valid"] for r in sweeps),
               "argv":sys.argv, "python":platform.python_version(), "numpy":np.__version__,
               "case_channel_pose_sha256":case_hashes, "shared_noisy_full_h_sha256":noise_hashes,
               "source_spec_and_input_sha256":{str(f):sha(f) for f in files}}
    (opts.out/"SUMMARY.json").write_text(json.dumps(clean(summary), indent=2,allow_nan=False)+"\n",
                                          encoding="utf-8")
    print(f"DONE {len(sweeps)} sweeps", flush=True)


if __name__ == "__main__":
    main()
