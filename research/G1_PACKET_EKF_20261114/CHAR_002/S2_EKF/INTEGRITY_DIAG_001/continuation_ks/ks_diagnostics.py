"""Trace diagnostics and fixed-packet scoring for G1-INT-001/KS-TRANSFER."""

import numpy as np


BLOCKS = (5, 10, 20, 30)
BOOTSTRAP_REPS = 1500
BOOTSTRAP_SEED = 20261115
COVERAGE = ("pose95_coverage", "xy95_coverage", "heading95_coverage")
RMSE = ("heading_rmse_deg", "xy_rmse_cm")
WINDOW = dict(half_seconds=5., half_distance_m=.25, half_yaw_deg=5., min_window_packets=10)


def interval(draws):
    return np.quantile(draws, [.025, .975], axis=0).tolist()


def boot_indices(times, seconds, rng):
    from metrics_s2 import _moving_block_indices

    duration = times[-1] - times[0] + np.median(np.diff(times))
    full_blocks = int(np.floor((duration + 1e-12) / seconds))
    return _moving_block_indices(times, seconds, BOOTSTRAP_REPS, rng), full_blocks


def scores_with_blocks(rows, times, contrasts, blocks=BLOCKS):
    """Retain the complete grid and use one resample across the arms of each route."""
    from metrics_s2 import METRICS, _reduce, _summarize

    routes = tuple(rows)
    arms = tuple(rows[routes[0]])
    if any(tuple(by_arm) != arms or any(len(value) != len(times[route]) for value in by_arm.values())
           for route, by_arm in rows.items()):
        raise ValueError("Different score grids within a bootstrap comparison")
    point = {route: {arm: _summarize(rows[route][arm]) for arm in arms} for route in routes}
    result = {"point": point, "blocks": {}}
    if len(routes) > 1:
        point["pooled"] = {arm: _summarize(np.concatenate([rows[route][arm] for route in routes])) for arm in arms}
    for seconds in blocks:
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        sums, groups, counts = {}, {}, {}
        for route in routes:
            index, counts[route] = boot_indices(times[route], seconds, rng)
            sums[route] = {arm: np.column_stack([col[index].sum(axis=1) for col in value.T])
                           for arm, value in rows[route].items()}
            groups[route] = _bootstrap_summary(sums[route], len(times[route]), contrasts, counts[route] < 8)
        if len(routes) > 1:
            pooled = {arm: sum(sums[route][arm] for route in routes) for arm in arms}
            groups["pooled"] = _bootstrap_summary(pooled, sum(map(len, times.values())), contrasts, min(counts.values()) < 8)
        result["blocks"][str(seconds)] = dict(full_blocks=counts, by_group=groups)
    return result


def _bootstrap_summary(sums, n, contrasts, reference_only):
    from metrics_s2 import METRICS, _reduce

    samples = {arm: _reduce(value / n) for arm, value in sums.items()}
    columns = lambda x: dict(zip(METRICS, np.asarray(interval(x)).T.tolist(), strict=True))
    return {"reference_only": bool(reference_only),
            "absolute_ci95": {arm: columns(value) for arm, value in samples.items()},
            "paired_ci95": {f"{arm}-{ref}": columns(samples[arm] - samples[ref]) for arm, ref in contrasts}}


def v3_status(scores, arm, supported):
    point = scores["point"]["R4"]
    baseline = point["LORO"]
    assessment = scores["blocks"]["10"]["by_group"]["R4"]
    lo, hi = assessment["absolute_ci95"][arm]["heading95_coverage"]
    ratios = {name: point[arm][name] / baseline[name] for name in RMSE}
    if supported == 0:
        state = "NOT_EVALUABLE"
    elif assessment["reference_only"] or lo <= .75 <= hi:
        state = "INCONCLUSIVE"
    elif lo > .75 and point[arm]["heading95_coverage"] >= .75 and max(ratios.values()) <= 1.25:
        state = "PASS"
    else:
        state = "FAIL"
    return dict(status=state, heading95_ci95=[lo, hi], rmse_ratios=ratios, supported_accepted=int(supported))


