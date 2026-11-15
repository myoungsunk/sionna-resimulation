"""G1-INT-DIAG-001/D4 pre-gate signed residual statistics and H3 verdicts."""

import numpy as np


CHANNELS = ("r", "s")
DISTANCE_BINS = ((0.0, 3.0), (3.0, 6.0), (6.0, 10.0), (10.0, None))
D4_THRESHOLDS = {
    "distance_bins_m": [list(bounds) for bounds in DISTANCE_BINS],
    "min_packets_per_bin": 30,
    "min_effective_packets_per_bin": 5.0,
    "min_supported_route_distance_bins": 4,
    "abs_mean_over_sigma_strictly_greater_than": 0.5,
    "min_fraction_supported_bins_above_threshold": 0.25,
}


def _autocorrelation_time(values, packet_indices):
    """D2's initial positive lag-pair estimate, with in-bin contiguous products only."""
    centered = values - values.mean()
    denominator = centered @ centered
    breaks = np.flatnonzero(np.diff(packet_indices) != 1) + 1
    segments = np.split(centered, breaks)
    pairs_at_one = sum(len(segment) - 1 for segment in segments)
    longest = max(map(len, segments))
    tau, last_lag = 1.0, 0
    if np.ptp(values) == 0.0 or denominator <= 0.0:
        return tau, last_lag, pairs_at_one, len(segments)
    for lag in range(1, min(len(values) // 2, longest - 1), 2):
        pair_sum = 0.0
        for offset in (lag, lag + 1):
            runs = [segment for segment in segments if len(segment) > offset]
            if sum(len(segment) - offset for segment in runs) < 2:
                return tau, last_lag, pairs_at_one, len(segments)
            pair_sum += sum(segment[:-offset] @ segment[offset:] for segment in runs) / denominator
        if pair_sum <= 0.0:
            break
        tau += 2.0 * pair_sum
        last_lag = lag + 1
    return float(tau), last_lag, pairs_at_one, len(segments)


def _summarize_bin(indices, epsilon, noise):
    n = len(indices)
    result = {
        "n": n, "n_eff": 0.0, "tau": None, "last_positive_lag": 0,
        "lag1_pair_count": 0, "contiguous_run_count": 0,
        "signed_mean": None, "rms": None, "centered_variance": None,
        "mean_R_eff": None, "sqrt_mean_R_eff": None, "abs_mean_over_sigma": None,
        "supported": False, "above_threshold": None,
    }
    if n == 0:
        return result

    values = epsilon[indices]
    mean = float(values.mean())
    mean_noise = float(noise[indices].mean())
    sigma = float(np.sqrt(mean_noise))
    tau, last_lag, pairs_at_one, segments = _autocorrelation_time(values, indices)
    n_eff = n / tau
    effect = abs(mean) / sigma
    supported = n >= D4_THRESHOLDS["min_packets_per_bin"] and n_eff >= D4_THRESHOLDS["min_effective_packets_per_bin"]
    result.update(
        n_eff=n_eff, tau=tau, last_positive_lag=last_lag, lag1_pair_count=pairs_at_one,
        contiguous_run_count=segments, signed_mean=mean, rms=float(np.sqrt(np.mean(values**2))),
        centered_variance=float(np.var(values)), mean_R_eff=mean_noise, sqrt_mean_R_eff=sigma,
        abs_mean_over_sigma=effect, supported=supported,
        above_threshold=effect > D4_THRESHOLDS["abs_mean_over_sigma_strictly_greater_than"],
    )
    return result


def _h3(rows):
    supported = [row for row in rows if row["supported"]]
    above = [row for row in supported if row["above_threshold"]]
    pos = sum(row["signed_mean"] > 0.0 for row in above)
    neg = len(above) - pos
    fraction = len(above) / len(supported) if supported else None
    if len(supported) < D4_THRESHOLDS["min_supported_route_distance_bins"]:
        status = "H3_INCONCLUSIVE"
    elif fraction >= D4_THRESHOLDS["min_fraction_supported_bins_above_threshold"]:
        status = "H3_SUPPORTED"
    else:
        status = "H3_NOT_SUPPORTED"
    direction = "mixed" if pos and neg else "positive" if pos else "negative" if neg else "none"
    fields = ("route", "distance_bin", "signed_mean", "abs_mean_over_sigma", "n_eff", "reference_metrics")
    return {
        "status": status, "supported_bins": len(supported), "above_threshold_bins": len(above),
        "above_threshold_fraction": fraction, "positive_above_threshold_bins": pos,
        "negative_above_threshold_bins": neg, "direction": direction,
        "exceedances": [{key: row[key] for key in fields} for row in above],
    }


def _cell_rows(cell):
    metadata = {key: cell[key] for key in ("anchor", "bias", "route")}
    t, pose_id, rho, e, noise, gate = (np.asarray(cell[key]) for key in (
        "t", "pose_id", "rho", "epsilon", "R_eff_diagonal", "mask"))
    n = len(t)
    if (n == 0 or any(a.shape != (n,) for a in (t, pose_id, rho, gate)) or
            e.shape != (n, 2) or noise.shape != (n, 2) or gate.dtype.kind != "b"):
        raise ValueError(f"D4 cell shape or mask mismatch: {metadata}")
    if not np.isfinite(t).all() or np.any(np.diff(t) <= 0) or len(np.unique(pose_id)) != n:
        raise ValueError(f"D4 invalid packet axis: {metadata}")
    finite = np.isfinite(rho) & np.isfinite(e).all(axis=1) & np.isfinite(noise).all(axis=1)
    if np.any(rho[finite] < 0.0) or np.any(noise[finite] <= 0.0):
        raise ValueError(f"D4 invalid distance or R_eff: {metadata}")

    rows = []
    for low, high in DISTANCE_BINS:
        label = f"[{low:g},{high:g})" if high is not None else f"[{low:g},inf)"
        in_bin = finite & (rho >= low)
        if high is not None:
            in_bin &= rho < high
        indices = np.flatnonzero(in_bin)
        for column, channel in enumerate(CHANNELS):
            stats = _summarize_bin(indices, e[:, column], noise[:, column])
            rows.append({**metadata, "channel": channel, "distance_bin": label,
                         "distance_min_m": low, "distance_max_m": high,
                         **stats, "reference_metrics": cell["reference_metrics"]})
    checks = {**metadata, "packets": n, "finite_pre_gate": int(finite.sum()),
              "nonfinite_pre_gate": int((~finite).sum()), "gate_accepted": int(gate.sum()),
              "finite_gate_rejected_included": int((finite & ~gate).sum())}
    if sum(row["n"] for row in rows if row["channel"] == "r") != checks["finite_pre_gate"]:
        raise ValueError(f"D4 finite packet count not conserved: {metadata}")
    return rows, checks


def analyze(cells):
    """Aggregate truth-state residuals with route × range bins as the H3 units."""
    bins, cell_checks, seen = [], [], set()
    for cell in cells:
        key = tuple(cell[field] for field in ("anchor", "bias", "route"))
        if key in seen:
            raise ValueError(f"D4 duplicate input cell: {key}")
        seen.add(key)
        rows, checks = _cell_rows(cell)
        bins.extend(rows)
        cell_checks.append(checks)
    groups = {}
    for anchor, bias in sorted({(anchor, bias) for anchor, bias, _ in seen}):
        groups.setdefault(anchor, {})[bias] = {
            channel: _h3([row for row in bins if (row["anchor"], row["bias"], row["channel"]) == (anchor, bias, channel)])
            for channel in CHANNELS
        }
    return {"bins": bins, "H3": groups, "cell_checks": cell_checks}


def synthetic_checks():
    """Check exact bin boundaries, gate independence, H3 thresholds and gap handling."""
    n_per_bin = 30
    n = n_per_bin * len(DISTANCE_BINS)
    rho = np.repeat([0.0, 3.0, 6.0, 10.0], n_per_bin)
    epsilon = np.column_stack((np.repeat([0.51, 0.5, 0.0, 0.0], n_per_bin), np.zeros(n)))
    case = {
        "anchor": "B", "bias": "B0", "route": "R4", "t": np.arange(n) * 0.2,
        "pose_id": np.arange(n), "rho": rho, "epsilon": epsilon,
        "R_eff_diagonal": np.ones_like(epsilon), "mask": np.zeros(n, dtype=bool), "reference_metrics": {},
    }
    summary = analyze([case])
    first, boundary = [row for row in summary["bins"] if row["channel"] == "r"][:2]
    r, s = (summary["H3"]["B"]["B0"][channel] for channel in CHANNELS)
    if (first["n"] != n_per_bin or not np.isclose(first["signed_mean"], 0.51) or first["tau"] != 1.0
            or boundary["above_threshold"] or summary["cell_checks"][0]["finite_gate_rejected_included"] != n
            or r["status"] != "H3_SUPPORTED" or r["above_threshold_fraction"] != 0.25
            or s["status"] != "H3_NOT_SUPPORTED"):
        raise AssertionError("D4 aggregation boundary check failed")
    correlated = np.linspace(0.0, 1.0, 30)
    contiguous = _autocorrelation_time(correlated, np.arange(30))
    disjoint = _autocorrelation_time(correlated, 2 * np.arange(30))
    if contiguous[0] <= 1.0 or contiguous[2] != 29 or disjoint != (1.0, 0, 0, 30):
        raise AssertionError("D4 autocorrelation gap handling check failed")
    return {"exact_distance_edges": True, "gate_rejections_included": n, "strict_signed_mean_threshold": True,
            "exact_quarter_h3_pass": True, "contiguous_tau": contiguous[0], "disjoint_tau": disjoint[0]}
