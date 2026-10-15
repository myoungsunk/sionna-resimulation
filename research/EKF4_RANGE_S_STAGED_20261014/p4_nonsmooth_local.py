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
from p4_lut_boundary import boundary_report, segment_crossings

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

def frozen_lut_angles(x,case):
    """Actual three angular trilinear LUT coordinates, in degrees."""
    ax,ay,az=case["anchor"]
    u,v=float(x[0]-ax),float(x[1]-ay)
    theta=math.degrees(math.atan2(math.hypot(u,v),az-case["robot_z_m"]))
    tx=math.degrees(math.atan2(-v,u))
    rx=(math.degrees(math.atan2(-v,-u))-math.degrees(x[2])
        -case["mount_deg"]+180.)%360.-180.
    return np.array([theta,tx,rx])

def directional_descent_polish(cost,y,lower,upper,max_rounds=32,*,context=None):
    """Do not stop at coordinate-wise Powell stagnation on tilted LUT facets.

    Probe the *actual objective* along deterministic off-axis directions
    and follow only real signed decreases. The same original objective
    and local domain bounds are maintained.
    """
    y=np.asarray(y,float).copy()
    directions=probe_directions(len(y))
    trace=[]
    for iteration in range(max_rounds):
        c0=cost(y)
        h=2e-5
        diffs=np.array([cost(y+h*d)-c0 if np.all(y+h*d>=lower)
                        and np.all(y+h*d<=upper) else np.inf
                        for d in directions])
        ranked=np.argsort(diffs)[:8]
        best_y=y
        best_cost=c0
        for idx in ranked:
            d=directions[idx]
            alphas=[h,4*h,20*h,100*h,1000*h]
            if context is not None:
                mu,Lp,case=context
                reach=1000*h
                segment=segment_crossings(mu+Lp@y,mu+Lp@(y+reach*d),
                                          case,samples=33)
                if segment["status"]=="CROSSING":
                    for crossing in segment["events"][:6]:
                        alpha=reach*crossing["cross_fraction"]
                        alphas.extend([max(0.,alpha-1e-7),alpha,
                                       min(reach,alpha+1e-7)])
            for alpha in sorted(set(alphas)):
                if alpha<=0:continue
                candidate=y+alpha*d
                if not(np.all(candidate>=lower) and np.all(candidate<=upper)):
                    continue
                cj=cost(candidate)
                if cj<best_cost-1e-13:
                    best_y,best_cost=candidate,cj
        if best_cost>=c0-1e-13:
            break
        trace.append(float(best_cost-c0))
        y=best_y.copy()
        # Recompute local off-axis descent after movement; DO NOT accept
        # optimizer 'success' without the final true-objective verification.
    return y,trace

