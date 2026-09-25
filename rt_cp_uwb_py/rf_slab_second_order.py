"""Second inverse-wavenumber saddle term for the infinite slab TT dyadic.

No fit to the reference integral. Phase Taylor coefficients are analytic;
amplitude derivatives use two independently sized complex Cauchy contours.
"""
import math
import numpy as np
from .rf_complex_saddle import slab_saddle_yy
from .rf_slab_dyadic import _spectral_amplitude, C0


def _multiply(a, b, degree):
    out = {}
    for (i,j), x in a.items():
        for (p,q), y in b.items():
            if i+j+p+q <= degree:
                key = i+p,j+q
                out[key] = out.get(key,0) + x*y
    return out


def _phase_tail(s, eps, L, d):
    result = {}
    for medium, length in [(1.,L),(eps,d)]:
        q = np.sqrt(medium-s*s)
        z = {(1,0):-2*s/q**2,(2,0):-1/q**2,(0,2):-1/q**2}
        power = {(0,0):1.}; coefficient = 1.
        for n in range(1,7):
            power = _multiply(power,z,6)
            coefficient *= (.5-n+1)/n
            for key,v in power.items():
                if sum(key)>=3:
                    result[key] = result.get(key,0)+length*q*coefficient*v
    return result


def _odd_factorial(n):
    return math.prod(range(1,n,2))


def second_order_dyadic(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m=0.):
    lead = slab_saddle_yy(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m)
    eps=complex(epsilon); s=lead['tangential_index']; L=air_distance_m; d=thickness_m
    k=2*np.pi*frequency_hz/C0; q0=np.sqrt(1-s*s); q1=np.sqrt(eps-s*s)
    dx=L/q0**3+d*eps/q1**3; dy=L/q0+d/q1
    tail=_phase_tail(s,eps,L,d); powers=[{(0,0):1.}]
    for n in range(4):
        powers.append(_multiply(powers[-1],tail,12))
    radius=.08*min(1.,abs(1-s),abs(np.sqrt(eps)-s))
    circle=np.exp(2j*np.pi*np.arange(24)/24); levels=[]
    for r in [radius,radius/2]:
        samples=np.array([[_spectral_amplitude(s+r*x,r*y,eps) for y in circle] for x in circle])
        fft=np.fft.fft2(samples,axes=(0,1))/len(circle)**2
        amplitude={(i,j):fft[i,j]/r**(i+j) for i in range(5) for j in range(5-i)}
        terms=[np.zeros((3,3),complex) for _ in range(3)]
        for count, phase in enumerate(powers):
            for (i,j),v in _multiply(amplitude,phase,2*(2+count)).items():
                if i%2 or j%2: continue
                order=(i+j)//2-count
                if order not in (0,1,2): continue
                moment=_odd_factorial(i)*_odd_factorial(j)/dx**(i//2)/dy**(j//2)
                terms[order] += v*moment*(1j/k)**order/math.factorial(count)
        levels.append(terms)
    g=_spectral_amplitude(s,0,eps); factor=lead['scaled_value']/g[1,1]
    change=float(np.linalg.norm(sum(levels[0])-sum(levels[1]))/np.linalg.norm(g))
    if change>1e-6: raise ValueError('SECOND_ORDER_DERIVATIVES_NOT_CONVERGED')
    scaled=factor*sum(levels[-1])
    return {'scaled_value':scaled,'value':scaled*np.exp(-1j*k*np.sqrt(eps)*d),
            'first_order_scaled':factor*sum(levels[-1][:2]),
            'second_term_scaled':factor*levels[-1][2], 'derivative_relative_change':change,
            'production_admission':False,'finite_scene_qualified':False}
