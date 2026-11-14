"""One MODEL-003 S2 characterization of the frozen G-T1 channels."""

import argparse
import csv
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares, minimize_scalar
from scipy.stats import kurtosis, t

from run_tb3_g1_pilot import read, sha, write
from run_tb3_model003_s1 import CASES, DRAWS, PA, ROUTES, SNRS, batches, m1r_s, open_case
from run_tb3_production import utc_now, verify
from tb3_model003_futility import evaluate_path, self_check, trailing_distance_mean
from tb3_model003_motion import generate_motion, geometry_from_rows
from tb3_model003_s1_observation import channel_to_cir, range_candidates, signed_s_at_tap
from validate_tb3_g4 import load_model


CURVES = ("C1", "C2", "C3", "C4")
PATHS = ("TEACH_REPEAT", "P-B", *CURVES)
PF_CASES = {"G-T1_A": "G-T1_A_P-F", "G-T1_B": "G-T1_B_P-F"}
KNOTS = np.array([0., 1.5, 3., 6., 10.])
SPATIAL_LAGS_M = np.geomspace(0.04, 5., 18)
YAW_LAGS_DEG = np.arange(2.5, 62.5, 2.5)
RAD = np.pi / 180


def stats(values):
    values = np.asarray(values)
    if not values.size:
        return dict(n=0, mean=None, variance=None, rms=None)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite input to S2 statistics")
    return dict(n=int(values.size), mean=float(values.mean()), variance=float(values.var()),
                rms=float(np.sqrt(np.mean(values**2))))


def observe(h, obs, df, rules, noise=None, rng=None):
    cir = channel_to_cir(h, obs, noise_var=noise, rng=rng)
    threshold = obs.detection_threshold(noise, n_taps=cir.shape[1]) if noise else 0.0
    fields = range_candidates(cir, df, threshold=threshold, rules=rules)
    for values in fields.values():
        values["s"] = signed_s_at_tap(cir, values["tap"], values["detected"])
    return fields


def clean_data(data, obs, df, rules, offsets):
    table = {rule: {key: [] for key in ("e_mp", "e_r", "tap")} for rule in rules}
    for ids in batches(list(range(len(data["d"])))):
        full = observe(data["full"][ids], obs, df, rules)
        los = observe(data["los"][ids], obs, df, rules)
        for rule in rules:
            if not full[rule]["detected"].all() or not los[rule]["detected"].all():
                raise ValueError("Non-detection in noiseless G-T1 characterization")
            table[rule]["e_mp"].extend(full[rule]["s"] - los[rule]["s"])
            table[rule]["e_r"].extend(full[rule]["range_m"] - offsets[rule] - data["d"][ids])
            table[rule]["tap"].extend(full[rule]["index"])
    return {r: {k: np.asarray(v) for k, v in row.items()} for r, row in table.items()}


def thermal(data, obs, df, rules, anchor, seed):
    ids = np.array(sorted({r["pose_id"] for r in data["samples"]
                           if r["set"] in PA and r["selected_5pt"] is True}))
    if not ids.size:
        raise ValueError("No P-A five-point station observations")
    result = {rule: {} for rule in rules}
    for snr in SNRS:
        values = {rule: np.full((DRAWS, len(ids), 2), np.nan) for rule in rules}
        noise = obs.noise_var_from_snr(snr)
        for draw in range(DRAWS):
            rng = np.random.default_rng(np.random.SeedSequence([seed, anchor, draw]))
            for kk in batches(np.arange(len(ids))):
                fields = observe(data["full"][ids[kk]], obs, df, rules, noise, rng)
                for rule, row in fields.items():
                    values[rule][draw, kk, 0] = row["s"]
                    values[rule][draw, kk, 1] = row["range_m"]
        for rule, array in values.items():
            counts = np.count_nonzero(np.isfinite(array[:, :, 0]), axis=0)
            enough = counts >= 2
            variances = np.var(array[:, enough], axis=0, ddof=1, where=np.isfinite(array[:, enough]))
            result[rule][snr] = (np.sum(variances * (counts[enough] - 1)[:, None], axis=0),
                                 int(sum(counts[enough] - 1)), int(sum(counts)), len(ids)*DRAWS)
    return result


