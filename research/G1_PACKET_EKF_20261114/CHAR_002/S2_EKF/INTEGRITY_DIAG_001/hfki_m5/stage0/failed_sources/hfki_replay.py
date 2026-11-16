"""HF-KI joint-update replay with a frozen E0 gate and reference covariance."""

from collections import deque
import math

import numpy as np


TOL = 1e-10
KI_WINDOW_S = 10.
KI_MAX_PACKETS = 100
LENGTH_M = 1.
G_REF = 1.
TRACE_FIELDS = ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S")


def _schedules(times, baseline, sigma_deg, yaw_length_deg, range_table, oracle):
    n = len(times)
    mask = np.asarray(baseline["mask"])
    reference = np.asarray(baseline["Reff"])
    if (n == 0 or not np.isfinite(times).all() or not np.all(np.diff(times) > 0)
            or mask.dtype.kind != "b" or mask.shape != (n,) or reference.shape != (n, 2, 2)):
        raise ValueError("Packet grid, fixed E0 mask and reference covariance must align")
    if not math.isfinite(sigma_deg) or sigma_deg < 0. or not yaw_length_deg > 0.:
        raise ValueError("Invalid heading floor or yaw length")

    slow = fixed_hazard = None
    if oracle is not None:
        reference = np.asarray(oracle["Reff"])
        slow = np.asarray(oracle["V"])
        fixed_hazard = np.asarray(oracle["hazard"])
        if (range_table is not None or reference.shape != (n, 2, 2)
                or slow.shape != (n,) or not np.isfinite(slow).all() or np.any(slow < 0.)
                or fixed_hazard.shape != (n,) or not np.isfinite(fixed_hazard).all()
                or np.any(np.diff(fixed_hazard) < 0.)):
            raise ValueError("Invalid C1 parity schedule")
    if not np.isfinite(reference).all() or np.linalg.eigvalsh(reference).min() <= 0.:
        raise ValueError("Reference covariance must be positive definite")
    if range_table is not None:
        edges = np.asarray(range_table["distance_edges_m"])
        variances = np.asarray(range_table["variances_m2"])
        if (edges.ndim != 1 or variances.ndim != 1 or len(variances) == 0
                or len(edges) != len(variances) + 1 or not np.isfinite(edges).all()
                or not np.all(np.diff(edges) > 0.)
                or not np.isfinite(variances).all() or np.any(variances < 0.)):
            raise ValueError("Range variance lookup requires ordered edges and nonnegative variances")
        range_table = edges, variances
    return mask, reference, slow, fixed_hazard, range_table


def _range_var(distance, table):
    if table is None:
        return 0., False
    edges, variances = table
    index = int(np.searchsorted(edges, distance, side="right")) - 1
    supported = 0 <= index < len(variances)
    return (float(variances[index]) if supported else 0.), supported


