"""M7 online-only replay. Evaluation, scoring and run authorization live outside this module.

H0: prediction only; H1: scalar range EKF; H2: E0-LORO; H3: GM+KI;
H4: GM; H5: residual KI; H5P: refitted KI (the caller supplies q_s prime).
Scheduled R_ref is retained solely for frozen M6 parity.
The caller supplies the frozen route-specific D5 sigma_b values and initial state.
"""
from collections import deque
import json
import math
from pathlib import Path
import sys

import numpy as np

GATE_2D = 9.210340371976184
GATE_1D = 6.6348966010212145
KNOTS = np.array([0., 1.5, 3., 6., 10.])
YAW_LENGTH_RAD = math.radians(10.)
ARMS = ("H0", "H1", "H2", "H3", "H4", "H5", "H5P")
ALIASES = {"G0": "H2", "G1KI": "H3", "G1_KI": "H3", "G1": "H4",
           "H5'": "H5P", "H5′": "H5P"}
# (injected gyro N, filter gyro N), in degrees/sqrt(second).
CONDITION_GYRO = {"B0": (.015, .015), "L2_GYRO_ARW": (.060, .060),
                  "L2_GYRO_ARW_Q_B0_STRESS": (.060, .015)}


def condition_gyro(condition, injected_gyro_N_deg_sqrt_s=None,
                   filter_gyro_N_deg_sqrt_s=None):
    """Resolve the preregistered pair, rejecting contradictory run arguments."""
    if condition not in CONDITION_GYRO:
        raise ValueError("Unknown M7 gyro/Q condition")
    injected, filtered = CONDITION_GYRO[condition]
    for supplied, expected in ((injected_gyro_N_deg_sqrt_s, injected),
                                (filter_gyro_N_deg_sqrt_s, filtered)):
        if supplied is not None and (not math.isfinite(supplied) or float(supplied) != expected):
            raise ValueError("Gyro N differs from the frozen condition")
    return injected, filtered


def input_process_covariance(ds, dt, filter_gyro_N_deg_sqrt_s, *, initial=False):
    """Only gyro-angle Q changes; distance and zero bias-RW retain native values."""
    if not np.isfinite([ds, dt, filter_gyro_N_deg_sqrt_s]).all():
        raise ValueError("Nonfinite process-noise specification")
    if filter_gyro_N_deg_sqrt_s <= 0. or dt < 0. or (not initial and dt <= 0.):
        raise ValueError("Invalid process-noise specification")
    if initial:
        return np.zeros((3, 3))
    return np.diag([2e-5 * abs(float(ds)),
                    math.radians(filter_gyro_N_deg_sqrt_s)**2 * float(dt), 0.])


def predict_navigation(core, online, x, P, i, controls, filter_gyro_N_deg_sqrt_s):
    """Use native B0 arithmetic exactly; pass explicit Q for matched L2.

    No module globals or shared native predictor settings are modified.
    """
    if i == 0:
        return x, P
    ds, gy, dt = (float(controls[k][i]) for k in ("ds", "gy", "dt"))
    Q = input_process_covariance(ds, dt, filter_gyro_N_deg_sqrt_s)
    if filter_gyro_N_deg_sqrt_s == .015:
        return online.predict(core, x, P, i, controls)
    return core.predict(x, P, ds, gy, dt, Q)[:2]


def load_environment(base_path=None):
    """Load only native model/code assets, never packets or evaluator arrays."""
    if base_path is None:
        base_path = Path(__file__).resolve().parent.parent / "G1_INT_DIAG_001_20261115/RUN_CONTRACT.json"
    base = json.loads(Path(base_path).read_bytes())
    native_path = Path(base["native"])
    sys.path.insert(0, str(native_path / "src"))
    from qclean_uwb.fp_sc.e0_baseline import SPEC, load_original_model
    if SPEC != {"anchor": (10., 0., 2.65), "robot_z_m": .45, "mount_deg": 0.}:
        raise ValueError("Unexpected native geometry")
    core, online, model, hashes = load_original_model(native_path)
    return dict(native=(core, online, model, SPEC.copy()), core=core, online=online,
                model=model, spec=SPEC.copy(), native_source_hashes=hashes,
                base_path=str(base_path))


