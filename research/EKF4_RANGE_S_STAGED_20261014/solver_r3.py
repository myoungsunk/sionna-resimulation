"""R3 finite-precision descent decisions for the *unchanged* MAP objective.

This is a conservative numerical guard, not interval arithmetic or proof
of global optimality. No tolerance, prior, model, Q/R or covariance changes.
"""
import math
import numpy as np


def resolved_armijo(c0, c1, slope0, *, sufficient_decrease=1e-4):
    """Accept only a *resolved* float64 decrease and strict Armijo.

    The absolute 32-eps margin is intentionally subtractive (NOT the
    previous "+ roundoff" tolerance that admitted uphill steps).
    Ambiguous costs are delegated to a true-gradient path integral.
    """
    if not all(map(math.isfinite, (c0, c1, slope0))):
        return False
    if slope0 >= 0 or not (0 < sufficient_decrease < 1):
        return False
    margin = 32*np.finfo(float).eps*max(1., abs(c0), abs(c1))
    delta = math.fsum([float(c1), -float(c0)])
    return bool(delta < -margin and delta <= sufficient_decrease*slope0)


def exact_newton_direction(evaluate, y, grad, *, diff_step=1e-4):
    """Guarded local fallback Hessian via central difference of true grad.

    Hessian must be symmetric to the differentiation accuracy, PD, and
    reasonably conditioned. Never substitutes a SciPy success flag for
    the caller's original ||gradient||_inf criterion.
    """
    y = np.asarray(y, dtype=float)
    grad = np.asarray(grad, dtype=float)
    n = len(y)
    H = np.empty((n,n), dtype=float)
    for j in range(n):
        h = diff_step*(1.+abs(float(y[j])))
        displacement = np.zeros(n)
        displacement[j] = h
        _, gp, _ = evaluate(y+displacement)
        _, gm, _ = evaluate(y-displacement)
        if gp is None or gm is None:
            return None
        if not np.isfinite(gp).all() or not np.isfinite(gm).all():
            return None
        H[:,j] = (gp-gm)/(2*h)
    if not np.isfinite(H).all():
        return None
    symmetry_error = np.linalg.norm(H-H.T, ord=np.inf)
    if symmetry_error > 1e-3*max(1., np.linalg.norm(H, ord=np.inf)):
        return None
    H = (H+H.T)*.5
    w = np.linalg.eigvalsh(H)
    if w[0] <= 1e-9 or w[-1]/w[0] > 1e10:
        return None
    step = np.linalg.solve(H, -grad)
    if not np.isfinite(step).all():
        return None
    slope = math.fsum(float(a)*float(b) for a,b in zip(grad,step))
    return step if slope < 0 else None
