"""M8 Step 1 replay: M7 recursion generalised to  R_ss = W_i + V_i + 2*sum_j sqrt(V_i V_j) k_ij
with optional normalised GM state eta (loading a_i*sigma_theta(rho_i)).

Online-only: receives the online packet, the frozen native model, frozen tables and condition.
No evaluator/truth input.  M7 helpers (Q, prediction, Joseph) are imported unchanged.

white : "packet"  -> W_i = packet R_ss + sigma_b(rho_before)^2   (M7 convention, parity modes)
        "model"   -> W_i = c1(rho)a^2 + c0(rho)  (F0)  |  0 (F1, F2)   [packet R_ss and sigma_b^2 NOT used]
corr  : None | "q_table" (M7 q_s, parity) | "C" (c1 a^2 + c0, F1) | "c0" (F2 residual)
gm    : None | ("const", sigma_rad) (H3 parity, normalised) | ("table",) (F2: sqrt(c1(rho)))
"""
from collections import deque
import math
import numpy as np
import m7_replay as R7


def _lookup(edges, values, distance):
    idx = int(np.searchsorted(edges, distance, side="right") - 1)
    idx = min(max(idx, 0), len(values) - 1)          # outside [0,10): hold end bin (exposure reported)
    return float(values[idx]), idx, bool(0. <= distance < edges[-1])