def replay(packet, controls, baseline, core, online, model, spec, *, sigma_deg,
           uniform=False, yaw_length_deg=10., range_table=None, oracle=None):
    """Apply either the live HF-KI recipe or a frozen C1 parity schedule."""
    times = np.asarray(packet["t"])
    mask, reference, slow, fixed_hazard, table = _schedules(
        times, baseline, sigma_deg, yaw_length_deg, range_table, oracle,
    )
    sigma = math.radians(sigma_deg)
    yaw_length = math.radians(yaw_length_deg)
    x, P = packet["x0"].copy(), packet["P0"].copy()
    arc = np.r_[0., np.cumsum(np.abs(controls["ds"][1:]))]
    yaw = 0.
    history = deque(maxlen=KI_MAX_PACKETS)
    rows = []
    for i, accepted in enumerate(mask):
        prior, Pprior = online.predict(core, x, P, i, controls)
        if i:
            yaw += abs(float(core.wrap(controls["gy"][i] - x[3] * controls["dt"][i])))
        h, H = (value[0] for value in model.batch(prior[None], spec))
        distance = math.hypot(*(prior[:2] - spec["anchor"][:2]))
        g = abs(float(H[1, 2]))
        variance_s = float(slow[i]) if slow is not None else (sigma * (G_REF if uniform else g)) ** 2
        variance_r, range_supported = _range_var(distance, table)
        hazard = float(fixed_hazard[i]) if fixed_hazard is not None else arc[i] / LENGTH_M + yaw / yaw_length
        variance = np.array([variance_r, variance_s])
        own_information = g**2 / reference[i, 1, 1]

        time = float(times[i])
        while history and time - history[0][0] > KI_WINDOW_S:
            history.popleft()
        causal = np.zeros(2)
        kernel_sum = 0.
        information = own_information
        for _, past_hazard, past_variance, past_information in history:
            kernel = np.exp(past_hazard - hazard)
            kernel_sum += kernel
            causal += 2. * np.sqrt(variance * past_variance) * kernel
            information += kernel * past_information
        count = len(history)
        if accepted:
            history.append((time, hazard, variance, own_information))

        R = reference[i].copy()
        R[0, 0] += variance_r + causal[0]
        R[1, 1] += variance_s
        R[1, 1] += causal[1]
        nu = packet["z"][i] - h - packet["muMB"][i]
        x, P, K, S = online.joseph(prior, Pprior, H, nu, R, accepted, 1.)
        rows.append(dict(
            x=x, P=P, prior=prior, Pprior=Pprior, h=h, H=H, K=K, Reff=R, nu=nu, S=S,
            g=g, yaw=yaw, hazard=hazard, distance=distance, V=variance_s, V_r=variance_r, k_sum=kernel_sum,
            causal=causal[1], causal_r=causal[0], I_cell=information, history_n=count,
            range_supported=range_supported,
            s_infl=R[1, 1] / reference[i, 1, 1],
        ))
    trace = {key: np.stack([row[key] for row in rows]) for key in rows[0]}
    trace.update(t=times.copy(), mask=mask.copy(), s_updated=mask.copy(), arc=arc, R_ref=reference.copy())
    if "pose_id" in packet:
        trace["pose_id"] = packet["pose_id"].copy()
    return trace


