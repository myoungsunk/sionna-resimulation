"""Run G1-MODEL-003 v3 S2′, S2-T and S2-F on frozen G-T1 A/B/C."""

import argparse
from itertools import combinations
from pathlib import Path
import re

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_model003_s1 import CASES, DRAWS, PA, ROUTES, SNRS, open_case
from run_tb3_model003_s2 import (
    CURVES, PATHS, SPATIAL_LAGS_M, YAW_LAGS_DEG, clean_data, fixed_checkpoints,
    grouped, lag_pairs, matched_intervals, revisit_inputs, rho, s_gradient, sensitivity_summary,
    stats, thermal, timeline_data,
)
from run_tb3_production import utc_now, verify
from tb3_model003_futility import evaluate_path, self_check as futility_check, trailing_distance_mean
from tb3_model003_motion import generate_motion, geometry_from_rows
from tb3_model003_v3_characterization import (
    _merge_bins, fit_c2, fit_c3, fit_c7, select_c2_penalty, synthetic_check,
)
from validate_tb3_g4 import load_model

QUESTION = "G1-MODEL-003"
MODEL_SETS = PA | {"P-A_PRIME", *CURVES}
C6_DIAGNOSTIC_SETS = ROUTES | {"P-D", "P-E", "P-F"}
ANCHORED_GROUPS = ["".join(group) for n in (1, 2, 3) for group in combinations("ABC", n)]


def distinct_poses(samples):
    """Frozen pose ID already encodes the position and wrapped yaw equivalence."""
    by_pose = {}
    # Use the original station if a pose also occurs in a spatial route.
    for row in sorted(samples, key=lambda row: (row["set"] not in PA, row["pose_id"])):
        by_pose.setdefault(row["pose_id"], row)
    return list(by_pose.values())


def sample_sites(rows, spacing):
    return [
        ("TEACH_REPEAT", row["station_id"]) if row["set"] in PA
        else (row["set"], max(0, int(np.ceil(float(row["along"])/spacing)-1)))
        for row in rows
    ]


def kernel_inputs(samples):
    spatial = grouped([r for r in samples if r["set"] in {"P-A_PRIME", *CURVES}], lambda r: r["set"])
    sweep = grouped([r for r in samples if r["set"] in PA and r["protocol"] == "dense49"],
                    lambda r: (r["set"], r["station_id"]))
    lengths = {name: float(np.ptp([r["along"] for r in rows])) for name, rows in spatial.items()}
    return spatial, sweep, lengths


def kernel_pairs(groups, residual, axis, lags):
    """Use frozen v2 within-sequence pairs after removing repeated pose IDs."""
    seen = set()
    sequences = []
    for rows in groups.values():
        keep = []
        for row in rows:
            if row["pose_id"] not in seen:
                keep.append(row)
                seen.add(row["pose_id"])
        sequences.append((np.asarray([r[axis] for r in keep]), residual[[r["pose_id"] for r in keep]]))
    return lag_pairs(sequences, lags)


def bounded_kernel(totals, lags, lower, upper):
    pairs = [p for batch in totals for p in batch]
    if not pairs:
        raise ValueError("No supported C3 lag pairs")
    cross, counts = [np.sum(part, axis=0) for part in zip(*pairs, strict=True)]
    valid = counts > 0
    y = cross[valid] / counts[valid]
    fit = fit_c3(lags[valid], y, counts[valid], lower=lower, upper=upper)
    return fit | dict(bin_midpoints=lags.tolist(), bin_pair_count=counts.astype(int).tolist(),
                      rho=[float(c/n) if n else None for c, n in zip(cross, counts, strict=True)])


