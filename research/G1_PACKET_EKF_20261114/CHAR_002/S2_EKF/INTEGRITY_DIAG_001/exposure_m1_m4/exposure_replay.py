"""Online exposure-control replay with fixed packet acceptance."""
from collections import deque
import math

import numpy as np

HIGH_G = 1.5
YAW_LIMIT = math.radians(10)
WINDOW_S = 10.0
MAX_HISTORY = 100
TOL = 1e-10


def motion_arc(ds):
    return np.r_[0.0, np.cumsum(np.abs(ds[1:]))]


def dwell_fraction(times, g):
    """Fraction of all packets with high sensitivity in the trailing 10 s."""
    right = np.arange(1, len(times) + 1)
    left = np.searchsorted(times, times - WINDOW_S, side="left")
    prefix = np.r_[0, np.cumsum(g >= HIGH_G)]
    return (prefix[right] - prefix[left]) / (right - left)


def density_factors(times, arc, mask, ell):
    """Causal factors from up to 100 earlier accepted packet rows."""
    if ell < 0:
        raise ValueError("ell must be nonnegative")
    factors = np.ones(len(times))
    if ell == 0:
        return factors
    history = deque(maxlen=MAX_HISTORY)
    for i, t in enumerate(times):
        while history and times[history[0]] < t - WINDOW_S:
            history.popleft()
        if history:
            factors[i] += 2.0 * np.exp((arc[list(history)] - arc[i]) / ell).sum()
        if mask[i]:
            history.append(i)
    return factors


def replay(packet, controls, baseline, core, online, model, spec, mode,
           ell=0.5, oracle_variance=None):
    """Replay one arm using an online packet and the frozen LORO trace."""
    if mode not in {"BASE", "D", "G", "I", "H", "L", "FULL"}:
        raise ValueError(f"unknown mode {mode}")
    if not np.isfinite(ell) or ell < 0:
        raise ValueError("ell must be finite and nonnegative")
    times = np.asarray(packet["t"])
    n = len(times)
    mask = np.asarray(baseline["mask"], dtype=bool)
    reference = np.asarray(baseline["Reff"])
    if (n == 0 or not np.all(np.diff(times) > 0) or mask.shape != (n,)
            or reference.shape != (n, 2, 2)):
        raise ValueError("packet and frozen trace must be aligned")
    if mode in {"H", "L", "FULL"}:
        oracle_variance = np.asarray(oracle_variance, dtype=float)
        if (oracle_variance.shape != (n,) or not np.all(np.isfinite(oracle_variance))
                or not np.all(oracle_variance > 0)):
            raise ValueError("oracle_variance must contain one positive R_ss per row")
    elif oracle_variance is not None:
        raise ValueError("oracle variance is restricted to H, L and FULL")

    x, P = packet["x0"].copy(), packet["P0"].copy()
    state_size = len(x)
    shapes = {
        "x": (state_size,), "P": (state_size, state_size),
        "prior": (state_size,), "Pprior": (state_size, state_size),
        "h": (2,), "H": (2, state_size), "K": (state_size, 2),
        "Reff": (2, 2), "nu": (2,), "S": (2, 2),
        "g": (), "yaw": (),
    }
    trace = {key: np.empty((n, *shape)) for key, shape in shapes.items()}
    arc = motion_arc(np.asarray(controls["ds"]))
    factors = density_factors(times, arc, mask, ell) if mode == "I" else np.ones(n)
    trace.update(arc=arc, mask=mask.copy(), F=factors, s_updated=np.zeros(n, dtype=bool))
    yaw = 0.0
    last_s = None

    for i in range(n):
        prior, Pprior = online.predict(core, x, P, i, controls)
        if i:
            yaw += abs(core.wrap(prior[2] - x[2]))
        h, H = (value[0] for value in model.batch(prior[None], spec))
        nu = packet["z"][i] - h - packet["muMB"][i]
        g = abs(H[1, 2])
        keep_s = mask[i]
        if keep_s and last_s is not None and (mode == "D" or (mode == "G" and g >= HIGH_G)):
            keep_s = arc[i] - arc[last_s] >= ell or yaw - trace["yaw"][last_s] >= YAW_LIMIT
        if keep_s:
            last_s = i

        R = reference[i].copy()
        if mode == "I":
            R[1, 1] *= factors[i]
        if mode == "FULL" or (mode == "H" and g >= HIGH_G) or (mode == "L" and g < HIGH_G):
            R[1, 1] = oracle_variance[i]
            factors[i] = R[1, 1] / reference[i, 1, 1]

        x, P, K, S = online.joseph(prior, Pprior, H, nu, R, mask[i], float(keep_s))
        values = (x, P, prior, Pprior, h, H, K, R, nu, S, g, yaw)
        for key, value in zip(shapes, values, strict=True):
            trace[key][i] = value
        trace["s_updated"][i] = keep_s

    trace["dwell"] = dwell_fraction(times, trace["g"])
    return trace


