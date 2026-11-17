"""Targeted M7 implementer checks; importing this file does not execute a replay.

Mother freezes both code hashes before calling run_checks. These are self-checks,
not an independent audit. No evaluator or scoring inputs are accepted.
"""
import hashlib
import importlib.util
import math
from pathlib import Path

import numpy as np

from m7_replay import (ARMS, CONDITION_GYRO, GATE_1D, GATE_2D,
                       condition_gyro, predict_navigation, replay)

TOL = 1e-10
PARITY_FIELDS = ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S")


def code_hashes():
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("m7_replay.py", "check_m7_replay.py")}


def compare(actual, expected, fields=PARITY_FIELDS):
    for key in ("t", "pose_id", "mask"):
        np.testing.assert_array_equal(actual[key], expected[key], err_msg=key)
    errors = {}
    for key in fields:
        np.testing.assert_allclose(actual[key], expected[key], atol=TOL, rtol=0., err_msg=key)
        errors[key] = float(np.max(np.abs(actual[key] - expected[key]), initial=0.))
    return errors


def _close(actual, expected):
    np.testing.assert_allclose(actual, expected, atol=TOL, rtol=0.)


def check_trace(trace, packet, env, arm, *, sigma_rad=0., sigma_b=None,
                q_table=None, fixed_mask=None, reference_R=None, condition="B0"):
    """Recompute predictions, gate decisions, full Joseph and causal history."""
    core, online, spec = (env[k] for k in ("core", "online", "spec"))
    joint = arm in ("H3", "H4")
    injected_N, filter_N = condition_gyro(condition)
    controls = {k: packet[k] for k in ("ds", "gy", "dt")}
    numeric = [v for v in trace.values() if np.asarray(v).dtype.kind in "biuf"]
    if not all(np.isfinite(v).all() for v in numeric):
        raise AssertionError("Nonfinite numeric trace")
    if any(np.asarray(v).dtype.kind == "O" for v in trace.values()):
        raise AssertionError("Object arrays are forbidden")
    np.testing.assert_array_equal(trace["t"], packet["t"])
    np.testing.assert_array_equal(trace["pose_id"], packet["pose_id"])
    assert str(trace["metadata_condition"]) == condition
    assert bool(trace["metadata_q_matches_injection"]) == (injected_N == filter_N)
    assert bool(trace["metadata_report_only"]) == (condition == "L2_GYRO_ARW_Q_B0_STRESS")
    _close(trace["b_g"], trace["x"][:, 3])
    _close(trace["P_bgbg"], trace["P"][:, 3, 3])
    _close(trace["b_g_prior"], trace["prior"][:, 3])
    _close(trace["P_bgbg_prior"], trace["Pprior"][:, 3, 3])
    _close(trace["injected_gyro_N_deg_sqrt_s"], injected_N)
    _close(trace["filter_gyro_N_deg_sqrt_s"], filter_N)
    _close(trace["dt"], packet["dt"])
    threshold = GATE_1D if arm == "H1" else GATE_2D
    _close(trace["threshold"], threshold)
    expected_mask = (np.zeros(len(packet["t"]), bool) if arm == "H0" else
                     trace["nis"] <= threshold if fixed_mask is None else fixed_mask)
    np.testing.assert_array_equal(trace["mask"], expected_mask)
    np.testing.assert_array_equal(trace["s_updated"], trace["mask"] & (arm not in ("H0", "H1")))
    for i in range(len(packet["t"])):
        old_x = packet["x0"] if i == 0 else trace["x"][i - 1]
        old_P = packet["P0"] if i == 0 else trace["P"][i - 1]
        # Independent explicit-Q calculation, rather than the replay wrapper.
        Q_input = np.zeros((3, 3))
        if i:
            Q_input[0, 0] = 2e-5 * abs(float(packet["ds"][i]))
            Q_input[1, 1] = math.radians(filter_N)**2 * float(packet["dt"][i])
            nav, Pnav = core.predict(old_x, old_P, *[float(packet[k][i])
                                      for k in ("ds", "gy", "dt")], Q_input)[:2]
        else:
            nav, Pnav = old_x, old_P
        _close(trace["Q_input"][i], Q_input)
        _close(trace["gyro_Q_rad2"][i], Q_input[1, 1])
        _close(trace["prior"][i], nav)
        _close(trace["Pprior"][i], Pnav)
        rho = np.linalg.norm(old_x[:2] - spec["anchor"][:2])
        _close(trace["rho_before"][i], rho)
        if reference_R is None:
            # Independent direct D5 table calculation, no replay helper reuse.
            if isinstance(sigma_b, dict):
                knots, vals = sigma_b["knots_m"], sigma_b["sigma_b"]
            elif len(sigma_b) == 2 and np.ndim(sigma_b[0]) == 1:
                knots, vals = sigma_b
            else:
                knots, vals = [0., 1.5, 3., 6., 10.], sigma_b
            sigma = np.interp(rho, knots, vals)
            Rref = packet["R"][i].copy()
            Rref[1, 1] += sigma**2
            _close(trace["sigma_b"][i], sigma)
        else:
            Rref = reference_R[i]
        _close(trace["R_ref"][i], Rref)
        hnav, Hnav = (f[0] for f in env["model"].batch(nav[None], spec))
        _close(trace["h_nav"][i], hnav)
        _close(trace["H"][i], Hnav[:1] if arm == "H1" else Hnav)
        prior = trace["prior_aug"][i] if joint else nav
        Pprior = trace["Pprior_aug"][i] if joint else Pnav
        H = trace["H_aug"][i] if joint else trace["H"][i]
        prediction = hnav[:1] if arm == "H1" else hnav.copy()
        if joint:
            alpha = 1. if i == 0 else math.exp(-abs(packet["ds"][i]) -
                abs(core.wrap(packet["gy"][i] - old_x[3] * packet["dt"][i])) / math.radians(10.))
            old_bias = 0. if i == 0 else trace["x_aug"][i - 1, 4]
            old_var = sigma_rad**2 if i == 0 else trace["P_aug"][i - 1, 4, 4]
            old_cross = np.zeros(4) if i == 0 else trace["P_aug"][i - 1, :4, 4]
            F = np.eye(4) if i == 0 else core.transition(old_x, *[packet[k][i] for k in ("ds", "gy", "dt")])[1]
            _close(trace["alpha"][i], alpha)
            _close(prior[4], alpha * old_bias)
            _close(Pprior[4, 4], alpha**2 * old_var + sigma_rad**2 * (1. - alpha**2))
            _close(Pprior[:4, 4], alpha * F @ old_cross)
            _close(H[:, 4], [0., Hnav[1, 2]])
            prediction[1] += Hnav[1, 2] * prior[4]
        _close(trace["h"][i], prediction)
        nu = np.zeros(2) if arm == "H0" else packet["z"][i, :len(prediction)] - prediction - packet["muMB"][i, :len(prediction)]
        _close(trace["nu"][i], nu)
        R = Rref.copy()
        distance = np.linalg.norm(nav[:2] - spec["anchor"][:2])
        _close(trace["distance"][i], distance)
        q, support = 0., False
        if q_table is not None:
            edges, values, supported = q_table
            for lo, hi, val, yes in zip(edges[:-1], edges[1:], values, supported, strict=True):
                if lo <= distance < hi and yes:
                    q, support = val, True
        _close(trace["q_s"][i], q)
        assert bool(trace["q_supported"][i]) == support
        indices = np.flatnonzero(trace["mask"][:i]) if q_table is not None else np.array([], int)
        indices = indices[packet["t"][i] - packet["t"][indices] <= 10.][-100:]
        kernel = np.exp(trace["hazard"][indices] - trace["hazard"][i])
        causal = 2. * np.sum(np.sqrt(q * trace["q_s"][indices]) * kernel)
        _close(trace["causal"][i], causal)
        assert trace["history_n"][i] == len(indices)
        R[1, 1] += q + causal
        if arm == "H1":
            R = R[:1, :1]
        _close(trace["Reff"][i], R)
        S = H @ Pprior @ H.T + R
        S = (S + S.T) / 2.
        _close(trace["S"][i], S)
        nis = 0. if arm == "H0" else float(nu @ np.linalg.inv(S) @ nu)
        _close(trace["nis"][i], nis)
        if trace["mask"][i]:
            # H1 really has one residual and one scalar innovation variance.
            if arm == "H1":
                assert H.shape == (1, 4) and S.shape == (1, 1)
                gain = (Pprior @ H[0])[:, None] / S[0, 0]
            else:
                gain = Pprior @ H.T @ np.linalg.inv(S)
            state = prior + gain @ nu
            state[2] = (state[2] + math.pi) % (2. * math.pi) - math.pi
            A = np.eye(len(prior)) - gain @ H
            post = A @ Pprior @ A.T + gain @ R @ gain.T
            post = (post + post.T) / 2.
        else:
            state, post = prior, Pprior
            gain = np.zeros((len(prior), len(nu)))
            # Explicit rejected-packet invariant, checked separately from Joseph.
            _close(trace["x"][i], nav)
            _close(trace["P"][i], Pnav)
        _close(trace["x"][i], state[:4])
        _close(trace["P"][i], post[:4, :4])
        _close(trace["K"][i], gain[:4])
        if joint:
            _close(trace["x_aug"][i], state)
            _close(trace["P_aug"][i], post)
    return dict(status="PASS", packets=len(packet["t"]), accepted=int(trace["mask"].sum()),
                rejected=int((~trace["mask"]).sum()), observation_dimension=trace["nu"].shape[1])