def local_nonsmooth_minimize(mu,P,z,model,*,warm_delta=None,
                             maxfev=24000,kink_case=None):
    cost,grad,Lp=fixed_objective(mu,P,z,model)
    n=len(mu)
    start=np.linalg.solve(Lp,warm_delta) if warm_delta is not None else np.zeros(n)
    c0=cost(start)
    lower=start-.75
    upper=start+.75
    bounds=list(zip(lower,upper))
    pw=minimize(cost,start,method="Powell",bounds=bounds,
        options={"maxiter":650,"maxfev":maxfev,"xtol":2e-10,"ftol":1e-12})
    candidates=[{"x":np.asarray(pw.x,float),"method":"POWELL",
                 "optimizer_success":bool(pw.success)}]
    crossing_details=[]
    boundary_candidates=[]
    if kink_case is not None:
        for base in (start,np.asarray(pw.x,float)):
            g=np.asarray(grad(base),float)
            if np.isfinite(g).all() and np.linalg.norm(g)>0:
                direction=-.05*g/np.linalg.norm(g)
                tmax=1.
                for i,di in enumerate(direction):
                    if di>0:tmax=min(tmax,max(0.,(upper[i]-base[i])/di))
                    elif di<0:tmax=min(tmax,max(0.,(lower[i]-base[i])/di))
                direction*=tmax
                scan=segment_crossings(mu+Lp@base,mu+Lp@(base+direction),
                                       kink_case,samples=129)
                crossing_details.append({
                    "status":scan["status"],
                    "events":scan.get("events",[])[:12]})
                if scan["status"]=="CROSSING":
                    for event in scan["events"][:12]:
                        yy=base+event["cross_fraction"]*direction
                        if np.all(yy>=lower) and np.all(yy<=upper) and np.isfinite(cost(yy)):
                            boundary_candidates.append({
                                "x":yy,"method":"LUT_BOUNDARY_INTERSECTION",
                                "optimizer_success":False,
                                "boundary":event["dimension"],
                                "fraction":event["cross_fraction"]})
    candidates.extend(boundary_candidates)
    # Active-grid facet constrained optimization: at a kink, tangent descent
    # can exist even when axis-parallel Powell appears stationary. The equality
    # only defines SEARCH SUBSPACE; final J is always ORIGINAL unsmoothed J.
    tried=0
    if kink_case is not None:
        refs=[start,np.asarray(pw.x,float)]
        for base in refs:
            angles=frozen_lut_angles(mu+Lp@base,kink_case)
            masks=[]
            for i,val in enumerate(angles):
                nearest=2*round(val/2)
                if abs(nearest-val)<.2:
                    masks.append((i,nearest))
            constraint_sets=[(one,) for one in masks]
            constraint_sets += [(masks[i],masks[j]) for i in range(len(masks))
                                for j in range(i+1,len(masks))]
            for facets in constraint_sets:
                def make_constraint(coord,target):
                    return {"type":"eq",
                       "fun":lambda y,coord=coord,target=target:
                             (float(frozen_lut_angles(mu+Lp@y,kink_case)[coord])
                              -target+180.)%360.-180.}
                constr=[make_constraint(*v) for v in facets]
                tried+=1
                try:
                    sol=minimize(cost,base,method="SLSQP",
                         bounds=bounds,constraints=constr,
                         options={"maxiter":220,"ftol":1e-12,"disp":False})
                    y=np.asarray(sol.x,float)
                    residual=max(abs(c["fun"](y)) for c in constr)
                    if (np.isfinite(y).all() and math.isfinite(cost(y)) and
                            residual<=1e-4 and cost(y)<=c0):
                        candidates.append({"x":y,"method":"ACTIVE_LUT_FACET",
                           "facets":[[int(v[0]),float(v[1])] for v in facets],
                           "optimizer_success":bool(sol.success),
                           "constraint_residual_deg":float(residual)})
                except (ArithmeticError,ValueError):
                    continue
    # Recheck cross-facet descent that Powell axis searches can miss.
    # Do not make a generalized-stationarity claim from this step alone.
    polished=[]
    for initial in sorted(candidates,key=lambda c:cost(c["x"]))[:3]:
        yy,improvements=directional_descent_polish(
            cost,initial["x"],lower,upper,
            context=(mu,Lp,kink_case) if kink_case is not None else None)
        if improvements:
            polished.append({"x":yy,"method":"DIRECTIONAL_BUNDLE_POLISH",
                "optimizer_success":True,"descent_rounds":len(improvements),
                "total_verified_delta":sum(improvements)})
    candidates.extend(polished)
    qualified=[]
    for cand in candidates:
        y=cand["x"]
        c1=cost(y)
        probe=local_probe(cost,y)
        hull=clarke_hull_proxy(grad,y)
        smooth_g=float(np.max(abs(grad(y))))
        # Approximate local non-smooth stationarity, NOT old smooth 1e-8.
        passed=bool(
            np.isfinite(c1) and c1<=c0
            and probe["min_directional_slope"]>=-1e-5
            and hull["status"]=="APPROXIMATE_HULL"
            and hull["norm"]<=1e-3)
        qualified.append((passed,float(c1),cand,probe,hull,smooth_g))
    # Prefer the best verified local solution; do NOT report "CONVERGED"
    # from mere SciPy optimizer flags. If none verified, return the
    # smallest-cost UNVERIFIED candidate without making a science claim.
    available=[r for r in qualified if r[0]]
    best=min(available or qualified,key=lambda v:v[1])
    passed,c1,selected,probe,hull,smooth_g=best
    y=selected["x"]
    delta=Lp@y
    geometry_at_selected=(boundary_report(mu+Lp@y,kink_case)
                          if kink_case is not None else None)
    return {"boundary_detector":geometry_at_selected,
            "crossing_scans":crossing_details,
            "explicit_boundary_candidates":len(boundary_candidates),
            "terminal_status":("NONSMMOOTH_LOCAL_CANDIDATE_VERIFIED"
                if passed else "NONSMMOOTH_LOCAL_UNVERIFIED"),
            "candidate_strategy":selected["method"],
            "active_set_tried":tried,
            "active_set_candidates":sum(c["method"]=="ACTIVE_LUT_FACET"
                for c in candidates),
            "original_smooth_gradient_satisfied":smooth_g<=1e-8,
            "original_smooth_gradient_inf":smooth_g,
            "powell_success":bool(pw.success),
            "powell_message":str(pw.message),
            "powell_nfev":int(pw.nfev),"powell_nit":int(pw.nit),
            "J_initial":float(c0),"J_final":float(c1),
            "J_delta":float(c1-c0),
            "probe":probe,"clarke_hull_proxy":hull,
            "local_step_inf":float(np.max(abs(y-start))),
            "posterior_delta":delta,
            "candidate_x":mu+delta}