def anchor_features(data, residual, thermal_result, kernels):
    source = data["samples"]
    model = distinct_poses([row for row in source if row["set"] in MODEL_SETS])
    diag = distinct_poses([row for row in source if row["set"] in C6_DIAGNOSTIC_SETS])
    model_ids = [r["pose_id"] for r in model]
    report_ids = [r["pose_id"] for r in diag]
    e_s, e_r, tap = (residual[key] for key in ("e_mp", "e_r", "tap"))
    spatial, sweep, lengths = kernels
    correlations = {
        channel: (kernel_pairs(spatial, e, "along", SPATIAL_LAGS_M),
                  kernel_pairs(sweep, e, "planned_rel_deg", YAW_LAGS_DEG))
        for channel, e in (("s", e_s), ("range", e_r))
    }
    return dict(rows=model, distance_m=data["d"][model_ids], s=e_s[model_ids], range=e_r[model_ids],
                thermal=thermal_result, prepared_pairs=correlations, path_lengths_m=lengths,
                revisit=revisit_inputs(source, e_s),
                tap_report={int(i): e_r[report_ids][tap[report_ids] == i]
                            for i in np.unique(tap[report_ids])})


def c1_summary(features):
    out = {}
    for snr in SNRS:
        ss, count, detected, attempted = (sum(items) for items in
                                         zip(*(row["thermal"][snr] for row in features), strict=True))
        if count <= 0:
            raise ValueError("C1 has no detected degrees of freedom")
        out[str(snr)] = dict(sigma_s=float(np.sqrt(ss[0]/count)), sigma_r_m=float(np.sqrt(ss[1]/count)),
                             detections=detected, attempts=attempted, degrees_of_freedom=count)
    return out


def c3_summary(features):
    lengths = {f"{anchor}/{path}": length for anchor, rows in features.items()
               for path, length in rows["path_lengths_m"].items()}
    bound = min(lengths.values()) / 3
    out = {}
    for channel in ("s", "range"):
        pairs = [row["prepared_pairs"][channel] for row in features.values()]
        out[channel] = dict(
            distance_m=bounded_kernel([p[0] for p in pairs], SPATIAL_LAGS_M, .016, bound),
            yaw_deg=bounded_kernel([p[1] for p in pairs], YAW_LAGS_DEG, 2.5, 60.),
            spatial_training_path_lengths_m=lengths,
        )
    return out


def fitted_range_mean(fit, corrected_range):
    return np.interp(corrected_range, fit["knots_m"], fit["bias_m"])


def range_mean(features, spacing, options):
    names = np.concatenate([np.repeat(a, len(row["distance_m"])) for a, row in features.items()])
    true_range = np.concatenate([row["distance_m"] for row in features.values()])
    residual = np.concatenate([row["range"] for row in features.values()])
    measured = true_range + residual
    site = np.fromiter(((a, key) for a, row in features.items()
                        for key in sample_sites(row["rows"], spacing)), dtype=object)
    groups = _merge_bins(measured, site, options["knots_m"], options["min_samples"], options["min_sites"])
    limits = [float((measured[left].max() + measured[right].min())/2)
              for left, right in zip(groups, groups[1:])]
    fit = dict(knots_m=[float(np.median(measured[idx])) for idx in groups],
               bias_m=[float(np.mean(residual[idx])) for idx in groups],
               bin_edges_m=limits, support_m=[float(measured.min()), float(measured.max())])
    remaining = residual - fitted_range_mean(fit, measured)
    centered = remaining.copy()
    bins, consider_bins = [], []
    for bin_id, idx in enumerate(groups):
        by_anchor = {}
        for anchor in features:
            members = idx[names[idx] == anchor]
            if len(members):
                mean = float(remaining[members].mean())
                centered[members] -= mean
                by_anchor[anchor] = dict(n=len(members), mean_m=mean)
        means = [record["mean_m"] for record in by_anchor.values()]
        variance = float(np.var(means, ddof=1)) if len(means) == len(features) and len(means) > 1 else None
        bins.append(dict(bin=bin_id, n=len(idx), sites=len(set(site[idx])),
                         low_observed_m=float(measured[idx].min()), high_observed_m=float(measured[idx].max())))
        consider_bins.append(dict(bin=bin_id, remaining_by_anchor=by_anchor, variance_m2=variance))
    supported = [item["variance_m2"] for item in consider_bins if item["variance_m2"] is not None]
    if len(features) > 1 and not supported:
        raise ValueError("C6-K needs a shared range bin across training anchors")
    diag = {str(key): stats(np.concatenate([row["tap_report"].get(key, []) for row in features.values()]))
            for key in sorted({k for row in features.values() for k in row["tap_report"]})}
    split = np.cumsum([len(row["range"]) for row in features.values()])[:-1]
    return (fit | dict(bins=bins, tap_diagnostic=diag, binning_axis="reported range minus LoS offset"),
            dict(variance_m2=float(np.mean(supported)) if supported else None,
                 shared_bins=len(supported), bins=consider_bins),
            dict(zip(features, np.split(centered, split), strict=True)))