def v4(cases, core, online, out):
    from d2 import _propagation
    from d3 import decompose, motion_arcs
    from replay_s2 import wrap

    results = {}
    for route, case in cases.items():
        packet, trace, eps, truth = (case[key] for key in ("packet", "e0", "eps", "truth"))
        arc, yaw = motion_arcs(packet, trace)
        parts = decompose(eps, packet["t"], arc, yaw, WINDOW)
        use = parts["support"]
        common = use & trace["mask"]
        arrays, checks = _propagation(packet, trace, truth, eps, core, online, 1e-10)
        channels = np.column_stack([eps[:, 1], parts["slow"][:, 1], parts["fast"][:, 1],
                                    np.where(use, parts["route_mean"][1], 0.),
                                    np.where(use, eps[:, 1], 0.)])
        a = np.zeros((4, channels.shape[1]))
        response = np.empty((len(eps), channels.shape[1]))
        for i, A in enumerate(arrays["A"]):
            a = A @ a + trace["K"][i, :, 1, None] * channels[i]
            response[i] = a[2]
        error = wrap(trace["x"][:, 2] - truth[:, 2])
        var = trace["P"][:, 2, 2]
        reuse_error = float(np.max(np.abs(response[:, 0] - arrays["s_response_raw_centered_unit"][:, 2, 0])))
        decomposition_error = float(np.max(np.abs(response[:, 1:4].sum(axis=1) - response[:, 4])))
        if max(reuse_error, decomposition_error) > 1e-12:
            raise ValueError("V4 fixed trace response failed parity or superposition")
        indices, _ = boot_indices(packet["t"], 10, np.random.default_rng(BOOTSTRAP_SEED))
        groups = {}
        for i, name in enumerate(("raw", "slow", "fast", "supported_constant", "supported_raw")):
            x, y = response[common, i], error[common]
            corr = _correlation(x, y)
            samples = [_correlation(response[j, i], error[j]) for row in indices if len(j := row[common[row]]) > 2]
            samples = [x for x in samples if x is not None]
            groups[name] = dict(correlation=corr, correlation_ci95=interval(samples) if samples else None,
                                response_mean_deg=float(np.rad2deg(x.mean())), error_mean_deg=float(np.rad2deg(y.mean())),
                                variance_ratio=float(x.var() / var[common].mean()))
        corr = groups["slow"]["correlation"]
        results[route] = dict(n=int(common.sum()), groups=groups, trace="original E0",
                              transition_error=checks["transition_max_normalized_error"],
                              response_parity=reuse_error, superposition_error=decomposition_error,
                              status=("SUPPORTED" if corr is not None and corr >= .80 else "NOT_SUPPORTED") if route == "R4" else "REFERENCE")
        np.savez_compressed(out / f"V4_{route}.npz", t=packet["t"], pose_id=packet["pose_id"], support=common,
                            response=response, heading_error=error, heading_variance=var)
    return results


def _correlation(x, y):
    x = x - x.mean()
    y = y - y.mean()
    scale = np.linalg.norm(x) * np.linalg.norm(y)
    return float(np.dot(x, y) / scale) if scale > 0 else None


def v5(case, core, online, model, out):
    from d3 import decompose, motion_arcs, observations
    from e0_batch import replay_batch
    from metrics_s2 import _summarize
    from replay_s2 import parity
    from verify_s2 import from_trace

    packet, trace = case["packet"], case["e0"]
    arc, yaw = motion_arcs(packet, trace)
    parts, support_by_width = {}, {}
    for width in (.25, .5, 1.):
        key = str(width)
        try:
            part = decompose(case["eps"], packet["t"], arc, yaw, WINDOW | {"half_distance_m": width / 2})
        except ValueError as exc:
            if str(exc) != "D3 has no locally supported residual decomposition":
                raise
            support_by_width[key] = np.zeros(len(arc), dtype=bool)
        else:
            parts[key] = part
            support_by_width[key] = part["support"]
    common = np.logical_and.reduce(list(support_by_width.values()))
    left = [("original", packet["z"])]
    for width, part in parts.items():
        names, variants = observations(packet["z"], part)
        left.extend((f"{width}_{name}", variants[names.index(name)]) for name in ("slow_s", "fast_s"))
    result = replay_batch(core, online, model, case["spec"], packet, trace["mask"], np.stack([z for _, z in left]))
    checks = parity({k: result[k][0] for k in ("x", "P")}, {k: trace[k] for k in ("x", "P")})
    rows = {name: from_trace({k: result[k][i] for k in ("x", "P")}, case["truth"])
            for i, (name, _) in enumerate(left)}
    summary = {width: dict(status="INCONCLUSIVE", support_n=0, reason="NO_D3_WINDOW_WITH_MIN_PACKET_SUPPORT")
               for width in support_by_width if width not in parts}
    base = rows["original"]
    for width, part in parts.items():
        support = part["support"]
        selections = {"full_grid": np.ones(len(support), dtype=bool), "own_support": support,
                      "common_support": common, "own_support_accepted": support & trace["mask"]}
        summary[width] = {name: {mode: _summarize(row[selection]) for mode, selection in selections.items()}
                          for name, row in [("original", base)] + [(arm, rows[f"{width}_{arm}"]) for arm in ("slow_s", "fast_s")]}
        summary[width].update(status="REPLAYED", support_n=int(support.sum()))
        summary[width]["physical_outside_accepted"] = {
            arm: int(((np.abs(dict(left)[f"{width}_{arm}"][:, 1]) > 1.) & trace["mask"]).sum())
            for arm in ("slow_s", "fast_s")}
    heading = summary["0.5"]["slow_s"]["own_support"]["heading95_coverage"] if "0.5" in parts else None
    np.savez_compressed(out / "V5_R4.npz", **{name: row for name, row in rows.items()}, t=packet["t"],
                        **{f"support_{width}": support for width, support in support_by_width.items()})
    return dict(parity=checks, windows=summary, primary_heading95=heading,
                status="INCONCLUSIVE" if heading is None else ("RECOVERED" if heading >= .90 else "NOT_RECOVERED"))