def bin_key(rows, allowed):
    return np.array(sorted({r["pose_id"] for r in rows if r["set"] in allowed}), dtype=int)


def lag_pairs(sequences, lags):
    """Sum within-sequence standardized products at prespecified separation bins."""
    edges = np.r_[0., (lags[:-1] + lags[1:])/2, lags[-1] + (lags[-1]-lags[-2])/2]
    pairs = []
    for x, v in sequences:
        order = np.argsort(x, kind="stable")
        x, v = np.asarray(x)[order], np.asarray(v)[order]
        if len(v) < 3 or v.std() == 0:
            continue
        i, j = np.triu_indices(len(v), k=1)
        gap = x[j] - x[i]
        keep = (gap > 0) & (gap < edges[-1])
        k = np.searchsorted(edges, gap[keep], side="right") - 1
        z = (v - v.mean()) / v.std()
        pairs.append((np.bincount(k, weights=z[i[keep]]*z[j[keep]], minlength=len(lags)),
                      np.bincount(k, minlength=len(lags))))
    return pairs


def fit_kernel(pairs, lags):
    if not pairs:
        raise ValueError("No S2 kernel pairs")
    cov, counts = [np.sum(group, axis=0) for group in zip(*pairs, strict=True)]
    good = counts > 0
    observed = cov[good] / counts[good]
    weights = counts[good] / counts[good].sum()
    fit = minimize_scalar(lambda log_l: np.sum(weights*(observed-np.exp(-lags[good]/np.exp(log_l)))**2),
                          bounds=np.log([lags[0]/10, lags[-1]*10]), method="bounded")
    if not fit.success:
        raise ValueError("S2 correlation length fit failed")
    return dict(length=float(np.exp(fit.x)), bin_midpoints=lags.tolist(),
                pair_count=counts.tolist(), rho=[float(v/n) if n else None for v, n in zip(cov, counts)])


def rho(pairs):
    pairs = np.asarray(pairs)
    if len(pairs) < 2 or np.any(pairs.std(axis=0) == 0):
        return dict(n=len(pairs), rho=None)
    return dict(n=len(pairs), rho=float(np.corrcoef(pairs.T)[0, 1]))


def grouped(rows, key):
    records = {}
    for row in rows:
        records.setdefault(key(row), []).append(row)
    return records


def spatial_inputs(samples, e):
    spatial = grouped([r for r in samples if r["set"] in ("P-A_PRIME", *CURVES)],
                      lambda r: r["set"])
    sweeps = grouped([r for r in samples if r["set"] in PA and r["protocol"] == "dense49"],
                     lambda r: (r["set"], r["station_id"]))
    def arrays(groups, axis):
        return [(np.array([r[axis] for r in rows]), np.array([e[r["pose_id"]] for r in rows]))
                for rows in groups.values()]
    return lag_pairs(arrays(spatial, "along"), SPATIAL_LAGS_M), lag_pairs(arrays(sweeps, "planned_rel_deg"),
                                                                        YAW_LAGS_DEG)


def revisit_inputs(samples, e):
    offset = grouped([r for r in samples if r["set"] == "P-D"], lambda r: r["offset_m"])
    pairs = {f"{d:.3f}": [(e[r["source_pose_id"]], e[r["pose_id"]]) for r in rows]
             for d, rows in offset.items()}
    phase = {name: {(r["station_id"], r["planned_rel_deg"]): e[r["pose_id"]] for r in samples
                    if r["set"] == name and r["selected_5pt"] is True} for name in PA}
    teach, repeat = phase["P-A_TEACH"], phase["P-A_REPEAT"]
    pairs["TEACH_REPEAT"] = [(teach[k], repeat[k]) for k in sorted(teach.keys() & repeat.keys())]
    verified_repeat = [r for r in samples if r["set"] == "P-E"]
    pairs["P-E"] = [(e[r["source_pose_id"]], e[r["pose_id"]]) for r in verified_repeat]
    return pairs


