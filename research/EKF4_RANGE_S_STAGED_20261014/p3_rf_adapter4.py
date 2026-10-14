"""Canonical EKF4 [range_raw, s] read-only frozen-LUT observation adapter.

Replicates pinned HsLut trilinear interpolation and s_model chain rule,
without reprocessing FFD or changing original EKF4 P2 solver.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
LUT_REL="results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/"
B_OLD=-0.5315983906250129
RR=0.0068578637
RS=0.0081
R0=np.diag([RR,RS])
GATE_JOINT=9.210340371976184
OBSERVATION_ORDER=("range_raw_m","s")
PERMUTE_SR_TO_RS=np.array([[0.,1.],[1.,0.]])

@dataclass(frozen=True)
class ObservationFrame:
    case_id: str
    channel: str
    time_s: float
    pose_id: int
    z: np.ndarray
    h: np.ndarray
    H: np.ndarray
    R: np.ndarray
    quality: dict

class FrozenLut:
    def __init__(self, root=REPO):
        root=Path(root)
        meta=json.loads((root/(LUT_REL+"hs_lut_meta.json")).read_text())["meta"]
        self.theta=np.asarray(meta["theta_deg"],float)
        a,b,step=(float(x) for x in meta["phi_deg"])
        self.phi=np.arange(a,b+step/2,step)
        self.s=np.load(root/(LUT_REL+"hs_lut_2deg.npy"),
                       mmap_mode="r",allow_pickle=False)
        if self.s.shape!=(46,180,180) or self.s.shape!=(
                len(self.theta),len(self.phi),len(self.phi)):
            raise RuntimeError("FROZEN_LUT_GRID_SHAPE_CHANGED")
        self.dt=float(self.theta[1]-self.theta[0])
        self.dp=float(self.phi[1]-self.phi[0])
        self.np=len(self.phi)
        self.nt=len(self.theta)
        if not (np.allclose(np.diff(self.theta),self.dt)
                and np.allclose(np.diff(self.phi),self.dp)):
            raise RuntimeError("FROZEN_LUT_AXIS_SPACING_CHANGED")

    def __call__(self, theta_deg, phi_tx_deg, phi_rx_deg):
        t=np.clip(np.asarray(theta_deg,float)/self.dt,0.0,self.nt-1-1e-9)
        a=(np.asarray(phi_tx_deg,float)+180.0)/self.dp
        b=(np.asarray(phi_rx_deg,float)+180.0)/self.dp
        i0=np.floor(t).astype(int)
        j0f,k0f=np.floor(a),np.floor(b)
        ft,fa,fb=t-i0,a-j0f,b-k0f
        j0,k0=j0f.astype(int)%self.np,k0f.astype(int)%self.np
        j1,k1,i1=(j0+1)%self.np,(k0+1)%self.np,i0+1
        S=self.s
        c000,c001,c010,c011=S[i0,j0,k0],S[i0,j0,k1],S[i0,j1,k0],S[i0,j1,k1]
        c100,c101,c110,c111=S[i1,j0,k0],S[i1,j0,k1],S[i1,j1,k0],S[i1,j1,k1]
        c00,c01,c10,c11=c000*(1-fb)+c001*fb,c010*(1-fb)+c011*fb,c100*(1-fb)+c101*fb,c110*(1-fb)+c111*fb
        c0,c1=c00*(1-fa)+c01*fa,c10*(1-fa)+c11*fa
        val=c0*(1-ft)+c1*ft
        d_t=(c1-c0)/self.dt
        d_a=((c01-c00)*(1-ft)+(c11-c10)*ft)/self.dp
        d_b=(((c001-c000)*(1-fa)+(c011-c010)*fa)*(1-ft)
             +((c101-c100)*(1-fa)+(c111-c110)*fa)*ft)/self.dp
        return float(val),np.array([d_t,d_a,d_b],float)

    def model(self,x,case):
        x=np.asarray(x,float)
        if x.shape not in ((3,),(4,)) or not np.isfinite(x).all():
            raise ValueError("EKF4_POSE_INVALID")
        anchor=np.asarray(case["anchor"],float)
        if anchor.shape!=(3,) or not np.isfinite(anchor).all():
            raise ValueError("INVALID_FROZEN_ANCHOR")
        mount=float(case["mount_deg"])
        z_tag=float(case["robot_z_m"])
        u,v=x[0]-anchor[0],x[1]-anchor[1]
        h=anchor[2]-z_tag
        rho2=np.maximum(u*u+v*v,1e-12)
        rho=np.sqrt(rho2)
        psi=np.degrees(x[2])+mount
        theta_geo=np.degrees(np.arctan2(rho,h))
        phi_tx=np.degrees(np.arctan2(-v,u))
        phi_rx=(np.degrees(np.arctan2(-v,-u))-psi+180.)%360.-180.
        val,g=self(theta_geo,phi_tx,phi_rx)
        k=180./np.pi
        dth_du=h/(rho2+h*h)*u/rho*k
        dth_dv=h/(rho2+h*h)*v/rho*k
        dtx_du=v/rho2*k
        dtx_dv=-u/rho2*k
        drx_du=-v/rho2*k
        drx_dv=u/rho2*k
        dsdx=g[0]*dth_du+g[1]*dtx_du+g[2]*drx_du
        dsdy=g[0]*dth_dv+g[1]*dtx_dv+g[2]*drx_dv
        dsdpsi=-g[2]*k
        # Keep the exact original 3D range formulation, not a 2D
        # range with a post-hoc constant.
        distance=float(np.linalg.norm(np.array([u,v,z_tag-anchor[2]])))
        H=np.zeros((2,len(x)),float)
        H[0,:2]=[u/distance,v/distance]
        H[1,:3]=[dsdx,dsdy,dsdpsi]
        pred=np.array([distance+B_OLD,val],float)
        return pred,H

    def quality(self,x,case):
        x=np.asarray(x,float)
        ax,ay,_=case["anchor"]
        rho=float(np.hypot(x[0]-ax,x[1]-ay))
        return {
            "estimated_horizontal_anchor_distance_m":rho,
            "near_anchor_pole":rho<=.1,
            "direct_bias_measurement_derivative_zero":True,
            "original_R0_independence_unverified":True}

def make_ekf4_observation(trace,k,prior_state,case,lut:FrozenLut):
    if k<0 or k>=len(trace.t_s):
        raise IndexError("POSE_INDEX_OUT_OF_RANGE")
    if not trace.detected[k]:
        raise ValueError("FROZEN_RF_NO_PACKET_AT_POSE")
    h,H=lut.model(prior_state,case)
    z=np.array([trace.z_range[k],trace.z_s[k]],float)
    if not (np.isfinite(h).all() and np.isfinite(H).all()
            and np.isfinite(z).all()):
        raise RuntimeError("RF_MODEL_NONFINITE")
    return ObservationFrame(
        trace.case_id,trace.channel,float(trace.t_s[k]),
        int(trace.pose_id[k]),z,h,H,R0.copy(),lut.quality(prior_state,case))

def reorder_original_joint(v,h,H,R,nu=None,S=None,K=None):
    P=PERMUTE_SR_TO_RS
    result={"z":P@v,"h":P@h,"H":P@H,"R":P@R@P.T}
    if nu is not None:result["innovation"]=P@nu
    if S is not None:result["S"]=P@S@P.T
    if K is not None:result["K"]=K@P.T
    return result
