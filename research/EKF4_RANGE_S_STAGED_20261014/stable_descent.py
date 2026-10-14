"""R2 near-roundoff descent guard for the SAME local MAP objective.

Embedded quadrature errors are numerical diagnostics, not certified bounds.
This helper NEVER declares convergence: the caller retains ||gradient||inf.
"""
import math
import numpy as np


def integrated_descent(evaluate, y, d, c0, g0, c1, g1, info):
    if g1 is None or not np.isfinite(c1) or not np.isfinite(g1).all():
        return None
    eps=np.finfo(float).eps
    norm=lambda x:float(np.linalg.norm(x,np.inf))
    n0,n1=norm(g0),norm(g1)
    dot=lambda a,b:float(math.fsum(float(x)*float(v) for x,v in zip(a,b)))
    slope0=dot(g0,d);slope1=dot(g1,d)
    if not (slope0<0 and n1<n0 and abs(slope1)<=.9*abs(slope0)):
        return None
    if norm(d)>1e-6*max(1.,norm(y)):
        return None
    if abs(c1-c0)>64*eps*max(1.,abs(c0),abs(c1)):
        return None
    slopes=[slope0]
    for t in (.25,.5,.75):
        _,g,_=evaluate(y+t*d)
        if g is None or not np.isfinite(g).all():
            return None
        slopes.append(dot(g,d))
    slopes.append(slope1)
    s0,sq,sh,st,s1=slopes
    s2=math.fsum([s0,4*sh,s1])/6
    s4=math.fsum([s0,4*sq,2*sh,4*st,s1])/12
    trap=(s0+s1)/2
    err=abs(s4-s2)/15
    # The scale accounts for cancellation in y - B.T*v. It is a numerical
    # noise estimate, not an interval-arithmetic certificate for arbitrary h.
    gnoise=64*eps*(1+norm(y)+norm(y+d)+math.sqrt(max(1.,norm(info)))*math.sqrt(2*max(1.,abs(c0),abs(c1))))
    noise=float(np.linalg.norm(d,1))*gnoise
    if not (s4+8*err+noise<1e-4*slope0 and abs(s4-s2)<=.001*abs(s4)+noise):
        return None
    expected=info@d
    curv=norm(g1-g0-expected)/max(norm(expected),1e-30)
    return {'direct_cost_difference':float(c1-c0),
            'gradient_integral_difference':s4,'gradient_integral_coarse':s2,
            'gradient_integral_trapezoid':trap,'quadrature_error_indicator':err,
            'gradient_integral_noise_estimate':noise,
            'gradient_new_inf':n1,'curvature_ratio':curv,
            'strong_wolfe_ratio':abs(slope1/slope0),
            'R2_guard':'EMBEDDED_TRUE_GRADIENT_DESCENT_NOT_GN_CURVATURE_MATCH'}


import math
import numpy as np


def verified_step_r3(evaluate, y, d, c0, g0, c1, g1, info):
    if g1 is None or not (np.isfinite(c0) and np.isfinite(c1)
                           and np.isfinite(g1).all() and np.isfinite(g0).all()):
        return None
    dot=lambda u,v:float(math.fsum(float(a)*float(b) for a,b in zip(u,v)))
    slope=dot(g0,d)
    if not slope < 0:
        return None
    sufficient=1e-4*slope
    raw_diff=c1-c0
    eps=np.finfo(float).eps
    # Cost evaluation roundoff is proportional to the magnitude of J. A
    # change above this floor is used directly, without extra offset.
    floor=32*eps*max(abs(c0),abs(c1),1.)
    if raw_diff < sufficient and raw_diff < -floor:
        return {'acceptance':'ARMIJO_DIRECT_VERIFIED',
                'direct_cost_difference':float(raw_diff),
                'gradient_new_inf':float(np.linalg.norm(g1,np.inf))}
    # Residual/Jacobian finite-difference cancellation can occasionally
    # make a candidate appear nondecreasing; compare independent 3/5 point
    # quadratures of the analytic gradient (not the GN Hessian proxy).
    ss=[slope]
    for t in (.25,.5,.75):
        _,g,_=evaluate(y+t*d)
        if g is None or not np.isfinite(g).all():
            return None
        ss.append(dot(g,d))
    slope1=dot(g1,d)
    ss.append(slope1)
    s0,s1,s2,s3,s4=ss
    q3=math.fsum((s0,4*s2,s4))/6.
    q5=math.fsum((s0,4*s1,2*s2,4*s3,s4))/12.
    err=abs(q5-q3)/15.
    if not (np.isfinite(q3) and np.isfinite(q5) and np.isfinite(err)):
        return None
    # Reject a quadrature disagreement as large as its claimed decrease,
    # but do not impose a scale-unrelated 1e-6 step or 64eps total-cost
    # gate: those two guards invalidated the four stored failures.
    if not (q5 < sufficient and q5 < 0
            and err < .1*abs(q5)
            and abs(q5-q3) < .2*abs(q5)):
        return None
    # Prevent a numerical 'success' designation: the caller independently
    # requires the unchanged infinity-gradient stationarity criterion.
    return {'acceptance':'GRADIENT_INTEGRAL_R3',
            'direct_cost_difference':float(raw_diff),
            'gradient_integral_difference':float(q5),
            'quadrature_disagreement':float(abs(q5-q3)),
            'quadrature_error_indicator':float(err),
            'gradient_new_inf':float(np.linalg.norm(g1,np.inf)),
            'roundoff_scale_estimate':float(floor)}