def fixed_checkpoints(rows, path, spacing):
    cum = np.cumsum([float(row["distance_increment_m"]) for row in rows])
    if path != "TEACH_REPEAT":
        at = np.arange(spacing, cum[-1] + 1e-10, spacing)
        return np.unique(np.minimum(np.searchsorted(cum, at), len(rows)-1))
    sweep_ends, straight_groups = {}, {}
    for i, row in enumerate(rows):
        key = row["phase"], row["station_id"]
        if row["motion"] in ("sweep", "hold") and row["station_id"]:
            sweep_ends[key] = i
        if row["motion"] == "straight":
            straight_groups.setdefault(key, []).append(i)
    halves = []
    for group in straight_groups.values():
        lower = max(0, group[0]-1)
        target = (cum[group[-1]] + cum[lower])/2
        halves.append(min(group, key=lambda i: abs(cum[i]-target)))
    return np.array(sorted(set(sweep_ends.values()) | set(halves)), dtype=int)


def timeline_data(path):
    streams = {case: {path: [] for path in PATHS} for case in CASES}
    with path.open(newline="", encoding="utf-8") as inp:
        for row in csv.DictReader(inp):
            stream = "TEACH_REPEAT" if row["stream"] in ("TEACH", "REPEAT") else row["stream"]
            if row["case"] in streams and stream in PATHS:
                streams[row["case"]][stream].append(row)
    if any(not rows for paths in streams.values() for rows in paths.values()):
        raise ValueError("Missing G-T1 frozen timeline path")
    return streams


def s_gradient(model, obs, banks, data, x, y, yaw, rule, step_rad):
    delta = np.array([x, y, data["rx_z"]]) - data["anchor"]
    distance = np.linalg.norm(delta)
    direction = delta / distance
    dy = step_rad / RAD
    plus = m1r_s(model, obs, banks, direction, yaw+dy, distance, 0., rule)[0]
    minus = m1r_s(model, obs, banks, direction, yaw-dy, distance, 0., rule)[0]
    return (plus-minus) / (2*step_rad)


def channel_features(data, residual, thermal_result, pf_diagnostic=None):
    e, er, tap = (residual[key] for key in ("e_mp", "e_r", "tap"))
    samples = data["samples"]
    model_ids = bin_key(samples, PA | {"P-A_PRIME", *CURVES})
    eval_ids = bin_key(samples, ROUTES | {"P-D", "P-E", "P-F"})
    kernels = {
        "s": spatial_inputs(samples, e),
        "range": spatial_inputs(samples, er),
    }
    steps = {int(index): er[eval_ids[tap[eval_ids] == index]] for index in np.unique(tap[eval_ids])}
    tail = e[eval_ids]
    distance, range_distance_e = data["d"][eval_ids], er[eval_ids]
    if pf_diagnostic is not None:
        pf_data, pf_residual = pf_diagnostic
        tail = np.r_[tail, pf_residual["e_mp"]]
        distance = np.r_[distance, pf_data["d"]]
        range_distance_e = np.r_[range_distance_e, pf_residual["e_r"]]
        for index in np.unique(pf_residual["tap"]):
            selected = pf_residual["e_r"][pf_residual["tap"] == index]
            steps[int(index)] = np.r_[steps.get(int(index), np.array([])), selected]
    return dict(thermal=thermal_result, rho=data["d"][model_ids], e=e[model_ids],
                range_e=er[model_ids], tail=tail, kernels=kernels,
                diagnostic_distance=distance, diagnostic_range_e=range_distance_e,
                revisit=revisit_inputs(samples, e), tap_steps=steps)


def radial_fit(rho_m, values):
    """Fit nonnegative linear interpolants to empirical variance by distance."""
    weights = np.stack([np.interp(rho_m, KNOTS, unit) for unit in np.eye(len(KNOTS))], axis=1)
    distance_bin = np.floor(rho_m / .5).astype(int)
    groups = [distance_bin == k for k in np.unique(distance_bin)]
    x, target, count = zip(*((weights[good].mean(axis=0), values[good].var(), int(good.sum()))
                             for good in groups if good.sum() >= 2), strict=True)
    fit = least_squares(lambda sig: np.sqrt(count)*((np.array(x) @ sig)**2 - target),
                        np.full(len(KNOTS), values.std() + 1e-10), bounds=(0, np.inf))
    if not fit.success:
        raise ValueError("S2 distance fit failed")
    return dict(sigma=fit.x.tolist(), observed_distance_m=[float(rho_m.min()), float(rho_m.max())],
                supported_knots=(np.array(x).max(axis=0) > 0).tolist(), bins=len(target))