def check_trace(trace, packet, controls, baseline, *, sigma_deg, uniform=False,
                yaw_length_deg=10., range_table=None, oracle=None, spec=None):
    """Independently recalculate causal windows and native update equations."""
    times = np.asarray(packet["t"])
    mask, reference, slow, fixed_hazard, table = _schedules(
        times, baseline, sigma_deg, yaw_length_deg, range_table, oracle,
    )
    np.testing.assert_array_equal(trace["t"], times)
    if "pose_id" in packet:
        np.testing.assert_array_equal(trace["pose_id"], packet["pose_id"])
    np.testing.assert_array_equal(trace["mask"], mask)
    np.testing.assert_array_equal(trace["s_updated"], mask)
    np.testing.assert_array_equal(trace["x"][~mask], trace["prior"][~mask])
    np.testing.assert_array_equal(trace["P"][~mask], trace["Pprior"][~mask])
    np.testing.assert_array_equal(trace["K"][~mask], 0.)
    if any(not np.isfinite(value).all() for value in trace.values()):
        raise ValueError("Nonfinite HF-KI trace")

    def compare(actual, expected, key):
        np.testing.assert_allclose(actual, expected, atol=TOL, rtol=0., err_msg=key)
        return float(np.max(np.abs(actual - expected), initial=0.))

    arc = np.r_[0., np.abs(controls["ds"][1:]).cumsum()]
    turn = controls["gy"][1:] - trace["x"][:-1, 3] * controls["dt"][1:]
    yaw = np.r_[0., np.abs(np.arctan2(np.sin(turn), np.cos(turn))).cumsum()]
    prior_turn = trace["prior"][1:, 2] - trace["x"][:-1, 2]
    prior_yaw = np.r_[0., np.abs(np.arctan2(np.sin(prior_turn), np.cos(prior_turn))).cumsum()]
    hazard = arc / LENGTH_M + yaw / math.radians(yaw_length_deg) if fixed_hazard is None else fixed_hazard
    anchor = (10., 0.) if spec is None else spec["anchor"][:2]
    distance = np.linalg.norm(trace["prior"][:, :2] - anchor, axis=1)
    g = np.abs(trace["H"][:, 1, 2])
    variance_s = slow if slow is not None else np.square(np.deg2rad(sigma_deg) * (np.full(len(g), G_REF) if uniform else g))
    range_supported = np.zeros(len(g), dtype=bool)
    variance_r = np.zeros(len(g))
    if table is not None:
        edges, variances = table
        for start, end, variance in zip(edges[:-1], edges[1:], variances, strict=True):
            use = (distance >= start) & (distance < end)
            range_supported[use] = True
            variance_r[use] = variance
    np.testing.assert_array_equal(trace["range_supported"], range_supported)
    expected = dict(arc=arc, yaw=yaw, hazard=hazard, distance=distance,
                    g=g, V=variance_s, V_r=variance_r, R_ref=reference)
    errors = {key: compare(trace[key], value, key) for key, value in expected.items()}
    errors["prior_yaw"] = compare(prior_yaw, yaw, "prior_yaw")
    covariance_expected = reference.copy()
    own_information = np.square(g) / reference[:, 1, 1]
    k_sum, information, causal_r, causal_s = np.zeros((4, len(g)))
    count = np.zeros(len(g), dtype=int)
    u = np.flatnonzero(mask)
    for i, time in enumerate(times):
        eligible = u[(u < i) & (time - times[u] <= KI_WINDOW_S)][-KI_MAX_PACKETS:]
        count[i] = len(eligible)
        kernel = np.exp(hazard[eligible] - hazard[i])
        k_sum[i] = kernel.sum()
        information[i] = own_information[i] + kernel @ own_information[eligible]
        causal_r[i] = 2. * (kernel @ np.sqrt(variance_r[eligible] * variance_r[i]))
        causal_s[i] = 2. * (kernel @ np.sqrt(variance_s[eligible] * variance_s[i]))
    covariance_expected[:, 0, 0] += variance_r + causal_r
    covariance_expected[:, 1, 1] += variance_s + causal_s
    np.testing.assert_array_equal(trace["history_n"], count)
    expected = dict(k_sum=k_sum, causal=causal_s, causal_r=causal_r, I_cell=information, Reff=covariance_expected,
                    s_infl=covariance_expected[:, 1, 1] / reference[:, 1, 1])
    for key, value in expected.items():
        errors[key] = compare(trace[key], value, key)

    Pprior, H, K = trace["Pprior"], trace["H"], trace["K"]
    nu = packet["z"] - trace["h"] - packet["muMB"]
    S = H @ Pprior @ H.swapaxes(1, 2) + trace["Reff"]
    A = np.eye(Pprior.shape[-1]) - K @ H
    P = A @ Pprior @ A.swapaxes(1, 2) + K @ trace["Reff"] @ K.swapaxes(1, 2)
    state = trace["prior"][mask] + (K[mask] @ nu[mask, :, None])[:, :, 0]
    state[:, 2] = np.arctan2(np.sin(state[:, 2]), np.cos(state[:, 2]))
    errors["nu"] = compare(trace["nu"], nu, "nu")
    errors["S"] = compare(trace["S"], S, "S")
    errors["gain"] = compare(K[mask] @ S[mask], (Pprior @ H.swapaxes(1, 2))[mask], "gain equation")
    errors["state"] = compare(trace["x"][mask], state, "posterior state")
    errors["covariance"] = compare(trace["P"], P, "Joseph covariance")
    errors["symmetry"] = compare(trace["P"], trace["P"].swapaxes(1, 2), "posterior symmetry")
    min_eigenvalue = float(np.linalg.eigvalsh(trace["P"]).min())
    if min_eigenvalue < -TOL:
        raise ValueError("HF-KI posterior covariance is not PSD")
    return dict(status="PASS", max_abs=errors, max_history=int(count.max()), min_eigenvalue=min_eigenvalue,
                range_fallback_count=int(np.sum(~range_supported)) if table is not None else 0,
                range_fallback_accepted_count=int(np.sum(mask & ~range_supported)) if table is not None else 0)
