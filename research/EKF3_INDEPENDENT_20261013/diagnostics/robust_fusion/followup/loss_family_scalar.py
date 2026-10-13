"""Candidate radial MAP solver; original loss and guard constants unchanged.

No RF updater is modified or monkeypatched by importing this module. Enumerate
real positive polynomial stationary weights, polish the original rational
equation, and check each candidate against the original 3D gradient/Hessian.
Finite precision root enumeration is not a formal global-optimality proof.
"""
import math
import numpy as np
from scipy.optimize import brentq
from loss_family import block_loss


def solve_map(y, hmat, p0, scale, family, parameter):
    lp=np.linalg.cholesky(p0); lr=np.linalg.cholesky(scale)
    b=np.linalg.solve(lr,y); a=np.linalg.solve(lr,hmat@lp)
    if len(b) not in (1,2): raise ValueError('One or two observation dimensions required')
    eigen,u=np.linalg.eigh(a@a.T)
    if eigen.min() < -1e-12*max(1.,eigen.max()):
        raise RuntimeError('Invalid radial observation information')
    eigen=np.maximum(eigen,0.); rotated=u.T@b; b2=rotated**2
    block_loss(b,family,parameter)  # Validate before constructing coefficients.
    alpha=parameter**2 if family=='cauchy' else parameter
    beta=alpha if family=='cauchy' else parameter+len(b)
    wmax=beta/alpha
    factors=[np.array([1.,2*wmax*ev,(wmax*ev)**2]) for ev in eigen]
    denominator=np.array([1.])
    for factor in factors: denominator=np.polynomial.polynomial.polymul(denominator,factor)
    polynomial=np.polynomial.polynomial.polymul([-1.,1.],denominator)
    for i in range(len(b)):
        other=np.array([1.])
        for j,factor in enumerate(factors):
            if j!=i: other=np.polynomial.polynomial.polymul(other,factor)
        polynomial=np.polynomial.polynomial.polyadd(polynomial,
            np.polynomial.polynomial.polymul([0.,b2[i]/alpha],other))
    roots=np.polynomial.polynomial.polyroots(polynomial/np.max(np.abs(polynomial)))
    def equation(t):
        q=float(np.sum(b2/(1+t*wmax*eigen)**2))
        return t*(1+q/alpha)-1
    candidates=[]
    real=[float(z.real) for z in roots if abs(z.imag)<=1e-7*max(1.,abs(z.real))
          and z.real>0 and z.real<=1+1e-10]
    # Full-interval safeguarded root independently supplies at least one candidate.
    real.append(brentq(equation,0.,1.,xtol=1e-14,rtol=1e-14,maxiter=100))
    polishing_iterations=0
    for initial in real:
        t=min(initial,1.)
        for iteration in range(12):
            div=1+t*wmax*eigen
            q=float(np.sum(b2/div**2))
            derivative=1+q/alpha-2*t*wmax*float(np.sum(b2*eigen/div**3))/alpha
            value=t*(1+q/alpha)-1
            if abs(value)<=1e-13: break
            if not math.isfinite(derivative) or derivative==0: break
            proposed=t-value/derivative
            if not 0<proposed<=1: break
            t=proposed
        polishing_iterations+=iteration+1
        weight=t*wmax
        v=a.T@(u@(weight*rotated/(1+weight*eigen)))
        residual=b-a@v
        loss,checked_weight,gradient,hessian=block_loss(residual,family,parameter)
        grad=v-a.T@gradient
        stationarity=float(np.linalg.norm(grad))
        objective=.5*float(v@v)+loss
        curvature=np.eye(3)+a.T@hessian@a
        if (np.isfinite(v).all() and math.isfinite(objective)
                and stationarity<=1e-7 and np.linalg.eigvalsh(curvature)[0]>=-1e-10
                and objective<=block_loss(b,family,parameter)[0]+1e-10):
            candidates.append((objective,v,stationarity,checked_weight,residual))
    if not candidates:
        raise RuntimeError('Radial robust MAP guard failed; update unapplied')
    objective,v,stationarity,weight,residual=min(candidates,key=lambda item:item[0])
    return dict(delta=lp@v,objective=objective,stationarity_norm=stationarity,
        robust_weight=float(weight),whitened_residual=residual,
        iterations=polishing_iterations,converged_starts=len(candidates),
        attempted_starts=len(real),optimizer_success=True,
        optimization_claim='NONCONVEX_LOCAL_MINIMUM_ONLY',
        solver='RADIAL_POLYNOMIAL_STATIONARY_CANDIDATES')
