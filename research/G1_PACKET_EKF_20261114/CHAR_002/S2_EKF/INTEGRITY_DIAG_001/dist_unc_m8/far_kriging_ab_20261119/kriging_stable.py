"""Deterministic cutoff-tie correction; NOT adopted without frozen parity.

The frozen implementation selects an arbitrary subset when the 150th/151st
L1 distances differ by roundoff. Resolve only that cutoff band by training-row
identity. The covariance kernel and all model parameters remain unchanged.
This changes historically arbitrary tie decisions, so the original POINT_B
gate must still pass before an A/B result can be accepted.
"""
import numpy as np


def neighbor_indices(distances, maxn=150):
    d=np.asarray(distances,dtype=float)
    if d.ndim!=1 or not np.isfinite(d).all() or not 0<maxn<=len(d):
        raise ValueError('Invalid Kriging distances or neighbor count')
    cutoff=float(np.partition(d,maxn-1)[maxn-1])
    tolerance=32*np.finfo(d.dtype).eps*max(1.,abs(cutoff))
    strict=np.flatnonzero(d<cutoff-tolerance)
    tied=np.flatnonzero(np.abs(d-cutoff)<=tolerance)
    need=maxn-len(strict)
    if need<0 or len(tied)<need:
        raise RuntimeError('Invalid cutoff tie band')
    return np.sort(np.r_[strict,tied[:need]])


def make_predictor(frozen):
    def krige_s(x,y,psi,rho,maxn=150):
        b=int(np.clip(np.searchsorted(frozen.EDG,rho,side='right')-1,0,2))
        B=frozen.BINS[b]; lx,ly,lp,nug=B['prm']; X=B['X']
        d=np.abs(X[:,0]-x)/lx+np.abs(X[:,1]-y)/ly+np.abs(frozen.wrap(X[:,2]-psi))/lp
        idx=neighbor_indices(d,maxn); Xi=X[idx]
        K=np.exp(-(np.abs(Xi[:,0,None]-Xi[None,:,0])/lx+np.abs(Xi[:,1,None]-Xi[None,:,1])/ly+
                   np.abs(frozen.wrap(Xi[:,2,None]-Xi[None,:,2]))/lp))
        w=np.linalg.solve((1-nug)*K+nug*np.eye(len(idx)),(1-nug)*np.exp(-d[idx]))
        return B['mu0']+w@(B['y'][idx]-B['mu0'])
    return krige_s