def v6(frozen):
    result = {}
    for key, cell in frozen["by_cell"].items():
        arms = {name: cell["arms"][name] for name in ("original", "slow_r", "slow_s", "slow_both")}
        deltas = {metric: [arms["slow_r"][metric] - arms["original"][metric],
                           arms["slow_both"][metric] - arms["slow_s"][metric]] for metric in COVERAGE}
        result[key] = dict(arms=arms, delta_range_only_and_increment=deltas)
    delta = result["B_B0_R4"]["delta_range_only_and_increment"]["xy95_coverage"]
    return dict(cells=result, r4_single_channel_supports_leaving_range_fixed=bool(delta[0] < .05),
                r4_incremental_range_effect=bool(delta[1] >= .05))


def v7(cases, out):
    result = {}
    for bias in ("B0", "L2"):
        for route in ("R2", "R4", "R5"):
            a, b = (cases[f"{anchor}_{bias}_{route}"] for anchor in ("A", "B"))
            for field in ("t", "pose_id"):
                if not np.array_equal(a["packet"][field], b["packet"][field]):
                    raise ValueError(f"V7 anchor grid mismatch: {bias} {route} {field}")
            use = a["e0"]["mask"] & b["e0"]["mask"]
            time = a["packet"]["t"]
            indices, blocks = boot_indices(time, 10, np.random.default_rng(BOOTSTRAP_SEED))
            channels = {}
            for name, channel in (("s_heading", 1), ("r_ray", 0)):
                values, draws = {}, {}
                for anchor, case in (("A", a), ("B", b)):
                    trace = case["e0"]
                    H = trace["H"][:, channel]
                    if channel == 1:
                        sensitivity = H[:, 2]
                    else:
                        ray = trace["prior"][:, :2] - np.asarray(case["spec"]["anchor"][:2])
                        norm = np.linalg.norm(ray, axis=1)
                        if (norm[use] <= 0).any():
                            raise ValueError("V7 anchor ray undefined")
                        sensitivity = np.divide(np.sum(H[:, :2] * ray, axis=1), norm, out=np.zeros_like(norm), where=norm > 0)
                    R = trace["Reff"][:, channel, channel]
                    numerator = np.where(use, sensitivity * case["eps"][:, channel] / R, 0.)
                    denom = np.where(use, np.abs(sensitivity) / np.sqrt(R), 0.)
                    den_sum = denom[indices].sum(axis=1)
                    if denom.sum() <= 0 or (den_sum <= 0).any():
                        raise ValueError("V7 unsupported information-weight normalization")
                    values[anchor] = float(numerator.sum() / denom.sum())
                    draws[anchor] = numerator[indices].sum(axis=1) / den_sum
                bounds = {anchor: interval(draw) for anchor, draw in draws.items()}
                blo, bhi = bounds["B"]
                ref_only = blocks < 8
                ratio = abs(values["A"] / values["B"]) if not (blo <= 0 <= bhi) and not ref_only else None
                channels[name] = dict(weighted_signed=values, ci95=bounds, ratio_A_over_B=ratio,
                                      paired_diff_ci95=interval(draws["A"] - draws["B"]),
                                      paired_abs_A_minus_twice_B_ci95=interval(np.abs(draws["A"]) - 2 * np.abs(draws["B"])),
                                      status="INCONCLUSIVE" if ratio is None else ("SUPPORTED" if ratio >= 2 else "NOT_SUPPORTED"))
            result[f"{bias}_{route}"] = dict(n=int(use.sum()), complete_10s_blocks=blocks, channels=channels)
    return result