def feature_fit(features):
    d = np.concatenate([a["rho"] for a in features])
    e = np.concatenate([a["e"] for a in features])
    er = np.concatenate([a["range_e"] for a in features])
    sigma_e, sigma_r = radial_fit(d, e), radial_fit(d, er)
    c1 = {}
    for snr in SNRS:
        ss, count, detections, attempts = (sum(items) for items in
                                          zip(*(a["thermal"][snr] for a in features), strict=True))
        c1[snr] = dict(sigma_s=float(np.sqrt(ss[0]/count)), sigma_r_m=float(np.sqrt(ss[1]/count)),
                       detections=detections, attempts=attempts, degrees_of_freedom=count)
    c2 = dict(knots_m=KNOTS.tolist(), sigma_b=sigma_e["sigma"], sigma_r_m=sigma_r["sigma"],
              s_distance_support=sigma_e, range_distance_support=sigma_r)
    c3 = {}
    for channel in ("s", "range"):
        c3[channel] = dict(distance_m=fit_kernel([p for a in features for p in a["kernels"][channel][0]],
                                                SPATIAL_LAGS_M),
                           yaw_deg=fit_kernel([p for a in features for p in a["kernels"][channel][1]],
                                              YAW_LAGS_DEG))
    c4 = {key: rho([pair for a in features for pair in a["revisit"].get(key, [])])
          for key in sorted({k for a in features for k in a["revisit"]})}
    c6 = {key: stats(np.concatenate([a["tap_steps"].get(key, np.array([])) for a in features]))
          for key in sorted({k for a in features for k in a["tap_steps"]})}
    c6["distance"] = []
    diagnostic_d = np.concatenate([a["diagnostic_distance"] for a in features])
    diagnostic_e = np.concatenate([a["diagnostic_range_e"] for a in features])
    edges = [*KNOTS, np.inf]
    for left, right in zip(edges, edges[1:]):
        rows = diagnostic_e[(diagnostic_d >= left) & (diagnostic_d < right)]
        c6["distance"].append(dict(low_m=left, high_m=right if np.isfinite(right) else None,
                                   residual=stats(rows)))
    tail = np.concatenate([a["tail"] for a in features])
    standardized = (tail-tail.mean()) / tail.std()
    nu, loc, scale = t.fit(standardized, floc=0)
    c7 = dict(n=len(tail), excess_kurtosis=float(kurtosis(standardized, fisher=True, bias=False)),
              student_t_df=float(nu), location=float(loc), scale=float(scale))
    return dict(C1=c1, C2=c2, C3=c3, C4=c4, C6=c6, C7=c7)


def sensitivity_summary(s):
    if not len(s):
        return dict(n=0, quantiles_abs_s_per_rad=None)
    return dict(n=len(s), quantiles_abs_s_per_rad=np.quantile(np.abs(s), [0., .1, .5, .9, 1.]).tolist())


def matched_intervals(eligible, settings, g_min):
    rng = np.random.default_rng(settings["seed"])
    reps = settings["replicates"]
    levels = tuple(next(iter(eligible.values()))["dr_errors_rad"])
    totals = {name: np.zeros(reps) for name in ("floor", *levels)}
    counts = np.zeros(reps)
    seed_count = next(iter(next(iter(eligible.values()))["dr_errors_rad"].values())).shape[1]
    seed_draw = rng.integers(0, seed_count, size=(reps, seed_count))
    for rows in eligible.values():
        good = rows["window_complete"] & (np.abs(rows["sensitivity_s_per_rad"]) >= g_min)
        sites = grouped(np.flatnonzero(good), lambda k: rows["site_ids"][k])
        if not sites:
            continue
        members = list(sites.values())
        sample = rng.integers(0, len(members), size=(reps, len(members)))
        h_sq = (rows["mean_e_mp"][good]/rows["sensitivity_s_per_rad"][good])**2
        point_sq = dict(zip(np.flatnonzero(good), h_sq, strict=True))
        totals["floor"] += np.array([sum(point_sq[i] for i in ids) for ids in members])[sample].sum(axis=1)
        counts += np.array([len(ids) for ids in members])[sample].sum(axis=1)
        for level in levels:
            e_sq = np.mean(rows["dr_errors_rad"][level]**2, axis=2)
            by_site_and_seed = np.array([e_sq[ids].sum(axis=0) for ids in members])
            sum_over_sites = by_site_and_seed[sample].sum(axis=1)
            totals[level] += np.take_along_axis(sum_over_sites, seed_draw, axis=1).mean(axis=1)
    tail = (1 - settings["ci_level"]) / 2
    return {key: np.quantile(np.sqrt(sums/counts), [tail, 1-tail]).tolist() if counts[0] else None
            for key, sums in totals.items()}


