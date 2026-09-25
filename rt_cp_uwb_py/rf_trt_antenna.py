"""Antenna-coupled TRT saddle and independent real-q/Weyl quadrature.

Harmonic continuation must be validated separately; no finite-body admission.
"""
import math
import numpy as np
from scipy.special import jv
from .rf_complex_ffd import polynomial_basis
from .rf_trt_spherical import spectral_amplitude
from .rf_complex_saddle import slab_saddle_yy
from .rf_slab_second_order import _multiply,_phase_tail,_odd_factorial
from .rf_layered_reference import _gauss,C0


def fields(coefficients,directions,degree,rotation):
    d=np.asarray(directions,complex);rot=np.asarray(rotation);local=d@rot;c=np.asarray(coefficients);out=(polynomial_basis(local,degree)@c.reshape(c.shape[0],-1)).reshape(len(d),3,-1)
    out-=local[:,:,None]*np.einsum('ni,nip->np',local,out)[:,None,:]
    return np.einsum('ab,nbp->nap',rot,out)*np.sqrt(2*np.pi/376.730313668)


def port_amplitude(x,y,eps,coefficients,degree,frame,tx_rotation,rx_rotation):
    x=np.atleast_1d(x);y=np.atleast_1d(y);q=np.sqrt(1-x*x-y*y);kin=np.column_stack((x,y,-q));kout=np.column_stack((x,y,q))
    tx=fields(coefficients,kin@frame.T,degree,tx_rotation);rx=fields(coefficients,-kout@frame.T,degree,rx_rotation)
    tx=np.einsum('ab,nbp->nap',frame.T,tx);rx=np.einsum('ab,nbp->nap',frame.T,rx)
    matrix=np.moveaxis(spectral_amplitude(x,y,eps),-1,0)
    return np.einsum('nai,nab,nbj->nij',rx,matrix,tx)


def corrected_ports(eps,f,L,d,rho,coefficients,degree,frame,tx_rotation,rx_rotation):
    lead=slab_saddle_yy(eps,f,L,2*d,rho);s=lead['tangential_index'];k=2*np.pi*f/C0;q0=np.sqrt(1-s*s);q1=np.sqrt(eps-s*s);dx=L/q0**3+2*d*eps/q1**3;dy=L/q0+2*d/q1;tail=_phase_tail(s,eps,L,2*d);powers=[{(0,0):1.}]
    for _ in range(4):powers.append(_multiply(powers[-1],tail,12))
    radius=.08*min(1.,abs(1-s),abs(np.sqrt(eps)-s));circle=np.exp(2j*np.pi*np.arange(24)/24);levels=[];ports=coefficients.shape[-1]
    for r in [radius,radius/2]:
        xx,yy=np.meshgrid(s+r*circle,r*circle,indexing='ij');samples=port_amplitude(xx.ravel(),yy.ravel(),eps,coefficients,degree,frame,tx_rotation,rx_rotation).reshape(24,24,ports,ports);fft=np.fft.fft2(samples,axes=(0,1))/24**2
        amplitude={(i,j):fft[i,j]/r**(i+j) for i in range(5) for j in range(5-i)};terms=[np.zeros((ports,ports),complex) for _ in range(3)]
        for count,phase in enumerate(powers):
            for (i,j),v in _multiply(amplitude,phase,2*(2+count)).items():
                if i%2 or j%2:continue
                order=(i+j)//2-count
                if order not in (0,1,2):continue
                moment=_odd_factorial(i)*_odd_factorial(j)/dx**(i//2)/dy**(j//2)
                terms[order]+=v*moment*(1j/k)**order/math.factorial(count)
        levels.append(sum(terms))
    change=float(np.linalg.norm(levels[1]-levels[0])/max(np.linalg.norm(levels[1]),1e-300))
    if change>1e-6:raise ValueError('PORT_CAUCHY_NOT_CONVERGED')
    factor=np.exp(-1j*k*(s*rho+L*q0+2*d*(q1-np.sqrt(eps))))/np.sqrt(dx*dy)*C0/f/(4*np.pi)
    scaled=levels[-1]*factor
    return dict(scaled_H=scaled,H=scaled*np.exp(-2j*k*np.sqrt(eps)*d),derivative_change=change,finite_body_admitted=False)


def reference_ports(eps,f,L,d,rho,coefficients,degree,frame,tx_rotation,rx_rotation,order=1024):
    k=2*np.pi*f/C0;nodes,weights=_gauss(order);nphi=1
    while nphi<=4*degree+8:nphi*=2
    phi=2*np.pi*np.arange(nphi)/nphi;cp=np.cos(phi);sp=np.sin(phi);harmonics=np.rint(np.fft.fftfreq(nphi)*nphi).astype(int)
    def integrate(upper,ev):
        total=np.zeros((coefficients.shape[-1],)*2,complex)
        for start in range(0,order,8):
            t=(nodes[start:start+8]+1)*upper/2;q=-1j*t if ev else t;s=np.sqrt(1-q*q+0j).real;shape=(len(q),nphi)
            x=s[:,None]*cp;y=s[:,None]*sp;qq=np.broadcast_to(q[:,None],shape);ss=np.broadcast_to(s[:,None],shape)
            kin=np.stack((x,y,-qq),axis=-1).reshape(-1,3);kout=np.stack((x,y,qq),axis=-1).reshape(-1,3)
            tx=fields(coefficients,kin@frame.T,degree,tx_rotation);rx=fields(coefficients,-kout@frame.T,degree,rx_rotation);tx=np.einsum('ab,nbp->nap',frame.T,tx);rx=np.einsum('ab,nbp->nap',frame.T,rx)
            sv=np.broadcast_to(np.stack((-sp,cp,np.zeros(nphi)),axis=-1),(len(q),nphi,3)).reshape(-1,3);pin=np.stack((qq*cp,qq*sp,ss),axis=-1).reshape(-1,3);pout=pin.copy();pout[:,2]*=-1
            ts=np.einsum('ni,nip->np',sv,tx);tp=np.einsum('ni,nip->np',pin,tx);rs=np.einsum('ni,nip->np',sv,rx);rp=np.einsum('ni,nip->np',pout,rx)
            q1=np.sqrt(eps-1+q*q+0j);q1=np.where(q1.imag>0,-q1,q1);ys0=q;ys1=q1;yp0=1/q;yp1=eps/q1;rs01=(ys0-ys1)/(ys0+ys1);rp01=(yp0-yp1)/(yp0+yp1);te=-(1-rs01**2)*rs01;tm=-(1-rp01**2)*rp01
            amp=(np.einsum('ni,nj->nij',rs,ts)*np.repeat(te,nphi)[:,None,None]+np.einsum('ni,nj->nij',rp,tp)*np.repeat(tm,nphi)[:,None,None]).reshape(len(q),nphi,*total.shape)
            modes=np.fft.fft(amp,axis=1)/nphi;angular=np.einsum('nm,nmij->nij',(-1j)**harmonics[None,:]*jv(harmonics[None,:],k*rho*s[:,None]),modes)
            phase=np.exp(-1j*k*(L*q+2*d*(q1-np.sqrt(eps))));total+=upper/2*np.einsum('n,n,nij->ij',weights[start:start+len(q)],phase,angular)
        return total
    scaled=(-1j*k*integrate(1,False)+k*integrate(max(2.,40/(k*L)),True))*C0/f/(4*np.pi)
    return dict(scaled_H=scaled,H=scaled*np.exp(-2j*k*np.sqrt(eps)*d),finite_body_admitted=False)
