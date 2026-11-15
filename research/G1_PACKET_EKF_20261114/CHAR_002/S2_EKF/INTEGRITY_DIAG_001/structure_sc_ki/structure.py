"""G1-INT-001 online replay with a frozen, externally supplied E0 gate."""

from collections import deque
import math

import numpy as np

from d0_d5 import KNOTS


CHANNELS = ('r', 's')
WHITE_FLOOR = 0.05
KI_WINDOW_S = 10.0
KI_MAX_PACKETS = 100


def _symmetric(matrix):
    return (matrix + matrix.T) * 0.5


def _consider_prior(previous, nav_prior, F, alpha):
    predicted = np.empty((6, 6))
    predicted[:4, :4] = nav_prior
    predicted[:4, 4:] = (F @ previous[:4, 4:]) * alpha
    predicted[4:, :4] = predicted[:4, 4:].T
    predicted[4:, 4:] = (
        alpha[:, None] * previous[4:, 4:] * alpha + np.diag(1.0 - alpha**2)
    )
    return predicted


def _consider_update(prior, prior_cov, H, innovation, loading, white, permitted, wrap):
    H_aug = np.hstack((H, loading))
    HP = H_aug @ prior_cov
    S = _symmetric(HP @ H_aug.T + white)
    gain = np.zeros((6, 2))
    if not permitted:
        return prior, prior_cov, gain, S

    gain[:4] = np.linalg.solve(S, HP[:, :4]).T
    state = prior + gain[:4] @ innovation
    state[2] = wrap(state[2])
    A = np.eye(6) - gain @ H_aug
    covariance = _symmetric(A @ prior_cov @ A.T + gain @ white @ gain.T)
    return state, covariance, gain, S


def _kernel_multiplier(history, t, arc, yaw_arc, q_eff, ell_m, ell_rad):
    while history and t - history[0][0] > KI_WINDOW_S:
        history.popleft()
    k = np.ones(2)
    for _, past_arc, past_yaw_arc, past_q_eff in history:
        decay = np.exp(-(arc - past_arc) / ell_m - (yaw_arc - past_yaw_arc) / ell_rad)
        k += 2.0 * np.sqrt(q_eff * past_q_eff) * decay
    return k


def _remember_packet(history, permitted, t, arc, yaw_arc, q_eff):
    if permitted:
        history.append((t, arc, yaw_arc, q_eff.copy()))


