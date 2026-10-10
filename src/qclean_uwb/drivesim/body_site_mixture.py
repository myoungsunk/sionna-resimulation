"""Exploratory 2/3-yaw RF site+point soft-mixture update into six-state Sensor-v2 EKF.

This is a concrete nominal posterior algorithm, not a physically calibrated
multipath covariance model. It makes a single Joseph update per latent
site/point condition and moment-matches full 6x6 Gaussian states/covariances.

Measurement validity and causal limits:
- Only measured amplitude ratios / estimated pose/yaw and frozen LoS LUT enter.
- All first-arrival cluster quantities remain quality features; they are not
  treated as LUT measurements without a separately validated cluster LUT.
- Multiple probe packets were sampled at different times. End-of-probe P6 and
  relative headings are used with an **APPROXIMATE cross-time model**.
  The true pose/measurement cross-time covariance has not been independently
  validated; site probabilities/credible intervals are NOT calibrated.
- No ground-truth pose, coherent RF phase, path oracle or LoS-only truth read.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
from typing import Any

import numpy as np

from .hs_lut import s_model
from .filters import wrap


@dataclass(frozen=True)
class NominalSitePointCovariance:
    """FROZEN EXPLORATORY assumptions (not fitted on held-out full routes)."""
    site_bad_prior:float=.35
    point_bad_prior_clean_site:float=.06
    point_bad_prior_dirty_site:float=.55
    good_s_std:float=.06
    bad_s_std:float=.30
    site_offset_std_clean:float=.01
    site_offset_std_dirty:float=.15
    site_yaw_std_clean_deg:float=1.
    site_yaw_std_dirty_deg:float=15.
    maximum_station_xy_est_change_m:float=.02
    model_id:str="NOMINAL_20261010_UNCALIBRATED_SITE_POINT_6D"
    minimum_P_heading:float=1e-12

    def validate(self):
        p=(self.site_bad_prior,self.point_bad_prior_clean_site,
           self.point_bad_prior_dirty_site)
        if not all(0<v<1 and math.isfinite(v) for v in p):
            raise ValueError("invalid site/point priors")
        sigmas=(self.good_s_std,self.bad_s_std,self.site_offset_std_clean,
                self.site_offset_std_dirty,self.site_yaw_std_clean_deg,
                self.site_yaw_std_dirty_deg)
        if not all(v>0 and math.isfinite(v) for v in sigmas):
            raise ValueError("invalid RF covariance")
        if self.maximum_station_xy_est_change_m<0 or self.minimum_P_heading<=0:
            raise ValueError("invalid station PSD tolerance")


class SitePointMixture6:
    """One-time batch posterior, using all detected 1–3 s observations.

    Group hypotheses:
      M∈{site clean, site contaminated}, c_i∈{point clean,point bad}.
    Measurement covariance mode:
      R = diag(sigma(c_i)^2) + sigma_site(M)^2 11^T
          + sigma_yaw(M)^2 Hpsi Hpsi^T.

    Each model mode has a 6D Kalman/Gaussian posterior with full x,y,yaw
    Jacobian. The final state/covariance is moment-matched across hypotheses,
    preserving the x-y-yaw and calibration cross covariance.

    Traces generated during probe were propagated with the real Sensor-v2 EKF.
    The new posterior is carried forward to later drive steps by the
    ContinuousRFQualityDrive orchestrator. It must not be re-assimilated.
    """
    def __init__(self, spec:NominalSitePointCovariance=NominalSitePointCovariance()):
        spec.validate()
        self.spec=spec
        self._used_batches=set()

    def __call__(self,ekf:Any,packets:list[dict])->dict:
        if getattr(ekf,"pending",None) is not None:
            raise RuntimeError("batch posterior may run only after final probe interval")
        if ekf.lut is None:
            raise ValueError("frozen LoS LUT required")
        if len(packets)<1 or len(packets)>3:
            raise ValueError("mixture requires 1–3 probe points")
        identifiers=tuple(str(p["packet_id"]) for p in packets)
        if len(identifiers)!=len(set(identifiers)):
            raise ValueError("duplicate probe packet")
        if identifiers in self._used_batches:
            raise ValueError("batch already used")
        # No side-effects before validation.
        measured=[p for p in packets if p.get("detected",False) and math.isfinite(float(p["s"]))]
        if not measured:
            self._used_batches.add(identifiers)
            return dict(status="NO_VALID_RF_S",covariance_model_id=self.spec.model_id,
                        scientific_PASS=False,n_used=0,q_site_bad=None,q_point_bad=None)
        if len(measured)!=len(packets):
            # Missing points are NOT imputed as clean; record skipped ID.
            unavailable=[p["packet_id"] for p in packets if p not in measured]
        else:
            unavailable=[]
        x,P=ekf.f.mean_cov()
        x=np.asarray(x,float).copy();P=np.asarray(P,float).copy()
        if x.shape!=(6,) or P.shape!=(6,6) or not np.isfinite(x).all() or not np.isfinite(P).all():
            raise ValueError("invalid full six-state prior")
        if P[2,2]<=self.spec.minimum_P_heading or np.linalg.eigvalsh(P).min()<-1e-9:
            raise ValueError("invalid or singular P heading prior")
        # The packet snapshots hold ESTIMATED x,y,yaw only.
        coords=np.stack([np.asarray(p["estimated_pose_pre_rf"],float) for p in measured])
        if coords.shape!=(len(measured),3) or not np.isfinite(coords).all():
            raise ValueError("missing estimated packet XY/yaw")
        dist=np.linalg.norm(coords[:,:2]-x[None,:2],axis=1)
        if np.max(dist)>self.spec.maximum_station_xy_est_change_m:
            raise ValueError("same-site assumption invalid at probe packet")
        delta=np.array([wrap(float(p["estimate_yaw_pre_rf_rad"])-x[2])
                        for p in measured])
        c=ekf.cfg
        residual=[];H=[]
        for p,d in zip(measured,delta):
            h,j=s_model(ekf.lut,c.anchor_xyz,c.robot_z,
                  float(x[0]),float(x[1]),float(x[2]+d),
                  c.mount_deg,with_jac=True)
            j=np.asarray(j,float)
            if j.shape!=(3,) or not np.isfinite(j).all() or not np.isfinite(h):
                raise ValueError("invalid LUT Jacobian or observation")
            row=np.zeros(6);row[:3]=j
            H.append(row);residual.append(float(p["s"])-float(h))
        H=np.stack(H)
        r=np.asarray(residual,float)
        if not np.isfinite(r).all():raise ValueError("invalid s residual")
        modes=[]
        n=len(r);one=np.ones(n)
        if not 2*n < 10: # sanity about complexity, maximum 3 anyway
            raise ValueError("unbounded hypothesis count")
        for site_bad in (0,1):
            ps=self.spec.site_bad_prior if site_bad else 1-self.spec.site_bad_prior
            p_point=self.spec.point_bad_prior_dirty_site if site_bad else self.spec.point_bad_prior_clean_site
            tau0=(self.spec.site_offset_std_dirty if site_bad else
                  self.spec.site_offset_std_clean)
            tau_ang=math.radians(
                self.spec.site_yaw_std_dirty_deg if site_bad else
                self.spec.site_yaw_std_clean_deg)
            for bitset in product((0,1),repeat=n):
                flags=np.asarray(bitset,int)
                diag=np.where(flags,self.spec.bad_s_std,self.spec.good_s_std)**2
                R=np.diag(diag)+tau0**2*np.outer(one,one)+tau_ang**2*np.outer(H[:,2],H[:,2])
                assert np.linalg.eigvalsh(R).min()>0
                S=H@P@H.T+R
                sign,det=np.linalg.slogdet(S)
                if sign<=0 or not np.isfinite(det):
                    raise FloatingPointError("invalid full pose predictive covariance")
                Si_r=np.linalg.solve(S,r)
                mahal=float(r@Si_r)
                loglik=-.5*(mahal+det+n*math.log(2*math.pi))
                logprior=(math.log(ps)+int(flags.sum())*math.log(p_point)+
                          (n-int(flags.sum()))*math.log(1-p_point))
                K=np.linalg.solve(S,H@P).T
                xp=x+K@r;xp[2]=wrap(float(xp[2]))
                A=np.eye(6)-K@H
                Pp=A@P@A.T+K@R@K.T
                Pp=(Pp+Pp.T)*.5
                if np.linalg.eigvalsh(Pp).min()<-1e-8:
                    raise FloatingPointError("mode posterior P non PSD")
                modes.append((site_bad,flags,loglik+logprior,xp,Pp,mahal))
        logits=np.array([t[2] for t in modes])
        hi=float(np.max(logits))
        weights=np.exp(logits-hi);weights=weights/weights.sum()
        if not np.isfinite(weights).all():
            raise FloatingPointError("invalid hypothesis probabilities")
        # Moment matching relative to wrapped *PRIOR* yaw: do not average ±π raw.
        diff=[]
        for _,_,_,xp,_,_ in modes:
            d=xp-x;d[2]=wrap(float(xp[2]-x[2]));diff.append(d)
        diff=np.stack(diff)
        mean_shift=weights@diff
        xf=x+mean_shift;xf[2]=wrap(float(xf[2]))
        Pf=np.zeros((6,6),float)
        for weight,d,mode in zip(weights,diff,modes):
            err=d-mean_shift
            err[2]=wrap(float(err[2]))
            Pf+=weight*(mode[4]+np.outer(err,err))
        Pf=(Pf+Pf.T)*.5
        eig=np.linalg.eigvalsh(Pf)
        if eig.min()<-1e-8 or not np.isfinite(Pf).all():
            raise FloatingPointError("mixture posterior covariance is invalid")
        q_site=float(sum(w*m[0] for w,m in zip(weights,modes)))
        q_point=[float(sum(w*m[1][i] for w,m in zip(weights,modes))) for i in range(n)]
        # Every detected observation contributes via its likelihood in every model.
        # This is not a lowest-residual angle selector.
        ekf.f.comps[0].x=xf
        ekf.f.comps[0].P=Pf
        self._used_batches.add(identifiers)
        return dict(status="APPLIED_UNCALIBRATED_MIXTURE",covariance_model_id=self.spec.model_id,
                    scientific_PASS=False,calibration="NOT_CALIBRATED_HELDOUT",
                    covariance_validated=False,
                    cross_time_pose_measurement_covariance="UNVERIFIED_APPROXIMATION",
                    n_used=n,
                    n_modes=len(modes),
                    q_site_bad=q_site,q_point_bad=q_point,
                    used_point_ids=[p["packet_id"] for p in measured],
                    unavailable_point_ids=unavailable,
                    mean_abs_residual_s=float(np.mean(abs(r))),
                    mean_mahal_mode=float(sum(w*m[5] for w,m in zip(weights,modes))),
                    heading_correction_deg=math.degrees(wrap(float(xf[2]-x[2]))),
                    heading_std_deg=math.degrees(math.sqrt(max(0,Pf[2,2]))),
                    posterior_psd_min_eigenvalue=float(eig.min()))