def shadow_gate(case, threshold, core, online, model):
    packet, spec, control = (case[name] for name in ("packet", "spec", "controls"))
    x, P = packet["x0"].copy(), packet["P0"].copy()
    mask = np.zeros(len(packet["t"]), dtype=bool)
    nis = np.empty(len(mask))
    for i in range(len(mask)):
        prior, cov = online.predict(core, x, P, i, control)
        obs, H = (field[0] for field in model.batch(prior[None], spec))
        residual = packet["z"][i] - obs - packet["muBASE"][i]
        R = packet["R"][i]
        S = H @ cov @ H.T + R
        nis[i] = residual @ np.linalg.solve(S, residual)
        mask[i] = bool(nis[i] <= threshold)
        x, P, _, _ = online.joseph(prior, cov, H, residual, R, mask[i], 1.)
    return mask, nis


def d6(cases, route_cases, core, online, model, out):
    from d0_d5 import replay_sigma
    from replay_s2 import parity
    from verify_s2 import from_trace

    rows, times, diagnostics, exclusions = {}, {}, {}, {}
    arms = ("E0", "LORO")
    names = {"native": float(online.GATE), "13.8": 13.8, "all_valid": float("inf")}
    for route, ka in route_cases.items():
        case = cases[route]
        packet = case["packet"]
        ref, truth = case["e0"], case["truth"]
        ref_mask = ref["mask"]
        rows[route], diagnostics[route], times[route] = {}, {}, packet["t"]
        normalized = case["eps"] / np.sqrt(np.diagonal(packet["R"], axis1=1, axis2=2))
        for name, threshold in names.items():
            mask, nis = shadow_gate(case, threshold, core, online, model)
            if not np.isfinite(nis).all() or (name == "all_valid" and not mask.all()):
                raise ValueError("D6 shadow valid-packet gate failed")
            e0 = online.replay(packet, case["controls"], "W0", core, model, case["spec"], fixed_mask=mask)
            loro = replay_sigma(packet, case["controls"], mask, core, online, model, case["spec"], ka["table"])
            checks = {}
            if name == "native":
                for label, trial, expected in (("E0", e0, ref), ("LORO", loro, ka["loro"])):
                    keys = ("x", "P", "prior", "Pprior", "H", "K", "Reff", "nu", "S", "mask")
                    checks[label] = parity(trial, {key: expected[key] for key in keys})
            groups = {"common_accepted": mask & ref_mask, "additional_accepted": mask & ~ref_mask,
                      "additional_rejected": ~mask & ref_mask, "common_rejected": ~mask & ~ref_mask}
            t = packet["t"]
            diagnostics[route][name] = dict(
                accepted=int(mask.sum()), changed=int((mask != ref_mask).sum()), baseline_parity=checks,
                longest_gap_s=float(np.diff(np.r_[t[0], t[mask], t[-1]]).max()),
                groups={key: dict(n=int(sel.sum()),
                                  normalized_residual_mean=normalized[sel].mean(axis=0).tolist() if sel.any() else None,
                                  normalized_residual_rms=np.sqrt((normalized[sel] ** 2).mean(axis=0)).tolist() if sel.any() else None,
                                  shadow_NIS_median=float(np.median(nis[sel])) if sel.any() else None)
                        for key, sel in groups.items()})
            for label, trace in zip(arms, (e0, loro), strict=True):
                rows[route][f"{label}_{name}"] = from_trace(trace, truth)
            np.savez_compressed(out / f"D6_{route}_{name}.npz", t=t, pose_id=packet["pose_id"], mask=mask, nis=nis,
                                standardized_residual=normalized, E0=rows[route][f"E0_{name}"], LORO=rows[route][f"LORO_{name}"])
    pairs = [(f"{arm}_{name}", f"{arm}_native") for arm in arms for name in ("13.8", "all_valid")]
    scores = scores_with_blocks(rows, times, pairs, (5, 10))
    for group, point in scores["point"].items():
        exclusions[group] = {}
        for arm, ref in pairs:
            delta = {key: point[arm][key] - point[ref][key] for key in COVERAGE}
            ci = {str(block): {key: scores["blocks"][str(block)]["by_group"][group]["paired_ci95"][f"{arm}-{ref}"][key]
                               for key in COVERAGE} for block in (5, 10)}
            good = all(abs(x) < .03 for x in delta.values()) and all(
                -.03 < lim[0] <= lim[1] < .03 for metrics in ci.values() for lim in metrics.values())
            exclusions[group][arm] = dict(delta=delta, ci95=ci, satisfies_equivalence=bool(good))
    status = all(row["satisfies_equivalence"] for group in exclusions.values() for row in group.values())
    return dict(status="H5_PRACTICALLY_EXCLUDED" if status else "H5_NOT_EXCLUDED",
                mask_diagnostics=diagnostics, comparisons=exclusions, scores=scores)
