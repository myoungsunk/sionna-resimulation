"""Fixed-mask Schmidt/KI replays and historical SC comparisons."""

from collections import deque
from dataclasses import dataclass
import math

import numpy as np
from d0_d5 import KNOTS


KI_WINDOW_S = 10.0
KI_MAX_PACKETS = 100
WHITE_FLOOR_RELATIVE = 1.0e-12
PARITY_KEYS = ("x", "P", "prior", "Pprior", "h", "H", "K", "nu", "S", "sigma_b",
               "rho_before", "mask", "t", "pose_id")


@dataclass(frozen=True)
class Noise:
    """Variances in squared observation units and lengths in meters."""

    white: float
    fast: float
    slow: float
    ell_fast: float
    ell_slow: float

    def __post_init__(self):
        values = (self.white, self.fast, self.slow, self.ell_fast, self.ell_slow)
        if not all(math.isfinite(value) and value >= 0.0 for value in values):
            raise ValueError("Invalid supported KS noise model")
        if min(self.ell_fast, self.ell_slow) <= 0.0:
            raise ValueError("KS lengths must be positive")


def _partition(reference, noise, uncap_slow):
    """Keep the white and fast allocations at a given prior when lifting the slow cap."""
    if not (math.isfinite(reference) and reference > 0.0):
        raise ValueError("Nonpositive base polarization variance")
    if noise is None:
        return reference, 0.0, 0.0, 0.0, False

    white_floor = max(noise.white, WHITE_FLOOR_RELATIVE * reference)
    available = max(0.0, reference - white_floor)
    fast = min(noise.fast, available)
    capped_slow = min(noise.slow, available - fast)
    white = reference - (fast + capped_slow)
    slow = noise.slow if uncap_slow else capped_slow
    return white, fast, slow, capped_slow, white_floor >= reference


def _kernel_extra(history, time, hazard, variance):
    """Use past accepted packets with the shared inclusive time and packet limits."""
    while history and time - history[0][0] > KI_WINDOW_S:
        history.popleft()
    excess = np.zeros_like(variance)
    for _, previous_hazard, previous_variance in history:
        excess += 2.0 * np.sqrt(variance * previous_variance) * np.exp(previous_hazard - hazard)
    return excess


def _augmented_prior(previous, nav_prior, transition, alpha):
    covariance = np.empty_like(previous)
    covariance[:4, :4] = nav_prior
    covariance[:4, 4:] = (transition @ previous[:4, 4:]) * alpha
    covariance[4:, :4] = covariance[:4, 4:].T
    covariance[4:, 4:] = np.eye(len(alpha)) + alpha[:, None] * (
        previous[4:, 4:] - np.eye(len(alpha))
    ) * alpha
    return covariance


def _augmented_update(prior, covariance, jacobian, innovation, white, permitted, wrap,
                      *, estimate_bias=False, forced_nav_gain=None):
    projected = jacobian @ covariance
    innovation_cov = projected @ jacobian.T + white
    innovation_cov = (innovation_cov + innovation_cov.T) * 0.5
    gain = np.zeros((len(prior), jacobian.shape[0]))
    if not permitted:
        return prior, covariance, gain, innovation_cov
    if estimate_bias:
        gain[:] = np.linalg.solve(innovation_cov, projected).T
    elif forced_nav_gain is None:
        gain[:4] = np.linalg.solve(innovation_cov, projected[:, :4]).T
    else:
        gain[:4] = forced_nav_gain
    posterior = prior + gain @ innovation
    posterior[2] = wrap(posterior[2])
    residual_map = np.eye(len(prior)) - gain @ jacobian
    updated_cov = residual_map @ covariance @ residual_map.T + gain @ white @ gain.T
    return posterior, (updated_cov + updated_cov.T) * 0.5, gain, innovation_cov