def check_parity(trace, baseline):
    """Compare an inactive arm against the native E0-LORO trace."""
    errors = {}
    np.testing.assert_array_equal(trace["mask"], baseline["mask"])
    for key in ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S"):
        errors[key] = float(np.max(np.abs(trace[key] - baseline[key])))
        np.testing.assert_allclose(trace[key], baseline[key], atol=TOL, rtol=0, err_msg=key)
    return errors


def check_trace(trace, packet, controls, baseline, mode, ell=0.5, oracle_variance=None):
    """Recompute the arm's schedule and independently verify scalar range updates."""
    times = packet["t"]
    mask = baseline["mask"]
    np.testing.assert_array_equal(trace["mask"], mask)
    np.testing.assert_array_equal(trace["x"][~mask], trace["prior"][~mask])
    np.testing.assert_array_equal(trace["P"][~mask], trace["Pprior"][~mask])
    np.testing.assert_array_equal(trace["K"][~mask], 0.0)
    np.testing.assert_array_equal(trace["g"], np.abs(trace["H"][:, 1, 2]))
    np.testing.assert_array_equal(trace["arc"], motion_arc(controls["ds"]))
    increments = controls["gy"][1:] - trace["x"][:-1, 3] * controls["dt"][1:]
    wrapped = np.arctan2(np.sin(increments), np.cos(increments))
    np.testing.assert_allclose(trace["yaw"], np.r_[0, np.cumsum(np.abs(wrapped))],
                               atol=TOL, rtol=0)

    errors = {
        "innovation_variance": 0.0, "gain_equation": 0.0, "state": 0.0,
        "covariance": 0.0, "symmetry": 0.0,
    }
    min_eigenvalue = None
    last_s = None
    for i, accepted in enumerate(mask):
        high = trace["g"][i] >= HIGH_G
        keep = bool(accepted)
        if last_s is not None and (mode == "D" or (mode == "G" and high)):
            step = trace["arc"][i] - trace["arc"][last_s]
            turn = trace["yaw"][i] - trace["yaw"][last_s]
            keep = keep and (step >= ell or turn >= YAW_LIMIT)
        assert trace["s_updated"][i] == keep, f"polarization schedule row {i}"
        if not keep:
            np.testing.assert_array_equal(trace["K"][i, :, 1], 0.0)
        else:
            last_s = i

        R = baseline["Reff"][i].copy()
        if mode == "I" and ell > 0:
            history = np.flatnonzero(mask[:i] & (times[:i] >= times[i] - WINDOW_S))[-MAX_HISTORY:]
            weights = (math.exp((trace["arc"][j] - trace["arc"][i]) / ell) for j in history)
            R[1, 1] *= 1.0 + 2.0 * math.fsum(weights)
        if mode == "FULL" or (mode == "H" and high) or (mode == "L" and not high):
            R[1, 1] = oracle_variance[i]
        np.testing.assert_allclose(trace["Reff"][i], R, atol=TOL, rtol=0)
        ratio = R[1, 1] / baseline["Reff"][i, 1, 1]
        np.testing.assert_allclose(trace["F"][i], ratio, atol=TOL, rtol=0)
        visible = (times >= times[i] - WINDOW_S) & (times <= times[i])
        expected_dwell = (trace["g"][visible] >= HIGH_G).mean()
        np.testing.assert_allclose(trace["dwell"][i], expected_dwell, atol=TOL, rtol=0)

        if accepted and not keep:
            row = trace["H"][i, 0]
            prior = trace["prior"][i]
            Pprior = trace["Pprior"][i]
            cross = Pprior @ row
            innovation_variance = R[0, 0] + row @ cross
            gain = cross / innovation_variance
            x = prior + gain * trace["nu"][i, 0]
            x[2] = math.atan2(math.sin(x[2]), math.cos(x[2]))
            if x[2] == math.pi:
                x[2] = -math.pi
            A = np.eye(len(prior)) - np.outer(gain, row)
            P = A @ Pprior @ A.T + R[0, 0] * np.outer(gain, gain)
            actual_P = trace["P"][i]
            for key, delta in (
                ("innovation_variance", trace["S"][i, 0, 0] - innovation_variance),
                ("gain_equation", trace["K"][i, :, 0] * innovation_variance - cross),
                ("state", trace["x"][i] - x),
                ("covariance", actual_P - P),
                ("symmetry", actual_P - actual_P.T),
            ):
                errors[key] = max(errors[key], float(np.max(np.abs(delta))))
                np.testing.assert_allclose(delta, 0.0, atol=TOL, rtol=0, err_msg=f"{key} row {i}")
            eigenvalue = float(np.linalg.eigvalsh(actual_P).min())
            assert eigenvalue >= -TOL, f"range covariance row {i}"
            min_eigenvalue = eigenvalue if min_eigenvalue is None else min(min_eigenvalue, eigenvalue)

    return {
        "packet_count": len(times),
        "accepted": int(mask.sum()),
        "polarization_updates": int(trace["s_updated"].sum()),
        "range_only": int((mask & ~trace["s_updated"]).sum()),
        "range_only_max_abs": errors,
        "range_only_min_eigenvalue": min_eigenvalue,
    }
