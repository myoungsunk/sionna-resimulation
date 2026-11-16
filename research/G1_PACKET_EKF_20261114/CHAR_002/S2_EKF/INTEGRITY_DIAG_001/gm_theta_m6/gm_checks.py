"""Independent numerical recomputation for the M6 replay and native model."""

import math

import numpy as np

from gm_replay import PARITY_FIELDS, _augmented_observation, _predict_bias, _update, replay


TOL = 1e-10


def _compare(actual, expected, field, tol=TOL):
    np.testing.assert_allclose(actual, expected, atol=tol, rtol=0., err_msg=field)
    return float(np.max(np.abs(actual - expected), initial=0.))


def parity(actual, expected, fields=PARITY_FIELDS):
    """Require identical grid and mask, with the frozen tolerance on numeric traces."""
    for key in ("t", "pose_id", "mask"):
        np.testing.assert_array_equal(actual[key], expected[key], err_msg=key)
    return {key: _compare(actual[key], expected[key], key) for key in fields}


def check_trace(trace, packet, controls, baseline, core, spec, *, arm="G0",
                sigma_rad=0., q_table=None, sigma_table=None, a2_variance=None,
                near=None, disable_beta=False):
    """Whole-grid checks for dynamics, signed observation, gain, and causal schedule."""
    t = packet["t"]
    mask, R_ref = baseline["mask"], baseline["Reff"]
    n = len(t)
    np.testing.assert_array_equal(trace["t"], t)
    if "pose_id" in packet:
        np.testing.assert_array_equal(trace["pose_id"], packet["pose_id"])
    np.testing.assert_array_equal(trace["mask"], mask)
    np.testing.assert_array_equal(trace["s_updated"], mask)
    np.testing.assert_array_equal(trace["R_ref"], R_ref)
    if not all(np.isfinite(a).all() for a in trace.values()):
        raise ValueError("Nonfinite M6 trace")
    errors = {}

    def compare(key, value):
        errors[key] = _compare(trace[key], value, key)

    joint = arm in ("G1", "G2")
    partial = arm in ("G3", "G5psi", "G5y")
    near = np.zeros(n, dtype=bool) if near is None else near
    partial_active = np.ones(n, dtype=bool) if arm == "G3" else near
    if not partial or disable_beta:
        partial_active = np.zeros(n, dtype=bool)
    distance = np.linalg.norm(trace["prior"][:, :2] - spec["anchor"][:2], axis=1)
    compare("distance", distance)
    a = trace["H"][:, 1, 2]
    compare("a", a)
    compare("g", np.abs(a))
    sigma = np.full(n, sigma_rad)
    if sigma_table is not None:
        centers, values = sigma_table
        sigma = np.exp(np.interp(distance, centers, np.log(values)))
    compare("sigma_theta_rad", sigma)

    ds, gy, dt = (controls[k][1:] for k in ("ds", "gy", "dt"))
    dpsi = gy - trace["x"][:-1, 3] * dt
    turn = np.abs(np.arctan2(np.sin(dpsi), np.cos(dpsi)))
    arc = np.r_[0., np.cumsum(np.abs(ds))]
    yaw = np.r_[0., np.cumsum(turn)]
    alpha = np.r_[1., np.exp(-np.abs(ds) - turn / math.radians(10.))]
    compare("arc", arc)
    compare("yaw", yaw)
    compare("alpha", alpha)
    compare("hazard", arc + yaw / math.radians(10.))

    q = np.zeros(n)
    supported = np.zeros(n, dtype=bool)
    if q_table is not None:
        edges, values, support = q_table
        for lo, hi, value, yes in zip(edges[:-1], edges[1:], values, support, strict=True):
            use = (distance >= lo) & (distance < hi) & yes
            q[use] = value
            supported |= use
    compare("q_s", q)
    np.testing.assert_array_equal(trace["q_supported"], supported)
    causal = np.zeros(n)
    history = np.zeros(n, dtype=int)
    own_info = np.square(a) / R_ref[:, 1, 1]
    I = own_info.copy()
    if q_table is not None or partial:
        accepted = np.flatnonzero(mask)
        # The hazard was independently checked above. Using its validated coordinate
        # here avoids amplifying cumulative roundoff in the information sums.
        hazard = trace["hazard"]
        for i, time in enumerate(t):
            indices = accepted[(accepted < i) & (time - t[accepted] <= 10.)][-100:]
            kernel = np.exp(hazard[indices] - hazard[i])
            I[i] += kernel @ own_info[indices]
            causal[i] = 2. * (kernel @ np.sqrt(q[i] * q[indices]))
            history[i] = len(indices)
    np.testing.assert_array_equal(trace["history_n"], history)
    compare("I_cell", I)
    beta = np.ones(n)
    beta[partial_active] = 1. / (1. + I[partial_active] * sigma[partial_active]**2)
    compare("beta", beta)

    R = R_ref.copy()
    R[:, 1, 1] += q
    R[:, 1, 1] += causal
    V_fixed = np.zeros(n)
    causal_fixed = np.zeros(n)
    if a2_variance is not None:
        V_fixed[~near], causal_fixed[~near] = a2_variance[~near].T
        R[:, 1, 1] += V_fixed
        R[:, 1, 1] += causal_fixed
    compare("V", q + V_fixed)
    compare("causal", causal + causal_fixed)
    compare("Reff", R)
    compare("s_infl", R[:, 1, 1] / R_ref[:, 1, 1])

    x, P, prior, Pprior, H, K = (trace[k] for k in ("x", "P", "prior", "Pprior", "H", "K"))
    h = trace["h_nav"].copy()
    state_initial = packet["x0"]
    P_initial = packet["P0"]
    if joint:
        x, P, prior, Pprior, H, K = (
            trace[k + "_internal"] for k in ("x", "P", "prior", "Pprior", "H", "K")
        )
        scale = sigma if sigma_table is not None else np.ones(n)
        stationary = 1. if sigma_table is not None else sigma_rad**2
        state_initial = np.r_[state_initial, 0.]
        P_initial = np.pad(P_initial, ((0, 1), (0, 1)))
        P_initial[4, 4] = stationary
        transform = np.column_stack((np.ones((n, 4)), scale))
        compare("x_aug", x * transform)
        compare("P_aug", P * transform[:, :, None] * transform[:, None, :])
        compare("prior_aug", prior * transform)
        compare("Pprior_aug", Pprior * transform[:, :, None] * transform[:, None, :])
        compare("H_aug", np.concatenate((trace["H"], np.column_stack((np.zeros(n), a))[:, :, None]), axis=2))
        compare("K_aug", K * transform[:, :, None])
        expected_H = trace["H_aug"].copy()
        expected_H[:, 1, 4] *= scale
        compare("H_internal", expected_H)
        compare("b_theta", x[:, 4] * scale)
        compare("b_theta_prior", prior[:, 4] * scale)
        h[:, 1] += a * prior[:, 4] * scale
        if arm == "G2":
            np.testing.assert_array_equal(x[:, 4], 0.)
            np.testing.assert_array_equal(K[:, 4], 0.)
    compare("h", h)
    expected_prior = np.empty_like(prior)
    expected_cov = np.empty_like(Pprior)
    expected_prior[0], expected_cov[0] = state_initial, P_initial
    for i in range(1, n):
        y, F, G = core.transition(x[i-1, :4], float(ds[i-1]), float(gy[i-1]), float(dt[i-1]))
        expected_prior[i, :4] = y
        process = G @ np.diag([2e-5 * abs(ds[i-1]), math.radians(.015)**2 * dt[i-1], 0.]) @ G.T
        if joint:
            phi = np.zeros((5, 5))
            phi[:4, :4], phi[4, 4] = F, alpha[i]
            process = np.pad(process, ((0, 1), (0, 1)))
            process[4, 4] = stationary * (1. - alpha[i]**2)
            expected_prior[i, 4] = alpha[i] * x[i-1, 4]
        else:
            phi = F
        expected_cov[i] = phi @ P[i-1] @ phi.T + process
    errors["prior_transition"] = _compare(prior, expected_prior, "whole-state transition")
    errors["prior_covariance"] = _compare(Pprior, expected_cov, "whole prior covariance")
    nu = packet["z"] - h - packet["muMB"]
    compare("nu", nu)
    projected = H @ Pprior
    S = projected @ H.swapaxes(1, 2) + R
    compare("S", S)

    expected_K = np.zeros_like(K)
    for i in np.flatnonzero(mask):
        gain = np.linalg.solve(S[i], projected[i]).T
        if partial_active[i]:
            row = 1 if arm == "G5y" else 2
            # K_cond @ L = K, so scaling only its second column adds this row correction.
            nuisance = (beta[i] - 1.) * gain[row, 1]
            gain[row] += nuisance * np.array([-R[i, 1, 0] / R[i, 0, 0], 1.])
        if arm == "G2":
            gain[4] = 0.
        expected_K[i] = gain
    errors["gain"] = _compare(K, expected_K, "actual gain")
    np.testing.assert_array_equal(K[~mask], 0.)
    np.testing.assert_array_equal(x[~mask], prior[~mask])
    np.testing.assert_array_equal(P[~mask], Pprior[~mask])
    expected_x = prior.copy()
    expected_x[mask] += (K[mask] @ nu[mask, :, None])[:, :, 0]
    expected_x[mask, 2] = core.wrap(expected_x[mask, 2])
    errors["posterior_state"] = _compare(x, expected_x, "posterior state")
    residual = np.eye(K.shape[1]) - K @ H
    expected_P = residual @ Pprior @ residual.swapaxes(1, 2) + K @ R @ K.swapaxes(1, 2)
    errors["joseph"] = _compare(P, expected_P, "Joseph covariance")
    compare("Knu", (K[:, :4] @ nu[:, :, None])[:, :, 0])
    minimum = {}
    for name, matrix in (("P", P), ("Pprior", Pprior), ("S", S), ("Reff", R)):
        errors[name + "_symmetric"] = _compare(matrix, matrix.swapaxes(1, 2), name + " symmetry")
        minimum[name] = float(np.linalg.eigvalsh(matrix).min())
        if minimum[name] < -1e-12 or (name in ("S", "Reff") and minimum[name] <= 0.):
            raise ValueError(name + " violates its positive (semi-)definiteness contract")
    return dict(status="PASS", max_abs=errors, min_eigenvalues=minimum, count=n,
                max_history=int(history.max()), supported_count=int(supported.sum()),
                unsupported_accepted=int(np.sum(mask & ~supported)) if q_table is not None else 0)