def _geometry(case, core, online, model, previous, covariance, i):
    packet, controls, spec = (case[key] for key in ("packet", "controls", "spec"))
    ax, ay = spec["anchor"][:2]
    rho_before = math.hypot(previous[0] - ax, previous[1] - ay)
    sigma = float(np.interp(rho_before, KNOTS, case["table"]))
    prior, prior_cov = online.predict(core, previous, covariance, i, controls)
    rho_prior = math.hypot(prior[0] - ax, prior[1] - ay)
    h, H = (item[0] for item in model.batch(prior[None], spec))
    transition = np.eye(4)
    if i:
        _, transition, _ = core.transition(
            previous, *(float(controls[key][i]) for key in ("ds", "gy", "dt")),
        )
    reference = packet["R"][i].copy()
    reference[1, 1] += sigma**2
    return prior, prior_cov, h, H, transition, rho_before, rho_prior, sigma, reference


def _common_step(x, P, prior, Pprior, h, H, K, covariance, innovation, innovation_cov,
                 sigma, rho_before, rho_prior, reference):
    return dict(x=x, P=P, prior=prior, Pprior=Pprior, h=h, H=H, K=K, Reff=covariance,
                nu=innovation, S=innovation_cov, sigma_b=sigma, rho_before=rho_before,
                rho_prior=rho_prior, R_ref=reference)


def _trace(case, steps):
    packet = case["packet"]
    return {
        **{key: np.stack([step[key] for step in steps]) for key in steps[0]},
        "t": packet["t"].copy(),
        "pose_id": packet["pose_id"].copy(),
        "mask": case["mask"].copy(),
    }


def replay_ks(case, core, online, model, noise, *, arm="KS", uncap_slow=False,
              check_special=None):
    """Use an online noise(distance, sensitivity) lookup with a whitened fallback."""
    if arm not in ("KS", "KI") or check_special not in (
        None, "white", "independent", "empty_history",
    ):
        raise ValueError("Invalid KS/KI replay options")
    if uncap_slow and arm != "KS":
        raise ValueError("Slow cap override is reserved for the V3 KS oracle")
    packet, mask, controls = (case[key] for key in ("packet", "mask", "controls"))
    x = packet["x0"].copy()
    P = packet["P0"].copy()
    P_aug = np.eye(5)
    P_aug[:4, :4] = P
    history = deque(maxlen=KI_MAX_PACKETS)
    hazard = np.zeros(2)
    inverse_length = np.zeros(2)
    arc = 0.0
    steps = []
    for i, accepted in enumerate(mask):
        prior, Pprior, h, H, F, rho_before, d, sigma_b, reference = _geometry(
            case, core, online, model, x, P, i,
        )
        g = abs(float(H[1, 2]))
        fitted = None if check_special == "white" else noise(d, g)
        white, fast, slow, capped_slow, white_fallback = _partition(reference[1, 1], fitted, uncap_slow)
        if fitted is not None:
            inverse_length = 1.0 / np.array([fitted.ell_fast, fitted.ell_slow])
        travel = abs(float(controls["ds"][i])) if i else 0.0
        arc += travel
        increment = travel * inverse_length
        hazard += increment
        components = np.array([fast, slow])
        causal = _kernel_extra(history, float(packet["t"][i]), hazard, components)
        history_n = len(history)
        if accepted and check_special not in ("independent", "empty_history"):
            history.append((float(packet["t"][i]), hazard.copy(), components))
        white_obs = reference.copy()
        white_obs[1, 1] = white + fast + causal[0]
        innovation = packet["z"][i] - h - packet["muMB"][i]
        if arm == "KS":
            alpha = np.array([0.0 if check_special == "independent" else np.exp(-increment[1])])
            Pprior_aug = _augmented_prior(P_aug, Pprior, F, alpha)
            D = np.array([[0.0], [math.sqrt(slow)]])
            state, P_aug, K_aug, innovation_cov = _augmented_update(
                np.r_[prior, 0.0], Pprior_aug, np.column_stack((H, D)), innovation,
                white_obs, accepted, core.wrap,
            )
            x, P, K = state[:4], P_aug[:4, :4], K_aug[:4]
        else:
            white_obs[1, 1] += slow + causal[1]
            x, P, K, innovation_cov = online.joseph(prior, Pprior, H, innovation,
                                                     white_obs, accepted, 1.0)
        steps.append(_common_step(x, P, prior, Pprior, h, H, K, white_obs, innovation,
                                  innovation_cov, sigma_b, rho_before, d, reference))
        step = steps[-1]
        step.update(
            sensitivity=g, arc=arc, hazard=hazard.copy(), history_n=history_n, causal=causal,
            W_op=white, V_f=0.0 if fitted is None else fitted.fast, V_f_op=fast,
            V_l=0.0 if fitted is None else fitted.slow, V_l_capped=capped_slow, V_l_op=slow,
            supported=fitted is not None, white_fallback=white_fallback,
        )
        if arm == "KS":
            step.update(P_aug=P_aug, Pprior_aug=Pprior_aug, K_aug=K_aug, D=D,
                        alpha=alpha, u_mean=state[4:])
    return _trace(case, steps)


