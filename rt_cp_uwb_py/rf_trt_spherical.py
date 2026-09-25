"""TRT point-source dyadic: independent Weyl reference and complex saddle.

The first internal slab echo includes material propagation twice. Finite-body
boundary eligibility, antenna continuation and channel admission are separate.
These routines do not replace a finite object by an admitted infinite slab.
"""
import math
import numpy as np
from scipy.special import jv
from .rf_layered_reference import _gauss,validate,C0
from .rf_complex_saddle import slab_saddle_yy
from .rf_slab_second_order import _phase_tail,_multiply,_odd_factorial


def _echo(q,eps):
    q1=np.sqrt(complex(eps)-1+q*q+0j)
    q1=np.where((q1.imag>0)|((q1.imag==0)&(q1.real<0)),-q1,q1)
    te=4*q*q1*(q1-q)/(q+q1)**3
    tm=4*eps*q*q1*(eps*q-q1)/(q1+eps*q)**3
    return te,tm,q1


def reference(epsilon,frequency_hz,L,d,rho,order=1024):
    validate(epsilon,frequency_hz,L,d,rho);k=2*np.pi*frequency_hz/C0;n=np.sqrt(complex(epsilon));nodes,weights=_gauss(order)
    def integrate(upper,ev):
        t=(nodes+1)*upper/2;q=-1j*t if ev else t;s=np.sqrt(1-q*q+0j).real
        te,tm,q1=_echo(q,epsilon);j0,j1,j2=[jv(i,k*rho*s) for i in range(3)]
        w=np.zeros((len(q),3,3),complex);w[:,0,0]=((j0+j2)*te+q*q*(j0-j2)*tm)/2;w[:,1,1]=((j0-j2)*te+q*q*(j0+j2)*tm)/2
        w[:,2,2]=-s*s*j0*tm;w[:,0,2]=-1j*q*s*j1*tm;w[:,2,0]=1j*q*s*j1*tm
        return upper/2*np.einsum('n,n,nij->ij',weights,np.exp(-1j*k*(L*q+2*d*(q1-n))),w)
    scaled=-1j*k*integrate(1,False)+k*integrate(max(2.,40/(k*L)),True)
    return dict(scaled_value=scaled,value=scaled*np.exp(-2j*k*n*d),order=order,finite_body_qualified=False)


def spectral_amplitude(x,y,eps):
    u=x*x+y*y;a=np.sqrt(1-u);b=np.sqrt(eps-u)
    te=4*a*b*(b-a)/(a+b)**3;tm=4*eps*a*b*(eps*a-b)/(b+eps*a)**3
    # Exact cancellation of (tm*a*a-te)/(a*u), including the optical axis.
    j=-4*b*(a-b)*(4*a**3*b-4*a*a*b*b+a*a-3*a*b-1)/(b+eps*a)**3
    h=te/a
    return np.array([[h+x*x*j,x*y*j,tm*x],[x*y*j,h+y*y*j,tm*y],[-tm*x,-tm*y,-tm*u/a]],complex)


def corrected(epsilon,frequency_hz,L,d,rho):
    lead=slab_saddle_yy(epsilon,frequency_hz,L,2*d,rho);eps=complex(epsilon);s=lead['tangential_index'];k=2*np.pi*frequency_hz/C0
    q0=np.sqrt(1-s*s);q1=np.sqrt(eps-s*s);dx=L/q0**3+2*d*eps/q1**3;dy=L/q0+2*d/q1
    tail=_phase_tail(s,eps,L,2*d);powers=[{(0,0):1.}]
    for _ in range(4):powers.append(_multiply(powers[-1],tail,12))
    radius=.08*min(1.,abs(1-s),abs(np.sqrt(eps)-s));circle=np.exp(2j*np.pi*np.arange(24)/24);levels=[]
    for r in [radius,radius/2]:
        samples=np.array([[spectral_amplitude(s+r*x,r*y,eps) for y in circle] for x in circle]);fft=np.fft.fft2(samples,axes=(0,1))/len(circle)**2
        amplitude={(i,j):fft[i,j]/r**(i+j) for i in range(5) for j in range(5-i)};terms=[np.zeros((3,3),complex) for _ in range(3)]
        for count,phase in enumerate(powers):
            for (i,j),v in _multiply(amplitude,phase,2*(2+count)).items():
                if i%2 or j%2:continue
                order=(i+j)//2-count
                if order not in (0,1,2):continue
                moment=_odd_factorial(i)*_odd_factorial(j)/dx**(i//2)/dy**(j//2)
                terms[order]+=v*moment*(1j/k)**order/math.factorial(count)
        levels.append(terms)
    g=spectral_amplitude(s,0,eps);change=float(np.linalg.norm(sum(levels[0])-sum(levels[1]))/max(np.linalg.norm(g),1e-30))
    if change>1e-6:raise ValueError('TRT_CAUCHY_DERIVATIVES_NOT_CONVERGED')
    phase=np.exp(-1j*k*(s*rho+L*q0+2*d*(q1-np.sqrt(eps))))/np.sqrt(dx*dy)
    scaled=phase*sum(levels[-1]);return dict(value=scaled*np.exp(-2j*k*np.sqrt(eps)*d),scaled_value=scaled,leading_scaled=phase*g,derivative_change=change,saddle=lead,finite_body_qualified=False)