def replay_structure(packet, controls, mask, core, online, model, spec, table, fit, *, arm,
                     check_special=None):
    """Replay one held-out fold. All geometry and clocks are available online."""
    switches = {'SC': (None, 'q_zero', 'phi_zero'), 'KI': (None, 'q_zero', 'empty_history')}
    if arm not in switches or check_special not in switches[arm]:
        raise ValueError(f'Unsupported replay options: {arm!r}, {check_special!r}')

    n = len(mask)
    shapes = {
        'x': (4,), 'P': (4, 4), 'prior': (4,), 'Pprior': (4, 4), 'h': (2,), 'H': (2, 4),
        'K': (4, 2), 'Reff': (2, 2), 'nu': (2,), 'S': (2, 2), 'sigma_b': (), 'rho_before': (),
        'R_ref': (2, 2), 'R_white': (2, 2), 'rho_prior': (), 'q': (2,), 'q_eff': (2,),
        'alpha': (2,), 'arc': (), 'yaw_arc': (), 'k': (2,), 'history_n': (), 'D': (2, 2),
        'P_aug': (6, 6), 'Pprior_aug': (6, 6), 'K_aug': (6, 2), 'u_mean': (2,),
    }
    trace = {name: np.empty((n, *shape)) for name, shape in shapes.items()}
    trace['mask'] = mask.copy()
    trace['history_n'] = np.empty(n, dtype=np.int64)

    q_knots_m = np.asarray(fit['q_knots_m'], dtype=float)
    channel_fits = [fit['fits'][channel] for channel in CHANNELS]
    q_knots = np.asarray([entry['q_knots'] for entry in channel_fits], dtype=float)
    ell_m = np.asarray([entry['ell_m'] for entry in channel_fits], dtype=float)
    ell_rad = np.deg2rad([entry['ell_deg'] for entry in channel_fits])
    ax, ay = spec['anchor'][:2]
    x, P = packet['x0'].copy(), packet['P0'].copy()
    P_aug = np.eye(6) if arm == 'SC' else np.zeros((6, 6))
    P_aug[:4, :4] = P
    history = deque(maxlen=KI_MAX_PACKETS)
    arc = yaw_arc = 0.0

    for i in range(n):
        rho_before = math.hypot(x[0] - ax, x[1] - ay)
        sigma_b = float(np.interp(rho_before, KNOTS, table))
        prior, Pprior = online.predict(core, x, P, i, controls)
        da = abs(float(controls['ds'][i])) if i else 0.0
        dyaw = abs(float(core.wrap(prior[2] - x[2]))) if i else 0.0
        arc += da
        yaw_arc += dyaw
        alpha = np.exp(-da / ell_m - dyaw / ell_rad)
        if check_special == 'phi_zero':
            alpha[:] = 0.0

        rho_prior = math.hypot(prior[0] - ax, prior[1] - ay)
        q = np.array([np.interp(rho_prior, q_knots_m, values) for values in q_knots])
        q_eff = np.minimum(q, 1.0 - WHITE_FLOOR)
        if check_special == 'q_zero':
            q_eff[:] = 0.0
        R_ref = packet['R'][i].copy()
        R_ref[1, 1] += sigma_b**2
        D = np.diag(np.sqrt(q_eff * R_ref.diagonal()))
        R_white = R_ref - D @ D.T
        np.linalg.cholesky(R_white)
        h, H = (field[0] for field in model.batch(prior[None], spec))
        nu = packet['z'][i] - h - packet['muMB'][i]

        if arm == 'SC':
            F = np.eye(4)
            if i:
                increments = (float(controls[key][i]) for key in ('ds', 'gy', 'dt'))
                _, F, _ = core.transition(x, *increments)
            Pprior_aug = _consider_prior(P_aug, Pprior, F, alpha)
            x, P_aug, K_aug, S = _consider_update(
                prior, Pprior_aug, H, nu, D, R_white, mask[i], core.wrap
            )
            P = P_aug[:4, :4]
            Reff, multiplier, history_n = R_white, np.ones(2), 0
        else:
            t = float(packet['t'][i])
            multiplier = _kernel_multiplier(history, t, arc, yaw_arc, q_eff, ell_m, ell_rad)
            history_n = len(history)
            Reff = R_ref.copy()
            Reff[np.diag_indices(2)] *= multiplier
            x, P, K, S = online.joseph(prior, Pprior, H, nu, Reff, mask[i], 1.0)
            if check_special != 'empty_history':
                _remember_packet(history, mask[i], t, arc, yaw_arc, q_eff)
            # Common trace layout. KI has no latent covariance or gain.
            Pprior_aug = np.zeros((6, 6))
            Pprior_aug[:4, :4] = Pprior
            P_aug[:4, :4] = P
            K_aug = np.vstack((K, np.zeros((2, 2))))
        step = {
            'x': x, 'P': P, 'prior': prior, 'Pprior': Pprior, 'h': h, 'H': H, 'K': K_aug[:4],
            'Reff': Reff, 'nu': nu, 'S': S, 'sigma_b': sigma_b, 'rho_before': rho_before,
            'R_ref': R_ref, 'R_white': R_white, 'rho_prior': rho_prior, 'q': q, 'q_eff': q_eff,
            'alpha': alpha, 'arc': arc, 'yaw_arc': yaw_arc, 'k': multiplier, 'history_n': history_n,
            'D': D, 'P_aug': P_aug, 'Pprior_aug': Pprior_aug, 'K_aug': K_aug, 'u_mean': np.zeros(2),
        }
        for name, value in step.items():
            trace[name][i] = value
    return trace