def fit_variances(features, thermal_by_anchor, pooled_c1, spacing, conditional, options):
    results = {}
    for snr in SNRS:
        snr_key = str(snr)
        results[snr_key] = {}
        for channel in ("s", "range", "range_conditional"):
            base = "s" if channel == "s" else "range"
            thermal_key = "sigma_s" if base == "s" else "sigma_r_m"
            training = {
                a: dict(distance_m=row["distance_m"], residual=row[base],
                        site=sample_sites(row["rows"], spacing[base]),
                        thermal_std=thermal_by_anchor[a][snr_key][thermal_key])
                for a, row in features.items()
            }
            params = {k: options[k] for k in ("knots_m", "min_samples", "min_sites")}
            if channel == "range_conditional":
                # C6 demeaning uses only these outer donors. Reuse the independently
                # selected offset-only range penalty; do not tune against held-out data.
                cv = results[snr_key]["range"]["lambda_selection"]
                residual = np.concatenate([conditional[a] for a in training])
            else:
                cv = (select_c2_penalty(training, **params, penalties=options["penalties"]) if len(training) > 1
                      else dict(selected_penalty=min(options["penalties"]), status="SINGLE_DONOR_DIAGNOSTIC"))
                residual = np.concatenate([r["residual"] for r in training.values()])
            fit = fit_c2(
                np.concatenate([r["distance_m"] for r in training.values()]), residual,
                ((a, key) for a, row in training.items() for key in row["site"]),
                **params, thermal_std=pooled_c1[snr_key][thermal_key], penalty=cv["selected_penalty"])
            results[snr_key][channel] = fit | dict(lambda_selection=cv)
        results[snr_key]["range_conditional"]["residual"] = "C6-adjusted, centered within donor and range bin"
    return results


def fit_group(features, thermal_by_anchor, options):
    c1, c3 = c1_summary(features.values()), c3_summary(features)
    spacing = {c: max(1., 2*c3[c]["distance_m"]["length"]) for c in ("s", "range")}
    c6, c6k, conditional = range_mean(features, spacing["range"], options)
    by_snr = fit_variances(features, thermal_by_anchor, c1, spacing, conditional, options)
    c2 = by_snr["30"]
    c4 = {key: rho([pair for row in features.values() for pair in row["revisit"].get(key, [])])
          for key in sorted({k for row in features.values() for k in row["revisit"]})}
    c7 = fit_c7(
        np.concatenate([row["distance_m"] for row in features.values()]),
        np.concatenate([row["s"] for row in features.values()]),
        ((a, key) for a, row in features.items() for key in sample_sites(row["rows"], spacing["s"])), c2["s"],
    )
    return dict(C1=c1, C2=c2, C2_by_snr=by_snr, C2_w=dict(
        s_variance=c2["s"]["white_variance"], range_variance_m2=c2["range"]["white_variance"]),
        C3=c3, C4=c4, C6=c6, C6_K=c6k, C7=c7, site_spacing_m=spacing)



