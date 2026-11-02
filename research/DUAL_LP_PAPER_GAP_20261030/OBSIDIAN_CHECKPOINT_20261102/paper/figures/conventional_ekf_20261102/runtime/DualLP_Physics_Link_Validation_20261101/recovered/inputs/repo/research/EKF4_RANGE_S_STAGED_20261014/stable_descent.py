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