def replay_v9(case, core, online, model, *, arm="GM", fixed_schedule=True):
    """Recreate historical SC noise with controlled lookup and alternative gain rules."""
    if arm not in ("SC", "GM", "FIXED_GAIN"):
        raise ValueError("Invalid V9 replay arm")
    if arm == "FIXED_GAIN" and not fixed_schedule:
        raise ValueError("V9 fixed gain uses the frozen LORO noise schedule")
    packet, mask, controls, loro = (case[k] for k in ("packet", "mask", "controls", "loro"))
    x, P = packet["x0"].copy(), packet["P0"].copy()
    u_mean = np.zeros(2)
    P_aug = np.eye(6)
    P_aug[:4, :4] = P
    kernels = [case["fit"]["fits"][channel] for channel in ("r", "s")]
    knots = case["fit"]["q_knots_m"]
    lengths = np.array([kernel["ell_m"] for kernel in kernels])
    yaw_lengths = np.deg2rad([kernel["ell_deg"] for kernel in kernels])
    anchor = np.asarray(case["spec"]["anchor"][:2])
    steps = []
    for i, accepted in enumerate(mask):
        prior, Pprior, h, H, F, rho_before, d, sigma, reference = _geometry(
            case, core, online, model, x, P, i,
        )
        travel = abs(float(controls["ds"][i])) if i else 0.0
        lookup_distance = d
        if fixed_schedule:
            lookup_distance = float(np.linalg.norm(loro["prior"][i, :2] - anchor))
            reference = loro["Reff"][i]
            sigma = float(loro["sigma_b"][i])
            yaw = abs(float(core.wrap(loro["prior"][i, 2] - loro["x"][i-1, 2]))) if i else 0.0
        else:
            yaw = abs(float(core.wrap(prior[2] - x[2]))) if i else 0.0
        alpha = np.exp(-travel / lengths - yaw / yaw_lengths)
        q = np.array([np.interp(lookup_distance, knots, kernel["q_knots"]) for kernel in kernels])
        D = np.diag(np.sqrt(np.minimum(q, 0.95) * reference.diagonal()))
        white = reference - D @ D.T
        Pprior_aug = _augmented_prior(P_aug, Pprior, F, alpha)
        u_prior = alpha * u_mean
        innovation = packet["z"][i] - h - packet["muMB"][i] - D @ u_prior
        forced_gain = loro["K"][i] if arm == "FIXED_GAIN" else None
        state, P_aug, K_aug, innovation_cov = _augmented_update(
            np.r_[prior, u_prior], Pprior_aug, np.column_stack((H, D)), innovation, white,
            accepted, core.wrap, estimate_bias=arm == "GM", forced_nav_gain=forced_gain,
        )
        x, u_mean, P = state[:4], state[4:], P_aug[:4, :4]
        steps.append(_common_step(x, P, prior, Pprior, h, H, K_aug[:4], white, innovation,
                                  innovation_cov, sigma, rho_before, d, reference))
        steps[-1].update(
            P_aug=P_aug, Pprior_aug=Pprior_aug, K_aug=K_aug, D=D, alpha=alpha,
            u_mean=u_mean, u_prior=u_prior, q=q, lookup_distance=lookup_distance,
        )
    return _trace(case, steps)