def _q_table(table):
    if table is None:
        return None
    edges, values, supported = (np.asarray(a) for a in table)
    if (values.ndim != 1 or not len(values) or edges.shape != (len(values) + 1,)
            or supported.shape != values.shape or supported.dtype.kind != "b"
            or not np.isfinite(edges).all() or not np.all(np.diff(edges) > 0.)
            or not np.isfinite(values).all() or np.any(values < 0.)
            or np.any(values[~supported] != 0.)):
        raise ValueError("Invalid frozen additive-s variance table")
    return edges, values, supported


def _sigma_table(value, env):
    if value is None:
        value = env.get("sigma_b")
    if value is None:
        raise ValueError("Own R_ref requires frozen route-specific sigma_b")
    if isinstance(value, dict):
        knots, values = value["knots_m"], value["sigma_b"]
    elif len(value) == 2 and np.ndim(value[0]) == 1:
        knots, values = value
    else:
        knots, values = KNOTS, value
    knots, values = np.asarray(knots, float), np.asarray(values, float)
    if (knots.ndim != 1 or len(knots) < 2 or values.shape != knots.shape
            or not np.isfinite(knots).all() or not np.all(np.diff(knots) > 0.)
            or not np.isfinite(values).all() or np.any(values < 0.)):
        raise ValueError("Invalid frozen D5 sigma_b lookup")
    return knots, values


def _packet(packet):
    n = len(packet["t"])
    shapes = dict(t=(n,), pose_id=(n,), z=(n, 2), muMB=(n, 2), muBASE=(n, 2),
                  R=(n, 2, 2), D=(n,), x0=(4,), P0=(4, 4), ds=(n,), gy=(n,), dt=(n,))
    if set(packet) != set(shapes):
        raise ValueError("Online packet must contain only the frozen candidate keys")
    for key, shape in shapes.items():
        a = np.asarray(packet[key])
        if a.shape != shape or a.dtype.kind not in "biuf" or not np.isfinite(a).all():
            raise ValueError(f"Invalid online packet field {key}")
    if not n or np.any(np.diff(packet["t"]) <= 0.):
        raise ValueError("Packet times must increase")
    if not np.array_equal(packet["dt"], np.r_[0., np.diff(packet["t"])]):
        raise ValueError("Control dt must match packet times")
    np.linalg.cholesky(packet["R"])
    return n


def _joseph(core, prior, Pprior, H, nu, R, accepted):
    projected = H @ Pprior
    S = projected @ H.T + R
    S = (S + S.T) * .5
    K = np.zeros((len(prior), len(nu)))
    if not accepted:
        return prior, Pprior, K, S
    K = np.linalg.solve(S, projected).T
    x = prior + K @ nu
    x[2] = core.wrap(x[2])
    A = np.eye(len(prior)) - K @ H
    P = A @ Pprior @ A.T + K @ R @ K.T
    return x, (P + P.T) * .5, K, S


