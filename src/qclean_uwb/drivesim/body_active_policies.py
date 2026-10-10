"""Executable *NOMINAL* RF s quality gate and causal Sensor-v2 single-s update.

These are transparent conservative prototypes for the causal orchestrator.
The conversion of NIS and FP/cluster differences into q is NOT held-out
calibrated to P(actual heading correct <=5deg). Do not use as a production
confidence probability; full LoS FFD LUT, port gains and thermal SNR must
be verified before native-Sionna science comparisons.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from .hs_lut import s_model

@dataclass(frozen=True)
class NominalFPQualityConfig:
    s_std:float=.09
    nis_half_confidence:float=6.6349
    nis_softness:float=2.0
    cluster_absdiff_scale:float=.15
    use_simulated_first_cluster:bool=True
    model_id:str="UNVALIDATED_NIS_AND_FP_CLUSTER_QUALITY_V1"

    def validate(self):
        vals=(self.s_std,self.nis_half_confidence,
              self.nis_softness,self.cluster_absdiff_scale)
        if not all(math.isfinite(x) and x>0 for x in vals):
            raise ValueError("positive noise and quality config required")

def _predict_s(lut,anchor_xyz,robot_z,mount_deg,x):
    h,j=s_model(lut,anchor_xyz,robot_z,float(x[0]),float(x[1]),
                float(x[2]),float(mount_deg),with_jac=True)
    H=np.zeros(6);H[:3]=j
    return float(h),H

class NominalFPQuality:
    """API: callable(measured_packet, x_pre_s[6], P_pre_s[6,6])->q_good.

    First-arrival common gates are ONLY model-quality covariates, not
    extra independent s measurements. The gate never reads oracle H/true pose.
    """
    def __init__(self,lut,anchor_xyz,robot_z,mount_deg,
                 config:NominalFPQualityConfig=NominalFPQualityConfig()):
        config.validate()
        if lut is None:raise ValueError("frozen LoS LUT required")
        self.lut,self.anchor,self.z,self.mount,self.cfg=(
            lut,anchor_xyz,robot_z,mount_deg,config)
        self.last_diagnostic=None

    def __call__(self,packet,x,P):
        x=np.asarray(x,float);P=np.asarray(P,float)
        if x.shape!=(6,) or P.shape!=(6,6):
            raise ValueError("quality requires full six-state prior")
        if not packet.detected or not np.isfinite(packet.s):
            self.last_diagnostic=dict(status="NOT_DETECTED",q_good=0.,
                                      model_id=self.cfg.model_id)
            return 0.
        h,H=_predict_s(self.lut,self.anchor,self.z,self.mount,x)
        S=float(H@P@H+self.cfg.s_std**2)
        if not math.isfinite(S) or S<=0:raise ValueError("predictive s innovation covariance invalid")
        innovation=float(packet.s-h)
        nis=innovation**2/S
        d=0.
        if (self.cfg.use_simulated_first_cluster and
              getattr(packet,"first_cluster_s",None) is not None and
              getattr(packet,"first_cluster_availability","")=="SIMULATED_AMPLITUDE_CIR_ONLY"):
            values=np.asarray(packet.first_cluster_s,float)
            if values.ndim!=1:raise ValueError("bad cluster shape")
            finite=values[np.isfinite(values)]
            if len(finite):d=float(np.max(abs(finite-packet.s)))
        logbad=(nis-self.cfg.nis_half_confidence)/self.cfg.nis_softness
        logbad+=d/self.cfg.cluster_absdiff_scale
        # Numerical stable sigmoid; q is a risk score, not calibrated P(correct).
        q=float(np.exp(-np.logaddexp(0.,logbad)))
        self.last_diagnostic=dict(status="AVAILABLE",
           model_id=self.cfg.model_id,q_good=q,s_innovation=innovation,
           NIS=nis,FP_cluster_max_s_difference=d,
           calibration="UNVALIDATED_SCIENTIFIC_PROTOTYPE")
        return q

@dataclass(frozen=True)
class NominalSingleSConfig:
    q_floor:float=.1
    max_variance_multiplier:float=100.
    model_id:str="UNVALIDATED_FROZEN_LUT_S_R_Q_INFLATED"

class NominalFPLUTUpdate:
    """API: callable(ekf,packet,q_good)->{status,model_id,...}.
    Causal s update after range. Do NOT call if s already assimilated.
    """
    def __init__(self,spec:NominalSingleSConfig=NominalSingleSConfig()):
        if not(0<spec.q_floor<1) or spec.max_variance_multiplier<1:
            raise ValueError("invalid nominal RF soft weighting")
        self.spec=spec

    def __call__(self,ekf,packet,q_good):
        if getattr(ekf,"pending",None) is None:
            raise RuntimeError("cannot add s outside an active sensor-v2 tick")
        if ekf.lut is None:
            raise ValueError("frozen LoS LUT required for s")
        if not packet.detected or not np.isfinite(packet.s):
            return dict(status="MISSING",model_id=self.spec.model_id)
        if not math.isfinite(q_good) or not 0<q_good<=1:
            raise ValueError("quality out of range")
        x,P=ekf.f.mean_cov()
        h,H=_predict_s(ekf.lut,ekf.cfg.anchor_xyz,ekf.cfg.robot_z,
                       ekf.cfg.mount_deg,x)
        nominal=float(ekf.f._s_R(*packet.power))
        factor=min(self.spec.max_variance_multiplier,
                  max(1.,1/max(q_good,self.spec.q_floor)**2))
        R=nominal*factor
        y,Rout,S,status=ekf.f.scalar(float(packet.s),h,H,R,"s")
        ekf.pending.update(s_H=H,s_innovation=float(y),s_R=float(Rout),
                           s_S=float(S),s_status=str(status),
                           single_quality_q=float(q_good),
                           s_nominal_multiplier=float(factor))
        return dict(status=str(status),model_id=self.spec.model_id,
                    q_nominal=float(q_good),R_s_effective=float(R),
                    innovation_pre_gate=float(y),S_pre_gate=float(S),
                    NIS_pre_gate=float(y*y/S) if S>0 else None,
                    calibration="NOT_HELDOUT_VALIDATED",scientific_PASS=False)
