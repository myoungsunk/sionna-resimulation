"""Numerical definitions. No model fitting, truth access, or experiment launch."""
from __future__ import annotations
import numpy as np
from .common import require, ContractError


def wrap(x):
    return (np.asarray(x) + np.pi) % (2 * np.pi) - np.pi


def delta(a, b):
    d = np.asarray(a, float) - np.asarray(b, float)
    d = d.copy(); d[..., 2] = wrap(d[..., 2])
    return d


def psd(a, *, positive=False, rtol=1e-10, name='covariance'):
    a = np.asarray(a, dtype=np.float64)
    require(a.ndim == 2 and a.shape[0] == a.shape[1] and np.isfinite(a).all(), f'{name}: invalid shape/values')
    require(np.allclose(a, a.T, rtol=rtol, atol=1e-14), f'{name}: asymmetric')
    a = (a + a.T) / 2
    eig = np.linalg.eigvalsh(a); scale = max(float(np.max(np.abs(eig))), 1e-30)
    require(eig[0] >= -max(rtol * scale, 1e-15), f'{name}: not PSD, min={eig[0]}')
    if positive:
        require(eig[0] > 0, f'{name}: singular; no hidden eigenvalue clipping')
    return a


def solve_spd(a, b, *, condition_limit=1e14):
    a = psd(a, positive=True)
    require(np.isfinite(b).all(),'Nonfinite solve right-hand side')
    require(np.linalg.cond(a) <= condition_limit, 'Ill-conditioned solve')
    return np.linalg.solve(a, b)


def moments(Y):
    Y = np.asarray(Y, float)
    require(Y.ndim == 2 and len(Y) > 0 and np.isfinite(Y).all(), 'Invalid moment input')
    mean = Y.mean(axis=0); Z = Y - mean
    M = Y.T @ Y / len(Y); C = Z.T @ Z / len(Y)
    require(np.allclose(M, C + np.outer(mean, mean), rtol=1e-10, atol=1e-13), 'Moment identity')
    return mean, C, M


def whiten(cov, rtol=1e-9):
    """Retained-eigenspace whitening. Duplicate coordinates add no independent information.

    Returns an r-by-m map; zero eigenmodes are dropped, not inflated into new observations.
    """
    cov = psd(cov)
    e, U = np.linalg.eigh(cov)
    keep = e > max(float(e.max(initial=0)) * rtol, 1e-15)
    require(keep.any(), 'No identifiable feature covariance mode')
    return (U[:, keep] / np.sqrt(e[keep])).T, dict(cov_rank=int(keep.sum()), eig_min=float(e[keep].min()), eig_max=float(e.max()))


def projector(d, J, omega, scale, *, rank_rtol=1e-8):
    """Local state-orthogonal residual; only call after applying the same valid-tap mask."""
    d = np.asarray(d, float); J = np.asarray(J, float); scale = np.asarray(scale, float)
    require(J.shape == (len(d), len(scale)), 'Profile Jacobian shape')
    require(np.isfinite(d).all() and np.isfinite(J).all() and (scale > 0).all(), 'Nonfinite profile/J or invalid scale')
    W, info = whiten(omega)
    A = W @ (J * scale[None, :])
    U, s, _ = np.linalg.svd(A, full_matrices=False)
    rank = int(np.sum(s > max(s.max(initial=0) * rank_rtol, 1e-13)))
    P = np.eye(len(W)) - U[:, :rank] @ U[:, :rank].T
    u = P @ W @ d
    # Fixed-dimensional representation in original tap coordinates. Basis-invariant metric map.
    score = W.T @ u
    info.update(state_rank=rank, residual_rank=len(W) - rank,
                orthogonality=float(np.linalg.norm(P @ A)), idempotence=float(np.linalg.norm(P @ P - P)),
                u_norm=float(np.linalg.norm(u)))
    return score, P, W, info


def masked_projector(d, J, omega, scale, mask):
    mask = np.asarray(mask, bool)
    out = np.full(len(d), np.nan)
    if not mask.any():
        return out, {'status': 'NO_VALID_TAPS', 'valid_taps': 0}
    try:
        score, P, W, info = projector(np.asarray(d)[mask], np.asarray(J)[mask], np.asarray(omega)[np.ix_(mask, mask)], scale)
        out[mask] = score
        return out, {'status': 'PASS', 'valid_taps': int(mask.sum()), **info}
    except ContractError as e:
        return out, {'status': 'UNIDENTIFIABLE', 'reason': str(e), 'valid_taps': int(mask.sum())}


def finite_jacobian(fun, x, steps=(1e-5, 1e-5, 1e-6), cols=(0, 1, 2)):
    x = np.asarray(x, float); y = np.asarray(fun(x), float)
    J = np.empty((y.size, len(cols)))
    for j, (col, step) in enumerate(zip(cols, steps)):
        plus, minus = x.copy(), x.copy(); plus[col] += step; minus[col] -= step
        plus[2] = wrap(plus[2]); minus[2] = wrap(minus[2])
        J[:, j] = (np.asarray(fun(plus)) - np.asarray(fun(minus))) / (2 * step)
    return J


def response_pair(base_plus, base_minus, corr_plus, corr_minus, eps=1e-10):
    db = float(base_plus - base_minus); dc = float(corr_plus - corr_minus)
    return dict(delta_base=db, delta_corrected=dc, G=dc / db if abs(db) > eps else np.nan,
                ratio_defined=bool(abs(db) > eps), sign_reversal=bool(db * dc < 0),
                suppressed=bool(abs(db) > eps and abs(dc) < .5 * abs(db)))


