"""First inverse-frequency correction of the infinite-slab yy TT saddle.

Analytic amplitude derivatives and cubic/quartic optical phase derivatives,
contracted with Gaussian moments. No fitted phase, reference integral calls,
finite-scene integration or production admission.
"""
import numpy as np
from .rf_complex_saddle import slab_saddle_yy,C0


def corrected_slab_yy(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m=0.):
    leading=slab_saddle_yy(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m)
    eps=complex(epsilon);s=leading['tangential_index'];L=air_distance_m;d=thickness_m
    u=s*s;q0=np.sqrt(1-u);q1=np.sqrt(eps-u)
    dx=L/q0**3+d*eps/q1**3;dy=L/q0+d/q1
    # Spectral amplitude g(x,y)=T_TE*x^2/(q0*(x^2+y^2))
    #                          +q0*T_TM*y^2/(x^2+y^2).
    # h(u)=T_TE/q0; j(u)=(q0*T_TM-h)/u, rationalized at u=0.
    h=4*q1/(q0+q1)**2
    log_first=1/(q0*q1)-1/(2*q1*q1)
    hp=h*log_first
    hpp=h*(log_first**2+.5/(q0**3*q1)+.5/(q0*q1**3)-.5/q1**4)
    j=h*(1-3*eps+2*eps*u-2*eps*q0*q1)/(q1+eps*q0)**2
    gx=2*s*hp;gxx_half=hp+2*u*hpp;gyy_half=hp+j
    # Phi3=a*x^3+b*x*y^2; Phi4=c*x^4+e*x^2*y^2+f*y^4.
    a=-s/2*(L/q0**5+d*eps/q1**5)
    b=-s/2*(L/q0**3+d/q1**3)
    c=-(L*(1/q0**5+5*u/q0**7)+d*eps*(1/q1**5+5*u/q1**7))/8
    e=-(L*(1/q0**3+3*u/q0**5)+d*(1/q1**3+3*u/q1**5))/4
    f=-(L/q0**3+d/q1**3)/8
    # Covariance i*diag(1/dx,1/dy)/k. All four terms contribute at 1/k.
    terms={
        'amplitude_curvature':gxx_half/dx+gyy_half/dy,
        'amplitude_phase_cubic':gx*(3*a/dx**2+b/(dx*dy)),
        'phase_quartic':h*(3*c/dx**2+e/(dx*dy)+3*f/dy**2),
        'phase_cubic_squared':h/2*(15*a*a/dx**3+6*a*b/(dx*dx*dy)+3*b*b/(dx*dy*dy))}
    coefficient=sum(terms.values())/h
    factor=1+1j*coefficient/(2*np.pi*frequency_hz/C0)
    if not np.isfinite([factor,coefficient]).all():raise ValueError('NONFINITE_ASYMPTOTIC_CORRECTION')
    return {'value':leading['value']*factor,'scaled_value':leading['scaled_value']*factor,
        'leading_value':leading['value'],'leading_scaled_value':leading['scaled_value'],
        'correction_factor':complex(factor),'inverse_k_coefficient_per_m':complex(coefficient),
        'coefficient_terms_per_m':{key:complex(value/h) for key,value in terms.items()},
        'stationarity_residual_m':leading['stationarity_residual_m'],
        'production_admission':False,'finite_scene_qualified':False}
