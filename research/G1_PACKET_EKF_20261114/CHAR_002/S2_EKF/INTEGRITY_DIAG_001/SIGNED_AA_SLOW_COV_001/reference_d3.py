"""D3 residual decomposition and fixed-gate E0 oracle replay."""

import numpy as np


def motion_arcs(packet, trace):
    from replay_s2 import wrap

    increments = wrap(packet["gy"][1:] - trace["x"][:-1, 3] * packet["dt"][1:])
    prior_increments = wrap(trace["prior"][1:, 2] - trace["x"][:-1, 2])
    if not np.allclose(increments, prior_increments, atol=1e-12, rtol=0):
        raise ValueError("Pre-measurement yaw motion disagrees with frozen controls")
    arc = np.r_[0., np.cumsum(np.abs(packet["ds"][1:]))]
    yaw = np.r_[0., np.cumsum(np.abs(increments))]
    return arc, yaw


def decompose(eps, t, arc, yaw, config):
    coordinate = (t, arc, yaw)
    radii = (config["half_seconds"], config["half_distance_m"], np.deg2rad(config["half_yaw_deg"]))
    left = np.maximum.reduce([np.searchsorted(x, x - step - 1e-12, side="left")
                              for x, step in zip(coordinate, radii, strict=True)])
    right = np.minimum.reduce([np.searchsorted(x, x + step + 1e-12, side="right")
                               for x, step in zip(coordinate, radii, strict=True)])
    n = right - left
    support = n >= config["min_window_packets"]
    if not support.any():
        raise ValueError("D3 has no locally supported residual decomposition")
    route_mean = eps.mean(axis=0)
    centered = eps - route_mean
    accumulated = np.vstack([np.zeros(2), np.cumsum(centered, axis=0)])
    slow = np.zeros_like(eps)
    slow[support] = (accumulated[right[support]] - accumulated[left[support]]) / n[support, None]
    slow[support] -= slow[support].mean(axis=0)
    fast = np.where(support[:, None], centered - slow, 0.)
    error = float(np.max(np.abs(eps[support] - (route_mean + slow[support] + fast[support]))))
    if error > 1e-12 or np.max(np.abs(slow[support].mean(axis=0))) > 1e-12:
        raise ValueError("D3 decomposition reconstruction or centering failed")
    # The two raw window boundaries independently meet all three caps.
    for values, limit in zip(coordinate, radii, strict=True):
        if np.max(values - values[left]) > limit + 2e-12 or np.max(values[right-1] - values) > limit + 2e-12:
            raise ValueError("Window crosses a frozen cap")
    return dict(slow=slow, fast=fast, route_mean=route_mean, support=support, window_n=n,
                left=left, right=right, reconstruction_error=error)


def component_summary(eps, parts, use):
    if not use.any():
        return {"n": 0}
    slow, fast = parts["slow"][use], parts["fast"][use]
    ss = slow.var(axis=0)
    ff = fast.var(axis=0)
    cov_twice = 2. * np.mean((slow - slow.mean(axis=0)) * (fast - fast.mean(axis=0)), axis=0)
    total = eps[use].var(axis=0)
    if not np.allclose(ss + ff + cov_twice, total, atol=1e-12, rtol=1e-12):
        raise ValueError("D3 variance decomposition did not close")
    shares = np.divide(np.column_stack([ss, ff, cov_twice]), total[:, None],
                       out=np.zeros((2, 3)), where=total[:, None] > 0)
    return {"n": int(use.sum()), "var_total": total.tolist(), "var_slow": ss.tolist(), "var_fast": ff.tolist(),
            "two_cov_slow_fast": cov_twice.tolist(), "variance_fraction_slow_fast_crossterm": shares.tolist(),
            "raw_mean": eps[use].mean(axis=0).tolist(), "slow_mean": slow.mean(axis=0).tolist(),
            "fast_mean": fast.mean(axis=0).tolist()}


def observations(z, parts):
    groups = {"s": (1,), "r": (0,), "both": (0, 1)}
    support = parts["support"]
    edits = dict(slow=parts["slow"], fast=parts["fast"], constant=np.broadcast_to(parts["route_mean"], z.shape))
    names, variants = ["original"], [z]
    for component, delta in edits.items():
        for label, channels in groups.items():
            z_new = z.copy()
            sl = np.ix_(support, channels)
            z_new[sl] -= delta[sl]
            if not np.array_equal(z_new[~support], z[~support]):
                raise ValueError("Unsupported D3 packets changed")
            omitted = tuple(c for c in (0, 1) if c not in channels)
            if omitted and not np.array_equal(z_new[:, omitted], z[:, omitted]):
                raise ValueError("Unintervened D3 channel changed")
            names.append(f"{component}_{label}")
            variants.append(z_new)
    return names, np.stack(variants)