def check_trace(trace, case, *, forced_gain=False, expect_zero_nuisance=True,
                history_enabled=True):
    """Fail closed on invalid gate, covariance, or update identities."""
    from replay_s2 import parity, validate_trace

    validate_trace(trace)
    mask = case["mask"]
    for key in ("t", "pose_id", "mask"):
        expected = mask if key == "mask" else case["packet"][key]
        np.testing.assert_array_equal(trace[key], expected)
    for posterior, prior in (("x", "prior"), ("P", "Pprior")):
        np.testing.assert_array_equal(trace[posterior][~mask], trace[prior][~mask])
    np.testing.assert_array_equal(trace["K"][~mask], 0.0)
    minimum_eigenvalue = float(np.linalg.eigvalsh(trace["P"]).min())
    gain = trace["K"]
    G = trace["H"]
    predicted, posterior = trace["Pprior"], trace["P"]
    if "P_aug" in trace:
        G = np.concatenate((G, trace["D"]), axis=2)
        predicted, posterior = trace["Pprior_aug"], trace["P_aug"]
        gain = trace["K_aug"]
        for cov in (predicted, posterior):
            eigenvalue = float(np.linalg.eigvalsh(cov).min())
            if eigenvalue < -1e-12 or np.max(abs(cov - cov.swapaxes(1, 2))) > 1e-12:
                raise ValueError("Indefinite or asymmetric augmented covariance")
            minimum_eigenvalue = min(minimum_eigenvalue, eigenvalue)
        np.testing.assert_array_equal(posterior[:, :4, :4], trace["P"])
        np.testing.assert_array_equal(predicted[:, :4, :4], trace["Pprior"])
        np.testing.assert_array_equal(posterior[~mask], predicted[~mask])
        np.testing.assert_array_equal(gain[~mask], 0.0)
        if expect_zero_nuisance:
            np.testing.assert_array_equal(trace["u_mean"], 0.0)
            np.testing.assert_array_equal(gain[:, 4:], 0.0)
            expected_nuisance = np.broadcast_to(np.eye(G.shape[2] - 4), posterior[:, 4:, 4:].shape)
            np.testing.assert_array_equal(posterior[:, 4:, 4:], expected_nuisance)
            np.testing.assert_array_equal(predicted[:, 4:, 4:], expected_nuisance)
    R = trace["Reff"]
    sigma = G @ predicted @ G.swapaxes(1, 2) + R
    np.linalg.cholesky(R)
    np.linalg.cholesky(sigma)
    np.testing.assert_allclose(trace["S"], sigma, rtol=1e-10, atol=1e-12)
    if not forced_gain:
        dimensions = 4 if expect_zero_nuisance else G.shape[2]
        target = predicted[mask, :dimensions, :] @ G[mask].swapaxes(1, 2)
        np.testing.assert_allclose(gain[mask, :dimensions] @ sigma[mask], target,
                                   rtol=1e-10, atol=1e-12)
    else:
        parity(trace, {key: case["loro"][key] for key in ("x", "prior", "K", "nu")})
    correction = np.eye(G.shape[2]) - gain @ G
    joseph = correction @ predicted @ correction.swapaxes(1, 2) + gain @ R @ gain.swapaxes(1, 2)
    np.testing.assert_allclose(posterior, joseph, rtol=1e-10, atol=1e-12)
    if "V_l" in trace:
        reference = trace["R_ref"][:, 1, 1]
        np.testing.assert_allclose(trace["W_op"] + trace["V_f_op"] + trace["V_l_capped"],
                                   reference, rtol=1e-12, atol=0.0)
        for key in ("R_ref", "Reff"):
            np.testing.assert_array_equal(trace[key][:, 0, :], trace["R_ref"][:, 0, :])
        minimum_white = float(trace["W_op"].min())
        if minimum_white <= 0.0:
            raise ValueError("Nonpositive KS white variance")
        # Independently reconstruct accepted history using immutable time and hazard trace.
        admitted = np.flatnonzero(mask) if history_enabled else np.empty(0, dtype=int)
        expected_excess = np.zeros_like(trace["causal"])
        expected_counts = np.zeros(len(mask), dtype=int)
        variance = np.column_stack((trace["V_f_op"], trace["V_l_op"]))
        for i, end in enumerate(np.searchsorted(admitted, np.arange(len(mask)))):
            past = admitted[max(0, end - KI_MAX_PACKETS):end]
            past = past[trace["t"][i] - trace["t"][past] <= KI_WINDOW_S]
            expected_counts[i] = len(past)
            expected_excess[i] = 2.0 * np.sum(
                np.sqrt(variance[i] * variance[past]) *
                np.exp(trace["hazard"][past] - trace["hazard"][i]), axis=0,
            )
        np.testing.assert_allclose(trace["causal"], expected_excess, rtol=1e-10, atol=1e-12)
        np.testing.assert_array_equal(trace["history_n"], expected_counts)
    return {"status": "PASS", "covariance_min_eigenvalue": minimum_eigenvalue,
            "innovation_covariance_max_abs": float(np.max(abs(trace["S"] - sigma))),
            "joseph_max_abs": float(np.max(abs(posterior - joseph)))}