def timeline_analysis(cases, residuals, fits, timeline, rule, model, obs, banks, settings, bootstrap):
    all_futility, c5, c8 = {}, {}, {}
    step = settings["derivative_step_rad"]
    g_min = settings["g_min_s_per_rad"]
    spacing = max(1., 2*fits["ABC"]["C3"]["s"]["distance_m"]["length"])
    for path in PATHS:
        eligible, long, sensitivities = {}, {}, {}
        for case, data in cases.items():
            rows = timeline[case][path]
            packet_ids = np.array([int(row["rf_pose_id"]) for row in rows])
            e = residuals[case][rule]["e_mp"][packet_ids]
            cp = fixed_checkpoints(rows, path, spacing)
            x = np.array([float(row["distance_increment_m"]) for row in rows])
            means, mask = trailing_distance_mean(np.cumsum(x), e, cp)
            g = np.array([s_gradient(model, obs, banks, data, float(rows[i]["truth_x_m"]),
                                     float(rows[i]["truth_y_m"]), float(rows[i]["truth_yaw_deg"]), rule, step)
                          for i in cp])
            motion = generate_motion(**geometry_from_rows(rows), path_id=path)
            dr = {level: np.asarray(rows_errors)[cp] for level, rows_errors in motion["heading_error_rad"].items()}
            sites = ([("midpoint" if rows[i]["motion"] == "straight" else "station", rows[i]["station_id"])
                      for i in cp] if path == "TEACH_REPEAT" else cp.tolist())
            eligible[case] = dict(checkpoint_ids=[int(rows[i]["sequence"]) for i in cp],
                                  mean_e_mp=means, window_complete=mask, sensitivity_s_per_rad=g, dr_errors_rad=dr,
                                  site_ids=sites)
            window, point = stats(means[mask]), stats(e[cp[mask]])
            ratio = window["variance"]/point["variance"] if point["variance"] else None
            long[case] = dict(window=window, same_checkpoint_point=point, V_long=ratio,
                              windows_insufficient=int((~mask).sum()))
            sensitivities[case] = {
                label: sensitivity_summary(g[np.array([rows[i]["motion"] in modes for i in cp], dtype=bool)])
                for label, modes in {"straight": ("straight",), "sweeps": ("hold", "sweep", "in_place")}.items()
            }
        result = evaluate_path(eligible, g_min)
        result["equivalent_bias_deg_per_s"] = motion["equivalent_bias_deg_per_s"]
        result["non_gating_bootstrap_rms_ci_rad"] = matched_intervals(eligible, bootstrap, g_min)
        result["checkpoint_spacing_m"] = spacing if path != "TEACH_REPEAT" else None
        c5[path], c8[path] = long, sensitivities
        if path == "P-B":
            result["scope"] = "STRAIGHT_CONTROL"
        all_futility[path] = result
    return all_futility, c5, c8