def geometry_checks(trace, model, spec, *, raise_on_failure=True):
    """Test all supplied priors, keeping changed SourceFFD cells/taps separate."""
    priors = trace["prior"]
    b_prior = trace["b_theta_prior"]
    report = {}
    for step in (1e-4, 5e-5):
        checked, changed, failed = np.zeros((3, 3), dtype=int)
        max_abs, max_relative, max_omitted = np.zeros((3, 3))
        first_failures = []
        for offset in range(0, len(priors), 64):
            states = priors[offset:offset+64]
            n = len(states)
            points = np.concatenate([states, *(states + sign * step * np.eye(4)[j]
                                     for j in range(3) for sign in (1, -1))])
            h, jac, diag = model.batch(points, spec, return_diagnostics=True)
            expected = trace["H"][offset:offset+len(states)]
            _compare(jac[:n], expected, "SourceFFD analytic Jacobian on trace")
            _compare(h[:n], trace["h_nav"][offset:offset+n], "SourceFFD h on trace")
            for j in range(3):
                i_plus, i_minus = (1 + 2*j)*n, (2 + 2*j)*n
                plus, minus = slice(i_plus, i_plus+n), slice(i_minus, i_minus+n)
                same = np.ones(n, dtype=bool)
                for key in ("tap", "strong_port", "cells"):
                    branch = np.asarray(diag[key]).reshape(len(points), -1)
                    same &= ((branch[:n] == branch[plus]) & (branch[:n] == branch[minus])).all(axis=1)
                fd = (h[plus] - h[minus]) / (2. * step)
                error = np.abs(fd - expected[:, :, j])
                magnitude = np.maximum(np.abs(fd), np.abs(expected[:, :, j]))
                rel = error / (1e-6 + 1e-4 * magnitude)
                invalid = same & (rel > 1.).any(axis=1)
                checked[j] += int(same.sum())
                changed[j] += int((~same).sum())
                failed[j] += int(invalid.sum())
                max_abs[j] = max(max_abs[j], np.max(error[same], initial=0.))
                max_relative[j] = max(max_relative[j], np.max(rel[same], initial=0.))
                omitted = b_prior[offset:offset+n] * (jac[plus, 1, 2] - jac[minus, 1, 2]) / (2. * step)
                max_omitted[j] = max(max_omitted[j], np.max(np.abs(omitted[same]), initial=0.))
                for k in np.flatnonzero(invalid)[:max(0, 12-len(first_failures))]:
                    first_failures.append(dict(index=int(offset+k), state_axis=j,
                                               max_error=float(error[k].max()),
                                               max_ratio=float(rel[k].max())))
        report[str(step)] = dict(checked=checked.tolist(), branch_changes=changed.tolist(),
                                 failures=failed.tolist(), max_abs=max_abs.tolist(),
                                 max_tolerance_ratio=max_relative.tolist(),
                                 max_abs_omitted_b_times_grad_a=max_omitted.tolist(), examples=first_failures)
    passed = all(not sum(row["failures"]) and min(row["checked"]) > 0 for row in report.values())
    result = dict(status="PASS" if passed else "FAIL", finite_difference=report)
    if not passed and raise_on_failure:
        raise ValueError(f"SourceFFD same-branch finite differences failed: {result}")
    return result


