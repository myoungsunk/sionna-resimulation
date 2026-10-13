"""Bias4 EKF with fixed-prior, fixed-linearization block Huber MAP updates.

RF mean/covariance are supplied by the held-out training contract. Covariance
is the local IRLS Gaussian/Joseph approximation, not an exact Huber posterior.
No truth input, RF gate, covariance projection, or repeated prior information.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from d6_d9_common import DiagnosticFilter, range_h, wrap


def huber_block(residual, delta):
    """Return radial loss, one scalar block weight, and whitened gradient."""
    v = np.asarray(residual, float)
    if not np.isfinite(v).all() or not (delta > 0):
        raise ValueError('Finite residual and positive Huber delta required')
    norm = float(np.linalg.norm(v))
    weight = 1. if norm <= delta else float(delta / norm)
    loss = .5 * norm**2 if norm <= delta else delta * (norm - .5 * delta)
    return float(loss), weight, weight * v


def covariance_check(p, n, name):
    p = np.asarray(p, float)
    if p.shape != (n, n) or not np.isfinite(p).all():
        raise ValueError(f'{name}: finite {n}x{n} required')
    if not np.allclose(p, p.T, atol=1e-12, rtol=1e-12):
        raise ValueError(f'{name}: nonsymmetric')
    p = (p + p.T) / 2
    if np.linalg.eigvalsh(p)[0] <= 0:
        raise ValueError(f'{name}: positive definite required; no jitter applied')
    return p


class RobustBiasEKF:
    def __init__(self, x0, bias_prior_std_dps=.1, bias_rw_dps_sqrt_s=0.,
                 *, pose_cov=None, bias_initial_rad_s=0., max_iterations=100,
                 convergence_tol=1e-10):
        x0 = np.asarray(x0, float)
        if x0.shape != (3,) or not np.isfinite(x0).all():
            raise ValueError('Finite three-state initial pose required')
        if not all(math.isfinite(v) for v in (bias_prior_std_dps,
                bias_rw_dps_sqrt_s, bias_initial_rad_s, convergence_tol)):
            raise ValueError('Nonfinite initial parameter')
        if bias_prior_std_dps <= 0 or bias_rw_dps_sqrt_s < 0:
            raise ValueError('Invalid bias uncertainty')
        if max_iterations < 1 or convergence_tol <= 0:
            raise ValueError('Invalid IRLS convergence contract')
        self.filter = DiagnosticFilter(x0, bias_state=True,
            bias_std_dps=bias_prior_std_dps, bias_rw_dps_sqrt_s=bias_rw_dps_sqrt_s)
        self.filter.x[3] = bias_initial_rad_s
        if pose_cov is not None:
            self.filter.P[:3, :3] = covariance_check(pose_cov, 3, 'pose prior')
        self.max_iterations = int(max_iterations)
        self.convergence_tol = convergence_tol

    @property
    def x(self):
        return self.filter.x

    @property
    def P(self):
        return self.filter.P

    @property
    def pose(self):
        return self.filter.pose

    @property
    def Ppose(self):
        return self.filter.Ppose

    def predict(self, ds, dtheta, dt):
        if not all(math.isfinite(v) for v in (ds, dtheta, dt)) or dt <= 0:
            raise ValueError('Finite motion and positive dt required')
        old_x, old_p = self.x.copy(), self.P.copy()
        try:
            self.filter.predict(ds, dtheta, dt)
            covariance_check(self.P, 4, 'predicted covariance')
            if not np.isfinite(self.x).all():
                raise ValueError('Nonfinite predicted state')
        except Exception:
            self.filter.x, self.filter.P = old_x, old_p
            raise

    def update(self, arm, z_s, r_physical, model, anchor, height,
               mean, cov, huber_delta):
        """mean/cov ordered [s, range], or scalar-sized for A/B.

        Missing C components select subblocks. Infinities/NaNs represent missing
        observations; invalid model, covariance or convergence fails closed.
        huber_delta=inf selects the Gaussian measurement update.
        """
        if arm not in ('D0', 'A', 'B', 'C'):
            raise ValueError('Unknown observation arm')
        if arm == 'D0':
            return {'status': 'DR_only', 'iterations': 0, 'NIS': None}
        if not (huber_delta > 0):
            raise ValueError('Positive Huber delta required')
        indices = [j for j in ([0] if arm == 'A' else [1] if arm == 'B' else [0, 1])
                   if (z_s, r_physical)[j] is not None
                   and math.isfinite(float((z_s, r_physical)[j]))]
        if not indices:
            return {'status': 'missing', 'iterations': 0, 'NIS': None}
        mu = np.asarray(mean, float).reshape(-1)
        r = np.asarray(cov, float)
        if mu.size == 2 and r.shape == (2, 2):
            r = covariance_check(r, 2, 'RF total covariance')[np.ix_(indices, indices)]
            mu = mu[indices]
        elif arm in ('A', 'B') and mu.size == 1 and r.shape == (1, 1):
            r = covariance_check(r, 1, 'RF total covariance')
        else:
            raise ValueError('RF mean/covariance dimensions incompatible with arm')
        if not np.isfinite(mu).all():
            raise ValueError('Nonfinite RF mean')
        x0, p0 = self.x.copy(), covariance_check(self.P, 4, 'prior covariance')
        predictions, rows = [], []
        for j in indices:
            h, jac = model(x0[:3].copy()) if j == 0 else range_h(x0, anchor, height)
            jac = np.asarray(jac, float)
            if jac.shape != (3,) or not np.isfinite(jac).all() or not math.isfinite(h):
                raise ValueError('Invalid RF model/Jacobian')
            predictions.append(h)
            rows.append(np.r_[jac, 0.])
        hmat = np.asarray(rows)
        y = np.asarray([(z_s, r_physical)[j] for j in indices]) - predictions - mu
        lower = np.linalg.cholesky(r)
        whiten_y = np.linalg.solve(lower, y)
        whiten_h = np.linalg.solve(lower, hmat)
        information = np.linalg.solve(p0, np.eye(4))
        def solve_weight(weight):
            return np.linalg.solve(information + weight * whiten_h.T @ whiten_h,
                                   weight * whiten_h.T @ whiten_y)
        d = solve_weight(1.)
        iteration = 1
        if np.linalg.norm(whiten_y - whiten_h @ d) > huber_delta:
            # Same convex fixed-prior block-Huber MAP. Scalar safeguarded root
            # avoids arbitrarily slow IRLS near the Huber transition.
            def equation(weight):
                if weight == 0.: return -huber_delta
                residual = whiten_y - whiten_h @ solve_weight(weight)
                return weight * np.linalg.norm(residual) - huber_delta
            try:
                weight, result = brentq(equation, 0., 1., xtol=1e-14,
                    rtol=1e-14, maxiter=self.max_iterations, full_output=True)
            except (RuntimeError, ValueError) as exc:
                raise RuntimeError('Fixed-prior Huber solve did not converge; update unapplied') from exc
            if not result.converged:
                raise RuntimeError('Fixed-prior Huber solve did not converge; update unapplied')
            d = solve_weight(weight)
            iteration = result.iterations
        loss, weight, gradient = huber_block(whiten_y - whiten_h @ d, huber_delta)
        effective_r = r / weight
        s = hmat @ p0 @ hmat.T + effective_r
        gain = np.linalg.solve(s, hmat @ p0).T
        a = np.eye(4) - gain @ hmat
        posterior = covariance_check(a @ p0 @ a.T + gain @ effective_r @ gain.T,
                                     4, 'posterior covariance')
        new_x = x0 + d
        new_x[2] = wrap(new_x[2])
        if not np.isfinite(new_x).all():
            raise ValueError('Nonfinite posterior state')
        unweighted_s = hmat @ p0 @ hmat.T + r
        nis = float(y @ np.linalg.solve(unweighted_s, y))
        self.filter.x, self.filter.P = new_x, posterior
        return {'status': 'applied', 'NIS': nis, 'iterations': iteration,
                'huber_weight': weight, 'huber_loss': loss, 'innovation': y,
                'whitened_residual': whiten_y - whiten_h @ d,
                'objective': .5 * float(d @ information @ d) + loss,
                'stationarity_norm': float(np.linalg.norm(information @ d - whiten_h.T @ gradient)),
                'H': hmat, 'K': gain, 'R_effective': effective_r,
                'covariance_convention': 'LOCAL_IRLS_GAUSSIAN_JOSEPH_APPROXIMATION',
                'NIS_interpretation': 'DESCRIPTIVE_UNWEIGHTED_PRIOR_NIS_NOT_CHI2_GATE'}
