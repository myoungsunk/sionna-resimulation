"""M6 fixed-gate replay with signed heading-equivalent polarization bias."""

from collections import deque
import math

import numpy as np


YAW_LENGTH_RAD = math.radians(10.)
HISTORY_SECONDS = 10.
HISTORY_LIMIT = 100
ARMS = ("G0", "G1", "G2", "G3", "G4", "G5psi", "G5y")
PARITY_FIELDS = ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S")


def _validated_tables(q_table, sigma_table):
    if q_table is not None:
        edges, values, supported = (np.asarray(a) for a in q_table)
        if (values.ndim != 1 or len(values) == 0 or edges.shape != (len(values) + 1,)
                or supported.shape != values.shape or supported.dtype.kind != "b"
                or not np.isfinite(edges).all() or not np.all(np.diff(edges) > 0.)
                or not np.isfinite(values).all() or np.any(values < 0.)
                or np.any(values[~supported] != 0.)):
            raise ValueError("Invalid frozen additive-s variance table")
        q_table = edges, values, supported
    if sigma_table is not None:
        centers, sigmas = (np.asarray(a) for a in sigma_table)
        if (sigmas.ndim != 1 or len(sigmas) == 0 or centers.shape != sigmas.shape
                or not np.isfinite(centers).all() or not np.all(np.diff(centers) > 0.)
                or not np.isfinite(sigmas).all() or np.any(sigmas <= 0.)):
            raise ValueError("Invalid heading scale table")
        sigma_table = centers, np.log(sigmas)
    return q_table, sigma_table


def _q_lookup(distance, table):
    if table is None:
        return 0., False
    edges, values, supported = table
    index = np.searchsorted(edges, distance, side="right") - 1
    if 0 <= index < len(values) and supported[index]:
        return float(values[index]), True
    return 0., False


def _conditional_basis(R):
    """Keep the distance row first and condition the polarization row on it."""
    return np.array([[1., 0.], [-R[1, 0] / R[0, 0], 1.]])


def _predict_bias(bias, variance, cross, F, alpha, stationary):
    return (alpha * bias, alpha**2 * variance + stationary * (1. - alpha**2),
            alpha * (F @ cross))


def _augmented_observation(h, H, bias_prior, scale):
    signed_loading = scale * H[1, 2]
    return h + np.array([0., signed_loading * bias_prior]), np.column_stack((H, (0., signed_loading)))


def _update(core, prior, P, H, nu, R, accepted, *, consider=False, row=None, beta=1.):
    projected = H @ P
    S = projected @ H.T + R
    S = (S + S.T) * .5
    K = np.zeros((len(prior), 2))
    if not accepted:
        return prior, P, K, S
    if row is None or beta == 1.:
        K = np.linalg.solve(S, projected).T
    else:
        basis = _conditional_basis(R)
        K_cond = np.linalg.solve(basis @ S @ basis.T, basis @ projected).T
        K_cond[row, 1] *= beta
        K = K_cond @ basis
    if consider:
        K[4] = 0.
    x = prior + K @ nu
    x[2] = core.wrap(x[2])
    A = np.eye(len(prior)) - K @ H
    post = A @ P @ A.T + K @ R @ K.T
    return x, (post + post.T) * .5, K, S


