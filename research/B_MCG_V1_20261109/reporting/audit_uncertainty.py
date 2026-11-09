#!/usr/bin/env python3
"""Descriptive uncertainty audit from completed canonical traces only.

This evaluator never imports or runs the filter. It uses stored posterior x/P,
original evaluator truth and timestamps. Nominal 95% thresholds are unchanged;
no new policy-selection or adoption rule is introduced.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import scipy
from scipy.stats import chi2, norm

ROUTES = ("R2", "R4", "R5")
STRATA = ("B_FROZEN", "B_BIAS_COV")
MODES = ("OFF", "ACTIVE_RS")
AXES = ("xy", "heading", "pose")
EXPECTED_ROWS = {"R2": 979, "R4": 742, "R5": 1415}
LEVEL = .95
CRITICAL = {"xy": float(chi2.ppf(LEVEL, 2)),
            "heading": float(chi2.ppf(LEVEL, 1)),
            "pose": float(chi2.ppf(LEVEL, 3))}
Z975 = float(norm.ppf(.975))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    if not fields:
        raise ValueError("CSV_HAS_NO_SCHEMA")
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def wrap(x):
    return (np.asarray(x) + np.pi) % (2*np.pi) - np.pi


def statistics(values):
    values = np.asarray(values, float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("EMPTY_OR_NONFINITE_DESCRIPTIVE_VALUES")
    return {"mean": float(values.mean()), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95, method="linear"))}


def outside_episodes(outside, t, *, cadence_s, identity, axis):
    """Observed consecutive runs, with separate timestamp and sample support.

    elapsed_s is last outside timestamp minus first outside timestamp (one
    outside sample has elapsed 0). nominal_sample_support_s is count*cadence.
    The latter is not a measured continuous-time failure duration. It includes
    one nominal cell per sample, even at a censored acquisition boundary.
    """
    outside = np.asarray(outside, bool)
    t = np.asarray(t, float)
    if outside.shape != t.shape or len(t) == 0:
        raise ValueError("EPISODE_SHAPE")
    edges = np.flatnonzero(np.diff(np.r_[False, outside, False]))
    rows = []
    for number, (first, end) in enumerate(zip(edges[::2], edges[1::2]), 1):
        last = int(end - 1)
        rows.append({**identity, "axis": axis, "episode": number,
                     "first_k": int(first), "last_k": last,
                     "first_t_s": float(t[first]), "last_t_s": float(t[last]),
                     "outside_samples": int(end-first),
                     "observed_elapsed_s": float(t[last]-t[first]),
                     "nominal_sample_support_s": float((end-first)*cadence_s),
                     "left_censored": bool(first == 0),
                     "right_censored": bool(end == len(t))})
    summary = {"episode_count": len(rows), "outside_samples": int(outside.sum()),
               "left_censored_count": sum(int(x["left_censored"]) for x in rows),
               "right_censored_count": sum(int(x["right_censored"]) for x in rows),
               "duration_status": "OBSERVED_RUNS_DESCRIPTIVE" if rows else "NO_OUTSIDE_EPISODES"}
    for field in ("observed_elapsed_s", "nominal_sample_support_s"):
        vals = np.array([x[field] for x in rows])
        summary[field + "_max"] = float(vals.max()) if len(vals) else None
        summary[field + "_p95"] = float(np.quantile(vals, .95, method="linear")) if len(vals) else None
    assert sum(x["outside_samples"] for x in rows) == int(outside.sum())
    return summary, rows


def episode_definition_check():
    """Small independent known answer for isolated runs and right censoring."""
    t = np.array([0., .2, .4, .6, .8, 1.])
    summary, rows = outside_episodes([False, True, True, False, True, True], t,
                                    cadence_s=.2, identity={}, axis="fixture")
    assert summary["episode_count"] == 2 and summary["outside_samples"] == 4
    assert [(x["first_k"], x["last_k"]) for x in rows] == [(1, 2), (4, 5)]
    assert np.allclose([x["observed_elapsed_s"] for x in rows], [.2, .2], atol=1e-14)
    assert np.allclose([x["nominal_sample_support_s"] for x in rows], [.4, .4], atol=1e-14)
    assert not rows[0]["right_censored"] and rows[1]["right_censored"]
    _, one = outside_episodes([True], [2.], cadence_s=.2, identity={}, axis="fixture")
    assert one[0]["observed_elapsed_s"] == 0. and one[0]["nominal_sample_support_s"] == .2
    assert one[0]["left_censored"] and one[0]["right_censored"]
    empty, none = outside_episodes([False], [2.], cadence_s=.2, identity={}, axis="fixture")
    assert empty["episode_count"] == 0 and empty["observed_elapsed_s_max"] is None and not none
    return "PASS_KNOWN_ANSWER_DURATION_AND_CENSORING_FIXTURE"


def truth_for(route, assets, receipt):
    p = assets / f"{route}_B0_Full_10__evaluator.npz"
    expected = next(x for x in receipt["files"]
                    if x["name"].endswith(f"/{route}_B0_Full_10/evaluator.npz"))
    actual = sha(p)
    assert actual == expected["sha256"] and p.stat().st_size == expected["bytes"], "TRUTH_INPUT_HASH"
    with np.load(p, allow_pickle=False) as f:
        data = {k: f[k] for k in ("truth", "t", "pose_id")}
    assert len(data["t"]) == EXPECTED_ROWS[route]
    data["path"] = str(p)
    data["sha256"] = actual
    return data


def audit_record(route, stratum, mode, results, truth, runtime_hashes):
    identity = {"route": route, "stratum": stratum, "mode": mode}
    directory = results / "active" / stratum / mode
    meta_path = directory / f"{route}_{mode}.json"
    trace_path = directory / f"{route}_{mode}.npz"
    meta = read(meta_path)
    assert meta["status"] == "EXECUTED_RESEARCH_REPLAY"
    assert (meta["route"], meta["stratum"], meta["mode"]) == (route, stratum, mode)
    trace_sha = sha(trace_path)
    assert trace_sha == meta["trace_sha256"], "TRACE_HASH"
    assert meta["runtime_code_sha256"] == runtime_hashes, "FROZEN_RUNTIME_HASH"
    config_sha = hashlib.sha256(json.dumps(meta["config"], sort_keys=True).encode()).hexdigest()
    assert config_sha == meta["config_sha256"], "CONFIG_HASH"
    with np.load(trace_path, allow_pickle=False) as f:
        x, P, t, pose_id = (f[k] for k in ("x", "P", "t", "pose_id"))
    n = EXPECTED_ROWS[route]
    assert x.shape == (n, 4) and P.shape == (n, 4, 4) and truth["truth"].shape == (n, 3), "STATE_SHAPE"
    assert np.array_equal(t, truth["t"]) and np.array_equal(pose_id, truth["pose_id"]), "TRUTH_JOIN"
    assert all(np.isfinite(a).all() for a in (x, P, t, truth["truth"])), "NONFINITE_STATE"
    assert np.all(np.diff(t) > 0), "NONMONOTONIC_TIME"
    cadence = float(np.median(np.diff(t)))
    assert abs(cadence-.2) < 1e-10 and np.max(abs(np.diff(t)-cadence)) < 1e-10, "REGULAR_5HZ_REQUIRED"
    symmetry = float(np.max(abs(P-P.transpose(0, 2, 1))))
    min_eigen = float(np.linalg.eigvalsh(P).min())
    assert symmetry <= 1e-12 and min_eigen > 0, "COVARIANCE_INVALID"

    error = x[:, :3] - truth["truth"]
    error[:, 2] = wrap(error[:, 2])
    distances = {
        "pose": np.einsum("ni,ni->n", error, np.linalg.solve(P[:, :3, :3], error[..., None])[..., 0]),
        "xy": np.einsum("ni,ni->n", error[:, :2], np.linalg.solve(P[:, :2, :2], error[:, :2, None])[..., 0]),
        "heading": error[:, 2]**2 / P[:, 2, 2],
    }
    sign, logdet = np.linalg.slogdet(P[:, :2, :2])
    assert np.all(sign > 0)
    ellipse_area = np.pi * CRITICAL["xy"] * np.exp(logdet/2)
    heading_width = np.degrees(2 * Z975 * np.sqrt(P[:, 2, 2]))
    sizes = {"xy95_ellipse_area_m2": statistics(ellipse_area),
             "heading95_full_width_deg": statistics(heading_width)}
    coverage = {axis+"95_coverage": float(np.mean(distances[axis] <= CRITICAL[axis])) for axis in AXES}
    reconciliation = {k: abs(v-float(meta["metrics"][k])) for k, v in coverage.items()}
    assert max(reconciliation.values()) < 1e-12, "REPORTED_COVERAGE_MISMATCH"
    episodes, episode_rows = {}, []
    for axis in AXES:
        summary, rows = outside_episodes(distances[axis] > CRITICAL[axis], t,
                                        cadence_s=cadence, identity=identity, axis=axis)
        episodes[axis] = summary
        episode_rows.extend(rows)

    item = {**identity, "n": n, "sampling_cadence_s": cadence,
            "observed_elapsed_s": float(t[-1]-t[0]), "nominal_sample_support_s": float(n*cadence),
            "size": sizes, "coverage": coverage,
            "mean_nees": {axis: float(distances[axis].mean()) for axis in AXES}, "outside_episodes": episodes,
            "numerical_checks": {"max_P_asymmetry": symmetry, "minimum_P_eigenvalue": min_eigen,
                                 "metadata_coverage_max_error": max(reconciliation.values())},
            "provenance": {"metadata_path": str(meta_path), "metadata_sha256": sha(meta_path),
                           "trace_path": str(trace_path), "trace_sha256": trace_sha,
                           "truth_path": truth["path"], "truth_sha256": truth["sha256"],
                           "config_sha256": config_sha, "runtime_code_sha256": meta["runtime_code_sha256"],
                           "source_hashes": meta["source_hashes"], "archive_sha256": meta["archive_sha256"],
                           "policy_lock_sha256": meta.get("policy_lock_sha256"),
                           "execution_policy_role": meta["execution_policy_role"]}}
    flat = {**identity, "n": n, "sampling_cadence_s": cadence, "observed_elapsed_s": item["observed_elapsed_s"]}
    flat.update(coverage)
    for label, stats in sizes.items():
        flat.update({label+"_"+key: value for key, value in stats.items()})
    for axis, value in episodes.items():
        flat.update({axis+"_outside_"+key: val for key, val in value.items()})
    arrays = {"xy95_ellipse_area_m2": ellipse_area, "heading95_full_width_deg": heading_width,
              "distances": distances}
    return item, flat, episode_rows, arrays


def pool_records(records, episodes, arrays):
    """Pool rows for sizes/coverage, but never join episodes across routes."""
    pooled, table = [], []
    for stratum in STRATA:
        for mode in MODES:
            members = [r for r in records if r["stratum"] == stratum and r["mode"] == mode]
            assert len(members) == 3
            n = sum(r["n"] for r in members)
            raw = [arrays[(stratum, r, mode)] for r in ROUTES]
            sizes = {key: statistics(np.concatenate([a[key] for a in raw]))
                     for key in ("xy95_ellipse_area_m2", "heading95_full_width_deg")}
            distances = {axis: np.concatenate([a["distances"][axis] for a in raw]) for axis in AXES}
            coverage = {axis+"95_coverage": float(np.mean(distances[axis] <= CRITICAL[axis])) for axis in AXES}
            weighted_errors = []
            for key in coverage:
                weighted_errors.append(abs(coverage[key]-sum(r["n"]*r["coverage"][key] for r in members)/n))
            for key in sizes:
                weighted_errors.append(abs(sizes[key]["mean"]-sum(r["n"]*r["size"][key]["mean"] for r in members)/n))
            assert max(weighted_errors) < 1e-12
            summaries = {}
            for axis in AXES:
                runs = [e for e in episodes if e["stratum"] == stratum and e["mode"] == mode and e["axis"] == axis]
                outside_count = int(np.sum(distances[axis] > CRITICAL[axis]))
                assert sum(x["outside_samples"] for x in runs) == outside_count
                summary = {"episode_count": len(runs), "outside_samples": outside_count,
                           "left_censored_count": sum(int(x["left_censored"]) for x in runs),
                           "right_censored_count": sum(int(x["right_censored"]) for x in runs),
                           "duration_status": "OBSERVED_RUNS_DESCRIPTIVE" if runs else "NO_OUTSIDE_EPISODES"}
                for field in ("observed_elapsed_s", "nominal_sample_support_s"):
                    vals = np.array([r[field] for r in runs])
                    summary[field+"_max"] = float(vals.max()) if len(vals) else None
                    summary[field+"_p95"] = float(np.quantile(vals, .95, method="linear")) if len(vals) else None
                summaries[axis] = summary
            item = {"stratum": stratum, "mode": mode, "routes": list(ROUTES), "n": n,
                    "size": sizes, "coverage": coverage, "outside_episodes": summaries,
                    "mean_nees": {axis: float(values.mean()) for axis, values in distances.items()},
                    "weighted_mean_identity_max_error": max(weighted_errors),
                    "trace_sha256_by_route": {r["route"]: r["provenance"]["trace_sha256"] for r in members}}
            flat = {"stratum": stratum, "mode": mode, "n": n, **coverage}
            for key, stats in sizes.items():
                flat.update({key+"_"+k: v for k, v in stats.items()})
            for axis, summary in summaries.items():
                flat.update({axis+"_outside_"+k: v for k, v in summary.items()})
            pooled.append(item)
            table.append(flat)
    return pooled, table


def delivery_reconcile(path, records):
    if not path.is_file():
        return {"status": "NOT_AVAILABLE", "path": str(path)}
    reference = read(path)
    status = reference.get("status")
    if status != "COMPLETED_NUMERICAL_DELIVERY_EVALUATION":
        return {"status": "FINAL_DELIVERY_NOT_READY", "observed_status": status, "path": str(path), "sha256": sha(path)}
    lookup = {(r["stratum"], r["route"], r["mode"]): r for r in reference["evaluated_records"]}
    errors = []
    for r in records:
        old = lookup[(r["stratum"], r["route"], r["mode"])]
        assert old["trace_sha256"] == r["provenance"]["trace_sha256"], "DELIVERY_TRACE_HASH_MISMATCH"
        for key, value in r["coverage"].items():
            errors.append(abs(value-old["metrics"][key]))
    assert len(errors) == 36 and max(errors) < 1e-12, "DELIVERY_COVERAGE_MISMATCH"
    return {"status": "PASS_12_TRACES_36_COVERAGES", "path": str(path), "sha256": sha(path),
            "max_coverage_difference": max(errors)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--assets", type=Path)
    ap.add_argument("--input-receipt", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    root = a.root.resolve()
    assets = a.assets or root/"assets"
    receipt_path = a.input_receipt or root/"recovery/INPUT_RECEIPT.json"
    out = a.out or root/"results/uncertainty"
    results = root/"results"
    runtime_dir = Path(__file__).resolve().parents[1]
    hashes = {name: sha(runtime_dir/name) for name in ("mcg.py", "experiment.py")}
    own_hash = sha(__file__)
    receipt = read(receipt_path)
    assert receipt["status"] == "PASS_STAGED_HASHED_INPUTS"
    # Require all canonical metadata before creating a final-looking output.
    missing = [str(results/"active"/s/m/f"{r}_{m}.json")
               for s in STRATA for r in ROUTES for m in MODES
               if not (results/"active"/s/m/f"{r}_{m}.json").is_file()]
    if missing:
        raise FileNotFoundError("MISSING_COMPLETED_CANONICAL_METADATA: " + ", ".join(missing))
    fixture = episode_definition_check()
    truths = {r: truth_for(r, assets, receipt) for r in ROUTES}
    records, metrics_rows, episodes, arrays = [], [], [], {}
    for stratum in STRATA:
        for route in ROUTES:
            for mode in MODES:
                item, flat, rows, raw = audit_record(route, stratum, mode, results, truths[route], hashes)
                records.append(item)
                metrics_rows.append(flat)
                episodes.extend(rows)
                arrays[(stratum, route, mode)] = raw
    pooled, pooled_rows = pool_records(records, episodes, arrays)
    comparisons = []
    for stratum in STRATA:
        for route in ROUTES:
            by_mode = {r["mode"]: r for r in records if r["stratum"] == stratum and r["route"] == route}
            off, active = by_mode["OFF"], by_mode["ACTIVE_RS"]
            ratios = {key: {stat: active["size"][key][stat]/off["size"][key][stat] for stat in ("mean", "median", "p95")}
                      for key in off["size"]}
            comparisons.append({"stratum": stratum, "route": route,
                                "active_over_off_size_ratio": ratios,
                                "active_minus_off_coverage_pp": {k: 100*(active["coverage"][k]-off["coverage"][k]) for k in off["coverage"]},
                                "interpretation": "Descriptive own-state comparison; no new pass/fail threshold."})
    assert hashes == {name: sha(runtime_dir/name) for name in hashes} and own_hash == sha(__file__), "CODE_CHANGED_DURING_AUDIT"
    result = {
        "status": "COMPLETED_DESCRIPTIVE_UNCERTAINTY_AUDIT",
        "scope": "12 canonical OFF/ACTIVE_RS streams; 3 routes x 2 historical calibration strata. Saved posterior x/P only; no filter rerun or policy tuning.",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "nominal_level": LEVEL, "chi2_critical_values": CRITICAL, "normal_975_quantile": Z975,
        "formulas": {"xy95_ellipse_area_m2": "pi * chi2.ppf(.95,2) * sqrt(det(Pxy))",
                     "heading95_full_width_deg": "degrees(2 * norm.ppf(.975) * sqrt(Ppsi_psi))",
                     "coverage": "fraction of all posterior samples with squared Mahalanobis distance <= corresponding chi2 .95 threshold; heading residual wrapped to [-pi,pi)"},
        "episode_definitions": {"run": "Maximal consecutive observed samples outside the fixed nominal 95% region. All samples, including RF-rejected samples, are evaluated.",
                                "observed_elapsed_s": "t[last outside] - t[first outside]; one-sample run = 0 seconds. This does not infer unobserved entry/exit times.",
                                "nominal_sample_support_s": "outside sample count * median sampling cadence (verified regular 5Hz). This counts a nominal .2s support cell per sample; it is not a measured continuous duration and may extend a boundary cell past the last timestamp.",
                                "censoring": "Runs touching the first/last acquisition sample are flagged left/right censored. Max/p95 describe observed runs only, without survival extrapolation; a censored run can be longer in reality.",
                                "p95": "Unweighted np.quantile(...,.95,method='linear') across observed runs, not across samples. With no episodes, count=0 but duration max/p95=null.",
                                "independence": "Consecutive/overlapping samples and cross-mode copies are not independent experiments. No episode duration is a recovery-time ratio."},
        "pooling_definition": {"size_mean_and_coverage": "Concatenate all original rows across the three routes; equivalent to n-weighted route means. Identity checked numerically.",
                               "size_median_and_p95": "Compute on concatenated original per-sample area/width arrays, never average route quantiles.",
                               "episodes": "Keep every route boundary separate. Pool existing episode rows only: count sum, longest maximum, p95 of concatenated observed-run durations. Never join the last episode of one route to the first of another.",
                               "scope": "Descriptive pooled dataset; shared noise does not become independent replication."},
        "interpretation_limits": ["Nominal Gaussian/elliptical sizes are filter reports, not calibrated probability guarantees.",
                                  "Empirical coverage and confidence-region size must be read jointly; neither establishes accuracy alone.",
                                  "Consecutive filter coverage failures do not measure pure RF distortion duration or a guaranteed clean refresh interval.",
                                  "No new adoption rule or statistical significance claim.",
                                  "Same exposed corridor and shared sensor-noise realization; no new scene/seed validation."],
        "episode_definition_fixture": fixture, "n_records": len(records),
        "records": records, "pooled": pooled, "paired_descriptive_comparisons": comparisons,
        "delivery_reconciliation": delivery_reconcile(results/"delivery_evaluation/RESULTS.json", records),
        "provenance": {"script_path": str(Path(__file__).resolve()), "script_sha256": own_hash,
                       "runtime_code_sha256": hashes, "runtime_unchanged_entry_exit": True,
                       "input_receipt_path": str(receipt_path), "input_receipt_sha256": sha(receipt_path),
                       "source_commit": receipt["source_commit"], "python": sys.version,
                       "numpy": np.__version__, "scipy": scipy.__version__}}
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out/"METRICS.csv", metrics_rows)
    write_csv(out/"POOLED_METRICS.csv", pooled_rows)
    write_csv(out/"COVERAGE_EPISODES.csv", episodes)
    save_json(out/"RESULTS.json", result)
    save_json(out/"SHA256.json", {p.name: sha(p) for p in (out/"METRICS.csv", out/"POOLED_METRICS.csv", out/"COVERAGE_EPISODES.csv", out/"RESULTS.json")})
    print(json.dumps({"status": result["status"], "records": len(records), "outside_episodes": len(episodes),
                      "metadata_coverage_max_error": max(x["numerical_checks"]["metadata_coverage_max_error"] for x in records),
                      "delivery_reconciliation": result["delivery_reconciliation"], "output": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
