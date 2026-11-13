"""Step 1 summary and spatial-correlation analysis for G1-FLOOR-001.

This module consumes only the row-level sweep CSVs and caller-supplied spatial
arrays. It does not load research inputs or execute the estimator.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20261113
DERIVATIVE_MIN_PER_RAD = 0.1


def _number(row, name, default=float("nan")):
    try:
        return float(row[name])
    except (KeyError, TypeError, ValueError):
        return default


def _quantile(values, q):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.quantile(values, q)) if values.size else float("nan")


def _summarize(errors):
    errors = np.asarray(errors, dtype=float)
    errors = errors[np.isfinite(errors)]
    absolute = np.abs(errors)
    return {
        "n_valid": int(errors.size),
        "median_abs_deg": _quantile(absolute, 0.5),
        "rms_deg": float(np.sqrt(np.mean(errors**2))) if errors.size else float("nan"),
        "p95_abs_deg": _quantile(absolute, 0.95),
        "bias_deg": float(np.mean(errors)) if errors.size else float("nan"),
        "bad5_rate": float(np.mean(absolute > 5.0)) if errors.size else float("nan"),
        "bad10_rate": float(np.mean(absolute > 10.0)) if errors.size else float("nan"),
        "branch_flip_rate": float(np.mean(absolute > 45.0)) if errors.size else float("nan"),
    }


def _cluster_bootstrap(rows, metric, seed):
    """Paired physical-station bootstrap, retaining all rows within each XY."""
    clusters = defaultdict(list)
    for row in rows:
        # The case identifies the physical RT route realization; all seeds and
        # estimator arms at a station remain together in its cluster.
        key = (row.get("route", ""), row.get("station_xy", ""))
        clusters[key].append(row)
    if len(clusters) < 2:
        return float("nan"), float("nan")
    sums, counts = [], []
    for cluster in clusters.values():
        values = np.asarray([_number(row, metric) for row in cluster])
        values = values[np.isfinite(values)]
        sums.append(np.sum(values**2))
        counts.append(len(values))
    rng = np.random.default_rng(seed)
    k = len(clusters)
    sampled = rng.integers(k, size=(BOOTSTRAP_REPLICATES, k))
    numerator = np.asarray(sums)[sampled].sum(axis=1)
    denominator = np.asarray(counts)[sampled].sum(axis=1)
    valid = denominator > 0
    estimates = np.sqrt(numerator[valid] / denominator[valid])
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def _station_key(row):
    return f"{_number(row, 'x'):.4f},{_number(row, 'y'):.4f}"


def _read_case_csvs(paths):
    rows = []
    for path in paths:
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                row["case"] = row.get("case") or path.stem.removeprefix("S1_SWEEP_ERRORS_")
                row["station_xy"] = _station_key(row)
                rows.append(row)
    return rows


def _write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _summary_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        distance = _number(row, "dist_xy")
        distance_bin = "[0,5)" if distance < 5 else "[5,10)" if distance < 10 else "[10,inf)"
        groups[(row.get("case", ""), row.get("channel", ""), row.get("snr_db", ""),
                row.get("span_deg", ""), row.get("imu_k", ""), row.get("prior_sigma", ""),
                row.get("window", ""), row.get("xy_arm", ""),
                row.get("actual_span_deg", ""), distance_bin)].append(row)
        groups[(row.get("case", ""), row.get("channel", ""), row.get("snr_db", ""),
                row.get("span_deg", ""), row.get("imu_k", ""), row.get("prior_sigma", ""),
                row.get("window", ""), row.get("xy_arm", ""), "all", "all")].append(row)

    output = []
    for group_key, group in sorted(groups.items()):
        errors = [_number(row, "err_deg") for row in group]
        stats = _summarize(errors)
        stats.update(dict(zip(("case", "channel", "snr_db", "span_deg", "k",
                               "sigma_prior_deg", "window", "xy_arm", "actual_span_deg",
                               "distance_bin"), group_key)))
        stats["station_clusters"] = len({(row.get("route", ""), row.get("station_xy", ""))
                                         for row in group})
        stats["window_miss_rate"] = float(np.mean([
            str(row.get("window_miss", "")).lower() in ("1", "true", "yes") for row in group
        ])) if group else float("nan")
        stats["rms_ci95_low"], stats["rms_ci95_high"] = _cluster_bootstrap(group, "err_deg", BOOTSTRAP_SEED)
        output.append(stats)
    return output


def _threshold_for_training(rows):
    """Largest retained coverage subject to training bad5 <= 5 percent."""
    eligible = []
    margins = np.asarray([_number(row, "margin") for row in rows], dtype=float)
    errors = np.asarray([_number(row, "err_deg") for row in rows], dtype=float)
    valid = np.isfinite(margins) & np.isfinite(errors)
    margins, errors = margins[valid], errors[valid]
    for threshold in np.unique(margins):
        keep = margins >= threshold
        if np.any(keep) and np.mean(np.abs(errors[keep]) > 5.0) <= 0.05:
            eligible.append((int(np.sum(keep)), float(threshold)))
    if not eligible:
        return float("inf")
    # Maximize coverage; for equal coverage, use the larger, more conservative threshold.
    return max(eligible, key=lambda item: (item[0], item[1]))[1]


def _actual_span_is_90(row):
    actual = _number(row, "actual_span_deg")
    return np.isfinite(actual) and math.isclose(actual, 90.0, abs_tol=1e-9)


def _margin_cv(rows):
    output = []
    for case in sorted({row.get("case", "") for row in rows}):
        route = case[:2]
        test = [row for row in rows if row.get("case", "")[:2] == route]
        train = [row for row in rows if row.get("case", "")[:2] != route]
        # Evaluate the preregistered primary measurement arm only.
        def is_primary(row):
            return (row.get("channel") == "full" and row.get("xy_arm") == "XY-P"
                    and _number(row, "snr_db") == 30
                    and _number(row, "span_deg") == 90
                    and _actual_span_is_90(row)
                    and _number(row, "imu_k") == 0.0085
                    and _number(row, "prior_sigma") == 5
                    and _number(row, "window") == 30)
        train = [row for row in train if is_primary(row)]
        test = [row for row in test if is_primary(row) and row.get("case", "") == case]
        threshold = _threshold_for_training(train)
        finite = [row for row in test if math.isfinite(_number(row, "margin"))
                  and math.isfinite(_number(row, "err_deg"))]
        retained = [row for row in finite if _number(row, "margin") >= threshold]
        stats = _summarize([_number(row, "err_deg") for row in retained])
        output.append({
            "held_out_route": route,
            "held_out_case": case,
            "training_threshold": threshold,
            "n_test": len(finite),
            "n_retained": len(retained),
            "coverage": len(retained) / len(finite) if finite else float("nan"),
            "heldout_bad5_rate": stats["bad5_rate"],
            "heldout_bad10_rate": stats["bad10_rate"],
            "heldout_branch_flip_rate": stats["branch_flip_rate"],
        })
    return output


def _autocorrelation_by_segment(x, residual, lag_values):
    """Within-segment centered Pearson correlation at geometric lag bins."""
    valid_segments = []
    for x_seg, d_seg in zip(x, residual):
        x_seg = np.asarray(x_seg, dtype=float)
        d_seg = np.asarray(d_seg, dtype=float)
        valid = np.isfinite(x_seg) & np.isfinite(d_seg)
        x_seg, d_seg = x_seg[valid], d_seg[valid]
        if x_seg.size >= 3:
            order = np.argsort(x_seg)
            x_seg, d_seg = x_seg[order], d_seg[order]
            d_seg = d_seg - np.mean(d_seg)
            valid_segments.append((x_seg, d_seg))

    result = []
    for lag in lag_values:
        numerator = denominator_left = denominator_right = 0.0
        pair_count = 0
        for x_seg, d_seg in valid_segments:
            left, right = np.triu_indices(d_seg.size, k=1)
            delta = x_seg[right] - x_seg[left]
            selected = (delta >= lag - 0.02) & (delta < lag + 0.02)
            if not np.any(selected):
                continue
            a, b = d_seg[left[selected]], d_seg[right[selected]]
            numerator += float(np.sum(a * b))
            denominator_left += float(np.sum(a * a))
            denominator_right += float(np.sum(b * b))
            pair_count += int(a.size)
        denom = math.sqrt(denominator_left * denominator_right)
        result.append((numerator / denom if denom > 0 else float("nan"), pair_count))
    return result


def _rank_average(values):
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    start = 0
    while start < values.size:
        end = start + 1
        while end < values.size and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = 0.5 * (start + end - 1) + 1.0
        start = end
    return ranks


def _adjacent_error_correlations(rows):
    output = {}
    for case in sorted({row.get("case", "") for row in rows}):
        primary = [row for row in rows if row.get("case") == case
                   and row.get("channel") == "full" and row.get("xy_arm") == "XY-P"
                   and _number(row, "snr_db") == 30 and _number(row, "span_deg") == 90
                   and _actual_span_is_90(row)
                   and _number(row, "imu_k") == 0.0085
                   and _number(row, "prior_sigma") == 5
                   and _number(row, "window") == 30]
        stations = defaultdict(list)
        for row in primary:
            stations[row.get("group", "")].append(row)
        points = []
        for group, station_rows in stations.items():
            x = float(np.nanmedian([_number(row, "x") for row in station_rows]))
            y = float(np.nanmedian([_number(row, "y") for row in station_rows]))
            e = float(np.nanmedian([_number(row, "err_deg") for row in station_rows]))
            if np.isfinite(x) and np.isfinite(y) and np.isfinite(e):
                points.append((int(round(y / 0.25)), x, e, group))
        pairs = []
        for lane in sorted({point[0] for point in points}):
            lane_points = sorted((p for p in points if p[0] == lane), key=lambda p: p[1])
            for left, right in zip(lane_points, lane_points[1:]):
                if 1.0 <= right[1] - left[1] <= 3.0:
                    pairs.append((left[2], right[2]))
        a = np.asarray([pair[0] for pair in pairs], dtype=float)
        b = np.asarray([pair[1] for pair in pairs], dtype=float)
        pearson = float(np.corrcoef(a, b)[0, 1]) if a.size >= 2 and np.std(a) and np.std(b) else float("nan")
        ra, rb = _rank_average(a), _rank_average(b)
        spearman = float(np.corrcoef(ra, rb)[0, 1]) if a.size >= 2 and np.std(ra) and np.std(rb) else float("nan")
        output[case] = {"adjacent_heading_pearson": pearson,
                        "adjacent_heading_spearman": spearman,
                        "adjacent_station_pairs": int(a.size)}
    return output


def _spatial_rows(spatial_inputs):
    output, rho_by_case = [], {}
    for case, item in sorted(spatial_inputs.items()):
        x = np.asarray(item["x"], dtype=float)
        y = np.asarray(item["y"], dtype=float)
        yaw = np.asarray(item["yaw_deg"], dtype=float)
        full = np.asarray(item["s_full"], dtype=float)
        los = np.asarray(item["s_los"], dtype=float)
        jac = np.asarray(item["jac_yaw"], dtype=float)
        ds = full - los
        excluded = np.zeros(ds.size, dtype=bool)
        for indices in item.get("sweep_indices", []):
            excluded[np.asarray(indices, dtype=int)] = True
        ds[excluded] = np.nan

        # Preserve acquisition order, splitting when direction or heading changes
        # or the next travel point is outside the same straight leg.
        travel = np.flatnonzero(~excluded & np.isfinite(x) & np.isfinite(y) & np.isfinite(yaw))
        step_x = np.diff(x[travel])
        step_y = np.diff(y[travel])
        yaw_step = np.abs((np.diff(yaw[travel]) + 180.) % 360. - 180.)
        direction = np.cos(np.deg2rad(yaw[travel]))
        cuts = (np.hypot(step_x, step_y) > .20) | (yaw_step > 8.) | (
            (direction[1:] >= 0) != (direction[:-1] >= 0))
        if case.startswith("R4_"):
            # R4 follows diagonal legs that cross y=0; yaw sign distinguishes
            # the alternating headings. Crossing the corridor midline is travel.
            side = np.signbit(yaw[travel])
        else:
            side = y[travel] > 0
        cuts |= side[1:] != side[:-1]
        segments_x, segments_ds, segments_heading = [], [], []
        for order in np.split(travel, np.flatnonzero(cuts) + 1):
            if len(order) < 3:
                continue
            dx, dy = x[order[-1]] - x[order[0]], y[order[-1]] - y[order[0]]
            length = np.hypot(dx, dy)
            if length < .12 or abs(dx) < abs(dy):
                continue
            distance = ((x[order]-x[order[0]])*dx + (y[order]-y[order[0]])*dy) / length
            segments_x.append(distance)
            segments_ds.append(ds[order])
            valid_heading = np.isfinite(jac[order]) & (np.abs(jac[order]) >= DERIVATIVE_MIN_PER_RAD)
            heading_values = np.full(order.size, np.nan)
            valid = valid_heading & np.isfinite(ds[order])
            heading_values[valid] = np.degrees(ds[order][valid] / jac[order][valid])
            segments_heading.append(heading_values)

        max_lag = min(3.0, max((seg[-1] for seg in segments_x), default=0.0))
        lags = np.arange(0.04, max_lag + 0.001, 0.04)
        correlations = _autocorrelation_by_segment(segments_x, segments_ds, lags)
        lag_045 = _autocorrelation_by_segment(segments_x, segments_ds, [0.45])[0]
        lag_2m = _autocorrelation_by_segment(segments_x, segments_ds, [2.0])[0]
        raw_rho = lag_045[0]
        rho = float(np.clip(raw_rho, 0.0, 1.0)) if np.isfinite(raw_rho) else None
        rho_by_case[case] = rho
        crossing = next((lag for lag, (corr, _) in zip(lags, correlations)
                         if np.isfinite(corr) and corr <= 1.0 / math.e), float("nan"))

        valid_jac = np.isfinite(jac) & (np.abs(jac) >= DERIVATIVE_MIN_PER_RAD)
        heading_lag, heading_pairs = _autocorrelation_by_segment(
            segments_x, segments_heading, [0.45]
        )[0]
        output.append({
            "case": case,
            "lag_045_raw_rho": raw_rho,
            "lag_045_clipped_rho": rho,
            "lag_045_pairs": lag_045[1],
            "lag_2m_raw_rho": lag_2m[0],
            "lag_2m_pairs": lag_2m[1],
            "autocorr_by_lag": json.dumps([
                {"lag_m": float(lag), "rho": corr, "pairs": count}
                for lag, (corr, count) in zip(lags, correlations)
            ], separators=(",", ":")),
            "correlation_length_1e_m": crossing,
            "n_poses": int(ds.size),
            "n_valid_ds": int(np.isfinite(ds).sum()),
            "n_heading_equiv_valid": int(np.sum(valid_jac & np.isfinite(ds))),
            "heading_equiv_rho_045": heading_lag,
            "heading_equiv_pairs_045": heading_pairs,
        })
    return output, rho_by_case


def analyze(out, inventories, spatial_inputs):
    """Write S1 summaries and return Step 2 rho by case.

    Args:
        out: directory containing S1_SWEEP_ERRORS_<case>.csv files.
        inventories: reserved for caller inventory metadata.
        spatial_inputs: case-keyed arrays for each full and LoS trace.
    """
    del inventories
    out = Path(out)
    summary, diagnostic_rows = [], []
    for path in sorted(out.glob("S1_SWEEP_ERRORS_*.csv")):
        rows = _read_case_csvs([path])
        summary.extend(_summary_rows(rows))
        diagnostic_rows.extend(row for row in rows
                               if row["channel"] == "full" and row["xy_arm"] == "XY-P"
                               and _number(row, "snr_db") == 30 and _number(row, "span_deg") == 90
                               and _number(row, "imu_k") == 0.0085
                               and _number(row, "prior_sigma") == 5
                               and _number(row, "window") == 30)
    summary_fields = sorted({key for row in summary for key in row})
    _write_csv(out / "S1_SUMMARY.csv", summary, summary_fields or ["case"])
    mount_zero = [row for row in diagnostic_rows if row["case"].endswith("_m0")]
    margin = _margin_cv(mount_zero)
    _write_csv(out / "S1_MARGIN_CV.csv", margin, sorted({k for row in margin for k in row}) or ["held_out_case"])

    spatial, rho = _spatial_rows(spatial_inputs)
    adjacent = _adjacent_error_correlations(diagnostic_rows)
    for row in spatial:
        row.update(adjacent.get(row["case"], {}))
    _write_csv(out / "S1_SPATIAL_CORR.csv", spatial,
               sorted({key for row in spatial for key in row}) or ["case"])
    return rho