def synthetic_checks():
    """Check limiting cases with analytic fixtures and no experiment data."""
    P = np.diag([4.0, 2.0, 1.0, 0.5])
    P_aug = np.eye(6)
    P_aug[:4, :4] = P
    state = np.zeros(4)
    H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, -0.2, 0.8, 0.0]])
    nu = np.array([0.1, -0.3])
    ref = np.array([[1.0, 0.03], [0.03, 0.5]])
    D = np.diag(np.sqrt([0.8, 0.15]))
    white = ref - D @ D.T
    S_ref = H @ P @ H.T + ref
    K_ref = P @ H.T @ np.linalg.inv(S_ref)
    x_ref = K_ref @ nu
    P_ref = P - K_ref @ H @ P

    covariance_with_cross = P_aug.copy()
    covariance_with_cross[0, 4] = covariance_with_cross[4, 0] = 0.3
    error = {}
    for name, alpha, loading, R in (
        ('q_zero', np.ones(2), np.zeros((2, 2)), ref),
        ('phi_zero', np.zeros(2), D, white),
    ):
        previous = P_aug if name == 'q_zero' else covariance_with_cross
        prior_cov = _consider_prior(previous, P, np.eye(4), alpha)
        x_out, P_out, gain, S = _consider_update(prior_cov=prior_cov, prior=state, H=H,
                                               innovation=nu, loading=loading, white=R,
                                               permitted=True, wrap=float)
        error[name] = float(max(np.max(np.abs(actual - expected)) for actual, expected in (
            (x_out, x_ref), (P_out[:4, :4], P_ref), (gain[:4], K_ref), (S, S_ref),
        )))
        if error[name] > 1e-12:
            raise AssertionError(f'SC {name} white equivalence error {error[name]}')

    # Repeated measurements of a scalar plus an unknown, constant common bias.
    # Even infinitely many white-noise averages leave this analytic variance floor.
    common_bias_floor = 1.0 / (1.0 / P[0, 0] + 1.0 / D[0, 0]**2)
    H_stationary = np.zeros_like(H)
    H_stationary[0, 0] = 1.0
    min_eigenvalue = min_nav_variance = float('inf')
    for _ in range(200):
        _, P_aug, gain, _ = _consider_update(state, P_aug, H_stationary, np.zeros(2), D,
                                           np.diag(white.diagonal()), True, float)
        np.testing.assert_array_equal(P_aug[4:, 4:], np.eye(2))
        np.testing.assert_array_equal(gain[4:], 0.0)
        min_eigenvalue = min(min_eigenvalue, float(np.linalg.eigvalsh(P_aug)[0]))
        min_nav_variance = min(min_nav_variance, P_aug[0, 0])
    if min_eigenvalue < -1e-12 or min_nav_variance < common_bias_floor - 1e-12:
        raise AssertionError('SC stationary PSD or common-bias variance floor failed')
    predicted = _consider_prior(P_aug, P_aug[:4, :4], np.eye(4), np.array([0.3, 0.6]))
    reject_x, reject_P, reject_gain, _ = _consider_update(state, predicted, H, nu, D, white, False, float)
    np.testing.assert_array_equal(reject_x, state)
    np.testing.assert_array_equal(reject_P, predicted)
    np.testing.assert_array_equal(reject_gain, 0.0)

    history = deque(maxlen=KI_MAX_PACKETS)
    ranges = np.array([1.0, 2.0])
    yaws = np.array([0.5, 1.0])
    q = np.array([0.09, 0.16])
    np.testing.assert_array_equal(_kernel_multiplier(history, 0.0, 0.0, 0.0, q, ranges, yaws), 1.0)
    _remember_packet(history, True, 0.0, 0.0, 0.0, np.array([0.25, 0.25]))
    _remember_packet(history, False, 2.0, 0.7, 0.2, np.ones(2))
    _remember_packet(history, True, 3.0, 1.0, 0.3, np.array([0.04, 0.64]))
    multiplier = _kernel_multiplier(history, 10.0, 2.0, 0.5, q, ranges, yaws)
    expected = 1.0 + 2.0 * (np.array([0.15, 0.20]) * np.exp([-3.0, -1.5])
                            + np.array([0.06, 0.32]) * np.exp([-1.4, -0.7]))
    np.testing.assert_allclose(multiplier, expected, rtol=0, atol=1e-14)
    _kernel_multiplier(history, 10.01, 2.0, 0.5, q, ranges, yaws)
    if [row[0] for row in history] != [3.0]:
        raise AssertionError('KI expired or rejected row in history')
    for i in range(KI_MAX_PACKETS + 1):
        _remember_packet(history, True, float(20 + i), 2.0, 0.5, q)
    if len(history) != KI_MAX_PACKETS or history[0][0] != 21.0:
        raise AssertionError('KI packet count cap failed')
    return {
        'status': 'PASS', 'sc_white_equivalence_max_abs': error,
        'sc_stationary_min_eigenvalue': min_eigenvalue,
        'sc_stationary_common_bias_floor': common_bias_floor,
        'sc_stationary_min_variance': float(min_nav_variance),
        'sc_zero_latent_gain_exact_Puu_reject_identity': True,
        'ki_empty_and_reject_exclusion_inclusive_time_and_packet_cap': True,
        'ki_known_sum': multiplier.tolist(),
    }
