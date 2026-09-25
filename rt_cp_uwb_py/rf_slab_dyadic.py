"""Full electric 3x3 dyadic for the infinite-slab single TT benchmark.

Reference: independent angular-spectrum integration including evanescent modes.
Candidate: first inverse-k saddle correction, evaluated as a matrix, never as
a common scalar correction for arbitrary polarizations. No scene admission.
"""
import numpy as np
from scipy.special import jv
from .rf_layered_reference import validate,tt_coefficients,_gauss,C0
from .rf_complex_saddle import slab_saddle_yy


def reference_dyadic(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m=0.,*,order=1024,evanescent=True):
    validate(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m)
    k=2*np.pi*frequency_hz/C0;L=air_distance_m;d=thickness_m;n=np.sqrt(complex(epsilon))
    nodes,weights=_gauss(order)
    def integrate(upper,ev):
        x=(nodes+1)*upper/2;q=-1j*x if ev else x;s=np.sqrt(1-q*q+0j).real
        te,tm,q1=tt_coefficients(q,epsilon)
        j0,j1,j2=[jv(i,k*rho_m*s) for i in range(3)]
        w=np.zeros((len(q),3,3),complex)
        w[:,0,0]=((j0+j2)*te+q*q*(j0-j2)*tm)/2
        w[:,1,1]=((j0-j2)*te+q*q*(j0+j2)*tm)/2
        w[:,2,2]=s*s*j0*tm
        w[:,0,2]=w[:,2,0]=1j*q*s*j1*tm
        phase=np.exp(-1j*k*(L*q+d*(q1-n)))
        return upper/2*np.einsum('n,n,nij->ij',weights,phase,w)
    prop=-1j*k*integrate(1.,False)
    ev=k*integrate(max(2.,40/(k*L)),True) if evanescent else np.zeros((3,3),complex)
    factor=np.exp(-1j*k*n*d)
    return {'value':(prop+ev)*factor,'scaled_value':prop+ev,
        'propagating_scaled':prop,'evanescent_scaled':ev,'production_admission':False}


def _spectral_amplitude(x,y,eps):
    # Removable radial singularity rationalized: valid on the optical axis.
    u=x*x+y*y;q0=np.sqrt(1-u);q1=np.sqrt(eps-u)
    te=4*q0*q1/(q0+q1)**2;tm=4*eps*q0*q1/(q1+eps*q0)**2
    h=te/q0;j=h*(1-3*eps+2*eps*u-2*eps*q0*q1)/(q1+eps*q0)**2
    return np.array([[h+x*x*j,x*y*j,-tm*x],
                     [x*y*j,h+y*y*j,-tm*y],[-tm*x,-tm*y,tm*u/q0]],complex)


def corrected_dyadic(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m=0.):
    leading=slab_saddle_yy(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m)
    eps=complex(epsilon);s=leading['tangential_index'];L=air_distance_m;d=thickness_m;k=2*np.pi*frequency_hz/C0
    u=s*s;q0=np.sqrt(1-u);q1=np.sqrt(eps-u);dx=L/q0**3+d*eps/q1**3;dy=L/q0+d/q1
    a=-s/2*(L/q0**5+d*eps/q1**5);b=-s/2*(L/q0**3+d/q1**3)
    c=-(L*(1/q0**5+5*u/q0**7)+d*eps*(1/q1**5+5*u/q1**7))/8
    e=-(L*(1/q0**3+3*u/q0**5)+d*(1/q1**3+3*u/q1**5))/4;f=-(L/q0**3+d/q1**3)/8
    g=_spectral_amplitude(s,0,eps);h=g[1,1];factor=leading['scaled_value']/h
    angle=2*np.pi*np.arange(32)/32;circle=np.exp(1j*angle)
    radius=.03*min(1.,abs(1-s),abs(np.sqrt(eps)-s))
    corrections=[]
    for r in [radius,radius/2]:
        xx=np.array([_spectral_amplitude(s+r*z,0,eps) for z in circle])
        yy=np.array([_spectral_amplitude(s,r*z,eps) for z in circle])
        gx=np.einsum('n,nij->ij',circle**-1,xx)/len(circle)/r
        gxx=np.einsum('n,nij->ij',circle**-2,xx)/len(circle)/r**2
        gyy=np.einsum('n,nij->ij',circle**-2,yy)/len(circle)/r**2
        term=gxx/dx+gyy/dy+gx*(3*a/dx**2+b/(dx*dy))
        term+=g*(3*c/dx**2+e/(dx*dy)+3*f/dy**2)
        term+=g/2*(15*a*a/dx**3+6*a*b/(dx*dx*dy)+3*b*b/(dx*dy*dy))
        corrections.append(1j*term/k)
    error=float(np.linalg.norm(corrections[1]-corrections[0])/max(np.linalg.norm(g),1e-30))
    if error>1e-6:raise ValueError('CAUCHY_DERIVATIVE_NOT_CONVERGED')
    scaled=factor*(g+corrections[-1]);phase=np.exp(-1j*k*np.sqrt(eps)*d)
    return {'value':scaled*phase,'scaled_value':scaled,'leading_scaled':factor*g,
        'derivative_relative_change':error,'production_admission':False,'finite_scene_qualified':False}
