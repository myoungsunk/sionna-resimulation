"""Development asymptote for an infinite slab's y-polarized single TT term.

Complex stationary optical phase and Hessian; NOT a finite-scene producer.
No lossy ray-tube gate is removed by this module.
"""
import numpy as np
from scipy.optimize import root

C0=299792458.


def slab_saddle_yy(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m=0.):
    eps=complex(epsilon);L=float(air_distance_m);d=float(thickness_m);rho=float(rho_m)
    if not np.isfinite([eps,frequency_hz,L,d,rho]).all() or eps.real<1 or eps.imag>0 or min(frequency_hz,L,d)<=0 or rho<0:
        raise ValueError('INVALID_PASSIVE_SLAB')
    # Continue the physical real-index saddle into loss, preserving root sheets.
    initial=rho/np.sqrt(rho*rho+(L+d/np.sqrt(eps.real))**2)
    s=complex(initial)
    for fraction in np.linspace(0,1,33):
        ep=complex(eps.real,eps.imag*fraction)
        def residual(x):
            z=complex(*x);q0=np.sqrt(1-z*z);q1=np.sqrt(ep-z*z)
            r=L*z/q0+d*z/q1-rho
            return [r.real,r.imag]
        fit=root(residual,[s.real,s.imag],tol=1e-11)
        if np.linalg.norm(residual(fit.x))>1e-10:raise ValueError('COMPLEX_SADDLE_NOT_CONVERGED')
        s=complex(*fit.x)
    q0=np.sqrt(1-s*s);q1=np.sqrt(eps-s*s)
    if q0.real<=0 or q1.real<=0:raise ValueError('UNSUPPORTED_SADDLE_SHEET')
    meridional=L/q0**3+d*eps/q1**3;sagittal=L/q0+d/q1
    spreading=1/(q0*np.sqrt(meridional*sagittal))
    t=4*q0*q1/(q0+q1)**2
    optical=s*rho+L*q0+d*q1;k=2*np.pi*frequency_hz/C0
    scaled=t*spreading*np.exp(-1j*k*(optical-np.sqrt(eps)*d))
    return {'value':complex(scaled*np.exp(-1j*k*np.sqrt(eps)*d)),
            'scaled_value':complex(scaled),'spreading_per_m':complex(spreading),
            'tangential_index':complex(s),'optical_length_m':complex(optical),
            'stationarity_residual_m':float(abs(L*s/q0+d*s/q1-rho)),
            'production_admission':False,'finite_scene_qualified':False}