def clipping_summary(trace):
    accepted = trace["mask"]
    supported = accepted & trace["supported"]
    clipped = supported & (trace["V_l_capped"] < trace["V_l"])
    before = trace["V_l"][supported]
    capped = trace["V_l_capped"][supported]
    applied = trace["V_l_op"][supported]
    n, clipped_n = int(np.sum(supported)), int(np.sum(clipped))
    return dict(
        accepted=int(np.sum(accepted)), supported=n, clipped=clipped_n,
        unsupported=int(np.sum(accepted & ~trace["supported"])),
        white_fallback=int(np.sum(supported & trace["white_fallback"])),
        fraction=None if not n else clipped_n / n,
        mean_before=float(before.mean()) if n else None,
        mean_capped=float(capped.mean()) if n else None,
        mean_applied=float(applied.mean()) if n else None,
        mean_clipped_variance=float((before - capped).mean()) if n else None,
        max_clipped_variance=float(np.max(before - capped)) if n else None,
    )


def synthetic_checks():
    """Distinguish partition, kernel, Schmidt, and GM errors without RF inputs."""
    model = Noise(white=0.1, fast=0.5, slow=0.7, ell_fast=0.2, ell_slow=2.0)
    np.testing.assert_allclose(_partition(1.0, model, False)[:4], [0.1, 0.5, 0.4, 0.4])
    np.testing.assert_allclose(_partition(1.0, model, True)[:4], [0.1, 0.5, 0.7, 0.4])
    floor_exceeds_budget = Noise(white=1.5, fast=0.5, slow=0.7, ell_fast=0.2, ell_slow=2.0)
    assert _partition(1.0, floor_exceeds_budget, False) == (1.0, 0.0, 0.0, 0.0, True)
    assert _partition(1.0, floor_exceeds_budget, True) == (1.0, 0.0, 0.7, 0.0, True)
    assert _partition(1.0, None, True) == (1.0, 0.0, 0.0, 0.0, False)

    history = deque(maxlen=KI_MAX_PACKETS)
    current_hazard = np.array([5.0, 0.5])
    current_variance = np.array([0.25, 0.09])
    np.testing.assert_array_equal(_kernel_extra(history, 10.0, current_hazard, current_variance), 0.0)
    history.append((0.0, np.zeros(2), np.array([0.04, 0.25])))
    history.append((1.0, np.array([2.0, 0.1]), np.array([0.16, 0.01])))
    expected = [0.2 * math.exp(-5.0) + 0.4 * math.exp(-3.0),
                0.3 * math.exp(-0.5) + 0.06 * math.exp(-0.4)]
    excess = _kernel_extra(history, 10.0, current_hazard, current_variance)
    np.testing.assert_allclose(excess, expected, rtol=0, atol=1e-15)
    _kernel_extra(history, 10.0001, current_hazard, current_variance)
    assert [row[0] for row in history] == [1.0]

    prior = np.zeros(5)
    covariance = np.diag([4.0, 2.0, 1.0, 0.5, 1.0])
    H = np.array([[0.0, 1.0, 0.0, 0.0, 0.0],
                  [1.0, 0.0, 0.0, 0.0, math.sqrt(0.3)]])
    R = np.diag([1.0, 0.2])
    nu = np.array([0.2, -0.1])
    marginal = R + np.diag([0.0, 0.3])
    nav_H, nav_P = H[:, :4], covariance[:4, :4]
    white_cov = np.linalg.inv(np.linalg.inv(nav_P) + nav_H.T @ np.linalg.solve(marginal, nav_H))
    white_mean = white_cov @ nav_H.T @ np.linalg.solve(marginal, nu)
    x, P, K, _ = _augmented_update(prior, covariance, H, nu, R, True, float)
    np.testing.assert_allclose(P[:4, :4], white_cov, atol=1e-14)
    np.testing.assert_allclose(x[:4], white_mean, atol=1e-14)
    np.testing.assert_array_equal(K[4:], 0.0)

    forced_gain = np.arange(8, dtype=float).reshape(4, 2) * 0.01
    forced_mean, _, applied_gain, _ = _augmented_update(
        prior, covariance, H, nu, R, True, float, forced_nav_gain=forced_gain,
    )
    np.testing.assert_array_equal(applied_gain[:4], forced_gain)
    np.testing.assert_allclose(forced_mean[:4], forced_gain @ nu, atol=1e-14)
    rejected, rejected_cov, rejected_gain, _ = _augmented_update(
        prior, covariance, H, nu, R, False, float, estimate_bias=True,
    )
    np.testing.assert_array_equal(rejected, prior)
    np.testing.assert_array_equal(rejected_cov, covariance)
    np.testing.assert_array_equal(rejected_gain, 0.0)
    gm_mean, gm_cov, _, _ = _augmented_update(
        prior, covariance, H, nu, R, True, float, estimate_bias=True,
    )
    batch_cov = np.linalg.inv(np.linalg.inv(covariance) + H.T @ np.linalg.solve(R, H))
    batch_mean = batch_cov @ H.T @ np.linalg.solve(R, nu)
    np.testing.assert_allclose(gm_cov, batch_cov, atol=1e-14)
    np.testing.assert_allclose(gm_mean, batch_mean, atol=1e-14)

    stationary = covariance
    for _ in range(250):
        _, stationary, latent_gain, _ = _augmented_update(prior, stationary, H, nu, R, True, float)
        assert stationary[4, 4] == 1.0 and not np.any(latent_gain[4:])
    stationary_floor = 1.0 / (1.0 / covariance[0, 0] + 1.0 / 0.3)
    assert stationary[0, 0] >= stationary_floor - 1e-12
    assert np.linalg.eigvalsh(stationary).min() >= -1e-12
    reset = _augmented_prior(stationary, nav_P, np.eye(4), np.zeros(1))
    np.testing.assert_array_equal(reset, covariance)
    return {
        "status": "PASS",
        "partition_ordinary_uncapped_white_fallback": True,
        "inclusive_causal_kernel_max_abs": float(np.max(abs(excess - expected))),
        "schmidt_independent_marginal_max_abs": float(np.max(abs(P[:4, :4] - white_cov))),
        "gm_batch_covariance_max_abs": float(np.max(abs(gm_cov - batch_cov))),
        "stationary_common_bias_floor": stationary_floor,
        "stationary_final_variance": float(stationary[0, 0]),
        "fixed_gain_and_rejected_update": True,
    }