def replay(packet, controls, baseline, core, online, model, spec, *, arm="G0",
           sigma_rad=0., q_table=None, sigma_table=None, a2_variance=None,
           near=None, disable_beta=False):
    """Use online inputs and fixed schedules. A2 columns are V and causal, in that order."""
    if arm not in ARMS or not math.isfinite(sigma_rad) or sigma_rad < 0.:
        raise ValueError("Invalid M6 arm or heading scale")
    joint = arm in ("G1", "G2")
    partial = arm in ("G3", "G5psi", "G5y")
    exploratory = arm in ("G4", "G5psi", "G5y")
    if q_table is not None and arm != "G1":
        raise ValueError("An additive-s table requires G1")
    if sigma_table is not None and arm not in ("G1", "G2", "G3"):
        raise ValueError("A distance scale table requires G1, G2 or G3")
    if exploratory != (a2_variance is not None) or (near is not None and not exploratory):
        raise ValueError("G4/G5 require a frozen A2 schedule and only they allow a near mask")
    q_table, sigma_table = _validated_tables(q_table, sigma_table)

    times, mask, reference = (np.asarray(a) for a in (packet["t"], baseline["mask"], baseline["Reff"]))
    n = len(times)
    if (times.shape != (n,) or n == 0 or not np.isfinite(times).all()
            or np.any(np.diff(times) <= 0.) or mask.shape != (n,) or mask.dtype.kind != "b"
            or reference.shape != (n, 2, 2) or not np.isfinite(reference).all()
            or np.linalg.eigvalsh(reference).min() <= 0.):
        raise ValueError("Packet times, fixed mask and R_ref must be aligned")
    near = np.zeros(n, dtype=bool) if near is None else np.asarray(near)
    if near.shape != (n,) or near.dtype.kind != "b":
        raise ValueError("The G4/G5 near mask must align with the packet grid")
    if exploratory:
        a2_variance = np.asarray(a2_variance)
        if (a2_variance.shape != (n, 2) or not np.isfinite(a2_variance).all()
                or np.any(a2_variance < 0.)):
            raise ValueError("Expected nonnegative A2 V and causal columns")

    stationary = 1. if sigma_table is not None else sigma_rad**2
    x, P = packet["x0"].copy(), packet["P0"].copy()
    if joint:
        x, P = np.r_[x, 0.], np.pad(P, ((0, 1), (0, 1)))
        P[4, 4] = stationary
    arc, yaw = 0., 0.
    past = deque(maxlen=HISTORY_LIMIT)
    rows = []
    for i, (time, accepted) in enumerate(zip(times, mask, strict=True)):
        nav, Pnav = online.predict(core, x[:4], P[:4, :4], i, controls)
        alpha = 1.
        if i:
            ds, gy, dt = (float(controls[key][i]) for key in ("ds", "gy", "dt"))
            turn = abs(float(core.wrap(gy - x[3] * dt)))
            arc += abs(ds)
            yaw += turn
            alpha = math.exp(-abs(ds) - turn / YAW_LENGTH_RAD)
        hazard = arc + yaw / YAW_LENGTH_RAD
        distance = math.hypot(*(nav[:2] - spec["anchor"][:2]))
        local_sigma = sigma_rad
        if sigma_table is not None:
            centers, log_sigmas = sigma_table
            local_sigma = math.exp(float(np.interp(distance, centers, log_sigmas)))
        h, H = (field[0] for field in model.batch(nav[None], spec))
        a = float(H[1, 2])
        q_s, q_supported = _q_lookup(distance, q_table)
        own_info = a**2 / reference[i, 1, 1]
        information = own_info
        causal = 0.
        while past and time - past[0][0] > HISTORY_SECONDS:
            past.popleft()
        for _, old_hazard, old_q, old_info in past:
            kernel = math.exp(old_hazard - hazard)
            information += kernel * old_info
            causal += 2. * math.sqrt(q_s * old_q) * kernel
        history_n = len(past)
        if accepted and (partial or q_table is not None):
            past.append((time, hazard, q_s, own_info))

        R = reference[i].copy()
        R[1, 1] += q_s
        R[1, 1] += causal
        schedule_V, schedule_causal = (a2_variance[i] if exploratory and not near[i] else (0., 0.))
        R[1, 1] += schedule_V
        R[1, 1] += schedule_causal
        row = (1 if arm == "G5y" else 2) if partial and (arm == "G3" or near[i]) else None
        beta = 1. if row is None or disable_beta else 1. / (1. + information * local_sigma**2)

        if joint:
            F = core.transition(x[:4], ds, gy, dt)[1] if i else np.eye(4)
            bias, variance, cross = _predict_bias(x[4], P[4, 4], P[:4, 4], F, alpha, stationary)
            prior = np.r_[nav, bias]
            Pprior = np.empty((5, 5))
            Pprior[:4, :4] = Pnav
            Pprior[:4, 4] = Pprior[4, :4] = cross
            Pprior[4, 4] = variance
            # In the distance variant, physical b_theta = sigma(prior distance) * u.
            scale = local_sigma if sigma_table is not None else 1.
            prediction, H_internal = _augmented_observation(h, H, prior[4], scale)
        else:
            prior, Pprior, H_internal, prediction = nav, Pnav, H, h
            scale = 1.

        nu = packet["z"][i] - prediction - packet["muMB"][i]
        if not joint and beta == 1.:
            x, P, K, S = online.joseph(prior, Pprior, H, nu, R, accepted, 1.)
        else:
            x, P, K, S = _update(core, prior, Pprior, H_internal, nu, R, accepted,
                                 consider=arm == "G2", row=row, beta=beta)
        row_data = dict(
            x=x[:4], P=P[:4, :4], prior=nav, Pprior=Pnav, h=prediction, h_nav=h,
            H=H, K=K[:4], Reff=R, nu=nu, S=S, Knu=K[:4] @ nu,
            a=a, g=abs(a), alpha=alpha, beta=beta, I_cell=information, distance=distance,
            arc=arc, yaw=yaw, hazard=hazard, sigma_theta_rad=local_sigma,
            V=q_s + schedule_V, causal=causal + schedule_causal,
            q_s=q_s, q_supported=q_supported, history_n=history_n,
            s_infl=R[1, 1] / reference[i, 1, 1],
            b_theta=x[4] * scale if joint else 0.,
            b_theta_prior=prior[4] * scale if joint else 0.,
        )
        if joint:
            transform = np.array([1., 1., 1., 1., scale])
            row_data.update(
                x_aug=x * transform, P_aug=P * transform[:, None] * transform,
                prior_aug=prior * transform, Pprior_aug=Pprior * transform[:, None] * transform,
                H_aug=np.column_stack((H, (0., a))), K_aug=K * transform[:, None],
                x_internal=x, P_internal=P, prior_internal=prior, Pprior_internal=Pprior,
                H_internal=H_internal, K_internal=K,
            )
        rows.append(row_data)
    trace = {key: np.stack([row[key] for row in rows]) for key in rows[0]}
    trace.update(t=times.copy(), mask=mask.copy(), s_updated=mask.copy(), R_ref=reference.copy())
    if "pose_id" in packet:
        trace["pose_id"] = packet["pose_id"].copy()
    return trace

