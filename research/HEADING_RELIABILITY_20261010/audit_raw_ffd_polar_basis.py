#!/usr/bin/env python3
"""Optional true original LP FFD bank Cartesian theta=0 pole-gauge validation.

If git-lfs materialized NPZ files are unavailable, explicitly report BLOCKED.
Never substitute synthetic bank fields for original SHA-verified FFD.
"""
from __future__ import annotations
import hashlib,json,math,argparse
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
import sys
sys.path.insert(0,str(RUN/"source/src"))
from qclean_uwb.drivesim.pattern_apply import Bank,sph_basis
from qclean_uwb.drivesim.hs_lut import HsLut,los_s_direct

BANK_SHA={"LP_plus45_bank.npz":"b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
          "LP_minus45_bank.npz":"39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"}
def shafile(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for block in iter(lambda:f.read(4*1024*1024),b""):h.update(block)
 return h.hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument("--out",required=True,type=Path);args=parser.parse_args()
 o=args.out;o.mkdir(parents=True,exist_ok=True)
 state=dict(status="BLOCKED_LFS_BANK_NOT_MATERIALIZED",
   report="Raw FFD pole evaluation impossible without original 247MB git-lfs bank bytes",
   bank_expected_sha=BANK_SHA)
 for nm in BANK_SHA:
  p=ROOT/nm
  if not p.exists():
   state["missing"]=nm;(o/"STATUS.json").write_text(json.dumps(state,indent=2));return
  if p.stat().st_size<200:
   state["pointer_only"]=nm;(o/"STATUS.json").write_text(json.dumps(state,indent=2));return
  actual=shafile(p)
  if actual!=BANK_SHA[nm]:
   state["status"]="FAIL_BANK_HASH";state["wrong_sha"]={nm:actual}
   (o/"STATUS.json").write_text(json.dumps(state,indent=2));return
 banks=[]
 for p in BANK_SHA:
  z=np.load(ROOT/p,allow_pickle=False)
  banks.append(Bank(z))
 assert np.array_equal(banks[0].freqs_hz,banks[1].freqs_hz)
 results=[]
 for name,b in zip(BANK_SHA.keys(),banks):
  bins=[0,128,256]
  print(name,"theta",len(b.theta),"phi",len(b.phi),
        "e_theta",b.e_theta.shape,"e_phi",b.e_phi.shape,flush=True)
  for qbin in bins:
   for idx in (0,1,2):
    theta=float(b.theta[idx])
    phi=np.asarray(b.phi,float)
    # Reconstruct absolute complex Cartesian E vectors from polar components
    # on the original raw .npz samples at each φ grid point.
    ct=np.cos(theta);st=np.sin(theta)
    eTheta=np.stack([ct*np.cos(phi),ct*np.sin(phi),-st*np.ones_like(phi)],axis=-1)
    ePhi=np.stack([-np.sin(phi),np.cos(phi),np.zeros_like(phi)],axis=-1)
    a=b.e_theta[qbin,idx,:][:,None]
    c=b.e_phi[qbin,idx,:][:,None]
    vec=a*eTheta+c*ePhi
    mean=vec.mean(axis=0)
    amp=np.linalg.norm(vec,axis=1)
    cross=float(np.sqrt(np.mean(np.sum(abs(vec-mean)**2,axis=1)))/max(np.linalg.norm(mean),1e-30))
    variation=float(np.max(np.linalg.norm(vec-mean,axis=1))/max(np.linalg.norm(mean),1e-30))
    results.append(dict(port=name,freq_hz=float(b.freqs_hz[qbin]),
                        theta_deg=math.degrees(theta),phi_count=len(phi),
                        e_cart_mean_amp=float(np.linalg.norm(mean)),
                        relative_complex_std_across_phi=cross,
                        relative_complex_maxdelta_across_phi=variation,
                        mean_amp=float(amp.mean())))
 tab=pd.DataFrame(results)
 tab.to_csv(o/"ORIGINAL_FFD_COMPLEX_CARTESIAN_POLE_CONTINUITY.csv",index=False)
 # Direct bank contractions from the native original FFD pattern should be
 # compared against original matched Sionna LOS values at the actual points.
 label=pd.read_csv(RUN/"OUTPUT/02_LABELS_EVAL_ONLY.csv")
 caseinfo=json.loads((ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/CASES.json").read_text())
 caseby={c["case"]:c for c in caseinfo}
 rows=[]
 for r in label.itertuples():
  case=caseby[r.case];a=case["anchor_xyz"]
  u=r.true_x-a[0];v=r.true_y-a[1]
  rho=math.hypot(u,v)
  if rho>=.15:continue
  th=math.degrees(math.atan2(rho,a[2]-case["robot_z"]))
  phit=math.degrees(math.atan2(-v,u))
  phir=(math.degrees(math.atan2(-v,-u))-r.true_yaw_deg-case["mount_deg"]+180)%360-180
  direct=los_s_direct(banks,th,phit,phir,measure="fp")
  rows.append(dict(case=r.case,pose_id=r.pose_id,rho_m=rho,theta_deg=th,
            native_solver_s=r.s_los,direct_bank_s=direct,
            original_lut_s=r.s_lut_truth,
            native_minus_direct=r.s_los-direct,
            direct_minus_lut=direct-r.s_lut_truth))
 pd.DataFrame(rows).to_csv(o/"ORIGINAL_BANK_DIRECT_CONTRACTION_VS_NATIVE_LOS.csv",index=False)
 s=np.asarray([abs(z["native_minus_direct"]) for z in rows])
 state.update(status="RAW_FFD_BANK_VERIFIED_AND_POLE_TEST_EXECUTED",
       n_direct_native_comparisons=len(rows),
       native_vs_direct_los_s_max_abs=float(max(s)) if len(s) else None,
       raw_theta0_metrics=json.loads(tab[tab.theta_deg.abs()<1e-7].to_json(orient="records")),
       limitation="Raw e_theta/e_phi at theta0 can be coordinate gauge dependent; judge Cartesian E and matched direct/native LoS, not spherical component variation alone")
 (o/"STATUS.json").write_text(json.dumps(state,indent=2,allow_nan=False))
 with (o/"RESULTS_KO.md").open("w") as f:
  f.write("# 원본 SHA 검증 FFD LP +/-45 극점 Cartesian 필드 직접 계산\n\n")
  f.write(tab.to_markdown(index=False,floatfmt=".6f"))
  f.write("\n\n## 직접 FFD contraction vs native Sionna LOS\n\n")
  f.write(pd.DataFrame(rows).to_markdown(index=False,floatfmt=".6f"))
 print("RAW_FFD_RESULT",json.dumps(state,ensure_ascii=False,allow_nan=False)[:8500],flush=True)
if __name__=="__main__":main()