def window_analysis(cases, residuals, fits, timeline, rule, model, obs, banks, settings, bootstrap, seeds):
    paths, c5, c8, windows = {}, {}, {}, {}
    step = settings["derivative_step_rad"]
    g_min = settings["g_min_s_per_rad"]
    spacing = fits["ABC"]["site_spacing_m"]["s"]
    for path in PATHS:
        comparison, moments, sensitivities, windows[path] = {}, {}, {}, {}
        for case, data in cases.items():
            rows = timeline[case][path]
            packet_ids = np.array([int(row["rf_pose_id"]) for row in rows])
            errors = residuals[case][rule]["e_mp"][packet_ids]
            cp = fixed_checkpoints(rows, path, spacing)
            geometry = geometry_from_rows(rows)
            distance = np.cumsum(geometry["distance_increment_m"])
            means, complete = trailing_distance_mean(distance, errors, cp)
            gradient = np.array([
                s_gradient(model, obs, banks, data, float(rows[i]["truth_x_m"]), float(rows[i]["truth_y_m"]),
                           float(rows[i]["truth_yaw_deg"]), rule, step) for i in cp
            ])
            motion = generate_motion(**geometry, path_id=path, seeds=seeds)
            dr_errors = {k: np.asarray(v)[cp] for k, v in motion["heading_error_rad"].items()}
            site_ids = ([("midpoint" if rows[i]["motion"] == "straight" else "station", rows[i]["station_id"])
                         for i in cp] if path == "TEACH_REPEAT" else list(range(len(cp))))
            checkpoint_ids = [int(rows[i]["sequence"]) for i in cp]
            comparison[case] = dict(checkpoint_ids=checkpoint_ids, mean_e_mp=means, window_complete=complete,
                                    sensitivity_s_per_rad=gradient, dr_errors_rad=dr_errors, site_ids=site_ids)
            windows[path][case] = {
                "window_rows": [(checkpoint_ids[i], float(means[i])) for i in np.flatnonzero(complete)],
                "range_pose_ids": np.unique(packet_ids),
            }
            window, point = stats(means[complete]), stats(errors[cp[complete]])
            moments[case] = dict(window=window, same_checkpoint_point=point,
                                 V_long=window["variance"]/point["variance"] if point["variance"] else None,
                                 windows_insufficient=int((~complete).sum()))
            sensitivities[case] = {
                label: sensitivity_summary(gradient[np.array([rows[i]["motion"] in modes for i in cp], dtype=bool)])
                for label, modes in {"straight": ("straight",), "sweeps": ("hold", "sweep", "in_place")}.items()
            }
        path_result = evaluate_path(comparison, g_min)
        path_result["equivalent_bias_deg_per_s"] = motion["equivalent_bias_deg_per_s"]
        path_result["non_gating_bootstrap_rms_ci_rad"] = matched_intervals(comparison, bootstrap, g_min)
        path_result["checkpoint_spacing_m"] = None if path == "TEACH_REPEAT" else spacing
        if path == "P-B":
            path_result["scope"] = "STRAIGHT_CONTROL"
        paths[path], c5[path], c8[path] = path_result, moments, sensitivities
    return paths, c5, c8, windows


def path_s_variance(c5_path, anchors):
    # This is the existing v2 pooled population variance of the 5 m window means.
    windows = [row["window"] for case, row in c5_path.items() if case[-1] in anchors and row["window"]["n"]]
    n = sum(w["n"] for w in windows)
    if not n:
        return None
    mean = sum(w["n"] * w["mean"] for w in windows) / n
    return sum(w["n"] * (w["variance"] + (w["mean"] - mean)**2) for w in windows) / n


def transfer_component(rows, variance, key):
    denominator = float(np.sqrt(variance)) if variance is not None else None
    has_denominator = denominator is not None and denominator > 0
    labeled = [row | {"z": row[key]/denominator if row[key] is not None and has_denominator else None}
               for row in rows]
    valid = [row for row in labeled if row["z"] is not None]
    mean = float(np.mean([row["z"] for row in valid])) if valid else None
    worst = max(valid, key=lambda row: abs(row["z"])) if valid else None
    return dict(variance=variance, denominator=denominator, n_defined=len(valid), mean_z=mean, worst=worst,
                predicted_fail=any(abs(row["z"]) > 2. for row in valid),
                status="DEFINED" if valid else "UNDEFINED", rows=labeled)


