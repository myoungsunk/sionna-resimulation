"""Derivative-free, cell-aware nonsmooth LOCAL MAP optimizer candidate.

It preserves EXACT P4 prior/likelihood/LUT and returns a NEW, explicitly
separate terminal status. Never substitutes for original R4 'CONVERGED'.

Criterion: cost not increased, stable Powell minimization, 112 deterministic
2-sided unit-direction probes, and approximate Clarke subgradient hull of
neighboring active LUT cells. Not a global-minimum or interval certificate.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.optimize import minimize
from core import map_update
from p3_rf_adapter4 import R0

def fixed_objective(mu,P,z,model):
    mu=np.asarray(mu,float);P=np.asarray(P,float);z=np.asarray(z,float)
    Lp,Lr=np.linalg.cholesky(P),np.linalg.cholesky(R0)
    def cost(y):
        y=np.asarray(y,float)
        delta=Lp@y
        if np.abs(delta[2])>=np.pi:return float("inf")
        h,_=model(mu+delta)
        res=np.linalg.solve(Lr,z-h)
        return float(.5*(y@y+res@res))
    def smooth_cell_gradient(y):
        y=np.asarray(y,float)
        delta=Lp@y
        h,H=model(mu+delta)
        v=np.linalg.solve(Lr,z-h)
        B=np.linalg.solve(Lr,H@Lp)
        return y-B.T@v
    return cost,smooth_cell_gradient,Lp

def probe_directions(dims,seed=26015):
    rng=np.random.default_rng(seed)
    dirs=[]
    for i in range(dims):
        e=np.eye(dims)[i]
        dirs.extend([e,-e])
    for _ in range(96):
        v=rng.normal(size=dims)
        v/=np.linalg.norm(v)
        dirs.append(v)
    return np.asarray(dirs,float)

def local_probe(cost,y,scale=2e-5):
    dirs=probe_directions(len(y))
    c=float(cost(y))
    vals=np.array([(cost(y+scale*d)-c)/scale for d in dirs])
    return {"min_directional_slope":float(vals.min()),
            "negative_beyond_1e_minus_5":int((vals< -1e-5).sum()),
            "probe_count":len(dirs),
            "scale_whitened":scale}

def clarke_hull_proxy(gradient,y,radius=1e-7,seed=771):
    # Neighboring active cells can have different one-sided gradients at a
    # trilinear LUT knot. Sample in the 4-state whitened local chart.
    grads=[gradient(y)]
    for d in probe_directions(len(y),seed=seed):
        grads.append(gradient(y+radius*d))
    G=np.asarray(grads)
    if not np.isfinite(G).all():
        return {"status":"UNAVAILABLE","norm":None}
    n=len(G)
    def fun(w):
        g=w@G
        return float(g@g)
    def jac(w):return 2*(G@(w@G))
    guess=np.full(n,1/n)
    result=minimize(fun,guess,jac=jac,method="SLSQP",
        bounds=[(0.,1.)]*n,constraints={"type":"eq","fun":lambda w:np.sum(w)-1,
                                        "jac":lambda w:np.ones_like(w)},
        options={"maxiter":350,"ftol":1e-16})
    if not result.success:
        # A solver failure does not certify generalized stationarity.
        return {"status":"OPTIMIZER_UNVERIFIED","norm":None,
                "message":str(result.message)}
    return {"status":"APPROXIMATE_HULL","norm":float(math.sqrt(max(fun(result.x),0.))),
            "samples":n,"radius_whitened":radius}

def local_nonsmooth_minimize(mu,P,z,model,*,warm_delta=None,maxfev=24000):
    cost,grad,Lp=fixed_objective(mu,P,z,model)
    n=len(mu)
    start=np.linalg.solve(Lp,warm_delta) if warm_delta is not None else np.zeros(n)
    c0=cost(start)
    # Strict local scope around the ORIGINAL failing iterate. No global mode
    # hopping or truth-based choice of starts.
    lower=start-.75
    upper=start+.75
    def obj(y):return cost(y)
    result=minimize(obj,start,method="Powell",
        bounds=list(zip(lower,upper)),
        options={"maxiter":650,"maxfev":maxfev,"xtol":2e-10,"ftol":1e-12})
    y=np.asarray(result.x,float)
    c1=cost(y)
    probe=local_probe(cost,y)
    hull=clarke_hull_proxy(grad,y)
    smooth_g=float(np.max(abs(grad(y))))
    # Different non-smooth criterion. Not original 1e-8 gradient success.
    passed=bool(
        result.success and np.isfinite(c1) and c1<=c0+1e-11
        and probe["min_directional_slope"]>=-1e-5
        and hull["status"]=="APPROXIMATE_HULL"
        and hull["norm"]<=1e-3)
    delta=Lp@y
    return {"terminal_status":("NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED"
                if passed else "NONSMMOOTH_LOCAL_UNVERIFIED"),
            "original_smooth_gradient_satisfied":smooth_g<=1e-8,
            "original_smooth_gradient_inf":smooth_g,
            "powell_success":bool(result.success),
            "powell_message":str(result.message),
            "powell_nfev":int(result.nfev),"powell_nit":int(result.nit),
            "J_initial":float(c0),"J_final":float(c1),
            "J_delta":float(c1-c0),
            "probe":probe,"clarke_hull_proxy":hull,
            "local_step_inf":float(np.max(abs(y-start))),
            "posterior_delta":delta,
            "candidate_x":mu+delta}
