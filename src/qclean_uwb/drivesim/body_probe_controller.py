"""Causal 1/2/3-point body-yaw probe controller. NEVER takes true pose."""
from __future__ import annotations
from dataclasses import dataclass
import math

def wrap(x): return (x+math.pi)%(2*math.pi)-math.pi

@dataclass(frozen=True)
class ProbeMotionConfig:
    offsets_deg: tuple[float,...]=(0.,10.,20.)
    max_angular_speed_deg_s:float=25.
    max_angular_acceleration_deg_s2:float=100.
    proportional_gain_s_inv:float=3.
    yaw_tolerance_deg:float=.7
    rate_tolerance_deg_s:float=1.5
    settle_duration_s:float=.4
    rf_integration_s:float=.2
    max_stage_duration_s:float=15.
    max_total_duration_s:float=90.
    def validate(self):
        if not 1<=len(self.offsets_deg)<=3 or self.offsets_deg[0]!=0 or any(not math.isfinite(v) or abs(v)>60 for v in self.offsets_deg):
            raise ValueError("invalid probe offsets")
        v=(self.max_angular_speed_deg_s,self.max_angular_acceleration_deg_s2,
           self.proportional_gain_s_inv,self.yaw_tolerance_deg,self.rate_tolerance_deg_s,
           self.settle_duration_s,self.rf_integration_s,self.max_stage_duration_s,self.max_total_duration_s)
        if not all(math.isfinite(x) and x>0 for x in v):
            raise ValueError("invalid timing/limits")

@dataclass(frozen=True)
class ProbeDecision:
    phase:str
    command_linear_m_s:float
    command_angular_rad_s:float
    target_offset_deg:float
    rf_fire:bool
    rf_point_index:int|None
    elapsed_s:float
    done:bool
    failed:bool

class ProbeBodyController:
    """Feed estimated yaw and estimated yaw rate only, from an independent estimator."""
    def __init__(self,reference_estimated_yaw_rad:float,config:ProbeMotionConfig=ProbeMotionConfig()):
        config.validate()
        if not math.isfinite(reference_estimated_yaw_rad): raise ValueError("nonfinite heading")
        self.reference=reference_estimated_yaw_rad;self.cfg=config
        self.point=0;self.phase="SETTLE";self.total=0.;self.stage=0.;self.stable=0.
        self.failure_reason=None
    def _target(self):
        return self.cfg.offsets_deg[self.point] if self.point<len(self.cfg.offsets_deg) else 0.
    def update(self,*,estimated_yaw_rad:float,estimated_yaw_rate_rad_s:float,dt_s:float)->ProbeDecision:
        if not all(math.isfinite(x) for x in (estimated_yaw_rad,estimated_yaw_rate_rad_s,dt_s)) or dt_s<=0:
            raise ValueError("bad measured feedback/dt")
        if self.phase in ("DONE","FAILED"): return self._out(0.,False,None)
        self.total+=dt_s;self.stage+=dt_s;w=0.;fire=False;packet=None
        if self.total>self.cfg.max_total_duration_s or self.stage>self.cfg.max_stage_duration_s:
            self.phase="FAILED";self.failure_reason="TIMEOUT"
        else:
            err=wrap(self.reference+math.radians(self._target())-estimated_yaw_rad)
            settled=abs(err)<=math.radians(self.cfg.yaw_tolerance_deg) and abs(estimated_yaw_rate_rad_s)<=math.radians(self.cfg.rate_tolerance_deg_s)
            if self.phase in ("ROTATE","RETURN"):
                if settled:
                    self.phase="SETTLE_RETURN" if self.phase=="RETURN" else "SETTLE";self.stage=self.stable=0.
                else:
                    maxw=math.radians(self.cfg.max_angular_speed_deg_s)
                    alpha=math.radians(self.cfg.max_angular_acceleration_deg_s2)
                    w=math.copysign(min(maxw,self.cfg.proportional_gain_s_inv*abs(err),math.sqrt(2*alpha*abs(err))),err)
            elif self.phase in ("SETTLE","SETTLE_RETURN"):
                if settled:
                    self.stable+=dt_s
                    if self.stable>=self.cfg.settle_duration_s:
                        self.phase="DONE" if self.phase=="SETTLE_RETURN" else "MEASURE"
                        self.stage=self.stable=0.
                else:
                    self.phase="RETURN" if self.phase=="SETTLE_RETURN" else "ROTATE"
                    self.stage=self.stable=0.
            elif self.phase=="MEASURE":
                if not settled:
                    self.phase="ROTATE";self.stage=self.stable=0.
                elif self.stage>=self.cfg.rf_integration_s:
                    fire=True;packet=self.point;self.point+=1;self.stage=self.stable=0.
                    self.phase="ROTATE" if self.point<len(self.cfg.offsets_deg) else "RETURN"
        return self._out(w,fire,packet)
    def _out(self,w,fire,packet):
        return ProbeDecision(self.phase,0.,w if self.phase not in ("DONE","FAILED") else 0.,
                             self._target(),fire,packet,self.total,self.phase=="DONE",self.phase=="FAILED")