def information(j, U, Gamma, *, rtol=1e-8):
    j = np.asarray(j, float); U = np.asarray(U, float)
    require(U.shape[0] == len(j), 'Nuisance dimension')
    W, meta = whiten(Gamma)
    jw, Uw = W @ j, W @ U
    column_norm=np.linalg.norm(Uw,axis=0)
    normalized=Uw/np.where(column_norm>0,column_norm,1.)
    Q, s, _ = np.linalg.svd(normalized, full_matrices=False)
    rank = int(np.sum(s > max(s.max(initial=0) * rtol, 1e-13)))
    P = np.eye(len(jw)) - Q[:, :rank] @ Q[:, :rank].T
    v = P @ jw
    return dict(information=float(v @ v), unmarginalized=float(jw @ jw), nuisance_rank=rank,
                covariance_rank=meta['cov_rank'], remaining_rank=len(jw) - rank)


def profiled_cost(residual, U, Gamma):
    W, _ = whiten(Gamma)
    rw, Uw = W @ residual, W @ U
    beta = np.linalg.lstsq(Uw, rw, rcond=1e-8)[0]
    remaining = rw - Uw @ beta
    return float(remaining @ remaining), beta


def correlated_update_moments(P, H, R, C):
    """delta=xhat-truth; innovation=epsilon-H delta. Diagnostic moments only."""
    P, R = psd(P), psd(R)
    psd(np.block([[P, C], [C.T, R]]), name='joint prior/residual covariance')
    S = H @ P @ H.T + R - H @ C - C.T @ H.T
    S = psd(S, positive=True)
    B = P @ H.T - C
    K = solve_spd(S, B.T).T
    post = psd(P - K @ B.T)
    return S, K, post


def motion_observation_covariance(F, G, Q, H):
    """Full within-window covariance induced by process noise; no initial prior added."""
    n, obs, state = H.shape
    require(F.shape == (n, state, state), 'F shape')
    R = np.zeros((n * obs, n * obs))
    # Matrix map from each increment into all later observations.
    for k in range(1, n):
        B = np.zeros((n, obs, G.shape[2])); T = G[k].copy()
        B[k] = H[k] @ T
        for i in range(k + 1, n):
            T = F[i] @ T; B[i] = H[i] @ T
        B = B.reshape(n * obs, -1)
        R += B @ Q[k] @ B.T
    return psd(R)


def episode_curve(t, values, thresholds):
    t = np.asarray(t, float); values = np.asarray(values, float)
    require(len(t) == len(values) and (np.diff(t) > 0).all(), 'Episode timestamps')
    dt = np.r_[np.diff(t), 0.0]  # Do not invent exposure after the final timestamp.
    out = []
    for threshold in thresholds:
        high = values > threshold; starts = np.flatnonzero(high & ~np.r_[False, high[:-1]])
        ends = np.flatnonzero(high & ~np.r_[high[1:], False])
        durations = [float(dt[a:b + 1].sum()) for a, b in zip(starts, ends)]
        out.append(dict(threshold=float(threshold), episodes=len(starts), duration_total_s=float(dt[high].sum()),
                        duration_max_s=max(durations, default=0.0), right_censored=bool(high[-1])))
    return out


def paired_bootstrap(a, b, *, draws=4000, seed=20261023, margin=0.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    require(a.shape == b.shape and a.ndim == 1 and len(a) > 1, 'Paired bootstrap shape')
    require(np.isfinite(a).all() and np.isfinite(b).all(), 'Failed/nonfinite runs cannot be dropped')
    d = b - a; rng = np.random.default_rng(seed)
    ix = rng.integers(0, len(a), size=(draws, len(a)))
    boot = d[ix].mean(1); lo, hi = np.quantile(boot, [.025, .975])
    return dict(delta_mean=float(d.mean()), lower=float(lo), upper=float(hi),
                ratio_mean=float(np.mean(b / a)) if np.all(a > 0) else np.nan,
                ratio_defined=bool(np.all(a > 0)), all_seed_no_harm=bool(np.all(d <= 0)),
                empirical_no_harm=bool(d.mean() <= 0),
                conclusion='SUPPORT' if hi <= margin else ('CONTRARY' if lo > margin else 'INCONCLUSIVE'),
                margin=float(margin), n_pairs=len(a), interpretation='conditional on frozen RF, not independent scenes')


def time_block_sensitivity(t, difference, lengths=(10, 30, 60, 120), min_blocks=4):
    t, d = np.asarray(t, float), np.asarray(difference, float)
    out = []
    for seconds in lengths:
        complete = int((t[-1] - t[0]) // seconds)
        means = [float(d[(t >= t[0] + k * seconds) & (t < t[0] + (k + 1) * seconds)].mean()) for k in range(complete)]
        out.append(dict(block_s=seconds, complete_blocks=complete,
                        status='DESCRIPTIVE_ONLY' if complete >= min_blocks else 'INSUFFICIENT_BLOCKS',
                        block_mean_sd=float(np.std(means, ddof=1)) if complete >= 2 else np.nan,
                        note='No EKF replay of stitched bootstrap trajectories; no independence claim'))
    return out
