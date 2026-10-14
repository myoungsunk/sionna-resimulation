"""Read-only numeric frozen LoS LUT and physical [s,range] forward model.

Verbatim interpolation/geometric chain rule from archived hs_lut.py frozen
contract, but no FFD generation or model training. Parity vs 14 saved
one-step H/h outputs is REQUIRED before any new inference.
"""
from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np

B_OLD=-0.5315983906250129
RS=0.0081
RR=0.0068578637
R0=np.diag([RS,RR])
GATE_JOINT=9.210340371976184

LUT_REL='results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/'
class FrozenLut:
 def __init__(self,root:Path):
  root=Path(root)
  meta=json.loads((root/(LUT_REL+'hs_lut_meta.json')).read_text())['meta']
  self.theta=np.asarray(meta['theta_deg'],float)
  a,b,step=(float(x) for x in meta['phi_deg'])
  self.phi=np.arange(a,b+step/2,step)
  self.s=np.load(root/(LUT_REL+'hs_lut_2deg.npy'),mmap_mode='r',allow_pickle=False)
  if self.s.shape!=(len(self.theta),len(self.phi),len(self.phi)):
   raise RuntimeError('LUT shape/axes mismatch')
  self.dt=self.theta[1]-self.theta[0];self.dp=self.phi[1]-self.phi[0];self.np=len(self.phi);self.nt=len(self.theta)

 def __call__(self,theta,phi_tx,phi_rx):
  t=np.clip(float(theta)/self.dt,0.,self.nt-1-1e-9)
  a=(float(phi_tx)+180.)/self.dp;b=(float(phi_rx)+180.)/self.dp
  i0=int(np.floor(t));ft=t-i0
  jf,kf=np.floor(a),np.floor(b);fa,fb=a-jf,b-kf
  j=int(jf)%self.np;k=int(kf)%self.np
  j1=(j+1)%self.np;k1=(k+1)%self.np;i1=i0+1
  S=self.s
  c000,c001,c010,c011=S[i0,j,k],S[i0,j,k1],S[i0,j1,k],S[i0,j1,k1]
  c100,c101,c110,c111=S[i1,j,k],S[i1,j,k1],S[i1,j1,k],S[i1,j1,k1]
  c00,c01,c10,c11=c000*(1-fb)+c001*fb,c010*(1-fb)+c011*fb,c100*(1-fb)+c101*fb,c110*(1-fb)+c111*fb
  c0,c1=c00*(1-fa)+c01*fa,c10*(1-fa)+c11*fa
  val=c0*(1-ft)+c1*ft
  d_t=(c1-c0)/self.dt
  d_a=((c01-c00)*(1-ft)+(c11-c10)*ft)/self.dp
  d_b=(((c001-c000)*(1-fa)+(c011-c010)*fa)*(1-ft)+
       ((c101-c100)*(1-fa)+(c111-c110)*fa)*ft)/self.dp
  return float(val),np.array([d_t,d_a,d_b],float)

 def model(self,x,anchor_xyz,mount_deg):
  """Returns h=[s,corrected_raw_range] and H for 3state or 4state."""
  x=np.asarray(x,float)
  if x.shape not in ((3,),(4,)):raise ValueError('state must be 3 or 4')
  ax,ay,az=(float(v) for v in anchor_xyz)
  u,v=x[0]-ax,x[1]-ay;h=az-.45
  rho2=max(u*u+v*v,1e-12);rho=math.sqrt(rho2)
  psi=math.degrees(float(x[2]))+mount_deg
  theta_geo=math.degrees(math.atan2(rho,h))
  phi_tx=math.degrees(math.atan2(-v,u))
  phi_rx=(math.degrees(math.atan2(-v,-u))-psi+180.)%360.-180.
  hs,g=self(theta_geo,phi_tx,phi_rx)
  k=180./math.pi
  dthdu=h/(rho2+h*h)*u/rho*k;dthdv=h/(rho2+h*h)*v/rho*k
  dtxdu=v/rho2*k;dtxdv=-u/rho2*k
  drxdu=-v/rho2*k;drxdv=u/rho2*k
  H=np.zeros((2,len(x)))
  H[0,0]=g[0]*dthdu+g[1]*dtxdu+g[2]*drxdu
  H[0,1]=g[0]*dthdv+g[1]*dtxdv+g[2]*drxdv
  H[0,2]=-g[2]*k
  distance=math.sqrt(u*u+v*v+h*h)
  H[1,:2]=[u/distance,v/distance]
  return np.array([hs,distance+B_OLD]),H