def transfer_precheck(cases, residuals, fits, windows, c5, rule):
    folds = {}
    for case, data in cases.items():
        donors = "".join(a for a in "ABC" if a != case[-1])
        fit = fits[donors]
        c6 = fit["C6"]
        for path in PATHS:
            rows = windows[path][case]
            s_variance = path_s_variance(c5[path], donors)
            s_comp = transfer_component(
                [dict(checkpoint_id=idx, window_mean_s=e) for idx, e in rows["window_rows"]],
                s_variance, "window_mean_s")
            pose_ids = rows["range_pose_ids"]
            range_e = residuals[case][rule]["e_r"][pose_ids]
            distance = data["d"][pose_ids] + range_e
            corrected = range_e - fitted_range_mean(c6, distance)
            bin_ids = np.searchsorted(c6["bin_edges_m"], distance, side="right")
            out_of_support = (distance < c6["support_m"][0]) | (distance > c6["support_m"][1])
            bins = []
            for bin_id in range(len(c6["knots_m"])):
                assigned = bin_ids == bin_id
                take = assigned & ~out_of_support
                bins.append(dict(bin=bin_id, n=int(take.sum()),
                                 outside_training_support=int((assigned & out_of_support).sum()),
                                 bin_mean_m=float(corrected[take].mean()) if take.any() else None))
            r_comp = transfer_component(bins, fit["C6_K"]["variance_m2"], "bin_mean_m")
            folds[f"{case}/{path}"] = dict(held_out=case, training_anchors=list(donors), path=path,
                                          Z_s=s_comp, Z_r=r_comp,
                                          predicted_fail=s_comp["predicted_fail"] or r_comp["predicted_fail"])
    return folds


def verified_inputs(args):
    verify(args.plan, args.plan_sha256)
    verify(args.s0_report, args.s0_sha256)
    plan, s0 = read(args.plan), read(args.s0_report)
    if not re.fullmatch(r"[0-9a-f]{40}", args.plan_commit):
        raise ValueError("S2′ requires a verified Git plan commit")
    if any(item.get("question_id") != QUESTION or item.get("version") != 3 for item in (plan, s0)):
        raise ValueError("S2′ requires v3 plan and v3 S0")
    if s0["status"] != "PASS" or s0["timeline_sha256"] != plan["timeline_sha256"]:
        raise ValueError("S2′ requires v3 S0 PASS on the pinned timeline")
    verify(args.timeline, plan["timeline_sha256"])
    selection_path = args.s1_dir / "RANGING_RULE_SELECTION_V3.json"
    parity_path = args.s1_dir / "PARITY_V3.json"
    verify(selection_path, args.selection_sha256)
    verify(parity_path, args.parity_sha256)
    selection, parity = read(selection_path), read(parity_path)
    if (any(item.get("version") != 3 or item["status"] != "PASS"
            or item["s0_sha256"] != args.s0_sha256 or item["timeline_sha256"] != plan["timeline_sha256"]
            for item in (selection, parity))
            or selection["selected"] != parity["selected_rule"]
            or parity["selection_sha256"] != args.selection_sha256):
        raise ValueError("S2′ requires matching frozen v3 S1′ selection and parity PASS")
    verify(args.synthetic_receipt, plan["synthetic_sha256"])
    prior_tests = read(args.synthetic_receipt)
    verify(Path(__file__).with_name("tb3_model003_v3_characterization.py"), prior_tests["math_source_sha256"])
    runtime = synthetic_check(prior_tests["characterization"]["seed"])
    futility = futility_check()
    if (prior_tests["status"] != "PASS" or runtime["status"] != "PASS"
            or runtime["checks"] != prior_tests["characterization"]["checks"]
            or futility["status"] != "PASS" or futility != prior_tests["futility"]):
        raise ValueError("S2′ requires all prefrozen synthetic checks")
    if plan["thermal_draws_per_pose"] != DRAWS or list(plan["sensor_seeds"]) != list(range(40)):
        raise ValueError("Wrong built-in C1 draws or v3 motion seeds")
    return plan, selection, parity, runtime, futility