def run_s2(args):
    plan = read(args.plan)
    settings = plan["futility"]
    settings_source = read(args.s1_dir / "PARITY.json")
    selection = read(args.s1_dir / "RANGING_RULE_SELECTION.json")
    origin = read(args.s1_dir / "DELAY_ORIGIN.json")
    if any(item["status"] != "PASS" for item in (settings_source, selection, origin)):
        raise ValueError("S2 requires all three S1 receipts to pass")
    selected = selection["selected"]
    if settings_source["selected_rule"] != selected:
        raise ValueError("Frozen OR is inconsistent between S1 receipts")
    verify(args.timeline, plan["timeline_sha256"])
    verify(args.plan, args.plan_sha256)
    if not args.plan_commit or len(args.plan_commit) != 40:
        raise ValueError("S2 requires the verified plan commit")
    runtime_fixtures = self_check()
    verify(args.synthetic_receipt, plan["futility_synthetic_sha256"])
    if read(args.synthetic_receipt) != runtime_fixtures or runtime_fixtures["status"] != "PASS":
        raise ValueError("S2-F synthetic receipts disagree")
    started = utc_now()
    args.out.mkdir(mode=0o700, exist_ok=False, parents=True)
    model, obs, banks, freq, source_hashes, bank_hashes = load_model(args)
    df = float(freq[1]-freq[0])
    timeline = timeline_data(args.timeline)
    index_path = args.results_root / "CASES.json"
    indexed_sha = read(args.results_root / "GENERATION_RESULT.json")["cases_sha256"]
    verify(index_path, indexed_sha)
    verify(index_path, settings_source["production_cases_sha256"])
    index = read(index_path)
    cases = {case: open_case(args.results_root, index[case], case) for case in CASES}
    pf_cases = {case: open_case(args.results_root, index[name], name) for case, name in PF_CASES.items()}
    offsets = {r: values["mean_m"] for r, values in settings_source["offsets"].items()}
    rules = tuple(dict.fromkeys((selected, "O30")))
    features = {rule: {} for rule in rules}
    residuals = {}
    for anchor, (case, data) in enumerate(cases.items()):
        residuals[case] = clean_data(data, obs, df, rules, offsets)
        pf = clean_data(pf_cases[case], obs, df, rules, offsets) if case in pf_cases else {}
        noise = thermal(data, obs, df, rules, anchor, plan["rf_thermal_seed"])
        for rule in rules:
            diagnostic = (pf_cases[case], pf[rule]) if rule in pf else None
            features[rule][case[-1]] = channel_features(data, residuals[case][rule], noise[rule], diagnostic)
        print(f"S2 computed G-T1 features for {case}", flush=True)

    records, limits, calculated = {}, {}, {}
    for label, rule in (("OR", selected), ("O30", "O30")):
        if rule not in calculated:
            fitted = {"".join(anchors): feature_fit([features[rule][a] for a in anchors])
                      for n in (1, 2, 3) for anchors in combinations("ABC", n)}
            futility, c5, c8 = timeline_analysis(cases, residuals, fitted, timeline, rule, model, obs, banks,
                                                settings, plan["bootstrap"])
            calculated[rule] = (fitted, futility, c5, c8)
        fitted, futility, c5, c8 = calculated[rule]
        records[label] = dict(rule=rule, anchor_fits=fitted, C5_by_path=c5, C8_by_path=c8)
        limits[label] = dict(rule=rule, paths=futility)
    metadata = dict(status="PASS", question_id="G1-MODEL-003", plan_commit=args.plan_commit,
                    plan_sha256=args.plan_sha256, started_utc=started, finished_utc=utc_now(),
                    s1_receipts_sha256={file: sha(args.s1_dir / file) for file in
                                        ("DELAY_ORIGIN.json", "RANGING_RULE_SELECTION.json", "PARITY.json")},
                    timeline_sha256=sha(args.timeline), production_cases_sha256=indexed_sha,
                    source_sha256=source_hashes, banks_sha256=bank_hashes,
                    input_sha256={**{case: data["input_sha256"] for case, data in cases.items()},
                                  **{PF_CASES[c]: data["input_sha256"] for c, data in pf_cases.items()}})
    write(args.out / "CHARACTERIZATION_003.json", metadata | dict(chains=records))
    write(args.out / "FUTILITY.json", metadata | dict(chains=limits, governing_chain="OR",
                                                    synthetic=runtime_fixtures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results-root", "s1-dir", "model-source", "banks-dir", "plan", "synthetic-receipt", "timeline", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--plan-commit", required=True)
    parser.add_argument("--plan-sha256", required=True)
    run_s2(parser.parse_args())


if __name__ == "__main__":
    main()
