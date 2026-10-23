"""Single-update and actual recursive engine. Identical raw inputs; each branch owns its prior."""
from __future__ import annotations
from copy import deepcopy
import numpy as np
from .common import Inputs, Packet, Trace, require
from .numerics import wrap, psd, solve_spd


def update(x, P, packet, h, H, correction, *, mode='joint', gate='own', common_accept=None, eta=1.0):
    """Joseph update matching strict_common; eta scales update R only, NEVER gate R."""
    require(mode in ('joint','range_only'),'Unknown measurement update mode')
    require(np.asarray(x).shape==(4,) and np.asarray(h).shape==(2,) and np.asarray(H).shape==(2,4),'Invalid update dimensions')
    require(np.isfinite(x).all() and np.isfinite(h).all() and np.isfinite(H).all() and np.isfinite(correction),'Nonfinite update input must not become a gate refusal')
    P = psd(P); Rg = psd(packet.R, positive=True); Ru = Rg * eta
    require(eta > 0 and np.isfinite(eta), 'Invalid eta')
    nu = packet.z - h - packet.mu; nu = nu.copy(); nu[1] -= correction
    K = np.zeros((4, 2)); x = np.array(x, float, copy=True); P = P.copy()
    if mode == 'range_only':
        Hr = H[0:1]; hp = Hr @ P; hph = float((hp @ Hr.T).item())
        nis = float(nu[0]**2 / (hph + Rg[0, 0])); own = nis <= 6.6348966010212145
        K[:, :1] = (P @ Hr.T) / (hph + Ru[0, 0])
    else:
        HP = H @ P; HPH = HP @ H.T
        Sg = HPH + Rg; Sg = .5 * (Sg + Sg.T)
        nis = float(nu @ solve_spd(Sg, nu)); own = nis <= 9.210340371976184
        Se = HPH + Ru; Se = .5 * (Se + Se.T)
        K = solve_spd(Se, HP).T
    require(gate in ('own', 'force_accept', 'common'), 'Unknown gate policy')
    accepted = own if gate == 'own' else (True if gate == 'force_accept' else common_accept)
    require(accepted is not None, 'Common gate needs an explicit decision')
    if not accepted:
        K[:] = 0
        # Match the original refusal branch exactly: no angle wrap or covariance algebra.
        return dict(x=x, P=P, K=K, nis=nis, accepted=False, nu=nu, R_gate=Rg, R_update=Ru, own_accept=bool(own))
    x += K @ nu; x[2] = wrap(x[2])
    A = np.eye(4) - K @ H
    P = A @ P @ A.T + K @ Ru @ K.T; P = .5 * (P + P.T)
    psd(P)
    return dict(x=x, P=P, K=K, nis=nis, accepted=bool(accepted), nu=nu, R_gate=Rg, R_update=Ru, own_accept=bool(own))


def simulate(inputs: Inputs, model, corrector, *, start=0, x_prior=None, P_prior=None, stop=None,
             active_end=None, gate='own', common_mask=None, diagnostic_allowed=False):
    """Resume from an already-predicted state at start; no double prediction at branch point.

    active_end is an EXCLUSIVE time limit for correction. Thereafter both branches use BASE.
    No future derived features, gain, gate or states are shared between branches.
    """
    require(not corrector.diagnostic or diagnostic_allowed, 'Oracle forbidden in operational execution')
    require(start >= 0 and start < len(inputs.packets), 'Invalid start')
    stop = len(inputs.packets) if stop is None else stop
    require(start < stop <= len(inputs.packets), 'Invalid stop')
    before = inputs.checksum()
    model = deepcopy(model) if getattr(model, 'mutable_runtime', False) else model
    corrector = deepcopy(corrector)
    x = np.array(inputs.x0 if x_prior is None else x_prior, float, copy=True)
    P = np.array(inputs.P0 if P_prior is None else P_prior, float, copy=True)
    require(start == 0 or (x_prior is not None and P_prior is not None), 'Nonzero branch must clone both x-/P-')
    n = stop - start
    shapes = dict(x_minus=(4,), P_minus=(4,4), x_plus=(4,), P_plus=(4,4), h=(2,), H=(2,4), K=(4,2),
                  F=(4,4), G=(4,3), Q_input=(3,3), z_raw=(2,), mu_B=(2,), R_update=(2,2), R_gate=(2,2),
                  innovation=(2,), projection_valid_mask=(len(inputs.packets[0].profile),), feature_mask=(len(inputs.packets[0].profile),))
    a = {key: np.zeros((n,) + shape) for key, shape in shapes.items()}
    for key in ('t', 'pose_id', 'k', 'correction', 'd0', 'dB', 'NIS', 'accepted', 'profile_valid_count'):
        a[key] = np.zeros(n)
    a['profile_status'] = np.empty(n, dtype='U32')
    for ii, k in enumerate(range(start, stop)):
        p = inputs.packets[k]
        F, G, Q = np.eye(4), np.zeros((4,3)), np.zeros((3,3))
        if k > start:
            x, P, F, G, Q = model.predict(x, P, inputs.controls[k])
        h, H = model.observe(x)
        h, H = np.asarray(h, float), np.asarray(H, float)
        require(h.shape == (2,) and H.shape == (2,4) and np.isfinite(H).all(), 'Invalid physical model')
        active = active_end is None or p.t < active_end
        c, flags = corrector(p, x, h, model) if active else (0., {'profile_status': 'BASE_SUFFIX'})
        mode = 'range_only' if corrector.name == 'RANGE_ONLY' and active else 'joint'
        eta = 2.0 if corrector.name == 'BASE_ETA2' and active else 1.0
        result = update(x, P, p, h, H, c, mode=mode, gate=gate,
                        common_accept=None if common_mask is None else bool(common_mask[k]), eta=eta)
        for key, value in dict(x_minus=x, P_minus=P, h=h, H=H, F=F, G=G, Q_input=Q, z_raw=p.z,
                               mu_B=p.mu, feature_mask=p.profile_valid, x_plus=result['x'], P_plus=result['P'],
                               K=result['K'], R_update=result['R_update'], R_gate=result['R_gate'], innovation=result['nu']).items():
            a[key][ii] = value
        for key, value in dict(t=p.t, pose_id=p.pose_id, k=k, correction=c, d0=p.z[1]-h[1], dB=p.z[1]-h[1]-p.mu[1],
                              NIS=result['nis'], accepted=result['accepted'], profile_valid_count=p.profile_valid.sum()).items():
            a[key][ii] = value
        if flags.get('profile_valid') is not None:
            a['projection_valid_mask'][ii] = flags['profile_valid']
        a['profile_status'][ii] = flags.get('profile_status', 'NOT_USED')
        x, P = result['x'], result['P']
    require(inputs.checksum() == before, 'Runtime mutated frozen inputs')
    return Trace(a, {**inputs.identity, 'arm': corrector.name, 'model_hash': corrector.model_hash, 'source_hash': inputs.source_hash,
                     'raw_input_sha256': before, 'start_index': start, 'suffix': 'BASE' if active_end is not None else corrector.name,
                     'diagnostic': corrector.diagnostic, 'gate': gate})
