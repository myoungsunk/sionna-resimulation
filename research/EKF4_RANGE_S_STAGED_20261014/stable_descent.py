"""R3 directional cost difference for a FIXED Gaussian MAP objective.

For tiny steps, subtracting two float64 costs can have the wrong sign.
Compute ΔJ = integral grad J(y+t*d).d dt with nested Simpson rules.
This is a *numerical* convergence safeguard; not a certified error bound
or a new measurement. The caller alone decides CONVERGED from the original
gradient infinity norm criterion.
"""
import math
import numpy as np

def integrated_descent(evaluate, y, d, c0, g0, c1, g1, info):
    if g1 is None or not (np.isfinite(c0) and np.isfinite(c1) and
                           np.isfinite(g0).all() and np.isfinite(g1).all() and
                           np.isfinite(d).all()):
        return None
    norm=lambda x:float(np.linalg.norm(x,ord=np.inf))
    dot=lambda a,b:float(math.fsum(float(x)*float(v) for x,v in zip(a,b)))
    n0,n1=norm(g0),norm(g1)
    slope0=dot(g0,d)
    slope1=dot(g1,d)
    if slope0>=0 or n1>=n0:
        return None
    # Large steps belong to the ordinary resolved-cost Armijo path.
    # This bound does NOT prohibit any actual cost-reducing large step:
    # that path is tested by the caller independently.
    if norm(d)>1e-4*max(1.,norm(y)):
        return None
    eps=np.finfo(float).eps
    ambiguity=1024*eps*max(1.,abs(c0),abs(c1))
    if abs(c1-c0)>ambiguity:
        return None
    slopes={0:slope0,8:slope1}
    for k in range(1,8):
        _,g,_=evaluate(y+(k/8.)*d)
        if g is None or not np.isfinite(g).all():
            return None
        slopes[k]=dot(g,d)
    def simpson(step):
        n=8//step
        acc=math.fsum([slopes[0],slopes[8]]+
            [4*slopes[i] for i in range(step,8,2*step)]+
            [2*slopes[i] for i in range(2*step,8,2*step)])
        return acc*(step/8.)/3.
    s4=simpson(2)
    s8=simpson(1)
    error=abs(s8-s4)/15.
    # Diagnostics about cancellation in transformed residual gradients;
    # not claimed to certify an arbitrary nondifferentiable LUT.
    gnoise=32*eps*(1+norm(y)+norm(y+d)+
                   math.sqrt(max(1.,norm(info)))*math.sqrt(max(1.,2*abs(c0),2*abs(c1))))
    noise=float(np.linalg.norm(d,1))*gnoise
    if not (s8<0 and s8+8*error+noise<1e-4*slope0
            and abs(s8-s4)<=.01*abs(s8)+noise):
        return None
    return {'direct_cost_difference':float(c1-c0),
            'gradient_integral_difference':float(s8),
            'gradient_integral_coarse':float(s4),
            'gradient_integral_noise_estimate':float(noise),
            'quadrature_error_indicator':float(error),
            'gradient_new_inf':n1,'strong_wolfe_ratio':abs(slope1/slope0),
            'R3_guard':'NUMERICALLY_UNRESOLVED_DIRECT_COST_GRADIENT_QUADRATURE'}
