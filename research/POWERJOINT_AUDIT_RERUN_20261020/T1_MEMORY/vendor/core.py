"""Bias-aware [px, py, yaw, gyro_bias] research primitives.

Units: metres, radians, seconds. This is not a certified navigation stack.
A three-state baseline is explicitly supported for paired ablations.
Raw observation order is [range, s], never an independently inverted heading.
The MAP solver preserves the ORIGINAL prior during every iteration.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import math
import numpy as np

Model = Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]]


def wrap(a):
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def covariance(a, n, *, positive=False):
    p = np.asarray(a, dtype=float)
    if p.shape != (n, n) or not np.isfinite(p).all():
        raise ValueError('invalid covariance shape or nonfinite entries')
    if not np.allclose(p, p.T, rtol=1e-12, atol=1e-14):
        raise ValueError('nonsymmetric covariance')
    p = (p + p.T) / 2
    eig = np.linalg.eigvalsh(p)
    tol = 1e-12 * max(1., np.linalg.norm(p, 2))
    if eig[0] < -tol or (positive and eig[0] <= 0):
        raise ValueError('covariance not PSD/PD as requested')
    return p


def state_vector(x):
    x = np.asarray(x, dtype=float)
    if x.shape not in ((3,), (4,)) or not np.isfinite(x).all():
        raise ValueError('state must have 3 or 4 finite elements')
    return x


def sinc_half(a):
    """sin(a/2)/(a/2), derivative with respect to a (not a/2)."""
    if abs(a) < 1e-4:
        a2 = a*a
        return 1-a2/24+a2*a2/1920-a2**3/322560, -a/12+a**3/480-a**5/53760
    h = a/2
    return math.sin(h)/h, (h*math.cos(h)-math.sin(h))/(2*h*h)


def transition(x, ds, gyro_angle, dt):
    x = state_vector(x)
    if not np.isfinite([ds, gyro_angle, dt]).all() or dt <= 0:
        raise ValueError('finite increments and dt > 0 required')
    n = len(x)
    b = x[3] if n == 4 else 0.
    a = gyro_angle-b*dt
    c, dc = sinc_half(a)
    phi = x[2]+a/2
    u = np.array([math.cos(phi), math.sin(phi)])
    up = np.array([-u[1], u[0]])
    d = ds*c*u
    v = ds*(dc*u+c*up/2)
    out = x.copy()
    out[:2] += d
    out[2] = wrap(x[2]+a)
    F = np.eye(n)
    F[:2, 2] = np.array([-d[1], d[0]])
    G = np.zeros((n, 3 if n == 4 else 2))
    G[:2, 0] = c*u
    G[:2, 1] = v
    G[2, 1] = 1.
    if n == 4:
        F[:2, 3] = -dt*v
        F[2, 3] = -dt
        G[3, 2] = 1.
    return out, F, G


def predict(x, P, ds, gyro_angle, dt, Q_input):
    y, F, G = transition(x, ds, gyro_angle, dt)
    P = covariance(P, len(y))
    Q_input = covariance(Q_input, G.shape[1])
    return y, covariance(F@P@F.T+G@Q_input@G.T, len(y)), F, G


def sequential_affine(mu, P, z, h0, H, R):
    """Exact sequential conditioning of one FROZEN affine model.

    Joint noise is whitened by its Cholesky factor. h0 is h(mu).
    Residual of the second row is adjusted for the first state correction.
    No angular observation is assumed; yaw lives in a local prior chart.
    """
    mu = state_vector(mu)
    P = covariance(P, len(mu), positive=True)
    z, h0, H = np.asarray(z), np.asarray(h0), np.asarray(H)
    Lr = np.linalg.cholesky(covariance(R, len(z), positive=True))
    B = np.linalg.solve(Lr, H)
    v = np.linalg.solve(Lr, z-h0)
    delta = np.zeros(len(mu))
    C = P.copy()
    for row, target in zip(B, v):
        S = float(row@C@row+1.)
        K = C@row/S
        delta += K*(target-row@delta)
        A = np.eye(len(mu))-np.outer(K, row)
        C = A@C@A.T+np.outer(K, K)
    out = mu+delta
    out[2] = wrap(out[2])
    return out, covariance(C, len(mu)), delta


def gaussian_update(mu, P, z, model: Model, R, *, gate_threshold=None):
    mu = state_vector(mu)
    P = covariance(P, len(mu), positive=True)
    z = np.asarray(z, float)
    h, H = model(mu.copy())
    h, H = np.asarray(h, float), np.asarray(H, float)
    if h.shape != z.shape or H.shape != (len(z), len(mu)):
        raise ValueError('model dimensions do not match observation/state')
    if not np.isfinite(np.r_[z, h, H.ravel()]).all():
        raise ValueError('nonfinite model/observation')
    R = covariance(R, len(z), positive=True)
    nu = z-h
    S = covariance(H@P@H.T+R, len(z), positive=True)
    nis = float(nu@np.linalg.solve(S, nu))
    K = np.linalg.solve(S, H@P).T
    accepted = gate_threshold is None or nis <= gate_threshold
    out, C = mu.copy(), P.copy()
    if accepted:
        out += K@nu
        out[2] = wrap(out[2])
        A = np.eye(len(mu))-K@H
        C = covariance(A@P@A.T+K@R@K.T, len(mu))
    return out, C, {'accepted': accepted, 'NIS': nis, 'innovation': nu,
                    'S': S, 'H': H, 'K': K, 'R': R}


def conditional_rf(residual, H, R):
    """Range likelihood then conditional s likelihood, fixed Gaussian R."""
    R = covariance(R, 2, positive=True)
    r = np.asarray(residual, float)
    c = R[1, 0]/R[0, 0]
    return (float(r[0]), float(r[1]-c*r[0]), float(R[0, 0]),
            float(R[1, 1]-c*R[0, 1]), np.asarray(H)[1]-c*np.asarray(H)[0])


def recover_bias(mu, P, pose_mean, pose_cov):
    """Exact conditional-moment identity within an unwrapped Gaussian chart.

    pose_mean yaw must be on mu's same local unwrapped branch.
    Observations must be conditionally independent of bias given pose.
    """
    mu = state_vector(mu)
    if len(mu) != 4:
        raise ValueError('bias recovery needs 4-state prior')
    P = covariance(P, 4, positive=True)
    m = np.asarray(pose_mean, float)
    C = covariance(pose_cov, 3)
    A = np.linalg.solve(P[:3, :3], P[:3, 3]).T
    V = P[3, 3]-A@P[:3, 3]
    mean = np.r_[m, mu[3]+A@(m-mu[:3])]
    cov = np.zeros((4, 4))
    cov[:3, :3] = C
    cov[3, :3] = A@C
    cov[:3, 3] = cov[3, :3]
    cov[3, 3] = V+A@C@A
    return mean, covariance(cov, 4)


@dataclass
class MAPResult:
    x: np.ndarray
    P: np.ndarray
    status: str
    iterations: int
    cost: float
    gradient_inf: float
    prior_delta: np.ndarray
    history: list[dict]


def map_update(mu, P, z, model: Model, R, *, range_first=True,
               max_iter=40, gradient_tol=1e-8, max_step_halvings=24,
               initial_delta=None):
    """Local joint MAP in prior-whitened coordinates, with safeguarded GN.

    The fixed Gaussian negative-log-posterior and gradient_tol are unchanged.
    R2 uses embedded true-gradient quadrature at the cost cancellation
    floor. Gradient stationarity, the objective and the iteration limit
    are unchanged. This is a local safeguard, not a convergence proof.

    x=mu+chol(P)*y; prior residual is ALWAYS y. Angles supplied to the
    periodic model may be unwrapped. Restrict yaw delta to (-pi,pi) for
    this single local prior branch. This is not multimodal integration.
    Returned P is local Gauss-Newton covariance, NOT certified coverage.
    Failure is explicit; callers must not silently deploy a failed update.
    Optional initial_delta is a warm start for frozen regression, not a new
    prior or observation, and is mutually exclusive with range_first.
    """
    mu = state_vector(mu).copy()
    n = len(mu)
    P = covariance(P, n, positive=True)
    z = np.asarray(z, float)
    R = covariance(R, len(z), positive=True)
    Lp, Lr = np.linalg.cholesky(P), np.linalg.cholesky(R)
    if not np.isfinite(z).all():
        raise ValueError('nonfinite observation')
    y = np.zeros(n)
    if initial_delta is not None:
        if range_first:
            raise ValueError('initial_delta and range_first are mutually exclusive')
        initial_delta = np.asarray(initial_delta, dtype=float)
        if initial_delta.shape != (n,) or not np.isfinite(initial_delta).all():
            raise ValueError('initial_delta must be a finite full-state vector')
        if abs(initial_delta[2]) >= np.pi:
            raise ValueError('initial_delta outside the local angular chart')
        y = np.linalg.solve(Lp, initial_delta)
    if range_first:
        def rm(x):
            h, H = model(x)
            return np.asarray(h)[:1], np.asarray(H)[:1]
        xinit, _, _ = gaussian_update(mu, P, z[:1], rm, R[:1, :1])
        dinit = xinit-mu
        dinit[2] = wrap(dinit[2])
        y = np.linalg.solve(Lp, dinit)
        if abs((Lp@y)[2]) >= np.pi:
            y[:] = 0.

    def evaluate(yv):
        delta = Lp@yv
        if abs(delta[2]) >= np.pi:
            return math.inf, None, None
        h, H = model(mu+delta)
        h, H = np.asarray(h, float), np.asarray(H, float)
        if h.shape != z.shape or H.shape != (len(z), n):
            raise ValueError('MAP model dimensions')
        if not np.isfinite(np.r_[h, H.ravel()]).all():
            raise ValueError('nonfinite MAP model')
        v = np.linalg.solve(Lr, z-h)
        B = np.linalg.solve(Lr, H@Lp)
        return .5*float(yv@yv+v@v), yv-B.T@v, np.eye(n)+B.T@B

    history = []
    status = 'MAX_ITERATIONS'
    for it in range(max_iter+1):
        cost, grad, info = evaluate(y)
        if grad is None:
            status = 'OUTSIDE_LOCAL_CHART'
            break
        gn = float(np.max(np.abs(grad)))
        history.append({'iteration': it, 'cost': cost, 'gradient_inf': gn})
        if gn <= gradient_tol:
            status = 'CONVERGED'
            break
        if it == max_iter:
            break
        step = np.linalg.solve(info, -grad)
        directional = float(grad@step)
        accepted = False
        for j in range(max_step_halvings+1):
            t = 2.**(-j)
            actual_step = t*step
            candidate = y+actual_step
            new_cost, new_grad, _ = evaluate(candidate)
            # R3: never infer descent by subtracting two O(1) costs.
            # Use J(y+d)-J(y) = rho(y).Delta_rho + .5||Delta_rho||^2
            # for the ORIGINAL Gaussian posterior. No roundoff slack.
            if new_grad is None or not np.isfinite(new_cost):
                continue
            h0, _ = model(mu + Lp@y)
            h1, _ = model(mu + Lp@candidate)
            v0 = np.linalg.solve(Lr, z-np.asarray(h0, float))
            dv = np.linalg.solve(Lr, np.asarray(h0, float)-np.asarray(h1, float))
            drho = np.r_[actual_step, dv]
            rho = np.r_[y, v0]
            from math import fsum
            stable_delta = fsum(float(u)*float(v) for u,v in zip(rho, drho))
            stable_delta += .5*float(drho@drho)
            # Use the true-gradient line integral only near the cancellation
            # floor where h(x+d)-h(x) itself can become inaccurate.
            near_floor = abs(new_cost-cost) <= 256*np.finfo(float).eps*max(1., abs(cost))
            if near_floor:
                _, ghalf, _ = evaluate(y+.5*actual_step)
                if ghalf is not None:
                    integral = fsum(float(a)*float(d) for a,d in zip(
                        (grad+4*ghalf+new_grad)/6., actual_step))
                    # Both are algebraically the same objective. Divergence at
                    # roundoff is handled conservatively; never fake success.
                    if np.isfinite(integral) and integral < 0.:
                        if stable_delta >= 0. or abs(stable_delta-integral) > max(
                            1e-14*abs(integral), 100*np.finfo(float).eps*abs(integral)):
                            stable_delta = integral
                            history[-1]['stable_method'] = 'GRADIENT_INTEGRAL'
            if stable_delta <= 1e-4*t*directional and stable_delta < 0.:
                y = candidate
                history[-1]['step_fraction'] = t
                history[-1]['step_acceptance'] = 'STABLE_OBJECTIVE_DESCENT'
                history[-1]['stable_delta'] = stable_delta
                history[-1]['candidate_gradient_inf'] = float(np.max(np.abs(new_grad)))
                accepted = True
                break
        if not accepted:
            status = 'LINE_SEARCH_FAILED'
            break
    cost, grad, info = evaluate(y)
    if info is None:
        return MAPResult(mu.copy(), P.copy(), status, len(history)-1, cost,
                         math.inf, np.zeros(n), history)
    delta = Lp@y
    out = mu+delta
    out[2] = wrap(out[2])
    cov = covariance(Lp@np.linalg.solve(info, Lp.T), n, positive=True)
    return MAPResult(out, cov, status, len(history)-1, cost,
                     float(np.max(np.abs(grad))), delta, history)


class SyntheticRF:
    """Declared SYNTHETIC model, NOT FFD, not a calibrated real RF model.

    range=sqrt(dx^2+dy^2+height^2); s=.8*sin(yaw)+.15*sin(azimuth).
    Weak spatial coupling is deliberate; all s branches remain periodic.
    """
    def __init__(self, anchor=(-2., 3.), height=1.3):
        self.anchor = np.asarray(anchor, float)
        self.height = float(height)

    def __call__(self, x):
        x = state_vector(x)
        p = x[:2]-self.anchor
        q = float(p@p)
        if q < 1e-14:
            raise ValueError('undefined azimuth at anchor horizontal position')
        rho = math.sqrt(q+self.height**2)
        az = math.atan2(p[1], p[0])
        h = np.array([rho, .8*math.sin(x[2])+.15*math.sin(az)])
        H = np.zeros((2, len(x)))
        H[0, :2] = p/rho
        H[1, :2] = .15*math.cos(az)*np.array([-p[1], p[0]])/q
        H[1, 2] = .8*math.cos(x[2])
        return h, H