def information_barrier(trace, packet, controls, baseline, core, online, model, spec, **kwargs):
    """Perturb current observation and future suffix, with online-only input records."""
    n = len(packet["t"])
    probe = min(n-1, max(1, min(20, n//2)))
    fields = ("prior", "Pprior", "a", "alpha", "beta", "R_ref", "Reff", "mask")
    if "prior_internal" in trace:
        fields += ("prior_internal", "Pprior_internal")
    errors = {}
    for name, start in (("current", probe), ("future", probe+1)):
        stop = min(n, probe+4)
        raw = {k: (value[:stop].copy() if k not in ("x0", "P0") and np.shape(value)[:1] == (n,)
                  else value.copy()) for k, value in packet.items()}
        raw["z"][start:] += np.array([.2, -.1])
        active = {key: value[:stop] for key, value in controls.items()}
        fixed = {key: baseline[key][:stop] for key in ("mask", "Reff")}
        opts = dict(kwargs)
        for key in ("near", "a2_variance"):
            if opts.get(key) is not None:
                opts[key] = opts[key][:stop]
        changed = replay(raw, active, fixed, core, online, model, spec, **opts)
        np.testing.assert_array_equal(changed["mask"], trace["mask"][:stop])
        if name == "current":
            errors[name] = {key: _compare(changed[key][probe], trace[key][probe], key)
                            for key in fields if key != "mask"}
        else:
            errors[name] = {key: _compare(changed[key][:start], trace[key][:start], key)
                            for key in PARITY_FIELDS + ("a", "alpha", "beta", "R_ref")}
    return dict(status="PASS", probe_index=probe, max_abs=errors)


def synthetic_checks():
    """Use an independent posterior precision solve and a constant-cell Schur complement."""
    rng = np.random.default_rng(20261115)
    X = rng.normal(size=(5, 5))
    P = X @ X.T + np.eye(5)
    H = np.array([[.5, .4, 0., 0., 0.], [-.5, .3, -.8, 0., -.8]])
    R = np.array([[.4, .08], [.08, .2]])
    v = np.array([.12, -.23])
    prior = np.zeros(5)

    class Chart:
        @staticmethod
        def wrap(yaw):
            return np.arctan2(np.sin(yaw), np.cos(yaw))

    x, covariance, K, S = _update(Chart, prior, P, H, v, R, True)
    posterior_precision = np.linalg.inv(P) + H.T @ np.linalg.solve(R, H)
    reference_covariance = np.linalg.inv(posterior_precision)
    reference_x = reference_covariance @ H.T @ np.linalg.solve(R, v)
    checks = dict(state=_compare(x, reference_x, "linear five-state posterior"),
                  covariance=_compare(covariance, reference_covariance, "linear posterior covariance"))
    _, C_schmidt, K_schmidt, _ = _update(Chart, prior, P, H, v, R, True, consider=True)
    np.testing.assert_array_equal(K_schmidt[4], 0.)
    checks["schmidt_navigation_gain"] = _compare(K_schmidt[:4], K[:4], "Schmidt nav gain")
    checks["schmidt_cross"] = _compare(C_schmidt[:4, 4], P[:4, 4] - K[:4] @ (H @ P[:, 4]),
                                       "Schmidt cross covariance")
    checks["schmidt_variance"] = _compare(C_schmidt[4, 4], P[4, 4], "Schmidt variance")
    hold, C_hold, K_hold, S_hold = _update(Chart, prior, P, H, v, R, False)
    for lhs, rhs in ((hold, prior), (C_hold, P), (K_hold, np.zeros_like(K)), (S_hold, S)):
        np.testing.assert_array_equal(lhs, rhs)

    # Differentiate the actual conditional affine mean at both signs and zero.
    derivative_errors = []
    for signed in (-.8, 0., .8):
        H_nav = H[:, :4].copy()
        H_nav[1, 2] = signed
        h = np.array([.3, .05])
        means = [_augmented_observation(h, H_nav, b, 1.)[0]
                 for b in (.13 - 1e-4, .13 + 1e-4)]
        _, H_aug = _augmented_observation(h, H_nav, .13, 1.)
        fd = (means[1] - means[0]) / 2e-4
        derivative_errors.append(_compare(fd, np.array([0., signed]), "signed heading mean"))
        derivative_errors.append(_compare(fd, H_aug[:, 4], "signed heading Jacobian"))
    checks["signed_derivative"] = max(derivative_errors)
    process_errors = []
    for alpha in (0., .4, 1.):
        stationary = math.radians(2.)**2
        cross = P[:4, 4]
        b, covariance, propagated = _predict_bias(.13, stationary, cross, np.eye(4), alpha, stationary)
        process_errors.extend((_compare(covariance, stationary, "stationary variance"),
                               _compare(b, alpha * .13, "alpha mean"),
                               _compare(propagated, alpha * cross, "alpha cross covariance")))
    checks["alpha_endpoints_and_stationarity"] = max(process_errors)

    sigma = math.radians(2.)
    sensitivity = np.array([-.4, 2.4, -.9, 1.5])
    white = np.diag(np.array([.8, .7, .64, .55]) * .01)
    I = sensitivity @ np.linalg.solve(white, sensitivity)
    marginalized = white + sigma**2 * np.outer(sensitivity, sensitivity)
    effective = sensitivity @ np.linalg.solve(marginalized, sensitivity)
    checks["static_heading_information"] = _compare(effective, I / (1. + I * sigma**2), "static cell ceiling")
    if not effective < 1. / sigma**2:
        raise ValueError("Static cell information violates the marginal bound")
    return dict(status="PASS", max_abs=checks, static_information=effective, ceiling=1. / sigma**2)

