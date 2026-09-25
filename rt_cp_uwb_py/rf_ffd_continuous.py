"""Smooth real-sphere Cartesian harmonic surrogate of a pinned FFD bank.

Fit complex Cartesian fields, then project onto the tangent plane. No power
renormalization, efficiency correction, or evanescent continuation is applied.
"""
import numpy as np
from scipy.special import sph_harm_y


def directions_grid(theta,phi):
    t,p=np.meshgrid(np.deg2rad(theta),np.deg2rad(phi),indexing='ij')
    return np.stack([np.sin(t)*np.cos(p),np.sin(t)*np.sin(p),np.cos(t)],axis=-1)


def cartesian_grid(theta,phi,et,ep):
    t,p=np.meshgrid(np.deg2rad(theta),np.deg2rad(phi),indexing='ij')
    bt=np.stack([np.cos(t)*np.cos(p),np.cos(t)*np.sin(p),-np.sin(t)],axis=-1)
    bp=np.stack([-np.sin(p),np.cos(p),np.zeros_like(p)],axis=-1)
    return et[...,None]*bt+ep[...,None]*bp


class ContinuousFFD:
    def __init__(self,degree,coefficients):
        self.degree=degree
        self.coefficients=coefficients

    @classmethod
    def fit(cls,theta,phi,cartesian,degree):
        theta=np.asarray(theta);phi=np.asarray(phi);field=np.asarray(cartesian)
        if field.shape!=(len(theta),len(phi),3) or not np.isfinite(field).all():
            raise ValueError('INVALID_FIELD_GRID')
        if degree<0 or len(phi)<=2*degree or len(theta)<=degree+1:
            raise ValueError('INSUFFICIENT_TRAINING_GRID')
        if not np.allclose(phi,np.arange(len(phi))*360/len(phi)):
            raise ValueError('FULL_PERIOD_UNIFORM_PHI_REQUIRED')
        weights=np.sqrt(np.maximum(np.sin(np.deg2rad(theta)),0))
        modes=np.fft.fft(field,axis=1)/len(phi);coeff={}
        for m in range(-degree,degree+1):
            basis=np.stack([sph_harm_y(l,m,np.deg2rad(theta),0).real for l in range(abs(m),degree+1)],axis=1)
            c,_,rank,_=np.linalg.lstsq(basis*weights[:,None],modes[:,m%len(phi),:]*weights[:,None],rcond=None)
            if rank!=len(c): raise ValueError('HARMONIC_FIT_RANK_DEFICIENT')
            coeff[m]=c
        return cls(degree,coeff)

    def grid(self,theta,phi):
        out=np.zeros((len(theta),len(phi),3),complex)
        for m,c in self.coefficients.items():
            basis=np.stack([sph_harm_y(l,m,np.deg2rad(theta),0).real for l in range(abs(m),self.degree+1)],axis=1)
            out+=(basis@c)[:,None,:]*np.exp(1j*m*np.deg2rad(phi))[None,:,None]
        d=directions_grid(theta,phi)
        return out-d*np.sum(out*d,axis=-1,keepdims=True)

    def evaluate(self,directions,rotation=None,normalized=True):
        d=np.asarray(directions)
        if np.iscomplexobj(d) or d.ndim!=2 or d.shape[1]!=3 or not np.isfinite(d).all() or not np.allclose(np.linalg.norm(d,axis=1),1,atol=1e-10,rtol=0):
            raise ValueError('REAL_UNIT_DIRECTIONS_REQUIRED')
        rotation=np.eye(3) if rotation is None else np.asarray(rotation)
        if rotation.shape!=(3,3) or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-10) or not np.isclose(np.linalg.det(rotation),1):
            raise ValueError('PROPER_ROTATION_REQUIRED')
        local=d@rotation;t=np.arccos(np.clip(local[:,2],-1,1));p=np.arctan2(local[:,1],local[:,0])
        out=np.zeros((len(d),3),complex)
        for m,c in self.coefficients.items():
            basis=np.stack([sph_harm_y(l,m,t,0).real for l in range(abs(m),self.degree+1)],axis=1)
            out+=(basis@c)*np.exp(1j*m*p)[:,None]
        out-=local*np.sum(out*local,axis=1,keepdims=True)
        out=out@rotation.T
        return out*np.sqrt(2*np.pi/376.730313668) if normalized else out
