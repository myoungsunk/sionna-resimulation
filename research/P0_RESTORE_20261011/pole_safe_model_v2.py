"""P0 correction v2.
V1's 1-3deg splice reused the known-bad theta0 interpolation on (1,2).
This is a demonstrated contamination bug, not held-out RMSE hyperparameter tuning.
Keep original V1 evidence; use raw-field model over the ENTIRE bad theta cell.
"""
import math
import numpy as np
from qclean_uwb.drivesim import hs_lut as HL
from pole_safe_model import PoleSafeModel as OriginalCandidate

class PoleSafeModelV2(OriginalCandidate):
    def __init__(self,lut,banks):
        super().__init__(lut,banks)
        self.model_version='CARTESIAN_FIELD_DEG4_CORE2_BLEND2_3_FP_V2'

    def scalar(self,anchor,z,x,y,psi,mount=0.,with_jac=False):
        u,v=x-anchor[0],y-anchor[1];rho=math.hypot(u,v);height=anchor[2]-z
        theta=math.degrees(math.atan2(rho,height))
        if theta>=3.:
            return HL.s_model(self.original_lut,anchor,z,x,y,psi,mount,with_jac=with_jac)
        val,J,tap=self.field.s_jac(anchor,z,x,y,psi,mount)
        if theta<=2.:return (val,J) if with_jac else val
        t=theta-2.;w=t**3*(10-15*t+6*t*t);dw=30*t*t*(t-1)**2
        outer,K=HL.s_model(self.original_lut,anchor,z,x,y,psi,mount,with_jac=True)
        dtheta=np.array([height*u/(rho*(rho*rho+height*height)),height*v/(rho*(rho*rho+height*height)),0.])*180/np.pi
        val_out=(1-w)*val+w*outer
        derivative=(1-w)*J+w*K+dw*dtheta*(outer-val)
        return (float(val_out),derivative) if with_jac else float(val_out)
