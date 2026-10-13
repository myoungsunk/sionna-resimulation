"""Fixed-prior block Cauchy/Student-t diagnostic updates, no learned mean.

Student-t uses scale (nu-2)/nu R0, whose finite covariance is R0. Cauchy
is an M-estimator with R0 whitening, not a finite-variance Cauchy density.
MAP solutions are checked local minima; multistarts do not prove globality.
"""
import math
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
from m1_bias_robust_ekf import covariance_check
from d6_d9_common import (DiagnosticFilter, range_h, wrap, RS, RR,
                          GATE_1D_99, GATE_2D_99)


def block_loss(residual, family, parameter):
    """Return loss, common block weight, gradient and residual Hessian."""
    v = np.asarray(residual, float).reshape(-1)
    if not np.isfinite(v).all() or not v.size:
        raise ValueError('Finite nonempty residual required')
    q = float(v @ v)
    a = float(parameter)
    if family == 'cauchy':
        if not math.isfinite(a) or a <= 0:
            raise ValueError('Finite positive Cauchy scale required')
        denominator = a*a + q
        loss = .5*a*a*math.log1p(q/(a*a))
        weight = a*a/denominator
    elif family == 'student_t':
        if not math.isfinite(a) or a <= 2:
            raise ValueError('Finite Student-t df > 2 required')
        denominator = a + q
        loss = .5*(a+v.size)*math.log1p(q/a)
        weight = (a+v.size)/denominator
    else:
        raise ValueError('Unknown loss family')
    gradient = weight*v
    hessian = weight*np.eye(v.size) - (2*weight/denominator)*np.outer(v,v)
    return loss, weight, gradient, hessian


def student_scale(r0, df):
    if not math.isfinite(float(df)) or df <= 2:
        raise ValueError('Finite Student-t df > 2 required')
    return np.asarray(r0, float)*((df-2)/df)


def solve_map(y, hmat, p0, scale, family, parameter):
    """Two deterministic MAP starts in prior-whitened coordinates.

    Analytic gradient/Hessian; reject nonstationary or saddle solutions. No
    Gaussian fallback is committed when optimization fails.
    """
    lp = np.linalg.cholesky(p0)
    lr = np.linalg.cholesky(scale)
    b = np.linalg.solve(lr, y)
    a = np.linalg.solve(lr, hmat @ lp)

    cached_v, cached_terms = None, None
    def terms(v):
        nonlocal cached_v, cached_terms
        if cached_v is not None and np.array_equal(v,cached_v):
            return cached_terms
        residual = b-a@v
        loss, weight, gradient, hessian = block_loss(residual, family, parameter)
        cached_v = np.asarray(v).copy()
        cached_terms = (.5*float(v@v)+loss, v-a.T@gradient,
                        np.eye(3)+a.T@hessian@a, weight, residual)
        return cached_terms

    starts = [np.zeros(3), np.linalg.solve(np.eye(3)+a.T@a, a.T@b)]
    candidates = []
    for start in starts:
        result = minimize(lambda v: terms(v)[0], start,
            jac=lambda v: terms(v)[1], hess=lambda v: terms(v)[2],
            method='trust-exact', options={'gtol': 1e-9, 'maxiter': 100})
        objective, gradient, hessian, weight, residual = terms(result.x)
        stationarity = float(np.linalg.norm(gradient))
        # Solver status alone is insufficient (roundoff can halt at a valid MAP).
        if (np.isfinite(result.x).all() and math.isfinite(objective)
                and stationarity <= 1e-7
                and np.linalg.eigvalsh(hessian)[0] >= -1e-10
                and objective <= terms(start)[0]+1e-10):
            candidates.append((objective, result, stationarity, weight, residual))
    if not candidates:
        raise RuntimeError('Robust MAP convergence/local-minimum guard failed; update unapplied')
    objective, result, stationarity, weight, residual = min(candidates,key=lambda item:item[0])
    return dict(delta=lp@result.x, objective=objective,
                stationarity_norm=stationarity, robust_weight=float(weight),
                whitened_residual=residual, iterations=int(result.nit),
                converged_starts=len(candidates), attempted_starts=2,
                optimizer_success=bool(result.success),
                optimization_claim='NONCONVEX_LOCAL_MINIMUM_ONLY')


class LossFamilyPoseEKF:
    def __init__(self, x0, map_solver=None):
        self.filter = DiagnosticFilter(np.asarray(x0,float))
        self.map_solver = map_solver

    @property
    def x(self): return self.filter.f.x
    @property
    def P(self): return self.filter.f.P
    @property
    def pose(self): return self.x
    @property
    def Ppose(self): return self.P
    def predict(self, ds, dtheta, dt): self.filter.predict(ds,dtheta,dt)

    def update(self, arm, z_s, r_physical, model, anchor, height, *,
               family, parameter, cov=None):
        if arm not in ('D0','A','B','C'): raise ValueError('Unknown observation arm')
        # Validate loss configuration even when this packet is absent.
        block_loss(np.zeros(1),family,parameter)
        empty = dict(iterations=0, robust_weight=None, huber_weight=None, NIS=None)
        if arm == 'D0': return dict(empty,status='DR_only')
        observations = (z_s,r_physical)
        indices = [j for j in ([0] if arm=='A' else [1] if arm=='B' else [0,1])
                   if observations[j] is not None and math.isfinite(float(observations[j]))]
        if not indices: return dict(empty,status='missing')
        r0 = covariance_check(np.diag([RS,RR]) if cov is None else cov,2,'RF R0')
        r0 = r0[np.ix_(indices,indices)]
        x0 = self.x.copy()
        p0 = covariance_check(self.P,3,'prior covariance')
        predictions, rows = [], []
        for j in indices:
            h,jac = model(x0.copy()) if j==0 else range_h(x0,anchor,height)
            jac = np.asarray(jac,float)
            if jac.shape != (3,) or not np.isfinite(jac).all() or not math.isfinite(h):
                raise ValueError('Invalid RF model/Jacobian')
            predictions.append(h); rows.append(jac)
        hmat = np.asarray(rows)
        y = np.asarray([observations[j] for j in indices])-predictions
        s0 = hmat@p0@hmat.T+r0
        nis = float(y@np.linalg.solve(s0,y))
        gate = GATE_1D_99 if len(indices)==1 else GATE_2D_99
        if nis > gate:
            return dict(empty,status='rejected_NIS',NIS=nis,gate_threshold=gate)
        scale = student_scale(r0,parameter) if family=='student_t' else r0
        result = (self.map_solver or solve_map)(y,hmat,p0,scale,family,parameter)
        effective_r = scale/result['robust_weight']
        gain = np.linalg.solve(hmat@p0@hmat.T+effective_r,hmat@p0).T
        a = np.eye(3)-gain@hmat
        posterior = covariance_check(a@p0@a.T+gain@effective_r@gain.T,3,'posterior covariance')
        new_x = x0+result.pop('delta')
        new_x[2] = wrap(new_x[2])
        if not np.isfinite(new_x).all(): raise ValueError('Nonfinite posterior state')
        self.filter.f.x,self.filter.f.P = new_x,posterior
        result.update(status='applied',NIS=nis,gate_threshold=gate,
            innovation=y,H=hmat,K=gain,R_effective=effective_r,R0=r0,
            likelihood_scale=scale,observation_dimension=len(indices),
            huber_weight=result['robust_weight'],
            covariance_convention='LOCAL_IRLS_GAUSSIAN_JOSEPH_APPROXIMATION',
            NIS_interpretation='UNWEIGHTED_PRIOR_R0_99_PERCENT_GATE')
        return result
