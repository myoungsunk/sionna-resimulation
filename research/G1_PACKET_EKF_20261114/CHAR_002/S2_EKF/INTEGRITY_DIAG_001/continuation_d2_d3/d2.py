"""D2 diagnostic on frozen E0 traces. Each subset uses the same full prior."""

import numpy as np
from scipy.stats import spearmanr


DEFAULTS = {
    "window_seconds": 20., "min_accepted": 30, "lag_cap_seconds": 5.,
    "min_windows": 10, "min_windows_per_route": 2, "h2_supported": .70, "h2_rejected": .50,
    "h7_gain": .03, "d1_min_valid": 90, "transfer_zero_m": 1e-12, "parity_tolerance": 1e-10,
}
ROUTES = ("R2", "R4", "R5")
LEVELS = ("B_B0", "B_L2", "A_B0", "A_L2")


def _spread(values):
    if len(values) == 0:
        return None
    return dict(zip(("min", "p05", "median", "p95", "max"),
                    np.quantile(values, [0., .05, .50, .95, 1.]).tolist()))


def _rms(values):
    return float(np.sqrt(np.mean(np.sum(np.square(values), axis=-1))))


def _error(candidate, reference):
    return float(np.max(np.abs(candidate - reference) / np.maximum(1., np.abs(reference))))


def _subset_covariance(prior_covariance, jacobian, observation_covariance):
    hp = jacobian @ prior_covariance
    innovations = hp @ jacobian.swapaxes(-1, -2) + observation_covariance
    innovations = (innovations + innovations.swapaxes(-1, -2)) * .5
    gain = np.linalg.solve(innovations, hp).swapaxes(-1, -2)
    a = np.eye(4) - gain @ jacobian
    covariance = a @ prior_covariance @ a.swapaxes(-1, -2) + gain @ observation_covariance @ gain.swapaxes(-1, -2)
    return (covariance + covariance.swapaxes(-1, -2)) * .5, gain


def yaw_information(trace, tolerance):
    """Symmetric marginal-precision attribution from empty, r, s, and both subsets."""
    mask = trace["mask"]
    p, h, r = (trace[name][mask] for name in ("Pprior", "H", "Reff"))
    ir = np.linalg.inv(p)
    posterior = [p]
    checks = {}
    for name, subset in (("r", slice(0, 1)), ("s", slice(1, 2)), ("rs", slice(None))):
        hs, rs = h[:, subset, :], r[:, subset, subset]
        covariance, gain = _subset_covariance(p, hs, rs)
        independent = np.linalg.inv(ir + hs.swapaxes(-1, -2) @ np.linalg.solve(rs, hs))
        checks[f"{name}_information_form_max_normalized_error"] = _error(covariance, independent)
        posterior.append(covariance)
    checks["full_post_covariance_max_normalized_error"] = _error(posterior[-1], trace["P"][mask])
    checks["full_gain_max_normalized_error"] = _error(gain, trace["K"][mask])
    if not np.array_equal(trace["Pprior"][~mask], trace["P"][~mask]) or np.any(trace["K"][~mask] != 0.):
        raise ValueError("D2 rejected packet is not E0 predict-only")
    variances = np.column_stack([c[:, 2, 2] for c in posterior])
    if not np.isfinite(variances).all() or np.any(variances <= 0.):
        raise ValueError("D2 nonpositive heading variance")
    i0, i_r, i_s, i_rs = (1. / variances).T
    info_r = ((i_r - i0) + (i_rs - i_s)) * .5
    info_s = ((i_s - i0) + (i_rs - i_r)) * .5
    info = np.column_stack([info_r, info_s])
    for delta in (i_r-i0, i_s-i0, i_rs-i_r, i_rs-i_s):
        if np.min(delta / np.maximum(1., i_rs)) < -tolerance:
            raise ValueError("D2 conditional yaw precision decreased on adding a channel")
    checks["information_additivity_max_normalized_error"] = _error(info.sum(axis=1), i_rs-i0)
    if max(checks.values()) > tolerance:
        raise ValueError(f"D2 frozen E0 information checks failed: {checks}")
    # Excluded packets have no measured information increment and retain the prior variance.
    all_info = np.zeros((len(mask), 2))
    all_info[mask] = info
    all_variances = np.repeat(trace["Pprior"][:, 2, 2, None], 4, axis=1)
    all_variances[mask] = variances
    return all_info, all_variances, checks