def replay(packet, env, arm, *, sigma_rad=0., q_table=None, fixed_mask=None,
           reference_R=None, rref_policy="own", sigma_b=None, gate_threshold=None,
           condition="B0", injected_gyro_N_deg_sqrt_s=None,
           filter_gyro_N_deg_sqrt_s=None):
    """Replay from own x0/P0; an optional mask controls updates, never R lookup.

    Own R_ref: packet.R + diag(0, interp(previous posterior range, D5)^2).
    GM uses signed H_s,psi, stationary sigma_rad^2, and condition-specific Q.
    KI looks up own predicted-prior distance and retains only accepted history
    within 10 seconds, capped at 100 packets. muMB remains packet-frozen.
    """
    arm = ALIASES.get(arm, arm)
    if arm not in ARMS or not math.isfinite(sigma_rad) or sigma_rad < 0.:
        raise ValueError("Invalid arm or GM scale")
    injected_N, filter_N = condition_gyro(condition, injected_gyro_N_deg_sqrt_s,
                                         filter_gyro_N_deg_sqrt_s)
    n = _packet(packet)
    core, online, model, spec = (env[k] for k in ("core", "online", "model", "spec"))
    joint = arm in ("H3", "H4")
    if q_table is not None and arm not in ("H3", "H5", "H5P"):
        raise ValueError("KI table is allowed only for H3/H5/H5P")
    q_table = _q_table(q_table)
    if arm not in ("H3", "H4") and sigma_rad != 0.:
        raise ValueError("Only H3/H4 carry heading bias")
    if fixed_mask is not None:
        fixed_mask = np.asarray(fixed_mask)
        if fixed_mask.shape != (n,) or fixed_mask.dtype.kind != "b":
            raise ValueError("Fixed mask must be a boolean packet-grid array")
    threshold = GATE_1D if arm == "H1" else GATE_2D
    if gate_threshold is not None:
        if float(gate_threshold) != threshold:
            raise ValueError("Gate threshold differs from frozen arm threshold")
    if rref_policy == "own":
        if reference_R is not None:
            raise ValueError("Own policy does not accept a scheduled reference_R")
        knots, sigma_values = _sigma_table(sigma_b, env)
    elif rref_policy == "scheduled":
        reference_R = np.asarray(reference_R)
        if (reference_R.shape != (n, 2, 2) or not np.isfinite(reference_R).all()):
            raise ValueError("Scheduled policy requires aligned reference_R")
        np.linalg.cholesky(reference_R)
    else:
        raise ValueError("rref_policy must be own or scheduled")
    controls = {key: packet[key] for key in ("ds", "gy", "dt")}
    x, P = packet["x0"].copy(), packet["P0"].copy()
    stationary = sigma_rad**2
    if joint:
        x, P = np.r_[x, 0.], np.pad(P, ((0, 1), (0, 1)))
        P[4, 4] = stationary
    arc, yaw = 0., 0.
    past = deque(maxlen=100)
    rows = []
    for i, time in enumerate(packet["t"]):
        rho_before = math.hypot(*(x[:2] - spec["anchor"][:2]))
        local_sigma_b = float(np.interp(rho_before, knots, sigma_values)) if rref_policy == "own" else 0.
        reference = packet["R"][i].copy() if rref_policy == "own" else reference_R[i].copy()
        if rref_policy == "own":
            reference[1, 1] += local_sigma_b**2
        Q_input = input_process_covariance(float(controls["ds"][i]), float(controls["dt"][i]),
                                           filter_N, initial=i == 0)
        nav, Pnav = predict_navigation(core, online, x[:4], P[:4, :4], i, controls, filter_N)
        alpha = 1.
        if i:
            ds, gy, dt = (float(controls[k][i]) for k in ("ds", "gy", "dt"))
            turn = abs(float(core.wrap(gy - x[3] * dt)))
            arc += abs(ds)
            yaw += turn
            alpha = math.exp(-abs(ds) - turn / YAW_LENGTH_RAD)
        hazard = arc + yaw / YAW_LENGTH_RAD
        distance = math.hypot(*(nav[:2] - spec["anchor"][:2]))
        h, H = (field[0] for field in model.batch(nav[None], spec))
        a = float(H[1, 2])
        q_s, supported, q_bin = 0., False, -1
        if q_table is not None:
            edges, values, support = q_table
            idx = np.searchsorted(edges, distance, side="right") - 1
            q_bin = int(idx)
            if 0 <= idx < len(values) and support[idx]:
                q_s, supported = float(values[idx]), True
        while past and time - past[0][0] > 10.:
            past.popleft()
        own_info = a**2 / reference[1, 1]
        information, causal = own_info, 0.
        for _, old_hazard, old_q, old_info in past:
            kernel = math.exp(old_hazard - hazard)
            information += kernel * old_info
            causal += 2. * math.sqrt(q_s * old_q) * kernel
        history_n = len(past)
        R = reference.copy()
        R[1, 1] += q_s
        R[1, 1] += causal
        if joint:
            F = core.transition(x[:4], ds, gy, dt)[1] if i else np.eye(4)
            cross = alpha * (F @ P[:4, 4])
            prior = np.r_[nav, alpha * x[4]]
            Pprior = np.empty((5, 5))
            Pprior[:4, :4] = Pnav
            Pprior[:4, 4] = Pprior[4, :4] = cross
            Pprior[4, 4] = alpha**2 * P[4, 4] + stationary * (1. - alpha**2)
            prediction = h + np.array([0., a * prior[4]])
            H_internal = np.column_stack((H, (0., a)))
        else:
            prior, Pprior, prediction, H_internal = nav, Pnav, h, H
        if arm == "H1":
            prediction, H_internal, R = prediction[:1], H_internal[:1], R[:1, :1]
        nu = (np.zeros(2) if arm == "H0" else
              packet["z"][i, :len(prediction)] - prediction - packet["muMB"][i, :len(prediction)])
        Sgate = H_internal @ Pprior @ H_internal.T + R
        Sgate = (Sgate + Sgate.T) * .5
        nis = 0. if arm == "H0" else float(nu @ np.linalg.solve(Sgate, nu))
        accepted = False if arm == "H0" else bool(nis <= threshold if fixed_mask is None else fixed_mask[i])
        if not joint and arm != "H1":
            x, P, K, S = online.joseph(prior, Pprior, H_internal, nu, R, accepted, 1.)
        else:
            x, P, K, S = _joseph(core, prior, Pprior, H_internal, nu, R, accepted)
        if accepted and q_table is not None:
            past.append((time, hazard, q_s, own_info))
        row = dict(x=x[:4].copy(), P=P[:4, :4].copy(), prior=nav.copy(), Pprior=Pnav.copy(),
                   h=prediction, h_nav=h, H=H[:len(prediction)], K=K[:4], Reff=R, nu=nu, S=S,
                   Knu=K[:4] @ nu, a=a, g=abs(a), alpha=alpha, beta=1., I_cell=information,
                   distance=distance, rho_before=rho_before, sigma_b=local_sigma_b,
                   arc=arc, yaw=yaw, hazard=hazard, sigma_theta_rad=sigma_rad,
                   V=q_s, causal=causal, q_s=q_s, q_bin=q_bin,
                   q_supported=supported, history_n=history_n,
                   s_infl=(reference[1, 1] + q_s + causal) / reference[1, 1],
                   b_theta=float(x[4]) if joint else 0., b_theta_prior=float(prior[4]) if joint else 0.,
                   b_g=float(x[3]), P_bgbg=float(P[3, 3]), b_g_prior=float(nav[3]),
                   P_bgbg_prior=float(Pnav[3, 3]), injected_gyro_N_deg_sqrt_s=injected_N,
                   filter_gyro_N_deg_sqrt_s=filter_N, Q_input=Q_input,
                   gyro_Q_rad2=float(Q_input[1, 1]), dt=float(controls["dt"][i]),
                   nis=nis, threshold=threshold, mask=accepted,
                   s_updated=accepted and arm not in ("H0", "H1"), R_ref=reference)
        if joint:
            row.update(x_aug=x.copy(), P_aug=P.copy(), prior_aug=prior, Pprior_aug=Pprior,
                       H_aug=H_internal, K_aug=K, x_internal=x.copy(), P_internal=P.copy(),
                       prior_internal=prior, Pprior_internal=Pprior, H_internal=H_internal, K_internal=K)
        rows.append(row)
    trace = {key: np.stack([row[key] for row in rows]) for key in rows[0]}
    trace.update(t=packet["t"].copy(), pose_id=packet["pose_id"].copy(),
                 metadata_arm=np.array(arm), metadata_rref_policy=np.array(rref_policy),
                 metadata_observation_role=np.array("NOT_APPLICABLE_DR" if arm == "H0"
                     else "RANGE_ONLY" if arm == "H1" else "RANGE_AND_POLARIZATION"),
                 metadata_gate_mode=np.array("own" if fixed_mask is None else "fixed"),
                 metadata_condition=np.array(condition),
                 metadata_q_matches_injection=np.array(injected_N == filter_N),
                 metadata_report_only=np.array(condition == "L2_GYRO_ARW_Q_B0_STRESS"))
    return trace
