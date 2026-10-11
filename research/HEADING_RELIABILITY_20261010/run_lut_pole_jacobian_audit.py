#!/usr/bin/env python3
"""Test actual frozen s LUT numerical continuity/gradient at overhead anchor.

Uses native matched LoS labels at ORIGINAL stored pose only; other ring grid
points test only the LUT model, not independently generated Sionna channels.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
BLOCK=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
import sys
sys.path.insert(0,str(RUN/"source/src"))
from qclean_uwb.drivesim.hs_lut import HsLut,s_model
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);args=ap.parse_args()
 o=args.out;o.mkdir(parents=True,exist_ok=True)
 meta=json.loads((RUN/"LUT/hs_lut_meta.json").read_text())["meta"]
 lut=HsLut(dict(theta_deg=meta["theta_deg"],
               phi_deg=np.arange(meta["phi_deg"][0],meta["phi_deg"][1]+.01,meta["phi_deg"][2]),
               s=np.load(RUN/"LUT/hs_lut_2deg.npy")))
 cases={c["case"]:c for c in json.loads((BLOCK/"CASES.json").read_text())}
 data=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
 assert len(data)==9519
 rows=[]
 for c,g in data.groupby("case"):
  anchor=cases[c]["anchor_xyz"]
  rr=np.hypot(g.true_x-anchor[0],g.true_y-anchor[1])
  q=g[rr<=.5]
  for _,r in q.iterrows():
   x,y,psi=float(r.true_x),float(r.true_y),math.radians(r.true_yaw_deg)
   cfg=cases[c]
   h,H=s_model(lut,anchor,cfg["robot_z"],x,y,psi,cfg["mount_deg"],with_jac=True)
   dr=math.hypot(x-anchor[0],y-anchor[1])
   # Finite-difference xy/heading derivatives at ORIGINAL pose,
   # not ground truth gradients of Sionna RF.
   fd=[]
   for hstep in [1e-4,1e-3]:
    for j in range(3):
     inp=[x,y,psi];im=list(inp);ip=list(inp)
     ip[j]+=hstep;im[j]-=hstep
     a=s_model(lut,anchor,cfg["robot_z"],*ip,cfg["mount_deg"])
     b=s_model(lut,anchor,cfg["robot_z"],*im,cfg["mount_deg"])
     fd.append(float((a-b)/(2*hstep)))
   rows.append(dict(case=c,pose_id=int(r.pose_id),rho_m=dr,
     incidence_theta_deg=float(math.degrees(math.atan2(dr,anchor[2]-cfg["robot_z"]))),
     true_yaw_deg=float(r.true_yaw_deg),mount_deg=float(cfg["mount_deg"]),
     s_LOS_direct=float(r.s_los),s_LUT_model=float(h),
     e_LUT=float(r.s_los-h),e_MP=float(r.e_MP),
     Jx_per_m=float(H[0]),Jy_per_m=float(H[1]),Jpsi_per_rad=float(H[2]),
     Jxy_norm=float(np.linalg.norm(H[:2])),Jpsi_abs=float(abs(H[2])),
     finite_diff_x_1e4=fd[0],finite_diff_y_1e4=fd[1],finite_diff_psi_1e4=fd[2],
     finite_diff_x_1e3=fd[3],finite_diff_y_1e3=fd[4],finite_diff_psi_1e3=fd[5],
     jac_fd_x_absdiff=abs(H[0]-fd[0]),
     jac_fd_y_absdiff=abs(H[1]-fd[1]),
     near_pole_huge_error=bool(abs(r.s_los-h)>.1),
     presumed_cause="undetermined; check polar coordinate interpolation & antenna FFD parity"))
 aa=pd.DataFrame(rows)
 aa.sort_values("rho_m").to_csv(o/"NEAR_POLE_ACTUAL_LOS_AND_JACOBIAN.csv",index=False)
 total=[]
 for c,g in data.groupby("case"):
  anchor=cases[c]["anchor_xyz"]
  rr=np.hypot(g.true_x-anchor[0],g.true_y-anchor[1])
  for lo,hi in [(0,.05),(.05,.1),(.1,.2),(.2,.5),(.5,1),(1,2),(2,np.inf)]:
   sub=g[(rr>=lo)&(rr<hi)]
   if len(sub)==0:continue
   v=sub.s_los-sub.s_lut_truth
   total.append(dict(case=c,rho_bin=f"{lo}-{hi}",n=len(sub),
                     rms_lut=float(np.sqrt(np.mean(v*v))),max_abs=float(abs(v).max()),
                     n_gt01=int((abs(v)>.1).sum())))
 pd.DataFrame(total).to_csv(o/"NEAR_POLE_LOS_RISK_BY_RADIUS.csv",index=False)
 # Different approach bearings must collapse to unique physical LoS at rho->0;
 # if a LUT with direction basis interpolation is singular, its predictions
 # may depend spuriously on the approach direction even at small rho.
 ring=[]
 for case in ("R5_aA_m0","R5_aB_m0"):
  cfg=cases[case]
  a=cfg["anchor_xyz"]
  for yaw in (0.,45.,90.,135.):
   for rho in (0.,.00001,.0001,.001,.01,.03,.05,.10,.2,.5,1.0):
    vals=[]
    jj=[]
    for az in np.arange(0,360,45):
     x=float(a[0]+rho*math.cos(math.radians(az)))
     y=float(a[1]+rho*math.sin(math.radians(az)))
     val,jac=s_model(lut,a,cfg["robot_z"],x,y,math.radians(yaw),cfg["mount_deg"],with_jac=True)
     vals.append(float(val));jj.append(float(np.linalg.norm(jac[:2])))
    ring.append(dict(case=case,yaw_deg=yaw,rho_m=rho,
                     model_s_min=min(vals),model_s_max=max(vals),
                     model_s_range=max(vals)-min(vals),
                     Jxy_max=max(jj),Jxy_median=float(np.median(jj))))
 pd.DataFrame(ring).to_csv(o/"LUT_POLAR_APPROACH_DIRECTION_SWEEP.csv",index=False)
 close=aa[aa.rho_m<.1]
 far=aa[(aa.rho_m>=.1)&(aa.rho_m<=.5)]
 summary=dict(state="EXECUTED_FROZEN_LUT_POLAR_AUDIT",
  n_native_los_poses=9519,n_within_rho_0p1m=int(len(close)),
  n_rho_0p1_large_error=int((abs(close.e_LUT)>.1).sum()),
  n_rho_0p1_small_multipath_error=int((abs(close.e_MP)<.001).sum()),
  n_pole_0p1_rms=float(np.sqrt(np.mean(close.e_LUT**2))),
  n_normal_rho_0p1_to_0p5=int(len(far)),
  worst_close=close.iloc[np.argmax(abs(close.e_LUT))].to_dict() if len(close) else None,
  important_limits=["Jacobian continuity tested for frozen LUT but no fresh Sionna native H outside 9519 stored poses",
                    "Original F01 L1 failure remains open even if global RMS small",
                    "A strict rho gate uses estimated pose, not truth; impact on EKF not tested by this script",
                    "Near-pole high s mismatch is not multipath if direct full-LoS difference is near zero"])
 (o/"STATUS.json").write_text(json.dumps(summary,indent=2,allow_nan=False))
 with (o/"REPORT_KO.md").open("w") as f:
  f.write("# 앵커 수직입사 인근 LUT 값/gradient 검증\n\n")
  f.write(f"기존 9519 native direct LOS labels, rho<0.1m {len(close)} poses, |eLUT|>.1 {int((abs(close.e_LUT)>.1).sum()}.\n\n")
  f.write("## 실제 저장 RF native LOS points\n\n")
  f.write(close[["case","pose_id","rho_m","s_LOS_direct","s_LUT_model","e_LUT","Jxy_norm","jac_fd_x_absdiff","jac_fd_y_absdiff"]].to_markdown(index=False,floatfmt=".5f"))
  f.write("\n\n## 한계\n\nRing sweep은 LUT 연속성의 수치 검사만 가능; 새 위치 LoS FFD reference가 아니므로 root cause가 interpolation인지 실제 physical polar basis인지 확정하려면 추가 native H 또는 직접 FFD bank contraction이 필요.\n")
 print("POLE_AUDIT_RESULT",json.dumps({k:v for k,v in summary.items() if k!="worst_close"},allow_nan=False),flush=True)
if __name__=="__main__":main()