def _autocorrelation_time(sample, time, cap_s=None):
    """Positive adjacent lag pairs, beginning with lags 1 and 2."""
    centered = sample - np.mean(sample)
    denominator = centered @ centered
    tau, last_lag = 1., 0
    if denominator <= 0.:
        return tau, last_lag
    for lag in range(1, len(sample)//2, 2):
        products = []
        for j in (lag, lag+1):
            pair_product = centered[:-j] * centered[j:]
            if cap_s is not None:
                valid = time[j:] - time[:-j] <= cap_s
                if valid.sum() < 2:
                    return tau, last_lag
                pair_product = pair_product[valid]
            products.append(float(np.sum(pair_product) / denominator))
        if sum(products) <= 0.:
            break
        tau += 2. * sum(products)
        last_lag = lag + 1
    return tau, last_lag


def _window_rows(t, mask, z2, normalized_noise, info, cfg):
    size = cfg["window_seconds"]
    complete = int(np.floor((t[-1] - t[0] + 1e-9) / size))
    rows = []
    for index in range(complete):
        lo, hi = t[0] + size * np.array([index, index+1])
        window = (lo <= t) & (t < hi)
        accepted = window & mask
        sums = info[accepted].sum(axis=0)
        row = {"window_index": index, "start_s": float(lo), "stop_s": float(hi),
               "packets": int(window.sum()), "accepted": int(accepted.sum()),
               "yaw_information_r_s_rad_inverse_square": sums.tolist()}
        if accepted.sum() < cfg["min_accepted"] or sums.sum() <= 0.:
            row["status"] = "LOW_ACCEPTANCE" if accepted.sum() < cfg["min_accepted"] else "NONPOSITIVE_MEASURED_INFORMATION"
            rows.append(row)
            continue
        kappa = sums / sums.sum()
        u = normalized_noise[accepted]
        variance, mean = u.var(axis=0), u.mean(axis=0)
        tau, lags = zip(*[_autocorrelation_time(u[:, c], t[accepted]) for c in (0, 1)])
        cap_tau, cap_lags = zip(*[_autocorrelation_time(u[:, c], t[accepted], cfg["lag_cap_seconds"]) for c in (0, 1)])
        adjusted = variance * tau
        capped = variance * cap_tau
        rows.append({**row, "status": "VALID", "kappa_r": float(kappa[0]), "kappa_s": float(kappa[1]),
                     "u_mean_r_s": mean.tolist(), "u_var_r_s": variance.tolist(),
                     "tau_r_s": list(tau), "tau_last_lag_r_s": list(lags), "tau_5s_r_s": list(cap_tau),
                     "tau_5s_last_lag_r_s": list(cap_lags), "tau_v_r_s": adjusted.tolist(),
                     "tau_5s_v_r_s": capped.tolist(), "accepted_spacing_s": _spread(np.diff(t[accepted])),
                     "z2": float(z2[window].mean()), "z2_accepted": float(z2[accepted].mean()),
                     "pred_kappa": float(1. + kappa @ (adjusted - 1.)),
                     "pred_r_only": float(adjusted[0]), "pred_equal": float(adjusted.mean()),
                     "pred_kappa_5s": float(1. + kappa @ (capped - 1.)),
                     "pred_r_only_5s": float(capped[0]), "pred_equal_5s": float(capped.mean())})
    return rows


def _propagation(packet, trace, truth, eps, core, online, tolerance):
    mask = trace["mask"]
    x, p = trace["x"], trace["P"]
    prior, h, k_gain = (trace[name] for name in ("prior", "H", "K"))
    gain_s = k_gain[:, :, 1]
    raw = np.where(mask, eps[:, 1], 0.)
    mean = float(raw[mask].mean())
    centered, unit = np.where(mask, raw - mean, 0.), mask.astype(float)
    inputs = np.column_stack([raw, centered, unit])
    direct = gain_s[:, :, None] * inputs[:, None, :]
    f = np.broadcast_to(np.eye(4), (len(x), 4, 4)).copy()
    transition_error = max(_error(prior[0], packet["x0"]), _error(trace["Pprior"][0], packet["P0"]))
    for i in range(1, len(x)):
        state, f[i], _ = core.transition(x[i-1], packet["ds"][i], packet["gy"][i], packet["dt"][i])
        predicted, predicted_cov = online.predict(core, x[i-1], p[i-1], i, packet)
        transition_error = max(transition_error, _error(state, prior[i]), _error(predicted, prior[i]),
                               _error(predicted_cov, trace["Pprior"][i]))
    a = (np.eye(4) - k_gain @ h) @ f
    response = np.empty_like(direct)
    incremental = np.zeros((4, 3))
    for i, (step_jacobian, immediate) in enumerate(zip(a, direct)):
        incremental = step_jacobian @ incremental + immediate
        response[i] = incremental
    superposition_error = _error(response[:, :, 0], response[:, :, 1] + mean * response[:, :, 2])
    if transition_error > tolerance or superposition_error > tolerance or not np.isfinite(response).all():
        raise ValueError("D2 native transition parity or fixed-linear superposition failed")
    error_xy = x[:, :2] - truth[:, :2]
    local = response[:, :2, 1]
    norm_sensitivity = np.linalg.norm(gain_s[mask, :2], axis=1)
    error_scale = np.linalg.norm(error_xy) * np.linalg.norm(local)
    summary = {"s_accepted_raw_mean": mean, "s_accepted_raw_rms": float(np.sqrt(np.mean(raw[mask]**2))),
               "K_xy_s_norm_m_per_unit": _spread(norm_sensitivity),
               "H_s_xy_norm_unit_per_m": _spread(np.linalg.norm(h[mask, 1, :2], axis=1)),
               "H_s_abs_yaw_unit_per_rad": _spread(np.abs(h[mask, 1, 2])),
               "direct_centered_xy_rms_cm": 100*_rms(direct[:, :2, 1]), "centered_xy_rms_cm": 100*_rms(local),
               "centered_xy_peak_m": float(np.linalg.norm(local, axis=1).max()),
               "lagged_centered_xy_rms_cm": 100*_rms(local-direct[:, :2, 1]),
               "raw_xy_rms_cm": 100*_rms(response[:, :2, 0]),
               "unit_step_xy_rms_m_per_unit": _rms(response[:, :2, 2]),
               "centered_heading_rms_deg": float(np.rad2deg(np.sqrt(np.mean(response[:, 2, 1]**2)))),
               "baseline_xy_rmse_cm": 100*_rms(error_xy), "baseline_minus_local_xy_rmse_cm": 100*_rms(error_xy-local),
               "local_xy_error_vector_cosine": float(np.sum(error_xy*local)/error_scale) if error_scale > 0. else None,
               "transition_max_normalized_error": transition_error, "superposition_max_normalized_error": superposition_error}
    arrays = {"F": f, "A": a, "s_input_raw_centered_unit": inputs, "s_direct_raw_centered_unit": direct,
              "s_response_raw_centered_unit": response, "K_xy_s": gain_s[:, :2]}
    return arrays, summary


def compute_case(packet, truth, d0_trace, eps, core, online, config=None):
    """Return full-grid diagnostic arrays and case/window summaries."""
    cfg = DEFAULTS | (config or {})
    t, mask = np.asarray(packet["t"]), d0_trace["mask"]
    if len(t) == 0 or abs(t[-1]-t[0]) <= 0. or np.any(np.diff(t) <= 0.) or not mask.any():
        raise ValueError("D2 invalid time support or E0 acceptance mask")
    if not np.array_equal(d0_trace["t"], t) or not np.array_equal(d0_trace["pose_id"], packet["pose_id"]):
        raise ValueError("D2 trace and online packet grid differ")
    info, variances, checks = yaw_information(d0_trace, cfg["parity_tolerance"])
    reff = np.diagonal(d0_trace["Reff"], axis1=-2, axis2=-1)
    normalized = eps / np.sqrt(reff)
    yaw = (d0_trace["x"][:, 2] - truth[:, 2] + np.pi) % (2.*np.pi) - np.pi
    z2 = yaw**2 / d0_trace["P"][:, 2, 2]
    h, p = d0_trace["H"], d0_trace["Pprior"]
    hph = np.einsum("nci,nij,ncj->nc", h, p, h)
    geometric = np.divide(h[:, :, 2]**2 * p[:, 2, 2, None], hph, out=np.zeros_like(hph), where=hph > 0.)
    ratios = [_spread(geometric[mask & (hph[:, c] > 0.), c]) for c in (0, 1)]
    cross = {name: {"P_xy_yaw": [_spread(cov[mask, i, 2]) for i in (0, 1)],
                    "corr_xy_yaw": [_spread((cov[:, i, 2] / np.sqrt(cov[:, i, i]*cov[:, 2, 2]))[mask]) for i in (0, 1)]}
             for name, cov in (("prior", p), ("posterior", d0_trace["P"]))}
    motion, transfer = _propagation(packet, d0_trace, truth, eps, core, online, cfg["parity_tolerance"])
    windows = _window_rows(t, mask, z2, normalized, info, cfg)
    info_sum = info.sum(axis=0)
    expected_arrays = {"t": t, "pose_id": packet["pose_id"], "mask": mask, "z2": z2,
                       "truth_residual_r_s": eps, "standardized_truth_residual_r_s": normalized,
                       "yaw_variance_empty_r_s_rs": variances, "yaw_information_r_s": info,
                       "H_P_Ht_diagonal_r_s": hph, "geometric_heading_ratio_r_s": geometric,
                       "Pprior_xy_yaw": p[:, :2, 2], "Ppost_xy_yaw": d0_trace["P"][:, :2, 2], **motion}
    if not all(np.isfinite(a).all() for a in expected_arrays.values()):
        raise ValueError("D2 nonfinite per-packet diagnostic")
    summary = {"packets": len(t), "accepted": int(mask.sum()), "duration_s": float(t[-1]-t[0]),
               "complete_windows": len(windows), "valid_windows": sum(row["status"] == "VALID" for row in windows),
               "windows": windows, "mean_z2": float(z2.mean()), "mean_z2_accepted": float(z2[mask].mean()),
               "kappa_s_total": float(info_sum[1]/info_sum.sum()) if info_sum.sum() > 0. else None,
               "yaw_information_total_r_s_rad_inverse_square": info_sum.tolist(),
               "geometric_heading_ratio_r_s": ratios, "geometric_ratio_undefined_r_s": (hph[mask] <= 0.).sum(axis=0).tolist(),
               "xy_yaw_cross_covariance": cross, "h7_transfer": transfer, "checks": checks}
    return expected_arrays, summary


def _spearman(rows, truth_key="z2"):
    scores = {}
    for field in ("pred_kappa", "pred_r_only", "pred_equal", "pred_kappa_5s", "pred_r_only_5s", "pred_equal_5s"):
        x, y = [row[field] for row in rows], [row[truth_key] for row in rows]
        scores[field] = float(spearmanr(x, y).statistic) if len(x) >= 3 and len(set(x)) > 1 and len(set(y)) > 1 else None
    return scores


def aggregate(cases, d1_r4_xy_gain, d1_valid_reps, config=None):
    cfg = DEFAULTS | (config or {})
    grouped = {}
    for level in LEVELS:
        rows_by_route = {route: [row for row in cases[f"{level}_{route}"]["windows"] if row["status"] == "VALID"]
                         for route in ROUTES}
        rows = [row for per_route in rows_by_route.values() for row in per_route]
        corr = _spearman(rows)
        score = corr["pred_kappa"]
        enough = len(rows) >= cfg["min_windows"] and all(len(v) >= cfg["min_windows_per_route"] for v in rows_by_route.values())
        verdict = "INCONCLUSIVE"
        if enough and score is not None:
            if score >= cfg["h2_supported"]:
                verdict = "SUPPORTED"
            elif score < cfg["h2_rejected"]:
                verdict = "PREDICTION_REJECTED"
        comparable = [corr[k] for k in ("pred_r_only", "pred_equal") if corr[k] is not None]
        grouped[level] = {"valid_windows": len(rows), "enough_for_primary_threshold": enough,
                          "valid_windows_by_route": {r: len(w) for r, w in rows_by_route.items()},
                          "spearman": corr, "spearman_accepted_only_z2": _spearman(rows, truth_key="z2_accepted"),
                          "leave_one_route_out": {omit: _spearman([row for r, sub in rows_by_route.items() if r != omit for row in sub])
                                                  for omit in ROUTES},
                          "h2_prediction_verdict": verdict,
                          "kappa_additional_explanation": ("SUPPORTED" if verdict == "SUPPORTED" and comparable and score > max(comparable)
                                                           else "HELD_OPEN")}
    r4 = cases["B_B0_R4"]["h7_transfer"]
    transfer = r4["centered_xy_peak_m"] > cfg["transfer_zero_m"]
    h7 = "INCONCLUSIVE"
    if d1_valid_reps >= cfg["d1_min_valid"] and d1_r4_xy_gain is not None:
        h7 = "SUPPORTED_LOCAL_TRANSFER" if d1_r4_xy_gain >= cfg["h7_gain"] and transfer else "NOT_SUPPORTED_BY_JOINT_RULE"
    return {"H2_PRIMARY": grouped["B_B0"]["h2_prediction_verdict"], "H2_BY_LEVEL": grouped,
            "H7_PRIMARY": h7, "H7_B_B0_R4": {"d1_s_only_xy95_gain": d1_r4_xy_gain, "d1_valid_reps": d1_valid_reps,
                                             "measured_centered_s_to_xy_transfer_detected": transfer, **r4}}
