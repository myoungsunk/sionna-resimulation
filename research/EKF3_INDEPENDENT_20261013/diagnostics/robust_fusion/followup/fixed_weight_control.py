"""Three-state fixed common RF block weight; original prior R0 NIS gate.

This Gaussian control has no residual-dependent weighting. A weight of 1/3
uses R_effective=3*R0 after the unscaled gate. Physical range is converted to
the original detector-offset convention for exact unit-weight M0 parity.
"""
import math
import numpy as np
from loss_family import (DiagnosticFilter, covariance_check, range_h, wrap,
                         RS, RR, GATE_1D_99, GATE_2D_99)
from d6_d9_common import B_OLD


class FixedWeightPoseEKF:
    def __init__(self, x0, *, weight=1/3):
        if not math.isfinite(float(weight)) or not 0 < weight <= 1:
            raise ValueError('Fixed common weight must be finite and in (0,1]')
        self.weight = float(weight)
        self.filter = DiagnosticFilter(np.asarray(x0,float))

    @property
    def x(self): return self.filter.f.x
    @property
    def P(self): return self.filter.f.P
    @property
    def pose(self): return self.x
    @property
    def Ppose(self): return self.P
    def predict(self, ds, dtheta, dt): self.filter.predict(ds,dtheta,dt)

    def reset(self, x, p):
        """Install a supplied common prior atomically for one-step comparisons."""
        x=np.asarray(x,float)
        if x.shape != (3,) or not np.isfinite(x).all():
            raise ValueError('Finite three-state prior required')
        p=covariance_check(p,3,'reset prior covariance')
        self.filter.f.x,self.filter.f.P=x.copy(),p.copy()

    def update(self, arm, z_s, r_physical, model, anchor, height, *, cov=None):
        if arm not in ('D0','A','B','C'): raise ValueError('Unknown observation arm')
        empty=dict(iterations=0,robust_weight=None,huber_weight=None,NIS=None)
        if arm=='D0': return dict(empty,status='DR_only')
        observations=(z_s,r_physical)
        indices=[j for j in ([0] if arm=='A' else [1] if arm=='B' else [0,1])
                 if observations[j] is not None and math.isfinite(float(observations[j]))]
        if not indices: return dict(empty,status='missing')
        r0=covariance_check(np.diag([RS,RR]) if cov is None else cov,2,'RF R0')
        r0=r0[np.ix_(indices,indices)]
        x0=self.x.copy(); p0=covariance_check(self.P,3,'prior covariance')
        predicted, measured, rows=[],[],[]
        for j in indices:
            h,jac=model(x0.copy()) if j==0 else range_h(x0,anchor,height)
            jac=np.asarray(jac,float)
            if jac.shape != (3,) or not np.isfinite(jac).all() or not math.isfinite(h):
                raise ValueError('Invalid RF model/Jacobian')
            predicted.append(h if j==0 else h+B_OLD)
            measured.append(float(observations[j]) if j==0 else float(observations[j])+B_OLD)
            rows.append(jac)
        hmat=np.asarray(rows); innovation=np.asarray(measured)-predicted
        s0=covariance_check(hmat@p0@hmat.T+r0,len(indices),'prior innovation covariance')
        nis=float(innovation@np.linalg.solve(s0,innovation))
        gate=GATE_1D_99 if len(indices)==1 else GATE_2D_99
        if nis>gate:
            return dict(empty,status='rejected_NIS',NIS=nis,gate_threshold=gate)
        effective=r0/self.weight
        gain=np.linalg.solve(hmat@p0@hmat.T+effective,hmat@p0).T
        delta=gain@innovation
        new_x=x0+delta; new_x[2]=wrap(new_x[2])
        a=np.eye(3)-gain@hmat
        posterior=covariance_check(a@p0@a.T+gain@effective@gain.T,3,'posterior covariance')
        if not np.isfinite(new_x).all(): raise ValueError('Nonfinite posterior state')
        residual=innovation-hmat@delta
        whitened=np.linalg.solve(np.linalg.cholesky(r0),residual)
        objective=.5*float(delta@np.linalg.solve(p0,delta))+.5*self.weight*float(whitened@whitened)
        stationarity=np.linalg.solve(p0,delta)-hmat.T@np.linalg.solve(effective,residual)
        self.filter.f.x,self.filter.f.P=new_x,posterior
        return dict(status='applied',NIS=nis,gate_threshold=gate,iterations=0,
            robust_weight=self.weight,huber_weight=self.weight,
            H=hmat,K=gain,R_effective=effective,R0=r0,S0=s0,
            likelihood_scale=r0,observation_dimension=len(indices),
            innovation=innovation,whitened_residual=whitened,objective=objective,
            stationarity_norm=float(np.linalg.norm(stationarity)),
            covariance_convention='LINEARIZED_GAUSSIAN_JOSEPH',
            NIS_interpretation='UNWEIGHTED_PRIOR_R0_99_PERCENT_GATE',
            weight_policy='FIXED_COMMON_BLOCK_NO_RESIDUAL_DEPENDENCE')
