#!/usr/bin/env python3
"""Disentangle problematic theta=0 LUT slice versus theta=2,4 interpolants
using original matched native LoS-only Sionna H-derived labels.

Original FFD port-bank LFS bytes are NOT necessary to test the LUT slice.
This cannot prove raw FFD polar-basis input has no singularity; only tests
whether the theta=0 LUT contribution explains LoS matching failures.
"""
from __future__ import annotations
import argparse,math,json
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
BLOCK=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
import sys
sys.path.insert(0,str(RUN/"source/src"))
from qclean_uwb.drivesim.hs_lut import HsLut,s_model

def main():
  ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
  args=ap.parse_args();o=args.out;o.mkdir(parents=True,exist_ok=True)
  meta=json.loads((RUN/"LUT/hs_lut_meta.json").read_text())["meta"]
  lut=HsLut(dict(theta_deg=meta["theta_deg"],
      phi_deg=np.arange(meta["phi_deg"][0],meta["phi_deg"][1]+.01,meta["phi_deg"][2]),
      s=np.load(RUN/"LUT/hs_lut_2deg.npy")))
  cases={c["case"]:c for c in json.loads((BLOCK/"CASES.json").read_text())}
  labels=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
  assert len(labels)==9519
  res=[]
  for case,g in labels.groupby("case"):
    c=cases[case];ax,ay,az=c["anchor_xyz"]
    x,y,psi=np.asarray(g.true_x),np.asarray(g.true_y),np.radians(g.true_yaw_deg)
    u,v=x-ax,y-ay
    theta=np.degrees(np.arctan2(np.hypot(u,v),az-c["robot_z"]))
    phi_tx=np.degrees(np.arctan2(-v,u))
    phi_rx=(np.degrees(np.arctan2(-v,-u))-np.degrees(psi)-c["mount_deg"]+180)%360-180
    actual=s_model(lut,c["anchor_xyz"],c["robot_z"],x,y,psi,c["mount_deg"])
    assert np.max(abs(actual-np.asarray(g.s_lut_truth)))<1e-10
    # Two fixed, predeclared θ0-free diagnostics; do not tune using test labels.
    h2=lut(np.full_like(theta,2.),phi_tx,phi_rx)
    h4=lut(np.full_like(theta,4.),phi_tx,phi_rx)
    held2=np.where(theta<2,h2,actual)
    ext2=np.where(theta<2,h2+(theta-2.)*(h4-h2)/2,actual)
    ext2=np.clip(ext2,-1,1)
    # Distinct comparison of θ0 vs θ2 original stored values at same phi arguments.
    h0=lut(np.zeros_like(theta),phi_tx,phi_rx)
    out=pd.DataFrame(dict(case=case,route=g.route,pose_id=g.pose_id,
        true_yaw_deg=g.true_yaw_deg,mount_deg=c["mount_deg"],
        rho_m=np.hypot(u,v),theta_deg=theta,
        native_s_los=g.s_los,raw_s_lut=actual,
        lut_at_theta0=h0,lut_at_theta2=h2,lut_at_theta4=h4,
        clamp_theta2=held2,extrapolate_theta2_4=ext2,
        residual_raw=np.asarray(g.s_los)-actual,
        residual_clamp2=np.asarray(g.s_los)-held2,
        residual_extrapolate=np.asarray(g.s_los)-ext2))
    res.append(out)
  data=pd.concat(res,ignore_index=True)
  data.to_csv(o/"ALL_NATIVE_LOS_VS_POLE_SLICE_CANDIDATES.csv.gz",index=False)
  stats=[]
  for low,hi in [(0,.05),(.05,.1),(.1,.2),(.2,.5),(.5,1.),(1.,100.)]:
    g=data[(data.rho_m>=low)&(data.rho_m<hi)]
    if len(g)==0:continue
    for label,col in [("ORIGINAL","residual_raw"),("THETA_CLAMP_2","residual_clamp2"),
                      ("THETA_EXTRAP_2_4","residual_extrapolate")]:
      z=np.asarray(g[col],float)
      stats.append(dict(radius_range=f"{low:g}-{hi:g}m",candidate=label,n=len(g),
          e_LoS_LUT_RMS=float(np.sqrt(np.mean(z*z))),
          e_abs_p90=float(np.quantile(abs(z),.9)),
          e_abs_max=float(max(abs(z))),
          error_gt01=int((abs(z)>.1).sum())))
  stats=pd.DataFrame(stats)
  stats.to_csv(o/"PHYSICAL_NATIVE_LOS_FIXED_POLE_CANDIDATE_SCORES.csv",index=False)
  # Natural reference at θ→0: four distinct phi arrival bearings but fixed body yaw
  # and fixed physical anchor; tx/rx azimuths MUST obey propagation direction.
  rows=[]
  for mount in (0.,45.):
    c=cases["R2_aA_m0"]
    a=np.asarray(c["anchor_xyz"])
    for rho in (0.,.00001,.001,.01,.03,.05,.0768,.1):
      for yaw in (0.,45.,90.,180.):
        vals={name:[] for name in ("raw","theta0","theta2","theta4")}
        for bearing in range(0,360,45):
          x=float(a[0]+rho*math.cos(math.radians(bearing)))
          y=float(a[1]+rho*math.sin(math.radians(bearing)))
          u,v=x-a[0],y-a[1]
          th=math.degrees(math.atan2(math.hypot(u,v),a[2]-c["robot_z"]))
          pt=math.degrees(math.atan2(-v,u))
          pr=(math.degrees(math.atan2(-v,-u))-yaw-mount+180)%360-180
          for name,ang in (("raw",th),("theta0",0),("theta2",2),("theta4",4)):
            vals[name].append(float(lut(ang,pt,pr)))
        for name,q in vals.items():
          rows.append(dict(mount_deg=mount,body_yaw_deg=yaw,rho_m=rho,
                           LUT_slice=name,range_of_s_across_bearings=max(q)-min(q),
                           std_of_s_across_bearings=float(np.std(q)),
                           median_s=float(np.median(q))))
  ring=pd.DataFrame(rows);ring.to_csv(o/"THETA_0_2_4_SLICE_PHYSICAL_AZIMUTH_SWEEP.csv",index=False)
  # Reference continuity inference strongly depends on θ0 vs θ2, but doesn't
  # directly read FFD raw e_theta/e_phi at pole.
  close=stats[stats.radius_range.isin(["0-0.05m","0.05-0.1m"])]
  result={
    "status":"LUT_SLICE_DIAGNOSTIC_EXECUTED",
    "source":"Frozen hash-verified 2degree FFD LUT original 7-case native LoS labels",
    "n_original_native_poses":len(data),
    "original_near_pole_9_poses":int((data.rho_m<.1).sum()),
    "overall":json.loads(stats.to_json(orient="records")),
    "warning":["Theta-clamp/extrapolate are diagnostic alternatives, not validated new physical LUT",
               "Spherical e_theta/e_phi FFD original LFS byte content is still needed to attribute origin definitively",
               "If raw theta0 is ill-defined it may contaminate interpolation for theta<2deg",
               "The native LOS and LUT share FFD origins but different interpolation/contraction pipelines",
               "No new native H for synthetic ring points and no filter reexecution"]}
  (o/"STATUS.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
  with (o/"RESULTS_KO.md").open("w") as f:
    f.write("# 실제 Native LoS와 theta0/2/4 FFD LUT slice 분리 검증\n\n")
    f.write("기존 9519 native LoS labels과 frozen hs_lut_2deg를 사용. ThetaClamp/Extrapolate는 interpolation 원인 탐색 대조이며 모델 PASS가 아니다.\n\n")
    f.write(stats.to_markdown(index=False,floatfmt=".5f"))
    f.write("\n\nOriginal LP bank files are Git-LFS pointers, raw pole Cartesian field unresolved unless restored by LFS access.\n")
  print("LUT_SLICE_RESULT",json.dumps({"n":len(data),"near_pole":result["original_near_pole_9_poses"],
    "under0.1":json.loads(close.to_json(orient="records")),
    "sweep":json.loads(ring[(ring.rho_m==.01)&(ring.body_yaw_deg==0)&(ring.mount_deg==0)].to_json(orient="records"))},
    allow_nan=False),flush=True)
if __name__=="__main__":main()
