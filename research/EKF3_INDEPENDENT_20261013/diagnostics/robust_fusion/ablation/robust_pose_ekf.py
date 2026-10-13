"""True 3-state robust RF ablation; same block-Huber objective as M1.

Updater copied from m1_bias_robust_ekf.py with state dimension 4 -> 3 only.
Prediction calls the original EKF3, with no hidden bias state.
"""
import math
import numpy as np
from scipy.optimize import brentq
from m1_bias_robust_ekf import covariance_check, huber_block
from d6_d9_common import DiagnosticFilter, range_h, wrap

class RobustPoseEKF:
    def __init__(self, x0):
        self.filter = DiagnosticFilter(np.asarray(x0, float))
        self.max_iterations = 100
        self.convergence_tol = 1e-10

    @property
    def x(self): return self.filter.f.x
    @property
    def P(self): return self.filter.f.P
    @property
    def pose(self): return self.x
    @property
    def Ppose(self): return self.P
    def predict(self, ds, dtheta, dt):
        self.filter.predict(ds, dtheta, dt)

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
        x0, p0 = self.x.copy(), covariance_check(self.P, 3, 'prior covariance')
        predictions, rows = [], []
        for j in indices:
            h, jac = model(x0[:3].copy()) if j == 0 else range_h(x0, anchor, height)
            jac = np.asarray(jac, float)
            if jac.shape != (3,) or not np.isfinite(jac).all() or not math.isfinite(h):
                raise ValueError('Invalid RF model/Jacobian')
            predictions.append(h)
            rows.append(jac)
        hmat = np.asarray(rows)
        y = np.asarray([(z_s, r_physical)[j] for j in indices]) - predictions - mu
        lower = np.linalg.cholesky(r)
        whiten_y = np.linalg.solve(lower, y)
        whiten_h = np.linalg.solve(lower, hmat)
        information = np.linalg.solve(p0, np.eye(3))
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
        a = np.eye(3) - gain @ hmat
        posterior = covariance_check(a @ p0 @ a.T + gain @ effective_r @ gain.T,
                                     3, 'posterior covariance')
        new_x = x0 + d
        new_x[2] = wrap(new_x[2])
        if not np.isfinite(new_x).all():
            raise ValueError('Nonfinite posterior state')
        unweighted_s = hmat @ p0 @ hmat.T + r
        nis = float(y @ np.linalg.solve(unweighted_s, y))
        self.filter.f.x, self.filter.f.P = new_x, posterior
        return {'status': 'applied', 'NIS': nis, 'iterations': iteration,
                'huber_weight': weight, 'huber_loss': loss, 'innovation': y,
                'whitened_residual': whiten_y - whiten_h @ d,
                'objective': .5 * float(d @ information @ d) + loss,
                'stationarity_norm': float(np.linalg.norm(information @ d - whiten_h.T @ gradient)),
                'H': hmat, 'K': gain, 'R_effective': effective_r,
                'covariance_convention': 'LOCAL_IRLS_GAUSSIAN_JOSEPH_APPROXIMATION',
                'NIS_interpretation': 'DESCRIPTIVE_UNWEIGHTED_PRIOR_NIS_NOT_CHI2_GATE'}