def run(args):
    plan, selection, parity, synthetic, futility_synthetic = verified_inputs(args)
    started = utc_now()
    args.out.mkdir(mode=0o700, exist_ok=False, parents=True)
    model, obs, banks, frequency, source, bank_hash = load_model(args)
    df = float(frequency[1] - frequency[0])
    index_path = args.results_root / "CASES.json"
    verify(index_path, parity["production_cases_sha256"])
    index = read(index_path)
    cases = {case: open_case(args.results_root, index[case], case) for case in CASES}
    input_hash = {case: data["input_sha256"] for case, data in cases.items()}
    if input_hash != parity["input_sha256"] or input_hash != selection["input_sha256"]:
        raise ValueError("S2′ inputs differ from frozen S1′ G-T1 RF inputs")
    timeline = timeline_data(args.timeline)
    chosen = selection["selected"]
    rules = tuple(dict.fromkeys((chosen, "O30")))
    offsets = {rule: parity["offsets"][rule]["mean_m"] for rule in rules}
    features = {rule: {} for rule in rules}
    residuals = {}
    for i, (case, data) in enumerate(cases.items()):
        kernels = kernel_inputs(data["samples"])
        residuals[case] = clean_data(data, obs, df, rules, offsets)
        noise = thermal(data, obs, df, rules, i, plan["rf_thermal_seed"])
        for rule in rules:
            features[rule][case[-1]] = anchor_features(data, residuals[case][rule], noise[rule], kernels)
        print(f"S2′ G-T1 features: {case}", flush=True)

    computed, characterization, transfer, limits = {}, {}, {}, {}
    settings, bootstrap = plan["futility"], plan["bootstrap"]
    for label, rule in (("OR", chosen), ("O30", "O30")):
        if rule not in computed:
            local = features[rule]
            c1_by_anchor = {a: c1_summary([row]) for a, row in local.items()}
            fits = {group: fit_group({a: local[a] for a in group}, c1_by_anchor, plan["c2"])
                    for group in ANCHORED_GROUPS}
            scope, c5, c8, windows = window_analysis(
                cases, residuals, fits, timeline, rule, model, obs, banks, settings, bootstrap, tuple(plan["sensor_seeds"]))
            k_by_path = {p: {g: path_s_variance(c5[p], g) for g in fits} for p in PATHS}
            check = transfer_precheck(cases, residuals, fits, windows, c5, rule)
            computed[rule] = (dict(rule=rule, offset_m=offsets[rule], anchor_fits=fits, C5_by_path=c5,
                                   C5_K_by_path=k_by_path, C8_by_path=c8),
                              dict(rule=rule, paths=scope), dict(rule=rule, folds=check))
            print(f"S2′ characterization finished: {rule}", flush=True)
        characterization[label], limits[label], transfer[label] = computed[rule]

    tracked_source = source | {name: sha(Path(__file__).with_name(name)) for name in
                                (Path(__file__).name, "run_tb3_model003_s2.py", "tb3_model003_v3_characterization.py",
                                 "tb3_model003_futility.py", "tb3_model003_motion.py", "tb3_model003_s1_observation.py")}
    metadata = dict(status="PASS", question_id=QUESTION, version=3, stage="S2'", role="IMPLEMENTER",
                    plan_sha256=args.plan_sha256, plan_commit=args.plan_commit, started_utc=started,
                    finished_utc=utc_now(), synthetic_receipt_sha256=plan["synthetic_sha256"],
                    timeline_sha256=plan["timeline_sha256"], s0_sha256=args.s0_sha256,
                    s1_receipts_sha256={"RANGING_RULE_SELECTION_V3.json": args.selection_sha256,
                                        "PARITY_V3.json": args.parity_sha256},
                    production_cases_sha256=sha(index_path), input_sha256=input_hash,
                    source_sha256=tracked_source, banks_sha256=bank_hash, governing_chain="OR")
    write(args.out / "CHARACTERIZATION_003_V3.json", metadata | dict(chains=characterization, synthetic=synthetic))
    write(args.out / "TRANSFER_PRECHECK.json", metadata | dict(chains=transfer, stage="S2-T", abs_z_threshold=2.))
    write(args.out / "FUTILITY_V3.json", metadata | dict(chains=limits, stage="S2-F", synthetic=futility_synthetic))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results-root", "s0-report", "s1-dir", "model-source", "banks-dir", "plan", "synthetic-receipt",
                 "timeline", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("s0-sha256", "selection-sha256", "parity-sha256", "plan-commit", "plan-sha256"):
        parser.add_argument("--" + name, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