def compute_case(case, core, online, model, config, *, primary=False):
    from d0_d5 import compare
    from e0_batch import replay_batch
    from metrics_s2 import _summarize
    from replay_s2 import parity
    from verify_s2 import from_trace

    packet, trace = case["packet"], case["e0"]
    e = case["eps"]
    arc, yaw = motion_arcs(packet, trace)
    parts = decompose(e, packet["t"], arc, yaw, config)
    names, variants = observations(packet["z"], parts)
    mask = trace["mask"]
    result = replay_batch(core, online, model, case["spec"], packet, mask, variants)
    original_errors = parity({k: result[k][0] for k in ("x", "P")}, {k: trace[k] for k in ("x", "P")})
    rows = {key: from_trace({k: result[k][i] for k in ("x", "P")}, case["truth"])
            for i, key in enumerate(names)}
    summaries = {k: _summarize(v) for k, v in rows.items()}
    support = parts["support"]
    # D3 fixes the oracle subtraction itself; log excursions and a matched sensitivity.
    excursions = (variants[..., 0] <= 0.) | (np.abs(variants[..., 1]) > 1.)
    outside = {name: {"packets": int(bad.sum()), "accepted": int((bad & mask).sum())}
               for name, bad in zip(names, excursions, strict=True)}
    primary_ci = {}
    sensitivity = None
    if primary:
        for key in ("slow_s", "fast_s", "constant_s"):
            c = compare([{"time": packet["t"], "e0": rows["original"], "loro": rows[key]}])
            primary_ci[key] = c["moving_block_bootstrap_paired"]
        primary_names = ["slow_s", "fast_s", "constant_s"]
        joint_bad = excursions[[names.index(key) for key in primary_names]].any(axis=0)
        if (joint_bad & mask).any():
            corrected = variants[[names.index(key) for key in primary_names]].copy()
            corrected[:, joint_bad] = packet["z"][joint_bad]
            check = replay_batch(core, online, model, case["spec"], packet, mask, corrected)
            sensitivity = {"reverted_packets": int(joint_bad.sum()), "reverted_accepted": int((joint_bad & mask).sum()),
                           "scores": {key: _summarize(from_trace({k: check[k][i] for k in ("x", "P")}, case["truth"]))
                                      for i, key in enumerate(primary_names)}}
    report = {"n": len(e), "accepted": int(mask.sum()), "support_n": int(support.sum()),
              "accepted_support_n": int((support & mask).sum()), "support_fraction": float(support.mean()),
              "accepted_support_fraction": float(support[mask].mean()), "route_mean_r_s": parts["route_mean"].tolist(),
              "window_n_quantiles": np.quantile(parts["window_n"], [0., .25, .5, .75, 1.]).tolist(),
              "reconstruction_error": parts["reconstruction_error"],
              "variance_supported": component_summary(e, parts, support),
              "variance_supported_accepted": component_summary(e, parts, support & mask),
              "oracle_outside_physical_support": outside, "matched_physical_sensitivity": sensitivity,
              "original_parity": original_errors, "arms": summaries, "primary_paired_bootstrap": primary_ci}
    arrays = {**result, "arm_names": np.asarray(names), "t": packet["t"], "pose_id": packet["pose_id"], "mask": mask,
              "decomposition_support": support, "slow": parts["slow"], "fast": parts["fast"], "eps": e,
              "route_mean": parts["route_mean"], "window_n": parts["window_n"], "arc_m": arc, "yaw_arc_rad": yaw}
    return arrays, report


def priority(d2_results, d3_results, d1_results, target):
    primary = d3_results["by_cell"]["B_B0_R4"]
    slow = primary["arms"]["slow_s"]["heading95_coverage"]
    fast = primary["arms"]["fast_s"]["heading95_coverage"]
    picks = {True: "SC", False: "KI"}
    verdict = (picks[slow >= target] if (slow >= target) != (fast >= target) else
               "MIXED" if min(slow, fast) >= target else "INCONCLUSIVE")
    priority = verdict if d1_results["hypotheses"]["H1"] == "SUPPORTED" else "INCONCLUSIVE"
    physical = primary["matched_physical_sensitivity"]
    if physical and priority in picks.values():
        scores = physical["scores"]
        sensitivity_hits = [(scores[key]["heading95_coverage"] >= target) for key in ("slow_s", "fast_s")]
        if sensitivity_hits != [slow >= target, fast >= target]:
            priority = "INCONCLUSIVE_PHYSICAL_SENSITIVITY"
    return {"primary": "B_B0_R4 / heading95 / s channel", "recovery_target": target,
            "s_slow_removed_heading95": slow, "s_fast_removed_heading95": fast,
            "registered_d3_branch": verdict, "priority": priority,
            "h1_d1": d1_results["hypotheses"]["H1"], "h2_d2": d2_results["aggregate"]["H2_PRIMARY"],
            "h7_d2": d2_results["aggregate"]["H7_PRIMARY"],
            "scope": "diagnostic priority; candidate arms require separate validation"}
