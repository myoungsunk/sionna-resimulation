"""Polynomial continuation of fitted Cartesian spherical harmonics.

Continuation is explicitly opt-in. Real-grid accuracy alone does not qualify
complex directions; callers must check order stability on consumed directions.
"""
import math
import numpy as np
from scipy.special import sph_harm_y


def modes(degree):return [(l,m) for m in range(-degree,degree+1) for l in range(abs(m),degree+1)]


def polynomial_basis(directions,degree):
    d=np.asarray(directions,complex)
    if d.ndim!=2 or d.shape[1]!=3 or not np.isfinite(d).all() or np.max(abs(np.sum(d*d,axis=1)-1))>1e-9:raise ValueError('COMPLEX_UNIT_QUADRIC_REQUIRED')
    x,y,z=d.T;out=[]
    for m in range(-degree,degree+1):
        a=abs(m);w=x+(1j if m>=0 else -1j)*y
        h=(-1)**a*math.prod(range(1,2*a,2))*w**a;prev=np.zeros_like(h)
        for l in range(a,degree+1):
            if l>a:prev,h=h,((2*l-1)*z*h-(l+a-1)*prev)/(l-a)
            norm=np.sqrt((2*l+1)/(4*np.pi)*math.factorial(l-a)/math.factorial(l+a))
            out.append(norm*h*((-1)**a if m<0 else 1))
    return np.column_stack(out)


def evaluate(coefficients,directions,degree,rotation=None):
    rot=np.eye(3) if rotation is None else np.asarray(rotation,float);d=np.asarray(directions,complex)
    if rot.shape!=(3,3) or not np.allclose(rot.T@rot,np.eye(3),rtol=0,atol=1e-10) or abs(np.linalg.det(rot)-1)>1e-10:raise ValueError('PROPER_ROTATION_REQUIRED')
    local=d@rot;basis=polynomial_basis(local,degree);field=basis@np.asarray(coefficients)
    field-=local*np.sum(local*field,axis=1,keepdims=True)
    return field@rot.T*np.sqrt(2*np.pi/376.730313668)


def fit_batch(theta,phi,field,degree):
    """Field shape F,theta,phi,3; uniform full-period phi starts at zero."""
    weights=np.sqrt(np.maximum(np.sin(np.deg2rad(theta)),0));fourier=np.fft.fft(field,axis=2)/len(phi);coeff=[]
    for m in range(-degree,degree+1):
        basis=np.stack([sph_harm_y(l,m,np.deg2rad(theta),0).real for l in range(abs(m),degree+1)],axis=1)
        pinv=np.linalg.pinv(basis*weights[:,None]);c=np.einsum('lt,ftc->flc',pinv,fourier[:,:,m%len(phi),:]*weights[None,:,None]);coeff.append(c)
    return np.concatenate(coeff,axis=1)


def reconstruct_grid(coefficients,theta,phi,degree):
    f=len(coefficients);fourier=np.zeros((f,len(theta),len(phi),3),complex);offset=0
    for m in range(-degree,degree+1):
        count=degree-abs(m)+1;basis=np.stack([sph_harm_y(l,m,np.deg2rad(theta),0).real for l in range(abs(m),degree+1)],axis=1)
        fourier[:,:,m%len(phi),:]=np.einsum('tl,flc->ftc',basis,coefficients[:,offset:offset+count]);offset+=count
    out=np.fft.ifft(fourier,axis=2)*len(phi);t,p=np.meshgrid(np.deg2rad(theta),np.deg2rad(phi),indexing='ij');directions=np.stack((np.sin(t)*np.cos(p),np.sin(t)*np.sin(p),np.cos(t)),axis=-1)
    return out-directions*np.sum(out*directions,axis=-1,keepdims=True)
