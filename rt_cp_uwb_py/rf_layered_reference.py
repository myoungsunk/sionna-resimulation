"""Independent Weyl integral for one TT term of an infinite dielectric slab.

Air source and receiver, y-directed electric dipole, displacement (rho,0,L+d).
Returns 4*pi times the yy electric Green dyadic, in 1/m, with exp(+j omega t).
This is a path-order reference, NOT the full slab response (internal echoes
are excluded). No ray tracing, ray-tube, Fresnel helper or producer imports.
"""
from functools import lru_cache
import numpy as np
from scipy.integrate import quad
from scipy.special import jv, roots_legendre

C0=299792458.


def validate(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m):
    values=[complex(epsilon),frequency_hz,air_distance_m,thickness_m,rho_m]
    if not np.isfinite(values).all() or complex(epsilon).real<1 or complex(epsilon).imag>0:
        raise ValueError('PASSIVE_EPSILON_REAL_AT_LEAST_ONE_REQUIRED')
    if min(frequency_hz,air_distance_m,thickness_m)<=0 or rho_m<0:
        raise ValueError('POSITIVE_FREQUENCY_AIR_DISTANCE_THICKNESS_REQUIRED')


def tt_coefficients(q_air,epsilon):
    """Two boundary transmissions in tangential E, without propagation."""
    q0=np.asarray(q_air,complex)
    q1=np.sqrt(complex(epsilon)-1+q0*q0+0j)
    q1=np.where((q1.imag>0)|((q1.imag==0)&(q1.real<0)),-q1,q1)
    te=4*q0*q1/(q0+q1)**2
    tm=4*complex(epsilon)*q0*q1/(q1+complex(epsilon)*q0)**2
    return te,tm,q1


@lru_cache(maxsize=8)
def _gauss(order):return roots_legendre(order)


def single_pass_yy(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m=0.,
                   *,method='gauss',order=1024,tail_factor=40.):
    """Propagating q_air=u, 0<u<1; evanescent q_air=-i*t, 0<t<infinity.

    Remove exp(-i*k*n*d) while integrating to avoid loss-driven cancellation
    of tiny absolute fields. 'scaled_value' omits that same factor. Numerical
    convergence must be checked by the caller; no admission is implied.
    """
    validate(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m)
    if method not in ('gauss','quad') or order<16 or tail_factor<20:
        raise ValueError('INVALID_QUADRATURE_CONFIG')
    k=2*np.pi*frequency_hz/C0;n=np.sqrt(complex(epsilon));L=air_distance_m;d=thickness_m
    tmax=max(2.,tail_factor/(k*L))

    def integrand(x,evanescent):
        q=-1j*x if evanescent else x
        s=np.sqrt(1-q*q+0j).real
        te,tm,q1=tt_coefficients(q,epsilon)
        j0=jv(0,k*rho_m*s);j2=jv(2,k*rho_m*s)
        weight=((j0-j2)*te+q*q*(j0+j2)*tm)/2
        return weight*np.exp(-1j*k*(L*q+d*(q1-n)))

    if method=='gauss':
        nodes,weights=_gauss(order)
        def integrate(upper,ev):
            return upper/2*np.dot(weights,integrand((nodes+1)*upper/2,ev))
        prop=integrate(1.,False);evan=integrate(tmax,True);error=None
    else:
        errors=[]
        def integrate(upper,ev):
            real,er=quad(lambda x:float(integrand(x,ev).real),0,upper,epsabs=1e-12,epsrel=1e-11,limit=2000)
            imag,ei=quad(lambda x:float(integrand(x,ev).imag),0,upper,epsabs=1e-12,epsrel=1e-11,limit=2000)
            errors.append(er+ei);return real+1j*imag
        prop=integrate(1.,False);evan=integrate(tmax,True);error=k*sum(errors)
    scaled=-1j*k*prop+k*evan
    factor=np.exp(-1j*k*n*d)
    return {'value':complex(scaled*factor),'scaled_value':complex(scaled),
            'removed_factor':complex(factor),'propagating_scaled':complex(-1j*k*prop),
            'evanescent_scaled':complex(k*evan),'quadrature_error_estimate_scaled':error,
            'evanescent_tmax':tmax,'method':method,'order':order if method=='gauss' else None,
            'production_admission':False}