def replay_m8(packet, env, arm, *, table, sigma_b, condition, white, corr=None, gm=None,
              q_table=None, fixed_mask=None, mu_s_fn=None, a_fn=None):
    injected_N, filter_N = R7.condition_gyro(condition)
    n = R7._packet(packet)
    core, online, model, spec = (env[k] for k in ("core", "online", "model", "spec"))
    knots, sigma_values = R7._sigma_table(sigma_b, env)
    edges = np.asarray(table["edges"], float)
    c1v, c0v = np.asarray(table["c1"], float), np.asarray(table["c0"], float)
    if q_table is not None:
        q_table = R7._q_table(q_table)
    if fixed_mask is not None:
        fixed_mask = np.asarray(fixed_mask, bool)
        assert fixed_mask.shape == (n,)
    joint = gm is not None
    controls = {k: packet[k] for k in ("ds", "gy", "dt")}
    x, P = packet["x0"].copy(), packet["P0"].copy()
    if joint:
        x, P = np.r_[x, 0.], np.pad(P, ((0, 1), (0, 1)))
        P[4, 4] = 1.                                   # normalised eta, stationary variance 1
    arc, yaw = 0., 0.
    past = deque(maxlen=100)
    rows = []
    for i, time in enumerate(packet["t"]):
        rho_before = math.hypot(*(x[:2] - spec["anchor"][:2]))
        local_sigma_b = float(np.interp(rho_before, knots, sigma_values))
        reference = packet["R"][i].copy()
        reference[1, 1] += local_sigma_b**2            # M7 own R_ref (used for W only in "packet" mode)
        Q_input = R7.input_process_covariance(float(controls["ds"][i]), float(controls["dt"][i]),
                                              filter_N, initial=i == 0)
        nav, Pnav = R7.predict_navigation(core, online, x[:4], P[:4, :4], i, controls, filter_N)
        alpha = 1.
        if i:
            ds, gy, dt = (float(controls[k][i]) for k in ("ds", "gy", "dt"))
            turn = abs(float(core.wrap(gy - x[3] * dt)))
            arc += abs(ds)
            yaw += turn
            alpha = math.exp(-abs(ds) - turn / R7.YAW_LENGTH_RAD)
        hazard = arc + yaw / R7.YAW_LENGTH_RAD
        distance = math.hypot(*(nav[:2] - spec["anchor"][:2]))
        h, H = (field[0] for field in model.batch(nav[None], spec))
        a = float(H[1, 2]) if a_fn is None else float(a_fn(nav))
        c1, tbin, in_range = _lookup(edges, c1v, distance)
        c0 = float(c0v[tbin])
        # ---- white base W_i
        if white == "packet":
            W = reference[1, 1]
        elif white == "model":
            W = (c1 * a * a + c0) if arm == "F0" else 0.
        else:
            raise ValueError("white mode")
        # ---- correlated component V_i
        if corr is None:
            V, q_supported = 0., False
        elif corr == "q_table":
            e_, v_, s_ = q_table
            idx = np.searchsorted(e_, distance, side="right") - 1
            V, q_supported = ((float(v_[idx]), True) if 0 <= idx < len(v_) and s_[idx] else (0., False))
        elif corr == "C":
            V, q_supported = c1 * a * a + c0, True
        elif corr == "c0":
            V, q_supported = c0, True
        else:
            raise ValueError("corr mode")
        while past and time - past[0][0] > 10.:
            past.popleft()
        causal = 0.
        for _, old_hazard, old_V in past:
            causal += 2. * math.sqrt(V * old_V) * math.exp(old_hazard - hazard)
        history_n = len(past)
        R = reference.copy()
        R[1, 1] = W + V + causal
        if joint:
            load = gm[1] if gm[0] == "const" else math.sqrt(c1)
            F = core.transition(x[:4], ds, gy, dt)[1] if i else np.eye(4)
            cross = alpha * (F @ P[:4, 4])
            prior = np.r_[nav, alpha * x[4]]
            Pprior = np.empty((5, 5))
            Pprior[:4, :4] = Pnav
            Pprior[:4, 4] = Pprior[4, :4] = cross
            Pprior[4, 4] = alpha**2 * P[4, 4] + (1. - alpha**2)
            prediction = h + np.array([0., a * load * prior[4]])
            H_internal = np.column_stack((H, (0., a * load)))
        else:
            load = 0.
            prior, Pprior, prediction, H_internal = nav, Pnav, h, H
        muMB_i = packet["muMB"][i]
        if mu_s_fn is not None:
            ov = mu_s_fn(nav, distance, i)
            if ov is not None:
                muMB_i = np.array([muMB_i[0], ov])
        nu = packet["z"][i] - prediction - muMB_i
        Sgate = H_internal @ Pprior @ H_internal.T + R
        Sgate = (Sgate + Sgate.T) * .5
        nis = float(nu @ np.linalg.solve(Sgate, nu))
        accepted = bool(nis <= R7.GATE_2D) if fixed_mask is None else bool(fixed_mask[i])
        if not joint:
            x, P, K, S = online.joseph(prior, Pprior, H_internal, nu, R, accepted, 1.)
        else:
            x, P, K, S = R7._joseph(core, prior, Pprior, H_internal, nu, R, accepted)
        if accepted and corr is not None:
            past.append((time, hazard, V))
        rows.append(dict(x=x[:4].copy(), P=P[:4, :4].copy(), prior=nav.copy(), Pprior=Pnav.copy(),
                         H=H, K=K[:4], Reff=R, nu=nu, S=S, a=a, distance=distance, rho_before=rho_before,
                         sigma_b=local_sigma_b, arc=arc, yaw=yaw, hazard=hazard, W=W, V=V, causal=causal,
                         c1=c1, c0=c0, tbin=tbin, in_table_range=in_range, q_supported=q_supported,
                         history_n=history_n, nis=nis, threshold=R7.GATE_2D, mask=accepted,
                         s_infl=R[1, 1] / reference[1, 1], alpha=alpha, gm_load=load,
                         eta=float(x[4]) if joint else 0., P_eta=float(P[4, 4]) if joint else 0.,
                         b_theta=float(x[4]) * load if joint else 0.,
                         b_g=float(x[3]), P_bgbg=float(P[3, 3]), b_g_prior=float(nav[3]),
                         P_bgbg_prior=float(Pnav[3, 3]), injected_gyro_N_deg_sqrt_s=injected_N,
                         filter_gyro_N_deg_sqrt_s=filter_N, gyro_Q_rad2=float(Q_input[1, 1]),
                         dt=float(controls["dt"][i]), R_ref=reference,
                         P_aug=P.copy() if joint else np.zeros((5, 5))))
    trace = {key: np.stack([row[key] for row in rows]) for key in rows[0]}
    trace.update(t=packet["t"].copy(), pose_id=packet["pose_id"].copy(), metadata_arm=np.array(arm),
                 metadata_rref_policy=np.array("own"),
                 metadata_observation_role=np.array("RANGE_AND_POLARIZATION"),
                 metadata_gate_mode=np.array("own" if fixed_mask is None else "fixed"),
                 metadata_condition=np.array(condition),
                 metadata_q_matches_injection=np.array(injected_N == filter_N),
                 metadata_report_only=np.array(condition == "L2_GYRO_ARW_Q_B0_STRESS"))
    return trace


ARM_MODES = {"F0": dict(white="model", corr=None, gm=None),
             "F1": dict(white="model", corr="C", gm=None),
             "F2": dict(white="model", corr="c0", gm=("table",))}