def check_m6_parity(packet, env, *, fixed_mask, reference_R, sigma_rad, q_table, archived=None):
    """Matched frozen controls/x0/P0/mask/R_ref against the unmodified M6 engine.

    Optional archived maps G0/G1/G1KI to original trace dictionaries. Mother
    checks provenance/grid before passing arrays; this checker checks values.
    """
    parent = Path(__file__).resolve().parent.parent
    candidates = (parent / "G1_GM_THETA_M6_20261116/gm_replay.py",
                  parent / "gm_theta_m6/gm_replay.py")
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise FileNotFoundError("Pinned original M6 replay source was not found")
    spec = importlib.util.spec_from_file_location("m7_check_original_m6", path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    controls = {k: packet[k] for k in ("ds", "gy", "dt")}
    baseline = dict(mask=fixed_mask, Reff=reference_R)
    reports = {}
    for name, new_arm, old_arm, sigma, table in (
            ("G0", "H2", "G0", 0., None), ("G1", "H4", "G1", sigma_rad, None),
            ("G1KI", "H3", "G1", sigma_rad, q_table)):
        expected = original.replay(packet, controls, baseline, *env["native"],
                                   arm=old_arm, sigma_rad=sigma, q_table=table)
        actual = replay(packet, env, new_arm, sigma_rad=sigma, q_table=table,
                        fixed_mask=fixed_mask, reference_R=reference_R, rref_policy="scheduled")
        fields = PARITY_FIELDS + (("x_aug", "P_aug", "prior_aug", "Pprior_aug", "H_aug", "K_aug")
                                  if old_arm == "G1" else ())
        reports[name] = dict(original=compare(actual, expected, fields))
        if archived is not None:
            reports[name]["archive"] = compare(actual, archived[name], fields)
    return reports


def run_checks(packet, env, *, sigma_b, sigma_rad, q_table, fixed_mask,
               reference_R, frozen_code_hashes, q_prime_table, archived=None, condition="B0"):
    """Execute only after Mother freezes code and authorizes checks."""
    if code_hashes() != frozen_code_hashes:
        raise ValueError("Code differs from Mother's frozen hashes")
    report = dict(code_hashes=code_hashes(), own={}, special={})
    traces = {}
    for arm in ARMS:
        kw = dict(sigma_b=sigma_b, sigma_rad=sigma_rad if arm in ("H3", "H4") else 0.,
                  q_table=q_prime_table if arm == "H5P" else q_table if arm in ("H3", "H5") else None,
                  condition=condition)
        trace = traces[arm] = replay(packet, env, arm, **kw)
        report["own"][arm] = check_trace(trace, packet, env, arm, **kw)
    # A z perturbation must have exactly zero effect on DR's state/covariance.
    perturbed = dict(packet, z=packet["z"] + np.array([100., .25]))
    dr = replay(perturbed, env, "H0", sigma_b=sigma_b, condition=condition)
    np.testing.assert_array_equal(dr["x"], traces["H0"]["x"])
    np.testing.assert_array_equal(dr["P"], traces["H0"]["P"])
    assert not dr["mask"].any() and not dr["s_updated"].any()
    report["special"]["DR_z_independence"] = "PASS_EXACT"
    zero = (np.array([0., 1.5, 3., 6., 10.]), np.zeros(4), np.ones(4, bool))
    # Own-R paths must collapse as well as historical scheduled-R paths.
    for name, arm, sigma, table, target in (
            ("GM_sigma0", "H4", 0., None, "H2"),
            ("GMKI_q0", "H3", sigma_rad, zero, "H4"),
            ("KI_q0", "H5", 0., zero, "H2"),
            ("KIP_q0", "H5P", 0., zero, "H2"),
            ("KI_KIP_same_table", "H5P", 0., q_table, "H5"),
            ("GMKI_sigma0", "H3", 0., q_table, "H5")):
        trace = replay(packet, env, arm, sigma_b=sigma_b, sigma_rad=sigma, q_table=table,
                       condition=condition)
        report["special"][name] = compare(trace, traces[target])
    # Force every packet rejected to exercise rejected-state/P invariants even
    # if natural gating happens to accept the entire supplied packet stream.
    reject = np.zeros(len(packet["t"]), bool)
    for arm in ("H1", "H3"):
        kw = dict(sigma_b=sigma_b, sigma_rad=sigma_rad if arm == "H3" else 0.,
                  q_table=q_table if arm == "H3" else None, fixed_mask=reject, condition=condition)
        rejected = replay(packet, env, arm, **kw)
        report["special"][arm + "_reject_all"] = check_trace(rejected, packet, env, arm, **kw)
    # Nonconstant artificial sigma table makes the previous-posterior lookup
    # test observable even when the frozen production fold is flat at .005.
    varying = [.005, .011, .024, .053, .120]
    own = replay(packet, env, "H2", sigma_b=varying, fixed_mask=fixed_mask, condition=condition)
    report["special"]["own_R_previous_posterior_fixed_mask"] = check_trace(
        own, packet, env, "H2", sigma_b=varying, fixed_mask=fixed_mask, condition=condition)
    report["m6_scheduled_parity"] = (check_m6_parity(
        packet, env, fixed_mask=fixed_mask, reference_R=reference_R,
        sigma_rad=sigma_rad, q_table=q_table, archived=archived) if condition == "B0"
        else "NOT_APPLICABLE_NON_B0_Q_OR_SENSOR_CONDITION")
    report["status"] = "PASS_IMPLEMENTER_CHECKS"
    return report


def _synthetic_case(n=9, step=.2):
    """Small analytic model; never imports native models, sensors or evidence."""
    from types import SimpleNamespace

    def wrap(value):
        return (np.asarray(value) + np.pi) % (2. * np.pi) - np.pi

    def transition(state, ds, gyro, dt):
        F = np.eye(4)
        F[2, 3] = -dt
        prior = F @ state
        prior[0] += ds
        prior[2] = wrap(prior[2] + gyro)
        # Nonzero XY entries ensure an incorrect yaw-only P adjustment fails.
        G = np.array([[1., .2, 0.], [.3, -.1, 0.], [0., 1., 0.], [0., 0., 1.]])
        return prior, F, G

    def predict(state, P, ds, gyro, dt, Q):
        prior, F, G = transition(state, ds, gyro, dt)
        covariance = F @ P @ F.T + G @ Q @ G.T
        return prior, (covariance + covariance.T) / 2., F, G

    core = SimpleNamespace(wrap=wrap, transition=transition, predict=predict)

    def old_predict(core, state, P, index, controls):
        if index == 0:
            return state, P
        ds, gyro, dt = (float(controls[k][index]) for k in ("ds", "gy", "dt"))
        Q = np.diag([2e-5 * abs(ds), math.radians(.015)**2 * dt, 0.])
        return core.predict(state, P, ds, gyro, dt, Q)[:2]

    def old_joseph(prior, Pprior, H, nu, R, accepted, weight):
        assert weight == 1.
        S = H @ Pprior @ H.T + R
        S = (S + S.T) / 2.
        if not accepted:
            return prior, Pprior, np.zeros((4, 2)), S
        K = np.linalg.solve(S, H @ Pprior).T
        state = prior + K @ nu
        state[2] = wrap(state[2])
        A = np.eye(4) - K @ H
        covariance = A @ Pprior @ A.T + K @ R @ K.T
        return state, (covariance + covariance.T) / 2., K, S

    H = np.array([[1., .1, 0., 0.], [.1, .2, -.8, 0.]])

    def batch(states, spec):
        return states @ H.T + np.array([10., .2]), np.broadcast_to(H, (len(states), 2, 4)).copy()

    times = np.arange(n, dtype=float) * step
    dt = np.r_[0., np.diff(times)]
    ds = np.r_[0., np.full(n - 1, .04)]
    gy = np.r_[0., np.full(n - 1, .005)]
    initial = np.array([1., .05, .1, 0.])
    states = np.tile(initial, (n, 1))
    states[:, 0] += np.cumsum(ds)
    states[:, 2] += np.cumsum(gy)
    z = batch(states, {})[0]
    z += np.column_stack((.006 * np.sin(np.arange(n)), .008 * np.cos(np.arange(n))))
    packet = dict(t=times, pose_id=np.arange(n), z=z, muMB=np.zeros((n, 2)),
                  muBASE=np.zeros((n, 2)), R=np.tile(np.diag([.04**2, .05**2]), (n, 1, 1)),
                  D=np.zeros(n), ds=ds, gy=gy, dt=dt, x0=initial,
                  P0=np.diag([.1**2, .1**2, math.radians(5.)**2, math.radians(.1)**2]))
    env = dict(core=core, online=SimpleNamespace(predict=old_predict, joseph=old_joseph),
               model=SimpleNamespace(batch=batch), spec={"anchor": (10., 0., 2.65)})
    return packet, env


def run_synthetic_checks():
    """Code-only unit checks. No native loading, RF inputs or research replay."""
    packet, env = _synthetic_case()
    sigma_b = [.005, .011, .024, .053, .120]
    sigma = math.radians(2.)
    table = (np.array([0., 1.5, 3., 6., 10.]),
             np.array([.0001, .0002, .0003, .0004]), np.ones(4, bool))
    zero = (table[0], np.zeros(4), table[2])
    report = dict(classification="SYNTHETIC_IMPLEMENTATION_ONLY", conditions={}, special={})
    for condition in CONDITION_GYRO:
        traces = {}
        checks = {}
        for arm in ARMS:
            kwargs = dict(sigma_b=sigma_b, sigma_rad=sigma if arm in ("H3", "H4") else 0.,
                          q_table=table if arm in ("H3", "H5", "H5P") else None,
                          condition=condition)
            trace = traces[arm] = replay(packet, env, arm, **kwargs)
            checks[arm] = check_trace(trace, packet, env, arm, **kwargs)
            expected_role = ("NOT_APPLICABLE_DR" if arm == "H0" else "RANGE_ONLY"
                             if arm == "H1" else "RANGE_AND_POLARIZATION")
            assert trace["metadata_observation_role"].item() == expected_role
            if arm in ("H3", "H5", "H5P"):
                expected_bins = np.searchsorted(table[0], trace["distance"], side="right") - 1
                np.testing.assert_array_equal(trace["q_bin"], expected_bins)
            covariance = trace["P_aug"] if arm in ("H3", "H4") else trace["P"]
            _close(covariance, covariance.swapaxes(-1, -2))
            assert np.linalg.eigvalsh(covariance).min() >= -TOL
        for name, arm, scale, q, target in (
                ("GM_sigma0", "H4", 0., None, "H2"),
                ("GMKI_q0", "H3", sigma, zero, "H4"),
                ("GMKI_sigma0", "H3", 0., table, "H5"),
                ("KI_q0", "H5", 0., zero, "H2"),
                ("KIP_q0", "H5P", 0., zero, "H2"),
                ("KI_KIP_same_table", "H5P", 0., table, "H5")):
            actual = replay(packet, env, arm, sigma_b=sigma_b, sigma_rad=scale,
                            q_table=q, condition=condition)
            checks[name] = compare(actual, traces[target])
        altered = dict(packet, z=packet["z"] + [50., .3])
        other = replay(altered, env, "H0", sigma_b=sigma_b, condition=condition)
        np.testing.assert_array_equal(other["x"], traces["H0"]["x"])
        np.testing.assert_array_equal(other["P"], traces["H0"]["P"])
        checks["DR_z_independence"] = "PASS_EXACT"
        reject = np.zeros(len(packet["t"]), bool)
        for arm in ("H1", "H3", "H5P"):
            kwargs = dict(sigma_b=sigma_b, sigma_rad=sigma if arm == "H3" else 0.,
                          q_table=table if arm in ("H3", "H5P") else None,
                          fixed_mask=reject, condition=condition)
            rejected = replay(packet, env, arm, **kwargs)
            checks[arm + "_reject_all"] = check_trace(rejected, packet, env, arm, **kwargs)
        # Current-observation and future-observation changes cannot modify the
        # current prior/covariance/noise lookup; later states may legitimately differ.
        altered = dict(packet, z=packet["z"].copy())
        altered["z"][4:] += [2., .3]
        other = replay(altered, env, "H3", sigma_b=sigma_b, sigma_rad=sigma,
                       q_table=table, condition=condition)
        for key in ("x", "P", "mask", "R_ref", "Reff"):
            np.testing.assert_array_equal(other[key][:4], traces["H3"][key][:4])
        for key in ("prior", "Pprior", "a", "alpha", "R_ref", "Reff"):
            np.testing.assert_array_equal(other[key][4], traces["H3"][key][4])
        checks["observation_causality"] = "PASS_EXACT"
        report["conditions"][condition] = checks
    # Compare noise injection through the independent synthetic G, preserving
    # XY/yaw off-diagonal entries and zero gyro-bias random walk.
    controls = {k: packet[k] for k in ("ds", "gy", "dt")}
    state, P = packet["x0"], packet["P0"]
    _, baseline = predict_navigation(env["core"], env["online"], state, P, 1, controls, .015)
    _, matched = predict_navigation(env["core"], env["online"], state, P, 1, controls, .060)
    _, _, G = env["core"].transition(state, *[packet[k][1] for k in ("ds", "gy", "dt")])
    difference = np.outer(G[:, 1], G[:, 1]) * (math.radians(.060)**2 - math.radians(.015)**2) * packet["dt"][1]
    _close(matched - baseline, difference)
    _, baseline_again = predict_navigation(env["core"], env["online"], state, P, 1, controls, .015)
    np.testing.assert_array_equal(baseline_again, baseline)
    report["special"]["explicit_GQG_difference_no_global_leak"] = "PASS"
    # Both the 100-accepted-packet cap and 10-second expiry are observable.
    for name, n, step in (("history_cap", 130, .05), ("history_expiry", 9, 2.)):
        local, local_env = _synthetic_case(n, step)
        mask = np.ones(n, bool)
        trace = replay(local, local_env, "H5P", sigma_b=sigma_b,
                       q_table=table, fixed_mask=mask)
        report["special"][name] = check_trace(trace, local, local_env, "H5P",
                                              sigma_b=sigma_b, q_table=table, fixed_mask=mask)
        if name == "history_cap":
            assert trace["history_n"][-1] == 100
        else:
            assert trace["history_n"][-1] == 5
    for condition, bad in (("B0", .060), ("L2_GYRO_ARW", .015)):
        try:
            replay(packet, env, "H0", sigma_b=sigma_b, condition=condition,
                   filter_gyro_N_deg_sqrt_s=bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Contradictory condition/Q was accepted")
    report["special"]["contradictory_condition_rejected"] = "PASS"
    try:
        replay(dict(packet, truth=np.zeros((len(packet["t"]), 3))), env, "H0", sigma_b=sigma_b)
    except ValueError:
        pass
    else:
        raise AssertionError("Evaluator fields entered the online replay")
    report["special"]["evaluator_fields_rejected"] = "PASS"
    report.update(status="PASS_SYNTHETIC_IMPLEMENTATION_CHECKS",
                  native_parity="NOT_RUN", research_data_generation="NOT_RUN",
                  research_replay="NOT_RUN")
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(run_synthetic_checks(), ensure_ascii=False, allow_nan=False))
