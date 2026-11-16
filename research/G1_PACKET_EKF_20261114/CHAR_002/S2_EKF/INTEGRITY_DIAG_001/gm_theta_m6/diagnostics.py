"""M6 evaluator-only passage and correlation diagnostics."""

import numpy as np


def heading_error(trace, truth):
    error = trace["x"][:, 2] - truth[:, 2]
    return np.rad2deg((error + np.pi) % (2 * np.pi) - np.pi)


def passage_budget(case, trace):
    from exposure_score import branch_metrics

    truth, t = case["truth"], case["packet"]["t"]
    h = trace.get("H_aug", trace["H"])
    gain = trace.get("K_aug", trace["K"])
    r = trace["Reff"]
    l = np.linalg.cholesky(r)
    h_white = np.linalg.solve(l, h)
    innovation_white = np.linalg.solve(l, trace["nu"][..., None])[..., 0]
    gain_white = gain @ l
    update = gain_white * innovation_white[:, None, :]
    np.testing.assert_allclose(update.sum(axis=-1), (gain @ trace["nu"][..., None])[..., 0],
                               atol=1e-12, rtol=1e-12)
    yy = h_white[:, :, 1] ** 2
    psipsi = h_white[:, :, 2] ** 2
    ypsi = h_white[:, :, 1] * h_white[:, :, 2]
    err = trace["x"][:, 1] - truth[:, 1]
    pre_err = trace["prior"][:, 1] - truth[:, 1]
    sd = np.sqrt(trace["P"][:, 1, 1])
    heading = heading_error(trace, truth)
    branch = branch_metrics(trace, truth, t)
    branch.update(channel_order=["range", "range-conditional polarization"], windows=[])
    for passage in branch["passages"]:
        center = passage["time_s"]
        use = abs(t - center) <= 10.
        accepted = use & trace["mask"]
        near_after = use & (t >= center)
        first_opposite = t[near_after & (trace["x"][:, 1] * truth[:, 1] < 0.) & (abs(truth[:, 1]) >= .2)]
        first_increase = t[use & (abs(err) > abs(pre_err) + 1e-12)]
        row = dict(crossing_s=center, packets=int(use.sum()), accepted=int(accepted.sum()),
                   accepted_fraction=float(accepted.sum() / use.sum()),
                   J_yy=yy[accepted].sum(axis=0).tolist(), J_psipsi=psipsi[accepted].sum(axis=0).tolist(),
                   J_ypsi=ypsi[accepted].sum(axis=0).tolist(),
                   y_update_sum_m=update[use, 1, :].sum(axis=0).tolist(),
                   y_update_abs_sum_m=abs(update[use, 1, :]).sum(axis=0).tolist(),
                   psi_update_sum_rad=update[use, 2, :].sum(axis=0).tolist(),
                   psi_update_abs_sum_rad=abs(update[use, 2, :]).sum(axis=0).tolist(),
                   mean_Pyy=float(np.mean(trace["P"][use, 1, 1])),
                   mean_Pypsi=float(np.mean(trace["P"][use, 1, 2])),
                   first_opposite_s=None if not len(first_opposite) else float(first_opposite[0]),
                   first_update_increasing_abs_y_error_s=None if not len(first_increase) else float(first_increase[0]),
                   increase_precedes_opposite=None if not (len(first_opposite) and len(first_increase))
                   else bool(first_increase[0] < first_opposite[0]),
                   window_y_rmse_m=float(np.sqrt(np.mean(err[use] ** 2))),
                   window_heading_rmse_deg=float(np.sqrt(np.mean(heading[use] ** 2))),
                   series={key: value[use].tolist() for key, value in dict(
                       t=t, accepted=trace["mask"], y_truth=truth[:, 1], y_error=err, y_prior_error=pre_err,
                       heading_error_deg=heading, sd_y=sd, Pyy=trace["P"][:, 1, 1], Pypsi=trace["P"][:, 1, 2],
                       J_yy=yy, J_psipsi=psipsi, J_ypsi=ypsi, update_by_channel=update[:, 1:3],
                       **({"b_theta_cross_cov": trace["P_aug"][:, :4, 4], "H_aug": h, "K_aug": gain,
                           "S_aug": trace["S"]} if h.shape[-1] == 5 else {})
                   ).items()})
        branch["windows"].append(row)
    return branch


def passage_comparison(case, g0, a2):
    from ks_diagnostics import scores_with_blocks
    from verify_s2 import from_trace

    truth, t = case["truth"], case["packet"]["t"]
    base, candidate = (passage_budget(case, trace) for trace in (g0, a2))
    rows = []
    for base_pass, base_window, a2_pass, a2_window in zip(
        base["passages"], base["windows"], candidate["passages"], candidate["windows"], strict=True,
    ):
        crossing = base_pass["time_s"]
        i = abs(t - crossing) <= 10.
        pre = crossing - 5.
        paired = scores_with_blocks(
            {"route": {"A0": from_trace(g0, truth)[i], "A2_2": from_trace(a2, truth)[i]}},
            {"route": t[i]}, [("A2_2", "A0")], blocks=(10,),
        )
        rows.append(dict(
            crossing_s=crossing, truth_y_at_crossing_m=float(np.interp(crossing, t, truth[:, 1])),
            reference_only_window_bootstrap=paired["blocks"]["10"]["by_group"]["route"],
            A0=dict(window=base_window, passage=base_pass,
                    sd_y_5s_before_m=None if pre < t[0] else float(np.interp(pre, t, np.sqrt(g0["P"][:, 1, 1])))),
            A2_2=dict(window=a2_window, passage=a2_pass,
                      sd_y_5s_before_m=None if pre < t[0] else float(np.interp(pre, t, np.sqrt(a2["P"][:, 1, 1])))),
        ))
    return rows


def variogram(data):
    """Report empirical semivariance and the frozen kernel on the same pairs."""
    result = {}
    edges = {"arc_m": (0, .05, .1, .25, .5, 1, 2, 4, 8),
             "yaw_deg": (0, 2, 5, 10, 20, 45, 90, 180),
             "time_s": (0, .4, 1, 2, 5, 10, 20, 40)}
    for route, row in data.items():
        take = np.flatnonzero(row["mask"])
        i, j = np.triu_indices(take.size, k=1)
        i, j = take[i], take[j]
        arc = row["arc"][j] - row["arc"][i]
        angle = row["yaw_arc"][j] - row["yaw_arc"][i]
        dt = row["t"][j] - row["t"][i]
        semivar = .5 * (row["raw_s"][j] - row["raw_s"][i]) ** 2
        kernel_semivar = 1. - np.exp(-arc - angle / np.deg2rad(10))
        result[route] = {}
        for name, spacing in zip(edges, (arc, np.rad2deg(angle), dt), strict=True):
            bins = []
            for lo, hi in zip(edges[name][:-1], edges[name][1:], strict=True):
                sub = (spacing >= lo) & (spacing < hi)
                bins.append(dict(bounds=[lo, hi], pairs=int(sub.sum()),
                                 empirical_s2=float(semivar[sub].mean()) if sub.any() else None,
                                 frozen_unit_sill=float(kernel_semivar[sub].mean()) if sub.any() else None))
            result[route][name] = bins
    return result
